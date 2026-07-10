"""parts table (documents CRUD v1)

Postgres-targeted DDL, written from (and kept in lockstep with)
``documents.db.Part``. Values are frozen literals on purpose — a migration is
a historical snapshot and must not drift if the model constants change later.

Sequencing per docs/design/feature-tree.md §5: parts first (this revision),
feature-tree tables in ``0002_feature_tree`` after the design doc's item.

Revision ID: 0001
Revises: -
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parts",
        # sa.Uuid renders as native UUID on PostgreSQL.
        sa.Column("id", sa.Uuid(), primary_key=True),
        # Gateway-verified user id; no cross-service FK to the gateway's
        # users table (identity lives in another service's schema).
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
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
        # One name per owner, enforced by the constraint (race-free 409).
        # Its backing index's leftmost column also serves the owner-scoped
        # list scan — no separate ix_parts_owner_id (no redundant indexes,
        # same taste as feature-tree.md §1.2).
        sa.UniqueConstraint("owner_id", "name", name="uq_parts_owner_name"),
    )


def downgrade() -> None:
    op.drop_table("parts")
