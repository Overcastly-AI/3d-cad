"""Wall: a straight framed stud wall from a few inputs (STUD-WALL, RESEARCH §23).

What Chief Architect's framing and SketchUp's Medeek Wall build for a plain
wall: a bottom plate, studs on a layout from the wall's start with an end stud
flush at the far end, and a single or double top plate.
``docs/reference-parts/buildings.md`` B2's walls (no openings) are four of
these at the defaults.

This is a FRAMING MODEL with a cut list, not a structural design: no span,
load or code check is implied (buildings.md).

**Placement.** A wall is a line in plan: a start point, a direction (degrees
counterclockwise from +X, seen from above) and a length. The line is the
wall's EXTERIOR framing face; the framing lies to the right of the direction
by default, so walls drawn clockwise round a building have their exterior
outside, as Chief Architect and Revit expect walls to be drawn (Revit's
"Core Face: Exterior" location line). ``side`` flips the framing to the left
(Revit's flip arrows, Chief's "Reverse Wall Direction"). ``elevation`` lifts
the wall's underside off grade (a wall on a floor).

**Framing.** Every member is the stud profile's depth across the wall. The
bottom plate and each top plate run the full length: plates are butted at
corners, not lapped (corner assemblies and lapped plates are later rungs).
Studs run plate to plate, so their length is ``height`` minus the plates
(B2: 97.125 - 1.5 - 3 = 92.625, the precut). Stud centres sit 0.75 from the
start, then on ``spacing`` from the start, with an end stud flush at the far
end; a layout stud that would overlap the end stud is dropped (a 144 wall has
10 studs, a 113 wall 8), the same layout as a deck's joists.

**Members.** As in ``loft.deck``: each member is one body, a plan polygon on
a shared ``XY`` level datum (one per distinct bottom elevation) extruded up
as a new body, never fused, with role, profile and material metadata. Roles
emit in the cut list's order: studs, the openings' members, top plates,
bottom plate.

**Openings** (WINDOW-DOOR). A window or door names its host wall (a feature
input, ``loft.window`` and ``loft.door``), as Revit and Chief Architect host
them, and the wall frames every opening that names it: the registry hands the
wall the later features hosted in it (``ExpandInputs.hosted``, their inputs
only). Around each rough opening (RO): full-height kings outside jacks that
carry a doubled header on edge (two plies at the wall's faces, the spacer
between them not a member), top cripples from the header to the top plate
and, for a window, a flat sill with bottom cripples down to the bottom plate,
at the layout centres the opening replaces. A layout stud that would enter
the framing's span is dropped; a door cuts the bottom plate out of its RO.
Every shared face is ONE float, used by both members that meet at it, so no
two members overlap by rounding. The framing is laid out in wall-local
coordinates (:func:`wall_pieces`, a pure list of :class:`Piece`) and only
then placed in the world (:class:`WallFrame`). A roof or opening that reads
a wall's geometry builds :class:`WallSpec` from the wall's stored inputs.

Inputs are millimetres on the wire (their names end ``_mm``) and inches
inside, rounded to 1e-9 in so a round trip gives back the exact spec value.
"""

import dataclasses
import math
import uuid
from collections.abc import Iterable, Iterator, Sequence
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
from loft_wire.lumber import MM_PER_INCH, LumberProfile, LumberProfileKey
from loft_wire.materials import MaterialKey
from loft_wire.opening_units import OpeningUnitSize, catalogue
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    AngleInput,
    ChoiceInput,
    ChoiceOption,
    LengthInput,
    MaterialInput,
    MemberMetadata,
    PluginManifest,
    PluginMemberRole,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import (
    ExpandInputs,
    Hosted,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)

#: Rounding of an input's inch value (see the module docstring).
_INCH_DIGITS = 9
#: A layout stud within this of the end stud is dropped (the deck's joist rule,
#: kept bit for bit: loft.wall 1.0.0's layout must never change).
_EPS = 1e-9

