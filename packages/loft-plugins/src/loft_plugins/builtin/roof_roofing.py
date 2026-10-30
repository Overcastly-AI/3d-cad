"""Roof 1.9.0's roofing: the deck, fascia and rake boards of a gable, and
what lies on the deck, listed (ROOFING, RESEARCH §23).

Chief Architect's roof planes carry a sheathing layer and a roofing layer,
with fascia on the eaves and a rake board up each gable; its Materials List
counts the roofing in squares and the drip edge by length. ``loft.roof``
1.9.0 adds **Roofing** to a gable on picked walls (an outline): None (the
default, as a wall's Exterior finish is: roofing is a material the user
picks, so a stored roof and every update stay as they were) or **Asphalt
shingles**, which builds:

* **The deck**: 7/16 OSB on each plane, its underside on the rafters' top
  plane, from the fascia's outer face up to the ridge line, square-cut
  (its edges square to the plane, as a sheet's are): the eave edge's
  underside on the fascia's face, the ridge edge's underside on the ridge
  line, so the two planes meet on that line with the vee a ridge vent
  leaves open. Along the ridge it is flush with the end walls' sheathing
  (the gable OSB's outer face; the framing's when unsheathed). Courses of
  48 in run up from the eave, the last ripped; each course's sheets are
  8 ft at most, every end joint CENTRED ON A RAFTER (APA: a panel end
  bears on framing, its nails 3/8 in in), and the courses staggered 4 ft:
  even courses start with a sheet of up to 8 ft, odd ones with up to 4 ft,
  each to the farthest rafter centre it reaches.
* **Fascia**: a 1x board on each eave's tail plumb cuts, the smallest 1x
  whose width covers the plumb cut (one size deeper: a 2x8 tail at 6/12,
  8.106 in plumb, takes a 1x10), its top level with the rafters' top plane
  at its outer face so the deck rests on its edge. It runs the deck's
  length in the fewest pieces of 16 ft stock or less, each joint centred on
  the rafter nearest an equal division.
* **Rake boards**: a 1x6 up each rake on the gable's outer face (on the
  sheathing), its top edge in the deck's top plane, plumb-cut at the
  fascia's face and at the ridge line: four on a gable. The end walls'
  corner boards and siding and the gable's siding it covers are cut to it,
  as a carpenter fits them under the rake trim (a cut of the board's own
  section from exactly the bodies it meets).
* **Listed, not drawn** (:mod:`loft_wire.roofing`): every deck panel
  carries the roof's waste allowance, so the cut list buys architectural
  shingles (3 bundles a square) and synthetic underlayment (10-square
  rolls) over the deck's measured area; the first panel of each plane lists
  its eave (drip edge and starter), its two rakes (drip edge) and, on the
  first plane, the ridge (ridge cap), by their lengths.

Trim takes the end walls' Exterior finish's trim material (fibre cement,
PVC or cedar), else SPF. A roof on its typed bearing, a hip, and a gable
with no eave overhang take no roofing (hips and valleys are a later rung;
an eave with no tails has nothing to hang a fascia on): the roof is 1.8.0's
and the form says so.
"""

import itertools
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH, LumberProfile, lumber_profile
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    ChoiceInput,
    ChoiceOption,
    CountInput,
    MemberMetadata,
    PluginInput,
    PluginMemberRole,
    member_id,
)
from loft_wire.roofing import (
    DEFAULT_ROOFING_WASTE_PERCENT,
    MAX_ROOFING_WASTE_PERCENT,
    RoofEdgeRun,
    RoofingTakeoff,
)
from loft_wire.sheet_goods import SHEET_GOODS_BY_KEY, SheetGood
from loft_wire.siding import SidingProduct
from loft_wire.sketch import Point2D, SketchEntity, SketchLine

from loft_plugins.api import ExpandInputs, Member
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.deck import joist_centres
from loft_plugins.builtin.house import OutlineWall
from loft_plugins.builtin.roof import GablePlace, Rafter, number_name, unsupported

