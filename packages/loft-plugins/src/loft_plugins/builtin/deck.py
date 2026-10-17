"""Deck: a framed lumber deck from a few inputs (DECK, RESEARCH §23).

What SketchUp's Medeek Deck and Chief Architect's deck tool build, in their
order: a ledger on the house (or a freestanding deck's house-side rim and
beam), joists at a spacing with both end joists flush, a rim joist, a built-up
beam of plies (dropped under the joists, or flush with them), posts under the
beam at both ends and no more than a spacing apart, decking boards across the
joists with a gap and an overhang, optional mid-span blocking, and an optional
guard on the open sides. ``docs/reference-parts/buildings.md`` B1 is the
default deck exactly.

This is a FRAMING MODEL with a cut list, not a structural design: no span
table, load or code check is implied (buildings.md).

**Members.** Each member is one body: a plan rectangle sketched on a level
(an ``XY`` datum at the member's bottom elevation, shared by every member that
starts there) and extruded up its depth as a new body (``merge: false``).
Members never fuse, so the cut list measures each one and the kernel never
runs a whole-body boolean (RESEARCH §23). Each body's member carries its role,
its profile's nominal name and its material, so the cut list and mass read
them (``MemberMetadata``); documents applies the material to the body.

**Frame.** World X runs along the house, Y away from it, Z up; the deck
occupies X 0..width, Y 0..projection, with the decking top at ``height`` above
grade (Z 0). Framing is laid out in a local frame: ``a`` along the beams and
the ledger, ``b`` along the joists. Joists that run away from the house map
``a -> X, b -> Y``; joists along the house (freestanding only) map
``a -> Y, b -> X``.

**Decisions** (Medeek Deck, Chief Architect and IRC R507 prescriptive
practice; noted in RESEARCH §23):

* A ledger carries joist ends, so joists along the house need a freestanding
  deck; that combination is ``plugin_input_unsupported``.
* The ledger and rim joists are cut from the joist profile, top flush with the
  joists. A freestanding deck replaces the ledger with a house-side rim and a
  second beam line, set back from the house side as the outer one is from the
  rim.
* The beam setback is from the deck's outer edge to the beam's centre line
  (the joist cantilever). A dropped beam's top bears the joists; a flush
  beam's top is flush with them and the joists are cut at it and hung.
* Posts are the beam's supports, from grade to the beam's underside: their
  height follows from the deck height, the joist depth and the beam (Medeek
  derives it the same way). Footings are a later rung (buildings.md).
* Decking runs across the joists. Boards are whole (never ripped) and start
  at the house side (``b = 0``) with the gap between them; the count is the
  fewest that cover the projection plus the overhang, so the last board may
  overhang more (B1: 2.125 in). The overhang also extends the boards past the
  end joists at both ends.
* The guard (optional) stands on the decking along the open sides (three for
  an attached deck, four freestanding): 4x4 posts at every corner, including
  where a side meets the house, no more than 6 ft apart on centres; 2x4 top
  and bottom rails on edge between the posts, the top 36 in above the
  decking and the bottom 3.5 in above it; 2x2 balusters between the rails,
  equally spaced with no clear gap over 4 in (IRC R312).

Inputs are millimetres on the wire (their names end ``_mm``, so a §20 formula
drives them) and inches inside; every inch value is rounded to 1e-9 in so a
round trip through millimetres gives back the exact spec value.
"""

import itertools
import math
from collections.abc import Iterator
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
from loft_wire.lumber import (
    MM_PER_INCH,
    LumberProfile,
    LumberProfileKey,
    lumber_profile,
)
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    CountInput,
    LengthInput,
    MaterialInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError, lumber_options

#: Spec defaults (B1) and guard rules, in inches.
GUARD_HEIGHT = 36.0
GUARD_POST_SPACING = 72.0
GUARD_BOTTOM_GAP = 3.5
BALUSTER_MAX_GAP = 4.0
#: Rounding of an input's inch value (see the module docstring).
_INCH_DIGITS = 9
#: Float slack when counting bays and boards (in): far below a real length.
_EPS = 1e-9

_PT_PINE: MaterialKey = "southern_pine_pt"


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _INCH_DIGITS)


def _length(
    name: str,
    label: str,
    default_in: float,
    low_in: float,
    high_in: float,
    description: str,
    *,
    exclusive: bool = False,
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=description,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
        exclusive_minimum=exclusive,
    )


