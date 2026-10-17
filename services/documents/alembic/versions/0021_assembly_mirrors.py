"""assemblies: the component mirror table

ASM-MIRROR-COMPONENT (docs/BACKLOG.md). One new table, ``assembly_mirrors``:
an assembly's component mirrors (SolidWorks' Mirror Components, Fusion's
Mirror on components), each ONE entry holding its definition, not mirrored
instances:

- ``params`` the full validated
  :class:`loft_wire.component_mirrors.ComponentMirror` payload (JSONB): its
  seeds, its plane and which seeds get an opposite hand;
- ``order_index`` a dense stable order (plain UNIQUE, renumbered
  collision-free like ``assembly_patterns``).

``assembly_id`` is a real FK with ON DELETE CASCADE, so deleting an assembly
removes its mirrors. The seeds and the plane face a mirror names live inside
``params`` and are app-enforced at write time, like a pattern's.

Additive only: no existing table is altered, so every existing assembly loads
and evaluates unchanged. Downgrade drops the table, and with it every mirror.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assembly_mirrors",
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
        sa.Column("params", postgresql.JSONB(), nullable=False),
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
            "assembly_id", "order_index", name="uq_assembly_mirrors_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("assembly_mirrors")
