"""price books: a user's lumber prices for the cut list

PRICE-BOOK (docs/BACKLOG.md, RESEARCH §27). Two new tables:

- ``price_books``: one per owner (``uq_price_books_owner``), with the ISO
  4217 ``currency``. ``owner_id`` is the gateway-verified user id with no
  cross-service FK, as every document's.
- ``price_book_entries``: a book's prices in the user's order
  (``uq_price_book_entries_order``), each a material, a profile, a unit
  (``each`` with its ``stock_length_ft``, ``linear_foot`` or
  ``board_foot``) and integer ``price_cents`` (BIGINT, never a float). Two
  CHECKs back the wire's validation: no negative price, and a stock length
  exactly when the unit is ``each``. ``price_book_id`` cascades, so deleting
  a book deletes its entries.

Additive only: no existing table is altered. Downgrade drops both tables, and
with them every saved price.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            name,
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "price_books",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("owner_id", name="uq_price_books_owner"),
    )
    op.create_table(
        "price_book_entries",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "price_book_id",
            sa.Uuid(),
            sa.ForeignKey("price_books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("material", sa.String(32), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("stock_length_ft", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "price_book_id", "order_index", name="uq_price_book_entries_order"
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_price_book_entries_price"),
        sa.CheckConstraint(
            "(unit = 'each') = (stock_length_ft IS NOT NULL)",
            name="ck_price_book_entries_stock_length",
        ),
    )


def downgrade() -> None:
    op.drop_table("price_book_entries")
    op.drop_table("price_books")
