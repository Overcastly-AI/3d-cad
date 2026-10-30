"""Sheathing: sheet panels on a wall and a floor (SHEATHING, RESEARCH §23).

Sheathing is an option on the host tool, not a tool of its own, as Chief
Architect's wall and floor structure layers and Medeek's sheathing options
build it. Each option is a NEW plugin version whose framing is the previous
version's expansion unchanged, then the panels:

* ``loft.wall`` 1.2.0 adds **Exterior sheathing** (None, 7/16 OSB or 15/32
  plywood): panels the full wall height (base of the bottom plate to the top
  of the top plate) on the exterior face, outside the framing, 48 in wide from
  the wall's start, the last one cut to the wall's end, with every hosted
  door's and window's rough opening cut out. A panel an opening cuts in two is
  two panels; an opening's edge within 1/8 in of a joint takes the joint, so
  no hair-thin strip is left.

**Outside corners** (WALL-SHEATHING-CORNER). Where wall B butts wall T (B's
end on T's interior face, B's exterior face flush with T's end, square, on
the same base: B2's side walls butting its front and back walls), the
sheathing in B's plane laps past B's end over T's end grain and sheathing
edge: a rip T's framing depth plus T's sheathing thickness wide, B's full
height, in B's product, so the corner is closed with no overlap. This is
Chief Architect's convention of running one wall's sheathing past the
corner; it is the butting wall's sheathing, so an unsheathed B leaves the
corner as it is. An expansion sees only the features before it, so the
LATER of the two walls emits the rip (``corner/<end>`` on B, or
``return/<end>`` on T): the same rip whatever the tree order. A wall whose
ends meet no wall this way (a lone wall, a mitred or offset corner, walls
on different bases) keeps its butt ends.
* ``loft.floor`` 1.1.0 adds **Subfloor** (23/32 plywood by default, or None):
  4x8 panels on the joists' top (:attr:`FloorSpec.framing_top`), the long
  edge across the joists, rows 48 in along the joists from the floor's start
  and every other row staggered 4 ft, the floor's edges cutting the last
  panels. B5's 144 x 120 floor is 6 panels.

The wall's version is 1.2.0 on top of WALL-MEMBER-RENUMBER's 1.1.0: its
framing is 1.1.0's place-named members, and every panel, section and plane
is named by its place too (``exterior/<col>/<row>``, ``row/<r>/<c>``), so a
moved opening or a longer wall never renumbers a panel (RESEARCH §23).

**Members.** A panel is one body, as every framing member: a sketch of its
outline (a rectilinear polygon, the rough openings' notches in its edges and
holes in its face) on a plane, extruded by the product's thickness as a new
body, with the product as its profile ("7/16 OSB") and the product's material.
Its own roles (``sheathing_plane``/``sheathing_section``/``sheathing``, and
``subfloor_level``/``subfloor_section``/``subfloor``) keep the framing's
member ids, levels and sections exactly the previous version's, so upgrading
a wall or floor keeps every hosted reference on its member.

**Planes.** A wall's panels are sketched on a vertical plane at its exterior
face, extruded outward. An axis wall's plane is the ``XZ`` or ``YZ`` origin
datum offset to the face, exact; any other direction is a plane through the Z
axis at an angle from ``YZ``, offset to the face. A floor's panels lie on one
``XY`` level at the joists' top, as the framing's.
"""

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from loft_wire.datum_angle import DatumAngleParams, DatumOriginAxisRef
from loft_wire.features import (
    CustomFeature,
    DatumFeature,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    ChoiceInput,
    ChoiceOption,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
    semver_key,
)
from loft_wire.sheet_goods import (
    SHEET_GOODS_BY_KEY,
    SheetGood,
    SheetGoodKey,
    SheetSizeKey,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import floor as floor_v1
from loft_plugins.builtin import house
from loft_plugins.builtin import wall as wall_v1

#: A wall sheathing panel's width and a subfloor panel's (in): a sheet's.
PANEL_WIDTH = 48.0
#: A subfloor panel's length, across the joists (in): a 4x8's.
SUBFLOOR_LENGTH = 96.0
#: The narrowest piece cut (in): a wall end or an opening's edge closer than
#: this to a panel joint takes the joint, so no panel is a sub-micron sliver
#: (inputs are rounded to 1e-9 in, so 144.000000002 is a possible length).
_SLIVER = 1e-6
#: The trade's minimum rip (in): an opening whose edge would leave a strip of
#: panel narrower than this beside it is cut out to the joint instead. The
#: snap only ever moves an edge OUTWARD, enlarging the cut-out: a panel never
#: covers any part of a rough opening.
_TRADE_MIN = 1 / 8
#: Rounding of a coordinate before it is compared (the inputs' 1e-9 in).
_DIGITS = 9


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


# --- Rectilinear panels (pure) -------------------------------------------------------

Point = tuple[float, float]
Loop = list[Point]


@dataclass(frozen=True)
class Region:
    """One connected panel: its outer loop (counterclockwise) and its holes
    (clockwise), in the panel's plane coordinates (inches)."""

    outer: Loop
    holes: list[Loop]

    @property
    def area(self) -> float:
        return _signed_area(self.outer) + sum(_signed_area(h) for h in self.holes)


def _signed_area(loop: Sequence[Point]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(loop, [*loop[1:], loop[0]], strict=True):
        total += x0 * y1 - x1 * y0
    return total / 2


Rect = tuple[float, float, float, float]  # x0, x1, y0, y1


def rect_minus_rects(outer: Rect, cuts: Iterable[Rect]) -> list[Region]:
    """*outer* with every rectangle of *cuts* removed, as connected regions
    (each an outer loop and its holes), in a deterministic order.

    The rectangle is split on every cut edge inside it into a grid of cells;
    a cell is kept when its centre is in no cut. The kept cells' boundary,
    walked with the kept side on the left, is the regions' loops; each loop's
    collinear points are dropped. Every coordinate is one of the inputs', so
    a panel edge meets its neighbour's exactly."""
    x0, x1, y0, y1 = outer

    def low(v: float, lo: float, hi: float) -> float:
        """A cut's low edge: down to *lo* if it would leave a strip under the
        trade minimum below it; within float noise of either edge, that edge."""
        if lo <= v <= lo + _TRADE_MIN or abs(v - lo) <= _SLIVER:
            return lo
        return hi if abs(v - hi) <= _SLIVER else v

    def high(v: float, lo: float, hi: float) -> float:
        """A cut's high edge: up to *hi* if it would leave a strip under the
        trade minimum above it; within float noise of either edge, that edge."""
        if hi - _TRADE_MIN <= v <= hi or abs(v - hi) <= _SLIVER:
            return hi
        return lo if abs(v - lo) <= _SLIVER else v

    snapped = [
        (low(c[0], x0, x1), high(c[1], x0, x1), low(c[2], y0, y1), high(c[3], y0, y1))
        for c in cuts
    ]
    inside = [c for c in snapped if c[0] < x1 and c[1] > x0 and c[2] < y1 and c[3] > y0]
    xs = sorted({x0, x1, *(v for c in inside for v in c[:2] if x0 < v < x1)})
    ys = sorted({y0, y1, *(v for c in inside for v in c[2:] if y0 < v < y1)})
    nx, ny = len(xs) - 1, len(ys) - 1

    def kept(i: int, j: int) -> bool:
        if not (0 <= i < nx and 0 <= j < ny):
            return False
        cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
        return not any(c[0] < cx < c[1] and c[2] < cy < c[3] for c in inside)

    # Connected components of the kept cells (edge-adjacent), in scan order.
    component: dict[tuple[int, int], int] = {}
    count = 0
    for i in range(nx):
        for j in range(ny):
            if not kept(i, j) or (i, j) in component:
                continue
            stack = [(i, j)]
            component[(i, j)] = count
            while stack:
                a, b = stack.pop()
                for n in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if kept(*n) and n not in component:
                        component[n] = count
                        stack.append(n)
            count += 1

    # Directed boundary edges on grid indices, the kept cell on the left.
    edges: dict[tuple[int, int], tuple[tuple[int, int], int]] = {}
    for (i, j), comp in component.items():
        sides = (
            ((i, j - 1), (i, j), (i + 1, j)),
            ((i + 1, j), (i + 1, j), (i + 1, j + 1)),
            ((i, j + 1), (i + 1, j + 1), (i, j + 1)),
            ((i - 1, j), (i, j + 1), (i, j)),
        )
        for neighbour, start, end in sides:
            if not kept(*neighbour):
                if start in edges:
                    raise ValueError("panel cuts meet only at a corner")
                edges[start] = (end, comp)

    loops: dict[int, list[Loop]] = {c: [] for c in range(count)}
    while edges:
        start = min(edges)
        points = [start]
        comp = edges[start][1]
        at = start
        while True:
            nxt, _ = edges.pop(at)
            if nxt == start:
                break
            points.append(nxt)
            at = nxt
        loops[comp].append(_simplified([(xs[p[0]], ys[p[1]]) for p in points]))

    regions: list[Region] = []
    for comp in range(count):
        outers = [loop for loop in loops[comp] if _signed_area(loop) > 0]
        holes = [loop for loop in loops[comp] if _signed_area(loop) < 0]
        assert len(outers) == 1
        regions.append(Region(outers[0], holes))
    return regions


def _simplified(loop: Loop) -> Loop:
    """*loop* without its collinear points, starting at its lowest-left
    corner (so the same panel always sketches the same way)."""
    n = len(loop)
    corners: Loop = []
    for k in range(n):
        (ax, ay), (bx, by), (cx, cy) = loop[k - 1], loop[k], loop[(k + 1) % n]
        if (ax == bx == cx) or (ay == by == cy):
            continue
        corners.append((bx, by))
    first = min(range(len(corners)), key=lambda k: (corners[k][1], corners[k][0]))
    return corners[first:] + corners[:first]


def strips(
    length: float, width: float, offset: float = 0.0
) -> list[tuple[float, float]]:
    """``0..length`` cut into *width* pieces from ``-offset`` (a staggered row
    starts with a piece ``width - offset`` long), the last cut at *length*."""
    out: list[tuple[float, float]] = []
    start = 0.0
    end = width - offset if offset > 0 else width
    while start < length - _SLIVER:
        out.append((start, length if end >= length - _SLIVER else end))
        start, end = end, end + width
    return out


# --- Emission ----------------------------------------------------------------------


def _loops_entities(
    loops: Sequence[Sequence[Point2D]],
) -> list[SketchLine]:
    """Closed loops of sketch lines, ids ``e1``.. running across the loops."""
    lines: list[SketchLine] = []
    for loop in loops:
        for k, start in enumerate(loop):
            lines.append(
                SketchLine(
                    id=f"e{len(lines) + 1}",
                    kind="line",
                    start=start,
                    end=loop[(k + 1) % len(loop)],
                )
            )
    return lines


def _panel_members(
    inputs: ExpandInputs,
    roles: tuple[str, str],
    index: int,
    plane: DatumPlaneRef | FeatureRef,
    loops: Sequence[Sequence[Point2D]],
    good: SheetGood,
    reverse: bool,
    name: str,
    sheet: SheetSizeKey | None = None,
) -> Iterator[Member]:
    """One panel: its outline sketch and the extrude of it by the product's
    thickness, a new body carrying the product and its material, and the
    *sheet* it is hung from when that is not the shortest that covers it
    (GYPSUM-SHEETS). Both are named by the panel's place (*name*), so an
    opening moving or a wall growing never hands one panel's id to another
    (WALL-MEMBER-RENUMBER)."""
    section, role = roles
    yield Member(
        section,
        index,
        SketchFeature(
            type="sketch",
            version=1,
            params=SketchParamsV1(
                plane=plane, entities=list(_loops_entities(loops)), constraints=[]
            ),
        ),
        name=name,
    )
    yield Member(
        role,
        index,
        ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(
                profile=inputs.ref(section, index, name),
                distance_mm=good.thickness_mm,
                operation="add",
                direction="reverse" if reverse else "normal",
                merge=False,
            ),
        ),
        MemberMetadata(profile=good.name, material=good.material, sheet=sheet),
        name=name,
    )


def _good(inputs: ExpandInputs, name: str) -> SheetGood | None:
    value = inputs.choice(name)
    return SHEET_GOODS_BY_KEY.get(value)  # type: ignore[call-overload]


# --- Wall sheathing ------------------------------------------------------------------

#: The wall's sheathing options after None (the default: 1.1.0's wall).
WALL_SHEATHING: list[SheetGoodKey] = ["osb_7_16", "plywood_15_32"]


def wall_panels(
    wall: wall_v1.WallSpec, openings: Sequence[wall_v1.Opening]
) -> list[Region]:
    """The exterior face's panels in the wall's ``(u, z)`` (inches): 48 in
    strips from the wall's start, full height, each less the rough openings
    over it, in order along the wall."""
    return [region for _, region in placed_wall_panels(wall, openings)]


def placed_wall_panels(
    wall: wall_v1.WallSpec, openings: Sequence[wall_v1.Opening]
) -> list[tuple[str, Region]]:
    """:func:`wall_panels` with each panel's place name: ``exterior/<col>/
    <row>``, the column the 48 in strip from the wall's start and the row
    the piece of it counted from the bottom (1 only where an opening cuts a
    strip in two)."""
    return placed_wall_panels_between(wall, openings, 0.0, wall.length)


def placed_wall_panels_between(
    wall: wall_v1.WallSpec,
    openings: Sequence[wall_v1.Opening],
    first: float,
    last: float,
) -> list[tuple[str, Region]]:
    """:func:`placed_wall_panels` on the part ``first..last`` of the wall
    (``u``, inches): 48 in strips from *first*. An outline wall's face is
    sheathed short of an inside corner (BUILDING-OUTLINE); a whole face is
    ``0..length``, which is :func:`placed_wall_panels` exactly."""
    cuts = [
        (o.centre - o.width / 2, o.centre + o.width / 2, o.sill, o.head)
        for o in openings
    ]
    out: list[tuple[str, Region]] = []
    for col, (u0, u1) in enumerate(strips(last - first, PANEL_WIDTH)):
        pieces = rect_minus_rects((first + u0, first + u1, 0.0, wall.height), cuts)
        pieces.sort(
            key=lambda r: (min(y for _, y in r.outer), min(x for x, _ in r.outer))
        )
        out += [(f"exterior/{col}/{row}", r) for row, r in enumerate(pieces)]
    return out


@dataclass(frozen=True)
class FacePlane:
    """The vertical plane a wall's panels are sketched on (its normal
    outward, at the exterior face), and how wall ``(u, z)`` maps to its
    sketch ``(x, y)`` in mm.

    ``axis`` is ``"x"`` for the ``XZ`` datum (sketch x is world X, y is Z),
    ``"y"`` for ``YZ`` (x is world Y, y is Z) and ``"angle"`` for the plane
    through +Z (x is Z, y is the plane's in-plan ``y_dir``)."""

    frame: wall_v1.WallFrame
    axis: str
    origin: DatumPlaneRef | None
    offset_mm: float
    angle_deg: float
    reverse: bool
    y_dir: tuple[float, float]

    def sketch_point(self, u: float, z: float) -> Point2D:
        px, py = self.frame.plan(u, 0.0)
        height = _mm(self.frame.base + z)
        if self.axis == "x":
            return Point2D(x=_mm(px), y=height)
        if self.axis == "y":
            return Point2D(x=_mm(py), y=height)
        return Point2D(x=height, y=_mm(px) * self.y_dir[0] + _mm(py) * self.y_dir[1])

    def members(
        self,
        inputs: ExpandInputs,
        prefix: str = "",
        first: int = 0,
        role: str = "sheathing_plane",
    ) -> tuple[list[Member], DatumPlaneRef | FeatureRef]:
        """The datum members that make the plane, and the plane's reference,
        in *role* (a wall's gypsum planes are ``finish_plane``)."""
        if self.axis != "angle":
            base = "XZ" if self.axis == "x" else "YZ"
            if self.offset_mm == 0.0:
                return [], DatumPlaneRef(kind="datum_plane", plane=base)
            datum = DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base=base, offset_mm=self.offset_mm),
            )
            face = f"{prefix}face"
            return [Member(role, first, datum, name=face)], inputs.ref(
                role, first, face
            )
        face, turn = f"{prefix}face", f"{prefix}turned"
        turned = Member(
            role,
            first,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumAngleParams(
                    kind="angle",
                    line=DatumOriginAxisRef(kind="origin_axis", axis="Z"),
                    reference=DatumPlaneRef(kind="datum_plane", plane="YZ"),
                    angle_deg=self.angle_deg,
                ),
            ),
            name=turn,
        )
        if self.offset_mm == 0.0:
            return [turned], inputs.ref(role, first, turn)
        slid = Member(
            role,
            first + 1,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetFromParams(
                    kind="offset_from",
                    base=inputs.ref(role, first, turn),
                    offset_mm=self.offset_mm,
                ),
            ),
            name=face,
        )
        return [turned, slid], inputs.ref(role, first + 1, face)


