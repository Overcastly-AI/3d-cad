"""Floor: a framed platform floor from a few inputs (FLOOR-FRAME, RESEARCH §23).

What Chief Architect's floor framing and SketchUp's Medeek Foundation build
for a plain platform floor: sill plates laid flat on the foundation, a rim
(band) joist across the joist ends, and joists on a layout between the rims
with both end joists flush. ``docs/reference-parts/buildings.md`` B5's floor
is the defaults exactly.

This is a FRAMING MODEL with a cut list, not a structural design: no span
table, load or code check is implied (buildings.md).

**Placement.** A floor is a rectangle in plan: a start corner, a direction
(degrees counterclockwise from +X, seen from above), a width along the
direction and a depth to its left, so the default floor is X 0..width,
Y 0..depth (B2's and B5's frame). ``elevation`` is the top of the foundation:
the sill plates' underside.

**Framing.** The framing is laid out in a local frame: ``a`` along the rims
(the joist layout) and ``b`` along the joists. Joists run along the depth by
default (``a`` is the width), or along the width. Rims run the full ``a``
length at both ends of the joists; the end joists are the floor's other two
sides, flush with its edges, between the rims. Joist centres sit half a
thickness from ``a = 0``, then on ``spacing`` from ``a = 0``, with the far end
joist flush; a layout joist that would overlap it is dropped (the deck's and
the wall's layout, kept in this module's own copy so neither can move a
stored floor's joists). Rims and the end joists are cut from the joist size,
tops flush. The sill plates (on by default, pressure-treated 2x6) lie flat
under the rims and end joists, their outer edges flush with the floor's, and
are butted as wall plates are: the two under the rims run the full length and
the two under the end joists fit between them (B5: 2 at 144, 2 at 109).

**Members.** As in ``loft.deck`` and ``loft.wall``: each member is one body,
a plan rectangle on a shared ``XY`` level datum (one per distinct bottom
elevation) extruded up as a new body, never fused, with role, profile and
material metadata. Roles emit in the cut list's order: joists, rims, sills.

**Stable ids by slot.** A member's id is ``<feature>/<role>/<n>`` (RESEARCH
§23), so ``n`` is chosen to name the member's place, not its rank: the two
end joists are ``joist/0`` (at ``a = 0``) and ``joist/1`` (flush at the far
end), and the layout joist on slot ``k`` (centre ``k * spacing``) is
``joist/k+1``. Widening a floor adds joists after the ones it had, so a hole
through the end joist or any layout joist stays on that joist
(WALL-MEMBER-RENUMBER names the same bug in the wall and the deck). Rims are
``rim/0`` (``b = 0``) and ``rim/1``; sills ``sill/0..3`` under rim 0, rim 1,
end joist 0 and end joist 1.

**No float overlaps.** Every face two members share is computed once and
used by both; a layout joist whose face lands within 1e-9 in of the end
joist's takes the end joist's face, so a sweep over sizes and spacings finds
no two members overlapping at all (DECK's and WINDOW-DOOR's float class).

**The subfloor seam** (SHEATHING). The framing is a pure list of
:class:`Piece` in the local frame (:func:`floor_pieces`) placed in the world
only at emission (:class:`FloorFrame`), and :attr:`FloorSpec.framing_top` is
the joists' top: a later version adds the subfloor's panels on it to that
list as a new input, without moving a framing member, and walls stand on the
floor through their base elevation.

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

#: Rounding of an input's inch value (see the module docstring).
_INCH_DIGITS = 9
#: Float slack of the layout (in): far below any real length.
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


def _material(
    name: str, label: str, default: MaterialKey, description: str
) -> MaterialInput:
    return MaterialInput(
        kind="material",
        name=name,
        label=label,
        default=default,
        description=description,
    )


_JOISTS: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]
_SILLS: list[LumberProfileKey] = ["us_2x4", "us_2x6", "us_2x8"]

MANIFEST_V1 = PluginManifest(
    id="loft.floor",
    version="1.0.0",
    title="Floor",
    description="A framed platform floor: sill plates, rim joists and joists "
    "on a layout, with a cut list (Chief Architect, Medeek Foundation).",
    inputs=[
        _length(
            "start_x_mm",
            "Start X",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the floor's outside edge, in plan.",
        ),
        _length(
            "start_y_mm",
            "Start Y",
            0.0,
            -2400.0,
            2400.0,
            "A corner of the floor's outside edge, in plan.",
        ),
        AngleInput(
            kind="angle",
            name="direction_deg",
            label="Direction",
            description="Of the width, from +X, counterclockwise seen from "
            "above; the depth runs to its left.",
            default=0.0,
            minimum=-360.0,
            maximum=360.0,
        ),
        _length(
            "width_mm",
            "Width",
            144.0,
            48.0,
            960.0,
            "Along the direction, outside of the framing.",
        ),
        _length(
            "depth_mm",
            "Depth",
            120.0,
            48.0,
            960.0,
            "To the left of the direction, outside of the framing.",
        ),
        _length(
            "elevation_mm",
            "Base elevation",
            0.0,
            -240.0,
            1200.0,
            "Top of the foundation: the sill plates' underside above Z 0.",
        ),
        ChoiceInput(
            kind="choice",
            name="joist_profile",
            label="Joists",
            description="Joist size; the rims are cut from it.",
            options=lumber_options(_JOISTS),
            default="us_2x8",
        ),
        _length(
            "joist_spacing_mm",
            "Joist spacing",
            16.0,
            8.0,
            24.0,
            "On centres from the start; an end joist sits flush at the far end.",
        ),
        ChoiceInput(
            kind="choice",
            name="joist_direction",
            label="Joist direction",
            description="The joists span the depth (rims along the width) or "
            "the width.",
            options=[
                ChoiceOption(value="depth", label="Along the depth"),
                ChoiceOption(value="width", label="Along the width"),
            ],
            default="depth",
        ),
        ChoiceInput(
            kind="choice",
            name="sill_plate",
            label="Sill plate",
            description="Plates laid flat on the foundation under the rims "
            "and end joists.",
            options=[
                ChoiceOption(value="yes", label="Yes"),
                ChoiceOption(value="no", label="No"),
            ],
            default="yes",
        ),
        ChoiceInput(
            kind="choice",
            name="sill_profile",
            label="Sill size",
            description="Laid flat, its width under the framing's edge.",
            options=lumber_options(_SILLS),
            default="us_2x6",
        ),
        _material(
            "framing_material",
            "Framing material",
            _SPF,
            "Library material of the joists and rims (their mass and cut list).",
        ),
        _material(
            "sill_material",
            "Sill material",
            _PT_PINE,
            "Library material of the sill plates: pressure-treated where they "
            "meet the foundation.",
        ),
    ],
    members=[
        PluginMemberRole(role="level", title="Level"),
        PluginMemberRole(role="section", title="Section"),
        PluginMemberRole(
            role="joist",
            title="Joist",
            description="joist/0 and joist/1 are the end joists; joist/k+1 "
            "is the layout joist k spacings from the start.",
        ),
        PluginMemberRole(
            role="rim",
            title="Rim",
            description="Rim (band) joist across the joist ends.",
        ),
        PluginMemberRole(
            role="sill", title="Sill", description="Sill plate, flat on the foundation."
        ),
    ],
)


# --- The floor, in its own frame (pure, inches) -------------------------------------


@dataclass(frozen=True)
class FloorSpec:
    """A floor's inputs in inches."""

    start_x: float
    start_y: float
    direction_deg: float
    width: float
    depth: float
    elevation: float
    joist: LumberProfile
    spacing: float
    joists_along: Literal["depth", "width"]
    sill: LumberProfile | None
    framing_material: MaterialKey | None
    sill_material: MaterialKey | None

    @classmethod
    def from_inputs(cls, inputs: ExpandInputs) -> "FloorSpec":
        return cls(
            start_x=_inches("start_x_mm", inputs),
            start_y=_inches("start_y_mm", inputs),
            direction_deg=inputs.number("direction_deg"),
            width=_inches("width_mm", inputs),
            depth=_inches("depth_mm", inputs),
            elevation=_inches("elevation_mm", inputs),
            joist=inputs.lumber("joist_profile"),
            spacing=_inches("joist_spacing_mm", inputs),
            joists_along="width"
            if inputs.choice("joist_direction") == "width"
            else "depth",
            sill=inputs.lumber("sill_profile")
            if inputs.choice("sill_plate") == "yes"
            else None,
            framing_material=inputs.material("framing_material"),
            sill_material=inputs.material("sill_material"),
        )

    @property
    def span_a(self) -> float:
        """The rims' length: the joist layout runs along it."""
        return self.depth if self.joists_along == "width" else self.width

    @property
    def span_b(self) -> float:
        """Out to out of the rims: the joists run along it."""
        return self.width if self.joists_along == "width" else self.depth

    @property
    def framing_bottom(self) -> float:
        """The rims' and joists' underside, above the floor's base (in)."""
        return 0.0 if self.sill is None else self.sill.thickness_in

    @property
    def framing_top(self) -> float:
        """The joists' top above the floor's base (in): where a subfloor or a
        wall's bottom plate sits."""
        return self.framing_bottom + self.joist.width_in


