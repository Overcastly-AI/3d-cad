"""Roof 1.4.0: a roof on an outline wall, each wall defining the slope or not
(BUILDING-OUTLINE, ROOF-GABLE-WALLS, RESEARCH §23).

Revit builds a footprint roof from picked walls, each marked "Defines
Slope"; Chief Architect's gable wall is a wall that does not. ``loft.roof``
1.4.0 adds **Defines slope** (a segments input on the picked walls): the lines
of a picked OUTLINE wall (``loft.wall`` 1.3.0 on a sketch) whose walls carry
an eave. The plate height and width are read from the walls.

* **Gable:** two opposite walls of a rectangular outline define the slope.
  The ridge runs parallel to them, centred between their outer faces, the
  span is the distance between those faces and the length the outline's other
  side: 1.3.0's gable exactly, placed on the outline (B2 on an outline is
  ``b2-roof-6-12`` member for member; B7's roof follows its 288 dimension).
* **Hip:** every wall defines the slope (left empty, all do, as Revit's
  default): 1.3.0's hip roof on the outline's corners, a rectangle or an L.

Any other pick (one wall, two adjacent, three) is refused: a shed, a Dutch
gable and a hip with a gable end are later rungs. Without an outline wall,
1.4.0 is 1.3.0 exactly (the typed bearing, or hip on picked line walls), and
Defines slope must be left empty.

**1.5.0** (ROOF-HIP-SHEATHING-NOTCH, ROOF-THROUGH-SHEATHING-UPDATE) is 1.4.0's
members, then each member notched out of the sheathing of the walls it
picks (:func:`~loft_plugins.builtin.roof_sheathing.notches`): a hip on an
outline wall, which 1.4.0 refuses on sheathed walls, and a hip on picked
line walls. A gable on an outline keeps 1.4.0's notches byte for byte; a
roof on its typed bearing picks no walls and is 1.3.0's exactly.
"""

import math
import uuid
from collections.abc import Iterable
from typing import Literal

from loft_wire.features import (
    CustomFeature,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    FeatureListInput,
    PluginInput,
    SegmentsInput,
    member_id,
)
from loft_wire.sketch import SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin
from loft_plugins.builtin.deck import joist_centres
from loft_plugins.builtin.house import (
    is_outline_wall,
    outline_walls,
    stored_inputs,
    wall_outline,
)
from loft_plugins.builtin.roof import (
    MIN_OVERHANG_IN,
    STYLE_GABLE,
    STYLE_HIP,
    GablePlace,
    Rafter,
    gable_on,
    inches,
    layout_slots,
    rafter_for,
    unsupported,
)
from loft_plugins.builtin.roof_ceiling import (
    CEILING_INPUTS,
    CEILING_MATERIAL,
    CEILING_ROLE,
    ceiling_joists,
)
from loft_plugins.builtin.roof_footprint import MIN_PLATE_IN, Footprint
from loft_plugins.builtin.roof_sheathing import notches
from loft_plugins.builtin.roof_valley import MANIFEST_V1_3, expand_v1_3, hip_roof
from loft_plugins.builtin.sheathing import sheet_good

_DIGITS = 9
#: The typed bearing that picked walls replace.
_TYPED = ("span_mm", "length_mm", "plate_height_mm", "plate_width_mm")
#: A gable's bounds, as 1.0.0's typed span and length.
_SPAN_IN = (48.0, 480.0)
_LENGTH_IN = (24.0, 720.0)


def _inputs() -> list[PluginInput]:
    out: list[PluginInput] = []
    for item in MANIFEST_V1_3.inputs:
        if item.name in _TYPED:
            out.append(item.model_copy(update={"superseded_by": "walls"}))
        elif isinstance(item, FeatureListInput) and item.name == "walls":
            out.append(
                item.model_copy(
                    update={
                        "description": "The walls the roof bears on (Revit's Pick "
                        "Walls): an outline wall, or line walls closing a rectangle "
                        "or an L (Hip style). Plate height and width are read from "
                        "them. None: the typed bearing below."
                    }
                )
            )
            out.append(
                SegmentsInput(
                    kind="segments",
                    name="slope_walls",
                    label="Defines slope",
                    description="On an outline wall: the walls that carry an eave "
                    "(Revit's Defines Slope). Gable: two opposite walls. Hip: "
                    "every wall (empty is every wall).",
                    outline_input="walls",
                    min_items=0,
                )
            )
        else:
            out.append(item)
    return out


