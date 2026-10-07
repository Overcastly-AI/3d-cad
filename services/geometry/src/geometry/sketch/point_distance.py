"""Point-to-point and point-to-line distance dimensions (SKETCH-POINT-DISTANCE).

One definition of what :class:`~geometry.sketch.schemas.PointDistanceConstraint`
and :class:`~geometry.sketch.schemas.PointLineDistanceConstraint` measure,
shared by the solver encoding, the residual check and the readout, the way
:mod:`geometry.sketch.virtual_sharp` is for a line's length.

**Point to point** is Fusion 360's Sketch Dimension on two points. ``aligned``
is planegcs's ``P2PDistance``. ``horizontal`` and ``vertical`` are its
``Difference`` on the two x (or y) parameters, which is how FreeCAD encodes its
own DistanceX and DistanceY. ``Difference`` is signed: the sign is read from the
geometry as submitted (:func:`sense`), so the second point stays on the side of
the first it was drawn on.

**Point to line** is the perpendicular distance to the line's infinite support.
planegcs's ``P2LDistance`` is UNSIGNED (``|area| / length - d``): it is satisfied
with the point on either side of the line. Measured: a rim edge moved from
x = 120 to x = 100 takes a corner drawn at x = 119 to x = 101, 1 mm OUTSIDE the
rim, with the typed 1 mm reading true (``test_sketch_point_distance``).

So the side is held explicitly, with native constraints only, the way the
virtual sharp holds its corner. An auxiliary point ``Q`` rides on a rigid
"stick" from ``P``: ``P2PDistance(Q, P) = value``, and the stick is held at a
SIGNED right angle to the line (``L2LAngle`` at ``side * pi/2``), so
``Q = P - side * value * n`` (``n`` the line's left unit normal). Then
``PointOnLine(Q, line)``, whose error is planegcs's SIGNED offset of ``Q``,
reads ``offset(P) - side * value``: exactly the signed point-to-line distance.
Two new parameters and three equations, so the dimension takes exactly the one
degree of freedom it pins.

Two cheaper-looking encodings were measured and rejected. ``P2LDistance`` alone
flips (above). ``P2LDistance`` plus ``Q`` as the FOOT of the perpendicular (on
the line, ``Q -> P`` at the signed right angle) cannot flip, but it cannot cross
either: the moment a solve step carries the line past the point, ``Q -> P``
points the wrong way, the angle error sits at ``pi`` where ``atan2`` wraps, and
DogLeg stops there. The same rim edit read ``diverged``. The stick has no such
seam: the angle constrains only the stick's direction against the line's, and
the stick never turns over, wherever the line goes relative to ``P``.

``Q`` starts at ``P - side * value * n``, so the stick starts at its target
length and direction and is never zero-length, even when the stored point lies
on the line. That holds only because the wire refuses a value of 0
(``value_mm`` is ``gt=0``): at 0 the stick, and the angle on it, would vanish.
It is not an entity: nothing reads it back and the settle never pins it.

**The side** is a function of the submitted sketch alone, like an angle's frame
(:mod:`geometry.sketch.angles`): the sign of the cross product of the line's
``start -> end`` and ``start -> point``, ``+1`` (left) when it is exactly zero.
"""

import math
from collections.abc import Callable, Container, Mapping, Sequence

from loft_wire.sketch import spline_fit_index
from planegcs import ConstraintTag as GcsConstraintTag
from planegcs import LineId, PointId
from planegcs import Sketch as GcsSystem

from geometry.sketch.schemas import (
    DimensionPointRef,
    PointDistanceConstraint,
    PointLineDistanceConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSpline,
)
from geometry.sketch.solver import SketchDefinitionError
from geometry.sketch.virtual_sharp import intersect

_Vec = tuple[float, float]

#: ``(entity id, point name) -> coordinate``, or ``None`` if the entity has no
#: such point.
PointLookup = Callable[[str, str], _Vec | None]
#: ``entity id -> (start, end)`` of a LINE, or ``None`` if it is not one.
LineLookup = Callable[[str], tuple[_Vec, _Vec] | None]

#: The point dimensions, the kinds this module defines.
PointDimension = PointDistanceConstraint | PointLineDistanceConstraint