ROOFING_NONE = "none"
ROOFING_SHINGLES = "asphalt_shingles"
#: The deck's product (the founder's default, 2026-10-30).
DECK_GOOD: SheetGood = SHEET_GOODS_BY_KEY["osb_7_16"]
#: A course is a sheet's width; a sheet's length the most a piece runs.
COURSE_IN = 48.0
SHEET_IN = 96.0
#: An odd course starts with a half sheet at most (staggered 4 ft).
HALF_IN = 48.0
#: The shortest piece of deck or fascia laid (in): a joint is never put
#: where it would leave less on either side.
MIN_PIECE_IN = 12.0
#: The longest fascia piece (in): 16 ft, the longest 1x board every yard
#: stocks in clear lengths; and the most any piece may be (20 ft stock).
FASCIA_PIECE_IN = 192.0
MAX_PIECE_IN = 240.0
#: The fascia sizes offered, shallowest first.
FASCIA_PROFILES = ("us_1x6", "us_1x8", "us_1x10", "us_1x12")
RAKE_PROFILE = "us_1x6"
#: What the trim is made of without a sided wall's trim material.
_PLAIN_TRIM: MaterialKey = "spf_lumber"
_DIGITS = 9
#: Overlap (in²) below which a body is not met by a rake board.
_MEETS_IN2 = 1e-4

ROOFING_INPUTS: list[PluginInput] = [
    ChoiceInput(
        kind="choice",
        name="roofing",
        label="Roofing",
        description="Gable on picked walls: Asphalt shingles decks the roof in "
        "7/16 OSB, hangs a 1x fascia on the tails and a 1x6 rake board up each "
        "gable, and lists architectural shingles by the bundle, synthetic "
        "underlayment by the roll, drip edge, starter and ridge cap (Chief "
        "Architect's roofing layer). A hip, a typed bearing or a roof with no "
        "eave overhang takes none.",
        options=[
            ChoiceOption(value=ROOFING_NONE, label="None"),
            ChoiceOption(value=ROOFING_SHINGLES, label="Asphalt shingles"),
        ],
        default=ROOFING_NONE,
    ),
    CountInput(
        kind="count",
        name="roofing_waste_percent",
        label="Roofing waste (%)",
        description="Ordered over the deck's area for the shingles and "
        "underlayment (cuts at the rakes and ridge, laps), then rounded up "
        "to whole bundles and rolls.",
        default=DEFAULT_ROOFING_WASTE_PERCENT,
        minimum=0,
        maximum=MAX_ROOFING_WASTE_PERCENT,
    ),
]

ROOFING_ROLES = [
    PluginMemberRole(
        role="deck",
        title="Roof deck",
        description="One 7/16 OSB panel of the roof deck.",
    ),
    PluginMemberRole(
        role="fascia",
        title="Fascia",
        description="One piece of an eave's fascia on the rafter tails.",
    ),
    PluginMemberRole(
        role="rake_board",
        title="Rake board",
        description="A 1x6 up one rake of a gable.",
    ),
]


def _mm(value: float) -> float:
    return value * MM_PER_INCH


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


def wants_roofing(inputs: ExpandInputs) -> bool:
    """Whether the roof asks for roofing (Roofing is not None)."""
    if "roofing" not in inputs.values:
        return False
    value = inputs.choice("roofing")
    if value == ROOFING_NONE:
        return False
    if value != ROOFING_SHINGLES:
        raise unsupported(f"{value!r} is not a roofing", "roofing")
    return True


def fascia_profile(rafter: Rafter) -> LumberProfile:
    """The smallest 1x whose width covers the tails' plumb cut."""
    for key in FASCIA_PROFILES:
        profile = lumber_profile(key)  # type: ignore[arg-type]
        if profile.width_in >= rafter.plumb_depth - 1e-9:
            return profile
    raise unsupported(
        f"The rafters' plumb cut ({rafter.plumb_depth:.3f} in) is deeper than a "
        "1x12 fascia: a 2x fascia is a later rung. Choose a shallower rafter "
        "or pitch, or Roofing None.",
        "roofing",
    )


# --- The geometry (pure, inches, in the front plane's (y, z)) ------------------------