MANIFEST_V1_4 = MANIFEST_V1_3.model_copy(
    update={
        "version": "1.4.0",
        "description": "A gable or hip roof on its walls, each wall defining the "
        "slope or not, of rafters with a birdsmouth on each wall, ridges, hips, "
        "valleys and their jacks, with a cut list (Revit Roof by Footprint, "
        "Chief Architect).",
        "inputs": _inputs(),
    }
)


def expand_v1_4(inputs: ExpandInputs) -> Iterable[Member]:
    return _expand(inputs, notch_hips=False)


def expand_v1_5(inputs: ExpandInputs) -> Iterable[Member]:
    """1.5.0: 1.4.0's members, then every tail notched out of the picked
    walls' sheathing: a hip's commons, jacks and hips on an outline or on
    picked line walls too (ROOF-HIP-SHEATHING-NOTCH,
    ROOF-THROUGH-SHEATHING-UPDATE). A gable on an outline is 1.4.0's
    exactly; a roof on its typed bearing picks no walls and is too."""
    return _expand(inputs, notch_hips=True)


def expand_v1_6(inputs: ExpandInputs) -> Iterable[Member]:
    """1.6.0: 1.5.0's members, then a gable on an outline's ceiling joists
    (CEILING-JOISTS, :mod:`~loft_plugins.builtin.roof_ceiling`). A typed
    bearing, a hip, and Ceiling joists None are 1.5.0's exactly."""
    return _expand(inputs, notch_hips=True, ceiling=True)


