"""part_snapshots: bounded undo/redo history ring + parts.history_cursor

Implements docs/design/undo-redo.md (UR1) — server-side state snapshots, NOT
client command-inversion. Each tree mutation appends the part's FULL serialized
child state (ordered features + feature_dependencies + rollback_feature_id) in
the same transaction; undo/redo restore an adjacent snapshot VERBATIM, ids
byte-preserved, so ``feature_dependencies`` stays valid at any distance.

Schema notes:

- ``(part_id, seq)`` is the natural PK — one linear history per part, ``seq``
  monotonic and contiguous within the retained window (appends at
  ``cursor + 1``, pruning only from the floor). Its backing index also serves
  every history scan; no separate index needed.
- ``state`` is JSONB: a parametric tree is small JSON and the ring is bounded
  (``documents.history.HISTORY_MAX``), so storage is cheap by design.
- ``parts.history_cursor`` is NULLable — NULL means history was never seeded
  (the baseline is seeded lazily on the first mutation). No FK to
  ``part_snapshots``: the cursor/ring invariant is app-maintained (pruning and
  tail truncation would otherwise need a deferred self-referential dance for
  zero integrity gain — snapshots are already CASCADE-scoped to their part).

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "part_snapshots",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["part_id"],
            ["parts.id"],
            ondelete="CASCADE",
            name="fk_part_snapshots_part",
        ),
        sa.PrimaryKeyConstraint("part_id", "seq", name="pk_part_snapshots"),
    )
    op.add_column("parts", sa.Column("history_cursor", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("parts", "history_cursor")
    op.drop_table("part_snapshots")
