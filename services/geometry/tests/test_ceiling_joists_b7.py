"""CEILING-JOISTS acceptance: B7's gable tied by its ceiling joists, on STEP.

``goldens/b7-ceiling-joists`` is ``b7-outline``'s tree with its roof at
``loft.roof`` 1.6.0, every default kept: a 2x8 ceiling joist on the front and
back walls' plates beside each inner common pair. ``model.json`` and
``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_ceiling_joists.py``, as is
``fixtures/ceiling-joist-cases.json.gz`` (B7 at 28 ft and at 8/12, B10).
Geometry never learns plugins exist, so this module imports nothing from them.

Checked against B7's independent script (``test_outline_b7.script``) and
joists typed here from ``docs/reference-parts/buildings.md``, sharing no code
with the plugins:

1. the STEP's 228 solids are the script's 217 and 11 joists, solid for
   solid: X c + 0.75 .. c + 2.25 for c = 24 .. 264, Y 0..192, Z 108.59375 ..
   115.84375, each top corner snipped delta = 29/3 - 7.25 sqrt(1.25) down
   and 2 delta along, 2 088 - 3 delta^2 = 2 080.690584 in^3 a joist; the
   volume is b7-outline's 264 852.3788656 + 22 887.596423 in^3;
2. interference none, every pair probed exactly: each joist meets its rafter
   face to face and stands on the plates;
3. the cut list: 11 ceiling joists 192 in on one 16 ft stock each, under
   Roof, never spliced;
4. 28 ft frames 13 (B7's script at 336), 8/12 re-snips them, and B10's
   partitions stand face to face under them, with no interference.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_ceiling_joists_b7.py``.
"""

import gzip
import json
import math
import sys
from collections.abc import Sequence
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
from loft_wire.price_book import PriceBookResponse

# B7's independent script and probes. pytest imports test modules in
# importlib mode, so put this directory on the path to read them.
sys.path.insert(0, str(Path(__file__).parent))
from test_outline_b7 import (
    DENSITY,
    IN,
    PLATE,
    SPF,
    Member,
    _overlapping,  # pyright: ignore[reportPrivateUsage]
    _step_solids,  # pyright: ignore[reportPrivateUsage]
    _unmatched,  # pyright: ignore[reportPrivateUsage]
    analytic_volume,
    layout,
    prism_x,
    script,
)

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b7-ceiling-joists"
CASES = Path(__file__).resolve().parent / "fixtures" / "ceiling-joist-cases.json.gz"

# --- The joists, typed from buildings.md (inches) ---------------------------------

W = 192.0
DEPTH = 7.25  # 2x8
T = 1.5


def delta(rise: int) -> float:
    """The joist's top (the plate + 7.25) less the rafters' top plane at the
    wall's outside face: the heel's foot (the plate less 29/12, the heel held
    to a third of 7.25) plus the plumb depth 7.25 sqrt(144 + rise^2) / 12."""
    heel_foot = PLATE - DEPTH / 3
    return PLATE + DEPTH - (heel_foot + DEPTH * math.hypot(12.0, rise) / 12.0)


def joist_side(rise: int = 6) -> list[tuple[float, float]]:
    d = delta(rise)
    run = d * 12.0 / rise
    top = PLATE + DEPTH
    return [
        (0.0, PLATE),
        (W, PLATE),
        (W, top - d),
        (W - run, top),
        (run, top),
        (0.0, top - d),
    ]


def joist_volume(rise: int = 6) -> float:
    """1.5 x 7.25 x 192 less two triangles delta x delta / slope / 2."""
    d = delta(rise)
    return T * DEPTH * W - T * d * d * 12.0 / rise


def inner_commons(length: float) -> list[float]:
    """The commons but the two gable-end rafters (B7's 24 in layout)."""
    return layout(length, 24.0)[1:-1]


def joists(length: float = 288.0, rise: int = 6) -> list[Member]:
    side = joist_side(rise)
    return [
        Member("Ceiling joist", SPF, prism_x(side, c + 0.75, c + 2.25))
        for c in inner_commons(length)
    ]


def house(length: float = 288.0) -> list[Member]:
    return script(length) + joists(length)


def house_volume(length: float = 288.0) -> float:
    return analytic_volume(length) + len(inner_commons(length)) * joist_volume()


# --- 1. The STEP against the script -----------------------------------------------


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, NAME)


