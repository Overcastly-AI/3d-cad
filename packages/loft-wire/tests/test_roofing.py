"""Roofing (ROOFING): shingles by the bundle and underlayment by the roll
over the deck's measured area plus waste, drip edge in 10 ft sticks lapped
2 in a run, starter and ridge cap by the foot; and trim nested on stock.
Checked by hand against docs/reference-parts/buildings.md B7.

The cut list is built from synthetic measurements (a body's extents and
volume, as geometry measures them): B7's deck as two plane-sized panels
(the plugin lays 24; the area is what is bought), its fascia and casing.
``services/geometry/tests/test_roofing_b7.py`` runs the same on the
kernel's measurements of the ``b7-roofing`` golden.
"""

import math
import uuid

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import cut_list_csv
from loft_wire.cut_list_roofing import nest_on_stock
from loft_wire.materials import MATERIALS_BY_KEY
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import PriceBookEntry, PriceBookResponse
from loft_wire.roofing import (
    IN2_PER_SQUARE,
    ROOFING_ITEMS,
    RoofEdgeRun,
    RoofingTakeoff,
    bundles,
    drip_edge_sticks,
    roofing_item_for,
    whole_feet,
)
from loft_wire.yard_order import yard_order
from pydantic import ValidationError

IN = 25.4
SLOPE = 108.75 * math.sqrt(1.25)  # 121.5862 up each 6/12 plane
RUN = 288.875  # X -7/16 .. 288 7/16


def test_the_catalogue() -> None:
    assert [
        (i.key, i.material, i.sale, i.coverage_in2, i.stock_length_ft, i.price_unit)
        for i in ROOFING_ITEMS
    ] == [
        ("shingle_architectural", "asphalt_shingle", "area", 4800.0, None, "each"),
        ("underlayment_synthetic", "polypropylene", "area", 144000.0, None, "each"),
        ("drip_edge", "aluminium_3105", "stick", None, 10, "each"),
        ("shingle_starter", "asphalt_shingle", "foot", None, None, "linear_foot"),
        ("ridge_cap", "asphalt_shingle", "foot", None, None, "linear_foot"),
    ]
    assert all(i.material in MATERIALS_BY_KEY for i in ROOFING_ITEMS)
    assert roofing_item_for("Drip edge") is roofing_item_for("drip_edge")
    assert roofing_item_for("7/16 OSB") is None


def test_b7s_order_by_hand() -> None:
    """70 246.42 in² = 4.8782 squares; x 1.10 x 3 = 16.10: 17 bundles; 1
    roll. An eave of 288.875 takes 3 sticks ((288.875 - 2) / 118 = 2.43), a
    rake of 121.586 2 (1.01); 48.15 ft of starter buys 49, 24.07 of ridge
    cap 25."""
    area = 2 * SLOPE * RUN
    assert area == pytest.approx(70246.42, abs=5e-3)
    assert area / IN2_PER_SQUARE == pytest.approx(4.8782, abs=1e-4)
    assert bundles(area, 10) == 17
    assert bundles(area, 0) == 15
    assert (drip_edge_sticks(RUN), drip_edge_sticks(SLOPE)) == (3, 2)
    assert drip_edge_sticks(120.0) == 1 and drip_edge_sticks(238.0) == 2
    assert drip_edge_sticks(238.0 + 1e-6) == 3
    assert (whole_feet(2 * RUN), whole_feet(RUN)) == (49, 25)
    # At 8/12 a plane runs 130.7012: 75 512.64 in², 18 bundles.
    steep = 2 * 108.75 * math.hypot(1, 8 / 12) * RUN
    assert steep == pytest.approx(75512.64, abs=5e-3)
    assert bundles(steep, 10) == 18


def test_the_allowance_is_bounded() -> None:
    RoofingTakeoff(waste_percent=30)
    with pytest.raises(ValidationError):
        RoofingTakeoff(waste_percent=31)
    with pytest.raises(ValidationError):
        RoofEdgeRun.model_validate({"edge": "valley", "length_mm": 1.0})


