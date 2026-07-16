"""drawings: drawings + sheets + views + dimensions + annotations tables

Postgres-targeted DDL implementing docs/design/drawings.md §2 — a NEW document
type (a drawing = a layout of sheets, each holding views + dimensions +
annotations that reference a part/assembly), in its OWN tables, reusing the
part/assembly patterns but not their tables (§2.1). Frozen literals on purpose —
a migration is a historical snapshot and must not drift if model constants change
later.

Ordering uniques are PLAIN (not deferrable): the app renumbers collision-free
(monotone shift-down on delete), so they are correct under IMMEDIATE checking —
no deferrable clause is needed and the DDL is expressible on SQLite too (the
unit-test dialect uses the ORM metadata; the split is documented in
documents/db.py and verified by tests/test_migrations.py).

``views.ref_document_id`` is a CROSS-DOCUMENT reference (a part or an assembly),
NOT a DB FK (design §2.2): integrity is app-enforced in documents at write time
(existence, 409-with-dependents), because the reference must survive the
referenced doc's independent lifecycle. Only the parent links are real FKs
(ON DELETE CASCADE): drawing→sheets→views→dimensions and sheets→annotations, so
deleting a drawing removes its whole layout.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # drawings — owner-scoped document header + OCC counter (§2.2).
    op.create_table(
        "drawings",
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
        sa.UniqueConstraint("owner_id", "name", name="uq_drawings_owner_name"),
    )

    # sheets — a drawing's pages (§2.2).
    op.create_table(
        "sheets",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "drawing_id",
            sa.Uuid(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("size", sa.String(16), nullable=False),
        sa.Column("orientation", sa.String(16), nullable=False),
        sa.Column("projection", sa.String(16), nullable=False),
        # The free-text TitleBlock DTO; NULL when unset.
        sa.Column("title_block", postgresql.JSONB(), nullable=True),
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
        # Plain UNIQUE; app renumbers collision-free. Its backing index also
        # serves the ordered sheet scan.
        sa.UniqueConstraint(
            "drawing_id", "order_index", name="uq_sheets_drawing_order"
        ),
    )

    # views — projected views on a sheet, referencing a part / assembly (§2.2).
    op.create_table(
        "views",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sheet_id",
            sa.Uuid(),
            sa.ForeignKey("sheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Cross-document reference — app-enforced, deliberately NOT a DB FK.
        sa.Column("ref_document_id", sa.Uuid(), nullable=False),
        sa.Column("ref_document_kind", sa.String(16), nullable=False),
        # Pin-ready (§2.3): NULL in v1 = track the referenced document's tip.
        sa.Column("ref_pinned_version", sa.BigInteger(), nullable=True),
        sa.Column("projection", sa.String(16), nullable=False),
        sa.Column("scale_num", sa.Integer(), nullable=False),
        sa.Column("scale_den", sa.Integer(), nullable=False),
        sa.Column("pos_x_mm", sa.Float(), nullable=False),
        sa.Column("pos_y_mm", sa.Float(), nullable=False),
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
        sa.UniqueConstraint("sheet_id", "order_index", name="uq_views_sheet_order"),
    )
    # Reverse lookup for the cross-document 409-with-dependents pre-check
    # ("which views reference document X" — §2.2).
    op.create_index("ix_views_ref_document", "views", ["ref_document_id"])

    # dimensions — a view's dimensions, ordered per sheet (§2.2/§3).
    op.create_table(
        "dimensions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sheet_id",
            sa.Uuid(),
            sa.ForeignKey("sheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "view_id",
            sa.Uuid(),
            sa.ForeignKey("views.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        # The full Dimension DTO payload (validated by py-kit before it lands).
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
        sa.UniqueConstraint(
            "sheet_id", "order_index", name="uq_dimensions_sheet_order"
        ),
    )
    # Reverse lookup for the view→dimensions cascade renumber (app-side).
    op.create_index("ix_dimensions_view", "dimensions", ["view_id"])

    # annotations — a sheet's notes, ordered per sheet (§2.2).
    op.create_table(
        "annotations",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sheet_id",
            sa.Uuid(),
            sa.ForeignKey("sheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        # The full Annotation DTO payload (text + position).
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
        sa.UniqueConstraint(
            "sheet_id", "order_index", name="uq_annotations_sheet_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_index("ix_dimensions_view", table_name="dimensions")
    op.drop_table("dimensions")
    op.drop_index("ix_views_ref_document", table_name="views")
    op.drop_table("views")
    op.drop_table("sheets")
    op.drop_table("drawings")
