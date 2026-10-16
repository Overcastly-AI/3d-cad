"""views: add clear_title_block for the title-block-aware layout

Adds a NOT NULL ``views.clear_title_block`` BOOLEAN, server-default ``false``.
"Lay out standard views" sets it on the views it creates, and the composer then
moves that auto arrangement off the title block (BIKE2-DRAWING-SCALE). Every view
that exists before this migration backfills to ``false``, so a stored drawing
composes byte-identically: its views and its notes stay where they were.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "views",
        sa.Column(
            "clear_title_block",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("views", "clear_title_block")
