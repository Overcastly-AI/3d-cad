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

**1.3.0 names** (ROOF-MEMBER-RENUMBER, RESEARCH §23): 1.2.0's members in
1.2.0's order with 1.2.0's geometry, each named by its place, so lengthening,
re-spacing, re-pitching or re-picking the walls never hands one member's id
to another. A plane is named by the way its wall faces in the world
(``front`` is -Y, ``left`` -X; ``_notch`` for the two walls at an L's inside
corner); a layout line by its plane and slot: ``<plane>/ridge/start`` (the
ridge-end common, the layout's origin), ``.../ridge/slot/n`` at n spacings
from it, ``.../ridge/end`` (the flush far one), ``<plane>/king``, and
``<plane>/<other>/n`` for the n-th line from the end common toward the hip
it shares with plane *other*. A hip, valley or ridge is named by the two
planes it divides (``back/left``). No name embeds a feature id. Two layout
lines within 1e-9 in are one. 1.2.0 frames one too (ROOF-L-DOUBLED-COMMON):
it lays the ulp-off twin out and numbers it as before, then drops its own
features, so every other member keeps its id.

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
    DatumFeature,
    DatumMidplaneParams,
    DatumPlaneRef,
    FeatureRef,
)
from loft_wire.lumber import LumberProfile
from loft_wire.plugins import (
    ChoiceInput,
    FeatureListInput,
    MemberMetadata,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
)

from loft_plugins.api import ExpandInputs, Member, Plugin, lumber_options
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
    gable,
    hip_sides,
    inches,
    material_input,
    pitch_value,
    unsupported,
)
from loft_plugins.builtin.roof_footprint import (
    MAX_ROOF_WALLS,
    Dir,
    Footprint,
    Iso,
    Shape,
    Vec2,
    canonical,
    footprint_from_walls,
    walls_error,
)

_R2 = math.sqrt(2.0)
#: How far (in) a cutter prism runs past a member's sides.
_SIDE = 0.5
#: The least clearance (in) a cheek keeps from a seat, and a member's least
#: clear run where it is shortest.
_CLEAR = 1.0 / 16.0
#: A layout line is framed only if its member is at least this long (in, plan
#: run at its short side).
_MIN_RUN = 2.0

_DIGITS = 9
_EPS = 1e-6
#: Most framing members one roof frames (ROOF-HIP-SIZE: a 201-member hip took
#: 32 s of the gateway's 90).
MAX_ROOF_MEMBERS = 160


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
    #: 1.3.0: the plane's name (``front``, ``left_notch``) and each layout
    #: line's slot (``ridge/slot/2``, ``king``, ``left/1``), with *positions*.
    name: str = ""
    names: tuple[str, ...] = ()
    #: 1.2.0 (ROOF-L-DOUBLED-COMMON): the positions in *positions* within
    #: 1e-9 in of a line 1.3.0 keeps. Laid out and numbered as before, then
    #: dropped, so every other member keeps its index.
    twins: frozenset[float] = frozenset()

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
    #: The two planes it divides (1.3.0's name: ``back/left``).
    name: str = ""


@dataclass(frozen=True)
class Board:
    """A ridge board: canonical box and its top."""

    u0: float
    u1: float
    v0: float
    v1: float
    top: float
    #: The two planes it divides (1.3.0's name: ``back/front``).
    name: str = ""


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


#: 1.3.0's slack between two layout lines that are one (in): two series can
#: reach one place by different sums (ROOF-MEMBER-RENUMBER).
_TOUCH = 1e-9
#: A layout line's place: its position along the eave and its slot's name.
Slot = tuple[float, str]
#: A king common's slot (the ridge-end common on an end wall).
KING = "king"
_FACING: dict[Dir, str] = {
    (0, -1): "front",
    (0, 1): "back",
    (-1, 0): "left",
    (1, 0): "right",
}


