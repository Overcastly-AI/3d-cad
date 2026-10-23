"""SHEATHING acceptance: B5's floor with its subfloor and B2's walls in 7/16
OSB, with the door and window, standing on it, on STEP.

``goldens/b5-shed-sheathed`` is one ``loft.floor`` 1.1.0 and four
``loft.wall`` 1.2.0 expansions, pinned to the plugins by
``packages/loft-plugins/tests/test_sheathing.py``. The BACKLOG asks, each
checked here against numbers typed from the spec by hand:

1. the cut list buys the sheets the panels are cut from
   (SHEET-COUNT-PIECES): OSB 12 panels and 4 corner rips lapping the side
   walls past the front and back walls' ends (3.9375 x 97.125),
   47 422.71875 in^2, 12 sheets of 4x9 (the walls are 97.125 tall; 10 by
   area); plywood 6 panels, 17 280 in^2, 4 sheets of 4x8; at $24.98 a 4x9
   OSB sheet and $42.50 a 4x8 plywood sheet the lines extend to $299.76 and
   $170.00;
2. the exported STEP's solids are, solid for solid, an independent build123d
   script of the spec's members (panels as boxes less the rough openings),
   the OSB summing to 20 747.439453125 in^3 and the subfloor to 12 420 to
   1e-4;
3. interference none: no panel shares volume with the framing or another
   panel, and no panel enters a rough opening.
"""

import gzip
import itertools
import json
import math
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Pos,
    Solid,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import (
    cut_list_csv,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.price_book import PriceBookResponse

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b5-shed-sheathed"
IN = 25.4
T_OSB, T_PLY = 7 / 16, 23 / 32
BASE = 8.75 + T_PLY  # the walls stand on the subfloor: 9.46875
TOP = BASE + 97.125
SPF, PT = "spf_lumber", "southern_pine_pt"

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1


def _request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / NAME / "model.json").read_text()
    )


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return BodyExtentsResult.model_validate_json(response.content)


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request().model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path_factory.mktemp("step") / f"{NAME}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


# --- The spec's members, typed by hand ----------------------------------------------

S = 0.75
LONG = [S, *(16.0 * n for n in range(1, 9)), 143.25]  # a 144 wall's layout
SHORT = [S, *(16.0 * n for n in range(1, 7)), 112.25]  # a 113 wall's
STUDS = (1.5, 94.125)
PLATES = [(0.0, 1.5), (94.125, 95.625), (95.625, 97.125)]


def spec_floor() -> list[Bounds]:
    """buildings.md B5's floor (test_floor_b5's typing) and its subfloor:
    4x8 across the joists from X 0, rows of 48 along Y, staggered 4 ft."""
    centres = [S, *(16.0 * n for n in range(1, 9)), 143.25]
    floor: list[Bounds] = [
        (0, 144, 0, 5.5, 0, 1.5),
        (0, 144, 114.5, 120, 0, 1.5),
        (0, 5.5, 5.5, 114.5, 0, 1.5),
        (138.5, 144, 5.5, 114.5, 0, 1.5),
        (0, 144, 0, 1.5, 1.5, 8.75),
        (0, 144, 118.5, 120, 1.5, 8.75),
        *((c - S, c + S, 1.5, 118.5, 1.5, 8.75) for c in centres),
    ]
    subfloor: list[Bounds] = [
        (x0, x1, y0, y1, 8.75, BASE)
        for x0, x1, y0, y1 in [
            (0, 96, 0, 48),
            (96, 144, 0, 48),
            (0, 48, 48, 96),
            (48, 144, 48, 96),
            (0, 96, 96, 120),
            (96, 144, 96, 120),
        ]
    ]
    return floor + subfloor


