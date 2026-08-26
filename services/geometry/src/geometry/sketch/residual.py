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
constraints (``sqrt(2)`` times larger), and the POINT form of ``symmetric``
reports its WORST part rather than their RMS (also ``sqrt(2)``). Both sit
exactly ON ``MAX_STRICTER_RATIO``, which is why a constraint that aggregates
SEVERAL such parts — ``symmetric_lines``, which holds two mirrored pairs — uses
planegcs's RMS within each pair instead: two ``sqrt(2)`` departures compounding
is how the invariant gets broken, and it was, measurably
(:func:`_symmetric_lines_residual`).

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

from geometry.sketch.angles import AngleFrame, angle_frames, oriented_angle_rad
from geometry.sketch.schemas import (
    AngleConstraint,
    CoincidentConstraint,
    CollinearConstraint,
    ConcentricConstraint,
    DiameterConstraint,
    DimensionConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    MidpointConstraint,
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
    SymmetricLinesConstraint,
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
_PointKey = tuple[str, str]


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


def _angle_residual(
    constraint: AngleConstraint,
    entities_by_id: dict[str, SketchEntity],
    requested_deg: float,
    frame: AngleFrame | None,
) -> float:
    """``|solved angle - requested|`` in RADIANS — planegcs's own angular scale.

    ``ConstraintL2LAngle``'s error is the difference between the two lines'
    directed angles and the target, wrapped by ``atan2`` into ``(-pi, pi]``; this
    is that quantity re-derived from the solved DTOs. Radians, not degrees,
    because :data:`~geometry.sketch.planegcs_solver.SATISFIED_TOL_MM` is
    documented to be read on the constraint's OWN scale, and degrees would make
    this opinion ~57x more permissive than the solver's.

    ``frame is None`` means the constraint's own references did not resolve to
    two lines in the SUBMITTED sketch, which is not a state a built system can
    reach — so, like every other unresolvable reference here, it refuses.
    """
    if frame is None:
        return UNRESOLVABLE
    a_dir = _direction(entities_by_id.get(constraint.a))
    b_dir = _direction(entities_by_id.get(constraint.b))
    if a_dir is None or b_dir is None:
        return UNRESOLVABLE
    if math.hypot(*a_dir) == 0.0 or math.hypot(*b_dir) == 0.0:
        # A degenerate line has no direction; planegcs's own error is undefined
        # there and this opinion declines to be the rejecter (same posture as
        # `_unit_cross`).
        return 0.0
    error = oriented_angle_rad(frame, a_dir, b_dir) - math.radians(
        frame.sense * requested_deg
    )
    return abs(math.remainder(error, math.tau))


def _dimension_residual(
    constraint: DimensionConstraint,
    entities_by_id: dict[str, SketchEntity],
    requested: float,
    frame: AngleFrame | None,
) -> float:
    match constraint:
        case AngleConstraint():
            return _angle_residual(constraint, entities_by_id, requested, frame)
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
        case DiameterConstraint():
            # MEASURED, not assumed: planegcs's ``circle_diameter`` error is
            # ``r - d/2`` — the RADIUS-scale miss, not the diameter one. Probed
            # at r=10 asking d=26 it reports 3.0, the same number
            # ``set_circle_radius(13)`` reports, where ``|2r - d|`` would be 6.0.
            # Writing the diameter difference here would make this opinion
            # exactly 2x stricter than the solver's, which is the parallel bug's
            # shape: a second opinion that refuses holds the solver accepts.
            radius = _radius_of(entities_by_id.get(constraint.entity))
            if radius is None:
                return UNRESOLVABLE
            return abs(radius - requested / 2.0)
        case _:  # pragma: no cover — the dimension kinds above are exhaustive
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


def _symmetric_pair_parts(a: _Vec, b: _Vec, line: SketchLine) -> tuple[float, float]:
    """planegcs's two parts of "these two points mirror about ``line``".

    A perpendicular (the ``a -> b`` segment against the mirror line,
    unit-normalised) and a point-on-perpendicular-bisector (``|l1 - a|`` vs
    ``|l1 - b|``, mm). planegcs carries both under ONE tag and reports their RMS.
    """
    lx, ly = line.start.x, line.start.y
    dx, dy = line.end.x - lx, line.end.y - ly
    perpendicular = _unit_dot((b[0] - a[0], b[1] - a[1]), (dx, dy))
    bisector = abs(math.hypot(a[0] - lx, a[1] - ly) - math.hypot(b[0] - lx, b[1] - ly))
    return perpendicular, bisector


def _symmetric_pair_residual(a: _Vec, b: _Vec, line: SketchLine) -> float:
    """The WORSE of the two parts — the point form's long-standing convention."""
    return max(_symmetric_pair_parts(a, b, line))


def _symmetric_pair_rms(a: _Vec, b: _Vec, line: SketchLine) -> float:
    """planegcs's OWN aggregation of the two parts: their root-mean-square.

    Used where a constraint holds more than one mirrored pair, so that the max
    ACROSS pairs does not compound with a max WITHIN each pair — see
    :func:`_symmetric_lines_residual`, where that compounding measurably broke
    the "never the stricter witness" invariant.
    """
    perpendicular, bisector = _symmetric_pair_parts(a, b, line)
    return math.sqrt((perpendicular * perpendicular + bisector * bisector) / 2.0)


def _symmetric_residual(
    constraint: SymmetricConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """The WORSE of planegcs's two parts, which share one tag.

    ``addConstraintSymmetric`` is a perpendicular plus a
    point-on-perpendicular-bisector; planegcs reports their RMS, and taking the
    worst instead cannot make this opinion more permissive than that one.
    """
    a = _point_of(constraint.a, entities_by_id)
    b = _point_of(constraint.b, entities_by_id)
    line = entities_by_id.get(constraint.line)
    if a is None or b is None or not isinstance(line, SketchLine):
        return UNRESOLVABLE
    return _symmetric_pair_residual(a, b, line)


def _reflect(point: _Vec, line_start: _Vec, direction: _Vec) -> _Vec | None:
    """``point`` mirrored in the infinite line; ``None`` if the line is degenerate."""
    length_sq = direction[0] ** 2 + direction[1] ** 2
    if length_sq == 0.0:
        return None
    vx, vy = point[0] - line_start[0], point[1] - line_start[1]
    scale = 2.0 * (vx * direction[0] + vy * direction[1]) / length_sq
    return (
        line_start[0] + scale * direction[0] - vx,
        line_start[1] + scale * direction[1] - vy,
    )


def symmetric_lines_crossed(
    constraint: SymmetricLinesConstraint, points: dict[_PointKey, _Vec]
) -> bool:
    """Does ``a``'s START pair with ``b``'s END rather than with its start?

    The one authoring decision a ``symmetric_lines`` constraint carries, made
    from the SUBMITTED coordinates so it is a function of the sketch alone
    (RESEARCH §9) and identical for the solver wiring and for the residual —
    which must measure the same pairing the solver is holding or it would report
    a violation on a correct solve.

    Reflect ``a``'s two endpoints in the axis and compare the total squared
    distance to ``b``'s under each pairing; the closer one wins, and a tie keeps
    the straight (start-to-start) pairing so the answer is total. A missing or
    degenerate reference also falls back to the straight pairing — the constraint
    is malformed either way, and the solver's own kind checks are what report
    that.
    """
    keys = ("start", "end")
    try:
        a_points = [points[(constraint.a, key)] for key in keys]
        b_points = [points[(constraint.b, key)] for key in keys]
        axis = [points[(constraint.line, key)] for key in keys]
    except KeyError:
        return False
    direction = (axis[1][0] - axis[0][0], axis[1][1] - axis[0][1])
    mirrored = [_reflect(point, axis[0], direction) for point in a_points]
    if any(point is None for point in mirrored):
        return False

    def cost(pairs: list[tuple[_Vec, _Vec]]) -> float:
        return sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for p, q in pairs)

    straight = cost([(mirrored[0], b_points[0]), (mirrored[1], b_points[1])])  # pyright: ignore[reportArgumentType]
    crossed = cost([(mirrored[0], b_points[1]), (mirrored[1], b_points[0])])  # pyright: ignore[reportArgumentType]
    return crossed < straight


def symmetric_lines_pairs(
    constraint: SymmetricLinesConstraint, points: dict[_PointKey, _Vec]
) -> tuple[tuple[str, str], tuple[str, str]]:
    """The two ``(a point name, b point name)`` pairs this constraint relates."""
    if symmetric_lines_crossed(constraint, points):
        return (("start", "end"), ("end", "start"))
    return (("start", "start"), ("end", "end"))


def _symmetric_lines_residual(
    constraint: SymmetricLinesConstraint,
    entities_by_id: dict[str, SketchEntity],
    input_points: dict[_PointKey, _Vec],
) -> float:
    """The worst of the two mirrored point pairs, under the authored pairing.

    The max ACROSS the two pairs, because planegcs holds them as two separate
    tags and the settle asks each of them separately.

    **Within each pair the quantity is planegcs's own RMS, not the worse part,
    and that was forced by the agreement suite rather than chosen.** The point
    form of ``symmetric`` reports the worse of its two parts, which is up to
    ``sqrt(2)`` stricter than the RMS planegcs reports for the same tag — and
    ``sqrt(2)`` is exactly ``MAX_STRICTER_RATIO``, so one tag sits ON the ceiling
    and a max over two of them steps over it. Measured on the two-legs fixture:
    the worst-part form read **2.093** against planegcs's **1.419**, a ratio of
    1.47 where 1.414 is the bound, and the suite refused it. That is the module
    docstring's rule biting for real — a second opinion that refuses holds the
    solver accepts silently disables the settle — and the fix is to match the
    witness's aggregation, not to widen the bound.
    """
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    line = entities_by_id.get(constraint.line)
    if (
        not isinstance(a, SketchLine)
        or not isinstance(b, SketchLine)
        or not isinstance(line, SketchLine)
    ):
        return UNRESOLVABLE

    def end(entity: SketchLine, name: str) -> _Vec:
        point = entity.start if name == "start" else entity.end
        return (point.x, point.y)

    worst = 0.0
    for a_point, b_point in symmetric_lines_pairs(constraint, input_points):
        worst = max(worst, _symmetric_pair_rms(end(a, a_point), end(b, b_point), line))
    return worst


def _midpoint_residual(
    constraint: MidpointConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """The WORSE of planegcs's two parts, which share this constraint's index.

    ``midpoint`` is a point-on-line (perpendicular distance, mm) plus a
    point-on-perpendicular-bisector, and taking the worst of the two cannot make
    this opinion more permissive than asking each tag separately — the same
    posture as :func:`_symmetric_residual`, built from the same two ideas.

    **The bisector part is PROBED, not inferred.** The natural reading of "point
    on the perpendicular bisector" is ``| |p - l1| - |p - l2| |``, and that is
    NOT what planegcs reports: measured against a 40 mm line, its error is
    ``(|p - l1|^2 - |p - l2|^2) / L`` — which is twice the point's signed offset
    ALONG the line from the midpoint, and so grows without bound where the
    length difference saturates. At ``p = (140, 0)`` on ``(0,0)-(40,0)`` it reads
    **240** where the length difference reads 40, a factor of six. Writing the
    obvious formula would not have been *stricter* (the forbidden direction) but
    it would have made this witness six times blinder than the one it is meant
    to double-check, which is nearly as bad and much harder to notice: both
    formulas have the same zero set, so every converged solve would agree.
    That is the same trap the parallel residual fell into, caught the same way —
    by comparing the two opinions AWAY from a solution.
    """
    point = _point_of(constraint.point, entities_by_id)
    line = entities_by_id.get(constraint.line)
    if point is None or not isinstance(line, SketchLine):
        return UNRESOLVABLE
    start = (line.start.x, line.start.y)
    end = (line.end.x, line.end.y)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    perpendicular = _point_to_line(point, start, (end[0] - start[0], end[1] - start[1]))
    if perpendicular is None or length == 0.0:
        # A degenerate line defines neither a perpendicular nor a bisector;
        # planegcs's own error is undefined there and rejects the hold on its
        # own (same posture as `_unit_cross`). This opinion declines to be the
        # rejecter on account of its own blindness.
        return 0.0
    to_start = math.hypot(point[0] - start[0], point[1] - start[1])
    to_end = math.hypot(point[0] - end[0], point[1] - end[1])
    bisector = abs(to_start * to_start - to_end * to_end) / length
    return max(perpendicular, bisector)


def _collinear_residual(
    constraint: CollinearConstraint, entities_by_id: dict[str, SketchEntity]
) -> float:
    """The WORSE of the two point-on-line distances planegcs is actually holding.

    Exactly the two witnesses, in their own units: ``collinear`` is wired as
    ``b``'s two endpoints on ``a``'s infinite line, and ``point_on_line``'s error
    IS that perpendicular distance in mm (measured). So this is the max of the
    two tag errors rather than a re-derivation of "collinear" from some other
    definition, and it cannot be stricter than either.

    Note it deliberately does NOT also measure ``a``'s endpoints against ``b``.
    That would be a relation the solver is not holding, and where ``b`` is short
    or degenerate it reads a violation planegcs does not — a second opinion
    refusing on its own authority, which is the defect this module's docstring
    is about.
    """
    a = entities_by_id.get(constraint.a)
    b = entities_by_id.get(constraint.b)
    if not isinstance(a, SketchLine) or not isinstance(b, SketchLine):
        return UNRESOLVABLE
    start = (a.start.x, a.start.y)
    direction = (a.end.x - a.start.x, a.end.y - a.start.y)
    worst = 0.0
    for point in ((b.start.x, b.start.y), (b.end.x, b.end.y)):
        distance = _point_to_line(point, start, direction)
        if distance is None:
            # ``a`` is degenerate and defines no line; planegcs's own error is
            # undefined there and refuses the hold on its own (same posture as
            # `_unit_cross`). This opinion declines to be the rejecter.
            return 0.0
        worst = max(worst, distance)
    return worst


def constraint_residual(
    constraint: SketchConstraint,
    entities_by_id: dict[str, SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    requested: float | None,
    frame: AngleFrame | None = None,
) -> float | None:
    """This constraint's residual against the SOLVED entities, or ``None``.

    ``None`` means "not part of the constraint system", which today is exactly
    a DRIVEN dimension (``requested is None``): its value is measured back from
    the geometry, so it constrains nothing and cannot be violated.

    ``requested`` is the evaluated value of a DRIVING dimension, in that
    dimension's own unit; ``input_points`` supplies the author's submitted
    coordinates, which are what a ``fixed`` constraint pins to (``fix_point``
    reads the pre-solve position). ``frame`` is the angle convention for an
    ``angle`` dimension (:mod:`geometry.sketch.angles`) — the one piece of state
    that cannot be re-derived here, because it records the angle the author DREW
    and this function sees only the solved geometry.
    """
    match constraint:
        case DimensionConstraint():
            if requested is None:
                return None
            return _dimension_residual(constraint, entities_by_id, requested, frame)
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
        case SymmetricLinesConstraint():
            return _symmetric_lines_residual(constraint, entities_by_id, input_points)
        case MidpointConstraint():
            return _midpoint_residual(constraint, entities_by_id)
        case CollinearConstraint():
            return _collinear_residual(constraint, entities_by_id)
        case _:  # pragma: no cover — the constraint union is closed
            assert_never(constraint)


def geometric_residuals(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    driving_values: dict[int, float],
    frames: dict[int, AngleFrame] | None = None,
) -> list[tuple[int, float]]:
    """``(constraint index, residual)`` for every constraint in the system.

    In input order — deterministic, like every other pass over a sketch
    (RESEARCH §9). Driven dimensions are absent (they constrain nothing).

    ``frames`` are the angle conventions (:func:`~geometry.sketch.angles.
    angle_frames`), derived from ``input_points`` when not supplied. The settle
    passes its cached map: this runs once per trial solve, and re-deriving there
    would put a per-constraint union-find on the one path whose cost must not
    grow with sketch size (SETTLE-PERF-1). Deriving is free for a sketch with no
    angle dimension, which is every sketch authored before they existed.
    """
    if frames is None:
        frames = angle_frames(constraints, input_points)
    entities_by_id = {entity.id: entity for entity in entities}
    residuals: list[tuple[int, float]] = []
    for index, constraint in enumerate(constraints):
        residual = constraint_residual(
            constraint,
            entities_by_id,
            input_points,
            driving_values.get(index),
            frames.get(index),
        )
        if residual is not None:
            residuals.append((index, residual))
    return residuals


def worst_residual(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    input_points: dict[tuple[str, str], _Vec],
    driving_values: dict[int, float],
    frames: dict[int, AngleFrame] | None = None,
) -> float:
    """The largest residual over every constraint AND every entity's own form.

    ``0.0`` for a sketch with nothing to check, which is the honest answer: an
    unconstrained sketch of well-formed entities violates nothing.
    """
    worst = 0.0
    for entity in entities:
        worst = max(worst, entity_residual(entity))
    for _, residual in geometric_residuals(
        constraints, entities, input_points, driving_values, frames
    ):
        worst = max(worst, residual)
    return worst
