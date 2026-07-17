"""Per-part undo/redo history — the part serializer over the shared ring core.

Implements docs/design/undo-redo.md (UR1). The ring/cursor/seq mechanics —
lazy baseline, redo-tail truncation, bounded pruning, verbatim adjacent-
snapshot restore — live ONCE in :mod:`documents.history_core` (shared with
assembly history since UR3); this module contributes only what is
part-specific: how a part's mutable child state (ordered features +
``feature_dependencies`` edges + the rollback bar) serializes and restores.

The load-bearing decision (stated in full in the core's docstring): restore
is **verbatim** — every feature id, dependency edge, order_index and
timestamp byte-preserved, ids never re-minted, so ``feature_dependencies``
stays valid across any undo/redo distance.

Rollback-bar moves (``PUT /rollback``) are deliberately NOT history events in
v1 — the bar is view-state-like; it still RESTORES with each snapshot (it is
part of the serialized state), so a restore lands on a fully consistent tree.
"""

import copy
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db

# HISTORY_MAX / Direction re-exported: tests + route modules import from here.
from documents.history_core import (
    HISTORY_MAX as HISTORY_MAX,
)
from documents.history_core import (
    Direction as Direction,
)
from documents.history_core import (
    DocumentHistory,
)


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


async def _apply_state(
    session: AsyncSession, part: db.Part, state: dict[str, Any]
) -> None:
    """Replace the part's features + edges with a snapshot's, VERBATIM.

    Same ids, same order_index, same params/timestamps — then the rollback
    bar is repointed. Runs inside the caller's transaction (the core sets
    the cursor and the route bumps ``tree_version`` + commits).
    """
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


def _make_snapshot(
    part_id: uuid.UUID, seq: int, state: dict[str, Any]
) -> db.PartSnapshot:
    return db.PartSnapshot(part_id=part_id, seq=seq, state=state)


#: The part feature tree's history store (docs/design/undo-redo.md UR1).
PART_HISTORY = DocumentHistory[db.Part](
    kind="part",
    snapshot_model=db.PartSnapshot,
    scope_id=db.PartSnapshot.part_id,
    seq=db.PartSnapshot.seq,
    state=db.PartSnapshot.state,
    serialize=_serialize_state,
    apply_state=_apply_state,
    make_snapshot=_make_snapshot,
)
