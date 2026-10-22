"""Roof: a gable or hip roof of rafters on its bearing walls (ROOF, ROOF-HIP,
RESEARCH §23).

What Chief Architect's roof framing and SketchUp's Medeek Truss (rafter
roofs) build for a stick-framed gable: a ridge board along the building,
common rafters at a spacing in pairs, each with a plumb cut at the ridge, a
birdsmouth on the wall plate and a plumb-cut tail past the wall.
``docs/reference-parts/buildings.md`` B2's roof is the default exactly.

Two released versions stay registered: 1.0.0 (the gable, below) and 1.1.0,
which adds a Style choice, Gable (1.0.0's expansion exactly) or Hip (hips,
hip jacks and king commons; the 1.1.0 section). Every stored roof expands
by the version it pins.

This is a FRAMING MODEL with a cut list, not a structural design: no span
table, load or code check is implied (buildings.md). Trusses, valleys
(ROOF-VALLEY), rafter ties, collar ties and a rake (gable) overhang are
later rungs.

**Frame.** World X runs along the ridge, Y across the span, Z up. The two
bearing walls' outer faces are Y 0 and Y ``span``; their top plates' tops
are at ``plate_height`` and they are ``plate_width`` deep (a 2x4 wall: 3.5).
The roof runs X 0..``length``. That is where B2's walls stand; bearing on
picked wall features waits for STUD-WALL (BACKLOG note ROOF-BEARING-WALLS).

**Members.** Each rafter is ONE sketched side profile on a ``YZ`` plane at
its X (an offset datum shared by the pair at that X, or the origin ``YZ``
plane at X 0), extruded its thickness along +X as a new body
(``merge: false``). The ridge is its section on the ``YZ`` plane extruded
the roof's length. Members never fuse, so the cut list measures each one.

**Decisions** (framing practice, Chief Architect and Medeek; RESEARCH §23):

* Pitch is rise per 12 of run, chosen from 1/12 to 24/12 (a choice input:
  the form shows "6/12"; BACKLOG note PLUGIN-PITCH-INPUT).
* Rafter layout is the wall layout: centres from X 0 at half a thickness,
  then every spacing, an end rafter flush at the far end, and a layout
  rafter that would overlap it dropped. Each centre carries a pair.
* The overhang is HORIZONTAL, from the wall's outer face to the tail's
  plumb cut (as Chief Architect and the framing square measure it); 0 gives
  a rafter cut flush at the wall line, with no tail.
* The birdsmouth's heel (its plumb cut) is on the wall's outer face. The
  seat takes the full plate unless the heel would pass 1/3 of the rafter's
  depth; then the seat shortens (from the inside) to keep the heel at 1/3.
* The ridge board's top is flush with the rafters' top edge at its face, so
  the sheathing plane touches it. It must be at least as deep as the
  rafters' plumb cut (IRC R802.3), or the roof is refused.
* A rafter's LINE LENGTH, plumb cut to plumb cut, is the run (wall face to
  ridge face, plus the overhang) over cos(pitch); the cut list reports its
  OVERALL length from the body (long point to long point, as a SolidWorks
  weldment cut list does), which is the line length plus depth x rise/12.

Inputs are millimetres on the wire (names end ``_mm``) and inches inside,
rounded to 1e-9 in exactly as ``loft.deck`` does.
"""

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetParams,
    DatumPlaneRef,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import MM_PER_INCH, LumberProfile, LumberProfileKey
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    LengthInput,
    MaterialInput,
    MemberMetadata,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError, lumber_options
from loft_plugins.builtin.deck import joist_centres

#: Rounding of an input's inch value (as ``loft.deck``).
_INCH_DIGITS = 9
#: The heel may be at most this fraction of the rafter's depth.
HEEL_LIMIT = 1.0 / 3.0
#: Pitches offered, as rise per 12 of run.
PITCHES = tuple(range(1, 25))

_SPF: MaterialKey = "spf_lumber"
_RAFTERS: list[LumberProfileKey] = ["us_2x4", "us_2x6", "us_2x8", "us_2x10", "us_2x12"]
_RIDGES: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def inches(name: str, inputs: ExpandInputs) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _INCH_DIGITS)


def _length(
    name: str, label: str, default_in: float, low_in: float, high_in: float, text: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=text,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
    )


def material_input(name: str, label: str) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default=_SPF,
        description="Library material of these members (their mass and cut list).",
    )


def pitch_value(rise: int) -> str:
    """The choice value of a rise per 12 (``6`` -> ``"rise_6"``)."""
    return f"rise_{rise}"