def _choice(
    name: str, label: str, options: list[tuple[str, str]], description: str
) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=description,
        options=[ChoiceOption(value=v, label=t) for v, t in options],
        default=options[0][0],
    )


def _profiles(
    name: str,
    label: str,
    keys: list[LumberProfileKey],
    default: LumberProfileKey,
    description: str,
) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=description,
        options=lumber_options(keys),
        default=default,
    )


def _material(name: str, label: str) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default=_PT_PINE,
        description="Library material of these members (their mass and cut list).",
    )


_FRAMING: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]

MANIFEST_V1 = PluginManifest(
    id="loft.deck",
    version="1.0.0",
    title="Deck",
    description="A framed lumber deck: ledger, beam, posts, joists, rim and "
    "decking, with a cut list (Medeek Deck, Chief Architect).",
    inputs=[
        _length(
            "width_mm",
            "Width",
            192.0,
            48.0,
            480.0,
            "Along the house (X), outside of the framing.",
        ),
        _length(
            "depth_mm",
            "Projection",
            144.0,
            48.0,
            288.0,
            "Away from the house (Y), to the outside of the rim.",
        ),
        _length(
            "height_mm",
            "Height",
            30.0,
            12.0,
            144.0,
            "Top of the decking above grade; the posts run from grade to the beam.",
        ),
        _choice(
            "attachment",
            "Support",
            [("ledger", "Ledger on the house"), ("freestanding", "Freestanding")],
            "A ledger carries the joists at the house; a freestanding deck "
            "has a second beam on posts instead.",
        ),
        _profiles("joist_profile", "Joists", _FRAMING, "us_2x10", "Joist size."),
        _length(
            "joist_spacing_mm",
            "Joist spacing",
            16.0,
            8.0,
            24.0,
            "On centres, from the first end joist; both end joists sit flush.",
        ),
        _choice(
            "joist_direction",
            "Joist direction",
            [("away", "Away from the house"), ("along", "Along the house")],
            "Joists along the house need a freestanding deck.",
        ),
        _choice(
            "rim_joists",
            "Rim joists",
            [("yes", "Yes"), ("no", "No")],
            "A rim (band) joist across the joist ends.",
        ),
        _choice(
            "blocking",
            "Blocking",
            [("none", "None"), ("midspan", "At mid-span")],
            "A row of solid blocking between the joists halfway along their span.",
        ),
        _profiles("beam_profile", "Beam plies", _FRAMING, "us_2x10", "Ply size."),
        CountInput(
            kind="count",
            name="beam_plies",
            label="Beam ply count",
            description="Plies nailed side by side into one built-up beam.",
            default=2,
            minimum=1,
            maximum=4,
        ),
        _choice(
            "beam_position",
            "Beam",
            [("dropped", "Dropped (under the joists)"), ("flush", "Flush")],
            "A dropped beam bears the joists; a flush beam's top is level "
            "with theirs and the joists hang from it.",
        ),
        _length(
            "beam_setback_mm",
            "Beam setback",
            18.0,
            0.0,
            72.0,
            "From the deck's outer edge to the beam's centre: the joist cantilever.",
        ),
        _profiles(
            "post_profile",
            "Posts",
            ["us_4x4", "us_4x6", "us_6x6"],
            "us_6x6",
            "Post size.",
        ),
        _length(
            "post_spacing_mm",
            "Post spacing",
            96.0,
            24.0,
            192.0,
            "Most on centres; posts sit at both ends of the beam, equally spaced.",
        ),
        _profiles(
            "decking_profile",
            "Decking",
            ["us_5_4x6", "us_2x4", "us_2x6"],
            "us_5_4x6",
            "Board size.",
        ),
        _length(
            "decking_gap_mm",
            "Decking gap",
            0.125,
            0.0,
            0.5,
            "Between boards.",
        ),
        _length(
            "decking_overhang_mm",
            "Decking overhang",
            0.0,
            0.0,
            3.0,
            "Past the end joists and, at least, past the rim.",
        ),
        _choice(
            "guard",
            "Guard",
            [("none", "None"), ("open_sides", "On the open sides")],
            "4x4 posts, 2x4 rails and 2x2 balusters, 36 in above the decking.",
        ),
        _material("framing_material", "Framing material"),
        _material("beam_material", "Beam material"),
        _material("post_material", "Post material"),
        _material("decking_material", "Decking material"),
        _material("guard_material", "Guard material"),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="ledger", title="Ledger"),
        PluginMemberRole(role="rim", title="Rim"),
        PluginMemberRole(role="beam", title="Beam"),
        PluginMemberRole(role="joist", title="Joist"),
        PluginMemberRole(role="blocking", title="Blocking"),
        PluginMemberRole(role="post", title="Post"),
        PluginMemberRole(role="deck", title="Deck"),
        PluginMemberRole(role="guard_post", title="Guard post"),
        PluginMemberRole(role="rail", title="Rail"),
        PluginMemberRole(role="baluster", title="Baluster"),
    ],
)


