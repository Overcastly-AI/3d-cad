"""Slab: a slab on grade from the building outline (SLAB, RESEARCH §23).

What Chief Architect's and Revit's foundation tools build from the exterior
wall loop: a monolithic slab on grade, its top the walls' base, with an
optional THICKENED EDGE (a footing poured with the slab, square on its inner
face) under the outline. ``docs/reference-parts/buildings.md`` B8 is the
defaults on B7's outline; B2's plain slab is the edge turned off.

**Placement.** The slab fills a closed outline sketch (any loop the outline
reader accepts: horizontal and vertical lines, fully dimensioned, in plan),
or, with none picked, a typed rectangle placed as ``loft.floor``'s is (a
start corner, a direction, a width along it and a depth to its left). Its
TOP is at *Top elevation* (Z 0 by default); it is *Thickness* deep below.

**The thickened edge** is a ring *Edge width* wide inside the outline, from
the slab's underside down to *Edge depth* below the top (overall, as Chief
dimensions it). Its inner face is the outline inset by the edge width:
every corner moves in along both its lines' inward normals, so each inset
line keeps its direction; an outline too narrow for the ring (an inset line
that would vanish or turn, or cross another) is refused.

**One body per pour.** The slab is one new body: the plate extruded down
from the top, then the ring extruded down from the plate's underside and
MERGED into it (the active body the plate just started), so geometry fuses
them into one solid and the cut list lists one pour. The plate's extrude
carries the member metadata (the body's id is the feature that started it):
the concrete, its waste allowance, and the edge's rebar.

**Listed, not drawn** (:mod:`loft_wire.foundation`): 2 #4 bars in the edge,
one 3 in above its bottom and one 3 in below the slab top, each a closed loop
on the ring's centreline (the outline inset by half the edge width). They
would sit inside the concrete, so they are the pour's metadata, never bodies.
Anchor bolts belong to the plates that bear on the slab (``loft.wall``
1.4.0), which know their pieces.

Inputs are millimetres on the wire (their names end ``_mm``) and inches
inside, rounded to 1e-9 in so a round trip gives back the exact spec value.
"""

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
    ConcretePour,
    RebarRun,
)
from loft_wire.lumber import MM_PER_INCH
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
from loft_plugins.builtin.outline import outline_sketch, read_outline, unsupported

_DIGITS = 9
#: Float slack of the plan arithmetic (in).
_EPS = 1e-9
#: Rebar cover in the edge (in): 3 in above its bottom, 3 in below the top.
REBAR_COVER_IN = 3.0
#: Bars in the thickened edge.
EDGE_BARS = 2

Vec2 = tuple[float, float]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _DIGITS)


def _length(
    name: str,
    label: str,
    default_in: float,
    low_in: float,
    high_in: float,
    description: str,
    *,
    superseded_by: str | None = None,
    superseded_unless: str | None = None,
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
        superseded_unless=superseded_unless,
    )


_YES_NO = [
    ChoiceOption(value="yes", label="Yes"),
    ChoiceOption(value="no", label="No"),
]

MANIFEST_V1 = PluginManifest(
    id="loft.slab",
    version="1.0.0",
    title="Slab",
    description="A slab on grade on the building outline, with an optional "
    "thickened edge, listing its concrete, rebar and anchor bolts (Chief "
    "Architect, Revit).",
    inputs=[
        FeatureReferenceInput(
            kind="feature",
            name="outline",
            label="Outline",
            description="A closed loop of sketch lines on the XY plane, the "
            "framing's outside face, horizontal and vertical, every side "
            "dimensioned. The slab fills it. Empty: typed below.",
            feature_types=["sketch"],
            optional=True,
        ),
        _length(
            "start_x_mm",
            "Start X",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the slab, in plan.",
            superseded_by="outline",
        ),
        _length(
            "start_y_mm",
            "Start Y",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the slab, in plan.",
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
            48.0,
            1200.0,
            "Along the direction.",
            superseded_by="outline",
        ),
        _length(
            "depth_mm",
            "Depth",
            120.0,
            48.0,
            1200.0,
            "To the left of the direction.",
            superseded_by="outline",
        ),
        _length(
            "top_elevation_mm",
            "Top elevation",
            0.0,
            -120.0,
            120.0,
            "The slab's top above Z 0: where the walls on it stand.",
        ),
        _length(
            "thickness_mm",
            "Thickness",
            4.0,
            3.5,
            12.0,
            "Of the slab, down from its top.",
        ),
        ChoiceInput(
            kind="choice",
            name="thickened_edge",
            label="Thickened edge",
            description="A footing poured with the slab under the outline, "
            "square on its inner face.",
            options=_YES_NO,
            default="yes",
        ),
        _length(
            "edge_width_mm",
            "Edge width",
            12.0,
            6.0,
            48.0,
            "Inward from the outline.",
            superseded_by="thickened_edge",
            superseded_unless="yes",
        ),
        _length(
            "edge_depth_mm",
            "Edge depth",
            12.0,
            6.0,
            48.0,
            "Overall, from the slab's top to the edge's bottom.",
            superseded_by="thickened_edge",
            superseded_unless="yes",
        ),
        ChoiceInput(
            kind="choice",
            name="edge_rebar",
            label="Edge rebar",
            description="Bars listed in the cut list, not drawn: one 3 in "
            "above the edge's bottom and one 3 in below the slab's top, on "
            "the edge's centreline, each a closed loop lapped 24 in.",
            options=[
                ChoiceOption(value="two_4", label="2 #4"),
                ChoiceOption(value="none", label="None"),
            ],
            default="two_4",
            superseded_by="thickened_edge",
            superseded_unless="yes",
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
            role="slab",
            title="Slab",
            description="The pour: the slab and its thickened edge, one body.",
        ),
        PluginMemberRole(
            role="edge",
            title="Thickened edge",
            description="The edge's ring, merged into the slab's body.",
        ),
    ],
)


