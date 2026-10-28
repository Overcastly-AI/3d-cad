"""Foundation takeoff (SLAB, FOUNDATION-TAKEOFF): concrete by the cubic yard,
each pour its own order, rebar sticks, anchor bolts, and a crawl space's vents
and access door Each, checked against docs/reference-parts/buildings.md B8,
B8's edits, B2's plain slab and B9's pours, typed by hand.

The cut list is built from synthetic measurements (a body's extents and
volume, as geometry measures them): the slab's pour, its two loops, and the
bottom plates its walls stand on. ``services/geometry/tests/test_slab_b8.py``
runs the same on the kernel's measurements of the B8 golden.
"""

import uuid
from fractions import Fraction
from typing import Any

import pytest
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import (
    cut_list_csv,
)
from loft_wire.foundation import (
    FOUNDATION_ITEMS,
    AnchorBolts,
    ConcretePour,
    FoundationOpening,
    RebarRun,
    anchor_bolt_count,
    concrete_order_yd3,
    rebar_sticks,
    volume_yd3,
)
from loft_wire.materials import MATERIALS_BY_KEY
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import PriceBookEntry, PriceBookResponse
from pydantic import ValidationError

IN = 25.4
IN3 = IN**3


def test_the_catalogue() -> None:
    assert [(i.key, i.name, i.material, i.price_unit) for i in FOUNDATION_ITEMS] == [
        ("ready_mix", "Ready-mix concrete", "concrete", "cubic_yard"),
        ("rebar_4", "#4 rebar", "steel_a615", "each"),
        ("anchor_bolt_1_2", "1/2 in anchor bolt", "steel_f1554", "each"),
        ("foundation_vent", "Foundation vent", "steel_1018", "each"),
        ("crawl_access_door", "Crawl-space access door", "steel_1018", "each"),
    ]
    assert all(i.material in MATERIALS_BY_KEY for i in FOUNDATION_ITEMS)


# --- The arithmetic ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("in3", "net", "ordered"),
    [
        # B8: 308 736 / 46 656 = 6.617; x 1.05 = 6.948, ordered 7.
        (308736, 6.62, Fraction(7)),
        # B8 at 28 ft: 354 816 -> 7.605; x 1.05 = 7.985, ordered 8.
        (354816, 7.60, Fraction(8)),
        # B2's plain slab: 69 120 -> 1.481; x 1.05 = 1.556, ordered 1.75.
        (69120, 1.48, Fraction(7, 4)),
        # B9's footing: 118 784 -> 2.546; x 1.05 = 2.673, ordered 2.75.
        (118784, 2.55, Fraction(11, 4)),
        # B9's stem: 188 544 -> 4.041; x 1.05 = 4.243, ordered 4.25.
        (188544, 4.04, Fraction(17, 4)),
        # B9's stem at a 30 in crawl: 233 088 -> 4.996; x 1.05 = 5.246: 5.25.
        (233088, 5.00, Fraction(21, 4)),
    ],
)
def test_concrete_orders_the_allowance_rounded_up_to_a_quarter(
    in3: int, net: float, ordered: Fraction
) -> None:
    assert round(volume_yd3(in3 * IN3), 2) == net
    assert concrete_order_yd3(in3 * IN3, 5) == ordered


def test_with_no_allowance_the_order_is_the_net_rounded_up() -> None:
    """The spec's old figures (no waste factor): 6.75 for B8, 1.50 for B2."""
    assert concrete_order_yd3(308736 * IN3, 0) == Fraction(27, 4)
    assert concrete_order_yd3(69120 * IN3, 0) == Fraction(3, 2)
    # Exactly 2 yd^3 orders 2, not 2.25 by a rounding ulp.
    assert concrete_order_yd3(2 * 46656 * IN3, 0) == 2


def test_rebar_sticks_lap_24_in() -> None:
    assert rebar_sticks(912, closed=True) == 5  # B8: 76 ft, ceil(76 / 18)
    assert rebar_sticks(1008, closed=True) == 5  # 84 ft
    assert rebar_sticks(216, closed=True) == 1
    assert rebar_sticks(217, closed=True) == 2
    assert rebar_sticks(240, closed=False) == 1
    assert rebar_sticks(456, closed=False) == 2  # 20 ft + 18 ft
    assert rebar_sticks(457, closed=False) == 3