_PT_PINE: MaterialKey = "southern_pine_pt"
_SPF: MaterialKey = "spf_lumber"


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
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=description,
        default=_mm(default_in),
        minimum=_mm(low_in),
        maximum=_mm(high_in),
    )


def _material(name: str, label: str, default: MaterialKey) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default=default,
        description="Library material of these members (their mass and cut list).",
    )


_STUDS: list[LumberProfileKey] = ["us_2x4", "us_2x6", "us_2x8"]

MANIFEST_V1 = PluginManifest(
    id="loft.wall",
    version="1.0.0",
    title="Wall",
    description="A framed stud wall: bottom plate, studs on a layout and a "
    "single or double top plate, with a cut list (Chief Architect, Medeek Wall).",
    inputs=[
        _length(
            "start_x_mm",
            "Start X",
            0.0,
            -2400.0,
            2400.0,
            "Start of the wall's exterior face, in plan.",
        ),
        _length(
            "start_y_mm",
            "Start Y",
            0.0,
            -2400.0,
            2400.0,
            "Start of the wall's exterior face, in plan.",
        ),
        AngleInput(
            kind="angle",
            name="direction_deg",
            label="Direction",
            description="From +X, counterclockwise seen from above. Draw "
            "exterior walls clockwise round the building.",
            default=0.0,
            minimum=-360.0,
            maximum=360.0,
        ),
        _length(
            "length_mm",
            "Length",
            144.0,
            12.0,
            960.0,
            "Along the direction, end to end of the plates.",
        ),
        _length(
            "height_mm",
            "Height",
            97.125,
            24.0,
            240.0,
            "Plate to plate: underside of the bottom plate to the top of the "
            "top plate.",
        ),
        _length(
            "elevation_mm",
            "Base elevation",
            0.0,
            -240.0,
            1200.0,
            "Underside of the bottom plate above Z 0.",
        ),
        ChoiceInput(
            kind="choice",
            name="side",
            label="Framing side",
            description="Which side of the line the framing lies on, looking "
            "along the direction; the line is the exterior face.",
            options=[
                ChoiceOption(value="right", label="Right (exterior on the left)"),
                ChoiceOption(value="left", label="Left (exterior on the right)"),
            ],
            default="right",
        ),
        ChoiceInput(
            kind="choice",
            name="stud_profile",
            label="Studs",
            description="Stud size; the plates are cut from it.",
            options=lumber_options(_STUDS),
            default="us_2x4",
        ),
        _length(
            "stud_spacing_mm",
            "Stud spacing",
            16.0,
            8.0,
            24.0,
            "On centres from the wall's start; an end stud sits flush at the far end.",
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
        _material("stud_material", "Stud material", _SPF),
        _material("top_plate_material", "Top plate material", _SPF),
        _material("bottom_plate_material", "Bottom plate material", _PT_PINE),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(role="stud", title="Stud"),
        # An opening's members (WINDOW-DOOR). Titles are the cut list's words:
        # a king is a stud as bought and listed (buildings.md B2's "36 studs").
        PluginMemberRole(
            role="king",
            title="Stud",
            description="King stud: full height beside an opening's jack.",
        ),
        PluginMemberRole(
            role="jack",
            title="Jack",
            description="Jack (trimmer) stud: carries an opening's header.",
        ),
        PluginMemberRole(
            role="header",
            title="Header",
            description="One ply of an opening's doubled header, on edge.",
        ),
        PluginMemberRole(
            role="cripple",
            title="Cripple",
            description="Top cripple: header to top plate at a layout centre.",
        ),
        PluginMemberRole(
            role="sill", title="Sill", description="A window's flat rough sill."
        ),
        PluginMemberRole(
            role="sill_cripple",
            title="Cripple",
            description="Bottom cripple: bottom plate to a window's sill.",
        ),
        PluginMemberRole(role="top_plate", title="Top plate"),
        PluginMemberRole(role="bottom_plate", title="Bottom plate"),
    ],
)


# --- The wall, in its own frame (pure, inches) --------------------------------------


@dataclass(frozen=True)
class WallSpec:
    """A wall's inputs in inches (what a hosted opening or a roof reads)."""

    start_x: float
    start_y: float
    direction_deg: float
    length: float
    height: float
    elevation: float
    side: Literal["right", "left"]
    stud: LumberProfile
    spacing: float
    top_plates: int
    stud_material: MaterialKey | None
    top_plate_material: MaterialKey | None
    bottom_plate_material: MaterialKey | None

    @classmethod
    def from_inputs(cls, inputs: ExpandInputs) -> "WallSpec":
        return cls(
            start_x=_inches("start_x_mm", inputs),
            start_y=_inches("start_y_mm", inputs),
            direction_deg=inputs.number("direction_deg"),
            length=_inches("length_mm", inputs),
            height=_inches("height_mm", inputs),
            elevation=_inches("elevation_mm", inputs),
            side="left" if inputs.choice("side") == "left" else "right",
            stud=inputs.lumber("stud_profile"),
            spacing=_inches("stud_spacing_mm", inputs),
            top_plates=1 if inputs.choice("top_plate") == "single" else 2,
            stud_material=inputs.material("stud_material"),
            top_plate_material=inputs.material("top_plate_material"),
            bottom_plate_material=inputs.material("bottom_plate_material"),
        )

    @property
    def thickness(self) -> float:
        """The framing's depth across the wall (the stud's width)."""
        return self.stud.width_in

    @property
    def stud_length(self) -> float:
        """Plate to plate, less the bottom plate and the top plates."""
        return self.height - (1 + self.top_plates) * self.stud.thickness_in


@dataclass(frozen=True)
class Piece:
    """One member in the wall's frame (inches): ``u`` along the wall from its
    start, ``v`` across it from the exterior face, ``z`` up from its base."""

    role: str
    profile: LumberProfile
    material: MaterialKey | None
    u0: float
    u1: float
    v0: float
    v1: float
    z0: float
    z1: float
    #: The member's stable name in 1.1.0 (``slot/8``); ``None`` in 1.0.0.
    name: str | None = None


def stud_centres(length: float, spacing: float, thickness: float) -> list[float]:
    """Stud centres along a wall (in): 0.75 from the start, then on *spacing*
    from the start, an end stud flush at the far end, a layout stud that would
    overlap it dropped (buildings.md B2: 144 -> 10 studs, 113 -> 8). The
    wall's own copy of the deck's joist layout (WALL-SHARED-CENTRES), so a
    deck change can never move a stored wall's studs."""
    first, last = thickness / 2, length - thickness / 2
    inner: list[float] = []
    n = 1
    while spacing * n <= last - thickness + _EPS:
        inner.append(spacing * n)
        n += 1
    return [first, *inner, last]


# --- Openings (WINDOW-DOOR) ----------------------------------------------------------

#: The hosted plugins a 1.x wall frames, and what each is.
OPENING_PLUGINS: dict[str, Literal["door", "window"]] = {
    "loft.door": "door",
    "loft.window": "window",
}

#: An opening built without a feature (a test's): 1.1.0 names need one.
_NO_FEATURE = uuid.UUID(int=0)

#: An opening's members that stand at a layout slot (1.1.0 names them by it).
_AT_SLOTS = frozenset({"cripple", "sill_cripple"})

#: An opening's member roles, in emission (and cut list) order.
_OPENING_ROLES = ("king", "jack", "header", "cripple", "sill", "sill_cripple")


def _rounded(value: float) -> float:
    return round(value, _INCH_DIGITS)


#: Where an opening's distance runs from (``loft.window``/``loft.door``
#: 1.2.0's ``measure_from``, OPENING-FROM-END): the wall's start, its end or
#: its centre. ``nearer`` is a write-time choice, the end nearer the part
#: origin; documents stores the end it picks (``nearer_end``).
MeasureFrom = Literal["start", "end", "centre"]


def nearer_end(wall: WallSpec) -> Literal["start", "end"]:
    """The end of *wall* nearer the part origin in plan; the start on a tie,
    so a wall centred on the origin keeps 1.1.0's reading."""
    frame = WallFrame.of(wall)
    start = math.hypot(*frame.plan(0.0, 0.0))
    end = math.hypot(*frame.plan(wall.length, 0.0))
    return "end" if end < start - _EPS else "start"


def measured_from(inputs: ExpandInputs, wall: WallSpec | None) -> MeasureFrom:
    """An opening's reference: ``start`` before 1.2.0 (no ``measure_from``),
    and ``nearer`` resolved on *wall*."""
    if "measure_from" not in inputs.values:
        return "start"
    match inputs.choice("measure_from"):
        case "start":
            return "start"
        case "end":
            return "end"
        case "centre":
            return "centre"
        case "nearer":
            pass
        case other:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"Measured from: {other!r} is not a wall end.",
                input="measure_from",
            )
    if wall is None:
        raise RuntimeError("an opening measured from its nearer end needs its wall")
    return nearer_end(wall)


