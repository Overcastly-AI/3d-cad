"""Roof 1.2.0: hip and valley roofs on a footprint picked from walls
(ROOF-VALLEY, ROOF-HIP-TAIL, RESEARCH §23).

``loft.roof`` 1.2.0 adds a WALLS input (a feature list of ``loft.wall``
features) and a valley size. With walls picked, the roof's footprint is the
loop of their outer faces, as Revit's Roof by Footprint (Pick Walls) and Chief
Architect's roof from walls build it: corners where consecutive walls' lines
meet, the plate height and width read from the walls. With none picked it is
1.1.0's typed rectangle. Gable is 1.0.0's expansion exactly, on the typed
bearing only (a gable on picked walls needs a per-wall "defines slope"
choice: BACKLOG note ROOF-BEARING-WALLS).

**Shapes.** Equal pitch, every wall an eave, walls at multiples of 90 deg:
the planes meet on hips and valleys at 45 deg in plan, the orthogonal
straight skeleton. This rung frames a rectangle (B3) and an L (B4); a
footprint of more corners is refused (ROOF-VALLEY-SHAPES). Each footprint is
mapped by an isometry onto a CANONICAL one, framed there and mapped back:

* a rectangle ``[0, A] x [0, B]``, ``A >= B + t`` (the ridge along u);
* an L ``[0, A] x [0, B]`` less the notch ``[0, a] x [0, b]``, its reflex
  corner at ``(a, b)``. Its arms are H = ``[0, A] x [b, B]`` (width
  ``w1 = B - b``) and V = ``[a, A] x [0, B]`` (``w2 = A - a``), mirrored so
  ``w1 >= w2``. H is a hipped rectangle whose ridge runs ``u`` from
  ``w1/2`` to ``A - w1/2``; V's ridge runs ``v`` from ``w2/2`` (a hipped
  end) to the valley's top. One valley rises from ``(a, b)``. Equal widths
  (B4): the valley and both ridges meet on one node, the V ridge butting the
  H ridge's face. Unequal (B4's 48 in wing): V's ridge is lower and ends on
  a node ``N1`` where the valley ends; a hip runs from ``N1`` to H's ridge
  end ``N2``, between the main front and the end planes.

**Members**, buildings.md "Hip and valley conventions" (B3, B4):

* ridges run half a common past each hip end; a ridge that meets another
  ridge butts its face; V's ridge in an unequal L runs half a common past
  ``N1``;
* each plane's rafters are laid out on its eave: commons on the spacing from
  each ridge-end (or king) common's CENTRE, the far ridge-end common flush;
  jacks outward from those on the spacing. Each layout line is clipped to the
  plane's framing region (the plane's face less the hips', valleys' and
  ridges' half thicknesses) and named by where it ends: wall to ridge
  (common, a king to a ridge's end face), wall to hip (jack), valley to
  ridge (valley jack), valley to hip (hip-valley cripple). A tail that would
  cross a valley is cheek-cut at the valley's face. A layout line whose
  valley cheek would cut its seat, or whose top end would not clear it, is
  not framed;
* hips (dropped) and valleys (not dropped: their top centreline on the
  valley line) are side profiles on a midplane datum, extruded symmetric,
  intersected with their plan outline (double cheeks, a valley's V notch at
  the fascias' inside corner), less the seat: everything below the plate
  inside the walls' outer faces;
* ROOF-HIP-TAIL: a hip's or valley's tail is ripped parallel to its top to
  the depth at which its lowest edge meets the commons' undersides (plumb on
  the centreline: the commons' plumb cut less the hip's drop), so the fascia
  line is straight. 1.0.0 and 1.1.0 are released and keep their full tails.

Every cutter outline and every uncut profile runs past the faces it does not
make (``PAST``, ``_SIDE``), so no cutter face coincides with a member's
(DECK's float class). Feature counts are bounded: a roof of more than
``MAX_ROOF_MEMBERS`` members is refused (ROOF-HIP-SIZE).
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from loft_wire.features import (
    CustomFeature,
    DatumFeature,
    DatumMidplaneParams,
    DatumPlaneRef,
    FeatureRef,
)
from loft_wire.lumber import LumberProfile
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    ChoiceInput,
    FeatureListInput,
    MemberMetadata,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
)

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError, lumber_options
from loft_plugins.builtin.roof import (
    HEADROOM,
    HIP_PROFILES,
    MANIFEST_V1_1,
    MIN_OVERHANG_IN,
    PAST,
    PITCHES,
    STYLE_GABLE,
    STYLE_HIP,
    Builder,
    Corner,
    PlaneRef,
    Rafter,
    ccw,
    expand,
    hip_sides,
    inches,
    material_input,
    pitch_value,
    unsupported,
)
from loft_plugins.builtin.wall import WallSpec

_R2 = math.sqrt(2.0)
#: How far (in) a cutter prism runs past a member's sides.
_SIDE = 0.5
#: The least clearance (in) a cheek keeps from a seat, and a member's least
#: clear run where it is shortest.
_CLEAR = 1.0 / 16.0
#: A layout line is framed only if its member is at least this long (in, plan
#: run at its short side).
_MIN_RUN = 2.0
#: Most walls one roof picks, and the shapes this rung frames (corners).
MAX_ROOF_WALLS = 12
#: Most framing members one roof frames (ROOF-HIP-SIZE: a 201-member hip took
#: 32 s of the gateway's 90).
MAX_ROOF_MEMBERS = 160
#: The footprint's largest extent (in), as the typed length's maximum.
MAX_EXTENT_IN = 720.0
#: An L's arms are at least this wide, and stand at least this far proud of
#: each other (in); unequal arms differ by at least _MIN_ARM_STEP.
MIN_ARM_IN = 48.0
MIN_WING_IN = 24.0
MIN_ARM_STEP_IN = 12.0
#: The lowest plate a picked wall may carry (in), as the typed plate height.
MIN_PLATE_IN = 12.0
_EPS = 1e-6
_DIGITS = 9

Vec2 = tuple[float, float]
Dir = tuple[int, int]


# --- Manifest ----------------------------------------------------------------------


def _v1_1_input(name: str) -> PluginInput:
    return next(item for item in MANIFEST_V1_1.inputs if item.name == name)


def _typed(name: str) -> PluginInput:
    item = _v1_1_input(name)
    return item.model_copy(
        update={
            "description": f"{item.description} Typed bearing: read from the walls "
            "when walls are picked."
        }
    )


MANIFEST_V1_2 = PluginManifest(
    id="loft.roof",
    version="1.2.0",
    title="Roof",
    description="A gable, or a hip roof with valleys on walls you pick, of "
    "rafters with a birdsmouth on each wall, ridges, hips, valleys and their "
    "jacks, with a cut list (Chief Architect, Revit Roof by Footprint).",
    inputs=[
        _v1_1_input("style"),
        FeatureListInput(
            kind="features",
            name="walls",
            label="Walls",
            description="Hip style: the walls the roof bears on, every one an "
            "eave (Revit's Pick Walls). Their outer faces close a rectangle or "
            "an L at 90 deg; plate height and width are read from them. None: "
            "the typed bearing below.",
            feature_types=["custom"],
            plugin_ids=["loft.wall"],
            min_items=0,
            max_items=MAX_ROOF_WALLS,
        ),
        _typed("span_mm"),
        _typed("length_mm"),
        _typed("plate_height_mm"),
        _typed("plate_width_mm"),
        _v1_1_input("pitch"),
        _v1_1_input("spacing_mm"),
        _v1_1_input("overhang_mm"),
        _v1_1_input("rafter_profile"),
        _v1_1_input("ridge_profile"),
        _v1_1_input("hip_profile"),
        ChoiceInput(
            kind="choice",
            name="valley_profile",
            label="Valleys",
            description="Valley size (Hip style on an L): at least as deep as the "
            "commons' plumb cut. Valleys are not raised.",
            options=lumber_options(HIP_PROFILES),
            default="us_2x8",
        ),
        _v1_1_input("rafter_material"),
        material_input("ridge_material", "Ridge, hip and valley material"),
    ],
    members=[
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="rafter", title="Rafter"),
        PluginMemberRole(role="common", title="Common"),
        PluginMemberRole(role="jack", title="Jack"),
        PluginMemberRole(role="valley_jack", title="Valley jack"),
        PluginMemberRole(role="cripple", title="Cripple"),
        PluginMemberRole(role="hip", title="Hip"),
        PluginMemberRole(role="valley", title="Valley"),
        PluginMemberRole(role="ridge", title="Ridge"),
        PluginMemberRole(role="cutter", title="Cutter"),
        PluginMemberRole(role="trim", title="Trim"),
    ],
)


# --- Plan geometry (pure, inches) --------------------------------------------------


@dataclass(frozen=True)
class Half:
    """The half-plane ``n . X <= c`` in canonical plan coordinates."""

    n: Dir
    c: float

    def at(self, x: Vec2) -> float:
        """``n . x - c``: <= 0 inside."""
        return self.n[0] * x[0] + self.n[1] * x[1] - self.c


def _norm(n: Dir) -> float:
    return math.hypot(n[0], n[1])


def side_of(n: Dir, c: float, ref: Vec2, offset: float) -> Half:
    """The half-plane on *ref*'s side of the line ``n . X = c``, its edge moved
    *offset* (in, square to the line) toward *ref*: a member's face."""
    sign = 1 if n[0] * ref[0] + n[1] * ref[1] - c > 0 else -1
    # sign * (n.X - c) >= offset * |n|  <=>  -sign n.X <= -sign c - offset |n|
    return Half((-sign * n[0], -sign * n[1]), -sign * c - offset * _norm(n))


