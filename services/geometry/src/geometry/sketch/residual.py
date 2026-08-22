"""Constraint residuals measured from the SOLVED ENTITIES, not from the solver.

The second, independently-derived opinion on "did this solve actually satisfy
the constraints" (SETTLE-3, RESEARCH §2). ``planegcs``'s
``constraint_error(tag)`` is the solver's report on *its own* parameter array;
:func:`geometric_residuals` re-derives the same quantities from the
:class:`~geometry.sketch.schemas.SketchEntity` DTOs that
:meth:`~geometry.sketch.planegcs_solver._GcsBuild.read_back` is about to ship.
Requiring both to hold is the repo's standing answer to a self-verifying check
(CLAUDE.md: *a wrong claim verifies happily against itself* — get a second
opinion from a different derivation, not a louder assertion of the first).

**Two things it can see that the solver's self-report cannot, both real:**

1. **The internal arc rules are outside the solver check's scope entirely.**
   ``add_arc_cse`` auto-adds the rules tying an arc's ``start``/``end`` points
   to its ``center``/``radius``/angles, and they all carry planegcs tag ``0``,
   whose ``constraint_error`` reads ``nan``; the settle check deliberately asks
   only the CALLER's tags, so nothing asks whether an arc is still an arc. But
   ``read_back`` reads ``start_point``/``end_point`` — parameters distinct from
   ``center``/``radius`` and tied to them only by those unasked rules. An arc
   whose two endpoints sit at different distances from its own centre is not a
   curve any kernel can build, and until now it could be shipped.
   :func:`entity_residual` asks that question of the DTO directly.
2. **A hold is accepted on ``SolveStatus.Converged``, which is DogLeg reporting
   that it STOPPED, not that it succeeded** — FreeCAD's DogLeg returns
   ``Success`` when the final error is under its own threshold and ``Converged``
   when it merely stalled. So the residual check is the whole of the safety net
   there, and a residual read off the stalled parameter array is the least
   independent evidence available.

**The formulas are deliberately planegcs's own, not "better" ones.** What is
independent here is the DATA (the DTO entities) and the code path, not the
definition; sharing the definition is what lets the two opinions share the
``SATISFIED_TOL_MM`` scale, so a disagreement means the geometry and the solver
disagree rather than that two conventions were compared. Same posture as
``scripts/check-build-context.py`` re-implementing moby's ignore matcher and
diffing it against the real one. Two small departures remain: a coincidence is
the point distance rather than planegcs's RMS over its two component
constraints (``sqrt(2)`` times larger), and a multi-part constraint (symmetric)
reports its WORST part rather than their RMS.

**Being STRICTER than the solver is a defect here, not a safety margin.** Both
opinions must hold for a settle to keep a hold, so an over-strict residual does
not catch more — it silently refuses settles that are correct, and the product
quietly reverts to the pre-SOLVE-1 behaviour with every gate green. Both
departures above are bounded small factors on quantities already eight orders
under tolerance; anything larger is a bug, and two were found that way (see
below, and :func:`_tangent_residual`).

Angular kinds are the UNIT-NORMALISED cross and dot products, dimensionless —
which is what planegcs itself reports, measured rather than assumed. The first
draft used the raw mm^2 products on the reasoning that matching the solver's
convention was the conservative choice; against a 40 x 38 mm pair that read
**600** where planegcs read **0.394**, i.e. 1500x too large, in the one
direction a second opinion must never err. Both formulas have the same zero
set, so nothing caught it until the two were compared AWAY from a solution.

That is the validation this module needs and the obvious one does not give:
comparing the two opinions after a converged solve compares ``0.0`` against
``0.0``. ``test_sketch_residual_agreement.py`` reads both at the INPUT
configuration, where every residual is large, and asserts (a) identical zero
sets and (b) that this opinion is never the stricter of the two by a margin
that could matter at :data:`SATISFIED_TOL_MM`.
"""

import math
from typing import assert_never

from py_kit.schemas.sketch import spline_fit_index

from geometry.sketch.schemas import (
    CoincidentConstraint,
    ConcentricConstraint,
    DimensionConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSpline,
    SymmetricConstraint,
    TangentConstraint,
    VerticalConstraint,
)