# --- Layout (pure, inches) ---------------------------------------------------------


def joist_centres(length: float, spacing: float, thickness: float) -> list[float]:
    """Joist centres along the beam (in): both end joists flush with the ends,
    the layout on *spacing* from the first end between them; a layout joist
    that would overlap the far end joist is dropped (buildings.md B1/B2)."""
    first, last = thickness / 2, length - thickness / 2
    inner: list[float] = []
    n = 1
    while spacing * n <= last - thickness + _EPS:
        inner.append(spacing * n)
        n += 1
    return [first, *inner, last]


def equal_centres(length: float, size: float, most: float) -> list[float]:
    """Centres of members of *size* at both ends of *length*, equally spaced,
    no more than *most* apart (posts on a beam, guard posts on a side)."""
    first, last = size / 2, length - size / 2
    bays = max(1, math.ceil((last - first) / most - _EPS))
    # The last centre is `last` exactly: `first + (last - first)` can land one
    # ulp off it, and a guard corner post shared by two sides must coincide.
    return [
        last if n == bays else first + (last - first) * n / bays
        for n in range(bays + 1)
    ]


def board_count(depth: float, overhang: float, board: float, gap: float) -> int:
    """The fewest whole boards, from ``b = 0`` with *gap* between, whose far
    edge reaches *depth* + *overhang*."""
    return max(1, math.ceil((depth + overhang + gap) / (board + gap) - _EPS))


def baluster_count(clear: float, size: float = 1.5) -> int:
    """Fewest balusters of *size* in a *clear* bay leaving no gap over 4 in."""
    if clear <= BALUSTER_MAX_GAP + _EPS:
        return 0
    return math.ceil((clear - BALUSTER_MAX_GAP) / (size + BALUSTER_MAX_GAP) - _EPS)


# --- Emission ----------------------------------------------------------------------

Rect = tuple[float, float, float, float]  # world x0, x1, y0, y1 (in)
#: The world axis a guard side runs along.
Axis = Literal["x", "y"]


def _rectangle(rect: Rect) -> list[SketchLine]:
    x0, x1, y0, y1 = rect
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=_mm(corners[i][0]), y=_mm(corners[i][1])),
            end=Point2D(x=_mm(corners[(i + 1) % 4][0]), y=_mm(corners[(i + 1) % 4][1])),
        )
        for i in range(4)
    ]


def level_name(z: float) -> str:
    """A 1.1.0 level's name: its elevation (in) printed to 9 places without
    trailing zeros (``z/38.75``)."""
    return "z/" + f"{z:.9f}".rstrip("0").rstrip(".")


class _Emitter:
    """Levels, section sketches and member extrudes, with running indices.

    A ``named`` emitter (1.1.0, WALL-MEMBER-RENUMBER) names every member by
    its place: the member by the name its caller gives, its section by
    ``<role>/<name>`` and each level by its height, so no id depends on how
    many members came before it."""

    def __init__(self, inputs: ExpandInputs, named: bool = False) -> None:
        self.inputs = inputs
        self.named = named
        self.levels: dict[float, int] = {}
        self.sections = 0
        self.counts: dict[str, int] = {}

    def member(
        self,
        role: str,
        profile: LumberProfile,
        material: MaterialKey | None,
        rect: Rect,
        z0: float,
        z1: float,
        name: str = "",
    ) -> Iterator[Member]:
        """One body: *rect* in plan from *z0* up to *z1* (inches), called
        *name* within its role when the emitter is named."""
        key = name if self.named else None
        plane: DatumPlaneRef | FeatureRef
        if z0 == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane="XY")
        else:
            # 1.1.0 shares a level by its height to 1e-9 in, as the wall does
            # (WALL-LEVEL-EQ): two sums one ulp apart are one datum and one
            # name. 1.0.0 keys the exact float, as released.
            at = round(z0, _INCH_DIGITS) + 0.0 if self.named else z0
            level_key = level_name(at) if self.named else None
            level = self.levels.get(at)
            if level is None:
                level = self.levels[at] = len(self.levels)
                yield Member(
                    "level",
                    level,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumOffsetParams(base="XY", offset_mm=_mm(z0)),
                    ),
                    name=level_key,
                )
            plane = self.inputs.ref("level", level, level_key)
        section = self.sections
        self.sections += 1
        section_key = None if key is None else f"{role}/{key}"
        yield Member(
            "section",
            section,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_rectangle(rect)), constraints=[]
                ),
            ),
            name=section_key,
        )
        index = self.counts.get(role, 0)
        self.counts[role] = index + 1
        yield Member(
            role,
            index,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=self.inputs.ref("section", section, section_key),
                    distance_mm=_mm(z1 - z0),
                    operation="add",
                    merge=False,
                ),
            ),
            MemberMetadata(profile=profile.name, material=material),
            name=key,
        )