def test_the_joist_numbers_are_buildings_mds() -> None:
    d = delta(6)
    heel_foot = PLATE - DEPTH / 3
    assert heel_foot == pytest.approx(106.1770833, abs=1e-7)
    assert PLATE + DEPTH - d == pytest.approx(114.282829, abs=1e-6)
    assert d == pytest.approx(29 / 3 - 7.25 * math.sqrt(1.25), abs=1e-12)
    assert (round(d, 6), round(2 * d, 6)) == (1.560920, 3.121840)
    assert joist_volume() == pytest.approx(2088 - 3 * d * d, abs=1e-9)
    assert round(joist_volume(), 6) == 2080.690584
    assert inner_commons(288) == list(range(24, 265, 24))
    assert round(11 * joist_volume(), 6) == 22887.596423
    assert house_volume() == pytest.approx(264852.3788656 + 22887.596423, abs=1e-6)


def test_the_step_is_the_script_and_eleven_joists(step_solids: list[Solid]) -> None:
    mine = house()
    assert len(step_solids) == len(mine) == 228
    assert _unmatched(step_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(house_volume(), abs=1e-4)
    for joist in joists():
        assert float(measure_shape(joist.solid).volume) / IN**3 == pytest.approx(
            joist_volume(), abs=1e-6
        )


# --- 2. Interference none ---------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert _overlapping(step_solids) == []


# --- 3. The cut list --------------------------------------------------------------


def _request(name: str = NAME) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": SPF,
                "profile": "us_2x8",
                "unit": "each",
                "stock_length_ft": 16,
                "price_cents": 1797,
            }
        ],
    }
)


def test_the_joists_are_one_16_ft_piece_each_under_roof() -> None:
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
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(extents, members, request.materials),
        price_book=BOOK,
    )
    roof = [line for line in cut_list.lines if line.system == "roof"]
    assert [(line.member, line.quantity) for line in roof] == [
        ("Rafter", 26),
        ("Ridge", 1),
        ("Ceiling joist", 11),
    ]
    line = roof[2]
    assert line.profile == "2x8"
    assert round(line.length_mm / IN, 6) == 192.0
    assert line.stock_pieces_ft == [16]
    assert line.extended_price_cents == 11 * 1797


# --- 4. The edits and B10 ---------------------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


def _joist_solids(solids: Sequence[Solid]) -> list[Solid]:
    """The solids standing on the plates 1.5 x 192 x 7.25 in box: the joists."""
    out: list[Solid] = []
    for s in solids:
        bb = s.bounding_box()
        size = (bb.size.X / IN, bb.size.Y / IN, bb.size.Z / IN)
        if (
            abs(size[0] - T) < 1e-6
            and abs(size[1] - W) < 1e-6
            and abs(size[2] - DEPTH) < 1e-6
            and abs(bb.min.Z / IN - PLATE) < 1e-6
        ):
            out.append(s)
    return out


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_case_builds_its_joists_with_no_interference(case: dict[str, Any]) -> None:
    """B7 at 28 ft is the script at 336 and 13 joists; at 8/12 each of the 11
    joists is re-snipped (delta 29/3 - 7.25 sqrt(13) / 3, 1.5 delta along);
    in B10 P2's top plate is face to face under them."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert _overlapping(solids) == []
    found = _joist_solids(solids)
    rise = 8 if case["name"] == "b7-8-12" else 6
    assert len(found) == case["joists"] == {"b7-336": 13}.get(case["name"], 11)
    for s in found:
        volume = float(measure_shape(s).volume) / IN**3
        assert volume == pytest.approx(joist_volume(rise), abs=1e-6)
    if case["name"] == "b7-8-12":
        assert round(delta(8), 6) == 0.953251
        assert round(joist_volume(8), 6) == round(2088 - 2.25 * delta(8) ** 2, 6)
    if case["name"] == "b7-336":
        mine = house(336)
        assert len(solids) == len(mine) == 234 + 13
        assert _unmatched(solids, [m.solid for m in mine]) == []
        volume = sum(float(measure_shape(s).volume) for s in solids) / IN**3
        assert volume == pytest.approx(house_volume(336), abs=1e-4)
    if case["name"] == "b10":
        assert len(solids) == 284 + 11


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
    and the typed joists: the volume analytic, the rest measured on their
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