#: Residual reported for a constraint whose references cannot be resolved in
#: the solved entities. Unresolvable is not "satisfied": every reference was
#: resolvable when the system was built, so failing to resolve one now means
#: the two views disagree about the sketch, and the safe direction is to
#: refuse. ``inf`` compares False against every tolerance without needing one.
UNRESOLVABLE = math.inf

_Vec = tuple[float, float]


def _point_of(
    ref: EntityPointRef, entities_by_id: dict[str, SketchEntity]
) -> _Vec | None:
    """The DTO coordinate an ``EntityPointRef`` names, or ``None`` if it names none."""
    entity = entities_by_id.get(ref.entity)
    match entity:
        case SketchPoint():
            return (
                (entity.position.x, entity.position.y)
                if ref.point == "position"
                else None
            )
        case SketchLine():
            if ref.point == "start":
                return (entity.start.x, entity.start.y)
            if ref.point == "end":
                return (entity.end.x, entity.end.y)
            return None
        case SketchCircle():
            return (entity.center.x, entity.center.y) if ref.point == "center" else None
        case SketchArc():
            if ref.point == "center":
                return (entity.center.x, entity.center.y)
            if ref.point == "start":
                return (entity.start.x, entity.start.y)
            if ref.point == "end":
                return (entity.end.x, entity.end.y)
            return None
        case SketchSpline():
            index = spline_fit_index(ref.point)
            if index is None or not 0 <= index < len(entity.points):
                return None
            fit = entity.points[index]
            return (fit.x, fit.y)
        case None:
            return None
        case _:  # pragma: no cover — the entity union is closed
            assert_never(entity)


def _direction(entity: SketchEntity | None) -> _Vec | None:
    """A line's ``start -> end`` vector; ``None`` for anything that is not a line."""
    if not isinstance(entity, SketchLine):
        return None
    return (entity.end.x - entity.start.x, entity.end.y - entity.start.y)


def _radius_of(entity: SketchEntity | None) -> float | None:
    """A circle's radius, or an arc's ``|start - center|``; ``None`` otherwise.

    An arc's radius is DERIVED from its start point rather than carried, exactly
    as :func:`geometry.sketch.expression.measure_dimension` derives it, so an arc
    whose endpoints disagree about their own centre distance shows up here as a
    disagreement with the solver's arc-radius parameter — which is the point.
    """
    if isinstance(entity, SketchCircle):
        return entity.radius
    if isinstance(entity, SketchArc):
        return math.hypot(
            entity.start.x - entity.center.x, entity.start.y - entity.center.y
        )
    return None


def _center_of(entity: SketchEntity | None) -> _Vec | None:
    if isinstance(entity, SketchCircle | SketchArc):
        return (entity.center.x, entity.center.y)
    return None


def _unit_cross(a: _Vec, b: _Vec) -> float:
    """``sin`` of the angle between two vectors — planegcs's own parallel error.

    ``0.0`` when either vector is degenerate: the relation is undefined there
    and planegcs's normalised error is ``0/0``, so the SOLVER's opinion already
    refuses such a hold (``nan`` fails its comparison). This one declines to be
    the rejecter on account of its own blindness.
    """
    scale = math.hypot(*a) * math.hypot(*b)
    return 0.0 if scale == 0.0 else abs(a[0] * b[1] - a[1] * b[0]) / scale


def _unit_dot(a: _Vec, b: _Vec) -> float:
    """``cos`` of the angle between two vectors — planegcs's perpendicular error."""
    scale = math.hypot(*a) * math.hypot(*b)
    return 0.0 if scale == 0.0 else abs(a[0] * b[0] + a[1] * b[1]) / scale


def _point_to_line(point: _Vec, start: _Vec, direction: _Vec) -> float | None:
    """Perpendicular distance from ``point`` to the infinite line, in mm."""
    length = math.hypot(*direction)
    if length == 0.0:
        return None  # a degenerate line defines no distance
    return (
        abs((point[0] - start[0]) * direction[1] - (point[1] - start[1]) * direction[0])
        / length
    )


