"""Twisted extrude — the extrude feature's ``twist_angle_deg`` (helical-gear gap #1).

docs/design/twisted-extrude.md. The golden
``extrude-twist-square20-hole-r3-h30-30deg`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py`` (analytic mass properties,
exact topology, in-process + cross-interpreter byte determinism, STEP round
trip). This module covers what one golden cannot:

* **no twist is the old extrude, byte for byte** — ``twist_angle_deg`` absent,
  ``null`` and ``0`` all produce the identical evaluate response (mesh id
  included) that the committed extrude golden produces;
* **handedness is about the direction of travel** — a positive twist is a
  right-hand helix for ``direction: normal`` AND ``reverse``;
* **the twist axis** goes through ``twist_center``, defaulting to the sketch
  origin;
* **cut mode** (the helical gear's tooth gap), including a holed profile and
  disjoint regions, removes exactly ``area(profile ∩ blank section) x depth``
  for a blank that is a solid of revolution about the twist axis (every slice
  of the tool is a rotated copy of the profile, and the blank's slice is
  rotation-invariant), with the removal visibly rotated;
* **a malformed sweep is a named refusal** (``twist_failed``), never the
  inverted, ``BRepCheck``-valid solid OCCT can return.

Every expected number is analytic; the two tolerances below were measured
first, then set, and say so.
"""

import json
import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import geometry.kernel.twist as twist_kernel
import pytest
from build123d import Face, Plane, Solid, Wire
from fastapi.testclient import TestClient
from geometry.assembly.protocol import ResolvedAxis
from geometry.assembly.resolve import resolve_mate_geometry
from geometry.features import evaluate_tree
from geometry.features.evaluate import reset_rebuild_cache
from geometry.kernel import export_step_bytes, measure_shape
from geometry.kernel.edges import enumerate_edges
from geometry.kernel.imports import import_step_solid
from geometry.kernel.properties import volume_integrand
from geometry.kernel.step_assembly import read_step_assembly
from geometry.main import app
from loft_wire.assemblies import MateAxisRef
from loft_wire.features import EvaluateTreeRequest, EvaluateTreeResult
from loft_wire.sketch import Point2D

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
EXTRUDE_GOLDEN = GOLDENS / "sketch-extrude-40x25x10" / "model.json"
TWIST_GOLDEN = GOLDENS / "extrude-twist-square20-hole-r3-h30-30deg"

#: Absolute bound (mm^3, and mm on AABB bounds) for this module's twisted
#: bodies, MEASURED FIRST, THEN SET (2026-09-24, pipe-shell fit 1e-7 mm): the
#: worst volume residual against the analytic value is +2.44e-6 mm^3 (the holed
#: disjoint-region cut, 1e-10 relative, five B-spline flank families), then
#: +3.9e-7 (helical slot) and +2.7e-7 (holed prism, = the golden's residual);
#: AABB bounds carry the 1.0e-7 modelling-tolerance padding. 2e-5 is 8x the
#: worst case. The golden keeps its own, tighter, per-model bound (2e-6).
TWIST_TOL = 2e-5

#: Absolute bound (mm) on centroids here, measured the same way: worst
#: residual 4.2e-10 (the orbiting square), 12x inside this. A handedness error
#: moves centroid.y by >= 0.15 mm, eight orders of magnitude outside it.
CENTROID_TOL = 5e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000077a")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000077a1")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000077b1")
SKETCH2_ID = uuid.UUID("00000000-0000-0000-0000-0000000077a2")
EXTRUDE2_ID = uuid.UUID("00000000-0000-0000-0000-0000000077b2")
XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _circle(eid: str, c: tuple[float, float], r: float) -> dict[str, Any]:
    return {"id": eid, "kind": "circle", "center": {"x": c[0], "y": c[1]}, "radius": r}


