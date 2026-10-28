"""price books: concrete, rebar and anchor bolt prices

SLAB (docs/BACKLOG.md, RESEARCH §23, ``loft_wire.foundation``). Ready-mix
concrete (``ready_mix``) is priced per ``cubic_yard`` with no stock length or
sheet, a #4 rebar stick (``rebar_4``) ``each`` at its 20 ft stock length
(which the CHECKs already allow), and a 1/2 in anchor bolt
(``anchor_bolt_1_2``) ``each`` with neither, as a window or door unit is.

* ``ck_price_book_entries_each_stock`` and ``ck_price_book_entries_unit_each``
  read "a unit" as "a unit or an anchor bolt": an Each price with neither a
  stock length nor a sheet;
* a new ``ck_price_book_entries_cubic_yard`` holds the cubic yard to
  ready-mix, with neither, and ready-mix to the cubic yard.

Every existing row satisfies all three: no stored profile is a foundation
item and no stored unit is ``cubic_yard`` (the wire refused both before).

Downgrade: DELETES every foundation-item price (an older Loft cannot read
one; lumber, sheet and unit prices are kept) and restores 0025's CHECKs.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 0025's unit key: a window or door, priced Each with neither stock nor sheet.
_UNIT = "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_')"
#: An Each price with neither stock nor sheet: a unit or an anchor bolt.
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile = 'anchor_bolt_1_2')"
)
_FOUNDATION = "profile IN ('ready_mix', 'rebar_4', 'anchor_bolt_1_2')"


def _each_checks(item: str) -> None:
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {item})",
    )
    op.create_check_constraint(
        "ck_price_book_entries_unit_each",
        "price_book_entries",
        f"NOT {item} OR (stock_length_ft IS NULL AND sheet IS NULL)",
    )


def _drop_each_checks() -> None:
    op.drop_constraint(
        "ck_price_book_entries_unit_each", "price_book_entries", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )


def upgrade() -> None:
    _drop_each_checks()
    _each_checks(_EACH_ITEM)
    op.create_check_constraint(
        "ck_price_book_entries_cubic_yard",
        "price_book_entries",
        "(unit = 'cubic_yard') = "
        "(profile = 'ready_mix' AND stock_length_ft IS NULL AND sheet IS NULL)",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM price_book_entries WHERE {_FOUNDATION}")
    op.drop_constraint(
        "ck_price_book_entries_cubic_yard", "price_book_entries", type_="check"
    )
    _drop_each_checks()
    _each_checks(_UNIT)
