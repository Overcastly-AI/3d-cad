"""Custom features: where documents runs the plugins (PLUGIN-REGISTRY, RESEARCH §23).

A custom feature is one stored row (``type: "custom"``) pinning a plugin and
version, holding its inputs and its LAST EXPANSION. Documents expands it

* **on every write** of the feature (:func:`prepare_custom_write`): inputs
  checked against the pinned manifest, formulas resolved (§20), the plugin
  run under its caps, and the members stored with the row. Any failure is a
  422 with the plugin's typed code;
* **once per evaluation request** (:func:`evaluation_entries`, where formulas
  are already resolved): re-expanded with the part's current parameters and
  the features before it, so geometry receives base features only. A
  re-expansion that fails keeps the stored members and sends them with an
  ``input_error`` (geometry builds nothing for them), as a formula that no
  longer resolves does. A server WITHOUT the plugin (or the pinned version)
  sends the stored members as they are: the part still rebuilds, read-only;
* **on a ``.loft`` export or a version** (:func:`refresh_expansions`): the
  stored expansion is brought up to date, so a file opened elsewhere carries
  what this server would build.

The members' ids are ``member_id(<feature-id>, role, n)``; a later feature
may reference a member (a pick on generated geometry), and its dependency
edge is materialised to the custom feature's row.
"""

