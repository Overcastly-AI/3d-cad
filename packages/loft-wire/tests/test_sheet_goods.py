"""SHEATHING: the sheet-goods library, sheet lines in the cut list, per-sheet
prices, and the price book's version helpers (PRICE-BOOK-VERSION).

The figures are the BACKLOG's B2 and B5 targets, worked by hand there: B2's
OSB is 45 893 in^2 cut from 11 sheets of 4x9 (SHEET-COUNT-PIECES: 9 by area)
at $24.98 = $274.78; B5's plywood is 17 280 in^2, 4 sheets of 4x8 at $42.50
= $170.00.
"""

import math
import uuid
from typing import Any, get_args

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    classify_body,
    cut_list_csv,
    cut_list_response,
    part_pieces,
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
    SHEET_SIZES_BY_KEY,
    SheetMaterialKey,
    covering_sheet,
    sheet_good_for,
)
from loft_wire.sheet_nesting import (
    _leftovers,  # pyright: ignore[reportPrivateUsage]
    sheets_to_cut,
)
from pydantic import ValidationError

IN = 25.4


def test_the_library() -> None:
    assert [(g.key, g.name, g.material, g.thickness_in) for g in SHEET_GOODS] == [
        ("osb_7_16", "7/16 OSB", "osb", 0.4375),
        ("plywood_15_32", "15/32 plywood", "plywood", 0.46875),
        ("plywood_23_32", "23/32 plywood", "plywood", 0.71875),
        ("gypsum_1_2", "1/2 gypsum", "gypsum", 0.5),
        ("gypsum_5_8", "5/8 gypsum", "gypsum", 0.625),
    ]
    assert [(s.key, s.width_in, s.length_in) for s in SHEET_SIZES] == [
        ("4x8", 48, 96),
        ("4x9", 48, 108),
        ("4x10", 48, 120),
        ("4x12", 48, 144),
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


def test_gypsum_is_cut_from_the_4x8_and_4x12_it_is_sold_in() -> None:
    """INTERIOR-WALLS: gypsum board is sold in 4x8 and 4x12, never 4x9 or
    4x10, so a 100 in piece of a 4x12 course is cut from a 4x12."""
    gypsum = sheet_good_for("gypsum_1_2")
    assert gypsum is not None

    def key(a: float, b: float) -> str | None:
        size = covering_sheet(a * IN, b * IN, gypsum)
        return None if size is None else size.key

    assert key(96, 48) == "4x8"
    assert key(85, 48) == "4x8"
    assert key(100, 48) == "4x12"
    assert key(144, 48) == "4x12"
    assert key(145, 48) is None
    osb = sheet_good_for("osb_7_16")
    assert covering_sheet(130 * IN, 48 * IN, osb) is None  # no 4x12 OSB
    assert covering_sheet(130 * IN, 48 * IN) is None


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


def test_panels_are_one_line_of_the_sheets_they_are_cut_from() -> None:
    (line,) = _response(_b2_osb()).lines
    assert (line.member, line.profile, line.material, line.quantity) == (
        "Sheathing",
        "7/16 OSB",
        "osb",
        12,
    )
    assert line.sheet == "4x9"
    assert line.area_mm2 == pytest.approx(45893 * IN**2, abs=1e-6)
    # 10 full-width panels take a sheet each (openings are not credited);
    # the first 17 in panel takes an 11th, the second is cut from its 31 in
    # rip. By area it was 45 893 / 5 184 = 8.85 -> 9, two short.
    assert line.stock_quantity == 11
    assert line.offcut_area_mm2 == pytest.approx((11 * 5184 - 45893) * IN**2)
    assert line.stock_length_ft is None and line.waste_mm is None
    assert line.section_mm == [pytest.approx(7 / 16 * IN), pytest.approx(48 * IN)]
    assert line.length_mm == pytest.approx(108 * IN)


def test_a_panel_exactly_one_sheet_buys_one_sheet() -> None:
    (line,) = _response(
        [_panel(96, 48, 23 / 32, 96 * 48, "Subfloor", "23/32 plywood")] * 3
    ).lines
    assert line.stock_quantity == 3


def test_b5s_subfloor_is_4_sheets_of_4x8() -> None:
    """2 x 96 x 48 whole; 96 x 24 takes a third, its rip 23.875 wide after
    the kerf, which the 48 x 24 fills, 1/8 in short in APA's panel gap
    (SHEET-KERF-GAP); a 48 x 48 takes a fourth, its 47.875 end the other
    square. A kerf alone made it 6 (SHEET-KERF)."""
    (line,) = _response(_b5_plywood()).lines
    assert (line.sheet, line.quantity, line.stock_quantity) == ("4x8", 6, 4)
    assert line.area_mm2 == pytest.approx(17280 * IN**2, abs=1e-6)
    assert line.offcut_area_mm2 == pytest.approx((4 * 4608 - 17280) * IN**2)


def _b5_walls() -> list[tuple[BodyExtent, CutListMember]]:
    """B5's walls (B2's on the floor): 10 panels 48 wide, 2 of 17 and 4
    corner rips 3.9375 wide, all 97.125 tall (test_sheathing_b5's golden)."""
    h = 97.125
    widths = [48.0] * 10 + [17.0] * 2 + [3.9375] * 4
    return [_panel(h, w, 7 / 16, w * h, "Sheathing", "7/16 OSB") for w in widths]


def test_b5s_walls_are_cut_from_12_sheets_not_10_by_area() -> None:
    """SHEET-COUNT-PIECES' acceptance. Each 48 panel takes a 4x9 (10). The
    first 17 takes an 11th and leaves a 31 x 108 rip; the second 17 is cut
    from it, leaving 14 x 108, which holds three 3.9375 rips (2.1875 left);
    the fourth rip takes a 12th sheet. The 48 x 10.875 ends fit no panel."""
    (line,) = _response(_b5_walls()).lines
    assert (line.sheet, line.quantity, line.stock_quantity) == ("4x9", 16, 12)
    area = 10 * 48 * 97.125 + 2 * 17 * 97.125 + 4 * 3.9375 * 97.125
    assert math.ceil(area / (48 * 108)) == 10  # by area, even with no openings


def test_the_count_does_not_depend_on_the_panel_order() -> None:
    panels = _b5_walls() + _b2_osb()
    forward = _response(panels).lines[0].stock_quantity
    backward = _response(panels[::-1]).lines[0].stock_quantity
    # 20 at 48 wide, 4 at 17 two to a sheet, and the 4 rips in the two 14 in
    # rips the 17s leave: 22, one fewer than the two lines apart.
    assert forward == backward == 22


def test_an_offcut_is_reused_only_where_it_covers_a_whole_panel() -> None:
    sheet = SHEET_SIZES_BY_KEY["4x8"]
    ft = 12 * IN
    # A 1/8 in kerf is lost at each cut (SHEET-KERF), but a piece up to 1/8
    # in short fills its panel, the shortfall in APA's panel gap
    # (SHEET-KERF-GAP): a 24 in rip leaves 23.875, which fills the next
    # 24 in rip, so 4 x 24 in rips take 2 sheets.
    assert sheets_to_cut([(8 * ft, 2 * ft)] * 4, sheet) == 2
    # Kerfs add up past the gap: three 16 in rips leave 15.75 for the third
    # (1/4 in short), so 2 sheets; three 15.875 in rips fit one.
    assert sheets_to_cut([(8 * ft, 16 * IN)] * 3, sheet) == 2
    assert sheets_to_cut([(8 * ft, 15.875 * IN)] * 3, sheet) == 1
    # 3 x 32 in wide panels: no offcut (15.875 in) covers another: 3 sheets,
    # though their area is 2 sheets. The 15.875 in rips left fill 16 in ones.
    assert sheets_to_cut([(8 * ft, 32 * IN)] * 3, sheet) == 3
    assert sheets_to_cut([(8 * ft, 32 * IN)] * 3 + [(8 * ft, 16 * IN)] * 3, sheet) == 3
    # A 4 x 4 end is cut across a 4 x 8 sheet: two 48 in squares from one
    # sheet (47 15/16 each in the gap), but not three 32 x 48 thirds (two
    # kerfs leave the last 31.75, 1/4 in short).
    assert sheets_to_cut([(4 * ft, 4 * ft)] * 3, sheet) == 2
    assert sheets_to_cut([(32 * IN, 4 * ft)] * 3, sheet) == 2
    # Only a cut side loses a kerf (SHEET-KERF-HALVES): a side within APA's
    # 1/8 in panel gap of the sheet's is laid uncut. A 96 x 47.9 panel is a
    # whole sheet and leaves nothing; a 96 x 24 rip's other side is uncut, so
    # the 23.875 beside it is all the one rip cut loses.
    assert sheets_to_cut([(95.9 * IN, 47.9 * IN)] * 2, sheet) == 2
    assert sheets_to_cut([(8 * ft, 47.9 * IN), (8 * ft, 0.05 * IN)], sheet) == 2
    assert sheets_to_cut([(8 * ft, 24 * IN), (8 * ft, 23.875 * IN)], sheet) == 1
    # A panel exactly a sheet buys one, not two by a rounding ulp.
    assert sheets_to_cut([(sheet.length_mm + 1e-9, sheet.width_mm)], sheet) == 1
    assert sheets_to_cut([], sheet) == 0


def test_a_part_placed_twice_cuts_its_panels_twice() -> None:
    body, member = _b5_plywood()[4]  # 96 x 24
    piece = classify_body(body, member, None, count=3)
    (line,) = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="assembly",
        name="A",
        length_unit="in",
        pieces=[piece],
    ).lines
    # Three 96 x 24 rips: two from one sheet (the second 1/8 in short, in
    # the panel gap), the third from a second.
    assert (line.quantity, line.stock_quantity) == (3, 2)


