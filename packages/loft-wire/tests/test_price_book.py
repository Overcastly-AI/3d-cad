"""PRICE-BOOK: the price book's wire rules and the cut list's prices.

The B1 and B2 totals are BACKLOG item 6's acceptance, worked by hand there
(B1 $943.94, $839.54 without the 6x6; B2 $396.07; B1 + 2 x B2 $1,736.08).
Here they are priced from the buildings.md tables as pieces; the geometry
suite prices the same buildings from their measured goldens.
"""

import csv
import io
import uuid
from dataclasses import replace
from typing import Any

import pytest
from loft_wire.cut_list import (
    CutListPiece,
    CutListResponse,
    csv_text,
    cut_list_csv,
    cut_list_response,
    format_cents,
    lumber_for,
    nominal_size_in,
    splice_label,
    stock_piece_price,
    stock_pieces_ft,
    stock_splices,
)
from loft_wire.lumber import LUMBER_PROFILES, MM_PER_INCH
from loft_wire.price_book import (
    MAX_PRICE_BOOK_ENTRIES,
    MAX_PRICE_CENTS,
    PriceBookEntry,
    PriceBookResponse,
    PriceBookUpdate,
)
from loft_wire.sheet_goods import SHEET_SIZES_BY_KEY, sheet_good_for
from pydantic import ValidationError

PT, SPF = "southern_pine_pt", "spf_lumber"


def _each(material: str, profile: str, feet: int, cents: int) -> dict[str, Any]:
    return {
        "material": material,
        "profile": profile,
        "unit": "each",
        "stock_length_ft": feet,
        "price_cents": cents,
    }


def _per(material: str, profile: str, unit: str, cents: int) -> dict[str, Any]:
    return {
        "material": material,
        "profile": profile,
        "unit": unit,
        "price_cents": cents,
    }


#: BACKLOG item 6's sample book, as the dialog would PUT it.
SAMPLE_BOOK: list[dict[str, Any]] = [
    _each(PT, "us_2x10", 16, 2847),
    _each(PT, "us_2x10", 12, 1998),
    _per(PT, "us_6x6", "board_foot", 145),
    _per(PT, "us_5_4x6", "linear_foot", 112),
    _each(PT, "us_2x4", 8, 527),
    _each(PT, "us_2x4", 10, 697),
    _each(PT, "us_2x4", 12, 837),
    _each(SPF, "us_2x4", 8, 398),
    _each(SPF, "us_2x4", 10, 548),
    _each(SPF, "us_2x4", 12, 658),
    _each(SPF, "us_2x6", 8, 648),
    _per(SPF, "us_2x8", "linear_foot", 94),
]

#: buildings.md B1: member, profile, material, qty, length (in).
B1 = [
    ("Ledger", "2x10", PT, 1, 192.0),
    ("Rim", "2x10", PT, 1, 192.0),
    ("Beam", "2x10", PT, 2, 192.0),
    ("Joist", "2x10", PT, 13, 141.0),
    ("Post", "6x6", PT, 3, 10.5),
    ("Deck", "5/4x6", PT, 26, 192.0),
]

#: buildings.md B2 with its door, window and 6/12 roof (rafters at their
#: overall length 82.410).
B2 = [
    ("Stud", "2x4", SPF, 36, 92.625),
    ("Jack", "2x4", SPF, 4, 81.0),
    ("Header", "2x6", SPF, 2, 41.0),
    ("Cripple", "2x4", SPF, 4, 6.125),
    ("Top plate", "2x4", SPF, 4, 144.0),
    ("Bottom plate", "2x4", PT, 2, 53.0),
    ("Top plate", "2x4", SPF, 4, 113.0),
    ("Bottom plate", "2x4", PT, 2, 113.0),
    ("Bottom plate", "2x4", PT, 1, 144.0),
    ("Header", "2x6", SPF, 2, 27.5),
    ("Sill", "2x4", SPF, 1, 24.5),
    ("Cripple", "2x4", SPF, 2, 43.0),
    ("Rafter", "2x6", SPF, 14, 82.410),
    ("Ridge", "2x8", SPF, 1, 144.0),
]


def _pieces(table: list[tuple[Any, ...]], count: int = 1) -> list[CutListPiece]:
    pieces: list[CutListPiece] = []
    for member, profile, material, quantity, length_in, *system in table:
        lumber = lumber_for(profile)
        assert lumber is not None
        pieces.append(
            CutListPiece(
                member=member,
                profile=profile,
                lumber=True,
                material=material,
                classification="member",
                length_mm=length_in * MM_PER_INCH,
                section_mm=(lumber.thickness_mm, lumber.width_mm),
                count=quantity * count,
                system=system[0] if system else "other",
            )
        )
    return pieces


def _book(entries: list[dict[str, Any]]) -> PriceBookResponse:
    update = PriceBookUpdate.model_validate({"entries": entries})
    return PriceBookResponse(currency=update.currency, entries=update.entries)


def _priced(
    pieces: list[CutListPiece], entries: list[dict[str, Any]] = SAMPLE_BOOK
) -> CutListResponse:
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="Priced",
        length_unit="in",
        pieces=pieces,
        price_book=_book(entries),
    )


