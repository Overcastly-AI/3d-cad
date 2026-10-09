"""Sketch dimension expressions: the geometry side of Loft's expression language.

The language itself (tokenizer, parser, units, functions, the dependency
order and cycle report) lives in :mod:`loft_wire.expr`, standard-library only,
so documents and ``loft-script`` evaluate a string exactly as this service
does. This module adapts it to the sketch solver and keeps what needs solved
geometry: measuring a DRIVEN dimension's value back from the solve.

Every expression failure surfaces here as :class:`SketchExpressionError`, a
subclass of :class:`~geometry.sketch.solver.SketchDefinitionError`, so the
feature evaluator maps it to the ``sketch_invalid`` per-feature error (never a
500): syntax errors, unknown or driven references, reference cycles, unit
clashes, division by zero and out-of-range results.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from loft_wire import expr
from loft_wire.sketch import (
    AngleConstraint,
    DiameterConstraint,
    DimensionConstraint,
    DistanceConstraint,
    PointDistanceConstraint,
    PointLineDistanceConstraint,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchEntity,
    SketchLine,
)

from geometry.sketch.angles import AngleFrame, measured_angle_deg
from geometry.sketch.point_distance import entity_lookups, measured
from geometry.sketch.solver import SketchDefinitionError
from geometry.sketch.virtual_sharp import measured_length


class SketchExpressionError(SketchDefinitionError):
    """A dimension expression is malformed, references an unknown/driven
    dimension, forms a reference cycle, mixes units, or divides by zero.

    A subclass of :class:`SketchDefinitionError` so the existing
    ``except SketchDefinitionError`` in the feature evaluator maps it to the
    ``sketch_invalid`` error envelope with no new plumbing.
    """


@dataclass(frozen=True)
class SketchExpression:
    """A parsed dimension expression whose failures are sketch errors."""

    parsed: expr.Expression

    def references(self) -> frozenset[str]:
        return self.parsed.references()

    def evaluate(self, resolve: Callable[[str], float]) -> float:
        """Evaluate with each reference a plain number (mm or degrees)."""
        try:
            return self.parsed.evaluate_number(resolve)
        except expr.ExpressionError as exc:
            raise SketchExpressionError(str(exc)) from exc


def parse_expression(text: str) -> SketchExpression:
    """Parse a dimension expression (raises :class:`SketchExpressionError`).

    Exposed for unit testing; callers normally use
    :func:`evaluate_driving_dimensions`.
    """
    try:
        return SketchExpression(expr.parse(text))
    except expr.ExpressionError as exc:
        raise SketchExpressionError(str(exc)) from exc


def evaluate_driving_dimensions(
    constraints: Sequence[SketchConstraint],
) -> dict[int, float]:
    """Every DRIVING dimension's value, by constraint index, in its own unit
    (mm, or degrees for an angle). See
    :func:`loft_wire.expr.evaluate_driving_dimensions`; any failure is a
    :class:`SketchExpressionError`."""
    try:
        return expr.evaluate_driving_dimensions(constraints)
    except expr.ExpressionError as exc:
        raise SketchExpressionError(str(exc)) from exc


def measure_dimension(
    constraint: DimensionConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """Measure a **driven** dimension's value from solved geometry (mm).

    A driven dimension is excluded from the constraint system, so its displayed
    value is read back from the geometry it dimensions: a distance is the solved
    line's length; a radius is the solved circle's radius or the arc's
    ``|start - center|``; a diameter is twice that radius, so the readout is in
    the same unit the user typed. A driven dimension on the wrong entity kind (or an
    unknown entity) is a malformed definition — :class:`SketchDefinitionError`,
    mapped to ``sketch_invalid`` like any other bad reference.
    """
    match constraint:
        case DistanceConstraint():
            length = measured_length(constraint, entities_by_id)
            if length is not None:
                return length
            entity = entities_by_id.get(constraint.entity)
            sharps = (constraint.start_sharp, constraint.end_sharp)
            if not isinstance(entity, SketchLine) or any(
                s is not None and not isinstance(entities_by_id.get(s), SketchLine)
                for s in sharps
            ):
                raise SketchDefinitionError(
                    f"Driven 'distance' dimension requires a line entity (and "
                    f"a line for any virtual sharp); {constraint.entity!r} "
                    "does not resolve"
                )
            # A virtual sharp of two PARALLEL lines does not exist: the solve
            # reads conflicting (residual.py), and the readout falls back to
            # the line's own length rather than inventing a far-away point.
            return math.hypot(
                entity.end.x - entity.start.x, entity.end.y - entity.start.y
            )
        case PointDistanceConstraint() | PointLineDistanceConstraint():
            # A sharp whose legs are parallel in THIS geometry reads its named
            # point, as `distance` reads its own end; non-lines still refuse.
            value = measured(
                constraint, *entity_lookups(entities_by_id), sharp_fallback=True
            )
            if value is None:
                raise SketchDefinitionError(
                    f"Driven {constraint.kind!r} dimension does not resolve: a "
                    "point it names is missing, a virtual sharp's lines are not "
                    "two crossing lines, or the line is not a line"
                )
            return value
        case RadiusConstraint():
            entity = entities_by_id.get(constraint.entity)
            if isinstance(entity, SketchCircle):
                return entity.radius
            if isinstance(entity, SketchArc):
                return math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
            raise SketchDefinitionError(
                f"Driven 'radius' dimension requires a circle or arc entity; "
                f"{constraint.entity!r} is neither"
            )
        case DiameterConstraint():
            entity = entities_by_id.get(constraint.entity)
            if isinstance(entity, SketchCircle):
                return 2.0 * entity.radius
            if isinstance(entity, SketchArc):
                return 2.0 * math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
            raise SketchDefinitionError(
                f"Driven 'diameter' dimension requires a circle or arc entity; "
                f"{constraint.entity!r} is neither"
            )
        case _:
            raise SketchDefinitionError(
                f"Cannot measure driven dimension of kind {constraint!r}"
            )


def measure_angle(
    constraint: AngleConstraint,
    entities_by_id: dict[str, SketchEntity],
    frame: AngleFrame | None,
) -> float:
    """Measure an angle dimension from solved geometry, in DEGREES.

    The angular twin of :func:`measure_dimension`, kept separate because its
    unit is not millimetres and because it needs the authoring convention
    (:class:`~geometry.sketch.angles.AngleFrame`) that says WHICH of the two
    supplementary angles the constraint names — a fact about the sketch as
    DRAWN, which solved geometry alone cannot supply.

    Both ids must be lines: an angle dimension on anything else is a malformed
    definition (:class:`SketchDefinitionError`, mapped to ``sketch_invalid``),
    the same treatment a radius dimension on a line gets.
    """
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    if not isinstance(a, SketchLine) or not isinstance(b, SketchLine):
        raise SketchDefinitionError(
            f"'angle' dimension requires two line entities; {constraint.a!r} "
            f"and {constraint.b!r} are not both known lines"
        )
    if frame is None:  # pragma: no cover — a two-line constraint always frames
        raise SketchDefinitionError(
            f"'angle' dimension between {constraint.a!r} and {constraint.b!r} "
            "has no measurable frame in the submitted sketch"
        )
    return measured_angle_deg(
        frame,
        (a.end.x - a.start.x, a.end.y - a.start.y),
        (b.end.x - b.start.x, b.end.y - b.start.y),
    )
