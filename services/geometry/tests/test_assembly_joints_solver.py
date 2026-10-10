"""Joint solving, S4b (RESEARCH §22): every motion, drives, limits, diagnosis.

Synthetic joint frames whose answer is known by construction, the way
``test_assembly_joints.py`` tests S4a: the DOF each motion leaves (0/1/1/2/3/3),
the cylindrical / planar / ball placements, drive values on the axes they
apply to, the limit active set (a free axis past a bound stops on it, with
``at_limit``), the seam rule at ±180°, a joint conflicting with a legacy mate
named by kind, and restart determinism of the numeric limit path.
"""

from __future__ import annotations

import math
import subprocess
import sys
import uuid

import numpy as np
import pytest
from geometry.assembly import (
    AssemblySolveInput,
    AssemblySolveResult,
    ResolvedAxis,
    ResolvedFace,
    ResolvedFrame,
    RigidBodyAssemblySolver,
    SolverInstance,
    SolverMate,
)
from geometry.assembly.joint_math import read_rotation
from geometry.assembly.transform import Pose, quat_from_rotvec
from loft_wire.assemblies import (
    CoincidentMate,
    ConcentricMate,
    MateAxisRef,
    MateFaceRef,
)
from loft_wire.features import EdgeSignature, PlanarFaceSignature
from loft_wire.geometry import Vec3
from loft_wire.joints import (
    JointLimits,
    JointMate,
    JointMotion,
    JointOrigin,
    JointValue,
)

#: Closed-form placements are exact to float64 round-off; the numeric fallback
#: converges below SATISFIED_TOL (test_assembly_joints' posture).
EXACT_TOL = 1e-9
NUMERIC_TOL = 1e-6

SOLVER = RigidBodyAssemblySolver()


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _v3(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=x, y=y, z=z)


def pose(t: tuple[float, float, float], rotvec: tuple[float, float, float]) -> Pose:
    return Pose(
        t=np.array(t, dtype=np.float64),
        q=quat_from_rotvec(np.array(rotvec, dtype=np.float64)),
    )


def _rz(deg: float) -> tuple[float, float, float]:
    return (0.0, 0.0, math.radians(deg))


_FACE_SIG = PlanarFaceSignature(
    normal=_v3(0.0, 0.0, 1.0), centroid=_v3(0.0, 0.0, 0.0), area_mm2=1.0
)
_EDGE_SIG = EdgeSignature(
    curve="circle",
    end_a=_v3(0.0, 0.0, 0.0),
    end_b=_v3(0.0, 0.0, 0.0),
    midpoint=_v3(0.0, 0.0, 0.0),
    length_mm=1.0,
)


def _origin(n: int) -> JointOrigin:
    # The solver ignores the signature (resolution happened upstream).
    return JointOrigin(instance_id=iid(n), kind="face_centre", signature=_FACE_SIG)


def _frame(
    origin: tuple[float, float, float],
    z: tuple[float, float, float],
    x: tuple[float, float, float],
) -> ResolvedFrame:
    return ResolvedFrame(origin=_v3(*origin), z=_v3(*z), x=_v3(*x))


