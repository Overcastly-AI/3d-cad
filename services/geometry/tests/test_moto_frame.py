# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false
"""Motorcycle cradle frame — the founder's standing tube-frame test case.

The golden ``frame-moto-cradle-tube-od25.4-t1.6`` runs every parametrized gate
(mass properties, topology, determinism, STEP round trip) from
``test_goldens.py`` / ``test_step_roundtrip.py``. This file adds the checks a
golden cannot express, each against a number derived OUTSIDE the code under
test:

* an independent build123d build of the same frame (closed filleted ring swept
  in ONE piece, where the tree sweeps two open halves) -- volume and the
  two-way boolean difference;
* the Pappus volume of the swept rail, annulus area x path length;
* the two strict xfails that pin what the tree cannot do yet (BACKLOG Notes,
  2026-10-07 "moto frame").
"""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Face,
    Plane,
    Solid,
    Vector,
    Wire,
)
from geometry.features import evaluate_tree
from geometry.harness import load_model_request
from geometry.kernel import measure_shape
from geometry.kernel.lumps import lump_count
from geometry.kernel.types import BodyShape
from loft_wire.features import EvaluateTreeRequest

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "frame-moto-cradle-tube-od25.4-t1.6"
)

# The spec, in mm (X forward, Z up, frame symmetric about the XZ plane).
TUBE_OD = 25.4
TUBE_ID = 22.2
BEND_R = 80.0
RAIL_Y = 110.0
#: The cross tubes end 6 mm short of the rail centrelines. Ending ON the centreline
#: puts the tube's end face in the plane where the two equal-diameter outer
#: cylinders' intersection curves cross (a singular point), and OCCT's fuse and
#: its STEP round trip both wander by 1e-2 mm^3 there.
TUBE_Y = 104.0
RAIL_CORNERS_XZ = [
    (0.0, 520.0),
    (-520.0, 560.0),
    (-760.0, 600.0),
    (-560.0, 300.0),
    (-80.0, 120.0),
]


def _front_apex_xz() -> tuple[float, float]:
    """Where the rail centreline passes nearest the front corner (0, 520).

    Closed form for a fillet of radius R in a corner whose neighbours subtend
    the angle 2*phi: the arc's centre sits R/sin(phi) from the corner along the
    bisector, so the arc's apex is R/sin(phi) - R from the corner towards it.
    """
    corner = Vector(*RAIL_CORNERS_XZ[0])
    toward = [Vector(*RAIL_CORNERS_XZ[i]) - corner for i in (1, -1)]
    a, b = (v.normalized() for v in toward)
    bisector = (a + b).normalized()
    phi = math.acos(max(-1.0, min(1.0, a.dot(b)))) / 2
    apex = corner + bisector * (BEND_R / math.sin(phi) - BEND_R)
    return (apex.X, apex.Y)


#: Four Y cross tubes. Three sit on the rail centreline: two at corners that the
#: fillet barely moves, and (-300, 202.5), the point of the straight lower run
#: from (-560,300) to (-80,120) (slope -0.375: 300 - 0.375 * 260). The fourth is
#: the front apex, through whose centre the steering-head axis passes.
CROSS_TUBES_XZ = [(-520.0, 560.0), (-560.0, 300.0), (-300.0, 202.5), _front_apex_xz()]
HEAD_OD, HEAD_ID, HEAD_LEN = 50.0, 32.0, 160.0
HEAD_CENTRE_XZ = CROSS_TUBES_XZ[3]
HEAD_RAKE_DEG = 25.0

ANNULUS_AREA = math.pi * ((TUBE_OD / 2) ** 2 - (TUBE_ID / 2) ** 2)


def _tree() -> EvaluateTreeRequest:
    request = load_model_request((GOLDEN / "model.json").read_text(encoding="utf-8"))
    assert isinstance(request, EvaluateTreeRequest)
    return request


def _prefix(request: EvaluateTreeRequest, last_id: int) -> EvaluateTreeRequest:
    kept = [f for f in request.features if int(str(f.id)[-12:], 16) <= last_id]
    return request.model_copy(update={"features": kept})


def _expected() -> dict[str, Any]:
    return json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))


def _annulus(plane: Plane, outer: float, inner: float) -> Face:
    return Face(
        Wire.make_circle(outer / 2, plane), [Wire.make_circle(inner / 2, plane)]
    )


def _rail_path() -> Wire:
    """The closed rail path: the five corners, every corner filleted R80."""
    pts = [Vector(x, RAIL_Y, z) for x, z in RAIL_CORNERS_XZ]
    outline = Face(Wire.make_polygon(pts, close=True))
    filleted = outline.fillet_2d(BEND_R, list(outline.vertices()))
    return filleted.outer_wire()


