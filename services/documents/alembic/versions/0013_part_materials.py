"""parts: add the material assignment (document default + per-body overrides)

Implements docs/design/materials.md §2. One NULLABLE JSON/JSONB column,
``parts.materials``, holding a serialized
:class:`~py_kit.schemas.materials.MaterialAssignment` — ``default_material``
plus a ``bodies`` list of per-body overrides keyed by each body's §MB-0 base
feature id.

NULL is load-bearing, not laziness: it is the honest "nobody has said what this
part is made of", which every pre-existing row backfills to for free and which
makes the evaluated ``mass_g`` come back **null** rather than ``0`` or a
defaulted steel. There is no server default because there is no material value
that would be true of a part nobody has assigned one to (the same reasoning as
the all-NULL last-evaluate record in 0012).

Why JSON rather than a column per field: the assignment is written and read as
ONE object (the PATCH replaces it wholesale, geometry consumes it wholesale) and
its ``bodies`` list is variable-length, so a normalized child table would buy
nothing the single validated pydantic model does not already guarantee —
``params``/``section_params`` set that precedent. A nullable column needs no
table rewrite on Postgres, and the ORM metadata renders the same column on
SQLite, so the ``create_all`` path the native boot and ``just e2e`` use picks it
up too.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Same dialect split as the ORM metadata (documents/db.py): JSONB on Postgres.
_JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("parts", sa.Column("materials", _JSON_VARIANT, nullable=True))


def downgrade() -> None:
    op.drop_column("parts", "materials")
