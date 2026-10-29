"""price books: bagged concrete and post base prices

DECK-FOOTINGS (docs/BACKLOG.md, RESEARCH §23, ``loft_wire.foundation``). A
deck's pier footings are bought as 80 lb bags of concrete
(``concrete_bag_80``) and each post stands in a post base
(``post_base_4x4``, ``post_base_4x6``, ``post_base_6x6``), both priced
``each`` with no stock length and no sheet, as an anchor bolt, a foundation
vent and an access door are. The two CHECKs that read "an Each price with
neither stock nor sheet is a unit, an anchor bolt, a vent or an access door"
(``ck_price_book_entries_each_stock`` and ``ck_price_book_entries_unit_each``,
0029) learn the bag and the post bases. Every existing row satisfies both: no
stored profile is one of them (the wire refused them before).

Downgrade: DELETES every bag and post base price (an older Loft has no way
to hold one; every other price is kept), first moving each book that held one
on a version, as 0029 does, so a draft read before the downgrade cannot save
over the book it no longer matches, and restores 0029's CHECKs.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 0029's Each price with neither stock nor sheet: a unit, an anchor bolt, a
#: vent or an access door.
_UNIT = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door'))"
)
#: The same, with the bag and the post bases (DECK-FOOTINGS).
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door', "
    "'concrete_bag_80') OR substr(profile, 1, 10) = 'post_base_')"
)
#: Casework hardware, priced Each (0028).
_HARDWARE = "(profile = 'hinge' OR substr(profile, 1, 6) = 'slide_')"
_FOOTING = "(profile = 'concrete_bag_80' OR substr(profile, 1, 10) = 'post_base_')"


def _each_checks(item: str) -> None:
    op.create_check_constraint(
        "ck_price_book_entries_each_stock",
        "price_book_entries",
        "(unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {item} "
        f"OR {_HARDWARE})",
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


def downgrade() -> None:
    op.execute(
        "UPDATE price_books SET version = version + 1 WHERE id IN "
        f"(SELECT price_book_id FROM price_book_entries WHERE {_FOOTING})"
    )
    op.execute(f"DELETE FROM price_book_entries WHERE {_FOOTING}")
    _drop_each_checks()
    _each_checks(_UNIT)
