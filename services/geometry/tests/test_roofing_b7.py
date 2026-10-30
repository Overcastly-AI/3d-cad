"""ROOFING acceptance: B7 sided and roofed in asphalt shingles, on STEP.

``goldens/b7-roofing`` is ``b7-siding`` (B7 drawn today, sided in Lap) with
``loft.roof`` 1.9.0's Roofing picked: Asphalt shingles, 10 % waste.
``model.json``, ``members.json`` and ``fixtures/roofing-cases.json.gz`` are
pinned to the plugins by ``packages/loft-plugins/tests/test_roofing.py``.
Geometry never learns plugins exist, so this module imports nothing from
them.

Checked against ``test_siding_b7.script`` (B7 and its finish, from the
independent scripts B7 was accepted on) and the roofing typed here from
``docs/reference-parts/buildings.md``, sharing no code with the plugins:

1. the STEP's 361 solids are the script's 329, the end walls' 4 corner
   boards and the 2 gables' lap cut to the rake boards, and the roofing's
   32, solid for solid: per plane 3 courses (48, 48 and the 25.5862 rip,
   square to the 6/12 plane on the rafters' top plane from the fascia's
   face Y -12.75 to the ridge line) of 4 sheets jointed on rafter centres
   (X 72, 168, 264; the odd course 24, 120, 216), X -7/16 .. 288 7/16; a
   1x10 fascia on each eave's tails jointed at X 144; four 1x6 rake boards
   on the gable OSB's face;
2. interference none, every pair probed exactly;
3. the cut list: the deck 70 246.42 in² on 21 4x8 sheets, 17 bundles
   (4.8782 squares x 1.10 x 3 = 16.10), 1 roll, drip edge 1 064.09 in in 14
   sticks (3 an eave, 2 a rake), starter 49 ft (48.15), ridge cap 25 ft
   (24.07); fascia 4 pieces of 144.4375 on 4 14 ft sticks; rake boards 4 on
   12 ft; casing nested into 14 8 ft sticks (not 23); the 12 gable OSB
   panels on 4 4x8 sheets (not 6); every line priced;
4. 8/12 (75 512.64 in², 18 bundles), 28 ft, vinyl, unsided, unsheathed,
   no gable ends and a house turned off the origin build with no
   interference.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_roofing_b7.py``.
"""

import gzip
import itertools
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import CutListMember, cut_list_response, part_pieces
from loft_wire.features import EvaluateTreeRequest
from loft_wire.price_book import PriceBookResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_outline_b7 as b7
import test_siding_b7 as sided

NAME = "b7-roofing"
IN = b7.IN
GOLDENS = b7.GOLDENS
CASES = Path(__file__).resolve().parent / "fixtures" / "roofing-cases.json.gz"
FC, OSB_M = "fibre_cement", b7.OSB_M

# --- The roofing, typed from buildings.md (inches) -----------------------------------

PLATE = b7.PLATE  # 108.59375
S = 7 / 16  # the OSB, the deck's and the gables'
W = 192.0
COS, SIN = 2 / math.sqrt(5), 1 / math.sqrt(5)  # 6/12
PLUMB = 7.25 * math.sqrt(1.25)  # the 2x8's plumb cut, 8.106: a 1x10 fascia
EAVE = -12.75  # the fascia's face: 12 in of overhang and 3/4 in of fascia
SLOPE = 108.75 / COS  # 121.5862 up each plane
RAKE_W, TRIM_T = 5.5, 0.75  # 1x6 rake boards, 1x fascia and rakes
FASCIA_W = 9.25


def top(y: float) -> float:
    """The rafters' top plane over Y (front): the plate less the heel 29/12."""
    return PLATE - 7.25 / 3 + y / 2 + PLUMB


def rake_bottom(y: float) -> float:
    """A front rake board's underside: the deck's top plane less 5.5 / cos."""
    return top(y) + (S - RAKE_W) / COS


def mirror(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(W - y, z) for y, z in points]


def course(s0: float, s1: float) -> list[tuple[float, float]]:
    """A front course's section: square to the plane, on its top plane."""
    z0 = top(EAVE)
    return [
        (EAVE + s * COS - n * SIN, z0 + s * SIN + n * COS)
        for s, n in ((s0, 0.0), (s1, 0.0), (s1, S), (s0, S))
    ]


