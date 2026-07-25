"""views: add section_params jsonb for section views

Adds a nullable ``views.section_params`` JSONB column holding a section view's
cutting plane + flip (docs/design/drawings-section.md §1) — the validated
:class:`~py_kit.schemas.drawings.SectionViewParams` payload. NULL for every
non-section view, so all existing views are untouched (a purely additive column;
the ORM metadata renders the same column on SQLite as ``JSON`` — the unit-test
dialect split documented in documents/db.py, verified by tests/test_migrations.py).

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "views",
        sa.Column("section_params", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("views", "section_params")