def test_casing_nests_on_14_eight_foot_sticks() -> None:
    """B7's 23 casing pieces (buildings.md: 3040s 43 x 55, 2030s 31 x 43,
    the door's 44.5 head and 85.5 legs), first fit decreasing with a 1/8 in
    kerf: the 85.5s alone, each 55 with a 31 (86.125), 44.5 with a 43, the
    43s in pairs: 14 sticks, not 23."""
    casing = [43.0] * 10 + [55.0] * 6 + [31.0] * 4 + [44.5] + [85.5] * 2
    assert sum(casing) == 1099.5
    assert nest_on_stock(casing, 96.0) == 14
    assert nest_on_stock([48.0, 47.875], 96.0) == 1  # a kerf between
    assert nest_on_stock([48.0, 48.0], 96.0) == 2


# --- A cut list from synthetic measurements -------------------------------------------

DECK_T = 7 / 16


def _deck(index: int, edges: list[RoofEdgeRun]) -> tuple[BodyExtent, CutListMember]:
    fid = uuid.UUID(int=0x100 + index)
    body = BodyExtent(
        base_feature_id=fid,
        extents_mm=(RUN * IN, SLOPE * IN, DECK_T * IN),
        volume_mm3=RUN * SLOPE * DECK_T * IN**3,
    )
    member = CutListMember(
        feature_id=fid,
        role="deck",
        title="Roof deck",
        plugin_id="loft.roof",
        metadata=MemberMetadata(
            profile="7/16 OSB",
            material="osb",
            roofing=RoofingTakeoff(edges=edges),
        ),
    )
    return body, member


def _board(
    index: int, role: str, title: str, profile: str, width: float, length: float
) -> tuple[BodyExtent, CutListMember]:
    fid = uuid.UUID(int=0x200 + index)
    t = 1.0 if profile == "5/4x4" else 0.75
    body = BodyExtent(
        base_feature_id=fid,
        extents_mm=(length * IN, width * IN, t * IN),
        volume_mm3=length * width * t * IN**3,
    )
    plugin = "loft.wall" if role in ("casing", "corner_board") else "loft.roof"
    member = CutListMember(
        feature_id=fid,
        role=role,
        title=title,
        plugin_id=plugin,
        metadata=MemberMetadata(profile=profile, material="fibre_cement"),
    )
    return body, member


BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {"material": m, "profile": p, "unit": u, **stock, "price_cents": c}
            for m, p, u, stock, c in [
                ("asphalt_shingle", "shingle_architectural", "each", {}, 3998),
                ("polypropylene", "underlayment_synthetic", "each", {}, 15900),
                ("aluminium_3105", "drip_edge", "each", {"stock_length_ft": 10}, 898),
                ("asphalt_shingle", "shingle_starter", "linear_foot", {}, 275),
                ("asphalt_shingle", "ridge_cap", "linear_foot", {}, 325),
                ("osb", "osb_7_16", "each", {"sheet": "4x8"}, 2198),
                ("fibre_cement", "us_1x10", "each", {"stock_length_ft": 14}, 3698),
                ("fibre_cement", "us_5_4x4", "linear_foot", {}, 145),
            ]
        ],
    }
)


def _cut_list() -> CutListResponse:
    plane = [
        RoofEdgeRun(edge="eave", length_mm=RUN * IN),
        RoofEdgeRun(edge="rake", length_mm=SLOPE * IN),
        RoofEdgeRun(edge="rake", length_mm=SLOPE * IN),
    ]
    pairs = [
        _deck(0, [*plane, RoofEdgeRun(edge="ridge", length_mm=RUN * IN)]),
        _deck(1, plane),
        *(_board(k, "fascia", "Fascia", "1x10", 9.25, 144.4375) for k in range(4)),
        *(
            _board(10 + k, "casing", "Casing", "5/4x4", 3.5, length)
            for k, length in enumerate(
                [43.0] * 10 + [55.0] * 6 + [31.0] * 4 + [44.5] + [85.5] * 2
            )
        ),
    ]
    extents = BodyExtentsResult(
        part_id=uuid.UUID(int=1), tree_version=1, bodies=[b for b, _ in pairs]
    )
    return cut_list_response(
        document_id=uuid.UUID(int=1),
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(extents, [m for _, m in pairs], None),
        price_book=BOOK,
    )