def opening_centre(inputs: ExpandInputs, wall: WallSpec | None) -> float:
    """The opening's centre along its wall from the wall's start (in): the
    offset itself from the start (1.0.0 and 1.1.0 exactly), the wall's
    length less it from the end, half the length plus it from the centre."""
    offset = _inches("offset_mm", inputs)
    reference = measured_from(inputs, wall)
    if reference == "start":
        return offset
    if wall is None:
        raise RuntimeError("an opening measured from its end or centre needs its wall")
    if reference == "end":
        return _rounded(wall.length - offset)
    return _rounded(wall.length / 2 + offset)


#: ``loft.window``/``loft.door`` 1.3.0's ``size`` for a typed unit size.
CUSTOM_SIZE = "custom"


@dataclass(frozen=True)
class UnitSize:
    """An opening's unit (a door's slab) and its rough opening (in), and the
    catalogue size it is (``None`` for a typed, custom size)."""

    width: float
    height: float
    ro_width: float
    ro_height: float
    size: OpeningUnitSize | None = None


def unit_size(kind: Literal["door", "window"], inputs: ExpandInputs) -> UnitSize:
    """The unit and rough opening an opening's inputs give: from its picked
    call size (1.3.0's ``size``, OPENING-UNITS), whose rough opening the
    catalogue sets; else the typed unit width and height plus their
    allowances, as 1.0.0-1.2.0 frame them."""
    picked = inputs.values.get("size")
    if isinstance(picked, str) and picked != CUSTOM_SIZE:
        found = next((u for u in catalogue(kind).values() if u.key == picked), None)
        if found is None:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                f"Size: {picked!r} is not a {kind} size in the catalogue.",
                input="size",
            )
        return UnitSize(
            found.width_in,
            found.height_in,
            found.ro_width_in,
            found.ro_height_in,
            found,
        )
    width = _inches("width_mm", inputs)
    height = _inches("height_mm", inputs)
    return UnitSize(
        width,
        height,
        _rounded(width + _inches("ro_width_allowance_mm", inputs)),
        _rounded(height + _inches("ro_height_allowance_mm", inputs)),
    )