MANIFEST_V1 = PluginManifest(
    id="loft.roof",
    version="1.0.0",
    title="Roof",
    description="A gable of common rafters with a birdsmouth on each wall and "
    "a ridge board, with a cut list (Chief Architect, Medeek Truss).",
    inputs=[
        _length(
            "span_mm",
            "Span",
            120.0,
            48.0,
            480.0,
            "Across the ridge (Y), outside face to outside face of the two "
            "bearing walls.",
        ),
        _length(
            "length_mm",
            "Length",
            144.0,
            24.0,
            720.0,
            "Along the ridge (X), outside of the end rafters.",
        ),
        _length(
            "plate_height_mm",
            "Plate height",
            97.125,
            12.0,
            240.0,
            "Top of the bearing walls' top plate above Z 0.",
        ),
        _length(
            "plate_width_mm",
            "Plate width",
            3.5,
            1.5,
            11.25,
            "Depth of the bearing walls (a 2x4 wall: 3.5 in): the most the "
            "birdsmouth seat takes.",
        ),
        ChoiceInput(
            kind="choice",
            name="pitch",
            label="Pitch",
            description="Rise per 12 of run.",
            options=[
                ChoiceOption(value=pitch_value(r), label=f"{r}/12") for r in PITCHES
            ],
            default=pitch_value(6),
        ),
        _length(
            "spacing_mm",
            "Rafter spacing",
            24.0,
            12.0,
            48.0,
            "On centres, from the first end rafter; both end rafters sit flush.",
        ),
        _length(
            "overhang_mm",
            "Eave overhang",
            12.0,
            0.0,
            36.0,
            "Level, from the wall's outside face to the tail's plumb cut.",
        ),
        ChoiceInput(
            kind="choice",
            name="rafter_profile",
            label="Rafters",
            description="Rafter size.",
            options=lumber_options(_RAFTERS),
            default="us_2x6",
        ),
        ChoiceInput(
            kind="choice",
            name="ridge_profile",
            label="Ridge board",
            description="At least as deep as the rafters' plumb cut.",
            options=lumber_options(_RIDGES),
            default="us_2x8",
        ),
        material_input("rafter_material", "Rafter material"),
        material_input("ridge_material", "Ridge material"),
    ],
    members=[
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="rafter", title="Rafter"),
        PluginMemberRole(role="ridge", title="Ridge"),
    ],
)


# --- Rafter geometry (pure, inches) ----------------------------------------------


@dataclass(frozen=True)
class Rafter:
    """One common rafter of a gable, in the front rafter's (Y, Z) frame.

    ``rise`` is per 12 of run. The bottom edge is the line through the seat's
    inner corner ``(seat, plate_height)`` at the pitch; the top edge is the
    plumb depth above it.
    """

    rise: float
    depth: float
    plate_height: float
    plate_width: float
    ridge_face: float  # Y of the ridge board's face
    overhang: float

    @property
    def slope(self) -> float:
        return self.rise / 12.0

    @property
    def plumb_depth(self) -> float:
        """The rafter's depth measured plumb: the height of a plumb cut."""
        return self.depth * math.hypot(12.0, self.rise) / 12.0

    @property
    def seat(self) -> float:
        """The birdsmouth seat: the full plate, unless the heel would pass
        1/3 of the depth."""
        return min(self.plate_width, self.depth * HEEL_LIMIT / self.slope)

    @property
    def heel(self) -> float:
        """The birdsmouth's plumb cut, on the wall's outside face."""
        return self.seat * self.slope

    def bottom(self, y: float) -> float:
        return self.plate_height + (y - self.seat) * self.slope

    @property
    def run(self) -> float:
        """Level run between the plumb cuts: overhang plus wall to ridge."""
        return self.overhang + self.ridge_face

    @property
    def line_length(self) -> float:
        """Along the rafter, plumb cut to plumb cut."""
        return self.run * math.hypot(12.0, self.rise) / 12.0

    @property
    def overall_length(self) -> float:
        """Long point to long point along the rafter (the cut list's length)."""
        return self.line_length + self.depth * self.slope

    @property
    def top_at_ridge(self) -> float:
        return self.bottom(self.ridge_face) + self.plumb_depth

    def profile(self) -> list[tuple[float, float]]:
        """The side profile's corners (Y, Z), counter-clockwise from the tail's
        bottom: tail plumb cut, birdsmouth (heel, seat), ridge plumb cut."""
        p, d = self.plate_height, self.plumb_depth
        r = self.ridge_face
        ridge = [(r, self.bottom(r)), (r, self.bottom(r) + d)]
        if self.overhang > 0.0:
            tail = -self.overhang
            return [
                (tail, self.bottom(tail)),
                (0.0, p - self.heel),
                (0.0, p),
                (self.seat, p),
                *ridge,
                (tail, self.bottom(tail) + d),
            ]
        return [(0.0, p), (self.seat, p), *ridge, (0.0, self.bottom(0.0) + d)]


def rafter_for(
    rise: float,
    rafter: LumberProfile,
    ridge: LumberProfile,
    span: float,
    plate_height: float,
    plate_width: float,
    overhang: float,
) -> Rafter:
    return Rafter(
        rise=rise,
        depth=rafter.width_in,
        plate_height=plate_height,
        plate_width=plate_width,
        ridge_face=span / 2 - ridge.thickness_in / 2,
        overhang=overhang,
    )


# --- Emission ----------------------------------------------------------------------


def _polygon(points: list[tuple[float, float]]) -> list[SketchLine]:
    n = len(points)
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=Point2D(x=_mm(points[i][0]), y=_mm(points[i][1])),
            end=Point2D(x=_mm(points[(i + 1) % n][0]), y=_mm(points[(i + 1) % n][1])),
        )
        for i in range(n)
    ]


def unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    """1.0.0's gable (and 1.1.0's and 1.2.0's Style Gable): members by ordinal."""
    return gable(inputs, named=False)