def named_point(entity: SketchEntity | None, name: str) -> _Vec | None:
    """The coordinate of ``entity``'s point ``name``, or ``None`` if it has none."""
    match entity:
        case SketchPoint() if name == "position":
            return (entity.position.x, entity.position.y)
        case SketchLine() | SketchArc() if name in ("start", "end"):
            at = entity.start if name == "start" else entity.end
            return (at.x, at.y)
        case SketchCircle() | SketchArc() if name == "center":
            return (entity.center.x, entity.center.y)
        case SketchSpline():
            index = spline_fit_index(name)
            if index is None or not 0 <= index < len(entity.points):
                return None
            return (entity.points[index].x, entity.points[index].y)
        case _:
            return None


def entity_lookups(
    entities_by_id: Mapping[str, SketchEntity],
) -> tuple[PointLookup, LineLookup]:
    """Point and line lookups over DTO entities (solved, or as submitted)."""

    def point_at(entity: str, name: str) -> _Vec | None:
        return named_point(entities_by_id.get(entity), name)

    def line_at(entity: str) -> tuple[_Vec, _Vec] | None:
        line = entities_by_id.get(entity)
        if not isinstance(line, SketchLine):
            return None
        return ((line.start.x, line.start.y), (line.end.x, line.end.y))

    return point_at, line_at


def point_table_lookups(
    points: Mapping[tuple[str, str], _Vec],
) -> tuple[PointLookup, LineLookup]:
    """The same lookups over a ``(entity, point) -> coordinate`` table.

    The residual check is handed the SUBMITTED sketch as such a table. It does
    not know entity kinds, so an arc's ends would read as a line's here; the
    solver build refuses a non-line wherever a line is required, and a residual
    is only ever asked of a sketch that built.
    """

    def point_at(entity: str, name: str) -> _Vec | None:
        return points.get((entity, name))

    def line_at(entity: str) -> tuple[_Vec, _Vec] | None:
        start, end = points.get((entity, "start")), points.get((entity, "end"))
        return None if start is None or end is None else (start, end)

    return point_at, line_at


def operands(constraint: PointDimension) -> tuple[tuple[str, DimensionPointRef], ...]:
    """``(slot, ref)`` for each point operand, in a fixed order."""
    if isinstance(constraint, PointDistanceConstraint):
        return (("a", constraint.a), ("b", constraint.b))
    return (("point", constraint.point),)


def operand(
    ref: DimensionPointRef,
    point_at: PointLookup,
    line_at: LineLookup,
    *,
    sharp_fallback: bool = False,
) -> _Vec | None:
    """Where a point operand is: the named point, or the virtual sharp it names.

    ``None`` when a reference does not resolve, or a sharp's two lines are
    parallel (they meet nowhere). With ``sharp_fallback`` a parallel pair reads
    the named point instead, as a driven ``distance`` reads its own end: the
    solve already reports such a sharp conflicting, and the readout must not
    turn that into ``sketch_invalid``.
    """
    if ref.sharp is None:
        return point_at(ref.entity, ref.point)
    own, other = line_at(ref.entity), line_at(ref.sharp)
    if own is None or other is None:
        return None
    at = intersect(own[0], own[1], other[0], other[1])
    if at is None and sharp_fallback:
        return point_at(ref.entity, ref.point)
    return at