def _rows(cut_list: CutListResponse) -> list[tuple[Any, ...]]:
    return [
        (
            line.member,
            line.stock_quantity,
            line.unit_price_cents,
            line.price_unit,
            line.extended_price_cents,
        )
        for line in cut_list.lines
    ]


# --- the acceptance totals ------------------------------------------------------


def test_b1_totals_943_94() -> None:
    cut_list = _priced(_pieces(B1))
    assert _rows(cut_list) == [
        ("Ledger", 1, 2847, "each", 2847),
        ("Rim", 1, 2847, "each", 2847),
        ("Beam", 2, 2847, "each", 5694),
        ("Joist", 13, 1998, "each", 25974),
        # 6x6 x 8 ft = 24 BF x $1.45; 5/4x6 x 16 ft x $1.12.
        ("Post", 3, 3480, "board_foot", 10440),
        ("Deck", 26, 1792, "linear_foot", 46592),
    ]
    assert (cut_list.currency, cut_list.total_price_cents) == ("USD", 94394)
    assert cut_list.unpriced_lines == 0


def test_b1_without_the_6x6_price_blanks_the_post() -> None:
    book = [e for e in SAMPLE_BOOK if e["profile"] != "us_6x6"]
    cut_list = _priced(_pieces(B1), book)
    post = next(line for line in cut_list.lines if line.member == "Post")
    assert (post.stock_quantity, post.unit_price_cents, post.price_unit) == (
        3,
        None,
        None,
    )
    assert post.extended_price_cents is None
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (83954, 1)


def test_b2_totals_396_07() -> None:
    cut_list = _priced(_pieces(B2))
    by_member = {
        (line.member, round(line.length_mm / MM_PER_INCH, 3)): line.extended_price_cents
        for line in cut_list.lines
    }
    assert by_member[("Stud", 92.625)] == 14328
    assert by_member[("Rafter", 82.41)] == 9072
    assert by_member[("Ridge", 144.0)] == 1128
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (39607, 0)


def test_an_assembly_of_b1_and_two_b2_totals_1736_08() -> None:
    """One grouped list across the parts, so the total is the sum."""
    cut_list = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="assembly",
        name="Yard",
        length_unit="in",
        pieces=[*_pieces(B1), *_pieces(B2, count=2)],
        price_book=_book(SAMPLE_BOOK),
    )
    assert cut_list.total_price_cents == 173608 == 94394 + 2 * 39607


def test_no_book_leaves_every_line_blank_not_zero() -> None:
    cut_list = _priced(_pieces(B1), [])
    assert {line.unit_price_cents for line in cut_list.lines} == {None}
    assert cut_list.total_price_cents is None
    assert cut_list.unpriced_lines == len(B1)


# --- which price wins, and rounding ---------------------------------------------


def test_each_for_the_stock_length_wins_then_per_foot_then_board_foot() -> None:
    joists = _pieces([("Joist", "2x10", PT, 2, 141.0)])  # 12 ft stock
    every = [
        _per(PT, "us_2x10", "board_foot", 100),
        _per(PT, "us_2x10", "linear_foot", 150),
        _each(PT, "us_2x10", 12, 1998),
    ]
    assert _rows(_priced(joists, every)) == [("Joist", 2, 1998, "each", 3996)]
    # An Each for ANOTHER stock length does not price a 12 ft piece.
    other = [_each(PT, "us_2x10", 16, 2847), *every[:2]]
    assert _rows(_priced(joists, other)) == [("Joist", 2, 1800, "linear_foot", 3600)]
    # 2x10 x 12 ft = 20 BF.
    assert _rows(_priced(joists, every[:1])) == [("Joist", 2, 2000, "board_foot", 4000)]
    # Another material's or profile's price does not apply.
    wrong = [_each(SPF, "us_2x10", 12, 1), _each(PT, "us_2x12", 12, 1)]
    assert _rows(_priced(joists, wrong)) == [("Joist", 2, None, None, None)]


def test_board_feet_are_nominal_and_round_half_up_once_per_piece() -> None:
    sizes = {p.name: nominal_size_in(p) for p in LUMBER_PROFILES}
    assert sizes["5/4x6"] == (1.25, 6) and sizes["2x4"] == (2, 4)
    two_by_four = lumber_for("2x4")
    decking = lumber_for("5/4x6")
    assert two_by_four is not None and decking is not None

    def board_foot(cents: int) -> PriceBookEntry:
        return PriceBookEntry.model_validate(_per(PT, "us_2x4", "board_foot", cents))

    # 2x4 x 8 ft = 5.333 BF: $1.00/BF is 533.33 -> 533 cents a piece.
    assert stock_piece_price(board_foot(100), two_by_four, 8) == 533
    # 5/4x6 x 10 ft = 6.25 BF: 2 cents/BF is 12.5 -> 13 (half up), 1 is 6.
    assert stock_piece_price(board_foot(2), decking, 10) == 13
    assert stock_piece_price(board_foot(1), decking, 10) == 6
    # Rounded per piece, then multiplied: 10 x 533, never round(10 x 533.33).
    studs = _pieces([("Stud", "2x4", PT, 10, 92.625)])
    priced = _priced(studs, [_per(PT, "us_2x4", "board_foot", 100)])
    assert _rows(priced) == [("Stud", 10, 533, "board_foot", 5330)]