def face_plane(wall: wall_v1.WallSpec) -> FacePlane:
    """The exterior face's plane (module docstring): exact on the axes."""
    frame = wall_v1.WallFrame.of(wall)
    out = (-frame.across[0] + 0.0, -frame.across[1] + 0.0)
    if out[0] == 0.0:
        # Along X: XZ (normal -Y) moved to the face's Y; outward +Y reverses.
        return FacePlane(frame, "x", None, -_mm(frame.y) + 0.0, 0.0, out[1] > 0, (0, 0))
    if out[1] == 0.0:
        # Along Y: YZ (normal +X) moved to the face's X; outward -X reverses.
        return FacePlane(frame, "y", None, _mm(frame.x) + 0.0, 0.0, out[0] < 0, (0, 0))
    # The kernel's plane through +Z turned `angle` from YZ: normal
    # (cos a, sin a, 0), y_dir = normal x Z = (sin a, -cos a, 0), through the
    # origin; then slid along the normal to the face.
    angle = math.degrees(math.atan2(out[1], out[0])) % 360.0
    radians = math.radians(angle)
    normal = (math.cos(radians), math.sin(radians))
    offset = _mm(frame.x) * normal[0] + _mm(frame.y) * normal[1]
    return FacePlane(
        frame, "angle", None, offset, angle, False, (normal[1], -normal[0])
    )