@dataclass(frozen=True)
class Opening:
    """A hosted rough opening (RO) in its wall's frame, inches: ``centre``
    along the wall, the RO's ``width``, its ``sill`` and ``head`` above the
    wall's base (a door's sill is the base: it cuts the bottom plate)."""

    kind: Literal["door", "window"]
    name: str
    centre: float
    width: float
    sill: float
    head: float
    header: LumberProfile
    #: The door or window feature's id: 1.1.0 names its members after it.
    feature_id: uuid.UUID = _NO_FEATURE

    @classmethod
    def from_inputs(
        cls,
        kind: Literal["door", "window"],
        name: str,
        inputs: ExpandInputs,
        wall: WallSpec | None = None,
    ) -> "Opening":
        """An opening from a ``loft.door`` / ``loft.window`` 1.x's inputs: the
        RO is the unit plus its allowance, or its picked size's
        (:func:`unit_size`); a window's head height is the RO's top, and a
        door's RO stands on the wall's base. Its centre is measured on
        *wall*, its host (:func:`opening_centre`)."""
        size = unit_size(kind, inputs)
        width, height = size.ro_width, size.ro_height
        if kind == "door":
            sill, head = 0.0, height
        else:
            head = _inches("head_height_mm", inputs)
            sill = _rounded(head - height)
        return cls(
            kind=kind,
            name=name,
            centre=opening_centre(inputs, wall),
            width=width,
            sill=sill,
            head=head,
            header=inputs.lumber("header_profile"),
            feature_id=inputs.feature_id,
        )

    @classmethod
    def from_hosted(cls, hosted: Hosted, wall: WallSpec) -> "Opening | None":
        """The opening a hosted feature frames; ``None`` for a hosted plugin
        a wall does not frame. A door or window release this wall does not
        know is refused rather than guessed at."""
        kind = OPENING_PLUGINS.get(hosted.plugin_id)
        if kind is None:
            return None
        if not hosted.plugin_version.startswith("1."):
            raise PluginError(
                PLUGIN_INPUT_UNSUPPORTED,
                f"{hosted.name}: Wall 1.0.0 cannot frame {hosted.plugin_id} "
                f"{hosted.plugin_version}.",
            )
        return cls.from_inputs(kind, hosted.name, hosted.inputs, wall)