def number_name(value: float) -> str:
    """A length (in) as a name segment: rounded to 1e-9 in, printed to 9
    places without trailing zeros (``58.5``, ``-120``)."""
    return f"{round(value, _INCH_DIGITS) + 0.0:.{_INCH_DIGITS}f}".rstrip("0").rstrip(
        "."
    )


def layout_slots(count: int) -> list[str]:
    """The 1.3.0 names of :func:`~loft_plugins.builtin.deck.joist_centres`'
    centres, in order: ``start``, ``slot/n`` for the layout centre at ``n x
    spacing`` from the start, and ``end`` (the flush far one). A slot's name
    depends on the spacing alone, so lengthening the roof renames none."""
    return ["start", *(f"slot/{n}" for n in range(1, count - 1)), "end"][:count]


#: The gable's ridge, and its section, in 1.3.0: the board between the front
#: and back planes (a hip roof's ridges are named by their planes too).
GABLE_RIDGE = "back/front"


@dataclass(frozen=True)
class GablePlace:
    """Where a gable stands (BUILDING-OUTLINE): its bearing walls' outer faces
    from ``(x0, y0)``, the ridge along world X (the walls at ``y0`` and ``y0 +
    span``) or along Y (the walls at ``x0`` and ``x0 + span``). The default
    is 1.0.0's frame: X 0..length, Y 0..span."""

    x0: float = 0.0
    y0: float = 0.0
    along_x: bool = True


def gable(inputs: ExpandInputs, named: bool) -> Iterator[Member]:
    """The gable on its typed bearing. *named* (1.3.0, ROOF-MEMBER-RENUMBER)
    gives every member a stable name: a rafter by its side and layout slot
    (``front/slot/3``), its section after it, a plane by its X (``yz/71.25``),
    the ridge by the planes it divides. Same members, order and geometry as
    unnamed."""
    return gable_on(
        inputs,
        named,
        inches("span_mm", inputs),
        inches("length_mm", inputs),
        inches("plate_height_mm", inputs),
        inches("plate_width_mm", inputs),
        GablePlace(),
    )


def gable_on(
    inputs: ExpandInputs,
    named: bool,
    span: float,
    length: float,
    plate_height: float,
    plate_width: float,
    place: GablePlace,
) -> Iterator[Member]:
    """The gable on a bearing given in inches, at *place*. At the default
    place it is :func:`gable`'s every member, byte for byte. Along Y the
    rafters stand on ``XZ`` planes (normal -Y) extruded toward +Y, the sides
    are ``left`` and ``right`` and the planes ``xz/<y>``."""
    pitch = inputs.choice("pitch")
    rises = {pitch_value(r): r for r in PITCHES}
    if pitch not in rises:
        raise unsupported(f"{pitch!r} is not a pitch", "pitch")
    rise = rises[pitch]
    spacing = inches("spacing_mm", inputs)
    overhang = inches("overhang_mm", inputs)
    rafter_p = inputs.lumber("rafter_profile")
    ridge_p = inputs.lumber("ridge_profile")
    rafter_mat = inputs.material("rafter_material")
    ridge_mat = inputs.material("ridge_material")

    r = rafter_for(rise, rafter_p, ridge_p, span, plate_height, plate_width, overhang)
    # The bounds keep the ridge clear of the walls: the smallest span puts its
    # face 23.25 in in, past the widest plate (11.25).
    if ridge_p.width_in < r.plumb_depth:
        raise unsupported(
            f"The ridge board must be at least as deep as the rafters' plumb cut "
            f"({r.plumb_depth:.3f} in): choose a deeper ridge or a shallower "
            "rafter or pitch.",
            "ridge_profile",
        )

    # Along the ridge from `start`, across it from `across` (world, in).
    start, across = (place.x0, place.y0) if place.along_x else (place.y0, place.x0)
    base, axis = ("YZ", "yz") if place.along_x else ("XZ", "xz")
    sides = ("front", "back") if place.along_x else ("left", "right")
    ridge_key = GABLE_RIDGE if place.along_x else "left/right"
    direction: Literal["normal", "reverse"] = "normal" if place.along_x else "reverse"

    def shifted(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if across == 0.0:
            return points
        return [(across + y, z) for y, z in points]

    def offset(at: float) -> float:
        # YZ's normal is +X; XZ's is -Y, so a plane at Y y is offset -y.
        return _mm(at) if place.along_x else -_mm(at) + 0.0

    front = r.profile()
    back = [(span - y, z) for y, z in reversed(front)]
    t = rafter_p.thickness_in
    rafter_meta = MemberMetadata(profile=rafter_p.name, material=rafter_mat)

    planes = 0
    sections = 0
    rafters = 0
    first_plane: DatumPlaneRef | FeatureRef | None = None
    centres = joist_centres(length, spacing, t)
    slots = layout_slots(len(centres)) if named else [None] * len(centres)
    for centre, slot in zip(centres, slots, strict=True):
        x0 = centre - t / 2
        at = x0 if start == 0.0 else start + x0
        plane: DatumPlaneRef | FeatureRef
        if at == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane=base)
        else:
            plane_name = None if slot is None else f"{axis}/{number_name(at)}"
            yield Member(
                "plane",
                planes,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(base=base, offset_mm=offset(at)),
                ),
                name=plane_name,
            )
            plane = inputs.ref("plane", planes, plane_name)
            planes += 1
        if first_plane is None:
            first_plane = plane
        for side, outline in ((sides[0], front), (sides[1], back)):
            rafter_name = None if slot is None else f"{side}/{slot}"
            section_name = None if slot is None else f"rafter/{rafter_name}"
            yield Member(
                "section",
                sections,
                SketchFeature(
                    type="sketch",
                    version=1,
                    params=SketchParamsV1(
                        plane=plane,
                        entities=list(_polygon(shifted(outline))),
                        constraints=[],
                    ),
                ),
                name=section_name,
            )
            yield Member(
                "rafter",
                rafters,
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=inputs.ref("section", sections, section_name),
                        distance_mm=_mm(t),
                        operation="add",
                        merge=False,
                        direction=direction,
                    ),
                ),
                rafter_meta,
                name=rafter_name,
            )
            sections += 1
            rafters += 1

    # The ridge board: its section on the first rafters' plane (the YZ
    # plane in 1.0.0's frame), run the roof's length.
    half = ridge_p.thickness_in / 2
    top = r.top_at_ridge
    bottom = top - ridge_p.width_in
    centre_y = span / 2
    ridge_name = ridge_key if named else None
    ridge_section = f"ridge/{ridge_key}" if named else None
    ridge_plane = (
        DatumPlaneRef(kind="datum_plane", plane=base)
        if first_plane is None
        else first_plane
    )
    yield Member(
        "section",
        sections,
        SketchFeature(
            type="sketch",
            version=1,
            params=SketchParamsV1(
                plane=ridge_plane,
                entities=list(
                    _polygon(
                        shifted(
                            [
                                (centre_y - half, bottom),
                                (centre_y + half, bottom),
                                (centre_y + half, top),
                                (centre_y - half, top),
                            ]
                        )
                    )
                ),
                constraints=[],
            ),
        ),
        name=ridge_section,
    )
    yield Member(
        "ridge",
        0,
        ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(
                profile=inputs.ref("section", sections, ridge_section),
                distance_mm=_mm(length),
                operation="add",
                merge=False,
                direction=direction,
            ),
        ),
        MemberMetadata(profile=ridge_p.name, material=ridge_mat),
        name=ridge_name,
    )


