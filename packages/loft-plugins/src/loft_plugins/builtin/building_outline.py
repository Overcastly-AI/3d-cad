"""Walls and a floor on one outline sketch (BUILDING-OUTLINE, RESEARCH §23).

One closed sketch drives a house's walls and floor, as Chief Architect
builds floors and roofs from the exterior wall loop and Revit draws walls on
picked lines. Two releases, each the previous one unchanged when its new
inputs are left empty:

* ``loft.wall`` 1.3.0 adds **Outline** (a sketch: one wall per line, joined
  at the corners, :mod:`~loft_plugins.builtin.house`) and **On floor** (a
  ``loft.floor``: the walls stand on its top, subfloor included, so no base
  elevation is typed: SHEATHING-WALL-BASE). With no outline it is 1.2.0's
  wall, member for member, at the floor's top when one is picked.
* ``loft.floor`` 1.2.0 adds **Outline** (a rectangle): the floor fills it,
  the width along the outline's first line. With no outline it is 1.1.0's.
* ``loft.wall`` 1.4.0 (SLAB; released in ``interior_wall`` with its
  partitions' backing): **On floor** accepts a ``loft.slab`` too: the
  walls stand on the slab's top, and each bottom-plate piece bearing on it
  lists its anchor bolts (IRC R403.1.6, counted from the piece's measured
  length by the cut list), as Chief Architect lists them from the
  foundation. On a floor, or on none, it is 1.3.0's wall member for member.
* ``loft.floor`` 1.3.0 replaces Joist direction with **Joists bear on**
  (FLOOR-JOIST-SPAN): Long walls (the default: the joists span the shorter
  way), Front and back, or Left and right, as Chief Architect frames a floor
  across its shorter span and Revit picks a span direction. An outline's
  rectangle is read from its corners, so the drawing order cannot turn the
  joists (:func:`~loft_plugins.builtin.house.floor_values_v1_3`).

**An outline wall's members.** Each wall is framed exactly as a 1.2.0 wall
of its spec (studs from its clockwise start, its hosted doors and windows,
its sheathing), and every member is named under the wall's sketch line
(``e3/slot/2``, ``e3/opening/<id>/0``, ``e3/exterior/1/0``), so a member keeps
its id when another wall changes, as WALL-MEMBER-RENUMBER keeps it when an
opening moves. Windows and doors 1.1.0 name their wall of the outline
(``wall_segment``); a 1.0.0 opening cannot.

**Sheathing at the corners.** At an outside corner the fitted wall's
sheathing laps past its end over the through wall's end grain and sheathing
edge (WALL-SHEATHING-CORNER's rip, B7's four 5.9375 in rips). At an inside
corner the through wall's sheathing stops at the corner (its framing runs on
past it, inside the other wall) and the fitted wall's starts the sheathing's
thickness clear of it, so the two panels close the corner with no overlap.
"""

import dataclasses
from collections import Counter
from collections.abc import Iterator, Sequence

from loft_wire.foundation import AnchorBolts
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    PluginInput,
    PluginManifest,
)

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import sheathing
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.house import (
    OutlineWall,
    floor_values,
    floor_values_v1_3,
    outline_walls,
    picked_slab,
    wall_outline,
    wall_values,
)
from loft_plugins.builtin.outline import Outline

# --- Manifests ---------------------------------------------------------------------

_WALL_LINE = ("start_x_mm", "start_y_mm", "direction_deg", "length_mm", "side")
_FLOOR_RECTANGLE = ("start_x_mm", "start_y_mm", "direction_deg", "width_mm", "depth_mm")


def _superseded(
    inputs: Sequence[PluginInput], names: dict[str, str]
) -> list[PluginInput]:
    """*inputs* with each named one marked unused once its pick is set."""
    return [
        item.model_copy(update={"superseded_by": names[item.name]})
        if item.name in names
        else item
        for item in inputs
    ]


def _outline_input(what: str) -> FeatureReferenceInput:
    return FeatureReferenceInput(
        kind="feature",
        name="outline",
        label="Outline",
        description=f"A closed loop of sketch lines on the XY plane, the "
        f"framing's outside face, horizontal and vertical, every side "
        f"dimensioned and a corner on the origin. {what} Empty: typed below.",
        feature_types=["sketch"],
        optional=True,
    )


_FLOOR_PICK = FeatureReferenceInput(
    kind="feature",
    name="floor",
    label="On floor",
    description="The floor the walls stand on: their base is its top, the "
    "subfloor's when it has one. Empty: the typed base elevation.",
    feature_types=["custom"],
    plugin_ids=["loft.floor"],
    optional=True,
)