def spec_framing() -> list[Bounds]:
    """buildings.md B2's framing with its door (front, X 53..91) and window
    (right side, Y 47.75..72.25, Z 46..82.5), on BASE."""
    out: list[Bounds] = []
    fy = (0.0, 3.5)
    out += [(x - S, x + S, *fy, *STUDS) for x in LONG if not 50 < x < 94]
    out += [
        (50, 51.5, *fy, *STUDS),
        (92.5, 94, *fy, *STUDS),
        (51.5, 53, *fy, 1.5, 82.5),
        (91, 92.5, *fy, 1.5, 82.5),
        (51.5, 92.5, 0, 1.5, 82.5, 88),
        (51.5, 92.5, 2, 3.5, 82.5, 88),
        (63.25, 64.75, *fy, 88, 94.125),
        (79.25, 80.75, *fy, 88, 94.125),
        (0, 144, *fy, *PLATES[1]),
        (0, 144, *fy, *PLATES[2]),
        (0, 53, *fy, *PLATES[0]),
        (91, 144, *fy, *PLATES[0]),
    ]
    by = (116.5, 120.0)
    out += [(x - S, x + S, *by, *STUDS) for x in LONG]
    out += [(0, 144, *by, *z) for z in PLATES]
    lx = (0.0, 3.5)
    out += [(*lx, 3.5 + u - S, 3.5 + u + S, *STUDS) for u in SHORT]
    out += [(*lx, 3.5, 116.5, *z) for z in PLATES]
    rx = (140.5, 144.0)

    def y(u0: float, u1: float) -> tuple[float, float]:
        return (116.5 - u1, 116.5 - u0)

    out += [(*rx, *y(u - S, u + S), *STUDS) for u in SHORT if not 41 < u < 72]
    out += [
        (*rx, *y(41.25, 42.75), *STUDS),
        (*rx, *y(70.25, 71.75), *STUDS),
        (*rx, *y(42.75, 44.25), 1.5, 82.5),
        (*rx, *y(68.75, 70.25), 1.5, 82.5),
        (140.5, 142, *y(42.75, 70.25), 82.5, 88),
        (142.5, 144, *y(42.75, 70.25), 82.5, 88),
        (*rx, *y(47.25, 48.75), 88, 94.125),
        (*rx, *y(63.25, 64.75), 88, 94.125),
        (*rx, *y(44.25, 68.75), 44.5, 46),
        (*rx, *y(47.25, 48.75), 1.5, 44.5),
        (*rx, *y(63.25, 64.75), 1.5, 44.5),
    ]
    out += [(*rx, 3.5, 116.5, *z) for z in PLATES]
    return [(*b[:4], b[4] + BASE, b[5] + BASE) for b in out]


#: The rough openings in the OSB's planes (in): the door's and the window's.
DOOR: Bounds = (53, 91, -T_OSB, 0, BASE, BASE + 82.5)
WINDOW: Bounds = (144, 144 + T_OSB, 47.75, 72.25, BASE + 46, BASE + 82.5)
#: The same openings grown 1 in either side through the panel's thickness,
#: so the script's cut is not coplanar with the panel's faces.
DOOR_CUT: Bounds = (53, 91, -1 - T_OSB, 1, BASE, BASE + 82.5)
WINDOW_CUT: Bounds = (143, 145 + T_OSB, 47.75, 72.25, BASE + 46, BASE + 82.5)

#: Each OSB panel: its box and the rough opening cut from it, if any. 48 in
#: from each wall's start (front from X 144 going -X, left from Y 3.5 going
#: +Y, back from X 0, right from Y 116.5 going -Y), outside its face.
PANELS: list[tuple[Bounds, Bounds | None]] = [
    ((96, 144, -T_OSB, 0, BASE, TOP), None),
    ((48, 96, -T_OSB, 0, BASE, TOP), DOOR_CUT),
    ((0, 48, -T_OSB, 0, BASE, TOP), None),
    ((-T_OSB, 0, 3.5, 51.5, BASE, TOP), None),
    ((-T_OSB, 0, 51.5, 99.5, BASE, TOP), None),
    ((-T_OSB, 0, 99.5, 116.5, BASE, TOP), None),
    ((0, 48, 120, 120 + T_OSB, BASE, TOP), None),
    ((48, 96, 120, 120 + T_OSB, BASE, TOP), None),
    ((96, 144, 120, 120 + T_OSB, BASE, TOP), None),
    ((144, 144 + T_OSB, 68.5, 116.5, BASE, TOP), WINDOW_CUT),
    ((144, 144 + T_OSB, 20.5, 68.5, BASE, TOP), WINDOW_CUT),
    ((144, 144 + T_OSB, 3.5, 20.5, BASE, TOP), None),
    # Corner rips: each side wall's plane laps over the front and back walls'
    # end grain and OSB edge, 3.5 + 7/16 wide (WALL-SHEATHING-CORNER).
    ((-T_OSB, 0, -T_OSB, 3.5, BASE, TOP), None),
    ((-T_OSB, 0, 116.5, 120 + T_OSB, BASE, TOP), None),
    ((144, 144 + T_OSB, 116.5, 120 + T_OSB, BASE, TOP), None),
    ((144, 144 + T_OSB, -T_OSB, 3.5, BASE, TOP), None),
]


def _box(b: Bounds) -> Solid:
    x0, x1, y0, y1, z0, z1 = b
    return (
        Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, (z0 + z1) / 2 * IN)
        * Box((x1 - x0) * IN, (y1 - y0) * IN, (z1 - z0) * IN)
    ).solid()


