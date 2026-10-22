"""3D sketch: points and lines in model space (SKETCH-3D, RESEARCH §28).

SolidWorks' *3D Sketch* and Fusion 360's 3D sketch, scoped to what a tube
frame skeleton needs: POINTS placed anywhere in model space, LINES between
them, and the relations that hold a skeleton together. A 3D sketch sits on no
plane; its coordinates are world millimetres.

* A **point** stores its last position. ``snap`` attaches it to geometry
  outside the sketch (SolidWorks' coincident-to-vertex relation): the origin,
  a point of an earlier sketch (2D or 3D), or an end of a model edge (a model
  vertex). A snapped point follows that geometry on every rebuild and is fixed
  for the solve.
* A **line** joins two of the sketch's points by id, so a chained skeleton
  shares its joints. ``construction`` lines solve but are only references.
* **Constraints** (SolidWorks' 3D sketch relations): ``coincident`` (two
  points), ``fixed`` (a point stays where it is stored), ``along`` (a line
  parallel to the world X, Y or Z axis: SolidWorks' Along X/Y/Z).
  **Dimensions**: ``length`` (a line) and ``distance`` (two points), both
  driving.

The geometry service solves the sketch from the stored positions (a small
Gauss-Newton solve with minimum-norm steps, so the answer stays near the
stored positions, though it is not in general the nearest solution; a lone
length dimension slides the free end along its line). Pipe and Plane
Along Path take its lines as path curves through the ordinary
:class:`loft_wire.pipe.PathSketchCurve`, naming the 3D sketch as ``sketch``.

Pure pydantic, no kernel types. Every model is new, so no stored feature
changes shape or bytes.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from loft_wire.geometry import Vec3
from loft_wire.refs import FeatureRef
from loft_wire.signatures import EdgeSubshapeRef
from loft_wire.sketch import EntityId
from loft_wire.twist import is_none

#: Ceiling on points + lines in one 3D sketch, and on its constraints (the 2D
#: sketch's posture: an order of magnitude past any real skeleton).
MAX_SKETCH_3D_ENTITIES = 1000
MAX_SKETCH_3D_CONSTRAINTS = 2000


class Sketch3DOriginSnap(BaseModel):
    """``kind: "origin"``: the world origin (the part's origin point)."""

    kind: Literal["origin"]


class Sketch3DSketchPointSnap(BaseModel):
    """``kind: "sketch_point"``: a point of an EARLIER sketch, 2D or 3D.

    ``point`` names which point of ``entity``: a curve's ``start``/``end``, a
    circle's or arc's ``center``, a 2D sketch point's or a 3D sketch point's
    ``position``. Read from the solved sketch on every rebuild, so editing
    that sketch moves this point.
    """

    kind: Literal["sketch_point"]
    sketch: FeatureRef = Field(description="The EARLIER sketch that owns the point.")
    entity: EntityId
    point: Literal["start", "end", "center", "position"]


class Sketch3DVertexSnap(BaseModel):
    """``kind: "vertex"``: a model vertex, named as one end of a picked edge.

    ``end`` is ``a`` or ``b`` of the edge signature (its canonically ordered
    endpoints). The edge resolves through the same tiers as every picked edge.
    """

    kind: Literal["vertex"]
    edge: EdgeSubshapeRef
    end: Literal["a", "b"]


#: What a 3D sketch point may be attached to. Discriminated on ``kind``.
Sketch3DSnap = Annotated[
    Sketch3DOriginSnap | Sketch3DSketchPointSnap | Sketch3DVertexSnap,
    Field(discriminator="kind"),
]


class Sketch3DPoint(BaseModel):
    """A point in model space."""

    id: EntityId
    kind: Literal["point"]
    position: Vec3 = Field(
        description="World position (mm): typed, or the last solved position. "
        "The solve starts here; the answer stays near it (minimum-norm "
        "Gauss-Newton steps), though not always at the nearest solution."
    )
    snap: Sketch3DSnap | None = Field(
        default=None,
        exclude_if=is_none,
        description="Geometry the point is attached to (it follows it and is "
        "fixed for the solve), or absent for a free point.",
    )


class Sketch3DLine(BaseModel):
    """A straight line between two points of the same 3D sketch."""

    id: EntityId
    kind: Literal["line"]
    start: EntityId = Field(description="Id of the start point.")
    end: EntityId = Field(description="Id of the end point.")
    construction: bool = Field(
        default=False,
        description="Reference-only: solves and can be dimensioned and picked, "
        "but reads as a construction line in the sketch.",
    )


Sketch3DEntity = Annotated[Sketch3DPoint | Sketch3DLine, Field(discriminator="kind")]


class Sketch3DCoincident(BaseModel):
    """Two points at one place."""

    kind: Literal["coincident"]
    a: EntityId
    b: EntityId


class Sketch3DFixed(BaseModel):
    """A point held at its stored position."""

    kind: Literal["fixed"]
    point: EntityId


class Sketch3DAlong(BaseModel):
    """A line parallel to a world axis (SolidWorks' Along X / Y / Z)."""

    kind: Literal["along"]
    line: EntityId
    axis: Literal["x", "y", "z"]


class Sketch3DLength(BaseModel):
    """A driving length dimension on a line."""

    kind: Literal["length"]
    line: EntityId
    value_mm: float = Field(gt=0, allow_inf_nan=False)


class Sketch3DDistance(BaseModel):
    """A driving point-to-point distance (straight, in model space)."""

    kind: Literal["distance"]
    a: EntityId
    b: EntityId
    value_mm: float = Field(gt=0, allow_inf_nan=False)


Sketch3DConstraint = Annotated[
    Sketch3DCoincident
    | Sketch3DFixed
    | Sketch3DAlong
    | Sketch3DLength
    | Sketch3DDistance,
    Field(discriminator="kind"),
]


class Sketch3DParamsV1(BaseModel):
    """A 3D sketch: points and lines in model space, and their relations."""

    entities: list[Sketch3DEntity] = Field(
        max_length=MAX_SKETCH_3D_ENTITIES,
        description="Points and lines; ids are unique within the sketch and a "
        "line names two distinct points of it.",
    )
    constraints: list[Sketch3DConstraint] = Field(
        default_factory=list["Sketch3DConstraint"],
        max_length=MAX_SKETCH_3D_CONSTRAINTS,
    )

    @model_validator(mode="after")
    def _ids_resolve(self) -> Self:
        ids = [entity.id for entity in self.entities]
        if len(set(ids)) != len(ids):
            raise ValueError("3D sketch entity ids must be unique")
        points = {e.id for e in self.entities if isinstance(e, Sketch3DPoint)}
        lines = {e.id for e in self.entities if isinstance(e, Sketch3DLine)}
        for entity in self.entities:
            if isinstance(entity, Sketch3DLine):
                if entity.start not in points or entity.end not in points:
                    raise ValueError(f"line {entity.id!r} must join two points")
                if entity.start == entity.end:
                    raise ValueError(f"line {entity.id!r} joins a point to itself")
        for index, c in enumerate(self.constraints):
            named = (
                [c.a, c.b]
                if isinstance(c, Sketch3DCoincident | Sketch3DDistance)
                else [c.point]
                if isinstance(c, Sketch3DFixed)
                else []
            )
            if any(p not in points for p in named):
                raise ValueError(f"constraint {index} names a point not in the sketch")
            if len(named) == 2 and named[0] == named[1]:
                raise ValueError(f"constraint {index} names the same point twice")
            if isinstance(c, Sketch3DAlong | Sketch3DLength) and c.line not in lines:
                raise ValueError(f"constraint {index} names a line not in the sketch")
        return self


class SolvedPoint3D(BaseModel):
    """One solved point of a 3D sketch."""

    id: EntityId
    position: Vec3


class SolvedSketch3DData(BaseModel):
    """Per-feature payload of an ``ok`` 3D sketch: the solved point positions
    (world mm, entity order) and how constrained it is. ``kind`` is the
    :data:`loft_wire.features.FeatureData` tag."""

    kind: Literal["solved_sketch_3d"] = "solved_sketch_3d"
    points: list[SolvedPoint3D]
    dof: int = Field(
        ge=0, description="Remaining degrees of freedom (0 = fully constrained)."
    )
    redundant_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices of constraints that are consistent but add nothing.",
    )
