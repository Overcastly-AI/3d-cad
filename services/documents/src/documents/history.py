"""Per-part undo/redo history — bounded tree-state snapshots.

Implements docs/design/undo-redo.md (UR1). The load-bearing decision, applied
here and nowhere else (DRY — one snapshot/restore path covers create, update,
delete and reorder identically):

    Undo/redo restore a snapshot **verbatim** — every feature id, dependency
    edge, order_index and timestamp byte-preserved. Entities are NEVER
    re-created with fresh ids: a restore is a replace-from-snapshot inside one
    transaction, so ``feature_dependencies`` stays valid across any distance
    (re-minting ids would orphan every downstream reference on redo).

Model (design §"Model"): a linear per-part history with a cursor
(``parts.history_cursor`` = the ``part_snapshots.seq`` whose state IS the
current tree; NULL = never seeded). The baseline (pre-first-edit state) is
seeded lazily on the first mutation; every mutating op then appends its
post-op state at ``cursor + 1`` after truncating any redo tail, keeping seqs
contiguous within the retained window so adjacent snapshots are exactly
``cursor ± 1``. The ring is bounded at :data:`HISTORY_MAX`; appending past the
cap prunes from the floor (logged — never silently implied infinite).

Rollback-bar moves (``PUT /rollback``) are deliberately NOT history events in
v1 — the bar is view-state-like; it still RESTORES with each snapshot (it is
part of the serialized state), so a restore lands on a fully consistent tree.
"""

import copy
import uuid
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from py_kit import get_logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db

_logger = get_logger("documents.history")

#: Bounded ring size (design §"Model"): at most this many snapshots per part.
#: You can undo within the window, not before it.
HISTORY_MAX = 50

#: Which adjacent snapshot to restore: undo = ``cursor - 1``, redo = ``cursor + 1``.
Direction = Literal["undo", "redo"]


