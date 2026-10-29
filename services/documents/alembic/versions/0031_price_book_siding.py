"""price books: siding per board or per square, and its trim

SIDING-TRIM (docs/BACKLOG.md, RESEARCH §23, ``loft_wire.siding``). A siding
board (``fibre_cement_lap_8_25``, ``cedar_bevel_1_2x8``) is priced ``each``
at its 12 ft stock length or per linear foot, as lumber is, which the
CHECKs already allow; vinyl (``vinyl_d4``) is priced per ``square`` (100 ft²
of wall), a new unit with no stock length or sheet. A new
``ck_price_book_entries_square`` holds the square to vinyl, with neither,
and vinyl to the square. The 5/4x4 trim (``us_5_4x4``) is lumber. Every
existing row satisfies it: no stored unit is ``square`` (the wire refused it
before).

Downgrade: DELETES every siding and 5/4x4 price and every price in fibre
cement or western red cedar (an older Loft cannot read one; every other
price is kept), first moving each book that held one on a version, as 0029
does, so a draft read before the downgrade cannot save over the book it no
longer matches, and drops the CHECK.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: What an older Loft cannot hold: a siding product, the trim, their materials.
_SIDING = (
    "(profile IN ('fibre_cement_lap_8_25', 'vinyl_d4', 'cedar_bevel_1_2x8', "
    "'us_5_4x4') OR material IN ('fibre_cement', 'western_red_cedar'))"
)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_price_book_entries_square",
        "price_book_entries",
        "(unit = 'square') = "
        "(profile = 'vinyl_d4' AND stock_length_ft IS NULL AND sheet IS NULL)",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE price_books SET version = version + 1 WHERE id IN "
        f"(SELECT price_book_id FROM price_book_entries WHERE {_SIDING})"
    )
    op.execute(f"DELETE FROM price_book_entries WHERE {_SIDING}")
    op.drop_constraint(
        "ck_price_book_entries_square", "price_book_entries", type_="check"
    )