# --- Outside corners ------------------------------------------------------------------

#: How close two walls' faces must meet to be a corner (in).
_CORNER_TOL = 1e-6

End = Literal["start", "end"]


@dataclass(frozen=True)
class EarlierWall:
    """An earlier ``loft.wall`` in the tree: its spec and sheathing product."""

    spec: wall_v1.WallSpec
    good: SheetGood | None


def earlier_walls(inputs: ExpandInputs) -> list[EarlierWall]:
    """Every earlier ``loft.wall`` (any version; only 1.2.x is sheathed), in
    tree order, read from its stored inputs as a roof reads its walls."""
    out: list[EarlierWall] = []
    for feature_id, envelope in inputs.earlier.items():
        if not isinstance(envelope, CustomFeature):
            continue
        if envelope.params.plugin_id != "loft.wall":
            continue
        values = ExpandInputs(feature_id, envelope.params.inputs)
        try:
            # A 1.3.0 wall may stand on a floor or be an outline's walls
            # (BUILDING-OUTLINE); earlier releases are one typed line.
            specs = house.wall_specs_of(
                feature_id, envelope, inputs.earlier, inputs.parameters
            )
        except PluginError:
            continue
        good = None
        if semver_key(envelope.params.plugin_version) >= (1, 2, 0) and (
            "sheathing" in envelope.params.inputs
        ):
            good = _good(values, "sheathing")
        out += [EarlierWall(spec, good) for _, spec in specs]
    return out