#: A's joint frame at (1, 2, 3) facing +Z; B's (B-local) at its origin facing
#: -Z. At rot 0 the opposed-Z alignment leaves B's body unrotated.
_FRAME_A = _frame((1.0, 2.0, 3.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
_FRAME_B = _frame((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0))
_SEED_B = pose((7.0, -4.0, 9.0), _rz(40.0))


def _joint(
    motion: JointMotion,
    *,
    mate_id: int = 7001,
    order: int = 0,
    value: JointValue | None = None,
    limits: JointLimits | None = None,
    offset_mm: float = 0.0,
    angle_deg: float = 0.0,
    frames: tuple[ResolvedFrame, ResolvedFrame] = (_FRAME_A, _FRAME_B),
    instances: tuple[int, int] = (1, 2),
) -> SolverMate:
    return SolverMate(
        mate_id=iid(mate_id),
        order_index=order,
        mate=JointMate(
            motion=motion,
            a=_origin(instances[0]),
            b=_origin(instances[1]),
            offset_mm=offset_mm,
            angle_deg=angle_deg,
            limits=limits,
            value=value or JointValue(),
        ),
        geometry=frames,
    )


def _problem(mates: list[SolverMate], b_seed: Pose) -> AssemblySolveInput:
    return AssemblySolveInput(
        instances=[
            SolverInstance(
                instance_id=iid(1),
                grounded=True,
                placement=Pose.identity().to_placement(),
            ),
            SolverInstance(
                instance_id=iid(2), grounded=False, placement=b_seed.to_placement()
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


def _dof(result: AssemblySolveResult) -> int:
    return 0 if result.diagnosis is None else result.diagnosis.remaining_dof


# --- motions: DOF and placement -------------------------------------------------


@pytest.mark.parametrize(
    ("motion", "dof"),
    [
        ("rigid", 0),
        ("revolute", 1),
        ("slider", 1),
        ("cylindrical", 2),
        ("planar", 3),
        ("ball", 3),
    ],
)
def test_each_motion_leaves_its_dof(motion: JointMotion, dof: int) -> None:
    """The hard rows' rank leaves 0/1/1/2/3/3 DOF, placed in closed form."""
    result = SOLVER.solve(_problem([_joint(motion)], _SEED_B))
    assert result.method == "closed_form"
    assert _dof(result) == dof
    assert result.status == ("well_constrained" if dof == 0 else "under_constrained")


@pytest.mark.parametrize(("motion", "dof"), [("cylindrical", 2), ("planar", 3)])
def test_driving_every_value_keeps_the_dof(motion: JointMotion, dof: int) -> None:
    """Drive values place a joint but remove no DOF (Fusion's driven joint)."""
    value = (
        JointValue(rot_deg=30.0, lin_mm=4.0)
        if motion == "cylindrical"
        else JointValue(rot_deg=30.0)
    )
    result = SOLVER.solve(_problem([_joint(motion, value=value)], _SEED_B))
    assert _dof(result) == dof


def test_cylindrical_takes_both_values_along_and_about_one_axis() -> None:
    """Driven rot 90 and lin 5 with offset 2: B turned 90° about A's Z, its
    origin 2 + 5 along A's Z from A's origin."""
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "cylindrical",
                    offset_mm=2.0,
                    value=JointValue(rot_deg=90.0, lin_mm=5.0),
                )
            ],
            _SEED_B,
        )
    )
    _assert_pose(_pose_of(result, 2), pose((1.0, 2.0, 10.0), _rz(90.0)), EXACT_TOL)
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(90.0, abs=EXACT_TOL)
    assert state.lin_mm == pytest.approx(5.0, abs=EXACT_TOL)
    assert state.at_limit is False


def test_undriven_cylindrical_keeps_the_seed_turn_and_travel() -> None:
    """Seed at (7, -4, 9) turned 40°: on A's axis line the joint keeps the
    turn (40°) and the travel along the axis (9 - 3 = 6)."""
    result = SOLVER.solve(_problem([_joint("cylindrical")], _SEED_B))
    _assert_pose(_pose_of(result, 2), pose((1.0, 2.0, 9.0), _rz(40.0)), EXACT_TOL)
    (state,) = result.joint_states
    assert (state.rot_deg, state.lin_mm) == (
        pytest.approx(40.0, abs=EXACT_TOL),
        pytest.approx(6.0, abs=EXACT_TOL),
    )


def test_planar_takes_the_turn_and_keeps_the_seed_slide() -> None:
    """Planar, offset 2, driven to 30°: B lies 2 above A's plane, turned 30°,
    at the seed's in-plane spot (7, -4); the seed's height 9 is discarded."""
    result = SOLVER.solve(
        _problem(
            [_joint("planar", offset_mm=2.0, value=JointValue(rot_deg=30.0))],
            _SEED_B,
        )
    )
    _assert_pose(_pose_of(result, 2), pose((7.0, -4.0, 5.0), _rz(30.0)), EXACT_TOL)
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(30.0, abs=EXACT_TOL)
    assert state.lin_mm is None


def test_ball_keeps_the_seed_orientation_about_the_shared_point() -> None:
    """A ball moves B so the frame origins meet (offset 1 along A's Z) and
    keeps whatever orientation the seed had, a tilt included."""
    seed = pose((7.0, -4.0, 9.0), (0.3, -0.2, 0.5))
    result = SOLVER.solve(_problem([_joint("ball", offset_mm=1.0)], seed))
    _assert_pose(
        _pose_of(result, 2), Pose(t=np.array([1.0, 2.0, 4.0]), q=seed.q), EXACT_TOL
    )
    (state,) = result.joint_states
    assert (state.rot_deg, state.lin_mm, state.at_limit) == (None, None, False)


# --- limits ---------------------------------------------------------------------


def test_undriven_revolute_past_its_max_stops_on_it() -> None:
    """Seeded at 40° with max 30°: the joint stops at 30°, at_limit, still 1
    DOF (a limit pins the joint, it does not remove the DOF)."""
    result = SOLVER.solve(
        _problem([_joint("revolute", limits=JointLimits(rot_max_deg=30.0))], _SEED_B)
    )
    assert result.method == "closed_form"
    assert (result.status, _dof(result)) == ("under_constrained", 1)
    _assert_pose(_pose_of(result, 2), pose((1.0, 2.0, 3.0), _rz(30.0)), EXACT_TOL)
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(30.0, abs=EXACT_TOL)
    assert state.at_limit is True


def test_inside_its_limits_a_joint_is_not_at_a_limit() -> None:
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute",
                    limits=JointLimits(rot_min_deg=-45.0, rot_max_deg=45.0),
                )
            ],
            _SEED_B,
        )
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(40.0, abs=EXACT_TOL)
    assert state.at_limit is False