def test_a_line_without_stock_or_material_is_unpriced() -> None:
    # Longer than any splice (5 x 24 ft = 120 ft of 2x10): no stock, even
    # per foot, and the line says why.
    long = _pieces([("Top plate", "2x10", PT, 1, 1440.01)])
    no_material = [
        CutListPiece(
            member=None,
            profile="2x10",
            lumber=True,
            material=None,
            classification="matched",
            length_mm=100 * MM_PER_INCH,
            section_mm=(1.5 * MM_PER_INCH, 9.25 * MM_PER_INCH),
        )
    ]
    unclassified = [
        CutListPiece(
            member=None,
            profile=None,
            lumber=False,
            material=PT,
            classification="unclassified",
            length_mm=50.0,
            section_mm=(10.0, 20.0),
        )
    ]
    book = [_per(PT, "us_2x10", "linear_foot", 150)]
    cut_list = _priced([*long, *no_material, *unclassified], book)
    assert [line.unit_price_cents for line in cut_list.lines] == [None, None, None]
    assert [line.stock_quantity for line in cut_list.lines] == [None, 1, None]
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (None, 3)
    assert [line.stock_note for line in cut_list.lines] == [
        "Longer than 5 x 24 ft: no splice of stock covers it",
        None,
        None,
    ]


# --- long members are spliced (CUT-LIST-LONG-STOCK) -----------------------------

#: house-b7.spec.ts's book (the 8 prices the QA round typed), plus an 8 ft
#: SPF 2x10 so the 24 ft rims and ridge splice as 16 + 8.
B7_BOOK: list[dict[str, Any]] = [
    _each(SPF, "us_2x10", 16, 2297),
    _each(PT, "us_2x6", 16, 1698),
    {
        "material": "plywood",
        "profile": "plywood_23_32",
        "unit": "each",
        "sheet": "4x8",
        "price_cents": 4250,
    },
    _each(SPF, "us_2x6", 8, 648),
    _each(PT, "us_2x6", 12, 1248),
    {
        "material": "osb",
        "profile": "osb_7_16",
        "unit": "each",
        "sheet": "4x9",
        "price_cents": 2498,
    },
    _each(SPF, "us_2x6", 16, 1398),
    _each(SPF, "us_2x8", 12, 1347),
    _each(SPF, "us_2x10", 8, 1147),
]

#: B7's lumber, house-b7.spec.ts's independently calculated table in tree
#: order (member, profile, material, qty, length in, system).
B7 = [
    ("Joist", "2x10", SPF, 19, 189.0, "floor"),
    ("Rim", "2x10", SPF, 2, 288.0, "floor"),
    ("Sill", "2x6", PT, 2, 288.0, "floor"),
    ("Sill", "2x6", PT, 2, 181.0, "floor"),
    ("Stud", "2x6", SPF, 60, 92.625, "walls"),
    ("Jack", "2x6", SPF, 12, 81.0, "walls"),
    ("Header", "2x6", SPF, 6, 39.5, "walls"),
    ("Header", "2x6", SPF, 2, 41.0, "walls"),
    ("Cripple", "2x6", SPF, 14, 6.125, "walls"),
    ("Sill", "2x6", SPF, 3, 36.5, "walls"),
    ("Cripple", "2x6", SPF, 7, 31.0, "walls"),
    ("Top plate", "2x6", SPF, 4, 288.0, "walls"),
    ("Bottom plate", "2x6", PT, 2, 125.0, "walls"),
    ("Header", "2x6", SPF, 4, 27.5, "walls"),
    ("Sill", "2x6", SPF, 2, 24.5, "walls"),
    ("Cripple", "2x6", SPF, 4, 43.0, "walls"),
    ("Top plate", "2x6", SPF, 4, 181.0, "walls"),
    ("Bottom plate", "2x6", PT, 2, 181.0, "walls"),
    ("Bottom plate", "2x6", PT, 1, 288.0, "walls"),
    ("Rafter", "2x8", SPF, 26, 123.5341, "roof"),
    ("Ridge", "2x10", SPF, 1, 288.0, "roof"),
]

#: B7's lines as the list orders them (CUT-LIST-PANEL): by system, then
#: member as it first appears, then length, shortest first. house-b7.spec.ts
#: reads the same rows.
B7_ORDER = [
    ("floor", "Joist", 19, 189.0),
    ("floor", "Rim", 2, 288.0),
    ("floor", "Sill", 2, 181.0),
    ("floor", "Sill", 2, 288.0),
    ("walls", "Stud", 60, 92.625),
    ("walls", "Jack", 12, 81.0),
    ("walls", "Header", 4, 27.5),
    ("walls", "Header", 6, 39.5),
    ("walls", "Header", 2, 41.0),
    ("walls", "Cripple", 14, 6.125),
    ("walls", "Cripple", 7, 31.0),
    ("walls", "Cripple", 4, 43.0),
    ("walls", "Sill", 2, 24.5),
    ("walls", "Sill", 3, 36.5),
    ("walls", "Top plate", 4, 181.0),
    ("walls", "Top plate", 4, 288.0),
    ("walls", "Bottom plate", 2, 125.0),
    ("walls", "Bottom plate", 2, 181.0),
    ("walls", "Bottom plate", 1, 288.0),
    ("roof", "Rafter", 26, 123.5341),
    ("roof", "Ridge", 1, 288.0),
    # A sheet line's length is its sheet's (:func:`_sheets`).
    ("sheathing", "Subfloor", 14, 96.0),
    ("sheathing", "Sheathing", 24, 108.0),
]

