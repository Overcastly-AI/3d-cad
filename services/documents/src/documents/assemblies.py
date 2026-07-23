"""``/api/v1/assemblies`` — assembly CRUD (graph of instances + mates).

Implements the write rules of docs/design/assemblies.md §1: a NEW document type
(§1.1) with owner-scoped auth + uniform-404 visibility (mirroring
:mod:`documents.parts`), optimistic concurrency via ``doc_version`` (stale write
→ **422**, keeping 409 unambiguous for the dependents conflict — the
feature-tree.md §1.2 pattern), cross-document integrity enforced at write time
(existence + acyclicity + 409-with-dependents — §1.2, NOT a DB FK), and
dense-integer renumbering of the stable instance/mate order.

This service never imports kernel code (CLAUDE.md service boundaries): a mate
names part geometry with pure-pydantic signatures (:mod:`py_kit.schemas.
assemblies`), never a kernel type. Acyclicity is a bounded documents-side walk
over the sub-assembly instance edges (§1.2) — the cross-document analogue of the
part tree's strict-backward acyclicity — rejected cleanly at write time, never a
stack overflow at eval.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from py_kit import ConflictError, NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.assemblies import (
    AssemblyBomResponse,
    AssemblyCreate,
    AssemblyGraphResponse,
    AssemblyListResponse,
    AssemblyResponse,
    AssemblyUndoRedoRequest,
    AssemblyUpdate,
    BomLine,
    InstanceCreate,
    InstanceMutationResponse,
    InstanceResponse,
    InstanceUpdate,
    Mate,
    MateCreate,
    MateMutationResponse,
    MateResponse,
    RefDocumentKind,
    mate_instance_ids,
)
from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assembly_history import (
    ASSEMBLY_HISTORY,
    ordered_instances,
    ordered_mates,
)
from documents.history_core import Direction
from documents.parts import (
    Principal,
    get_owned_assembly,
    referenced_document_exists,
    reject_if_instanced,
)

_logger = get_logger("documents.assemblies")

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])

#: Reconstruct a stored mate row's params into the discriminated union.
_MATE_ADAPTER: TypeAdapter[Mate] = TypeAdapter(Mate)


# --- shared plumbing --------------------------------------------------------------


def _ensure_fresh(assembly: db.Assembly, expected_version: int) -> None:
    """Optimistic-concurrency gate: stale writes are 422 (design §1.2).

    422 — NOT 409 — so the two write-failure modes are distinguishable by
    status alone (409 stays reserved for the delete-with-dependents conflict).
    """
    if assembly.doc_version != expected_version:
        raise ValidationApiError(
            "Stale assembly version: the assembly changed since it was last read.",
            code="stale_assembly_version",
            details={
                "provided": expected_version,
                "current": assembly.doc_version,
            },
        )


async def _get_instance(
    session: AsyncSession, assembly: db.Assembly, instance_id: uuid.UUID
) -> db.Instance:
    """An instance of *assembly*, or 404 (unknown id == another assembly's id)."""
    instance = await session.get(db.Instance, instance_id)
    if instance is None or instance.assembly_id != assembly.id:
        raise NotFoundError("Instance not found.", code="instance_not_found")
    return instance


async def _get_mate(
    session: AsyncSession, assembly: db.Assembly, mate_id: uuid.UUID
) -> db.Mate:
    """A mate of *assembly*, or 404 (unknown id == another assembly's id)."""
    mate = await session.get(db.Mate, mate_id)
    if mate is None or mate.assembly_id != assembly.id:
        raise NotFoundError("Mate not found.", code="mate_not_found")
    return mate


async def _count(
    session: AsyncSession,
    model: type[db.Instance] | type[db.Mate],
    assembly_id: uuid.UUID,
) -> int:
    """How many instances/mates the assembly already has (append position)."""
    result = await session.execute(
        select(func.count()).select_from(model).where(model.assembly_id == assembly_id)
    )
    return int(result.scalar_one())


async def _shift_down(
    session: AsyncSession,
    model: type[db.Instance] | type[db.Mate],
    assembly_id: uuid.UUID,
    from_index: int,
) -> None:
    """Close the gap left by a delete: shift every row at/after *from_index* by
    -1, ascending so the shuffle is legal even under IMMEDIATE unique checking."""
    result = await session.execute(
        select(model.id, model.order_index)
        .where(model.assembly_id == assembly_id, model.order_index >= from_index)
        .order_by(model.order_index)
    )
    for row_id, order_index in result.all():
        await session.execute(
            update(model).where(model.id == row_id).values(order_index=order_index - 1)
        )


# --- cross-document integrity (§1.2) ----------------------------------------------


async def _sub_assembly_children(
    session: AsyncSession, assembly_id: uuid.UUID
) -> list[uuid.UUID]:
    """The assembly ids this assembly instances as SUB-ASSEMBLIES (graph edges)."""
    result = await session.execute(
        select(db.Instance.ref_document_id).where(
            db.Instance.assembly_id == assembly_id,
            db.Instance.ref_document_kind == "assembly",
        )
    )
    return list(result.scalars())


async def _serialize_owner_cycle_writes(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    """Serialize cycle-sensitive writes PER OWNER before the acyclicity walk.

    The :func:`_reaches` guard is read-then-write: it walks sub-assembly edges
    with plain unlocked SELECTs, then the caller commits a new edge. Row-locking
    only the mutated assembly (``get_owned_assembly(for_update=True)``) does NOT
    close the window: under READ COMMITTED two concurrent SAME-OWNER reciprocal
    adds — "B into A" (row-locks A) and "A into B" (row-locks B) — each run the
    walk without seeing the other's uncommitted edge, both pass, both commit →
    a persisted cycle A→B→A, defeating the write-time acyclicity invariant the
    whole Assemblies pillar relies on (eval assuming an acyclic graph).

    A transaction-scoped Postgres advisory lock keyed on the owner makes at
    most one cycle-creating write per owner run its check+write at a time (a
    SINGLE lock per owner → deadlock-free, auto-released at commit/rollback);
    the loser then walks the winner's now-committed edge and is cleanly
    rejected ``assembly_cycle``. Acquired AFTER the disjoint per-row FOR UPDATE
    locks, but since all cycle writers contend on the one owner lock at most one
    is ever in the critical section — no lock-order cycle, so no deadlock.

    SQLite (the unit-test dialect) already globally serializes writes (one
    writer), so the TOCTOU cannot occur there and ``pg_advisory_xact_lock`` does
    not exist — skip the lock on any non-Postgres dialect (the same
    dialect-aware posture as :func:`get_owned_assembly`'s ``for_update``).
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(str(owner_id))))
    )


async def _reaches(session: AsyncSession, start: uuid.UUID, target: uuid.UUID) -> bool:
    """Is *target* reachable from *start* over sub-assembly edges (inclusive)?

    A bounded, deterministic documents-side DFS (§1.2, no kernel). Adding an
    instance that makes assembly A reference sub-assembly X creates the edge
    A→X; that closes a cycle iff X can already reach A (``_reaches(X, A)``) —
    which subsumes the direct self-reference X == A. ``seen`` bounds the walk
    even on a (pre-existing) malformed graph, so it can never loop forever.
    """
    seen: set[uuid.UUID] = set()
    stack: list[uuid.UUID] = [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(await _sub_assembly_children(session, node))
    return False


# --- serialization ----------------------------------------------------------------


def _instance_response(instance: db.Instance) -> InstanceResponse:
    """Row → DTO (``from_attributes``): the Placement JSONB and the
    ``ref_document_kind`` string are validated into their models by pydantic."""
    return InstanceResponse.model_validate(instance)


def _mate_response(mate: db.Mate) -> MateResponse:
    """Row → DTO: the params JSONB reassembled into the discriminated union."""
    return MateResponse(
        id=mate.id,
        assembly_id=mate.assembly_id,
        order_index=mate.order_index,
        mate=_MATE_ADAPTER.validate_python(mate.params),
    )


async def graph_response(
    session: AsyncSession, assembly: db.Assembly
) -> AssemblyGraphResponse:
    instances = await ordered_instances(session, assembly.id)
    mates = await ordered_mates(session, assembly.id)
    can_undo, can_redo = await ASSEMBLY_HISTORY.availability(session, assembly)
    return AssemblyGraphResponse(
        assembly=AssemblyResponse.model_validate(assembly),
        doc_version=assembly.doc_version,
        instances=[_instance_response(row) for row in instances],
        mates=[_mate_response(row) for row in mates],
        can_undo=can_undo,
        can_redo=can_redo,
    )


# --- assembly routes --------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_assembly(
    request: AssemblyCreate, owner_id: Principal, session: SessionDep
) -> AssemblyResponse:
    """Create an assembly (201; envelope 409 on a duplicate name for this owner)."""
    assembly = db.Assembly(
        owner_id=owner_id, name=request.name, length_unit=request.length_unit
    )
    session.add(assembly)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"An assembly named {request.name!r} already exists.",
            code="assembly_name_taken",
        ) from None
    _logger.info(
        "assembly_created", assembly_id=str(assembly.id), owner_id=str(owner_id)
    )
    return AssemblyResponse.model_validate(assembly)


@router.get("")
async def list_assemblies(
    owner_id: Principal, session: SessionDep
) -> AssemblyListResponse:
    """The caller's assemblies, oldest first (deterministic id tiebreak)."""
    result = await session.execute(
        select(db.Assembly)
        .where(db.Assembly.owner_id == owner_id)
        .order_by(db.Assembly.created_at, db.Assembly.id)
    )
    return AssemblyListResponse(
        assemblies=[AssemblyResponse.model_validate(row) for row in result.scalars()]
    )


@router.get("/{assembly_id}")
async def get_assembly(
    assembly_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> AssemblyGraphResponse:
    """One owned assembly with its full instance + mate graph (uniform 404)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id)
    return await graph_response(session, assembly)


async def _resolve_document_names(
    session: AsyncSession,
    owner_id: uuid.UUID,
    refs: set[tuple[uuid.UUID, RefDocumentKind]],
) -> dict[tuple[uuid.UUID, RefDocumentKind], str]:
    """Current names of the referenced parts / assemblies, keyed by (id, kind).

    Owner-scoped (defense-in-depth — references are same-owner enforced at write
    time): a referenced document DELETED since it was instanced is simply absent
    from the map, and the BOM reports that line ``missing`` rather than 500-ing.
    One query per kind over only the ids actually referenced.
    """
    part_ids = {ref_id for ref_id, kind in refs if kind == "part"}
    assembly_ids = {ref_id for ref_id, kind in refs if kind == "assembly"}
    names: dict[tuple[uuid.UUID, RefDocumentKind], str] = {}
    if part_ids:
        result = await session.execute(
            select(db.Part.id, db.Part.name).where(
                db.Part.id.in_(part_ids), db.Part.owner_id == owner_id
            )
        )
        for ref_id, name in result.all():
            names[(ref_id, "part")] = name
    if assembly_ids:
        result = await session.execute(
            select(db.Assembly.id, db.Assembly.name).where(
                db.Assembly.id.in_(assembly_ids), db.Assembly.owner_id == owner_id
            )
        )
        for ref_id, name in result.all():
            names[(ref_id, "assembly")] = name
    return names


async def _bom_response(
    session: AsyncSession, assembly: db.Assembly
) -> AssemblyBomResponse:
    """Aggregate the assembly's DIRECT instances into a flat BOM (read model).

    One line per referenced document (``ref_document_id`` + kind), quantity =
    the count of instances sharing it, name resolved to the referenced
    document's CURRENT name (null + ``missing`` when deleted-but-still-instanced).
    Deterministically ordered by resolved name then ``ref_document_id`` (missing
    lines sort last, then by id) so the list is stable across reads.
    """
    result = await session.execute(
        select(
            db.Instance.ref_document_id,
            db.Instance.ref_document_kind,
            func.count(),
        )
        .where(db.Instance.assembly_id == assembly.id)
        .group_by(db.Instance.ref_document_id, db.Instance.ref_document_kind)
    )
    groups: list[tuple[uuid.UUID, RefDocumentKind, int]] = [
        (ref_id, kind, int(count)) for ref_id, kind, count in result.all()
    ]
    names = await _resolve_document_names(
        session, assembly.owner_id, {(ref_id, kind) for ref_id, kind, _ in groups}
    )
    lines = [
        BomLine(
            ref_document_id=ref_id,
            ref_document_kind=kind,
            name=names.get((ref_id, kind)),
            missing=(ref_id, kind) not in names,
            quantity=count,
        )
        for ref_id, kind, count in groups
    ]
    # Stable order: resolved name, then id; deleted-ref (null name) lines last.
    lines.sort(
        key=lambda line: (line.name is None, line.name or "", str(line.ref_document_id))
    )
    return AssemblyBomResponse(
        assembly_id=assembly.id,
        lines=lines,
        total_instances=sum(line.quantity for line in lines),
    )


@router.get("/{assembly_id}/bom")
async def get_assembly_bom(
    assembly_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> AssemblyBomResponse:
    """The assembly's flat bill of materials (direct instances only; uniform 404).

    A pure read model (assemblies.md residual): groups the assembly's DIRECT
    instances by referenced document, resolving each to its current name and
    kind. NOT recursive into rigid sub-assemblies — a sub-assembly instance is a
    single ``kind: "assembly"`` line (recursive/indented BOM is a tracked
    follow-up). A referenced document deleted while still instanced is reported
    as a ``missing`` line with a null name, never a 500.
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id)
    return await _bom_response(session, assembly)


@router.patch("/{assembly_id}")
async def update_assembly(
    assembly_id: uuid.UUID,
    request: AssemblyUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyResponse:
    """Rename and/or re-unit an assembly (bumps ``doc_version``; 409 on a name
    clash).

    Changing ``length_unit`` is a document edit (docs/design/units.md §U1) —
    metadata only, storage stays canonical mm — and bumps ``doc_version`` like
    any header mutation. Unlike a part rename (outside UR1 history), this IS a
    UR3 history event — the snapshot state carries the mutable header fields,
    so undo restores them (docs/design/undo-redo.md UR3).
    """
    if request.name is None and request.length_unit is None:
        raise ValidationApiError(
            "Provide at least one of name or length_unit.",
            code="empty_assembly_update",
        )
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, request.expected_version)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    if request.name is not None:
        assembly.name = request.name
    if request.length_unit is not None:
        assembly.length_unit = request.length_unit
    assembly.doc_version += 1
    try:
        # record() flushes while serializing, so a duplicate-name violation can
        # surface here as well as at commit — both map to the friendly 409.
        await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"An assembly named {request.name!r} already exists.",
            code="assembly_name_taken",
        ) from None
    _logger.info(
        "assembly_updated",
        assembly_id=str(assembly.id),
        doc_version=assembly.doc_version,
    )
    return AssemblyResponse.model_validate(assembly)


@router.delete("/{assembly_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assembly(
    assembly_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> None:
    """Delete an owned assembly; 409 when instanced as a sub-assembly elsewhere.

    The assembly→instances/mates CASCADE removes its own graph. A 409-with-
    dependents pre-check (design §1.2, mirroring the part 409) refuses the
    delete while ANOTHER assembly still instances this one as a sub-assembly,
    listing the referencing assemblies.
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id)
    await reject_if_instanced(
        session, assembly_id, owner_id, code="assembly_has_dependents"
    )
    await session.delete(assembly)
    await session.commit()
    _logger.info(
        "assembly_deleted", assembly_id=str(assembly_id), owner_id=str(owner_id)
    )


# --- instance routes --------------------------------------------------------------


@router.post("/{assembly_id}/instances", status_code=status.HTTP_201_CREATED)
async def create_instance(
    assembly_id: uuid.UUID,
    request: InstanceCreate,
    owner_id: Principal,
    session: SessionDep,
) -> InstanceMutationResponse:
    """Add an instance referencing a part / sub-assembly (append at the tip).

    Enforces cross-document integrity (§1.2): the referenced document must exist
    and belong to the caller (else ``ref_document_not_found`` 422), and a
    sub-assembly reference must not create a cycle (``assembly_cycle`` 422 —
    walked here, never a stack overflow at eval).
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, request.expected_version)

    # Only a sub-assembly edge can close a cycle; serialize those per owner
    # (Postgres) before the read-then-write acyclicity walk so two concurrent
    # reciprocal adds can't each miss the other's uncommitted edge (TOCTOU).
    if request.ref_document_kind == "assembly":
        await _serialize_owner_cycle_writes(session, owner_id)

    if not await referenced_document_exists(
        session, owner_id, request.ref_document_id, request.ref_document_kind
    ):
        raise ValidationApiError(
            f"Referenced {request.ref_document_kind} {request.ref_document_id} "
            "does not exist.",
            code="ref_document_not_found",
            details={
                "ref_document_id": str(request.ref_document_id),
                "ref_document_kind": request.ref_document_kind,
            },
        )
    if request.ref_document_kind == "assembly" and await _reaches(
        session, request.ref_document_id, assembly_id
    ):
        raise ValidationApiError(
            "An assembly cannot contain itself (directly or through a "
            "sub-assembly chain).",
            code="assembly_cycle",
            details={"ref_document_id": str(request.ref_document_id)},
        )

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    position = await _count(session, db.Instance, assembly_id)
    instance = db.Instance(
        id=uuid.uuid4(),
        assembly_id=assembly_id,
        ref_document_id=request.ref_document_id,
        ref_document_kind=request.ref_document_kind,
        ref_pinned_version=None,  # v1 tracks tip (§1.3)
        name=request.name,
        grounded=request.grounded,
        placement=request.placement.model_dump(mode="json"),
        order_index=position,
    )
    session.add(instance)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "instance_created",
        assembly_id=str(assembly_id),
        instance_id=str(instance.id),
        ref_document_id=str(instance.ref_document_id),
        doc_version=assembly.doc_version,
    )
    return InstanceMutationResponse(
        instance=_instance_response(instance), doc_version=assembly.doc_version
    )


