"""features: add suppressed boolean for feature suppress

Adds a NOT NULL ``features.suppressed`` BOOLEAN column, server-default ``false``
so every pre-existing feature backfills to unsuppressed in one statement (the
additive-optional posture of the envelope-level suppress flag —
docs/design/feature-tree.md §4.3a, py-kit ``FeatureEnvelopeBase``). The flag
lives beside ``params`` because it is orthogonal to every feature type (a
rebuild flag, not a modeling parameter); documents reads it back through
``FEATURE_REGISTRY.load(..., suppressed=...)`` on both the CRUD response and the
evaluation-request the geometry service consumes, and a dedicated
``PATCH .../features/{id}/suppress`` toggles it.

The ORM metadata renders the same column on SQLite as ``BOOLEAN`` with a
``false`` server-default (the unit-test / native-boot dialect split documented
in documents/db.py, verified by tests/test_migrations.py), so the
``metadata.create_all`` path used by the native boot and ``just e2e`` picks it up
too.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "features",
        sa.Column(
            "suppressed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("features", "suppressed")