@dataclass(frozen=True)
class Plane:
    """One gable plane's deck, in the front rafters' frame: ``y`` across
    from the low eave wall's framing face, ``z`` world. The back plane is
    its mirror about the ridge line."""

    rafter: Rafter
    span: float
    fascia_t: float

    @property
    def cos(self) -> float:
        return 12.0 / math.hypot(12.0, self.rafter.rise)

    @property
    def sin(self) -> float:
        return self.rafter.rise / math.hypot(12.0, self.rafter.rise)

    @property
    def eave(self) -> float:
        """The fascia's outer face (y)."""
        return -(self.rafter.overhang + self.fascia_t)

    def top(self, y: float) -> float:
        """The rafters' top plane: the deck's underside."""
        return self.rafter.bottom(y) + self.rafter.plumb_depth

    @property
    def slope_length(self) -> float:
        """Along the deck's underside, the fascia's face to the ridge line."""
        return (self.span / 2 - self.eave) / self.cos

    def courses(self) -> list[tuple[float, float]]:
        """Each course's (s0, s1) up the slope from the eave."""
        out: list[tuple[float, float]] = []
        s, total = 0.0, self.slope_length
        while s < total - 1e-6:
            out.append((s, min(s + COURSE_IN, total)))
            s += COURSE_IN
        return out

    def panel(self, s0: float, s1: float, t: float) -> list[tuple[float, float]]:
        """A course's section: square to the plane, *t* thick."""
        y, z = self.eave, self.top(self.eave)

        def at(s: float, n: float) -> tuple[float, float]:
            return (y + s * self.cos - n * self.sin, z + s * self.sin + n * self.cos)

        return [at(s0, 0.0), at(s1, 0.0), at(s1, t), at(s0, t)]

    def deck_top(self, y: float) -> float:
        """The deck's top plane over *y*."""
        return self.top(y) + DECK_GOOD.thickness_in / self.cos

    def rake(self, width: float) -> list[tuple[float, float]]:
        """A rake board's section: its top in the deck's top plane, plumb
        cut at the fascia's face and the ridge line."""
        y0, y1 = self.eave, self.span / 2
        drop = width / self.cos
        return [
            (y0, self.deck_top(y0) - drop),
            (y1, self.deck_top(y1) - drop),
            (y1, self.deck_top(y1)),
            (y0, self.deck_top(y0)),
        ]

    def fascia(self, width: float) -> list[tuple[float, float]]:
        """The fascia's section: on the tails' plumb cut, its top level with
        the rafters' top plane at its outer face."""
        y0, y1 = self.eave, -self.rafter.overhang
        z1 = self.top(y0)
        return [(y0, z1 - width), (y1, z1 - width), (y1, z1), (y0, z1)]


def joints(
    start: float,
    end: float,
    centres: Sequence[float],
    first_max: float,
    most: float,
) -> list[tuple[float, float]]:
    """A course's pieces from *start* to *end*: each to the farthest rafter
    centre it reaches (the first at most *first_max*, the rest *most*),
    leaving at least :data:`MIN_PIECE_IN` either side of every joint."""
    out: list[tuple[float, float]] = []
    a, reach = start, first_max
    while a + reach < end - 1e-9:
        ok = [
            c
            for c in centres
            if a + MIN_PIECE_IN <= c <= a + reach + 1e-9 and end - c >= MIN_PIECE_IN
        ]
        if not ok:
            raise unsupported(
                "The roof deck finds no rafter to joint a sheet on within "
                f"{reach:g} in: close the rafter spacing.",
                "spacing_mm",
            )
        out.append((a, max(ok)))
        a, reach = max(ok), most
    out.append((a, end))
    return out


def fascia_joints(
    start: float, end: float, centres: Sequence[float]
) -> list[tuple[float, float]]:
    """The fewest pieces of at most 16 ft, each joint on the rafter centre
    nearest an equal division."""
    n = max(1, math.ceil((end - start) / FASCIA_PIECE_IN - 1e-9))
    cuts: list[float] = []
    for k in range(1, n):
        ideal = start + (end - start) * k / n
        ok = [
            c
            for c in centres
            if c - (cuts[-1] if cuts else start) >= MIN_PIECE_IN
            and end - c >= MIN_PIECE_IN
        ]
        if not ok:
            raise unsupported("The fascia finds no rafter to joint on.", "spacing_mm")
        cuts.append(min(ok, key=lambda c: (abs(c - ideal), c)))
    edges = [start, *cuts, end]
    pieces = list(itertools.pairwise(edges))
    if any(b - a > MAX_PIECE_IN + 1e-9 for a, b in pieces):
        raise unsupported(
            "A fascia piece would pass 20 ft: close the rafter spacing.", "spacing_mm"
        )
    return pieces