@router.patch("/{assembly_id}/instances/{instance_id}")
async def update_instance(
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
    request: InstanceUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> InstanceMutationResponse:
    """Re-place / rename / (un)ground / reorder an instance (bumps ``doc_version``).

    Re-pointing the referenced document is deliberately NOT an update (it
    changes the graph edge the acyclicity walk sees) — delete + recreate.
    """
    if (
        request.name is None
        and request.placement is None
        and request.grounded is None
        and request.order_index is None
    ):
        raise ValidationApiError(
            "Provide at least one of name, placement, grounded, or order_index.",
            code="empty_instance_update",
        )
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, request.expected_version)
    instance = await _get_instance(session, assembly, instance_id)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)

    if request.name is not None:
        instance.name = request.name
    if request.placement is not None:
        instance.placement = request.placement.model_dump(mode="json")
    if request.grounded is not None:
        instance.grounded = request.grounded
    if request.order_index is not None:
        await _reorder_instance(session, assembly_id, instance, request.order_index)

    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "instance_updated",
        assembly_id=str(assembly_id),
        instance_id=str(instance_id),
        doc_version=assembly.doc_version,
    )
    return InstanceMutationResponse(
        instance=_instance_response(instance), doc_version=assembly.doc_version
    )


async def _reorder_instance(
    session: AsyncSession,
    assembly_id: uuid.UUID,
    instance: db.Instance,
    new_index: int,
) -> None:
    """Move *instance* to *new_index*, renumbering the rest dense 0..n-1.

    Two-phase through a disjoint range (final+offset → final) so no per-row
    state is ever duplicated under IMMEDIATE unique checking (the reorder-
    features posture)."""
    instances = await ordered_instances(session, assembly_id)
    ids = [row.id for row in instances]
    ids.remove(instance.id)
    clamped = max(0, min(new_index, len(ids)))
    ids.insert(clamped, instance.id)
    if [row.id for row in instances] == ids:
        return  # no-op: already in the requested position
    final_index = {row_id: i for i, row_id in enumerate(ids)}
    offset = len(ids)
    for row_id in ids:
        await session.execute(
            update(db.Instance)
            .where(db.Instance.id == row_id)
            .values(order_index=final_index[row_id] + offset)
        )
    for row_id in ids:
        await session.execute(
            update(db.Instance)
            .where(db.Instance.id == row_id)
            .values(order_index=final_index[row_id])
        )


