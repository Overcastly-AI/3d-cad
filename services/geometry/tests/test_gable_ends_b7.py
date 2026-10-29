"""GABLE-END-STUDS acceptance: B7's gables framed and sheathed, on STEP.

``goldens/b7-gable-ends`` is ``b7-ceiling-joists``' tree with its roof at
``loft.roof`` 1.7.0, every default kept: gable studs on each end wall's top
plate at its layout, cut to the rafters' underside, and the end walls' OSB
carried up to the rafters' top plane. ``model.json``, ``members.json`` and
``fixtures/gable-end-cases.json.gz`` are pinned to the plugins by
``packages/loft-plugins/tests/test_gable_end_studs.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked against B7's independent script with its ceiling joists
(``test_ceiling_joists_b7.house``) and the gable ends typed here from
``docs/reference-parts/buildings.md``, sharing no code with the plugins:

1. the STEP's 262 solids are the script's 228, 22 studs and 12 panels,
   solid for solid: the left gable's studs X 0..5.5 at Y 21.5 + 16k (the
   left wall lays out from the front), the right's X 282.5..288 at Y 170.5 -
   16k (the right wall from the back), each the (Y, Z) quad from the plate
   (108.59375) to the underside 106.1770833 + min(Y, 192 - Y) / 2; the OSB
   X -7/16..0 and 288..288 7/16 in the walls' columns and corner rips, up
   to the top plane 114.282829 + min(Y, 192 - Y) / 2;
2. interference none, every pair probed exactly: the end rafters bear on
   the studs' cut tops face to face, and the OSB is outside the framing;
3. the cut list: 22 gable studs, 2 of each of 11 lengths (long points
   262.791667 in a gable) under Roof; the gables' 12 OSB panels, 11 410.37
   in^2, cut from 6 sheets of 4x8 by ``sheets_to_cut`` on their measured
   extents (the trapezoids measure along their sloped edges);
4. 28 ft, 8/12, B10, B7 at 291 (a joist left off the end wall), a 171 span
   (a ridge post) and B7 turned off the origin all build with no
   interference.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_gable_ends_b7.py``.
"""

import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest
from loft_wire.sheet_goods import SHEET_SIZES_BY_KEY
from loft_wire.sheet_nesting import sheets_to_cut

sys.path.insert(0, str(Path(__file__).parent))
import itertools

from test_ceiling_joists_b7 import house as joisted
from test_ceiling_joists_b7 import house_volume as joisted_volume
from test_outline_b7 import (
    DENSITY,
    IN,
    OSB_M,
    PLATE,
    SPF,
    Member,
    _overlapping,  # pyright: ignore[reportPrivateUsage]
    _step_solids,  # pyright: ignore[reportPrivateUsage]
    _unmatched,  # pyright: ignore[reportPrivateUsage]
    prism_x,
)

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b7-gable-ends"
CASES = Path(__file__).resolve().parent / "fixtures" / "gable-end-cases.json.gz"

# --- The gable ends, typed from buildings.md (inches) -------------------------------

W = 192.0
D = 5.5  # 2x6 walls
OSB = 7 / 16
HEEL = 7.25 / 3  # the heel held to a third of the 2x8's depth


def underside(y: float, rise: int = 6) -> float:
    return PLATE - HEEL + min(y, W - y) * rise / 12


def top_plane(y: float, rise: int = 6) -> float:
    return underside(y, rise) + 7.25 * math.hypot(12, rise) / 12


LEFT = [21.5 + 16 * k for k in range(11)]
RIGHT = [170.5 - 16 * k for k in range(11)]
LEFT_COLUMNS = [-OSB, 5.5, 53.5, 101.5, 149.5, 186.5, W + OSB]
RIGHT_COLUMNS = [-OSB, 5.5, 42.5, 90.5, 138.5, 186.5, W + OSB]


def stud_side(c: float) -> list[tuple[float, float]]:
    y0, y1 = c - 0.75, c + 0.75
    return [(y0, PLATE), (y1, PLATE), (y1, underside(y1)), (y0, underside(y0))]


def panel_side(y0: float, y1: float) -> list[tuple[float, float]]:
    points = [(y0, PLATE), (y1, PLATE), (y1, top_plane(y1))]
    if y0 < W / 2 < y1:
        points.append((W / 2, top_plane(W / 2)))
    return [*points, (y0, top_plane(y0))]


def long_point(c: float) -> float:
    return min(c + 0.75, W - c + 0.75) / 2 - HEEL


def gable_members(length: float = 288.0) -> list[Member]:
    out: list[Member] = []
    for x0, centres, cuts, ox in (
        (0.0, LEFT, LEFT_COLUMNS, -OSB),
        (length - D, RIGHT, RIGHT_COLUMNS, length),
    ):
        out += [
            Member("Gable stud", SPF, prism_x(stud_side(c), x0, x0 + D))
            for c in centres
        ]
        out += [
            Member("Sheathing", OSB_M, prism_x(panel_side(a, b), ox, ox + OSB))
            for a, b in itertools.pairwise(cuts)
        ]
    return out


