"""assembly_snapshots: bounded undo/redo ring + assemblies.history_cursor

Implements docs/design/undo-redo.md UR3 — the assembly fast-follow of 0006's
part ring, same mechanism (``documents.history_core``): each instance/mate/
header mutation appends the assembly's FULL serialized mutable state (header
name/length_unit + ordered instances + ordered mates) in the same
transaction; undo/redo restore an adjacent snapshot VERBATIM, instance/mate
ids byte-preserved, so a mate's instance references inside its params JSONB
stay valid at any distance.

Schema notes (mirroring 0006's, which see):

- ``(assembly_id, seq)`` natural PK — one linear history per assembly,
  ``seq`` monotonic and contiguous within the retained window. Its backing
  index also serves every history scan; no separate index needed.
- ``state`` is JSONB: an assembly graph is small JSON and the ring is
  bounded (``documents.history_core.HISTORY_MAX``), so storage is cheap.
- ``assemblies.history_cursor`` is NULLable — NULL means history was never
  seeded. No FK to ``assembly_snapshots``: the cursor/ring invariant is
  app-maintained (snapshots are already CASCADE-scoped to their assembly).

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assembly_snapshots",
        sa.Column("assembly_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assembly_id"],
            ["assemblies.id"],
            ondelete="CASCADE",
            name="fk_assembly_snapshots_assembly",
        ),
        sa.PrimaryKeyConstraint("assembly_id", "seq", name="pk_assembly_snapshots"),
    )
    op.add_column(
        "assemblies", sa.Column("history_cursor", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assemblies", "history_cursor")
    op.drop_table("assembly_snapshots")