#: 1.0.0 numbers planes, sections and rafters in layout order, so a longer
#: roof hands the end rafters' numbers to new layout rafters, and a shorter
#: or re-spaced one moves every number (ROOF-MEMBER-RENUMBER). One ridge.
_RENUMBERED_V1 = frozenset({"plane", "section", "rafter"})

ROOF_V1 = Plugin(MANIFEST_V1, expand, renumbered_roles=_RENUMBERED_V1)


# --- 1.1.0: Style, Gable or Hip (ROOF-HIP) -----------------------------------------
#
# 1.1.0 adds a Style choice (Chief Architect's roof style, Medeek's rafter roof
# type) and a hip profile. Gable is 1.0.0's expansion member for member (the
# same expander), so a Gable at 1.1.0 is B2's roof exactly; 1.0.0 stays
# registered and every stored 1.0.0 roof expands as it always did.
#
# Hip, on the same typed bearing (buildings.md "Hip and valley conventions",
# B3): every wall is an eave carrying a plane of the one pitch; a ridge
# L - W + one common thickness; side commons from ridge end to ridge end on
# the spacing; a king common on each end wall; DROPPED hips from each plate
# corner to the inside corner of the ridge-end and king commons; hip jacks
# laid out on the spacing outward from those commons, each cheek-cut to the
# hip's side face. Every member is built from base features only:
#
# * a common is its side profile (1.0.0's) on a vertical datum, extruded its
#   thickness;
# * a JACK is its side profile, run past the hip, INTERSECTED (a boolean) with
#   a vertical prism of its plan outline, one edge of which is the hip's side
#   face: the cheek is a plumb cut 45 deg in plan, which is the 45 deg saw
#   bevel on the plumb line a framer cuts (it reads 48.19 deg off square on
#   the top edge at 6/12, buildings.md);
# * a HIP is its side profile on a MIDPLANE datum through its centreline
#   (between the two walls' planes at its corner), extruded symmetric its
#   thickness, intersected with the prism of the box its double cheeks bound
#   (the fascia corner and the inside corner at the ridge), less the seat:
#   everything below the plate inside both walls' outer faces (a double heel
#   on the corner);
# * a cutter's outline, and a trimmed member's uncut profile, run PAST
#   beyond every face they do not make, so no cutter face coincides with a
#   member's (the float-coincidence class DECK found).
#
# ROOF-VALLEY seam: the hip roof is built from a Footprint's eaves and
# corners. 1.1.0's footprint is the typed rectangle; 1.2.0 takes the loop of
# the picked walls' outer faces, whose reflex corners carry valleys.

STYLE_GABLE = "gable"
STYLE_HIP = "hip"
#: The smallest framed tail (in): an overhang is 0 (no tail) or at least
#: this. Below it an edge falls under the kernel's tolerance (ROOF-OVERHANG-MIN).
MIN_OVERHANG_IN = 1.0 / 16.0
#: How far (in) a trimmed member's uncut profile, and a cutter's outline, run
#: past every face they do not make.
PAST = 2.0
#: How far (in) a cutter prism rises above the ridge's top.
HEADROOM = 12.0
_ROOT2 = math.sqrt(2.0)
HIP_PROFILES: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]


