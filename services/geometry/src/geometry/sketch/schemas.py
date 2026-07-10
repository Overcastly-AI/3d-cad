"""Sketch DTOs — 2D entities, constraints, and the solved-sketch result.

Pure pydantic models: no kernel (OCP/build123d) and no solver (planegcs)
types appear here, so these shapes can cross the service boundary unchanged.
They are deliberately importable/moveable — when the sketch API lands they
migrate to ``py_kit.schemas`` (single source of truth, CLAUDE.md DRY rule)
and this module becomes a thin re-export like :mod:`geometry.schemas`.

Shapes follow the feature-tree design (docs/design/feature-tree.md §2.4/§6):
entities carry **sketch-local string ids** (``"e1"``, ``"e2"``, …) that
topological-naming selectors will address later, and the solved result is the
payload the coming ``FeatureResult`` extension (feature-tree §7.10) returns
per sketch feature.

Units: millimetres, matching the persisted feature params
(``py_kit.schemas.geometry`` convention — units are fixed per field, never
tagged per value). Coordinates are 2D in the sketch plane; mapping the plane
into 3D is the sketch *feature's* job, not the solver's.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

#: Sketch-local entity id — unique within one sketch, stable across edits.
EntityId = Annotated[
    str, Field(min_length=1, description="Sketch-local entity id, e.g. 'e1'")
]


class Point2D(BaseModel):
    """A point in sketch-plane coordinates (mm)."""

    x: float
    y: float


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class SketchPoint(BaseModel):
    """A free point (construction geometry, arc centers to snap to, …)."""

    id: EntityId
    kind: Literal["point"]
    position: Point2D


class SketchLine(BaseModel):
    """A line segment between two endpoints."""

    id: EntityId
    kind: Literal["line"]
    start: Point2D
    end: Point2D


class SketchCircle(BaseModel):
    """A full circle."""

    id: EntityId
    kind: Literal["circle"]
    center: Point2D
    radius: float = Field(gt=0, description="Radius (mm)")


class SketchArc(BaseModel):
    """A circular arc traversed **counterclockwise** from start to end.

    The radius is implied by ``|start - center|``; the solver keeps start and
    end on the circle (they may move to satisfy constraints).
    """

    id: EntityId
    kind: Literal["arc"]
    center: Point2D
    start: Point2D
    end: Point2D


SketchEntity = Annotated[
    SketchPoint | SketchLine | SketchCircle | SketchArc,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

#: Named point of an entity. ``position`` addresses a point entity; ``start``/
#: ``end`` address line and arc endpoints; ``center`` addresses circle and
#: arc centers.
PointName = Literal["start", "end", "center", "position"]


class EntityPointRef(BaseModel):
    """Names one point of one entity, e.g. ``{"entity": "e1", "point": "end"}``."""

    entity: EntityId
    point: PointName


class CoincidentConstraint(BaseModel):
    """Two named points share a location."""

    kind: Literal["coincident"]
    a: EntityPointRef
    b: EntityPointRef


class HorizontalConstraint(BaseModel):
    """A line is parallel to the sketch X axis."""

    kind: Literal["horizontal"]
    entity: EntityId


class VerticalConstraint(BaseModel):
    """A line is parallel to the sketch Y axis."""

    kind: Literal["vertical"]
    entity: EntityId


class DistanceConstraint(BaseModel):
    """Driving dimension: the length of a line (mm)."""

    kind: Literal["distance"]
    entity: EntityId
    value_mm: float = Field(gt=0, description="Line length (mm)")


class RadiusConstraint(BaseModel):
    """Driving dimension: the radius of a circle or arc (mm)."""

    kind: Literal["radius"]
    entity: EntityId
    value_mm: float = Field(gt=0, description="Radius (mm)")


class FixedConstraint(BaseModel):
    """Anchor a named point at its current (input) coordinates.

    Every fully-constrained sketch needs an anchor — without one, a rigid
    solution still floats with two translational degrees of freedom.
    """

    kind: Literal["fixed"]
    point: EntityPointRef


SketchConstraint = Annotated[
    CoincidentConstraint
    | HorizontalConstraint
    | VerticalConstraint
    | DistanceConstraint
    | RadiusConstraint
    | FixedConstraint,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Solver input / output
# ---------------------------------------------------------------------------


class SketchDefinition(BaseModel):
    """Solver input: entities (with starting positions) plus constraints.

    Entity positions double as the solver's starting guess — the solved
    result stays near where the user drew. Both lists are **ordered**;
    solvers must process them in list order (determinism, RESEARCH §9).
    """

    entities: list[SketchEntity]
    constraints: list[SketchConstraint]

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchDefinition":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


#: Outcome of a solve, in precedence order (a conflicting sketch is reported
#: ``conflicting`` even if it is also over- or underconstrained):
#:
#: - ``conflicting``      — constraints are mutually unsatisfiable.
#: - ``overconstrained``  — a constraint is redundant (consistent but
#:                          superfluous); a solution may still be returned.
#: - ``diverged``         — the numeric solve failed with no diagnosed
#:                          conflict (bad starting guess, degenerate input).
#: - ``underconstrained`` — solved, but degrees of freedom remain.
#: - ``converged``        — solved and fully constrained.
SketchSolveStatus = Literal[
    "converged",
    "underconstrained",
    "overconstrained",
    "conflicting",
    "diverged",
]


class SolvedSketch(BaseModel):
    """Solver output: solved geometry plus diagnosis.

    This is the payload the per-feature solved-sketch ``FeatureResult``
    extension (feature-tree §7.10) will carry for sketch features.
    """

    status: SketchSolveStatus
    entities: list[SketchEntity] = Field(
        description=(
            "Same entities (ids, kinds, order) as the input. Positions are "
            "solved when the numeric solve succeeded (converged, "
            "underconstrained, and consistent overconstrained cases); for "
            "conflicting/diverged sketches the input positions are returned "
            "unchanged."
        )
    )
    dof: int | None = Field(
        default=None,
        description=(
            "Remaining degrees of freedom (0 = fully constrained); None when "
            "the diagnosis cannot determine it (e.g. conflicting systems)."
        ),
    )
    conflicting_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices into the input constraint list that conflict.",
    )
    redundant_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices into the input constraint list that are redundant.",
    )
