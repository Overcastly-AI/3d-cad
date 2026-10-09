"""Assembly JOINTS: the Onshape/Fusion mate-connector style of mating.

A joint is one more member of the :data:`~loft_wire.assemblies.Mate` union
(``type="joint"``), stored in the same ``mates`` table as the five legacy
mates, which keep their exact shapes. Where a legacy mate states a geometric
relation (two faces coplanar), a joint pairs two FRAMES, one on each
instance, and names the motion left between them, the way a working engineer
thinks about a hinge or a slide:

- each side is a :class:`JointOrigin`: a point on picked geometry (the centre
  of a planar face, the centre of a circular edge, or the start, middle or end
  of an edge), named with the SAME stage-1 signatures the legacy mates reuse,
  plus ``flip`` / ``quarter_turns`` to reorient the frame about it;
- ``motion`` is the joint kind: rigid, revolute, slider, cylindrical, planar or
  ball;
- ``value`` is the joint's current position along its free axes. The persisted
  truth of a joint is this VALUE (Onshape style); a new joint snaps B onto A,
  and the solver (later) places B from A's frame plus the value.

Units are fixed per field (``*_mm`` millimetres, ``*_deg`` degrees), as in the
rest of the wire. Pure pydantic: no kernel types (CLAUDE.md boundaries).
"""

import uuid
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from loft_wire.geometry import Vec3
from loft_wire.signatures import EdgeSignature, PlanarFaceSignature

#: Where on the picked geometry a joint origin sits.
JointOriginKind = Literal["face_centre", "circle_centre", "edge_point"]

#: Which point of an edge an ``edge_point`` origin sits on.
JointEdgePoint = Literal["start", "mid", "end"]

#: The motion a joint leaves free between its two frames.
JointMotion = Literal["rigid", "revolute", "slider", "cylindrical", "planar", "ball"]

#: Motions with ONE rotational value about the joint Z axis. A ball has three
#: rotations and no single scalar, so it carries no rotation value or limit.
ROTATING_MOTIONS: frozenset[str] = frozenset({"revolute", "cylindrical", "planar"})

#: Motions with ONE translational value along the joint Z axis. A planar joint
#: translates in two in-plane directions, so a single scalar cannot name its
#: translation; it carries none.
SLIDING_MOTIONS: frozenset[str] = frozenset({"slider", "cylindrical"})

#: Display names, used for the joint's ordinal label ("Revolute 1").
MOTION_LABELS: dict[str, str] = {
    "rigid": "Rigid",
    "revolute": "Revolute",
    "slider": "Slider",
    "cylindrical": "Cylindrical",
    "planar": "Planar",
    "ball": "Ball",
}

#: Bound on any joint angle (degrees): ten full turns either way. Generous for a
#: multi-turn revolute, finite so no value can overflow the solver.
MAX_JOINT_ANGLE_DEG = 3600.0

#: Bound on any joint length (mm): 100 m either way.
MAX_JOINT_LENGTH_MM = 100_000.0

_Angle = Annotated[
    float,
    Field(allow_inf_nan=False, ge=-MAX_JOINT_ANGLE_DEG, le=MAX_JOINT_ANGLE_DEG),
]
_Length = Annotated[
    float,
    Field(allow_inf_nan=False, ge=-MAX_JOINT_LENGTH_MM, le=MAX_JOINT_LENGTH_MM),
]

#: A face or an edge signature. Not a tagged union: ``subshape_type`` defaults
#: on both and stored payloads omit it, while the two shapes share no required
#: field, so pydantic's smart union picks the one that fits.
JointSignature = PlanarFaceSignature | EdgeSignature


