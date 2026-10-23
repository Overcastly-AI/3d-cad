"""Window and Door: rough openings hosted in a wall (WINDOW-DOOR, RESEARCH §23).

As Revit and Chief Architect host them: a window or door names its host wall
(a ``loft.wall`` feature input) and sits at an offset along it, and the WALL
frames it. ``loft.wall`` receives every opening that names it
(``ExpandInputs.hosted``) and lays out kings, jacks, a doubled header, top
cripples and, for a window, a flat sill with bottom cripples, cutting the
bottom plate for a door (``loft_plugins.builtin.wall``). A write to an opening
re-expands its wall.

Through 1.2.0 an opening frames its ROUGH OPENING only and expands to no
member of its own. 1.3.0 (OPENING-UNITS) picks the unit by call size from a
catalogue (``loft_wire.opening_units``: 3040 is a 3'0" x 4'0" window, 3068 a
3'0" x 6'8" door), which sets the rough opening, and DRAWS the unit as two
bodies, a frame and its glass (a door: a frame and its slab), inside the
rough opening and clear of the framing, as Revit's and Chief Architect's
window and door families draw it. The cut list lists the unit once, Each, on
its frame (``MemberMetadata.unit``). "Rough opening only" leaves it out. Its expansion
checks that it fits its wall, so a write that does not fit is refused on the
opening's own field, before the wall is re-expanded.

**Inputs.** Unit width and height, the rough-opening allowance added to each
(a 36 x 80 prehung door takes 2 x 2.5, a 24 x 36 window 0.5 x 0.5: B2's
38 x 82.5 and 24.5 x 36.5), the offset of the unit's centre along the wall
from the wall's start, and for a window the head height: the top of the rough
opening (the header's underside) above the wall's base, 82.5 in by default so
window and door heads align, as framers set them. A door's rough opening
stands on the wall's base. The header is two plies of ``header_profile`` on
edge; from 1.4.0 (HEADER-PLIES), by default as many as fill the wall (three
in a 2x6 wall), or two with foam between.
"""

from collections.abc import Iterator
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
from loft_wire.lumber import MM_PER_INCH, LumberProfileKey
from loft_wire.materials import MaterialKey
from loft_wire.opening_units import UNIT_MATERIAL, OpeningUnitPart, catalogue
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    LengthInput,
    MemberMetadata,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
    SegmentsInput,
)
from loft_wire.sketch import Point2D

from loft_plugins.api import (
    Expander,
    ExpandInputs,
    InputValue,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)
from loft_plugins.builtin.house import is_outline_wall, wall_specs_of
from loft_plugins.builtin.sheathing import FacePlane, face_plane, loops_entities
from loft_plugins.builtin.wall import (
    CUSTOM_SIZE,
    Opening,
    UnitSize,
    WallSpec,
    frame_opening,
    nearer_end,
    unit_size,
)

_HEADERS: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]


def _length(
    name: str, label: str, default_in: float, low_in: float, high_in: float, help: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=help,
        default=default_in * MM_PER_INCH,
        minimum=low_in * MM_PER_INCH,
        maximum=high_in * MM_PER_INCH,
    )


def _inputs(
    kind: Literal["door", "window"],
    unit: tuple[float, float],
    allowance: tuple[float, float],
) -> list[PluginInput]:
    what = "door" if kind == "door" else "window"
    inputs: list[PluginInput] = [
        FeatureReferenceInput(
            kind="feature",
            name="host_wall",
            label="Host wall",
            description=f"The wall this {what} sits in; the wall frames it.",
            feature_types=["custom"],
            plugin_ids=["loft.wall"],
            host=True,
        ),
        _length(
            "offset_mm",
            "Offset",
            72.0,
            0.0,
            960.0,
            f"From the wall's start to the {what}'s centre, along the wall.",
        ),
        _length("width_mm", "Unit width", unit[0], 12.0, 144.0, "The unit's width."),
        _length("height_mm", "Unit height", unit[1], 12.0, 144.0, "The unit's height."),
        _length(
            "ro_width_allowance_mm",
            "RO width allowance",
            allowance[0],
            0.0,
            6.0,
            "Added to the unit width for the rough opening (shims, plumbing).",
        ),
        _length(
            "ro_height_allowance_mm",
            "RO height allowance",
            allowance[1],
            0.0,
            6.0,
            "Added to the unit height for the rough opening.",
        ),
    ]
    if kind == "window":
        inputs.append(
            _length(
                "head_height_mm",
                "Head height",
                82.5,
                24.0,
                234.0,
                "Top of the rough opening (the header's underside) above the "
                "wall's base; 82.5 aligns with a 6'8\" door's.",
            )
        )
    inputs.append(
        ChoiceInput(
            kind="choice",
            name="header_profile",
            label="Header",
            description="Two plies on edge over the jacks.",
            options=lumber_options(_HEADERS),
            default="us_2x6",
        )
    )
    return inputs


