"""A building outline read from a sketch, with no solver (BUILDING-OUTLINE).

One closed sketch drives a house's walls and floor, as Chief Architect builds
floors and roofs from the exterior wall loop and Revit draws walls on picked
lines. The outline is a closed loop of sketch lines on the framing's outside
face, dimensioned like any sketch. A plugin runs in documents, which has no
sketch solver (only geometry imports planegcs, RESEARCH §2), so this module
reads the loop's corners from the sketch's CONSTRAINTS in closed form:

* every non-construction entity is a line, and the lines close ONE loop
  (their ends joined by ``coincident`` constraints, read symbolically, never
  by distance);
* every loop line is horizontal or vertical, by a ``horizontal`` or
  ``vertical`` constraint, or by ``parallel``, ``perpendicular`` or
  ``collinear`` to such a line;
* then the corners are the unique solution of the LINEAR system those
  constraints make: horizontal and vertical lines, ``fixed`` points (the
  sketch origin is one), line lengths, horizontal and vertical point
  distances, point-to-line distances, ``equal``, ``collinear``, ``midpoint``
  and ``symmetric`` about a horizontal or vertical line. A length's sign (which
  way the line runs) is the drawn geometry's, as the solver keeps it.

It is solved in exact rationals of the stored numbers. The loop must be FULLY
DEFINED by those constraints (every corner determined), or the outline is
refused: a solver keeps an under-defined sketch near where it was drawn, which
this reader cannot reproduce, and a wall that does not stand on the sketch the
user sees is wrong geometry. Constraints of other kinds are not read; with the
loop fully defined they can only agree with it or make the sketch itself fail
to solve, which the sketch reports. The solved sketch and this reading agree
to the solver's convergence (~1e-10 mm): the sketch is only drawn, the walls
are built from these numbers.

Dimension values are read from the stored constraints, which documents keeps
resolved (a dimension's formula and the part's parameters, RESEARCH §20), so
editing one dimension re-reads the outline in the same rebuild.

**Order.** The loop is walked CLOCKWISE seen from above (the way walls are
drawn, RESEARCH §23 "Placement": the framing to the right of each line),
starting with the sketch's first loop line. Coordinates are inches, rounded to
1e-9 in as every plugin input.
"""

import math
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from loft_wire.features import (
    AuthoredEnvelope,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    FeatureRef,
    SketchFeature,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import PLUGIN_INPUT_INVALID, PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import (
    CoincidentConstraint,
    CollinearConstraint,
    DimensionConstraint,
    DimensionPointRef,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    MidpointConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    PointDistanceConstraint,
    PointLineDistanceConstraint,
    SketchLine,
    SketchPoint,
    SymmetricConstraint,
    VerticalConstraint,
)

from loft_plugins.api import PluginError

Vec2 = tuple[float, float]
Dir = tuple[int, int]
Axis = Literal["h", "v"]
Facing = Literal["front", "back", "left", "right"]

_DIGITS = 9
#: A redundant constraint may disagree with the others by this much (mm) and
#: still count as the same equation (two dimensions typed to one value).
_REDUNDANT_MM = Fraction(1, 1_000_000)
#: A line id becomes the first segment of its walls' member names.
_NAMEABLE = "abcdefghijklmnopqrstuvwxyz"
#: Most lines one outline may have (a roof picks at most 32 slope walls).
MAX_OUTLINE_LINES = 32


def unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


@dataclass(frozen=True)
class Segment:
    """One line of the outline, walked clockwise: its sketch id and its ends
    (inches, world plan: an outline sketch is on XY)."""

    line_id: str
    start: Vec2
    end: Vec2

    @property
    def direction(self) -> Dir:
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        return (
            (1 if dx > 0 else -1 if dx < 0 else 0),
            (1 if dy > 0 else -1 if dy < 0 else 0),
        )

    @property
    def length(self) -> float:
        return round(math.dist(self.start, self.end), _DIGITS)

    @property
    def direction_deg(self) -> float:
        return {(1, 0): 0.0, (0, 1): 90.0, (-1, 0): 180.0, (0, -1): 270.0}[
            self.direction
        ]

    @property
    def facing(self) -> Facing:
        """Which way the wall on this line faces in the world: its outward
        normal, to the left of the clockwise direction (front is -Y, as the
        roof names its planes)."""
        dx, dy = self.direction
        facings: dict[Dir, Facing] = {
            (0, -1): "front",
            (0, 1): "back",
            (-1, 0): "left",
            (1, 0): "right",
        }
        return facings[(-dy, dx)]


@dataclass(frozen=True)
class Outline:
    """The loop, clockwise from the sketch's first loop line."""

    segments: tuple[Segment, ...]

    def index(self, line_id: str, input_name: str) -> int:
        for k, segment in enumerate(self.segments):
            if segment.line_id == line_id:
                return k
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"{line_id!r} is not a line of the outline.",
            input=input_name,
        )

    def convex_at_start(self, k: int) -> bool:
        """Whether the corner at segment *k*'s start is convex (an outside
        corner): walking clockwise, the loop turns right there."""
        a = self.segments[k - 1].direction
        b = self.segments[k].direction
        return a[0] * b[1] - a[1] * b[0] < 0

    def convex_at_end(self, k: int) -> bool:
        return self.convex_at_start((k + 1) % len(self.segments))

    @property
    def ccw_corners(self) -> tuple[Vec2, ...]:
        """The corners counter-clockwise (a roof's footprint order)."""
        return tuple(segment.start for segment in reversed(self.segments))

    @property
    def is_rectangle(self) -> bool:
        return len(self.segments) == 4 and all(
            self.convex_at_start(k) for k in range(4)
        )

    def label(self, k: int) -> str:
        """``the front wall (e1)``, for messages."""
        segment = self.segments[k]
        return f"the {segment.facing} wall ({segment.line_id})"