@dataclass(frozen=True)
class Strip:
    """A member's plan in its own frame: ``X = origin + s d + q e`` with ``d``
    the unit of *direction* and ``e`` it turned 90 deg left; ``|q| <= width``.
    *lower* bounds s from below as a max over groups of a min over each
    group's alternatives (an OR: a valley's tail is outside the fascias'
    inside corner); *upper* as a min over groups of a max."""

    origin: Vec2
    direction: Dir
    width: float
    lower: tuple[tuple[Half, ...], ...]
    upper: tuple[tuple[Half, ...], ...]

    @property
    def d(self) -> Vec2:
        k = _norm(self.direction)
        return (self.direction[0] / k, self.direction[1] / k)

    @property
    def e(self) -> Vec2:
        d = self.d
        return (-d[1], d[0])

    def point(self, s: float, q: float) -> Vec2:
        d, e = self.d, self.e
        return (
            self.origin[0] + s * d[0] + q * e[0],
            self.origin[1] + s * d[1] + q * e[1],
        )

    def _line(self, h: Half) -> tuple[float, float, float]:
        """*h* as ``a s <= r - b q``: (a, b, r)."""
        d, e = self.d, self.e
        a = h.n[0] * d[0] + h.n[1] * d[1]
        b = h.n[0] * e[0] + h.n[1] * e[1]
        r = h.c - (h.n[0] * self.origin[0] + h.n[1] * self.origin[1])
        return a, b, r

    def _bound(self, h: Half, q: float, lower: bool) -> float:
        a, b, r = self._line(h)
        if lower != (a < 0) or abs(a) < 1e-12:
            raise ValueError("a strip bound on the wrong end")
        return (r - b * q) / a

    def lo(self, q: float) -> float:
        return max(min(self._bound(h, q, True) for h in g) for g in self.lower)

    def hi(self, q: float) -> float:
        return min(max(self._bound(h, q, False) for h in g) for g in self.upper)

    def stations(self, width: float | None = None) -> list[float]:
        """Every q in ``[-w, w]`` where a bound may bend: the ends, 0, and
        each crossing of two bound lines."""
        w = self.width if width is None else width
        lines = [self._line(h) for g in (*self.lower, *self.upper) for h in g]
        out = {-w, 0.0, w}
        for i, (a1, b1, r1) in enumerate(lines):
            for a2, b2, r2 in lines[i + 1 :]:
                # (r1 - b1 q)/a1 = (r2 - b2 q)/a2
                den = b1 * a2 - b2 * a1
                if abs(den) > 1e-12:
                    q = (r1 * a2 - r2 * a1) / den
                    if -w < q < w:
                        out.add(q)
        return sorted(out)

    def gap(self, width: float | None = None) -> float:
        """The least ``hi - lo`` across ``|q| <= width``."""
        return min(self.hi(q) - self.lo(q) for q in self.stations(width))

    def outline(self) -> list[Vec2]:
        """The plan polygon (canonical), counter-clockwise or not."""
        qs = self.stations()
        ring = [(self.lo(q), q) for q in qs] + [(self.hi(q), q) for q in reversed(qs)]
        out: list[Vec2] = []
        for s, q in ring:
            p = self.point(s, q)
            if not out or math.dist(out[-1], p) > 1e-9:
                out.append(p)
        if math.dist(out[0], out[-1]) <= 1e-9:
            out.pop()
        # Drop a station where the outline runs straight on.
        n = len(out)
        return [
            p
            for i, p in enumerate(out)
            if abs(
                (p[0] - out[i - 1][0]) * (out[(i + 1) % n][1] - p[1])
                - (p[1] - out[i - 1][1]) * (out[(i + 1) % n][0] - p[0])
            )
            > 1e-9
        ]


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