def _members(what: str) -> list[PluginMemberRole]:
    return [
        PluginMemberRole(
            role="unit",
            title="Unit",
            description=f"The {what} unit's body (not yet drawn: the wall frames "
            "the rough opening).",
        )
    ]


WINDOW_MANIFEST_V1 = PluginManifest(
    id="loft.window",
    version="1.0.0",
    title="Window",
    description="A window hosted in a wall: its wall frames the rough opening "
    "with kings, jacks, a header, a sill and cripples (Revit, Chief Architect).",
    inputs=_inputs("window", (24.0, 36.0), (0.5, 0.5)),
    members=_members("window"),
)

DOOR_MANIFEST_V1 = PluginManifest(
    id="loft.door",
    version="1.0.0",
    title="Door",
    description="A door hosted in a wall: its wall frames the rough opening "
    "with kings, jacks, a header and cripples, and cuts the bottom plate.",
    inputs=_inputs("door", (36.0, 80.0), (2.0, 2.5)),
    members=_members("door"),
)


def _host(inputs: ExpandInputs, segments: bool) -> tuple[WallSpec, bool]:
    """The host wall's spec, from its stored inputs (the registry has checked
    it is an earlier ``loft.wall``), and whether it frames as 1.1.0 does.
    *segments* (1.1.0) reads ``wall_segment``: which wall of an outline wall
    (BUILDING-OUTLINE) the opening sits in."""
    ref = inputs.feature("host_wall")
    host = inputs.resolve(ref)
    if not isinstance(host, CustomFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Host wall: pick an earlier Wall.", input="host_wall"
        )
    named = host.params.plugin_version != "1.0.0"
    if not segments:
        if is_outline_wall(host):
            # Outline walls are new: no stored 1.0.0 opening names one.
            raise PluginError(
                PLUGIN_INPUT_UNSUPPORTED,
                "Host wall: this release cannot pick one wall of an outline; "
                "update the opening to pick its wall.",
                input="host_wall",
            )
        spec = WallSpec.from_inputs(ExpandInputs(ref.feature_id, host.params.inputs))
        return spec, named
    specs = dict(wall_specs_of(ref.feature_id, host, inputs.earlier, inputs.parameters))
    picked = inputs.segments("wall_segment")
    if None in specs:
        if picked:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Wall: the host is one wall, not an outline; leave Wall empty.",
                input="wall_segment",
            )
        return specs[None], named
    if len(picked) != 1 or picked[0] not in specs:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Wall: pick the wall of the outline this opening sits in.",
            input="wall_segment",
        )
    return specs[picked[0]], named


def _expander(
    kind: Literal["door", "window"], title: str, segments: bool = False
) -> Expander:
    def expand(inputs: ExpandInputs) -> Iterator[Member]:
        wall, named = _host(inputs, segments)
        opening = Opening.from_inputs(kind, f"This {title}", inputs, wall)
        frame_opening(wall, opening, named)
        return iter(())

    return expand


WINDOW_V1 = Plugin(WINDOW_MANIFEST_V1, _expander("window", "window"))
DOOR_V1 = Plugin(DOOR_MANIFEST_V1, _expander("door", "door"))


# --- 1.1.0: a wall of an outline (BUILDING-OUTLINE) -------------------------------


def _with_segment(manifest: PluginManifest) -> PluginManifest:
    """*manifest* at 1.1.0: a Wall pick after the host, for an outline wall."""
    inputs = list(manifest.inputs)
    inputs.insert(
        1,
        SegmentsInput(
            kind="segments",
            name="wall_segment",
            label="Wall",
            description="When the host is an outline wall: which of its walls "
            "(a line of the outline) this sits in. Empty for a single wall.",
            outline_input="host_wall",
            min_items=0,
            max_items=1,
        ),
    )
    return manifest.model_copy(
        update={
            "version": "1.1.0",
            "inputs": inputs,
            "description": manifest.description
            + " It may sit in one wall of an outline wall.",
        }
    )