# --- Reading the sketch -------------------------------------------------------------


def outline_sketch(
    ref: FeatureRef,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    input_name: str,
) -> SketchFeature:
    """The sketch *ref* names, checked to lie in plan (on ``XY`` or an
    unflipped offset of it, where sketch x and y are world X and Y)."""
    sketch = earlier.get(ref.feature_id)
    if not isinstance(sketch, SketchFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Outline: pick an earlier sketch.",
            input=input_name,
        )
    plane = sketch.params.plane
    in_plan = isinstance(plane, DatumPlaneRef) and plane.plane == "XY"
    if isinstance(plane, FeatureRef):
        datum = earlier.get(plane.feature_id)
        in_plan = (
            isinstance(datum, DatumFeature)
            and isinstance(datum.params, DatumOffsetParams)
            and datum.params.base == "XY"
            and not datum.params.flip
        )
    if not in_plan:
        raise unsupported(
            "Outline: draw the outline in plan, on the XY plane (or a plane "
            "offset from it).",
            input_name,
        )
    return sketch


PointKey = tuple[str, str]


class _Points:
    """Union-find over named points: ``coincident`` merges them."""

    def __init__(self) -> None:
        self._parent: dict[PointKey, PointKey] = {}

    def add(self, key: PointKey) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: PointKey) -> PointKey:
        parent = self._parent[key]
        if parent == key:
            return key
        root = self.find(parent)
        self._parent[key] = root
        return root

    def union(self, a: PointKey, b: PointKey) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)

    def __contains__(self, key: PointKey) -> bool:
        return key in self._parent


class _System:
    """A linear system over named point coordinates, kept in reduced
    row-echelon form as equations arrive (exact rationals)."""

    def __init__(self) -> None:
        #: pivot variable -> (coefficients without the pivot, rhs): the
        #: pivot equals rhs - sum(coefficients * variables).
        self._rows: dict[
            tuple[PointKey, int], tuple[dict[tuple[PointKey, int], Fraction], Fraction]
        ] = {}
        self.conflict = False

    def add(
        self, coeffs: Mapping[tuple[PointKey, int], Fraction], rhs: Fraction
    ) -> None:
        row = {k: v for k, v in coeffs.items() if v != 0}
        value = rhs
        # Substitute every pivot the equation names.
        changed = True
        while changed:
            changed = False
            for var in sorted(row):
                if var in self._rows:
                    coef = row.pop(var)
                    others, pivot_rhs = self._rows[var]
                    value -= coef * pivot_rhs
                    for other, c in others.items():
                        row[other] = row.get(other, Fraction(0)) - coef * c
                        if row[other] == 0:
                            del row[other]
                    changed = True
                    break
        if not row:
            if abs(value) > _REDUNDANT_MM:
                self.conflict = True
            return
        pivot = min(row)
        scale = row.pop(pivot)
        others = {k: v / scale for k, v in row.items()}
        pivot_rhs = value / scale
        # Eliminate the new pivot from every existing row.
        for var, (existing, existing_rhs) in list(self._rows.items()):
            coef = existing.get(pivot)
            if coef is None:
                continue
            updated = dict(existing)
            del updated[pivot]
            for other, c in others.items():
                updated[other] = updated.get(other, Fraction(0)) - coef * c
                if updated[other] == 0:
                    del updated[other]
            self._rows[var] = (updated, existing_rhs - coef * pivot_rhs)
        self._rows[pivot] = (others, pivot_rhs)

    def value(self, var: tuple[PointKey, int]) -> Fraction | None:
        row = self._rows.get(var)
        if row is None or row[0]:
            return None
        return row[1]


