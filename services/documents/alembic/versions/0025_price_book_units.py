"""price books: window and door unit prices

OPENING-UNITS (docs/BACKLOG.md, RESEARCH §23). A window or door unit is
priced ``each`` per unit by its key (``window_3040``, ``door_3068``), with no
stock length and no sheet. The CHECK that an ``each`` price has a stock length
or a sheet (``ck_price_book_entries_each_stock``) becomes "... or is a unit",
and a new one (``ck_price_book_entries_unit_each``) holds a unit's price to
``each`` with neither. Every existing row satisfies both: no stored profile
starts ``window_`` or ``door_`` (the wire refused any such profile before).

Downgrade: DELETES every unit price (an older Loft has no way to hold one;
lumber and sheet prices are kept) and restores 0023's CHECK.

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A unit key, in SQL both Postgres and SQLite read the same way (``LIKE``'s
#: ``_`` is a wildcard, so the prefix is compared exactly).
_UNIT = "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {_UNIT})",
    )
    op.create_check_constraint(
        "ck_price_book_entries_unit_each",
        "price_book_entries",
        f"NOT {_UNIT} OR (stock_length_ft IS NULL AND sheet IS NULL)",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM price_book_entries WHERE {_UNIT}")
    op.drop_constraint(
        "ck_price_book_entries_unit_each", "price_book_entries", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = (stock_length_ft IS NOT NULL OR sheet IS NOT NULL)",
    )
