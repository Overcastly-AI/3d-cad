"""Joint-origin resolution (S4a, RESEARCH §21): each origin kind to a frame.

Resolves real origins against the committed plate part (the
sketch-extrude-plate-2holes golden: 40 x 25 x 10, r5 through-holes at
(12, 12.5) and (28, 12.5)) and checks the frame rules by hand: the face centre
with its outward normal, a hole rim's centre with its axis pointing OUT of the
face it bounds, an edge's canonical start / mid / end with the tangent from
start to end, the X reference rule, and flip / quarter_turns.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import itertools
import uuid
from pathlib import Path

import numpy as np
import pytest
from build123d import GeomType, Solid
from geometry.assembly import AssemblyDefinitionError, ResolvedFrame
from geometry.assembly.joint_math import build_frame, reference_x
from geometry.assembly.joint_origins import resolve_joint_origin
from geometry.features import evaluate_tree
from geometry.kernel.edges import edge_signature_dto
from geometry.kernel.faces import (
    SubshapeUnresolvedError,
    face_signature_dto,
    planar_faces,
)
from loft_wire.features import (
    EdgeSignature,
    EvaluateTreeRequest,
    PlanarFaceSignature,
)
from loft_wire.geometry import Vec3
from loft_wire.joints import JointEdgePoint, JointOrigin
from OCP.BRepAdaptor import BRepAdaptor_Curve

#: Resolution tolerance (mm / unit-vector components): the frames come from the
#: exact B-rep of an axis-aligned plate, so they are exact to float64 round-off.
FRAME_TOL = 1e-9

_PLATE_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens/sketch-extrude-plate-2holes-40x25x10/model.json"
)


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


@pytest.fixture(scope="module")
def body() -> Solid:
    request = EvaluateTreeRequest.model_validate_json(
        _PLATE_MODEL.read_text(encoding="utf-8")
    )
    solid = evaluate_tree(request).body
    assert isinstance(solid, Solid)
    return solid


def _face_sig(body: Solid, nz: float) -> PlanarFaceSignature:
    for record in planar_faces(body):
        if abs(record.signature.normal.z - nz) < FRAME_TOL:
            sig = face_signature_dto(record.face)
            assert sig is not None
            return sig
    raise AssertionError(f"no planar face with normal z = {nz}")


def _hole_sig(body: Solid, cx: float, cy: float, cz: float) -> EdgeSignature:
    for edge in body.edges():
        if edge.geom_type != GeomType.CIRCLE:
            continue
        loc = BRepAdaptor_Curve(edge.wrapped).Circle().Location()
        centre = np.array([loc.X(), loc.Y(), loc.Z()])
        if centre == pytest.approx(np.array([cx, cy, cz]), abs=FRAME_TOL):
            return edge_signature_dto(edge)
    raise AssertionError(f"no circular edge at ({cx}, {cy}, {cz})")


def _v(vec: Vec3) -> np.ndarray:
    return np.array([vec.x, vec.y, vec.z], dtype=np.float64)


def _assert_frame(
    frame: ResolvedFrame,
    origin: tuple[float, float, float],
    z: tuple[float, float, float],
    x: tuple[float, float, float],
) -> None:
    assert _v(frame.origin) == pytest.approx(np.array(origin), abs=FRAME_TOL)
    assert _v(frame.z) == pytest.approx(np.array(z), abs=FRAME_TOL)
    assert _v(frame.x) == pytest.approx(np.array(x), abs=FRAME_TOL)


def _line_sig(
    body: Solid, start: tuple[float, float, float], end: tuple[float, float, float]
) -> EdgeSignature:
    for edge in body.edges():
        if edge.geom_type != GeomType.LINE:
            continue
        sig = edge_signature_dto(edge)
        if _v(sig.end_a) == pytest.approx(np.array(start), abs=FRAME_TOL) and _v(
            sig.end_b
        ) == pytest.approx(np.array(end), abs=FRAME_TOL):
            return sig
    raise AssertionError(f"no straight edge {start} -> {end}")


def test_face_centre_is_the_centroid_with_the_outward_normal(body: Solid) -> None:
    top = JointOrigin(
        instance_id=iid(1), kind="face_centre", signature=_face_sig(body, 1.0)
    )
    bottom = JointOrigin(
        instance_id=iid(1), kind="face_centre", signature=_face_sig(body, -1.0)
    )
    # The top face is the 40 x 25 rectangle minus two equal holes placed
    # symmetrically about x = 20, so its area centroid is the rectangle's.
    _assert_frame(resolve_joint_origin(body, top), (20, 12.5, 10), (0, 0, 1), (1, 0, 0))
    _assert_frame(
        resolve_joint_origin(body, bottom), (20, 12.5, 0), (0, 0, -1), (1, 0, 0)
    )


def test_face_centre_follows_a_resized_face(body: Solid) -> None:
    """Picked on the 40-wide plate, resolved on the part widened to 60: the
    top face re-matches (coplanar tier) and the origin is its NEW centre
    (30, 12.5, 10), as a Fusion face-centre origin moves with the face, not
    the stored (20, 12.5, 10) a sketch plane keeps."""
    widened = Solid.make_box(60.0, 25.0, 10.0)
    origin = JointOrigin(
        instance_id=iid(1), kind="face_centre", signature=_face_sig(body, 1.0)
    )
    _assert_frame(
        resolve_joint_origin(widened, origin), (30, 12.5, 10), (0, 0, 1), (1, 0, 0)
    )


def test_circle_centre_axis_points_out_of_the_face_it_bounds(body: Solid) -> None:
    """The top and bottom rims of one hole share a gp_Circ axis line, but a
    joint origin's Z points OUT of the body: +Z on the top rim, -Z on the
    bottom rim (as a Fusion / Onshape origin on a hole edge does)."""
    for z_rim, z_axis in ((10.0, 1.0), (0.0, -1.0)):
        for cx, cy in ((12.0, 12.5), (28.0, 12.5)):
            origin = JointOrigin(
                instance_id=iid(1),
                kind="circle_centre",
                signature=_hole_sig(body, cx, cy, z_rim),
            )
            _assert_frame(
                resolve_joint_origin(body, origin),
                (cx, cy, z_rim),
                (0, 0, z_axis),
                (1, 0, 0),
            )


@pytest.mark.parametrize(
    ("at", "point"),
    [("start", (0, 0, 10)), ("mid", (20, 0, 10)), ("end", (40, 0, 10))],
)
def test_edge_point_start_mid_end_with_the_tangent(
    body: Solid, at: JointEdgePoint, point: tuple[float, float, float]
) -> None:
    origin = JointOrigin(
        instance_id=iid(1),
        kind="edge_point",
        at=at,
        signature=_line_sig(body, (0, 0, 10), (40, 0, 10)),
    )
    # Z = tangent start -> end = +X; X = reference_x(+X) = +Y (Y wins the tie).
    _assert_frame(resolve_joint_origin(body, origin), point, (1, 0, 0), (0, 1, 0))


def test_edge_point_is_independent_of_the_edge_orientation(body: Solid) -> None:
    """Every straight edge of the plate: start is the signature's canonical
    end_a, end is end_b and Z points from one to the other, whichever way OCCT
    happened to orient the edge (some of the plate's edges run reversed)."""
    reversed_edges = 0
    for edge in body.edges():
        if edge.geom_type != GeomType.LINE:
            continue
        sig = edge_signature_dto(edge)
        curve = BRepAdaptor_Curve(edge.wrapped)
        first = curve.Value(curve.FirstParameter())
        if _v(Vec3(x=first.X(), y=first.Y(), z=first.Z())) != pytest.approx(
            _v(sig.end_a), abs=FRAME_TOL
        ):
            reversed_edges += 1
        direction = _v(sig.end_b) - _v(sig.end_a)
        direction /= np.linalg.norm(direction)
        ends: tuple[tuple[JointEdgePoint, Vec3], ...] = (
            ("start", sig.end_a),
            ("end", sig.end_b),
        )
        for at, point in ends:
            frame = resolve_joint_origin(
                body,
                JointOrigin(
                    instance_id=iid(1), kind="edge_point", at=at, signature=sig
                ),
            )
            assert _v(frame.origin) == pytest.approx(_v(point), abs=FRAME_TOL)
            assert _v(frame.z) == pytest.approx(direction, abs=FRAME_TOL)
    assert reversed_edges > 0, "the plate no longer has a reversed edge to test"


def test_flip_reverses_z_and_keeps_x(body: Solid) -> None:
    """flip is a half turn about the frame's X: Z and Y reverse, X is kept."""
    origin = JointOrigin(
        instance_id=iid(1),
        kind="face_centre",
        signature=_face_sig(body, 1.0),
        flip=True,
    )
    _assert_frame(
        resolve_joint_origin(body, origin), (20, 12.5, 10), (0, 0, -1), (1, 0, 0)
    )


@pytest.mark.parametrize(
    ("turns", "x"),
    [(0, (1, 0, 0)), (1, (0, 1, 0)), (2, (-1, 0, 0)), (3, (0, -1, 0))],
)
def test_quarter_turns_rotate_x_about_z(
    body: Solid, turns: int, x: tuple[float, float, float]
) -> None:
    """Right-handed 90° steps about the frame's +Z (here the top face's +Z)."""
    origin = JointOrigin(
        instance_id=iid(1),
        kind="face_centre",
        signature=_face_sig(body, 1.0),
        quarter_turns=turns,
    )
    _assert_frame(resolve_joint_origin(body, origin), (20, 12.5, 10), (0, 0, 1), x)


def test_quarter_turns_follow_the_flipped_z(body: Solid) -> None:
    """Flip first, then turn about the FLIPPED Z (-Z): +X turns to -Y."""
    origin = JointOrigin(
        instance_id=iid(1),
        kind="face_centre",
        signature=_face_sig(body, 1.0),
        flip=True,
        quarter_turns=1,
    )
    _assert_frame(
        resolve_joint_origin(body, origin), (20, 12.5, 10), (0, 0, -1), (0, -1, 0)
    )


def test_every_flip_and_turn_is_a_proper_right_handed_frame() -> None:
    z = np.array([0.3, -0.5, 0.8], dtype=np.float64)
    for flip, turns in itertools.product((False, True), range(4)):
        frame = build_frame(np.zeros(3), z, flip=flip, quarter_turns=turns)
        assert frame.rot.T @ frame.rot == pytest.approx(np.eye(3), abs=FRAME_TOL)
        assert float(np.linalg.det(frame.rot)) == pytest.approx(1.0, abs=FRAME_TOL)
        sign = -1.0 if flip else 1.0
        assert frame.z == pytest.approx(sign * z / np.linalg.norm(z), abs=FRAME_TOL)


def test_reference_x_rule_and_its_round_off_tie_band() -> None:
    """The least-aligned axis, ties X < Y < Z; round-off on an axis-aligned Z
    does not swap the pick (without the band, (1e-17, 0, 1) would pick Y)."""
    assert reference_x(np.array([0.0, 0.0, 1.0])) == pytest.approx([1, 0, 0])
    assert reference_x(np.array([0.0, 0.0, -1.0])) == pytest.approx([1, 0, 0])
    assert reference_x(np.array([1.0, 0.0, 0.0])) == pytest.approx([0, 1, 0])
    assert reference_x(np.array([0.0, 1.0, 0.0])) == pytest.approx([1, 0, 0])
    noisy = np.array([1e-17, 0.0, 1.0])
    assert reference_x(noisy / np.linalg.norm(noisy)) == pytest.approx([1, 0, 0])
    tilted = np.array([0.6, 0.0, 0.8])
    # Y is the least aligned (0 vs 0.6 vs 0.8): X = +Y, already perpendicular.
    assert reference_x(tilted) == pytest.approx([0, 1, 0])


def test_unresolvable_origin_is_a_definition_error_with_the_cause(
    body: Solid,
) -> None:
    stale = _line_sig(body, (0, 0, 10), (40, 0, 10)).model_copy(
        update={
            "end_a": Vec3(x=500.0, y=0.0, z=10.0),
            "end_b": Vec3(x=540.0, y=0.0, z=10.0),
            "midpoint": Vec3(x=520.0, y=0.0, z=10.0),
        }
    )
    origin = JointOrigin(
        instance_id=iid(1), kind="edge_point", at="start", signature=stale
    )
    with pytest.raises(AssemblyDefinitionError) as info:
        resolve_joint_origin(body, origin)
    assert isinstance(info.value.__cause__, SubshapeUnresolvedError)