# --- The slab, in plan (pure, inches) -----------------------------------------------


@dataclass(frozen=True)
class SlabSpec:
    """A slab's inputs in inches, its outline counter-clockwise in plan."""

    corners: tuple[Vec2, ...]
    top: float
    thickness: float
    edge_width: float | None
    edge_depth: float
    bars: int
    waste_percent: int

    @property
    def bottom(self) -> float:
        """The slab's underside (in): the edge's top."""
        return round(self.top - self.thickness, _DIGITS)


def _cos_sin(degrees: float) -> tuple[float, float]:
    """cos and sin of *degrees*, exact at multiples of 90."""
    turn = degrees % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    if turn in exact:
        return exact[turn]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0  # + 0.0: never -0.0


def slab_corners(inputs: ExpandInputs) -> tuple[Vec2, ...]:
    """The slab's outline, counter-clockwise: the picked outline's corners,
    or the typed rectangle's."""
    ref = inputs.optional_feature("outline")
    if ref is not None:
        outline = read_outline(
            outline_sketch(ref, inputs.earlier, "outline"),
            "outline",
            inputs.parameters,
        )
        return outline.ccw_corners
    x, y = _inches("start_x_mm", inputs), _inches("start_y_mm", inputs)
    width, depth = _inches("width_mm", inputs), _inches("depth_mm", inputs)
    c, s = _cos_sin(inputs.number("direction_deg"))
    along, left = (c * width, s * width), (-s * depth, c * depth)
    return (
        (_r(x), _r(y)),
        (_r(x + along[0]), _r(y + along[1])),
        (_r(x + along[0] + left[0]), _r(y + along[1] + left[1])),
        (_r(x + left[0]), _r(y + left[1])),
    )


def slab_spec(inputs: ExpandInputs) -> SlabSpec:
    edge = inputs.choice("thickened_edge") == "yes"
    thickness = _inches("thickness_mm", inputs)
    depth = _inches("edge_depth_mm", inputs)
    if edge and depth <= thickness + _EPS:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Edge depth: {depth:g} in is not below the slab's {thickness:g} in; "
            "the edge's depth is overall, from the slab's top.",
            input="edge_depth_mm",
        )
    return SlabSpec(
        corners=slab_corners(inputs),
        top=_inches("top_elevation_mm", inputs),
        thickness=thickness,
        edge_width=_inches("edge_width_mm", inputs) if edge else None,
        edge_depth=depth,
        bars=EDGE_BARS if edge and inputs.choice("edge_rebar") == "two_4" else 0,
        waste_percent=inputs.count("waste_percent"),
    )