def entity_residual(entity: SketchEntity) -> float:
    """How far an entity is from being a well-formed instance of its own kind (mm).

    Only arcs can be internally inconsistent: ``center``/``start``/``end`` are
    three independent DTO coordinates, and an arc requires the two endpoints to
    be equidistant from the centre. planegcs enforces that with its own
    tag-``0`` arc rules, which no caller-tag residual check can see (their error
    reads ``nan``, and the settle check asks only the caller's tags), so this is
    the only thing that asks. Every other kind is well-formed by construction.
    """
    if isinstance(entity, SketchArc):
        start = math.hypot(
            entity.start.x - entity.center.x, entity.start.y - entity.center.y
        )
        end = math.hypot(entity.end.x - entity.center.x, entity.end.y - entity.center.y)
        return abs(start - end)
    return 0.0


def _dimension_residual(
    constraint: DimensionConstraint,
    entities_by_id: dict[str, SketchEntity],
    requested: float,
) -> float:
    match constraint:
        case DistanceConstraint():
            direction = _direction(entities_by_id.get(constraint.entity))
            if direction is None:
                return UNRESOLVABLE
            return abs(math.hypot(*direction) - requested)
        case RadiusConstraint():
            radius = _radius_of(entities_by_id.get(constraint.entity))
            if radius is None:
                return UNRESOLVABLE
            return abs(radius - requested)
        case _:  # pragma: no cover — only distance/radius dimensions exist today
            return UNRESOLVABLE