def _wall_inputs() -> list[PluginInput]:
    names = dict.fromkeys(_WALL_LINE, "outline") | {"elevation_mm": "floor"}
    inputs = _superseded(sheathing.WALL_MANIFEST_V1_2.inputs, names)
    at = next(k for k, item in enumerate(inputs) if item.name == "elevation_mm")
    inputs.insert(at, _FLOOR_PICK)
    walls = (
        "One wall per line, joined at the corners (the first line's walls run through)."
    )
    return [_outline_input(walls), *inputs]


WALL_MANIFEST_V1_3 = PluginManifest(
    id="loft.wall",
    version="1.3.0",
    title=sheathing.WALL_MANIFEST_V1_2.title,
    description="Framed stud walls on a line, or one per line of an outline "
    "sketch joined at the corners, on a floor if picked: plates, studs, "
    "openings and optional exterior sheathing, with a cut list (Chief "
    "Architect, Revit, Medeek Wall).",
    inputs=_wall_inputs(),
    members=sheathing.WALL_MANIFEST_V1_2.members,
)

FLOOR_MANIFEST_V1_3_INPUTS: list[PluginInput] = [
    _outline_input("The floor fills it (a rectangle; the width along its first line)."),
    *_superseded(
        sheathing.FLOOR_MANIFEST_V1_1.inputs, dict.fromkeys(_FLOOR_RECTANGLE, "outline")
    ),
]

FLOOR_MANIFEST_V1_2 = PluginManifest(
    id="loft.floor",
    version="1.2.0",
    title=sheathing.FLOOR_MANIFEST_V1_1.title,
    description="A framed platform floor on a typed rectangle or an outline "
    "sketch: sill plates, rim joists, joists on a layout and a subfloor, with "
    "a cut list (Chief Architect, Medeek Foundation).",
    inputs=FLOOR_MANIFEST_V1_3_INPUTS,
    members=sheathing.FLOOR_MANIFEST_V1_1.members,
)


# --- Floor 1.2.0 -------------------------------------------------------------------


def expand_floor_v1_2(inputs: ExpandInputs) -> Iterator[Member]:
    """1.1.0's floor, on the outline's rectangle when one is picked."""
    yield from sheathing.expand_floor_v1_1(floor_values(inputs))


# --- Floor 1.3.0 -------------------------------------------------------------------

JOISTS_BEAR_ON = ChoiceInput(
    kind="choice",
    name="joists_bear_on",
    label="Joists bear on",
    description="The walls under the rims; the joists span between them. Long "
    "walls frames the shorter span. Front and back are the width's edges (on "
    "an outline, the walls facing -Y and +Y), left and right the depth's.",
    options=[
        ChoiceOption(value="long_walls", label="Long walls"),
        ChoiceOption(value="front_back", label="Front and back"),
        ChoiceOption(value="left_right", label="Left and right"),
    ],
    default="long_walls",
)


def _floor_inputs_v1_3() -> list[PluginInput]:
    """1.2.0's inputs with Joist direction replaced, in place, by Joists
    bear on, and the outline's text no longer tying the span to its first line."""
    replaced = {
        "joist_direction": JOISTS_BEAR_ON,
        "outline": _outline_input(
            "The floor fills it (a rectangle; Joists bear on picks the span)."
        ),
    }
    return [replaced.get(item.name, item) for item in FLOOR_MANIFEST_V1_3_INPUTS]


FLOOR_MANIFEST_V1_3 = PluginManifest(
    id="loft.floor",
    version="1.3.0",
    title=sheathing.FLOOR_MANIFEST_V1_1.title,
    description="A framed platform floor on a typed rectangle or an outline "
    "sketch: sill plates, rim joists, joists spanning between the walls they "
    "bear on (the long walls by default), and a subfloor, with a cut list "
    "(Chief Architect, Revit, Medeek Foundation).",
    inputs=_floor_inputs_v1_3(),
    members=sheathing.FLOOR_MANIFEST_V1_1.members,
)


def expand_floor_v1_3(inputs: ExpandInputs) -> Iterator[Member]:
    """1.1.0's floor on the rectangle typed or read from the outline's
    corners, its joists across the walls they bear on."""
    yield from sheathing.expand_floor_v1_1(floor_values_v1_3(inputs))


# --- Wall 1.3.0 --------------------------------------------------------------------


def _openings(
    inputs: ExpandInputs, walls: Sequence[OutlineWall]
) -> dict[str, list[wall_v1.Opening]]:
    """The hosted doors and windows by the line of the wall they sit in,
    each measured on that wall (OPENING-FROM-END)."""
    specs = {wall.line_id: wall.spec for wall in walls}
    out: dict[str, list[wall_v1.Opening]] = {line: [] for line in specs}
    for hosted in inputs.hosted:
        if hosted.plugin_id not in wall_v1.OPENING_PLUGINS:
            continue
        if hosted.plugin_version == "1.0.0":
            raise PluginError(
                PLUGIN_INPUT_UNSUPPORTED,
                f"{hosted.name}: its release cannot name one wall of an outline; "
                "update it and pick its wall.",
            )
        picked = hosted.inputs.segments("wall_segment")
        if len(picked) != 1 or picked[0] not in out:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"{hosted.name}: pick the wall of the outline it sits in.",
                input="wall_segment",
            )
        opening = wall_v1.Opening.from_hosted(hosted, specs[picked[0]])
        if opening is not None:
            out[picked[0]].append(opening)
    return out


