"""parts: history-name backfill bookkeeping and its journal

DESIGN-INTENT-BACKFILL (docs/BACKLOG.md, RESEARCH §14 "Backfill"). Two
changes, both for the one-off pass that names stored picks made before
history names existed:

- ``parts.ref_names_checked_version BIGINT NULL``: the ``tree_version`` the
  backfill last ran at. NULL means pending, and every existing row is NULL,
  which is exactly right: they are the parts whose picks may lack names.
  Nullable with no default, so the ALTER is catalog-only on Postgres (no table
  rewrite, no long lock on a big ``parts``).
- ``ref_name_backfills``: one row per write (and per revert) with the params
  before and after, geometry's report and the geometry build that computed
  it, so an operator can audit or revert a part. Cascades with its part.

The kernel never runs here. The names themselves are written by the running
services when a part is next opened (or by the operator sweep,
``python -m gateway.ref_backfill``), never by this migration: computing a
name needs a cold rebuild of the part, which does not belong in a schema
upgrade.

Downgrade drops both. Names already written stay in ``features.params`` (they
are valid params at every revision back to the one that added the
``topo_name`` field); revert a part first if they must go too.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "parts",
        sa.Column("ref_names_checked_version", sa.BigInteger(), nullable=True),
    )
    op.create_table(
        "ref_name_backfills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "part_id",
            sa.Uuid(),
            sa.ForeignKey("parts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=True),
        sa.Column("tree_version_before", sa.BigInteger(), nullable=False),
        sa.Column("tree_version_after", sa.BigInteger(), nullable=False),
        sa.Column("params_before", _JSON, nullable=False),
        sa.Column("params_after", _JSON, nullable=False),
        sa.Column("report", _JSON, nullable=True),
        sa.Column("report_sha256", sa.String(64), nullable=True),
        sa.Column("kernel", sa.String(256), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ref_name_backfills_part_id", "ref_name_backfills", ["part_id"])


def downgrade() -> None:
    op.drop_index("ix_ref_name_backfills_part_id", table_name="ref_name_backfills")
    op.drop_table("ref_name_backfills")
    op.drop_column("parts", "ref_names_checked_version")