def _script() -> list[Solid]:
    """The independent script: each member a build123d Box, each notched
    panel a Box less its rough opening's Box (no Loft code)."""
    solids = [_box(b) for b in spec_floor() + spec_framing()]
    for panel, cut in PANELS:
        solid = _box(panel)
        if cut is not None:
            solid = (solid - _box(cut)).solid()  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        solids.append(solid)
    return solids


def _signature(solid: Solid) -> tuple[float, ...]:
    box = solid.bounding_box()
    values = (box.min.X, box.max.X, box.min.Y, box.max.Y, box.min.Z, box.max.Z)
    volume = float(measure_shape(solid).volume) / IN**3
    return (round(volume, 6), *(round(v / IN, 6) + 0.0 for v in values))


# --- 1. The cut list and its prices -----------------------------------------------


def _book(*entries: tuple[str, str, str, int]) -> PriceBookResponse:
    return PriceBookResponse.model_validate(
        {
            "currency": "USD",
            "entries": [
                {
                    "material": material,
                    "profile": profile,
                    "unit": "each",
                    "sheet": sheet,
                    "price_cents": cents,
                }
                for material, profile, sheet, cents in entries
            ],
        }
    )


SHEET_BOOK = _book(
    ("osb", "osb_7_16", "4x9", 2498), ("plywood", "plywood_23_32", "4x8", 4250)
)


def test_the_cut_list_buys_the_sheets_the_panels_are_cut_from() -> None:
    request = _request()
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B5",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(), request.materials),
        price_book=SHEET_BOOK,
    )
    sheets = [line for line in cut_list.lines if line.sheet is not None]
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            line.sheet,
            round((line.area_mm2 or 0) / IN**2, 6),
            line.stock_quantity,
            round((line.offcut_area_mm2 or 0) / IN**2, 6),
            line.unit_price_cents,
            line.extended_price_cents,
        )
        for line in sheets
    ]
    assert rows == [
        ("Subfloor", "23/32 plywood", "plywood", 6, "4x8", 17280, 4, 1152, 4250, 17000),
        (
            "Sheathing",
            "7/16 OSB",
            "osb",
            16,
            "4x9",
            47422.71875,
            12,
            14785.28125,
            2498,
            29976,
        ),
    ]
    # By hand, a 1/8 in kerf at each cut, and a piece up to 1/8 in short
    # filling its panel in APA's panel gap (SHEET-KERF-GAP). Plywood: two
    # 96 x 48 whole; the 96 x 24 takes a third sheet and the 48 x 24 comes
    # from its 23.875 rip; a 48 x 48 takes the fourth and the other is its
    # 47.875 end. OSB: the 10 panels 48 wide (openings are cut out of whole
    # panels) take 10; the first 17 an 11th, the second 17 its 30.875 in
    # rip, which then holds three 3.9375 rips (13.75 - 3 x 4.0625 = 1.5625);
    # the fourth rip a 12th. By area it was 10 (47 422.71875 / 5 184 = 9.15).
    assert math.ceil(47422.71875 / (48 * 108)) == 10
    assert 4 * 48 * 96 - 17280 == 1152 and 12 * 48 * 108 - 47422.71875 == 14785.28125
    assert 4 * 4250 == 17000 and 12 * 2498 == 29976
    # The framing's lines are B5's floor and B2's door-and-window walls.
    lumber = Counter(
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 6))
        for line in cut_list.lines
        if line.sheet is None
    )
    assert sum(q for (_, _, q, _) in lumber.elements()) == 16 + 64
    assert cut_list.unclassified == 0
    assert cut_list.unpriced_lines == len(cut_list.lines) - 2
    assert cut_list.total_price_cents == 17000 + 29976


def test_the_csv_shows_the_area_and_the_sheet() -> None:
    request = _request()
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B5",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(), request.materials),
        price_book=SHEET_BOOK,
    )
    rows = cut_list_csv(cut_list).split("\r\n")
    plywood = next(r for r in rows if "23/32 plywood" in r)
    osb = next(r for r in rows if "7/16 OSB" in r)
    assert plywood.endswith(",6,,,17280,4x8 sheet,,4,42.50,Each,170.00")
    assert osb.endswith(",16,,,47422.7188,4x9 sheet,,12,24.98,Each,299.76")


# --- 2. The STEP against the spec and an independent script -------------------------