def _v1_input(name: str) -> PluginInput:
    return next(item for item in MANIFEST_V1.inputs if item.name == name)


def _overhang_v1_1() -> PluginInput:
    return _v1_input("overhang_mm").model_copy(
        update={
            "description": "Level, from the wall's outside face to the tail's "
            "plumb cut: 0 (cut flush at the wall) or at least 1/16 in."
        }
    )


MANIFEST_V1_1 = PluginManifest(
    id="loft.roof",
    version="1.1.0",
    title="Roof",
    description="A gable or hip roof of rafters with a birdsmouth on each wall, "
    "a ridge board and, for a hip, hips and hip jacks, with a cut list (Chief "
    "Architect, Medeek Truss).",
    inputs=[
        ChoiceInput(
            kind="choice",
            name="style",
            label="Style",
            description="Gable: two planes on the long walls, gable ends. Hip: "
            "every wall an eave, the planes meeting on hips at the corners.",
            options=[
                ChoiceOption(value=STYLE_GABLE, label="Gable"),
                ChoiceOption(value=STYLE_HIP, label="Hip"),
            ],
            default=STYLE_GABLE,
        ),
        _v1_input("span_mm"),
        _v1_input("length_mm"),
        _v1_input("plate_height_mm"),
        _v1_input("plate_width_mm"),
        _v1_input("pitch"),
        _v1_input("spacing_mm"),
        _overhang_v1_1(),
        _v1_input("rafter_profile"),
        _v1_input("ridge_profile"),
        ChoiceInput(
            kind="choice",
            name="hip_profile",
            label="Hips",
            description="Hip size (Hip style): at least as deep as the commons' "
            "plumb cut. Hips are dropped, not backed.",
            options=lumber_options(HIP_PROFILES),
            default="us_2x8",
        ),
        _v1_input("rafter_material"),
        material_input("ridge_material", "Ridge and hip material"),
    ],
    members=[
        PluginMemberRole(role="plane", title="Plane"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="rafter", title="Rafter"),
        PluginMemberRole(role="common", title="Common"),
        PluginMemberRole(role="jack", title="Jack"),
        PluginMemberRole(role="hip", title="Hip"),
        PluginMemberRole(role="ridge", title="Ridge"),
        PluginMemberRole(role="cutter", title="Cutter"),
        PluginMemberRole(role="trim", title="Trim"),
    ],
)


# --- The footprint (the ROOF-VALLEY seam) ------------------------------------------

Vec2 = tuple[float, float]


@dataclass(frozen=True)
class Eave:
    """One eave wall: its outer face from ``origin`` along ``along`` for
    ``length``, the roof plane rising toward ``inward`` (world unit axes).
    A member on it is placed by ``a`` (along, from the origin) and ``d``
    (inward from the face)."""

    origin: Vec2
    along: Vec2
    inward: Vec2
    length: float

    def world(self, a: float, d: float) -> Vec2:
        return (
            self.origin[0] + self.along[0] * a + self.inward[0] * d,
            self.origin[1] + self.along[1] * a + self.inward[1] * d,
        )

    @property
    def along_x(self) -> bool:
        return self.along[0] != 0.0


@dataclass(frozen=True)
class Corner:
    """A convex plate corner: its hip rises from ``point`` along
    ``direction`` (each component +-1: 45 deg in plan)."""

    point: Vec2
    direction: tuple[int, int]


@dataclass(frozen=True)
class Footprint:
    """The bearing walls' outer faces. 1.1.0: the typed rectangle X 0..length,
    Y 0..span. ROOF-VALLEY replaces it with the loop of picked walls."""

    length: float
    span: float

    def eaves(self) -> tuple[Eave, Eave, Eave, Eave]:
        """Front, back, left, right."""
        length, span = self.length, self.span
        return (
            Eave((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), length),
            Eave((0.0, span), (1.0, 0.0), (0.0, -1.0), length),
            Eave((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), span),
            Eave((length, 0.0), (0.0, 1.0), (-1.0, 0.0), span),
        )

    def corners(self) -> tuple[Corner, Corner, Corner, Corner]:
        """Front-left, front-right, back-left, back-right."""
        length, span = self.length, self.span
        return (
            Corner((0.0, 0.0), (1, 1)),
            Corner((length, 0.0), (-1, 1)),
            Corner((0.0, span), (1, -1)),
            Corner((length, span), (-1, -1)),
        )


# --- Hip geometry (pure, inches) ---------------------------------------------------


