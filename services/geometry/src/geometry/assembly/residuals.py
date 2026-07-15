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
- ``concentric(A, B)`` → ``[dA x dB, (pB-pA) - ((pB-pA)·dA) dA]`` — axes parallel
  plus lines coincident.
- ``angle(A, B)`` → ``[nA·nB - cos θ]`` — the angle between normals (fast-follow).
- ``lock(A, B)`` → ``[tB - t*, log(qB ⊗ q*⁻¹)]`` where ``(t*, q*) = A ∘ rel`` and
  ``rel`` is the authored seed relative pose — B rigidly fixed to A.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from py_kit.schemas.assemblies import (
    AngleMate,
    CoincidentMate,
    ConcentricMate,
    DistanceMate,
    LockMate,
    MateParams,
    mate_instance_ids,
)

from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    ResolvedAxis,
    ResolvedFace,
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

CompiledMateKind = Literal["coincident", "concentric", "angle", "lock"]

_ZERO3 = np.zeros(3, dtype=np.float64)


@dataclass(frozen=True)
class CompiledMate:
    """A mate in solver-internal form (see the module docstring).

    For a face mate ``dir_a``/``dir_b`` are unit normals; for ``concentric`` they
    are unit axis directions; ``point_a``/``point_b`` are on the plane/axis. All
    arrays are in the respective instance's LOCAL frame. ``lock_rel`` is the
    authored relative pose for a lock mate (``None`` otherwise).
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
    lock_rel: Pose | None

    def residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
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

        # angle
        na_w = pose_a.apply_direction(self.dir_a)
        nb_w = pose_b.apply_direction(self.dir_b)
        return np.array([float(np.dot(na_w, nb_w)) - self.cos_theta], dtype=np.float64)


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
    lock_rel: Pose | None = None

    if isinstance(mate, LockMate):
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
        lock_rel=lock_rel,
    )