def test_the_spec_is_the_backlogs_arithmetic() -> None:
    """The hand-typed panels in exact rationals: 16 panels (4 of them corner
    rips), 47 422.71875 in^2, 20 747.439453125 in^3; the subfloor 12 420."""
    t = Fraction(7, 16)
    area = Fraction(0)
    for panel, cut in PANELS:
        x0, x1, y0, y1, z0, z1 = (Fraction(v) for v in panel)
        face = (max(x1 - x0, y1 - y0)) * (z1 - z0)
        if cut is not None:
            cx0, cx1, cy0, cy1, cz0, cz1 = (Fraction(v) for v in cut)
            lo = max(cx0, x0) if x1 - x0 > y1 - y0 else max(cy0, y0)
            hi = min(cx1, x1) if x1 - x0 > y1 - y0 else min(cy1, y1)
            face -= (hi - lo) * (cz1 - cz0)
        area += face
    assert len(PANELS) == 16
    assert area == 45893 + 4 * Fraction(63, 16) * Fraction(777, 8) == 47422.71875
    assert area * t == Fraction(10622689, 512) == 20747.439453125
    sub = [b for b in spec_floor() if b[4] == 8.75]
    assert len(sub) == 6
    plywood = sum(
        Fraction(b[1] - b[0]) * Fraction(b[3] - b[2]) * Fraction(23, 32) for b in sub
    )
    assert plywood == 12420


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    script = _script()
    assert len(step_solids) == len(script) == 16 + 6 + 64 + 16
    assert Counter(_signature(s) for s in step_solids) == Counter(
        _signature(s) for s in script
    )
    osb = [s for s in step_solids if _is_osb(s)]
    assert len(osb) == 16
    volume = sum(float(measure_shape(s).volume) for s in osb) / IN**3
    assert volume == pytest.approx(20747.439453125, abs=1e-4)
    plywood = [s for s in step_solids if _is_plywood(s)]
    assert len(plywood) == 6
    volume = sum(float(measure_shape(s).volume) for s in plywood) / IN**3
    assert volume == pytest.approx(12420, abs=1e-4)


def _thickness(solid: Solid) -> float:
    box = solid.bounding_box()
    return min(box.size.X, box.size.Y, box.size.Z) / IN


def _is_osb(solid: Solid) -> bool:
    return abs(_thickness(solid) - T_OSB) < 1e-6


def _is_plywood(solid: Solid) -> bool:
    return abs(_thickness(solid) - T_PLY) < 1e-6


# --- 3. Interference none -----------------------------------------------------------


def _overlapping(solids: Sequence[Solid]) -> list[tuple[int, int, float]]:
    """Pairs whose bounding boxes overlap on all three axes by ANY amount,
    probed exactly; those sharing any volume."""
    boxes = [s.bounding_box() for s in solids]
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            > max(getattr(a.min, k), getattr(b.min, k))
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return bad


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert _overlapping(step_solids) == []


def test_no_panel_enters_a_rough_opening(step_solids: list[Solid]) -> None:
    for solid in step_solids:
        if not _is_osb(solid):
            continue
        for hole in (DOOR, WINDOW):
            probe = probe_overlap(solid, _box(hole))
            assert not probe.unresolved
            assert probe.volume_mm3 == pytest.approx(0.0, abs=1e-6)


# --- Mass ---------------------------------------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    """PT sills and bottom plates, SPF framing, OSB at 641 and plywood at 577."""
    request = _request()
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    pt = 4174.5 + (144 + 2 * 113 + 2 * 53) * 5.25
    total = 20030.25 + 28942.125
    osb, plywood = 20747.439453125, 12420.0
    want = (pt * 582 + (total - pt) * 450 + osb * 641 + plywood * 577) * 1e-6 * IN**3
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- A sweep of turned walls, holes and floors --------------------------------------

SWEEP = Path(__file__).resolve().parent / "fixtures" / "sheathing-sweep.json.gz"


def _sweep() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(SWEEP.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _sweep(), ids=[c["name"] for c in _sweep()])
def test_the_sweep_builds_every_panel_touching_only(case: dict[str, Any]) -> None:
    """Turned walls with a door and window across panel joints, a window
    inside a panel (a hole), a left-side wall, turned and width-joisted
    floors: one valid solid per member, the panels' volume the sketches' net
    area times the thickness, and no two solids sharing any volume (a panel
    on a turned wall's face overlaps its studs' boxes, so it is probed)."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    shape = build_model_solid(request)
    solids: list[Solid] = list(shape.solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    # The panels are emitted after the framing: the last solids.
    thin = solids[-case["panels"] :]
    volume = sum(float(measure_shape(s).volume) for s in thin) / IN**3
    assert volume == pytest.approx(case["panel_volume_in3"], abs=1e-4)
    assert _overlapping(solids) == []
