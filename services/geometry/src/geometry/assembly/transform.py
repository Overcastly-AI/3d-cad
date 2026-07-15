"""Rigid-body transform + unit-quaternion math for the assembly solver.

Pure numpy (no kernel type, no GPL) — the numeric core the ``AssemblySolver``
manipulates (design ``docs/design/assemblies.md`` §2.3). A pose is a rigid
transform ``x = (t ∈ ℝ³, q ∈ S³)`` acting on a point as ``world = R(q)·local +
t``. Quaternions are stored ``(x, y, z, w)`` to match
:class:`py_kit.schemas.assemblies.Quat` (identity ``(0, 0, 0, 1)``), so no lossy
representation change happens at the boundary.

Determinism (RESEARCH §9): every routine is a fixed sequence of float64 numpy
ops — same inputs in, bitwise-identical bytes out. There is no random state, no
iteration-order dependence, and no ad-hoc epsilon that changes the result value
(the small guards below only pick the numerically-stable branch of an exact
limit, e.g. the small-angle expansion of the quaternion exponential).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from py_kit.schemas.assemblies import Placement, Quat
from py_kit.schemas.geometry import Vec3

Vector = NDArray[np.float64]

#: Below this rotation-vector / quaternion-vector magnitude the exact
#: trig limit is replaced by its first-order expansion (both are the SAME
#: analytic value; this only avoids a 0/0). Not a tolerance on the result.
_SMALL_ANGLE = 1e-12


def as_vector(vec: Vec3) -> Vector:
    """A :class:`Vec3` DTO as a float64 3-vector."""
    return np.array([vec.x, vec.y, vec.z], dtype=np.float64)


def as_vec3(vec: Vector) -> Vec3:
    """A float64 3-vector back as a :class:`Vec3` DTO (full precision)."""
    return Vec3(x=float(vec[0]), y=float(vec[1]), z=float(vec[2]))


def normalize(vec: Vector) -> Vector:
    """Unit vector; a zero vector is returned unchanged (degenerate guard)."""
    n = float(np.linalg.norm(vec))
    if n == 0.0:
        return vec
    return vec / n


def quat_normalize(q: Vector) -> Vector:
    """Renormalise a quaternion to the unit sphere.

    Called after every solver step (design §2.2) so the pose stays a valid
    rotation; a zero quaternion degrades to identity rather than NaN.
    """
    n = float(np.linalg.norm(q))
    if n == 0.0:
        return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    return q / n


def quat_conjugate(q: Vector) -> Vector:
    """Conjugate ``(-x, -y, -z, w)`` — the inverse of a UNIT quaternion."""
    return np.array([-q[0], -q[1], -q[2], q[3]], dtype=np.float64)


def quat_multiply(a: Vector, b: Vector) -> Vector:
    """Hamilton product ``a ⊗ b`` in ``(x, y, z, w)`` order."""
    ax, ay, az, aw = a[0], a[1], a[2], a[3]
    bx, by, bz, bw = b[0], b[1], b[2], b[3]
    return np.array(
        [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ],
        dtype=np.float64,
    )


def quat_to_matrix(q: Vector) -> NDArray[np.float64]:
    """Rotation matrix ``R(q)`` of a (near-)unit quaternion ``(x, y, z, w)``."""
    x, y, z, w = q[0], q[1], q[2], q[3]
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def quat_from_rotvec(rotvec: Vector) -> Vector:
    """Quaternion exponential of a rotation vector (axis · angle).

    The solver's local increment lives in ℝ³ (a rotation vector); this maps it
    onto the unit sphere so the 6-DOF step retracts cleanly onto the manifold.
    """
    theta = float(np.linalg.norm(rotvec))
    if theta < _SMALL_ANGLE:
        return quat_normalize(
            np.array(
                [rotvec[0] / 2, rotvec[1] / 2, rotvec[2] / 2, 1.0], dtype=np.float64
            )
        )
    axis = rotvec / theta
    s = math.sin(theta / 2)
    return np.array(
        [axis[0] * s, axis[1] * s, axis[2] * s, math.cos(theta / 2)], dtype=np.float64
    )


def rotvec_from_quat(q: Vector) -> Vector:
    """Quaternion logarithm — the rotation vector of a unit quaternion.

    Used for the ``lock`` mate's orientation residual (design §2.3): the
    shortest-arc rotation carrying one orientation to another.
    """
    q = quat_normalize(q)
    if q[3] < 0:  # shortest arc — the two antipodal quaternions are one rotation
        q = -q
    v = q[:3]
    vn = float(np.linalg.norm(v))
    if vn < _SMALL_ANGLE:
        return 2.0 * v
    theta = 2.0 * math.atan2(vn, float(q[3]))
    return (theta / vn) * v


def matrix_to_quat(rot: NDArray[np.float64]) -> Vector:
    """Unit quaternion of a proper rotation matrix (Shepperd's method).

    Branch selection keys off the largest diagonal term for numerical
    stability; the branch is a pure function of the matrix, so the result is
    deterministic.
    """
    m = rot
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    return quat_normalize(np.array([x, y, z, w], dtype=np.float64))


@dataclass(frozen=True)
class Pose:
    """A rigid transform ``(t, q)`` acting ``world = R(q)·local + t``.

    Immutable; every operation returns a fresh :class:`Pose`. ``q`` is kept
    normalised by construction (the constructors below and every solver step
    renormalise).
    """

    t: Vector
    q: Vector

    @staticmethod
    def identity() -> Pose:
        return Pose(
            t=np.zeros(3, dtype=np.float64),
            q=np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64),
        )

    @staticmethod
    def from_placement(placement: Placement) -> Pose:
        """Seed pose from an authored :class:`Placement` (renormalising ``q``)."""
        o = placement.orientation
        return Pose(
            t=as_vector(placement.position),
            q=quat_normalize(np.array([o.x, o.y, o.z, o.w], dtype=np.float64)),
        )

    def to_placement(self) -> Placement:
        """This pose as a wire :class:`Placement` (full precision, unit ``q``)."""
        q = quat_normalize(self.q)
        return Placement(
            position=as_vec3(self.t),
            orientation=Quat(
                x=float(q[0]), y=float(q[1]), z=float(q[2]), w=float(q[3])
            ),
        )

    def matrix(self) -> NDArray[np.float64]:
        return quat_to_matrix(self.q)

    def apply_point(self, local: Vector) -> Vector:
        return self.matrix() @ local + self.t

    def apply_direction(self, local: Vector) -> Vector:
        return self.matrix() @ local

    def compose(self, other: Pose) -> Pose:
        """``self ∘ other`` — apply ``other`` then ``self``."""
        return Pose(
            t=self.matrix() @ other.t + self.t,
            q=quat_normalize(quat_multiply(self.q, other.q)),
        )

    def inverse(self) -> Pose:
        rinv = self.matrix().T
        return Pose(t=-(rinv @ self.t), q=quat_conjugate(self.q))

    def retract(self, delta_t: Vector, delta_rotvec: Vector) -> Pose:
        """Apply a local 6-DOF increment ``(δt, δω)`` and renormalise.

        The rotation increment is a world-frame left-multiplication
        (``q ← exp(δω) ⊗ q``); paired with the finite-difference Jacobian that
        uses the SAME retraction, the linearisation is self-consistent.
        """
        return Pose(
            t=self.t + delta_t,
            q=quat_normalize(quat_multiply(quat_from_rotvec(delta_rotvec), self.q)),
        )


def relative_pose(a: Pose, b: Pose) -> Pose:
    """The transform ``rel`` with ``a ∘ rel = b`` — b expressed in a's frame."""
    return a.inverse().compose(b)
