"""Joint frames, residuals, limits and measurement for the assembly solver.

A joint (:class:`loft_wire.joints.JointMate`) pairs two FRAMES, one on each
instance, and names the motion left free between them (Fusion 360 joints,
Onshape mate connectors). This module is the numeric half: pure numpy, no
kernel type. :mod:`geometry.assembly.joint_origins` resolves each
:class:`~loft_wire.joints.JointOrigin` against the part body into a
:class:`LocalFrame` in that instance's LOCAL part frame; this module turns the
two frames plus the motion into solver rows. Conventions (RESEARCH §21, §22):

- **Alignment.** A joint brings the two frames together the way Fusion and
  Onshape do: origins coincident, Z axes OPPOSED and X axes aligned, so two
  outward face normals meet face to face (the legacy ``coincident`` mate's
  ``flush``). Formally ``F_B = F_A ∘ T`` with
  ``T = Trans(u, v, offset + lin) ∘ RotZ(angle + rot) ∘ RotX(π)``; a ball
  joint's rotation is free instead.
- **Free axes.** Rigid frees nothing; revolute ``rot`` about A's Z; slider
  ``lin`` along it; cylindrical both; planar ``rot`` plus the in-plane
  ``(u, v)``; ball the whole rotation about the shared point. ``offset_mm`` /
  ``angle_deg`` are the fixed shift and turn of the relation (a planar joint's
  offset is the distance between its two planes).
- **Rows.** HARD rows per motion (rank 6 rigid, 5 revolute and slider, 4
  cylindrical, 3 planar, 3 ball), then one DRIVING row per set value (rot
  before lin). Remaining DOF counts the hard rows only, so a driven hinge is
  fully PLACED yet still reports its 1 DOF, as Fusion does. A limit the solve
  would cross is PINNED at its bound as one more driving row.
- **Measurement.** ``rot`` is the signed angle from A's X axis (turned by
  ``angle_deg``) to B's X axis about A's Z, wrapped to (-180°, 180°]; ``lin`` is
  ``(p_B - p_A)·z_A - offset_mm``.

Determinism (RESEARCH §9): fixed sequences of float64 numpy ops.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace

import numpy as np
from loft_wire.joints import ROTATING_MOTIONS, SLIDING_MOTIONS, JointMate, JointState
from numpy.typing import NDArray

from geometry.assembly.transform import (
    Pose,
    as_vec3,
    matrix_to_quat,
    rotvec_from_quat,
)

Vector = NDArray[np.float64]
Matrix = NDArray[np.float64]

#: Hard rows per motion. Their RANK is 6 minus the motion's DOF (module docs):
#: the rows are written in world coordinates, so a 3-row axis alignment has
#: rank 2.
HARD_ROWS: dict[str, int] = {
    "rigid": 6,
    "revolute": 6,
    "slider": 6,
    "cylindrical": 6,
    "planar": 4,
    "ball": 3,
}

#: A joint position within this of a limit (radians for a rotation, mm for a
#: translation) is ON the limit (``at_limit``); one beyond it by more is pinned
#: to the bound and re-solved. Below the solve's ``SATISFIED_TOL`` (1e-7), so a
#: value the solve left on the bound is never pinned twice; far above the
#: float64 noise of a measured angle.
LIMIT_TOL = 1e-9

#: Two reference-axis alignments within this of each other count as a TIE in
#: :func:`reference_x`, so OCCT round-off on an axis-aligned direction (a normal
#: of ``(1e-17, 0, 1)``) cannot swap the chosen reference from X to Y and turn
#: the frame 90°. Far above float64 noise, far below any real tilt.
REFERENCE_TIE_TOL = 1e-9

_HALF_TURN_X = np.diag(np.array([1.0, -1.0, -1.0], dtype=np.float64))

#: A ``(min, max)`` pair, either side optional (radians or mm).
Bounds = tuple[float | None, float | None]

_NO_BOUNDS: Bounds = (None, None)


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


def rotation_branch_centre(bounds: Bounds) -> float:
    """Centre ``c`` of the branch ``(c - π, c + π]`` a rotation is read on
    against ``bounds`` (the SEAM RULE, RESEARCH §22).

    Two bounds: their midpoint, so the excluded arc splits at the point
    opposite the allowed one and an angle past either bound is read on the
    side of the NEARER bound (the exact opposite point, on the half-open
    branch's closed end, reads as past the max). One bound: the point of the
    allowed side nearest the joint's zero, so a lone ``max 90°`` reads on the
    principal branch (-π, π] and a lone ``min 200°`` on the branch around 200°.
    """
    low, high = bounds
    if low is not None and high is not None:
        return 0.5 * (low + high)
    if low is not None and low > 0.0:
        return low
    if high is not None and high < 0.0:
        return high
    return 0.0


def read_rotation(rot: float, bounds: Bounds) -> float:
    """``rot`` (radians, any branch) read on the seam-rule branch of
    ``bounds`` (see :func:`rotation_branch_centre`)."""
    centre = rotation_branch_centre(bounds)
    return centre + wrap_pi(rot - centre)


def _past(reading: float, bounds: Bounds) -> float | None:
    """The bound ``reading`` lies beyond by more than :data:`LIMIT_TOL`."""
    low, high = bounds
    if high is not None and reading > high + LIMIT_TOL:
        return high
    if low is not None and reading < low - LIMIT_TOL:
        return low
    return None


def _on(reading: float, bounds: Bounds) -> bool:
    return any(b is not None and abs(reading - b) <= LIMIT_TOL for b in bounds)


@dataclass(frozen=True)
class CompiledJoint:
    """A joint in solver form (see the module docstring).

    ``rot_value`` (radians) and ``lin_value`` (mm) are the DRIVEN values, ``None``
    when that axis is free; a limit the active set pins becomes a driven value
    at the bound. ``rot_bounds`` / ``lin_bounds`` are the limits (radians, mm).
    ``rot_held`` / ``lin_held`` mark a value that sits on a limit by
    construction: driven at a bound, or pinned there.
    """

    motion: str
    frame_a: LocalFrame
    frame_b: LocalFrame
    offset_mm: float
    angle_rad: float
    rot_value: float | None
    lin_value: float | None
    rot_bounds: Bounds = _NO_BOUNDS
    lin_bounds: Bounds = _NO_BOUNDS
    rot_held: bool = False
    lin_held: bool = False

    @property
    def hard_rows(self) -> int:
        return HARD_ROWS[self.motion]

    @property
    def drive_rows(self) -> int:
        return (self.rot_value is not None) + (self.lin_value is not None)

    @property
    def rows(self) -> int:
        return self.hard_rows + self.drive_rows

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

    def hard_residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
        """The motion's hard rows (:data:`HARD_ROWS`); zero iff the frames sit
        as the motion allows."""
        pa, ra, pb, rb = self._world(pose_a, pose_b)
        za = ra[:, 2]
        if self.motion in ("slider", "cylindrical"):
            w = pb - pa
            along = float(np.dot(w, za))
            if self.motion == "slider":
                return np.concatenate(
                    [w - along * za, _rotation_error(rb, self._aligned(ra))]
                )
            # cylindrical: on A's axis line, Z opposed; turn and slide free
            return np.concatenate([w - along * za, rb[:, 2] + za])
        if self.motion == "planar":
            # Z opposed and B's origin on A's plane shifted by the offset;
            # in-plane slide and turn about the normal free.
            along = float(np.dot(pb - pa, za))
            return np.concatenate(
                [rb[:, 2] + za, np.array([along - self.offset_mm], dtype=np.float64)]
            )
        position = pb - (pa + self.offset_mm * za)
        if self.motion == "rigid":
            return np.concatenate([position, _rotation_error(rb, self._aligned(ra))])
        if self.motion == "ball":
            return position
        # revolute: shared axis (Z opposed), rotation about it free or driven
        return np.concatenate([position, rb[:, 2] + za])

    def drive_residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
        """One row per driven (or limit-pinned) value, rot before lin."""
        pa, ra, pb, rb = self._world(pose_a, pose_b)
        rows: list[float] = []
        if self.rot_value is not None:
            phi = self._phi(ra, rb)
            rows.append(wrap_pi(phi - self.angle_rad - self.rot_value))
        if self.lin_value is not None:
            along = float(np.dot(pb - pa, ra[:, 2]))
            rows.append(along - self.offset_mm - self.lin_value)
        return np.array(rows, dtype=np.float64)

    def residual(self, pose_a: Pose, pose_b: Pose) -> Vector:
        """Hard rows, then the driving rows."""
        hard = self.hard_residual(pose_a, pose_b)
        if self.drive_rows == 0:
            return hard
        return np.concatenate([hard, self.drive_residual(pose_a, pose_b)])

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

    def _in_plane(self, pose_a: Pose, pose_b: Pose) -> tuple[float, float]:
        """B's origin from A's along A's frame X and Y (a planar joint's slide)."""
        pa, ra, pb, _ = self._world(pose_a, pose_b)
        w = pb - pa
        return float(np.dot(w, ra[:, 0])), float(np.dot(w, ra[:, 1]))

    def relative_pose(
        self, rot: float, lin: float, u: float = 0.0, v: float = 0.0
    ) -> Pose:
        """Body B in body A's frame at joint position ``(rot, lin, u, v)``:
        ``F_A ∘ T ∘ F_B⁻¹``."""
        t_rot = rot_z(self.angle_rad + rot) @ _HALF_TURN_X
        joint = Pose(
            t=np.array([u, v, self.offset_mm + lin], dtype=np.float64),
            q=matrix_to_quat(t_rot),
        )
        return self.frame_a.pose().compose(joint).compose(self.frame_b.pose().inverse())

    def snap_child(self, parent_pose: Pose, child_is_b: bool, seed_child: Pose) -> Pose:
        """The child's pose that satisfies this joint, given the placed parent.

        Driven axes take the value; a FREE axis keeps the child's seed position
        along it (measured against the placed parent), so an undriven joint
        settles at the seed deterministically. Rigid has no free axis; a ball
        keeps the child's seed orientation.
        """
        if self.motion == "ball":
            child = self._snap_ball(parent_pose, child_is_b, seed_child)
        else:
            if child_is_b:
                pose_a, pose_b = parent_pose, seed_child
            else:
                pose_a, pose_b = seed_child, parent_pose
            seed_rot, seed_lin = self.measure(pose_a, pose_b)
            rot = 0.0
            lin = 0.0
            u = 0.0
            v = 0.0
            if self.motion in ROTATING_MOTIONS:
                rot = self.rot_value if self.rot_value is not None else seed_rot
            if self.motion in SLIDING_MOTIONS:
                lin = self.lin_value if self.lin_value is not None else seed_lin
            if self.motion == "planar":
                u, v = self._in_plane(pose_a, pose_b)
            rel = self.relative_pose(rot, lin, u, v)
            child = parent_pose.compose(rel if child_is_b else rel.inverse())
        # q and -q are one rotation; report the w >= 0 one (a stable placement).
        if float(child.q[3]) < 0.0:
            child = Pose(t=child.t, q=-child.q)
        return child

    def _snap_ball(self, parent_pose: Pose, child_is_b: bool, seed_child: Pose) -> Pose:
        """Keep the child's seed orientation; translate it so B's origin sits
        ``offset_mm`` along A's Z from A's origin."""
        rot = seed_child.matrix()
        if child_is_b:
            pa = parent_pose.apply_point(self.frame_a.origin)
            za = parent_pose.apply_direction(self.frame_a.z)
            t = pa + self.offset_mm * za - rot @ self.frame_b.origin
        else:
            pb = parent_pose.apply_point(self.frame_b.origin)
            za = rot @ self.frame_a.z
            t = pb - self.offset_mm * za - rot @ self.frame_a.origin
        return Pose(t=t, q=seed_child.q)

    def _rotates(self) -> bool:
        return self.motion in ROTATING_MOTIONS

    def _slides(self) -> bool:
        return self.motion in SLIDING_MOTIONS

    def pin_limits(self, pose_a: Pose, pose_b: Pose) -> CompiledJoint | None:
        """This joint with every FREE axis that sits past a limit pinned to
        that bound (rot before lin), or ``None`` when none does.

        A driven axis is never pinned: its value was clamped at compile time.
        A rotation is read on the seam-rule branch (:func:`read_rotation`).
        """
        rot, lin = self.measure(pose_a, pose_b)
        pin_rot: float | None = None
        pin_lin: float | None = None
        if self._free_rot():
            pin_rot = _past(read_rotation(rot, self.rot_bounds), self.rot_bounds)
        if self._free_lin():
            pin_lin = _past(lin, self.lin_bounds)
        if pin_rot is None and pin_lin is None:
            return None
        return replace(
            self,
            rot_value=self.rot_value if pin_rot is None else pin_rot,
            rot_held=self.rot_held or pin_rot is not None,
            lin_value=self.lin_value if pin_lin is None else pin_lin,
            lin_held=self.lin_held or pin_lin is not None,
        )

    def limited_axes(self) -> int:
        """How many free axes carry a limit (bounds the active-set passes)."""
        rot = self._free_rot() and self.rot_bounds != _NO_BOUNDS
        lin = self._free_lin() and self.lin_bounds != _NO_BOUNDS
        return int(rot) + int(lin)

    def _free_rot(self) -> bool:
        return self.motion in ROTATING_MOTIONS and self.rot_value is None

    def _free_lin(self) -> bool:
        return self.motion in SLIDING_MOTIONS and self.lin_value is None

    def _at_limit(self, rot: float, lin: float) -> bool:
        if self.rot_held or self.lin_held:
            return True
        if self._free_rot() and _on(
            read_rotation(rot, self.rot_bounds), self.rot_bounds
        ):
            return True
        return self._free_lin() and _on(lin, self.lin_bounds)

    def state(self, mate_id: uuid.UUID, pose_a: Pose, pose_b: Pose) -> JointState:
        """The reported :class:`JointState` at the solved poses.

        ``rot_deg`` reads on the principal branch (-180, 180] whatever the
        limits; ``at_limit`` is true when an axis is held on a limit (driven
        at a bound or pinned there) or a free axis sits within
        :data:`LIMIT_TOL` of one.
        """
        rot, lin = self.measure(pose_a, pose_b)
        axis = pose_a.matrix() @ self.frame_a.z
        return JointState(
            mate_id=mate_id,
            rot_deg=wrap_deg(math.degrees(rot)) if self._rotates() else None,
            lin_mm=lin if self._slides() else None,
            at_limit=self._at_limit(rot, lin),
            axis_world=as_vec3(axis),
        )


def _radians(degrees: float | None) -> float | None:
    return None if degrees is None else math.radians(degrees)


def _clamp(value: float, low: float | None, high: float | None) -> tuple[float, bool]:
    """``value`` clamped into ``[low, high]`` and whether it sits on a bound."""
    if high is not None and value >= high:
        return high, True
    if low is not None and value <= low:
        return low, True
    return value, False


def compile_joint(
    joint: JointMate, frame_a: LocalFrame, frame_b: LocalFrame
) -> CompiledJoint:
    """A :class:`CompiledJoint` from the wire joint and its two resolved frames.

    A driven value outside its limits never reaches here from documents (it
    refuses one, ``joint_value_out_of_limits``); a request that carries one
    anyway is clamped to the bound, so geometry never places a joint past a
    limit.
    """
    rotates = joint.motion in ROTATING_MOTIONS
    slides = joint.motion in SLIDING_MOTIONS
    limits = joint.limits
    rot_deg = joint.value.rot_deg if rotates else None
    lin_mm = joint.value.lin_mm if slides else None
    rot_bounds_deg: Bounds = _NO_BOUNDS
    lin_bounds: Bounds = _NO_BOUNDS
    if limits is not None and rotates:
        rot_bounds_deg = (limits.rot_min_deg, limits.rot_max_deg)
    if limits is not None and slides:
        lin_bounds = (limits.lin_min_mm, limits.lin_max_mm)
    rot_held = False
    lin_held = False
    if rot_deg is not None:
        rot_deg, rot_held = _clamp(rot_deg, *rot_bounds_deg)
    if lin_mm is not None:
        lin_mm, lin_held = _clamp(lin_mm, *lin_bounds)
    return CompiledJoint(
        motion=joint.motion,
        frame_a=frame_a,
        frame_b=frame_b,
        offset_mm=joint.offset_mm,
        angle_rad=math.radians(joint.angle_deg),
        rot_value=math.radians(rot_deg) if rot_deg is not None else None,
        lin_value=lin_mm,
        rot_bounds=(_radians(rot_bounds_deg[0]), _radians(rot_bounds_deg[1])),
        lin_bounds=lin_bounds,
        rot_held=rot_held,
        lin_held=lin_held,
    )