@dataclass(frozen=True)
class Piece:
    """One member in the floor's local frame (inches): ``a`` along the rims,
    ``b`` along the joists, ``z`` up from the floor's base. ``index`` is the
    member's slot (module docstring), unique within its role."""

    role: str
    index: int
    profile: LumberProfile
    material: MaterialKey | None
    a0: float
    a1: float
    b0: float
    b1: float
    z0: float
    z1: float


def joist_slots(length: float, spacing: float, thickness: float) -> list[int]:
    """The layout slots ``k >= 1`` (centre ``k * spacing`` from the start) that
    fit between the end joists: half a thickness from the start, then every
    spacing, an end joist flush at the far end, a layout joist that would
    overlap it dropped (buildings.md B5: 144 at 16 -> 1..8, at 12 -> 1..11).
    The floor's own copy of the deck's and the wall's rule."""
    inner_face = length - thickness  # the far end joist's inner face
    slots: list[int] = []
    k = 1
    while spacing * k + thickness / 2 <= inner_face + _EPS:
        slots.append(k)
        k += 1
    return slots


def joist_centres(length: float, spacing: float, thickness: float) -> list[float]:
    """Every joist centre along the rims (in), in order along them."""
    centres = [spacing * k for k in joist_slots(length, spacing, thickness)]
    return [thickness / 2, *centres, length - thickness / 2]


