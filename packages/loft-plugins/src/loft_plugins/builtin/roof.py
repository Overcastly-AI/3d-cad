"""Roof: a gable of common rafters on two bearing walls (ROOF, RESEARCH §23).

What Chief Architect's roof framing and SketchUp's Medeek Truss (rafter
roofs) build for a stick-framed gable: a ridge board along the building,
common rafters at a spacing in pairs, each with a plumb cut at the ridge, a
birdsmouth on the wall plate and a plumb-cut tail past the wall.
``docs/reference-parts/buildings.md`` B2's roof is the default exactly.

This is a FRAMING MODEL with a cut list, not a structural design: no span
table, load or code check is implied (buildings.md). Trusses, hips, valleys,
rafter ties, collar ties and a rake (gable) overhang are later rungs.

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
from collections.abc import Iterator
from dataclasses import dataclass

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
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    LengthInput,
    MaterialInput,
    MemberMetadata,
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


def _inches(name: str, inputs: ExpandInputs) -> float:
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


def _material(name: str, label: str) -> MaterialInput:
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
        _material("rafter_material", "Rafter material"),
        _material("ridge_material", "Ridge material"),
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


def _unsupported(message: str, input_name: str) -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=input_name)


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    span = _inches("span_mm", inputs)
    length = _inches("length_mm", inputs)
    plate_height = _inches("plate_height_mm", inputs)
    plate_width = _inches("plate_width_mm", inputs)
    pitch = inputs.choice("pitch")
    rises = {pitch_value(r): r for r in PITCHES}
    if pitch not in rises:
        raise _unsupported(f"{pitch!r} is not a pitch", "pitch")
    rise = rises[pitch]
    spacing = _inches("spacing_mm", inputs)
    overhang = _inches("overhang_mm", inputs)
    rafter_p = inputs.lumber("rafter_profile")
    ridge_p = inputs.lumber("ridge_profile")
    rafter_mat = inputs.material("rafter_material")
    ridge_mat = inputs.material("ridge_material")

    r = rafter_for(rise, rafter_p, ridge_p, span, plate_height, plate_width, overhang)
    # The bounds keep the ridge clear of the walls: the smallest span puts its
    # face 23.25 in in, past the widest plate (11.25).
    if ridge_p.width_in < r.plumb_depth:
        raise _unsupported(
            f"The ridge board must be at least as deep as the rafters' plumb cut "
            f"({r.plumb_depth:.3f} in): choose a deeper ridge or a shallower "
            "rafter or pitch.",
            "ridge_profile",
        )

    front = r.profile()
    back = [(span - y, z) for y, z in reversed(front)]
    t = rafter_p.thickness_in
    rafter_meta = MemberMetadata(profile=rafter_p.name, material=rafter_mat)

    planes = 0
    sections = 0
    rafters = 0
    for centre in joist_centres(length, spacing, t):
        x0 = centre - t / 2
        plane: DatumPlaneRef | FeatureRef
        if x0 == 0.0:
            plane = DatumPlaneRef(kind="datum_plane", plane="YZ")
        else:
            yield Member(
                "plane",
                planes,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(base="YZ", offset_mm=_mm(x0)),
                ),
            )
            plane = inputs.ref("plane", planes)
            planes += 1
        for outline in (front, back):
            yield Member(
                "section",
                sections,
                SketchFeature(
                    type="sketch",
                    version=1,
                    params=SketchParamsV1(
                        plane=plane, entities=list(_polygon(outline)), constraints=[]
                    ),
                ),
            )
            yield Member(
                "rafter",
                rafters,
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=inputs.ref("section", sections),
                        distance_mm=_mm(t),
                        operation="add",
                        merge=False,
                    ),
                ),
                rafter_meta,
            )
            sections += 1
            rafters += 1

    # The ridge board: its section on the YZ plane, run the roof's length.
    half = ridge_p.thickness_in / 2
    top = r.top_at_ridge
    bottom = top - ridge_p.width_in
    centre_y = span / 2
    yield Member(
        "section",
        sections,
        SketchFeature(
            type="sketch",
            version=1,
            params=SketchParamsV1(
                plane=DatumPlaneRef(kind="datum_plane", plane="YZ"),
                entities=list(
                    _polygon(
                        [
                            (centre_y - half, bottom),
                            (centre_y + half, bottom),
                            (centre_y + half, top),
                            (centre_y - half, top),
                        ]
                    )
                ),
                constraints=[],
            ),
        ),
    )
    yield Member(
        "ridge",
        0,
        ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(
                profile=inputs.ref("section", sections),
                distance_mm=_mm(length),
                operation="add",
                merge=False,
            ),
        ),
        MemberMetadata(profile=ridge_p.name, material=ridge_mat),
    )


ROOF_V1 = Plugin(MANIFEST_V1, expand)