#: B7's modelled panels (length, width in; count), as the b7-outline golden
#: lays them out: the subfloor's 4x8s and 4 ft squares, and the walls' 48 in
#: panels, two 37 in fillers and four 5.9375 in corner rips, 97.125 tall.
B7_SUBFLOOR = [((96.0, 48.0), 10), ((48.0, 48.0), 4)]
B7_SHEATHING = [((97.125, 48.0), 18), ((97.125, 37.0), 2), ((97.125, 5.9375), 4)]


def _sheets(
    member: str, key: str, area_in2: float, sizes: list[tuple[tuple[float, float], int]]
) -> list[CutListPiece]:
    """B7's subfloor or sheathing panels, *sizes*, their faces scaled to the
    table's net area (openings cut out; the count does not credit them)."""
    good = sheet_good_for(key)
    assert good is not None
    sheet = SHEET_SIZES_BY_KEY["4x8" if key == "plywood_23_32" else "4x9"]
    gross = sum(a * b * n for (a, b), n in sizes)
    return [
        CutListPiece(
            member=member,
            profile=good.name,
            lumber=False,
            material=good.material,
            classification="member",
            length_mm=a * MM_PER_INCH,
            section_mm=(good.thickness_in * MM_PER_INCH, b * MM_PER_INCH),
            count=n,
            sheet=sheet,
            area_mm2=a * b * area_in2 / gross * MM_PER_INCH**2,
        )
        for (a, b), n in sizes
    ]


def _b7_pieces() -> list[CutListPiece]:
    pieces = _pieces(B7)
    pieces[4:4] = _sheets("Subfloor", "plywood_23_32", 55296, B7_SUBFLOOR)
    pieces[16:16] = _sheets("Sheathing", "osb_7_16", 83175.71875, B7_SHEATHING)
    return pieces


def test_stock_for_a_long_member_is_the_fewest_joints_then_least_waste() -> None:
    ft = 12 * MM_PER_INCH
    # Dimension lumber runs to 24 ft (NO-SPLICE-SPANS): one stock length to
    # 24 ft, no splice.
    assert stock_pieces_ft(24 * ft) == (24,)
    assert stock_splices(24 * ft) == ()
    # 26 ft: three zero-waste two-piece splices, the most even first.
    assert stock_splices(26 * ft) == ((14, 12), (16, 10), (18, 8))
    assert stock_pieces_ft(36 * ft) == (18, 18)
    # 49 ft: 2 x 24 is short, so 3 pieces 1 ft over, the most even 18 + 16
    # + 16 (2 x 24 + 8 is 7 ft over).
    assert stock_pieces_ft(49 * ft) == (18, 16, 16)
    assert stock_pieces_ft(120 * ft) == (24, 24, 24, 24, 24)
    assert stock_pieces_ft(120 * ft + 0.01) is None
    # A one-piece member (a joist) is never spliced.
    assert stock_pieces_ft(26 * ft, splice=False) is None
    assert stock_pieces_ft(23.75 * ft, splice=False) == (24,)
    assert splice_label((12, 12)) == "2 x 12 ft"
    assert splice_label((20, 20, 8)) == "2 x 20 ft + 8 ft"
    assert splice_label((14, 12)) == "14 ft + 12 ft"


def test_lengths_to_20_ft_splice_as_before() -> None:
    """The 8 to 20 ft list (boards, decking, timbers) keeps
    SPLICE-FEWEST-PIECES' choices."""
    ft = 12 * MM_PER_INCH
    lengths = (8, 10, 12, 14, 16, 20)
    assert stock_splices(24 * ft, lengths) == ((12, 12), (14, 10), (16, 8))
    assert stock_pieces_ft(36 * ft, lengths) == (20, 16)
    # 37 ft: 20 + 20 wastes 3 ft and 14 + 12 + 12 wastes 1, but has one more
    # joint, so 2 x 20 (SPLICE-FEWEST-PIECES, IRC R602.3.2).
    assert stock_splices(37 * ft, lengths) == ((20, 20),)
    assert stock_pieces_ft(41 * ft, lengths) == (14, 14, 14)  # 3 pieces, 1 ft over
    assert stock_pieces_ft(100 * ft, lengths) == (20, 20, 20, 20, 20)
    assert stock_pieces_ft(100 * ft + 0.01, lengths) is None
    assert stock_pieces_ft(100 * ft + 0.01, lengths) is None


