"""Interior walls: partitions on plan sketch lines, their backing in the walls
they meet, and gypsum board (INTERIOR-WALLS, RESEARCH §23).

As Chief Architect's Interior Wall tool and Revit's interior wall type draw
them. Two releases work together:

* ``loft.interior_wall`` 1.0.0 frames one partition per line OFF the loop of
  its exterior walls' outline sketch (``outline.read_plan``), or per line of
  a separate plan sketch. A partition is CENTRED on its line (Revit's default
  location line, "Wall Centerline"), 2x4 at 16 in o.c. by default, as tall as
  its walls and on the same base (the subfloor when they stand on a floor),
  with no sheathing and 1/2 in gypsum on both faces. Doors are ``loft.door``
  1.4.0 features hosted in it, one partition picked as their wall.
* ``loft.wall`` 1.4.0 is 1.3.0 member for member, plus: the BACKING it frames
  where a hosted partition meets it, as it frames the openings it hosts, an
  optional gypsum finish on its inside face, and On floor accepting a
  ``loft.slab`` (SLAB: the walls stand on its top and each bottom plate lists
  its anchor bolts, ``building_outline.on_slab``).

**Where a partition runs.** Its line gives its axis (horizontal or vertical,
by constraint) and its across position (solved from the sketch's dimensions,
as the outline's corners are; it must be fully defined). Its ends are the
framing it MEETS: from the middle of the drawn line, the first wall or
partition each way along it. So a partition follows the walls it runs
between when the house is resized, with no constraint tying its ends to
them (Loft's sketcher has no point-on-line), as Revit's walls stay joined.
It stops at the inside face of an exterior wall, and at the near face of a
partition it meets in a T. A partition blocks another's run only where its
drawn line spans the other's whole thickness, so a T's stem never stops the
partition it meets. Its studs lay out from its START, the end its line was
drawn from, as a wall's do from its start.

Refused (each names the line and what to change): a line not horizontal or
vertical, or not fully defined across; a run that meets no wall one way; a
partition meeting a wall at its end or corner, meeting another partition
end to end (an L between partitions is a later rung), crossing one, or
overlapping any framing; backing that would land in an opening's framing;
two backings in one place.

**Backing** (IRC R702.3.5 needs every edge of the board fastened; at a T the
board on the wall a partition meets needs something to land on). The wall a
partition meets frames it, flush with the face the partition meets:

* ``ladder`` (the default, and the energy-code choice: no extra studs in an
  insulated wall): flat blocks of the partition's stud size across the bay
  between the two studs either side of the partition, centred every 24 in
  above the bottom plate's top while they fit under the top plates (24, 48
  and 72 in on a 92-5/8 in stud, three blocks). A layout stud standing under
  the partition splits the ladder in two.
* ``three_stud``: two full-height studs of the wall's size flanking the
  partition, the partition's end stud the third; the layout studs they
  displace are dropped (an end stud never is: the partition is refused).

**Gypsum** (GA-216; Chief's wall layers): 4x8 sheets (4x12 a choice) hung
horizontally in 48 in courses down from the top of the top plate; a remainder
at the floor of 3 in or less is left for the base to cover, more is a ripped
course stopped 1/2 in above the base. Each face is laid out from its wall's
start in sheet lengths, the rough openings and the partitions meeting it cut
out. Where walls meet, the MET face's board runs to the meeting framing and
the meeting wall's board stops at the met board's face, so no two boards
overlap: a partition's board stops at the gypsum (or framing) of the wall it
meets; at an exterior wall's outside corner the through wall's inside board
runs to the fitted wall's framing and the fitted wall's stops at it; at an
inside corner the through wall's board runs on past its end by the board's
thickness, and the fitted wall's past its own by the through wall's depth,
over the through wall's end grain. Panels are listed under Walls and bought
by the sheets they are cut from, as every sheet good is (GYPSUM-SHEETS); a
face hung from 4x12s names its sheet on each panel (:func:`hung_sheet`), so
its end pieces are nested on 4x12s too, not bought as 4x8s.
"""

import dataclasses
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from loft_wire.expr import Quantity
from loft_wire.features import AuthoredEnvelope, CustomFeature, FeatureRef
from loft_wire.lumber import LumberProfile, LumberProfileKey
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    LengthInput,
    MaterialInput,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
    semver_key,
)
from loft_wire.sheet_goods import (
    SHEET_GOODS_BY_KEY,
    SHEET_SIZES_BY_KEY,
    SheetGood,
    SheetSizeKey,
)

from loft_plugins.api import (
    ExpandInputs,
    Hosted,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)
from loft_plugins.builtin import building_outline, house, sheathing
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.outline import (
    Axis,
    Outline,
    PartitionLine,
    outline_sketch,
    read_plan,
)

_DIGITS = 9
#: Two faces closer than this meet (in): the inputs' rounding.
_TOL = 1e-6
#: The release of ``loft.wall`` that frames a partition's backing.
WALL_BACKING_VERSION = (1, 4, 0)
#: The plugin id of a partition feature.
INTERIOR_WALL = "loft.interior_wall"

#: Ladder blocks are centred this far apart, from the bottom plate's top (in).
LADDER_SPACING = 24.0
#: A gypsum course's height (in): a sheet's width, hung horizontally.
COURSE = 48.0
#: A remainder at the floor up to this is left for the base to cover (in).
BASE_GAP = 3.0
#: A ripped bottom course stops this far above the base (in).
RIP_GAP = 0.5


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


# --- The layout (pure, inches) -------------------------------------------------------

ElementKey = tuple[Literal["wall", "partition"], str]
Backing = Literal["ladder", "three_stud"]


