"""Virtual sharps: a length dimension measured to a corner a fillet removed.

SKETCH-FILLET-KEEP-DIMS. A sketch fillet or chamfer trims its two legs back
from their shared corner. Before this, the web dropped the length dimension on
each trimmed leg (it measured a corner that no longer exists), which left the
rounded rectangle with free size: R5 -> R15 on an 80 x 50 rectangle grew it to
100 x 70, because nothing held the legs' lines apart any more.

SolidWorks and Fusion 360 keep the dimension and measure it to the *virtual
sharp*: the point where the two legs' infinite supports meet. A
:class:`~geometry.sketch.schemas.DistanceConstraint` carries that as
``start_sharp`` / ``end_sharp`` (the other leg's id), and this module is its
one definition, shared by the solver, the residual check and the readout.

**Solver encoding** (FreeCAD's, for its own virtual-sharp dimensions): each
sharp end is an auxiliary planegcs point held ON both lines by two
``point_on_line`` constraints, and the dimension is the plain point-to-point
distance between the two ends. Two new parameters, two independent equations
while the lines are not parallel, so the pair adds no DOF and removes none: the
only degree of freedom the dimension takes is the one its value pins, exactly
as the untrimmed length did. The auxiliary point is not an entity: nothing
reads it back, the settle never pins it, and it starts at the intersection of
the lines as the build sees them, so the build stays a function of the sketch.

**Measurement** is the closed-form intersection of the two solved lines, not
the auxiliary point, so the residual check is an independent opinion of the
geometry the payload ships. Parallel lines have no sharp; such a dimension is
unresolvable and the payload gate reports it conflicting rather than guessing.
"""

import math
from collections.abc import Container, Mapping, Sequence

from planegcs import ConstraintTag as GcsConstraintTag
from planegcs import LineId, PointId
from planegcs import Sketch as GcsSystem

from geometry.sketch.schemas import DistanceConstraint, SketchEntity, SketchLine
from geometry.sketch.solver import SketchDefinitionError

_Vec = tuple[float, float]


def line_intersection(a: SketchLine, b: SketchLine) -> _Vec | None:
    """Where the infinite supports of ``a`` and ``b`` meet, or ``None`` if parallel.

    Exact zero only: a cross product of ``0.0`` is the one value at which the
    formula divides by zero. Lines within a hair of parallel give a far-away
    sharp, which is the true answer for them.
    """
    p1, p2 = (a.start.x, a.start.y), (a.end.x, a.end.y)
    return intersect(p1, p2, (b.start.x, b.start.y), (b.end.x, b.end.y))


def intersect(p1: _Vec, p2: _Vec, q1: _Vec, q2: _Vec) -> _Vec | None:
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = q2[0] - q1[0], q2[1] - q1[1]
    cross = rx * sy - ry * sx
    if cross == 0.0:
        return None
    t = ((q1[0] - p1[0]) * sy - (q1[1] - p1[1]) * sx) / cross
    return (p1[0] + t * rx, p1[1] + t * ry)


def distance_ends(
    constraint: DistanceConstraint, entities_by_id: Mapping[str, SketchEntity]
) -> tuple[_Vec, _Vec] | None:
    """The two points a ``distance`` measures between, or ``None`` if unresolvable.

    Each end is the line's own endpoint, or the virtual sharp with the line the
    constraint names for that side. ``None`` when an id is not a line or a
    sharp's lines are parallel.
    """
    line = entities_by_id.get(constraint.entity)
    if not isinstance(line, SketchLine):
        return None
    ends: list[_Vec] = []
    for own, sharp in (
        (line.start, constraint.start_sharp),
        (line.end, constraint.end_sharp),
    ):
        if sharp is None:
            ends.append((own.x, own.y))
            continue
        other = entities_by_id.get(sharp)
        if not isinstance(other, SketchLine):
            return None
        at = line_intersection(line, other)
        if at is None:
            return None
        ends.append(at)
    return ends[0], ends[1]


def measured_length(
    constraint: DistanceConstraint, entities_by_id: Mapping[str, SketchEntity]
) -> float | None:
    """The length a ``distance`` reads on this geometry, or ``None``."""
    ends = distance_ends(constraint, entities_by_id)
    if ends is None:
        return None
    (x0, y0), (x1, y1) = ends
    return math.hypot(x1 - x0, y1 - y0)


#: ``constraint index -> {"start" | "end": auxiliary point}`` for every sharp.
SharpPoints = dict[int, dict[str, PointId]]


def _sharps(constraint: DistanceConstraint) -> tuple[tuple[str, str | None], ...]:
    return (("start", constraint.start_sharp), ("end", constraint.end_sharp))


def allocate_sharps(
    gcs: GcsSystem,
    constraints: Sequence[object],
    driving: Container[int],
    lines: Mapping[str, LineId],
    points: Mapping[tuple[str, str], PointId],
) -> SharpPoints:
    """Every driving distance's auxiliary sharp points, BEFORE any constraint.

    Called between the entities and the constraints so the auxiliary parameters
    sit right after the entities' own, ahead of every fixed parameter the
    constraints allocate. Measured: allocated later (beside their constraint),
    the free parameters straddled two of the binding's ``std::deque`` chunks,
    planegcs's subsystem orders its parameters by ADDRESS (a
    ``std::set<double*>``), and the chunks' order depends on the heap: the
    80 x 50 rounded rectangle at R15 solved to two different last bits within
    one process. Here they are contiguous with the entities' parameters, and
    in constraint order, so the build is the same system every time.
    """
    allocated: SharpPoints = {}
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, DistanceConstraint) or index not in driving:
            continue
        if constraint.entity not in lines:
            continue  # the solver's own kind check names it
        for name, sharp in _sharps(constraint):
            if sharp is None:
                continue
            if sharp not in lines:
                raise SketchDefinitionError(
                    "A 'distance' virtual sharp is where two lines meet; "
                    f"{sharp!r} is not a known line"
                )
            ends = [(constraint.entity, "start"), (constraint.entity, "end")]
            own = [gcs.get_point(points[key]) for key in ends]
            other = [gcs.get_point(points[(sharp, p)]) for p in ("start", "end")]
            guess = intersect(own[0], own[1], other[0], other[1])
            at = guess if guess is not None else own[0 if name == "start" else 1]
            allocated.setdefault(index, {})[name] = gcs.add_point(at[0], at[1])
    return allocated


def add_distance(
    gcs: GcsSystem,
    constraint: DistanceConstraint,
    lines: Mapping[str, LineId],
    points: Mapping[tuple[str, str], PointId],
    value_mm: float,
    sharps: Mapping[str, PointId],
) -> list[GcsConstraintTag]:
    """The planegcs tags for one driving ``distance``, either form.

    Without sharps this is the single ``p2p_distance`` it has always been (same
    call, same order, so a stored sketch builds the identical system). With a
    sharp, its two ``point_on_line`` tags come first; ``sharps`` holds the
    auxiliary points :func:`allocate_sharps` made for this constraint.
    """
    tags: list[GcsConstraintTag] = []
    ends: list[PointId] = []
    for name, sharp in _sharps(constraint):
        if sharp is None:
            ends.append(points[(constraint.entity, name)])
            continue
        aux = sharps[name]
        tags.append(gcs.point_on_line(aux, lines[constraint.entity]))
        tags.append(gcs.point_on_line(aux, lines[sharp]))
        ends.append(aux)
    tags.append(gcs.set_p2p_distance(ends[0], ends[1], value_mm))
    return tags