@dataclass(frozen=True)
class Hip:
    """A dropped hip in its vertical plane: ``s`` is the plan distance from
    the plate corner along its centreline (negative over the overhang)."""

    rise: float
    depth: float
    thickness: float
    plate_height: float
    height_above_plate: float  # the commons' HAP at the wall's face
    run: float  # along each wall, the corner to the ridge's inside corner
    overhang: float

    @property
    def slope(self) -> float:
        """Rise per unit of plan run along the hip (6/12: 0.354)."""
        return self.rise / 12.0 / _ROOT2

    @property
    def unit_length(self) -> float:
        """Along the hip per 12 of COMMON run (6/12: 18.00)."""
        return math.hypot(12.0 * _ROOT2, self.rise)

    @property
    def drop(self) -> float:
        """The top's centreline below the planes, so its edges lie in them
        (6/12, 2x8: 0.265)."""
        return self.thickness / 2 * self.slope

    @property
    def plumb_depth(self) -> float:
        return self.depth * self.unit_length / (12.0 * _ROOT2)

    def top(self, s: float) -> float:
        """The top's centreline at *s*."""
        return self.plate_height + self.height_above_plate - self.drop + self.slope * s

    @property
    def line_length(self) -> float:
        """Along the top's centreline, the tail's long point to the ridge's."""
        return (self.run + self.overhang) * self.unit_length / 12.0

    @property
    def heel(self) -> float:
        """The double heel's height on the centreline at the corner."""
        return self.plate_height - (self.top(0.0) - self.plumb_depth)

    def profile(self) -> list[tuple[float, float]]:
        """(s, z) counter-clockwise: the parallelogram, run PAST past both
        double cheeks (the plan cutter makes them)."""
        lo = -self.overhang * _ROOT2 - PAST
        hi = self.run * _ROOT2 + PAST
        d = self.plumb_depth
        return [
            (lo, self.top(lo) - d),
            (hi, self.top(hi) - d),
            (hi, self.top(hi)),
            (lo, self.top(lo)),
        ]


def jack_centres(
    half: float, spacing: float, thickness: float, hip_thickness: float, seat: float
) -> list[float]:
    """Hip jacks' centres from a corner along one wall, longest first: on
    the spacing outward from the ridge-end (or king) common at *half*, while
    the jack's short point on the hip still clears its seat. A shorter one
    would be a tail jack, a later rung (BACKLOG note ROOF-TAIL-JACKS)."""
    out: list[float] = []
    n = 1
    while True:
        centre = half - spacing * n
        if centre - thickness / 2 - hip_thickness / 2 * _ROOT2 < seat:
            return out
        out.append(centre)
        n += 1


def ccw(points: list[Vec2]) -> list[Vec2]:
    """*points* counter-clockwise (a mirrored outline is reversed)."""
    n = len(points)
    twice = sum(
        points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
        for i in range(n)
    )
    return points if twice > 0 else list(reversed(points))


# --- Emission ----------------------------------------------------------------------

PlaneRef = DatumPlaneRef | FeatureRef


class Builder:
    """One expansion's members: an index per role, datums emitted once.

    *named* (1.3.0, ROOF-MEMBER-RENUMBER): every member carries a stable name
    given by its caller, and each offset datum is named by its base, its
    offset rounded to 1e-9 in, and its flip (``yz/58.5``, ``xz/-120/flip``),
    so a datum's id never depends on what was emitted before it. Unnamed (1.1.0
    and 1.2.0), members are numbered per role in emission order."""

    def __init__(self, inputs: ExpandInputs, named: bool = False) -> None:
        self.inputs = inputs
        self.named = named
        self.members: list[Member] = []
        self._next: dict[str, int] = {}
        self._planes: dict[tuple[str, float, bool], PlaneRef] = {}

    def add(
        self,
        role: str,
        feature: DatumFeature | SketchFeature | ExtrudeFeature | BooleanFeature,
        metadata: MemberMetadata | None = None,
        name: str | None = None,
    ) -> FeatureRef:
        index = self._next.get(role, 0)
        self._next[role] = index + 1
        if not self.named:
            name = None
        elif name is None:
            raise ValueError(f"a named roof's {role} needs a name")
        self.members.append(Member(role, index, feature, metadata, name))
        return self.inputs.ref(role, index, name)

    def plane(
        self, base: Literal["XY", "XZ", "YZ"], offset_in: float, flip: bool = False
    ) -> PlaneRef:
        """An origin plane, or an offset datum (one per position: 1.3.0 shares
        it by the offset rounded to 1e-9 in, so one ulp never makes two)."""
        offset_in += 0.0  # never a -0.0 on the wire
        if offset_in == 0.0 and not flip:
            return DatumPlaneRef(kind="datum_plane", plane=base)
        key = (base, round(offset_in, _INCH_DIGITS) if self.named else offset_in, flip)
        if key not in self._planes:
            name = f"{base.lower()}/{number_name(offset_in)}" + (
                "/flip" if flip else ""
            )
            self._planes[key] = self.add(
                "plane",
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(
                        base=base, offset_mm=_mm(offset_in), flip=flip
                    ),
                ),
                name=name,
            )
        return self._planes[key]

    def sketch(
        self, plane: PlaneRef, outline: list[Vec2], name: str | None = None
    ) -> FeatureRef:
        """A closed polygon, in inches on the plane's (u, v)."""
        return self.add(
            "section",
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_polygon(ccw(outline))), constraints=[]
                ),
            ),
            name=name,
        )

    def extrude(
        self,
        role: str,
        profile: FeatureRef,
        distance_in: float,
        metadata: MemberMetadata | None = None,
        *,
        symmetric: bool = False,
        name: str | None = None,
    ) -> FeatureRef:
        return self.add(
            role,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=profile,
                    distance_mm=_mm(distance_in),
                    operation="add",
                    merge=False,
                    extent="symmetric" if symmetric else "one_side",
                ),
            ),
            metadata,
            name=name,
        )

    def prism(self, outline: list[Vec2], height_in: float) -> FeatureRef:
        """A cutter: *outline* on the XY plane, extruded up *height_in*."""
        section = self.sketch(DatumPlaneRef(kind="datum_plane", plane="XY"), outline)
        return self.extrude("cutter", section, height_in)

    def trim(
        self,
        target: FeatureRef,
        tool: FeatureRef,
        operation: Literal["intersect", "subtract"],
        name: str | None = None,
    ) -> None:
        self.add(
            "trim",
            BooleanFeature(
                type="boolean",
                version=1,
                params=BooleanParamsV1(operation=operation, target=target, tool=tool),
            ),
            name=name,
        )


