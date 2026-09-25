"""refresh_tokens.replaced_by_id (the reuse interval)

Links each spent refresh token to the token issued in its place, so a client
that lost the rotation response can retry within the reuse interval
(``gateway.auth.security.REFRESH_REUSE_INTERVAL_S``). Kept in lockstep with
``gateway.db.RefreshToken``; frozen literals, as in every revision.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_refresh_tokens_replaced_by",
        "refresh_tokens",
        "refresh_tokens",
        ["replaced_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_refresh_tokens_replaced_by", "refresh_tokens", type_="foreignkey"
    )
    op.drop_column("refresh_tokens", "replaced_by_id")
