# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false
"""Sweep along a CLOSED path (SWEEP-CLOSED-PATH) — what the goldens cannot say.

The goldens ``sweep-closed-torus-ring-R50-r5`` and
``sweep-closed-rounded-rect-loop-140x100-rc20-rect10x6`` run every parametrized
gate (mass properties, topology, mesh, determinism, STEP round trip). This file
checks each against an INDEPENDENT build123d twin that involves no sweep at all
(an analytic torus, an extruded 2D ring), with an empty two-way boolean
difference, and pins the closed sweep's kernel decisions (docs/RESEARCH.md
§19):

* the swept body does not depend on where the loop's first entity starts (the
  profile is seated where it meets the path);
* the binormal is fixed on the sketch normal, so a section offset to one side of
  an S-curved loop stays on its side (a Frenet frame flips it) and the volume is
  Pappus' A (L - 2 pi d);
* a non-G1 joint, a bend tighter than the section, a section lying along the
  path, and a twist are typed refusals, never a self-intersecting body;
* a closed sweep cuts as well as adds.
"""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from build123d import Edge, Face, Location, Plane, Solid, Vector, Wire
from geometry.features import evaluate_tree
from geometry.harness import load_model_request
from geometry.kernel import measure_shape
from geometry.kernel.lumps import lump_count
from geometry.kernel.sweep import build_path_wire
from geometry.kernel.sweep_closed import (
    PathCornerError,
    check_closed_path_tangent,
    sweep_closed_profile,
)
from geometry.kernel.types import BodyShape
from loft_wire.features import EvaluateTreeRequest, EvaluateTreeResult
from loft_wire.sketch import SketchEntity
from pydantic import TypeAdapter

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
TORUS = GOLDENS / "sweep-closed-torus-ring-R50-r5"
LOOP = GOLDENS / "sweep-closed-rounded-rect-loop-140x100-rc20-rect10x6"


def _model(golden: Path) -> dict[str, Any]:
    return json.loads((golden / "model.json").read_text(encoding="utf-8"))


def _tolerance(golden: Path) -> float:
    expected = json.loads((golden / "expected.json").read_text(encoding="utf-8"))
    return float(expected["tolerance"])


def _evaluate(model: dict[str, Any]) -> tuple[EvaluateTreeResult, BodyShape | None]:
    request = load_model_request(json.dumps(model))
    assert isinstance(request, EvaluateTreeRequest)
    evaluation = evaluate_tree(request)
    return evaluation.result, evaluation.body


def _body(model: dict[str, Any]) -> BodyShape:
    result, body = _evaluate(model)
    assert all(r.status == "ok" for r in result.features), [
        (r.feature_id, r.error) for r in result.features if r.error
    ]
    assert body is not None
    return body


def _errors(model: dict[str, Any]) -> list[tuple[str, str]]:
    result, _ = _evaluate(model)
    return [(r.error.code, r.error.message) for r in result.features if r.error]


def _assert_same_solid(mine: BodyShape, twin: BodyShape, tolerance: float) -> None:
    """Equal volume (one integrator on both sides) and an empty two-way cut."""
    assert measure_shape(mine).volume == pytest.approx(
        measure_shape(twin).volume, abs=tolerance
    )
    lost = float(mine.cut(twin).volume)
    gained = float(twin.cut(mine).volume)
    assert lost <= tolerance, f"the sweep has {lost} mm^3 the twin lacks"
    assert gained <= tolerance, f"the twin has {gained} mm^3 the sweep lacks"


def _rounded_rect(width: float, height: float, radius: float) -> Face:
    """A centred rounded rectangle from exact lines and quarter circles.

    Not ``fillet_2d``: its corner arcs land 3e-5 mm^3 off the closed form here.
    """
    hx, hy = width / 2, height / 2
    cx, cy = hx - radius, hy - radius
    edges: list[Edge] = []
    for sx, sy, start_deg in ((1, -1, 270), (1, 1, 0), (-1, 1, 90), (-1, -1, 180)):
        centre = Vector(sx * cx, sy * cy, 0)
        edges.append(
            Edge.make_circle(
                radius, Plane.XY.move(Location(centre)), start_deg, start_deg + 90
            )
        )
    corners = [e.position_at(p) for e in edges for p in (0, 1)]
    for i in range(4):
        edges.append(Edge.make_line(corners[2 * i + 1], corners[(2 * i + 2) % 8]))
    return Face(Wire.combine(edges)[0])


