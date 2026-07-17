"""Analytic goldens for the DISTANCE and ANGLE mates (design ``assemblies.md``
§2.3/§5 — the assembly solver's documented fast-follow, "the same solver, one
extra scalar").

These pin the two conventions the distance/angle residuals hinge on, PROVED
against synthetic resolved geometry (no kernel — the ``(point, normal)`` pairs are
constructed from a chosen target pose, so the analytic answer is known by
construction, mirroring :mod:`tests.test_assembly_solver`). The full author →
resolve → solve path against REAL bodies is proved separately by the
``assembly-two-plates-gap`` golden (a distance mate landing two real plates
exactly 5 mm apart).

**The pinned distance sign convention** (design §2.3, ``residuals.py``): a
``distance`` mate rides the ``coincident`` residual with ``target =
distance_mm``. ``distance_mm`` is the SIGNED gap measured along face **A's
outward normal** ``n_A``: at the solution ``n_A · (p_B - p_A) = distance_mm``,
with B's outward normal held anti-parallel to A's (the coincident ``flush``
sense). So ``p_B`` sits ``distance_mm`` along ``+n_A`` from ``p_A`` — POSITIVE =
a gap on the ``+n_A`` side (the two outward normals face each other across the
gap), NEGATIVE = B on the ``-n_A`` side, ZERO = a plain flush coincident.

**The pinned angle convention** (design §2.3, ``residuals.py``): ``angle_deg``
is the angle φ between the two faces' OUTWARD normals, ``acos(n_A · n_B) =
angle_deg`` (no flush sense — an angle mate constrains only the scalar angle).
The residual is ``sin(φ - θ)`` for a non-degenerate target so the Jacobian row
stays full-strength at the target; the parallel/anti-parallel degenerate
(θ ≈ 0°/180°) falls back to ``cosφ - cosθ`` and is reported honestly, never NaN,
never a wrong pose claimed well_constrained.

Tolerance is the documented per-model :data:`DA_TOL`, never an inline epsilon.
"""

from __future__ import annotations

import math
import struct
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
    RigidBodyAssemblySolver,
    SolverInstance,
    SolverMate,
)
from geometry.assembly.transform import Pose, as_vector, quat_from_rotvec
from py_kit.schemas.assemblies import (
    AngleMate,
    CoincidentMate,
    ConcentricMate,
    DistanceMate,
    MateAxisRef,
    MateFaceRef,
)
from py_kit.schemas.features import EdgeSignature, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Per-model solve tolerance (mm for positions/gaps, dimensionless for
#: normals/angles-as-cosines). The numeric LM converges well below this for a
#: non-degenerate target; documented once, used everywhere here (CLAUDE.md
#: geometry conventions — never an inline epsilon).
DA_TOL = 1e-6

#: Angle-landing tolerance in DEGREES: the solved dihedral must equal the target
#: this closely. Derived from DA_TOL on the normal direction (a 1e-6 direction
#: error is ~6e-5°); set at 1e-4° so it is a real bound, not a rounding of DA_TOL.
ANGLE_DEG_TOL = 1e-4

SOLVER = RigidBodyAssemblySolver()

_Z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
_ORIGIN = np.array([0.0, 0.0, 0.0], dtype=np.float64)


# --- construction helpers (self-contained: the restart probe execs THIS file) ---


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def vec3(a: np.ndarray) -> Vec3:
    return Vec3(x=float(a[0]), y=float(a[1]), z=float(a[2]))


def pose(t: tuple[float, float, float], rotvec: tuple[float, float, float]) -> Pose:
    return Pose(
        t=np.array(t, dtype=np.float64),
        q=quat_from_rotvec(np.array(rotvec, dtype=np.float64)),
    )


def _face_sig() -> PlanarFaceSignature:
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=0.0),
        area_mm2=1.0,
    )