def test_slider_past_its_max_stops_on_it() -> None:
    """Seed travel 6 along A's Z, max 2.5: the slider stops at 2.5."""
    result = SOLVER.solve(
        _problem(
            [_joint("slider", limits=JointLimits(lin_min_mm=0.0, lin_max_mm=2.5))],
            _SEED_B,
        )
    )
    (state,) = result.joint_states
    assert state.lin_mm == pytest.approx(2.5, abs=EXACT_TOL)
    assert state.at_limit is True
    assert _pose_of(result, 2).t == pytest.approx(np.array([1.0, 2.0, 5.5]))


def test_cylindrical_pins_both_axes_in_one_pass() -> None:
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "cylindrical",
                    limits=JointLimits(
                        rot_min_deg=-10.0,
                        rot_max_deg=10.0,
                        lin_min_mm=-1.0,
                        lin_max_mm=1.0,
                    ),
                )
            ],
            _SEED_B,
        )
    )
    _assert_pose(_pose_of(result, 2), pose((1.0, 2.0, 4.0), _rz(10.0)), EXACT_TOL)
    (state,) = result.joint_states
    assert (state.rot_deg, state.lin_mm, state.at_limit) == (
        pytest.approx(10.0, abs=EXACT_TOL),
        pytest.approx(1.0, abs=EXACT_TOL),
        True,
    )


def test_a_value_driven_onto_a_bound_is_at_the_limit() -> None:
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute",
                    value=JointValue(rot_deg=-30.0),
                    limits=JointLimits(rot_min_deg=-30.0, rot_max_deg=30.0),
                )
            ],
            _SEED_B,
        )
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(-30.0, abs=EXACT_TOL)
    assert state.at_limit is True


def test_a_value_past_its_limit_never_reaches_geometry() -> None:
    """Documents refuses such a value; one that arrives anyway is clamped."""
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "slider",
                    value=JointValue(lin_mm=50.0),
                    limits=JointLimits(lin_max_mm=20.0),
                )
            ],
            _SEED_B,
        )
    )
    (state,) = result.joint_states
    assert state.lin_mm == pytest.approx(20.0, abs=EXACT_TOL)
    assert state.at_limit is True


def _pin_mate(mate_id: int, b_axis: tuple[float, float]) -> SolverMate:
    """A legacy concentric between a vertical axis through world (0, 0) on the
    grounded A and a vertical axis through B-local ``b_axis``."""
    return SolverMate(
        mate_id=iid(mate_id),
        order_index=1,
        mate=ConcentricMate(
            a=MateAxisRef(instance_id=iid(1), signature=_EDGE_SIG),
            b=MateAxisRef(instance_id=iid(2), signature=_EDGE_SIG),
        ),
        geometry=(
            ResolvedAxis(point=_v3(0.0, 0.0, 0.0), direction=_v3(0.0, 0.0, 1.0)),
            ResolvedAxis(point=_v3(*b_axis, 0.0), direction=_v3(0.0, 0.0, 1.0)),
        ),
    )


