"""parts: named versions, never pruned

LOFT-VERSIONS (docs/BACKLOG.md, docs/FILE-FORMAT.md "Versions"). One new
table, ``part_versions``: a part's named versions, each holding the tree as
``tree.json`` holds it, a per-part ``seq`` (unique with the part), the name,
message and author display name, and the sha256 of the tree's canonical
``.loft`` bytes. It cascades with its part and nothing else ever deletes from
it.

Additive only: no existing row or column is touched, so the upgrade is a
plain CREATE TABLE. Downgrade drops the table, and with it every saved version;
export the parts as ``.loft`` first if the versions must be kept.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "part_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "part_id",
            sa.Uuid(),
            sa.ForeignKey("parts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "message", sa.String(2000), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("author", sa.String(80), nullable=True),
        sa.Column("tree", _JSON, nullable=False),
        sa.Column("tree_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("part_id", "seq", name="uq_part_versions_part_seq"),
    )


def downgrade() -> None:
    op.drop_table("part_versions")