@router.delete("/{assembly_id}/instances/{instance_id}")
async def delete_instance(
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
    expected_version: Annotated[
        int,
        Query(ge=0, description="Optimistic-concurrency guard (design §1.2)"),
    ],
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Remove an instance; also removes mates that reference it (bumps version).

    A mate is a constraint EDGE, meaningless without both endpoints — so
    deleting an instance cascades to the mates naming it (documents-side, since
    the mate's instance refs live in JSONB, not a DB FK). Both instances and
    mates are renumbered dense. Returns the updated graph (the client's new
    ``doc_version``)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, expected_version)
    instance = await _get_instance(session, assembly, instance_id)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)

    # Cascade-remove mates that reference this instance (§1.2 graph integrity).
    for mate in await ordered_mates(session, assembly_id):
        if instance_id in mate_instance_ids(_MATE_ADAPTER.validate_python(mate.params)):
            deleted_mate_index = mate.order_index
            await session.delete(mate)
            await session.flush()
            await _shift_down(session, db.Mate, assembly_id, deleted_mate_index + 1)

    deleted_index = instance.order_index
    await session.delete(instance)
    await session.flush()
    await _shift_down(session, db.Instance, assembly_id, deleted_index + 1)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "instance_deleted",
        assembly_id=str(assembly_id),
        instance_id=str(instance_id),
        doc_version=assembly.doc_version,
    )
    return await graph_response(session, assembly)