def _rect(prefix: str, x0: float, y0: float, x1: float, y1: float) -> list[Any]:
    return [
        _line(f"{prefix}1", (x0, y0), (x1, y0)),
        _line(f"{prefix}2", (x1, y0), (x1, y1)),
        _line(f"{prefix}3", (x1, y1), (x0, y1)),
        _line(f"{prefix}4", (x0, y1), (x0, y0)),
    ]


def _sketch(feature_id: uuid.UUID, entities: list[Any]) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def _extrude(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    **extra: Any,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "profile": {"kind": "feature", "feature_id": str(profile_id)},
        "distance_mm": distance_mm,
        "operation": "add",
        "direction": "normal",
    }
    params.update(extra)
    return {
        "id": str(feature_id),
        "feature": {"type": "extrude", "version": 1, "params": params},
    }


def _evaluate(features: list[dict[str, Any]]) -> EvaluateTreeResult:
    response = client.post(
        "/api/v1/evaluate",
        json={"part_id": str(PART_ID), "tree_version": 1, "features": features},
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


def _ok_properties(result: EvaluateTreeResult) -> Any:
    assert [r.status for r in result.features] == ["ok"] * len(result.features), [
        (r.status, r.error) for r in result.features
    ]
    assert result.properties is not None
    return result.properties


def _mean_rotation(theta: float) -> tuple[float, float]:
    """Mean over z of (cos, sin) of a section turned uniformly from 0 to theta."""
    return math.sin(theta) / theta, (1.0 - math.cos(theta)) / theta


# --- No twist is the old extrude, byte for byte ----------------------------------


@pytest.mark.parametrize("twist", ["absent", None, 0.0, -0.0])
def test_no_twist_is_byte_identical_to_the_plain_extrude(twist: object) -> None:
    """The committed extrude golden, with the twist field absent / null / 0 / -0:
    the WHOLE response is identical, mesh id included, because a zero twist
    never leaves the prism path (the `_extrude_tool` branch point)."""
    baseline: dict[str, Any] = json.loads(EXTRUDE_GOLDEN.read_text())
    variant: dict[str, Any] = json.loads(EXTRUDE_GOLDEN.read_text())
    if twist != "absent":
        variant["features"][1]["feature"]["params"]["twist_angle_deg"] = twist
        variant["features"][1]["feature"]["params"]["twist_center"] = {
            "x": 7.0,
            "y": -3.0,
        }
    first = client.post("/api/v1/evaluate", json=baseline)
    second = client.post("/api/v1/evaluate", json=variant)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- The twisted prism: volume, handedness, axis ---------------------------------

SQUARE = _rect("s", -10.0, -10.0, 10.0, 10.0)
#: An OFF-AXIS hole makes the handedness observable in the centroid: a centred
#: square is symmetric under the twist, a mirrored helix would pass it.
SQUARE_WITH_HOLE = [*SQUARE, _circle("h1", (4.0, 0.0), 3.0)]
HOLED_AREA = 400.0 - 9.0 * math.pi
HOLED_CENTROID_X0 = -(9.0 * math.pi) * 4.0 / HOLED_AREA  # slice centroid at z=0


@pytest.mark.parametrize(
    ("direction", "twist", "sense"),
    [
        ("normal", 30.0, 1.0),  # right-hand about +Z: CCW seen from +Z
        ("normal", -30.0, -1.0),  # left-hand
        ("reverse", 30.0, -1.0),  # right-hand about -Z: CW seen from +Z
        ("reverse", -30.0, 1.0),
    ],
)
def test_twist_is_right_handed_about_the_direction_of_travel(
    direction: str, twist: float, sense: float
) -> None:
    """Every slice is the profile turned by `sense * theta(z)` about +Z, so the
    volume is area x depth (Cavalieri) and the centroid is the slice centroid
    rotated by the MEAN turn — whose y sign is the handedness."""
    props = _ok_properties(
        _evaluate(
            [
                _sketch(SKETCH_ID, SQUARE_WITH_HOLE),
                _extrude(
                    EXTRUDE_ID,
                    SKETCH_ID,
                    30.0,
                    direction=direction,
                    twist_angle_deg=twist,
                ),
            ]
        )
    )
    cos_mean, sin_mean = _mean_rotation(math.radians(30.0))
    z_mid = 15.0 if direction == "normal" else -15.0
    assert props.volume == pytest.approx(HOLED_AREA * 30.0, abs=TWIST_TOL)
    assert props.centroid.x == pytest.approx(
        HOLED_CENTROID_X0 * cos_mean, abs=CENTROID_TOL
    )
    assert props.centroid.y == pytest.approx(
        sense * HOLED_CENTROID_X0 * sin_mean, abs=CENTROID_TOL
    )
    assert props.centroid.z == pytest.approx(z_mid, abs=CENTROID_TOL)
    assert props.topology.faces == 7  # 4 helicoidal flanks + hole tube + 2 caps


def test_twist_axis_goes_through_twist_center() -> None:
    """A 20 mm square at (10..30, -10..10): about its OWN centre it spins in
    place (centroid on the axis, AABB half-width a(cos t + sin t)); about the
    default sketch origin it orbits (centroid swings off (20, 0))."""
    square = _rect("s", 10.0, -10.0, 30.0, 10.0)
    spun = _ok_properties(
        _evaluate(
            [
                _sketch(SKETCH_ID, square),
                _extrude(
                    EXTRUDE_ID,
                    SKETCH_ID,
                    30.0,
                    twist_angle_deg=30.0,
                    twist_center={"x": 20.0, "y": 0.0},
                ),
            ]
        )
    )
    half = 10.0 * (math.cos(math.radians(30.0)) + math.sin(math.radians(30.0)))
    assert spun.volume == pytest.approx(400.0 * 30.0, abs=TWIST_TOL)
    assert spun.centroid.x == pytest.approx(20.0, abs=CENTROID_TOL)
    assert spun.centroid.y == pytest.approx(0.0, abs=CENTROID_TOL)
    # optimal AABB is padded ~1e-7 by the modelling tolerance (golden rationale)
    assert spun.bounding_box.max.x == pytest.approx(20.0 + half, abs=TWIST_TOL)
    assert spun.bounding_box.min.y == pytest.approx(-half, abs=TWIST_TOL)

    orbit = _ok_properties(
        _evaluate(
            [
                _sketch(SKETCH_ID, square),
                _extrude(EXTRUDE_ID, SKETCH_ID, 30.0, twist_angle_deg=30.0),
            ]
        )
    )
    cos_mean, sin_mean = _mean_rotation(math.radians(30.0))
    assert orbit.volume == pytest.approx(400.0 * 30.0, abs=TWIST_TOL)
    assert orbit.centroid.x == pytest.approx(20.0 * cos_mean, abs=CENTROID_TOL)
    assert orbit.centroid.y == pytest.approx(20.0 * sin_mean, abs=CENTROID_TOL)


@pytest.mark.parametrize(
    ("plane", "centre_world", "normal"),
    [
        # RESEARCH §12: XZ is x_dir +X, y_dir +Z, z_dir -Y; YZ is +Y, +Z, +X.
        ("XZ", (20.0, 0.0, 5.0), (0.0, -1.0, 0.0)),
        ("YZ", (0.0, 20.0, 5.0), (1.0, 0.0, 0.0)),
    ],
)
def test_twist_center_is_sketch_local_not_world(
    plane: str, centre_world: tuple[float, float, float], normal: tuple[float, ...]
) -> None:
    """``twist_center`` is in the SKETCH's (u, v), mapped through the plane.

    A 20 mm square at u in [10, 30], v in [-5, 15] twisted about its own centre
    (u, v) = (20, 5) spins in place, so the solid's centroid is that centre's
    WORLD position plus half the extrusion along the plane normal - on XZ and
    YZ, where sketch (u, v) and world (x, y) disagree. Treating the centre as
    world (x, y, 0) puts the axis 5 mm off the square's centre, so the section
    orbits and the centroid moves (review of d823af9: that mutation passed the
    whole suite, because every other twist test sketches on XY about the
    origin)."""
    square = _rect("s", 10.0, -5.0, 30.0, 15.0)
    sketch = _sketch(SKETCH_ID, square)
    sketch["feature"]["params"]["plane"] = {"kind": "datum_plane", "plane": plane}
    props = _ok_properties(
        _evaluate(
            [
                sketch,
                _extrude(
                    EXTRUDE_ID,
                    SKETCH_ID,
                    30.0,
                    twist_angle_deg=30.0,
                    twist_center={"x": 20.0, "y": 5.0},
                ),
            ]
        )
    )
    expected = [c + 15.0 * n for c, n in zip(centre_world, normal, strict=True)]
    assert props.volume == pytest.approx(400.0 * 30.0, abs=TWIST_TOL)
    assert props.centroid.x == pytest.approx(expected[0], abs=CENTROID_TOL)
    assert props.centroid.y == pytest.approx(expected[1], abs=CENTROID_TOL)
    assert props.centroid.z == pytest.approx(expected[2], abs=CENTROID_TOL)


def test_twisted_extrude_starts_a_second_body_with_merge_false() -> None:
    """`merge: false` composes with a twist: the twisted prism is a NEW body."""
    result = _evaluate(
        [
            _sketch(SKETCH_ID, _rect("s", -50.0, -5.0, -40.0, 5.0)),
            _extrude(EXTRUDE_ID, SKETCH_ID, 10.0),
            _sketch(SKETCH2_ID, SQUARE),
            _extrude(EXTRUDE2_ID, SKETCH2_ID, 30.0, twist_angle_deg=45.0, merge=False),
        ]
    )
    props = _ok_properties(result)
    assert len(result.bodies) == 2
    assert props.volume == pytest.approx(1000.0 + 400.0 * 30.0, abs=TWIST_TOL)


# --- Cap edges are analytic again ---------------------------------------------------


def _golden_body() -> Any:
    request = EvaluateTreeRequest.model_validate_json(
        (TWIST_GOLDEN / "model.json").read_text()
    )
    evaluation = evaluate_tree(request)
    assert evaluation.body is not None
    return evaluation.body


def test_cap_edges_are_lines_and_circles_and_a_rim_is_a_mate_axis() -> None:
    """A pipe shell rebuilds even the end sections as B-spline fits, so before
    the restoration a twisted body had NO line or circle edge, and everything
    keyed on edge type missed its rims (review of d823af9: mate axis, measure
    direction, drawings, edge re-match). Census of the golden: the 8 square
    sides and 2 hole rims on the two caps are LINE / CIRCLE, and only the 5
    genuinely helical edges (4 corners + the tube seam) are B-splines. The far
    rim then resolves as an assembly axis: centre = the hole centre (4, 0)
    turned 30 deg, direction +/-Z."""
    body = _golden_body()
    census: dict[tuple[str, str], int] = {}
    for record in enumerate_edges(body):
        edge = record.edge
        heights = [edge.start_point().Z, edge.end_point().Z, edge.position_at(0.5).Z]
        on_cap = any(all(abs(z - cap) < 1e-6 for z in heights) for cap in (0.0, 30.0))
        key = ("cap" if on_cap else "side", record.signature.curve)
        census[key] = census.get(key, 0) + 1
    assert census == {("cap", "line"): 8, ("cap", "circle"): 2, ("side", "other"): 5}

    rim = next(
        record
        for record in enumerate_edges(body)
        if record.signature.curve == "circle"
        and abs(record.edge.position_at(0.0).Z - 30.0) < 1e-6
    )
    axis = resolve_mate_geometry(
        body, MateAxisRef(instance_id=PART_ID, signature=rim.signature)
    )
    assert isinstance(axis, ResolvedAxis)
    turn = math.radians(30.0)
    assert axis.point.x == pytest.approx(4.0 * math.cos(turn), abs=CENTROID_TOL)
    assert axis.point.y == pytest.approx(4.0 * math.sin(turn), abs=CENTROID_TOL)
    assert axis.point.z == pytest.approx(30.0, abs=CENTROID_TOL)
    assert abs(axis.direction.z) == pytest.approx(1.0, abs=CENTROID_TOL)


# --- Cut mode: the helical gear's tooth gap ----------------------------------------

BLANK_R = 20.0
BLANK_H = 20.0
#: A slot x in [15, 25], |y| <= 2 crossing the blank's rim: the part inside the
#: disc is { 15 <= x <= sqrt(400 - y^2), |y| <= 2 }.
SLOT_AREA = 2.0 * math.sqrt(396.0) + 400.0 * math.asin(0.1) - 60.0
SLOT_MOMENT_X = (175.0 * 4.0 - 16.0 / 3.0) / 2.0  # integral of x dA over it
POCKET_DEPTH = 10.0


def _blank() -> list[dict[str, Any]]:
    return [
        _sketch(SKETCH_ID, [_circle("c1", (0.0, 0.0), BLANK_R)]),
        _extrude(EXTRUDE_ID, SKETCH_ID, BLANK_H),
    ]


def test_twisted_cut_removes_the_helical_slot() -> None:
    """The gear's route: a twisted CUT through a round blank. The blank's slice
    is rotation-invariant, so the removal is exactly slot-area x depth, and the
    removed slice centroid (x_r, 0) turns with height, so the body's centroid
    carries the mean turn — a straight cut would leave centroid.y at 0."""
    theta = math.radians(40.0)
    props = _ok_properties(
        _evaluate(
            [
                *_blank(),
                _sketch(SKETCH2_ID, _rect("k", 15.0, -2.0, 25.0, 2.0)),
                _extrude(
                    EXTRUDE2_ID,
                    SKETCH2_ID,
                    BLANK_H,
                    operation="cut",
                    twist_angle_deg=40.0,
                ),
            ]
        )
    )
    blank_volume = math.pi * BLANK_R**2 * BLANK_H
    removed = SLOT_AREA * BLANK_H
    cos_mean, sin_mean = _mean_rotation(theta)
    lever = -(SLOT_MOMENT_X * BLANK_H) / (blank_volume - removed)
    assert props.volume == pytest.approx(blank_volume - removed, abs=TWIST_TOL)
    assert props.centroid.x == pytest.approx(lever * cos_mean, abs=CENTROID_TOL)
    assert props.centroid.y == pytest.approx(lever * sin_mean, abs=CENTROID_TOL)


def test_twisted_cut_of_disjoint_regions_and_a_holed_region() -> None:
    """Cut mode keeps extrude's multi-region rule under a twist: two disjoint
    loops are two tools, and a loop with a hole leaves the hole's material (a
    helical rod standing in the pocket — hence a blind pocket, so the rod stays
    attached to the material above it)."""
    ring = [
        *_rect("a", 5.0, -3.0, 11.0, 3.0),
        _circle("ah", (8.0, 0.0), 1.0),  # hole INSIDE region a: material kept
        *_rect("b", -11.0, -3.0, -5.0, 3.0),
    ]
    props = _ok_properties(
        _evaluate(
            [
                *_blank(),
                _sketch(SKETCH2_ID, ring),
                _extrude(
                    EXTRUDE2_ID,
                    SKETCH2_ID,
                    POCKET_DEPTH,
                    operation="cut",
                    twist_angle_deg=-25.0,
                ),
            ]
        )
    )
    removed = (36.0 - math.pi + 36.0) * POCKET_DEPTH
    assert props.volume == pytest.approx(
        math.pi * BLANK_R**2 * BLANK_H - removed, abs=TWIST_TOL
    )


# --- Refusals ---------------------------------------------------------------------

#: The vanishing-twist probe runs in a CHILD process with this wall-clock limit,
#: because the defect it guards is a HANG (an infinite helix pitch never
#: returned from Edge.make_helix): in-process, a regression would stall the
#: whole suite instead of failing this test. A passing run costs a few seconds,
#: nearly all of it the child's imports.
VANISHING_TWIST_TIMEOUT_S = 120

_VANISHING_TWIST_PROBE = """
import json
import sys

from build123d import Face, Wire, Plane
from fastapi.testclient import TestClient
from geometry.kernel.twist import TwistError, twisted_extrude_face
from geometry.main import app
from loft_wire.sketch import Point2D

face = Face(Wire.make_polygon(
    [(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], close=True))
kernel = {}
for twist, distance in ((5e-324, 10.0), (1e-305, 10.0), (1e-300, 10.0),
                        (1e-160, 10.0), (1e-9, 1e150)):
    try:
        twisted_extrude_face(face, Plane.XY, distance, False, twist,
                             Point2D(x=0.0, y=0.0))
        kernel[repr(twist)] = "ok"
    except TwistError:
        kernel[repr(twist)] = "twist_error"
    except Exception as exc:
        kernel[repr(twist)] = type(exc).__name__

client = TestClient(app)
responses = [client.post("/api/v1/evaluate", json=body).content.decode()
             for body in json.loads(sys.argv[1])]
print(json.dumps({"kernel": kernel, "responses": responses}))
"""


def test_a_vanishing_twist_cannot_hang_a_worker() -> None:
    """Regression (review of d823af9): a VALID sub-normal twist made the aux
    helix pitch infinite and ``Edge.make_helix`` never returned - no evaluate
    timeout exists, and the stored row re-hung every rebuild. Both guards are
    asserted, in a child process with a timeout so a regression FAILS here
    instead of stalling the suite:

    * the wire model folds ``|twist| < 1e-9`` into "no twist", so over the API
      5e-324 is simply the plain prism, byte-identical to no twist at all;
    * the kernel refuses a non-finite / overflowing pitch as ``TwistError``
      BEFORE building the helix, for any caller (1e-300 used to escape as a
      bare ZeroDivisionError, and a vast distance overflows it too).
    """
    square = _rect("s", -5.0, -5.0, 5.0, 5.0)
    bodies = [
        {
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [
                _sketch(SKETCH_ID, square),
                _extrude(EXTRUDE_ID, SKETCH_ID, 10.0, **extra),
            ],
        }
        for extra in ({"twist_angle_deg": 5e-324}, {})
    ]
    child = subprocess.run(
        [sys.executable, "-c", _VANISHING_TWIST_PROBE, json.dumps(bodies)],
        capture_output=True,
        text=True,
        timeout=VANISHING_TWIST_TIMEOUT_S,
        check=False,
    )
    assert child.returncode == 0, child.stderr[-2000:]
    report = json.loads(child.stdout.strip().splitlines()[-1])
    assert report["kernel"] == {
        "5e-324": "twist_error",
        "1e-305": "twist_error",
        "1e-300": "twist_error",
        "1e-160": "twist_error",
        "1e-09": "twist_error",
    }
    vanishing, untwisted = report["responses"]
    assert vanishing == untwisted
    assert json.loads(vanishing)["properties"]["volume"] == pytest.approx(
        1000.0, abs=1e-9
    )


def test_a_sweep_that_comes_back_wrong_is_twist_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Cavalieri guard refuses a malformed sweep by name; the last good
    body survives.

    Ten turns in 30 mm on a 20 mm square is swept INSIDE-OUT by OCCT (volume
    -A*d). Since geometry QA F3 the kernel re-orients that exact solid, so no
    known input still reaches the guard, which is why the test takes the
    re-orientation away to produce a malformed tool on purpose. Without the
    guard, the inverted tool shipped as ``ok`` (seen at d823af9).
    """

    def keep_inside_out(solid: Solid) -> Solid:
        return solid

    monkeypatch.setattr(twist_kernel, "orient_closed_solid", keep_inside_out)
    reset_rebuild_cache()
    try:
        result = _evaluate(
            [
                *_blank(),
                _sketch(SKETCH2_ID, SQUARE),
                _extrude(EXTRUDE2_ID, SKETCH2_ID, 30.0, twist_angle_deg=3600.0),
            ]
        )
    finally:
        reset_rebuild_cache()
    assert [r.status for r in result.features] == ["ok", "ok", "ok", "error"]
    error = result.features[3].error
    assert error is not None
    assert error.code == "twist_failed"
    assert "did not sweep cleanly" in error.message
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * BLANK_R**2 * BLANK_H, abs=TWIST_TOL
    )


def test_the_cavalieri_guard_reads_the_reported_volume_integrand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review N1: the guard integrates the SAME shape the reported mass
    properties do (properties.volume_integrand), so it cannot pass a body the
    inspector reads differently."""
    seen: list[object] = []
    real = volume_integrand

    def spy(shape: Any) -> object:
        seen.append(shape)
        return real(shape)

    monkeypatch.setattr(twist_kernel, "volume_integrand", spy)
    square = Face(
        Wire.make_polygon(
            [(-10, -10, 0), (10, -10, 0), (10, 10, 0), (-10, 10, 0)], close=True
        )
    )
    twist_kernel.twisted_extrude_face(
        square, Plane.XY, 30.0, False, 90.0, Point2D(x=0.0, y=0.0)
    )
    assert seen


@pytest.mark.parametrize("twist", [3600.0, 3100.0, -3000.0, -3600.0])
def test_a_reoriented_sweep_survives_a_step_round_trip(twist: float) -> None:
    """Review B1 of da457ef: the three sweeps OCCT returns inside out (+3600,
    +3100, -3000; -3600 is the control that never was) re-import from STEP
    with +A*d, through BOTH readers. The file was always right, face for
    face; OCCT's reader turned it inside out on re-import because its
    infinite-point classification fails on a many-turn helicoid. Before the
    fix: -12000 mm^3 on the first three."""
    square = Face(
        Wire.make_polygon(
            [(-10, -10, 0), (10, -10, 0), (10, 10, 0), (-10, 10, 0)], close=True
        )
    )
    tool = twist_kernel.twisted_extrude_face(
        square, Plane.XY, 30.0, False, twist, Point2D(x=0.0, y=0.0)
    )
    step = export_step_bytes(tool).decode()
    single = import_step_solid(step)
    assert measure_shape(single).volume == pytest.approx(12000.0, abs=TWIST_TOL)
    [product] = read_step_assembly(step).products
    assert measure_shape(product.body).volume == pytest.approx(12000.0, abs=TWIST_TOL)


@pytest.mark.parametrize(
    "extra",
    [
        {"twist_angle_deg": 3600.5},
        {"twist_angle_deg": -3601.0},
        {"twist_angle_deg": "NaN"},
        {"twist_angle_deg": 10.0, "twist_center": {"x": "Infinity", "y": 0.0}},
    ],
)
def test_out_of_range_twist_is_refused_at_validation(extra: dict[str, Any]) -> None:
    response = client.post(
        "/api/v1/evaluate",
        json={
            "part_id": str(PART_ID),
            "tree_version": 1,
            "features": [
                _sketch(SKETCH_ID, SQUARE),
                _extrude(EXTRUDE_ID, SKETCH_ID, 30.0, **extra),
            ],
        },
    )
    assert response.status_code == 422, response.text


# --- Determinism --------------------------------------------------------------------


def test_twisted_cut_response_is_byte_deterministic() -> None:
    """RESEARCH §9 on the twisted path: same tree, identical response bytes,
    mesh id included. (Cross-interpreter determinism: the golden's gate.)"""
    payload = {
        "part_id": str(PART_ID),
        "tree_version": 1,
        "features": [
            *_blank(),
            _sketch(SKETCH2_ID, _rect("k", 15.0, -2.0, 25.0, 2.0)),
            _extrude(
                EXTRUDE2_ID, SKETCH2_ID, BLANK_H, operation="cut", twist_angle_deg=40.0
            ),
        ],
    }
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
