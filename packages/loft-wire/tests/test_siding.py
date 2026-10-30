"""Siding and trim (SIDING-TRIM): siding bought by its net area plus a
waste allowance in whole boards or squares, its trim as 5/4x4 lumber,
checked by hand against docs/reference-parts/buildings.md B7.

The cut list is built from synthetic measurements (a body's extents and
volume, as geometry measures them): B7's four wall faces of fibre-cement
lap with their cased openings cut out, its two gables, a corner board and a
casing piece. ``services/geometry/tests/test_siding_b7.py`` runs the same on
the kernel's measurements of the ``b7-siding`` golden.
"""

import math
import uuid

import pytest
from loft_wire.cut_list import (
    SYSTEM_LABELS,
    SYSTEM_ORDER,
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import cut_list_csv
from loft_wire.lumber import LUMBER_PROFILES_BY_KEY, stock_lengths_ft
from loft_wire.materials import MATERIALS_BY_KEY
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import PriceBookEntry, PriceBookResponse
from loft_wire.siding import (
    DEFAULT_SIDING_WASTE_PERCENT,
    IN2_PER_SQUARE,
    SIDING_PRODUCTS,
    SIDING_PRODUCTS_BY_KEY,
    TRIM_PROFILE,
    SidingTakeoff,
    siding_order,
    siding_product_for,
)
from pydantic import ValidationError

IN = 25.4
LAP = SIDING_PRODUCTS_BY_KEY["fibre_cement_lap_8_25"]
VINYL = SIDING_PRODUCTS_BY_KEY["vinyl_d4"]
CEDAR = SIDING_PRODUCTS_BY_KEY["cedar_bevel_1_2x8"]


# --- The catalogue ------------------------------------------------------------------


def test_the_catalogue() -> None:
    """Lap: HardiePlank 8.25 x 5/16 at 7 in, 7 x 144 = 1 008 in² a 12 ft
    board; vinyl double 4, 0.044 in, by the 14 400 in² square; cedar 1/2 x 8
    bevel (7-1/4 face, 15/32 butt) at the 1 in lap WRCLA asks, 6.25 x 144 =
    900 in² a 12 ft board."""
    assert [
        (p.key, p.material, p.thickness_in, p.exposure_in, p.sale, p.coverage_in2)
        for p in SIDING_PRODUCTS
    ] == [
        ("fibre_cement_lap_8_25", "fibre_cement", 0.3125, 7.0, "board", 1008.0),
        ("vinyl_d4", "pvc", 0.044, 8.0, "square", 14400.0),
        ("cedar_bevel_1_2x8", "western_red_cedar", 0.46875, 6.25, "board", 900.0),
    ]
    assert IN2_PER_SQUARE == 100 * 144
    assert CEDAR.width_in - CEDAR.exposure_in == 1.0
    assert all(p.material in MATERIALS_BY_KEY for p in SIDING_PRODUCTS)
    assert all(p.trim_material in MATERIALS_BY_KEY for p in SIDING_PRODUCTS)
    assert [p.trim_material for p in SIDING_PRODUCTS] == [
        "fibre_cement",
        "pvc",
        "western_red_cedar",
    ]
    assert siding_product_for("Fibre-cement lap 8-1/4") is LAP
    assert siding_product_for("vinyl_d4") is VINYL
    assert siding_product_for("7/16 OSB") is None
    trim = LUMBER_PROFILES_BY_KEY[TRIM_PROFILE]
    assert (trim.name, trim.thickness_in, trim.width_in) == ("5/4x4", 1.0, 3.5)
    assert stock_lengths_ft(trim) == (8, 10, 12, 14, 16, 18, 20)
    assert DEFAULT_SIDING_WASTE_PERCENT == 10


def test_the_pms_order_rounds_up_to_whole_boards_and_squares() -> None:
    """buildings.md's arithmetic: 90 898.5 in² x 1.10 / 1 008 = 99.19, 100
    boards; / 14 400 = 6.94, 7 squares."""
    assert pytest.approx(99.19, abs=0.005) == 90898.5 * 1.1 / 1008
    assert siding_order(LAP, 90898.5, 10) == 100
    assert pytest.approx(6.94, abs=0.005) == 90898.5 * 1.1 / 14400
    assert siding_order(VINYL, 90898.5, 10) == 7


def test_an_exact_order_buys_no_extra() -> None:
    assert siding_order(LAP, 100 * 1008 / 1.1, 10) == 100
    assert siding_order(LAP, 1008.0, 0) == 1
    assert siding_order(LAP, 1008.0 + 1e-3, 0) == 2
    assert siding_order(LAP, 0.0, 10) == 0


def test_the_allowance_is_bounded() -> None:
    SidingTakeoff(product="vinyl_d4", waste_percent=30)
    with pytest.raises(ValidationError):
        SidingTakeoff(product="vinyl_d4", waste_percent=31)
    with pytest.raises(ValidationError):
        SidingTakeoff.model_validate({"product": "aluminium", "waste_percent": 10})


# --- B7's siding, by hand ------------------------------------------------------------

#: The envelope at the OSB's face: 288 7/8 by 192 7/8. Each outside corner
#: is two 5/4x4 boards, the fitted (side) wall's lapping the through
#: wall's edge, so the front and back faces lose 3.5 in a corner and the
#: sides 2.5: the siding runs 281.875 along the front and back and 187.875
#: along the sides, 939.5 in all, from the foundation top (Z 0) to the top
#: plate (108.59375).
FRONT, SIDE, HEIGHT = 288.875 - 7.0, 192.875 - 5.0, 108.59375
#: Cased openings (unit + 3.5 each way; a door's frame, 37.5 x 82, on its
#: sill): 3040 43 x 55, 2030 31 x 43, the 3068's frame 44.5 x 85.5.
CASED = {"3040": 43 * 55, "2030": 31 * 43, "3068": 44.5 * 85.5}
#: A rafter tail's notch in the 5/16 lap (6/12, the heel at 29/6 from the
#: framing's face): over the layer, 7/16 .. 3/4 out, the tail's underside is
#: 1/2 (29/6 + w) under the plate, 1.5 wide: its volume over the layer's
#: thickness, as the measured area reads it.
SEAT, S, T = 29 / 6, 7 / 16, 5 / 16


def notch_area(t: float = T) -> float:
    volume = 1.5 * 0.5 * (SEAT * t + ((S + t) ** 2 - S**2) / 2)
    return volume / t


def test_b7s_siding_by_hand() -> None:
    """939.5 x 108.59375 = 102 023.828125 gross, less the cased openings
    3 x 2 365 + 2 x 1 333 + 3 804.75 = 13 565.75 and the 22 tails' notches
    (11 a wall over the siding; the end rafters notch the corner boards):
    88 368.53125 in²; with the gables' 2 x 5 705.185554 (the siding over
    the gable OSB, Y -7/16 .. 192 7/16 up to the rafters' top plane) 99
    778.902 in², x 1.10 / 1 008 = 108.89: 109 boards."""
    assert 2 * FRONT + 2 * SIDE == 939.5
    gross = 939.5 * HEIGHT
    assert gross == 102023.828125
    cased = 3 * CASED["3040"] + 2 * CASED["2030"] + CASED["3068"]
    assert cased == 13565.75
    assert notch_area() == pytest.approx(4.0703125, abs=1e-12)
    walls = gross - cased - 22 * notch_area()
    assert walls == pytest.approx(88368.53125, abs=1e-9)
    gables = 2 * 5705.185554
    assert (walls + gables) * 1.1 / 1008 == pytest.approx(108.886, abs=1e-3)
    assert siding_order(LAP, walls + gables, 10) == 109
    assert siding_order(LAP, walls, 10) == 97  # the walls alone: 96.43
    assert siding_order(VINYL, walls + gables, 10) == 8  # 7.62
    assert siding_order(CEDAR, walls + gables, 10) == 122  # 121.95


def test_b7s_casing_and_corner_boards_by_hand() -> None:
    """Picture-frame casing, the long points: 3040 2 x 55 + 2 x 43 = 196,
    2030 2 x 43 + 2 x 31 = 148, the door 2 x 85.5 + 44.5 = 215.5: 3 x 196 +
    2 x 148 + 215.5 = 1 099.5 in (the PM's 1 094 cased the door's slab,
    36 x 80, not its 37.5 x 82 frame); 8 corner boards of 108.59375."""
    assert 3 * 196 + 2 * 148 + 215.5 == 1099.5
    assert 2 * 83.5 + 43 == 210 and 3 * 196 + 2 * 148 + 210 == 1094


# --- The cut list --------------------------------------------------------------------

LAP_META = MemberMetadata(
    profile=LAP.name,
    material="fibre_cement",
    siding=SidingTakeoff(product=LAP.key, waste_percent=10),
)
TRIM_META = MemberMetadata(profile="5/4x4", material="fibre_cement")


def _body(
    name: str, extents_in: tuple[float, float, float], area_in2: float
) -> BodyExtent:
    fid = uuid.uuid5(uuid.NAMESPACE_URL, name)
    return BodyExtent(
        base_feature_id=fid,
        extents_mm=(extents_in[0] * IN, extents_in[1] * IN, extents_in[2] * IN),
        volume_mm3=area_in2 * extents_in[2] * IN**3,
    )


def _member(
    body: BodyExtent, role: str, title: str, plugin: str, meta: MemberMetadata
) -> CutListMember:
    return CutListMember(
        feature_id=body.base_feature_id,
        role=role,
        title=title,
        plugin_id=plugin,
        metadata=meta,
    )


def b7_pieces(
    meta: MemberMetadata = LAP_META, t: float = T
) -> tuple[BodyExtentsResult, list[CutListMember]]:
    """B7's four faces and two gables (their areas by hand, above), 8
    corner boards and the door's casing."""
    walls = 88368.53125
    front = (FRONT * HEIGHT - 2 * CASED["3040"] - CASED["3068"]) - 11 * notch_area()
    back = (FRONT * HEIGHT - CASED["3040"]) - 11 * notch_area()
    side = SIDE * HEIGHT - CASED["2030"]
    assert front + back + 2 * side == pytest.approx(walls, abs=1e-9)
    bodies: list[BodyExtent] = []
    members: list[CutListMember] = []
    for k, (area, length) in enumerate(
        ((front, FRONT), (side, SIDE), (back, FRONT), (side, SIDE))
    ):
        body = _body(f"siding/{k}", (length, HEIGHT, t), area)
        bodies.append(body)
        members.append(_member(body, "siding", "Siding", "loft.wall", meta))
    for k in range(2):
        body = _body(f"gable/{k}", (192.875, 53.689079, t), 5705.185554)
        bodies.append(body)
        members.append(_member(body, "gable_siding", "Siding", "loft.roof", meta))
    for k in range(8):
        body = _body(f"corner/{k}", (HEIGHT, 3.5, 1.0), HEIGHT * 3.5)
        bodies.append(body)
        members.append(
            _member(body, "corner_board", "Corner board", "loft.wall", TRIM_META)
        )
    for side_, (length, area) in {
        "head": (44.5, (44.5 + 37.5) / 2 * 3.5),
        "left": (85.5, (85.5 + 82) / 2 * 3.5),
        "right": (85.5, (85.5 + 82) / 2 * 3.5),
    }.items():
        body = _body(f"casing/{side_}", (length, 3.5, 1.0), area)
        bodies.append(body)
        members.append(_member(body, "casing", "Casing", "loft.wall", TRIM_META))
    result = BodyExtentsResult(part_id=uuid.uuid4(), tree_version=1, bodies=bodies)
    return result, members


BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": "fibre_cement",
                "profile": "fibre_cement_lap_8_25",
                "unit": "each",
                "stock_length_ft": 12,
                "price_cents": 1398,
            },
            {
                "material": "pvc",
                "profile": "vinyl_d4",
                "unit": "square",
                "price_cents": 13900,
            },
            {
                "material": "western_red_cedar",
                "profile": "cedar_bevel_1_2x8",
                "unit": "linear_foot",
                "price_cents": 289,
            },
            {
                "material": "fibre_cement",
                "profile": "us_5_4x4",
                "unit": "linear_foot",
                "price_cents": 145,
            },
        ],
    }
)