@pytest.mark.parametrize(
    ("length", "bolts"),
    [(125, 3), (181, 4), (288, 5), (173, 4), (336, 6), (96, 2), (24, 2), (12, 2)],
)
def test_anchor_bolts_by_r403_1_6(length: float, bolts: int) -> None:
    assert anchor_bolt_count(length) == bolts


# --- The price book ------------------------------------------------------------------


def _entry(**fields: Any) -> PriceBookEntry:
    return PriceBookEntry.model_validate(fields)


def test_each_item_is_priced_its_one_way() -> None:
    _entry(material="concrete", profile="ready_mix", unit="cubic_yard", price_cents=1)
    _entry(
        material="steel_a615",
        profile="rebar_4",
        unit="each",
        stock_length_ft=20,
        price_cents=1,
    )
    _entry(
        material="steel_f1554", profile="anchor_bolt_1_2", unit="each", price_cents=1
    )
    for key in ("foundation_vent", "crawl_access_door"):
        _entry(material="steel_1018", profile=key, unit="each", price_cents=1)
    for bad in (
        {
            "material": "steel_1018",
            "profile": "foundation_vent",
            "unit": "each",
            "stock_length_ft": 8,
        },
        {
            "material": "steel_1018",
            "profile": "crawl_access_door",
            "unit": "each",
            "sheet": "4x8",
        },
        {
            "material": "steel_1018",
            "profile": "foundation_vent",
            "unit": "linear_foot",
        },
        {"material": "concrete", "profile": "ready_mix", "unit": "each"},
        {
            "material": "concrete",
            "profile": "ready_mix",
            "unit": "cubic_yard",
            "stock_length_ft": 8,
        },
        {"material": "steel_a615", "profile": "rebar_4", "unit": "each"},
        {
            "material": "steel_a615",
            "profile": "rebar_4",
            "unit": "linear_foot",
        },
        {
            "material": "steel_f1554",
            "profile": "anchor_bolt_1_2",
            "unit": "each",
            "stock_length_ft": 8,
        },
        {"material": "spf_lumber", "profile": "us_2x4", "unit": "cubic_yard"},
    ):
        with pytest.raises(ValidationError):
            _entry(**bad, price_cents=1)


BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": "concrete",
                "profile": "ready_mix",
                "unit": "cubic_yard",
                "price_cents": 16500,
            },
            {
                "material": "steel_a615",
                "profile": "rebar_4",
                "unit": "each",
                "stock_length_ft": 20,
                "price_cents": 1498,
            },
            {
                "material": "steel_f1554",
                "profile": "anchor_bolt_1_2",
                "unit": "each",
                "price_cents": 248,
            },
            {
                "material": "steel_1018",
                "profile": "foundation_vent",
                "unit": "each",
                "price_cents": 1298,
            },
            {
                "material": "steel_1018",
                "profile": "crawl_access_door",
                "unit": "each",
                "price_cents": 4997,
            },
        ],
    }
)


# --- The cut list ---------------------------------------------------------------------


def _house(length: int) -> tuple[BodyExtentsResult, list[CutListMember]]:
    """B8 at *length*: the slab (plate and edge, measured as one body), its
    two loops (the outline less 4 x the 12 in edge), and the bottom plates:
    the front cut at the door's rough opening (X 125..163), the back whole,
    the sides 181 between them."""
    bodies: list[BodyExtent] = []
    members: list[CutListMember] = []
    slab_in3 = length * 192 * 4 + (length * 192 - (length - 24) * 168) * 8
    slab = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(length * IN, 192 * IN, 12 * IN),
        volume_mm3=slab_in3 * IN3,
    )
    loop = 2 * (length + 192) - 48
    bodies.append(slab)
    members.append(
        CutListMember(
            feature_id=slab.base_feature_id,
            role="slab",
            title="Slab",
            plugin_id="loft.slab",
            metadata=MemberMetadata(
                profile="Ready-mix concrete",
                material="concrete",
                concrete=ConcretePour(),
                rebar=[RebarRun(length_mm=loop * IN, closed=True)] * 2,
            ),
        )
    )
    for plate in (125, length - 163, length, 181, 181):
        body = BodyExtent(
            base_feature_id=uuid.uuid4(),
            extents_mm=(plate * IN, 5.5 * IN, 1.5 * IN),
            volume_mm3=plate * 5.5 * 1.5 * IN3,
        )
        bodies.append(body)
        members.append(
            CutListMember(
                feature_id=body.base_feature_id,
                role="bottom_plate",
                title="Bottom plate",
                plugin_id="loft.wall",
                metadata=MemberMetadata(
                    profile="2x6",
                    material="southern_pine_pt",
                    anchor_bolts=AnchorBolts(),
                ),
            )
        )
    extents = BodyExtentsResult(part_id=uuid.uuid4(), tree_version=1, bodies=bodies)
    return extents, members


