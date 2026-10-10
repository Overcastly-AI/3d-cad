"""``/api/v1/parts/{part_id}/parameters`` — the part's parameter table.

PART-PARAMETERS step 3 (RESEARCH §20). ``GET`` reads the table; ``PUT``
replaces it whole. A PUT is one tree mutation, exactly like a feature write:
the part row is locked, ``expected_tree_version`` must match (stale → 422
``stale_tree_version``, :func:`documents.features.ensure_fresh`),
``tree_version`` bumps, and one history snapshot is recorded so undo/redo walk
the table with the features (:mod:`documents.history`).

Every PUT evaluates the whole table with :func:`loft_wire.parameters.
resolve_parameters` and stores each row's resolved ``value``. A table that
does not evaluate is refused with 422 and the expression error's stable
``code`` (``expression_syntax``, ``expression_unknown_name``,
``expression_cycle`` with its ``chain``, ``expression_name_invalid``,
``expression_units``, ``expression_domain``, ``expression_too_complex``).

Owner-scoped through :func:`~documents.parts.get_owned_part`: another owner's
part is the same 404 as a missing one.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from loft_wire.parameters import (
    ParameterTableError,
    PartParameter,
    PartParameterInput,
    PartParametersResponse,
    PartParametersUpdate,
    resolve_parameters,
)
from py_kit import ValidationApiError, get_logger
from py_kit.db import SessionDep

from documents import db, history
from documents.features import ensure_fresh
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.parameters")

router = APIRouter(prefix="/api/v1/parts", tags=["parameters"])


def resolved_rows(rows: list[PartParameterInput]) -> list[dict[str, Any]]:
    """The stored form of *rows*, evaluated; a 422 naming the fault otherwise.

    Shared by the PUT and every other writer of ``parts.parameters`` (a
    ``.loft`` import, a version restore), so a table is never stored without
    passing the same evaluation.
    """
    try:
        resolved = resolve_parameters(rows)
    except ParameterTableError as exc:
        details: dict[str, Any] = {}
        if exc.parameter is not None:
            details["parameter"] = exc.parameter
        if exc.chain:
            details["chain"] = list(exc.chain)
        raise ValidationApiError(exc.message, code=exc.code, details=details) from exc
    return [row.model_dump(mode="json") for row in resolved]


def stored_parameters(part: db.Part) -> list[PartParameter]:
    """The part's table as wire rows."""
    return [PartParameter.model_validate(row) for row in part.parameters]


@router.get("/{part_id}/parameters")
async def get_parameters(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> PartParametersResponse:
    """The part's parameter table, in its stored order."""
    part = await get_owned_part(session, owner_id, part_id)
    return PartParametersResponse(
        tree_version=part.tree_version, parameters=stored_parameters(part)
    )


@router.put("/{part_id}/parameters")
async def put_parameters(
    part_id: uuid.UUID,
    request: PartParametersUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> PartParametersResponse:
    """Replace the whole parameter table: one undoable tree edit.

    Stale ``expected_tree_version`` → 422 ``stale_tree_version``. A table that
    does not evaluate (bad or repeated name, syntax, unknown name, cycle, unit
    clash, non-finite value) → 422 with the expression error's code.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    ensure_fresh(part, request.expected_tree_version)
    rows = resolved_rows(request.parameters)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)
    part.parameters = rows
    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "part_parameters_replaced",
        part_id=str(part.id),
        parameters=len(rows),
        tree_version=part.tree_version,
    )
    return PartParametersResponse(
        tree_version=part.tree_version, parameters=stored_parameters(part)
    )
