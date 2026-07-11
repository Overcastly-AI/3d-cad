"""2D sketch solving — DTOs, the ``SketchSolver`` protocol, and backends.

Decision record: RESEARCH §2 (planegcs, LGPL-2.1-or-later, behind the
protocol). Callers import from this package, never from ``planegcs``.
"""

from geometry.sketch.planegcs_solver import PlanegcsSketchSolver
from geometry.sketch.schemas import (
    CoincidentConstraint,
    ConcentricConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolveStatus,
    SolvedSketch,
    SymmetricConstraint,
    TangentConstraint,
    VerticalConstraint,
)
from geometry.sketch.solver import SketchDefinitionError, SketchSolver

__all__ = [
    "CoincidentConstraint",
    "ConcentricConstraint",
    "DistanceConstraint",
    "EntityPointRef",
    "EqualConstraint",
    "FixedConstraint",
    "HorizontalConstraint",
    "ParallelConstraint",
    "PerpendicularConstraint",
    "PlanegcsSketchSolver",
    "Point2D",
    "RadiusConstraint",
    "SketchArc",
    "SketchCircle",
    "SketchConstraint",
    "SketchDefinition",
    "SketchDefinitionError",
    "SketchEntity",
    "SketchLine",
    "SketchPoint",
    "SketchSolveStatus",
    "SketchSolver",
    "SolvedSketch",
    "SymmetricConstraint",
    "TangentConstraint",
    "VerticalConstraint",
]