def _cut_list(length: int, book: PriceBookResponse = BOOK) -> Any:
    extents, members = _house(length)
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B8",
        length_unit="in",
        pieces=part_pieces(extents, members, None),
        price_book=book,
    )


def _foundation(cut_list: Any) -> list[tuple[Any, ...]]:
    return [
        (
            line.member,
            line.item,
            line.quantity,
            None if line.order_yd3 is None else line.order_yd3,
            line.stock_quantity,
            line.extended_price_cents,
        )
        for line in cut_list.lines
        if line.system == "foundation"
    ]


def test_b8_lists_its_pour_sticks_and_bolts_first() -> None:
    cut_list = _cut_list(288)
    assert cut_list.lines[0].system == "foundation"
    assert _foundation(cut_list) == [
        # 7 yd^3 x $165.00
        ("Slab", "concrete", 1, 7.0, None, 115500),
        # 2 loops of 912 (76 ft), 5 sticks each, x $14.98
        ("Rebar", "rebar", 2, None, 10, 14980),
        # 3 + 3 + 5 + 4 + 4, x $2.48
        ("Anchor bolt", "anchor_bolt", 19, None, 19, 4712),
    ]
    concrete = cut_list.lines[0]
    assert concrete.volume_mm3 == pytest.approx(308736 * IN3)
    assert (concrete.waste_percent, concrete.price_unit) == (5, "cubic_yard")
    rebar = cut_list.lines[1]
    assert (round(rebar.length_mm / IN, 9), rebar.stock_length_ft) == (912, 20)
    assert cut_list.unpriced_lines == 3  # the plates: no lumber in this book


def test_b8_at_28_ft_is_one_edit() -> None:
    assert _foundation(_cut_list(336)) == [
        ("Slab", "concrete", 1, 8.0, None, 132000),
        ("Rebar", "rebar", 2, None, 10, 14980),
        # front 3 + 4 (125 and 173), back 6, sides 4 + 4
        ("Anchor bolt", "anchor_bolt", 21, None, 21, 5208),
    ]


def test_unpriced_items_stay_blank() -> None:
    cut_list = _cut_list(288, PriceBookResponse(currency="USD"))
    assert [line.extended_price_cents for line in cut_list.lines] == [None] * len(
        cut_list.lines
    )
    assert cut_list.lines[0].order_yd3 == 7.0  # ordered with no price


def test_the_csv_lists_the_order() -> None:
    rows = cut_list_csv(_cut_list(288)).split("\r\n")
    assert rows[1] == (
        '1,Foundation,Slab,Ready-mix concrete,,"Concrete (normal-weight, '
        'reinforced)",1,,,,6.62 yd3 net + 5% waste,,7.00,165.00,Per yd3,1155.00'
    )
    assert rows[2] == (
        "2,Foundation,Rebar,#4 rebar,,Reinforcing steel (ASTM A615),2,912,1824,,"
        "20 ft,,10,14.98,Each,149.80"
    )
    assert rows[3] == (
        "3,Foundation,Anchor bolt,1/2 in anchor bolt,,Anchor-bolt steel (ASTM "
        "F1554),19,,,,Each,,19,2.48,Each,47.12"
    )