def butts(b: wall_v1.WallSpec, b_end: End, t: wall_v1.WallSpec) -> End | None:
    """The end of *t* that *b*'s *b_end* butts against, or ``None``: *b*'s end
    lies on *t*'s interior face at *t*'s end, *b* runs away from *t* square to
    it, *b*'s exterior face is flush with *t*'s end face, and both stand on
    the same base. B2's side walls butt the front and back walls."""
    fb, ft = wall_v1.WallFrame.of(b), wall_v1.WallFrame.of(t)
    if abs(b.elevation - t.elevation) > _CORNER_TOL:
        return None
    ex, ey = fb.plan(0.0 if b_end == "start" else b.length, 0.0)
    rx, ry = ex - ft.x, ey - ft.y
    u = rx * ft.along[0] + ry * ft.along[1]
    v = rx * ft.across[0] + ry * ft.across[1]
    if abs(v - t.thickness) > _CORNER_TOL:
        return None
    if abs(u) <= _CORNER_TOL:
        t_end: End = "start"
        inward = ft.along
    elif abs(u - t.length) <= _CORNER_TOL:
        t_end = "end"
        inward = (-ft.along[0], -ft.along[1])
    else:
        return None
    sign = 1.0 if b_end == "start" else -1.0
    away = (sign * fb.along[0], sign * fb.along[1])

    def same(a: tuple[float, float], c: tuple[float, float]) -> bool:
        return abs(a[0] - c[0]) <= _CORNER_TOL and abs(a[1] - c[1]) <= _CORNER_TOL

    if same(away, ft.across) and same(fb.across, inward):
        return t_end
    return None


