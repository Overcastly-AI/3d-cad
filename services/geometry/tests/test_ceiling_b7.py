"""GYPSUM-SHEETS acceptance: B7's ceiling hung from its ceiling joists, on STEP.

``goldens/b7-ceiling`` is ``b7-gable-ends``' tree with its roof at
``loft.roof`` 1.8.0 (the same members: B7's walls carry no exterior finish)
and one ``loft.ceiling`` 1.0.0 on it, every default kept. ``model.json``,
``members.json`` and ``fixtures/ceiling-cases.json.gz`` are pinned to the
plugins by ``packages/loft-plugins/tests/test_ceiling.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked against B7's independent script with its ceiling joists and gable
ends (``test_gable_ends_b7.house``) and the ceiling typed here from
``docs/reference-parts/buildings.md`` and BACKLOG GYPSUM-SHEETS, sharing no
code with the plugins:

1. the STEP's 270 solids are the script's 262 and 8 ceiling panels, solid
   for solid: X 5.5..145.5 and 145.5..282.5 (the joint on the centre of the
   joist at X 144.75..146.25) by Y 5.5..53.5, ..101.5, ..149.5, ..186.5 (a
   37 in rip), Z 108.09375..108.59375 under the joists; 277 x 181 x 1/2 =
   25 068.5 in^3 more than b7-gable-ends;
2. interference none, every pair probed exactly: the board's top meets the
   joists' and the plates' undersides face to face, its edges the walls';
3. the cut list: one line, 8 panels of 1/2 ceiling gypsum, 50 137 in^2
   (348.17 ft^2), cut from 8 sheets of 4x12 (no panel fits another's
   offcut: 144 - 140 and 144 - 137 are under 37);
4. B10 under its ceiling (P1 and P2 cut out with their gypsum: 13 panels),
   B10 with its walls' inside gypsum, 28 ft (12), 8/12 (8) and B7 turned off
   the origin (8, the courses along X) all build with no interference, every
   pair probed exactly: against the ceiling joists, the partitions and every
   board.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_ceiling_b7.py``.
"""

import gzip
import json
import sys
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

sys.path.insert(0, str(Path(__file__).parent))
from test_gable_ends_b7 import house as gabled
from test_gable_ends_b7 import house_volume as gabled_volume
from test_outline_b7 import (
    DENSITY,
    IN,
    PLATE,
    Member,
    _overlapping,  # pyright: ignore[reportPrivateUsage]
    _step_solids,  # pyright: ignore[reportPrivateUsage]
    _unmatched,  # pyright: ignore[reportPrivateUsage]
    box,
)

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b7-ceiling"
CASES = Path(__file__).resolve().parent / "fixtures" / "ceiling-cases.json.gz"
GYP = "gypsum"
#: ASCE 7-16 C3.1-1a's gypsum board, as the material library gives it.
DENSITIES = {**DENSITY, GYP: 846.0}

# --- The ceiling, typed from buildings.md and BACKLOG (inches) ---------------------

BOARD = 0.5
COURSES = [(5.5, 53.5), (53.5, 101.5), (101.5, 149.5), (149.5, 186.5)]
#: 277 in in two 4x12 lengths: the joint on the joist beside the common at
#: X 144 (144.75..146.25), the farthest a 144 in sheet from X 5.5 reaches.
RUNS = [(5.5, 145.5), (145.5, 282.5)]


def ceiling_members() -> list[Member]:
    return [
        Member("Ceiling", GYP, box((a0, a1, b0, b1, PLATE - BOARD, PLATE)))
        for b0, b1 in COURSES
        for a0, a1 in RUNS
    ]


def house() -> list[Member]:
    return gabled() + ceiling_members()


def house_volume() -> float:
    return gabled_volume() + 277 * 181 * BOARD


# --- 1. The STEP against the script -----------------------------------------------


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, NAME)


def test_the_ceiling_numbers_are_the_backlogs() -> None:
    assert PLATE == 108.59375
    assert [b - a for a, b in RUNS] == [140, 137]
    assert [b - a for a, b in COURSES] == [48, 48, 48, 37]
    assert 144.75 < RUNS[0][1] < 146.25 and RUNS[0][1] - RUNS[0][0] <= 144
    assert round(277 * 181 / 144, 2) == 348.17
    assert house_volume() - gabled_volume() == 25068.5


def test_the_step_is_the_script_and_the_ceiling(step_solids: list[Solid]) -> None:
    mine = house()
    assert len(step_solids) == len(mine) == 270
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


def test_the_ceiling_takes_8_sheets_of_4x12() -> None:
    cut_list = _cut_list()
    ceiling = [line for line in cut_list.lines if line.member == "Ceiling"]
    assert len(ceiling) == 1
    line = ceiling[0]
    assert (line.system, line.profile, line.material) == (
        "walls",
        "1/2 ceiling gypsum",
        GYP,
    )
    assert line.quantity == 8
    assert line.area_mm2 / IN**2 == pytest.approx(50137, abs=1e-6)
    assert (line.sheet, line.stock_quantity) == ("4x12", 8)
    assert cut_list.unclassified == 0
    # The rest is b7-gable-ends': its 24 wall panels on 21 4x9s.
    walls = [
        ln for ln in cut_list.lines if ln.system == "sheathing" and ln.sheet == "4x9"
    ]
    assert [(ln.quantity, ln.stock_quantity) for ln in walls] == [(24, 21)]


# --- 4. The other cases -----------------------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


#: Each case's ceiling panels. B10: P1 (X 177.75..182.25 with its boards)
#: splits each course's east sheet; P2 (Y 129.75..134.25 east of P1) splits
#: the third course's piece east of P1 again: 3 + 3 + 4 + 3. At 28 ft, 325
#: in is 140 + 144 + 41 (joints on the joists at X 145.5 and 289.5).
PANELS = {
    "b10": 13,
    "b10-inside-gypsum": 13,
    "b7-336": 12,
    "b7-8-12": 8,
    "along-y-moved": 8,
}


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_case_hangs_its_ceiling_with_no_interference(
    case: dict[str, Any],
) -> None:
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert _overlapping(solids) == []
    assert case["panels"] == PANELS[case["name"]]


# --- Mass and expected.json's numbers -----------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = _request()
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITIES[m.material] * 1e-6
        for m in house()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the script
    and the typed ceiling: the volume analytic, the rest measured on their
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
        density = DENSITIES[m.material] * 1e-6
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