# --- mate routes ------------------------------------------------------------------


@router.post("/{assembly_id}/mates", status_code=status.HTTP_201_CREATED)
async def create_mate(
    assembly_id: uuid.UUID,
    request: MateCreate,
    owner_id: Principal,
    session: SessionDep,
) -> MateMutationResponse:
    """Add a mate (append at the tip). Every instance it names must belong to
    this assembly (``mate_instance_unknown`` 422 otherwise)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, request.expected_version)

    named_ids = mate_instance_ids(request.mate)
    # A mate is a constraint EDGE between two DISTINCT instances; naming one
    # instance on both sides (lock a==b, or a face/axis mate whose two refs
    # share an instance) is degenerate — it constrains an instance to itself.
    if named_ids[0] == named_ids[1]:
        raise ValidationApiError(
            "A mate cannot constrain an instance to itself.",
            code="mate_self_reference",
            details={"instance_id": str(named_ids[0])},
        )

    member_ids = {row.id for row in await ordered_instances(session, assembly_id)}
    for named_id in named_ids:
        if named_id not in member_ids:
            raise ValidationApiError(
                f"Mate references instance {named_id}, which is not part of this "
                "assembly.",
                code="mate_instance_unknown",
                details={"instance_id": str(named_id)},
            )

    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)
    position = await _count(session, db.Mate, assembly_id)
    mate = db.Mate(
        id=uuid.uuid4(),
        assembly_id=assembly_id,
        order_index=position,
        type=request.mate.type,
        params=request.mate.model_dump(mode="json"),
    )
    session.add(mate)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mate_created",
        assembly_id=str(assembly_id),
        mate_id=str(mate.id),
        mate_type=mate.type,
        doc_version=assembly.doc_version,
    )
    return MateMutationResponse(
        mate=_mate_response(mate), doc_version=assembly.doc_version
    )


@router.delete("/{assembly_id}/mates/{mate_id}")
async def delete_mate(
    assembly_id: uuid.UUID,
    mate_id: uuid.UUID,
    expected_version: Annotated[
        int,
        Query(ge=0, description="Optimistic-concurrency guard (design §1.2)"),
    ],
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Remove a mate; renumbers the rest dense (bumps ``doc_version``)."""
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, expected_version)
    mate = await _get_mate(session, assembly, mate_id)
    pre_op = await ASSEMBLY_HISTORY.baseline_state(session, assembly)

    deleted_index = mate.order_index
    await session.delete(mate)
    await session.flush()
    await _shift_down(session, db.Mate, assembly_id, deleted_index + 1)
    assembly.doc_version += 1
    await ASSEMBLY_HISTORY.record(session, assembly, pre_op)
    await session.commit()
    _logger.info(
        "mate_deleted",
        assembly_id=str(assembly_id),
        mate_id=str(mate_id),
        doc_version=assembly.doc_version,
    )
    return await graph_response(session, assembly)