@dataclass(frozen=True)
class Element:
    """A wall or partition's framing in plan: its key, axis, spec, and its
    footprint ``x0, x1, y0, y1`` (in)."""

    key: ElementKey
    axis: Axis
    spec: wall_v1.WallSpec
    rect: tuple[float, float, float, float]
    #: An outline wall's place in the outline (``None`` for a partition).
    outline_wall: house.OutlineWall | None = None

    def span(self, i: int) -> tuple[float, float]:
        """The footprint along world axis *i* (0 X, 1 Y)."""
        return (self.rect[0], self.rect[1]) if i == 0 else (self.rect[2], self.rect[3])

    def u_of(self, coordinate: float) -> float:
        """The wall-frame ``u`` of a world coordinate along the element."""
        frame = wall_v1.WallFrame.of(self.spec)
        i = 0 if self.axis == "h" else 1
        start = (frame.x, frame.y)[i]
        return _r((coordinate - start) * frame.along[i])

    def v_of(self, coordinate: float) -> float:
        """The wall-frame ``v`` of a world coordinate across the element."""
        frame = wall_v1.WallFrame.of(self.spec)
        j = 1 if self.axis == "h" else 0
        start = (frame.x, frame.y)[j]
        return _r((coordinate - start) * frame.across[j])


def _rect(spec: wall_v1.WallSpec) -> tuple[float, float, float, float]:
    frame = wall_v1.WallFrame.of(spec)
    a = frame.plan(0.0, 0.0)
    b = frame.plan(spec.length, spec.thickness)
    return (
        _r(min(a[0], b[0])),
        _r(max(a[0], b[0])),
        _r(min(a[1], b[1])),
        _r(max(a[1], b[1])),
    )


def _axis_of(spec: wall_v1.WallSpec) -> Axis:
    return "h" if spec.direction_deg % 180.0 == 0.0 else "v"


@dataclass(frozen=True)
class Junction:
    """Where partition *meeting* meets element *met*: its footprint along the
    met element (``a..b``, its ``u``) and the face it meets (``v`` 0, or the
    element's depth)."""

    met: ElementKey
    meeting: str
    a: float
    b: float
    face_v: float


@dataclass(frozen=True)
class Partition:
    """One partition: its line, its framing spec, and what each end meets."""

    line_id: str
    spec: wall_v1.WallSpec
    start: ElementKey
    end: ElementKey


@dataclass(frozen=True)
class Layout:
    """A partition feature's partitions and every junction they make."""

    partitions: tuple[Partition, ...]
    junctions: tuple[Junction, ...]

    def at(self, key: ElementKey) -> list[Junction]:
        return [j for j in self.junctions if j.met == key]


def _refuse(message: str, input_name: str = "sketch") -> PluginError:
    return PluginError(PLUGIN_INPUT_INVALID, f"Partitions: {message}", input=input_name)


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(
        min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > _TOL for k in range(0, len(a), 2)
    )


def _name(key: ElementKey, outline: Outline | None) -> str:
    if key[0] == "partition":
        return f"partition {key[1]}"
    if outline is not None:
        for k, segment in enumerate(outline.segments):
            if segment.line_id == key[1]:
                return outline.label(k)
    return f"the wall {key[1]}"


def lay_out(
    lines: Sequence[PartitionLine],
    walls: Sequence[house.OutlineWall],
    base: wall_v1.WallSpec,
    outline: Outline | None = None,
) -> Layout:
    """Every partition of *lines* framed as *base* (stud, height, elevation,
    materials) between the *walls* it meets (module docstring)."""
    h = base.thickness / 2
    elements: list[Element] = [
        Element(("wall", w.line_id), _axis_of(w.spec), w.spec, _rect(w.spec), w)
        for w in walls
    ]
    by_line = {p.line_id: p for p in lines}
    if len(by_line) != len(lines):
        raise _refuse("two partitions share a line id; redraw one.")
    out: list[tuple[PartitionLine, float, float, ElementKey, ElementKey]] = []
    for line in lines:
        i = 0 if line.axis == "h" else 1  # along the line
        c = line.at
        d0, d1 = line.drawn
        if d0 == d1:
            raise _refuse(f"{line.line_id} is drawn with no length; redraw it.")
        middle = (d0 + d1) / 2
        hits: dict[int, tuple[float, ElementKey]] = {}
        for wall in elements:
            if wall.axis == line.axis:
                continue
            r0, r1 = wall.span(1 - i)
            if not r0 < c < r1:
                continue
            s0, s1 = wall.span(i)
            if s0 >= middle and (1 not in hits or s0 < hits[1][0]):
                hits[1] = (s0, wall.key)
            if s1 <= middle and (-1 not in hits or s1 > hits[-1][0]):
                hits[-1] = (s1, wall.key)
        for other in lines:
            if other.axis == line.axis or other.line_id == line.line_id:
                continue
            lo, hi = sorted(other.drawn)
            if not (lo <= c - h + _TOL and c + h - _TOL <= hi):
                continue
            s0, s1 = other.at - h, other.at + h
            key: ElementKey = ("partition", other.line_id)
            if s0 >= middle and (1 not in hits or s0 < hits[1][0]):
                hits[1] = (s0, key)
            if s1 <= middle and (-1 not in hits or s1 > hits[-1][0]):
                hits[-1] = (s1, key)
        for way in (-1, 1):
            if way not in hits:
                raise _refuse(
                    f"{line.line_id} meets no wall towards its "
                    f"{'start' if (way < 0) == (d1 > d0) else 'end'}; a partition "
                    "runs between walls or partitions (draw it inside the outline)."
                )
        lo_s, lo_key = hits[-1]
        hi_s, hi_key = hits[1]
        forward = d1 > d0
        start, end = (lo_key, hi_key) if forward else (hi_key, lo_key)
        out.append((line, _r(lo_s), _r(hi_s), start, end))

    meets = {line.line_id: (start, end) for line, _, _, start, end in out}
    for line_id, ends in meets.items():
        for key in ends:
            if key[0] == "partition" and ("partition", line_id) in meets[key[1]]:
                raise _refuse(
                    f"{min(line_id, key[1])} and {max(line_id, key[1])} cross; "
                    "split one where they cross, so each ends on the other."
                )
    partitions: list[Partition] = []
    for line, lo, hi, start, end in out:
        forward = line.drawn[1] > line.drawn[0]
        length = _r(hi - lo)
        if not 12.0 - 1e-9 <= length <= 960.0 + 1e-9:
            raise _refuse(
                f"{line.line_id} would be {length:g} in long between the walls it "
                "meets; a partition is 12 to 960 in."
            )
        direction = {
            ("h", True): 0.0,
            ("h", False): 180.0,
            ("v", True): 90.0,
            ("v", False): 270.0,
        }[(line.axis, forward)]
        along = lo if forward else hi
        spec = dataclasses.replace(
            base,
            start_x=0.0,
            start_y=0.0,
            direction_deg=direction,
            length=length,
            side="right",
        )
        # Centred on the line: the framing lies right of the direction, so the
        # line is half the depth to its left.
        across = wall_v1.WallFrame.of(spec).across
        point = (along, line.at) if line.axis == "h" else (line.at, along)
        spec = dataclasses.replace(
            spec,
            start_x=_r(point[0] - h * across[0]),
            start_y=_r(point[1] - h * across[1]),
        )
        partitions.append(Partition(line.line_id, spec, start, end))

    p_elements = {
        p.line_id: Element(
            ("partition", p.line_id),
            next(line.axis for line in lines if line.line_id == p.line_id),
            p.spec,
            _rect(p.spec),
        )
        for p in partitions
    }
    every = {**{e.key: e for e in elements}, **{e.key: e for e in p_elements.values()}}
    # No partition overlaps any framing.
    for p in partitions:
        mine = p_elements[p.line_id]
        for other in every.values():
            if other.key == mine.key:
                continue
            if _overlap(mine.rect, other.rect):
                raise _refuse(
                    f"{p.line_id} crosses or overlaps {_name(other.key, outline)}; "
                    "partitions meet walls and each other only in a T (an L "
                    "between partitions is a later rung): move it, or split it "
                    "where it crosses."
                )
    junctions: list[Junction] = []
    for p in partitions:
        mine = p_elements[p.line_id]
        i = 0 if mine.axis == "h" else 1
        for end_name, key in (("start", p.start), ("end", p.end)):
            met = every[key]
            lo, hi = mine.span(1 - i)  # the partition's thickness, along met
            r0, r1 = met.span(1 - i)
            if not (r0 - _TOL <= lo and hi <= r1 + _TOL) or (
                key[0] == "partition" and (abs(lo - r0) <= _TOL or abs(hi - r1) <= _TOL)
            ):
                raise _refuse(
                    f"{p.line_id}'s {end_name} meets {_name(key, outline)} at its "
                    "end or corner; move it along, clear of the corner"
                    + (
                        " (an L between partitions is a later rung)."
                        if key[0] == "partition"
                        else "."
                    )
                )
            # The met face: the one nearer the partition's middle.
            s0, s1 = met.span(i)
            mid = sum(mine.span(i)) / 2
            face = s0 if mid < s0 else s1
            u = sorted((met.u_of(lo), met.u_of(hi)))
            junctions.append(Junction(key, p.line_id, u[0], u[1], met.v_of(face)))
    return Layout(tuple(partitions), tuple(junctions))