COURSES = [(0.0, 48.0), (48.0, 96.0), (96.0, SLOPE)]
JOINTS = ([-S, 72.0, 168.0, 264.0, 288 + S], [-S, 24.0, 120.0, 216.0, 288 + S])
FASCIA = [
    (EAVE, top(EAVE) - FASCIA_W),
    (-12.0, top(EAVE) - FASCIA_W),
    (-12.0, top(EAVE)),
    (EAVE, top(EAVE)),
]
RAKE = [
    (EAVE, rake_bottom(EAVE)),
    (96.0, rake_bottom(96.0)),
    (96.0, rake_bottom(96.0) + RAKE_W / COS),
    (EAVE, rake_bottom(EAVE) + RAKE_W / COS),
]


def rake_solids() -> list[b7.Member]:
    out: list[b7.Member] = []
    for x0 in (-S - TRIM_T, 288 + S):
        for side in (RAKE, mirror(RAKE)):
            out.append(b7.Member("Rake board", FC, b7.prism_x(side, x0, x0 + TRIM_T)))
    return out


def roofing_members() -> list[b7.Member]:
    out: list[b7.Member] = []
    for back in (False, True):
        for k, (s0, s1) in enumerate(COURSES):
            section = course(s0, s1)
            if back:
                section = mirror(section)
            for a0, a1 in itertools.pairwise(JOINTS[k % 2]):
                out.append(b7.Member("Roof deck", OSB_M, b7.prism_x(section, a0, a1)))
    for side in (FASCIA, mirror(FASCIA)):
        for a0, a1 in ((-S, 144.0), (144.0, 288 + S)):
            out.append(b7.Member("Fascia", FC, b7.prism_x(side, a0, a1)))
    return [*out, *rake_solids()]


def script() -> list[b7.Member]:
    """test_siding_b7's B7, its end walls' corner boards and the gables' lap
    cut to the rake boards over them, then the roofing."""
    rakes = [m.solid for m in rake_solids()]
    out: list[b7.Member] = []
    for m in sided.script():
        solid = m.solid
        if m.member in ("Corner board", "Siding"):
            for rake in rakes:
                if solid.bounding_box().overlaps(rake.bounding_box()):  # pyright: ignore[reportUnknownMemberType]
                    cut = solid.cut(rake).solids()[0]  # pyright: ignore[reportUnknownMemberType]
                    if (
                        float(measure_shape(cut).volume)
                        < float(measure_shape(solid).volume) - 1e-6
                    ):
                        solid = cut
        out.append(b7.Member(m.member, m.material, solid))
    return [*out, *roofing_members()]


#: Where a rake board's underside crosses the plate (front plane): Y -0.0582.
Y_PLATE = 2 * (PLATE - top(0.0) - (S - RAKE_W) / COS)


def roofing_volume() -> float:
    """The deck, fascia and rake boards, less what the rakes cut from the
    4 end-wall corner boards (a triangle 3/4 deep under each) and the
    gables' lap (5/16, under each rake from Y -7/16 to the ridge)."""
    deck = 2 * SLOPE * 288.875 * S
    fascia = 2 * 288.875 * TRIM_T * FASCIA_W
    rakes = 4 * 108.75 * RAKE_W / COS * TRIM_T
    corner = 0.5 * (PLATE - rake_bottom(-S - 1)) * (Y_PLATE + S + 1) * TRIM_T
    band = (RAKE_W - S) / COS
    lap = (Y_PLATE + S) * ((top(-S) + top(Y_PLATE)) / 2 - PLATE) + band * (
        96.0 - Y_PLATE
    )
    return deck + fascia + rakes - 4 * corner - 4 * lap * sided.T


def house_volume() -> float:
    return sided.house_volume() + roofing_volume()


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, NAME)  # pyright: ignore[reportPrivateUsage]


# --- 1. The numbers and the STEP ---------------------------------------------------


