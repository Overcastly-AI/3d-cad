"""Joint solving (S4a, RESEARCH §21): rigid, revolute and slider joints.

Two layers. The SOLVER is exercised against synthetic joint frames whose
answer is known by construction (the RotX(180°) opposed-Z alignment, the
offset/angle shift, the free axis at the seed or driven by the value, DOF from
the hard rows only, the snap of either side, the numeric fallback). The
PIPELINE is exercised on the two joint goldens' real plates
(``goldens-assembly/assembly-hinge-revolute`` and ``assembly-slider``): the
hinge's far edge distance from its axis, the slider's exact 80 mm travel, a
joint conflicting with a legacy mate named in the diagnosis, and the motions
S4a does not solve dropped as ``mate_unsupported``.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

import numpy as np
import pytest
from geometry.assembly import (
    AssemblySolveInput,
    AssemblySolveResult,
    ResolvedAxis,
    ResolvedFrame,
    RigidBodyAssemblySolver,
    SolverInstance,
    SolverMate,
    evaluate_assembly,
)
from geometry.assembly.transform import Pose, quat_from_rotvec
from loft_wire.assemblies import (
    ConcentricMate,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    EvaluatedMate,
    MateAxisRef,
)
from loft_wire.features import EdgeSignature, PlanarFaceSignature
from loft_wire.geometry import Vec3
from loft_wire.joints import JointMate, JointMotion, JointOrigin, JointValue

#: Closed-form joint placements are exact to float64 round-off (the goldens
#: measured <= 5.4e-15 mm); the numeric fallback converges below SATISFIED_TOL.
#: Same per-suite posture as test_assembly_solver.ASSEMBLY_TOL.
EXACT_TOL = 1e-9
NUMERIC_TOL = 1e-6

SOLVER = RigidBodyAssemblySolver()
_GOLDENS = Path(__file__).resolve().parent.parent / "goldens-assembly"


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _v3(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=x, y=y, z=z)


def pose(t: tuple[float, float, float], rotvec: tuple[float, float, float]) -> Pose:
    return Pose(
        t=np.array(t, dtype=np.float64),
        q=quat_from_rotvec(np.array(rotvec, dtype=np.float64)),
    )


def _face_origin(n: int) -> JointOrigin:
    # The solver ignores the signature (resolution happened upstream).
    return JointOrigin(
        instance_id=iid(n),
        kind="face_centre",
        signature=PlanarFaceSignature(
            normal=_v3(0.0, 0.0, 1.0), centroid=_v3(0.0, 0.0, 0.0), area_mm2=1.0
        ),
    )


def _frame(
    origin: tuple[float, float, float],
    z: tuple[float, float, float],
    x: tuple[float, float, float],
) -> ResolvedFrame:
    return ResolvedFrame(origin=_v3(*origin), z=_v3(*z), x=_v3(*x))


def _joint(
    motion: JointMotion,
    frame_a: ResolvedFrame,
    frame_b: ResolvedFrame,
    *,
    mate_id: int = 7001,
    order: int = 0,
    value: JointValue | None = None,
    offset_mm: float = 0.0,
    angle_deg: float = 0.0,
) -> SolverMate:
    return SolverMate(
        mate_id=iid(mate_id),
        order_index=order,
        mate=JointMate(
            motion=motion,
            a=_face_origin(1),
            b=_face_origin(2),
            offset_mm=offset_mm,
            angle_deg=angle_deg,
            value=value or JointValue(),
        ),
        geometry=(frame_a, frame_b),
    )


def _problem(
    mates: list[SolverMate],
    b_seed: Pose,
    *,
    a_seed: Pose | None = None,
    ground_b: bool = False,
) -> AssemblySolveInput:
    return AssemblySolveInput(
        instances=[
            SolverInstance(
                instance_id=iid(1),
                grounded=not ground_b,
                placement=(a_seed or Pose.identity()).to_placement(),
            ),
            SolverInstance(
                instance_id=iid(2), grounded=ground_b, placement=b_seed.to_placement()
            ),
        ],
        mates=mates,
    )


def _pose_of(result: AssemblySolveResult, n: int) -> Pose:
    for placed in result.placements:
        if placed.instance_id == iid(n):
            return Pose.from_placement(placed.placement)
    raise AssertionError(f"no placement for instance {n}")


def _assert_pose(got: Pose, want: Pose, tol: float) -> None:
    assert got.t == pytest.approx(want.t, abs=tol)
    assert got.matrix() == pytest.approx(want.matrix(), abs=tol)


#: A's joint frame at (1, 2, 3) facing +Z; B's (B-local) at its origin facing -Z.
#: At rot 0 the opposed-Z alignment leaves B's body unrotated.
_FRAME_A = _frame((1.0, 2.0, 3.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
_FRAME_B = _frame((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0))
_SEED_B = pose((7.0, -4.0, 9.0), (0.0, 0.0, math.radians(40.0)))


# --- solver: placement ----------------------------------------------------------


def test_rigid_joint_with_offset_and_angle_is_fully_placed() -> None:
    """B's frame sits offset 5 along A's Z, turned 30° about it, Z opposed:
    B's body is RotZ(30°) at (1, 2, 3 + 5). Rigid leaves 0 DOF."""
    result = SOLVER.solve(
        _problem(
            [_joint("rigid", _FRAME_A, _FRAME_B, offset_mm=5.0, angle_deg=30.0)],
            _SEED_B,
        )
    )
    assert (result.status, result.method, result.diagnosis) == (
        "well_constrained",
        "closed_form",
        None,
    )
    _assert_pose(
        _pose_of(result, 2), pose((1.0, 2.0, 8.0), (0.0, 0.0, math.radians(30))), 1e-12
    )
    (state,) = result.joint_states
    assert (state.rot_deg, state.lin_mm, state.at_limit) == (None, None, False)
    assert state.axis_world == _v3(0.0, 0.0, 1.0)