# --- the goldens against their independent twins ------------------------------


def test_torus_ring_matches_the_analytic_torus() -> None:
    """R50 / r5: the swept ring IS Solid.make_torus(50, 5), and 2 pi^2 R r^2."""
    tolerance = _tolerance(TORUS)
    ring = _body(_model(TORUS))
    assert lump_count(ring) == 1
    assert measure_shape(ring).volume == pytest.approx(
        2 * math.pi**2 * 50 * 5**2, abs=tolerance
    )
    _assert_same_solid(ring, Solid.make_torus(50, 5), tolerance)


def test_rounded_rect_loop_matches_an_extruded_ring() -> None:
    """The swept band IS the 2D ring between the R25 and R15 offsets, extruded
    6 mm: the outer and inner offsets of the path by the half-width 5."""
    tolerance = _tolerance(LOOP)
    band = _body(_model(LOOP))
    ring = _rounded_rect(150, 110, 25) - _rounded_rect(130, 90, 15)
    assert isinstance(ring, Face)
    twin = Solid.extrude(ring.moved(Plane.XY.offset(-3).location), Vector(0, 0, 6))
    _assert_same_solid(band, twin, tolerance)
    # The prism sum by hand: straights w*h*len plus four quarter annuli.
    assert measure_shape(band).volume == pytest.approx(
        60 * 320 + 4 * 6 * (math.pi / 4) * (25**2 - 15**2), abs=tolerance
    )


def test_the_band_does_not_depend_on_where_the_loop_starts() -> None:
    """Rotating and reversing the path's entity list moves the wire's start
    away from (and then onto) other joints; the profile is seated where it
    meets the path, so every order builds the same band."""
    tolerance = _tolerance(LOOP)
    reference = _body(_model(LOOP))
    seat = Vector(0, -50, 0)  # where the golden's section meets the path
    for shift in (0, 3, 5):
        model = copy.deepcopy(_model(LOOP))
        entities = model["features"][1]["feature"]["params"]["entities"]
        rotated = entities[shift:] + entities[:shift]
        model["features"][1]["feature"]["params"]["entities"] = rotated[::-1]
        start = build_path_wire(Plane.XY, _entities(rotated[::-1])).position_at(0)
        assert (start - seat).length > 10, "the loop must not start at the seat"
        _assert_same_solid(_body(model), reference, tolerance)


# --- the fixed binormal ---------------------------------------------------------


def _peanut() -> Wire:
    """A closed C2 loop with four inflections (a peanut), on XY."""
    points = [(70, 0), (45, 30), (0, 14), (-45, 30), (-70, 0), (-45, -30), (0, -14)]
    points.append((45, -30))
    return Wire([Edge.make_spline([Vector(x, y, 0) for x, y in points], periodic=True)])


def test_an_offset_section_stays_on_its_side_through_inflections() -> None:
    """A 4 x 6 section lying wholly LEFT of the path and ABOVE its plane.

    With the binormal fixed on +Z the section never rolls: the band stays in
    z in [0, 6] all the way round, and its volume is Pappus for an offset
    section, A (L - 2 pi d), d = 2 the centroid's offset towards the inside of
    this counter-clockwise loop (whose tangent turns by 2 pi). A Frenet frame
    flips at each inflection: OCCT's Frenet sweep of the same section reaches
    z = -6 and is not even a valid solid.
    """
    path = _peanut()
    start, tangent = path.position_at(0), path.tangent_at(0)
    plane = Plane(origin=start, x_dir=Vector(0, 0, 1).cross(tangent), z_dir=tangent)
    corners = [(0, 0), (4, 0), (4, 6), (0, 6)]
    points = [Vector(plane.from_local_coords(c)) for c in corners]
    section = Face(Wire.make_polygon(points, close=True))
    band = sweep_closed_profile(section, path, Vector(0, 0, 1))
    box = band.bounding_box()
    low, high = box.min.Z, box.max.Z
    assert low == pytest.approx(0.0, abs=2e-7)
    assert high == pytest.approx(6.0, abs=2e-7)
    # BSpline swept faces: the pipe shell approximates them, to ~1e-8 relative.
    assert measure_shape(band).volume == pytest.approx(
        24 * (path.length - 2 * math.pi * 2), rel=1e-6
    )
    frenet = Solid.sweep(section, path, is_frenet=True)
    assert frenet.bounding_box().min.Z < -5


