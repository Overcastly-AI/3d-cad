"""Roof 1.2.0's footprint: the loop of the picked walls' outer faces, mapped
onto a canonical rectangle or L (ROOF-VALLEY, RESEARCH §23).

Each wall end must meet exactly one perpendicular wall's line within a wall
thickness (butted or meeting at the line); the framing must face in, the
plates be one height and one stud size. :func:`canonical` maps the loop by
an isometry (:class:`Iso`) onto ``[0, A] x [0, B]`` (a rectangle, ``A >= B``)
or that box less the notch ``[0, a] x [0, b]`` (an L whose ``B - b >= A - a``)
and refuses every other outline, so ``roof_valley`` frames two shapes only.
"""

import math
from dataclasses import dataclass

from loft_wire.features import CustomFeature
from loft_wire.plugins import PLUGIN_INPUT_INVALID

from loft_plugins.api import ExpandInputs, PluginError
from loft_plugins.builtin.house import wall_specs_of
from loft_plugins.builtin.roof import unsupported
from loft_plugins.builtin.wall import WallSpec

Vec2 = tuple[float, float]
Dir = tuple[int, int]

#: Most walls one roof picks, and the shapes this rung frames (corners).
MAX_ROOF_WALLS = 12
#: The footprint's largest extent (in), as the typed length's maximum.
MAX_EXTENT_IN = 720.0
#: An L's arms are at least this wide, and stand at least this far proud of
#: each other (in); unequal arms differ by at least MIN_ARM_STEP_IN.
MIN_ARM_IN = 48.0
MIN_WING_IN = 24.0
MIN_ARM_STEP_IN = 12.0
#: The lowest plate a picked wall may carry (in), as the typed plate height.
MIN_PLATE_IN = 12.0
_EPS = 1e-6
_DIGITS = 9


@dataclass(frozen=True)
class Iso:
    """Canonical plan -> world: ``origin + m p``, *m* a signed permutation
    (``m[i]`` is the world image of canonical axis i)."""

    origin: Vec2
    m: tuple[Dir, Dir]

    def vec(self, v: Vec2) -> Vec2:
        (a, b), (c, d) = self.m
        return (a * v[0] + c * v[1], b * v[0] + d * v[1])

    def point(self, p: Vec2) -> Vec2:
        """*p* in the world, rounded as inputs are (a datum's offset)."""
        x, y = self.exact(p)
        return (round(x, _DIGITS) + 0.0, round(y, _DIGITS) + 0.0)

    def exact(self, p: Vec2) -> Vec2:
        """*p* in the world (a cutter's outline: its cheeks exactly)."""
        v = self.vec(p)
        return (self.origin[0] + v[0] + 0.0, self.origin[1] + v[1] + 0.0)

    def dir(self, v: Dir) -> Dir:
        w = self.vec((float(v[0]), float(v[1])))
        return (round(w[0]), round(w[1]))


# --- The footprint -----------------------------------------------------------------


@dataclass(frozen=True)
class Footprint:
    """The walls' outer faces, counter-clockwise (world, in), and the plate."""

    corners: tuple[Vec2, ...]
    plate_height: float
    plate_width: float


def walls_error(message: str) -> PluginError:
    return unsupported(message, "walls")


def _axis(direction_deg: float) -> Dir | None:
    turns = direction_deg / 90.0
    k = round(turns)
    if abs(turns - k) > 1e-9:
        return None
    return ((1, 0), (0, 1), (-1, 0), (0, -1))[k % 4]


@dataclass(frozen=True)
class _WallLine:
    name: str
    start: Vec2
    end: Vec2
    along: Dir
    across: Dir
    thickness: float
    plate: float

    @property
    def horizontal(self) -> bool:
        return self.along[1] == 0

    def ends(self) -> tuple[Vec2, Vec2]:
        return (self.start, self.end)


def _wall_line(name: str, spec: WallSpec) -> _WallLine:
    along = _axis(spec.direction_deg)
    if along is None:
        raise walls_error(
            f"{name} runs at {spec.direction_deg:g} deg; a roof on walls takes "
            "walls at multiples of 90 deg."
        )
    across: Dir = (
        (along[1], -along[0]) if spec.side == "right" else (-along[1], along[0])
    )
    start = (spec.start_x, spec.start_y)
    end = (
        round(spec.start_x + along[0] * spec.length, _DIGITS) + 0.0,
        round(spec.start_y + along[1] * spec.length, _DIGITS) + 0.0,
    )
    return _WallLine(
        name,
        start,
        end,
        along,
        across,
        spec.thickness,
        round(spec.elevation + spec.height, _DIGITS),
    )


