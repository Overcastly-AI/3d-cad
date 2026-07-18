"""users table (auth v1)

Postgres-targeted DDL, written from (and kept in lockstep with)
``gateway.db.User``. Values are frozen literals on purpose — a migration is a
historical snapshot and must not drift if the model constants change later.

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
        "users",
        # sa.Uuid renders as native UUID on PostgreSQL.
        sa.Column("id", sa.Uuid(), primary_key=True),
        # 320 = RFC 5321 max address length; lowercase-normalized at write.
        sa.Column("email", sa.String(320), nullable=False),
        # argon2 encoded hash (~97 chars today; headroom for parameter bumps).
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )


def downgrade() -> None:
    op.drop_table("users")