def signed_line_offset(point: _Vec, start: _Vec, end: _Vec) -> float | None:
    """Signed perpendicular distance from ``point`` to the line (mm); + is left.

    planegcs's own ``PointOnLine`` error, so the two opinions share a scale.
    ``None`` for a degenerate line, which defines no distance.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return None
    return (dx * (point[1] - start[1]) - dy * (point[0] - start[0])) / length


def sense(value: float) -> float:
    """``+1.0`` or ``-1.0``: the side a signed quantity is on, ``+1`` at zero."""
    return -1.0 if value < 0.0 else 1.0


def signed_value(
    constraint: PointDimension,
    point_at: PointLookup,
    line_at: LineLookup,
    *,
    sharp_fallback: bool = False,
) -> float | None:
    """The quantity the solver holds, with its sign; ``None`` if unresolvable.

    ``aligned``: the distance. ``horizontal``/``vertical``: ``b - a`` along X/Y.
    Point to line: the signed perpendicular offset (+ is left of the line).
    """
    if isinstance(constraint, PointDistanceConstraint):
        a = operand(constraint.a, point_at, line_at, sharp_fallback=sharp_fallback)
        b = operand(constraint.b, point_at, line_at, sharp_fallback=sharp_fallback)
        if a is None or b is None:
            return None
        match constraint.direction:
            case "aligned":
                return math.hypot(b[0] - a[0], b[1] - a[1])
            case "horizontal":
                return b[0] - a[0]
            case "vertical":
                return b[1] - a[1]
    point = operand(constraint.point, point_at, line_at, sharp_fallback=sharp_fallback)
    line = line_at(constraint.line)
    if point is None or line is None:
        return None
    return signed_line_offset(point, line[0], line[1])


def measured(
    constraint: PointDimension,
    point_at: PointLookup,
    line_at: LineLookup,
    *,
    sharp_fallback: bool = False,
) -> float | None:
    """The unsigned value the dimension reads on this geometry, or ``None``."""
    value = signed_value(constraint, point_at, line_at, sharp_fallback=sharp_fallback)
    return None if value is None else abs(value)


def residual(
    constraint: PointDimension,
    solved: tuple[PointLookup, LineLookup],
    submitted: tuple[PointLookup, LineLookup],
    requested: float,
) -> float | None:
    """``|held - target|`` in mm, the side taken from the SUBMITTED geometry.

    For the signed kinds the target is ``side * requested``, so a point that
    crossed to the other side reads ``2 * requested`` out, never ``0``.
    ``None`` when a reference does not resolve.
    """
    held = signed_value(constraint, *solved)
    if held is None:
        return None
    if _is_aligned(constraint):
        return abs(held - requested)
    drawn = signed_value(constraint, *submitted)
    if drawn is None:
        return None
    return abs(held - sense(drawn) * requested)


def _is_aligned(constraint: PointDimension) -> bool:
    return (
        isinstance(constraint, PointDistanceConstraint)
        and constraint.direction == "aligned"
    )


# -- solver encoding ---------------------------------------------------------

#: ``constraint index -> {slot: auxiliary point}``. Slots are the operand names
#: (``"a"``, ``"b"``, ``"point"``) for virtual sharps, and ``"tip"``.
AuxPoints = dict[int, dict[str, PointId]]


def allocate_aux(
    gcs: GcsSystem,
    constraints: Sequence[SketchConstraint],
    driving: Mapping[int, float],
    lines: Mapping[str, LineId],
    points: Mapping[tuple[str, str], PointId],
    sides: Mapping[int, float],
) -> AuxPoints:
    """Every driving point dimension's auxiliary points, BEFORE any constraint.

    Same placement rule as :func:`~geometry.sketch.virtual_sharp.allocate_sharps`
    and called right after it, so the free parameters stay contiguous and in
    constraint order (SKETCH-SOLVE-HEAP-ORDER). Starting guesses come from the
    build's own start pose (``gcs.get_point``), never from anything outside the
    sketch.
    """
    allocated: AuxPoints = {}

    def line_at(entity: str) -> tuple[_Vec, _Vec] | None:
        if entity not in lines:
            return None
        return (
            gcs.get_point(points[(entity, "start")]),
            gcs.get_point(points[(entity, "end")]),
        )

    def point_at(entity: str, name: str) -> _Vec | None:
        pid = points.get((entity, name))
        return None if pid is None else gcs.get_point(pid)

    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, PointDimension) or index not in driving:
            continue
        aux: dict[str, PointId] = {}
        at: dict[str, _Vec] = {}
        for slot, ref in operands(constraint):
            if ref.sharp is None:
                where = point_at(ref.entity, ref.point)
                if where is not None:
                    at[slot] = where
                continue
            own, other = line_at(ref.entity), line_at(ref.sharp)
            if own is None or other is None:
                raise SketchDefinitionError(
                    "A virtual sharp is where two lines meet; "
                    f"{ref.entity!r} and {ref.sharp!r} are not both known lines"
                )
            guess = intersect(own[0], own[1], other[0], other[1])
            own_end = own[0 if ref.point == "start" else 1]
            where = guess if guess is not None else own_end
            aux[slot] = gcs.add_point(where[0], where[1])
            at[slot] = where
        if isinstance(constraint, PointLineDistanceConstraint):
            line = line_at(constraint.line)
            point = at.get("point")
            if line is not None and point is not None:
                tip = _tip_guess(point, line, sides.get(index, 1.0) * driving[index])
                aux["tip"] = gcs.add_point(tip[0], tip[1])
        if aux:
            allocated[index] = aux
    return allocated


def _tip_guess(point: _Vec, line: tuple[_Vec, _Vec], offset: float) -> _Vec:
    """``point - offset * n``: where the stick's tip starts (module docstring)."""
    (sx, sy), (ex, ey) = line
    length = math.hypot(ex - sx, ey - sy)
    if length == 0.0:
        return point
    nx, ny = -(ey - sy) / length, (ex - sx) / length
    return (point[0] - offset * nx, point[1] - offset * ny)


