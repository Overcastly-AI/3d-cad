"""assemblies: the component pattern table

ASM-A3-PATTERN (docs/BACKLOG.md). One new table, ``assembly_patterns``: an
assembly's component patterns (Fusion Pattern Components, Onshape linear /
circular pattern and Replicate, SolidWorks component patterns), each ONE entry
holding its definition, not copied instances:

- ``type`` (``linear`` / ``circular`` / ``hole``) promoted to a column, as a
  mate's is; ``params`` the full validated
  :data:`loft_wire.component_patterns.ComponentPattern` payload (JSONB);
- ``order_index`` a dense stable order (plain UNIQUE, renumbered
  collision-free like ``mates``);
- ``driven_count`` the count a hole-driven pattern had when it was last
  written, as geometry resolved it (NULL for linear and circular patterns,
  whose count is in ``params``). It feeds the write-time instance bound only;
  the BOM and every evaluation resolve the count again.

``assembly_id`` is a real FK with ON DELETE CASCADE, so deleting an assembly
removes its patterns. The seeds and references a pattern names live inside
``params`` and are app-enforced at write time, like a mate's instance refs.

Additive only: no existing table is altered, so every existing assembly loads
and evaluates unchanged. Downgrade drops the table, and with it every pattern.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assembly_patterns",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assembly_id",
            sa.Uuid(),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("driven_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "assembly_id", "order_index", name="uq_assembly_patterns_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("assembly_patterns")