# --- Backing in the wall a partition meets --------------------------------------------

#: The roles that frame an opening: backing never lands in them.
_OPENING_ROLES = frozenset(
    {"king", "jack", "header", "cripple", "sill", "sill_cripple"}
)


def backed_pieces(
    wall: wall_v1.WallSpec,
    pieces: Sequence[wall_v1.Piece],
    junctions: Sequence[Junction],
    style: Backing,
    block: LumberProfile,
    name_of: Mapping[str, str],
    label: str,
) -> list[wall_v1.Piece]:
    """*pieces* (a wall's or partition's members, named) with the backing of
    every junction framed in (module docstring). *name_of* names each
    meeting partition's members (``backing/<name>/<k>``); *label* names this
    wall in a refusal."""
    t, depth = wall.stud.thickness_in, wall.thickness
    stud_top = t + wall.stud_length
    kept = list(pieces)
    added: list[wall_v1.Piece] = []
    first, last = 0.0, wall.length
    for j in sorted(junctions, key=lambda j: (j.a, j.meeting)):
        reach = t if style == "three_stud" else 0.0
        a, b = j.a - reach, j.b + reach
        for p in kept:
            if p.role in _OPENING_ROLES and p.u1 > a + _TOL and p.u0 < b - _TOL:
                raise _refuse(
                    f"{j.meeting} meets {label} in an opening's framing; move it "
                    "along, clear of the opening."
                )
        name = f"backing/{name_of[j.meeting]}"
        if style == "three_stud":
            displaced = [
                p
                for p in kept
                if p.role == "stud" and p.u1 > a + _TOL and p.u0 < b - _TOL
            ]
            if (
                a < first + t - _TOL
                or b > last - t + _TOL
                or any(p.name in ("start", "end") for p in displaced)
            ):
                raise _refuse(
                    f"{j.meeting} meets {label} too near its end for two flanking "
                    "studs; use ladder backing, or move it."
                )
            kept = [p for p in kept if p not in displaced]
            mine = [
                wall_v1.Piece(
                    "backing_stud",
                    wall.stud,
                    wall.stud_material,
                    u0,
                    u1,
                    0.0,
                    depth,
                    t,
                    stud_top,
                    f"{name}/{k}",
                )
                for k, (u0, u1) in enumerate(((a, j.a), (j.b, b)))
            ]
        else:
            verticals = sorted(
                (p for p in kept if p.role in ("stud", "king")), key=lambda p: p.u0
            )
            left = max((p.u1 for p in verticals if p.u1 <= a + _TOL), default=None)
            right = min((p.u0 for p in verticals if p.u0 >= b - _TOL), default=None)
            if left is None or right is None:
                raise _refuse(
                    f"{j.meeting} meets {label} past its end studs; move it along."
                )
            inner = [
                p for p in verticals if p.u0 >= left - _TOL and p.u1 <= right + _TOL
            ]
            edges = [left]
            for p in inner:
                edges += [p.u0, p.u1]
            edges.append(right)
            bays = [
                (edges[k], edges[k + 1])
                for k in range(0, len(edges), 2)
                if edges[k + 1] - edges[k] > _TOL
            ]
            v0 = 0.0 if j.face_v == 0.0 else depth - block.thickness_in
            v1 = v0 + block.thickness_in
            centres: list[float] = []
            k = 1
            while t + k * LADDER_SPACING + block.width_in / 2 <= stud_top + _TOL:
                centres.append(t + k * LADDER_SPACING)
                k += 1
            mine = [
                wall_v1.Piece(
                    "block",
                    block,
                    wall.stud_material,
                    u0,
                    u1,
                    v0,
                    v1,
                    _r(zc - block.width_in / 2),
                    _r(zc + block.width_in / 2),
                    f"{name}/{n}",
                )
                for n, ((u0, u1), zc) in enumerate(
                    (bay, zc) for bay in bays for zc in centres
                )
            ]
        for piece in mine:
            for other in added:
                if _overlap(
                    (piece.u0, piece.u1, piece.v0, piece.v1, piece.z0, piece.z1),
                    (other.u0, other.u1, other.v0, other.v1, other.z0, other.z1),
                ):
                    raise _refuse(
                        f"two partitions meet {label} in one place ({j.meeting}); "
                        "move one along."
                    )
        added += mine
    return [*kept, *added]


