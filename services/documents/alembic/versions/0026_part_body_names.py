"""parts: the user's body renames

BODY-NAMES (docs/BACKLOG.md). ``parts.body_names`` JSONB NULL holds the
part's ``[{base_feature_id, name}]`` renames
(:class:`loft_wire.body_names.BodyName`). NULL is "no body renamed", which
every existing part reads as, so no row is rewritten.

Additive only. Downgrade drops the column, and with it every body rename;
export the parts as ``.loft`` first if those must be kept.

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("parts", sa.Column("body_names", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("parts", "body_names")