def _expand(
    inputs: ExpandInputs, *, notch_hips: bool, ceiling: bool = False
) -> list[Member]:
    picks = inputs.features("walls")
    outlines = [p for p in picks if is_outline_wall(inputs.resolve(p))]
    slope = inputs.segments("slope_walls")
    if not outlines:
        if slope:
            raise unsupported(
                "Defines slope picks the walls of an outline wall: pick one in "
                "Walls, or leave Defines slope empty.",
                "slope_walls",
            )
        members = list(expand_v1_3(inputs))
        if notch_hips and picks:
            # A hip on picked line walls (a gable takes none: 1.3.0 refuses).
            members += notches(inputs, members, [p.feature_id for p in picks], "walls")
        return members
    if len(picks) != 1:
        raise unsupported(
            "Pick the outline wall alone: its walls are the roof's bearing.",
            "walls",
        )
    overhang = inches("overhang_mm", inputs)
    if 0.0 < overhang < MIN_OVERHANG_IN - 1e-9:
        raise unsupported(
            "The eave overhang must be 0 (cut flush at the wall) or at least 1/16 in.",
            "overhang_mm",
        )
    ref = picks[0]
    envelope = inputs.resolve(ref)
    assert isinstance(envelope, CustomFeature)
    wall_inputs = stored_inputs(
        ref.feature_id, envelope, inputs.earlier, inputs.parameters
    )
    outline = wall_outline(wall_inputs)
    assert outline is not None
    walls = outline_walls(wall_inputs, outline)
    spec = walls[0].spec
    plate = round(spec.elevation + spec.height, _DIGITS)
    if plate < MIN_PLATE_IN - 1e-6:
        raise unsupported(f"The walls' plates are below {MIN_PLATE_IN:g} in.", "walls")
    picked = [outline.index(line_id, "slope_walls") for line_id in slope]
    style = inputs.choice("style")
    if style == STYLE_HIP:
        if picked and len(picked) != len(outline.segments):
            raise unsupported(
                "A hip roof's every wall defines the slope: pick them all, or "
                "leave Defines slope empty. (A gable end on a hip roof is a later "
                "rung.)",
                "slope_walls",
            )
        if not notch_hips and sheet_good(wall_inputs, "sheathing") is not None:
            raise unsupported(
                "A hip roof on sheathed outline walls is a later rung: its "
                "tails and hips would pass through the wall sheathing. Choose "
                "Gable, or sheathe the walls after (Exterior sheathing None).",
                "style",
            )
        footprint = Footprint(outline.ccw_corners, plate, spec.thickness)
        members = hip_roof(inputs, footprint, typed=False, named=True)
        if notch_hips:
            members += notches(inputs, members, [ref.feature_id], "style")
        return members
    if style != STYLE_GABLE:
        raise unsupported(f"{style!r} is not a roof style", "style")
    if not outline.is_rectangle:
        raise unsupported(
            "A gable roofs a rectangular outline; choose Hip for an L.", "style"
        )
    segments = outline.segments
    if len(picked) != 2 or segments[picked[0]].direction != tuple(
        -c for c in segments[picked[1]].direction
    ):
        raise unsupported(
            "A gable's slope is defined by two opposite walls: pick the two "
            "walls its rafters bear on (the gable ends do not define slope).",
            "slope_walls",
        )
    along_x = segments[picked[0]].direction[1] == 0
    xs = [s.start[0] for s in segments]
    ys = [s.start[1] for s in segments]
    width_x = round(max(xs) - min(xs), _DIGITS)
    width_y = round(max(ys) - min(ys), _DIGITS)
    span, length = (width_y, width_x) if along_x else (width_x, width_y)
    if not _SPAN_IN[0] - 1e-9 <= span <= _SPAN_IN[1] + 1e-9:
        raise unsupported(
            f"A gable spans {_SPAN_IN[0]:g} to {_SPAN_IN[1]:g} in between the walls "
            f"that define its slope; these are {span:g} in apart.",
            "slope_walls",
        )
    if not _LENGTH_IN[0] - 1e-9 <= length <= _LENGTH_IN[1] + 1e-9:
        raise unsupported(
            f"A gable runs {_LENGTH_IN[0]:g} to {_LENGTH_IN[1]:g} in along its "
            f"ridge; this one is {length:g} in.",
            "slope_walls",
        )
    place = GablePlace(min(xs) + 0.0, min(ys) + 0.0, along_x)
    members = list(gable_on(inputs, True, span, length, plate, spec.thickness, place))
    # Which side of the gable each eave wall is: the rafters' first side
    # (front, or left along Y) bears on the wall at the low coordinate.
    low_side, high_side = ("front", "back") if along_x else ("left", "right")
    across = 1 if along_x else 0
    lowest = min(ys) if along_x else min(xs)
    eaves = {
        (low_side if segments[k].start[across] == lowest else high_side): (
            segments[k].line_id
        )
        for k in picked
    }
    rafter = rafter_for(
        int(inputs.choice("pitch").removeprefix("rise_")),
        inputs.lumber("rafter_profile"),
        inputs.lumber("ridge_profile"),
        span,
        plate,
        spec.thickness,
        overhang,
    )
    members += _tail_notches(
        inputs, ref.feature_id, wall_inputs, eaves, rafter, length, place
    )
    if ceiling:
        members += ceiling_joists(inputs, members, rafter, span, length, place)
    return members


def _panel_span(
    inputs: ExpandInputs, panel: uuid.UUID
) -> tuple[float, float, float] | None:
    """An earlier sheathing panel's extent along its wall (its sketch's x on
    the wall's ``XZ`` or ``YZ`` face plane) and its top (in), or ``None``
    when the wall has no panel of that name."""
    body = inputs.earlier.get(panel)
    if not isinstance(body, ExtrudeFeature):
        return None
    section = inputs.earlier.get(body.params.profile.feature_id)
    if not isinstance(section, SketchFeature):
        return None
    along: list[float] = []
    up: list[float] = []
    for entity in section.params.entities:
        if isinstance(entity, SketchLine):
            along.append(entity.start.x / MM_PER_INCH)
            up.append(entity.start.y / MM_PER_INCH)
    if not along:
        return None
    return (min(along), max(along), max(up))


