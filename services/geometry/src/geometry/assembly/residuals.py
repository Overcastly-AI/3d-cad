"""Per-mate residual math (design ``docs/design/assemblies.md`` §2.3).

A :class:`CompiledMate` is the solver-internal form of one
:class:`~geometry.assembly.protocol.SolverMate`: the resolved geometry lifted to
float64 numpy arrays, the two instance indices it couples, and a residual
evaluated in the WORLD frame given the two instances' current poses. The
residual vanishes exactly when the mate is satisfied. Compiling is where
malformed input is rejected (:class:`AssemblyDefinitionError`).

The structured geometry is kept on the dataclass (not hidden in a closure) so
the closed-form fast path (:mod:`geometry.assembly.solver`) can read the local
face/axis directly.

Residuals (world frame, design §2.3):

- ``coincident(A, B, flush)`` → ``[nA·(pB-pA) - target, nA ± nB]`` — a signed gap
  along the normal (``target`` = 0, or ``distance_mm`` for a distance mate) plus
  normals anti-parallel (flush, ``nA + nB``) / parallel (``nA - nB``).
- ``distance(A, B)`` → the SAME coincident residual with ``target = distance_mm``
  and the flush (anti-parallel) alignment. PINNED SIGN CONVENTION (design §2.3):
  ``distance_mm`` is the signed gap measured along face A's OUTWARD normal ``nA``
  — at the solution ``nA·(pB-pA) = distance_mm``, so ``pB`` sits ``distance_mm``
  along ``+nA`` from ``pA`` (positive = a gap on the ``+nA`` side, negative = B on
  the ``-nA`` side, zero = a plain flush coincident). Proved by the
  ``assembly-two-plates-gap`` golden + ``test_assembly_distance_angle``.
- ``concentric(A, B)`` → ``[dA x dB, (pB-pA) - ((pB-pA)·dA) dA]`` — axes parallel
  plus lines coincident.
- ``angle(A, B)`` → ``[sin(φ - θ)]`` for a non-degenerate target θ (``sinφ·cosθ -
  cosφ·sinθ`` with ``cosφ = nA·nB``, ``sinφ = ‖nAxnB‖``), falling back to
  ``[cosφ - cosθ]`` at the (anti)parallel degenerate. PINNED ANGLE CONVENTION
  (design §2.3): ``angle_deg`` is the angle φ between the two OUTWARD normals,
  ``acos(nA·nB) = angle_deg`` (no flush sense). ``sin(φ - θ)`` keeps the Jacobian
  row full-strength at the target so the numeric LM converges cleanly (the scalar
  ``nA·nB - cosθ`` is flat near alignment and stalls); see :meth:`residual`.
- ``lock(A, B)`` → ``[tB - t*, log(qB ⊗ q*⁻¹)]`` where ``(t*, q*) = A ∘ rel`` and
  ``rel`` is the authored seed relative pose — B rigidly fixed to A.
- ``joint(A, B)`` → frame-to-frame rows from :mod:`geometry.assembly.joint_math`
  (6 hard rows, plus one DRIVING row when the joint's value is set; the last
  ``drive_rows`` rows of the block are the driving ones).
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
from loft_wire.assemblies import (
    AngleMate,
    CoincidentMate,
    ConcentricMate,
    DistanceMate,
    LockMate,
    MateParams,
    mate_instance_ids,
)
from loft_wire.joints import JointMate
from numpy.typing import NDArray

from geometry.assembly.joint_math import (
    SOLVED_MOTIONS,
    CompiledJoint,
    LocalFrame,
    compile_joint,
)
from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    ResolvedAxis,
    ResolvedFace,
    ResolvedFrame,
    ResolvedMateGeometry,
    SolverMate,
)
from geometry.assembly.transform import (
    Pose,
    as_vector,
    normalize,
    quat_conjugate,
    quat_multiply,
    relative_pose,
    rotvec_from_quat,
)

Vector = NDArray[np.float64]

CompiledMateKind = Literal["coincident", "concentric", "angle", "lock", "joint"]

_ZERO3 = np.zeros(3, dtype=np.float64)

#: sinθ below this treats the angle target as the (anti)parallel DEGENERATE (θ
#: within ~2.6e-4° of 0° or 180°) and switches the angle residual from the
#: well-conditioned sin(φ - θ) form to (cosφ - cosθ), whose sign distinguishes
#: parallel from anti-parallel (see :meth:`CompiledMate.residual`). Far above the
#: solver's float64 noise, far below any real non-degenerate angle mate.
_ANGLE_DEGENERATE_SIN = 1e-9


@dataclass(frozen=True)
class CompiledMate:
    """A mate in solver-internal form (see the module docstring).

    For a face mate ``dir_a``/``dir_b`` are unit normals; for ``concentric`` they
    are unit axis directions; ``point_a``/``point_b`` are on the plane/axis. All
    arrays are in the respective instance's LOCAL frame. ``lock_rel`` is the
    authored relative pose for a lock mate (``None`` otherwise). ``joint`` is the
    compiled joint for a ``joint`` mate (``None`` otherwise), whose last
    ``drive_rows`` residual rows are driving rows, not hard constraints.
    """

    mate_id: uuid.UUID
    order_index: int
    kind: CompiledMateKind
    idx_a: int
    idx_b: int
    rows: int
    point_a: Vector
    dir_a: Vector
    point_b: Vector
    dir_b: Vector
    target: float
    flush: bool
    cos_theta: float
    sin_theta: float
    lock_rel: Pose | None
    joint: CompiledJoint | None = None
    drive_rows: int = 0

    def residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
        if self.kind == "joint":
            assert self.joint is not None
            return self.joint.residual(pose_a, pose_b)

        if self.kind == "lock":
            assert self.lock_rel is not None
            desired = pose_a.compose(self.lock_rel)
            pos_err = pose_b.t - desired.t
            rot_err = rotvec_from_quat(
                quat_multiply(pose_b.q, quat_conjugate(desired.q))
            )
            return np.concatenate([pos_err, rot_err])

        if self.kind == "coincident":
            pa_w = pose_a.apply_point(self.point_a)
            na_w = pose_a.apply_direction(self.dir_a)
            pb_w = pose_b.apply_point(self.point_b)
            nb_w = pose_b.apply_direction(self.dir_b)
            gap = float(np.dot(na_w, pb_w - pa_w)) - self.target
            alignment = na_w + nb_w if self.flush else na_w - nb_w
            return np.array(
                [gap, alignment[0], alignment[1], alignment[2]], dtype=np.float64
            )

        if self.kind == "concentric":
            pa_w = pose_a.apply_point(self.point_a)
            da_w = pose_a.apply_direction(self.dir_a)
            pb_w = pose_b.apply_point(self.point_b)
            db_w = pose_b.apply_direction(self.dir_b)
            parallel: Vector = np.cross(da_w, db_w)
            w = pb_w - pa_w
            perp = w - float(np.dot(w, da_w)) * da_w
            return np.concatenate([parallel, perp])

        # angle: drive the angle φ between the two outward normals to the target
        # θ, where cosφ = n_A·n_B and sinφ = ‖n_A x n_B‖ (≥ 0 since φ ∈ [0, π]).
        na_w = pose_a.apply_direction(self.dir_a)
        nb_w = pose_b.apply_direction(self.dir_b)
        cos_phi = float(np.dot(na_w, nb_w))
        if self.sin_theta >= _ANGLE_DEGENERATE_SIN:
            # Non-degenerate target θ ∈ (0°, 180°): residual sin(φ - θ) =
            # sinφ·cosθ - cosφ·sinθ, NOT the scalar (n_A·n_B - cosθ). Both vanish
            # exactly at φ = θ, but d/dφ of sin(φ - θ) is cos(φ - θ) = 1 at the
            # target whereas d/dφ of (cosφ - cosθ) is -sinφ, which collapses toward
            # the parallel/anti-parallel ends and stalls the LM seed-dependently
            # just short of tolerance. sin(φ - θ) keeps the Jacobian row
            # full-strength at the target so the numeric solve converges cleanly.
            # Unique zero in [0, π] at φ = θ; no division → NaN-free everywhere.
            sin_phi = float(np.linalg.norm(np.cross(na_w, nb_w)))
            return np.array(
                [sin_phi * self.cos_theta - cos_phi * self.sin_theta],
                dtype=np.float64,
            )
        # Degenerate target: exactly parallel (θ ≈ 0°, cosθ = +1) or anti-parallel
        # (θ ≈ 180°, cosθ = -1). sin(φ - θ) can't distinguish the two ends (sinφ
        # vanishes at both), so use (cosφ - cosθ): its SIGN pins parallel vs
        # anti-parallel and it still drives the correct direction. The gradient
        # vanishes at the target (an inherent zero-gradient bifurcation of the
        # (anti)parallel configuration), so this end is the honest degenerate the
        # diagnosis reports as under_constrained / not_converged — never NaN, never
        # a wrong pose claimed well_constrained (design §2.3).
        return np.array([cos_phi - self.cos_theta], dtype=np.float64)


def _face(geom: ResolvedMateGeometry, mate_type: str, slot: str) -> ResolvedFace:
    if not isinstance(geom, ResolvedFace):
        raise AssemblyDefinitionError(
            f"{mate_type} mate slot {slot!r} requires a resolved planar face, "
            f"got {geom.kind!r}"
        )
    return geom


def _axis(geom: ResolvedMateGeometry, mate_type: str, slot: str) -> ResolvedAxis:
    if not isinstance(geom, ResolvedAxis):
        raise AssemblyDefinitionError(
            f"{mate_type} mate slot {slot!r} requires a resolved axis, "
            f"got {geom.kind!r}"
        )
    return geom


def _local_frame(geom: ResolvedMateGeometry, motion: str, slot: str) -> LocalFrame:
    if not isinstance(geom, ResolvedFrame):
        raise AssemblyDefinitionError(
            f"{motion} joint slot {slot!r} requires a resolved frame, got {geom.kind!r}"
        )
    # Columns [x, z x x, z]: X is re-orthogonalised against Z so a synthetic
    # frame that is not exactly orthonormal still gives a proper rotation.
    z = normalize(as_vector(geom.z))
    x_raw = as_vector(geom.x)
    x = x_raw - float(np.dot(x_raw, z)) * z
    if float(np.linalg.norm(z)) == 0.0 or float(np.linalg.norm(x)) < 1e-9:
        raise AssemblyDefinitionError(
            f"{motion} joint slot {slot!r} has a degenerate frame (zero or "
            "parallel axes)"
        )
    x = normalize(x)
    return LocalFrame(
        origin=as_vector(geom.origin), rot=np.column_stack([x, np.cross(z, x), z])
    )


def _compile_joint(solver_mate: SolverMate, mate: JointMate) -> CompiledJoint:
    if mate.motion not in SOLVED_MOTIONS:
        raise AssemblyDefinitionError(
            f"a {mate.motion} joint is not supported by the solver yet"
        )
    geometry = _require_geometry(solver_mate)
    return compile_joint(
        mate,
        _local_frame(geometry[0], mate.motion, "a"),
        _local_frame(geometry[1], mate.motion, "b"),
    )


def _require_geometry(
    solver_mate: SolverMate,
) -> tuple[ResolvedMateGeometry, ResolvedMateGeometry]:
    geometry = solver_mate.geometry
    if geometry is None:
        raise AssemblyDefinitionError(
            f"{solver_mate.mate.type} mate {solver_mate.mate_id} requires resolved "
            "geometry for both slots"
        )
    return geometry


def compile_mate(
    solver_mate: SolverMate,
    index_of: Mapping[uuid.UUID, int],
    seed_poses: list[Pose],
) -> CompiledMate:
    """Lift a :class:`SolverMate` to a :class:`CompiledMate`.

    ``index_of`` maps instance id → index; ``seed_poses`` (indexed likewise)
    derives a ``lock`` mate's target relative pose from the authored seeds.
    Raises :class:`AssemblyDefinitionError` for an unknown instance, a self-mate,
    or resolved geometry of the wrong kind for the mate.
    """
    mate: MateParams = solver_mate.mate
    ids = mate_instance_ids(mate)
    for inst_id in ids:
        if inst_id not in index_of:
            raise AssemblyDefinitionError(
                f"mate {solver_mate.mate_id} references unknown instance {inst_id}"
            )
    idx_a = index_of[ids[0]]
    idx_b = index_of[ids[1]]
    if idx_a == idx_b:
        raise AssemblyDefinitionError(
            f"mate {solver_mate.mate_id} constrains an instance to itself"
        )

    kind: CompiledMateKind
    point_a = _ZERO3
    dir_a = _ZERO3
    point_b = _ZERO3
    dir_b = _ZERO3
    target = 0.0
    flush = True
    cos_theta = 0.0
    sin_theta = 0.0
    lock_rel: Pose | None = None
    joint: CompiledJoint | None = None

    if isinstance(mate, JointMate):
        kind = "joint"
        joint = _compile_joint(solver_mate, mate)
        rows = joint.rows
    elif isinstance(mate, LockMate):
        kind = "lock"
        rows = 6
        lock_rel = relative_pose(seed_poses[idx_a], seed_poses[idx_b])
    elif isinstance(mate, CoincidentMate | DistanceMate):
        kind = "coincident"
        rows = 4
        fa = _face(_require_geometry(solver_mate)[0], mate.type, "a")
        fb = _face(_require_geometry(solver_mate)[1], mate.type, "b")
        point_a = as_vector(fa.point)
        dir_a = normalize(as_vector(fa.normal))
        point_b = as_vector(fb.point)
        dir_b = normalize(as_vector(fb.normal))
        # PINNED SIGN CONVENTION (design §2.3; proved by assembly-two-plates-gap +
        # test_assembly_distance_angle): a distance mate rides the coincident
        # residual with target = distance_mm and the flush (anti-parallel)
        # alignment. distance_mm is the SIGNED gap along face A's OUTWARD normal
        # n_A — at the solution n_A·(p_B - p_A) = distance_mm, so p_B sits
        # distance_mm along +n_A from p_A (positive = gap on the +n_A side,
        # negative = B on the -n_A side, zero = a plain flush coincident).
        target = mate.distance_mm if isinstance(mate, DistanceMate) else 0.0
        flush = mate.flush if isinstance(mate, CoincidentMate) else True
    elif isinstance(mate, ConcentricMate):
        kind = "concentric"
        rows = 6
        aa = _axis(_require_geometry(solver_mate)[0], mate.type, "a")
        ab = _axis(_require_geometry(solver_mate)[1], mate.type, "b")
        point_a = as_vector(aa.point)
        dir_a = normalize(as_vector(aa.direction))
        point_b = as_vector(ab.point)
        dir_b = normalize(as_vector(ab.direction))
    else:  # AngleMate — the only remaining member of the Mate union
        assert isinstance(mate, AngleMate)
        kind = "angle"
        rows = 1
        fa = _face(_require_geometry(solver_mate)[0], mate.type, "a")
        fb = _face(_require_geometry(solver_mate)[1], mate.type, "b")
        point_a = as_vector(fa.point)
        dir_a = normalize(as_vector(fa.normal))
        point_b = as_vector(fb.point)
        dir_b = normalize(as_vector(fb.normal))
        cos_theta = math.cos(math.radians(mate.angle_deg))
        sin_theta = math.sin(math.radians(mate.angle_deg))

    return CompiledMate(
        mate_id=solver_mate.mate_id,
        order_index=solver_mate.order_index,
        kind=kind,
        idx_a=idx_a,
        idx_b=idx_b,
        rows=rows,
        point_a=point_a,
        dir_a=dir_a,
        point_b=point_b,
        dir_b=dir_b,
        target=target,
        flush=flush,
        cos_theta=cos_theta,
        sin_theta=sin_theta,
        lock_rel=lock_rel,
        joint=joint,
        drive_rows=joint.drive_rows if joint is not None else 0,
    )