def _outline_sheathing(
    inputs: ExpandInputs,
    wall: OutlineWall,
    openings: Sequence[wall_v1.Opening],
) -> Iterator[Member]:
    """One outline wall's panels (module docstring), named by place."""
    good = sheathing.sheet_good(inputs, "sheathing")
    if good is None:
        return
    spec = wall.spec
    t, s = spec.thickness, good.thickness_in
    first, last = 0.0, spec.length
    if not wall.convex_start:
        first = t if wall.through else s
    if not wall.convex_end:
        last = spec.length - (t if wall.through else s)
    plane = sheathing.face_plane(spec)
    datums, ref = plane.members(inputs)
    yield from datums
    placed = sheathing.placed_wall_panels_between(spec, openings, first, last)
    if not wall.through:
        ends: tuple[tuple[sheathing.End, bool], ...] = (
            ("start", wall.convex_start),
            ("end", wall.convex_end),
        )
        for end, convex in ends:
            if convex:
                rip = sheathing.corner_rip(spec, end, spec, good)
                placed.append((f"corner/{end}", rip))
    for index, (name, region) in enumerate(placed):
        loops = [
            [plane.sketch_point(u, z) for u, z in loop]
            for loop in (region.outer, *region.holes)
        ]
        yield from sheathing.panel_members(
            inputs,
            ("sheathing_section", "sheathing"),
            index,
            ref,
            loops,
            good,
            plane.reverse,
            name,
        )


def _outline_members(inputs: ExpandInputs, outline: Outline) -> Iterator[Member]:
    """Every outline wall's members in turn, clockwise from the first line,
    each named under its line and numbered on across the walls."""
    walls = outline_walls(inputs, outline)
    openings = _openings(inputs, walls)
    counts: Counter[str] = Counter()
    for wall in walls:
        sub = dataclasses.replace(inputs, name_prefix=wall.line_id)
        mine = openings[wall.line_id]
        pieces = wall_v1.wall_pieces(wall.spec, mine, named=True)
        frame = wall_v1.WallFrame.of(wall.spec)
        for member in (
            *wall_v1.emit_pieces(sub, frame, pieces),
            *_outline_sheathing(sub, wall, mine),
        ):
            if member.name is None:  # every 1.1.0+ member is named
                raise RuntimeError(f"loft.wall: unnamed {member.role} in an outline")
            yield dataclasses.replace(
                member,
                index=counts[member.role],
                name=f"{wall.line_id}/{member.name}",
            )
            counts[member.role] += 1


def expand_wall_v1_3(inputs: ExpandInputs) -> Iterator[Member]:
    outline = wall_outline(inputs)
    if outline is None:
        yield from sheathing.expand_wall_v1_2(wall_values(inputs))
        return
    yield from _outline_members(inputs, outline)


WALL_V1_3 = Plugin(WALL_MANIFEST_V1_3, expand_wall_v1_3)
FLOOR_V1_2 = Plugin(FLOOR_MANIFEST_V1_2, expand_floor_v1_2)
FLOOR_V1_3 = Plugin(FLOOR_MANIFEST_V1_3, expand_floor_v1_3)


# --- Wall 1.4.0's slab (the release is interior_wall.WALL_V1_4) ----------------

FLOOR_OR_SLAB_PICK = _FLOOR_PICK.model_copy(
    update={
        "description": "The floor or slab the walls stand on: their base is "
        "its top (a floor's subfloor when it has one); on a slab each bottom "
        "plate lists its anchor bolts. Empty: the typed base elevation.",
        "plugin_ids": ["loft.floor", "loft.slab"],
    }
)


def bolted(member: Member) -> Member:
    """A bottom plate bearing on concrete, listing its anchor bolts."""
    if member.role != "bottom_plate" or member.metadata is None:
        return member
    return dataclasses.replace(
        member,
        metadata=member.metadata.model_copy(update={"anchor_bolts": AnchorBolts()}),
    )


def on_slab(inputs: ExpandInputs, members: Iterator[Member]) -> Iterator[Member]:
    """*members* of a 1.4.0 wall; on a picked slab its bottom plates list
    their anchor bolts (SLAB)."""
    if picked_slab(inputs) is None:
        yield from members
        return
    yield from (bolted(member) for member in members)