WINDOW_MANIFEST_V1_1 = _with_segment(WINDOW_MANIFEST_V1)
DOOR_MANIFEST_V1_1 = _with_segment(DOOR_MANIFEST_V1)

WINDOW_V1_1 = Plugin(WINDOW_MANIFEST_V1_1, _expander("window", "window", True))
DOOR_V1_1 = Plugin(DOOR_MANIFEST_V1_1, _expander("door", "door", True))


# --- 1.2.0: measured from either end or the centre (OPENING-FROM-END) --------------

#: The distance's bounds at 1.2.0: signed, as from the centre it runs either
#: way (positive towards the wall's end); a wall is at most 960 in long.
_DISTANCE_IN = 960.0


def _with_measure_from(manifest: PluginManifest) -> PluginManifest:
    """*manifest* (1.1.0) at 1.2.0: Measured from after the Wall pick, and
    the offset read from it, as Revit's and Chief Architect's temporary
    dimensions read from either wall end."""
    what = manifest.title.lower()
    inputs: list[PluginInput] = []
    for item in manifest.inputs:
        if item.name == "offset_mm":
            inputs.append(
                ChoiceInput(
                    kind="choice",
                    name="measure_from",
                    label="Measured from",
                    description=f"The point of the wall the {what}'s distance "
                    "runs from. Nearer the origin stores whichever end is "
                    "nearer the part origin, so the opening stays put in plan "
                    "when the far end moves.",
                    options=[
                        ChoiceOption(value="nearer", label="Nearer the origin"),
                        ChoiceOption(value="start", label="Wall start"),
                        ChoiceOption(value="end", label="Wall end"),
                        ChoiceOption(value="centre", label="Wall centre"),
                    ],
                    default="nearer",
                )
            )
            inputs.append(
                _length(
                    "offset_mm",
                    "Distance",
                    72.0,
                    -_DISTANCE_IN,
                    _DISTANCE_IN,
                    f"From the Measured-from point to the {what}'s centre, "
                    "along the wall (from the centre, positive towards the "
                    "wall's end).",
                )
            )
        else:
            inputs.append(item)
    return manifest.model_copy(
        update={
            "version": "1.2.0",
            "inputs": inputs,
            "description": manifest.description
            + " Its distance runs from the wall's start, end or centre.",
        }
    )


def _settle(inputs: ExpandInputs) -> dict[str, InputValue]:
    """Nearer the origin is stored as the wall end it is (documents calls
    this on every write), so a stored opening never changes reference."""
    values = dict(inputs.values)
    if inputs.choice("measure_from") == "nearer":
        wall, _ = _host(inputs, True)
        values["measure_from"] = nearer_end(wall)
    return values


WINDOW_MANIFEST_V1_2 = _with_measure_from(WINDOW_MANIFEST_V1_1)
DOOR_MANIFEST_V1_2 = _with_measure_from(DOOR_MANIFEST_V1_1)

WINDOW_V1_2 = Plugin(
    WINDOW_MANIFEST_V1_2, _expander("window", "window", True), settle=_settle
)
DOOR_V1_2 = Plugin(DOOR_MANIFEST_V1_2, _expander("door", "door", True), settle=_settle)


# --- 1.3.0: a unit picked by call size and drawn (OPENING-UNITS) --------------------

#: How a 1.3.0 unit is drawn (in): Loft's drawing convention, as a Revit or
#: Chief Architect family draws a unit, not a maker's section. A window is a
#: frame 2 in wide round the glass and 3-1/4 in deep (a vinyl
#: new-construction frame), the frame's outside face on the framing's
#: exterior face, and one 1/4 in pane centred in its depth. A door is a
#: frame of 3/4 in jambs and head and a 1-1/4 in threshold, the framing's
#: depth deep, round a 1-3/4 in slab at its exterior face.
WINDOW_FRAME_FACE = 2.0
WINDOW_FRAME_DEPTH = 3.25
GLASS = 0.25
DOOR_JAMB = 0.75
DOOR_THRESHOLD = 1.25
DOOR_SLAB = 1.75

#: The second body's material: a window's glass, a door's wood slab.
_INFILL_MATERIAL: dict[str, MaterialKey] = {"window": "glass", "door": "spf_lumber"}

#: A rectangle in the wall's frame (in): u0, u1, z0, z1.
Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class UnitBody:
    """One body of a unit in its wall's frame (inches): a rectangle in the
    wall's plane, less a rectangular hole, from ``v0`` to ``v1`` in from the
    framing's exterior face."""

    role: str
    outer: Rect
    hole: Rect | None
    v0: float
    v1: float
    material: MaterialKey
    counted: bool