def _left_normal(a: Vec2, b: Vec2) -> Vec2:
    """The unit normal to the left of a -> b (inward on a CCW loop)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return (-dy / length, dx / length)


def _segments_cross(a: Vec2, b: Vec2, c: Vec2, d: Vec2) -> bool:
    """Whether segments ab and cd share a point (touching counts)."""

    def orient(p: Vec2, q: Vec2, r: Vec2) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on(p: Vec2, q: Vec2, r: Vec2) -> bool:
        return (
            min(p[0], q[0]) - _EPS <= r[0] <= max(p[0], q[0]) + _EPS
            and min(p[1], q[1]) - _EPS <= r[1] <= max(p[1], q[1]) + _EPS
        )

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 > _EPS and o2 < -_EPS) or (o1 < -_EPS and o2 > _EPS)) and (
        (o3 > _EPS and o4 < -_EPS) or (o3 < -_EPS and o4 > _EPS)
    ):
        return True
    return (
        (abs(o1) <= _EPS and on(a, b, c))
        or (abs(o2) <= _EPS and on(a, b, d))
        or (abs(o3) <= _EPS and on(c, d, a))
        or (abs(o4) <= _EPS and on(c, d, b))
    )


def inset(corners: Sequence[Vec2], distance: float) -> tuple[Vec2, ...]:
    """*corners* (counter-clockwise) moved *distance* inward: each corner
    along both its lines' inward normals (the lines are perpendicular, or
    collinear, at every corner), so each inset line is parallel to its own.
    Refused when a line would vanish or turn, or two would cross."""
    n = len(corners)
    normals = [_left_normal(corners[k], corners[(k + 1) % n]) for k in range(n)]
    out: list[Vec2] = []
    for k in range(n):
        before, after = normals[k - 1], normals[k]
        if math.isclose(before[0], after[0], abs_tol=_EPS) and math.isclose(
            before[1], after[1], abs_tol=_EPS
        ):
            shift = after  # collinear lines: one normal
        else:
            shift = (before[0] + after[0], before[1] + after[1])
        x, y = corners[k]
        out.append((_r(x + distance * shift[0]), _r(y + distance * shift[1])))
    for k in range(n):
        a, b = corners[k], corners[(k + 1) % n]
        c, d = out[k], out[(k + 1) % n]
        along = (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1])
        if along <= _EPS:
            raise unsupported(
                f"Thickened edge: a side of the outline is too short for a "
                f"{distance:g} in edge; narrow the edge or turn it off.",
                "edge_width_mm",
            )
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent through the closing corner
            if _segments_cross(out[i], out[(i + 1) % n], out[j], out[(j + 1) % n]):
                raise unsupported(
                    f"Thickened edge: the outline is too narrow for a "
                    f"{distance:g} in edge; narrow the edge or turn it off.",
                    "edge_width_mm",
                )
    return tuple(out)


def perimeter(corners: Sequence[Vec2]) -> float:
    n = len(corners)
    return round(
        sum(math.dist(corners[k], corners[(k + 1) % n]) for k in range(n)), _DIGITS
    )


def edge_bars(slab: SlabSpec) -> list[RebarRun]:
    """The edge's bars: closed loops on its centreline (module docstring)."""
    if slab.edge_width is None or slab.bars == 0:
        return []
    loop = perimeter(inset(slab.corners, slab.edge_width / 2))
    return [RebarRun(length_mm=_mm(loop), closed=True) for _ in range(slab.bars)]


# --- Reading a slab (what a wall on it reads) ---------------------------------------


def slab_top(inputs: ExpandInputs) -> float:
    """A stored ``loft.slab``'s top (in), from its inputs: where a wall on
    it stands (read from inputs, never members, RESEARCH §23)."""
    return _inches("top_elevation_mm", inputs)


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


def _on_plane(
    inputs: ExpandInputs, z: float, levels: dict[float, int]
) -> tuple[list[Member], DatumPlaneRef | FeatureRef]:
    """The plane at *z* (in): ``XY`` at 0, else a level datum shared by its
    elevation, with the datum member the first time it is used."""
    key = round(z, _DIGITS) + 0.0  # + 0.0: -0.0 is the XY plane too
    if key == 0.0:
        return [], DatumPlaneRef(kind="datum_plane", plane="XY")
    level = levels.get(key)
    members: list[Member] = []
    if level is None:
        level = levels[key] = len(levels)
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
    return members, inputs.ref("level", level)


def _section(
    index: int, plane: DatumPlaneRef | FeatureRef, loops: Sequence[Sequence[Vec2]]
) -> Member:
    return Member(
        "section",
        index,
        SketchFeature(
            type="sketch",
            version=1,
            params=SketchParamsV1(
                plane=plane, entities=list(_loops(loops)), constraints=[]
            ),
        ),
    )


def _down(
    inputs: ExpandInputs, section: int, depth: float, merge: bool
) -> ExtrudeFeature:
    return ExtrudeFeature(
        type="extrude",
        version=1,
        params=ExtrudeParamsV1(
            profile=inputs.ref("section", section),
            distance_mm=_mm(depth),
            operation="add",
            direction="reverse",
            merge=merge,
        ),
    )


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    slab = slab_spec(inputs)
    levels: dict[float, int] = {}
    datums, top = _on_plane(inputs, slab.top, levels)
    yield from datums
    yield _section(0, top, [slab.corners])
    concrete = FOUNDATION_ITEMS_BY_KEY["ready_mix"]
    bars = edge_bars(slab)
    yield Member(
        "slab",
        0,
        _down(inputs, 0, slab.thickness, merge=False),
        MemberMetadata(
            profile=concrete.name,
            material=concrete.material,
            concrete=ConcretePour(waste_percent=slab.waste_percent),
            rebar=bars or None,
        ),
    )
    if slab.edge_width is None:
        return
    inner = inset(slab.corners, slab.edge_width)
    datums, under = _on_plane(inputs, slab.bottom, levels)
    yield from datums
    yield _section(1, under, [slab.corners, inner])
    yield Member(
        "edge", 0, _down(inputs, 1, slab.edge_depth - slab.thickness, merge=True)
    )


SLAB_V1 = Plugin(MANIFEST_V1, expand)
