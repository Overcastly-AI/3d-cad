"""The plugin registry and the one way a custom feature is expanded (RESEARCH §23).

* :class:`PluginRegistry` keeps EVERY released version of every plugin. A
  stored feature pins ``plugin_id`` + ``plugin_version`` and is always
  expanded by that version's expander, so a release never changes a stored
  part; updating is an explicit edit of the pin, as in Onshape.
* :func:`canonical_inputs` checks a feature's inputs against the pinned
  manifest: unknown names, kinds, options, bounds; defaults filled in; numbers
  in the type their unit says (a length ``30`` is stored ``30.0``, which is
  what lets ``expressions`` drive it).
* :func:`expand` runs the expander under the caps (5,000 members, 2 s of CPU,
  10 s of wall-clock) and
  validates what comes back exactly as a user's features are validated: the
  same pydantic models, declared roles, unique ``(role, index)``, and every
  reference to a strictly earlier feature of an allowed type (§2.2).
* Hosting (a window in a wall): a feature (or feature-list) input with
  ``plugin_ids`` must name earlier custom features of them, and a ``host``
  input's target receives the hosted feature's inputs as ``ExpandInputs.hosted``
  (:func:`host_of`). Only inputs cross, never expansions, so a host and its
  hosted features cannot form a cycle.

Every failure is a :class:`~loft_plugins.api.PluginError` with a typed code.
"""

import math
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import get_args

from loft_wire.expr import Quantity
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    CustomInputValue,
    ExpandedMember,
    Feature,
    FeatureRef,
    feature_references,
)
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    MAX_PLUGIN_EXPANSION,
    PLUGIN_EXPAND_TIME_LIMIT_S,
    PLUGIN_EXPAND_WALL_LIMIT_S,
    PLUGIN_EXPANSION_INVALID,
    PLUGIN_EXPANSION_TIMEOUT,
    PLUGIN_EXPANSION_TOO_LARGE,
    PLUGIN_INPUT_INVALID,
    PLUGIN_NOT_FOUND,
    PLUGIN_VERSION_NOT_FOUND,
    AngleInput,
    ChoiceInput,
    CountInput,
    FeatureListInput,
    FeatureReferenceInput,
    LengthInput,
    MaterialInput,
    PluginCatalog,
    PluginInput,
    PluginManifest,
    ProfileInput,
    SegmentsInput,
    member_id,
    semver_key,
)
from pydantic import TypeAdapter, ValidationError

from loft_plugins.api import ExpandInputs, Hosted, InputValue, Plugin, PluginError

_FEATURE: TypeAdapter[Feature] = TypeAdapter(Feature)

#: The clocks the expansion budget reads (module attributes so tests can fake
#: them). The CPU clock is the CALLING thread's: an expansion runs in-process,
#: in the thread that calls :func:`expand`, so other requests' work and a
#: loaded machine do not count against it.
_cpu_clock = time.thread_time
_wall_clock = time.monotonic


class PluginRegistry:
    """Every released version of every registered plugin."""

    def __init__(self, plugins: Iterable[Plugin] = ()) -> None:
        self._plugins: dict[str, dict[str, Plugin]] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: Plugin) -> None:
        """Add one released version. Re-registering a version is refused: a
        release is immutable, so a changed expansion is a NEW version."""
        manifest = plugin.manifest
        versions = self._plugins.setdefault(manifest.id, {})
        if manifest.version in versions:
            raise ValueError(f"{manifest.id} {manifest.version} is registered twice")
        versions[manifest.version] = plugin

    def get(self, plugin_id: str, version: str) -> Plugin:
        """The pinned version, or ``plugin_not_found`` /
        ``plugin_version_not_found``."""
        versions = self._plugins.get(plugin_id)
        if versions is None:
            raise PluginError(
                PLUGIN_NOT_FOUND,
                f"No plugin {plugin_id!r} is installed on this server.",
            )
        plugin = versions.get(version)
        if plugin is None:
            raise PluginError(
                PLUGIN_VERSION_NOT_FOUND,
                f"Plugin {plugin_id!r} has no released version {version}.",
            )
        return plugin

    def latest(self, plugin_id: str) -> Plugin:
        """The newest released version (what a new feature is inserted with)."""
        versions = self._plugins.get(plugin_id)
        if not versions:
            raise PluginError(PLUGIN_NOT_FOUND, f"No plugin {plugin_id!r}.")
        return versions[max(versions, key=semver_key)]

    def catalog(self) -> PluginCatalog:
        """Every manifest, by id, newest version first, the newest flagged."""
        manifests: list[PluginManifest] = []
        for plugin_id in sorted(self._plugins):
            ordered = sorted(self._plugins[plugin_id], key=semver_key, reverse=True)
            for position, version in enumerate(ordered):
                manifest = self._plugins[plugin_id][version].manifest
                manifests.append(manifest.model_copy(update={"latest": position == 0}))
        return PluginCatalog(plugins=manifests)