def test_undriven_revolute_has_one_dof_and_keeps_the_seed_angle() -> None:
    result = SOLVER.solve(_problem([_joint("revolute", _FRAME_A, _FRAME_B)], _SEED_B))
    assert result.status == "under_constrained"
    assert result.method == "closed_form"
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    _assert_pose(
        _pose_of(result, 2),
        pose((1.0, 2.0, 3.0), (0.0, 0.0, math.radians(40.0))),
        EXACT_TOL,
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(40.0, abs=EXACT_TOL)
    assert state.lin_mm is None


@pytest.mark.parametrize(
    ("value", "reading"),
    [(90.0, 90.0), (-90.0, -90.0), (180.0, 180.0), (-180.0, 180.0), (270.0, -90.0)],
)
def test_driven_revolute_is_placed_but_still_reports_one_dof(
    value: float, reading: float
) -> None:
    """A set value places B (its rotation follows the value, right-handed about
    A's Z) yet the hinge keeps its 1 DOF, as in Fusion. rot_deg reads back in
    (-180, 180]."""
    result = SOLVER.solve(
        _problem(
            [_joint("revolute", _FRAME_A, _FRAME_B, value=JointValue(rot_deg=value))],
            _SEED_B,
        )
    )
    assert result.status == "under_constrained"
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    _assert_pose(
        _pose_of(result, 2),
        pose((1.0, 2.0, 3.0), (0.0, 0.0, math.radians(value))),
        EXACT_TOL,
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(reading, abs=EXACT_TOL)


#: A slider along A's +X: A's frame faces +X (reference X = +Y); B's frame is
#: the same edge direction, flipped (Z = -X, X kept = +Y), so B is unrotated.
_SLIDE_A = _frame((0.0, 0.0, 10.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
_SLIDE_B = _frame((0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def test_undriven_slider_keeps_the_seed_travel() -> None:
    seed = pose((12.0, 1.0, 2.0), (0.0, 0.0, 0.1))
    result = SOLVER.solve(_problem([_joint("slider", _SLIDE_A, _SLIDE_B)], seed))
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    _assert_pose(_pose_of(result, 2), pose((12.0, 0.0, 10.0), (0, 0, 0)), EXACT_TOL)
    (state,) = result.joint_states
    assert state.lin_mm == pytest.approx(12.0, abs=EXACT_TOL)
    assert state.rot_deg is None
    assert state.axis_world == _v3(1.0, 0.0, 0.0)


def test_driven_slider_with_offset_travels_value_plus_offset() -> None:
    seed = pose((12.0, 1.0, 2.0), (0.0, 0.0, 0.1))
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "slider",
                    _SLIDE_A,
                    _SLIDE_B,
                    offset_mm=5.0,
                    value=JointValue(lin_mm=-30.0),
                )
            ],
            seed,
        )
    )
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    _assert_pose(_pose_of(result, 2), pose((-25.0, 0.0, 10.0), (0, 0, 0)), EXACT_TOL)
    assert result.joint_states[0].lin_mm == pytest.approx(-30.0, abs=EXACT_TOL)


def test_a_free_a_side_snaps_onto_a_grounded_b() -> None:
    """The joint snaps whichever side is free: with B grounded at identity, A
    moves so its frame meets B's, driven to 90°."""
    result = SOLVER.solve(
        _problem(
            [_joint("revolute", _FRAME_A, _FRAME_B, value=JointValue(rot_deg=90.0))],
            Pose.identity(),
            a_seed=pose((3.0, 3.0, 3.0), (0.1, 0.0, 0.0)),
            ground_b=True,
        )
    )
    assert result.method == "closed_form"
    # B (identity) turned +90° about A's Z: A is B turned -90°, A's frame
    # origin (1, 2, 3) landing on B's frame origin (0, 0, 0).
    a_rot = pose((0.0, 0.0, 0.0), (0.0, 0.0, -math.pi / 2))
    want = Pose(t=-a_rot.apply_point(np.array([1.0, 2.0, 3.0])), q=a_rot.q)
    _assert_pose(_pose_of(result, 1), want, EXACT_TOL)
    assert result.joint_states[0].rot_deg == pytest.approx(90.0, abs=EXACT_TOL)


# --- solver: numeric fallback and diagnosis ---------------------------------------


def _pin_axis_mate(mate_id: int, b_axis_x: float) -> SolverMate:
    """A legacy concentric between A's vertical axis at x = 11 (world) and B's
    vertical axis at B-local x = ``b_axis_x``: with the hinge at A's (1, 2)
    this fixes the hinge angle (0° when ``b_axis_x`` = 10)."""
    edge = EdgeSignature(
        curve="circle",
        end_a=_v3(0.0, 0.0, 0.0),
        end_b=_v3(0.0, 0.0, 0.0),
        midpoint=_v3(0.0, 0.0, 0.0),
        length_mm=1.0,
    )
    return SolverMate(
        mate_id=iid(mate_id),
        order_index=1,
        mate=ConcentricMate(
            a=MateAxisRef(instance_id=iid(1), signature=edge),
            b=MateAxisRef(instance_id=iid(2), signature=edge),
        ),
        geometry=(
            ResolvedAxis(point=_v3(11.0, 2.0, 0.0), direction=_v3(0.0, 0.0, 1.0)),
            ResolvedAxis(point=_v3(b_axis_x, 0.0, 0.0), direction=_v3(0, 0, 1)),
        ),
    )


def test_joint_coupled_with_a_legacy_mate_solves_numerically() -> None:
    """The snap keeps the seed's 40°, which the concentric refuses, so the
    numeric solver runs and lands the hinge at 0°, fully constrained."""
    result = SOLVER.solve(
        _problem(
            [_joint("revolute", _FRAME_A, _FRAME_B), _pin_axis_mate(7002, 10.0)],
            _SEED_B,
        )
    )
    assert result.method == "numeric"
    assert result.status == "well_constrained"
    _assert_pose(_pose_of(result, 2), pose((1.0, 2.0, 3.0), (0, 0, 0)), NUMERIC_TOL)
    assert result.joint_states[0].rot_deg == pytest.approx(0.0, abs=NUMERIC_TOL)


def test_driven_joint_conflicting_with_a_legacy_mate_names_both() -> None:
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute",
                    _FRAME_A,
                    _FRAME_B,
                    value=JointValue(rot_deg=90.0),
                ),
                _pin_axis_mate(7002, 10.0),
            ],
            _SEED_B,
        )
    )
    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert set(result.diagnosis.conflicting_mates) == {iid(7001), iid(7002)}