def test_a_long_line_lists_its_splice_and_buys_one_set_per_member() -> None:
    (line,) = _priced(_pieces([("Top plate", "2x6", SPF, 4, 312.0)]), []).lines
    assert (line.stock_length_ft, line.stock_pieces_ft, line.waste_mm) == (
        None,
        [14, 12],
        0,
    )
    assert line.stock_quantity == 4 and line.unit_price_cents is None
    (short,) = _priced(_pieces([("Stud", "2x6", SPF, 3, 92.625)]), []).lines
    assert (short.stock_length_ft, short.stock_pieces_ft) == (8, [8])


def test_a_splice_is_priced_on_its_pieces_each_per_foot_or_board_foot() -> None:
    plate = _pieces([("Top plate", "2x6", SPF, 4, 288.0)])
    # Each: the cheapest tied splice the book prices whole (16 + 8 here).
    each = [_each(SPF, "us_2x6", 16, 1398), _each(SPF, "us_2x6", 8, 648)]
    (line,) = _priced(plate, each).lines
    assert (line.stock_pieces_ft, line.unit_price_cents, line.price_unit) == (
        [16, 8],
        2046,
        "each",
    )
    # Bought as a splice, it has no single stock length (it listed 24 ft).
    assert line.stock_length_ft is None
    assert (line.stock_quantity, line.extended_price_cents) == (4, 8184)
    # With 12 ft priced too, 2 x 12 at 12.00 beats 16 + 8 at 20.46.
    (line,) = _priced(plate, [*each, _each(SPF, "us_2x6", 12, 600)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([12, 12], 1200)
    # With no 24 ft Each, per foot prices the one 24 ft stock length the
    # plate is listed as (since NO-SPLICE-SPANS; it was 2 x 12 ft, the same
    # 24 ft bought).
    (line,) = _priced(plate, [each[0], _per(SPF, "us_2x6", "linear_foot", 95)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents, line.price_unit) == (
        [24],
        2280,
        "linear_foot",
    )
    assert line.extended_price_cents == 9120
    # Board feet, rounded once per piece: a 26 ft 2x10 is 14 + 12 ft, 23 1/3
    # and 20 BF, at $1.45: 33.8333 -> 33.83, plus 29.00.
    ridge = _pieces([("Ridge", "2x10", SPF, 1, 312.0)])
    (line,) = _priced(ridge, [_per(SPF, "us_2x10", "board_foot", 145)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([14, 12], 3383 + 2900)
    assert line.price_unit == "board_foot"
    # Only 16 ft priced Each: no tied splice is priced whole, so the yard
    # sells 2 x 16 (8 ft more waste), its offcut recomputed.
    (line,) = _priced(plate, each[:1]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([16, 16], 2796)
    assert line.waste_mm == pytest.approx(8 * 12 * MM_PER_INCH)
    # Nothing priced at all: one 24 ft stock length, blank.
    (line,) = _priced(plate, []).lines
    assert line.unit_price_cents is None and line.stock_pieces_ft == [24]
    # A 24 ft Each prices it whole, before any splice.
    (line,) = _priced(plate, [*each, _each(SPF, "us_2x6", 24, 2698)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([24], 2698)


def test_a_28_ft_member_buys_the_first_splice_the_book_prices() -> None:
    """B7 stretched to 28 ft (CUT-LIST-SPLICE-TIES): the two-piece 28 ft
    ties, 2 x 14, 16 + 12, 18 + 10 and 20 + 8, have no SPF price, and nor
    has any two-piece 30 ft cover, so the yard quotes 2 x 16 (32 ft, 4 ft =
    1219.2 mm over; two pieces before 16 + 8 + 8's three). The PT sill's
    16 + 12 tie is priced and kept."""
    pieces = _pieces(
        [
            ("Rim", "2x10", SPF, 2, 336.0),
            ("Sill", "2x6", PT, 2, 336.0),
            ("Top plate", "2x6", SPF, 4, 336.0),
            ("Ridge", "2x10", SPF, 1, 336.0),
        ]
    )
    cut_list = _priced(pieces, B7_BOOK)
    assert cut_list.unpriced_lines == 0
    assert [
        (
            line.member,
            splice_label(line.stock_pieces_ft or []),
            line.unit_price_cents,
            line.extended_price_cents,
            round(line.waste_mm or 0, 6),
        )
        for line in cut_list.lines
    ] == [
        ("Rim", "2 x 16 ft", 2 * 2297, 2 * 4594, 1219.2),
        ("Sill", "16 ft + 12 ft", 1698 + 1248, 2 * 2946, 0),
        ("Top plate", "2 x 16 ft", 2 * 1398, 4 * 2796, 1219.2),
        ("Ridge", "2 x 16 ft", 2 * 2297, 4594, 1219.2),
    ]
    # Unpriced, the first choice stands.
    assert [line.stock_pieces_ft for line in _priced(pieces, []).lines] == [
        [14, 14],
        [14, 14],
        [14, 14],
        [14, 14],
    ]


def test_a_28_ft_member_buys_two_16s_not_three_pieces_when_10_ft_is_priced() -> None:
    """SPLICE-FEWEST-PIECES: with an 8, 10 and 16 ft book, 10 + 10 + 8 covers
    28 ft with no waste, but its three pieces are one more joint to land over
    a stud, so the yard sells 2 x 16 (4 ft over, kept for blocking)."""
    book = [
        _each(SPF, "us_2x6", 8, 648),
        _each(SPF, "us_2x6", 10, 798),
        _each(SPF, "us_2x6", 16, 1398),
    ]
    (line,) = _priced(_pieces([("Top plate", "2x6", SPF, 4, 336.0)]), book).lines
    assert (line.stock_pieces_ft, line.unit_price_cents, line.price_unit) == (
        [16, 16],
        2 * 1398,
        "each",
    )
    assert line.waste_mm == pytest.approx(4 * 12 * MM_PER_INCH)
    assert line.extended_price_cents == 4 * 2 * 1398


def test_a_37_ft_member_buys_two_20s_when_20_ft_is_priced() -> None:
    """37 ft: 2 x 20 (3 ft over) before 14 + 12 + 12 (1 ft over), though
    the book prices both and the three pieces cost less."""
    book = [
        _each(SPF, "us_2x10", 20, 2998),
        _each(SPF, "us_2x10", 14, 1947),
        _each(SPF, "us_2x10", 12, 1747),
    ]
    (line,) = _priced(_pieces([("Rim", "2x10", SPF, 2, 444.0)]), book).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([20, 20], 2 * 2998)
    assert line.waste_mm == pytest.approx(3 * 12 * MM_PER_INCH)


def test_b7_is_priced_to_the_last_line_2968_79() -> None:
    """B7's 5 lines over 20 ft (the 288 in rims, sills, top and bottom plates
    and the ridge) were blank; spliced, they price.

    By hand, the QA round's $2,608.83 (18 lines) plus the five splices:
    rims 2 x (22.97 + 11.47) = 68.88, sills 2 x (2 x 12.48) = 49.92, top
    plates 4 x (13.98 + 6.48) = 81.84, bottom plate 1 x 24.96 = 24.96 and
    ridge 1 x 34.44 = 34.44: 260.04 more, $2,868.87. SHEET-COUNT-PIECES
    then buys the OSB the walls are cut from, 21 sheets, not 17 by area: 18
    at 48 in, one per 37 in filler (its 11 in rip holds one 5.9375 corner
    rip) and one for the other two rips, 4 x 24.98 = 99.92 more, $2,968.79.
    SHEET-KERF loses 1/8 in at each cut, but a square's 47.875 in end fills
    the next 48 in square, 1/8 in short in APA's panel gap (SHEET-KERF-GAP),
    so the subfloor's 14 panels stay 12 sheets. The 24 ft rims, plates and ridge are
    24 ft stock now, but the book prices no 24 ft, so they splice as before.
    """
    cut_list = _priced(_b7_pieces(), B7_BOOK)
    assert len(cut_list.lines) == 23 and cut_list.unpriced_lines == 0
    long = [
        (
            line.member,
            splice_label(line.stock_pieces_ft or []),
            line.extended_price_cents,
        )
        for line in cut_list.lines
        if line.length_mm > 20 * 12 * MM_PER_INCH
    ]
    assert long == [
        ("Rim", "16 ft + 8 ft", 6888),
        ("Sill", "2 x 12 ft", 4992),
        ("Top plate", "16 ft + 8 ft", 8184),
        ("Bottom plate", "2 x 12 ft", 2496),
        ("Ridge", "16 ft + 8 ft", 3444),
    ]
    assert [
        (
            line.system,
            line.member,
            line.quantity,
            round(line.length_mm / MM_PER_INCH, 4),
        )
        for line in cut_list.lines
    ] == B7_ORDER
    sheets = [(line.member, line.stock_quantity) for line in cut_list.lines[-2:]]
    assert sheets == [("Subfloor", 12), ("Sheathing", 21)]
    assert cut_list.total_price_cents == 286887 + 4 * 2498 == 296879
    short = sum(
        line.extended_price_cents or 0
        for line in cut_list.lines
        if line.length_mm <= 20 * 12 * MM_PER_INCH
    )
    assert short == 260883 + 4 * 2498  # the QA round's, and 4 more sheets
    rows = cut_list_csv(cut_list).split("\r\n")
    assert rows[2].startswith("2,Floor,Rim,")
    assert rows[2].endswith(",16 ft + 8 ft,0,2,34.44,Each,68.88")
    assert rows[4].startswith("4,Floor,Sill,")
    assert rows[4].endswith(",2 x 12 ft,0,2,24.96,Each,49.92")
    assert rows[-2] == ",Total,,,,,,,,,,,,,,2968.79"


# --- spans are one piece (NO-SPLICE-SPANS) ---------------------------------------


def _one_piece(
    member: str, profile: str, material: str, quantity: int, length_in: float
) -> list[CutListPiece]:
    """*member* as a plugin's spanning member (``one_piece``)."""
    return [
        replace(p, one_piece=True)
        for p in _pieces([(member, profile, material, quantity, length_in)])
    ]


def test_a_285_in_joist_is_one_24_ft_piece_never_two_12s() -> None:
    """FLOOR-JOIST-SPAN's left-and-right span: 19 joists 285 in long. They
    were 2 x 12 ft spliced; a joist spans wall to wall, so it is one 24 ft
    stick, and a book with no 24 ft leaves it blank rather than splice."""
    joists = _one_piece("Joist", "2x10", SPF, 19, 285.0)
    (line,) = _priced(joists, B7_BOOK).lines
    assert (line.one_piece, line.stock_length_ft, line.stock_pieces_ft) == (
        True,
        24,
        [24],
    )
    assert line.waste_mm == pytest.approx(3 * MM_PER_INCH)
    assert (line.unit_price_cents, line.extended_price_cents) == (None, None)
    # Priced at 24 ft Each, or per foot on 24 ft; never on a splice of the
    # 12s and 16s the book prices.
    book = [*B7_BOOK, _each(SPF, "us_2x10", 12, 1747)]
    (line,) = _priced(joists, book).lines
    assert line.unit_price_cents is None and line.stock_pieces_ft == [24]
    (line,) = _priced(joists, [*book, _each(SPF, "us_2x10", 24, 4197)]).lines
    assert (line.unit_price_cents, line.extended_price_cents) == (4197, 19 * 4197)
    (line,) = _priced(joists, [_per(SPF, "us_2x10", "linear_foot", 175)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([24], 24 * 175)


def test_a_joist_past_24_ft_has_no_stock_and_says_why() -> None:
    joists = _one_piece("Joist", "2x10", SPF, 2, 300.0)
    rim = _pieces([("Rim", "2x10", SPF, 2, 300.0)])
    cut_list = _priced([*joists, *rim], [_per(SPF, "us_2x10", "linear_foot", 175)])
    joist, rim_line = cut_list.lines
    assert (joist.stock_pieces_ft, joist.stock_quantity, joist.waste_mm) == (
        None,
        None,
        None,
    )
    assert (
        joist.stock_note == "One piece, longer than 24 ft stock: a joist is not spliced"
    )
    assert joist.unit_price_cents is None and cut_list.unpriced_lines == 1
    # The rim beside it bears on the sill along its length, so it splices.
    assert rim_line.stock_pieces_ft == [14, 12] and rim_line.stock_note is None
    row = cut_list_csv(cut_list).split("\r\n")[1]
    assert ',"One piece, longer than 24 ft stock: a joist is not spliced",' in row
    # A 6x6 post is a timber, sold to 20 ft: past it, no stock.
    (post,) = _priced(_one_piece("Post", "6x6", PT, 1, 241.0), []).lines
    assert (
        post.stock_note == "One piece, longer than 20 ft stock: a post is not spliced"
    )


def test_a_shorter_stock_the_book_lacks_falls_to_the_next_it_prices() -> None:
    """With 18 ft in the list, a 17 ft rafter is 18 ft stock; a book with no
    18 ft buys 20 ft, as it did before the list had 18 ft."""
    rafters = _one_piece("Rafter", "2x8", SPF, 4, 204.0)
    (line,) = _priced(rafters, []).lines
    assert line.stock_pieces_ft == [18]
    (line,) = _priced(rafters, [_each(SPF, "us_2x8", 20, 2297)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([20], 2297)
    assert line.waste_mm == pytest.approx(36 * MM_PER_INCH)
    # The stock shown is the stock bought: 20 ft, not the 18 ft first choice.
    assert line.stock_length_ft == 20
    # A length every yard stocks stands alone: a 12 ft joist with only 16 ft
    # priced stays blank, so its blank asks for the 12 ft price.
    joists = _one_piece("Joist", "2x10", PT, 2, 141.0)
    (line,) = _priced(joists, [_each(PT, "us_2x10", 16, 2847)]).lines
    assert line.unit_price_cents is None and line.stock_pieces_ft == [12]
    # A 21 ft plate whose book prices only 12 ft splices 2 x 12; under 20 ft
    # nothing splices, so a 17 ft plate with only 12 ft priced is blank.
    plate = _pieces([("Top plate", "2x6", SPF, 2, 252.0)])
    (line,) = _priced(plate, [_each(SPF, "us_2x6", 12, 1047)]).lines
    assert (line.stock_pieces_ft, line.unit_price_cents) == ([12, 12], 2 * 1047)
    short = _pieces([("Top plate", "2x6", SPF, 2, 204.0)])
    (line,) = _priced(short, [_each(SPF, "us_2x6", 12, 1047)]).lines
    assert line.unit_price_cents is None and line.stock_pieces_ft == [18]


def _cents(cell: str) -> int:
    whole, part = cell.split(".")
    return int(whole) * 100 + int(part)


@pytest.mark.parametrize("building", ["b1", "b2", "b7"])
def test_every_csv_row_multiplies_out(building: str) -> None:
    """Stock qty x Unit price = Extended on every priced row (lumber, splices
    and sheets), so a row copied onto a purchase order is what it costs."""
    if building == "b7":
        cut_list = _priced(_b7_pieces(), B7_BOOK)
    else:
        cut_list = _priced(_pieces(B1 if building == "b1" else B2))
    rows = list(csv.reader(io.StringIO(cut_list_csv(cut_list))))
    header = rows[0]
    qty, unit, extended = (
        header.index("Stock qty"),
        header.index("Unit price (USD)"),
        header.index("Extended (USD)"),
    )
    priced = [row for row in rows[1:-1] if row[extended]]
    assert len(priced) == len(cut_list.lines)
    for row in priced:
        assert int(row[qty]) * _cents(row[unit]) == _cents(row[extended]), row
    for line in cut_list.lines:
        assert line.unit_price_cents is not None and line.stock_quantity is not None
        assert line.extended_price_cents == line.unit_price_cents * line.stock_quantity


# --- the wire rules -------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"price_cents": -1}, "negative"),
        ({"price_cents": MAX_PRICE_CENTS + 1}, "too high"),
        ({"price_cents": 398.0}, "a float"),
        ({"price_cents": "398"}, "a string"),
        ({"price_cents": True}, "a bool"),
        ({"stock_length_ft": None}, "each without a stock length"),
        ({"stock_length_ft": 19}, "not a stock length"),
        ({"stock_length_ft": 26}, "longer than any stock"),
        ({"unit": "per_sheet"}, "unknown unit"),
        ({"profile": "2x4"}, "a name, not a key"),
        ({"material": "oak"}, "unknown material"),
        ({"note": "x"}, "an unknown field"),
    ],
)
def test_an_entry_is_refused(change: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError):
        PriceBookEntry.model_validate({**_each(SPF, "us_2x4", 8, 398), **change})


def test_a_per_foot_price_has_no_stock_length() -> None:
    with pytest.raises(ValidationError, match="Only an 'each' price"):
        PriceBookEntry.model_validate(
            {**_per(SPF, "us_2x8", "linear_foot", 94), "stock_length_ft": 8}
        )
    assert PriceBookEntry.model_validate(_each(SPF, "us_2x4", 8, 0)).price_cents == 0


def test_a_book_is_bounded_and_has_one_price_per_key() -> None:
    PriceBookUpdate.model_validate({"entries": SAMPLE_BOOK})
    with pytest.raises(ValidationError, match="repeats an earlier entry"):
        PriceBookUpdate.model_validate(
            {"entries": [*SAMPLE_BOOK, _each(PT, "us_2x10", 16, 1)]}
        )
    # Each per stock length and a per-foot price of one profile coexist.
    PriceBookUpdate.model_validate(
        {
            "entries": [
                _each(PT, "us_2x10", 8, 1),
                _each(PT, "us_2x10", 10, 1),
                _per(PT, "us_2x10", "linear_foot", 1),
                _per(PT, "us_2x10", "board_foot", 1),
            ]
        }
    )
    woods = (PT, SPF, "dfl_lumber", "lvl", "glulam_dfl")
    many = [
        _per(material, profile.key, unit, 1)
        for material in woods
        for profile in LUMBER_PROFILES
        for unit in ("linear_foot", "board_foot")
    ]
    many += [
        _each(material, profile.key, feet, 1)
        for material in woods
        for profile in LUMBER_PROFILES
        for feet in (8, 10, 12, 14, 16, 20)
    ]
    assert len(many) > MAX_PRICE_BOOK_ENTRIES
    PriceBookUpdate.model_validate({"entries": many[:MAX_PRICE_BOOK_ENTRIES]})
    with pytest.raises(ValidationError, match="at most 500"):
        PriceBookUpdate.model_validate({"entries": many[: MAX_PRICE_BOOK_ENTRIES + 1]})
    with pytest.raises(ValidationError):
        PriceBookUpdate.model_validate({"currency": "EUR", "entries": []})


# --- CSV ------------------------------------------------------------------------


def test_the_csv_carries_the_prices_and_a_total_row() -> None:
    book = [e for e in SAMPLE_BOOK if e["profile"] != "us_6x6"]
    rows = cut_list_csv(_priced(_pieces(B1), book)).split("\r\n")
    assert rows[0].endswith(
        "Waste each (in),Stock qty,Unit price (USD),Price unit,Extended (USD)"
    )
    assert rows[4].endswith(",,12 ft,3,13,19.98,Each,259.74")
    assert rows[5].endswith(",,8 ft,85.5,3,,,")  # the post: blank, not 0
    assert rows[6].endswith(",,16 ft,0,26,17.92,Per ft,465.92")
    assert rows[7] == ',"Total of priced lines, 1 unpriced",,,,,,,,,,,,,,839.54'
    full = cut_list_csv(_priced(_pieces(B1))).split("\r\n")
    assert full[7] == ",Total,,,,,,,,,,,,,,943.94"
    assert format_cents(173608) == "1736.08" and format_cents(5) == "0.05"


@pytest.mark.parametrize(
    "value", [" =HYPERLINK(1)", "  +cmd", "\u00a0@SUM(A1)", " \t-2", "\n=1"]
)
def test_a_formula_after_leading_whitespace_is_escaped(value: str) -> None:
    """CUT-LIST-CSV-HARDEN: a spreadsheet may skip leading spaces, so a
    trigger after them is a formula too."""
    assert csv_text(value) == f"'{value}"


@pytest.mark.parametrize("value", ["Joist", " Joist", "2x4", "5/4x6", ""])
def test_plain_text_is_unchanged(value: str) -> None:
    assert csv_text(value) == value