def _tail_notches(
    inputs: ExpandInputs,
    wall_id: uuid.UUID,
    wall_inputs: ExpandInputs,
    eaves: dict[str, str],
    rafter: Rafter,
    length: float,
    place: GablePlace,
) -> list[Member]:
    """Each rafter tail notched out of the eave wall's sheathing it passes
    through (BUILDING-OUTLINE). The heel is on the framing's outside face, so
    a tail crosses the sheathing below the plate's top; framers notch the
    sheathing round the tails, as a Revit wall attached to the roof is cut by
    it. Each notch is a cut of the rafter's own side profile, its thickness,
    from exactly the panels it crosses (Objects To Cut): the panel then meets
    the rafter face to face, with no shared volume. None without sheathing
    or a tail (overhang 0)."""
    good = sheet_good(wall_inputs, "sheathing")
    if good is None or rafter.overhang == 0.0:
        return []
    s = good.thickness_in
    # The tail's underside where it leaves the sheathing's outside face: the
    # panel material above it is the rafter's.
    low = rafter.bottom(-s)
    t = inputs.lumber("rafter_profile").thickness_in
    spacing = inches("spacing_mm", inputs)
    centres = joist_centres(length, spacing, t)
    slots = layout_slots(len(centres))
    start = place.x0 if place.along_x else place.y0
    direction: Literal["normal", "reverse"] = "normal" if place.along_x else "reverse"
    panels: dict[str, list[tuple[uuid.UUID, tuple[float, float, float]]]] = {}
    for side, line_id in eaves.items():
        found: list[tuple[uuid.UUID, tuple[float, float, float]]] = []
        names = [f"{line_id}/corner/start", f"{line_id}/corner/end"]
        names += [
            f"{line_id}/exterior/{col}/{row}"
            for col in range(math.ceil(length / 48.0) + 2)
            for row in range(4)
        ]
        for name in names:
            panel = member_id(wall_id, "sheathing", 0, name)
            extent = _panel_span(inputs, panel)
            if extent is not None:
                found.append((panel, extent))
        panels[side] = found
    out: list[Member] = []
    for centre, slot in zip(centres, slots, strict=True):
        x0 = centre - t / 2
        at = x0 if start == 0.0 else start + x0
        for side in eaves:
            hit = [
                FeatureRef(kind="feature", feature_id=panel)
                for panel, (a, b, top) in panels[side]
                if min(b, at + t) - max(a, at) > 1e-9 and top > low + 1e-9
            ]
            if not hit:
                continue
            name = f"{side}/{slot}"
            out.append(
                Member(
                    "cutter",
                    len(out),
                    ExtrudeFeature(
                        type="extrude",
                        version=1,
                        params=ExtrudeParamsV1(
                            profile=inputs.ref("section", 0, f"rafter/{name}"),
                            distance_mm=t * MM_PER_INCH,
                            operation="cut",
                            direction=direction,
                            cut_bodies=hit,
                        ),
                    ),
                    name=f"tail/{name}",
                )
            )
    return out


ROOF_V1_4 = Plugin(MANIFEST_V1_4, expand_v1_4)

MANIFEST_V1_5 = MANIFEST_V1_4.model_copy(
    update={
        "version": "1.5.0",
        "description": MANIFEST_V1_4.description
        + " Every rafter and hip tail is notched out of the sheathing of the "
        "walls it bears on.",
    }
)

ROOF_V1_5 = Plugin(MANIFEST_V1_5, expand_v1_5)


def _inputs_v1_6() -> list[PluginInput]:
    """1.5.0's inputs, the ceiling joists' after the member sizes and their
    material after the others'."""
    out: list[PluginInput] = []
    for item in MANIFEST_V1_5.inputs:
        if item.name == "rafter_material":
            out += CEILING_INPUTS
        out.append(item)
    out.append(CEILING_MATERIAL)
    return out


MANIFEST_V1_6 = MANIFEST_V1_5.model_copy(
    update={
        "version": "1.6.0",
        "description": MANIFEST_V1_5.description
        + " A gable on its walls ties each inner common pair with a ceiling "
        "joist on the plates (IRC R802.5.2).",
        "inputs": _inputs_v1_6(),
        "members": [*MANIFEST_V1_5.members, CEILING_ROLE],
    }
)

ROOF_V1_6 = Plugin(MANIFEST_V1_6, expand_v1_6)