def test_a_floor_panel_keeps_the_sheets_strength_axis() -> None:
    """SUBFLOOR-GRAIN: a 60 x 40 panel leaves a 35.875 x 40 end (along the
    sheet's length x across it). A 38 x 20 wall panel turns to fit it, 20
    along the sheet; a 38 x 20 subfloor panel would then run its strength
    axis along the joists, so it takes a second sheet."""
    sheet = SHEET_SIZES_BY_KEY["4x8"]
    panels = [(60 * IN, 40 * IN), (38 * IN, 20 * IN)]
    assert sheets_to_cut(panels, sheet) == 1
    assert sheets_to_cut(panels, sheet, turn=False) == 2
    # The member's role decides: subfloor panels keep the axis, wall
    # sheathing turns. Each its own line, though the product is the same.
    sizes = [(60, 40), (38, 20)]
    floor = [
        _panel(a, b, 23 / 32, a * b, "Subfloor", "23/32 plywood") for a, b in sizes
    ]
    wall = [
        _panel(a, b, 23 / 32, a * b, "Sheathing", "23/32 plywood") for a, b in sizes
    ]
    lines = _response(floor + wall).lines
    assert [(ln.member, ln.stock_quantity) for ln in lines] == [
        ("Subfloor", 2),
        ("Sheathing", 1),
    ]