def shoelace(points: list[tuple[float, float]]) -> float:
    n = len(points)
    return (
        abs(
            sum(
                points[i][0] * points[(i + 1) % n][1]
                - points[(i + 1) % n][0] * points[i][1]
                for i in range(n)
            )
        )
        / 2
    )


def gable_osb_area() -> float:
    """One gable's OSB (in^2): Y -7/16 .. 192 7/16 under the top plane."""
    k = top_plane(0.0) - PLATE
    half = W / 2 + OSB
    return 2 * (k * half + 0.5 * ((W / 2) ** 2 - OSB**2) / 2)


def house(length: float = 288.0) -> list[Member]:
    return joisted(length) + gable_members(length)


def house_volume() -> float:
    studs = 2 * 8.25 * (sum(long_point(c) for c in LEFT) - 11 * 0.375)
    return joisted_volume() + studs + 2 * gable_osb_area() * OSB


# --- 1. The STEP against the script -----------------------------------------------


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, NAME)


def test_the_gable_numbers_are_buildings_mds() -> None:
    """d / 2 - 29/12 at each stud's higher face; 262.791667 a gable, both
    gables alike (the right wall's layout is the left's mirror); 2 134 in^3
    of studs a gable; the OSB 5 705.19 in^2 a gable."""
    assert pytest.approx(106.1770833, abs=1e-7) == PLATE - HEEL
    assert top_plane(0.0) == pytest.approx(114.282829, abs=1e-6)
    assert sum(long_point(c) for c in LEFT) == pytest.approx(262.791667, abs=1e-6)
    assert sum(long_point(c) for c in RIGHT) == pytest.approx(262.791667, abs=1e-6)
    assert 8.25 * (sum(long_point(c) for c in LEFT) - 11 * 0.375) == pytest.approx(
        2134.0, abs=1e-9
    )
    for c in LEFT:
        assert 5.5 * shoelace(stud_side(c)) == pytest.approx(
            8.25 * (long_point(c) - 0.375), abs=1e-9
        )
    area = sum(shoelace(panel_side(a, b)) for a, b in itertools.pairwise(LEFT_COLUMNS))
    assert area == pytest.approx(gable_osb_area(), abs=1e-9)
    assert round(gable_osb_area(), 2) == 5705.19
    assert house_volume() == pytest.approx(
        287739.9752886 + 4268.0 + 2 * 5705.185554 * OSB, abs=1e-5
    )


def test_the_step_is_the_script_and_the_gable_ends(step_solids: list[Solid]) -> None:
    mine = house()
    assert len(step_solids) == len(mine) == 262
    assert _unmatched(step_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(house_volume(), abs=1e-4)


# --- 2. Interference none ---------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert _overlapping(step_solids) == []


# --- 3. The cut list --------------------------------------------------------------


def _request(name: str = NAME) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _cut_list() -> Any:
    request = _request()
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(extents, members, request.materials),
    )


def test_the_studs_are_listed_by_their_long_points_under_roof() -> None:
    cut_list = _cut_list()
    roof = [line for line in cut_list.lines if line.system == "roof"]
    studs = [line for line in roof if line.member == "Gable stud"]
    assert [line.member for line in roof[:3]] == ["Rafter", "Ridge", "Ceiling joist"]
    assert {line.profile for line in studs} == {"2x6"}
    lengths = Counter({round(line.length_mm / IN, 6): line.quantity for line in studs})
    assert lengths == Counter({round(long_point(c), 6): 2 for c in LEFT})
    assert sum(k * n for k, n in lengths.items()) == pytest.approx(
        2 * 262.791667, abs=1e-5
    )


def test_the_gables_osb_is_six_4x8_sheets() -> None:
    """The 12 gable panels fit 4x8 sheets (the walls' 97.125 in panels are
    on 4x9s, a line of their own), 11 410.37 in^2. Each panel is measured in
    its own frame, along its two largest perpendicular faces: the peak panel
    and the corner pieces along the plate (48 x 53.69, 5.9375 x 8.44), the
    four trapezoids along their sloped edge, the longer (48 x 50.94 is
    65.71 x 45.56, 48 x 32.44 is 57.44 x 29.01, 37 x 26.94 is 45.14 x
    24.10). By hand, largest first: each 65.71 and each 53.69 takes a sheet
    (no offcut is 48 by more than 42.2), each 57.44 too (its offcuts are
    30.16 x 45.56 and 42.19 x 48), and the rest fit the offcuts: 6 sheets,
    sheets_to_cut's count."""
    rects = [(65.7132, 45.5613), (53.6891, 48.0), (57.4397, 29.0144), (45.1413, 24.095)]
    rects = [*rects, (8.4391, 5.9375), (8.4391, 5.9375)] * 2
    assert (
        sheets_to_cut(((a * IN, b * IN) for a, b in rects), SHEET_SIZES_BY_KEY["4x8"])
        == 6
    )
    cut_list = _cut_list()
    osb = [
        line
        for line in cut_list.lines
        if line.system == "sheathing"
        and line.sheet == "4x8"
        and line.profile == "7/16 OSB"
    ]
    assert len(osb) == 1
    assert (osb[0].quantity, osb[0].stock_quantity) == (12, 6)
    assert osb[0].area_mm2 / IN**2 == pytest.approx(2 * gable_osb_area(), abs=1e-4)
    assert round(2 * gable_osb_area(), 2) == 11410.37
    # The walls' line is b7-ceiling-joists': 24 panels on 21 4x9 sheets.
    walls = [
        line
        for line in cut_list.lines
        if line.system == "sheathing" and line.sheet == "4x9"
    ]
    assert [(line.quantity, line.stock_quantity) for line in walls] == [(24, 21)]