def _tangent_residual(
    constraint: TangentConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """Line/curve: ``|centre-to-line distance - r|``. Curve/curve: "do they touch".

    Line/curve matches planegcs exactly — measured, its
    ``tangent_line_circle``/``tangent_line_arc`` error IS ``gap - r`` in mm.

    Curve/curve is deliberately the WEAKER condition ``min(|d - (r1 + r2)|,
    |d - |r1 - r2||)`` — tangency on *either* branch, external or internal.
    planegcs's own curve/curve error is neither: it is quadratic (``d^2 - R^2``,
    mm^2) and it SELECTS the branch, so writing "external" here — the obvious
    reading of ``tangent_circle_circle``, which exposes no internal variant —
    makes this opinion reject valid geometry. Measured before it shipped: two
    circles made coincident and tangent settle to one circle at the origin,
    which planegcs correctly calls satisfied (``d = |r1 - r2| = 0``) and an
    external-only residual calls a **17.22 mm** violation. That would have been
    a second opinion that is itself wrong, which is worse than none — the
    randomised sweep that found it reported five such "holes" and every one was
    this bug.

    A second opinion may be weaker than the first; it may not be stricter for a
    reason it invented. Its job is to see what the first is blind to, not to
    re-referee cases the first already judges correctly.
    """
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    line, curve = (a, b) if isinstance(a, SketchLine) else (b, a)
    if isinstance(line, SketchLine):
        radius = _radius_of(curve)
        center = _center_of(curve)
        if radius is None or center is None:
            return UNRESOLVABLE
        distance = _point_to_line(
            center,
            (line.start.x, line.start.y),
            (line.end.x - line.start.x, line.end.y - line.start.y),
        )
        return UNRESOLVABLE if distance is None else abs(distance - radius)
    ra, rb = _radius_of(a), _radius_of(b)
    ca, cb = _center_of(a), _center_of(b)
    if ra is None or rb is None or ca is None or cb is None:
        return UNRESOLVABLE
    distance = math.hypot(cb[0] - ca[0], cb[1] - ca[1])
    return min(abs(distance - (ra + rb)), abs(distance - abs(ra - rb)))


def _equal_residual(
    constraint: EqualConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    da, db = _direction(a), _direction(b)
    if da is not None and db is not None:
        return abs(math.hypot(*da) - math.hypot(*db))
    ra, rb = _radius_of(a), _radius_of(b)
    if ra is None or rb is None:
        return UNRESOLVABLE
    return abs(ra - rb)


def _symmetric_residual(
    constraint: SymmetricConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """The WORSE of planegcs's two parts, which share one tag.

    ``addConstraintSymmetric`` is a perpendicular (the ``a -> b`` segment against
    the mirror line, mm^2) plus a point-on-perpendicular-bisector (``|l1 - a|``
    vs ``|l1 - b|``, mm). planegcs reports their RMS; taking the worst instead
    cannot make this opinion more permissive than that one.
    """
    a = _point_of(constraint.a, entities_by_id)
    b = _point_of(constraint.b, entities_by_id)
    line = entities_by_id.get(constraint.line)
    if a is None or b is None or not isinstance(line, SketchLine):
        return UNRESOLVABLE
    lx, ly = line.start.x, line.start.y
    dx, dy = line.end.x - lx, line.end.y - ly
    perpendicular = _unit_dot((b[0] - a[0], b[1] - a[1]), (dx, dy))
    bisector = abs(math.hypot(a[0] - lx, a[1] - ly) - math.hypot(b[0] - lx, b[1] - ly))
    return max(perpendicular, bisector)


def constraint_residual(
    constraint: SketchConstraint,
    entities_by_id: dict[str, SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    requested: float | None,
) -> float | None:
    """This constraint's residual against the SOLVED entities, or ``None``.

    ``None`` means "not part of the constraint system", which today is exactly
    a DRIVEN dimension (``requested is None``): its value is measured back from
    the geometry, so it constrains nothing and cannot be violated.

    ``requested`` is the evaluated value of a DRIVING dimension;
    ``input_points`` supplies the author's submitted coordinates, which are what
    a ``fixed`` constraint pins to (``fix_point`` reads the pre-solve position).
    """
    match constraint:
        case DimensionConstraint():
            if requested is None:
                return None
            return _dimension_residual(constraint, entities_by_id, requested)
        case CoincidentConstraint():
            a = _point_of(constraint.a, entities_by_id)
            b = _point_of(constraint.b, entities_by_id)
            if a is None or b is None:
                return UNRESOLVABLE
            return math.hypot(b[0] - a[0], b[1] - a[1])
        case ConcentricConstraint():
            a = _center_of(entities_by_id.get(constraint.a))
            b = _center_of(entities_by_id.get(constraint.b))
            if a is None or b is None:
                return UNRESOLVABLE
            return math.hypot(b[0] - a[0], b[1] - a[1])
        case HorizontalConstraint():
            direction = _direction(entities_by_id.get(constraint.entity))
            return UNRESOLVABLE if direction is None else abs(direction[1])
        case VerticalConstraint():
            direction = _direction(entities_by_id.get(constraint.entity))
            return UNRESOLVABLE if direction is None else abs(direction[0])
        case FixedConstraint():
            here = _point_of(constraint.point, entities_by_id)
            there = input_points.get((constraint.point.entity, constraint.point.point))
            if here is None or there is None:
                return UNRESOLVABLE
            return max(abs(here[0] - there[0]), abs(here[1] - there[1]))
        case ParallelConstraint():
            a = _direction(entities_by_id.get(constraint.a))
            b = _direction(entities_by_id.get(constraint.b))
            if a is None or b is None:
                return UNRESOLVABLE
            return _unit_cross(a, b)
        case PerpendicularConstraint():
            a = _direction(entities_by_id.get(constraint.a))
            b = _direction(entities_by_id.get(constraint.b))
            if a is None or b is None:
                return UNRESOLVABLE
            return _unit_dot(a, b)
        case TangentConstraint():
            return _tangent_residual(constraint, entities_by_id)
        case EqualConstraint():
            return _equal_residual(constraint, entities_by_id)
        case SymmetricConstraint():
            return _symmetric_residual(constraint, entities_by_id)
        case _:  # pragma: no cover — the constraint union is closed
            assert_never(constraint)


def geometric_residuals(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    driving_values: dict[int, float],
) -> list[tuple[int, float]]:
    """``(constraint index, residual)`` for every constraint in the system.

    In input order — deterministic, like every other pass over a sketch
    (RESEARCH §9). Driven dimensions are absent (they constrain nothing).
    """
    entities_by_id = {entity.id: entity for entity in entities}
    residuals: list[tuple[int, float]] = []
    for index, constraint in enumerate(constraints):
        residual = constraint_residual(
            constraint, entities_by_id, input_points, driving_values.get(index)
        )
        if residual is not None:
            residuals.append((index, residual))
    return residuals


def worst_residual(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    driving_values: dict[int, float],
) -> float:
    """The largest residual over every constraint AND every entity's own form.

    ``0.0`` for a sketch with nothing to check, which is the honest answer: an
    unconstrained sketch of well-formed entities violates nothing.
    """
    worst = 0.0
    for entity in entities:
        worst = max(worst, entity_residual(entity))
    for _, residual in geometric_residuals(
        constraints, entities, input_points, driving_values
    ):
        worst = max(worst, residual)
    return worst