def _unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


@dataclass(frozen=True)
class _Beam:
    centre: float  # b (in)
    lo: float
    hi: float


def joist_names(count: int) -> list[str]:
    """The 1.1.0 names of :func:`joist_centres`' *count* joists, in order:
    the start end joist, ``slot/n`` for the layout joist at ``n x spacing``,
    and the far end joist. Widening the deck adds slots and moves the end
    joist, but never renames a joist."""
    return ["start", *(f"slot/{n}" for n in range(1, count - 1)), "end"]


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    """1.0.0: members numbered in emission order."""
    yield from _expand(inputs, named=False)


def expand_v1_1(inputs: ExpandInputs) -> Iterator[Member]:
    """1.1.0: 1.0.0's members in 1.0.0's order, each named by its place
    (WALL-MEMBER-RENUMBER): a joist by its layout slot, a ply by its beam
    line, a board by its row, a guard member by its side and bay."""
    yield from _expand(inputs, named=True)


def _expand(inputs: ExpandInputs, named: bool) -> Iterator[Member]:
    width = _inches("width_mm", inputs)
    depth = _inches("depth_mm", inputs)
    height = _inches("height_mm", inputs)
    attached = inputs.choice("attachment") == "ledger"
    along = inputs.choice("joist_direction") == "along"
    if attached and along:
        raise _unsupported(
            "Joists along the house need a freestanding deck: a ledger carries "
            "joist ends.",
            "joist_direction",
        )
    joist = inputs.lumber("joist_profile")
    spacing = _inches("joist_spacing_mm", inputs)
    rims = inputs.choice("rim_joists") == "yes"
    blocking = inputs.choice("blocking") == "midspan"
    beam = inputs.lumber("beam_profile")
    plies = inputs.count("beam_plies")
    flush = inputs.choice("beam_position") == "flush"
    setback = _inches("beam_setback_mm", inputs)
    post = inputs.lumber("post_profile")
    post_spacing = _inches("post_spacing_mm", inputs)
    board = inputs.lumber("decking_profile")
    gap = _inches("decking_gap_mm", inputs)
    overhang = _inches("decking_overhang_mm", inputs)
    guard = inputs.choice("guard") == "open_sides"
    framing_mat = inputs.material("framing_material")
    beam_mat = inputs.material("beam_material")
    post_mat = inputs.material("post_material")
    deck_mat = inputs.material("decking_material")
    guard_mat = inputs.material("guard_material")

    # Local frame: a along the beams, b along the joists.
    span_a, span_b = (depth, width) if along else (width, depth)

    def world(a0: float, a1: float, b0: float, b1: float) -> Rect:
        return (b0, b1, a0, a1) if along else (a0, a1, b0, b1)

    jt, jd = joist.thickness_in, joist.width_in
    deck_bottom = height - board.thickness_in
    joist_top, joist_bottom = deck_bottom, deck_bottom - jd
    beam_width = plies * beam.thickness_in
    beam_top = joist_top if flush else joist_bottom
    beam_bottom = beam_top - beam.width_in
    if beam_bottom <= 0.0:
        raise _unsupported(
            "The deck is too low for its beam: the beam would reach grade. "
            "Raise the height or use a smaller beam or joist.",
            "height_mm",
        )

    near_band = rims or attached  # the ledger, or a freestanding house-side rim
    b_start = jt if near_band else 0.0
    b_end = span_b - jt if rims else span_b
    lines = [span_b - setback] if attached else [setback, span_b - setback]
    beams = [_Beam(c, c - beam_width / 2, c + beam_width / 2) for c in sorted(lines)]
    for line in beams:
        low, high = (b_start, b_end) if flush else (0.0, span_b)
        if line.lo < low - _EPS or line.hi > high + _EPS:
            where = "between the ledger and the rim" if flush else "under the deck"
            raise _unsupported(
                f"The beam must sit {where}: change the setback.",
                "beam_setback_mm",
            )
    if len(beams) == 2 and beams[0].hi > beams[1].lo + _EPS:
        raise _unsupported(
            "The two beams overlap: the deck is too shallow for its setback.",
            "beam_setback_mm",
        )

    e = _Emitter(inputs, named)

    # Ledger (attached) and rim joists, full length along a.
    if attached:
        yield from e.member(
            "ledger",
            joist,
            framing_mat,
            world(0.0, span_a, 0.0, jt),
            joist_bottom,
            joist_top,
            "house",
        )
    if rims:
        yield from e.member(
            "rim",
            joist,
            framing_mat,
            world(0.0, span_a, span_b - jt, span_b),
            joist_bottom,
            joist_top,
            "outer",
        )
        if not attached:
            yield from e.member(
                "rim",
                joist,
                framing_mat,
                world(0.0, span_a, 0.0, jt),
                joist_bottom,
                joist_top,
                "house",
            )

    # Beam lines by name: the outer one, and a freestanding deck's house one.
    line_names = ["outer"] if attached else ["house", "outer"]

    # Beam plies, full length along a.
    for line, line_name in zip(beams, line_names, strict=True):
        for ply in range(plies):
            b0 = line.lo + ply * beam.thickness_in
            yield from e.member(
                "beam",
                beam,
                beam_mat,
                world(0.0, span_a, b0, b0 + beam.thickness_in),
                beam_bottom,
                beam_top,
                f"{line_name}/ply/{ply}",
            )

    # Joists: whole between the supports, or cut at a flush beam.
    segments: list[tuple[float, float]] = []
    start = b_start
    for line in beams if flush else []:
        segments.append((start, line.lo))
        start = line.hi
    segments.append((start, b_end))
    centres = joist_centres(span_a, spacing, jt)
    names = joist_names(len(centres))
    for a, joist_name in zip(centres, names, strict=True):
        for k, (b0, b1) in enumerate(segments):
            if b1 - b0 > _EPS:
                yield from e.member(
                    "joist",
                    joist,
                    framing_mat,
                    world(a - jt / 2, a + jt / 2, b0, b1),
                    joist_bottom,
                    joist_top,
                    joist_name if len(segments) == 1 else f"{joist_name}/bay/{k}",
                )

    # Mid-span blocking between the near support and the outer beam.
    if blocking:
        near = b_start if attached else beams[0].centre
        mid = (near + beams[-1].centre) / 2
        for (left, right), after in zip(
            itertools.pairwise(centres), names[:-1], strict=True
        ):
            a0, a1 = left + jt / 2, right - jt / 2
            if a1 - a0 > _EPS:
                # Named after the joist it follows from the start.
                yield from e.member(
                    "blocking",
                    joist,
                    framing_mat,
                    world(a0, a1, mid - jt / 2, mid + jt / 2),
                    joist_bottom,
                    joist_top,
                    after,
                )

    # Posts under every beam line, grade to the beam's underside. The post's
    # thickness runs along the beam and its width across it.
    pt, pw = post.thickness_in, post.width_in
    for line, line_name in zip(beams, line_names, strict=True):
        for k, a in enumerate(equal_centres(span_a, pt, post_spacing)):
            yield from e.member(
                "post",
                post,
                post_mat,
                world(
                    a - pt / 2, a + pt / 2, line.centre - pw / 2, line.centre + pw / 2
                ),
                0.0,
                beam_bottom,
                f"{line_name}/{k}",
            )

    # Decking across the joists, from the house side.
    pitch = board.width_in + gap
    for i in range(board_count(span_b, overhang, board.width_in, gap)):
        b0 = pitch * i
        yield from e.member(
            "deck",
            board,
            deck_mat,
            world(-overhang, span_a + overhang, b0, b0 + board.width_in),
            deck_bottom,
            height,
            f"row/{i}",
        )

    if guard:
        yield from _guard(e, width, depth, height, attached, guard_mat)


