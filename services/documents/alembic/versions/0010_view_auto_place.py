"""views: add auto_place boolean for drag-to-place persistence

Adds a NOT NULL ``views.auto_place`` BOOLEAN column, server-default ``true`` so
every pre-existing view backfills to bounds-aware auto-layout in one statement
(the additive-optional posture the ``views.section_params`` / ``features.suppressed``
columns carry — docs/design/drawing-export.md §4.2, py-kit ``SheetViewPlacement``).
``false`` marks a view whose ``pos_x_mm``/``pos_y_mm`` were hand-placed by a
drag-to-place gesture: the compose/export path threads the flag into
``SheetViewPlacement.auto_place`` so the composer HONORS the persisted position
verbatim instead of deriving an anchor, and the position survives reload.

The ORM metadata renders the same column on SQLite as ``BOOLEAN`` with a ``true``
server-default (the unit-test / native-boot dialect split documented in
documents/db.py, verified by tests/test_migrations.py), so the
``metadata.create_all`` path used by the native boot and ``just e2e`` picks it up
too.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "views",
        sa.Column(
            "auto_place",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("views", "auto_place")