class JointOrigin(BaseModel):
    """One side of a joint: a frame on an instance's part body.

    The origin is a point on picked geometry; the frame's Z axis is the face
    normal (``face_centre``), the circle's axis (``circle_centre``) or the edge
    direction (``edge_point``). ``flip`` reverses Z, and ``quarter_turns``
    rotates the frame about Z in 90 degree steps (Onshape's "reorient").
    """

    instance_id: uuid.UUID = Field(
        description="The instance whose part body carries this origin"
    )
    kind: JointOriginKind = Field(
        description="`face_centre` (a planar face, `signature` is a face "
        "signature), `circle_centre` (a circular edge) or `edge_point` (any "
        "edge, at `at`)"
    )
    signature: JointSignature = Field(
        description="Stage-1 signature of the picked face or edge (reused "
        "from features)"
    )
    at: JointEdgePoint | None = Field(
        default=None,
        description="Which point of the edge, for `edge_point` only (required "
        "there, rejected on the other kinds)",
    )
    flip: bool = Field(default=False, description="Reverse the frame's Z axis")
    quarter_turns: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Rotate the frame about its Z axis by 90 degree steps (0-3)",
    )

    @model_validator(mode="after")
    def _kind_matches_signature(self) -> Self:
        if self.kind == "face_centre":
            if not isinstance(self.signature, PlanarFaceSignature):
                raise ValueError("a face_centre origin needs a planar-face signature")
        elif not isinstance(self.signature, EdgeSignature):
            raise ValueError(f"a {self.kind} origin needs an edge signature")
        elif self.kind == "circle_centre" and self.signature.curve != "circle":
            raise ValueError("a circle_centre origin needs a circular edge")
        if self.kind == "edge_point" and self.at is None:
            raise ValueError("an edge_point origin needs `at` (start, mid or end)")
        if self.kind != "edge_point" and self.at is not None:
            raise ValueError("`at` applies to an edge_point origin only")
        return self


class JointLimits(BaseModel):
    """Optional travel limits. Each bound is optional; a min may not exceed
    its max. Which bounds apply depends on the motion (see :class:`JointMate`).
    """

    rot_min_deg: _Angle | None = Field(default=None, description="Lowest angle")
    rot_max_deg: _Angle | None = Field(default=None, description="Highest angle")
    lin_min_mm: _Length | None = Field(default=None, description="Lowest offset")
    lin_max_mm: _Length | None = Field(default=None, description="Highest offset")

    @model_validator(mode="after")
    def _min_not_above_max(self) -> Self:
        if (
            self.rot_min_deg is not None
            and self.rot_max_deg is not None
            and self.rot_min_deg > self.rot_max_deg
        ):
            raise ValueError("rot_min_deg exceeds rot_max_deg")
        if (
            self.lin_min_mm is not None
            and self.lin_max_mm is not None
            and self.lin_min_mm > self.lin_max_mm
        ):
            raise ValueError("lin_min_mm exceeds lin_max_mm")
        return self

    def has_rotation(self) -> bool:
        return self.rot_min_deg is not None or self.rot_max_deg is not None

    def has_translation(self) -> bool:
        return self.lin_min_mm is not None or self.lin_max_mm is not None


class JointValue(BaseModel):
    """A joint's current position along its free axes (the persisted truth)."""

    rot_deg: _Angle | None = Field(
        default=None, description="Rotation about the joint Z axis (degrees)"
    )
    lin_mm: _Length | None = Field(
        default=None, description="Translation along the joint Z axis (mm)"
    )


def _check_applies(motion: str, limits: JointLimits | None, value: JointValue) -> None:
    """Reject a limit or value on an axis the motion does not free."""
    rotates = motion in ROTATING_MOTIONS
    slides = motion in SLIDING_MOTIONS
    if limits is not None:
        if limits.has_rotation() and not rotates:
            raise ValueError(f"a {motion} joint takes no rotation limits")
        if limits.has_translation() and not slides:
            raise ValueError(f"a {motion} joint takes no linear limits")
    if value.rot_deg is not None and not rotates:
        raise ValueError(f"a {motion} joint has no rotation value")
    if value.lin_mm is not None and not slides:
        raise ValueError(f"a {motion} joint has no linear value")


