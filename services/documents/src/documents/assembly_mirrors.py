"""``/api/v1/assemblies/{id}/mirrors``: component mirrors (ASM-MIRROR-COMPONENT).

Create, replace and delete an assembly's component mirrors (SolidWorks' Mirror
Components, Fusion's Mirror on components). A mirror is ONE entry of the
assembly holding its definition; geometry places its twins after the solve.
Every write bumps ``doc_version`` under the usual optimistic-concurrency guard
and is one undo step; the write rules are :mod:`documents.mirror_rows`.

The instance bound counts twins: a mirror that would take this assembly, or any
assembly that contains it, past it is refused with the typed
``assembly_too_large``.

No kernel import (CLAUDE.md boundaries).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from loft_wire.assemblies import AssemblyGraphResponse
from loft_wire.component_mirrors import (
    MirrorCreate,
    MirrorMutationResponse,
    MirrorUpdate,
)
from py_kit import NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assemblies import ensure_fresh, graph_response
from documents.assembly_history import ASSEMBLY_HISTORY
from documents.mirror_rows import (
    mirror_response,
    renumber_mirrors,
    require_mirror_room,
    validate_mirror,
)
from documents.occurrences import reject_oversize
from documents.parts import Principal, get_owned_assembly

_logger = get_logger("documents.assembly_mirrors")

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])


async def _get_mirror(
    session: AsyncSession, assembly: db.Assembly, mirror_id: uuid.UUID
) -> db.AssemblyMirror:
    row = await session.get(db.AssemblyMirror, mirror_id)
    if row is None or row.assembly_id != assembly.id:
        raise NotFoundError("Mirror not found.", code="mirror_not_found")
    return row


async def _within_bounds(
    session: AsyncSession, owner_id: uuid.UUID, assembly_id: uuid.UUID
) -> None:
    """The written mirror keeps this assembly and every one containing it
    within the instance bound, or the write is rolled back (typed 422)."""
    await session.flush()
    try:
        await reject_oversize(session, owner_id, assembly_id)
    except ValidationApiError:
        await session.rollback()
        raise


@router.post("/{assembly_id}/mirrors", status_code=status.HTTP_201_CREATED)
async def create_mirror(
    assembly_id: uuid.UUID,
    request: MirrorCreate,
    owner_id: Principal,
    session: SessionDep,
) -> MirrorMutationResponse:
    """Add a component mirror (appended to the assembly's mirrors).

    Refusals (422): ``mirror_seed_unknown``, ``mirror_opposite_hand_needs_part``,
    ``mirror_reference_unknown``, ``mirror_needs_part``,
    ``mirror_limit_exceeded``, ``assembly_too_large``,
    ``stale_assembly_version``. Another user's assembly is a uniform 404.
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    await validate_mirror(session, owner_id, assembly_id, request.mirror)
    position = await require_mirror_room(session, assembly_id)

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    row = db.AssemblyMirror(
        id=uuid.uuid4(),
        assembly_id=assembly_id,
        order_index=position,
        params=request.mirror.model_dump(mode="json"),
    )
    session.add(row)
    await _within_bounds(session, owner_id, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mirror_created",
        assembly_id=str(assembly_id),
        mirror_id=str(row.id),
        doc_version=assembly.doc_version,
    )
    return MirrorMutationResponse(
        mirror=mirror_response(row), doc_version=assembly.doc_version
    )


@router.patch("/{assembly_id}/mirrors/{mirror_id}")
async def update_mirror(
    assembly_id: uuid.UUID,
    mirror_id: uuid.UUID,
    request: MirrorUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> MirrorMutationResponse:
    """Replace a mirror's definition; it keeps its id (and so its twins'
    ids) and its place. The same refusals as a create, plus
    ``mirror_not_found`` (404)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, request.expected_version)
    row = await _get_mirror(session, assembly, mirror_id)
    await validate_mirror(session, owner_id, assembly_id, request.mirror)

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    row.params = request.mirror.model_dump(mode="json")
    await _within_bounds(session, owner_id, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mirror_updated",
        assembly_id=str(assembly_id),
        mirror_id=str(mirror_id),
        doc_version=assembly.doc_version,
    )
    return MirrorMutationResponse(
        mirror=mirror_response(row), doc_version=assembly.doc_version
    )


@router.delete("/{assembly_id}/mirrors/{mirror_id}")
async def delete_mirror(
    assembly_id: uuid.UUID,
    mirror_id: uuid.UUID,
    expected_version: Annotated[
        int,
        Query(ge=0, description="Optimistic-concurrency guard (design §1.2)"),
    ],
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Delete a mirror and with it every twin it placed; its seeds stay."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    ensure_fresh(assembly, expected_version)
    row = await _get_mirror(session, assembly, mirror_id)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    await session.delete(row)
    await renumber_mirrors(session, assembly_id)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mirror_deleted",
        assembly_id=str(assembly_id),
        mirror_id=str(mirror_id),
        doc_version=assembly.doc_version,
    )
    return await graph_response(session, assembly)
