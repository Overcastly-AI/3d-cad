# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""The bike frame from ONE skeleton: four Pipes, one body (PIPE-ALONG-PATH).

The acceptance of the backlog item, against an independent build: the down,
seat, top and head tubes are four Pipes on one skeleton sketch, fused into one
valid body that matches a plain-build123d frame (hand-computed joints, tubes as
cylinders minus bores, no sweep and no sketch solve) to 1e-4 in volume and
bounding box with an empty two-way difference; and editing the head angle
73 -> 72 deg in the skeleton rebuilds every tube and matches the twin at 72.
The golden ``frame-bike-4-pipes-one-skeleton-head73`` runs the parametrized
gates (mass properties, topology, determinism, STEP round trip).
"""

import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType

import pytest
from build123d import Plane, Solid, Vector, export_step, import_step
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from loft_wire.features import EvaluateTreeRequest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_pipe_builder_frame", Path(__file__).with_name("_pipe_builder.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pb = _builder()
GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "frame-bike-4-pipes-one-skeleton-head73"
)
#: The tubes and the skeleton joints at their two ends.
ENDS = {
    "down": ("bb", "ht_bottom"),
    "seat": ("bb", "st_top"),
    "top": ("st_top", "ht_top"),
    "head": ("ht_top", "ht_bottom"),
}


def _tube(a: Vector, b: Vector, od: float, wall: float) -> Solid:
    axis = b - a
    plane = Plane(origin=a, z_dir=axis.normalized())
    outer = Solid.make_cylinder(od / 2, axis.length, plane)
    bore = Solid.make_cylinder(od / 2 - wall, axis.length, plane)
    return outer.cut(bore).solids()[0]


def independent_frame(head_angle_deg: float) -> Solid:
    """The frame in plain build123d from the joints worked out by hand."""
    joints = {
        name: Vector(x, 0.0, z)
        for name, (x, z) in pb.skeleton_points(head_angle_deg).items()
    }
    tubes = [_tube(joints[a], joints[b], *pb.TUBES[n]) for n, (a, b) in ENDS.items()]
    body = tubes[0].fuse(*tubes[1:])
    (solid,) = body.clean().solids()
    return solid


def _evaluate(head_angle_deg: float) -> Solid:
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(pb.bike_frame(head_angle_deg))
    )
    statuses = [(r.feature_id, r.status, r.error) for r in evaluation.result.features]
    assert all(status == "ok" for _, status, _ in statuses), statuses
    assert evaluation.body is not None
    (solid,) = evaluation.body.solids()
    return solid


@pytest.mark.parametrize("head_angle_deg", [73.0, 72.0])
def test_four_pipes_on_one_skeleton_are_the_independent_frame(
    head_angle_deg: float,
) -> None:
    mine = _evaluate(head_angle_deg)
    twin = independent_frame(head_angle_deg)
    assert mine.is_valid
    ours, theirs = measure_shape(mine), measure_shape(twin)
    assert ours.topology.shells == 1
    assert ours.volume == pytest.approx(theirs.volume, rel=1e-4)
    # Observed 3e-9 relative; held far tighter than the acceptance's 1e-4.
    assert ours.volume == pytest.approx(theirs.volume, rel=1e-8)
    for got, want in (
        (ours.bounding_box.min, theirs.bounding_box.min),
        (ours.bounding_box.max, theirs.bounding_box.max),
    ):
        assert (got.x, got.y, got.z) == pytest.approx(
            (want.x, want.y, want.z), abs=1e-4
        )
    assert float(mine.cut(twin).volume) <= 1e-6
    assert float(twin.cut(mine).volume) <= 1e-6


def test_the_head_angle_edit_moves_the_head_and_down_tubes() -> None:
    """73 -> 72 deg: the head tube's bottom moves forward and down by the hand
    numbers, so the head and down tubes change and the seat and top tubes do
    not; the frame volume moves by the two tubes' own change plus the joints'."""
    at73, at72 = (pb.skeleton_points(a) for a in (73.0, 72.0))
    assert at72["ht_bottom"][0] - at73["ht_bottom"][0] == pytest.approx(
        150 * (math.cos(math.radians(72)) - math.cos(math.radians(73)))
    )
    assert at72["st_top"] == at73["st_top"] and at72["ht_top"] == at73["ht_top"]
    before, after = _evaluate(73.0), _evaluate(72.0)
    box_before = measure_shape(before).bounding_box
    box_after = measure_shape(after).bounding_box
    # The head tube's bottom cap sets x_max: 433.856 + 25 sin 73 -> 436.353 + 25 sin 72.
    assert box_after.max.x - box_before.max.x == pytest.approx(
        at72["ht_bottom"][0]
        + 25 * math.sin(math.radians(72))
        - at73["ht_bottom"][0]
        - 25 * math.sin(math.radians(73)),
        abs=1e-6,
    )
    assert float(after.volume) != pytest.approx(float(before.volume), abs=1.0)


def test_the_golden_is_this_tree() -> None:
    """The golden's model.json is exactly the builder's tree, so the test above
    and the golden gates hold the same frame."""
    assert json.loads((GOLDEN / "model.json").read_text()) == pb.bike_frame()


def _plain_step_roundtrip(solid: Solid, tmp_path: Path) -> Solid:
    """build123d's own export_step / import_step: no Loft code on the path."""
    path = tmp_path / "plain.step"
    assert export_step(solid, str(path))
    (reread,) = import_step(str(path)).solids()
    return reread