def _cut_list(meta: MemberMetadata = LAP_META, t: float = T) -> CutListResponse:
    extents, members = b7_pieces(meta, t)
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(extents, members, None),
        price_book=BOOK,
    )


def test_the_siding_is_one_line_of_109_boards_under_siding_and_trim() -> None:
    """The walls' four faces and the roof's two gables, one product, one
    allowance: one line, its net area theirs summed, 109 boards ordered once
    over the total, $13.98 a board."""
    cut_list = _cut_list()
    siding = [line for line in cut_list.lines if line.siding is not None]
    assert len(siding) == 1
    line = siding[0]
    assert (line.system, line.member, line.profile, line.material) == (
        "siding",
        "Siding",
        "Fibre-cement lap 8-1/4",
        "fibre_cement",
    )
    assert line.quantity == 6
    assert (line.area_mm2 or 0.0) / IN**2 == pytest.approx(
        88368.53125 + 2 * 5705.185554, abs=1e-6
    )
    assert (line.stock_quantity, line.stock_length_ft, line.waste_percent) == (
        109,
        12,
        10,
    )
    assert line.length_mm == 144 * IN
    assert line.section_mm == [pytest.approx(T * IN), pytest.approx(8.25 * IN)]
    assert (line.unit_price_cents, line.price_unit, line.extended_price_cents) == (
        1398,
        "each",
        109 * 1398,
    )