# --- Gypsum ---------------------------------------------------------------------------


def courses(height: float) -> list[tuple[float, float]]:
    """A face's courses (``z0, z1`` above the base), top down: 48 in each
    from the top of the top plate, a remainder over :data:`BASE_GAP` a
    ripped course stopped :data:`RIP_GAP` above the base."""
    out: list[tuple[float, float]] = []
    top = height
    while top - COURSE >= -_TOL:
        out.append((_r(top - COURSE), _r(top)))
        top = _r(top - COURSE)
    if top > BASE_GAP + _TOL:
        out.append((RIP_GAP, top))
    return out


def finish_regions(
    height: float,
    first: float,
    last: float,
    sheet_length: float,
    cuts: Sequence[sheathing.Rect],
) -> list[tuple[str, sheathing.Region]]:
    """A face's gypsum panels in its wall's ``(u, z)``: each course cut into
    sheet lengths from *first* to *last*, less *cuts*, named
    ``<course>/<col>/<k>``."""
    out: list[tuple[str, sheathing.Region]] = []
    for row, (z0, z1) in enumerate(courses(height)):
        for col, (u0, u1) in enumerate(sheathing.strips(last - first, sheet_length)):
            pieces = sheathing.rect_minus_rects(
                (_r(first + u0), _r(first + u1), z0, z1), cuts
            )
            pieces.sort(
                key=lambda r: (min(y for _, y in r.outer), min(x for x, _ in r.outer))
            )
            out += [(f"{row}/{col}/{k}", r) for k, r in enumerate(pieces)]
    return out


def flipped(spec: wall_v1.WallSpec) -> wall_v1.WallSpec:
    """*spec* seen from its other face: the same ``u``, its ``v = depth``
    face as the exterior face, so :func:`sheathing.face_plane` gives that
    face's plane, its outward normal into the room."""
    frame = wall_v1.WallFrame.of(spec)
    return dataclasses.replace(
        spec,
        start_x=_r(spec.start_x + spec.thickness * frame.across[0]),
        start_y=_r(spec.start_y + spec.thickness * frame.across[1]),
        side="left" if spec.side == "right" else "right",
    )


def finish_members(
    inputs: ExpandInputs,
    spec: wall_v1.WallSpec,
    good: SheetGood,
    regions: Sequence[tuple[str, sheathing.Region]],
    face: str,
    plane_index: int,
    panel_index: int,
    sheet: SheetSizeKey | None = None,
) -> Iterator[Member]:
    """The panels of one face (on *spec*'s exterior face: :func:`flipped`
    for the other), named ``finish/<face>/...`` under *inputs*' prefix,
    each naming the *sheet* it is hung from (:func:`hung_sheet`)."""
    if not regions:
        return
    plane = sheathing.face_plane(spec)
    datums, ref = plane.members(inputs, f"finish/{face}/", plane_index, "finish_plane")
    yield from datums
    for k, (name, region) in enumerate(regions):
        loops = [
            [plane.sketch_point(u, z) for u, z in loop]
            for loop in (region.outer, *region.holes)
        ]
        yield from sheathing.panel_members(
            inputs,
            ("finish_section", "finish"),
            panel_index + k,
            ref,
            loops,
            good,
            plane.reverse,
            f"finish/{face}/{name}",
            sheet,
        )


def _finish_good(inputs: ExpandInputs, name: str = "finish") -> SheetGood | None:
    if name not in inputs.values:
        return None
    return SHEET_GOODS_BY_KEY.get(inputs.choice(name))  # type: ignore[call-overload]


def _sheet_length(inputs: ExpandInputs, name: str = "finish_sheet") -> float:
    choice = inputs.choice(name) if name in inputs.values else "sheet_4x8"
    key = choice.removeprefix("sheet_")
    size = SHEET_SIZES_BY_KEY.get(key)  # type: ignore[call-overload]
    if size is None:
        raise PluginError(PLUGIN_INPUT_INVALID, f"{key!r} is not a sheet.", input=name)
    return size.length_in


def hung_sheet(inputs: ExpandInputs, name: str = "finish_sheet") -> SheetSizeKey | None:
    """The sheet a face's panels name as the one they are hung from
    (GYPSUM-SHEETS): a 4x12 choice, so the cut list nests every panel of it,
    end pieces too, on 4x12s. 4x8 (the default) is the shortest gypsum
    sheet, which the cut list picks for every panel it covers anyway, so its
    panels name none and stay byte for byte what they were."""
    choice = inputs.choice(name) if name in inputs.values else "sheet_4x8"
    key = choice.removeprefix("sheet_")
    return None if key == "4x8" else key  # type: ignore[return-value]


