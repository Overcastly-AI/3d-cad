"""Sketch DTOs — thin re-export of the shared py-kit models.

The boundary models live in :mod:`py_kit.schemas.sketch` (single source of
truth, CLAUDE.md DRY rule), migrated there by the "Sketch model + solver API"
item exactly as this module's original docstring promised — sketch feature
params persisted by documents and the solver input/output used here are the
same pydantic shapes. This module stays as the service-local alias, keeping
solver/evaluator/test imports stable (same pattern as :mod:`geometry.schemas`).
"""

from py_kit.schemas.sketch import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityId,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    Point2D,
    PointName,
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
    VerticalConstraint,
)

__all__ = [
    "CoincidentConstraint",
    "DistanceConstraint",
    "EntityId",
    "EntityPointRef",
    "FixedConstraint",
    "HorizontalConstraint",
    "Point2D",
    "PointName",
    "RadiusConstraint",
    "SketchArc",
    "SketchCircle",
    "SketchConstraint",
    "SketchDefinition",
    "SketchEntity",
    "SketchLine",
    "SketchPoint",
    "SketchSolveStatus",
    "SolvedSketch",
    "VerticalConstraint",
]