def floor_pieces(floor: FloorSpec) -> list[Piece]:
    """The floor's members in its own frame, in the cut list's order: joists
    (both end joists, then the layout by slot), rims, sills."""
    joist, mat = floor.joist, floor.framing_material
    t = joist.thickness_in
    la, lb = floor.span_a, floor.span_b
    z0, z1 = floor.framing_bottom, floor.framing_top
    # Each shared face is ONE float: the rims' inner faces are the joists'
    # ends, the end joists' inner faces cap the layout.
    b_in, b_out = t, lb - t
    far = la - t
    pieces = [
        Piece("joist", 0, joist, mat, 0.0, t, b_in, b_out, z0, z1),
        Piece("joist", 1, joist, mat, far, la, b_in, b_out, z0, z1),
    ]
    for k in joist_slots(la, floor.spacing, t):
        c = floor.spacing * k
        a0, a1 = c - t / 2, c + t / 2
        if a1 > far:  # within _EPS of the end joist: share its face
            a0, a1 = far - t, far
        pieces.append(Piece("joist", k + 1, joist, mat, a0, a1, b_in, b_out, z0, z1))
    pieces += [
        Piece("rim", 0, joist, mat, 0.0, la, 0.0, b_in, z0, z1),
        Piece("rim", 1, joist, mat, 0.0, la, b_out, lb, z0, z1),
    ]
    sill = floor.sill
    if sill is not None:
        w, st, smat = sill.width_in, sill.thickness_in, floor.sill_material
        # Butted as wall plates: full length under the rims, between them
        # under the end joists.
        s_in, s_out = w, lb - w
        pieces += [
            Piece("sill", 0, sill, smat, 0.0, la, 0.0, s_in, 0.0, st),
            Piece("sill", 1, sill, smat, 0.0, la, s_out, lb, 0.0, st),
            Piece("sill", 2, sill, smat, 0.0, w, s_in, s_out, 0.0, st),
            Piece("sill", 3, sill, smat, la - w, la, s_in, s_out, 0.0, st),
        ]
    return pieces


def _cos_sin(degrees: float) -> tuple[float, float]:
    """cos and sin of *degrees*, exact at multiples of 90 (so an axis floor's
    corners carry no 1e-16 noise)."""
    turn = degrees % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    if turn in exact:
        return exact[turn]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


@dataclass(frozen=True)
class FloorFrame:
    """The floor's local frame placed in the world: plan point of ``(a, b)``."""

    x: float
    y: float
    a_axis: tuple[float, float]
    b_axis: tuple[float, float]
    base: float

    @classmethod
    def of(cls, floor: FloorSpec) -> "FloorFrame":
        c, s = _cos_sin(floor.direction_deg)
        along, left = (c, s), (-s, c)
        if floor.joists_along == "width":
            return cls(floor.start_x, floor.start_y, left, along, floor.elevation)
        return cls(floor.start_x, floor.start_y, along, left, floor.elevation)

    def plan(self, a: float, b: float) -> tuple[float, float]:
        return (
            self.x + a * self.a_axis[0] + b * self.b_axis[0],
            self.y + a * self.a_axis[1] + b * self.b_axis[1],
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
    inputs: ExpandInputs, frame: FloorFrame, pieces: list[Piece]
) -> Iterator[Member]:
    """Levels, section sketches and member extrudes. Levels are shared by
    their bottom elevation rounded to 1e-9 in (WALL-LEVEL-EQ)."""
    levels: dict[float, int] = {}
    for section, piece in enumerate(pieces):
        z0 = frame.base + piece.z0
        key = round(z0, _INCH_DIGITS) + 0.0  # + 0.0: -0.0 is the XY plane too
        plane: DatumPlaneRef | FeatureRef
        if key == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane="XY")
        else:
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
                )
            plane = inputs.ref("level", level)
        corners = [
            frame.plan(a, b)
            for a, b in (
                (piece.a0, piece.b0),
                (piece.a1, piece.b0),
                (piece.a1, piece.b1),
                (piece.a0, piece.b1),
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
        yield Member(
            piece.role,
            piece.index,
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
    floor = FloorSpec.from_inputs(inputs)
    yield from _emit(inputs, FloorFrame.of(floor), floor_pieces(floor))


FLOOR_V1 = Plugin(MANIFEST_V1, expand)

#: The parts a later release frames other pieces with (SECOND-FLOOR).
cos_sin = _cos_sin
emit = _emit
