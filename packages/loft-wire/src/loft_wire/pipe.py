"""Pipe and Plane Along Path: a tube along picked curves (PIPE-ALONG-PATH).

Fusion 360's *Pipe* and *Plane Along Path*, the two commands a tube frame is
built from: one skeleton sketch holds every tube's centre line, each tube is a
Pipe on some of those lines, and a plane normal to a line at a point carries
any sketch that has to sit across a tube.

**The path is a picked chain of curves**, each a sketch curve of an EARLIER
sketch (line, arc, circle, spline; construction curves included, the natural
skeleton) or an edge of an earlier body. One sketch can feed any number of
Pipes, and one Pipe may take curves from several sketches and edges at once.
The geometry service orders the picks into one chain on every rebuild: an
open or closed chain is swept, a pick that branches (three curves at one
point) or falls apart (two chains) is the typed rebuild error
``sweep_path_not_connected``.

**The section is a circle of ``outer_diameter_mm``** centred on the chain's
start and normal to it there, or a ring when ``wall_thickness_mm`` is set
(Fusion's *Hollow*). The chain starts at the free end of the first picked
curve's own start side (for a closed chain, at the first curve's start).
Sharp corners are MITRED, as Fusion's Pipe builds them; a bend tighter than
the outer radius is refused, never swept through itself.

Every field is additive: :class:`PipeParamsV1` is a new feature type and
:class:`DatumAlongPathParams` joins ``DatumParams`` by its own ``kind``, so no
stored feature changes shape or bytes. Pure pydantic, no kernel types.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from loft_wire.refs import FeatureRef
from loft_wire.signatures import EdgeSubshapeRef
from loft_wire.sketch import EntityId

#: Ceiling on the curves of one pipe path (a work bound like
#: ``MAX_SELECTOR_REFS``: each is one resolve plus one edge of the spine).
MAX_PIPE_PATH_SEGMENTS = 500


class PathSketchCurve(BaseModel):
    """``kind: "sketch_curve"``: one curve entity of an EARLIER sketch.

    ``sketch`` materialises into ``feature_dependencies`` like an extrude's
    profile; ``entity`` is the sketch-local id of a line, arc, circle or spline
    (a construction curve counts: it is what a skeleton is drawn in). The curve
    is read from the SOLVED sketch on every rebuild, so re-dimensioning the
    skeleton moves every pipe on it.
    """

    kind: Literal["sketch_curve"]
    sketch: FeatureRef = Field(description="The EARLIER sketch that owns the curve.")
    entity: EntityId = Field(
        description="Sketch-local id of a line, arc, circle or spline in it."
    )


#: One picked curve of a path: a sketch curve, or a model edge (the stage-1
#: :class:`EdgeSubshapeRef` a fillet pick echoes). Discriminated on ``kind``.
PathSegment = Annotated[PathSketchCurve | EdgeSubshapeRef, Field(discriminator="kind")]


class PipeParamsV1(BaseModel):
    """A circular or ring section swept along a picked chain of curves.

    See the module docstring. ``operation`` and ``merge`` are the other
    sketch solids' fields: ``add`` with ``merge`` joins the tube to the active
    body (Fusion's *Join*), ``add`` without it starts a new body (*New Body*),
    and ``cut`` removes it from the active body (*Cut*). Failures are typed
    rebuild errors on the pipe: ``reference_unresolved`` (a missing sketch or
    curve), ``subshape_unresolved`` / ``subshape_ambiguous`` (an edge),
    ``sweep_path_not_connected`` (branched or disjoint picks, or a curve
    picked twice), ``sweep_failed`` (a bend tighter than the section),
    ``sweep_self_intersecting`` (the path comes back through the tube).
    """

    path: list[PathSegment] = Field(
        min_length=1,
        max_length=MAX_PIPE_PATH_SEGMENTS,
        description="The picked curves, in pick order (>= 1): sketch curves of "
        "earlier sketches and/or edges of an earlier body. They must form one "
        "connected chain, open or closed, with no branch.",
    )
    outer_diameter_mm: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Outside diameter of the tube section (mm).",
    )
    wall_thickness_mm: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Wall thickness (mm) of a HOLLOW pipe: the section is a "
        "ring from the outside diameter inwards. Null for a solid round bar. "
        "Must be less than the outer radius.",
    )
    operation: Literal["add", "cut"]
    merge: bool = Field(
        default=True,
        description="ADD only: True joins the tube to the active body (or "
        "starts the first body); False starts a NEW body. Ignored for a cut.",
    )

    @model_validator(mode="after")
    def _wall_inside_radius(self) -> Self:
        wall = self.wall_thickness_mm
        if wall is not None and wall >= self.outer_diameter_mm / 2:
            raise ValueError(
                f"A wall of {wall} mm leaves no bore in a tube of outside "
                f"diameter {self.outer_diameter_mm} mm; it must be less than "
                "the outer radius."
            )
        return self


class DatumAlongPathParams(BaseModel):
    """A plane normal to a curve at a point along it (``kind: "along_path"``).

    Fusion 360's *Plane Along Path* (SolidWorks' Plane "normal to curve"):
    the plane passes through the point of ``path`` at ``ratio`` of its length
    (``measure: "ratio"``) or ``distance_mm`` along it (``"distance"``),
    measured from the curve's start (a sketch curve's own start; for an edge,
    ``end_a`` of the signature AS PICKED, kept on rebuild), and its normal is
    the curve's tangent there, in the direction of travel. ``x_dir`` is pinned
    from the normal (the on-face rule) and ``flip`` negates the normal,
    keeping ``x_dir``, as for every datum kind. A distance past the curve's
    end is the typed rebuild error ``datum_path_out_of_range``.
    """

    kind: Literal["along_path"]
    path: PathSegment = Field(
        description="The curve the plane is normal to: a sketch curve of an "
        "earlier sketch, or a model edge."
    )
    measure: Literal["ratio", "distance"] = Field(
        default="ratio",
        description="`ratio`: place the plane at `ratio` of the curve's "
        "length; `distance`: at `distance_mm` along it from its start.",
    )
    ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Fraction of the curve's length from its start (0..1); "
        "used when `measure` is `ratio`.",
    )
    distance_mm: float = Field(
        default=0.0,
        ge=0.0,
        allow_inf_nan=False,
        description="Distance along the curve from its start (mm); used when "
        "`measure` is `distance`.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir) — "
        "the same rule as `offset`.",
    )