class JointMate(BaseModel):
    """A joint between two instance frames (``type="joint"``).

    ``offset_mm`` / ``angle_deg`` are the fixed relation between the two frames
    (B's frame sits ``offset_mm`` along A's Z and turned ``angle_deg`` about
    it) at a zero ``value``. Limits and value fields must suit the motion:
    rotation for revolute / cylindrical / planar, translation for slider /
    cylindrical; rigid and ball take neither. A value outside its limits is
    refused by the documents service (``joint_value_out_of_limits``), not here,
    so a stored row always parses.
    """

    type: Literal["joint"] = "joint"
    motion: JointMotion = Field(description="The motion left free between A and B")
    a: JointOrigin = Field(description="Frame on the first (anchor) instance")
    b: JointOrigin = Field(description="Frame on the second (moving) instance")
    offset_mm: _Length = Field(
        default=0.0, description="Fixed offset of B's frame along A's Z axis (mm)"
    )
    angle_deg: _Angle = Field(
        default=0.0, description="Fixed turn of B's frame about A's Z axis (deg)"
    )
    limits: JointLimits | None = Field(
        default=None, description="Optional travel limits; null = unlimited"
    )
    value: JointValue = Field(
        default_factory=JointValue,
        description="Current position along the free axes (the persisted truth)",
    )

    @model_validator(mode="after")
    def _limits_and_value_apply(self) -> Self:
        _check_applies(self.motion, self.limits, self.value)
        return self


def joint_limit_violation(joint: JointMate, label: str) -> str | None:
    """A message naming the limit the joint's value breaks, or None.

    ``label`` is the joint's display name ("Revolute 1"); the message reads
    "Revolute 1: 200° exceeds max 180°".
    """
    limits = joint.limits
    if limits is None:
        return None
    checks: list[tuple[float | None, float | None, float | None, str]] = [
        (joint.value.rot_deg, limits.rot_min_deg, limits.rot_max_deg, "°"),
        (joint.value.lin_mm, limits.lin_min_mm, limits.lin_max_mm, " mm"),
    ]
    for value, low, high, unit in checks:
        if value is None:
            continue
        if high is not None and value > high:
            return f"{label}: {value:g}{unit} exceeds max {high:g}{unit}"
        if low is not None and value < low:
            return f"{label}: {value:g}{unit} is below min {low:g}{unit}"
    return None


class MateUpdate(BaseModel):
    """Edit a joint in place: its value, limits, B-side orientation or offsets.

    Every field but ``expected_version`` is optional and at least one must be
    given. ``limits`` distinguishes absent (unchanged) from an explicit null
    (remove the limits). ``flip`` / ``quarter_turns`` set origin B's, the
    Onshape "flip primary axis" / "reorient" on an existing joint. Bumps
    ``doc_version`` and records one undo step. Legacy mates are not editable
    here (delete and recreate).
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    value: JointValue | None = Field(default=None, description="New joint value")
    limits: JointLimits | None = Field(
        default=None,
        description="New limits; an explicit null removes them, absent keeps them",
    )
    offset_mm: _Length | None = Field(default=None, description="New fixed offset")
    angle_deg: _Angle | None = Field(default=None, description="New fixed angle")
    flip: bool | None = Field(default=None, description="New flip of origin B")
    quarter_turns: int | None = Field(
        default=None, ge=0, le=3, description="New quarter turns of origin B"
    )

    def apply_to(self, joint: JointMate) -> JointMate:
        """The joint with this update applied, re-validated as a whole."""
        data: dict[str, Any] = joint.model_dump(mode="json")
        if self.value is not None:
            data["value"] = self.value.model_dump(mode="json")
        if "limits" in self.model_fields_set:
            data["limits"] = (
                None if self.limits is None else self.limits.model_dump(mode="json")
            )
        if self.offset_mm is not None:
            data["offset_mm"] = self.offset_mm
        if self.angle_deg is not None:
            data["angle_deg"] = self.angle_deg
        if self.flip is not None:
            data["b"]["flip"] = self.flip
        if self.quarter_turns is not None:
            data["b"]["quarter_turns"] = self.quarter_turns
        return JointMate.model_validate(data)

    def is_empty(self) -> bool:
        return self.model_fields_set <= {"expected_version"}


class JointState(BaseModel):
    """A solved joint's position, reported with an assembly evaluation."""

    mate_id: uuid.UUID
    rot_deg: float | None = Field(
        default=None, description="Solved rotation; null when the motion has none"
    )
    lin_mm: float | None = Field(
        default=None, description="Solved translation; null when the motion has none"
    )
    at_limit: bool = Field(
        default=False, description="True when the joint sits on one of its limits"
    )
    axis_world: Vec3 = Field(description="The joint Z axis in world coordinates")