def test_a_piece_is_never_more_than_an_eighth_short() -> None:
    """The gap absorbs 1/8 in once, not per piece: a 40 x 24 panel cut from
    a 96 x 23.875 rip leaves an end 23.875 wide (the material), not 24 (the
    panel), so a 30 x 24.125 and a 20 x 24.25 after it do not fit."""
    leftovers = _leftovers((96 * IN, 23.875 * IN), (40 * IN, 24 * IN), turn=True)
    assert leftovers == [(pytest.approx(55.875 * IN), pytest.approx(23.875 * IN))]
    assert _leftovers((96 * IN, 23.875 * IN), (40 * IN, 24 * IN), turn=False) == [
        (pytest.approx(55.875 * IN), pytest.approx(23.875 * IN))
    ]
    sheet = SHEET_SIZES_BY_KEY["4x8"]
    panels = [(96, 24), (40, 24), (30, 24.125), (20, 24.25)]
    assert sheets_to_cut([(a * IN, b * IN) for a, b in panels], sheet) == 2


def _oriented(
    across: float, along: float, across_axis: tuple[float, float, float]
) -> tuple[BodyExtent, CutListMember]:
    """A 23/32 subfloor panel *across* x *along* (in), its across side along
    *across_axis* in the world, the joists along the other face axis."""
    body, member = _panel(
        max(across, along),
        min(across, along),
        23 / 32,
        across * along,
        "Subfloor",
        "23/32 plywood",
    )
    other = (0.0, 1.0, 0.0) if across_axis == (1.0, 0.0, 0.0) else (1.0, 0.0, 0.0)
    first, second = (across_axis, other) if across >= along else (other, across_axis)
    body = body.model_copy(update={"axes": (first, second, (0.0, 0.0, 1.0))})
    return body, member


