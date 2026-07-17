"""length_unit: document display unit on parts + assemblies

Implements docs/design/units.md §U1 — a per-document DISPLAY unit
(``Literal["mm","cm","m","in","ft"]``). The one load-bearing rule (design
§"the one load-bearing rule"): storage and the kernel stay canonical
millimetres FOREVER; ``length_unit`` is presentation metadata about how to
render/parse a document's canonical mm values — it converts NOTHING downstream
and touches no ``*_mm`` value.

Backward compatible: the column lands NOT NULL with ``server_default 'mm'`` so
every pre-existing part/assembly row backfills to millimetres and nothing
observable changes until a user picks another unit. The app-level default is
kept in the ORM too (documents/db.py) so both write paths agree.

Drawings deliberately follow their referenced part in a LATER slice (design
§1, out of v1), so no ``length_unit`` lands on ``drawings`` here.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL with a server_default backfills existing rows to canonical mm in
    # a single statement (no separate UPDATE needed); the default persists so
    # future inserts without the column also land 'mm'.
    op.add_column(
        "parts",
        sa.Column(
            "length_unit",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'mm'"),
        ),
    )
    op.add_column(
        "assemblies",
        sa.Column(
            "length_unit",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'mm'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("assemblies", "length_unit")
    op.drop_column("parts", "length_unit")
