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
from loft_wire.plugin_warning import ROOF_ROOFING_NO_OVERHANG
from loft_wire.plugins import (
    FeatureListInput,
    PluginInput,
    SegmentsInput,
    member_id,
)
from loft_wire.siding import TRIM_THICKNESS_IN
from loft_wire.sketch import SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import roof_roofing
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
    CEILING_BESIDE,
    CEILING_INPUTS,
    CEILING_MATERIAL,
    CEILING_ROLE,
    ceiling_joists,
)
from loft_plugins.builtin.roof_footprint import MIN_PLATE_IN, Footprint
from loft_plugins.builtin.roof_gable import (
    GABLE_INPUTS,
    GABLE_ROLES,
    GABLE_SIDING_ROLE,
    GABLE_STUDS,
    GableSection,
    clear_of_gables,
    gable_ends,
)
from loft_plugins.builtin.roof_roofing import (
    ROOFING_INPUTS,
    ROOFING_ROLES,
    wants_roofing,
)
from loft_plugins.builtin.roof_sheathing import notches
from loft_plugins.builtin.roof_valley import MANIFEST_V1_3, expand_v1_3, hip_roof
from loft_plugins.builtin.sheathing import sheet_good
from loft_plugins.builtin.wall_finish import finish_product, waste_percent

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


def expand_v1_7(inputs: ExpandInputs) -> Iterable[Member]:
    """1.7.0: 1.6.0's members, then a gable on an outline's end walls framed
    and sheathed up to the roof (GABLE-END-STUDS,
    :mod:`~loft_plugins.builtin.roof_gable`). A typed bearing, a hip, and
    Gable ends None are 1.6.0's exactly."""
    return _expand(inputs, notch_hips=True, ceiling=True, gables=True)


def expand_v1_8(inputs: ExpandInputs) -> Iterable[Member]:
    """1.8.0: 1.7.0's members, a gable's end walls' exterior finish (a
    ``loft.wall`` 1.5.0's) carried up each gable over its sheathing
    (SIDING-TRIM). Walls with no finish, a typed bearing, a hip and Gable
    ends None are 1.7.0's exactly."""
    return _expand(
        inputs, notch_hips=True, ceiling=True, gables=True, gable_siding=True
    )


def expand_v1_9(inputs: ExpandInputs) -> Iterable[Member]:
    """1.9.0: 1.8.0's members, then a gable on an outline's roofing when
    Roofing is not None (ROOFING, :mod:`~loft_plugins.builtin.roof_roofing`):
    the deck, fascia and rake boards, the rake boards cut into the end walls'
    trim and siding. Roofing None, a typed bearing, a hip and a gable with no
    eave overhang are 1.8.0's exactly."""
    return _expand(
        inputs,
        notch_hips=True,
        ceiling=True,
        gables=True,
        gable_siding=True,
        roofing=True,
    )


def roofing_note(inputs: ExpandInputs) -> str | None:
    """The stored roof's ``roof_roofing_no_overhang`` message, or None: a
    gable on an outline wall asks for Roofing but has no eave overhang, so
    :func:`expand_v1_9` lays none (no tails to hang the fascia on). Pure."""
    if "roofing" not in inputs.values or not wants_roofing(inputs):
        return None
    if inputs.choice("style") != STYLE_GABLE or inches("overhang_mm", inputs) > 0.0:
        return None
    if not any(is_outline_wall(inputs.resolve(p)) for p in inputs.features("walls")):
        return None
    return (
        "Roofing is Asphalt shingles, but this gable has no eave overhang: no "
        "roofing without rafter tails to hang the fascia on; give the eaves an "
        "overhang, or set Roofing to None."
    )


def roofing_notes(inputs: ExpandInputs) -> list[tuple[str, str]]:
    """The stored roof's input warnings, as (code, message), as
    ``finish_notes``."""
    note = roofing_note(inputs)
    return [] if note is None else [(ROOF_ROOFING_NO_OVERHANG, note)]