def _area_adaptive(solid: Solid) -> float:
    """Surface area by OCCT's ADAPTIVE rule (eps 1e-9), not the product's
    fixed-order one, to tell a face that moved from an integral that moved."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(solid.wrapped, props, 1e-9)
    return props.Mass()


def test_the_step_drift_is_occts_not_loft_geometry(
    tmp_path: Path, roundtrip_tol: float
) -> None:
    """The executable justification of the golden's ``roundtrip_tolerance``
    (geometry-QA sign-off 2026-10-16). The plain-build123d twin, which shares no
    Loft code, round-tripped through build123d's own STEP writer and reader,
    drifts in volume far past ROUNDTRIP_TOL: the drift is OCCT's STEP
    re-approximation of the trimmed tube-tube faces, not the Pipe feature. The
    tree body's larger AREA drift is the product's fixed-order area integral
    re-evaluated on those faces; the adaptive rule sees the faces move by under
    1e-5 mm^2. Measured (build123d 0.11.1 / OCCT 7.9): twin volume +8.65e-4 mm^3,
    area -1.6e-4 mm^2; tree volume +1.6e-5, area -6.09e-3 (adaptive -2.7e-6);
    the same through Loft's export_step_bytes. The allowance keeps >= 4x over
    the worst of these."""
    allowance = json.loads((GOLDEN / "expected.json").read_text())[
        "roundtrip_tolerance"
    ]
    worst = 0.0
    for name, solid in (("twin", independent_frame(73.0)), ("tree", _evaluate(73.0))):
        reread = _plain_step_roundtrip(solid, tmp_path)
        before, after = measure_shape(solid), measure_shape(reread)
        assert after.topology == before.topology, name
        d_volume = abs(after.volume - before.volume)
        d_area = abs(after.surface_area - before.surface_area)
        worst = max(worst, d_volume, d_area)
        if name == "twin":
            # No Loft code built or exported it, and it still breaks the bound
            # (its centroid moves 5.1e-7 mm too, past ROUNDTRIP_TOL as well).
            assert d_volume > 100 * roundtrip_tol, d_volume
            continue
        # The tree: the faces themselves barely move; the integral does. And
        # the centroid and bounds hold ROUNDTRIP_TOL with no allowance.
        moved = abs(_area_adaptive(reread) - _area_adaptive(solid))
        assert moved < 1e-5, moved
        for got, want in (
            (after.centroid, before.centroid),
            (after.bounding_box.min, before.bounding_box.min),
            (after.bounding_box.max, before.bounding_box.max),
        ):
            assert (got.x, got.y, got.z) == pytest.approx(
                (want.x, want.y, want.z), abs=roundtrip_tol
            )
    assert 4 * worst <= allowance, (worst, allowance)
