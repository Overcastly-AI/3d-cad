"""The angle-dimension convention, in ONE place, because two derivations use it.

An :class:`~geometry.sketch.schemas.AngleConstraint` is authored as a single
unsigned number in (0, 180), and turning that number into something a solver can
hold takes two decisions the DTO deliberately does not carry:

1. **Which of the two supplementary angles the user means.** Two lines that meet
   at a corner subtend an interior angle and its supplement; a profile traversed
   in loop order has the *directions* of two adjacent edges differing by the
   EXTERIOR angle, so taking planegcs's raw line-to-line angle would display 150
   where the user sees 30. The fix is to orient each line away from the corner
   the two share, which is the interior angle every CAD tool shows. The corner is
   found from the sketch's ``coincident`` constraints — symbolically, never by
   comparing coordinates against an epsilon (CLAUDE.md forbids ad-hoc epsilons,
   and a proximity test would silently change a constraint's MEANING as the
   geometry moved).
2. **Which side of ``a`` the line ``b`` sits on.** planegcs's angle is signed;
   the DTO's is not. The sign is taken from the geometry AS DRAWN, so typing a
   new number resizes the angle the author already has instead of reflecting the
   profile through ``a``.

Both decisions are captured once, in an :class:`AngleFrame` derived from the
constraint list and the SUBMITTED coordinates — a function of the sketch alone,
so it is deterministic (RESEARCH §9) and identical for every consumer.

**Why this is a module and not two similar code paths.** The solver wiring
(:mod:`geometry.sketch.planegcs_solver`) and the independent geometric residual
(:mod:`geometry.sketch.residual`) must agree EXACTLY about which angle was
asked for: the residual exists to be a second opinion on the solved geometry,
and a second opinion that measured a different angle than the one requested
would report a violation on a correct solve (or, worse, silence on a wrong one).
Sharing the DATA and the code path is what makes their disagreement meaningful.
"""

import math
from dataclasses import dataclass

from geometry.sketch.schemas import (
    AngleConstraint,
    CoincidentConstraint,
    ConcentricConstraint,
    SketchConstraint,
)

_Vec = tuple[float, float]
_PointKey = tuple[str, str]

#: The endpoint pairs a shared corner can be made of, in the fixed order they
#: are tested. Deterministic by construction: two lines constrained coincident at
#: more than one endpoint are degenerate, and the first match wins rather than an
#: arbitrary one (RESEARCH §9).
_CORNER_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("start", "start"),
    ("start", "end"),
    ("end", "start"),
    ("end", "end"),
)


def coincidence_classes(
    constraints: list[SketchConstraint],
) -> dict[_PointKey, _PointKey]:
    """``(entity id, point name)`` → the representative of its coincidence class.

    Two points joined by ``coincident`` (or two centres joined by ``concentric``,
    which :meth:`~geometry.sketch.planegcs_solver._GcsBuild._add_concentric`
    translates to exactly that) are ONE location in every solution the caller's
    constraints admit.

    Two callers, for two different reasons. The settle uses it to reason about
    pins it has already tried: pinning either member at the same target is the
    same demand, so a refusal for one is a refusal for both
    (:meth:`~geometry.sketch.planegcs_solver._GcsBuild._known_infeasible`); in a
    closed outline every corner is shared by two entities, so that halves the
    questions the settle has to put to the solver. :func:`angle_frames` uses it to
    find the corner an angle dimension is measured at.

    Union-find, merged in input constraint order, and the representative is the
    smallest member by ``(entity id, point name)`` — so the map is a function of
    the sketch alone, never of iteration order (RESEARCH §9).
    """
    parent: dict[_PointKey, _PointKey] = {}

    def find(key: _PointKey) -> _PointKey:
        root = parent.setdefault(key, key)
        while root != parent[root]:
            root = parent[root]
        while parent[key] != root:  # path compression
            parent[key], key = root, parent[key]
        return root

    def union(a: _PointKey, b: _PointKey) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            low, high = sorted((root_a, root_b))
            parent[high] = low

    for constraint in constraints:  # input order — deterministic (RESEARCH §9)
        match constraint:
            case CoincidentConstraint():
                union(
                    (constraint.a.entity, constraint.a.point),
                    (constraint.b.entity, constraint.b.point),
                )
            case ConcentricConstraint():
                union((constraint.a, "center"), (constraint.b, "center"))
            case _:
                pass
    return {key: find(key) for key in parent}


@dataclass(frozen=True)
class AngleFrame:
    """How one angle dimension's unsigned number maps onto directed geometry.

    ``reversed_a``/``reversed_b`` orient each line AWAY from the corner the two
    share (``True`` = use ``end -> start``); ``sense`` is ``+1.0`` when the
    author drew ``b`` counter-clockwise of ``a`` and ``-1.0`` when clockwise.
    """

    reversed_a: bool
    reversed_b: bool
    sense: float