def footprint_from_walls(inputs: ExpandInputs) -> Footprint | None:
    """The loop of the picked walls' outer faces, or ``None`` if none."""
    picks = inputs.features("walls")
    if not picks:
        return None
    lines: list[_WallLine] = []
    for ref in picks:
        wall = inputs.resolve(ref)
        if not isinstance(wall, CustomFeature):
            raise PluginError(
                PLUGIN_INPUT_INVALID, "Walls: pick earlier Walls.", input="walls"
            )
        # A 1.3.0 wall may stand on a floor, or be an outline's walls, one per
        # line (BUILDING-OUTLINE); earlier releases are one typed line each.
        for _, spec in wall_specs_of(ref.feature_id, wall, inputs.earlier):
            lines.append(_wall_line(f"Wall {len(lines) + 1}", spec))
    if len(lines) not in (4, 6):
        raise walls_error(
            f"{len(lines)} walls picked: this roof frames a rectangle (4 walls) or "
            "an L (6 walls), every wall an eave."
        )
    plates = {round(w.plate, 6) for w in lines}
    if len(plates) != 1:
        raise walls_error(
            "The picked walls' plates are at different heights: a roof bears on "
            "one plate height (set each wall's height and base elevation)."
        )
    widths = {round(w.thickness, 6) for w in lines}
    if len(widths) != 1:
        raise walls_error("The picked walls are of different stud sizes.")
    tol = max(w.thickness for w in lines) + _EPS
    # Each wall end meets exactly one perpendicular wall's line, at a corner
    # within a wall's thickness of both ends (butted or meeting at the line).
    links: dict[tuple[int, int], tuple[int, int, Vec2]] = {}
    for i, wi in enumerate(lines):
        for end_i, pi in enumerate(wi.ends()):
            found: list[tuple[int, int, Vec2]] = []
            for j, wj in enumerate(lines):
                if j == i or wj.horizontal == wi.horizontal:
                    continue
                corner = (
                    (wj.start[0], wi.start[1])
                    if wi.horizontal
                    else (wi.start[0], wj.start[1])
                )
                if math.dist(corner, pi) > tol:
                    continue
                for end_j, pj in enumerate(wj.ends()):
                    if math.dist(corner, pj) <= tol:
                        found.append((j, end_j, corner))
            if len(found) != 1:
                which = "start" if end_i == 0 else "end"
                raise walls_error(
                    f"The picked walls do not close one loop at {wi.name}'s {which}: "
                    "pick every wall of the outline, each meeting the next at a corner."
                )
            links[(i, end_i)] = found[0]
    corners: list[Vec2] = []
    at, end = 0, 1
    for _ in range(len(lines)):
        j, end_j, corner = links[(at, end)]
        if links[(j, end_j)][:2] != (at, end):
            raise walls_error("The picked walls do not close one loop.")
        corners.append(corner)
        at, end = j, 1 - end_j
    if at != 0 or end != 1 or len(set(corners)) != len(lines):
        raise walls_error("The picked walls do not close one loop.")
    twice = sum(
        corners[i][0] * corners[i - 1][1] - corners[i - 1][0] * corners[i][1]
        for i in range(len(corners))
    )
    # The shoelace sum above is minus twice the area: negative when the walk
    # is counter-clockwise.
    loop = corners if twice < 0 else list(reversed(corners))
    # Every wall frames toward the inside: its framing side is the loop's left.
    for wall in lines:
        index = next(
            k
            for k in range(len(loop))
            if _on_edge(loop[k], loop[(k + 1) % len(loop)], wall)
        )
        a, b = loop[index], loop[(index + 1) % len(loop)]
        left = (-(b[1] - a[1]), b[0] - a[0])
        if left[0] * wall.across[0] + left[1] * wall.across[1] <= 0:
            raise walls_error(
                f"{wall.name}'s framing lies outside the roof's outline: flip its "
                "framing side, so every wall's line is the outer face."
            )
    plate = lines[0].plate
    if plate < MIN_PLATE_IN - _EPS:
        raise walls_error(f"The walls' plates are below {MIN_PLATE_IN:g} in.")
    return Footprint(tuple(loop), plate, lines[0].thickness)


def _on_edge(a: Vec2, b: Vec2, wall: _WallLine) -> bool:
    """Whether the loop edge a->b lies on *wall*'s line."""
    if wall.horizontal:
        return abs(a[1] - wall.start[1]) < _EPS and abs(b[1] - wall.start[1]) < _EPS
    return abs(a[0] - wall.start[0]) < _EPS and abs(b[0] - wall.start[0]) < _EPS