def _f(value: float) -> Fraction:
    return Fraction(value)


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def read_outline(sketch: SketchFeature, input_name: str = "outline") -> Outline:
    """The loop of *sketch*'s lines, clockwise (module docstring), or a
    :class:`PluginError` on *input_name* saying what to add or change."""

    def refuse(message: str) -> PluginError:
        return unsupported(f"Outline: {message}", input_name)

    entities = sketch.params.entities
    lines = {e.id: e for e in entities if isinstance(e, SketchLine)}
    points = {e.id: e for e in entities if isinstance(e, SketchPoint)}
    loop_ids = [
        e.id for e in entities if isinstance(e, SketchLine) and not e.construction
    ]
    for e in entities:
        if not e.construction and not isinstance(e, SketchLine):
            raise refuse(
                f"{e.id} is a {e.kind}; the outline is a loop of straight lines "
                "(make other geometry construction)."
            )
    if len(loop_ids) < 4:
        raise refuse("draw a closed loop of at least four lines.")
    if len(loop_ids) > MAX_OUTLINE_LINES:
        raise refuse(f"at most {MAX_OUTLINE_LINES} lines.")

    def stored(ref: EntityPointRef) -> tuple[float, float] | None:
        entity = lines.get(ref.entity) or points.get(ref.entity)
        if isinstance(entity, SketchLine) and ref.point in ("start", "end"):
            at = entity.start if ref.point == "start" else entity.end
            return (at.x, at.y)
        if isinstance(entity, SketchPoint) and ref.point == "position":
            return (entity.position.x, entity.position.y)
        return None

    nodes = _Points()
    for line in lines.values():
        nodes.add((line.id, "start"))
        nodes.add((line.id, "end"))
    for point in points.values():
        nodes.add((point.id, "position"))

    def key(ref: EntityPointRef) -> PointKey | None:
        if isinstance(ref, DimensionPointRef) and ref.sharp is not None:
            return None
        k = (ref.entity, ref.point)
        return k if k in nodes else None

    constraints = sketch.params.constraints
    for c in constraints:
        if isinstance(c, CoincidentConstraint):
            a, b = key(c.a), key(c.b)
            if a is not None and b is not None:
                nodes.union(a, b)

    # One closed loop: every loop line's ends are joined to exactly one other
    # loop line's end.
    ends: dict[PointKey, list[tuple[str, str]]] = {}
    for line_id in loop_ids:
        for end in ("start", "end"):
            ends.setdefault(nodes.find((line_id, end)), []).append((line_id, end))
    for at in ends.values():
        if len(at) != 2:
            line_id, end = at[0]
            raise refuse(
                f"{line_id}'s {end} must meet exactly one other line (coincident): "
                "the outline is one closed loop."
            )
    for line_id in loop_ids:
        if nodes.find((line_id, "start")) == nodes.find((line_id, "end")):
            raise refuse(f"{line_id} starts where it ends.")
    walk: list[tuple[str, PointKey, PointKey]] = []
    current = loop_ids[0]
    node = nodes.find((current, "start"))
    for _ in range(len(loop_ids)):
        a = nodes.find((current, "start"))
        b = nodes.find((current, "end"))
        far = b if a == node else a
        walk.append((current, node, far))
        node = far
        current = next(lid for lid, _ in ends[far] if lid != current)
    if (
        current != loop_ids[0]
        or node != walk[0][1]
        or len({lid for lid, _, _ in walk}) != len(loop_ids)
    ):
        raise refuse("the lines must close one loop (they make more than one).")

    # Each line's axis: horizontal, vertical, or inferred through parallel,
    # perpendicular and collinear.
    axis: dict[str, Axis] = {}

    def assign(line_id: str, value: Axis) -> bool:
        if line_id not in lines:
            return False
        held = axis.get(line_id)
        if held is None:
            axis[line_id] = value
            return True
        if held != value:
            raise refuse(f"{line_id} is constrained both horizontal and vertical.")
        return False

    for c in constraints:
        if isinstance(c, HorizontalConstraint):
            assign(c.entity, "h")
        elif isinstance(c, VerticalConstraint):
            assign(c.entity, "v")
    other: dict[Axis, Axis] = {"h": "v", "v": "h"}
    changed = True
    while changed:
        changed = False
        for c in constraints:
            if isinstance(c, ParallelConstraint | CollinearConstraint):
                for x, y in ((c.a, c.b), (c.b, c.a)):
                    if x in axis:
                        changed |= assign(y, axis[x])
            elif isinstance(c, PerpendicularConstraint):
                for x, y in ((c.a, c.b), (c.b, c.a)):
                    if x in axis:
                        changed |= assign(y, other[axis[x]])
    for line_id in loop_ids:
        if line_id not in axis:
            raise refuse(
                f"{line_id} is not constrained horizontal or vertical; outline "
                "lines run along the sketch's axes."
            )

    def var(k: PointKey, coordinate: int) -> tuple[PointKey, int]:
        return (nodes.find(k), coordinate)

    def coord(a: Axis) -> int:
        return 0 if a == "h" else 1

    system = _System()
    one = Fraction(1)

    def line_ends(line_id: str) -> tuple[PointKey, PointKey]:
        return (line_id, "start"), (line_id, "end")

    def drawn(line_id: str, a: Axis) -> int:
        line = lines[line_id]
        delta = (line.end.x - line.start.x) if a == "h" else (line.end.y - line.start.y)
        sign = _sign(delta)
        if sign == 0:
            raise refuse(f"{line_id} is drawn with no length; redraw it.")
        return sign

    for line_id, a in axis.items():
        s, e = line_ends(line_id)
        across = 1 - coord(a)
        system.add({var(s, across): one, var(e, across): -one}, Fraction(0))

    for c in constraints:
        if isinstance(c, DimensionConstraint) and not c.is_driving:
            continue
        match c:
            case FixedConstraint():
                k = key(c.point)
                at = stored(c.point)
                if k is None or at is None:
                    continue
                system.add({var(k, 0): one}, _f(at[0]))
                system.add({var(k, 1): one}, _f(at[1]))
            case DistanceConstraint():
                if c.start_sharp is not None or c.end_sharp is not None:
                    continue
                a = axis.get(c.entity)
                if a is None:
                    continue
                s, e = line_ends(c.entity)
                i = coord(a)
                sign = drawn(c.entity, a)
                system.add({var(e, i): one, var(s, i): -one}, sign * _f(c.value_mm))
            case PointDistanceConstraint():
                ka, kb = key(c.a), key(c.b)
                pa, pb = stored(c.a), stored(c.b)
                if ka is None or kb is None or pa is None or pb is None:
                    continue
                direction = c.direction
                if direction == "aligned":
                    shared = [
                        lid
                        for lid in axis
                        if {nodes.find(x) for x in line_ends(lid)}
                        == {nodes.find(ka), nodes.find(kb)}
                    ]
                    if not shared:
                        continue
                    direction = "horizontal" if axis[shared[0]] == "h" else "vertical"
                i = 0 if direction == "horizontal" else 1
                sign = _sign(pb[i] - pa[i])
                if sign == 0:
                    raise refuse(
                        f"a {direction} dimension measures two points drawn level; "
                        "redraw them apart."
                    )
                system.add({var(kb, i): one, var(ka, i): -one}, sign * _f(c.value_mm))
            case PointLineDistanceConstraint():
                kp, pp = key(c.point), stored(c.point)
                a = axis.get(c.line)
                if kp is None or pp is None or a is None:
                    continue
                i = 1 - coord(a)
                start = lines[c.line].start
                sign = _sign(pp[i] - (start.x, start.y)[i])
                if sign == 0:
                    raise refuse(f"a dimension to {c.line} measures a point on it.")
                s, _ = line_ends(c.line)
                system.add({var(kp, i): one, var(s, i): -one}, sign * _f(c.value_mm))
            case EqualConstraint():
                aa, ab = axis.get(c.a), axis.get(c.b)
                if aa is None or ab is None:
                    continue
                sa, ea = line_ends(c.a)
                sb, eb = line_ends(c.b)
                ia, ib = coord(aa), coord(ab)
                ga, gb = drawn(c.a, aa), drawn(c.b, ab)
                coeffs: dict[tuple[PointKey, int], Fraction] = {}
                for k, v in (
                    (var(ea, ia), Fraction(ga)),
                    (var(sa, ia), Fraction(-ga)),
                    (var(eb, ib), Fraction(-gb)),
                    (var(sb, ib), Fraction(gb)),
                ):
                    coeffs[k] = coeffs.get(k, Fraction(0)) + v
                system.add(coeffs, Fraction(0))
            case CollinearConstraint():
                aa = axis.get(c.a)
                if aa is None or c.b not in lines:
                    continue
                i = 1 - coord(aa)
                system.add(
                    {var((c.a, "start"), i): one, var((c.b, "start"), i): -one},
                    Fraction(0),
                )
            case MidpointConstraint():
                kp = key(c.point)
                if kp is None or c.line not in lines:
                    continue
                s, e = line_ends(c.line)
                half = Fraction(1, 2)
                for i in (0, 1):
                    coeffs = {var(kp, i): one}
                    for k in (var(s, i), var(e, i)):
                        coeffs[k] = coeffs.get(k, Fraction(0)) - half
                    system.add(coeffs, Fraction(0))
            case SymmetricConstraint():
                ka, kb = key(c.a), key(c.b)
                a = axis.get(c.line)
                if ka is None or kb is None or a is None:
                    continue
                i = 1 - coord(a)  # across the mirror line
                j = coord(a)  # along it
                s, _ = line_ends(c.line)
                coeffs = {var(ka, i): one}
                for k, v in ((var(kb, i), one), (var(s, i), Fraction(-2))):
                    coeffs[k] = coeffs.get(k, Fraction(0)) + v
                system.add(coeffs, Fraction(0))
                system.add({var(ka, j): one, var(kb, j): -one}, Fraction(0))
            case _:
                continue

    if system.conflict:
        raise refuse(
            "its dimensions disagree (the sketch is over-constrained); remove "
            "the extra dimension."
        )
    corners: dict[PointKey, Vec2] = {}
    for line_id, start, _ in walk:
        x = system.value((start, 0))
        y = system.value((start, 1))
        if x is None or y is None:
            raise refuse(
                f"it is not fully defined at {line_id}'s start: dimension every "
                "side and constrain a corner to the origin, so the walls stand "
                "where the sketch is."
            )
        corners[start] = (_inches(x), _inches(y))

    segments = [Segment(line_id, corners[a], corners[b]) for line_id, a, b in walk]
    for segment in segments:
        if segment.length <= 0.0:
            raise refuse(f"{segment.line_id} has no length.")
    _check_simple(segments, refuse)
    twice = sum(s.start[0] * s.end[1] - s.end[0] * s.start[1] for s in segments)
    if twice > 0:  # counter-clockwise as walked: walk it the other way
        first = segments[0]
        rest = [Segment(s.line_id, s.end, s.start) for s in reversed(segments[1:])]
        segments = [Segment(first.line_id, first.end, first.start), *rest]
    for k, segment in enumerate(segments):
        previous = segments[k - 1]
        if previous.direction == segment.direction:
            raise refuse(
                f"{previous.line_id} and {segment.line_id} run on in one line; "
                "join them into one line."
            )
    return Outline(tuple(segments))