def eave_name(iso: Iso, inward: Dir, notch: bool = False) -> str:
    """A plane's 1.3.0 name: the way its wall faces in the WORLD (``front`` is
    -Y, ``left`` -X), ``_notch`` for the two walls at an L's inside corner.
    It does not depend on the canonical frame, so neither picking the walls
    in another order nor an arm growing past the other renames a plane."""
    world = iso.dir(inward)
    return _FACING[(-world[0], -world[1])] + ("_notch" if notch else "")


def pair(a: str, b: str) -> str:
    """A hip's, valley's or ridge's 1.3.0 name: the two planes it divides."""
    return "/".join(sorted((a, b)))


def ridge_slots(p0: float, p1: float, spacing: float, t: float) -> list[Slot]:
    """:func:`ridge_layout` named: ``ridge/start`` (the ridge-end common at
    *p0*, the layout's origin), ``ridge/slot/n`` at ``n x spacing`` from it
    and ``ridge/end`` (the flush one at *p1*)."""
    layout = ridge_layout(p0, p1, spacing, t)
    names = ["ridge/start", *(f"ridge/slot/{n}" for n in range(1, len(layout)))]
    if len(layout) > 1 and layout[-1] == p1:
        names[-1] = "ridge/end"
    return list(zip(layout, names, strict=True))


def jack_slots(
    p: float, spacing: float, sign: int, limit: float, toward: str
) -> list[Slot]:
    """:func:`_outward` named: ``<toward>/n``, the jack *n* spacings from the
    end common at *p* toward the hip it shares with the plane *toward*."""
    return [
        (c, f"{toward}/{n}")
        for n, c in enumerate(_outward(p, spacing, sign, limit), start=1)
    ]


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