def _independent_frame() -> tuple[BodyShape, float]:
    """The same frame built in build123d alone; returns (solid, closed path length).

    One closed ring sweep (the tree sweeps two open halves butted end to end),
    mirrored about XZ, three Y tubes, one revolved-by-construction head tube
    (a hollow cylinder on a plane whose normal is the raked axis).
    """
    # The tubes stop at TUBE_Y: a tube that ends ON the rail axis (equal diameters,
    # axes crossing) made OCCT's fuse of the one-piece ring sweep return a negative
    # volume, and a fuzzy fuse is no fix (it moves the volume by up to 1 mm^3).
    path = _rail_path()
    start = Plane(path.location_at(0))
    rail = Solid.sweep(_annulus(start, TUBE_OD, TUBE_ID), path)
    frame = rail.fuse(rail.mirror(Plane.XZ))
    for x, z in CROSS_TUBES_XZ:
        plane = Plane(origin=(x, TUBE_Y, z), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        tube = Solid.extrude(
            _annulus(plane, TUBE_OD, TUBE_ID), plane.z_dir * (2 * TUBE_Y)
        )
        frame = frame.fuse(tube)
    rake = math.radians(HEAD_RAKE_DEG)
    axis = Vector(-math.sin(rake), 0, math.cos(rake))
    base = Vector(HEAD_CENTRE_XZ[0], 0, HEAD_CENTRE_XZ[1]) - axis * (HEAD_LEN / 2)
    head_plane = Plane(origin=base, z_dir=axis)
    head = Solid.make_cylinder(HEAD_OD / 2, HEAD_LEN, head_plane).cut(
        Solid.make_cylinder(HEAD_ID / 2, HEAD_LEN, head_plane)
    )
    frame = frame.fuse(head)
    return frame, path.length


def test_golden_matches_independent_build123d_frame() -> None:
    """Volume within the golden's tolerance, and the boolean difference empty."""
    expected = _expected()
    tolerance = expected["tolerance"]
    evaluation = evaluate_tree(_tree())
    assert evaluation.body is not None
    independent, _ = _independent_frame()

    mine = measure_shape(evaluation.body).volume
    # Same integrator on both sides (measure_shape, adaptive VOLUME_EPS): the
    # comparison is of the two BUILDS, not of two quadratures.
    theirs = measure_shape(independent).volume
    assert mine == pytest.approx(theirs, abs=tolerance)
    assert expected["properties"]["volume"] == pytest.approx(theirs, abs=tolerance)

    lost_volume = float(evaluation.body.cut(independent).volume)
    gained_volume = float(independent.cut(evaluation.body).volume)
    assert lost_volume <= tolerance, (
        f"tree has {lost_volume} mm^3 the build123d frame lacks"
    )
    assert gained_volume <= tolerance, (
        f"build123d frame has {gained_volume} mm^3 the tree lacks"
    )


def test_swept_rail_volume_is_pappus() -> None:
    """Annulus area x path length, to 1e-6 relative.

    The path is tangent-continuous and the bend (R80) is far larger than the tube
    radius (12.7), so Pappus' centroid theorem is exact for the swept solid. The
    tree's two open halves fused must equal one ring sweep of the closed
    path; the length comes from the independent build123d wire, not the tree.
    """
    request = _tree()
    evaluation = evaluate_tree(_prefix(request, 0x0F))  # datums, sketches, 2 sweeps
    assert evaluation.body is not None
    rail_volume = measure_shape(evaluation.body).volume
    expected = ANNULUS_AREA * _rail_path().length
    assert rail_volume == pytest.approx(expected, rel=1e-6)


def test_frame_is_one_lump_and_so_is_the_independent_twin() -> None:
    """Every member overlaps real tube material: one lump, in both builds."""
    evaluation = evaluate_tree(_tree())
    assert evaluation.body is not None
    assert lump_count(evaluation.body) == 1
    independent, _ = _independent_frame()
    assert lump_count(independent) == 1


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG Notes 2026-10-07 'moto frame': an in-chain add that bridges "
    "the two lumps a mirror leaves is refused (boolean_failed, 'produced 1 lumps "
    "from a 2-lump body') -- Fusion/SolidWorks join them",
)
def test_cross_tube_extrude_joins_the_mirrored_rails() -> None:
    request = _prefix(_tree(), 0x15)
    # The golden joins the tube with merge=False + a boolean union; the user's
    # literal flow is a plain merging extrude after the mirror.
    features = copy.deepcopy(request.model_dump(mode="json")["features"])
    for item in features:
        if item["feature"]["type"] == "extrude":
            item["feature"]["params"].pop("merge", None)
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {**request.model_dump(mode="json"), "features": features}
        )
    )
    assert all(r.status == "ok" for r in evaluation.result.features)
    assert evaluation.body is not None
    assert lump_count(evaluation.body) == 1


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG Notes 2026-10-07 'moto frame': a sweep along a closed, "
    "tangent-continuous path is refused (sweep_path_closed); the golden sweeps "
    "two open halves instead",
)
def test_closed_loop_rail_sweeps_in_one_piece() -> None:
    request = _tree()
    data = request.model_dump(mode="json")
    by_id = {f["id"]: f for f in data["features"]}
    upper = by_id["00000000-0000-0000-0000-00000000000a"]["feature"]["params"]
    lower = by_id["00000000-0000-0000-0000-00000000000d"]["feature"]["params"]
    # Close the loop: the upper half's sketch plus the lower half's entities.
    upper["entities"] = upper["entities"] + lower["entities"]
    keep = [f for f in data["features"] if int(f["id"][-12:], 16) <= 0x0C]
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate({**data, "features": keep})
    )
    assert all(r.status == "ok" for r in evaluation.result.features), [
        (str(r.feature_id)[-4:], r.error.code)
        for r in evaluation.result.features
        if r.error
    ]
