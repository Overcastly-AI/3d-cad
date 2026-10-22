"""price books: per-sheet prices and a save version

SHEATHING and PRICE-BOOK-VERSION (docs/BACKLOG.md, RESEARCH §27), one
migration for one wire change:

- ``price_book_entries.sheet`` (nullable ``VARCHAR(8)``): the sheet ('4x8',
  '4x9', '4x10') a sheet product's ``each`` price is for. The CHECK that an
  ``each`` price has a stock length becomes "an ``each`` price has a stock
  length or a sheet" (``ck_price_book_entries_each_stock``), and a new one
  refuses both at once (``ck_price_book_entries_one_stock``). Every existing
  row satisfies both: its ``sheet`` is NULL.
- ``price_books.version`` (``INTEGER NOT NULL``, server default 1, CHECK
  ``>= 1``): one more on every save, so a ``PUT`` drafted from an older book
  is refused with 412. Every existing book has been saved once at least, so
  it starts at 1.

Downgrade: drops ``version``, DELETES every sheet price (an older Loft has no
way to hold one; the lumber prices are kept), drops ``sheet`` and restores
the old CHECK.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_books",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint("ck_price_books_version", "price_books", "version >= 1")
    op.add_column("price_book_entries", sa.Column("sheet", sa.String(8), nullable=True))
    op.drop_constraint(
        "ck_price_book_entries_stock_length", "price_book_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = (stock_length_ft IS NOT NULL OR sheet IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_price_book_entries_one_stock",
        "price_book_entries",
        "stock_length_ft IS NULL OR sheet IS NULL",
    )


def downgrade() -> None:
    op.execute("DELETE FROM price_book_entries WHERE sheet IS NOT NULL")
    op.drop_constraint(
        "ck_price_book_entries_one_stock", "price_book_entries", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )
    op.drop_column("price_book_entries", "sheet")
    op.create_check_constraint(
        "ck_price_book_entries_stock_length",
        "price_book_entries",
        "(unit = 'each') = (stock_length_ft IS NOT NULL)",
    )
    op.drop_constraint("ck_price_books_version", "price_books", type_="check")
    op.drop_column("price_books", "version")