def _edge_sig() -> EdgeSignature:
    return EdgeSignature(
        curve="circle",
        end_a=Vec3(x=0.0, y=0.0, z=0.0),
        end_b=Vec3(x=0.0, y=0.0, z=0.0),
        midpoint=Vec3(x=0.0, y=0.0, z=0.0),
        length_mm=1.0,
    )


def face_ref(instance_id: uuid.UUID) -> MateFaceRef:
    return MateFaceRef(instance_id=instance_id, signature=_face_sig())


def axis_ref(instance_id: uuid.UUID) -> MateAxisRef:
    return MateAxisRef(instance_id=instance_id, signature=_edge_sig())


def local_face(
    target: Pose, world_point: np.ndarray, world_normal: np.ndarray
) -> ResolvedFace:
    """A ResolvedFace in an instance's LOCAL frame that lands at the given world
    geometry when the instance is at ``target``."""
    inv = target.inverse()
    return ResolvedFace(
        point=vec3(inv.apply_point(world_point)),
        normal=vec3(inv.apply_direction(world_normal)),
    )


def local_axis(
    target: Pose, world_point: np.ndarray, world_dir: np.ndarray
) -> ResolvedAxis:
    inv = target.inverse()
    return ResolvedAxis(
        point=vec3(inv.apply_point(world_point)),
        direction=vec3(inv.apply_direction(world_dir)),
    )


def instance(n: int, *, grounded: bool, seed: Pose) -> SolverInstance:
    return SolverInstance(
        instance_id=iid(n), grounded=grounded, placement=seed.to_placement()
    )


def placement_of(result: AssemblySolveResult, n: int) -> Pose:
    for p in result.placements:
        if p.instance_id == iid(n):
            return Pose.from_placement(p.placement)
    raise AssertionError(f"no placement for instance {n}")


def solved_face_gap(
    result: AssemblySolveResult,
    mate: SolverMate,
    n_a: int,
    n_b: int,
) -> tuple[float, np.ndarray, np.ndarray]:
    """The signed gap ``n_A · (p_B - p_A)`` and the two world normals, evaluated
    on the SOLVED poses — the physical quantity the distance mate pins."""
    assert mate.geometry is not None
    fa, fb = mate.geometry
    assert isinstance(fa, ResolvedFace) and isinstance(fb, ResolvedFace)
    pa = placement_of(result, n_a)
    pb = placement_of(result, n_b)
    na = pa.apply_direction(as_vector(fa.normal))
    nb = pb.apply_direction(as_vector(fb.normal))
    gap = float(
        np.dot(
            na,
            pb.apply_point(as_vector(fb.point)) - pa.apply_point(as_vector(fa.point)),
        )
    )
    return gap, na, nb