# --- undo / redo (docs/design/undo-redo.md UR3) -----------------------------------


async def _reject_restore_integrity_violations(
    session: AsyncSession, owner_id: uuid.UUID, assembly_id: uuid.UUID
) -> None:
    """Post-restore cross-document integrity pass (UR3 review fix).

    A restore re-enters the assembly graph, so it must uphold the SAME
    write-time invariants every other write path enforces (§1.2) — the world
    may have legally moved since the snapshot was taken:

    - a restored instance's referenced document may have been DELETED since
      (``reject_if_instanced`` only guards live instance rows, deliberately —
      snapshots never block a delete), which would leave a dangling
      ``ref_document_id``;
    - a restored sub-assembly edge may CLOSE A CYCLE with edges added since
      (the reviewer's repro: record A→B, delete it, add B→A, undo → A→B→A),
      violating the load-bearing write-time acyclicity invariant.

    Runs over the restored-but-uncommitted state, under the same per-owner
    advisory lock as :func:`create_instance` when any sub-assembly edge is
    involved (so a restore can't race a concurrent reciprocal add past the
    walk). On violation: roll back — cursor, ring and ``doc_version`` all
    unmoved, the snapshot stays restorable once the conflict is resolved —
    and raise a single typed 409 ``assembly_restore_conflict`` whose
    ``details.reason`` names the failed check (``ref_document_not_found`` /
    ``assembly_cycle``, the live write paths' codes) plus the offending ids.
    One code (not the write paths' 422s) because this is a conflict between
    HISTORY and the current world, not a bad request — the client's move is
    to resolve the named conflict, not to fix its payload.
    """
    instances = await ordered_instances(session, assembly_id)
    if any(row.ref_document_kind == "assembly" for row in instances):
        await _serialize_owner_cycle_writes(session, owner_id)
    for row in instances:
        if not await referenced_document_exists(
            session, owner_id, row.ref_document_id, row.ref_document_kind
        ):
            details = {
                "reason": "ref_document_not_found",
                "instance_id": str(row.id),
                "ref_document_id": str(row.ref_document_id),
                "ref_document_kind": row.ref_document_kind,
            }
            await session.rollback()
            raise ConflictError(
                "Restoring this history step would reference a document that "
                "no longer exists.",
                code="assembly_restore_conflict",
                details=details,
            )
    for row in instances:
        if row.ref_document_kind == "assembly" and await _reaches(
            session, row.ref_document_id, assembly_id
        ):
            details = {
                "reason": "assembly_cycle",
                "instance_id": str(row.id),
                "ref_document_id": str(row.ref_document_id),
            }
            await session.rollback()
            raise ConflictError(
                "Restoring this history step would make the assembly contain "
                "itself (directly or through a sub-assembly chain).",
                code="assembly_restore_conflict",
                details=details,
            )