def test_the_roofing_numbers_are_buildings_mds() -> None:
    assert pytest.approx(8.1059, abs=1e-4) == PLUMB and PLUMB > 7.25  # 1x10
    assert pytest.approx(121.5862, abs=1e-4) == SLOPE
    assert pytest.approx(70246.42, abs=5e-3) == 2 * SLOPE * 288.875
    assert top(EAVE) == pytest.approx(107.9079, abs=1e-4)
    assert pytest.approx(-0.0582, abs=1e-4) == Y_PLATE
    mine = roofing_members()
    assert len(mine) == 24 + 4 + 4
    volume = sum(float(measure_shape(m.solid).volume) for m in mine) / IN**3
    deck_fascia_rakes = (
        2 * SLOPE * 288.875 * S
        + 2 * 288.875 * TRIM_T * FASCIA_W
        + 4 * 108.75 * RAKE_W / COS * TRIM_T
    )
    assert volume == pytest.approx(deck_fascia_rakes, abs=1e-6)
    cut = sum(float(measure_shape(m.solid).volume) for m in script()) / IN**3
    assert cut == pytest.approx(house_volume(), abs=1e-5)


def test_the_step_is_the_script(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 329 + 32
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(house_volume(), abs=1e-4)


# --- 2. Interference none ---------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


# --- 3. The cut list --------------------------------------------------------------

#: b7-siding's book, and the roofing: a 4x8 of 7/16 OSB $21.98, a bundle of
#: architectural shingles $39.98, a 10-square roll $159.00, a 10 ft drip edge
#: $8.98, starter and ridge cap $2.75 and $3.25 a foot, fibre-cement 1x10 at
#: 14 ft $36.98 and 1x6 at 12 ft $21.98.
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            *(e.model_dump(mode="json") for e in sided.BOOK.entries),
            *(
                {"material": m, "profile": p, "unit": u, **stock, "price_cents": c}
                for m, p, u, stock, c in [
                    ("asphalt_shingle", "shingle_architectural", "each", {}, 3998),
                    ("polypropylene", "underlayment_synthetic", "each", {}, 15900),
                    (
                        "aluminium_3105",
                        "drip_edge",
                        "each",
                        {"stock_length_ft": 10},
                        898,
                    ),
                    ("asphalt_shingle", "shingle_starter", "linear_foot", {}, 275),
                    ("asphalt_shingle", "ridge_cap", "linear_foot", {}, 325),
                    (FC, "us_1x10", "each", {"stock_length_ft": 14}, 3698),
                    (FC, "us_1x6", "each", {"stock_length_ft": 12}, 2198),
                ]
            ),
        ],
    }
)


def _cut_list() -> Any:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(b7._extents(request), members, request.materials),  # pyright: ignore[reportPrivateUsage]
        price_book=BOOK,
    )


@pytest.fixture(scope="module")
def cut_list() -> Any:
    return _cut_list()


def _line(cut_list: Any, member: str) -> Any:
    (line,) = [x for x in cut_list.lines if x.member == member]
    return line


def test_the_deck_is_21_sheets_of_its_measured_area(cut_list: Any) -> None:
    """24 panels, 70 246.42 in², on 21 4x8 sheets under Roof: largest first,
    8 full sheets, the 4 rips 25.59 wide, the 4 72.44 x 48 ends and the
    offcuts' leavings (the PM's 20 laid its sheets from the rake, so their
    joints missed the rafters' centres by 7/16 in)."""
    deck = _line(cut_list, "Roof deck")
    assert (deck.system, deck.profile, deck.sheet) == ("roof", "7/16 OSB", "4x8")
    assert deck.quantity == 24
    assert (deck.area_mm2 or 0) / IN**2 == pytest.approx(2 * SLOPE * 288.875, abs=1e-4)
    assert deck.stock_quantity == 21
    assert deck.extended_price_cents == 21 * 2198