def test_the_sloped_panels_measure_along_their_slope() -> None:
    """The four trapezoids' frames: along the sloped edge (2, 1) / sqrt 5
    and across it, the extents of their corners (the hand numbers above)."""

    def extents(y0: float, y1: float) -> tuple[float, float]:
        pts = [(y - y0, z - PLATE) for y, z in panel_side(y0, y1)]
        if y1 > W / 2:  # the back side slopes down: mirror it
            pts = [(y1 - y0 - y, z) for y, z in pts]
        u = [(2 * y + z) / math.sqrt(5) for y, z in pts]
        v = [(-y + 2 * z) / math.sqrt(5) for y, z in pts]
        return (max(u) - min(u), max(v) - min(v))

    got = [extents(a, b) for a, b in ((101.5, 149.5), (5.5, 53.5), (149.5, 186.5))]
    assert [(round(a, 4), round(b, 4)) for a, b in got] == [
        (65.7132, 45.5613),
        (57.4397, 29.0144),
        (45.1413, 24.095),
    ]


# --- 4. The edits and the other cases ---------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


#: Each case's counts: bodies (b7-ceiling-joists' cases plus 34), studs,
#: panels, joists. A 171 span's end walls are 160 long: inner centres 16 ..
#: 144, 9 a gable. B7 turned: its end walls run through, 192 long (11 a
#: gable, 16 .. 176 from the outside corner) in 4 columns and no rip. At 291
#: the joist on the right wall's plate is left off: 11, not 1.6.0's 12.
COUNTS = {
    "b7-336": (247 + 34, 22, 12, 13),
    "b7-8-12": (228 + 34, 22, 12, 11),
    "b10": (295 + 34, 22, 12, 11),
    "b7-291": (None, 22, 12, 11),
    "ridge-post-171": (None, 18, 12, 11),
    "along-y-moved": (None, 22, 8, 11),
}


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_case_builds_its_gable_ends_with_no_interference(
    case: dict[str, Any],
) -> None:
    """28 ft (the right gable at X 330.5..336), 8/12 (re-cut, 2d/3 - 29/12),
    B10 (P2 meets the right wall below its plate), 291 (its joist over the
    end wall left off), a 171 span (a stud under the ridge on each wall, cut
    square to it) and B7 turned and moved (the gables run through)."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert _overlapping(solids) == []
    bodies, studs, panels, joists = COUNTS[case["name"]]
    if bodies is not None:
        assert case["bodies"] == bodies
    assert (case["studs"], case["panels"]) == (studs, panels)
    assert case["joists"] == joists
    if case["name"] == "b7-336":
        mine = house(336)
        assert _unmatched(solids, [m.solid for m in mine]) == []


# --- Mass and expected.json's numbers -----------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = _request()
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITY[m.material] * 1e-6
        for m in house()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the script
    and the typed gable ends: the volume analytic, the rest measured on their
    solids; a planar face of n vertices on h holes meshes as n + 2h - 2
    triangles."""
    mine = house()
    area = 0.0
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    vertices = triangles = faces = edges = 0
    total = 0.0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        total += v
        area += float(props.surface_area)
        c = props.centroid
        density = DENSITY[m.material] * 1e-6
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * density * value
        mass += v * density
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": house_volume() * IN**3,
        "surface_area": area,
        "centroid": [x / total for x in moments],
        "mass_g": mass,
        "center_of_mass": [x / mass for x in mass_moments],
        "bbox": [
            min(b.min.X for b in bb),
            min(b.min.Y for b in bb),
            min(b.min.Z for b in bb),
            max(b.max.X for b in bb),
            max(b.max.Y for b in bb),
            max(b.max.Z for b in bb),
        ],
        "topology": {"faces": faces, "edges": edges, "shells": len(mine)},
        "mesh": {"vertices": vertices, "triangles": triangles},
    }


if __name__ == "__main__":
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