# --- Overlap (a rake board against the bodies it may meet) --------------------------

Poly = list[tuple[float, float]]


def _clip(subject: Poly, clip: Poly) -> Poly:
    """*subject* clipped by the CONVEX counter-clockwise *clip*
    (Sutherland-Hodgman)."""

    def inside(
        p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
    ) -> bool:
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0.0

    def cross(
        p: tuple[float, float],
        q: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> tuple[float, float]:
        dx, dy = q[0] - p[0], q[1] - p[1]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = dx * ey - dy * ex
        t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
        return (p[0] + t * dx, p[1] + t * dy)

    out: Poly = subject
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        source: Poly = out
        out = []
        for k in range(len(source)):
            p, q = source[k - 1], source[k]
            if inside(q, a, b):
                if not inside(p, a, b):
                    out.append(cross(p, q, a, b))
                out.append(q)
            elif inside(p, a, b):
                out.append(cross(p, q, a, b))
        if not out:
            return []
    return out


def _area(poly: Poly) -> float:
    n = len(poly)
    return (
        sum(
            poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
            for i in range(n)
        )
        / 2.0
    )


def _ccw(poly: Poly) -> Poly:
    return poly if _area(poly) > 0 else list(reversed(poly))


def sketch_loops(sketch: SketchFeature) -> list[Poly]:
    """A sketch's closed loops of lines, in its (x, y) in inches."""
    loops: list[Poly] = []
    current: Poly = []
    first: tuple[float, float] | None = None
    for entity in sketch.params.entities:
        if not isinstance(entity, SketchLine):
            continue
        start = (entity.start.x / MM_PER_INCH, entity.start.y / MM_PER_INCH)
        end = (entity.end.x / MM_PER_INCH, entity.end.y / MM_PER_INCH)
        if first is None:
            first = start
        current.append(start)
        if math.dist(end, first) < 1e-9:
            loops.append(current)
            current, first = [], None
    return loops


def met_area(rake: Poly, loops: Sequence[Poly]) -> float:
    """The area (in²) of a body's face loops (outer and holes) under the
    convex *rake* section."""
    clip = _ccw(rake)
    signs = [1.0 if _area(loop) > 0 else -1.0 for loop in loops]
    if loops and signs[0] < 0:  # the outer loop clockwise: every sign flips
        signs = [-s for s in signs]
    total = 0.0
    for sign, loop in zip(signs, loops, strict=True):
        part = _clip(_ccw(loop), clip)
        if len(part) >= 3:
            total += sign * abs(_area(part))
    return total


# --- Emission -----------------------------------------------------------------------


@dataclass(frozen=True)
class Context:
    """What the gable's roofing needs from the roof (:func:`roofing`)."""

    rafter: Rafter
    span: float
    length: float
    place: GablePlace
    wall_id: uuid.UUID
    ends: Sequence[OutlineWall]  # the end walls, as the outline orders them
    sheathed: float  # the walls' sheathing thickness (0 unsheathed)
    finish: SidingProduct | None  # the walls' Exterior finish
    spacing: float
    rafter_t: float
    waste: int


def roofing(
    inputs: ExpandInputs, members: Sequence[Member], ctx: Context
) -> list[Member]:
    """The deck, fascia and rake boards, then the rake boards' cuts out of
    the end walls' corner boards and siding and the gables' siding (module
    docstring), numbered after *members* of each role."""
    used = {
        role: sum(1 for m in members if m.role == role)
        for role in ("plane", "section", "deck", "fascia", "rake_board", "cutter")
    }
    out: list[Member] = []

    def index(role: str) -> int:
        return used[role] + sum(1 for m in out if m.role == role)

    place = ctx.place
    start, across0 = (place.x0, place.y0) if place.along_x else (place.y0, place.x0)
    base: Literal["YZ", "XZ"] = "YZ" if place.along_x else "XZ"
    axis = base.lower()
    direction: Literal["normal", "reverse"] = "normal" if place.along_x else "reverse"
    sides = ("front", "back") if place.along_x else ("left", "right")
    planes: dict[float, DatumPlaneRef | FeatureRef] = {}

    def plane_at(at: float) -> DatumPlaneRef | FeatureRef:
        at = _r(at)
        if at == 0.0:
            return DatumPlaneRef(kind="datum_plane", plane=base)
        if at not in planes:
            name = f"roofing/{axis}/{number_name(at)}"
            k = index("plane")
            offset = _mm(at) if place.along_x else -_mm(at) + 0.0
            out.append(
                Member(
                    "plane",
                    k,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumOffsetParams(base=base, offset_mm=offset),
                    ),
                    name=name,
                )
            )
            planes[at] = inputs.ref("plane", k, name)
        return planes[at]

    def sketch(name: str, at: float, points: Poly) -> FeatureRef:
        k = index("section")
        entities: list[SketchEntity] = [
            SketchLine(
                id=f"e{i + 1}",
                kind="line",
                start=Point2D(x=_mm(across0 + points[i][0]), y=_mm(points[i][1])),
                end=Point2D(
                    x=_mm(across0 + points[(i + 1) % len(points)][0]),
                    y=_mm(points[(i + 1) % len(points)][1]),
                ),
            )
            for i in range(len(points))
        ]
        out.append(
            Member(
                "section",
                k,
                SketchFeature(
                    type="sketch",
                    version=1,
                    params=SketchParamsV1(
                        plane=plane_at(at), entities=entities, constraints=[]
                    ),
                ),
                name=name,
            )
        )
        return inputs.ref("section", k, name)

    def body(
        role: str,
        name: str,
        at: float,
        points: Poly,
        distance: float,
        meta: MemberMetadata,
    ) -> FeatureRef:
        profile = sketch(f"{role}/{name}", at, points)
        k = index(role)
        out.append(
            Member(
                role,
                k,
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=profile,
                        distance_mm=_mm(distance),
                        operation="add",
                        merge=False,
                        direction=direction,
                    ),
                ),
                meta,
                name=name,
            )
        )
        return profile

    fascia_p = fascia_profile(ctx.rafter)
    rake_p = lumber_profile(RAKE_PROFILE)
    plane = Plane(ctx.rafter, ctx.span, fascia_p.thickness_in)

    def mirrored(points: Poly, side: str) -> Poly:
        if side == sides[0]:
            return points
        return [(ctx.span - y, z) for y, z in reversed(points)]

    x_lo, x_hi = -ctx.sheathed, ctx.length + ctx.sheathed
    centres = joist_centres(ctx.length, ctx.spacing, ctx.rafter_t)
    trim: MaterialKey = (
        ctx.finish.trim_material if ctx.finish is not None else _PLAIN_TRIM
    )
    run = _mm(x_hi - x_lo)
    rake_run = _mm(plane.slope_length)

    # The deck: each plane's courses up from the eave, sheets jointed on rafters.
    t = DECK_GOOD.thickness_in
    for p, side in enumerate(sides):
        for k, (s0, s1) in enumerate(plane.courses()):
            first = SHEET_IN if k % 2 == 0 else HALF_IN
            pieces = joints(x_lo, x_hi, centres, first, SHEET_IN)
            section = mirrored(plane.panel(s0, s1, t), side)
            for j, (a0, a1) in enumerate(pieces):
                edges: list[RoofEdgeRun] = []
                if k == 0 and j == 0:
                    edges = [
                        RoofEdgeRun(edge="eave", length_mm=run),
                        RoofEdgeRun(edge="rake", length_mm=rake_run),
                        RoofEdgeRun(edge="rake", length_mm=rake_run),
                    ]
                    if p == 0:
                        edges.append(RoofEdgeRun(edge="ridge", length_mm=run))
                meta = MemberMetadata(
                    profile=DECK_GOOD.name,
                    material=DECK_GOOD.material,
                    roofing=RoofingTakeoff(waste_percent=ctx.waste, edges=edges),
                )
                body(
                    "deck",
                    f"{side}/{k}/{j}",
                    start + a0,
                    section,
                    a1 - a0,
                    meta,
                )

    # The fascia on each eave.
    fascia_meta = MemberMetadata(profile=fascia_p.name, material=trim)
    for side in sides:
        section = mirrored(plane.fascia(fascia_p.width_in), side)
        for j, (a0, a1) in enumerate(fascia_joints(x_lo, x_hi, centres)):
            body("fascia", f"{side}/{j}", start + a0, section, a1 - a0, fascia_meta)

    # The rake boards, and each one's cut out of what it covers.
    rake_meta = MemberMetadata(profile=rake_p.name, material=trim)
    w = rake_p.thickness_in
    for end, at in (("start", x_lo - w), ("end", x_hi)):
        covered = _covered(inputs, members, ctx, end)
        for side in sides:
            section = mirrored(plane.rake(rake_p.width_in), side)
            profile = body(
                "rake_board", f"{end}/{side}", start + at, section, w, rake_meta
            )
            world = [(across0 + y, z) for y, z in section]
            hit = [ref for ref, loops in covered if met_area(world, loops) > _MEETS_IN2]
            if not hit:
                continue
            out.append(
                Member(
                    "cutter",
                    index("cutter"),
                    ExtrudeFeature(
                        type="extrude",
                        version=1,
                        params=ExtrudeParamsV1(
                            profile=profile,
                            distance_mm=_mm(w),
                            operation="cut",
                            direction=direction,
                            cut_bodies=hit,
                        ),
                    ),
                    name=f"rake/{end}/{side}",
                )
            )
    return out