def _refuse(opening: Opening, why: str, field: str = "offset_mm") -> PluginError:
    return PluginError(PLUGIN_INPUT_INVALID, f"{opening.name}: {why}", input=field)


@dataclass(frozen=True)
class Framing:
    """One opening's members by role, and the span ``left..right`` (outer
    face of one king to the other's) that no layout stud may enter."""

    left: float
    right: float
    pieces: dict[str, list[Piece]]


def stud_slots(length: float, spacing: float, thickness: float) -> list[str]:
    """The 1.1.0 names of :func:`stud_centres`' studs, in the same order: the
    start stud, ``slot/n`` for the layout stud at ``n x spacing`` from the
    start, and the end stud. A slot's name depends on the spacing alone, so
    an opening or a length change elsewhere never renames a stud."""
    count = len(stud_centres(length, spacing, thickness))
    return ["start", *(f"slot/{n}" for n in range(1, count - 1)), "end"]


#: 1.1.0's slack on the comparisons that decide which layout studs an
#: opening replaces (in): two faces that meet are touching even when their
#: two sums differ by an ulp (WALL-MEMBER-RENUMBER). 1.0.0 compares exactly,
#: and keeps doing so.
_TOUCH = 1e-9


def _layout(wall: WallSpec, named: bool = False) -> tuple[list[Piece], float]:
    """The layout studs, and the studs' top (the top plates' underside).
    *named* (1.1.0) gives each its slot name."""
    t, depth = wall.stud.thickness_in, wall.thickness
    stud_top = t + wall.stud_length
    centres = stud_centres(wall.length, wall.spacing, t)
    names: list[str | None] = (
        list(stud_slots(wall.length, wall.spacing, t))
        if named
        else [None] * len(centres)
    )
    studs = [
        Piece(
            "stud",
            wall.stud,
            wall.stud_material,
            c - t / 2,
            c + t / 2,
            0.0,
            depth,
            t,
            stud_top,
            name,
        )
        for c, name in zip(centres, names, strict=True)
    ]
    return studs, stud_top


def _named(pieces: list[Piece], opening: Opening) -> list[Piece]:
    """*pieces* (one role of one opening) named after the opening, in order."""
    return [
        dataclasses.replace(p, name=f"opening/{opening.feature_id}/{k}")
        for k, p in enumerate(pieces)
    ]


