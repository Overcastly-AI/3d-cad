"""SHEATHING: the sheet-goods library, sheet lines in the cut list, per-sheet
prices, and the price book's version helpers (PRICE-BOOK-VERSION).

The figures are the BACKLOG's B2 and B5 targets, worked by hand there: B2's
OSB is 45 893 in^2, 9 sheets of 4x9 at $24.98 = $224.82; B5's plywood is
17 280 in^2, 4 sheets of 4x8 at $42.50 = $170.00.
"""

import uuid
from typing import Any, get_args

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    CutListMember,
    classify_body,
    cut_list_csv,
    cut_list_response,
)
from loft_wire.materials import MATERIALS_BY_KEY, MaterialKey
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import (
    EMPTY_PRICE_BOOK,
    PriceBookEntry,
    PriceBookResponse,
    PriceBookUpdate,
    parse_if_match,
    price_book_etag,
)
from loft_wire.sheet_goods import (
    SHEET_GOODS,
    SHEET_SIZES,
    SheetMaterialKey,
    covering_sheet,
    sheet_good_for,
)
from pydantic import ValidationError

IN = 25.4


def test_the_library() -> None:
    assert [(g.key, g.name, g.material, g.thickness_in) for g in SHEET_GOODS] == [
        ("osb_7_16", "7/16 OSB", "osb", 0.4375),
        ("plywood_15_32", "15/32 plywood", "plywood", 0.46875),
        ("plywood_23_32", "23/32 plywood", "plywood", 0.71875),
    ]
    assert [(s.key, s.width_in, s.length_in) for s in SHEET_SIZES] == [
        ("4x8", 48, 96),
        ("4x9", 48, 108),
        ("4x10", 48, 120),
    ]
    # Every sheet material is a library material, with a density.
    assert set(get_args(SheetMaterialKey)) <= set(get_args(MaterialKey))
    for key in get_args(SheetMaterialKey):
        assert MATERIALS_BY_KEY[key].density_kg_m3 > 0
    assert sheet_good_for("7/16 OSB") is SHEET_GOODS[0]
    assert sheet_good_for("osb_7_16") is SHEET_GOODS[0]
    assert sheet_good_for("2x4") is None and sheet_good_for(None) is None


def test_a_panel_is_cut_from_the_shortest_sheet_that_covers_it() -> None:
    def key(a: float, b: float) -> str | None:
        size = covering_sheet(a * IN, b * IN)
        return None if size is None else size.key

    assert key(96, 48) == "4x8"
    assert key(48, 96) == "4x8"  # either order
    assert key(97.125, 48) == "4x9"  # B2's walls
    assert key(97.125, 17) == "4x9"
    assert key(108, 48) == "4x9"
    assert key(109, 48) == "4x10"
    assert key(121, 48) is None
    assert key(96, 48.5) is None


def _panel(
    length: float, width: float, thickness: float, area: float, title: str, profile: str
) -> tuple[BodyExtent, CutListMember]:
    body = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(length * IN, width * IN, thickness * IN),
        volume_mm3=area * thickness * IN**3,
    )
    member = CutListMember(
        feature_id=body.base_feature_id,
        role=title.lower(),
        title=title,
        metadata=MemberMetadata(
            profile=profile, material="osb" if "OSB" in profile else "plywood"
        ),
    )
    return body, member


def _b2_osb() -> list[tuple[BodyExtent, CutListMember]]:
    """B2's 12 panels: 9 whole (6 of 48, 2 of 17... by wall) and three cut
    round the door and window, 45 893 in^2 net in all."""
    h = 97.125
    whole = [48.0] * 7 + [17.0] * 2
    out = [_panel(h, w, 7 / 16, w * h, "Sheathing", "7/16 OSB") for w in whole]
    out.append(_panel(h, 48, 7 / 16, 48 * h - 38 * 82.5, "Sheathing", "7/16 OSB"))
    out.append(_panel(h, 48, 7 / 16, 48 * h - 3.75 * 36.5, "Sheathing", "7/16 OSB"))
    out.append(_panel(h, 48, 7 / 16, 48 * h - 20.75 * 36.5, "Sheathing", "7/16 OSB"))
    return out


def _b5_plywood() -> list[tuple[BodyExtent, CutListMember]]:
    sizes = [(96, 48), (48, 48), (48, 48), (96, 48), (96, 24), (48, 24)]
    return [_panel(a, b, 23 / 32, a * b, "Subfloor", "23/32 plywood") for a, b in sizes]


def _response(
    panels: list[tuple[BodyExtent, CutListMember]],
    book: PriceBookResponse | None = None,
) -> Any:
    pieces = [classify_body(body, member, None) for body, member in panels]
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B",
        length_unit="in",
        pieces=pieces,
        price_book=EMPTY_PRICE_BOOK if book is None else book,
    )


def _sheet_book(*entries: tuple[str, str, str, int]) -> PriceBookResponse:
    return PriceBookResponse.model_validate(
        {
            "currency": "USD",
            "entries": [
                {
                    "material": m,
                    "profile": p,
                    "unit": "each",
                    "sheet": s,
                    "price_cents": c,
                }
                for m, p, s, c in entries
            ],
        }
    )