def _rename(
    members: Iterator[Member], prefix: str, counts: Counter[str]
) -> Iterator[Member]:
    """*members* (emitted under the name prefix *prefix*) named under it and
    numbered on across the expansion, as the outline walls are."""
    for member in members:
        if member.name is None:
            raise RuntimeError(f"unnamed {member.role} in a partition")
        yield dataclasses.replace(
            member, index=counts[member.role], name=f"{prefix}/{member.name}"
        )
        counts[member.role] += 1


# --- Reading the features -------------------------------------------------------------


@dataclass(frozen=True)
class Host:
    """A partition feature's exterior walls: their outline, the walls, their
    shared spec, and the inside finish they carry."""

    feature_id: uuid.UUID
    outline: Outline
    sketch: FeatureRef
    walls: tuple[house.OutlineWall, ...]
    base: wall_v1.WallSpec
    finish: SheetGood | None


def host_of(
    ref: FeatureRef,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity],
) -> Host:
    """The exterior walls a partition feature names (``host_wall``)."""
    envelope = earlier.get(ref.feature_id)
    if (
        not isinstance(envelope, CustomFeature)
        or envelope.params.plugin_id != "loft.wall"
    ):
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Exterior walls: pick an earlier Wall drawn on an outline.",
            input="host_wall",
        )
    if semver_key(envelope.params.plugin_version) < WALL_BACKING_VERSION:
        raise PluginError(
            PLUGIN_INPUT_UNSUPPORTED,
            f"Exterior walls: Wall {envelope.params.plugin_version} cannot frame "
            "a partition's backing; update the walls to 1.4.0.",
            input="host_wall",
        )
    inputs = house.stored_inputs(ref.feature_id, envelope, earlier, parameters)
    outline = house.wall_outline(inputs)
    sketch = inputs.optional_feature("outline")
    if outline is None or sketch is None:
        raise PluginError(
            PLUGIN_INPUT_UNSUPPORTED,
            "Exterior walls: partitions stand inside walls drawn on an outline; "
            "pick a Wall with an Outline.",
            input="host_wall",
        )
    walls = house.outline_walls(inputs, outline)
    base = wall_v1.WallSpec.from_inputs(house.wall_values(inputs))
    return Host(
        ref.feature_id, outline, sketch, tuple(walls), base, _finish_good(inputs)
    )


@dataclass(frozen=True)
class Partitions:
    """A partition feature read: its host, its spec, its layout and options."""

    host: Host
    base: wall_v1.WallSpec
    layout: Layout
    backing: Backing
    finish: SheetGood | None
    sheet_length: float
    sheet: SheetSizeKey | None = None


def partitions_of(
    inputs: ExpandInputs,
    host: Host,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity],
) -> Partitions:
    """A ``loft.interior_wall``'s partitions, from its inputs (its own, or
    as its host wall receives them) and the features *earlier* than its host
    wall, where its sketch must be; its dimensions read with *parameters*."""
    picked = inputs.optional_feature("sketch") if "sketch" in inputs.values else None
    order = list(earlier)
    if picked is None:
        sketch_ref, loop = host.sketch, True
    else:
        sketch_ref, loop = picked, False
        if picked.feature_id not in earlier or (
            host.feature_id in earlier
            and order.index(picked.feature_id) > order.index(host.feature_id)
        ):
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Sketch: draw the partitions' sketch before the exterior walls, "
                "so the walls can frame their backing (move it above them).",
                input="sketch",
            )
        if picked.feature_id == host.sketch.feature_id:
            sketch_ref, loop = host.sketch, True
    sketch = outline_sketch(sketch_ref, earlier, "sketch")
    plan = read_plan(sketch, "sketch", parameters, loop=loop)
    if not plan.partitions:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Sketch: draw a line off the outline for each partition (none is)."
            if loop
            else "Sketch: draw a line for each partition (none is).",
            input="sketch",
        )
    for line in plan.partitions:
        if (
            not line.line_id.isascii()
            or not line.line_id[:1].isalpha()
            or not all(ch.isalnum() or ch == "_" for ch in line.line_id)
            or line.line_id.lower() != line.line_id
        ):
            raise PluginError(
                PLUGIN_INPUT_UNSUPPORTED,
                f"Sketch: line id {line.line_id!r} cannot name its partition's "
                "members; redraw that line.",
                input="sketch",
            )
    stud = inputs.lumber("stud_profile")
    base = dataclasses.replace(
        host.base,
        stud=stud,
        spacing=round(inputs.number("stud_spacing_mm") / 25.4, _DIGITS),
        top_plates=1 if inputs.choice("top_plate") == "single" else 2,
        stud_material=inputs.material("stud_material"),
        top_plate_material=inputs.material("top_plate_material"),
        bottom_plate_material=inputs.material("bottom_plate_material"),
    )
    if base.stud_length <= 0:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Top plate: the walls are too low for these plates.",
            input="top_plate",
        )
    layout = lay_out(plan.partitions, host.walls, base, host.outline)
    backing: Backing = (
        "three_stud" if inputs.choice("backing") == "three_stud" else "ladder"
    )
    return Partitions(
        host,
        base,
        layout,
        backing,
        _finish_good(inputs),
        _sheet_length(inputs),
        hung_sheet(inputs),
    )


def partition_specs_of(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity] | None = None,
) -> list[tuple[str | None, wall_v1.WallSpec]]:
    """The partitions a stored ``loft.interior_wall`` stands for, by line, as
    a door hosted in one reads them."""
    inputs = house.stored_inputs(feature_id, envelope, earlier, parameters)
    host = host_of(inputs.feature("host_wall"), earlier, inputs.parameters)
    found = partitions_of(inputs, host, earlier, inputs.parameters)
    return [(p.line_id, p.spec) for p in found.layout.partitions]


# --- Finished faces (what a cabinet run's backs sit on, CASEWORK-B10) ---------------