def _round_in(value: float) -> float:
    return round(value, 9)


def _frame_material(size: UnitSize, kind: Literal["door", "window"]) -> MaterialKey:
    return size.size.material if size.size is not None else UNIT_MATERIAL[kind]


def unit_bodies(
    kind: Literal["door", "window"], wall: WallSpec, opening: Opening, size: UnitSize
) -> list[UnitBody]:
    """The unit in *opening* (the constants above): a window centred in its
    rough opening, the unit its call size; a door's frame round its slab,
    centred across the opening and standing on the wall's base. Raises a
    :class:`PluginError` when a typed (custom) size leaves no room for the
    frame or the glass."""
    c = opening.centre
    if kind == "window":
        w, h = size.width, size.height
        z0 = _round_in(opening.sill + (opening.head - opening.sill - h) / 2)
        outer = (_round_in(c - w / 2), _round_in(c + w / 2), z0, _round_in(z0 + h))
        f = WINDOW_FRAME_FACE
        glass = (outer[0] + f, outer[1] - f, outer[2] + f, outer[3] - f)
        if glass[1] <= glass[0] or glass[3] <= glass[2]:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"This window: a {w:g} x {h:g} in unit leaves no glass inside "
                f"its {f:g} in frame; make it larger.",
                input="width_mm",
            )
        mid = (WINDOW_FRAME_DEPTH - GLASS) / 2
        material = _frame_material(size, kind)
        return [
            UnitBody("frame", outer, glass, 0.0, WINDOW_FRAME_DEPTH, material, True),
            UnitBody(
                "glazing", glass, None, mid, mid + GLASS, _INFILL_MATERIAL[kind], False
            ),
        ]
    w = size.width + 2 * DOOR_JAMB
    h = size.height + DOOR_JAMB + DOOR_THRESHOLD
    if w > opening.width or h > opening.head:
        wide = w > opening.width
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"This door: its frame ({w:g} x {h:g} in round a {size.width:g} x "
            f"{size.height:g} in slab) does not fit its {opening.width:g} x "
            f"{opening.head:g} in rough opening; widen the allowances.",
            input="ro_width_allowance_mm" if wide else "ro_height_allowance_mm",
        )
    outer = (_round_in(c - w / 2), _round_in(c + w / 2), 0.0, h)
    slab = (
        outer[0] + DOOR_JAMB,
        outer[1] - DOOR_JAMB,
        DOOR_THRESHOLD,
        DOOR_THRESHOLD + size.height,
    )
    return [
        UnitBody(
            "frame",
            outer,
            slab,
            0.0,
            wall.thickness,
            _frame_material(size, kind),
            True,
        ),
        UnitBody("slab", slab, None, 0.0, DOOR_SLAB, _INFILL_MATERIAL[kind], False),
    ]


def _profile(size: UnitSize) -> str:
    """The cut list's size: the call size, or a custom unit's inches."""
    if size.size is not None:
        return size.size.code
    return f"{size.width:g} x {size.height:g} in"


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


PlaneRef = DatumPlaneRef | FeatureRef
Direction = Literal["normal", "reverse"]


def _unit_plane(
    inputs: ExpandInputs,
    face: FacePlane,
    v: float,
    index: int,
    turned: FeatureRef | None,
) -> tuple[list[Member], PlaneRef, Direction]:
    """The plane *v* in from the framing's exterior face, parallel to it, the
    datum members that make it, and the extrude direction that runs into
    the wall from it. An axis wall's plane is the ``XZ``/``YZ`` datum offset
    to it, exact; any other wall's is *turned* (the plane through Z at the
    face's angle, emitted once) offset along its normal, which is outward."""
    inward = face.frame.across
    if face.axis == "x":  # XZ: normal -Y
        dot = -inward[1]
    elif face.axis == "y":  # YZ: normal +X
        dot = inward[0]
    else:
        dot = -1.0
    offset = face.offset_mm + _mm(v) * dot + 0.0
    direction: Direction = "normal" if dot > 0 else "reverse"
    name = f"v/{v:g}"
    if face.axis != "angle":
        base = "XZ" if face.axis == "x" else "YZ"
        if offset == 0.0:
            return [], DatumPlaneRef(kind="datum_plane", plane=base), direction
        datum = DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(base=base, offset_mm=offset),
        )
    else:
        if turned is None:
            raise RuntimeError("an angled wall's unit plane needs its turned plane")
        datum = DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetFromParams(
                kind="offset_from", base=turned, offset_mm=offset
            ),
        )
    return (
        [Member("unit_plane", index, datum, name=name)],
        inputs.ref("unit_plane", index, name),
        direction,
    )


