"""parts: the parameter table; features: per-field expressions

PART-PARAMETERS (docs/BACKLOG.md, RESEARCH §20), step 3. Two columns:

* ``parts.parameters`` JSONB NOT NULL DEFAULT '[]': the part's ordered table
  of ``{id, name, expression, unit, comment, value}`` rows
  (:class:`loft_wire.parameters.PartParameter`). Every existing part reads as
  having no parameters. The default is a constant, so on Postgres 11+ the add
  is catalog-only: no table rewrite.
* ``features.expressions`` JSONB NULL: a JSON pointer into ``params`` mapped to
  the expression that drives that number. Nothing writes it yet (step 4);
  NULL means "every field is a plain number", which is every existing feature.

Additive only. Downgrade drops both columns, and with them every parameter
table and feature expression; export the parts as ``.loft`` first if those
must be kept.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "parts",
        sa.Column("parameters", _JSON, nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("features", sa.Column("expressions", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("features", "expressions")
    op.drop_column("parts", "parameters")
