"""Foundation takeoff (SLAB): concrete by the cubic yard, rebar sticks and
anchor bolts, checked against docs/reference-parts/buildings.md B8, B8's
edits, B2's plain slab and B9's pour, typed by hand.

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
    cut_list_csv,
    cut_list_response,
    part_pieces,
)
from loft_wire.foundation import (
    FOUNDATION_ITEMS,
    AnchorBolts,
    ConcretePour,
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
        # B9's stem and footing: 307 328 -> 6.587; x 1.05 = 6.917, ordered 7.
        (307328, 6.59, Fraction(7)),
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
    for bad in (
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


def test_a_pours_waste_is_its_own_line() -> None:
    """Two pours of one allowance are one line (the order on their sum);
    another allowance is another line."""
    extents, members = _house(288)
    twin = extents.bodies[0].model_copy(update={"base_feature_id": uuid.uuid4()})
    other = members[0].model_copy(
        update={
            "feature_id": twin.base_feature_id,
            "metadata": members[0].metadata.model_copy(
                update={"concrete": ConcretePour(waste_percent=10), "rebar": None}
            ),
        }
    )
    extents = extents.model_copy(update={"bodies": [*extents.bodies, twin]})
    pieces = part_pieces(extents, [*members, other], None)
    cut_list = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B8",
        length_unit="in",
        pieces=pieces,
        price_book=BOOK,
    )
    pours = [line for line in cut_list.lines if line.item == "concrete"]
    assert [(p.waste_percent, p.order_yd3) for p in pours] == [(5, 7.0), (10, 7.5)]