def _rect_loop(face: FacePlane, rect: Rect) -> list[Point2D]:
    u0, u1, z0, z1 = rect
    corners = ((u0, z0), (u1, z0), (u1, z1), (u0, z1))
    return [face.sketch_point(u, z) for u, z in corners]


def unit_members(
    inputs: ExpandInputs,
    kind: Literal["door", "window"],
    wall: WallSpec,
    opening: Opening,
    size: UnitSize,
) -> Iterator[Member]:
    """The unit's planes, sketches and two bodies, each a new body carrying
    the unit's metadata: the frame counted, the glazing or slab not."""
    face = face_plane(wall)
    bodies = unit_bodies(kind, wall, opening, size)
    turned: FeatureRef | None = None
    planes = 0
    if face.axis == "angle":
        yield Member(
            "unit_plane",
            planes,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumAngleParams(
                    kind="angle",
                    line=DatumOriginAxisRef(kind="origin_axis", axis="Z"),
                    reference=DatumPlaneRef(kind="datum_plane", plane="YZ"),
                    angle_deg=face.angle_deg,
                ),
            ),
            name="turned",
        )
        turned = inputs.ref("unit_plane", planes, "turned")
        planes += 1
    made: dict[float, tuple[PlaneRef, Direction]] = {}
    key = None if size.size is None else size.size.key
    for section, body in enumerate(bodies):
        if body.v0 not in made:
            datums, ref, direction = _unit_plane(inputs, face, body.v0, planes, turned)
            yield from datums
            planes += len(datums)
            made[body.v0] = (ref, direction)
        ref, direction = made[body.v0]
        loops = [_rect_loop(face, body.outer)]
        if body.hole is not None:
            loops.append(_rect_loop(face, body.hole))
        yield Member(
            "unit_section",
            section,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=ref, entities=list(loops_entities(loops)), constraints=[]
                ),
            ),
            name=body.role,
        )
        yield Member(
            body.role,
            0,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=inputs.ref("unit_section", section, body.role),
                    distance_mm=_mm(body.v1 - body.v0),
                    operation="add",
                    direction=direction,
                    merge=False,
                ),
            ),
            MemberMetadata(
                profile=_profile(size),
                material=body.material,
                unit=OpeningUnitPart(kind=kind, key=key, counted=body.counted),
            ),
        )


def _size_choice(kind: Literal["door", "window"]) -> ChoiceInput:
    door = kind == "door"
    return ChoiceInput(
        kind="choice",
        name="size",
        label="Size",
        description=f"The {kind}'s call size: feet and inches of the width, "
        "then the height (3040 is 3'0\" x 4'0\""
        + ("; a door's is its slab's" if door else "")
        + "). It sets the unit and the rough opening; Custom uses the typed "
        "size and allowances.",
        options=[
            *(
                ChoiceOption(value=u.key, label=f"{u.code} ({u.label})")
                for u in catalogue(kind).values()
            ),
            ChoiceOption(value=CUSTOM_SIZE, label="Custom (type the size)"),
        ],
        default="door_3068" if door else "window_3040",
    )


#: 1.3.0's labels for the typed size, which only Custom reads.
_CUSTOM_LABELS = {
    "width_mm": "Custom width",
    "height_mm": "Custom height",
    "ro_width_allowance_mm": "Custom RO width allowance",
    "ro_height_allowance_mm": "Custom RO height allowance",
}