def frame_plan(shape: Shape, dims: Dims, named: bool = False) -> Plan:
    """The roof's ridges, planes and hips/valleys on the canonical shape.
    *named* (1.3.0): every layout line carries its slot's name, and layout
    lines within 1e-9 in of each other are one (module docstring)."""
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
    iso = shape.iso
    # The planes' names, by the way each faces in the world (module docstring).
    n_back, n_left = eave_name(iso, (0, -1)), eave_name(iso, (1, 0))
    n_right = eave_name(iso, (-1, 0))
    n_front = eave_name(iso, (0, 1), notch=shape.is_l)
    plan.boards.append(
        Board(
            uL - t / 2,
            uR + t / 2,
            vH - tr / 2,
            vH + tr / 2,
            h_top,
            pair(n_back, n_front),
        )
    )
    h_layout = ridge_slots(uL, uR, s, t)

    def eave(
        origin: Vec2,
        along: Dir,
        inward: Dir,
        slots: Sequence[Sequence[Slot]],
        tops: Sequence[tuple[float, float, Dir, float, float, bool]],
        valley: tuple[Dir, float] | None = None,
        *,
        name: str,
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
        # One layout line per place: the first group's (a king, then a ridge
        # layout, then the jacks) wins a place two groups reach within 1e-9.
        kept: list[Slot] = []
        for group in slots:
            for p, label in group:
                if all(abs(p - q) > _TOUCH for q, _ in kept):
                    kept.append((p, label))
        kept.sort()
        if not named:
            positions = tuple(sorted({p for group in slots for p, _ in group}))
            twins = frozenset(positions) - {p for p, _ in kept}
            return Eave(origin, along, inward, positions, pieces, low, twins=twins)
        return Eave(
            origin,
            along,
            inward,
            tuple(p for p, _ in kept),
            pieces,
            low,
            name,
            tuple(label for _, label in kept),
        )

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
            [
                h_layout,
                jack_slots(uL, s, -1, -oh, n_left),
                jack_slots(uR, s, 1, A + oh, n_right),
            ],
            [
                (-inf, uL - t / 2, *h_top_left, th2, False),
                ridge_top,
                (uR + t / 2, inf, *h_top_right, th2, False),
            ],
            name=n_back,
        )
    )
    plan.eaves.append(
        eave(
            (0.0, 0.0),
            (0, 1),
            (1, 0),
            [
                [(vH, KING)],
                jack_slots(vH, s, -1, b - oh, n_front),
                jack_slots(vH, s, 1, B + oh, n_back),
            ],
            [
                (-inf, vH - t / 2, *h_low_left, th2, False),
                king_left,
                (vH + t / 2, inf, *h_top_left, th2, False),
            ],
            name=n_left,
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
                [
                    h_layout,
                    jack_slots(uL, s, -1, -oh, n_left),
                    jack_slots(uR, s, 1, A + oh, n_right),
                ],
                [
                    (-inf, uL - t / 2, *h_low_left, th2, False),
                    ridge_low,
                    (uR + t / 2, inf, *h_low_right, th2, False),
                ],
                name=n_front,
            )
        )
        plan.eaves.append(
            eave(
                (A, 0.0),
                (0, 1),
                (-1, 0),
                [
                    [(vH, KING)],
                    jack_slots(vH, s, -1, -oh, n_front),
                    jack_slots(vH, s, 1, B + oh, n_back),
                ],
                [
                    (-inf, vH - t / 2, *h_low_right, th2, False),
                    king_right,
                    (vH + t / 2, inf, *h_top_right, th2, False),
                ],
                name=n_right,
            )
        )
        corners.append(((A, 0.0), (-1, 1), w1 / 2 - t / 2))
        _corner_hips(plan, corners, dims)
        return plan

    # The L: V arm, valley, and (unequal) the hip N1 -> N2.
    n_wing_left = eave_name(iso, (1, 0), notch=True)
    n_wing_front = eave_name(iso, (0, 1))
    w2 = shape.w2
    uV, vB = (uR if shape.equal else a + w2 / 2), w2 / 2
    vT = vH if shape.equal else b + w2 / 2
    v_top = top + dims.k * (w2 / 2 - tr / 2)
    v_end = vH - tr / 2 if shape.equal else vT + t / 2
    plan.boards.append(
        Board(
            uV - tr / 2,
            uV + tr / 2,
            vB - t / 2,
            v_end,
            v_top,
            pair(n_wing_left, n_right),
        )
    )
    v_layout = ridge_slots(vB, vT, s, t)
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
    mf_slots = [h_layout, jack_slots(uL, s, -1, -oh, n_left)]
    if not shape.equal:
        mf_tops.append((uR + t / 2, uV - tr / 2, *h6, th2, False))
        mf_slots.append(jack_slots(uR, s, 1, uV, n_right))
    plan.eaves.append(
        eave((0.0, b), (1, 0), (0, 1), mf_slots, mf_tops, valley_line, name=n_front)
    )
    # Wing left (u = a, v 0..b).
    plan.eaves.append(
        eave(
            (a, 0.0),
            (0, 1),
            (1, 0),
            [v_layout, jack_slots(vB, s, -1, -oh, n_wing_front)],
            [(-inf, vB - t / 2, *h5, th2, False), v_left],
            valley_line,
            name=n_wing_left,
        )
    )
    # Wing front (v = 0, u a..A): V's hipped end.
    plan.eaves.append(
        eave(
            (0.0, 0.0),
            (1, 0),
            (0, 1),
            [
                [(uV, KING)],
                jack_slots(uV, s, -1, a - oh, n_wing_left),
                jack_slots(uV, s, 1, A + oh, n_right),
            ],
            [
                (-inf, uV - t / 2, *h5, th2, False),
                v_king,
                (uV + t / 2, inf, *h4, th2, False),
            ],
            name=n_wing_front,
        )
    )
    # Right (u = A, v 0..B).
    r_tops: list[tuple[float, float, Dir, float, float, bool]] = [
        (-inf, vB - t / 2, *h4, th2, False),
        v_right,
    ]
    r_slots = [
        [(vH, KING)],
        v_layout,
        jack_slots(vB, s, -1, -oh, n_wing_front),
        jack_slots(vH, s, 1, B + oh, n_back),
    ]
    if not shape.equal:
        r_tops.append((vT + t / 2, vH - t / 2, *h6, th2, False))
        r_slots.append(jack_slots(vH, s, -1, vT, n_front))
    r_tops += [king_right, (vH + t / 2, inf, *h_top_right, th2, False)]
    if shape.equal:
        r_tops = [
            (-inf, vB - t / 2, *h4, th2, False),
            (vB - t / 2, vH - tr / 2, (1, 0), uV + tr / 2, 0.0, True),
            king_right,
            (vH + t / 2, inf, *h_top_right, th2, False),
        ]
    plan.eaves.append(eave((A, 0.0), (0, 1), (-1, 0), r_slots, r_tops, name=n_right))

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
            pair(n_front, n_wing_left),
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
        plan.lines.append(
            LineMember("hip", hip6, z0, dims.m, None, None, pair(n_front, n_right))
        )
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
        # The two planes whose walls meet at the corner.
        meeting = [
            e.name
            for e in plan.eaves
            if abs(e.inward[0] * (cu - e.origin[0]) + e.inward[1] * (cv - e.origin[1]))
            < _TOUCH
        ]
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
                pair(*meeting) if len(meeting) == 2 else "",
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
    #: 1.3.0: ``<plane>/<slot>`` (``front/ridge/slot/2``, ``left/front/1``).
    name: str | None = None
    #: 1.2.0: an ulp-off twin of a kept line, dropped once numbered
    #: (:attr:`Eave.twins`).
    twin: bool = False


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
    for i, c in enumerate(eave.positions):
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
                f"{eave.name}/{eave.names[i]}" if eave.names else None,
                c in eave.twins,
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
    return [(iso.exact(eave.at(c, d))[axis], z) for d, z in profile]


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