@dataclass(frozen=True)
class FinishedFace:
    """One face of a wall or partition as a room sees it (in): its framing
    face at ``v`` in its spec's frame (0, or the spec's depth), the way out
    of it (``-1`` or ``+1`` along the frame's ``across``), the board on it
    (0 with none), where the finished face runs along ``u`` (its board's
    ends, else the framing's), and the partitions meeting it, by name, each
    ``u`` span with its boards."""

    spec: wall_v1.WallSpec
    v: float
    out: float
    finish: float
    first: float
    last: float
    meeting: tuple[tuple[str, float, float], ...] = ()


def _meeting(
    found: Partitions, key: ElementKey, face_v: float
) -> list[tuple[str, float, float]]:
    """The partitions of *found* meeting *key*'s ``face_v`` face, each with
    its boards on both sides (they stop at this face's board)."""
    g = 0.0 if found.finish is None else found.finish.thickness_in
    return [
        (f"partition {j.meeting}", _r(j.a - g), _r(j.b + g))
        for j in found.layout.at(key)
        if abs(j.face_v - face_v) <= _TOL
    ]


def wall_faces_of(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity],
) -> dict[str | None, FinishedFace]:
    """The inside face of each wall a stored ``loft.wall`` stands for, by
    line (``None`` for a line wall): its inside gypsum (1.4.0), where that
    finished face runs (:func:`_finished_span`, the walls it meets' boards
    included), and the partitions of each earlier Interior wall on these
    walls that meet it."""
    specs = house.wall_specs_of(feature_id, envelope, earlier, parameters)
    if None in dict(specs):
        spec = dict(specs)[None]
        return {None: FinishedFace(spec, spec.thickness, 1.0, 0.0, 0.0, spec.length)}
    inputs = house.stored_inputs(feature_id, envelope, earlier, parameters)
    outline = house.wall_outline(inputs)
    assert outline is not None
    walls = house.outline_walls(inputs, outline)
    good = _finish_good(inputs) if "finish" in inputs.values else None
    host: Host | None = None
    found: list[Partitions] = []
    for fid, other in earlier.items():
        if (
            not isinstance(other, CustomFeature)
            or other.params.plugin_id != INTERIOR_WALL
        ):
            continue
        theirs = house.stored_inputs(fid, other, earlier, parameters)
        ref = theirs.optional_feature("host_wall")
        if ref is None or ref.feature_id != feature_id:
            continue
        host = host or host_of(ref, earlier, parameters)
        found.append(partitions_of(theirs, host, earlier, parameters))
    out: dict[str | None, FinishedFace] = {}
    for wall in walls:
        spec, t = wall.spec, wall.spec.thickness
        first, last = _finished_span(wall, 0.0 if good is None else good.thickness_in)
        meeting = [m for f in found for m in _meeting(f, ("wall", wall.line_id), t)]
        out[wall.line_id] = FinishedFace(
            spec,
            t,
            1.0,
            0.0 if good is None else good.thickness_in,
            first,
            last,
            tuple(meeting),
        )
    return out


def _finished_span(wall: house.OutlineWall, g: float) -> tuple[float, float]:
    """Where an outline wall's FINISHED inside face runs along it, its
    boards *g* thick (0 with none): at an outside corner of the outline (a
    room's corner) to the face of the wall it meets, that wall's board
    included, so a through wall's face stops ``t + g`` in from its end
    though its own board runs on under the other's to ``t``; at an inside
    corner to its own board's end past the corner (:func:`_inside_run`)."""
    spec, t = wall.spec, wall.spec.thickness
    if wall.through:
        first = t + g if wall.convex_start else -g
        last = spec.length - t - g if wall.convex_end else spec.length + g
    else:
        first = g if wall.convex_start else -t
        last = spec.length - g if wall.convex_end else spec.length + t
    return _r(first), _r(last)


def partition_faces_of(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity],
) -> dict[str, tuple[FinishedFace, FinishedFace]]:
    """Each partition of a stored ``loft.interior_wall``, by line: its left
    and right faces looking along it from its start (its gypsum's ``left``
    and ``right``, ``v`` 0 and its depth), each with its gypsum, where that
    runs (:func:`_face_runs`) and the partitions meeting it."""
    inputs = house.stored_inputs(feature_id, envelope, earlier, parameters)
    host = host_of(inputs.feature("host_wall"), earlier, inputs.parameters)
    found = partitions_of(inputs, host, earlier, inputs.parameters)
    g = 0.0 if found.finish is None else found.finish.thickness_in
    out: dict[str, tuple[FinishedFace, FinishedFace]] = {}
    for p in found.layout.partitions:
        key: ElementKey = ("partition", p.line_id)
        first, last = _face_runs(found, p)
        t = p.spec.thickness
        out[p.line_id] = (
            FinishedFace(
                p.spec, 0.0, -1.0, g, first, last, tuple(_meeting(found, key, 0.0))
            ),
            FinishedFace(
                p.spec, t, 1.0, g, first, last, tuple(_meeting(found, key, t))
            ),
        )
    return out


# --- loft.interior_wall 1.0.0 ---------------------------------------------------------


def _finish_choice(name: str, label: str, default: str, help: str) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=help,
        options=[
            ChoiceOption(value="gypsum_1_2", label="1/2 gypsum"),
            ChoiceOption(value="gypsum_5_8", label="5/8 gypsum (Type X)"),
            ChoiceOption(value="none", label="None"),
        ],
        default=default,
    )


def _sheet_choice() -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name="finish_sheet",
        label="Gypsum sheets",
        description="The sheet the gypsum is hung from, horizontally: its "
        "length is each panel's along the wall.",
        options=[
            ChoiceOption(value="sheet_4x8", label="4x8"),
            ChoiceOption(value="sheet_4x12", label="4x12"),
        ],
        default="sheet_4x8",
    )


def _material(name: str, label: str) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default="spf_lumber",
        description="Library material of these members (their mass and cut list).",
    )


_STUDS: list[LumberProfileKey] = ["us_2x4", "us_2x6"]

_MM = 25.4

