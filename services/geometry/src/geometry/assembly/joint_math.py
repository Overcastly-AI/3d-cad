"""Joint frames, residuals and measurement for the assembly solver (S4a).

A joint (:class:`loft_wire.joints.JointMate`) pairs two FRAMES, one on each
instance, and names the motion left free between them (Fusion 360 joints,
Onshape mate connectors). This module is the numeric half: pure numpy, no
kernel type. :mod:`geometry.assembly.joint_origins` resolves each
:class:`~loft_wire.joints.JointOrigin` against the part body into a
:class:`LocalFrame` in that instance's LOCAL part frame; this module turns the
two frames plus the motion into solver rows. Conventions (RESEARCH §21):

- **Alignment.** A joint brings the two frames together the way Fusion and
  Onshape do: origins coincident, Z axes OPPOSED and X axes aligned, so two
  outward face normals meet face to face (the legacy ``coincident`` mate's
  ``flush``). Formally ``F_B = F_A ∘ T(rot, lin)`` with
  ``T = Trans(0, 0, offset + lin) ∘ RotZ(angle + rot) ∘ RotX(π)``.
- **Free axes.** Rigid frees nothing; revolute frees ``rot`` about A's Z;
  slider frees ``lin`` along A's Z. ``offset_mm`` / ``angle_deg`` are the fixed
  shift and turn of the relation (the wire's definition).
- **Rows.** Every joint has 6 HARD rows (rank 6 rigid, 5 revolute, 5 slider)
  plus one DRIVING row when its ``value`` is set. Remaining DOF counts the hard
  rows only, so a driven hinge is fully PLACED yet still reports its 1 DOF, as
  Fusion does.
- **Measurement.** ``rot`` is the signed angle from A's X axis (turned by
  ``angle_deg``) to B's X axis about A's Z, wrapped to (-180°, 180°]; ``lin`` is
  ``(p_B - p_A)·z_A - offset_mm``.

Determinism (RESEARCH §9): fixed sequences of float64 numpy ops.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import numpy as np
from loft_wire.joints import JointMate, JointState
from numpy.typing import NDArray

from geometry.assembly.transform import (
    Pose,
    as_vec3,
    matrix_to_quat,
    rotvec_from_quat,
)

Vector = NDArray[np.float64]
Matrix = NDArray[np.float64]

#: Joint motions the S4a solver places. Cylindrical, planar and ball are stored
#: and edited but dropped as ``mate_unsupported`` until S4b.
SOLVED_MOTIONS: frozenset[str] = frozenset({"rigid", "revolute", "slider"})

#: Hard rows per solved joint (rank 6 rigid, 5 revolute/slider; see module docs).
HARD_ROWS = 6

#: Two reference-axis alignments within this of each other count as a TIE in
#: :func:`reference_x`, so OCCT round-off on an axis-aligned direction (a normal
#: of ``(1e-17, 0, 1)``) cannot swap the chosen reference from X to Y and turn
#: the frame 90°. Far above float64 noise, far below any real tilt.
REFERENCE_TIE_TOL = 1e-9

_HALF_TURN_X = np.diag(np.array([1.0, -1.0, -1.0], dtype=np.float64))


def rot_z(theta: float) -> Matrix:
    """Rotation by ``theta`` radians about +Z (right-handed)."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array(
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def wrap_pi(angle: float) -> float:
    """``angle`` (radians) wrapped to (-π, π]."""
    wrapped = math.remainder(angle, 2.0 * math.pi)
    if wrapped <= -math.pi:
        wrapped += 2.0 * math.pi
    return wrapped


def wrap_deg(angle: float) -> float:
    """``angle`` (degrees) wrapped to (-180, 180]."""
    wrapped = math.remainder(angle, 360.0)
    if wrapped <= -180.0:
        wrapped += 360.0
    return wrapped


def _unit(vec: Vector) -> Vector:
    n = float(np.linalg.norm(vec))
    if n == 0.0:
        raise ValueError("a joint frame axis has zero length")
    return vec / n