def _thickness(good: SheetGood | None) -> float:
    return 0.0 if good is None else good.thickness_mm / MM_PER_INCH


def corner_rip(
    b: wall_v1.WallSpec, b_end: End, t: wall_v1.WallSpec, t_good: SheetGood | None
) -> Region:
    """The piece in *b*'s exterior plane (*b*'s ``(u, z)``) that laps past
    *b*'s end over *t*'s end grain and sheathing edge: *t*'s framing depth
    plus its sheathing thickness wide, *b*'s full height."""
    width = t.thickness + _thickness(t_good)
    u0, u1 = (-width, 0.0) if b_end == "start" else (b.length, b.length + width)
    return Region([(u0, 0.0), (u1, 0.0), (u1, b.height), (u0, b.height)], [])


def wall_sheathing(inputs: ExpandInputs) -> Iterator[Member]:
    """The wall's sheathing members: its own panels (none when the option is
    None), then the outside corners it closes (module docstring)."""
    good = _good(inputs, "sheathing")
    wall = wall_v1.WallSpec.from_inputs(inputs)
    others = earlier_walls(inputs)
    index = 0
    if good is not None:
        plane = face_plane(wall)
        datums, ref = plane.members(inputs)
        yield from datums
        placed = placed_wall_panels(wall, wall_v1.hosted_openings(inputs, wall))
        # This wall butts an earlier one: its run laps past that end.
        for end in ("start", "end"):
            for other in others:
                if butts(wall, end, other.spec) is not None:
                    rip = corner_rip(wall, end, other.spec, other.good)
                    placed.append((f"corner/{end}", rip))
                    break
        for name, region in placed:
            loops = [
                [plane.sketch_point(u, z) for u, z in loop]
                for loop in (region.outer, *region.holes)
            ]
            yield from _panel_members(
                inputs,
                ("sheathing_section", "sheathing"),
                index,
                ref,
                loops,
                good,
                plane.reverse,
                name,
            )
            index += 1
    # An earlier sheathed wall butts this one: this wall closes that corner,
    # with the earlier wall's product in the earlier wall's plane.
    first = 2
    for other in others:
        if other.good is None:
            continue
        for b_end in ("start", "end"):
            t_end = butts(other.spec, b_end, wall)
            if t_end is None:
                continue
            plane = face_plane(other.spec)
            prefix = f"return/{t_end}/"
            datums, ref = plane.members(inputs, prefix, first)
            first += 2
            yield from datums
            rip = corner_rip(other.spec, b_end, wall, good)
            loops = [[plane.sketch_point(u, z) for u, z in rip.outer]]
            yield from _panel_members(
                inputs,
                ("sheathing_section", "sheathing"),
                index,
                ref,
                loops,
                other.good,
                plane.reverse,
                f"return/{t_end}",
            )
            index += 1