def _with_twin(waste: int) -> Any:
    """B8 and a second slab pour, a twin of the first, at *waste* percent."""
    extents, members = _house(288)
    twin = extents.bodies[0].model_copy(update={"base_feature_id": uuid.uuid4()})
    other = members[0].model_copy(
        update={
            "feature_id": twin.base_feature_id,
            "metadata": members[0].metadata.model_copy(
                update={"concrete": ConcretePour(waste_percent=waste), "rebar": None}
            ),
        }
    )
    extents = extents.model_copy(update={"bodies": [*extents.bodies, twin]})
    pieces = part_pieces(extents, [*members, other], None)
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B8",
        length_unit="in",
        pieces=pieces,
        price_book=BOOK,
    )


def test_a_pours_waste_is_its_own_line() -> None:
    """Another allowance is another line: 6.62 x 1.10 = 7.28, 7.50."""
    pours = [line for line in _with_twin(10).lines if line.item == "concrete"]
    assert [(p.waste_percent, p.order_yd3) for p in pours] == [(5, 7.0), (10, 7.5)]


def test_two_pours_of_one_member_are_ordered_one_by_one() -> None:
    """SLAB-MULTI-POUR: two 6.62 yd³ slabs are two deliveries of 7.00 (6.95
    each, rounded up), 14.00 on their one line."""
    (pour,) = [line for line in _with_twin(5).lines if line.item == "concrete"]
    assert (pour.member, pour.quantity, pour.order_yd3) == ("Slab", 2, 14.0)
    assert pour.extended_price_cents == 14 * 16500
    # B2's plain slab twice: 1.56 + 1.56 = 3.11 would round to 3.25 on the
    # sum, but each truck brings 1.75: 3.50.
    b2 = 69120 * IN3
    assert concrete_order_yd3(2 * b2, 5) == Fraction(13, 4)
    assert 2 * concrete_order_yd3(b2, 5) == Fraction(7, 2)


# --- A pour that bolts another feature's plates (CRAWL-SPACE) ------------------------


VENTS = FoundationOpening(
    item="foundation_vent", width_mm=16 * IN, height_mm=8 * IN, quantity=5
)
ACCESS = FoundationOpening(
    item="crawl_access_door", width_mm=24 * IN, height_mm=16 * IN, quantity=1
)


def _b9(
    openings: list[FoundationOpening] | None = None,
) -> tuple[BodyExtentsResult, list[CutListMember]]:
    """B9's footing (118 784 in^3, two loops of 968 and 888) and stem
    (188 544 in^3 less its openings, the bolts for the floor's four sills,
    and *openings*), a pour each."""
    footing = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(296 * IN, 200 * IN, 8 * IN),
        volume_mm3=118784 * IN3,
    )
    stem = BodyExtent(
        base_feature_id=uuid.uuid4(),
        extents_mm=(288 * IN, 192 * IN, 26.5 * IN),
        volume_mm3=188544 * IN3,
    )
    members = [
        CutListMember(
            feature_id=footing.base_feature_id,
            role="footing",
            title="Footing",
            plugin_id="loft.foundation",
            metadata=MemberMetadata(
                profile="Ready-mix concrete",
                material="concrete",
                concrete=ConcretePour(),
                rebar=[
                    RebarRun(length_mm=968 * IN, closed=True),
                    RebarRun(length_mm=888 * IN, closed=True),
                ],
            ),
        ),
        CutListMember(
            feature_id=stem.base_feature_id,
            role="stem",
            title="Stem wall",
            plugin_id="loft.foundation",
            metadata=MemberMetadata(
                profile="Ready-mix concrete",
                material="concrete",
                concrete=ConcretePour(),
                anchor_bolts=AnchorBolts(
                    plates_mm=[288 * IN, 288 * IN, 181 * IN, 181 * IN]
                ),
                foundation_openings=openings,
            ),
        ),
    ]
    extents = BodyExtentsResult(
        part_id=uuid.uuid4(), tree_version=1, bodies=[footing, stem]
    )
    return extents, members


def _b9_cut_list(openings: list[FoundationOpening] | None = None) -> Any:
    extents, members = _b9(openings)
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B9",
        length_unit="in",
        pieces=part_pieces(extents, members, None),
        price_book=BOOK,
    )