def test_a_free_axis_moved_by_another_mate_stops_at_the_limit() -> None:
    """Numeric path: a planar joint on A's z = 3 plane plus a legacy pin
    through B-local (10, 0) leaves B one turn about the pin. The seed turns it
    60°, past max 30°: the active set pins 30° and re-solves, so B turns
    about the pin to exactly 30°, consistent (1 DOF left, at_limit)."""
    seed = pose((-5.0, -8.0, 9.0), _rz(60.0))
    result = SOLVER.solve(
        _problem(
            [
                _joint("planar", limits=JointLimits(rot_max_deg=30.0)),
                _pin_mate(7002, (10.0, 0.0)),
            ],
            seed,
        )
    )
    assert result.method == "numeric"
    assert (result.status, _dof(result)) == ("under_constrained", 1)
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    _assert_pose(
        _pose_of(result, 2), pose((-10.0 * c, -10.0 * s, 3.0), _rz(30.0)), NUMERIC_TOL
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(30.0, abs=NUMERIC_TOL)
    assert state.at_limit is True


def test_a_limit_fighting_a_legacy_mate_is_a_conflict_naming_both() -> None:
    """A revolute at A's (1, 2) plus a pin that only a 0° hinge satisfies,
    with limits [10°, 90°]: the joint cannot reach 0°, so the pinned limit
    and the pin are named together."""
    pin = SolverMate(
        mate_id=iid(7002),
        order_index=1,
        mate=ConcentricMate(
            a=MateAxisRef(instance_id=iid(1), signature=_EDGE_SIG),
            b=MateAxisRef(instance_id=iid(2), signature=_EDGE_SIG),
        ),
        geometry=(
            ResolvedAxis(point=_v3(11.0, 2.0, 0.0), direction=_v3(0.0, 0.0, 1.0)),
            ResolvedAxis(point=_v3(10.0, 0.0, 0.0), direction=_v3(0.0, 0.0, 1.0)),
        ),
    )
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute", limits=JointLimits(rot_min_deg=10.0, rot_max_deg=90.0)
                ),
                pin,
            ],
            _SEED_B,
        )
    )
    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert set(result.diagnosis.conflicting_mates) == {iid(7001), iid(7002)}
    assert result.joint_states[0].at_limit is True


# --- the seam rule at ±180° -----------------------------------------------------


@pytest.mark.parametrize(
    ("seed_deg", "stop_deg"),
    [
        (180.0, 90.0),  # the seam itself reads +180: past the max
        (179.0, 90.0),
        (-179.0, -90.0),
        (100.0, 90.0),
        (-100.0, -90.0),
    ],
)
def test_seam_rule_principal_limits(seed_deg: float, stop_deg: float) -> None:
    """Limits [-90°, 90°] read on (-180°, 180°]: an angle past them goes to the
    nearer bound, and the seam (±180°, equally far) goes to the max."""
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute", limits=JointLimits(rot_min_deg=-90.0, rot_max_deg=90.0)
                )
            ],
            pose((7.0, -4.0, 9.0), _rz(seed_deg)),
        )
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(stop_deg, abs=EXACT_TOL)
    assert state.at_limit is True


@pytest.mark.parametrize(
    ("seed_deg", "reading", "at_limit"),
    [
        (-170.0, -170.0, False),  # 190°: inside [150°, 210°], across the seam
        (180.0, 180.0, False),
        (140.0, 150.0, True),  # just short of the min
        (-140.0, -150.0, True),  # 220°: past the max, which reads -150°
        (0.0, -150.0, True),  # opposite the arc's middle: to the max
    ],
)
def test_seam_rule_limits_across_the_seam(
    seed_deg: float, reading: float, at_limit: bool
) -> None:
    """Limits [150°, 210°] straddle ±180°. The angle is read on the branch
    centred on the limits, (0°, 360°], so 190° (shown as -170°) is inside, and
    an angle outside goes to the nearer bound around the circle. rot_deg is
    still reported on (-180°, 180°]."""
    result = SOLVER.solve(
        _problem(
            [
                _joint(
                    "revolute",
                    limits=JointLimits(rot_min_deg=150.0, rot_max_deg=210.0),
                )
            ],
            pose((7.0, -4.0, 9.0), _rz(seed_deg)),
        )
    )
    (state,) = result.joint_states
    assert state.rot_deg == pytest.approx(reading, abs=EXACT_TOL)
    assert state.at_limit is at_limit


def test_seam_rule_one_sided_limits() -> None:
    """A lone max reads on (-180°, 180°] (the joint's zero is home): 120° stops
    at max 90°, -120° is free. A lone min above 0 reads around that min."""
    centred = [
        read_rotation(math.radians(d), (None, math.radians(90.0)))
        for d in (120.0, -120.0)
    ]
    assert [math.degrees(r) for r in centred] == pytest.approx([120.0, -120.0])
    around_min = read_rotation(math.radians(-160.0), (math.radians(200.0), None))
    assert math.degrees(around_min) == pytest.approx(200.0)
    stopped = SOLVER.solve(
        _problem(
            [_joint("revolute", limits=JointLimits(rot_max_deg=90.0))],
            pose((7.0, -4.0, 9.0), _rz(120.0)),
        )
    )
    assert stopped.joint_states[0].rot_deg == pytest.approx(90.0, abs=EXACT_TOL)
    free = SOLVER.solve(
        _problem(
            [_joint("revolute", limits=JointLimits(rot_max_deg=90.0))],
            pose((7.0, -4.0, 9.0), _rz(-120.0)),
        )
    )
    assert free.joint_states[0].rot_deg == pytest.approx(-120.0, abs=EXACT_TOL)
    assert free.joint_states[0].at_limit is False


