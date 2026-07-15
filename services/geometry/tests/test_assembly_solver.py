"""Unit tests for the ``AssemblySolver`` core (design ``assemblies.md`` §2).

Item #2 proves the SOLVER MATH against **synthetic** resolved geometry — the
``(point, normal)`` / ``(point, direction)`` pairs item #3 will derive from real
OCCT bodies. No kernel here; every mate's geometry is constructed from a chosen
target pose so the analytic solution is known by construction.

Determinism (RESEARCH §9) is asserted BITWISE: the same input solved twice — and
in a fresh interpreter (a worker-restart probe, mirroring ``test_goldens.py``) —
packs to byte-identical placement floats. Tolerances are the documented
per-model :data:`ASSEMBLY_TOL`, never ad-hoc per-assert epsilons.
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
    AssemblyDefinitionError,
    AssemblySolveInput,
    AssemblySolveResult,
    ResolvedAxis,
    ResolvedFace,
    RigidBodyAssemblySolver,
    SolverInstance,
    SolverMate,
)
from geometry.assembly.transform import Pose, quat_from_rotvec
from py_kit.schemas.assemblies import (
    CoincidentMate,
    ConcentricMate,
    LockMate,
    MateAxisRef,
    MateFaceRef,
    Placement,
)
from py_kit.schemas.features import EdgeSignature, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Per-model solve tolerance (mm for positions, dimensionless for quaternion
#: components / normals). The closed-form path is exact to ~1e-12; the numeric LM
#: converges well below this. Documented here, used everywhere in this suite —
#: never an inline epsilon (CLAUDE.md geometry conventions).
ASSEMBLY_TOL = 1e-6

SOLVER = RigidBodyAssemblySolver()


# --- construction helpers -------------------------------------------------------


def iid(n: int) -> uuid.UUID:
    """A fixed, deterministic uuid (so restart-probe inputs are reproducible)."""
    return uuid.UUID(int=n)


def vec3(a: np.ndarray) -> Vec3:
    return Vec3(x=float(a[0]), y=float(a[1]), z=float(a[2]))


def pose(t: tuple[float, float, float], rotvec: tuple[float, float, float]) -> Pose:
    return Pose(
        t=np.array(t, dtype=np.float64),
        q=quat_from_rotvec(np.array(rotvec, dtype=np.float64)),
    )


def _dummy_face_sig() -> PlanarFaceSignature:
    # The solver ignores the signature (item #3 resolves it); a valid stand-in.
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=0.0),
        area_mm2=1.0,
    )


def _dummy_edge_sig() -> EdgeSignature:
    return EdgeSignature(
        curve="circle",
        end_a=Vec3(x=0.0, y=0.0, z=0.0),
        end_b=Vec3(x=0.0, y=0.0, z=0.0),
        midpoint=Vec3(x=0.0, y=0.0, z=0.0),
        length_mm=1.0,
    )


def face_ref(instance_id: uuid.UUID) -> MateFaceRef:
    return MateFaceRef(instance_id=instance_id, signature=_dummy_face_sig())


def axis_ref(instance_id: uuid.UUID) -> MateAxisRef:
    return MateAxisRef(instance_id=instance_id, signature=_dummy_edge_sig())


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


def rotation_matrix(result_placement: Placement) -> np.ndarray:
    return Pose.from_placement(result_placement).matrix()


def placement_of(result: AssemblySolveResult, n: int) -> Placement:
    for p in result.placements:
        if p.instance_id == iid(n):
            return p.placement
    raise AssertionError(f"no placement for instance {n}")


def assert_pose_matches(result: AssemblySolveResult, n: int, target: Pose) -> None:
    got = placement_of(result, n)
    tp = target.to_placement()
    assert got.position.x == pytest.approx(tp.position.x, abs=ASSEMBLY_TOL)
    assert got.position.y == pytest.approx(tp.position.y, abs=ASSEMBLY_TOL)
    assert got.position.z == pytest.approx(tp.position.z, abs=ASSEMBLY_TOL)
    # Compare rotation matrices (quaternion double-cover ±q is one rotation).
    got_r = rotation_matrix(got)
    want_r = target.matrix()
    assert np.allclose(got_r, want_r, atol=ASSEMBLY_TOL)


def pack_placements(result: AssemblySolveResult) -> bytes:
    """All placement floats packed little-endian — the bitwise determinism unit.

    Order is the result's placement order (== input instance order); each
    placement contributes position (x,y,z) then quaternion (x,y,z,w) as float64.
    """
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


# --- shared problem builders (also used by the restart probe) -------------------

# An oblique face normal (neither parallel nor perpendicular to the +Z axis) so
# that a single coincident + concentric pair FULLY locates the free instance
# (6 DOF): the coincident's along-axis component fixes the otherwise-free slide,
# its perpendicular component fixes the otherwise-free spin.
_OBLIQUE_N = np.array([1.0, 0.0, 1.0], dtype=np.float64) / math.sqrt(2.0)
_Z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
_ORIGIN = np.array([0.0, 0.0, 0.0], dtype=np.float64)


def build_bolt_tree_problem() -> tuple[AssemblySolveInput, Pose]:
    """Two plates: A grounded, B located by coincident + concentric to A.

    Fully-located single-parent tree → the closed-form fast path. Returns the
    problem and the analytic target pose of B.
    """
    a_seed = Pose.identity()
    b_target = pose((10.0, 20.0, 30.0), (math.pi / 2, 0.0, 0.0))  # 90° about X
    b_seed = pose((13.0, 18.0, 31.0), (math.radians(70.0), 0.0, 0.0))  # displaced

    coincident = SolverMate(
        mate_id=iid(1001),
        order_index=0,
        mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
        geometry=(
            local_face(a_seed, _ORIGIN, _OBLIQUE_N),
            local_face(b_target, _ORIGIN, -_OBLIQUE_N),
        ),
    )
    concentric = SolverMate(
        mate_id=iid(1002),
        order_index=1,
        mate=ConcentricMate(a=axis_ref(iid(1)), b=axis_ref(iid(2))),
        geometry=(
            local_axis(a_seed, _ORIGIN, _Z),
            local_axis(b_target, _ORIGIN, _Z),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[coincident, concentric],
    )
    return problem, b_target


def build_coupled_problem() -> tuple[AssemblySolveInput, Pose]:
    """B located by a concentric to grounded A1 AND a coincident to grounded A2.

    Two placed parents → NOT a single-parent tree → the numeric LM fallback.
    Fully & consistently locates B (oblique face normal), target known.
    """
    a1_seed = Pose.identity()
    a2_seed = Pose.identity()
    b_target = pose((7.0, -4.0, 12.0), (0.0, math.pi / 3, 0.0))  # 60° about Y
    b_seed = pose((9.0, -1.0, 15.0), (0.0, math.radians(45.0), 0.0))

    concentric = SolverMate(
        mate_id=iid(2001),
        order_index=0,
        mate=ConcentricMate(a=axis_ref(iid(1)), b=axis_ref(iid(3))),
        geometry=(
            local_axis(a1_seed, _ORIGIN, _Z),
            local_axis(b_target, _ORIGIN, _Z),
        ),
    )
    coincident = SolverMate(
        mate_id=iid(2002),
        order_index=1,
        mate=CoincidentMate(a=face_ref(iid(2)), b=face_ref(iid(3)), flush=True),
        geometry=(
            local_face(a2_seed, _ORIGIN, _OBLIQUE_N),
            local_face(b_target, _ORIGIN, -_OBLIQUE_N),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a1_seed),
            instance(2, grounded=True, seed=a2_seed),
            instance(3, grounded=False, seed=b_seed),
        ],
        mates=[concentric, coincident],
    )
    return problem, b_target


# --- fast path ------------------------------------------------------------------


def test_bolt_tree_uses_closed_form_fast_path() -> None:
    """The bolt case propagates from ground with NO iterative solve, landing at
    the hand-derived analytic pose (design §2.2, §6.1)."""
    problem, b_target = build_bolt_tree_problem()
    result = SOLVER.solve(problem)

    assert result.method == "closed_form"  # exact, no iteration
    assert result.status == "well_constrained"
    assert result.diagnosis is None
    assert_pose_matches(result, 2, b_target)
    # Grounded A stays fixed at its seed (identity).
    assert_pose_matches(result, 1, Pose.identity())


def test_lock_mate_fixes_relative_pose() -> None:
    """A two-instance lock holds B rigidly at its authored pose relative to the
    grounded A — closed-form, well-constrained (design §2.3)."""
    a_seed = pose((5.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    b_seed = pose((5.0, 0.0, 40.0), (0.0, 0.0, math.pi / 2))
    lock = SolverMate(
        mate_id=iid(3001),
        order_index=0,
        mate=LockMate(a_instance_id=iid(1), b_instance_id=iid(2)),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[lock],
    )
    result = SOLVER.solve(problem)

    assert result.method == "closed_form"
    assert result.status == "well_constrained"
    # With A fixed at its seed, the lock leaves B at its authored pose.
    assert_pose_matches(result, 2, b_seed)


# --- numeric fallback -----------------------------------------------------------


def test_coupled_graph_uses_numeric_solver() -> None:
    """A free instance constrained to TWO grounded parents is not a single-parent
    tree → the deterministic LM fallback converges to the known pose (§2.2)."""
    problem, b_target = build_coupled_problem()
    result = SOLVER.solve(problem)

    assert result.method == "numeric"
    assert result.status == "well_constrained"
    assert result.diagnosis is None
    assert_pose_matches(result, 3, b_target)


# --- determinism (RESEARCH §9) --------------------------------------------------


def test_solve_is_deterministic_bitwise() -> None:
    """Same input, two fresh solver instances → byte-identical placements, for
    BOTH the closed-form and numeric paths (RESEARCH §9 solver-determinism)."""
    for build in (build_bolt_tree_problem, build_coupled_problem):
        problem, _ = build()
        first = pack_placements(RigidBodyAssemblySolver().solve(problem))
        second = pack_placements(RigidBodyAssemblySolver().solve(problem))
        assert first == second


_RESTART_PROBE = """\
import importlib.util, sys
spec = importlib.util.spec_from_file_location("assembly_probe", {path!r})
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
from geometry.assembly import RigidBodyAssemblySolver
problem, _ = mod.{builder}()
sys.stdout.write(RigidBodyAssemblySolver().solve(problem).model_dump_json())
"""


@pytest.mark.parametrize(
    "builder", ["build_bolt_tree_problem", "build_coupled_problem"]
)
def test_solve_is_deterministic_across_interpreter_restart(builder: str) -> None:
    """A fresh-interpreter solve (worker-restart emulation, RESEARCH §9) yields
    byte-identical placements to the in-process solve."""
    problem, _ = globals()[builder]()
    in_process = pack_placements(RigidBodyAssemblySolver().solve(problem))

    proc = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE.format(path=__file__, builder=builder)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"restart probe failed:\n{proc.stderr}"
    restarted = pack_placements(AssemblySolveResult.model_validate_json(proc.stdout))
    assert in_process == restarted


# --- under-constrained (a first-class, NON-fatal status) ------------------------


def test_single_coincident_is_under_constrained_not_an_error() -> None:
    """One coincident mate leaves 3 DOF: the solve REPORTS them (remaining_dof=3),
    returns a valid seed-consistent placement, and never raises (design §2.4)."""
    a_seed = Pose.identity()
    b_seed = pose((5.0, 7.0, 0.0), (0.0, 0.0, 0.0))  # already flush on z=0
    coincident = SolverMate(
        mate_id=iid(4001),
        order_index=0,
        mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
        geometry=(
            local_face(a_seed, _ORIGIN, _Z),
            local_face(b_seed, _ORIGIN, -_Z),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[coincident],
    )
    result = SOLVER.solve(problem)

    assert result.status == "under_constrained"
    assert result.method == "numeric"  # a partial constraint falls to the LM
    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof == 3
    assert result.diagnosis.classification is None
    # Seed-consistent: the free DOF are left at the authored seed.
    assert_pose_matches(result, 2, b_seed)


# --- over-constrained (redundant, consistent → NOT an error) --------------------


def test_redundant_mate_is_over_constrained_removable() -> None:
    """A lock that fully fixes B plus a consistent coincident → over-constrained:
    the coincident is redundant + removable, the assembly still solves (§2.4)."""
    a_seed = Pose.identity()
    b_seed = pose((0.0, 0.0, 15.0), (0.0, 0.0, 0.0))
    lock = SolverMate(
        mate_id=iid(5001),
        order_index=0,  # processed first → keeps rank; the coincident is redundant
        mate=LockMate(a_instance_id=iid(1), b_instance_id=iid(2)),
    )
    coincident = SolverMate(
        mate_id=iid(5002),
        order_index=1,
        mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
        geometry=(
            local_face(a_seed, np.array([0.0, 0.0, 5.0]), _Z),
            local_face(b_seed, np.array([0.0, 0.0, 5.0]), -_Z),  # consistent at seed
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[lock, coincident],
    )
    result = SOLVER.solve(problem)

    assert result.status == "over_constrained"
    assert result.diagnosis is not None
    assert result.diagnosis.classification == "redundant"
    assert result.diagnosis.removable is True
    assert iid(5002) in result.diagnosis.redundant_mates
    assert result.diagnosis.remaining_dof == 0
    # A consistent over-constraint still solves (B stays locked at its seed).
    assert_pose_matches(result, 2, b_seed)


# --- conflicting (unsatisfiable → the fatal case, names offenders) --------------


def test_contradictory_mates_are_conflicting_with_offenders() -> None:
    """B's one face pinned flush to two parallel planes at different heights is
    unsatisfiable → conflicting, naming the offending mate ids, no hang (§2.4)."""
    a_seed = Pose.identity()
    b_seed = pose((0.0, 0.0, 3.0), (0.0, 0.0, 0.0))
    b_face = local_face(b_seed, _ORIGIN, -_Z)  # the SAME physical face, twice
    mate_low = SolverMate(
        mate_id=iid(6001),
        order_index=0,
        mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
        geometry=(local_face(a_seed, np.array([0.0, 0.0, 0.0]), _Z), b_face),
    )
    mate_high = SolverMate(
        mate_id=iid(6002),
        order_index=1,
        mate=CoincidentMate(a=face_ref(iid(1)), b=face_ref(iid(2)), flush=True),
        geometry=(local_face(a_seed, np.array([0.0, 0.0, 10.0]), _Z), b_face),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[mate_low, mate_high],
    )
    result = SOLVER.solve(problem)

    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert result.diagnosis.classification == "conflicting"
    assert result.diagnosis.removable is False
    assert iid(6001) in result.diagnosis.conflicting_mates
    assert iid(6002) in result.diagnosis.conflicting_mates
    assert result.diagnosis.suggested_fix is not None


# --- quaternion handling --------------------------------------------------------


def test_zero_rotvec_is_identity_quaternion() -> None:
    q = quat_from_rotvec(np.zeros(3))
    assert np.allclose(q, np.array([0.0, 0.0, 0.0, 1.0]), atol=ASSEMBLY_TOL)


def test_seed_quaternion_is_renormalised() -> None:
    """A non-unit authored quaternion is renormalised on the way in (design §2.3
    — the boundary need not carry an exactly-unit quaternion)."""
    from py_kit.schemas.assemblies import Placement, Quat

    placement = Placement(
        position=Vec3(x=0.0, y=0.0, z=0.0), orientation=Quat(x=0.0, y=0.0, z=0.0, w=2.0)
    )
    p = Pose.from_placement(placement)
    assert float(np.linalg.norm(p.q)) == pytest.approx(1.0, abs=ASSEMBLY_TOL)


def test_ninety_degree_rotation_resolves_correctly() -> None:
    """The bolt target carries a 90° rotation; the solver recovers the quaternion
    (checked via the rotation matrix, immune to the ±q double cover)."""
    problem, _b_target = build_bolt_tree_problem()
    result = SOLVER.solve(problem)
    got_r = rotation_matrix(placement_of(result, 2))
    # 90° about X maps +Y → +Z.
    mapped = got_r @ np.array([0.0, 1.0, 0.0])
    assert np.allclose(mapped, np.array([0.0, 0.0, 1.0]), atol=ASSEMBLY_TOL)


# --- malformed input raises (the exception-vs-status contract) ------------------


def test_mate_referencing_unknown_instance_raises() -> None:
    problem = AssemblySolveInput(
        instances=[instance(1, grounded=True, seed=Pose.identity())],
        mates=[
            SolverMate(
                mate_id=iid(7001),
                order_index=0,
                mate=LockMate(a_instance_id=iid(1), b_instance_id=iid(99)),
            )
        ],
    )
    with pytest.raises(AssemblyDefinitionError):
        SOLVER.solve(problem)


def test_wrong_resolved_geometry_kind_raises() -> None:
    """A concentric mate given a resolved FACE (not an axis) is malformed."""
    a_seed = Pose.identity()
    b_seed = Pose.identity()
    bad = SolverMate(
        mate_id=iid(7002),
        order_index=0,
        mate=ConcentricMate(a=axis_ref(iid(1)), b=axis_ref(iid(2))),
        geometry=(
            local_face(a_seed, _ORIGIN, _Z),  # a face where an axis is required
            local_axis(b_seed, _ORIGIN, _Z),
        ),
    )
    problem = AssemblySolveInput(
        instances=[
            instance(1, grounded=True, seed=a_seed),
            instance(2, grounded=False, seed=b_seed),
        ],
        mates=[bad],
    )
    with pytest.raises(AssemblyDefinitionError):
        SOLVER.solve(problem)


def test_empty_assembly_raises() -> None:
    with pytest.raises(AssemblyDefinitionError):
        SOLVER.solve(AssemblySolveInput(instances=[]))
