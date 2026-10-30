"""price books: roofing by the bundle, roll, stick and foot

ROOFING (docs/BACKLOG.md, RESEARCH §23, ``loft_wire.roofing``). A roof's
architectural shingles (``shingle_architectural``) are priced ``each`` per
bundle and its synthetic underlayment (``underlayment_synthetic``) ``each``
per roll, with no stock length and no sheet, as an anchor bolt or a bag of
concrete is; so the two CHECKs that read "an Each price with neither stock
nor sheet is a unit, an anchor bolt, a vent, an access door, a bag or a post
base" (``ck_price_book_entries_each_stock`` and
``ck_price_book_entries_unit_each``, 0030) learn them. Drip edge
(``drip_edge``) is ``each`` per 10 ft stick (a stock length, which the CHECKs
already allow), starter and ridge cap per linear foot, and the fascia's 1x10
and 1x12 are lumber. Every existing row satisfies both: no stored profile is
one of them (the wire refused them before).

Downgrade: DELETES every roofing price and every price of a 1x10 or 1x12 or
in asphalt shingle, polypropylene or 3105 aluminium (an older Loft cannot
read one; every other price is kept), first moving each book that held one
on a version, as 0030 does, so a draft read before the downgrade cannot save
over the book it no longer matches, and restores 0030's CHECKs.

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 0030's Each price with neither stock nor sheet.
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door', "
    "'concrete_bag_80') OR substr(profile, 1, 10) = 'post_base_')"
)
#: The same, with a bundle of shingles and a roll of underlayment (ROOFING).
_ROOFING_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door', "
    "'concrete_bag_80', 'shingle_architectural', 'underlayment_synthetic') "
    "OR substr(profile, 1, 10) = 'post_base_')"
)
#: Casework hardware, priced Each (0028).
_HARDWARE = "(profile = 'hinge' OR substr(profile, 1, 6) = 'slide_')"
#: What an older Loft cannot hold: a roofing item, the fascia's boards, the
#: roofing materials.
_ROOFING = (
    "(profile IN ('shingle_architectural', 'underlayment_synthetic', "
    "'drip_edge', 'shingle_starter', 'ridge_cap', 'us_1x10', 'us_1x12') OR "
    "material IN ('asphalt_shingle', 'polypropylene', 'aluminium_3105'))"
)


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
    _each_checks(_ROOFING_ITEM)


def downgrade() -> None:
    op.execute(
        "UPDATE price_books SET version = version + 1 WHERE id IN "
        f"(SELECT price_book_id FROM price_book_entries WHERE {_ROOFING})"
    )
    op.execute(f"DELETE FROM price_book_entries WHERE {_ROOFING}")
    _drop_each_checks()
    _each_checks(_EACH_ITEM)
