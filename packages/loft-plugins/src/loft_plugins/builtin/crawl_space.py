"""Foundation: a crawl space's stem wall on a continuous footing (CRAWL-SPACE).

What Chief Architect's foundation and Revit's foundation walls build under
the exterior wall loop: a POURED-CONCRETE STEM WALL (CMU is a later choice)
on a continuous footing, with the framed floor on its top. RESEARCH §23;
``docs/reference-parts/buildings.md`` B9 is the defaults on B7's outline.

**Placement.** The stem's OUTSIDE face is the outline (a closed outline
sketch the outline reader accepts, or a typed rectangle placed as
``loft.slab``'s is), *Stem thickness* inward. Its TOP is the base elevation
of the floor picked in *Floor on it* (the floor's sills' underside), Z 0
with none, so a ``loft.floor`` on the same outline sits on it unchanged: its
sills flush with the stem's outside face, as Chief seats a platform floor.

**Heights.** *Crawl height* is grade to the joists' underside (the stem's
top plus the floor's sill, 1.5 in with no floor picked), so grade is that
much below the joists. The footing's bottom is *Footing below grade* under
grade (IRC R403.1.4: at least 12 in); the footing is *Footing width* wide,
centred under the stem, *Footing thickness* deep; the stem runs from the
footing's top to its own. A taller crawl lowers grade and the footing and
moves nothing above the stem's top. Under 18 in IRC R317.1 wants treated or
naturally durable joists: documents warns (``crawl_height_low``), and the
feature builds.

**One body per pour** (buildings.md's convention): the footing is poured
first and the stem formed on it, so each is a new body, the footing's ring
extruded down from its top and the stem's down from its own top to the
footing's, face to face. Each lists its concrete with the waste allowance
(the cut list orders the two on their sum, as it groups pours of one
allowance); the footing carries its rebar, the stem the anchor bolts cast
into it.

**Openings cut from the stem** at its top, through its thickness (a cut
scoped to the stem's body, its tool 1 in clear of the stem's faces and top),
so the sill caps them as a foundation vent is set:

* **Vents** (IRC R408.1): 1 ft² of net free area per 150 ft² of crawl (the
  area inside the stem), at *Vent net area* each, and at least one within
  3 ft of each corner, so ``max(corners, ceil(area / 150 / net))``. Each
  corner's vent is centred 24 in from it on the corner's longer line (on a
  tie, the one facing front or back). The rest go round the lines that do
  not hold the access, longest first (then front, back, left, right, then
  the line nearer the origin), each line's spaced evenly between its corner
  vents: B9's fifth vent is centred on the front wall.
* **The access** (IRC R408.4, through a perimeter wall: at least 16 in high
  by 24 in wide, above grade) is centred on the longest line facing *Access
  in* (on a tie, the one nearer the origin).

An opening that would reach into a corner's crossing stem, overlap another
or reach below grade is refused, saying which.

**Listed, not drawn** (:mod:`loft_wire.foundation`, SLAB's takeoff): 2 #4
bars in the footing 3 in above its bottom and 3 in in from each face, each a
closed loop lapped 24 in; and the 1/2 in anchor bolts cast in for the sills
(IRC R403.1.6): for each sill piece of the floor picked, counted from its
length, or with none picked one sill on each side of the outline. The bolts
are the pour's, so ``loft.floor`` is unchanged.

Inputs are millimetres on the wire (their names end ``_mm``) and inches
inside, rounded to 1e-9 in so a round trip gives back the exact spec value.
"""

import itertools
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

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
from loft_wire.foundation import (
    DEFAULT_CONCRETE_WASTE_PERCENT,
    FOUNDATION_ITEMS_BY_KEY,
    MAX_CONCRETE_WASTE_PERCENT,
    AnchorBolts,
    ConcretePour,
    RebarRun,
)
from loft_wire.lumber import LUMBER_PROFILES_BY_KEY, MM_PER_INCH
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    AngleInput,
    ChoiceInput,
    ChoiceOption,
    CountInput,
    FeatureReferenceInput,
    LengthInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import floor as floor_v1
from loft_plugins.builtin.house import floor_of
from loft_plugins.builtin.outline import unsupported
from loft_plugins.builtin.slab import inset, perimeter, slab_corners