def solved_normal_angle_deg(
    result: AssemblySolveResult,
    world_normal_a: np.ndarray,
    n_b: int,
    local_normal_b: np.ndarray,
) -> float:
    """The angle (degrees) between A's fixed world normal and B's solved world
    normal — the dihedral the angle mate pins."""
    nb = placement_of(result, n_b).apply_direction(local_normal_b)
    dot = float(np.dot(world_normal_a, nb)) / (
        float(np.linalg.norm(world_normal_a)) * float(np.linalg.norm(nb))
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def pack_placements(result: AssemblySolveResult) -> bytes:
    """All placement floats packed little-endian — the bitwise determinism unit."""
    buf = bytearray()
    for p in result.placements:
        pl = p.placement
        for value in (
            pl.position.x,
            pl.position.y,
            pl.position.z,
            pl.orientation.x,
            pl.orientation.y,
            pl.orientation.z,
            pl.orientation.w,
        ):
            buf += struct.pack("<d", value)
    return bytes(buf)


# --- single distance mate: the SIGN convention, both signs + the zero degenerate


def _single_distance_problem(
    distance_mm: float,
) -> tuple[AssemblySolveInput, SolverMate]:
    """A grounded (top face at the world origin, +Z), B free above with its bottom
    face normal -Z, mated by ONE distance mate. A single face mate leaves 3 DOF
    (the in-plane slide + spin), so this is under-constrained by construction —
    but the GAP along +Z is fully pinned, which is what we assert."""
    a_seed = Pose.identity()
    b_seed = pose((1.0, 2.0, 7.0), (0.05, 0.03, 0.0))  # displaced so the solve works
    mate = SolverMate(
        mate_id=iid(1001),
        order_index=0,
        mate=DistanceMate(
            a=face_ref(iid(1)), b=face_ref(iid(2)), distance_mm=distance_mm
        ),
        geometry=(
            local_face(a_seed, _ORIGIN, _Z),
            local_face(b_seed, np.array([1.0, 2.0, 7.0]), -_Z),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[mate],
    )
    return problem, mate


@pytest.mark.parametrize("distance_mm", [5.0, -5.0, 0.0])
def test_distance_mate_pins_signed_gap_along_face_a_normal(distance_mm: float) -> None:
    """The solved gap ``n_A · (p_B - p_A)`` equals ``distance_mm`` EXACTLY (the
    pinned sign convention), for a positive gap, a negative gap (B on the -n_A
    side), and the zero degenerate — and B's outward normal stays anti-parallel to
    A's (the coincident flush sense the distance mate inherits)."""
    problem, mate = _single_distance_problem(distance_mm)
    result = SOLVER.solve(problem)

    assert result.status == "under_constrained"  # one face mate ⇒ 3 DOF remain
    gap, na, nb = solved_face_gap(result, mate, 1, 2)
    assert gap == pytest.approx(distance_mm, abs=DA_TOL)
    # flush: the two outward normals are anti-parallel across the gap.
    assert float(np.dot(na, nb)) == pytest.approx(-1.0, abs=DA_TOL)


def test_zero_distance_equals_coincident() -> None:
    """A ``distance`` mate with ``distance_mm = 0`` is byte-for-byte the same
    solve as the equivalent ``coincident`` mate (the zero degenerate IS a flush
    coincident — the pinned convention's boundary case)."""
    a_seed = Pose.identity()
    b_seed = pose((1.0, 2.0, 7.0), (0.05, 0.03, 0.0))
    geom = (
        local_face(a_seed, _ORIGIN, _Z),
        local_face(b_seed, np.array([1.0, 2.0, 7.0]), -_Z),
    )
    dist = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[
            SolverMate(
                mate_id=iid(1),
                order_index=0,
                mate=DistanceMate(
                    a=face_ref(iid(1)), b=face_ref(iid(2)), distance_mm=0.0
                ),
                geometry=geom,
            )
        ],
    )
    coin = AssemblySolveInput(
        instances=dist.instances,
        mates=[
            SolverMate(
                mate_id=iid(1),
                order_index=0,
                mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
                geometry=geom,
            )
        ],
    )
    assert pack_placements(SOLVER.solve(dist)) == pack_placements(SOLVER.solve(coin))


def test_single_distance_removes_the_same_dof_as_a_coincident() -> None:
    """DOF accounting: a distance mate removes the SAME degrees of freedom a
    coincident does (it pins the along-normal translation to ``distance_mm``
    instead of 0), so a lone distance mate reports exactly 3 remaining DOF — the
    same as a lone coincident (design §2.4)."""
    problem, _ = _single_distance_problem(5.0)
    result = SOLVER.solve(problem)
    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof == 3
    assert result.diagnosis.classification is None


# --- fully-located distance: an EXACT solved pose a known gap apart --------------


def build_distance_bolt_problem() -> tuple[AssemblySolveInput, Pose]:
    """A grounded; B located by a distance mate (+5 mm gap) + two concentric holes
    → fully located. The synthetic twin of the ``assembly-two-plates-gap`` golden:
    B lands exactly (0, 0, 15) with identity orientation (A's top at z=10, +5 gap).
    """
    gap = 5.0
    a_seed = Pose.identity()
    b_target = pose((0.0, 0.0, 10.0 + gap), (0.0, 0.0, 0.0))
    b_seed = pose((3.0, 2.0, 16.0), (0.0, 0.0, 0.1))  # displaced + spun
    a_top = np.array([20.0, 12.5, 10.0], dtype=np.float64)
    h1 = np.array([12.0, 12.5, 10.0], dtype=np.float64)
    h2 = np.array([28.0, 12.5, 10.0], dtype=np.float64)
    distance = SolverMate(
        mate_id=iid(1),
        order_index=0,
        mate=DistanceMate(a=face_ref(iid(1)), b=face_ref(iid(2)), distance_mm=gap),
        geometry=(
            local_face(a_seed, a_top, _Z),
            local_face(b_target, a_top + np.array([0.0, 0.0, gap]), -_Z),
        ),
    )
    c1 = SolverMate(
        mate_id=iid(2),
        order_index=1,
        mate=ConcentricMate(a=axis_ref(iid(1)), b=axis_ref(iid(2))),
        geometry=(
            local_axis(a_seed, h1, _Z),
            local_axis(b_target, h1 + np.array([0.0, 0.0, gap]), _Z),
        ),
    )
    c2 = SolverMate(
        mate_id=iid(3),
        order_index=2,
        mate=ConcentricMate(a=axis_ref(iid(1)), b=axis_ref(iid(2))),
        geometry=(
            local_axis(a_seed, h2, _Z),
            local_axis(b_target, h2 + np.array([0.0, 0.0, gap]), _Z),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[distance, c1, c2],
    )
    return problem, b_target


def test_distance_bolt_lands_exact_pose() -> None:
    """The fully-located distance joint lands B at exactly (0, 0, 15) identity —
    well_constrained (the two holes pin all six DOF, the distance mate setting the
    along-normal one to the 5 mm gap)."""
    problem, b_target = build_distance_bolt_problem()
    result = SOLVER.solve(problem)
    assert result.status == "well_constrained"
    got = placement_of(result, 2)
    assert np.allclose(got.t, b_target.t, atol=DA_TOL)
    assert np.allclose(got.matrix(), b_target.matrix(), atol=DA_TOL)


# --- single angle mate: the ANGLE convention, 30° and 90° -----------------------


def _single_angle_problem(
    angle_deg: float, seed_rotvec: tuple[float, float, float]
) -> AssemblySolveInput:
    """A grounded (face normal +Z), B free with its face LOCAL normal +Z tilted by
    the seed rotation, mated by ONE angle mate. A lone angle mate removes exactly
    1 DOF, so this is under-constrained (5 DOF remain) by construction."""
    a_seed = Pose.identity()
    b_seed = pose((0.0, 0.0, 5.0), seed_rotvec)
    mate = SolverMate(
        mate_id=iid(9),
        order_index=0,
        mate=AngleMate(a=face_ref(iid(1)), b=face_ref(iid(2)), angle_deg=angle_deg),
        geometry=(
            ResolvedFace(point=vec3(_ORIGIN), normal=vec3(_Z)),
            ResolvedFace(point=vec3(_ORIGIN), normal=vec3(_Z)),
        ),
    )
    return AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[mate],
    )


@pytest.mark.parametrize("angle_deg", [30.0, 90.0, 120.0])
def test_angle_mate_lands_exact_dihedral(angle_deg: float) -> None:
    """The solved angle between the two outward normals equals the target EXACTLY
    (the pinned convention: ``angle_deg = acos(n_A · n_B)``), for an acute, a
    right, and an obtuse target — driven from a tilted seed."""
    result = SOLVER.solve(_single_angle_problem(angle_deg, (0.0, 0.6, 0.2)))
    assert result.status == "under_constrained"  # a lone angle mate ⇒ 5 DOF remain
    solved = solved_normal_angle_deg(result, _Z, 2, _Z)
    assert solved == pytest.approx(angle_deg, abs=ANGLE_DEG_TOL)


def test_single_angle_removes_exactly_one_dof() -> None:
    """DOF accounting: an angle mate removes exactly 1 DOF, so a lone angle mate on
    a free 6-DOF instance reports 5 remaining DOF (design §2.4)."""
    result = SOLVER.solve(_single_angle_problem(30.0, (0.0, 0.6, 0.2)))
    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof == 5
    assert result.diagnosis.classification is None


# --- angle degenerate: parallel / anti-parallel handled cleanly (no NaN) --------


@pytest.mark.parametrize("angle_deg", [0.0, 180.0])
def test_angle_parallel_degenerate_is_clean_and_honest(angle_deg: float) -> None:
    """A parallel (0°) or anti-parallel (180°) angle target is the genuine
    degenerate — a zero-gradient bifurcation. The solve must be NaN-free, drive the
    normal toward the correct end, and NEVER claim well_constrained (an honest
    non-``well_constrained`` status), never a wrong pose (design §2.3/§2.4)."""
    result = SOLVER.solve(_single_angle_problem(angle_deg, (0.5, 0.0, 0.0)))
    # Never a silent success at the degenerate: the honest status is not the clean
    # well_constrained (it is under_constrained or the fatal not_converged).
    assert result.status != "well_constrained"
    solved_pose = placement_of(result, 2)
    assert not np.isnan(solved_pose.t).any()
    assert not np.isnan(solved_pose.q).any()
    # It drives the RIGHT way: nearer the target end than the opposite end.
    solved = solved_normal_angle_deg(result, _Z, 2, _Z)
    assert abs(solved - angle_deg) < 90.0


# --- determinism (RESEARCH §9): a mixed distance + angle graph -------------------


def build_distance_angle_problem() -> tuple[AssemblySolveInput, None]:
    """A grounded; B fully located by distance + two concentric; C constrained to A
    by an angle mate (30°). One graph exercising BOTH new mates for the bitwise
    determinism probe. C leaves 5 DOF, so the assembly is under_constrained overall
    — a valid, deterministic best-fit."""
    bolt, _ = build_distance_bolt_problem()
    c_seed = pose((0.0, 30.0, 5.0), (0.0, 0.6, 0.2))
    angle = SolverMate(
        mate_id=iid(4),
        order_index=3,
        mate=AngleMate(a=face_ref(iid(1)), b=face_ref(iid(5)), angle_deg=30.0),
        geometry=(
            ResolvedFace(point=vec3(_ORIGIN), normal=vec3(_Z)),
            ResolvedFace(point=vec3(_ORIGIN), normal=vec3(_Z)),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            *bolt.instances,
            instance(5, grounded=False, seed=c_seed),
        ],
        mates=[*bolt.mates, angle],
    )
    return problem, None


def test_distance_angle_solve_is_deterministic_bitwise() -> None:
    """Same distance+angle input, two fresh solver instances → byte-identical
    placements (RESEARCH §9 solver-determinism, extended to the new mates)."""
    problem, _ = build_distance_angle_problem()
    first = pack_placements(RigidBodyAssemblySolver().solve(problem))
    second = pack_placements(RigidBodyAssemblySolver().solve(problem))
    assert first == second


_RESTART_PROBE = """\
import importlib.util, sys
spec = importlib.util.spec_from_file_location("da_probe", {path!r})
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
from geometry.assembly import RigidBodyAssemblySolver
problem, _ = mod.build_distance_angle_problem()
sys.stdout.write(RigidBodyAssemblySolver().solve(problem).model_dump_json())
"""


def test_distance_angle_solve_is_deterministic_across_interpreter_restart() -> None:
    """A fresh-interpreter solve of the distance+angle graph (worker-restart
    emulation, RESEARCH §9) yields byte-identical placements to the in-process
    solve — the BLAS pin fixes the FP reduction order across processes."""
    problem, _ = build_distance_angle_problem()
    in_process = pack_placements(RigidBodyAssemblySolver().solve(problem))
    proc = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE.format(path=__file__)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"restart probe failed:\n{proc.stderr}"
    restarted = pack_placements(AssemblySolveResult.model_validate_json(proc.stdout))
    assert in_process == restarted
