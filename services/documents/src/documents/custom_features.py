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
    FeatureError,
    FeatureRef,
    FeatureReference,
    feature_references,
)
from loft_wire.plugins import (
    PLUGIN_READ_ONLY,
    FeatureReferenceInput,
    PluginCatalog,
    ProfileInput,
    member_id,
)
from py_kit import ValidationApiError, get_logger

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
    others = sum(row_size(row) for row in rows if row.id != feature_id)
    total = others + len(result.params.expansion or [])
    if total > MAX_TREE_FEATURES:
        raise ValidationApiError(
            f"With this expansion the part would send {total} features to "
            f"geometry; the limit is {MAX_TREE_FEATURES}.",
            code="feature_limit_exceeded",
            details={"max_features": MAX_TREE_FEATURES, "expanded": total},
        )
    return result


# --- evaluation ------------------------------------------------------------------


def _stored(envelope: CustomFeature) -> list[ExpandedMember]:
    return list(envelope.params.expansion or [])


def _evaluate_custom(
    row_id: uuid.UUID,
    envelope: CustomFeature,
    parameters: Mapping[str, Quantity],
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    budget: int,
) -> tuple[list[ExpandedMember], FeatureError | None]:
    """The members to send, and the error to send them with."""
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
    members = members or []
    if len(members) > budget:
        return _stored(envelope), FeatureError(
            code=PARAMETER_VALUE_INVALID,
            message=f"[plugin_expansion_too_large] the part would send more than "
            f"{MAX_TREE_FEATURES} features to geometry",
        )
    return members, None


def evaluation_entries(
    part: db.Part, rows: Sequence[db.Feature]
) -> list[EvaluatedFeatureInput]:
    """Evaluation-request entries for *rows*: every formula resolved once and
    every custom feature replaced by its members (module docstring). A
    suppressed feature is skipped by geometry, so it carries no error."""
    values = parameter_values(part.parameters)
    entries: list[EvaluatedFeatureInput] = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    spare = MAX_TREE_FEATURES - sum(row_size(row) for row in rows)
    for row in rows:
        envelope, error = load_feature(row)
        earlier[row.id] = envelope
        if not isinstance(envelope, CustomFeature):
            feature, resolve_error = evaluation_input(envelope, values)
            entries.append(
                EvaluatedFeatureInput(
                    id=row.id,
                    feature=feature,
                    input_error=None if row.suppressed else (error or resolve_error),
                )
            )
            continue
        stored = len(_stored(envelope))
        if error is not None:
            members = _stored(envelope)
        else:
            members, error = _evaluate_custom(
                row.id, envelope, values, earlier, stored + spare
            )
        spare -= len(members) - stored
        for member in members:
            earlier[member.id] = member.feature
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
    up to date (best effort: a feature that does not expand here keeps its
    stored members). Rows are not modified."""
    values = parameter_values(part.parameters)
    out: list[dict[str, Any]] = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for row in rows:
        envelope = load_feature(row)[0]
        earlier[row.id] = envelope
        params = row.params
        if isinstance(envelope, CustomFeature):
            members, error = _evaluate_custom(
                row.id, envelope, values, earlier, MAX_TREE_FEATURES
            )
            if error is None:
                params = {
                    **row.params,
                    "expansion": [m.model_dump(mode="json") for m in members],
                }
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


__all__ = [
    "AUTHORED_FEATURES",
    "PLUGINS",
    "authored_references",
    "evaluation_entries",
    "is_body_affecting",
    "member_id_mapping",
    "member_targets",
    "prepare_custom_write",
    "refresh_expansions",
    "router",
]