def _inches(value_mm: Fraction) -> float:
    return round(float(value_mm) / MM_PER_INCH, _DIGITS) + 0.0


def _check_simple(
    segments: Iterable[Segment], refuse: Callable[[str], PluginError]
) -> None:
    """No two lines that are not neighbours in the loop touch."""
    items = list(segments)
    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            a, b = items[i], items[j]
            if _boxes_touch(a, b):
                raise refuse(
                    f"{a.line_id} and {b.line_id} cross or touch; the outline "
                    "must not cross itself."
                )


def _boxes_touch(a: Segment, b: Segment) -> bool:
    """Axis-aligned segments touch iff their bounding boxes meet."""
    ax0, ax1 = sorted((a.start[0], a.end[0]))
    ay0, ay1 = sorted((a.start[1], a.end[1]))
    bx0, bx1 = sorted((b.start[0], b.end[0]))
    by0, by1 = sorted((b.start[1], b.end[1]))
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def check_nameable(outline: Outline, input_name: str) -> None:
    """Every line id can lead a member name (``e3``): a lowercase letter, then
    lowercase letters, digits or underscores (sketch ids are ``e1``, ``e2``)."""
    for segment in outline.segments:
        line_id = segment.line_id
        if not (
            line_id[0] in _NAMEABLE
            and all(c in _NAMEABLE or c.isdigit() or c == "_" for c in line_id)
            and line_id.isascii()
        ):
            raise unsupported(
                f"Outline: line id {line_id!r} cannot name its wall's members; "
                "redraw that line.",
                input_name,
            )