def _with_unit(
    manifest: PluginManifest, kind: Literal["door", "window"]
) -> PluginManifest:
    """*manifest* (1.2.0) at 1.3.0: a Size pick after the distance, the
    typed size and allowances kept for Custom, and Unit (drawn or not) last."""
    what = manifest.title.lower()
    infill = "slab" if kind == "door" else "glass"
    second = "slab" if kind == "door" else "glazing"
    inputs: list[PluginInput] = []
    for item in manifest.inputs:
        if item.name in _CUSTOM_LABELS:
            item = item.model_copy(
                update={
                    "label": _CUSTOM_LABELS[item.name],
                    "description": f"{item.description} Read when Size is Custom.",
                    # Hidden while a call size is picked (OPENING-UNITS).
                    "superseded_by": "size",
                    "superseded_unless": CUSTOM_SIZE,
                }
            )
        inputs.append(item)
        if item.name == "offset_mm":
            inputs.append(_size_choice(kind))
    inputs.append(
        ChoiceInput(
            kind="choice",
            name="draw_unit",
            label="Unit",
            description=f"Draw the {what} unit (frame and {infill}), listed and "
            "priced as one item, or frame the rough opening only.",
            options=[
                ChoiceOption(value="draw", label=f"Frame and {infill}"),
                ChoiceOption(value="none", label="Rough opening only"),
            ],
            default="draw",
        )
    )
    return manifest.model_copy(
        update={
            "version": "1.3.0",
            "inputs": inputs,
            "description": manifest.description
            + f" It is picked by call size and drawn as its frame and {infill}.",
            "members": [
                PluginMemberRole(role="unit_plane", title="Plane"),
                PluginMemberRole(role="unit_section", title="Section"),
                PluginMemberRole(
                    role="frame",
                    title="Frame",
                    description=f"The {what} unit's frame: the unit is listed "
                    "and priced on it.",
                ),
                PluginMemberRole(
                    role=second,
                    title=second.capitalize(),
                    description=f"The {what}'s {infill}, part of the unit.",
                ),
            ],
        }
    )


def _unit_expander(kind: Literal["door", "window"], title: str) -> Expander:
    def expand(inputs: ExpandInputs) -> Iterator[Member]:
        wall, named = _host(inputs, True)
        opening = Opening.from_inputs(kind, f"This {title}", inputs, wall)
        frame_opening(wall, opening, named)
        size = unit_size(kind, inputs)
        if inputs.choice("draw_unit") == "none":
            return
        yield from unit_members(inputs, kind, wall, opening, size)

    return expand


WINDOW_MANIFEST_V1_3 = _with_unit(WINDOW_MANIFEST_V1_2, "window")
DOOR_MANIFEST_V1_3 = _with_unit(DOOR_MANIFEST_V1_2, "door")

WINDOW_V1_3 = Plugin(
    WINDOW_MANIFEST_V1_3, _unit_expander("window", "window"), settle=_settle
)
DOOR_V1_3 = Plugin(DOOR_MANIFEST_V1_3, _unit_expander("door", "door"), settle=_settle)


# --- 1.4.0: a header the wall's thickness (HEADER-PLIES) ---------------------------


def _with_header_build(manifest: PluginManifest) -> PluginManifest:
    """*manifest* (1.3.0) at 1.4.0: Header build after the header's size. A
    built-up header is the wall's thickness (IRC R602.7; Table R602.7(1)
    sizes headers as plies, "3-2x8"): by default as many plies as fill the
    wall with 1/2 in spacers, two in a 2x4 wall and three in a 2x6
    (``loft_plugins.builtin.wall.header_plies``); or two plies with foam
    between, an insulated header."""
    inputs: list[PluginInput] = []
    for item in manifest.inputs:
        if item.name != "header_profile":
            inputs.append(item)
            continue
        inputs.append(
            item.model_copy(
                update={
                    "description": "Plies on edge over the jacks; size their "
                    "depth by the span."
                }
            )
        )
        inputs.append(
            ChoiceInput(
                kind="choice",
                name="header_build",
                label="Header build",
                description="Fill the wall: plies spaced to the wall's "
                "thickness (two in a 2x4 wall and three in a 2x6, with 1/2 in "
                "spacers; three in a 2x8, with wider gaps). Two "
                "plies: one at each face, rigid foam between (an insulated "
                "header).",
                options=[
                    ChoiceOption(value="fill", label="Fill the wall"),
                    ChoiceOption(value="two_ply", label="Two plies, foam between"),
                ],
                default="fill",
            )
        )
    return manifest.model_copy(
        update={
            "version": "1.4.0",
            "inputs": inputs,
            "description": manifest.description
            + " Its header fills the wall's thickness.",
        }
    )


WINDOW_MANIFEST_V1_4 = _with_header_build(WINDOW_MANIFEST_V1_3)
DOOR_MANIFEST_V1_4 = _with_header_build(DOOR_MANIFEST_V1_3)

WINDOW_V1_4 = Plugin(
    WINDOW_MANIFEST_V1_4, _unit_expander("window", "window"), settle=_settle
)
DOOR_V1_4 = Plugin(DOOR_MANIFEST_V1_4, _unit_expander("door", "door"), settle=_settle)
