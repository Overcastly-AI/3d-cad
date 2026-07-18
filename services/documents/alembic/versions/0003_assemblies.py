"""assemblies: assemblies + instances + mates tables

Postgres-targeted DDL implementing docs/design/assemblies.md §1.2 — a NEW
document type (assembly = a graph of instances + mates), in its OWN tables,
reusing the part model's patterns but not its tables (§1.1). Frozen literals on
purpose — a migration is a historical snapshot and must not drift if model
constants change later.

Postgres-only clause (SQLite tests use the ORM metadata instead — the split
documented in documents/db.py and verified by tests/test_migrations.py):

- ``uq_instances_assembly_order`` is DEFERRABLE INITIALLY DEFERRED so in-place
  renumbering shuffles are legal within one transaction (the same posture as
  ``uq_features_part_order``). ``uq_mates_assembly_order`` is a plain UNIQUE
  (design §1.2 mates DDL); app code renumbers collision-free so it is correct
  under IMMEDIATE checking too.

``instances.ref_document_id`` is a CROSS-DOCUMENT reference (a part or a
sub-assembly), NOT a DB FK (design §1.2): integrity is app-enforced in documents
at write time (existence, acyclicity, 409-with-dependents), because the
reference must survive the referenced doc's independent lifecycle. Only the
``assembly_id`` parent link is a real FK (ON DELETE CASCADE) so deleting an
assembly removes its instances + mates.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # assemblies — owner-scoped document header + OCC counter.
    op.create_table(
        "assemblies",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Gateway-verified user id; no cross-service FK (RESEARCH §3).
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "doc_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
        # One name per owner (race-free 409); backing index serves the
        # owner-scoped list scan — no separate index.
        sa.UniqueConstraint("owner_id", "name", name="uq_assemblies_owner_name"),
    )

    # instances — placed references to parts / sub-assemblies (§1.2).
    op.create_table(
        "instances",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assembly_id",
            sa.Uuid(),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Cross-document reference — app-enforced, deliberately NOT a DB FK.
        sa.Column("ref_document_id", sa.Uuid(), nullable=False),
        sa.Column("ref_document_kind", sa.String(16), nullable=False),
        # Pin-ready (§1.3): NULL in v1 = track the referenced document's tip.
        sa.Column("ref_pinned_version", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "grounded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # The Placement DTO (position + quaternion).
        sa.Column("placement", postgresql.JSONB(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
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
        # Deferrable so renumbering shuffles are legal in-transaction; its
        # backing index also serves the ordered instance scan.
        sa.UniqueConstraint(
            "assembly_id",
            "order_index",
            name="uq_instances_assembly_order",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    # Reverse lookup for the cross-document 409-with-dependents pre-check
    # ("which instances reference document X" — §1.2).
    op.create_index("ix_instances_ref_document", "instances", ["ref_document_id"])

    # mates — the constraint edges of the assembly's mate graph (§1.2/§2.1).
    op.create_table(
        "mates",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assembly_id",
            sa.Uuid(),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        # The full Mate DTO payload (validated by py-kit before it lands here).
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
        # Plain UNIQUE (design §1.2 mates DDL); app renumbers collision-free.
        sa.UniqueConstraint(
            "assembly_id", "order_index", name="uq_mates_assembly_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("mates")
    op.drop_index("ix_instances_ref_document", table_name="instances")
    op.drop_table("instances")
    op.drop_table("assemblies")