def _covered(
    inputs: ExpandInputs,
    members: Sequence[Member],
    ctx: Context,
    end: str,
) -> list[tuple[FeatureRef, list[Poly]]]:
    """The bodies a rake board at the roof's *end* may cover, each with its
    face's loops in world (across, Z): the end wall's corner boards and
    siding (``loft.wall`` 1.5.0's) and the gable's siding (1.8.0's). The end
    wall at the roof's start is the one whose face is nearer the low end."""
    if ctx.finish is None or not ctx.ends:
        return []

    def along(wall: OutlineWall) -> float:
        px, py = wall_v1.WallFrame.of(wall.spec).plan(0.0, 0.0)
        return px if ctx.place.along_x else py

    walls = sorted(ctx.ends, key=along)
    wall = walls[0] if end == "start" else walls[-1]
    found: list[tuple[FeatureRef, list[Poly]]] = []
    names = [
        ("corner_board", f"{wall.line_id}/corner/start"),
        ("corner_board", f"{wall.line_id}/corner/end"),
    ]
    k = 0
    while member_id(ctx.wall_id, "siding", 0, f"{wall.line_id}/siding/{k}") in (
        inputs.earlier
    ):
        names.append(("siding", f"{wall.line_id}/siding/{k}"))
        k += 1
    for role, name in names:
        feature = member_id(ctx.wall_id, role, 0, name)
        loops = _earlier_loops(inputs, feature)
        if loops:
            found.append((FeatureRef(kind="feature", feature_id=feature), loops))
    by_name = {(m.role, m.name): m for m in members}
    siding = by_name.get(("gable_siding", f"{wall.line_id}/siding"))
    section = by_name.get(("section", f"gable_siding/{wall.line_id}/siding"))
    if siding is not None and section is not None:
        assert isinstance(section.feature, SketchFeature)
        found.append(
            (
                inputs.ref("gable_siding", siding.index, siding.name),
                sketch_loops(section.feature),
            )
        )
    return found


def _earlier_loops(inputs: ExpandInputs, feature: uuid.UUID) -> list[Poly]:
    """An earlier member's sketched loops (its extrude's profile), or none."""
    body = inputs.earlier.get(feature)
    if not isinstance(body, ExtrudeFeature):
        return []
    section = inputs.earlier.get(body.params.profile.feature_id)
    if not isinstance(section, SketchFeature):
        return []
    return sketch_loops(section)