async def _restore_history_step(
    assembly_id: uuid.UUID,
    request: AssemblyUndoRedoRequest,
    owner_id: uuid.UUID,
    session: AsyncSession,
    direction: Direction,
) -> AssemblyGraphResponse:
    """Shared undo/redo body — the assembly sibling of the part's.

    Undo/redo ARE document edits: the same OCC guard as every other assembly
    write (stale → 422), a ``doc_version`` bump, and the restored graph in
    the response so the client re-renders (and re-evaluates) authoritatively.

    Boundary shape — undo at the ring's floor / redo at its top is a CLEAN
    no-op per the design ("clean no-ops, not errors"): 200 with the CURRENT
    graph, ``doc_version`` untouched, nothing committed. The UI disables the
    controls via ``can_undo``/``can_redo`` on this same response, so a click
    racing a just-changed history state lands harmlessly here and resyncs.

    Restoring a snapshotted assembly ``name`` (the header rides in UR3
    snapshots — see :mod:`documents.assembly_history`) can collide with a
    name taken since; that surfaces as the same friendly
    ``assembly_name_taken`` 409 the PATCH itself uses. Cross-document
    integrity (dangling refs / cycles) is re-checked post-restore —
    :func:`_reject_restore_integrity_violations` (409
    ``assembly_restore_conflict``).
    """
    assembly = await get_owned_assembly(session, owner_id, assembly_id, for_update=True)
    _ensure_fresh(assembly, request.expected_version)
    if await ASSEMBLY_HISTORY.restore_adjacent(session, assembly, direction):
        try:
            # Inside the try: the pass's first SELECT autoflushes the restored
            # header, so a name collision can surface HERE, not just at commit.
            await _reject_restore_integrity_violations(session, owner_id, assembly_id)
            assembly.doc_version += 1
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Assumption (reviewed 2026-07-18): the only constraint a restore
            # can violate at flush/commit is uq_assemblies_owner_name —
            # instances/mates were bulk-replaced with internally-consistent
            # snapshot rows and cross-document refs are checked by the
            # integrity pass above. Revisit if the snapshot state ever grows
            # a new constrained surface.
            raise ConflictError(
                "Restoring this history step would collide with an existing "
                "assembly name.",
                code="assembly_name_taken",
            ) from None
        _logger.info(
            "history_restored",
            assembly_id=str(assembly.id),
            direction=direction,
            history_cursor=assembly.history_cursor,
            doc_version=assembly.doc_version,
        )
    return await graph_response(session, assembly)


@router.post("/{assembly_id}/undo")
async def undo(
    assembly_id: uuid.UUID,
    request: AssemblyUndoRedoRequest,
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Restore the previous history snapshot VERBATIM (ids preserved).

    Clean no-op at the baseline; stale ``expected_version`` → 422.
    """
    return await _restore_history_step(assembly_id, request, owner_id, session, "undo")


@router.post("/{assembly_id}/redo")
async def redo(
    assembly_id: uuid.UUID,
    request: AssemblyUndoRedoRequest,
    owner_id: Principal,
    session: SessionDep,
) -> AssemblyGraphResponse:
    """Restore the next history snapshot VERBATIM (ids preserved).

    Clean no-op at the top of the ring; stale ``expected_version`` → 422.
    """
    return await _restore_history_step(assembly_id, request, owner_id, session, "redo")