def _side_plane(b: Builder, eave: Eave, centre: float, thickness: float) -> PlaneRef:
    """The datum a member centred at *centre* on *eave* is sketched on, the
    face it extrudes from: on a wall along X its low-X face (YZ, normal +X);
    along Y its high-Y face (XZ, whose normal is -Y)."""
    if eave.along_x:
        return b.plane("YZ", eave.origin[0] + centre - thickness / 2)
    return b.plane("XZ", -(eave.origin[1] + centre + thickness / 2))


def _side_outline(eave: Eave, profile: list[Vec2]) -> list[Vec2]:
    """A side profile's (d, z) on its datum's (u, v): u is the world
    coordinate across the wall (Y on a wall along X, else X), v is Z."""
    axis = 1 if eave.along_x else 0
    return [(eave.world(0.0, d)[axis], z) for d, z in profile]


def hip_sides(corner: Corner) -> tuple[float, bool]:
    """The XZ side of the hip's midplane datum: the plane at the corner's Y,
    flipped to a +Y normal for the hips along (-1, 1) and (1, -1), so that
    with the YZ side (+X normal) the bisector's normal (1, ny) / sqrt 2 is
    square to the hip in plan."""
    hx, hy = corner.direction
    return corner.point[1], -hx * hy > 0


def _hip_outline(corner: Corner, hip: Hip) -> list[Vec2]:
    """The hip's side profile on its midplane datum's (u, v), as geometry
    resolves that datum: origin the corner (on the two sides' line, nearest
    the world origin), normal (1, ny) / sqrt 2, x_dir +Z, y_dir normal x Z."""
    hx, hy = corner.direction
    ny = -hx * hy
    norm = math.sqrt(1.0 + ny * ny)
    v_axis = (ny / norm, -1.0 / norm)
    out: list[Vec2] = []
    for s, z in hip.profile():
        dx, dy = hx * s / _ROOT2, hy * s / _ROOT2
        out.append((z, dx * v_axis[0] + dy * v_axis[1]))
    return out


def _corner_box(corner: Corner, lo: float, hi: float) -> list[Vec2]:
    """The square from *lo* to *hi* along both walls from *corner*."""
    (cx, cy), (hx, hy) = corner.point, corner.direction
    return [
        (cx + hx * a, cy + hy * b) for a, b in ((lo, lo), (hi, lo), (hi, hi), (lo, hi))
    ]


def _along(eave: Eave, p: float, from_far_end: bool) -> float:
    """``a`` on *eave* of a point *p* along it from one of its corners."""
    return eave.length - p if from_far_end else p


