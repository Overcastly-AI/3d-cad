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
emit in the cut list's order: studs, top plates, bottom plate.

**Openings (the WINDOW-DOOR seam).** A window or door names its host wall
(a feature input), as Revit and Chief Architect host them, and the wall
frames every opening that names it: kings, jacks, header, cripples and sill
replace the layout studs inside the rough opening, and a door cuts the
bottom plate. The framing is laid out in wall-local coordinates
(:func:`wall_pieces`, a pure list of :class:`Piece`) and only then placed in
the world (:class:`WallFrame`), so openings change the local list alone.
Until a hosted feature exists no stored wall has an opening, so adding
opening framing changes no stored expansion. A roof or opening that reads a
wall's geometry builds :class:`WallSpec` from the wall's stored inputs.

Inputs are millimetres on the wire (their names end ``_mm``) and inches
inside, rounded to 1e-9 in so a round trip gives back the exact spec value.
"""

import math
from collections.abc import Iterator, Sequence
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
from loft_wire.plugins import (
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

from loft_plugins.api import ExpandInputs, Member, Plugin, lumber_options
from loft_plugins.builtin.deck import joist_centres

#: Rounding of an input's inch value (see the module docstring).
_INCH_DIGITS = 9

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


def stud_centres(length: float, spacing: float, thickness: float) -> list[float]:
    """Stud centres along a wall (in): 0.75 from the start, then on *spacing*
    from the start, an end stud flush at the far end, a layout stud that would
    overlap it dropped (buildings.md B2: 144 -> 10 studs, 113 -> 8)."""
    return joist_centres(length, spacing, thickness)


def wall_pieces(wall: WallSpec) -> list[Piece]:
    """The wall's members in its own frame, in the cut list's order. (The
    WINDOW-DOOR seam: hosted openings replace the studs inside their rough
    openings here, and nowhere else.)"""
    t, depth = wall.stud.thickness_in, wall.thickness
    stud_top = t + wall.stud_length
    pieces = [
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
        )
        for c in stud_centres(wall.length, wall.spacing, t)
    ]
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
            )
        )
    pieces.append(
        Piece(
            "bottom_plate",
            wall.stud,
            wall.bottom_plate_material,
            0.0,
            wall.length,
            0.0,
            depth,
            0.0,
            t,
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


def _emit(
    inputs: ExpandInputs, frame: WallFrame, pieces: list[Piece]
) -> Iterator[Member]:
    """Levels, section sketches and member extrudes, with running indices."""
    levels: dict[float, int] = {}
    counts: dict[str, int] = {}
    for section, piece in enumerate(pieces):
        z0 = frame.base + piece.z0
        plane: DatumPlaneRef | FeatureRef
        if z0 == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane="XY")
        else:
            level = levels.get(z0)
            if level is None:
                level = levels[z0] = len(levels)
                yield Member(
                    "level",
                    level,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumOffsetParams(base="XY", offset_mm=_mm(z0)),
                    ),
                )
            plane = inputs.ref("level", level)
        corners = [
            frame.plan(u, v)
            for u, v in (
                (piece.u0, piece.v0),
                (piece.u1, piece.v0),
                (piece.u1, piece.v1),
                (piece.u0, piece.v1),
            )
        ]
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
                    profile=inputs.ref("section", section),
                    distance_mm=_mm(piece.z1 - piece.z0),
                    operation="add",
                    merge=False,
                ),
            ),
            MemberMetadata(profile=piece.profile.name, material=piece.material),
        )


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    wall = WallSpec.from_inputs(inputs)
    yield from _emit(inputs, WallFrame.of(wall), wall_pieces(wall))


WALL_V1 = Plugin(MANIFEST_V1, expand)