def ceiling_joist_note(inputs: ExpandInputs) -> str | None:
    """Why a 1.6.0 roof asked for ceiling joists frames none (its chosen
    joist would pass the ridge board), or ``None``: the stored roof's
    ``ceiling_joists_omitted`` warning. Pure, as the expansion it re-runs."""
    if inputs.values.get("ceiling_joists") != CEILING_BESIDE:
        return None
    notes: list[str] = []
    try:
        _expand(inputs, notch_hips=True, ceiling=True, notes=notes)
    except PluginError:
        return None
    return notes[0] if notes else None


def _expand(
    inputs: ExpandInputs,
    *,
    notch_hips: bool,
    ceiling: bool = False,
    notes: list[str] | None = None,
    gables: bool = False,
    gable_siding: bool = False,
    roofing: bool = False,
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
    ends = (
        [w for w in walls if w.line_id not in eaves.values()]
        if gables and inputs.choice("gable_ends") == GABLE_STUDS
        else []
    )
    if ceiling:
        members += ceiling_joists(
            inputs,
            members,
            rafter,
            span,
            length,
            place,
            notes,
            clear_of_gables(ends, place),
        )
    if ends:
        ridge = inputs.lumber("ridge_profile")
        section = GableSection(
            rafter,
            span,
            ridge.thickness_in / 2,
            rafter.top_at_ridge - ridge.width_in,
        )
        good = sheet_good(wall_inputs, "sheathing")
        product = finish_product(wall_inputs) if gable_siding else None
        finish = None if product is None else (product, waste_percent(wall_inputs))
        members += gable_ends(
            inputs, members, ref.feature_id, ends, good, section, place, finish
        )
    if roofing and overhang > 0.0 and wants_roofing(inputs):
        good = sheet_good(wall_inputs, "sheathing")
        members += roof_roofing.roofing(
            inputs,
            members,
            roof_roofing.Context(
                rafter=rafter,
                span=span,
                length=length,
                place=place,
                wall_id=ref.feature_id,
                ends=[w for w in walls if w.line_id not in eaves.values()],
                eaves=(eaves[low_side], eaves[high_side]),
                sheathed=0.0 if good is None else good.thickness_in,
                finish=finish_product(wall_inputs),
                spacing=inches("spacing_mm", inputs),
                rafter_t=inputs.lumber("rafter_profile").thickness_in,
                waste=inputs.count("roofing_waste_percent"),
            ),
        )
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
    or a tail (overhang 0).

    A ``loft.wall`` 1.5.0's exterior finish lies outside the sheathing under
    the same tails, so each tail is notched out of the siding and the corner
    boards it crosses too (SIDING-TRIM), listed after the sheathing: a wall
    before 1.5.0 has none, so a stored roof's notches are as they were."""
    good = sheet_good(wall_inputs, "sheathing")
    finish = finish_product(wall_inputs)
    if (good is None and finish is None) or rafter.overhang == 0.0:
        return []
    s = 0.0 if good is None else good.thickness_in
    # The tail's underside where it leaves each layer's outside face: the
    # layer's material above it is the rafter's.
    siding = 0.0 if finish is None else finish.thickness_in
    outside = {
        "sheathing": s,
        "siding": s + siding,
        "corner_board": s + TRIM_THICKNESS_IN,
    }
    t = inputs.lumber("rafter_profile").thickness_in
    spacing = inches("spacing_mm", inputs)
    centres = joist_centres(length, spacing, t)
    slots = layout_slots(len(centres))
    start = place.x0 if place.along_x else place.y0
    direction: Literal["normal", "reverse"] = "normal" if place.along_x else "reverse"
    panels: dict[str, list[tuple[uuid.UUID, tuple[float, float, float], float]]] = {}
    for side, line_id in eaves.items():
        found: list[tuple[uuid.UUID, tuple[float, float, float], float]] = []
        names = [
            ("sheathing", f"{line_id}/corner/start"),
            ("sheathing", f"{line_id}/corner/end"),
        ]
        names += [
            ("sheathing", f"{line_id}/exterior/{col}/{row}")
            for col in range(math.ceil(length / 48.0) + 2)
            for row in range(4)
        ]
        if finish is not None:
            k = 0
            while member_id(wall_id, "siding", 0, f"{line_id}/siding/{k}") in (
                inputs.earlier
            ):
                names.append(("siding", f"{line_id}/siding/{k}"))
                k += 1
            names += [
                ("corner_board", f"{line_id}/corner/start"),
                ("corner_board", f"{line_id}/corner/end"),
            ]
        for role, name in names:
            panel = member_id(wall_id, role, 0, name)
            extent = _panel_span(inputs, panel)
            if extent is not None:
                found.append((panel, extent, rafter.bottom(-outside[role])))
        panels[side] = found
    out: list[Member] = []
    for centre, slot in zip(centres, slots, strict=True):
        x0 = centre - t / 2
        at = x0 if start == 0.0 else start + x0
        for side in eaves:
            hit = [
                FeatureRef(kind="feature", feature_id=panel)
                for panel, (a, b, top), low in panels[side]
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


def _inputs_v1_7() -> list[PluginInput]:
    """1.6.0's inputs, Gable ends after the ceiling joists' size."""
    out: list[PluginInput] = []
    for item in MANIFEST_V1_6.inputs:
        out.append(item)
        if item.name == "ceiling_joist_profile":
            out += GABLE_INPUTS
    return out


MANIFEST_V1_7 = MANIFEST_V1_6.model_copy(
    update={
        "version": "1.7.0",
        "description": "A gable or hip roof on its walls, each wall defining the "
        "slope or not: rafters with a birdsmouth on each wall, ridges, hips, "
        "valleys and jacks, the tails notched out of the wall sheathing, with "
        "a cut list (Revit Roof by Footprint, Chief Architect). A gable on its "
        "walls ties each inner common pair with a ceiling joist (IRC "
        "R802.5.2) and frames its end walls up to the roof: gable studs on "
        "their layout, their sheathing carried up.",
        "inputs": _inputs_v1_7(),
        "members": [*MANIFEST_V1_6.members, *GABLE_ROLES],
    }
)

ROOF_V1_7 = Plugin(MANIFEST_V1_7, expand_v1_7)


MANIFEST_V1_8 = MANIFEST_V1_7.model_copy(
    update={
        "version": "1.8.0",
        "description": "A gable or hip roof on its walls, each wall defining the "
        "slope or not: rafters with a birdsmouth on each wall, ridges, hips, "
        "valleys and jacks, the tails notched out of the walls' sheathing and "
        "siding, with a cut list (Revit Roof by Footprint, Chief Architect). A "
        "gable on its walls ties each inner common pair with a ceiling joist "
        "and frames its end walls up to the roof: gable studs on their "
        "layout, their sheathing and siding carried up.",
        "members": [*MANIFEST_V1_7.members, GABLE_SIDING_ROLE],
    }
)

ROOF_V1_8 = Plugin(MANIFEST_V1_8, expand_v1_8)


def _inputs_v1_9() -> list[PluginInput]:
    """1.8.0's inputs, Roofing and its waste after Gable ends."""
    out: list[PluginInput] = []
    for item in MANIFEST_V1_8.inputs:
        out.append(item)
        if item.name == "gable_ends":
            out += ROOFING_INPUTS
    return out


MANIFEST_V1_9 = MANIFEST_V1_8.model_copy(
    update={
        "version": "1.9.0",
        "description": "A gable or hip roof on its walls, each wall defining the "
        "slope or not: rafters with a birdsmouth on each wall, ridges, hips, "
        "valleys and jacks, the tails notched out of the walls' sheathing and "
        "siding, with a cut list (Revit Roof by Footprint, Chief Architect). A "
        "gable on its walls ties each inner common pair with a ceiling joist, "
        "frames its end walls up to the roof, and can be roofed: a 7/16 OSB "
        "deck, fascia and rake boards, with shingles, underlayment, drip edge, "
        "starter and ridge cap listed.",
        "inputs": _inputs_v1_9(),
        "members": [*MANIFEST_V1_8.members, *ROOFING_ROLES],
    }
)

ROOF_V1_9 = Plugin(MANIFEST_V1_9, expand_v1_9)
