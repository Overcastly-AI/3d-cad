"""Feature formulas against the part's parameter table (PART-PARAMETERS step 4).

RESEARCH §20. The evaluation itself is :mod:`loft_wire.feature_resolve`; this
module is where documents applies it:

* **on every feature write** (:func:`resolve_for_write`): every formula is
  evaluated against the part's table and the numbers are stored in
  ``params``. A syntax error, an unknown name, a cycle, a unit clash or a value
  its field refuses is a 422 with the expression error's code; so is a sketch
  dimension that takes a parameter's name;
* **once per evaluation request** (:func:`evaluation_features`, shared by the
  part and the assembly request): formulas are resolved again and stripped,
  so geometry receives numbers only. A feature that no longer resolves keeps
  its last good numbers and carries an ``input_error``; the request is a 200;
* **on a table PUT** (:func:`apply_table_change`): a parameter still in use
  cannot be deleted (409 ``parameter_in_use``), a rename rewrites every
  reference, and every dependent feature is re-resolved in the same
  transaction, so the PUT stays one undo step.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from loft_wire.expr import Quantity
from loft_wire.feature_input import PARAMETER_UNRESOLVED
from loft_wire.feature_resolve import (
    FeatureExpressionError,
    check_dimension_names,
    parameter_references,
    parameter_values,
    rename_parameters,
    resolve_feature,
    uses_parameters,
)
from loft_wire.features import (
    AUTHORED_FEATURES,
    MAX_TREE_FEATURES,
    AuthoredEnvelope,
    CustomFeature,
    EvaluatedFeatureInput,
    FeatureError,
)
from py_kit import ConflictError, ValidationApiError
from pydantic import ValidationError

from documents import db

if TYPE_CHECKING:
    from documents.custom_features import SentMembers


def _api_error(exc: FeatureExpressionError) -> ValidationApiError:
    details: dict[str, Any] = {}
    if exc.pointer is not None:
        details["pointer"] = exc.pointer
    return ValidationApiError(exc.message, code=exc.code, details=details)


def resolve_for_write[E: AuthoredEnvelope](part: db.Part, envelope: E) -> E:
    """*envelope* with every formula resolved against the part's table (the
    numbers stored in ``params``, formulas kept where they were written), or
    422."""
    try:
        check_dimension_names(envelope, (row["name"] for row in part.parameters))
        return resolve_feature(envelope, parameter_values(part.parameters))
    except FeatureExpressionError as exc:
        raise _api_error(exc) from exc


def load_feature(row: db.Feature) -> tuple[AuthoredEnvelope, FeatureError | None]:
    """The stored row as an envelope, its expressions included.

    Expressions whose pointers no longer fit the params (a params upcast moved
    a field) cannot be carried: the envelope comes back without them and the
    feature is reported unresolved, never a 500. The stored column is kept.
    """
    try:
        envelope = AUTHORED_FEATURES.load(
            row.type,
            row.param_version,
            row.params,
            suppressed=row.suppressed,
            expressions=row.expressions,
        )
    except ValidationError:
        if row.expressions is None:
            raise
        envelope = AUTHORED_FEATURES.load(
            row.type, row.param_version, row.params, suppressed=row.suppressed
        )
        return envelope, FeatureError(
            code=PARAMETER_UNRESOLVED,
            message="This feature's formulas no longer match its fields; "
            "re-enter them.",
        )
    return envelope, None


def evaluation_features(
    part: db.Part,
    rows: Sequence[db.Feature],
    members_out: "SentMembers | None" = None,
) -> list[EvaluatedFeatureInput]:
    """Evaluation-request entries for *rows*, every formula resolved once and
    every custom feature expanded to its base features
    (:func:`documents.custom_features.evaluation_entries`)."""
    from documents.custom_features import evaluation_entries

    return evaluation_entries(part, rows, members_out)


def _store(row: db.Feature, envelope: AuthoredEnvelope) -> None:
    row.param_version = envelope.version
    row.params = envelope.params.model_dump(mode="json")
    row.expressions = envelope.expressions


def parameter_renames(
    old_rows: Sequence[Mapping[str, Any]], new_rows: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    """old name -> new name for every row (by ``id``) the new table renames."""
    old_names = {row["id"]: row["name"] for row in old_rows}
    return {
        old_names[row["id"]]: row["name"]
        for row in new_rows
        if row["id"] in old_names and old_names[row["id"]] != row["name"]
    }


def apply_table_change(
    rows: Sequence[db.Feature],
    old_rows: Sequence[Mapping[str, Any]],
    new_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Carry a parameter-table replacement into the features (*rows*).

    Refuses (409 ``parameter_in_use``) deleting a parameter a feature reads,
    and (422) a parameter that takes a sketch dimension's name or a rename
    that would push a formula past its length cap (naming the feature and the
    pointer). Renames (same id, new name) are rewritten token by token. Every
    feature that reads the table is re-resolved; one that no longer resolves
    keeps its last good numbers and is reported by the next evaluation, as
    Fusion keeps a red feature rather than refusing the parameter edit.
    """
    new_ids = {row["id"] for row in new_rows}
    new_names = {str(row["name"]) for row in new_rows}
    removed = {
        str(row["name"]) for row in old_rows if row["id"] not in new_ids
    } - new_names
    loaded = [(row, load_feature(row)[0]) for row in rows]
    in_use = [
        (row, sorted(parameter_references(envelope) & removed))
        for row, envelope in loaded
    ]
    in_use = [(row, names) for row, names in in_use if names]
    if in_use:
        names = sorted({name for _, used in in_use for name in used})
        raise ConflictError(
            f"Parameter {names[0]!r} is used by {len(in_use)} feature(s); "
            "remove those references first.",
            code="parameter_in_use",
            details={
                "parameters": names,
                "features": [
                    {"id": str(row.id), "name": row.name, "parameters": used}
                    for row, used in in_use
                ],
            },
        )
    for row, envelope in loaded:
        try:
            check_dimension_names(envelope, new_names)
        except FeatureExpressionError as exc:
            raise ValidationApiError(
                f"{exc.message} (feature {row.name!r})",
                code=exc.code,
                details={"feature_id": str(row.id)},
            ) from exc
    values: dict[str, Quantity] = parameter_values(new_rows)
    renames = parameter_renames(old_rows, new_rows)
    # Every change is computed before any row is touched: a rename that a
    # feature cannot take refuses the whole PUT.
    changes: list[tuple[db.Feature, AuthoredEnvelope]] = []
    from documents.custom_features import Hosts, expanded_size, retabled, row_size

    renamed_by_id: dict[uuid.UUID, AuthoredEnvelope] = {}
    for row, envelope in loaded:
        if row.expressions is not None and envelope.expressions is None:
            continue  # formulas that no longer load are kept as stored
        try:
            renamed_by_id[row.id] = rename_parameters(envelope, renames)
        except FeatureExpressionError as exc:
            raise ValidationApiError(
                f"Feature {row.name!r}: {exc.message}",
                code=exc.code,
                details={
                    "feature_id": str(row.id),
                    "feature_name": row.name,
                    "pointer": exc.pointer,
                },
            ) from exc
    # A wall re-frames when a door it hosts reads the table, even if the wall
    # itself reads none (WINDOW-DOOR): it is given the renamed doors.
    hosts = Hosts(rows, renamed_by_id)

    def reads_table(row: db.Feature, envelope: AuthoredEnvelope) -> bool:
        return uses_parameters(envelope) or any(
            uses_parameters(renamed_by_id.get(hosted.id) or load_feature(hosted)[0])
            for hosted in hosts.rows_of(row.id)
        )

    # A re-expansion that would take the part past MAX_TREE_FEATURES keeps its
    # stored members, as a formula that no longer resolves keeps its numbers;
    # the next evaluation reports it (plugin_expansion_too_large).
    size = expanded_size(rows)
    for row, envelope in loaded:
        renamed = renamed_by_id.get(row.id)
        if renamed is None or not reads_table(row, renamed):
            continue
        resolved: AuthoredEnvelope
        if isinstance(renamed, CustomFeature):
            resolved = renamed
            expanded = retabled(row, renamed, rows, values, hosts)
            if expanded is not None:
                grown = len(expanded.params.expansion or []) - row_size(row)
                if size + grown <= MAX_TREE_FEATURES:
                    resolved, size = expanded, size + grown
        else:
            try:
                resolved = resolve_feature(renamed, values)
            except FeatureExpressionError:
                resolved = renamed
        if resolved.model_dump(mode="json") != envelope.model_dump(mode="json"):
            changes.append((row, resolved))
    for row, resolved in changes:
        _store(row, resolved)
