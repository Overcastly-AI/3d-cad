"""Document-agnostic undo/redo ring mechanics (docs/design/undo-redo.md).

Factored out of the part implementation when UR3 added assembly history: the
cursor/seq/ring math is IDENTICAL by design across document types — a linear
per-document history with a cursor, lazy baseline seeding on the first
mutation, redo-tail truncation on a fresh edit, appends at ``cursor + 1``
(seqs contiguous within the retained window so adjacent snapshots are exactly
``cursor ± 1``), and a bounded ring pruned from the floor at
:data:`HISTORY_MAX` — so it lives here exactly once (CLAUDE.md DRY rule).

What differs per document type is ONLY how the document's mutable child state
serializes and restores; those callables are injected per
:class:`DocumentHistory` instance and live beside their document's routes
(:mod:`documents.history` for parts, :mod:`documents.assembly_history` for
assemblies). The load-bearing rule both share, stated once:

    Undo/redo restore a snapshot **verbatim** — every entity id, order_index
    and timestamp byte-preserved. Entities are NEVER re-created with fresh
    ids: a restore is a replace-from-snapshot inside one transaction, so any
    reference *to* a restored entity (``feature_dependencies`` edges, a
    mate's instance ids inside its params) stays valid across any distance
    (re-minting ids would orphan every downstream reference on redo).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import sqlalchemy as sa
from py_kit import get_logger
from sqlalchemy import SQLColumnExpression, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped

#: Bounded ring size (design §"Model"): at most this many snapshots per
#: document. You can undo within the window, not before it.
HISTORY_MAX = 50

#: Which adjacent snapshot to restore: undo = ``cursor - 1``, redo = ``cursor + 1``.
Direction = Literal["undo", "redo"]


class HistoryDocument(Protocol):
    """The document-row surface the ring mechanics need (Part / Assembly)."""

    id: Mapped[uuid.UUID]
    #: The snapshot ``seq`` whose state IS the current document; NULL = never
    #: seeded (no mutation yet). Maintained here, in the same transaction as
    #: every document write.
    history_cursor: Mapped[int | None]


@dataclass(frozen=True)
class DocumentHistory[DocT: HistoryDocument]:
    """One document type's history store: shared ring math + injected state I/O.

    ``serialize`` returns the document's FULL mutable child state (flushed,
    deterministic ordering, deep-copied JSON payloads); ``apply_state``
    replaces the live child rows with a serialized state VERBATIM (same ids,
    same order, same timestamps) inside the caller's transaction. The ring
    columns are the snapshot table's ``(scope_id, seq)`` natural PK plus its
    JSONB ``state``.
    """

    #: Log/telemetry name for the scope id field ("part" → ``part_id=...``).
    kind: str
    #: The snapshot ORM class (delete targets).
    snapshot_model: type[DeclarativeBase]
    #: Snapshot columns: document scope FK, per-document seq, JSONB state.
    #: Typed as column EXPRESSIONS (not ``InstrumentedAttribute``) so pyright
    #: does not descriptor-resolve them on instance access.
    scope_id: SQLColumnExpression[uuid.UUID]
    seq: SQLColumnExpression[int]
    state: SQLColumnExpression[dict[str, Any]]
    #: Per-document-type state I/O (module docstring).
    serialize: Callable[[AsyncSession, DocT], Awaitable[dict[str, Any]]]
    apply_state: Callable[[AsyncSession, DocT, dict[str, Any]], Awaitable[None]]
    #: ``(document_id, seq, state) -> snapshot row`` constructor.
    make_snapshot: Callable[[uuid.UUID, int, dict[str, Any]], DeclarativeBase]

    async def _bounds(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> tuple[int, int] | None:
        """``(floor, top)`` seq bounds of the document's ring, or None when empty."""
        floor, top = (
            await session.execute(
                select(sa.func.min(self.seq), sa.func.max(self.seq)).where(
                    self.scope_id == document_id
                )
            )
        ).one()
        if floor is None or top is None:
            return None
        return int(floor), int(top)

    async def availability(
        self, session: AsyncSession, document: DocT
    ) -> tuple[bool, bool]:
        """``(can_undo, can_redo)`` — cursor position vs the ring bounds."""
        if document.history_cursor is None:
            return False, False
        bounds = await self._bounds(session, document.id)
        if bounds is None:  # pragma: no cover - invariant: cursor set => rows exist
            return False, False
        floor, top = bounds
        return document.history_cursor > floor, document.history_cursor < top

    async def baseline_state(
        self, session: AsyncSession, document: DocT
    ) -> dict[str, Any] | None:
        """The PRE-op state for lazy baseline seeding, or None once history exists.

        Call at the top of a mutating op (after the OCC guard, before any
        write); pass the result to :meth:`record` after the mutation. Only
        the document's FIRST recorded mutation captures a baseline — that
        snapshot is the state undo can walk back to (design §"Model",
        ``snapshots[0]``).
        """
        if document.history_cursor is not None:
            return None
        return await self.serialize(session, document)

    async def record(
        self, session: AsyncSession, document: DocT, baseline: dict[str, Any] | None
    ) -> None:
        """Append the post-op state and advance the cursor (same transaction).

        Call AFTER the document write (+ version bump), BEFORE commit. In
        order: seed the lazy baseline when this is the document's first
        recorded mutation, truncate any redo tail (``seq > cursor`` — the
        standard linear-history rule; a fresh edit while undone drops redo),
        append the resulting state at ``cursor + 1``, prune the ring past
        :data:`HISTORY_MAX`.
        """
        if document.history_cursor is None:
            if baseline is None:  # pragma: no cover - programming error, fail loud
                raise RuntimeError(
                    f"history for {self.kind} {document.id} is unseeded but no "
                    "baseline state was captured; call baseline_state() before "
                    "mutating"
                )
            session.add(self.make_snapshot(document.id, 0, baseline))
            document.history_cursor = 0
        cursor = document.history_cursor
        await session.execute(
            delete(self.snapshot_model).where(
                self.scope_id == document.id, self.seq > cursor
            )
        )
        state = await self.serialize(session, document)
        new_cursor = cursor + 1
        session.add(self.make_snapshot(document.id, new_cursor, state))
        document.history_cursor = new_cursor
        # Bounded ring: keep at most HISTORY_MAX snapshots. Seqs are
        # contiguous and the cursor is at the top right after an append, so
        # the floor is a simple threshold. Log the drop — never silently
        # imply infinite history.
        floor = new_cursor - (HISTORY_MAX - 1)
        pruned = await session.execute(
            delete(self.snapshot_model)
            .where(self.scope_id == document.id, self.seq < floor)
            .returning(self.seq)
        )
        dropped = len(pruned.all())
        if dropped:
            # Per-kind logger name (documents.history.part / .assembly) so a
            # log query can tell the two rings apart (review 🟢 2026-07-18).
            get_logger(f"documents.history.{self.kind}").info(
                "history_ring_pruned",
                dropped=dropped,
                floor_seq=floor,
                **{f"{self.kind}_id": str(document.id)},
            )

    async def restore_adjacent(
        self, session: AsyncSession, document: DocT, direction: Direction
    ) -> bool:
        """Restore the adjacent snapshot VERBATIM; False = boundary (clean no-op).

        Replace-from-snapshot inside the caller's transaction (via
        ``apply_state``), then repoint the cursor. The caller bumps the
        document's version counter and commits (undo/redo ARE document
        edits, design §"Version / OCC interaction"); on False the caller
        returns the current document unchanged (design: boundary ops are
        "clean no-ops, not errors").
        """
        if document.history_cursor is None:
            return False
        target_seq = document.history_cursor + (1 if direction == "redo" else -1)
        state = (
            await session.execute(
                select(self.state).where(
                    self.scope_id == document.id, self.seq == target_seq
                )
            )
        ).scalar_one_or_none()
        if state is None:
            return False
        await self.apply_state(session, document, state)
        document.history_cursor = target_seq
        return True