# --- The canonical shape -----------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """The canonical footprint (module docstring) and its map to the world.
    A rectangle has ``a = b = 0``."""

    A: float
    B: float
    a: float
    b: float
    iso: Iso
    #: An L whose arms are one width (to 1e-6 in): one node, framed exactly.
    equal: bool = False

    @property
    def is_l(self) -> bool:
        return self.a > 0.0

    @property
    def w1(self) -> float:
        return self.B - self.b

    @property
    def w2(self) -> float:
        return self.w1 if self.equal else self.A - self.a


def _mirror(iso: Iso) -> Iso:
    """*iso* after swapping the canonical axes."""
    return Iso(iso.origin, (iso.m[1], iso.m[0]))


def canonical(fp: Footprint, t: float) -> Shape:
    """Map *fp* onto the canonical rectangle or L, refusing other shapes."""
    pts = list(fp.corners)
    n = len(pts)
    turns: list[float] = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        turns.append(cross)
    reflex = [i for i in range(n) if turns[i] < 0]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if max(xs) - min(xs) > MAX_EXTENT_IN + _EPS or (
        max(ys) - min(ys) > MAX_EXTENT_IN + _EPS
    ):
        raise walls_error(
            f"The walls' outline is over {MAX_EXTENT_IN:g} in across: frame it as "
            "more than one roof."
        )
    if n == 4 and not reflex:
        wide = max(xs) - min(xs) >= max(ys) - min(ys)
        m: tuple[Dir, Dir] = ((1, 0), (0, 1)) if wide else ((0, 1), (1, 0))
        iso = Iso((min(xs), min(ys)), m)
        long = max(xs) - min(xs) if wide else max(ys) - min(ys)
        short = max(ys) - min(ys) if wide else max(xs) - min(xs)
        shape = Shape(round(long, _DIGITS), round(short, _DIGITS), 0.0, 0.0, iso)
        if t - 1e-9 > shape.A - shape.B:
            raise walls_error(
                "A hip roof's long side must be at least its short side plus one "
                f"rafter thickness ({shape.B + t:g} in): the ridge-end commons "
                "would overlap (a pyramid roof is a later rung)."
            )
        return shape
    if n != 6 or len(reflex) != 1:
        raise walls_error(
            "The walls' outline is not a rectangle or an L: this roof frames those "
            "two (more corners are a later rung)."
        )
    r = reflex[0]
    d_in = _unit(pts[r - 1], pts[r])
    d_out = _unit(pts[r], pts[(r + 1) % n])
    m = (d_in, (-d_out[0], -d_out[1]))

    # Canonical coordinates: m^T (X - X0), shifted so the box's corner is 0.
    def local(p: Vec2) -> Vec2:
        return (
            m[0][0] * p[0] + m[0][1] * p[1],
            m[1][0] * p[0] + m[1][1] * p[1],
        )

    loc = [local(p) for p in pts]
    u0 = min(p[0] for p in loc)
    v0 = min(p[1] for p in loc)
    origin_world = Iso((0.0, 0.0), m).vec((u0, v0))
    iso = Iso(origin_world, m)
    big_u = round(max(p[0] for p in loc) - u0, _DIGITS)
    big_v = round(max(p[1] for p in loc) - v0, _DIGITS)
    a = round(loc[r][0] - u0, _DIGITS)
    b = round(loc[r][1] - v0, _DIGITS)
    if (big_v - b) < (big_u - a) - 1e-9:
        iso = _mirror(iso)
        big_u, big_v, a, b = big_v, big_u, b, a
    equal = abs((big_v - b) - (big_u - a)) <= _EPS
    if equal:
        a = big_u - (big_v - b)  # float noise only: one node, exactly
    shape = Shape(big_u, big_v, a, b, iso, equal)
    if min(shape.w1, shape.w2) < MIN_ARM_IN - _EPS:
        raise walls_error(f"Each arm of the L must be at least {MIN_ARM_IN:g} in wide.")
    if min(a, b) < MIN_WING_IN - _EPS:
        raise walls_error(
            f"Each arm of the L must stand at least {MIN_WING_IN:g} in proud of the "
            "other."
        )
    if not shape.equal and shape.w1 - shape.w2 < MIN_ARM_STEP_IN - _EPS:
        raise walls_error(
            "The L's arms must be the same width, or differ by at least "
            f"{MIN_ARM_STEP_IN:g} in (so the narrow arm's ridge ends on a hip)."
        )
    if shape.A - shape.w1 < t - 1e-9:
        raise walls_error(
            "The L's wider arm must be at least its width plus one rafter "
            f"thickness long ({shape.w1 + t:g} in)."
        )
    return shape


def _unit(a: Vec2, b: Vec2) -> Dir:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return (
        int(math.copysign(1, dx)) if abs(dx) > _EPS else 0,
        int(math.copysign(1, dy)) if abs(dy) > _EPS else 0,
    )