_DIGITS = 9
#: Float slack of the plan arithmetic (in).
_EPS = 1e-9
#: Rebar cover in the footing (in): above its bottom and in from each face.
REBAR_COVER_IN = 3.0
#: Bars in the footing.
FOOTING_BARS = 2
#: IRC R408.1: 1 ft² of net vent area per 150 ft² of crawl space.
VENT_AREA_RATIO = 150
#: IRC R408.1: a vent within 3 ft of each corner; centred 24 in from it.
CORNER_VENT_IN = 24.0
#: IRC R317.1: joists closer than 18 in to exposed ground are treated.
MIN_UNTREATED_CRAWL_IN = 18.0
#: The sill a crawl height is measured over when no floor is picked: a 2x.
ASSUMED_SILL_IN = LUMBER_PROFILES_BY_KEY["us_2x6"].thickness_in
#: How far an opening's cutting tool reaches past the stem's faces and top
#: (in): the cut is scoped to the stem's body, so it touches nothing else.
TOOL_CLEARANCE_IN = 1.0

Vec2 = tuple[float, float]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _DIGITS)


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0  # + 0.0: never -0.0


def _length(
    name: str,
    label: str,
    default_in: float,
    low_in: float,
    high_in: float,
    description: str,
    *,
    superseded_by: str | None = None,
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=description,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
        superseded_by=superseded_by,
    )


#: Which way a line faces, in the order ties are broken.
FACINGS = ("front", "back", "left", "right")

MANIFEST_V1 = PluginManifest(
    id="loft.foundation",
    version="1.0.0",
    title="Foundation",
    description="A crawl space: a poured-concrete stem wall on a continuous "
    "footing under the building outline, with vents and an access cut from "
    "the stem, listing its concrete, rebar and anchor bolts (Chief "
    "Architect, Revit).",
    inputs=[
        FeatureReferenceInput(
            kind="feature",
            name="outline",
            label="Outline",
            description="A closed loop of sketch lines on the XY plane, the "
            "framing's outside face, horizontal and vertical, every side "
            "dimensioned: the stem's outside face. Empty: typed below.",
            feature_types=["sketch"],
            optional=True,
        ),
        _length(
            "start_x_mm",
            "Start X",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the stem's outside face, in plan.",
            superseded_by="outline",
        ),
        _length(
            "start_y_mm",
            "Start Y",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the stem's outside face, in plan.",
            superseded_by="outline",
        ),
        AngleInput(
            kind="angle",
            name="direction_deg",
            label="Direction",
            description="Of the width, from +X, counterclockwise seen from "
            "above; the depth runs to its left.",
            default=0.0,
            minimum=-360.0,
            maximum=360.0,
            superseded_by="outline",
        ),
        _length(
            "width_mm",
            "Width",
            144.0,
            72.0,
            1200.0,
            "Along the direction.",
            superseded_by="outline",
        ),
        _length(
            "depth_mm",
            "Depth",
            120.0,
            72.0,
            1200.0,
            "To the left of the direction.",
            superseded_by="outline",
        ),
        FeatureReferenceInput(
            kind="feature",
            name="floor",
            label="Floor on it",
            description="The earlier floor on the stem, on the same outline: "
            "the stem's top is its base elevation, the crawl height is measured "
            "to its joists' underside, and its sills' anchor bolts are listed. "
            "Empty: the top at Z 0 under a 1.5 in sill on each side.",
            feature_types=["custom"],
            plugin_ids=["loft.floor"],
            optional=True,
        ),
        _length(
            "crawl_height_mm",
            "Crawl height",
            24.0,
            12.0,
            72.0,
            "Grade to the joists' underside. Under 18 in IRC R317.1 wants "
            "treated or durable joists (a warning).",
        ),
        _length(
            "stem_thickness_mm",
            "Stem thickness",
            8.0,
            6.0,
            16.0,
            "Inward from the outline.",
        ),
        _length(
            "footing_width_mm",
            "Footing width",
            16.0,
            8.0,
            48.0,
            "Centred under the stem.",
        ),
        _length(
            "footing_thickness_mm",
            "Footing thickness",
            8.0,
            6.0,
            24.0,
            "Of the footing, up from its bottom.",
        ),
        _length(
            "footing_depth_mm",
            "Footing below grade",
            12.0,
            12.0,
            72.0,
            "Grade to the footing's bottom: at least 12 in (IRC R403.1.4), "
            "and below the frost line.",
        ),
        ChoiceInput(
            kind="choice",
            name="footing_rebar",
            label="Footing rebar",
            description="Bars listed in the cut list, not drawn: two 3 in "
            "above the footing's bottom and 3 in in from each face, each a "
            "closed loop lapped 24 in.",
            options=[
                ChoiceOption(value="two_4", label="2 #4"),
                ChoiceOption(value="none", label="None"),
            ],
            default="two_4",
        ),
        _length(
            "vent_width_mm",
            "Vent width",
            16.0,
            8.0,
            32.0,
            "Of each foundation vent, along the stem.",
        ),
        _length(
            "vent_height_mm",
            "Vent height",
            8.0,
            4.0,
            16.0,
            "Down from the stem's top.",
        ),
        CountInput(
            kind="count",
            name="vent_net_area",
            label="Vent net area (in²)",
            description="Each vent's net free area, from its maker: R408.1 "
            "wants 1 ft² per 150 ft² of crawl, so it sets how many vents.",
            default=72,
            minimum=8,
            maximum=512,
        ),
        ChoiceInput(
            kind="choice",
            name="access_wall",
            label="Access in",
            description="The wall the crawl-space access is centred in: its "
            "longest line facing that way.",
            options=[
                ChoiceOption(value="front", label="Front"),
                ChoiceOption(value="back", label="Back"),
                ChoiceOption(value="left", label="Left"),
                ChoiceOption(value="right", label="Right"),
            ],
            default="back",
        ),
        _length(
            "access_width_mm",
            "Access width",
            24.0,
            24.0,
            48.0,
            "At least 24 in (IRC R408.4).",
        ),
        _length(
            "access_height_mm",
            "Access height",
            16.0,
            16.0,
            36.0,
            "Down from the stem's top; at least 16 in and above grade (IRC R408.4).",
        ),
        CountInput(
            kind="count",
            name="waste_percent",
            label="Concrete waste (%)",
            description="Ordered over the net volume for spillage and "
            "sub-grade variance, then rounded up to 1/4 yd³.",
            default=DEFAULT_CONCRETE_WASTE_PERCENT,
            minimum=0,
            maximum=MAX_CONCRETE_WASTE_PERCENT,
        ),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(
            role="footing",
            title="Footing",
            description="The continuous footing's pour, with its rebar.",
        ),
        PluginMemberRole(
            role="stem",
            title="Stem wall",
            description="The stem wall's pour on the footing, with the sills' "
            "anchor bolts.",
        ),
        PluginMemberRole(
            role="vent",
            title="Vent",
            description="A foundation vent cut from the stem (IRC R408.1).",
        ),
        PluginMemberRole(
            role="access",
            title="Access",
            description="The crawl-space access cut from the stem (IRC R408.4).",
        ),
    ],
)