def test_legacy_mate_repeating_a_rigid_joint_is_redundant() -> None:
    """A rigid joint already fixes B; a later concentric that agrees with it
    adds no rank and is named redundant (over_constrained, removable)."""
    result = SOLVER.solve(
        _problem(
            [_joint("rigid", _FRAME_A, _FRAME_B), _pin_axis_mate(7002, 10.0)],
            _SEED_B,
        )
    )
    assert result.status == "over_constrained"
    assert result.diagnosis is not None
    assert result.diagnosis.redundant_mates == [iid(7002)]


# --- pipeline: the golden plates ------------------------------------------------


def _golden(name: str) -> EvaluateAssemblyRequest:
    return EvaluateAssemblyRequest.model_validate_json(
        (_GOLDENS / name / "model.json").read_text(encoding="utf-8")
    )


def _with_value(
    request: EvaluateAssemblyRequest, value: JointValue
) -> EvaluateAssemblyRequest:
    joint = request.mates[0].mate
    assert isinstance(joint, JointMate)
    mate = request.mates[0].model_copy(
        update={"mate": joint.model_copy(update={"value": value})}
    )
    return request.model_copy(update={"mates": [mate, *request.mates[1:]]})


def _placed(result: EvaluateAssemblyResult, n: int) -> Pose:
    for inst in result.instances:
        if inst.instance_id == iid(n):
            return Pose.from_placement(inst.placement)
    raise AssertionError(f"no instance {n}")


