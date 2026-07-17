"""Per-assembly undo/redo history — the assembly serializer over the ring core.

Implements docs/design/undo-redo.md UR3 (the "same snapshot mechanism over
instances + mates" fast-follow). The ring/cursor/seq mechanics live ONCE in
:mod:`documents.history_core` (shared with part history); this module
contributes only what is assembly-specific: how an assembly's mutable state
serializes and restores.

State composition (see :class:`documents.db.AssemblySnapshot`): the ordered
instances and mates with EVERY mutable column verbatim, PLUS the mutable
header fields ``name`` / ``length_unit``. The header rides in the snapshot
because — unlike a part rename, which UR1 left outside history — the
assembly PATCH *is* a UR3 history event; recording it without capturing the
header would make undo-of-a-rename a visible no-op. Restoring a snapshotted
``name`` can collide with a name taken since (unique per owner); the
undo/redo routes surface that as the same 409 the PATCH itself uses.

The load-bearing rule (stated in full in the core's docstring): restore is
**verbatim** — instance/mate ids, order_index, placements, params and
timestamps byte-preserved, ids never re-minted, so a mate's instance
references inside its params JSONB stay valid across any undo/redo distance.
"""

import copy
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.history_core import DocumentHistory


async def ordered_instances(
    session: AsyncSession, assembly_id: uuid.UUID
) -> list[db.Instance]:
    """The assembly's instances, ``ORDER BY order_index`` (total by uniqueness).

    Shared with :mod:`documents.assemblies` (which imports it for its reads)
    so the deterministic ordered scan is defined once.
    """
    result = await session.execute(
        select(db.Instance)
        .where(db.Instance.assembly_id == assembly_id)
        .order_by(db.Instance.order_index)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def ordered_mates(session: AsyncSession, assembly_id: uuid.UUID) -> list[db.Mate]:
    """The assembly's mates, ``ORDER BY order_index`` (total by uniqueness)."""
    result = await session.execute(
        select(db.Mate)
        .where(db.Mate.assembly_id == assembly_id)
        .order_by(db.Mate.order_index)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _serialize_state(
    session: AsyncSession, assembly: db.Assembly
) -> dict[str, Any]:
    """The assembly's full mutable state, verbatim (design §"Model").

    Flushes first so the state reflects every pending write of the current
    transaction (renumbered indexes, fresh defaults). Ordering is
    deterministic — instances and mates by ``order_index`` (total by
    uniqueness) — so equal graphs serialize byte-identically. JSONB payloads
    (placement, mate params) are deep-copied so a later in-place mutation of
    a live row can never silently rewrite a captured snapshot (the UR1
    review hardening, applied here from the start).
    """
    await session.flush()
    instances = await ordered_instances(session, assembly.id)
    mates = await ordered_mates(session, assembly.id)
    return {
        "name": assembly.name,
        "length_unit": assembly.length_unit,
        "instances": [
            {
                "id": str(instance.id),
                "order_index": instance.order_index,
                "ref_document_id": str(instance.ref_document_id),
                "ref_document_kind": instance.ref_document_kind,
                "ref_pinned_version": instance.ref_pinned_version,
                "name": instance.name,
                "grounded": instance.grounded,
                "placement": copy.deepcopy(instance.placement),
                "created_at": instance.created_at.isoformat(),
                "updated_at": instance.updated_at.isoformat(),
            }
            for instance in instances
        ],
        "mates": [
            {
                "id": str(mate.id),
                "order_index": mate.order_index,
                "type": mate.type,
                "params": copy.deepcopy(mate.params),
                "created_at": mate.created_at.isoformat(),
                "updated_at": mate.updated_at.isoformat(),
            }
            for mate in mates
        ],
    }


async def _apply_state(
    session: AsyncSession, assembly: db.Assembly, state: dict[str, Any]
) -> None:
    """Replace the assembly's instances + mates (and header) with a snapshot's.

    VERBATIM: same ids, same order_index, same placements/params/timestamps.
    Instances and mates carry no DB FK between them (a mate's instance refs
    live inside its params JSONB), so plain bulk delete + re-insert is safe
    in either order. Runs inside the caller's transaction (the core sets the
    cursor and the route bumps ``doc_version`` + commits).
    """
    await session.execute(delete(db.Mate).where(db.Mate.assembly_id == assembly.id))
    await session.execute(
        delete(db.Instance).where(db.Instance.assembly_id == assembly.id)
    )
    for row in state["instances"]:
        session.add(
            db.Instance(
                id=uuid.UUID(row["id"]),
                assembly_id=assembly.id,
                ref_document_id=uuid.UUID(row["ref_document_id"]),
                ref_document_kind=row["ref_document_kind"],
                ref_pinned_version=row["ref_pinned_version"],
                name=row["name"],
                grounded=row["grounded"],
                placement=row["placement"],
                order_index=row["order_index"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        )
    for row in state["mates"]:
        session.add(
            db.Mate(
                id=uuid.UUID(row["id"]),
                assembly_id=assembly.id,
                order_index=row["order_index"],
                type=row["type"],
                params=row["params"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        )
    await session.flush()
    assembly.name = state["name"]
    assembly.length_unit = state["length_unit"]


def _make_snapshot(
    assembly_id: uuid.UUID, seq: int, state: dict[str, Any]
) -> db.AssemblySnapshot:
    return db.AssemblySnapshot(assembly_id=assembly_id, seq=seq, state=state)


#: The assembly graph's history store (docs/design/undo-redo.md UR3).
ASSEMBLY_HISTORY = DocumentHistory[db.Assembly](
    kind="assembly",
    snapshot_model=db.AssemblySnapshot,
    scope_id=db.AssemblySnapshot.assembly_id,
    seq=db.AssemblySnapshot.seq,
    state=db.AssemblySnapshot.state,
    serialize=_serialize_state,
    apply_state=_apply_state,
    make_snapshot=_make_snapshot,
)
