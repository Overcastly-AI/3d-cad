"""sheets: add parts_list_structure for the parts list's BOM structure

DRAWING-PARTS-LIST-LEVEL. Adds a NOT NULL ``sheets.parts_list_structure``
VARCHAR(16), server-default ``'top_level'``: which of the assembly BOM's three
views (``top_level``, ``indented``, ``parts_only``) the sheet's parts list
shows, backed by the CHECK ``ck_sheets_parts_list_structure``. Every sheet
stored before this migration backfills to ``top_level``, the list it already
showed, so nothing a user has drafted changes.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sheets",
        sa.Column(
            "parts_list_structure",
            sa.String(16),
            nullable=False,
            server_default="top_level",
        ),
    )
    op.create_check_constraint(
        "ck_sheets_parts_list_structure",
        "sheets",
        "parts_list_structure IN ('top_level', 'indented', 'parts_only')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sheets_parts_list_structure", "sheets", type_="check")
    op.drop_column("sheets", "parts_list_structure")
