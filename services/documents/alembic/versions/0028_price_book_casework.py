"""price books: casework banding and hardware prices

CASEWORK (docs/BACKLOG.md, RESEARCH §23). A casework item is priced in the
one unit it names (``loft_wire.casework``): edge banding per linear foot
(``edge_banding``), a hinge or a pair of slides Each (``hinge``,
``slide_22``), with no stock length and no sheet. The CHECK that an
``each`` price has a stock length, a sheet or is a unit or an anchor bolt
(``ck_price_book_entries_each_stock``, 0027) becomes "... or is hardware", and a
new one (``ck_price_book_entries_item_stock``) holds every casework item to
no stock length and no sheet. Every existing row satisfies both: no stored
profile is a casework key (the wire refused them before).

Downgrade: DELETES every casework price (an older Loft has no way to hold
one; every other price is kept) and restores 0027's CHECK.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 0027's Each price with neither stock nor sheet: a unit or an anchor bolt.
_UNIT = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile = 'anchor_bolt_1_2')"
)
#: Hardware, priced Each: a hinge or a slide pair (``slide_22``).
_HARDWARE = "(profile = 'hinge' OR substr(profile, 1, 6) = 'slide_')"
#: Every casework item: the hardware and the banding.
_ITEM = f"({_HARDWARE} OR profile = 'edge_banding')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {_UNIT} "
        f"OR {_HARDWARE})",
    )
    op.create_check_constraint(
        "ck_price_book_entries_item_stock",
        "price_book_entries",
        f"NOT {_ITEM} OR (stock_length_ft IS NULL AND sheet IS NULL)",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM price_book_entries WHERE {_ITEM}")
    op.drop_constraint(
        "ck_price_book_entries_item_stock", "price_book_entries", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {_UNIT})",
    )