def test_shingles_underlayment_drip_edge_starter_and_ridge_cap(cut_list: Any) -> None:
    area = 2 * SLOPE * 288.875
    assert area / 14400 == pytest.approx(4.8782, abs=1e-4)
    shingles = _line(cut_list, "Shingles")
    assert (shingles.stock_quantity, shingles.quantity, shingles.waste_percent) == (
        17,
        17,
        10,
    )
    assert area * 1.10 * 3 / 14400 == pytest.approx(16.10, abs=5e-3)
    assert (shingles.area_mm2 or 0) / IN**2 == pytest.approx(area, abs=1e-4)
    assert shingles.extended_price_cents == 17 * 3998
    assert _line(cut_list, "Underlayment").stock_quantity == 1
    drip = _line(cut_list, "Drip edge")
    assert drip.quantity == 6 and drip.stock_quantity == 2 * 3 + 4 * 2
    assert drip.total_length_mm / IN == pytest.approx(2 * 288.875 + 4 * SLOPE, abs=1e-6)
    assert round(drip.total_length_mm / IN, 2) == 1064.09
    starter, ridge = _line(cut_list, "Starter"), _line(cut_list, "Ridge cap")
    assert round(starter.total_length_mm / IN / 12, 2) == 48.15
    assert round(ridge.total_length_mm / IN / 12, 2) == 24.07
    assert (starter.stock_quantity, ridge.stock_quantity) == (49, 25)
    assert ridge.extended_price_cents == 25 * 325


def test_the_trim_is_nested_on_stock(cut_list: Any) -> None:
    """Fascia 4 x 144.4375 on 14 ft; rake boards 4 x 124.34 on 12 ft; the
    casing's 23 pieces, 1 099.5 in, first fit on 8 ft sticks: 14, not 23;
    the corner boards 8 on 10 ft."""
    fascia = _line(cut_list, "Fascia")
    assert (fascia.profile, fascia.material, fascia.nested) == ("1x10", FC, True)
    assert [round(c / IN, 6) for c in fascia.cuts_mm] == [144.4375] * 4
    assert (fascia.stock_length_ft, fascia.stock_quantity) == (14, 4)
    rake = _line(cut_list, "Rake board")
    assert (rake.profile, rake.stock_length_ft, rake.stock_quantity) == ("1x6", 12, 4)
    # Long point to long point: the plumb cuts' 108.75 in plan on the slope
    # plus the board's depth over the pitch.
    assert rake.length_mm / IN == pytest.approx(SLOPE + RAKE_W * 0.5, abs=1e-6)
    casing = _line(cut_list, "Casing")
    assert casing.quantity == 23 and casing.total_length_mm / IN == 1099.5
    assert (casing.stock_length_ft, casing.stock_quantity) == (8, 14)
    assert casing.extended_price_cents == 14 * 1198
    boards = _line(cut_list, "Corner board")
    assert (boards.stock_length_ft, boards.stock_quantity) == (10, 8)


def test_the_gable_osb_nests_on_4_sheets(cut_list: Any) -> None:
    """GABLE-SHEET-NESTING: each gable panel measured by its plan rectangle
    (its bottom and plumb sides), so the 12 panels nest on 4 4x8 sheets,
    not the 6 their sloped frames took."""
    (osb,) = [
        x
        for x in cut_list.lines
        if x.system == "sheathing" and x.sheet == "4x8" and x.profile == "7/16 OSB"
    ]
    assert (osb.quantity, osb.stock_quantity) == (12, 4)


def test_every_line_is_priced(cut_list: Any) -> None:
    assert cut_list.unpriced_lines == 0
    assert cut_list.unclassified == 0
    assert cut_list.total_price_cents == sum(
        line.extended_price_cents or 0 for line in cut_list.lines
    )


# --- 4. The other cases ------------------------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


#: Each case's roofing: deck panels, fascia pieces, rake boards, rake cuts.
#: 28 ft jointed on 16 ft fascia (X 168); unsided and unsheathed, nothing to
#: cut; turned off the origin, its ridge along Y, 288 long: as B7.
COUNTS = {
    "b7-8-12": (24, 4, 4, 4),
    "b7-336": (24, 4, 4, 4),
    "b7-vinyl": (24, 4, 4, 4),
    "b7-unsided": (24, 4, 4, 0),
    "b7-unsheathed": (24, 4, 4, 0),
    "b7-no-gable-ends": (24, 4, 4, 4),
    "along-y-moved": (24, 4, 4, 4),
}


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_case_roofs_with_no_interference(case: dict[str, Any]) -> None:
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert b7._overlapping(solids) == []  # pyright: ignore[reportPrivateUsage]
    found = (case["deck"], case["fascia"], case["rake_board"], case["rake_cut"])
    assert found == COUNTS[case["name"]]


# --- Mass and expected.json's numbers -----------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * b7.DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def expected_numbers() -> dict[str, Any]:
    return sided.numbers(script(), house_volume())


if __name__ == "__main__":
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