def _guard(
    e: _Emitter,
    width: float,
    depth: float,
    floor: float,
    attached: bool,
    material: MaterialKey | None,
) -> Iterator[Member]:
    """The guard on the open sides, in world coordinates (module docstring)."""
    post_p = lumber_profile("us_4x4")
    rail_p = lumber_profile("us_2x4")
    baluster_p = lumber_profile("us_2x2")
    ps = post_p.width_in
    half = ps / 2
    # Sides as (axis the side runs along, fixed coordinate of its centre line,
    # length): walking left side (house -> out), front, right side (out ->
    # house), and back for a freestanding deck.
    # Sides are named for 1.1.0's member names (a post by the side that
    # placed it and its number along it, a rail or baluster by its bay).
    sides: list[tuple[str, Axis, float, float, bool]] = [
        ("left", "y", half, depth, False),
        ("front", "x", depth - half, width, False),
        ("right", "y", width - half, depth, True),
    ]
    if not attached:
        sides.append(("back", "x", half, width, True))
    posts: list[tuple[float, float, str]] = []
    seen: set[tuple[float, float]] = set()
    # side name, bay number, axis, line, from, to
    bays: list[tuple[str, int, Axis, float, float, float]] = []

    def add_post(x: float, y: float, name: str) -> None:
        # A corner post is shared by two sides: dedupe on the position to
        # 1e-6 mm, never exact float equality (DECK review).
        key = (round(_mm(x), 6), round(_mm(y), 6))
        if key not in seen:
            seen.add(key)
            posts.append((x, y, name))

    for side, axis, line, length, backwards in sides:
        along = equal_centres(length, ps, GUARD_POST_SPACING)
        if backwards:
            along = along[::-1]
        for k, s in enumerate(along):
            add_post(*((s, line) if axis == "x" else (line, s)), f"{side}/{k}")
        for bay, (s0, s1) in enumerate(itertools.pairwise(along)):
            lo, hi = min(s0, s1), max(s0, s1)
            bays.append((side, bay, axis, line, lo + half, hi - half))

    top = floor + GUARD_HEIGHT
    for x, y, name in posts:
        yield from e.member(
            "guard_post",
            post_p,
            material,
            (x - half, x + half, y - half, y + half),
            floor,
            top,
            name,
        )

    rt, rw = rail_p.thickness_in, rail_p.width_in
    bottom_rail = (floor + GUARD_BOTTOM_GAP, floor + GUARD_BOTTOM_GAP + rw)
    top_rail = (top - rw, top)

    def plan(axis: Axis, line: float, s0: float, s1: float, across: float) -> Rect:
        if axis == "x":
            return (s0, s1, line - across / 2, line + across / 2)
        return (line - across / 2, line + across / 2, s0, s1)

    for side, bay, axis, line, s0, s1 in bays:
        for (z0, z1), course in ((bottom_rail, "bottom"), (top_rail, "top")):
            yield from e.member(
                "rail",
                rail_p,
                material,
                plan(axis, line, s0, s1, rt),
                z0,
                z1,
                f"{side}/{bay}/{course}",
            )
    bs = baluster_p.width_in
    for side, bay, axis, line, s0, s1 in bays:
        clear = s1 - s0
        n = baluster_count(clear, bs)
        space = (clear - n * bs) / (n + 1)
        for k in range(n):
            c0 = s0 + space * (k + 1) + bs * k
            yield from e.member(
                "baluster",
                baluster_p,
                material,
                plan(axis, line, c0, c0 + bs, bs),
                bottom_rail[1],
                top_rail[0],
                f"{side}/{bay}/{k}",
            )


#: 1.0.0 numbers every role in emission order. A ledger and the rims are one
#: per edge and boards count from the house, so those keep their member; any
#: other role can pass to another member on a re-layout.
_RENUMBERED = frozenset(
    {
        "level",
        "section",
        "beam",
        "joist",
        "blocking",
        "post",
        "guard_post",
        "rail",
        "baluster",
    }
)

MANIFEST_V1_1 = MANIFEST_V1.model_copy(
    update={
        "version": "1.1.0",
        "description": MANIFEST_V1.description
        + " Each member keeps its name when the deck is resized.",
    }
)

DECK_V1 = Plugin(MANIFEST_V1, expand, renumbered_roles=_RENUMBERED)
DECK_V1_1 = Plugin(MANIFEST_V1_1, expand_v1_1)