def reference_x(z: Vector) -> Vector:
    """The deterministic in-plane X axis of a frame with unit Z ``z``.

    The world (instance-local) axis LEAST aligned with ``z`` (ties within
    :data:`REFERENCE_TIE_TOL` broken X < Y < Z), with its ``z`` component
    projected out. The rule of :func:`geometry.kernel.faces.deterministic_x_dir`
    (a face-normal +Z gives +X, a +X axis gives +Y), plus the tie band. Even in
    ``z``: ``reference_x(-z) == reference_x(z)``.
    """
    aligned = np.abs(z)
    best = float(aligned.min())
    index = next(i for i in range(3) if float(aligned[i]) <= best + REFERENCE_TIE_TOL)
    axis = np.zeros(3, dtype=np.float64)
    axis[index] = 1.0
    return _unit(axis - float(np.dot(axis, z)) * z)


@dataclass(frozen=True)
class LocalFrame:
    """A right-handed frame in an instance's LOCAL part frame.

    ``rot`` holds the unit axes as columns ``[x, y, z]``.
    """

    origin: Vector
    rot: Matrix

    @property
    def z(self) -> Vector:
        return self.rot[:, 2]

    @property
    def x(self) -> Vector:
        return self.rot[:, 0]

    def pose(self) -> Pose:
        return Pose(t=self.origin, q=matrix_to_quat(self.rot))


def build_frame(
    origin: Vector, z: Vector, *, flip: bool = False, quarter_turns: int = 0
) -> LocalFrame:
    """A frame at ``origin`` with Z ``z``, X from :func:`reference_x`, reoriented.

    ``flip`` is a half turn about the frame's X axis: Z and Y reverse and X is
    kept, so a flip changes only which way the frame faces (Onshape's "flip
    primary axis"). ``quarter_turns`` then turns X about the (flipped) Z by 90°
    steps, right-handed (Onshape's "reorient secondary axis"). Y = Z x X keeps
    the frame right-handed throughout.
    """
    z_unit = _unit(np.asarray(z, dtype=np.float64))
    x_unit = reference_x(z_unit)
    if flip:
        z_unit = -z_unit
    turns = quarter_turns % 4
    for _ in range(turns):
        x_unit = np.cross(z_unit, x_unit)  # +90° about z (x ⊥ z, both unit)
    y_unit = np.cross(z_unit, x_unit)
    return LocalFrame(
        origin=np.asarray(origin, dtype=np.float64),
        rot=np.column_stack([x_unit, y_unit, z_unit]),
    )


def _rotation_error(actual: Matrix, target: Matrix) -> Vector:
    """Rotation vector of ``actual · targetᵀ`` (zero iff the two coincide)."""
    return rotvec_from_quat(matrix_to_quat(actual @ target.T))