def hip_roof(
    inputs: ExpandInputs, fp: Footprint, typed: bool, named: bool = False
) -> list[Member]:
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
    plan = frame_plan(shape, dims, named)
    rafters = [m for e in plan.eaves for m in eave_members(e, dims)]
    total = len(rafters) + len(plan.lines) + len(plan.boards)
    if total > MAX_ROOF_MEMBERS:
        raise unsupported(
            f"This roof would frame {total} members; one Roof frames at most "
            f"{MAX_ROOF_MEMBERS}: widen the spacing, or split the roof.",
            "spacing_mm",
        )
    return _emit(inputs, shape, dims, plan, rafters, named)


def _emit(
    inputs: ExpandInputs,
    shape: Shape,
    dims: Dims,
    plan: Plan,
    rafters: list[EaveMember],
    named: bool = False,
) -> list[Member]:
    """The members, in 1.2.0's order. *named* (1.3.0): a body by its place
    (``member.name``), its section ``<role>/<name>``, its k-th cutter and
    trim ``<role>/<name>/<k>`` (the cutter's section ``cutter/...``), a hip's
    or valley's midplane ``<role>/<name>``; offset datums by their offset
    (:class:`~loft_plugins.builtin.roof.Builder`)."""
    iso = shape.iso
    b = Builder(inputs, named)
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

    def prism(outline: list[Vec2], up_to: float, name: str) -> FeatureRef:
        section = b.sketch(base, _world(iso, outline), f"cutter/{name}")
        return b.extrude("cutter", section, up_to - low, name=name)

    order = {kind: i for i, kind in enumerate(_ORDER)}
    ranked = sorted(
        enumerate(rafters),
        key=lambda item: (order[item[1].kind], -round(item[1].run, 6), item[0]),
    )
    dropped: set[int] = set()
    for _, member in ranked:
        start = len(b.members)
        key = f"{member.kind}/{member.name}"
        plane = _side_plane(b, iso, member.eave, member.centre, t)
        section = b.sketch(
            plane,
            _side_outline(iso, member.eave, member.centre, member.profile),
            key,
        )
        body = b.extrude(member.kind, section, t, rafter_meta, name=member.name)
        if member.cutter is not None:
            cut = f"{key}/0"
            b.trim(body, prism(member.cutter, height, cut), "intersect", cut)
        if member.twin:
            dropped.update(range(start, len(b.members)))

    for kind in ("hip", "valley"):
        profile = dims.hip if kind == "hip" else dims.valley
        meta = MemberMetadata(profile=profile.name, material=ridge_mat)
        plumb = dims.line_plumb(profile)
        for line in (ln for ln in plan.lines if ln.kind == kind):
            key = f"{kind}/{line.name}"
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
                name=key,
            )
            section = b.sketch(
                mid, _line_outline(corner, _line_profile(line, plumb)), key
            )
            body = b.extrude(
                kind,
                section,
                profile.thickness_in,
                meta,
                symmetric=True,
                name=line.name,
            )
            b.trim(
                body,
                prism(line.strip.outline(), height, f"{key}/0"),
                "intersect",
                f"{key}/0",
            )
            if line.seat is not None:
                seat = prism(line.seat.outline(), dims.plate, f"{key}/1")
                b.trim(body, seat, "subtract", f"{key}/1")

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
        section = b.sketch(plane, outline, f"ridge/{board.name}")
        b.extrude("ridge", section, length, ridge_meta, name=board.name)
    return _drop_twins(inputs, b.members, dropped)