@pytest.mark.parametrize(
    ("rot_deg", "direction"), [(0.0, (1.0, 0.0, 0.0)), (90.0, (0.0, 1.0, 0.0))]
)
def test_hinge_far_top_edge_is_28_from_the_axis(
    rot_deg: float, direction: tuple[float, float, float]
) -> None:
    """Hand value: B's far top edge (B-local x = 40, z = 10) is 40 - 12 = 28
    from the hole-1 axis; at 0° it lies along A's +X, at 90° along A's +Y."""
    result = evaluate_assembly(
        _with_value(_golden("assembly-hinge-revolute"), JointValue(rot_deg=rot_deg))
    )
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    (state,) = result.joint_states
    axis = np.array([state.axis_world.x, state.axis_world.y, state.axis_world.z])
    axis_point = np.array([12.0, 12.5, 10.0])  # A is grounded at identity
    far_mid = _placed(result, 2).apply_point(np.array([40.0, 12.5, 10.0]))
    offset = far_mid - axis_point
    radial = offset - float(np.dot(offset, axis)) * axis
    assert float(np.linalg.norm(radial)) == pytest.approx(28.0, abs=EXACT_TOL)
    assert radial / 28.0 == pytest.approx(np.array(direction), abs=EXACT_TOL)
    assert state.rot_deg == pytest.approx(rot_deg, abs=EXACT_TOL)


def test_undriven_hinge_settles_at_the_seed_angle() -> None:
    """No value: the hinge keeps B's seeded spin, 2·atan2(0.05, 0.99875)."""
    result = evaluate_assembly(
        _with_value(_golden("assembly-hinge-revolute"), JointValue())
    )
    assert result.diagnosis is not None and result.diagnosis.remaining_dof == 1
    seed_angle = math.degrees(2.0 * math.atan2(0.05, 0.99875))
    assert result.joint_states[0].rot_deg == pytest.approx(seed_angle, abs=EXACT_TOL)
    assert _placed(result, 2).t[2] == pytest.approx(10.0, abs=EXACT_TOL)