# --- Inputs ----------------------------------------------------------------------


def _refuse(item: PluginInput, why: str) -> PluginError:
    return PluginError(
        PLUGIN_INPUT_INVALID,
        f"Input {item.label!r} ({item.name}): {why}",
        input=item.name,
    )


def _number(
    item: LengthInput | AngleInput, value: CustomInputValue, bounds: bool
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(item, "must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise _refuse(item, "must be finite")
    low = item.minimum
    if (
        bounds
        and low is not None
        and (number < low or (item.exclusive_minimum and number == low))
    ):
        above = "above" if item.exclusive_minimum else "at least"
        raise _refuse(item, f"must be {above} {low:g} {item.unit}")
    if bounds and item.maximum is not None and number > item.maximum:
        raise _refuse(item, f"must be at most {item.maximum:g} {item.unit}")
    return number


def _count(item: CountInput, value: CustomInputValue, bounds: bool) -> int:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refuse(item, "must be a whole number")
    if bounds and not item.minimum <= value <= item.maximum:
        raise _refuse(item, f"must be from {item.minimum} to {item.maximum}")
    return value


def _feature_list(
    item: FeatureListInput, value: CustomInputValue | None
) -> list[FeatureRef] | None:
    """A feature-list input's stored value: the picks in order, or ``None``
    (not stored) for an empty pick of an optional input."""
    if value is None:
        if item.min_items == 0:
            return None
        raise _refuse(item, f"pick at least {item.min_items}")
    if not isinstance(value, list) or not all(isinstance(v, FeatureRef) for v in value):
        raise _refuse(item, "must name features")
    picks = [v for v in value if isinstance(v, FeatureRef)]
    if len(picks) < item.min_items:
        raise _refuse(item, f"pick at least {item.min_items}")
    if len(picks) > item.max_items:
        raise _refuse(item, f"pick at most {item.max_items}")
    if len({ref.feature_id for ref in picks}) != len(picks):
        raise _refuse(item, "names a feature twice")
    return picks


def _segments(item: SegmentsInput, value: CustomInputValue | None) -> list[str] | None:
    """A segments input's stored value: the line ids in order, or ``None``
    (not stored) for an empty pick of an optional input. Whether each id is
    a line of the outline is the plugin's check: only it reads the sketch."""
    if value is None:
        if item.min_items == 0:
            return None
        raise _refuse(item, f"pick at least {item.min_items}")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _refuse(item, "must name lines of the outline")
    picks = [v for v in value if isinstance(v, str)]
    if len(picks) < item.min_items:
        raise _refuse(item, f"pick at least {item.min_items}")
    if len(picks) > item.max_items:
        raise _refuse(item, f"pick at most {item.max_items}")
    if len(set(picks)) != len(picks):
        raise _refuse(item, "names a line twice")
    return picks


def _canonical(
    item: PluginInput, value: CustomInputValue | None, bounds: bool
) -> CustomInputValue | None:
    """The stored value of one input (``None``: left empty, not stored)."""
    match item:
        case LengthInput() | AngleInput():
            return _number(item, item.default if value is None else value, bounds)
        case CountInput():
            return _count(item, item.default if value is None else value, bounds)
        case ChoiceInput():
            value = item.default if value is None else value
            if value not in [option.value for option in item.options]:
                raise _refuse(item, "is not one of its options")
            return value
        case MaterialInput():
            value = item.default if value is None else value
            if value is not None and value not in get_args(MaterialKey):
                raise _refuse(item, "is not a library material")
            return value
        case FeatureListInput():
            return _feature_list(item, value)
        case SegmentsInput():
            return _segments(item, value)
        case ProfileInput() | FeatureReferenceInput():
            if value is None:
                if isinstance(item, FeatureReferenceInput) and item.optional:
                    return None
                raise _refuse(item, "pick a feature")
            if not isinstance(value, FeatureRef):
                raise _refuse(item, "must name a feature")
            return value


def canonical_inputs(
    manifest: PluginManifest,
    inputs: Mapping[str, CustomInputValue],
    *,
    bounds: bool = True,
) -> dict[str, CustomInputValue]:
    """*inputs* checked against *manifest*, defaults filled in, in manifest
    order. ``bounds=False`` checks only kinds (before formulas are resolved:
    a number a formula will replace is not yet the value to bound)."""
    declared = {item.name for item in manifest.inputs}
    unknown = sorted(set(inputs) - declared)
    if unknown:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"{manifest.title} has no input {unknown[0]!r}.",
            input=unknown[0],
        )
    out: dict[str, CustomInputValue] = {}
    for item in manifest.inputs:
        value = _canonical(item, inputs.get(item.name), bounds)
        if value is not None:
            out[item.name] = value
    return out


def settle_inputs(
    plugin: Plugin,
    feature_id: uuid.UUID,
    inputs: Mapping[str, CustomInputValue],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    *,
    parameters: Mapping[str, Quantity] | None = None,
) -> dict[str, CustomInputValue]:
    """The canonical *inputs* a write STORES: unchanged unless the plugin
    makes a write-time choice (``Plugin.settle``), checked again against the
    manifest. Raises :class:`PluginError`."""
    if plugin.settle is None:
        return dict(inputs)
    values: dict[str, InputValue] = {item.name: None for item in plugin.manifest.inputs}
    values.update(inputs)
    context = ExpandInputs(feature_id, values, earlier, parameters=parameters or {})
    settled = plugin.settle(context)
    raw = {
        name: value
        for name, value in settled.items()
        if value is not None and name in values
    }
    return canonical_inputs(plugin.manifest, raw)


# --- Hosting ---------------------------------------------------------------------


def host_of(
    manifest: PluginManifest, inputs: Mapping[str, CustomInputValue]
) -> uuid.UUID | None:
    """The feature *inputs* name as host (a window's wall), or ``None``."""
    item = manifest.host_input()
    value = None if item is None else inputs.get(item.name)
    return value.feature_id if isinstance(value, FeatureRef) else None


def _check_plugin_references(
    manifest: PluginManifest,
    inputs: Mapping[str, CustomInputValue],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
) -> None:
    """A feature input with ``plugin_ids`` names an EARLIER custom feature of
    one of those plugins: a window whose host is missing, later, or not a
    wall is refused here, before its plugin runs."""
    for item in manifest.inputs:
        if (
            not isinstance(item, FeatureReferenceInput | FeatureListInput)
            or item.plugin_ids is None
        ):
            continue
        value = inputs.get(item.name)
        picks = value if isinstance(value, list) else [value]
        wanted = " or ".join(item.plugin_ids)
        for pick in picks:
            if not isinstance(pick, FeatureRef):
                continue
            target = earlier.get(pick.feature_id)
            if target is None:
                raise _refuse(item, f"names no earlier feature; pick a {wanted}")
            if not isinstance(target, CustomFeature):
                raise _refuse(item, f"names a {target.type}, not a {wanted}")
            if target.params.plugin_id not in item.plugin_ids:
                raise _refuse(
                    item, f"names a {target.params.plugin_id}, not a {wanted}"
                )


# --- Expansion -------------------------------------------------------------------


def _invalid(title: str, why: str) -> PluginError:
    return PluginError(
        PLUGIN_EXPANSION_INVALID, f"{title} produced an invalid feature: {why}"
    )


def validate_members(
    feature_id: uuid.UUID,
    members: Sequence[ExpandedMember],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    *,
    title: str = "This custom feature",
) -> None:
    """A STORED expansion's integrity, with or without its plugin (a ``.loft``
    import): every member id is the one :func:`member_id` derives, and every
    reference passes §2.2. Raises ``plugin_expansion_invalid``."""
    seen: set[uuid.UUID] = set()
    for member in members:
        if member.id != member_id(feature_id, member.role, member.index, member.name):
            raise _invalid(title, f"{member.role}/{member.index} has a foreign id")
        if member.id in seen:
            raise _invalid(title, f"{member.role}/{member.index} repeats an id")
        seen.add(member.id)
    _check_references(title, list(members), earlier)


def _check_references(
    title: str,
    members: list[ExpandedMember],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
) -> None:
    """§2.2 on every member: each reference names a STRICTLY earlier base
    feature (one before the custom feature, or an earlier member of this
    expansion) of a type its slot accepts."""
    seen: dict[uuid.UUID, str] = {}
    for member in members:
        for reference in feature_references(member.feature):
            target = reference.ref.feature_id
            if target in seen:
                target_type = seen[target]
            elif target in earlier and earlier[target].type != "custom":
                target_type = earlier[target].type
            else:
                raise _invalid(
                    title,
                    f"{member.role}/{member.index} slot {reference.slot!r} names "
                    "no earlier feature",
                )
            if target_type not in reference.allowed_types:
                raise _invalid(
                    title,
                    f"{member.role}/{member.index} slot {reference.slot!r} cannot "
                    f"name a {target_type!r} feature",
                )
        seen[member.id] = member.feature.type


def expand(
    plugin: Plugin,
    feature_id: uuid.UUID,
    inputs: Mapping[str, CustomInputValue],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    *,
    hosted: Sequence[Hosted] = (),
    cpu_limit_s: float = PLUGIN_EXPAND_TIME_LIMIT_S,
    wall_limit_s: float = PLUGIN_EXPAND_WALL_LIMIT_S,
    parameters: Mapping[str, Quantity] | None = None,
) -> list[ExpandedMember]:
    """The members of custom feature *feature_id*, from canonical *inputs*.

    *earlier* is every feature before it (base features by id, and earlier
    custom features with their members by member id); *hosted* the later
    features naming it as host, in tree order. Raises
    :class:`PluginError`: the plugin's own refusal, ``plugin_expansion_too_large``
    past 5,000 members, ``plugin_expansion_timeout`` past the CPU budget or
    the wall-clock backstop (checked as each member is yielded, and at the
    end), or
    ``plugin_expansion_invalid`` for a member the authoring checks refuse.
    """
    manifest = plugin.manifest
    title = f"{manifest.title} {manifest.version}"
    _check_plugin_references(manifest, inputs, earlier)
    values: dict[str, InputValue] = {item.name: None for item in manifest.inputs}
    values.update(inputs)
    roles = {item.role for item in manifest.members}
    cpu_deadline = _cpu_clock() + cpu_limit_s
    wall_deadline = _wall_clock() + wall_limit_s
    members: list[ExpandedMember] = []
    keys: set[tuple[str, int]] = set()
    ids: set[uuid.UUID] = set()

    def check_time() -> None:
        if _cpu_clock() > cpu_deadline:
            raise PluginError(
                PLUGIN_EXPANSION_TIMEOUT,
                f"{manifest.title} used more than {cpu_limit_s:g} s of CPU time "
                "to expand.",
            )
        if _wall_clock() > wall_deadline:
            raise PluginError(
                PLUGIN_EXPANSION_TIMEOUT,
                f"{manifest.title} took longer than {wall_limit_s:g} s "
                "(wall-clock) to expand.",
            )

    try:
        context = ExpandInputs(
            feature_id, values, earlier, hosted, parameters=parameters or {}
        )
        for member in plugin.expand(context):
            if len(members) >= MAX_PLUGIN_EXPANSION:
                raise PluginError(
                    PLUGIN_EXPANSION_TOO_LARGE,
                    f"{manifest.title} expands to more than {MAX_PLUGIN_EXPANSION} "
                    "features; reduce its counts.",
                )
            check_time()
            if member.role not in roles:
                raise _invalid(title, f"undeclared role {member.role!r}")
            key = (member.role, member.index)
            if key in keys:
                raise _invalid(title, f"{member.role}/{member.index} twice")
            keys.add(key)
            identity = member_id(feature_id, member.role, member.index, member.name)
            if identity in ids:
                raise _invalid(title, f"{member.role}/{member.name} twice")
            ids.add(identity)
            try:
                feature = _FEATURE.validate_python(
                    member.feature.model_dump(mode="json")
                )
                members.append(
                    ExpandedMember(
                        role=member.role,
                        index=member.index,
                        name=member.name,
                        id=identity,
                        feature=feature,
                        metadata=member.metadata,
                    )
                )
            except ValidationError as exc:
                detail = exc.errors()[0]
                where = "/".join(str(part) for part in detail["loc"])
                raise _invalid(
                    title, f"{member.role}/{member.index} {where}: {detail['msg']}"
                ) from exc
    except PluginError:
        raise
    except Exception as exc:  # a plugin bug is the feature's error, never a 500
        raise _invalid(title, f"{type(exc).__name__}: {exc}") from exc
    check_time()
    _check_references(title, members, earlier)
    return members