async def _serialize_state(session: AsyncSession, part: db.Part) -> dict[str, Any]:
    """The part's full mutable child state, verbatim (design §"Model").

    Flushes first so the state reflects every pending write of the current
    transaction (renumbered indexes, fresh defaults). Ordering is
    deterministic — features by ``order_index`` (total by uniqueness), edges
    by ``(feature_id, references_feature_id)`` — so equal trees serialize
    byte-identically.
    """
    await session.flush()
    features = (
        await session.execute(
            select(db.Feature)
            .where(db.Feature.part_id == part.id)
            .order_by(db.Feature.order_index)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    edges = (
        await session.execute(
            select(db.FeatureDependency)
            .where(db.FeatureDependency.part_id == part.id)
            .order_by(
                db.FeatureDependency.feature_id,
                db.FeatureDependency.references_feature_id,
            )
        )
    ).scalars()
    return {
        "rollback_feature_id": (
            str(part.rollback_feature_id)
            if part.rollback_feature_id is not None
            else None
        ),
        "features": [
            {
                "id": str(feature.id),
                "order_index": feature.order_index,
                "name": feature.name,
                "type": feature.type,
                "param_version": feature.param_version,
                # Deep-copy: the baseline is captured pre-op and flushed later
                # in the transaction; holding a reference to the live row's
                # params dict would let any future in-place mutation silently
                # rewrite the snapshot (review 2026-07-17, latent hardening).
                "params": copy.deepcopy(feature.params),
                "created_at": feature.created_at.isoformat(),
                "updated_at": feature.updated_at.isoformat(),
            }
            for feature in features
        ],
        "dependencies": [
            {
                "feature_id": str(edge.feature_id),
                "references_feature_id": str(edge.references_feature_id),
            }
            for edge in edges
        ],
    }


async def _bounds(session: AsyncSession, part_id: uuid.UUID) -> tuple[int, int] | None:
    """``(floor, top)`` seq bounds of the part's ring, or None when empty."""
    floor, top = (
        await session.execute(
            select(
                sa.func.min(db.PartSnapshot.seq), sa.func.max(db.PartSnapshot.seq)
            ).where(db.PartSnapshot.part_id == part_id)
        )
    ).one()
    if floor is None or top is None:
        return None
    return int(floor), int(top)


async def availability(session: AsyncSession, part: db.Part) -> tuple[bool, bool]:
    """``(can_undo, can_redo)`` — cursor position vs the ring bounds."""
    if part.history_cursor is None:
        return False, False
    bounds = await _bounds(session, part.id)
    if bounds is None:  # pragma: no cover - invariant: cursor set => rows exist
        return False, False
    floor, top = bounds
    return part.history_cursor > floor, part.history_cursor < top


async def baseline_state(session: AsyncSession, part: db.Part) -> dict[str, Any] | None:
    """The PRE-op state for lazy baseline seeding, or None once history exists.

    Call at the top of a mutating op (after the OCC guard, before any tree
    write); pass the result to :func:`record` after the mutation. Only the
    part's FIRST recorded mutation captures a baseline — that snapshot is the
    state undo can walk back to (design §"Model", ``snapshots[0]``).
    """
    if part.history_cursor is not None:
        return None
    return await _serialize_state(session, part)


async def record(
    session: AsyncSession, part: db.Part, baseline: dict[str, Any] | None
) -> None:
    """Append the post-op state and advance the cursor (same transaction).

    Call AFTER the tree write (+ ``tree_version`` bump), BEFORE commit. In
    order: seed the lazy baseline when this is the part's first recorded
    mutation, truncate any redo tail (``seq > cursor`` — the standard
    linear-history rule; a fresh edit while undone drops redo), append the
    resulting state at ``cursor + 1``, prune the ring past :data:`HISTORY_MAX`.
    """
    if part.history_cursor is None:
        if baseline is None:  # pragma: no cover - programming error, fail loud
            raise RuntimeError(
                f"history for part {part.id} is unseeded but no baseline "
                "state was captured; call baseline_state() before mutating"
            )
        session.add(db.PartSnapshot(part_id=part.id, seq=0, state=baseline))
        part.history_cursor = 0
    cursor = part.history_cursor
    await session.execute(
        delete(db.PartSnapshot).where(
            db.PartSnapshot.part_id == part.id, db.PartSnapshot.seq > cursor
        )
    )
    state = await _serialize_state(session, part)
    new_cursor = cursor + 1
    session.add(db.PartSnapshot(part_id=part.id, seq=new_cursor, state=state))
    part.history_cursor = new_cursor
    # Bounded ring: keep at most HISTORY_MAX snapshots. Seqs are contiguous
    # and the cursor is at the top right after an append, so the floor is a
    # simple threshold. Log the drop — never silently imply infinite history.
    floor = new_cursor - (HISTORY_MAX - 1)
    pruned = await session.execute(
        delete(db.PartSnapshot)
        .where(db.PartSnapshot.part_id == part.id, db.PartSnapshot.seq < floor)
        .returning(db.PartSnapshot.seq)
    )
    dropped = len(pruned.all())
    if dropped:
        _logger.info(
            "history_ring_pruned",
            part_id=str(part.id),
            dropped=dropped,
            floor_seq=floor,
        )


async def restore_adjacent(
    session: AsyncSession, part: db.Part, direction: Direction
) -> bool:
    """Restore the adjacent snapshot VERBATIM; False = boundary (clean no-op).

    Replace-from-snapshot inside the caller's transaction: the part's
    features + dependency edges are deleted and re-inserted exactly as
    serialized — same ids, same order_index, same params/timestamps — then
    the rollback bar and cursor are repointed. The caller bumps
    ``tree_version`` and commits (undo/redo ARE document edits, design
    §"Version / OCC interaction"); on False the caller returns the current
    tree unchanged (design: boundary ops are "clean no-ops, not errors").
    """
    if part.history_cursor is None:
        return False
    target_seq = part.history_cursor + (1 if direction == "redo" else -1)
    snapshot = await session.get(db.PartSnapshot, (part.id, target_seq))
    if snapshot is None:
        return False
    state = snapshot.state

    # Null the bar first (flushed by autoflush before the deletes) so the
    # Postgres composite FK's SET NULL never races our restore of it.
    part.rollback_feature_id = None
    await session.flush()
    await session.execute(
        delete(db.FeatureDependency).where(db.FeatureDependency.part_id == part.id)
    )
    await session.execute(delete(db.Feature).where(db.Feature.part_id == part.id))
    for row in state["features"]:
        session.add(
            db.Feature(
                id=uuid.UUID(row["id"]),
                part_id=part.id,
                order_index=row["order_index"],
                name=row["name"],
                type=row["type"],
                param_version=row["param_version"],
                params=row["params"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        )
    await session.flush()  # feature rows must exist before their edges (FK)
    for edge in state["dependencies"]:
        session.add(
            db.FeatureDependency(
                part_id=part.id,
                feature_id=uuid.UUID(edge["feature_id"]),
                references_feature_id=uuid.UUID(edge["references_feature_id"]),
            )
        )
    await session.flush()
    bar = state["rollback_feature_id"]
    part.rollback_feature_id = uuid.UUID(bar) if bar is not None else None
    part.history_cursor = target_seq
    return True