def frame_opening(wall: WallSpec, opening: Opening, named: bool = False) -> Framing:
    """Kings, jacks, header plies, cripples and sill round *opening*, at the
    layout studs it replaces. Raises a :class:`PluginError` naming the input
    to change when the opening does not fit the wall (what a door or window
    checks on its own write, before its wall re-expands). *named* is 1.1.0:
    members named after the opening, and faces that meet within
    :data:`_TOUCH` count as touching."""
    layout, stud_top = _layout(wall, named)
    t, depth = wall.stud.thickness_in, wall.thickness
    stud, mat = wall.stud, wall.stud_material
    tol = _TOUCH if named else 0.0
    u0 = opening.centre - opening.width / 2
    u1 = opening.centre + opening.width / 2
    # Each face is computed ONCE and shared by the two members meeting at it.
    b, e = u0 - t, u1 + t  # the jacks' outer faces: the header's ends
    a, f = b - t, e + t  # the kings' outer faces
    first, last = layout[0], layout[-1]
    if a < first.u1 - tol or f > last.u0 + tol:
        raise _refuse(
            opening,
            f"its framing ({a:g} to {f:g} in along the wall) must lie between "
            f"the wall's end studs ({first.u1:g} to {last.u0:g} in); move it "
            "along the wall or make it narrower.",
        )
    hp = opening.header
    header_top = opening.head + hp.width_in
    if header_top > stud_top:
        raise _refuse(
            opening,
            f"its head ({opening.head:g} in) and {hp.name} header reach "
            f"{header_top:g} in, above the top plate's underside "
            f"({stud_top:g} in); lower the head or the unit.",
            "head_height_mm" if opening.kind == "window" else "height_mm",
        )
    sill_bottom = opening.sill - t
    if opening.kind == "window" and sill_bottom < t:
        raise _refuse(
            opening,
            f"its rough sill at {opening.sill:g} in leaves no room for the flat "
            f"sill on the bottom plate (it needs {2 * t:g} in); raise the head "
            "or shorten the unit.",
            "head_height_mm",
        )
    replaced = [p for p in layout if p.u1 > a + tol and p.u0 < f - tol]
    pieces: dict[str, list[Piece]] = {role: [] for role in _OPENING_ROLES}
    pieces["king"] = [
        Piece("king", stud, mat, a, b, 0.0, depth, t, stud_top),
        Piece("king", stud, mat, e, f, 0.0, depth, t, stud_top),
    ]
    pieces["jack"] = [
        Piece("jack", stud, mat, b, u0, 0.0, depth, t, opening.head),
        Piece("jack", stud, mat, u1, e, 0.0, depth, t, opening.head),
    ]
    pieces["header"] = [
        Piece("header", hp, mat, b, e, v0, v1, opening.head, header_top)
        for v0, v1 in ((0.0, hp.thickness_in), (depth - hp.thickness_in, depth))
    ]
    if header_top < stud_top:
        pieces["cripple"] = [
            Piece(
                "cripple",
                stud,
                mat,
                p.u0,
                p.u1,
                0.0,
                depth,
                header_top,
                stud_top,
                p.name,
            )
            for p in replaced
            if p.u0 >= b - tol and p.u1 <= e + tol
        ]
    if opening.kind == "window":
        pieces["sill"] = [
            Piece("sill", stud, mat, u0, u1, 0.0, depth, sill_bottom, opening.sill)
        ]
        if sill_bottom > t:
            pieces["sill_cripple"] = [
                Piece(
                    "sill_cripple",
                    stud,
                    mat,
                    p.u0,
                    p.u1,
                    0.0,
                    depth,
                    t,
                    sill_bottom,
                    p.name,
                )
                for p in replaced
                if p.u0 >= u0 - tol and p.u1 <= u1 + tol
            ]
    if named:
        # A cripple stands at the layout slot it replaces and keeps that
        # stud's name (`slot/5`), so resizing the opening never hands its
        # name to the cripple beside it; the rest are named by the opening.
        pieces = {
            role: members if role in _AT_SLOTS else _named(members, opening)
            for role, members in pieces.items()
        }
    return Framing(a, f, pieces)