def test_a_floor_panel_runs_across_the_joists_as_laid() -> None:
    """SUBFLOOR-GRAIN in the panel's true orientation: geometry's axes and
    the part's joists say which side runs across them. Three 30 x 48 last-
    column panels (30 across the joists, 48 along) are cut across one 96 in
    sheet's length; turned long side along the sheet, as the extents alone
    read them, they took 2."""
    joist = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(189 * IN, 9.25 * IN, 1.5 * IN),
        volume_mm3=189 * 9.25 * 1.5 * IN**3,
        axes=((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    )
    joist_member = CutListMember(
        feature_id=joist.base_feature_id,
        role="joist",
        title="Joist",
        metadata=MemberMetadata(profile="2x10", material="spf_lumber"),
    )
    panels = [_oriented(30, 48, (1.0, 0.0, 0.0)) for _ in range(3)]
    bodies = [joist, *(b for b, _ in panels)]
    members = [joist_member, *(m for _, m in panels)]
    result = BodyExtentsResult(part_id=uuid.uuid4(), tree_version=1, bodies=bodies)
    pieces = part_pieces(result, members, None)
    assert [p.grain_mm for p in pieces[1:]] == [
        (pytest.approx(30 * IN), pytest.approx(48 * IN))
    ] * 3
    lines = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="F",
        length_unit="in",
        pieces=pieces,
    ).lines
    assert [(ln.member, ln.stock_quantity) for ln in lines if ln.sheet] == [
        ("Subfloor", 1)
    ]
    # The extents alone (no joist, no axes) read 48 x 30, long side across.
    assert (
        sheets_to_cut([(48 * IN, 30 * IN)] * 3, SHEET_SIZES_BY_KEY["4x8"], turn=False)
        == 2
    )
    # A full panel lies across the joists, its 96 in side along the sheet.
    body, member = _oriented(96, 48, (1.0, 0.0, 0.0))
    result = BodyExtentsResult(
        part_id=uuid.uuid4(), tree_version=1, bodies=[joist, body]
    )
    (_, full) = part_pieces(result, [joist_member, member], None)
    assert full.grain_mm == (pytest.approx(96 * IN), pytest.approx(48 * IN))


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
        11 * 2498,
    )
    assert (plywood.unit_price_cents, plywood.extended_price_cents) == (4250, 17000)
    assert response.total_price_cents == 27478 + 17000
    # A 4x8 price does not price a line of 4x9 sheets.
    other = _sheet_book(("osb", "osb_7_16", "4x8", 2000))
    (line,) = _response(_b2_osb(), other).lines
    assert line.unit_price_cents is None


def test_the_csv_shows_area_and_sheet() -> None:
    book = _sheet_book(("osb", "osb_7_16", "4x9", 2498))
    rows = cut_list_csv(_response(_b2_osb(), book)).split("\r\n")
    assert rows[0].startswith(
        "Item,System,Member,Profile,Section (in),Material,Qty,Length (in),"
        "Total length (in),Area (sq in),Stock,"
    )
    assert rows[1] == (
        "1,Sheathing,Sheathing,7/16 OSB,0.4375 x 48,OSB (oriented strand board),12,,,"
        "45893,4x9 sheet,,11,24.98,Each,274.78"
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
