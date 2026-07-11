"""feature tree: features + feature_dependencies, parts tree columns

Postgres-targeted DDL implementing docs/design/feature-tree.md §1.2 exactly,
in the §5 operation order. Frozen literals on purpose — a migration is a
historical snapshot and must not drift if model constants change later.

Postgres-only clauses (SQLite tests use the ORM metadata instead — split
documented in documents/db.py and verified by tests/test_migrations.py):

- ``uq_features_part_order`` is DEFERRABLE INITIALLY DEFERRED so in-place
  renumbering shuffles are legal within one transaction.
- ``fk_feature_deps_target`` is ON DELETE NO ACTION DEFERRABLE INITIALLY
  DEFERRED — checked at COMMIT, not per row: whole-part CASCADE deletes pass
  (by commit time the parts→features CASCADE has removed dependents and
  edges), while a lone delete of a still-referenced feature that slips past
  documents' 409 pre-check still fails as a corruption backstop. RESTRICT
  would make part deletion impossible (review-log 🔴 fix, design §2.3).
- ``fk_parts_rollback_feature`` is composite — the bar can only point at a
  feature of the SAME part — with the Postgres-15+ referencing-column list
  on SET NULL (stack pins Postgres 16). Added as a separate op because the
  parts↔features FK pair is circular (§5).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # §5 op 1 — features, with both unique constraints.
    op.create_table(
        "features",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "part_id",
            sa.Uuid(),
            sa.ForeignKey("parts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("param_version", sa.Integer(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Deferrable so renumbering shuffles are legal; its backing unique
        # index also serves the ordered tree load — no separate index (§1.2).
        sa.UniqueConstraint(
            "part_id",
            "order_index",
            name="uq_features_part_order",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Composite-FK target: every reference TO a feature pins its part
        # (§2.2 rule 1 — DB-enforced, not app-only).
        sa.UniqueConstraint("part_id", "id", name="uq_features_part_id"),
    )

    # §5 op 2 — materialized reference edges + reverse-lookup index.
    op.create_table(
        "feature_dependencies",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), primary_key=True),
        sa.Column("references_feature_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["part_id", "feature_id"],
            ["features.part_id", "features.id"],
            ondelete="CASCADE",
            name="fk_feature_deps_feature",
        ),
        # Backstop only (friendly 409 comes from documents' pre-check, §2.3).
        # Deferred so whole-part CASCADE deletes pass; NOT RESTRICT.
        sa.ForeignKeyConstraint(
            ["part_id", "references_feature_id"],
            ["features.part_id", "features.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
            name="fk_feature_deps_target",
        ),
    )
    op.create_index(
        "ix_feature_deps_target", "feature_dependencies", ["references_feature_id"]
    )

    # §5 op 3 — optimistic-concurrency counter.
    op.add_column(
        "parts",
        sa.Column(
            "tree_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # §5 op 4 — rollback bar + composite same-part FK (circular, so a
    # separate op after features exists).
    op.add_column("parts", sa.Column("rollback_feature_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_parts_rollback_feature",
        "parts",
        "features",
        ["id", "rollback_feature_id"],
        ["part_id", "id"],
        ondelete="SET NULL (rollback_feature_id)",
    )


def downgrade() -> None:
    op.drop_constraint("fk_parts_rollback_feature", "parts", type_="foreignkey")
    op.drop_column("parts", "rollback_feature_id")
    op.drop_column("parts", "tree_version")
    op.drop_index("ix_feature_deps_target", table_name="feature_dependencies")
    op.drop_table("feature_dependencies")
    op.drop_table("features")