# --- The foundation, in plan and section (pure, inches) -----------------------------


@dataclass(frozen=True)
class Line:
    """One line of the outline, counter-clockwise: corner *k* to *k* + 1."""

    index: int
    start: Vec2
    end: Vec2

    @property
    def length(self) -> float:
        return round(math.dist(self.start, self.end), _DIGITS)

    @property
    def along(self) -> Vec2:
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        return (dx / self.length, dy / self.length)

    @property
    def inward(self) -> Vec2:
        """The unit normal into the building (to the left, walked CCW)."""
        ux, uy = self.along
        return (-uy, ux)

    @property
    def facing(self) -> str:
        """Its outward normal's name (front is -Y, as the roof names them)."""
        nx, ny = self.inward
        if abs(ny) >= abs(nx):
            return "front" if ny > 0 else "back"
        return "left" if nx > 0 else "right"

    def rank(self) -> tuple[float, int, float, float]:
        """Longest first, then front, back, left, right, then nearer the origin."""
        mid = ((self.start[0] + self.end[0]) / 2, (self.start[1] + self.end[1]) / 2)
        return (-self.length, FACINGS.index(self.facing), mid[0], mid[1])

    def point(self, s: float, d: float = 0.0) -> Vec2:
        """*s* along from its start and *d* inward."""
        ux, uy = self.along
        nx, ny = self.inward
        x, y = self.start
        return (_r(x + s * ux + d * nx), _r(y + s * uy + d * ny))


@dataclass(frozen=True)
class Opening:
    """A vent or the access: centred *at* along its line, *width* wide."""

    kind: str
    line: Line
    at: float
    width: float
    height: float

    @property
    def low(self) -> float:
        return self.at - self.width / 2

    @property
    def high(self) -> float:
        return self.at + self.width / 2

    def plan(self, thickness: float) -> tuple[Vec2, ...]:
        """Its cutting tool's footprint, counter-clockwise: through the stem
        and :data:`TOOL_CLEARANCE_IN` past both faces, so no face of the tool
        lies on one of the stem's."""
        out, deep = -TOOL_CLEARANCE_IN, thickness + TOOL_CLEARANCE_IN
        return (
            self.line.point(self.low, out),
            self.line.point(self.high, out),
            self.line.point(self.high, deep),
            self.line.point(self.low, deep),
        )