def _walls_error(message: str) -> PluginError:
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
        raise _walls_error(
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
        spec = WallSpec.from_inputs(ExpandInputs(ref.feature_id, wall.params.inputs))
        lines.append(_wall_line(f"Wall {len(lines) + 1}", spec))
    if len(lines) not in (4, 6):
        raise _walls_error(
            f"{len(lines)} walls picked: this roof frames a rectangle (4 walls) or "
            "an L (6 walls), every wall an eave."
        )
    plates = {round(w.plate, 6) for w in lines}
    if len(plates) != 1:
        raise _walls_error(
            "The picked walls' plates are at different heights: a roof bears on "
            "one plate height (set each wall's height and base elevation)."
        )
    widths = {round(w.thickness, 6) for w in lines}
    if len(widths) != 1:
        raise _walls_error("The picked walls are of different stud sizes.")
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
                raise _walls_error(
                    f"The picked walls do not close one loop at {wi.name}'s {which}: "
                    "pick every wall of the outline, each meeting the next at a corner."
                )
            links[(i, end_i)] = found[0]
    corners: list[Vec2] = []
    at, end = 0, 1
    for _ in range(len(lines)):
        j, end_j, corner = links[(at, end)]
        if links[(j, end_j)][:2] != (at, end):
            raise _walls_error("The picked walls do not close one loop.")
        corners.append(corner)
        at, end = j, 1 - end_j
    if at != 0 or end != 1 or len(set(corners)) != len(lines):
        raise _walls_error("The picked walls do not close one loop.")
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
            raise _walls_error(
                f"{wall.name}'s framing lies outside the roof's outline: flip its "
                "framing side, so every wall's line is the outer face."
            )
    plate = lines[0].plate
    if plate < MIN_PLATE_IN - _EPS:
        raise _walls_error(f"The walls' plates are below {MIN_PLATE_IN:g} in.")
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
        raise _walls_error(
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
            raise _walls_error(
                "A hip roof's long side must be at least its short side plus one "
                f"rafter thickness ({shape.B + t:g} in): the ridge-end commons "
                "would overlap (a pyramid roof is a later rung)."
            )
        return shape
    if n != 6 or len(reflex) != 1:
        raise _walls_error(
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
        raise _walls_error(
            f"Each arm of the L must be at least {MIN_ARM_IN:g} in wide."
        )
    if min(a, b) < MIN_WING_IN - _EPS:
        raise _walls_error(
            f"Each arm of the L must stand at least {MIN_WING_IN:g} in proud of the "
            "other."
        )
    if not shape.equal and shape.w1 - shape.w2 < MIN_ARM_STEP_IN - _EPS:
        raise _walls_error(
            "The L's arms must be the same width, or differ by at least "
            f"{MIN_ARM_STEP_IN:g} in (so the narrow arm's ridge ends on a hip)."
        )
    if shape.A - shape.w1 < t - 1e-9:
        raise _walls_error(
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


# --- Dimensions --------------------------------------------------------------------


@dataclass(frozen=True)
class Dims:
    rise: int
    plate: float
    plate_width: float
    spacing: float
    overhang: float
    rafter: LumberProfile
    ridge: LumberProfile
    hip: LumberProfile
    valley: LumberProfile

    @property
    def k(self) -> float:
        return self.rise / 12.0

    @property
    def m(self) -> float:
        """Rise per unit of plan run along a hip or valley."""
        return self.k / _R2

    @property
    def t(self) -> float:
        return self.rafter.thickness_in

    @property
    def common(self) -> Rafter:
        """The commons' section (its ridge face is set per member)."""
        return Rafter(
            rise=self.rise,
            depth=self.rafter.width_in,
            plate_height=self.plate,
            plate_width=self.plate_width,
            ridge_face=0.0,
            overhang=self.overhang,
        )

    @property
    def seat(self) -> float:
        return self.common.seat

    @property
    def plumb(self) -> float:
        return self.common.plumb_depth

    @property
    def hap(self) -> float:
        """The commons' height above plate at the wall's outer face."""
        return self.common.plumb_depth - self.common.heel

    @property
    def unit(self) -> float:
        return math.hypot(12.0, self.rise)

    @property
    def hip_unit(self) -> float:
        return math.hypot(12.0 * _R2, self.rise)

    def line_plumb(self, profile: LumberProfile) -> float:
        return profile.width_in * self.hip_unit / (12.0 * _R2)


# --- The framing plan (canonical) --------------------------------------------------

Kind = Literal["common", "jack", "valley_jack", "cripple"]


@dataclass(frozen=True)
class Piece:
    """Over ``p0 .. p1`` along an eave, a member's top end is *face*; a
    *square* end (a ridge's side or end face) is cut by the profile."""

    p0: float
    p1: float
    face: Half
    square: bool


@dataclass(frozen=True)
class Eave:
    """One plane: its wall's outer face from *origin* along *along*, rising
    toward *inward* (canonical units); where its rafters are laid out, what
    each ends on, and the valley face a rafter may start at."""

    origin: Vec2
    along: Dir
    inward: Dir
    positions: tuple[float, ...]
    pieces: tuple[Piece, ...]
    valley: Half | None = None

    def at(self, p: float, d: float) -> Vec2:
        return (
            self.origin[0] + self.along[0] * p + self.inward[0] * d,
            self.origin[1] + self.along[1] * p + self.inward[1] * d,
        )

    def fascia(self, d: float) -> Half:
        """``inward . X >= inward . origin + d``."""
        o = self.inward[0] * self.origin[0] + self.inward[1] * self.origin[1]
        return Half((-self.inward[0], -self.inward[1]), -(o + d))


@dataclass(frozen=True)
class LineMember:
    """A hip or valley: its strip (plan), its top's height at the strip's
    origin, and its seat region (a strip of its own) or none."""

    kind: Literal["hip", "valley"]
    strip: Strip
    z0: float
    slope: float
    rip: tuple[float, float] | None  # (s_step, rip depth) of a ripped tail
    seat: Strip | None


@dataclass(frozen=True)
class Board:
    """A ridge board: canonical box and its top."""

    u0: float
    u1: float
    v0: float
    v1: float
    top: float


@dataclass
class Plan:
    eaves: list[Eave] = field(default_factory=list[Eave])
    lines: list[LineMember] = field(default_factory=list[LineMember])
    boards: list[Board] = field(default_factory=list[Board])


def ridge_layout(p0: float, p1: float, spacing: float, t: float) -> list[float]:
    """Centres along a ridge from its end common at *p0* to the one at *p1*:
    on the spacing from *p0*'s centre, *p1* flush, a layout common that would
    overlap it dropped (buildings.md B4)."""
    out = [p0]
    n = 1
    while p0 + spacing * n <= p1 - t + 1e-9:
        out.append(p0 + spacing * n)
        n += 1
    if p1 - p0 >= t - 1e-9:
        out.append(p1)
    return out


def _outward(p: float, spacing: float, sign: int, limit: float) -> list[float]:
    """Jack layout from the end common at *p*, every spacing toward *sign*,
    while still within *limit* along the eave."""
    out: list[float] = []
    n = 1
    while True:
        c = p + sign * spacing * n
        if (c - limit) * sign > 0:
            return out
        out.append(c)
        n += 1


def _face_piece(
    origin: Vec2,
    along: Dir,
    inward: Dir,
    p0: float,
    p1: float,
    n: Dir,
    c: float,
    offset: float,
    square: bool,
) -> Piece:
    """A top-end piece: the face of the line ``n . X = c`` (*offset* off it)
    on the eave's side (toward the wall)."""
    mid = (p0 + p1) / 2 if math.isfinite(p0 + p1) else (p0 if math.isfinite(p0) else p1)
    ref = (
        origin[0] + along[0] * mid - inward[0] * 1e6,
        origin[1] + along[1] * mid - inward[1] * 1e6,
    )
    return Piece(p0, p1, side_of(n, c, ref, offset), square)


def frame_plan(shape: Shape, dims: Dims) -> Plan:
    """The roof's ridges, planes and hips/valleys on the canonical shape."""
    t, s, oh = dims.t, dims.spacing, dims.overhang
    tr = dims.ridge.thickness_in
    hh = dims.hip.thickness_in / _R2
    th2 = dims.hip.thickness_in / 2  # a hip's half thickness, square to it
    A, B, a, b = shape.A, shape.B, shape.a, shape.b
    inf = math.inf
    plan = Plan()
    w1 = shape.w1
    vH = b + w1 / 2
    uL, uR = w1 / 2, A - w1 / 2
    top = dims.plate + dims.hap
    h_top = top + dims.k * (w1 / 2 - tr / 2)
    plan.boards.append(Board(uL - t / 2, uR + t / 2, vH - tr / 2, vH + tr / 2, h_top))
    h_layout = ridge_layout(uL, uR, s, t)

    def eave(
        origin: Vec2,
        along: Dir,
        inward: Dir,
        positions: Iterable[float],
        tops: Sequence[tuple[float, float, Dir, float, float, bool]],
        valley: tuple[Dir, float] | None = None,
    ) -> Eave:
        pieces = tuple(
            _face_piece(origin, along, inward, p0, p1, n, c, off, sq)
            for p0, p1, n, c, off, sq in tops
        )
        low = None
        if valley is not None:
            n, c = valley
            # The valley's face on this plane's side (away from the wall).
            probe = Eave(origin, along, inward, (), pieces)
            ref = probe.at(0.0, 1e6)
            low = side_of(n, c, ref, dims.valley.thickness_in / 2)
        return Eave(origin, along, inward, tuple(sorted(set(positions))), pieces, low)

    # Hip lines (centre): n . X = c.
    h_top_left: tuple[Dir, float] = ((1, 1), B)  # from (0, B)
    h_top_right: tuple[Dir, float] = ((-1, 1), B - A)  # from (A, B)
    h_low_left: tuple[Dir, float] = ((-1, 1), b)  # from (0, b)
    king_left = (vH - t / 2, vH + t / 2, (1, 0), uL - t / 2, 0.0, True)
    king_right = (vH - t / 2, vH + t / 2, (1, 0), uR + t / 2, 0.0, True)
    ridge_top = (uL - t / 2, uR + t / 2, (0, 1), vH + tr / 2, 0.0, True)
    ridge_low = (uL - t / 2, uR + t / 2, (0, 1), vH - tr / 2, 0.0, True)

    # Back (v = B) and left (u = 0): H's hipped rectangle, as 1.1.0's.
    plan.eaves.append(
        eave(
            (0.0, B),
            (1, 0),
            (0, -1),
            [*h_layout, *_outward(uL, s, -1, -oh), *_outward(uR, s, 1, A + oh)],
            [
                (-inf, uL - t / 2, *h_top_left, th2, False),
                ridge_top,
                (uR + t / 2, inf, *h_top_right, th2, False),
            ],
        )
    )
    plan.eaves.append(
        eave(
            (0.0, 0.0),
            (0, 1),
            (1, 0),
            [vH, *_outward(vH, s, -1, b - oh), *_outward(vH, s, 1, B + oh)],
            [
                (-inf, vH - t / 2, *h_low_left, th2, False),
                king_left,
                (vH + t / 2, inf, *h_top_left, th2, False),
            ],
        )
    )
    corners: list[tuple[Vec2, Dir, float]] = [
        ((0.0, b), (1, 1), w1 / 2 - t / 2),
        ((0.0, B), (1, -1), w1 / 2 - t / 2),
        ((A, B), (-1, -1), w1 / 2 - t / 2),
    ]
    if not shape.is_l:
        # Front (v = 0) and right (u = A): the rest of B3.
        h_low_right: tuple[Dir, float] = ((1, 1), A)  # from (A, 0)
        plan.eaves.append(
            eave(
                (0.0, 0.0),
                (1, 0),
                (0, 1),
                [*h_layout, *_outward(uL, s, -1, -oh), *_outward(uR, s, 1, A + oh)],
                [
                    (-inf, uL - t / 2, *h_low_left, th2, False),
                    ridge_low,
                    (uR + t / 2, inf, *h_low_right, th2, False),
                ],
            )
        )
        plan.eaves.append(
            eave(
                (A, 0.0),
                (0, 1),
                (-1, 0),
                [vH, *_outward(vH, s, -1, -oh), *_outward(vH, s, 1, B + oh)],
                [
                    (-inf, vH - t / 2, *h_low_right, th2, False),
                    king_right,
                    (vH + t / 2, inf, *h_top_right, th2, False),
                ],
            )
        )
        corners.append(((A, 0.0), (-1, 1), w1 / 2 - t / 2))
        _corner_hips(plan, corners, dims)
        return plan

    # The L: V arm, valley, and (unequal) the hip N1 -> N2.
    w2 = shape.w2
    uV, vB = (uR if shape.equal else a + w2 / 2), w2 / 2
    vT = vH if shape.equal else b + w2 / 2
    v_top = top + dims.k * (w2 / 2 - tr / 2)
    v_end = vH - tr / 2 if shape.equal else vT + t / 2
    plan.boards.append(Board(uV - tr / 2, uV + tr / 2, vB - t / 2, v_end, v_top))
    v_layout = ridge_layout(vB, vT, s, t)
    valley_line: tuple[Dir, float] = ((-1, 1), b - a)  # v - u = b - a
    h5: tuple[Dir, float] = ((-1, 1), -a)  # from (a, 0)
    h4: tuple[Dir, float] = ((1, 1), A)  # from (A, 0)
    h6: tuple[Dir, float] = ((1, 1), A + b)  # N1 -> N2
    v_right = (vB - t / 2, v_end, (1, 0), uV + tr / 2, 0.0, True)
    v_left = (vB - t / 2, v_end, (1, 0), uV - tr / 2, 0.0, True)
    v_king = (uV - t / 2, uV + t / 2, (0, 1), vB - t / 2, 0.0, True)

    # Main front (v = b, u 0..a).
    mf_tops: list[tuple[float, float, Dir, float, float, bool]] = [
        (-inf, uL - t / 2, *h_low_left, th2, False),
        ridge_low,
    ]
    mf_positions = [*h_layout, *_outward(uL, s, -1, -oh)]
    if not shape.equal:
        mf_tops.append((uR + t / 2, uV - tr / 2, *h6, th2, False))
        mf_positions += _outward(uR, s, 1, uV)
    plan.eaves.append(
        eave((0.0, b), (1, 0), (0, 1), mf_positions, mf_tops, valley_line)
    )
    # Wing left (u = a, v 0..b).
    plan.eaves.append(
        eave(
            (a, 0.0),
            (0, 1),
            (1, 0),
            [*v_layout, *_outward(vB, s, -1, -oh)],
            [(-inf, vB - t / 2, *h5, th2, False), v_left],
            valley_line,
        )
    )
    # Wing front (v = 0, u a..A): V's hipped end.
    plan.eaves.append(
        eave(
            (0.0, 0.0),
            (1, 0),
            (0, 1),
            [uV, *_outward(uV, s, -1, a - oh), *_outward(uV, s, 1, A + oh)],
            [
                (-inf, uV - t / 2, *h5, th2, False),
                v_king,
                (uV + t / 2, inf, *h4, th2, False),
            ],
        )
    )
    # Right (u = A, v 0..B).
    r_tops: list[tuple[float, float, Dir, float, float, bool]] = [
        (-inf, vB - t / 2, *h4, th2, False),
        v_right,
    ]
    r_positions = [*v_layout, *_outward(vB, s, -1, -oh), vH]
    r_positions += _outward(vH, s, 1, B + oh)
    if not shape.equal:
        r_tops.append((vT + t / 2, vH - t / 2, *h6, th2, False))
        r_positions += _outward(vH, s, -1, vT)
    r_tops += [king_right, (vH + t / 2, inf, *h_top_right, th2, False)]
    if shape.equal:
        r_tops = [
            (-inf, vB - t / 2, *h4, th2, False),
            (vB - t / 2, vH - tr / 2, (1, 0), uV + tr / 2, 0.0, True),
            king_right,
            (vH + t / 2, inf, *h_top_right, th2, False),
        ]
    plan.eaves.append(eave((A, 0.0), (0, 1), (-1, 0), r_positions, r_tops))

    corners += [
        ((A, 0.0), (-1, 1), w2 / 2 - t / 2),
        ((a, 0.0), (1, 1), w2 / 2 - t / 2),
    ]
    _corner_hips(plan, corners, dims)

    # The valley: V notch at the fascias' inside corner, double cheek in the
    # inside corner of what it meets at the top, seat inside the walls.
    pad = dims.valley.thickness_in / 2 + _SIDE
    tail = (
        Half((-1, 0), -(a - oh)),  # u >= a - oh
        Half((0, -1), -(b - oh)),  # v >= b - oh
    )
    if shape.equal:
        upper = ((Half((1, 0), uV - tr / 2),), (Half((0, 1), vH - tr / 2),))
    else:
        upper = ((Half((1, 0), uV - tr / 2),), (Half((1, 1), A + b - hh),))
    strip = Strip((a, b), (1, 1), pad, (tail,), upper)
    plan.lines.append(
        LineMember(
            "valley",
            strip,
            top,
            dims.m,
            _rip(dims, dims.valley, 0.0, top),
            _seat(strip, (a, b), (1, 1), pad, dims, reflex=True),
        )
    )
    if not shape.equal:
        # Hip N1 -> N2: ends at N2's inside corner (double cheek), and at N1
        # on V's ridge end, wrapped round its top-left corner.
        pad_h = dims.hip.thickness_in / 2 + _SIDE
        n1 = (uV, vT)
        lower = ((Half((0, -1), -(vT + t / 2)), Half((1, 0), uV - tr / 2)),)
        upper6 = ((Half((-1, 0), -(uR + t / 2)),), (Half((0, 1), vH - t / 2),))
        hip6 = Strip(n1, (-1, 1), pad_h, lower, upper6)
        z0 = top + dims.k * (w2 / 2) - dims.m * dims.hip.thickness_in / 2
        plan.lines.append(LineMember("hip", hip6, z0, dims.m, None, None))
    return plan


def _rip(
    dims: Dims, profile: LumberProfile, inside: float, z0: float
) -> tuple[float, float] | None:
    """ROOF-HIP-TAIL: where a hip's or valley's ripped tail steps back to its
    full depth, and the ripped plumb depth (the commons' less the drop). The
    step is inside both walls, where the seat cuts everything below the plate,
    so it leaves no face. *inside*: the least s at which the member's whole
    width is inside the walls; *z0* its top at s 0."""
    if dims.overhang <= 0.0:
        return None
    depth = dims.plumb - dims.m * profile.thickness_in / 2
    # The ripped bottom reaches the plate at s_max.
    s_max = (dims.plate - z0 + depth) / dims.m
    if s_max - inside < 1e-3:
        raise unsupported(
            "This pitch and rafter leave no room to rip a hip's tail.", "pitch"
        )
    return ((inside + s_max) / 2, depth)


def _seat(
    strip: Strip, origin: Vec2, direction: Dir, pad: float, dims: Dims, *, reflex: bool
) -> Strip:
    """The region below the plate inside the walls' outer faces, around a hip
    (its corner's quadrant) or a valley (outside its reflex corner's notch),
    over the member's whole length. With no overhang its edge runs PAST out,
    off the member's own end."""
    out = PAST if dims.overhang <= 0.0 else 0.0
    du, dv = direction
    cu, cv = origin
    walls = (
        Half((-du, 0), -(du * cu - out)),  # (u - cu) du >= -out
        Half((0, -dv), -(dv * cv - out)),  # (v - cv) dv >= -out
    )
    lower = (walls,) if reflex else ((walls[0],), (walls[1],))
    s_end = max(strip.hi(q) for q in strip.stations()) + PAST
    far = (Half(direction, direction[0] * cu + direction[1] * cv + s_end * _R2),)
    return Strip(origin, direction, pad, lower, (far,))


def _corner_hips(
    plan: Plan, corners: list[tuple[Vec2, Dir, float]], dims: Dims
) -> None:
    oh = dims.overhang
    pad = dims.hip.thickness_in / 2 + _SIDE
    z0 = dims.plate + dims.hap - dims.m * dims.hip.thickness_in / 2
    for (cu, cv), (du, dv), run in corners:
        # Along each wall from the corner: -oh (the fascia corner) .. run (the
        # inside corner of the ridge-end and king commons).
        lower = (
            (Half((-du, 0), oh - du * cu),),
            (Half((0, -dv), oh - dv * cv),),
        )
        upper = (
            (Half((du, 0), run + du * cu),),
            (Half((0, dv), run + dv * cv),),
        )
        strip = Strip((cu, cv), (du, dv), pad, lower, upper)
        plan.lines.append(
            LineMember(
                "hip",
                strip,
                z0,
                dims.m,
                _rip(dims, dims.hip, dims.hip.thickness_in / 2, z0),
                _seat(strip, (cu, cv), (du, dv), pad, dims, reflex=False),
            )
        )


# --- Rafters on an eave -------------------------------------------------------------


@dataclass(frozen=True)
class EaveMember:
    kind: Kind
    eave: Eave
    centre: float
    profile: list[Vec2]  # (d, z)
    cutter: list[Vec2] | None  # canonical plan polygon, or None
    run: float  # plan run on the centreline, for the line length


def _band_strip(
    eave: Eave, c: float, width: float, low: Sequence[Half], up: Half
) -> Strip:
    return Strip(
        eave.at(c, 0.0),
        eave.inward,
        width,
        tuple((h,) for h in low),
        ((up,),),
    )


def _shift(face: Half, by: float) -> Half:
    """*face* moved *by* (in, square to it) away from its inside."""
    return Half(face.n, face.c + by * _norm(face.n))


def eave_members(eave: Eave, dims: Dims) -> list[EaveMember]:
    """Each layout line of *eave* that frames, as its member (module
    docstring: common, jack, valley jack or cripple)."""
    t, oh, seat = dims.t, dims.overhang, dims.seat
    half = t / 2
    out: list[EaveMember] = []
    for c in eave.positions:
        piece = next(
            (
                p
                for p in eave.pieces
                if p.p0 - 1e-9 <= c - half and c + half <= p.p1 + 1e-9
            ),
            None,
        )
        if piece is None:
            continue
        exact = _band_strip(eave, c, half, [eave.fascia(-oh)], piece.face)
        hi_min = min(exact.hi(q) for q in exact.stations())
        hi_max = max(exact.hi(q) for q in exact.stations())
        vstrip = (
            None
            if eave.valley is None
            else _band_strip(eave, c, half, [eave.valley], piece.face)
        )
        if vstrip is not None:
            v_max = max(vstrip.lo(q) for q in vstrip.stations())
            v_min = min(vstrip.lo(q) for q in vstrip.stations())
        else:
            v_max = v_min = -math.inf
        cheek = v_max > -oh - _EPS
        if v_max <= -oh - _EPS or (oh > 0.0 and v_max <= -_CLEAR):
            bears = True
        elif v_min >= seat + _CLEAR:
            bears = False
        else:
            continue
        lows = [eave.fascia(-oh - PAST)]
        if cheek:
            assert eave.valley is not None
            lows.append(eave.valley)
        if bears:
            if hi_min < seat + _CLEAR:
                continue
        elif hi_min - v_max < _MIN_RUN:
            continue
        top = _shift(piece.face, PAST) if piece.square else piece.face
        cutter = _band_strip(eave, c, half + _SIDE, lows, top)
        if cutter.gap() < _CLEAR:
            continue
        ridge_end = hi_max if piece.square else hi_max + PAST
        common = dims.common
        if bears:
            rafter = Rafter(
                rise=common.rise,
                depth=common.depth,
                plate_height=common.plate_height,
                plate_width=common.plate_width,
                ridge_face=ridge_end,
                overhang=oh,
            )
            profile = rafter.profile()
            low_c = max(-oh, exact.lo(0.0))
            if cheek and vstrip is not None:
                low_c = max(low_c, vstrip.lo(0.0))
            kind: Kind = "common" if piece.square else "jack"
        else:
            d0 = v_min - PAST
            bottom0 = common.bottom(d0)
            bottom1 = common.bottom(ridge_end)
            pd = common.plumb_depth
            profile = [
                (d0, bottom0),
                (ridge_end, bottom1),
                (ridge_end, bottom1 + pd),
                (d0, bottom0 + pd),
            ]
            assert vstrip is not None
            low_c = vstrip.lo(0.0)
            kind = "valley_jack" if piece.square else "cripple"
        needs_cutter = cheek or not piece.square or not bears
        out.append(
            EaveMember(
                kind,
                eave,
                c,
                profile,
                cutter.outline() if needs_cutter else None,
                exact.hi(0.0) - low_c,
            )
        )
    return out


# --- Emission ----------------------------------------------------------------------

_ORDER = ("common", "jack", "valley_jack", "cripple")


def _side_plane(b: Builder, iso: Iso, eave: Eave, c: float, t: float) -> PlaneRef:
    """The datum a rafter centred at *c* is sketched on: its low-X face (YZ,
    extruded +X) or its high-Y face (XZ, normal -Y)."""
    p0 = iso.point(eave.at(c - t / 2, 0.0))
    p1 = iso.point(eave.at(c + t / 2, 0.0))
    if abs(p0[0] - p1[0]) > 1e-9:
        return b.plane("YZ", min(p0[0], p1[0]))
    return b.plane("XZ", -max(p0[1], p1[1]))


def _side_outline(iso: Iso, eave: Eave, c: float, profile: list[Vec2]) -> list[Vec2]:
    """A side profile's (d, z) on its datum's (u, v): u the world coordinate
    across the wall, v Z."""
    inward = iso.dir(eave.inward)
    axis = 0 if inward[0] != 0 else 1
    return [(iso.point(eave.at(c, d))[axis], z) for d, z in profile]


def _world(iso: Iso, outline: list[Vec2]) -> list[Vec2]:
    return ccw([iso.exact(p) for p in outline])


def _line_outline(corner: Corner, profile: list[Vec2]) -> list[Vec2]:
    """A hip's or valley's (s, z) profile on its midplane datum's (u, v), as
    geometry resolves that datum (roof.py's ``_hip_outline``)."""
    hx, hy = corner.direction
    ny = -hx * hy
    norm = math.sqrt(1.0 + ny * ny)
    v_axis = (ny / norm, -1.0 / norm)
    out: list[Vec2] = []
    for s, z in profile:
        dx, dy = hx * s / _R2, hy * s / _R2
        out.append((z, dx * v_axis[0] + dy * v_axis[1]))
    return out


def _line_profile(member: LineMember, plumb: float) -> list[Vec2]:
    """(s, z) counter-clockwise: the top line and the depth below it, run
    PAST past both ends, with the ripped tail stepping to full depth."""
    strip = member.strip
    qs = strip.stations()
    lo = min(strip.lo(q) for q in qs) - PAST
    hi = max(strip.hi(q) for q in qs) + PAST

    def top(s: float) -> float:
        return member.z0 + member.slope * s

    if member.rip is None:
        return [
            (lo, top(lo) - plumb),
            (hi, top(hi) - plumb),
            (hi, top(hi)),
            (lo, top(lo)),
        ]
    step, depth = member.rip
    return [
        (lo, top(lo) - depth),
        (step, top(step) - depth),
        (step, top(step) - plumb),
        (hi, top(hi) - plumb),
        (hi, top(hi)),
        (lo, top(lo)),
    ]


def hip_roof(inputs: ExpandInputs, fp: Footprint, typed: bool) -> list[Member]:
    rise = {pitch_value(r): r for r in PITCHES}[inputs.choice("pitch")]
    dims = Dims(
        rise=rise,
        plate=fp.plate_height,
        plate_width=fp.plate_width,
        spacing=inches("spacing_mm", inputs),
        overhang=inches("overhang_mm", inputs),
        rafter=inputs.lumber("rafter_profile"),
        ridge=inputs.lumber("ridge_profile"),
        hip=inputs.lumber("hip_profile"),
        valley=inputs.lumber("valley_profile"),
    )
    plumb = dims.plumb
    if dims.ridge.width_in < plumb:
        raise unsupported(
            f"The ridge board must be at least as deep as the rafters' plumb cut "
            f"({plumb:.3f} in): choose a deeper ridge or a shallower rafter or pitch.",
            "ridge_profile",
        )
    if dims.hip.width_in < plumb:
        raise unsupported(
            f"The hips must be at least as deep as the commons' plumb cut "
            f"({plumb:.3f} in): choose a deeper hip.",
            "hip_profile",
        )
    if typed:
        span = fp.corners[2][1]
        length = fp.corners[1][0]
        if length - span < dims.t - 1e-9:
            raise unsupported(
                f"A hip roof's length must be at least its span plus one rafter "
                f"thickness ({span + dims.t:g} in), so the ridge-end commons do not "
                "overlap: lengthen it, or swap span and length.",
                "length_mm",
            )
    shape = canonical(fp, dims.t)
    if shape.is_l and dims.valley.width_in < plumb:
        raise unsupported(
            f"The valleys must be at least as deep as the commons' plumb cut "
            f"({plumb:.3f} in): choose a deeper valley.",
            "valley_profile",
        )
    plan = frame_plan(shape, dims)
    rafters = [m for e in plan.eaves for m in eave_members(e, dims)]
    total = len(rafters) + len(plan.lines) + len(plan.boards)
    if total > MAX_ROOF_MEMBERS:
        raise unsupported(
            f"This roof would frame {total} members; one Roof frames at most "
            f"{MAX_ROOF_MEMBERS}: widen the spacing, or split the roof.",
            "spacing_mm",
        )
    return _emit(inputs, shape, dims, plan, rafters)


def _emit(
    inputs: ExpandInputs,
    shape: Shape,
    dims: Dims,
    plan: Plan,
    rafters: list[EaveMember],
) -> list[Member]:
    iso = shape.iso
    b = Builder(inputs)
    t = dims.t
    rafter_meta = MemberMetadata(
        profile=dims.rafter.name, material=inputs.material("rafter_material")
    )
    ridge_mat = inputs.material("ridge_material")
    height = max(board.top for board in plan.boards) + HEADROOM
    low = min(
        dims.plate
        - dims.k * (dims.overhang + 2 * PAST)
        - 2 * dims.line_plumb(dims.hip)
        - 2 * dims.line_plumb(dims.valley)
        - 1.0,
        0.0,
    )
    base: PlaneRef = (
        DatumPlaneRef(kind="datum_plane", plane="XY")
        if low == 0.0
        else b.plane("XY", low)
    )

    def prism(outline: list[Vec2], up_to: float) -> FeatureRef:
        section = b.sketch(base, _world(iso, outline))
        return b.extrude("cutter", section, up_to - low)

    order = {kind: i for i, kind in enumerate(_ORDER)}
    ranked = sorted(
        enumerate(rafters),
        key=lambda item: (order[item[1].kind], -round(item[1].run, 6), item[0]),
    )
    for _, member in ranked:
        plane = _side_plane(b, iso, member.eave, member.centre, t)
        section = b.sketch(
            plane, _side_outline(iso, member.eave, member.centre, member.profile)
        )
        body = b.extrude(member.kind, section, t, rafter_meta)
        if member.cutter is not None:
            b.trim(body, prism(member.cutter, height), "intersect")

    for kind in ("hip", "valley"):
        profile = dims.hip if kind == "hip" else dims.valley
        meta = MemberMetadata(profile=profile.name, material=ridge_mat)
        plumb = dims.line_plumb(profile)
        for line in (ln for ln in plan.lines if ln.kind == kind):
            point = iso.point(line.strip.origin)
            corner = Corner(point, iso.dir(line.strip.direction))
            y, flip = hip_sides(corner)
            mid = b.add(
                "plane",
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumMidplaneParams(
                        kind="midplane",
                        a=b.plane("YZ", point[0]),
                        b=b.plane("XZ", -y, flip=flip),
                    ),
                ),
            )
            section = b.sketch(mid, _line_outline(corner, _line_profile(line, plumb)))
            body = b.extrude(kind, section, profile.thickness_in, meta, symmetric=True)
            b.trim(body, prism(line.strip.outline(), height), "intersect")
            if line.seat is not None:
                b.trim(body, prism(line.seat.outline(), dims.plate), "subtract")

    ridge_meta = MemberMetadata(profile=dims.ridge.name, material=ridge_mat)
    boards = sorted(plan.boards, key=lambda bd: -max(bd.u1 - bd.u0, bd.v1 - bd.v0))
    for board in boards:
        p0 = iso.point((board.u0, board.v0))
        p1 = iso.point((board.u1, board.v1))
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        bottom = board.top - dims.ridge.width_in
        if x1 - x0 >= y1 - y0:
            plane = b.plane("YZ", x0)
            outline = [(y0, bottom), (y1, bottom), (y1, board.top), (y0, board.top)]
            length = x1 - x0
        else:
            plane = b.plane("XZ", -y1)
            outline = [(x0, bottom), (x1, bottom), (x1, board.top), (x0, board.top)]
            length = y1 - y0
        section = b.sketch(plane, outline)
        b.extrude("ridge", section, length, ridge_meta)
    return b.members


def typed_footprint(inputs: ExpandInputs) -> Footprint:
    """1.1.0's typed bearing: walls' outer faces X 0..length, Y 0..span."""
    span = inches("span_mm", inputs)
    length = inches("length_mm", inputs)
    return Footprint(
        ((0.0, 0.0), (length, 0.0), (length, span), (0.0, span)),
        inches("plate_height_mm", inputs),
        inches("plate_width_mm", inputs),
    )


def expand_v1_2(inputs: ExpandInputs) -> Iterable[Member]:
    overhang = inches("overhang_mm", inputs)
    if 0.0 < overhang < MIN_OVERHANG_IN - 1e-9:
        raise unsupported(
            "The eave overhang must be 0 (cut flush at the wall) or at least 1/16 in.",
            "overhang_mm",
        )
    style = inputs.choice("style")
    picked = footprint_from_walls(inputs) if style == STYLE_HIP else None
    if style == STYLE_GABLE:
        if inputs.features("walls"):
            raise _walls_error(
                "A gable bears on its typed span and length: leave Walls empty, or "
                "choose Style Hip to roof the walls you picked."
            )
        return list(expand(inputs))
    if style != STYLE_HIP:
        raise unsupported(f"{style!r} is not a roof style", "style")
    if picked is None:
        return hip_roof(inputs, typed_footprint(inputs), typed=True)
    return hip_roof(inputs, picked, typed=False)


ROOF_V1_2 = Plugin(MANIFEST_V1_2, expand_v1_2)