def _drop_twins(
    inputs: ExpandInputs, members: list[Member], dropped: set[int]
) -> list[Member]:
    """*members* less the features only an ulp-off twin made
    (ROOF-L-DOUBLED-COMMON): its datum, section, body, cutter and trim. The
    rest keep their ``(role, index)``, so their ids; a feature that named the
    twin finds its member gone, as SolidWorks flags a dangling reference,
    never rebound. A twin's feature another member uses is kept."""
    if not dropped:
        return members
    ids = {
        i: str(inputs.ref(m.role, m.index, m.name).feature_id)
        for i, m in enumerate(members)
        if i in dropped
    }
    used = {
        i
        for i, fid in ids.items()
        for j, m in enumerate(members)
        if j not in dropped and fid in m.feature.model_dump_json()
    }
    gone = dropped - used
    return [m for i, m in enumerate(members) if i not in gone]


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
    return _expand(inputs, named=False)


def expand_v1_3(inputs: ExpandInputs) -> Iterable[Member]:
    """1.3.0: 1.2.0's members in 1.2.0's order, each named by its place
    (ROOF-MEMBER-RENUMBER, module docstring)."""
    return _expand(inputs, named=True)


def _expand(inputs: ExpandInputs, named: bool) -> list[Member]:
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
            raise walls_error(
                "A gable bears on its typed span and length: leave Walls empty, or "
                "choose Style Hip to roof the walls you picked."
            )
        return list(gable(inputs, named))
    if style != STYLE_HIP:
        raise unsupported(f"{style!r} is not a roof style", "style")
    if picked is None:
        return hip_roof(inputs, typed_footprint(inputs), typed=True, named=named)
    return hip_roof(inputs, picked, typed=False, named=named)


#: 1.2.0 numbers in emission order (commons, then jacks, ... by run): a longer
#: roof, a new spacing, a pitch that frames another jack or a re-shaped
#: footprint moves the numbers of nearly every role. Its one valley is always
#: the L's (ROOF-MEMBER-RENUMBER).
_RENUMBERED_V1_2 = frozenset(
    {
        "plane",
        "section",
        "rafter",
        "common",
        "jack",
        "valley_jack",
        "cripple",
        "hip",
        "ridge",
        "cutter",
        "trim",
    }
)

ROOF_V1_2 = Plugin(MANIFEST_V1_2, expand_v1_2, renumbered_roles=_RENUMBERED_V1_2)

MANIFEST_V1_3 = MANIFEST_V1_2.model_copy(
    update={
        "version": "1.3.0",
        "description": MANIFEST_V1_2.description
        + " Each member keeps its name when the roof is lengthened, re-spaced or "
        "re-pitched.",
    }
)

ROOF_V1_3 = Plugin(MANIFEST_V1_3, expand_v1_3)