@dataclass(frozen=True)
class FoundationSpec:
    """A foundation's inputs in inches, its outline counter-clockwise."""

    corners: tuple[Vec2, ...]
    top: float
    sill: float
    crawl: float
    stem: float
    footing_width: float
    footing_thickness: float
    footing_depth: float
    bars: int
    vent_width: float
    vent_height: float
    vent_net_in2: int
    access_wall: str
    access_width: float
    access_height: float
    waste_percent: int
    plates: tuple[float, ...]

    @property
    def grade(self) -> float:
        """Grade (in): the crawl height below the joists' underside."""
        return _r(self.top + self.sill - self.crawl)

    @property
    def footing_bottom(self) -> float:
        return _r(self.grade - self.footing_depth)

    @property
    def footing_top(self) -> float:
        """The stem's bottom."""
        return _r(self.footing_bottom + self.footing_thickness)

    @property
    def stem_height(self) -> float:
        return _r(self.top - self.footing_top)

    @property
    def footing_offset(self) -> float:
        """How far the footing reaches past each face of the stem (in)."""
        return _r((self.footing_width - self.stem) / 2)

    @property
    def lines(self) -> tuple[Line, ...]:
        n = len(self.corners)
        return tuple(
            Line(k, self.corners[k], self.corners[(k + 1) % n]) for k in range(n)
        )


def _floor_corners(spec: floor_v1.FloorSpec) -> set[Vec2]:
    turn = spec.direction_deg % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    c, s = exact.get(turn, (math.cos(math.radians(turn)), math.sin(math.radians(turn))))
    x, y, w, d = spec.start_x, spec.start_y, spec.width, spec.depth
    return {
        (_r(x), _r(y)),
        (_r(x + c * w), _r(y + s * w)),
        (_r(x + c * w - s * d), _r(y + s * w + c * d)),
        (_r(x - s * d), _r(y + c * d)),
    }


def sill_lengths(spec: floor_v1.FloorSpec) -> tuple[float, ...]:
    """The floor's sill pieces' lengths (in), in its member order."""
    return tuple(
        _r(max(p.a1 - p.a0, p.b1 - p.b0))
        for p in floor_v1.floor_pieces(spec)
        if p.role == "sill"
    )


def foundation_spec(inputs: ExpandInputs) -> FoundationSpec:
    corners = slab_corners(inputs)
    n = len(corners)
    sides = tuple(_r(math.dist(corners[k], corners[(k + 1) % n])) for k in range(n))
    top, sill, plates = 0.0, ASSUMED_SILL_IN, sides
    ref = inputs.optional_feature("floor") if "floor" in inputs.values else None
    if ref is not None:
        floor = floor_of(ref, inputs, "floor").spec
        if _floor_corners(floor) != {(_r(x), _r(y)) for x, y in corners}:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Floor on it: the floor's sills sit on the stem, so it must "
                "fill the same outline as the foundation.",
                input="floor",
            )
        top, sill = floor.elevation, floor.framing_bottom
        plates = sill_lengths(floor)
    spec = FoundationSpec(
        corners=corners,
        top=top,
        sill=sill,
        crawl=_inches("crawl_height_mm", inputs),
        stem=_inches("stem_thickness_mm", inputs),
        footing_width=_inches("footing_width_mm", inputs),
        footing_thickness=_inches("footing_thickness_mm", inputs),
        footing_depth=_inches("footing_depth_mm", inputs),
        bars=FOOTING_BARS if inputs.choice("footing_rebar") == "two_4" else 0,
        vent_width=_inches("vent_width_mm", inputs),
        vent_height=_inches("vent_height_mm", inputs),
        vent_net_in2=inputs.count("vent_net_area"),
        access_wall=inputs.choice("access_wall"),
        access_width=_inches("access_width_mm", inputs),
        access_height=_inches("access_height_mm", inputs),
        waste_percent=inputs.count("waste_percent"),
        plates=plates,
    )
    _check(spec)
    return spec