def _hip_roof(inputs: ExpandInputs) -> list[Member]:
    span = inches("span_mm", inputs)
    length = inches("length_mm", inputs)
    plate_height = inches("plate_height_mm", inputs)
    plate_width = inches("plate_width_mm", inputs)
    rise = {pitch_value(r): r for r in PITCHES}[inputs.choice("pitch")]
    spacing = inches("spacing_mm", inputs)
    overhang = inches("overhang_mm", inputs)
    rafter_p = inputs.lumber("rafter_profile")
    ridge_p = inputs.lumber("ridge_profile")
    hip_p = inputs.lumber("hip_profile")
    rafter_meta = MemberMetadata(
        profile=rafter_p.name, material=inputs.material("rafter_material")
    )
    ridge_mat = inputs.material("ridge_material")

    common = rafter_for(
        rise, rafter_p, ridge_p, span, plate_height, plate_width, overhang
    )
    t = rafter_p.thickness_in
    if ridge_p.width_in < common.plumb_depth:
        raise unsupported(
            f"The ridge board must be at least as deep as the rafters' plumb cut "
            f"({common.plumb_depth:.3f} in): choose a deeper ridge or a shallower "
            "rafter or pitch.",
            "ridge_profile",
        )
    if hip_p.width_in < common.plumb_depth:
        raise unsupported(
            f"The hips must be at least as deep as the commons' plumb cut "
            f"({common.plumb_depth:.3f} in): choose a deeper hip.",
            "hip_profile",
        )
    if length - span < t - 1e-9:
        raise unsupported(
            f"A hip roof's length must be at least its span plus one rafter "
            f"thickness ({span + t:g} in), so the ridge-end commons do not "
            "overlap: lengthen it, or swap span and length.",
            "length_mm",
        )

    footprint = Footprint(length, span)
    front, back, left, right = footprint.eaves()
    half = span / 2
    run = half - t / 2  # each wall to the ridge's inside corner
    king = Rafter(
        rise=rise,
        depth=rafter_p.width_in,
        plate_height=plate_height,
        plate_width=plate_width,
        ridge_face=run,
        overhang=overhang,
    )
    height = common.top_at_ridge + HEADROOM
    b = Builder(inputs)

    # Side commons, front and back, from ridge end to ridge end.
    for offset in joist_centres(length - span + t, spacing, t):
        centre = run + offset
        plane = _side_plane(b, front, centre, t)
        for eave in (front, back):
            section = b.sketch(plane, _side_outline(eave, common.profile()))
            b.extrude("common", section, t, rafter_meta)
    # A king common on each end wall, to the ridge's end face.
    for eave in (left, right):
        plane = _side_plane(b, eave, half, t)
        section = b.sketch(plane, _side_outline(eave, king.profile()))
        b.extrude("common", section, t, rafter_meta)

    # Hip jacks: from each corner along both its walls, longest first. In a
    # wall's frame from that corner (p along, d inward) the hip's side face
    # is the line d = p - hs.
    hs = hip_p.thickness_in / 2 * _ROOT2
    for c in jack_centres(half, spacing, t, hip_p.thickness_in, common.seat):
        jack = Rafter(
            rise=rise,
            depth=rafter_p.width_in,
            plate_height=plate_height,
            plate_width=plate_width,
            ridge_face=c + t / 2 - hs + PAST,
            overhang=overhang,
        )
        lo, hi = c - t / 2 - PAST, c + t / 2 + PAST
        tail = -overhang - PAST
        plan = [(lo, tail), (hi, tail), (hi, hi - hs), (lo, lo - hs)]
        for eave in (front, back, left, right):
            for far in (False, True):
                plane = _side_plane(b, eave, _along(eave, c, far), t)
                section = b.sketch(plane, _side_outline(eave, jack.profile()))
                body = b.extrude("jack", section, t, rafter_meta)
                outline = [eave.world(_along(eave, p, far), d) for p, d in plan]
                b.trim(body, b.prism(outline, height), "intersect")

    # Hips: dropped, double cheeks at the fascia corner and the ridge, seat
    # level at the plate inside both walls (buildings.md).
    hip = Hip(
        rise=rise,
        depth=hip_p.width_in,
        thickness=hip_p.thickness_in,
        plate_height=plate_height,
        height_above_plate=common.plumb_depth - common.heel,
        run=run,
        overhang=overhang,
    )
    hip_meta = MemberMetadata(profile=hip_p.name, material=ridge_mat)
    seat_from = 0.0 if overhang > 0.0 else -PAST
    for corner in footprint.corners():
        y, flip = hip_sides(corner)
        mid = b.add(
            "plane",
            DatumFeature(
                type="datum",
                version=1,
                params=DatumMidplaneParams(
                    kind="midplane",
                    a=b.plane("YZ", corner.point[0]),
                    b=b.plane("XZ", -y, flip=flip),
                ),
            ),
        )
        section = b.sketch(mid, _hip_outline(corner, hip))
        body = b.extrude("hip", section, hip_p.thickness_in, hip_meta, symmetric=True)
        cheeks = b.prism(_corner_box(corner, -overhang, run), height)
        b.trim(body, cheeks, "intersect")
        seat = b.prism(_corner_box(corner, seat_from, run + PAST), plate_height)
        b.trim(body, seat, "subtract")

    # The ridge: between the ridge-end commons' outer faces.
    top = common.top_at_ridge
    plane = _side_plane(b, front, half, t)
    section = b.sketch(
        plane,
        [
            (half - ridge_p.thickness_in / 2, top - ridge_p.width_in),
            (half + ridge_p.thickness_in / 2, top - ridge_p.width_in),
            (half + ridge_p.thickness_in / 2, top),
            (half - ridge_p.thickness_in / 2, top),
        ],
    )
    b.extrude(
        "ridge",
        section,
        length - span + t,
        MemberMetadata(profile=ridge_p.name, material=ridge_mat),
    )
    return b.members


def expand_v1_1(inputs: ExpandInputs) -> Iterable[Member]:
    overhang = inches("overhang_mm", inputs)
    if 0.0 < overhang < MIN_OVERHANG_IN - 1e-9:
        raise unsupported(
            "The eave overhang must be 0 (cut flush at the wall) or at least 1/16 in.",
            "overhang_mm",
        )
    style = inputs.choice("style")
    if style == STYLE_HIP:
        return _hip_roof(inputs)
    if style != STYLE_GABLE:
        raise unsupported(f"{style!r} is not a roof style", "style")
    return list(expand(inputs))


#: 1.1.0 numbers in emission order: a longer roof, a new spacing or (Hip) a
#: pitch that frames another jack moves the numbers of planes, sections,
#: rafters, commons, jacks and their cutters and trims. Its four hips are
#: always the typed rectangle's corners in one order, and it has one ridge.
_RENUMBERED_V1_1 = frozenset(
    {"plane", "section", "rafter", "common", "jack", "cutter", "trim"}
)

ROOF_V1_1 = Plugin(MANIFEST_V1_1, expand_v1_1, renumbered_roles=_RENUMBERED_V1_1)
