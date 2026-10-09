"""The plane-at-an-angle datum (``kind: "angle"``, DATUM-PLANE-ANGLE).

Fusion 360's *Plane at Angle*, SolidWorks' Plane "At angle" and Onshape's
Plane "Line angle": a plane THROUGH a line, turned about that line by a typed
angle from a reference plane. The line is a sketch line, a straight model edge
or an origin axis; the reference is an origin datum, an earlier datum or a
picked planar face (the same three forms a midplane side takes). The geometry
service resolves both on every rebuild, so the plane follows an edited sketch
line, a moved edge and a moved reference alike.

Conventions (docs/RESEARCH.md §18, implemented by
``geometry.kernel.datum_angle.plane_at_angle``):

* the line must be PARALLEL to the reference plane (it may lie in it or off
  it); a line that crosses the reference at an angle has no well-defined
  "angle from it", so that is the typed rebuild error
  ``datum_line_not_parallel``, never a guessed plane;
* ``angle_deg = 0`` is the plane through the line parallel to the reference;
  a positive angle turns the reference normal RIGHT-HANDED about the line's
  direction (start to end for a sketch line, ``end_a`` to ``end_b`` of the
  edge AS PICKED for an edge, kept on rebuild, +X/+Y/+Z for an origin axis);
* the plane's ``x_dir`` is the line direction, its origin the point of the
  line nearest the world origin, ``z_dir`` the turned normal (``flip``
  negates it, keeping ``x_dir``, the rule every datum kind shares).

Every field is additive: the variant joins :data:`loft_wire.features.DatumParams`
by its own ``kind``, so no stored datum changes shape or bytes.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from loft_wire.refs import FeatureRef, MidplaneSide
from loft_wire.signatures import EdgeSubshapeRef
from loft_wire.sketch import EntityId

#: The largest angle magnitude a plane at an angle accepts (degrees). One full
#: turn either way; anything past it names a plane a smaller angle already does.
MAX_DATUM_ANGLE_DEG = 360.0


class DatumSketchLineRef(BaseModel):
    """``kind: "sketch_line"`` — a LINE entity of an EARLIER sketch feature.

    ``sketch`` is a whole-feature :class:`FeatureRef` (it materialises into
    ``feature_dependencies`` like an extrude's profile); ``entity`` is the
    sketch-local id of a line in it, a construction line being the natural
    choice. The line is read from the SOLVED sketch at rebuild, so dragging or
    re-dimensioning it moves the plane. A missing sketch or entity, or an
    entity that is not a line, is a typed rebuild error on the datum.
    """

    kind: Literal["sketch_line"]
    sketch: FeatureRef = Field(
        description="The EARLIER sketch feature that owns the line."
    )
    entity: EntityId = Field(
        description="Sketch-local id of a LINE entity of that sketch (a "
        "construction line is ideal)."
    )


class DatumOriginAxisRef(BaseModel):
    """``kind: "origin_axis"`` — one of the world axes through the origin."""

    kind: Literal["origin_axis"]
    axis: Literal["X", "Y", "Z"] = Field(
        description="World origin axis the plane passes through and turns about."
    )


#: The line a plane at an angle passes through and turns about: a sketch line,
#: a straight model edge (the stage-1 :class:`EdgeSubshapeRef` a fillet pick
#: echoes, resolved through the same strict/named/durable tiers) or an origin
#: axis. Discriminated on ``kind``.
DatumAngleLine = Annotated[
    DatumSketchLineRef | DatumOriginAxisRef | EdgeSubshapeRef,
    Field(discriminator="kind"),
]


class DatumAngleParams(BaseModel):
    """A plane through a line, turned about it from a reference (``kind: "angle"``).

    See the module docstring for the conventions. Failures are all typed and
    leave the datum sick rather than crash the rebuild: a missing sketch or
    entity is ``reference_unresolved``, a curved entity or edge (or a line of
    zero length) is ``datum_line_invalid``, an edge or face that no longer
    resolves is ``subshape_unresolved`` / ``subshape_ambiguous``, and a line
    that is not parallel to the reference is ``datum_line_not_parallel``.
    """

    kind: Literal["angle"]
    line: DatumAngleLine = Field(
        description="The line the plane passes through and turns about: a "
        "sketch line, a straight model edge, or an origin axis."
    )
    reference: MidplaneSide = Field(
        description="The plane the angle is measured from: an origin datum, an "
        "earlier `datum` feature, or a picked planar face. The line must be "
        "parallel to it."
    )
    angle_deg: float = Field(
        allow_inf_nan=False,
        ge=-MAX_DATUM_ANGLE_DEG,
        le=MAX_DATUM_ANGLE_DEG,
        description="Angle from the reference plane (degrees). 0 is parallel "
        "to the reference; positive turns the reference normal right-handed "
        "about the line direction.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir so "
        "sketch +u is unchanged and +v flips) — the same rule as `offset`.",
    )