def test_b9s_pours_are_two_orders_and_list_the_sills_bolts() -> None:
    cut_list = _b9_cut_list()
    assert _foundation(cut_list) == [
        # 118 784 in^3 = 2.55 yd^3; x 1.05 = 2.67: 2.75 at $165.00
        ("Footing", "concrete", 1, 2.75, None, 45375),
        # 888 (74 ft) and 968 (80.67 ft): 5 sticks each, x $14.98
        ("Rebar", "rebar", 1, None, 5, 7490),
        ("Rebar", "rebar", 1, None, 5, 7490),
        # 188 544 in^3 = 4.04 yd^3; x 1.05 = 4.24: 4.25 at $165.00
        ("Stem wall", "concrete", 1, 4.25, None, 70125),
        # 5 + 5 + 4 + 4 for the sills, not the stem's 288 in length
        ("Anchor bolt", "anchor_bolt", 18, None, 18, 4464),
    ]
    footing, stem = (line for line in cut_list.lines if line.item == "concrete")
    assert footing.volume_mm3 is not None and stem.volume_mm3 is not None
    assert round(footing.volume_mm3 / IN3 / 46656, 2) == 2.55
    assert round(stem.volume_mm3 / IN3 / 46656, 2) == 4.04
    # 7.00 in all, as the one line ordered before (6.92 rounded once).
    assert footing.order_yd3 + stem.order_yd3 == 7.0


def test_b9_lists_its_vents_and_access_door_each() -> None:
    cut_list = _b9_cut_list([VENTS, ACCESS])
    assert _foundation(cut_list)[-2:] == [
        ("Vent 16 x 8", "foundation_vent", 5, None, 5, 5 * 1298),
        ("Access door 24 x 16", "access_door", 1, None, 1, 4997),
    ]
    vents, door = cut_list.lines[-2:]
    assert (vents.profile, vents.material, vents.price_unit) == (
        "Foundation vent",
        "steel_1018",
        "each",
    )
    assert door.profile == "Crawl-space access door"
    rows = cut_list_csv(cut_list).split("\r\n")
    assert rows[6].startswith("6,Foundation,Vent 16 x 8,Foundation vent,,")
    assert rows[6].endswith(",5,,,,Each,,5,12.98,Each,64.90")
    # A second size is a line of its own.
    small = VENTS.model_copy(update={"width_mm": 14 * IN, "quantity": 1})
    lines = _foundation(_b9_cut_list([VENTS, small, ACCESS]))
    assert [line[:3] for line in lines[-3:]] == [
        ("Vent 16 x 8", "foundation_vent", 5),
        ("Vent 14 x 8", "foundation_vent", 1),
        ("Access door 24 x 16", "access_door", 1),
    ]


def test_an_opening_is_bounded_and_sized_in_inches() -> None:
    assert VENTS.size == "16 x 8"
    odd = FoundationOpening(
        item="foundation_vent", width_mm=15.5 * IN, height_mm=7.75 * IN, quantity=1
    )
    assert odd.size == "15.5 x 7.75"
    for bad in (
        {"width_mm": 0.0},
        {"height_mm": 4000.0},
        {"quantity": 0},
        {"quantity": 10_001},
        {"item": "window_3040"},
    ):
        with pytest.raises(ValidationError):
            FoundationOpening.model_validate({**VENTS.model_dump(), **bad})
    with pytest.raises(ValidationError):
        MemberMetadata(foundation_openings=[VENTS] * 17)
    # Absent on every other member: stored metadata keeps its bytes.
    assert "foundation_openings" not in MemberMetadata().model_dump(mode="json")


def test_bolts_on_a_plate_count_its_measured_length() -> None:
    assert AnchorBolts().count(288) == 5
    assert AnchorBolts(plates_mm=[288 * IN, 181 * IN]).count(1000) == 9
    # Absent on a plate: the stored metadata keeps SLAB's bytes.
    assert AnchorBolts().model_dump(mode="json") == {"item": "anchor_bolt_1_2"}
    with pytest.raises(ValidationError):
        AnchorBolts(plates_mm=[0.0])