INTERIOR_INPUTS: list[PluginInput] = [
    FeatureReferenceInput(
        kind="feature",
        name="host_wall",
        label="Exterior walls",
        description="The walls on an outline the partitions stand inside: they "
        "take its height and base, and frame each partition's backing.",
        feature_types=["custom"],
        plugin_ids=["loft.wall"],
        host=True,
    ),
    FeatureReferenceInput(
        kind="feature",
        name="sketch",
        label="Sketch",
        description="A sketch of partition lines in plan, drawn before the "
        "walls. Empty: the lines off the loop of the walls' outline sketch. "
        "Each partition is centred on its line and runs between the walls it "
        "meets.",
        feature_types=["sketch"],
        optional=True,
    ),
    ChoiceInput(
        kind="choice",
        name="stud_profile",
        label="Studs",
        description="Stud size; the plates and ladder blocks are cut from it.",
        options=lumber_options(_STUDS),
        default="us_2x4",
    ),
    LengthInput(
        kind="length",
        name="stud_spacing_mm",
        label="Stud spacing",
        description="On centres from each partition's start; an end stud sits "
        "flush at its far end.",
        default=16.0 * _MM,
        minimum=8.0 * _MM,
        maximum=24.0 * _MM,
    ),
    ChoiceInput(
        kind="choice",
        name="top_plate",
        label="Top plate",
        description="A double top plate, or a single one.",
        options=[
            ChoiceOption(value="double", label="Double"),
            ChoiceOption(value="single", label="Single"),
        ],
        default="double",
    ),
    ChoiceInput(
        kind="choice",
        name="backing",
        label="Backing",
        description="What the wall a partition meets frames behind it for the "
        "gypsum: ladder blocks every 24 in between its studs, or two studs "
        "flanking the partition (a three-stud corner).",
        options=[
            ChoiceOption(value="ladder", label="Ladder blocking"),
            ChoiceOption(value="three_stud", label="Three-stud corner"),
        ],
        default="ladder",
    ),
    _finish_choice(
        "finish",
        "Gypsum",
        "gypsum_1_2",
        "Gypsum board on both faces, hung horizontally in 48 in courses down "
        "from the top plate, the doors' rough openings cut out.",
    ),
    _sheet_choice(),
    _material("stud_material", "Stud material"),
    _material("top_plate_material", "Top plate material"),
    _material("bottom_plate_material", "Bottom plate material"),
]

_FRAMING_ROLES: list[PluginMemberRole] = [
    PluginMemberRole(
        role="block",
        title="Block",
        description="Ladder blocking: a flat block between two studs, backing "
        "the gypsum where a partition meets this wall.",
    ),
    PluginMemberRole(
        role="backing_stud",
        title="Stud",
        description="A stud flanking a partition that meets this wall "
        "(three-stud corner).",
    ),
]
_FINISH_ROLES: list[PluginMemberRole] = [
    PluginMemberRole(role="finish_plane", title="Plane"),
    PluginMemberRole(role="finish_section", title="Section"),
    PluginMemberRole(
        role="finish",
        title="Gypsum",
        description="One gypsum board panel, its openings cut out.",
    ),
]

INTERIOR_MANIFEST_V1 = PluginManifest(
    id=INTERIOR_WALL,
    version="1.0.0",
    title="Interior wall",
    description="Partitions on sketch lines inside an outline's walls: 2x4 "
    "studs, plates and gypsum on both faces, each centred on its line and "
    "running between the walls it meets, which frame its backing (Chief "
    "Architect, Revit).",
    inputs=INTERIOR_INPUTS,
    members=[
        *(
            r
            for r in wall_v1.MANIFEST_V1.members
            if r.role not in ("sill", "sill_cripple")
        ),
        *_FRAMING_ROLES,
        *_FINISH_ROLES,
    ],
)


def _doors(
    hosted: Sequence[Hosted], specs: Mapping[str, wall_v1.WallSpec]
) -> dict[str, list[wall_v1.Opening]]:
    """The doors hosted in the partitions, by the partition they sit in."""
    out: dict[str, list[wall_v1.Opening]] = {line: [] for line in specs}
    for h in hosted:
        if h.plugin_id != "loft.door":
            continue
        picked = h.inputs.segments("wall_segment")
        if len(picked) != 1 or picked[0] not in out:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"{h.name}: pick the partition it sits in.",
                input="wall_segment",
            )
        opening = wall_v1.Opening.from_hosted(h, specs[picked[0]])
        if opening is not None:
            out[picked[0]].append(opening)
    return out


def _face_runs(found: Partitions, p: Partition) -> tuple[float, float]:
    """Where a partition's gypsum runs along it: from the board (or framing)
    of what its start meets to that of what its end meets."""

    def stop(key: ElementKey) -> float:
        good = found.host.finish if key[0] == "wall" else found.finish
        return 0.0 if good is None else good.thickness_in

    return stop(p.start), _r(p.spec.length - stop(p.end))


def expand_interior_v1(inputs: ExpandInputs) -> Iterator[Member]:
    host = host_of(inputs.feature("host_wall"), inputs.earlier, inputs.parameters)
    found = partitions_of(inputs, host, inputs.earlier, inputs.parameters)
    specs = {p.line_id: p.spec for p in found.layout.partitions}
    doors = _doors(inputs.hosted, specs)
    counts: Counter[str] = Counter()
    names = {p.line_id: p.line_id for p in found.layout.partitions}
    for p in found.layout.partitions:
        sub = dataclasses.replace(inputs, name_prefix=p.line_id)
        mine = doors[p.line_id]
        pieces = wall_v1.wall_pieces(p.spec, mine, named=True)
        junctions = found.layout.at(("partition", p.line_id))
        pieces = backed_pieces(
            p.spec,
            pieces,
            junctions,
            found.backing,
            found.base.stud,
            names,
            f"partition {p.line_id}",
        )
        frame = wall_v1.WallFrame.of(p.spec)
        yield from _rename(wall_v1.emit_pieces(sub, frame, pieces), p.line_id, counts)
        good = found.finish
        if good is None:
            continue
        first, last = _face_runs(found, p)
        holes = [
            (o.centre - o.width / 2, o.centre + o.width / 2, o.sill, o.head)
            for o in mine
        ]
        planes = 0
        for face, spec, face_v in (
            ("left", p.spec, 0.0),
            ("right", flipped(p.spec), p.spec.thickness),
        ):
            cuts = holes + [
                (j.a, j.b, -1.0, p.spec.height + 1.0)
                for j in junctions
                if j.face_v == face_v
            ]
            regions = finish_regions(
                p.spec.height, first, last, found.sheet_length, cuts
            )
            members = list(
                finish_members(
                    sub,
                    spec,
                    good,
                    regions,
                    face,
                    planes,
                    counts["finish"],
                    found.sheet,
                )
            )
            planes += sum(1 for m in members if m.role == "finish_plane")
            yield from _rename(iter(members), p.line_id, counts)


