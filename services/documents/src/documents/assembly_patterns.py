"""``/api/v1/assemblies/{id}/patterns``: component patterns (ASM-A3).

Create, replace and delete an assembly's component patterns (Fusion Pattern
Components, Onshape linear / circular pattern and Replicate, SolidWorks
component patterns). A pattern is ONE entry of the assembly holding its
definition; geometry places its copies after the solve. Every write bumps
``doc_version`` under the usual optimistic-concurrency guard and is one undo
step; the write rules are :mod:`documents.pattern_rows`.

The instance bound counts copies: a pattern that would take this assembly, or
any assembly that contains it, past it is refused with the typed
``assembly_too_large``. A hole-driven pattern's count is the driving part's
hole count, which only geometry knows, so the gateway resolves it first and
passes it as ``driven_count``.

Split from :mod:`documents.assemblies` to keep that module under the file-size
ratchet. No kernel import (CLAUDE.md boundaries).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from loft_wire.assemblies import MAX_ASSEMBLY_INSTANCES, AssemblyGraphResponse
from loft_wire.component_patterns import (
    ComponentPatternParams,
    HoleComponentPattern,
    PatternCreate,
    PatternMutationResponse,
    PatternUpdate,
)
from py_kit import NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assemblies import ensure_fresh, graph_response
from documents.assembly_history import ASSEMBLY_HISTORY
from documents.occurrences import reject_oversize
from documents.parts import Principal, get_owned_assembly
from documents.pattern_rows import (
    pattern_response,
    renumber_patterns,
    require_pattern_room,
    resolve_expressions,
    validate_pattern,
)

_logger = get_logger("documents.assembly_patterns")

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])

#: The count a hole-driven pattern had when the gateway resolved it.
DrivenCount = Annotated[
    int | None,
    Query(
        ge=1,
        le=MAX_ASSEMBLY_INSTANCES,
        description="A hole-driven pattern's count per seed (the seed included), "
        "as geometry resolved it for this write; set by the gateway. Ignored "
        "for linear and circular patterns.",
    ),
]


async def _get_pattern(
    session: AsyncSession, assembly: db.Assembly, pattern_id: uuid.UUID
) -> db.AssemblyPattern:
    row = await session.get(db.AssemblyPattern, pattern_id)
    if row is None or row.assembly_id != assembly.id:
        raise NotFoundError("Pattern not found.", code="pattern_not_found")
    return row


async def _checked(
    session: AsyncSession,
    owner_id: uuid.UUID,
    assembly_id: uuid.UUID,
    pattern: ComponentPatternParams,
) -> ComponentPatternParams:
    resolved = resolve_expressions(pattern)
    await validate_pattern(session, owner_id, assembly_id, resolved)
    return resolved


async def _within_bounds(
    session: AsyncSession, owner_id: uuid.UUID, assembly_id: uuid.UUID
) -> None:
    """The written pattern keeps this assembly and every one containing it
    within the instance bound, or the write is rolled back (typed 422)."""
    await session.flush()
    try:
        await reject_oversize(session, owner_id, assembly_id)
    except ValidationApiError:
        await session.rollback()
        raise


def _driven(pattern: ComponentPatternParams, driven_count: int | None) -> int | None:
    return driven_count if isinstance(pattern, HoleComponentPattern) else None


@router.post("/{assembly_id}/patterns", status_code=status.HTTP_201_CREATED)
async def create_pattern(
    assembly_id: uuid.UUID,
    request: PatternCreate,
    owner_id: Principal,
    session: SessionDep,
    driven_count: DrivenCount = None,
) -> PatternMutationResponse:
    """Add a component pattern (appended to the assembly's patterns).

    Refusals (422): ``pattern_seed_unknown``, ``pattern_reference_unknown``,
    ``pattern_needs_part``, ``pattern_driver_mismatch``, an expression error
    (its own code) or a value out of range (``pattern_value_invalid``),
    ``pattern_limit_exceeded``, ``assembly_too_large``,
    ``stale_assembly_version``. Another user's assembly is a uniform 404.
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    pattern = await _checked(session, owner_id, assembly_id, request.pattern)
    position = await require_pattern_room(session, assembly_id)

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    row = db.AssemblyPattern(
        id=uuid.uuid4(),
        assembly_id=assembly_id,
        order_index=position,
        type=pattern.type,
        params=pattern.model_dump(mode="json"),
        driven_count=_driven(pattern, driven_count),
    )
    session.add(row)
    await _within_bounds(session, owner_id, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "pattern_created",
        assembly_id=str(assembly_id),
        pattern_id=str(row.id),
        pattern_type=row.type,
        doc_version=assembly.doc_version,
    )
    return PatternMutationResponse(
        pattern=pattern_response(row), doc_version=assembly.doc_version
    )


@router.patch("/{assembly_id}/patterns/{pattern_id}")
async def update_pattern(
    assembly_id: uuid.UUID,
    pattern_id: uuid.UUID,
    request: PatternUpdate,
    owner_id: Principal,
    session: SessionDep,
    driven_count: DrivenCount = None,
) -> PatternMutationResponse:
    """Replace a pattern's definition; it keeps its id and its place. The
    same refusals as a create, plus ``pattern_not_found`` (404)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    row = await _get_pattern(session, assembly, pattern_id)
    pattern = await _checked(session, owner_id, assembly_id, request.pattern)

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    row.type = pattern.type
    row.params = pattern.model_dump(mode="json")
    row.driven_count = _driven(pattern, driven_count)
    await _within_bounds(session, owner_id, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "pattern_updated",
        assembly_id=str(assembly_id),
        pattern_id=str(pattern_id),
        doc_version=assembly.doc_version,
    )
    return PatternMutationResponse(
        pattern=pattern_response(row), doc_version=assembly.doc_version
    )


@router.delete("/{assembly_id}/patterns/{pattern_id}")
async def delete_pattern(
    assembly_id: uuid.UUID,
    pattern_id: uuid.UUID,
    expected_version: Annotated[
        int,
        Query(ge=0, description="Optimistic-concurrency guard (design §1.2)"),
    ],
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Delete a pattern and with it every copy it placed; its seeds stay."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, expected_version)
    row = await _get_pattern(session, assembly, pattern_id)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    await session.delete(row)
    await renumber_patterns(session, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "pattern_deleted",
        assembly_id=str(assembly_id),
        pattern_id=str(pattern_id),
        doc_version=assembly.doc_version,
    )
    return await graph_response(session, assembly)