def add_point_dimension(
    gcs: GcsSystem,
    constraint: PointDimension,
    resolve: Callable[[DimensionPointRef], PointId],
    resolve_line: Callable[[str], LineId],
    aux: Mapping[str, PointId],
    value_mm: float,
    side: float,
) -> list[GcsConstraintTag]:
    """The planegcs tags for one driving point dimension.

    ``resolve`` maps a plain point operand to its solver point; a virtual sharp
    operand is its auxiliary point from :func:`allocate_aux`, held on both lines
    exactly as :func:`~geometry.sketch.virtual_sharp.add_distance` holds one.
    ``side`` is ``+-1`` from the submitted geometry (:func:`sense`).
    """
    tags: list[GcsConstraintTag] = []
    ends: dict[str, PointId] = {}
    for slot, ref in operands(constraint):
        if ref.sharp is None:
            ends[slot] = resolve(ref)
            continue
        ends[slot] = aux[slot]
        tags.append(gcs.point_on_line(aux[slot], resolve_line(ref.entity)))
        tags.append(gcs.point_on_line(aux[slot], resolve_line(ref.sharp)))
    if isinstance(constraint, PointDistanceConstraint):
        a, b = ends["a"], ends["b"]
        if constraint.direction == "aligned":
            tags.append(gcs.set_p2p_distance(a, b, value_mm))
            return tags
        axis = 0 if constraint.direction == "horizontal" else 1
        a_param = gcs.get_point_param_ids(a)[axis]
        b_param = gcs.get_point_param_ids(b)[axis]
        offset = gcs.add_param(side * value_mm, fixed=True)
        tags.append(gcs.difference(a_param, b_param, offset))
        return tags
    line = resolve_line(constraint.line)
    point = ends["point"]
    tip = aux.get("tip")
    if tip is None:  # pragma: no cover — allocate_aux made one for every line
        raise SketchDefinitionError(
            f"Constraint 'point_line_distance' requires a line; {constraint.line!r}"
        )
    # The stick (module docstring): its length, its signed right angle to the
    # line, and its tip on the line.
    tags.append(gcs.set_p2p_distance(tip, point, value_mm))
    tags.append(gcs.set_l2l_angle(line, gcs.add_line(tip, point), side * math.pi / 2))
    tags.append(gcs.point_on_line(tip, line))
    return tags


def submitted_sides(
    constraints: Sequence[SketchConstraint],
    driving: Container[int],
    point_at: PointLookup,
    line_at: LineLookup,
) -> dict[int, float]:
    """``constraint index -> +-1`` for every driving signed point dimension.

    Read from the SUBMITTED sketch once per build, like the angle frames: the
    side records what the author drew, and re-reading it mid-settle would let
    it follow the solver instead.
    """
    sides: dict[int, float] = {}
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, PointDimension) or index not in driving:
            continue
        if _is_aligned(constraint):
            continue
        drawn = signed_value(constraint, point_at, line_at)
        sides[index] = 1.0 if drawn is None else sense(drawn)
    return sides