def test_slider_value_80_moves_the_part_exactly_80() -> None:
    at_0 = evaluate_assembly(
        _with_value(_golden("assembly-slider"), JointValue(lin_mm=0.0))
    )
    at_80 = evaluate_assembly(
        _with_value(_golden("assembly-slider"), JointValue(lin_mm=80.0))
    )
    p0, p80 = _placed(at_0, 2), _placed(at_80, 2)
    assert p0.t == pytest.approx(np.array([0.0, 0.0, 10.0]), abs=EXACT_TOL)
    assert p80.t - p0.t == pytest.approx(np.array([80.0, 0.0, 0.0]), abs=EXACT_TOL)
    assert float(np.linalg.norm(p80.t - p0.t)) == pytest.approx(80.0, abs=EXACT_TOL)
    assert p80.matrix() == pytest.approx(p0.matrix(), abs=EXACT_TOL)
    assert at_80.joint_states[0].lin_mm == pytest.approx(80.0, abs=EXACT_TOL)


def test_hinge_conflicting_with_a_legacy_concentric_is_named() -> None:
    """The 90° hinge through hole 1 plus a legacy concentric through hole 2
    (which only a 0° hinge satisfies): conflicting, naming both mates."""
    request = _golden("assembly-hinge-revolute")
    joint = request.mates[0].mate
    assert isinstance(joint, JointMate)
    hole_1_top = joint.a.signature
    assert isinstance(hole_1_top, EdgeSignature)
    # Hole 2 is hole 1 shifted +16 in x: shift the stored rim signature.
    hole_2_top = hole_1_top.model_copy(
        update={
            "end_a": _v3(hole_1_top.end_a.x + 16.0, hole_1_top.end_a.y, 10.0),
            "end_b": _v3(hole_1_top.end_b.x + 16.0, hole_1_top.end_b.y, 10.0),
            "midpoint": _v3(hole_1_top.midpoint.x + 16.0, hole_1_top.midpoint.y, 10.0),
        }
    )
    legacy = EvaluatedMate(
        mate_id=iid(0x3EA),
        order_index=1,
        mate=ConcentricMate(
            a=MateAxisRef(instance_id=iid(1), signature=hole_2_top),
            b=MateAxisRef(instance_id=iid(2), signature=hole_2_top),
        ),
    )
    result = evaluate_assembly(
        request.model_copy(update={"mates": [*request.mates, legacy]})
    )
    assert result.mate_errors == []
    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert set(result.diagnosis.conflicting_mates) == {iid(0x3E9), iid(0x3EA)}


@pytest.mark.parametrize("motion", ["cylindrical", "planar", "ball"])
def test_s4b_motions_are_dropped_as_unsupported(motion: JointMotion) -> None:
    request = _golden("assembly-hinge-revolute")
    joint = request.mates[0].mate
    assert isinstance(joint, JointMate)
    unsupported = JointMate(motion=motion, a=joint.a, b=joint.b)
    mate = request.mates[0].model_copy(update={"mate": unsupported})
    result = evaluate_assembly(request.model_copy(update={"mates": [mate]}))
    assert [e.mate_id for e in result.mate_errors] == [iid(0x3E9)]
    assert result.mate_errors[0].error.code == "mate_unsupported"
    assert f"{motion} joint" in result.mate_errors[0].error.message
    assert result.joint_states == []


def test_unresolvable_joint_origin_is_a_per_mate_error() -> None:
    request = _golden("assembly-slider")
    joint = request.mates[0].mate
    assert isinstance(joint, JointMate)
    stale_sig = joint.b.signature.model_copy(update={"length_mm": 999.0})
    stale = joint.model_copy(
        update={"b": joint.b.model_copy(update={"signature": stale_sig})}
    )
    mate = request.mates[0].model_copy(update={"mate": stale})
    result = evaluate_assembly(request.model_copy(update={"mates": [mate]}))
    assert [e.mate_id for e in result.mate_errors] == [iid(0x3E9)]
    assert result.mate_errors[0].error.code == "subshape_unresolved"
    assert result.joint_states == []
    assert all(inst.error is None for inst in result.instances)