def _check(spec: FoundationSpec) -> None:
    if spec.footing_width < spec.stem - _EPS:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Footing width: {spec.footing_width:g} in is narrower than the "
            f"{spec.stem:g} in stem it carries.",
            input="footing_width_mm",
        )
    if spec.footing_thickness > spec.footing_depth + _EPS:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Footing thickness: {spec.footing_thickness:g} in would stand "
            f"above grade, {spec.footing_depth:g} in over its bottom.",
            input="footing_thickness_mm",
        )
    if spec.vent_net_in2 > spec.vent_width * spec.vent_height + _EPS:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Vent net area: {spec.vent_net_in2} in² is more than the "
            f"{spec.vent_width:g} x {spec.vent_height:g} in opening.",
            input="vent_net_area",
        )
    for name, height, label in (
        ("vent_height_mm", spec.vent_height, "Vent"),
        ("access_height_mm", spec.access_height, "Access"),
    ):
        bottom = _r(spec.top - height)
        if bottom < spec.grade - _EPS:
            raise unsupported(
                f"{label} height: its bottom (Z {bottom:g}) would be below "
                f"grade (Z {spec.grade:g}), {spec.crawl:g} in under the "
                "joists; lower it or raise the crawl height (IRC R408.4: an "
                "access below grade needs an areaway).",
                name,
            )


def crawl_area_in2(spec: FoundationSpec) -> float:
    """The crawl space's plan area inside the stem (in²)."""
    inner = inset(spec.corners, spec.stem)
    n = len(inner)
    twice = sum(
        inner[k][0] * inner[(k + 1) % n][1] - inner[(k + 1) % n][0] * inner[k][1]
        for k in range(n)
    )
    return abs(twice) / 2


def vent_count(spec: FoundationSpec) -> int:
    """IRC R408.1: ``max(corners, ceil(area / 150 / net))``."""
    needed = crawl_area_in2(spec) / VENT_AREA_RATIO / spec.vent_net_in2
    return max(len(spec.corners), math.ceil(needed - _EPS))


def access_line(spec: FoundationSpec) -> Line:
    facing = [line for line in spec.lines if line.facing == spec.access_wall]
    if not facing:
        raise unsupported(
            f"Access in: the outline has no wall facing {spec.access_wall}.",
            "access_wall",
        )
    return min(facing, key=Line.rank)


def openings(spec: FoundationSpec) -> tuple[list[Opening], Opening]:
    """The vents, by line rank then along each line, and the access
    (module docstring)."""
    lines = spec.lines
    n = len(lines)
    access = access_line(spec)
    w, h = spec.vent_width, spec.vent_height
    at: dict[int, list[float]] = {line.index: [] for line in lines}
    # Each corner's vent on its longer line, 24 in from the corner.
    for k in range(n):
        before, after = lines[k - 1], lines[k]  # meeting at corner k
        if after.rank() <= before.rank():
            at[after.index].append(CORNER_VENT_IN)
        else:
            at[before.index].append(_r(before.length - CORNER_VENT_IN))
    extra = vent_count(spec) - n
    hosts = sorted(
        (line for line in lines if line.index != access.index), key=Line.rank
    )
    shares = [0] * n
    for j in range(extra):
        shares[hosts[j % len(hosts)].index] += 1
    for line in lines:
        k = shares[line.index]
        if k == 0:
            continue
        ends = at[line.index]
        lo = min(ends) if any(s < line.length / 2 for s in ends) else 0.0
        hi = max(ends) if any(s > line.length / 2 for s in ends) else line.length
        at[line.index] += [_r(lo + (hi - lo) * i / (k + 1)) for i in range(1, k + 1)]
    # Numbered by line rank, then along each line counter-clockwise: never
    # by the corner the sketch was drawn from.
    vents = [
        Opening("vent", line, s, w, h)
        for line in sorted(lines, key=Line.rank)
        for s in sorted(at[line.index])
    ]
    hole = Opening(
        "access", access, _r(access.length / 2), spec.access_width, spec.access_height
    )
    _check_openings(spec, [*vents, hole])
    return vents, hole


def _check_openings(spec: FoundationSpec, cut: Sequence[Opening]) -> None:
    for line in spec.lines:
        mine = sorted(
            (o for o in cut if o.line.index == line.index), key=lambda o: o.low
        )
        for o in mine:
            if o.low < spec.stem - _EPS or o.high > line.length - spec.stem + _EPS:
                raise unsupported(
                    f"The {o.kind} on the {line.facing} wall reaches into the "
                    f"corner's stem; the {line.length:g} in wall is too short "
                    "for it.",
                    "access_width_mm" if o.kind == "access" else "vent_width_mm",
                )
        for a, b in itertools.pairwise(mine):
            if b.low < a.high + _EPS:
                raise unsupported(
                    f"The {a.kind} and the {b.kind} on the {line.facing} wall "
                    f"overlap; narrow them or pick another wall for the access.",
                    "access_wall" if "access" in (a.kind, b.kind) else "vent_width_mm",
                )