def test_the_trim_is_lumber_under_siding_and_trim() -> None:
    """8 corner boards of 108.59375 (10 ft stock), the door's 2 legs of
    85.5 and its 44.5 head (8 ft), priced per foot of stock bought."""
    cut_list = _cut_list()
    trim = [line for line in cut_list.lines if line.siding is None]
    assert [
        (
            line.system,
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in trim
    ] == [
        ("siding", "Corner board", "5/4x4", 8, 108.59375, 10),
        ("siding", "Casing", "5/4x4", 1, 44.5, 8),
        ("siding", "Casing", "5/4x4", 2, 85.5, 8),
    ]
    assert [line.extended_price_cents for line in trim] == [
        8 * 10 * 145,
        8 * 145,
        2 * 8 * 145,
    ]
    assert cut_list.unpriced_lines == 0
    assert cut_list.total_price_cents == 109 * 1398 + 8 * 10 * 145 + 3 * 8 * 145


def test_vinyl_buys_squares_and_cedar_boards_by_the_foot() -> None:
    vinyl = MemberMetadata(
        profile=VINYL.name, material="pvc", siding=SidingTakeoff(product=VINYL.key)
    )
    line = next(x for x in _cut_list(vinyl, VINYL.thickness_in).lines if x.siding)
    # The vinyl's thinner layer under a tail notches a little less.
    assert (line.stock_quantity, line.stock_length_ft, line.length_mm) == (8, None, 0.0)
    assert (line.unit_price_cents, line.price_unit) == (13900, "square")
    assert line.extended_price_cents == 8 * 13900
    cedar = MemberMetadata(
        profile=CEDAR.name,
        material="western_red_cedar",
        siding=SidingTakeoff(product=CEDAR.key, waste_percent=15),
    )
    line = next(x for x in _cut_list(cedar, CEDAR.thickness_in).lines if x.siding)
    area = (line.area_mm2 or 0.0) / IN**2
    assert line.stock_quantity == math.ceil(area * 1.15 / 900)
    assert (line.unit_price_cents, line.price_unit) == (12 * 289, "linear_foot")


def test_two_allowances_are_two_lines() -> None:
    extents, members = b7_pieces()
    eleven = LAP_META.model_copy(
        update={"siding": SidingTakeoff(product=LAP.key, waste_percent=15)}
    )
    members = [
        m.model_copy(update={"metadata": eleven}) if m.role == "gable_siding" else m
        for m in members
    ]
    cut_list = cut_list_response(
        document_id=uuid.uuid4(),
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(extents, members, None),
    )
    lines = [line for line in cut_list.lines if line.siding is not None]
    assert [
        (line.quantity, line.waste_percent, line.stock_quantity) for line in lines
    ] == [
        (4, 10, 97),
        (2, 15, math.ceil(2 * 5705.185554 * 1.15 / 1008)),
    ]
    assert all(line.unit_price_cents is None for line in lines)


def test_siding_and_trim_follow_sheathing() -> None:
    assert SYSTEM_ORDER.index("siding") == SYSTEM_ORDER.index("sheathing") + 1
    assert SYSTEM_LABELS["siding"] == "Siding and trim"


def test_the_csv_writes_the_order() -> None:
    rows = cut_list_csv(_cut_list()).split("\r\n")
    siding = next(r for r in rows if "Fibre-cement lap" in r)
    cells = siding.split(",")
    assert cells[1:4] == ["Siding and trim", "Siding", "Fibre-cement lap 8-1/4"]
    assert cells[6] == "6"
    assert cells[7] == cells[8] == ""  # an area, no length to cut
    assert cells[10] == "12 ft boards + 10% waste"
    assert cells[12:] == ["109", "13.98", "Each", f"{109 * 1398 / 100:.2f}"]


# --- The price book ------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        {
            "material": "fibre_cement",
            "profile": "fibre_cement_lap_8_25",
            "unit": "each",
            "stock_length_ft": 12,
        },
        {
            "material": "fibre_cement",
            "profile": "fibre_cement_lap_8_25",
            "unit": "linear_foot",
        },
        {"material": "pvc", "profile": "vinyl_d4", "unit": "square"},
        {
            "material": "western_red_cedar",
            "profile": "cedar_bevel_1_2x8",
            "unit": "each",
            "stock_length_ft": 12,
        },
        {
            "material": "fibre_cement",
            "profile": "us_5_4x4",
            "unit": "each",
            "stock_length_ft": 12,
        },
        {"material": "pvc", "profile": "us_5_4x4", "unit": "linear_foot"},
    ],
)
def test_a_siding_price_is_taken(entry: dict[str, object]) -> None:
    PriceBookEntry.model_validate({**entry, "price_cents": 100})


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        (
            {
                "material": "fibre_cement",
                "profile": "fibre_cement_lap_8_25",
                "unit": "each",
                "stock_length_ft": 16,
            },
            "per 12 ft board",
        ),
        (
            {
                "material": "fibre_cement",
                "profile": "fibre_cement_lap_8_25",
                "unit": "square",
            },
            "per 12 ft board",
        ),
        (
            {
                "material": "pvc",
                "profile": "fibre_cement_lap_8_25",
                "unit": "each",
                "stock_length_ft": 12,
            },
            "is fibre_cement",
        ),
        ({"material": "pvc", "profile": "vinyl_d4", "unit": "each"}, "per square"),
        (
            {
                "material": "pvc",
                "profile": "vinyl_d4",
                "unit": "square",
                "sheet": "4x8",
            },
            "no sheet",
        ),
        ({"material": "osb", "profile": "osb_7_16", "unit": "square"}, "Only vinyl"),
        (
            {"material": "spf_lumber", "profile": "us_2x4", "unit": "square"},
            "Only vinyl",
        ),
    ],
)
def test_a_wrong_siding_price_is_refused(entry: dict[str, object], why: str) -> None:
    with pytest.raises(ValidationError, match=why):
        PriceBookEntry.model_validate({**entry, "price_cents": 100})
