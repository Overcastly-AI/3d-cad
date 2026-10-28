"""price books: foundation vent and crawl-space access door prices

FOUNDATION-TAKEOFF (docs/BACKLOG.md, ``loft_wire.foundation``). A foundation
vent (``foundation_vent``) and a crawl-space access door
(``crawl_access_door``) are priced ``each`` with no stock length and no
sheet, as an anchor bolt is (Chief's materials list carries them Each). The
two CHECKs that read "a unit or an anchor bolt" as an Each price with
neither (``ck_price_book_entries_each_stock`` and
``ck_price_book_entries_unit_each``, 0027 and 0028) read "... or a vent or
an access door". Every existing row satisfies both: no stored profile is
either key (the wire refused them before).

Downgrade: DELETES every vent and access-door price (an older Loft has no
way to hold one; every other price is kept), first moving each book that
held one on a version, so a draft read before the downgrade cannot save
over the book it no longer matches (the SLAB-PRICE-DOWNGRADE note on 0027),
and restores 0028's CHECKs.

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 0028's Each price with neither stock nor sheet: a unit or an anchor bolt.
_UNIT = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile = 'anchor_bolt_1_2')"
)
#: The foundation's Each units, priced with neither (FOUNDATION-TAKEOFF).
_OPENING = "profile IN ('foundation_vent', 'crawl_access_door')"
#: 0029's: a unit, an anchor bolt, a vent or an access door.
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door'))"
)
#: Casework hardware, priced Each (0028).
_HARDWARE = "(profile = 'hinge' OR substr(profile, 1, 6) = 'slide_')"


def _drop() -> None:
    op.drop_constraint(
        "ck_price_book_entries_unit_each", "price_book_entries", type_="check"
    )
    op.drop_constraint(
        "ck_price_book_entries_each_stock", "price_book_entries", type_="check"
    )


def _create(item: str) -> None:
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


def upgrade() -> None:
    _drop()
    _create(_EACH_ITEM)


def downgrade() -> None:
    op.execute(
        "UPDATE price_books SET version = version + 1 WHERE id IN "
        f"(SELECT price_book_id FROM price_book_entries WHERE {_OPENING})"
    )
    op.execute(f"DELETE FROM price_book_entries WHERE {_OPENING}")
    _drop()
    _create(_UNIT)