import uuid
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from fastapi import APIRouter
from loft_plugins import (
    PLUGIN_UPDATE_UNAVAILABLE,
    REGISTRY,
    ExpandInputs,
    Hosted,
    Plugin,
    PluginError,
    PluginRegistry,
    PluginUpdate,
    host_of,
    settle_inputs,
    update_for,
    updated_inputs,
    validate_members,
)
from loft_plugins import canonical_inputs as _canonical
from loft_plugins import expand as _expand
from loft_plugins.builtin.crawl_space import MIN_UNTREATED_CRAWL_IN
from loft_plugins.builtin.house import stored_inputs
from loft_plugins.builtin.roof_ceiling import CEILING_BESIDE
from loft_plugins.builtin.roof_outline import ceiling_joist_note
from loft_plugins.builtin.roof_sheathing import MIN_OVERLAP_IN3, through_sheathing
from loft_plugins.builtin.stair import STAIR, stair_notes
from loft_plugins.builtin.wall_finish import finish_notes
from loft_plugins.updates import UpdateEffect, update_effect
from loft_wire.expr import Quantity
from loft_wire.feature_input import PARAMETER_VALUE_INVALID
from loft_wire.feature_resolve import (
    FeatureExpressionError,
    evaluation_input,
    parameter_values,
    resolve_dimensions,
    resolve_feature,
)
from loft_wire.features import (
    AUTHORED_FEATURES,
    BODY_AFFECTING_FEATURE_TYPES,
    MAX_TREE_FEATURES,
    AuthoredEnvelope,
    CustomFeature,
    CustomInputValue,
    EvaluatedFeatureInput,
    ExpandedMember,
    FeatureDependent,
    FeatureDependents,
    FeatureError,
    FeatureRef,
    FeatureReference,
    feature_references,
)
from loft_wire.legacy_twist import (
    EXTRUDE_TWIST_DEPRECATED_CODE,
    EXTRUDE_TWIST_DEPRECATED_MESSAGE,
    authors_extrude_twist,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugin_warning import (
    CEILING_JOISTS_OMITTED,
    CRAWL_HEIGHT_LOW,
    ROOF_THROUGH_SHEATHING,
    PluginWarning,
)
from loft_wire.plugins import (
    PLUGIN_EXPANSION_TOO_LARGE,
    PLUGIN_READ_ONLY,
    FeatureListInput,
    FeatureReferenceInput,
    PluginCatalog,
    ProfileInput,
    member_id,
)
from loft_wire.tree_edits import MAX_UPDATE_ADDS
from loft_wire.tree_edits import PluginUpdate as PluginUpdateOffer
from py_kit import ConflictError, ValidationApiError, get_logger
from pydantic import ValidationError

from documents import db
from documents.feature_expressions import load_feature
from documents.parts import Principal

_logger = get_logger("documents.custom_features")

#: The plugins this server runs. A module attribute so a test can install a
#: registry with fixture plugins (``loft_plugins.testing``).
PLUGINS: PluginRegistry = REGISTRY

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(owner_id: Principal) -> PluginCatalog:
    """Every released version of every installed plugin, newest first: what
    the Build toolbar and each custom feature's form are generated from.
    Principal-gated like the document routes (the catalog is not scoped)."""
    del owner_id
    return PLUGINS.catalog()


# --- reading stored rows -----------------------------------------------------------


def stored_members(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """A custom row's stored expansion, as raw JSON (no validation)."""
    members = params.get("expansion")
    return cast(list[dict[str, Any]], members) if isinstance(members, list) else []


def member_targets(
    rows: Sequence[db.Feature],
) -> dict[uuid.UUID, tuple[db.Feature, str]]:
    """member id -> (the custom row that owns it, the member's feature type)."""
    out: dict[uuid.UUID, tuple[db.Feature, str]] = {}
    for row in rows:
        if row.type != "custom":
            continue
        for member in stored_members(row.params):
            feature = member.get("feature")
            if isinstance(feature, dict):
                kind = str(cast(dict[str, Any], feature).get("type"))
                out[uuid.UUID(str(member["id"]))] = (row, kind)
    return out


def row_size(row: db.Feature) -> int:
    """How many base features *row* sends geometry."""
    return len(stored_members(row.params)) if row.type == "custom" else 1


def expanded_size(rows: Iterable[db.Feature]) -> int:
    """How many base features *rows* send geometry: custom rows by member."""
    return sum(row_size(row) for row in rows)


def check_tree_size(total: int, what: str = "The part") -> None:
    """The write-side twin of ``EvaluateTreeRequest``'s ``MAX_TREE_FEATURES``
    bound, counted AFTER custom-feature expansion: a stored tree the evaluation
    contract cannot carry would make every later evaluation of the part fail.
    422 ``feature_limit_exceeded`` over it."""
    if total > MAX_TREE_FEATURES:
        raise ValidationApiError(
            f"{what} would send {total} features to geometry (custom features "
            f"count by their members); the limit is {MAX_TREE_FEATURES}.",
            code="feature_limit_exceeded",
            details={"max_features": MAX_TREE_FEATURES, "expanded": total},
        )


def row_types(row: db.Feature) -> set[str]:
    """The base feature types *row* contributes (its own, or its members')."""
    if row.type != "custom":
        return {row.type}
    return {
        str(cast(dict[str, Any], m.get("feature", {})).get("type"))
        for m in stored_members(row.params)
    }


def is_body_affecting(row: db.Feature) -> bool:
    return bool(row_types(row) & BODY_AFFECTING_FEATURE_TYPES)


def _earlier_from_rows(
    rows: Sequence[db.Feature],
    overrides: Mapping[uuid.UUID, AuthoredEnvelope] | None = None,
    parameters: Mapping[str, Quantity] | None = None,
) -> dict[uuid.UUID, AuthoredEnvelope]:
    """Every row's envelope by id, and every stored member's by member id.
    *overrides* replaces a row's stored envelope (a write not yet stored).
    A sketch is handed over with its dimension formulas resolved against
    *parameters* (:func:`_as_plugins_see`)."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for row in rows:
        envelope = (overrides or {}).get(row.id) or load_feature(row)[0]
        earlier[row.id] = _as_plugins_see(envelope, parameters or {})
        if isinstance(envelope, CustomFeature):
            for member in envelope.params.expansion or []:
                earlier[member.id] = member.feature
    return earlier


def _as_plugins_see(
    envelope: AuthoredEnvelope, parameters: Mapping[str, Quantity]
) -> AuthoredEnvelope:
    """What a later custom feature reads of *envelope*: a sketch with every
    driving dimension's formula evaluated (``336 in``, a parameter ``L``),
    as geometry solves it, so an outline's walls, floor and roof follow the
    sketch the user sees (BUILDING-OUTLINE). Everything else as stored."""
    return resolve_dimensions(envelope, parameters)


# --- references ------------------------------------------------------------------


def custom_references(envelope: CustomFeature) -> list[FeatureReference]:
    """The feature inputs' references, with the types their manifest allows.

    Without the plugin (a read-only carry) every reference is kept with any
    type allowed: the edges still protect what the stored expansion names."""
    try:
        manifest = PLUGINS.get(
            envelope.params.plugin_id, envelope.params.plugin_version
        ).manifest
    except PluginError:
        return [
            FeatureReference(slot, value, frozenset({"*"}))
            for name, stored in envelope.params.inputs.items()
            for slot, value in _picks(name, stored)
        ]
    out: list[FeatureReference] = []
    for item in manifest.inputs:
        stored = envelope.params.inputs.get(item.name)
        for slot, value in _picks(item.name, stored):
            if isinstance(item, ProfileInput):
                out.append(FeatureReference(slot, value, frozenset({"sketch"})))
            elif isinstance(item, FeatureReferenceInput | FeatureListInput):
                out.append(FeatureReference(slot, value, frozenset(item.feature_types)))
    return out


def _picks(name: str, value: CustomInputValue | None) -> list[tuple[str, FeatureRef]]:
    """The references one stored input holds, by slot: ``inputs/<name>``, or
    ``inputs/<name>/<i>`` for each pick of a feature list. A segments input's
    line ids (BUILDING-OUTLINE) are sketch-local names, not references."""
    if isinstance(value, FeatureRef):
        return [(f"inputs/{name}", value)]
    if isinstance(value, list):
        return [
            (f"inputs/{name}/{i}", ref)
            for i, ref in enumerate(value)
            if isinstance(ref, FeatureRef)
        ]
    return []


def authored_references(envelope: AuthoredEnvelope) -> list[FeatureReference]:
    """§2.2 references of any stored feature, custom ones included."""
    if isinstance(envelope, CustomFeature):
        return custom_references(envelope)
    return list(feature_references(envelope))


# --- writes ----------------------------------------------------------------------


def _refuse(exc: PluginError) -> ValidationApiError:
    details: dict[str, Any] = {}
    if exc.input is not None:
        details["input"] = exc.input
    return ValidationApiError(exc.message, code=exc.code, details=details)


def _same_pin_and_inputs(stored: db.Feature, envelope: CustomFeature) -> bool:
    return (
        stored.type == "custom"
        and stored.params.get("plugin_id") == envelope.params.plugin_id
        and stored.params.get("plugin_version") == envelope.params.plugin_version
        and stored.params.get("inputs")
        == envelope.params.model_dump(mode="json")["inputs"]
        and stored.expressions == envelope.expressions
    )


def _with(
    envelope: CustomFeature,
    inputs: dict[str, CustomInputValue],
    members: list[ExpandedMember] | None,
) -> CustomFeature:
    params = envelope.params.model_copy(update={"inputs": inputs, "expansion": members})
    return envelope.model_copy(update={"params": params})


def _expanded(
    plugin: Plugin,
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    parameters: Mapping[str, Quantity],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    hosted: Sequence[Hosted] = (),
) -> CustomFeature:
    """Inputs typed, formulas resolved, bounds checked, write-time choices
    settled (a window's "nearer the origin" stored as the end it is,
    OPENING-FROM-END), expanded with the features it *hosted*. Raises
    :class:`PluginError` or :class:`FeatureExpressionError`."""
    manifest = plugin.manifest
    typed = _with(
        envelope, _canonical(manifest, envelope.params.inputs, bounds=False), None
    )
    resolved = resolve_feature(typed, parameters)
    inputs = settle_inputs(
        plugin,
        feature_id,
        _canonical(manifest, resolved.params.inputs),
        earlier,
        parameters=parameters,
    )
    members = _expand(
        plugin, feature_id, inputs, earlier, hosted=hosted, parameters=parameters
    )
    return _with(resolved, inputs, members)


def check_members_authorable(
    members: Sequence[ExpandedMember], rows: Sequence[db.Feature]
) -> None:
    """The write rules a base feature meets, on every member: an ``import``
    only on an empty part (no body-affecting row in *rows*, the ones before
    the custom feature, nor an earlier member), and no deprecated extrude
    twist. A stored expansion (a ``.loft`` import, a version restore) passes
    here whether or not this server has the plugin."""
    prior_body = any(is_body_affecting(row) for row in rows)
    for member in members:
        feature = member.feature
        if feature.type == "import" and prior_body:
            raise ValidationApiError(
                f"Member {member.role}/{member.index} is an import, which sets "
                "the part's base body, so it cannot follow another "
                "body-producing feature.",
                code="import_with_prior_body",
                details={"member_id": str(member.id)},
            )
        if authors_extrude_twist(feature):
            raise ValidationApiError(
                EXTRUDE_TWIST_DEPRECATED_MESSAGE,
                code=EXTRUDE_TWIST_DEPRECATED_CODE,
                details={"member_id": str(member.id), "use": "sweep"},
            )
        prior_body = prior_body or feature.type in BODY_AFFECTING_FEATURE_TYPES


def _placements(members: Sequence[Mapping[str, Any]]) -> dict[uuid.UUID, Any]:
    """Each member's PLACEMENT: its feature as JSON with every reference to
    another member of the same expansion replaced by that member's placement,
    and an extrude's distance left out (WALL-MEMBER-RENUMBER). Two members
    with one placement sit in the same place in plan and on the same plane,
    whatever their ids; a member whose placement changed has moved (or, under
    an ordinal id, been renumbered). A taller wall's studs keep theirs."""
    table = {uuid.UUID(str(m["id"])): m["feature"] for m in members}
    memo: dict[uuid.UUID, Any] = {}

    def substitute(node: Any) -> Any:
        if isinstance(node, dict):
            fields = cast(dict[str, Any], node)
            target = fields.get("feature_id")
            if fields.get("kind") == "feature" and isinstance(target, str):
                ref = uuid.UUID(target)
                if ref in table:
                    return {"member": place(ref)}
            return {key: substitute(value) for key, value in fields.items()}
        if isinstance(node, list):
            return [substitute(item) for item in cast(list[Any], node)]
        return node

    def place(member: uuid.UUID) -> Any:
        if member not in memo:
            feature = dict(cast(dict[str, Any], table[member]))
            if feature.get("type") == "extrude":
                params = dict(cast(dict[str, Any], feature.get("params", {})))
                params.pop("distance_mm", None)
                feature["params"] = params
            memo[member] = substitute(feature)
        return memo[member]

    return {member: place(member) for member in table}


def _normalised(member: Mapping[str, Any]) -> Mapping[str, Any]:
    """A stored member as this server would dump it, so a field a later
    loft-wire added (and omits while default) never reads as a move."""
    try:
        return ExpandedMember.model_validate(member).model_dump(mode="json")
    except ValidationError:
        return member


def _renumbered_roles(
    stored: db.Feature, envelope_pin: tuple[str, str]
) -> frozenset[str]:
    """The roles whose ordinal ids a re-layout can hand to another member,
    for a stored custom feature re-expanded under the SAME pin (a changed pin
    names its members afresh, so only a vanished reference counts there)."""
    pin = (
        str(stored.params.get("plugin_id")),
        str(stored.params.get("plugin_version")),
    )
    if pin != envelope_pin:
        return frozenset()
    try:
        return PLUGINS.get(*pin).renumbered_roles
    except PluginError:
        return frozenset()


def check_referenced_members(
    stored: db.Feature,
    members: Sequence[ExpandedMember],
    rows: Sequence[db.Feature],
    pin: tuple[str, str] | None = None,
) -> None:
    """409 ``feature_has_dependents`` when a re-expansion drops (or retypes) a
    member a later feature references: the same refusal a delete of that
    feature would get, raised at the write instead of as a rebuild error.

    Also when it MOVES a referenced member whose id is an ordinal a re-layout
    can renumber (``loft.wall`` 1.0.0's ``stud/6``, WALL-MEMBER-RENUMBER):
    the reference cannot tell the stud that moved from another stud that
    took its number, and SolidWorks and Fusion flag such a reference rather
    than rebind it silently. *pin* is the re-expansion's plugin and version
    (the stored row's own when omitted)."""
    if stored.type != "custom":
        return
    stored_pin = (
        str(stored.params.get("plugin_id")),
        str(stored.params.get("plugin_version")),
    )
    renumbered = _renumbered_roles(stored, pin or stored_pin)
    new = {member.id: member for member in members}
    old_raw = [m for m in stored_members(stored.params) if "id" in m]
    old = {uuid.UUID(str(m["id"])): m for m in old_raw}
    placements: list[dict[uuid.UUID, Any]] = []

    def placed() -> list[dict[uuid.UUID, Any]]:
        if not placements:  # computed once, and only for a referenced member
            placements.append(_placements([_normalised(m) for m in old_raw]))
            placements.append(_placements([m.model_dump(mode="json") for m in members]))
        return placements

    def moved_member(target: uuid.UUID) -> bool:
        if str(old[target].get("role")) not in renumbered:
            return False
        before, after = placed()
        return before.get(target) != after.get(target)

    def dropped_duplicate(target: uuid.UUID) -> bool:
        """*target* was stored as an exact copy of another member of its role
        that the re-expansion keeps: a duplicate the plugin now drops
        (ROOF-L-DOUBLED-COMMON), lost at rebuild whatever this write does."""
        before = placed()[0]
        role = old[target].get("role")
        return any(
            other != target
            and other in new
            and old[other].get("role") == role
            and before.get(other) == before.get(target)
            for other in old
        )

    removed: list[db.Feature] = []
    duplicates: list[db.Feature] = []
    moved: list[db.Feature] = []
    for row in sorted(rows, key=lambda r: r.order_index):
        if row.order_index <= stored.order_index:
            continue
        for reference in authored_references(load_feature(row)[0]):
            target = reference.ref.feature_id
            if target not in old:
                continue
            member = new.get(target)
            if member is None or (
                "*" not in reference.allowed_types
                and member.feature.type not in reference.allowed_types
            ):
                if member is None and dropped_duplicate(target):
                    duplicates.append(row)
                else:
                    removed.append(row)
                break
            if moved_member(target):
                moved.append(row)
                break
    broken = removed + duplicates + moved
    if not broken:
        return
    dependents = FeatureDependents(
        dependents=[
            FeatureDependent(id=row.id, name=row.name, kind="feature")
            for row in sorted(broken, key=lambda r: r.order_index)
        ]
    )
    parts: list[str] = []
    if removed:
        parts.append(
            f"This change removes geometry that {len(removed)} later feature(s) "
            "reference; re-point or delete them first."
        )
    if duplicates:
        names = ", ".join(repr(row.name) for row in duplicates)
        parts.append(
            f"{names} refer(s) to a duplicate rafter that was removed from "
            f"{stored.name!r} (it was framed twice in the same place); delete "
            "or re-pick it."
        )
    if moved:
        names = ", ".join(repr(row.name) for row in moved)
        parts.append(
            f"This change moves a member that {names} reference(s). "
            f"{stored.name!r} is {stored_pin[0]} {stored_pin[1]}, which numbers "
            "its members in order, so the reference would land on another "
            "member; re-point or delete them first."
        )
    message = " ".join(parts)
    raise ConflictError(
        message,
        code="feature_has_dependents",
        details=dependents.model_dump(mode="json"),
    )


def prepare_custom_write(
    part: db.Part,
    envelope: CustomFeature,
    feature_id: uuid.UUID,
    position: int,
    rows: Sequence[db.Feature],
    stored: db.Feature | None = None,
) -> CustomFeature:
    """The custom feature as it is stored: canonical inputs, resolved
    formulas and its expansion against the features before *position*. 422
    with the plugin's code on any refusal; a feature whose plugin this server
    lacks may only be saved unchanged (``plugin_read_only``)."""
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError as exc:
        if stored is not None and _same_pin_and_inputs(stored, envelope):
            return _with(
                envelope,
                dict(envelope.params.inputs),
                CustomFeature.model_validate(
                    {"type": "custom", "version": 1, "params": stored.params}
                ).params.expansion,
            )
        if stored is not None and stored.type == "custom":
            raise ValidationApiError(
                f"{exc.message} This feature rebuilds from its stored expansion "
                "but cannot be edited here.",
                code=PLUGIN_READ_ONLY,
                details={"cause": exc.code},
            ) from exc
        raise _refuse(exc) from exc
    earlier_rows = [
        row for row in rows if row.order_index < position and row.id != feature_id
    ]
    parameters = parameter_values(part.parameters)
    try:
        result = _expanded(
            plugin,
            feature_id,
            envelope,
            parameters,
            _earlier_from_rows(earlier_rows, parameters=parameters),
            Hosts(rows).of(feature_id, parameters),
        )
    except PluginError as exc:
        raise _refuse(exc) from exc
    except FeatureExpressionError as exc:
        details: dict[str, Any] = {}
        if exc.pointer is not None:
            details["pointer"] = exc.pointer
        raise ValidationApiError(exc.message, code=exc.code, details=details) from exc
    members = result.params.expansion or []
    check_tree_size(
        expanded_size(row for row in rows if row.id != feature_id) + len(members),
        "With this expansion the part",
    )
    check_members_authorable(members, earlier_rows)
    if stored is not None:
        check_referenced_members(
            stored,
            members,
            rows,
            (envelope.params.plugin_id, envelope.params.plugin_version),
        )
    return result


# --- hosting (WINDOW-DOOR) ---------------------------------------------------------


def host_id(envelope: AuthoredEnvelope) -> uuid.UUID | None:
    """The feature *envelope* names as its host (a window's wall, or the
    deck a stair offers its inputs to), or ``None`` (not hosted, or its
    plugin is not on this server)."""
    if not isinstance(envelope, CustomFeature):
        return None
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError:
        return None
    return host_of(plugin.manifest, envelope.params.inputs, plugin)


def stored_host_id(row: db.Feature) -> uuid.UUID | None:
    """The host a STORED row names (a door's wall), or ``None``: not custom,
    not hosted, or a stored row that no longer loads (a write that would
    repair it must not fail on reading it)."""
    if row.type != "custom":
        return None
    try:
        return host_id(load_feature(row)[0])
    except ValidationError:
        return None


class Hosts:
    """Which rows each host is given (RESEARCH §23 "Hosting is by inputs"):
    every unsuppressed custom row of *rows* whose host input names it, in
    tree order, with its inputs typed and its formulas resolved. Only inputs
    cross, never expansions, so no hosting chain can cycle. *envelopes*
    replaces a row's stored envelope (a parameter rename not yet stored)."""

    def __init__(
        self,
        rows: Sequence[db.Feature],
        envelopes: Mapping[uuid.UUID, AuthoredEnvelope] | None = None,
    ) -> None:
        self._by_host: dict[uuid.UUID, list[tuple[db.Feature, CustomFeature]]] = {}
        for row in rows:
            if row.type != "custom" or row.suppressed:
                continue
            envelope = (envelopes or {}).get(row.id)
            if envelope is None:
                if stored_host_id(row) is None:
                    continue
                envelope = load_feature(row)[0]
            host = host_id(envelope)
            if host is not None and isinstance(envelope, CustomFeature):
                self._by_host.setdefault(host, []).append((row, envelope))

    def rows_of(self, host: uuid.UUID) -> list[db.Feature]:
        return [row for row, _ in self._by_host.get(host, [])]

    def of(self, host: uuid.UUID, parameters: Mapping[str, Quantity]) -> list[Hosted]:
        """The hosted features of *host*. Raises :class:`PluginError` naming
        a hosted feature whose inputs do not resolve: the host cannot frame
        what it cannot read, so the error is the host's."""
        out: list[Hosted] = []
        for row, envelope in self._by_host.get(host, []):
            pin = envelope.params
            manifest = PLUGINS.get(pin.plugin_id, pin.plugin_version).manifest
            try:
                typed = _with(
                    envelope, _canonical(manifest, pin.inputs, bounds=False), None
                )
                inputs = _canonical(
                    manifest, resolve_feature(typed, parameters).params.inputs
                )
            except PluginError as exc:
                raise PluginError(
                    exc.code, f"{row.name}: {exc.message}", input=exc.input
                ) from exc
            except FeatureExpressionError as exc:
                raise PluginError(
                    PARAMETER_VALUE_INVALID, f"{row.name}: {exc.message}"
                ) from exc
            out.append(
                Hosted(
                    feature_id=row.id,
                    plugin_id=pin.plugin_id,
                    plugin_version=pin.plugin_version,
                    name=row.name,
                    inputs=ExpandInputs(row.id, inputs),
                )
            )
        return out


def reexpand_hosts(
    part: db.Part, rows: Sequence[db.Feature], hosts: Iterable[uuid.UUID | None]
) -> None:
    """After a write to a hosted feature (a door added, moved, suppressed or
    deleted), re-expand each of its *hosts* in *rows*, the tree as written,
    and store the new members on the host's row: the write is refused (422
    with the plugin's code, naming the opening) when a host can no longer
    frame what it hosts, or (409) when the new framing drops a member a
    later feature references. A host whose plugin is missing keeps its
    stored expansion (read-only, as everywhere)."""
    by_id = {row.id: row for row in rows}
    index = Hosts(rows)
    parameters = parameter_values(part.parameters)
    for host in sorted({h for h in hosts if h is not None}):
        row = by_id.get(host)
        if row is None or row.type != "custom":
            continue
        _reexpand(row, rows, index, parameters, strict=True)


def picked_ids(envelope: AuthoredEnvelope) -> set[uuid.UUID]:
    """The features a custom feature picks through its inputs (a roof's
    walls); none for a base feature."""
    if not isinstance(envelope, CustomFeature):
        return set()
    return {ref.ref.feature_id for ref in custom_references(envelope)}


def pickers_of(rows: Sequence[db.Feature], feature_id: uuid.UUID) -> list[uuid.UUID]:
    """The custom features in *rows* that pick *feature_id* through an input
    (a roof's walls), in tree order."""
    out: list[uuid.UUID] = []
    for row in sorted(rows, key=lambda r: r.order_index):
        if row.type != "custom" or row.suppressed or row.id == feature_id:
            continue
        envelope = load_feature(row)[0]
        if isinstance(envelope, CustomFeature) and any(
            ref.ref.feature_id == feature_id for ref in custom_references(envelope)
        ):
            out.append(row.id)
    return out


def reexpand_pickers(
    part: db.Part, rows: Sequence[db.Feature], written: uuid.UUID
) -> None:
    """After a write to *written* (a wall), re-expand the custom features
    that pick it (a roof on its walls, ROOF-MEMBER-RENUMBER) on the tree as
    written, and refuse the write (409) when that drops, or under an ordinal
    pin moves, a member a later feature references, as an edit of the picker
    itself would be. A picker that no longer expands is left to report that
    at rebuild (a wall drawn in steps passes through outlines no roof
    frames), keeping its stored members.

    Pickers of pickers follow, in tree order (BUILDING-OUTLINE): an outline
    sketch's walls are picked by a roof, and a floor by its walls, so one
    dimension edit re-lays the walls, the floor and the roof together."""
    by_id = {row.id: row for row in rows}
    index = Hosts(rows)
    parameters = parameter_values(part.parameters)
    done: set[uuid.UUID] = set()
    pending = [written]
    while pending:
        source = pending.pop(0)
        for picker in pickers_of(rows, source):
            if picker in done:
                continue
            done.add(picker)
            _reexpand(by_id[picker], rows, index, parameters, strict=False)
            pending.append(picker)


def reexpand_reordered(part: db.Part, rows: Sequence[db.Feature]) -> None:
    """After a reorder, re-expand every custom feature of *rows* (the tree in
    its new order) and refuse the reorder (409) when that drops, or under an
    ordinal pin moves, a member a later feature references. A wall frames
    its openings in tree order, so swapping two doors can renumber a
    ``loft.wall`` 1.0.0 wall's opening members. One that no longer expands
    keeps its stored members, to report at rebuild."""
    index = Hosts(rows)
    parameters = parameter_values(part.parameters)
    for row in sorted(rows, key=lambda r: r.order_index):
        if row.type == "custom" and not row.suppressed:
            _reexpand(row, rows, index, parameters, strict=False)


def _reexpand(
    row: db.Feature,
    rows: Sequence[db.Feature],
    index: Hosts,
    parameters: Mapping[str, Quantity],
    *,
    strict: bool,
) -> None:
    """Re-expand *row* in *rows*, check what it drops or moves and store it.
    A plugin or formula error is a 422 when *strict*, else leaves the row."""
    envelope = load_feature(row)[0]
    assert isinstance(envelope, CustomFeature)
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError:
        return
    earlier_rows = [r for r in rows if r.order_index < row.order_index]
    try:
        result = _expanded(
            plugin,
            row.id,
            envelope,
            parameters,
            _earlier_from_rows(earlier_rows, parameters=parameters),
            index.of(row.id, parameters),
        )
    except PluginError as exc:
        if not strict:
            return
        raise _refuse(exc) from exc
    except FeatureExpressionError as exc:
        if not strict:
            return
        raise ValidationApiError(exc.message, code=exc.code) from exc
    members = result.params.expansion or []
    check_tree_size(
        expanded_size(r for r in rows if r.id != row.id) + len(members),
        f"Reframing {row.name!r}, the part",
    )
    check_members_authorable(members, earlier_rows)
    check_referenced_members(row, members, rows)
    params = result.params.model_dump(mode="json")
    if params != row.params:
        row.params = params


# --- evaluation ------------------------------------------------------------------


def _stored(envelope: CustomFeature) -> list[ExpandedMember]:
    return list(envelope.params.expansion or [])


def _evaluate_custom(
    row_id: uuid.UUID,
    envelope: CustomFeature,
    parameters: Mapping[str, Quantity],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    hosts: Hosts,
) -> tuple[list[ExpandedMember], FeatureError | None]:
    """The members to send, and the error to send them with (no size bound:
    :class:`_Budget` applies the tree's)."""
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError:
        return _stored(envelope), None  # read-only: the stored expansion rebuilds
    try:
        members = _expanded(
            plugin,
            row_id,
            envelope,
            parameters,
            earlier,
            hosts.of(row_id, parameters),
        ).params.expansion
    except FeatureExpressionError as exc:
        return _stored(envelope), exc.input_error()
    except PluginError as exc:
        return _stored(envelope), FeatureError(
            code=PARAMETER_VALUE_INVALID, message=f"[{exc.code}] {exc.message}"
        )
    return members or [], None


_TOO_LARGE = FeatureError(
    code=PARAMETER_VALUE_INVALID,
    message=f"[{PLUGIN_EXPANSION_TOO_LARGE}] the part would send more than "
    f"{MAX_TREE_FEATURES} features to geometry; reduce this feature's counts.",
)


class _Budget:
    """``MAX_TREE_FEATURES`` spread over a tree walked in order.

    Every row keeps one slot for itself until it is reached, so a custom
    feature can only take what the rows after it leave free. The request
    built from it never exceeds the bound, whatever is stored (a forged
    ``.loft``, a re-expansion that grew): a custom feature that does not fit
    is sent as its first member with ``plugin_expansion_too_large``, an
    error the user can act on instead of a part that no longer opens."""

    def __init__(self, rows: Sequence[db.Feature]) -> None:
        self._reserved = len(rows)
        self._used = 0

    def take(
        self,
        stored: list[ExpandedMember],
        members: list[ExpandedMember],
        error: FeatureError | None,
    ) -> tuple[list[ExpandedMember], FeatureError | None, bool]:
        """What one custom row sends, its error, and whether *members* (not a
        fallback) went out."""
        self._reserved -= 1
        room = max(MAX_TREE_FEATURES - self._used - self._reserved, 1)
        fits = len(members) <= room
        if not fits:
            error = error or _TOO_LARGE
            members = stored if len(stored) <= room else (stored or members)[:1]
        self._used += len(members)
        return members, error, fits

    def base(self) -> None:
        self._reserved -= 1
        self._used += 1


#: member id -> (the custom feature's envelope, the member as sent).
SentMembers = dict[uuid.UUID, tuple[CustomFeature, ExpandedMember]]


def evaluation_entries(
    part: db.Part, rows: Sequence[db.Feature], members_out: SentMembers | None = None
) -> list[EvaluatedFeatureInput]:
    """Evaluation-request entries for *rows*: every formula resolved once and
    every custom feature replaced by its members (module docstring), never
    more than ``MAX_TREE_FEATURES`` in all (:class:`_Budget`). A suppressed
    feature is skipped by geometry, so it carries no error. *members_out*, when
    given, receives every member sent, so the cut list reads the metadata of
    exactly the expansion geometry builds."""
    values = parameter_values(part.parameters)
    entries: list[EvaluatedFeatureInput] = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    budget = _Budget(rows)
    hosts = Hosts(rows)
    for row in rows:
        envelope, error = load_feature(row)
        earlier[row.id] = _as_plugins_see(envelope, values)
        if not isinstance(envelope, CustomFeature):
            budget.base()
            feature, resolve_error = evaluation_input(envelope, values)
            entries.append(
                EvaluatedFeatureInput(
                    id=row.id,
                    feature=feature,
                    input_error=None if row.suppressed else (error or resolve_error),
                )
            )
            continue
        stored = _stored(envelope)
        if error is not None:
            members = stored
        else:
            members, error = _evaluate_custom(row.id, envelope, values, earlier, hosts)
        members, error, _ = budget.take(stored, members, error)
        for member in members:
            earlier[member.id] = member.feature
            if members_out is not None:
                members_out[member.id] = (envelope, member)
            entries.append(
                EvaluatedFeatureInput(
                    id=member.id,
                    feature=member.feature.model_copy(
                        update={"suppressed": row.suppressed}
                    ),
                    input_error=None if row.suppressed else error,
                )
            )
    return entries


def refresh_expansions(
    part: db.Part, rows: Sequence[db.Feature]
) -> list[dict[str, Any]]:
    """Each row's params with every custom feature's stored expansion brought
    up to date (best effort: a feature that does not expand here, or whose
    new expansion would not fit the tree's bound, keeps its stored members).
    Rows are not modified."""
    values = parameter_values(part.parameters)
    out: list[dict[str, Any]] = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    budget = _Budget(rows)
    hosts = Hosts(rows)
    for row in rows:
        envelope = load_feature(row)[0]
        earlier[row.id] = _as_plugins_see(envelope, values)
        params = row.params
        if not isinstance(envelope, CustomFeature):
            budget.base()
        else:
            stored = _stored(envelope)
            members, error = _evaluate_custom(row.id, envelope, values, earlier, hosts)
            if error is not None:
                members = stored
            members, _, fits = budget.take(stored, members, error)
            if fits and error is None:
                params = {
                    **row.params,
                    "expansion": [m.model_dump(mode="json") for m in members],
                }
            else:
                members = stored
            for member in members:
                earlier[member.id] = member.feature
        out.append(params)
    return out


def retabled(
    row: db.Feature,
    envelope: CustomFeature,
    rows: Sequence[db.Feature],
    parameters: Mapping[str, Quantity],
    hosts: Hosts | None = None,
    earlier_writes: Mapping[uuid.UUID, AuthoredEnvelope] | None = None,
) -> CustomFeature | None:
    """*envelope* (its formulas renamed) re-resolved and re-expanded against a
    new parameter table, or ``None`` when it no longer expands: it then keeps
    its last good inputs and members, as a base feature keeps its numbers.
    *hosts* gives it the features it hosts with their formulas renamed;
    *earlier_writes* the earlier features the same table change rewrote (the
    walls a roof picks)."""
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
        earlier = _earlier_from_rows(
            [r for r in rows if r.order_index < row.order_index],
            earlier_writes,
            parameters,
        )
        hosted = (hosts or Hosts(rows)).of(row.id, parameters)
        return _expanded(plugin, row.id, envelope, parameters, earlier, hosted)
    except (PluginError, FeatureExpressionError):
        return None


def remap_member_name(name: str, mapping: Mapping[str, str]) -> str:
    """A member's name on a copy that re-mints ids: every segment that is an
    old id becomes its new one (a 1.1.0 wall names an opening's members
    after the opening, ``opening/<door-id>/0``), so the copy's names are the
    ones its own re-expansion gives (WALL-MEMBER-RENUMBER)."""
    return "/".join(mapping.get(segment, segment) for segment in name.split("/"))


def member_id_mapping(
    features: Iterable[tuple[uuid.UUID, str, Mapping[str, Any]]],
    mapping: Mapping[str, str],
) -> dict[str, str]:
    """old member id -> new member id, for a copy or import that re-mints the
    ids in *mapping*: a member's id derives from its custom feature's, and a
    reference to a generated member must follow it. *features* is
    ``(id, type, params)`` per stored feature."""
    out: dict[str, str] = {}
    for old, kind, params in features:
        new = mapping.get(str(old))
        if kind != "custom" or new is None:
            continue
        for member in stored_members(params):
            role, index = str(member["role"]), int(member["index"])
            name = member.get("name")
            out[str(member["id"])] = str(
                member_id(
                    uuid.UUID(new),
                    role,
                    index,
                    None if name is None else remap_member_name(str(name), mapping),
                )
            )
    return out


def check_stored_custom(
    row_id: uuid.UUID, envelope: AuthoredEnvelope, rows: Sequence[db.Feature]
) -> None:
    """A stored custom feature's expansion is intact (ids derived from
    *row_id*, references to features in *rows*, which are the ones before
    it): the gate a ``.loft`` import and a version restore pass through,
    whether or not this server has the plugin. 422 otherwise."""
    if not isinstance(envelope, CustomFeature):
        return
    try:
        validate_members(row_id, _stored(envelope), _earlier_from_rows(rows))
    except PluginError as exc:
        raise _refuse(exc) from exc
    check_members_authorable(_stored(envelope), rows)


# --- warnings ---------------------------------------------------------------------


def plugin_warnings(
    part: db.Part, row: db.Feature, rows: Sequence[db.Feature]
) -> list[PluginWarning] | None:
    """A stored roof's ``roof_through_sheathing`` warning (ROOF-THROUGH-
    SHEATHING-UPDATE), or None: its stored members' exact overlap with the
    sheathing of every earlier wall (:func:`through_sheathing`), less what
    its own cuts notch. A suppressed roof, or a suppressed wall, builds
    nothing and shares nothing. The pin is never moved here: the warning
    names the release that notches it when the roof picks its walls, and
    updating is the user's edit, undone like any other."""
    if row.type != "custom" or row.suppressed:
        return None
    envelope = load_feature(row)[0]
    if isinstance(envelope, CustomFeature) and envelope.params.plugin_id == (
        "loft.foundation"
    ):
        return _crawl_height_warning(envelope)
    if isinstance(envelope, CustomFeature) and envelope.params.plugin_id in _NOTES:
        return _input_warnings(part, row, envelope, rows)
    if (
        not isinstance(envelope, CustomFeature)
        or envelope.params.plugin_id != "loft.roof"
        or not envelope.params.expansion
    ):
        return None
    values = parameter_values(part.parameters)
    earlier = _earlier_from_rows(
        [r for r in rows if r.order_index < row.order_index and not r.suppressed],
        parameters=values,
    )
    out = [
        w
        for w in (
            _through_sheathing_warning(envelope, earlier, values),
            _ceiling_joists_warning(row.id, envelope, earlier, values),
        )
        if w is not None
    ]
    return out or None


def _through_sheathing_warning(
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    values: Mapping[str, Quantity],
) -> PluginWarning | None:
    """A stored roof's ``roof_through_sheathing``, or None. The update it
    offers is the declared one (``loft_plugins.updates``): it carries the
    inputs by its map and notches the sheathing; what else it adds (a
    gable's ceiling joists, PLUGIN-UPDATE-ALL) its offer names."""
    assert envelope.params.expansion is not None
    found = through_sheathing(envelope.params.expansion, earlier, values)
    if found.volume <= MIN_OVERLAP_IN3:
        return None
    declared = update_for("loft.roof", envelope.params.plugin_version, PLUGINS)
    picks = envelope.params.inputs.get("walls")
    update = (
        declared.to_version
        if declared is not None and isinstance(picks, list) and picks
        else None
    )
    about = "about " if found.approximate else ""
    shared = (
        f"This roof's rafter tails pass through the wall sheathing: {found.pairs} "
        f"member and panel pairs share {about}{found.volume:.4f} in³, counted "
        "twice in the volume, the mass and the STEP."
    )
    if update is not None:
        fix = (
            f" Update to {update} to notch the sheathing round them, as framers "
            "do; the update says what else it adds, and Undo restores this roof."
        )
    else:
        fix = (
            " A roof on its typed bearing picks no walls, so it cannot notch "
            "them: a roof on an outline wall, or a hip on the walls it picks, does."
        )
    return PluginWarning(
        code=ROOF_THROUGH_SHEATHING,
        message=shared + fix,
        overlap_in3=found.volume,
        pairs=found.pairs,
        update_to=update,
    )


def _ceiling_joists_warning(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    values: Mapping[str, Quantity],
) -> PluginWarning | None:
    """A 1.6.0 gable's ``ceiling_joists_omitted`` (CEILING-JOISTS), or None:
    it asks for ceiling joists, its stored expansion frames none, and its
    chosen joist would pass the ridge board. Advice, never a refusal: the
    roof builds without them, as Chief warns rather than blocks."""
    inputs = envelope.params.inputs
    expansion = envelope.params.expansion or []
    if inputs.get("ceiling_joists") != CEILING_BESIDE or any(
        m.role == "ceiling_joist" for m in expansion
    ):
        return None
    note = ceiling_joist_note(stored_inputs(feature_id, envelope, earlier, values))
    if note is None:
        return None
    return PluginWarning(
        code=CEILING_JOISTS_OMITTED,
        message=note,
        overlap_in3=0.0,
        pairs=0,
        update_to=None,
    )


#: The plugins whose stored inputs carry advice, as (code, message) notes.
_NOTES = {STAIR: stair_notes, "loft.wall": finish_notes}


def _input_warnings(
    part: db.Part, row: db.Feature, envelope: CustomFeature, rows: Sequence[db.Feature]
) -> list[PluginWarning] | None:
    """A stair's advice (STAIRS, :func:`stair_notes`: a cut stringer's
    throat under DCA6's 5 in, open sides over 30 in up with no guard, a deck
    guard across its head) or a wall's ``wall_finish_no_sheathing``
    (SIDING-TRIM), or None. Never a refusal: the feature builds."""
    values = parameter_values(part.parameters)
    earlier = _earlier_from_rows(
        [r for r in rows if r.order_index < row.order_index and not r.suppressed],
        parameters=values,
    )
    inputs = stored_inputs(row.id, envelope, earlier, values)
    notes = _NOTES[envelope.params.plugin_id](inputs)
    return [
        PluginWarning(
            code=code,  # pyright: ignore[reportArgumentType]
            message=message,
            overlap_in3=0.0,
            pairs=0,
            update_to=None,
        )
        for code, message in notes
    ] or None


def declared_update(row: db.Feature) -> PluginUpdate | None:
    """The declared update of a stored custom feature (``loft_plugins.updates``),
    or None: not custom, already the newest this server maps it to, or a
    release with no declared map. Offered whether or not the feature is
    suppressed, as Onshape's update."""
    if row.type != "custom":
        return None
    plugin_id = row.params.get("plugin_id")
    version = row.params.get("plugin_version")
    if not isinstance(plugin_id, str) or not isinstance(version, str):
        return None
    return update_for(plugin_id, version, PLUGINS)


#: The summary of an update whose effect cannot be read (PLUGIN-UPDATE-ALL).
CANNOT_PREVIEW = (
    "Can't preview this update (suppressed or refused); update it on its own."
)


@dataclass(frozen=True)
class _Refused:
    """An update's dry run refused, with the refusal's message: the offer
    says why it cannot preview (two stairs too close for the guard's posts)."""

    reason: str


#: What each out-of-date row's update would do, by (part, tree version,
#: row): a dry run re-expands the row and its host, so the tree's every read
#: does not repeat it. Every write bumps the tree version, so an entry can
#: never outlive the tree it was read from.
_EFFECTS: OrderedDict[
    tuple[uuid.UUID, int, uuid.UUID], UpdateEffect | _Refused | None
] = OrderedDict()
_EFFECTS_MAX = 2048


def _cannot_preview(refused: _Refused | None) -> str:
    """:data:`CANNOT_PREVIEW`, or with the dry run's refusal as its reason."""
    if refused is None:
        return CANNOT_PREVIEW
    reason = refused.reason.strip()
    if reason and reason[-1] not in ".!?":
        reason += "."
    return f"Can't preview this update: {reason[:600]} Update it on its own."


def _update_effect(
    part: db.Part, row: db.Feature, rows: Sequence[db.Feature]
) -> UpdateEffect | _Refused | None:
    """What updating *row* would add and whether it changes any member, read
    by a dry run on the tree as stored: the row re-expanded at its update's
    release, and a hosted row's host (a door's wall) with it. None when the
    row is suppressed (it builds nothing); :class:`_Refused`, with the
    refusal's message, when the dry run is refused."""
    key = (part.id, part.tree_version, row.id)
    if key in _EFFECTS:
        _EFFECTS.move_to_end(key)
        return _EFFECTS[key]
    effect = None if row.suppressed else _dry_run(part, row, rows)
    _EFFECTS[key] = effect
    while len(_EFFECTS) > _EFFECTS_MAX:
        _EFFECTS.popitem(last=False)
    return effect


def _dry_run(
    part: db.Part, row: db.Feature, rows: Sequence[db.Feature]
) -> UpdateEffect | _Refused:
    parameters = parameter_values(part.parameters)
    try:
        envelope = updated_envelope(part, row, rows)
        pin = envelope.params
        index = Hosts(rows, {row.id: envelope})
        earlier = [r for r in rows if r.order_index < row.order_index]
        result = _expanded(
            PLUGINS.get(pin.plugin_id, pin.plugin_version),
            row.id,
            envelope,
            parameters,
            _earlier_from_rows(earlier, parameters=parameters),
            index.of(row.id, parameters),
        )
        stored = load_feature(row)[0]
        assert isinstance(stored, CustomFeature)
        changed = [(pin.plugin_id, _stored(stored), result.params.expansion or [])]
        host = next((r for r in rows if r.id == host_id(envelope)), None)
        if host is not None and host.type == "custom" and not host.suppressed:
            host_envelope = load_feature(host)[0]
            assert isinstance(host_envelope, CustomFeature)
            host_pin = host_envelope.params
            reframed = _expanded(
                PLUGINS.get(host_pin.plugin_id, host_pin.plugin_version),
                host.id,
                host_envelope,
                parameters,
                _earlier_from_rows(
                    [r for r in rows if r.order_index < host.order_index],
                    parameters=parameters,
                ),
                index.of(host.id, parameters),
            )
            changed.append(
                (
                    host_pin.plugin_id,
                    _stored(host_envelope),
                    reframed.params.expansion or [],
                )
            )
    except (PluginError, FeatureExpressionError, ValidationApiError) as exc:
        return _Refused(exc.message)
    except ValidationError as exc:
        return _Refused(str(exc.errors()[0]["msg"]))
    update = declared_update(row)
    reason = "" if update is None else update.relay_reason
    return update_effect(changed, PLUGINS, reason)


def plugin_update_of(
    part: db.Part, row: db.Feature, rows: Sequence[db.Feature]
) -> PluginUpdateOffer | None:
    """The newest release a stored custom feature may be updated to
    (OPENING-UPDATE, PLUGIN-UPDATE-ALL), or None (:func:`declared_update`).
    The summary names what the update adds, read by a dry run against the
    tree as stored (``Adds 11 ceiling joists.``); an update that changes no
    member is ``quiet``: no badge, but Update all still takes it. One that
    moves a stored member (``Re-lays 19 joists ...``) is ``separate``:
    offered on its feature alone, never taken by Update all."""
    update = declared_update(row)
    if update is None:
        return None
    effect = _update_effect(part, row, rows)
    if effect is None or isinstance(effect, _Refused):
        # Suppressed, or its dry run refused (saying why): what it would
        # move is unknown, so it is never taken by Update all unseen.
        return PluginUpdateOffer(
            to_version=update.to_version,
            summary=f"{_cannot_preview(effect)} {update.summary}",
            separate=True,
        )
    return PluginUpdateOffer(
        to_version=update.to_version,
        summary=f"{effect.sentence} {update.summary}".strip(),
        adds=list(effect.adds[:MAX_UPDATE_ADDS]),
        quiet=not effect.changes,
        relays=list(effect.relays[:MAX_UPDATE_ADDS]),
        separate=bool(effect.relays),
    )


def updated_envelope(
    part: db.Part, row: db.Feature, rows: Sequence[db.Feature]
) -> CustomFeature:
    """*row* re-pinned to its update's release, its stored inputs carried by
    the update's explicit map (which reads the features before it in *rows*:
    a floor's outline) and its formulas kept on the same inputs; the
    expansion is left for :func:`prepare_custom_write`. 422
    ``plugin_update_unavailable`` when it has none, when the map cannot read
    what it needs, or when a formula drives an input the newer release does
    not have."""
    update = declared_update(row)
    envelope = load_feature(row)[0]
    if update is None or not isinstance(envelope, CustomFeature):
        raise ValidationApiError(
            f"{row.name!r} has no newer release to update to.",
            code=PLUGIN_UPDATE_UNAVAILABLE,
            details={"feature_id": str(row.id)},
        )
    pin = envelope.params
    target = PLUGINS.get(pin.plugin_id, update.to_version).manifest
    names = {item.name for item in target.inputs}
    for pointer in envelope.expressions or {}:
        if pointer.removeprefix("/inputs/").split("/")[0] not in names:
            raise ValidationApiError(
                f"{row.name!r}: {target.title} {target.version} has no input "
                f"{pointer!r} for its formula to drive.",
                code=PLUGIN_UPDATE_UNAVAILABLE,
                details={"feature_id": str(row.id), "pointer": pointer},
            )
    parameters = parameter_values(part.parameters)
    earlier = _earlier_from_rows(
        [r for r in rows if r.order_index < row.order_index and r.id != row.id],
        parameters=parameters,
    )
    try:
        inputs = updated_inputs(
            update, pin.inputs, stored_inputs(row.id, envelope, earlier, parameters)
        )
    except PluginError as exc:
        raise ValidationApiError(
            f"{row.name!r}: {exc.message}",
            code=PLUGIN_UPDATE_UNAVAILABLE,
            details={"feature_id": str(row.id), "cause": exc.code},
        ) from exc
    params = pin.model_copy(
        update={
            "plugin_version": update.to_version,
            "inputs": inputs,
            "expansion": None,
        }
    )
    return envelope.model_copy(update={"params": params})


def _crawl_height_warning(envelope: CustomFeature) -> list[PluginWarning] | None:
    """A foundation's ``crawl_height_low`` (CRAWL-SPACE), or None: its stored
    crawl height (grade to the joists' underside) under IRC R317.1's 18 in,
    below which the joists must be pressure-treated or naturally durable.
    Advice on an input, never a refusal: the foundation builds."""
    stored = envelope.params.inputs.get("crawl_height_mm")
    if isinstance(stored, bool) or not isinstance(stored, int | float):
        return None
    crawl = stored / MM_PER_INCH
    if crawl >= MIN_UNTREATED_CRAWL_IN - 1e-9:
        return None
    return [
        PluginWarning(
            code=CRAWL_HEIGHT_LOW,
            message=(
                f"The crawl height is {crawl:g} in, under the "
                f"{MIN_UNTREATED_CRAWL_IN:g} in of IRC R317.1: joists this close "
                "to the ground must be pressure-treated or naturally durable "
                "wood. Raise the crawl height, or frame the floor in treated "
                "joists."
            ),
            overlap_in3=0.0,
            pairs=0,
            update_to=None,
        )
    ]


__all__ = [
    "AUTHORED_FEATURES",
    "PLUGINS",
    "Hosts",
    "SentMembers",
    "authored_references",
    "check_members_authorable",
    "check_referenced_members",
    "check_tree_size",
    "declared_update",
    "evaluation_entries",
    "expanded_size",
    "host_id",
    "is_body_affecting",
    "member_id_mapping",
    "member_targets",
    "picked_ids",
    "pickers_of",
    "plugin_update_of",
    "plugin_warnings",
    "prepare_custom_write",
    "reexpand_hosts",
    "reexpand_pickers",
    "reexpand_reordered",
    "refresh_expansions",
    "remap_member_name",
    "router",
    "stored_host_id",
    "updated_envelope",
]