# --- diagnosis ------------------------------------------------------------------


def _coincident(mate_id: int, b_z: float) -> SolverMate:
    """A legacy flush coincident between A's top face z = 3 and B's bottom
    face at B-local z = ``b_z`` (normal -Z)."""
    return SolverMate(
        mate_id=iid(mate_id),
        order_index=1,
        mate=CoincidentMate(
            a=MateFaceRef(instance_id=iid(1), signature=_FACE_SIG),
            b=MateFaceRef(instance_id=iid(2), signature=_FACE_SIG),
        ),
        geometry=(
            ResolvedFace(point=_v3(0.0, 0.0, 3.0), normal=_v3(0.0, 0.0, 1.0)),
            ResolvedFace(point=_v3(0.0, 0.0, b_z), normal=_v3(0.0, 0.0, -1.0)),
        ),
    )


def test_rigid_joint_and_a_disagreeing_coincident_are_named_by_kind() -> None:
    """A rigid joint seats B's origin on A's (1, 2, 3); a coincident wants B's
    face at B-local z = 4 on that plane, i.e. B 4 lower. Over-constrained and
    contradictory: both are named, each by its kind."""
    result = SOLVER.solve(_problem([_joint("rigid"), _coincident(7002, 4.0)], _SEED_B))
    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert result.diagnosis.conflicting_mates == [iid(7001), iid(7002)]
    message = result.diagnosis.message
    assert f"rigid joint {iid(7001)}" in message
    assert f"coincident mate {iid(7002)}" in message


def test_rigid_joint_and_an_agreeing_coincident_is_redundant() -> None:
    result = SOLVER.solve(_problem([_joint("rigid"), _coincident(7002, 0.0)], _SEED_B))
    assert result.status == "over_constrained"
    assert result.diagnosis is not None
    assert result.diagnosis.redundant_mates == [iid(7002)]


# --- determinism ----------------------------------------------------------------


def _two_driven_joints(reverse: bool) -> AssemblySolveInput:
    """A grounded; B on a driven cylindrical; C on a planar to B with a rot
    limit its seed crosses. Stage 2 holds three driving rows."""
    frame_c = _frame((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0))
    mates = [
        _joint(
            "cylindrical",
            mate_id=7001,
            order=0,
            value=JointValue(rot_deg=25.0, lin_mm=3.0),
        ),
        _joint(
            "planar",
            mate_id=7002,
            order=1,
            limits=JointLimits(rot_min_deg=-20.0, rot_max_deg=20.0),
            frames=(_frame((0.0, 0.0, 5.0), (0, 0, 1), (1, 0, 0)), frame_c),
            instances=(2, 3),
        ),
        _pin_mate(7003, (10.0, 0.0)).model_copy(
            update={
                "order_index": 2,
                "mate": ConcentricMate(
                    a=MateAxisRef(instance_id=iid(1), signature=_EDGE_SIG),
                    b=MateAxisRef(instance_id=iid(3), signature=_EDGE_SIG),
                ),
            }
        ),
    ]
    problem = _problem(mates if not reverse else mates[::-1], _SEED_B)
    seed_c = pose((-4.0, -9.0, 20.0), _rz(70.0))
    third = SolverInstance(
        instance_id=iid(3), grounded=False, placement=seed_c.to_placement()
    )
    return problem.model_copy(update={"instances": [*problem.instances, third]})


def test_driving_rows_solve_in_mate_order_whatever_the_input_order() -> None:
    first = SOLVER.solve(_two_driven_joints(reverse=False))
    second = SOLVER.solve(_two_driven_joints(reverse=True))
    assert first.method == "numeric"
    assert first.model_dump_json() == second.model_dump_json()
    planar = first.joint_states[1]
    assert planar.at_limit is True


_RESTART_PROBE = """\
import sys

from geometry.assembly import AssemblySolveInput, RigidBodyAssemblySolver

problem = AssemblySolveInput.model_validate_json(sys.stdin.read())
print(RigidBodyAssemblySolver().solve(problem).model_dump_json())
"""


def test_numeric_limit_solve_is_identical_across_interpreter_restart() -> None:
    problem = _two_driven_joints(reverse=False)
    local = SOLVER.solve(problem).model_dump_json()
    probe = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=problem.model_dump_json(),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == local