@dataclass(frozen=True)
class CompiledJoint:
    """A solved-motion joint in solver form (see the module docstring).

    ``rot_value`` (radians) and ``lin_value`` (mm) are the DRIVEN values, ``None``
    when the joint's value leaves that axis free.
    """

    motion: str
    frame_a: LocalFrame
    frame_b: LocalFrame
    offset_mm: float
    angle_rad: float
    rot_value: float | None
    lin_value: float | None

    @property
    def drive_rows(self) -> int:
        if self.motion == "revolute" and self.rot_value is not None:
            return 1
        if self.motion == "slider" and self.lin_value is not None:
            return 1
        return 0

    @property
    def rows(self) -> int:
        return HARD_ROWS + self.drive_rows

    def _world(
        self, pose_a: Pose, pose_b: Pose
    ) -> tuple[Vector, Matrix, Vector, Matrix]:
        pa = pose_a.apply_point(self.frame_a.origin)
        ra = pose_a.matrix() @ self.frame_a.rot
        pb = pose_b.apply_point(self.frame_b.origin)
        rb = pose_b.matrix() @ self.frame_b.rot
        return pa, ra, pb, rb

    def _aligned(self, ra: Matrix) -> Matrix:
        """B's world orientation at zero free rotation: A turned by angle,
        Z opposed (half turn about X)."""
        return ra @ rot_z(self.angle_rad) @ _HALF_TURN_X

    def residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
        """Hard rows, then the driving row when the value is set."""
        pa, ra, pb, rb = self._world(pose_a, pose_b)
        za = ra[:, 2]
        if self.motion == "slider":
            w = pb - pa
            along = float(np.dot(w, za))
            rows = [w - along * za, _rotation_error(rb, self._aligned(ra))]
            if self.lin_value is not None:
                drive = along - self.offset_mm - self.lin_value
                rows.append(np.array([drive], dtype=np.float64))
            return np.concatenate(rows)
        position = pb - (pa + self.offset_mm * za)
        if self.motion == "rigid":
            return np.concatenate([position, _rotation_error(rb, self._aligned(ra))])
        # revolute: shared axis (Z opposed), rotation about it free or driven
        rows = [position, rb[:, 2] + za]
        if self.rot_value is not None:
            phi = self._phi(ra, rb)
            drive = wrap_pi(phi - self.angle_rad - self.rot_value)
            rows.append(np.array([drive], dtype=np.float64))
        return np.concatenate(rows)

    @staticmethod
    def _phi(ra: Matrix, rb: Matrix) -> float:
        """Angle of B's X about A's Z, from A's X (radians, atan2)."""
        xb = rb[:, 0]
        return math.atan2(float(np.dot(xb, ra[:, 1])), float(np.dot(xb, ra[:, 0])))

    def measure(self, pose_a: Pose, pose_b: Pose) -> tuple[float, float]:
        """``(rot radians in (-π, π], lin mm)`` of the pair at these poses."""
        pa, ra, pb, rb = self._world(pose_a, pose_b)
        rot = wrap_pi(self._phi(ra, rb) - self.angle_rad)
        lin = float(np.dot(pb - pa, ra[:, 2])) - self.offset_mm
        return rot, lin

    def relative_pose(self, rot: float, lin: float) -> Pose:
        """Body B in body A's frame at joint position ``(rot, lin)``:
        ``F_A ∘ T(rot, lin) ∘ F_B⁻¹``."""
        t_rot = rot_z(self.angle_rad + rot) @ _HALF_TURN_X
        joint = Pose(
            t=np.array([0.0, 0.0, self.offset_mm + lin], dtype=np.float64),
            q=matrix_to_quat(t_rot),
        )
        return self.frame_a.pose().compose(joint).compose(self.frame_b.pose().inverse())

    def snap_child(self, parent_pose: Pose, child_is_b: bool, seed_child: Pose) -> Pose:
        """The child's pose that satisfies this joint, given the placed parent.

        Driven axes take the value; a FREE axis keeps the child's seed position
        along it (measured against the placed parent), so an undriven joint
        settles at the seed deterministically. Rigid has no free axis.
        """
        if child_is_b:
            seed_rot, seed_lin = self.measure(parent_pose, seed_child)
        else:
            seed_rot, seed_lin = self.measure(seed_child, parent_pose)
        rot = 0.0
        lin = 0.0
        if self.motion == "revolute":
            rot = self.rot_value if self.rot_value is not None else seed_rot
        elif self.motion == "slider":
            lin = self.lin_value if self.lin_value is not None else seed_lin
        rel = self.relative_pose(rot, lin)
        child = parent_pose.compose(rel if child_is_b else rel.inverse())
        # q and -q are one rotation; report the w >= 0 one (a stable placement).
        if float(child.q[3]) < 0.0:
            child = Pose(t=child.t, q=-child.q)
        return child

    def state(self, mate_id: uuid.UUID, pose_a: Pose, pose_b: Pose) -> JointState:
        """The reported :class:`JointState` at the solved poses.

        ``at_limit`` is always False in S4a (limits are S4b).
        """
        rot, lin = self.measure(pose_a, pose_b)
        axis = pose_a.matrix() @ self.frame_a.z
        return JointState(
            mate_id=mate_id,
            rot_deg=wrap_deg(math.degrees(rot)) if self.motion == "revolute" else None,
            lin_mm=lin if self.motion == "slider" else None,
            at_limit=False,
            axis_world=as_vec3(axis),
        )


def compile_joint(
    joint: JointMate, frame_a: LocalFrame, frame_b: LocalFrame
) -> CompiledJoint:
    """A :class:`CompiledJoint` from the wire joint and its two resolved frames."""
    rot_deg = joint.value.rot_deg if joint.motion == "revolute" else None
    lin_mm = joint.value.lin_mm if joint.motion == "slider" else None
    return CompiledJoint(
        motion=joint.motion,
        frame_a=frame_a,
        frame_b=frame_b,
        offset_mm=joint.offset_mm,
        angle_rad=math.radians(joint.angle_deg),
        rot_value=math.radians(rot_deg) if rot_deg is not None else None,
        lin_value=lin_mm,
    )