def footing_bars(spec: FoundationSpec) -> list[RebarRun]:
    """The footing's closed loops, 3 in in from its outer and inner faces."""
    if spec.bars == 0:
        return []
    out = -spec.footing_offset + REBAR_COVER_IN
    inner = spec.stem + spec.footing_offset - REBAR_COVER_IN
    return [
        RebarRun(length_mm=_mm(perimeter(inset(spec.corners, d))), closed=True)
        for d in (out, inner)
    ]


# --- Emission ----------------------------------------------------------------------


def _loops(loops: Sequence[Sequence[Vec2]]) -> list[SketchLine]:
    """Closed loops of sketch lines (mm), ids ``e1``.. across the loops."""
    lines: list[SketchLine] = []
    for loop in loops:
        points = [Point2D(x=_mm(x), y=_mm(y)) for x, y in loop]
        for k, start in enumerate(points):
            lines.append(
                SketchLine(
                    id=f"e{len(lines) + 1}",
                    kind="line",
                    start=start,
                    end=points[(k + 1) % len(points)],
                )
            )
    return lines


class _Emitter:
    """The expansion's members: level datums shared by elevation, sections
    numbered in order."""

    def __init__(self, inputs: ExpandInputs) -> None:
        self.inputs = inputs
        self.levels: dict[float, int] = {}
        self.sections = 0

    def plane(self, z: float) -> tuple[list[Member], DatumPlaneRef | FeatureRef]:
        key = _r(z)
        if key == 0.0:
            return [], DatumPlaneRef(kind="datum_plane", plane="XY")
        level = self.levels.get(key)
        members: list[Member] = []
        if level is None:
            level = self.levels[key] = len(self.levels)
            members.append(
                Member(
                    "level",
                    level,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumOffsetParams(base="XY", offset_mm=_mm(key)),
                    ),
                )
            )
        return members, self.inputs.ref("level", level)

    def section(self, z: float, loops: Sequence[Sequence[Vec2]]) -> Iterator[Member]:
        datums, plane = self.plane(z)
        yield from datums
        yield Member(
            "section",
            self.sections,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_loops(loops)), constraints=[]
                ),
            ),
        )
        self.sections += 1

    def down(self, depth: float, *, cut: bool = False) -> ExtrudeFeature:
        """The last section extruded down *depth*: a new body, or a cut from
        the stem's alone."""
        return ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(
                profile=self.inputs.ref("section", self.sections - 1),
                distance_mm=_mm(depth),
                operation="cut" if cut else "add",
                direction="reverse",
                merge=False,
                cut_bodies=[self.inputs.ref("stem")] if cut else None,
            ),
        )


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    spec = foundation_spec(inputs)
    vents, access = openings(spec)
    emit = _Emitter(inputs)
    concrete = FOUNDATION_ITEMS_BY_KEY["ready_mix"]
    pour = ConcretePour(waste_percent=spec.waste_percent)
    ring = [
        inset(spec.corners, -spec.footing_offset),
        inset(spec.corners, spec.stem + spec.footing_offset),
    ]
    yield from emit.section(spec.footing_top, ring)
    yield Member(
        "footing",
        0,
        emit.down(spec.footing_thickness),
        MemberMetadata(
            profile=concrete.name,
            material=concrete.material,
            concrete=pour,
            rebar=footing_bars(spec) or None,
        ),
    )
    yield from emit.section(spec.top, [spec.corners, inset(spec.corners, spec.stem)])
    yield Member(
        "stem",
        0,
        emit.down(spec.stem_height),
        MemberMetadata(
            profile=concrete.name,
            material=concrete.material,
            concrete=pour,
            anchor_bolts=AnchorBolts(plates_mm=[_mm(p) for p in spec.plates])
            if spec.plates
            else None,
        ),
    )
    above = spec.top + TOOL_CLEARANCE_IN
    for k, vent in enumerate(vents):
        yield from emit.section(above, [vent.plan(spec.stem)])
        yield Member("vent", k, emit.down(vent.height + TOOL_CLEARANCE_IN, cut=True))
    yield from emit.section(above, [access.plan(spec.stem)])
    yield Member("access", 0, emit.down(access.height + TOOL_CLEARANCE_IN, cut=True))


FOUNDATION_V1 = Plugin(MANIFEST_V1, expand)
