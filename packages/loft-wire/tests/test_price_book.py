"""PRICE-BOOK: the price book's wire rules and the cut list's prices.

The B1 and B2 totals are BACKLOG item 6's acceptance, worked by hand there
(B1 $943.94, $839.54 without the 6x6; B2 $396.07; B1 + 2 x B2 $1,736.08).
Here they are priced from the buildings.md tables as pieces; the geometry
suite prices the same buildings from their measured goldens.
"""

import uuid
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
    stock_piece_price,
)
from loft_wire.lumber import LUMBER_PROFILES, MM_PER_INCH
from loft_wire.price_book import (
    MAX_PRICE_BOOK_ENTRIES,
    MAX_PRICE_CENTS,
    PriceBookEntry,
    PriceBookResponse,
    PriceBookUpdate,
)
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
    for member, profile, material, quantity, length_in in table:
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
    long = _pieces([("Beam", "2x10", PT, 1, 300.0)])  # longer than 20 ft
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
        ({"stock_length_ft": 18}, "not a stock length"),
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
    assert rows[4].endswith(",12 ft,3,13,19.98,Each,259.74")
    assert rows[5].endswith(",8 ft,85.5,3,,,")  # the post: blank, not 0
    assert rows[6].endswith(",16 ft,0,26,17.92,Per ft,465.92")
    assert rows[7] == ',"Total of priced lines, 1 unpriced",,,,,,,,,,,,839.54'
    full = cut_list_csv(_priced(_pieces(B1))).split("\r\n")
    assert full[7] == ",Total,,,,,,,,,,,,943.94"
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