# --- typed refusals -------------------------------------------------------------


def _entities(raw: list[dict[str, Any]]) -> list[SketchEntity]:
    return TypeAdapter(list[SketchEntity]).validate_python(raw)


def test_a_kink_of_a_hundredth_of_a_degree_is_named() -> None:
    """A near-circle whose two halves have centres 0.0087 mm apart meets itself
    at a 0.01 deg corner at each joint: refused, naming both entities and the
    sketch point of the first joint."""
    offset = 50 * math.tan(math.radians(0.01))
    raw = [
        {
            "id": "top",
            "kind": "arc",
            "center": {"x": 0, "y": 0},
            "start": {"x": 50, "y": 0},
            "end": {"x": -50, "y": 0},
        },
        {
            "id": "bottom",
            "kind": "arc",
            "center": {"x": 0, "y": offset},
            "start": {"x": -50, "y": 0},
            "end": {"x": 50, "y": 0},
        },
    ]
    with pytest.raises(PathCornerError) as refused:
        check_closed_path_tangent(Plane.XY, _entities(raw))
    message = str(refused.value)
    assert "0.01 deg" in message
    assert "'top' and 'bottom'" in message
    assert "(50, 0)" in message


def test_a_bend_tighter_than_the_section_is_refused() -> None:
    """r5 around R4: the inner wall would pass through the axis."""
    model = copy.deepcopy(_model(TORUS))
    path = model["features"][1]["feature"]["params"]
    path["entities"][0]["radius"] = 4.0
    path["constraints"][1]["value_mm"] = 4.0
    profile = model["features"][0]["feature"]["params"]
    profile["entities"][0]["center"]["x"] = 4.0
    [(code, message)] = _errors(model)
    assert code == "sweep_failed"
    assert "bends at radius 4 mm" in message
    assert "reaches 5 mm" in message


def test_a_section_lying_along_the_path_is_refused() -> None:
    """A section drawn on the path's own plane has no thickness to sweep."""
    model = copy.deepcopy(_model(TORUS))
    profile = model["features"][0]["feature"]["params"]
    profile["plane"]["plane"] = "XY"
    [(code, message)] = _errors(model)
    assert code == "sweep_failed"
    assert "lies along the path" in message


def test_a_twist_on_a_closed_path_is_twist_path_unsupported() -> None:
    model = copy.deepcopy(_model(TORUS))
    model["features"][2]["feature"]["params"]["twist_angle_deg"] = 90.0
    [(code, _)] = _errors(model)
    assert code == "twist_path_unsupported"


# --- cut -------------------------------------------------------------------------


def test_a_closed_sweep_cuts_a_groove_ring() -> None:
    """Cut the R50 / r5 ring into an R50 x 20 disc at mid-height: the groove is
    the inner half of the torus, whose half-disc section (area pi r^2 / 2) has
    its centroid 4r / 3pi inside R, so Pappus removes
    2 pi (R - 4r / 3pi) (pi r^2 / 2)."""
    model = copy.deepcopy(_model(TORUS))
    profile = model["features"][0]["feature"]["params"]
    profile["entities"][0]["center"]["y"] = 10.0  # XZ: sketch y is world z
    disc_sketch = {
        "id": "00000000-0000-0000-0000-000000c100a1",
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {"id": "d", "kind": "circle", "center": {"x": 0, "y": 0}}
                    | {"radius": 50.0}
                ],
                "constraints": [],
            },
        },
    }
    disc = {
        "id": "00000000-0000-0000-0000-000000c100a2",
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": disc_sketch["id"]},
                "distance_mm": 20.0,
                "operation": "add",
                "direction": "normal",
            },
        },
    }
    sweep = model["features"][2]
    sweep["feature"]["params"]["operation"] = "cut"
    model["features"] = [disc_sketch, disc, *model["features"]]
    body = _body(model)
    r, big_r = 5.0, 50.0
    groove = 2 * math.pi * (big_r - 4 * r / (3 * math.pi)) * (math.pi * r**2 / 2)
    assert measure_shape(body).volume == pytest.approx(
        math.pi * big_r**2 * 20 - groove, rel=1e-9
    )