def _bottom_plate_spans(
    length: float, doors: Iterable[Opening]
) -> list[tuple[float, float]]:
    """The bottom plate's pieces along the wall: whole, or cut out of every
    door's rough opening (doors in order along the wall, never overlapping)."""
    spans: list[tuple[float, float]] = []
    start = 0.0
    for door in doors:
        spans.append((start, door.centre - door.width / 2))
        start = door.centre + door.width / 2
    spans.append((start, length))
    return spans


def wall_pieces(
    wall: WallSpec, openings: Sequence[Opening] = (), named: bool = False
) -> list[Piece]:
    """The wall's members in its own frame, in the cut list's order: layout
    studs, every opening's members by role, top plates, bottom plate. Raises
    a :class:`PluginError` naming an opening that does not fit, or the later
    of two whose framing overlaps. *named* is 1.1.0 (:func:`frame_opening`):
    every piece carries its stable name."""
    t, depth = wall.stud.thickness_in, wall.thickness
    tol = _TOUCH if named else 0.0
    layout, stud_top = _layout(wall, named)
    ordered = sorted(openings, key=lambda o: (o.centre, o.name))
    framings = [frame_opening(wall, o, named) for o in ordered]
    for k in range(1, len(ordered)):
        if framings[k].left < framings[k - 1].right - tol:
            raise _refuse(
                ordered[k],
                f"its framing overlaps {ordered[k - 1].name}'s; move them "
                f"{framings[k - 1].right - framings[k].left:g} in further apart.",
            )
    pieces = [
        p
        for p in layout
        if all(p.u1 <= f.left + tol or p.u0 >= f.right - tol for f in framings)
    ]
    for role in _OPENING_ROLES:
        for framing in framings:
            pieces.extend(framing.pieces[role])
    for k in range(wall.top_plates):
        z0 = stud_top + k * t
        pieces.append(
            Piece(
                "top_plate",
                wall.stud,
                wall.top_plate_material,
                0.0,
                wall.length,
                0.0,
                depth,
                z0,
                z0 + t,
                f"course/{k + 1}" if named else None,
            )
        )
    doors = [o for o in ordered if o.kind == "door"]
    # 1.1.0 names the piece from the wall's start, then one after each door.
    starts = ["start", *(f"opening/{door.feature_id}" for door in doors)]
    for (u0, u1), start in zip(
        _bottom_plate_spans(wall.length, doors), starts, strict=True
    ):
        pieces.append(
            Piece(
                "bottom_plate",
                wall.stud,
                wall.bottom_plate_material,
                u0,
                u1,
                0.0,
                depth,
                0.0,
                t,
                start if named else None,
            )
        )
    return pieces


def _cos_sin(degrees: float) -> tuple[float, float]:
    """cos and sin of *degrees*, exact at multiples of 90 (so an axis wall's
    corners carry no 1e-16 noise)."""
    turn = degrees % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    if turn in exact:
        return exact[turn]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


@dataclass(frozen=True)
class WallFrame:
    """The wall's frame placed in the world: plan point of ``(u, v)``."""

    x: float
    y: float
    along: tuple[float, float]
    across: tuple[float, float]
    base: float

    @classmethod
    def of(cls, wall: WallSpec) -> "WallFrame":
        c, s = _cos_sin(wall.direction_deg)
        across = (s, -c) if wall.side == "right" else (-s, c)
        return cls(wall.start_x, wall.start_y, (c, s), across, wall.elevation)

    def plan(self, u: float, v: float) -> tuple[float, float]:
        return (
            self.x + u * self.along[0] + v * self.across[0],
            self.y + u * self.along[1] + v * self.across[1],
        )


# --- Emission ----------------------------------------------------------------------


def _polygon(corners: Sequence[tuple[float, float]]) -> list[SketchLine]:
    points = [Point2D(x=_mm(x), y=_mm(y)) for x, y in corners]
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=points[i],
            end=points[(i + 1) % len(points)],
        )
        for i in range(len(points))
    ]