def _expand_wall(inputs: ExpandInputs) -> Iterator[Member]:
    # The framing is 1.1.0's (place-named, WALL-MEMBER-RENUMBER), member for
    # member; then the panels.
    yield from wall_v1.expand_v1_1(inputs)
    yield from wall_sheathing(inputs)


#: 1.2.0's wall and 1.1.0's floor, and their parts, for the releases built on
#: them (BUILDING-OUTLINE).
expand_wall_v1_2 = _expand_wall
panel_members = _panel_members
loops_entities = _loops_entities
sheet_good = _good


def _option(key: SheetGoodKey) -> ChoiceOption:
    return ChoiceOption(value=key, label=SHEET_GOODS_BY_KEY[key].name)


_NONE = ChoiceOption(value="none", label="None")

WALL_MANIFEST_V1_2 = PluginManifest(
    id="loft.wall",
    version="1.2.0",
    title=wall_v1.MANIFEST_V1_1.title,
    description="A framed stud wall: bottom plate, studs on a layout, a single "
    "or double top plate and optional exterior sheathing, with a cut list "
    "(Chief Architect, Medeek Wall).",
    inputs=[
        *wall_v1.MANIFEST_V1_1.inputs,
        ChoiceInput(
            kind="choice",
            name="sheathing",
            label="Exterior sheathing",
            description="Sheet panels on the exterior face, full height, 48 in "
            "wide from the wall's start, cut round its doors and windows.",
            options=[_NONE, *(_option(key) for key in WALL_SHEATHING)],
            default="none",
        ),
    ],
    members=[
        *wall_v1.MANIFEST_V1_1.members,
        PluginMemberRole(role="sheathing_plane", title="Plane"),
        PluginMemberRole(role="sheathing_section", title="Section"),
        PluginMemberRole(
            role="sheathing",
            title="Sheathing",
            description="One exterior sheathing panel, openings cut out.",
        ),
    ],
)