INTERIOR_WALL_V1 = Plugin(INTERIOR_MANIFEST_V1, expand_interior_v1)


# --- loft.wall 1.4.0 ------------------------------------------------------------------

WALL_MANIFEST_V1_4 = PluginManifest(
    id="loft.wall",
    version="1.4.0",
    title=building_outline.WALL_MANIFEST_V1_3.title,
    description=building_outline.WALL_MANIFEST_V1_3.description
    + " They frame the backing of the partitions that meet them, may be "
    "finished with gypsum inside, and may stand on a slab, each bottom plate "
    "listing its anchor bolts.",
    inputs=[
        *(
            building_outline.FLOOR_OR_SLAB_PICK if item.name == "floor" else item
            for item in building_outline.WALL_MANIFEST_V1_3.inputs
        ),
        _finish_choice(
            "finish",
            "Inside gypsum",
            "none",
            "Gypsum board on the inside face, hung horizontally in 48 in "
            "courses down from the top plate, the rough openings and the "
            "partitions meeting it cut out.",
        ),
        _sheet_choice(),
    ],
    members=[
        *building_outline.WALL_MANIFEST_V1_3.members,
        *_FRAMING_ROLES,
        *_FINISH_ROLES,
    ],
)


def _inside_run(wall: house.OutlineWall, good: SheetGood) -> tuple[float, float]:
    """Where an outline wall's inside gypsum runs along it (module docstring:
    the met face to the meeting framing, the meeting face to the met board,
    and past an inside corner)."""
    spec, g, t = wall.spec, good.thickness_in, wall.spec.thickness
    if wall.through:
        first = t if wall.convex_start else -g
        last = spec.length - t if wall.convex_end else spec.length + g
    else:
        first = g if wall.convex_start else -t
        last = spec.length - g if wall.convex_end else spec.length + t
    return _r(first), _r(last)


def expand_wall_v1_4(inputs: ExpandInputs) -> Iterator[Member]:
    """1.3.0's members, each wall with the backing of the partitions that
    meet it after its framing, then its inside gypsum; on a slab, each bottom
    plate listing its anchor bolts (SLAB)."""
    yield from building_outline.on_slab(inputs, _framed_wall_v1_4(inputs))


def _framed_wall_v1_4(inputs: ExpandInputs) -> Iterator[Member]:
    outline = house.wall_outline(inputs)
    if outline is None:
        yield from sheathing.expand_wall_v1_2(house.wall_values(inputs))
        return
    walls = house.outline_walls(inputs, outline)
    openings = building_outline._openings(inputs, walls)  # pyright: ignore[reportPrivateUsage]
    sketch = inputs.optional_feature("outline")
    assert sketch is not None
    base = wall_v1.WallSpec.from_inputs(house.wall_values(inputs))
    finish = _finish_good(inputs)
    host = Host(inputs.feature_id, outline, sketch, tuple(walls), base, finish)
    found: list[tuple[Hosted, Partitions]] = []
    for h in inputs.hosted:
        if h.plugin_id != INTERIOR_WALL:
            continue
        try:
            found.append(
                (h, partitions_of(h.inputs, host, inputs.earlier, inputs.parameters))
            )
        except PluginError as exc:
            raise PluginError(
                exc.code, f"{h.name}: {exc.message}", input=exc.input
            ) from exc
    sheet_length = _sheet_length(inputs)
    hung = hung_sheet(inputs)
    counts: Counter[str] = Counter()
    for wall in walls:
        sub = dataclasses.replace(inputs, name_prefix=wall.line_id)
        mine = openings[wall.line_id]
        pieces = wall_v1.wall_pieces(wall.spec, mine, named=True)
        cuts = [
            (o.centre - o.width / 2, o.centre + o.width / 2, o.sill, o.head)
            for o in mine
        ]
        for h, partitions in found:
            junctions = partitions.layout.at(("wall", wall.line_id))
            names = {
                p.line_id: f"{h.feature_id}/{p.line_id}"
                for p in partitions.layout.partitions
            }
            pieces = backed_pieces(
                wall.spec,
                pieces,
                junctions,
                partitions.backing,
                partitions.base.stud,
                names,
                f"{h.name}'s wall {wall.line_id}",
            )
            cuts += [(j.a, j.b, -1.0, wall.spec.height + 1.0) for j in junctions]
        frame = wall_v1.WallFrame.of(wall.spec)
        members = [
            *wall_v1.emit_pieces(sub, frame, pieces),
            *building_outline._outline_sheathing(sub, wall, mine),  # pyright: ignore[reportPrivateUsage]
        ]
        if finish is not None:
            first, last = _inside_run(wall, finish)
            regions = finish_regions(wall.spec.height, first, last, sheet_length, cuts)
            members += finish_members(
                sub, flipped(wall.spec), finish, regions, "inside", 0, 0, hung
            )
        yield from _rename(iter(members), wall.line_id, counts)


WALL_V1_4 = Plugin(WALL_MANIFEST_V1_4, expand_wall_v1_4)

__all__ = [
    "INTERIOR_WALL_V1",
    "WALL_V1_4",
    "FinishedFace",
    "Layout",
    "Partition",
    "courses",
    "lay_out",
    "partition_faces_of",
    "partition_specs_of",
    "wall_faces_of",
]
