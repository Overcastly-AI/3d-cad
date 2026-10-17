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
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from fastapi import APIRouter
from loft_plugins import (
    REGISTRY,
    Plugin,
    PluginError,
    PluginRegistry,
    validate_members,
)
from loft_plugins import canonical_inputs as _canonical
from loft_plugins import expand as _expand
from loft_wire.expr import Quantity
from loft_wire.feature_input import PARAMETER_VALUE_INVALID
from loft_wire.feature_resolve import (
    FeatureExpressionError,
    evaluation_input,
    parameter_values,
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
from loft_wire.plugins import (
    PLUGIN_EXPANSION_TOO_LARGE,
    PLUGIN_READ_ONLY,
    FeatureReferenceInput,
    PluginCatalog,
    ProfileInput,
    member_id,
)
from py_kit import ConflictError, ValidationApiError, get_logger

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
) -> dict[uuid.UUID, AuthoredEnvelope]:
    """Every row's envelope by id, and every stored member's by member id."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for row in rows:
        envelope = load_feature(row)[0]
        earlier[row.id] = envelope
        if isinstance(envelope, CustomFeature):
            for member in envelope.params.expansion or []:
                earlier[member.id] = member.feature
    return earlier


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
            FeatureReference(f"inputs/{name}", value, frozenset({"*"}))
            for name, value in envelope.params.inputs.items()
            if isinstance(value, FeatureRef)
        ]
    out: list[FeatureReference] = []
    for item in manifest.inputs:
        value = envelope.params.inputs.get(item.name)
        if not isinstance(value, FeatureRef):
            continue
        if isinstance(item, ProfileInput):
            out.append(
                FeatureReference(f"inputs/{item.name}", value, frozenset({"sketch"}))
            )
        elif isinstance(item, FeatureReferenceInput):
            allowed = frozenset(item.feature_types)
            out.append(FeatureReference(f"inputs/{item.name}", value, allowed))
    return out


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
) -> CustomFeature:
    """Inputs typed, formulas resolved, bounds checked, expanded. Raises
    :class:`PluginError` or :class:`FeatureExpressionError`."""
    manifest = plugin.manifest
    typed = _with(
        envelope, _canonical(manifest, envelope.params.inputs, bounds=False), None
    )
    resolved = resolve_feature(typed, parameters)
    inputs = _canonical(manifest, resolved.params.inputs)
    members = _expand(plugin, feature_id, inputs, earlier)
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


def _check_vanished_members(
    stored: db.Feature,
    members: Sequence[ExpandedMember],
    rows: Sequence[db.Feature],
) -> None:
    """409 ``feature_has_dependents`` when a re-expansion drops (or retypes) a
    member a later feature references: the same refusal a delete of that
    feature would get, raised at the write instead of as a rebuild error."""
    if stored.type != "custom":
        return
    new = {member.id: member.feature.type for member in members}
    old = {
        uuid.UUID(str(member["id"]))
        for member in stored_members(stored.params)
        if "id" in member
    }
    broken: list[db.Feature] = []
    for row in sorted(rows, key=lambda r: r.order_index):
        if row.order_index <= stored.order_index:
            continue
        for reference in authored_references(load_feature(row)[0]):
            target = reference.ref.feature_id
            if target not in old:
                continue
            kind = new.get(target)
            if kind is None or (
                "*" not in reference.allowed_types
                and kind not in reference.allowed_types
            ):
                broken.append(row)
                break
    if broken:
        dependents = FeatureDependents(
            dependents=[
                FeatureDependent(id=row.id, name=row.name, kind="feature")
                for row in broken
            ]
        )
        raise ConflictError(
            f"This change removes geometry that {len(broken)} later feature(s) "
            "reference; re-point or delete them first.",
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
    try:
        result = _expanded(
            plugin,
            feature_id,
            envelope,
            parameter_values(part.parameters),
            _earlier_from_rows(earlier_rows),
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
        _check_vanished_members(stored, members, rows)
    return result


# --- evaluation ------------------------------------------------------------------


def _stored(envelope: CustomFeature) -> list[ExpandedMember]:
    return list(envelope.params.expansion or [])


def _evaluate_custom(
    row_id: uuid.UUID,
    envelope: CustomFeature,
    parameters: Mapping[str, Quantity],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
) -> tuple[list[ExpandedMember], FeatureError | None]:
    """The members to send, and the error to send them with (no size bound:
    :class:`_Budget` applies the tree's)."""
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
    except PluginError:
        return _stored(envelope), None  # read-only: the stored expansion rebuilds
    try:
        members = _expanded(
            plugin, row_id, envelope, parameters, earlier
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
    for row in rows:
        envelope, error = load_feature(row)
        earlier[row.id] = envelope
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
            members, error = _evaluate_custom(row.id, envelope, values, earlier)
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
    for row in rows:
        envelope = load_feature(row)[0]
        earlier[row.id] = envelope
        params = row.params
        if not isinstance(envelope, CustomFeature):
            budget.base()
        else:
            stored = _stored(envelope)
            members, error = _evaluate_custom(row.id, envelope, values, earlier)
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
) -> CustomFeature | None:
    """*envelope* (its formulas renamed) re-resolved and re-expanded against a
    new parameter table, or ``None`` when it no longer expands: it then keeps
    its last good inputs and members, as a base feature keeps its numbers."""
    try:
        plugin = PLUGINS.get(envelope.params.plugin_id, envelope.params.plugin_version)
        earlier = _earlier_from_rows(
            [r for r in rows if r.order_index < row.order_index]
        )
        return _expanded(plugin, row.id, envelope, parameters, earlier)
    except (PluginError, FeatureExpressionError):
        return None


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
            out[str(member["id"])] = str(member_id(uuid.UUID(new), role, index))
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


__all__ = [
    "AUTHORED_FEATURES",
    "PLUGINS",
    "SentMembers",
    "authored_references",
    "check_members_authorable",
    "check_tree_size",
    "evaluation_entries",
    "expanded_size",
    "is_body_affecting",
    "member_id_mapping",
    "member_targets",
    "prepare_custom_write",
    "refresh_expansions",
    "router",
]