def level_name(z: float) -> str:
    """A 1.1.0 level's name: its elevation (in), already rounded to 1e-9 in,
    printed to 9 places without trailing zeros (``z/1.5``)."""
    return "z/" + f"{z:.9f}".rstrip("0").rstrip(".")


def _emit(
    inputs: ExpandInputs, frame: WallFrame, pieces: list[Piece]
) -> Iterator[Member]:
    """Levels, section sketches and member extrudes, with running indices.

    Levels are shared by their bottom elevation rounded to 1e-9 in
    (WALL-LEVEL-EQ): a sill, a header and a cripple reach their heights by
    different sums, and one ulp must not make a second datum.

    Pieces that carry a name (1.1.0) emit named members: the member by its
    piece's name, its section sketch by ``<role>/<name>`` and each level by
    its elevation, so no member's id depends on what was emitted before it."""
    levels: dict[float, int] = {}
    counts: dict[str, int] = {}
    for section, piece in enumerate(pieces):
        z0 = frame.base + piece.z0
        key = round(z0, _INCH_DIGITS) + 0.0  # + 0.0: -0.0 is the XY plane too
        plane: DatumPlaneRef | FeatureRef
        if key == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane="XY")
        else:
            level_key = None if piece.name is None else level_name(key)
            level = levels.get(key)
            if level is None:
                level = levels[key] = len(levels)
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
            plane = inputs.ref("level", level, level_key)
        corners = [
            frame.plan(u, v)
            for u, v in (
                (piece.u0, piece.v0),
                (piece.u1, piece.v0),
                (piece.u1, piece.v1),
                (piece.u0, piece.v1),
            )
        ]
        section_key = None if piece.name is None else f"{piece.role}/{piece.name}"
        yield Member(
            "section",
            section,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_polygon(corners)), constraints=[]
                ),
            ),
            name=section_key,
        )
        index = counts.get(piece.role, 0)
        counts[piece.role] = index + 1
        yield Member(
            piece.role,
            index,
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=inputs.ref("section", section, section_key),
                    distance_mm=_mm(piece.z1 - piece.z0),
                    operation="add",
                    merge=False,
                ),
            ),
            MemberMetadata(profile=piece.profile.name, material=piece.material),
            name=piece.name,
        )


#: :func:`_emit` for the outline walls (BUILDING-OUTLINE), which emit each
#: wall's pieces under its sketch line's name.
emit_pieces = _emit


def hosted_openings(inputs: ExpandInputs, wall: WallSpec) -> list[Opening]:
    """The openings hosted in this wall, *wall* (the doors and windows
    naming it)."""
    found = (Opening.from_hosted(hosted, wall) for hosted in inputs.hosted)
    return [opening for opening in found if opening is not None]


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    wall = WallSpec.from_inputs(inputs)
    pieces = wall_pieces(wall, hosted_openings(inputs, wall))
    yield from _emit(inputs, WallFrame.of(wall), pieces)


def expand_v1_1(inputs: ExpandInputs) -> Iterator[Member]:
    """1.1.0: 1.0.0's members in 1.0.0's order, each named by its place
    (WALL-MEMBER-RENUMBER): a layout stud by its slot, an opening's members
    by the opening, a level by its height."""
    wall = WallSpec.from_inputs(inputs)
    pieces = wall_pieces(wall, hosted_openings(inputs, wall), named=True)
    yield from _emit(inputs, WallFrame.of(wall), pieces)


#: 1.0.0 numbers every role in emission order, so all but the top plates
#: (one per course, always) can pass to another member on a re-layout.
_RENUMBERED = frozenset({"level", "section", "stud", "bottom_plate", *_OPENING_ROLES})

MANIFEST_V1_1 = MANIFEST_V1.model_copy(
    update={
        "version": "1.1.0",
        "description": MANIFEST_V1.description
        + " Each member keeps its name when an opening moves.",
    }
)

WALL_V1 = Plugin(MANIFEST_V1, expand, renumbered_roles=_RENUMBERED)
WALL_V1_1 = Plugin(MANIFEST_V1_1, expand_v1_1)