def _direction(
    entity_id: str, points: dict[_PointKey, _Vec], flip: bool
) -> _Vec | None:
    """A line's direction vector from a point table, reversed when ``flip``.

    ``None`` when the table has no ``start``/``end`` for the id — which is every
    non-line entity, so a malformed angle constraint resolves to no frame rather
    than to a wrong one.
    """
    start = points.get((entity_id, "start"))
    end = points.get((entity_id, "end"))
    if start is None or end is None:
        return None
    dx, dy = end[0] - start[0], end[1] - start[1]
    return (-dx, -dy) if flip else (dx, dy)


def directed_angle(a: _Vec, b: _Vec) -> float:
    """Signed angle from ``a`` to ``b`` in radians, in ``(-pi, pi]``.

    The same quantity planegcs's ``ConstraintL2LAngle`` drives (its error is this
    difference wrapped the same way), so a residual built on it shares that
    constraint's scale and needs no conversion.
    """
    return math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])


def _frame_for(
    constraint: AngleConstraint,
    points: dict[_PointKey, _Vec],
    classes: dict[_PointKey, _PointKey],
) -> AngleFrame | None:
    reversed_a = reversed_b = False
    for a_point, b_point in _CORNER_CANDIDATES:
        a_class = classes.get((constraint.a, a_point))
        if a_class is not None and a_class == classes.get((constraint.b, b_point)):
            # Orient away from the corner: if the corner IS the line's end, the
            # direction leaving it is end -> start.
            reversed_a, reversed_b = a_point == "end", b_point == "end"
            break
    a_dir = _direction(constraint.a, points, reversed_a)
    b_dir = _direction(constraint.b, points, reversed_b)
    if a_dir is None or b_dir is None:
        return None
    drawn = directed_angle(a_dir, b_dir)
    # A degenerate or exactly-parallel input has no side; +1 keeps the frame a
    # total function of the sketch (the constraint is unsatisfiable-as-drawn
    # either way, and the solver's own diagnosis is what reports that).
    return AngleFrame(reversed_a, reversed_b, -1.0 if drawn < 0.0 else 1.0)


def angle_frames(
    constraints: list[SketchConstraint], points: dict[_PointKey, _Vec]
) -> dict[int, AngleFrame]:
    """``constraint index -> AngleFrame`` for every resolvable angle dimension.

    ``points`` are the SUBMITTED coordinates: the frame records the angle the
    author drew, so it must not be re-derived from a solve in progress (that
    would let the sign follow the solver instead of the intent).

    Returns ``{}`` — without building the coincidence classes at all — for a
    sketch with no angle dimension, which is every sketch authored before this
    constraint existed. That keeps this off the settle's hot path entirely
    (:data:`~geometry.sketch.planegcs_solver.SETTLE_WORK_UNITS`): a residual
    sweep runs once per trial solve, and rebuilding a union-find per trial would
    be a per-entity cost on the one path that must not grow.
    """
    indexed = [
        (index, constraint)
        for index, constraint in enumerate(constraints)
        if isinstance(constraint, AngleConstraint)
    ]
    if not indexed:
        return {}
    classes = coincidence_classes(constraints)
    frames: dict[int, AngleFrame] = {}
    for index, constraint in indexed:
        frame = _frame_for(constraint, points, classes)
        if frame is not None:
            frames[index] = frame
    return frames


def solver_target_rad(frame: AngleFrame, value_deg: float) -> float:
    """The signed angle to hand planegcs, in the LINES' OWN (unreversed) sense.

    planegcs constrains ``angle(b) - angle(a)`` for the lines' authored
    ``start -> end`` directions; there is no way to hand it a reversed line. But
    reversing a direction adds exactly ``pi`` to its angle, so an angle demanded
    between the oriented directions is the same demand shifted by ``pi`` per
    reversal::

        theta_oriented = theta_raw + pi * (reversed_b - reversed_a)

    which rearranges to the expression below. No wrapping is needed: the
    constraint's error is an ``atan2`` and so is periodic in ``2*pi``.
    """
    return math.radians(frame.sense * value_deg) + math.pi * (
        float(frame.reversed_a) - float(frame.reversed_b)
    )


def oriented_angle_rad(frame: AngleFrame, a_dir: _Vec, b_dir: _Vec) -> float:
    """Signed angle between two AUTHORED directions, re-read in ``frame``'s sense."""
    if frame.reversed_a:
        a_dir = (-a_dir[0], -a_dir[1])
    if frame.reversed_b:
        b_dir = (-b_dir[0], -b_dir[1])
    return directed_angle(a_dir, b_dir)


def measured_angle_deg(frame: AngleFrame, a_dir: _Vec, b_dir: _Vec) -> float:
    """The angle to DISPLAY for these directions, in degrees within ``[0, 180]``.

    The magnitude of :func:`oriented_angle_rad`: the readout is unsigned exactly
    as the authored ``value_deg`` is, so a driven angle dimension reads back the
    same number a driving one would have been given for the same geometry.
    """
    return abs(math.degrees(oriented_angle_rad(frame, a_dir, b_dir)))