WALL_V1_2 = Plugin(WALL_MANIFEST_V1_2, _expand_wall)


# --- Subfloor ------------------------------------------------------------------------

#: The floor's subfloor options before None (the default first).
FLOOR_SUBFLOOR: list[SheetGoodKey] = ["plywood_23_32"]


def subfloor_panels(floor: floor_v1.FloorSpec) -> list[Rect]:
    """The subfloor's panels in the floor's ``(a, b)`` frame (inches): rows
    48 along the joists (``b``) from the start, each 96 long across them
    (``a``), every other row starting with a 48 piece (staggered 4 ft)."""
    return [rect for _, rect in placed_subfloor_panels(floor)]


def placed_subfloor_panels(floor: floor_v1.FloorSpec) -> list[tuple[str, Rect]]:
    """:func:`subfloor_panels` named by place: ``row/<r>/<c>``, the row along
    the joists from the start and the panel across them."""
    out: list[tuple[str, Rect]] = []
    for row, (b0, b1) in enumerate(strips(floor.span_b, PANEL_WIDTH)):
        offset = PANEL_WIDTH if row % 2 else 0.0
        for col, (a0, a1) in enumerate(strips(floor.span_a, SUBFLOOR_LENGTH, offset)):
            out.append((f"row/{row}/{col}", (a0, a1, b0, b1)))
    return out


def floor_subfloor(inputs: ExpandInputs) -> Iterator[Member]:
    """The floor's subfloor members (none when the option is None): one level
    at the joists' top, a sketch and an extrude per panel."""
    good = _good(inputs, "subfloor")
    if good is None:
        return
    floor = floor_v1.FloorSpec.from_inputs(inputs)
    frame = floor_v1.FloorFrame.of(floor)
    z = frame.base + floor.framing_top
    plane: DatumPlaneRef | FeatureRef
    if round(z, _DIGITS) + 0.0 == 0.0:
        plane = DatumPlaneRef(kind="datum_plane", plane="XY")
    else:
        yield Member(
            "subfloor_level",
            0,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base="XY", offset_mm=_mm(z)),
            ),
            name="top",
        )
        plane = inputs.ref("subfloor_level", 0, "top")
    for index, (name, (a0, a1, b0, b1)) in enumerate(placed_subfloor_panels(floor)):
        corners = [
            frame.plan(a, b) for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))
        ]
        loop = [Point2D(x=_mm(x), y=_mm(y)) for x, y in corners]
        yield from _panel_members(
            inputs,
            ("subfloor_section", "subfloor"),
            index,
            plane,
            [loop],
            good,
            False,
            name,
        )


def _expand_floor(inputs: ExpandInputs) -> Iterator[Member]:
    # The framing is 1.0.0's, member for member; then the subfloor.
    yield from floor_v1.expand(inputs)
    yield from floor_subfloor(inputs)


FLOOR_MANIFEST_V1_1 = PluginManifest(
    id="loft.floor",
    version="1.1.0",
    title=floor_v1.MANIFEST_V1.title,
    description="A framed platform floor: sill plates, rim joists, joists on "
    "a layout and a subfloor, with a cut list (Chief Architect, Medeek "
    "Foundation).",
    inputs=[
        *floor_v1.MANIFEST_V1.inputs,
        ChoiceInput(
            kind="choice",
            name="subfloor",
            label="Subfloor",
            description="4x8 panels on the joists, the long edge across them, "
            "rows staggered 4 ft.",
            options=[*(_option(key) for key in FLOOR_SUBFLOOR), _NONE],
            default=FLOOR_SUBFLOOR[0],
        ),
    ],
    members=[
        *floor_v1.MANIFEST_V1.members,
        PluginMemberRole(role="subfloor_level", title="Level"),
        PluginMemberRole(role="subfloor_section", title="Section"),
        PluginMemberRole(
            role="subfloor",
            title="Subfloor",
            description="One subfloor panel on the joists.",
        ),
    ],
)

FLOOR_V1_1 = Plugin(FLOOR_MANIFEST_V1_1, _expand_floor)

expand_floor_v1_1 = _expand_floor