def test_panels_are_one_line_of_sheets_by_area() -> None:
    (line,) = _response(_b2_osb()).lines
    assert (line.member, line.profile, line.material, line.quantity) == (
        "Sheathing",
        "7/16 OSB",
        "osb",
        12,
    )
    assert line.sheet == "4x9"
    assert line.area_mm2 == pytest.approx(45893 * IN**2, abs=1e-6)
    assert line.stock_quantity == 9  # 45 893 / 5 184 = 8.85
    assert line.stock_length_ft is None and line.waste_mm is None
    assert line.section_mm == [pytest.approx(7 / 16 * IN), pytest.approx(48 * IN)]
    assert line.length_mm == pytest.approx(108 * IN)


def test_a_panel_exactly_one_sheet_buys_one_sheet() -> None:
    (line,) = _response(
        [_panel(96, 48, 23 / 32, 96 * 48, "Subfloor", "23/32 plywood")] * 3
    ).lines
    assert line.stock_quantity == 3


def test_b5s_subfloor_is_4_sheets_of_4x8() -> None:
    (line,) = _response(_b5_plywood()).lines
    assert (line.sheet, line.quantity, line.stock_quantity) == ("4x8", 6, 4)
    assert line.area_mm2 == pytest.approx(17280 * IN**2, abs=1e-6)


def test_panels_too_big_for_any_sheet_are_listed_unbought() -> None:
    (line,) = _response(
        [_panel(130, 48, 7 / 16, 130 * 48, "Sheathing", "7/16 OSB")]
    ).lines
    assert line.sheet is None and line.stock_quantity is None
    assert line.unit_price_cents is None


def test_sheet_lines_are_priced_per_sheet() -> None:
    book = _sheet_book(
        ("osb", "osb_7_16", "4x9", 2498), ("plywood", "plywood_23_32", "4x8", 4250)
    )
    response = _response(_b2_osb() + _b5_plywood(), book)
    osb, plywood = response.lines
    assert (osb.unit_price_cents, osb.price_unit, osb.extended_price_cents) == (
        2498,
        "each",
        22482,
    )
    assert (plywood.unit_price_cents, plywood.extended_price_cents) == (4250, 17000)
    assert response.total_price_cents == 22482 + 17000
    # A 4x8 price does not price a line of 4x9 sheets.
    other = _sheet_book(("osb", "osb_7_16", "4x8", 2000))
    (line,) = _response(_b2_osb(), other).lines
    assert line.unit_price_cents is None


def test_the_csv_shows_area_and_sheet() -> None:
    book = _sheet_book(("osb", "osb_7_16", "4x9", 2498))
    rows = cut_list_csv(_response(_b2_osb(), book)).split("\r\n")
    assert rows[0].startswith(
        "Item,Member,Profile,Section (in),Material,Qty,Length (in),"
        "Total length (in),Area (sq in),Stock,"
    )
    assert rows[1] == (
        "1,Sheathing,7/16 OSB,0.4375 x 48,OSB (oriented strand board),12,,,"
        "45893,4x9 sheet,,9,24.98,Each,224.82"
    )


# --- The price book's sheet entries ---------------------------------------------


def _entry(**fields: Any) -> PriceBookEntry:
    return PriceBookEntry.model_validate(
        {"material": "osb", "profile": "osb_7_16", "unit": "each", **fields}
    )


def test_a_sheet_price_names_its_sheet() -> None:
    entry = _entry(sheet="4x9", price_cents=2498)
    assert entry.key == ("osb", "osb_7_16", "each", None, "4x9")
    with pytest.raises(ValidationError, match="sheet"):
        _entry(price_cents=2498)
    with pytest.raises(ValidationError, match="sheet"):
        _entry(sheet="4x9", stock_length_ft=8, price_cents=2498)
    with pytest.raises(ValidationError, match="sheet"):
        _entry(unit="linear_foot", sheet="4x9", price_cents=2498)
    with pytest.raises(ValidationError):
        _entry(sheet="4x12", price_cents=2498)
    with pytest.raises(ValidationError, match="sheet"):
        PriceBookEntry.model_validate(
            {
                "material": "spf_lumber",
                "profile": "us_2x4",
                "unit": "each",
                "stock_length_ft": 8,
                "sheet": "4x8",
                "price_cents": 398,
            }
        )


def test_a_book_holds_one_price_per_sheet() -> None:
    a = {"material": "osb", "profile": "osb_7_16", "unit": "each", "price_cents": 1}
    PriceBookUpdate.model_validate(
        {"entries": [{**a, "sheet": "4x8"}, {**a, "sheet": "4x9"}]}
    )
    with pytest.raises(ValidationError, match="repeats"):
        PriceBookUpdate.model_validate(
            {"entries": [{**a, "sheet": "4x8"}, {**a, "sheet": "4x8"}]}
        )


# --- PRICE-BOOK-VERSION -----------------------------------------------------------


def test_the_version_is_the_etag_and_if_match_reads_it_back() -> None:
    assert PriceBookResponse(currency="USD").version == 0
    assert price_book_etag(3) == '"3"'
    assert parse_if_match('"3"') == 3
    assert parse_if_match("3") == 3
    assert parse_if_match(' "0" ') == 0
    for bad in ("*", "", '""', '"-1"', '"3', 'W/"3"', '"1e3"', '"٣"', "9" * 19):
        assert parse_if_match(bad) is None, bad