def test_b7s_roofing_lines() -> None:
    cut_list = _cut_list()
    roof = {
        line.member: line
        for line in cut_list.lines
        if line.roofing is not None or line.member == "Roof deck"
    }
    assert list(roof) == [
        "Roof deck",
        "Shingles",
        "Underlayment",
        "Drip edge",
        "Starter",
        "Ridge cap",
    ]
    assert all(line.system == "roof" for line in roof.values())
    shingles = roof["Shingles"]
    assert (shingles.area_mm2 or 0) / IN**2 == pytest.approx(2 * SLOPE * RUN)
    assert (shingles.quantity, shingles.stock_quantity, shingles.waste_percent) == (
        17,
        17,
        10,
    )
    assert shingles.extended_price_cents == 17 * 3998
    assert roof["Underlayment"].extended_price_cents == 15900
    drip = roof["Drip edge"]
    assert (drip.quantity, drip.stock_quantity, drip.stock_length_ft) == (6, 14, 10)
    assert round(drip.total_length_mm / IN, 2) == 1064.09
    assert drip.extended_price_cents == 14 * 898
    assert (roof["Starter"].stock_quantity, roof["Ridge cap"].stock_quantity) == (
        49,
        25,
    )
    assert roof["Ridge cap"].extended_price_cents == 25 * 325
    # The two plane-sized panels fit no sheet: only the deck is unpriced.
    assert all(line.extended_price_cents for line in roof.values() if line.roofing)


def test_trim_lines_are_nested() -> None:
    cut_list = _cut_list()
    fascia = next(x for x in cut_list.lines if x.member == "Fascia")
    assert (fascia.nested, fascia.stock_length_ft, fascia.stock_quantity) == (
        True,
        14,
        4,
    )
    assert fascia.extended_price_cents == 4 * 3698
    casing = next(x for x in cut_list.lines if x.member == "Casing")
    assert (casing.quantity, casing.stock_length_ft, casing.stock_quantity) == (
        23,
        8,
        14,
    )
    assert casing.total_length_mm / IN == pytest.approx(1099.5)
    assert (casing.waste_mm or 0.0) / IN == pytest.approx(14 * 96 - 1099.5)
    assert casing.extended_price_cents == 14 * 8 * 145
    assert [round(c / IN, 3) for c in casing.cuts_mm or []][:3] == [85.5, 85.5, 55.0]


def test_the_csv_and_the_yard_order_buy_bundles_sticks_and_feet() -> None:
    cut_list = _cut_list()
    csv = cut_list_csv(cut_list)
    assert "bundles + 10% waste" in csv and "10 ft sticks, lapped 2 in" in csv
    assert "49 ft" in csv
    order = {line.item: line for line in yard_order(cut_list).lines}
    assert (order["Shingles"].qty, order["Shingles"].length) == ("17", "")
    assert (order["Drip edge"].qty, order["Drip edge"].length) == ("14", "10 ft")
    assert order["Ridge cap"].qty == "25 ft"
    assert (order["Casing"].qty, order["Casing"].length) == ("14", "8 ft")


def test_the_book_prices_each_item_its_one_way() -> None:
    PriceBookEntry(
        material="aluminium_3105",
        profile="drip_edge",
        unit="each",
        stock_length_ft=10,
        price_cents=898,
    )
    for bad in (
        {"material": "asphalt_shingle", "profile": "drip_edge", "unit": "each"},
        {
            "material": "aluminium_3105",
            "profile": "drip_edge",
            "unit": "each",
            "stock_length_ft": 8,
        },
        {
            "material": "asphalt_shingle",
            "profile": "shingle_architectural",
            "unit": "linear_foot",
        },
        {"material": "asphalt_shingle", "profile": "ridge_cap", "unit": "each"},
        {
            "material": "polypropylene",
            "profile": "underlayment_synthetic",
            "unit": "each",
            "sheet": "4x8",
        },
    ):
        with pytest.raises(ValidationError):
            PriceBookEntry.model_validate({**bad, "price_cents": 1})
