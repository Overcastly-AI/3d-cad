"""Cabinets: a run of casework boxes as ONE feature (CASEWORK, RESEARCH §23).

As Mozaik places a run along a wall: an ordered list of boxes (the manifest's
list input, ``boxes``), each a base, wall, tall or vanity cabinet in US stock
sizes, or a filler, set side by side from the run's start. A single cabinet
is a run of one. The run sits on a ``loft.wall``'s inside face, measured from
either end as an opening is, or at a typed position and direction.

These are shop models with a cut list, not a joinery design
(``docs/reference-parts/casework.md``): panels butt, and dados, dowels,
screws, line-bore holes and hinge cups are not modelled. Every panel is a
separate body, as a wall's studs are.

**Frame.** Inches inside, rounded to 1e-9 in, millimetres on the wire. A
run's frame has X along the run, Y out from the wall (the carcass backs at
Y 0) and Z up from the floor it stands on (a picked wall's base). A panel is
a plan rectangle on a level datum extruded up, but a notched cabinet side:
its profile on a vertical plane across the run, extruded along it, exact on
the axes (an offset ``YZ`` or ``XZ`` datum) and on a plane turned about Z
otherwise.

**A box** (frameless, European full overlay). Sides 3/4 full height, the
bottom and back between them, the bottom in front of the back; a base or
vanity has two 4 in stretchers at its top, a wall or tall box a full top; a
base, tall or vanity box stands on a 4.5 in toe kick set back 3 in, its sides
notched for it. Adjustable shelves are 1/16 narrower than the inside and 1 in
back from the front, spaced evenly in the door bay. Fronts are 3/4 with a
1/16 reveal at the box's edges and 1/8 between fronts. Drawer boxes are 1/2
plywood on a 1/4 bottom, 1 in narrower than the opening, on the longest
side-mount slide (12-24 in, 2 in steps) that fits the inside depth. A
face-frame box adds a 3/4 x 1-1/2 hardwood frame (stiles full height, rails
at the top, the bottom and between fronts), its fronts overlaying it 1/2 in.

**Cut list.** Each panel carries its sheet product, material and, for
plywood, its grain direction (along a side's, back's or front's height, a
bottom's, stretcher's or shelf's width); edge banding on each exposed carcass
front edge and all four edges of each front (by the foot); and its hardware,
hinges by Blum's count for the door's height and a pair of slides per drawer
(Each). The cut list lists them under Casework.
"""

import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from loft_wire.casework import EdgeBanding, HardwareCount, slide_key
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
from loft_wire.lumber import MM_PER_INCH
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    AngleInput,
    ChoiceInput,
    ChoiceOption,
    CountInput,
    FeatureReferenceInput,
    LengthInput,
    ListInput,
    MemberMetadata,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
    SegmentsInput,
)
from loft_wire.sketch import Point2D, SketchLine

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin.house import wall_specs_of
from loft_plugins.builtin.wall import WallFrame, WallSpec, level_name

_DIGITS = 9
#: Panel thickness (carcass, fronts, fillers); drawer box sides and bottom.
T = 0.75
DRAWER_SIDE = 0.5
DRAWER_BOTTOM = 0.25
#: Frameless reveals: at a box's edges, and between neighbouring fronts.
REVEAL = 1 / 16
GAP = 1 / 8
#: Toe kick height and setback; stretcher width; shelf clearances.
TOE = 4.5
TOE_SETBACK = 3.0
STRETCHER = 4.0
SHELF_SIDE_CLEARANCE = 1 / 32
SHELF_SETBACK = 1.0
#: Drawer box: 1/2 in each side for the slides, sides 2 in shorter than the
#: front, the box's top 3/4 below its opening's top (frameless).
SLIDE_CLEARANCE = 0.5
DRAWER_SIDE_SHORT = 2.0
DRAWER_TOP_CLEARANCE = 0.75
#: Face frame: 3/4 x 1-1/2 hardwood, fronts overlaying it 1/2 in; a drawer
#: box 1 in smaller than its frame opening each way, centred in it.
FRAME_WIDTH = 1.5
OVERLAY = 0.5
FRAME_PROFILE = "1x2"
FRAME_MATERIAL: MaterialKey = "white_oak"

#: Carcass depth (in) by box type, back to front edge.
DEPTHS: dict[str, float] = {"base": 24.0, "wall": 12.0, "tall": 24.0, "vanity": 21.0}
#: The heights a box type is built in (in), its standard first.
HEIGHTS: dict[str, tuple[float, ...]] = {
    "base": (34.5,),
    "wall": (30.0, 36.0, 42.0),
    "tall": (84.0, 90.0, 96.0),
    "vanity": (34.5, 30.5),
}
_HEIGHT_OPTIONS: dict[str, float] = {
    "h30": 30.0,
    "h30_5": 30.5,
    "h34_5": 34.5,
    "h36": 36.0,
    "h42": 42.0,
    "h84": 84.0,
    "h90": 90.0,
    "h96": 96.0,
}
#: A box's fronts by type: the standard first, then every layout it takes.
FRONTS: dict[str, tuple[str, ...]] = {
    "base": ("drawer_door", "door", "false_door", "drawers"),
    "vanity": ("false_door", "door", "drawer_door", "drawers"),
    "wall": ("door",),
    "tall": ("stacked_doors", "door", "drawer_door"),
}
#: The base box a tall box's stacked doors line up with (in).
BASE_HEIGHT = 34.5
#: Widths of a box (not a filler): 9 to 48 in, 3 in steps.
MIN_WIDTH, MAX_WIDTH, WIDTH_STEP = 9.0, 48.0, 3.0
#: Auto doors: one to this width (in), two above: C1 widened to 27 keeps
#: its one door.
ONE_DOOR_MAX = 27.0

#: Blum's hinges per door by the door's height (in): to 35.4 two, to 63
#: three, to 78.7 four, to 94.5 five.
HINGE_TABLE: tuple[tuple[float, int], ...] = (
    (35.4, 2),
    (63.0, 3),
    (78.7, 4),
    (94.5, 5),
)
#: Side-mount slide lengths (in), longest first.
SLIDES: tuple[int, ...] = (24, 22, 20, 18, 16, 14, 12)

#: By carcass choice: the 3/4 product, its material and its banding's.
_PRODUCT = {"plywood": "3/4 plywood", "melamine": "3/4 melamine"}
_MATERIAL: dict[str, MaterialKey] = {"plywood": "plywood", "melamine": "melamine"}
_BANDING: dict[str, Literal["plywood", "pvc"]] = {
    "plywood": "plywood",
    "melamine": "pvc",
}
_PLY: MaterialKey = "plywood"

Grain = Literal["x", "y", "z"]


def _mm(inches: float) -> float:
    return inches * MM_PER_INCH


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


def _inches(inputs: ExpandInputs, name: str) -> float:
    return _r(inputs.number(name) / MM_PER_INCH)


def hinges_for(height_in: float) -> int:
    """Blum's hinge count for a door *height_in* tall (:data:`HINGE_TABLE`)."""
    for limit, count in HINGE_TABLE:
        if height_in <= limit + 1e-9:
            return count
    raise PluginError(
        PLUGIN_INPUT_UNSUPPORTED,
        f"Boxes: a {height_in:g} in door is taller than Blum's 94.5 in table; "
        "use stacked doors.",
        input="boxes",
    )


def slide_for(inside_depth_in: float) -> int | None:
    """The longest slide (in) that fits *inside_depth_in*, or ``None``."""
    for length in SLIDES:
        if length <= inside_depth_in + 1e-9:
            return length
    return None


def _cos_sin(degrees: float) -> tuple[float, float]:
    turn = degrees % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    if turn in exact:
        return exact[turn]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


# --- Inputs ------------------------------------------------------------------------


def _length(
    name: str, label: str, default: float, low: float, high: float, help: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=help,
        default=_mm(default),
        minimum=_mm(low),
        maximum=_mm(high),
    )


def _choice(
    name: str, label: str, options: Sequence[tuple[str, str]], help: str
) -> ChoiceInput:
    return ChoiceInput(
        kind="choice",
        name=name,
        label=label,
        description=help,
        options=[ChoiceOption(value=v, label=t) for v, t in options],
        default=options[0][0],
    )


def _count(
    name: str, label: str, default: int, low: int, high: int, help: str
) -> CountInput:
    return CountInput(
        kind="count",
        name=name,
        label=label,
        description=help,
        default=default,
        minimum=low,
        maximum=high,
    )


BOX_FIELDS = [
    _choice(
        "type",
        "Type",
        [
            ("base", "Base"),
            ("wall", "Wall"),
            ("tall", "Tall"),
            ("vanity", "Vanity"),
            ("filler", "Filler"),
        ],
        "Base 34.5 high and 24 deep, wall 12 deep, tall 24 deep, vanity 21 "
        "deep; a filler is a 3/4 panel the width typed, in line with its "
        "neighbour's fronts.",
    ),
    _length(
        "width_mm",
        "Width",
        24.0,
        0.5,
        MAX_WIDTH,
        "A box is 9 to 48 in, in 3 in steps; a filler any width.",
    ),
    _choice(
        "height",
        "Height",
        [
            ("standard", "Standard"),
            ("h30", "30 in"),
            ("h30_5", "30.5 in"),
            ("h34_5", "34.5 in"),
            ("h36", "36 in"),
            ("h42", "42 in"),
            ("h84", "84 in"),
            ("h90", "90 in"),
            ("h96", "96 in"),
        ],
        "Standard: base 34.5, wall 30, tall 84, vanity 34.5. A wall box is "
        "30, 36 or 42; a tall 84, 90 or 96; a vanity 34.5 or 30.5.",
    ),
    _choice(
        "fronts",
        "Fronts",
        [
            ("standard", "Standard"),
            ("drawer_door", "Drawer over doors"),
            ("door", "Doors"),
            ("false_door", "False front over doors"),
            ("drawers", "Drawers"),
            ("stacked_doors", "Stacked doors"),
        ],
        "Standard: a base box a drawer over doors, a vanity a false front "
        "over doors, a wall box doors, a tall box stacked doors split in line "
        "with a base box's door top.",
    ),
    _choice(
        "doors",
        "Doors",
        [("auto", "Auto"), ("one", "One"), ("two", "Two")],
        "Auto: one door to 27 in wide, two above (casework.md C1).",
    ),
    _count("drawers", "Drawers", 3, 1, 6, "How many drawers a drawer bank has."),
    _length(
        "drawer_height_mm",
        "Drawer front",
        6.0,
        3.0,
        12.0,
        "The top drawer's (or false front's) height; a drawer bank's others "
        "share the rest.",
    ),
    _count("shelves", "Shelves", 1, 0, 8, "Adjustable shelves in the door bay."),
]


def _typed(item: PluginInput) -> PluginInput:
    """A typed-position input: hidden once a wall is picked."""
    return item.model_copy(update={"superseded_by": "wall"})


INPUTS: list[PluginInput] = [
    FeatureReferenceInput(
        kind="feature",
        name="wall",
        label="Wall",
        description="The wall the run's backs sit on, at its inside face; "
        "empty for a typed position.",
        feature_types=["custom"],
        plugin_ids=["loft.wall"],
        optional=True,
    ),
    SegmentsInput(
        kind="segments",
        name="wall_segment",
        label="Wall line",
        description="When the wall is an outline wall: the line the run is on.",
        outline_input="wall",
        min_items=0,
        max_items=1,
    ),
    _choice(
        "measure_from",
        "Measured from",
        [("start", "Wall start"), ("end", "Wall end")],
        "The wall end the run's distance runs from; the boxes run away from it.",
    ),
    _length(
        "offset_mm",
        "Distance",
        0.0,
        0.0,
        960.0,
        "From the wall end, along its inside face, to the run's first box.",
    ),
    _length(
        "gap_mm",
        "Back gap",
        0.0,
        0.0,
        6.0,
        "From the wall's framing to the carcass backs: 1/2 in for gypsum.",
    ),
    _typed(_length("x_mm", "X", 0.0, -12000.0, 12000.0, "The run's start, X.")),
    _typed(_length("y_mm", "Y", 0.0, -12000.0, 12000.0, "The run's start, Y.")),
    _typed(
        _length("z_mm", "Floor", 0.0, -12000.0, 12000.0, "The floor it stands on, Z.")
    ),
    _typed(
        AngleInput(
            kind="angle",
            name="direction_deg",
            label="Direction",
            description="The way the run goes, from +X; its boxes face to "
            "the left of it (0: along +X, facing +Y).",
            default=0.0,
            minimum=-360.0,
            maximum=360.0,
        )
    ),
    _choice(
        "construction",
        "Construction",
        [("frameless", "Frameless"), ("face_frame", "Face frame")],
        "Frameless (European, full overlay), or a 3/4 x 1-1/2 hardwood face "
        "frame with 1/2 in overlay fronts.",
    ),
    _choice(
        "carcass",
        "Carcass",
        [("plywood", "3/4 plywood"), ("melamine", "3/4 melamine")],
        "The carcass and fronts; drawer boxes are 1/2 plywood on 1/4.",
    ),
    _length(
        "wall_bottom_mm",
        "Wall box bottom",
        54.0,
        12.0,
        96.0,
        "A wall box's bottom above the floor: 54 in, 18 in over a 36 in counter.",
    ),
    ListInput(
        kind="list",
        name="boxes",
        label="Boxes",
        description="The run's boxes and fillers, from its start.",
        item_label="Box",
        fields=list(BOX_FIELDS),
        min_items=1,
        max_items=32,
        default=[{"type": "base", "width_mm": _mm(24.0)}],
    ),
]

_ROLES: list[tuple[str, str, str | None]] = [
    ("level", "Level", None),
    ("plane", "Plane", None),
    ("section", "Section", None),
    ("side", "Side", None),
    ("back", "Back", None),
    ("bottom", "Bottom", None),
    ("top", "Top", None),
    ("stretcher", "Stretcher", None),
    ("toe_kick", "Toe kick", None),
    ("shelf", "Shelf", None),
    ("stile", "Stile", "The face frame's uprights."),
    ("rail", "Rail", "The face frame's cross pieces."),
    ("filler", "Filler", None),
    ("door", "Door", None),
    ("drawer_front", "Drawer front", None),
    ("false_front", "False front", None),
    ("drawer_side", "Drawer side", None),
    ("drawer_end", "Drawer front and back", None),
    ("drawer_bottom", "Drawer bottom", None),
]

MANIFEST = PluginManifest(
    id="loft.cabinets",
    version="1.0.0",
    title="Cabinets",
    description="A run of cabinets as one feature, as Mozaik places a run: "
    "base, wall, tall and vanity boxes in US sizes, frameless or face frame, "
    "on a wall's inside face or at a typed position, listed panel by panel "
    "with banding and hardware.",
    inputs=INPUTS,
    members=[
        PluginMemberRole(role=role, title=title, description=help)
        for role, title, help in _ROLES
    ],
)


# --- Layout ------------------------------------------------------------------------


@dataclass(frozen=True)
class Panel:
    """One body in the run's frame (in): a box from ``x0..x1`` (along the
    run), ``y0..y1`` (out from the wall) and ``z0..z1`` (up), less a toe notch
    over ``y >= notch[0]`` and ``z <= notch[1]`` for a notched side."""

    role: str
    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float
    product: str
    material: MaterialKey
    grain: Grain | None = None
    banding: float = 0.0
    banding_material: Literal["plywood", "pvc"] = "plywood"
    hardware: tuple[HardwareCount, ...] = ()
    notch: tuple[float, float] | None = None

    def moved(self, dx: float) -> "Panel":
        return replace(self, x0=_r(self.x0 + dx), x1=_r(self.x1 + dx))


@dataclass(frozen=True)
class Box:
    """One row of the run, resolved (in)."""

    number: int
    type: str
    width: float
    height: float = 0.0
    depth: float = 0.0
    bottom: float = 0.0
    toe: float = 0.0
    fronts: str = "door"
    doors: int = 1
    drawers: int = 0
    drawer_height: float = 6.0
    shelves: int = 0


@dataclass(frozen=True)
class Row:
    """One row of fronts, top first: its kind, its front's and its opening's
    bottom and top (in)."""

    kind: Literal["door", "drawer", "false"]
    z0: float
    z1: float
    oz0: float
    oz1: float


@dataclass(frozen=True)
class Style:
    """The run's construction and carcass."""

    face_frame: bool
    product: str
    material: MaterialKey
    grain: bool
    banding: Literal["plywood", "pvc"]


def _refuse(box: Box | int, why: str) -> PluginError:
    number = box if isinstance(box, int) else box.number
    return PluginError(PLUGIN_INPUT_INVALID, f"Box {number}: {why}", input="boxes")


def read_boxes(inputs: ExpandInputs, wall_bottom: float) -> list[Box]:
    """The ``boxes`` rows resolved to sizes and layouts (checked)."""
    out: list[Box] = []
    for number, row in enumerate(inputs.rows("boxes"), start=1):
        kind = row.choice("type")
        width = _inches(row, "width_mm")
        if kind == "filler":
            out.append(Box(number, kind, width))
            continue
        steps = width / WIDTH_STEP
        if (
            abs(steps - round(steps)) > 1e-6
            or width < MIN_WIDTH - 1e-9
            or width > MAX_WIDTH + 1e-9
        ):
            raise _refuse(number, f"a {kind} box is 9 to 48 in wide, in 3 in steps")
        width = round(steps) * WIDTH_STEP
        choice = row.choice("height")
        sizes = HEIGHTS[kind]
        height = sizes[0] if choice == "standard" else _HEIGHT_OPTIONS[choice]
        if height not in sizes:
            allowed = ", ".join(f"{h:g}" for h in sizes)
            raise _refuse(number, f"a {kind} box is {allowed} in high")
        fronts = row.choice("fronts")
        layouts = FRONTS[kind]
        fronts = layouts[0] if fronts == "standard" else fronts
        if fronts not in layouts:
            raise _refuse(number, f"a {kind} box takes no {fronts.replace('_', ' ')}")
        doors = {"one": 1, "two": 2}.get(row.choice("doors"))
        if doors is None:
            doors = 1 if width <= ONE_DOOR_MAX + 1e-9 else 2
        out.append(
            Box(
                number,
                kind,
                width,
                height,
                DEPTHS[kind],
                wall_bottom if kind == "wall" else 0.0,
                0.0 if kind == "wall" else TOE,
                fronts,
                doors,
                row.count("drawers") if fronts == "drawers" else 0,
                _inches(row, "drawer_height_mm"),
                0 if fronts == "drawers" else row.count("shelves"),
            )
        )
    if all(box.type == "filler" for box in out):
        raise _refuse(1, "a run needs a box, not only fillers")
    return out


def _rows_frameless(box: Box) -> list[Row]:
    z0, z1 = box.bottom + box.toe, box.bottom + box.height
    zone, r, g, f = z1 - z0, REVEAL, GAP, box.drawer_height
    heights: list[tuple[Literal["door", "drawer", "false"], float]]
    if box.fronts == "door":
        heights = [("door", zone - 2 * r)]
    elif box.fronts in ("drawer_door", "false_door"):
        top = "drawer" if box.fronts == "drawer_door" else "false"
        heights = [(top, f), ("door", zone - 2 * r - g - f)]
    elif box.fronts == "drawers":
        n = box.drawers
        if n == 1:
            heights = [("drawer", zone - 2 * r)]
        else:
            rest = (zone - 2 * r - (n - 1) * g - f) / (n - 1)
            heights = [("drawer", f)]
            heights.extend(("drawer", rest) for _ in range(n - 1))
    else:  # stacked doors: the lower's top in line with a base box's door's
        split = BASE_HEIGHT - r - f - g
        heights = [("door", z1 - r - split - g), ("door", split - z0 - r)]
    rows: list[Row] = []
    top = z1 - r
    for index, (kind, h) in enumerate(heights):
        if h <= 1e-9:
            raise _refuse(box, "its fronts leave no room for a door; lower the drawer")
        first, last = index == 0, index == len(heights) - 1
        bottom = top - h
        rows.append(
            Row(
                kind,
                _r(bottom),
                _r(top),
                _r(bottom - (r if last else g / 2)),
                _r(top + (r if first else g / 2)),
            )
        )
        top = bottom - g
    return rows


def _rows_face_frame(box: Box) -> list[Row]:
    z0, z1 = box.bottom + box.toe, box.bottom + box.height
    zone, w, f = z1 - z0, FRAME_WIDTH, box.drawer_height - 2 * OVERLAY
    openings: list[tuple[Literal["door", "drawer", "false"], float]]
    if box.fronts == "door":
        openings = [("door", zone - 2 * w)]
    elif box.fronts in ("drawer_door", "false_door"):
        top = "drawer" if box.fronts == "drawer_door" else "false"
        openings = [(top, f), ("door", zone - 3 * w - f)]
    elif box.fronts == "drawers":
        n = box.drawers
        if n == 1:
            openings = [("drawer", zone - 2 * w)]
        else:
            rest = (zone - (n + 1) * w - f) / (n - 1)
            openings = [("drawer", f)]
            openings.extend(("drawer", rest) for _ in range(n - 1))
    else:  # stacked doors: the lower opening's top a base box's door's
        split = BASE_HEIGHT - w - f - w
        openings = [("door", z1 - w - split - w), ("door", split - z0 - w)]
    rows: list[Row] = []
    top = z1 - w
    for kind, h in openings:
        if h <= 1e-9:
            raise _refuse(box, "its fronts leave no room for a door; lower the drawer")
        bottom = top - h
        rows.append(
            Row(kind, _r(bottom - OVERLAY), _r(top + OVERLAY), _r(bottom), _r(top))
        )
        top = bottom - w
    return rows


def _sheet(
    style: Style,
    role: str,
    box: tuple[float, float, float, float, float, float],
    grain: Grain,
    banding: float = 0.0,
    hardware: tuple[HardwareCount, ...] = (),
    notch: tuple[float, float] | None = None,
) -> Panel:
    x0, x1, y0, y1, z0, z1 = (_r(v) for v in box)
    return Panel(
        role,
        x0,
        x1,
        y0,
        y1,
        z0,
        z1,
        style.product,
        style.material,
        grain if style.grain else None,
        _r(banding),
        style.banding,
        hardware,
        notch,
    )


def _ply(
    role: str, box: tuple[float, float, float, float, float, float], thick: float
) -> Panel:
    x0, x1, y0, y1, z0, z1 = (_r(v) for v in box)
    product = "1/2 plywood" if thick == DRAWER_SIDE else "1/4 plywood"
    grain: Grain = "y" if role == "drawer_side" else "x"
    return Panel(role, x0, x1, y0, y1, z0, z1, product, _PLY, grain)


def box_panels(box: Box, style: Style) -> list[Panel]:
    """One box's panels in its own frame (X from its left side)."""
    W, D, H, zb, toe = box.width, box.depth, box.height, box.bottom, box.toe
    z0, z1 = zb + toe, zb + H
    band = not style.face_frame  # a face frame covers the carcass's edges
    inner = W - 2 * T
    out: list[Panel] = []
    notch = (D - TOE_SETBACK, toe) if toe > 0 else None
    side_band = (z1 - z0) if band else 0.0
    for x0 in (0.0, W - T):
        out.append(
            _sheet(style, "side", (x0, x0 + T, 0, D, zb, z1), "z", side_band, (), notch)
        )
    out.append(_sheet(style, "back", (T, W - T, 0, T, z0, z1), "z"))
    out.append(_sheet(style, "bottom", (T, W - T, T, D, z0, z0 + T), "x", inner * band))
    if box.type in ("base", "vanity"):
        out.append(
            _sheet(
                style,
                "stretcher",
                (T, W - T, D - STRETCHER, D, z1 - T, z1),
                "x",
                inner * band,
            )
        )
        out.append(
            _sheet(style, "stretcher", (T, W - T, T, T + STRETCHER, z1 - T, z1), "x")
        )
    else:
        out.append(
            _sheet(style, "top", (T, W - T, T, D, z1 - T, z1), "x", inner * band)
        )
    if toe > 0:
        y1 = D - TOE_SETBACK
        out.append(_sheet(style, "toe_kick", (T, W - T, y1 - T, y1, 0, toe), "x"))
    rows = _rows_face_frame(box) if style.face_frame else _rows_frameless(box)
    out += _shelves(box, style, rows)
    if style.face_frame:
        out += _frame(box, rows)
    out += _fronts(box, style, rows)
    out += _drawer_boxes(box, style, rows)
    return out


def _shelves(box: Box, style: Style, rows: list[Row]) -> list[Panel]:
    """Shelves spaced evenly in the door bay: from the bottom's top to the
    top's (or stretchers') underside, or under a drawer or false front to
    the drawers' zone (frameless: the box's top less the top fronts'
    heights, casework.md C1; face frame: the door opening's top)."""
    if box.shelves == 0:
        return []
    z0, z1 = box.bottom + box.toe, box.bottom + box.height
    b0 = z0 + T
    if box.fronts in ("drawer_door", "false_door"):
        b1 = rows[1].oz1 if style.face_frame else z1 - box.drawer_height
    else:
        b1 = z1 - T
    n = box.shelves
    clear = (b1 - b0 - n * T) / (n + 1)
    if clear <= 1e-9:
        raise _refuse(box, f"{n} shelves do not fit its door bay")
    W, D = box.width, box.depth
    inner = W - 2 * T - 2 * SHELF_SIDE_CLEARANCE
    out: list[Panel] = []
    for k in range(n):
        s0 = b0 + clear * (k + 1) + T * k
        out.append(
            _sheet(
                style,
                "shelf",
                (
                    T + SHELF_SIDE_CLEARANCE,
                    W - T - SHELF_SIDE_CLEARANCE,
                    T,
                    D - SHELF_SETBACK,
                    s0,
                    s0 + T,
                ),
                "x",
                inner,
            )
        )
    return out


def _frame(box: Box, rows: list[Row]) -> list[Panel]:
    """The face frame: two stiles, then the rails, top down."""
    W, D, w = box.width, box.depth, FRAME_WIDTH
    z0, z1 = box.bottom + box.toe, box.bottom + box.height

    def lumber(role: str, b: tuple[float, float, float, float, float, float]) -> Panel:
        x0, x1, y0, y1, za, zc = (_r(v) for v in b)
        return Panel(role, x0, x1, y0, y1, za, zc, FRAME_PROFILE, FRAME_MATERIAL)

    out = [
        lumber("stile", (0, w, D, D + T, z0, z1)),
        lumber("stile", (W - w, W, D, D + T, z0, z1)),
        lumber("rail", (w, W - w, D, D + T, z1 - w, z1)),
    ]
    for row in rows[:-1]:
        out.append(lumber("rail", (w, W - w, D, D + T, row.oz0 - w, row.oz0)))
    out.append(lumber("rail", (w, W - w, D, D + T, z0, z0 + w)))
    return out


def _fronts(box: Box, style: Style, rows: list[Row]) -> list[Panel]:
    W, D = box.width, box.depth
    if style.face_frame:
        edge, y0 = FRAME_WIDTH - OVERLAY, D + T
    else:
        edge, y0 = REVEAL, D
    out: list[Panel] = []
    for row in rows:
        h = row.z1 - row.z0
        spans = [(edge, W - edge)]
        if row.kind == "door" and box.doors == 2:
            spans = [(edge, W / 2 - GAP / 2), (W / 2 + GAP / 2, W - edge)]
        role = {"door": "door", "drawer": "drawer_front", "false": "false_front"}
        for x0, x1 in spans:
            hardware: tuple[HardwareCount, ...] = ()
            if row.kind == "door":
                hardware = (HardwareCount(key="hinge", quantity=hinges_for(h)),)
            out.append(
                _sheet(
                    style,
                    role[row.kind],
                    (x0, x1, y0, y0 + T, row.z0, row.z1),
                    "z",
                    2 * ((x1 - x0) + h),
                    hardware,
                )
            )
    return out


def _drawer_boxes(box: Box, style: Style, rows: list[Row]) -> list[Panel]:
    """A 1/2 plywood box on a 1/4 bottom behind each drawer front, on the
    longest slide pair that fits the inside depth."""
    drawers = [row for row in rows if row.kind == "drawer"]
    if not drawers:
        return []
    W, D = box.width, box.depth
    length = slide_for(D - T)
    if length is None:
        raise _refuse(box, "it is too shallow for a 12 in drawer slide")
    z_floor = box.bottom + box.toe + T
    z_ceiling = box.bottom + box.height - T
    out: list[Panel] = []
    for row in drawers:
        if style.face_frame:
            bx0, bx1 = FRAME_WIDTH + OVERLAY, W - FRAME_WIDTH - OVERLAY
            bottom = row.oz0 + OVERLAY
            top = row.oz1 - OVERLAY
        else:
            bx0, bx1 = T + SLIDE_CLEARANCE, W - T - SLIDE_CLEARANCE
            top = min(row.oz1, z_ceiling) - DRAWER_TOP_CLEARANCE
            bottom = top - (row.z1 - row.z0 - DRAWER_SIDE_SHORT) - DRAWER_BOTTOM
            if bottom < max(row.oz0, z_floor) - 1e-9:
                raise _refuse(box, "a drawer front is too short for its drawer box")
        side0 = bottom + DRAWER_BOTTOM
        y0 = D - length
        s = DRAWER_SIDE
        out += [
            _ply("drawer_side", (bx0, bx0 + s, y0, D, side0, top), s),
            _ply("drawer_side", (bx1 - s, bx1, y0, D, side0, top), s),
            _ply("drawer_end", (bx0 + s, bx1 - s, D - s, D, side0, top), s),
            _ply("drawer_end", (bx0 + s, bx1 - s, y0, y0 + s, side0, top), s),
        ]
        bottom_panel = _ply(
            "drawer_bottom", (bx0, bx1, y0, D, bottom, side0), DRAWER_BOTTOM
        )
        slides = (HardwareCount(key=slide_key(length), quantity=1),)
        out.append(replace(bottom_panel, hardware=slides))
    return out


def _filler(box: Box, neighbour: Box, style: Style) -> Panel:
    """A filler in line with its neighbour's fronts (frameless) or frame."""
    D = neighbour.depth
    z0 = neighbour.bottom + neighbour.toe
    return _sheet(
        style,
        "filler",
        (0, box.width, D, D + T, z0, neighbour.bottom + neighbour.height),
        "z",
    )


def run_panels(boxes: list[Box], style: Style) -> list[tuple[int, Panel]]:
    """Every panel of the run in its frame, with its box's index (from 0)."""
    out: list[tuple[int, Panel]] = []
    x = 0.0
    for index, box in enumerate(boxes):
        if box.type == "filler":
            later = [b for b in boxes[index + 1 :] if b.type != "filler"]
            earlier = [b for b in boxes[:index] if b.type != "filler"]
            neighbour = (later or earlier[::-1])[0]
            panels = [_filler(box, neighbour, style)]
        else:
            panels = box_panels(box, style)
        out += [(index, p.moved(x)) for p in panels]
        x = _r(x + box.width)
    return out


# --- Placement ----------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """The run's frame in the world (in): its start, its direction along the
    run, out from the wall, and the floor's Z."""

    x: float
    y: float
    along: tuple[float, float]
    out: tuple[float, float]
    base: float

    def plan(self, u: float, v: float) -> tuple[float, float]:
        """The world plan point of run (u, v), unrounded: on a turned run a
        1e-9 in rounding would move each corner off its exact rotation."""
        return (
            self.x + u * self.along[0] + v * self.out[0] + 0.0,
            self.y + u * self.along[1] + v * self.out[1] + 0.0,
        )

    def world(self, grain: Grain) -> tuple[float, float, float]:
        if grain == "z":
            return (0.0, 0.0, 1.0)
        a, b = self.along if grain == "x" else self.out
        return (a + 0.0, b + 0.0, 0.0)


def _wall_spec(inputs: ExpandInputs, ref: FeatureRef) -> WallSpec:
    host = inputs.resolve(ref)
    if not isinstance(host, CustomFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Wall: pick an earlier Wall.", input="wall"
        )
    specs = dict(wall_specs_of(ref.feature_id, host, inputs.earlier, inputs.parameters))
    picked = inputs.segments("wall_segment")
    if None in specs:
        if picked:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Wall line: the wall is one wall, not an outline; leave it empty.",
                input="wall_segment",
            )
        return specs[None]
    if len(picked) != 1 or picked[0] not in specs:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Wall line: pick the line of the outline the run is on.",
            input="wall_segment",
        )
    return specs[picked[0]]


def framing_length(inputs: ExpandInputs, ref: FeatureRef) -> float:
    """The length (in) of the picked wall's framing, along which a 1.0.0 run
    measures its Distance (the 1.0.0 -> 1.1.0 update map reads it)."""
    return _wall_spec(inputs, ref).length


def placement(inputs: ExpandInputs, run_length: float) -> Placement:
    """Where the run's frame is: on the picked wall's inside face, from the
    end measured from, or at the typed position and direction."""
    ref = inputs.optional_feature("wall")
    if ref is None:
        c, s = _cos_sin(inputs.number("direction_deg"))
        return Placement(
            _inches(inputs, "x_mm"),
            _inches(inputs, "y_mm"),
            (c, s),
            (-s + 0.0, c),
            _inches(inputs, "z_mm"),
        )
    wall = _wall_spec(inputs, ref)
    frame = WallFrame.of(wall)
    offset = _inches(inputs, "offset_mm")
    if offset + run_length > wall.length + 1e-9:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            f"Distance: the {run_length:g} in run from {offset:g} in does not "
            f"fit the {wall.length:g} in wall.",
            input="offset_mm",
        )
    from_end = inputs.choice("measure_from") == "end"
    u0 = wall.length - offset if from_end else offset
    sign = -1.0 if from_end else 1.0
    x, y = frame.plan(u0, wall.thickness + _inches(inputs, "gap_mm"))
    along = (sign * frame.along[0] + 0.0, sign * frame.along[1] + 0.0)
    return Placement(_r(x), _r(y), along, frame.across, frame.base)


# --- Emission ----------------------------------------------------------------------


def _loop(points: Sequence[Point2D]) -> list[SketchLine]:
    return [
        SketchLine(
            id=f"e{i + 1}",
            kind="line",
            start=points[i],
            end=points[(i + 1) % len(points)],
        )
        for i in range(len(points))
    ]


def _pt(x_in: float, y_in: float) -> Point2D:
    return Point2D(x=_mm(x_in), y=_mm(y_in))


class _Emitter:
    """Levels, planes, sections and panel extrudes with running indices,
    each member named by its place (``box/2/1``), so an edit that keeps a
    box keeps its members' names."""

    def __init__(self, inputs: ExpandInputs, place: Placement) -> None:
        self.inputs = inputs
        self.place = place
        self.levels: dict[float, FeatureRef | DatumPlaneRef] = {}
        self.counts: dict[str, int] = {}
        self.turned: FeatureRef | None = None

    def _index(self, role: str) -> int:
        n = self.counts.get(role, 0)
        self.counts[role] = n + 1
        return n

    def level(self, z: float) -> Iterator[Member]:
        key = _r(self.place.base + z)
        if key in self.levels:
            return
        if key == 0.0:
            self.levels[key] = DatumPlaneRef(kind="datum_plane", plane="XY")
            return
        name = level_name(key)
        index = self._index("level")
        yield Member(
            "level",
            index,
            DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base="XY", offset_mm=_mm(key)),
            ),
            name=name,
        )
        self.levels[key] = self.inputs.ref("level", index, name)

    def _metadata(self, panel: Panel) -> MemberMetadata:
        return MemberMetadata(
            profile=panel.product,
            material=panel.material,
            grain=None if panel.grain is None else list(self.place.world(panel.grain)),
            banding=(
                None
                if panel.banding <= 0
                else EdgeBanding(
                    length_mm=_mm(panel.banding), material=panel.banding_material
                )
            ),
            hardware=list(panel.hardware) or None,
        )

    def panel(self, panel: Panel, name: str) -> Iterator[Member]:
        if panel.notch is not None:
            yield from self._side(panel, name)
            return
        yield from self.level(panel.z0)
        plane = self.levels[_r(self.place.base + panel.z0)]
        p = self.place
        corners = [
            p.plan(u, v)
            for u, v in (
                (panel.x0, panel.y0),
                (panel.x1, panel.y0),
                (panel.x1, panel.y1),
                (panel.x0, panel.y1),
            )
        ]
        section = f"{panel.role}/{name}"
        s_index = self._index("section")
        yield Member(
            "section",
            s_index,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane,
                    entities=list(_loop([_pt(x, y) for x, y in corners])),
                    constraints=[],
                ),
            ),
            name=section,
        )
        yield Member(
            panel.role,
            self._index(panel.role),
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=self.inputs.ref("section", s_index, section),
                    distance_mm=_mm(_r(panel.z1 - panel.z0)),
                    operation="add",
                    merge=False,
                ),
            ),
            self._metadata(panel),
            name=name,
        )

    def _side(self, panel: Panel, name: str) -> Iterator[Member]:
        """A notched side: its (y, z) profile on the plane across the run at
        its x0, extruded along the run by its thickness."""
        p = self.place
        assert panel.notch is not None
        ny, nz = panel.notch
        profile = [
            (panel.y0, panel.z0),
            (ny, panel.z0),
            (ny, nz),
            (panel.y1, nz),
            (panel.y1, panel.z1),
            (panel.y0, panel.z1),
        ]
        ax, ay = p.along
        section = f"{panel.role}/{name}"
        plane: FeatureRef | DatumPlaneRef
        direction: Literal["normal", "reverse"]
        points: list[Point2D] = []
        origin = p.plan(panel.x0, 0.0)
        if ay == 0.0 or ax == 0.0:
            if ay == 0.0:  # across the run is YZ (normal +X)
                base, offset = "YZ", origin[0]
                direction = "normal" if ax > 0 else "reverse"
            else:  # XZ (normal -Y)
                base, offset = "XZ", -origin[1] + 0.0
                direction = "normal" if ay < 0 else "reverse"
            for v, z in profile:
                wx, wy = p.plan(panel.x0, v)
                points.append(_pt(wy if base == "YZ" else wx, _r(p.base + z)))
            if offset == 0.0:
                plane = DatumPlaneRef(kind="datum_plane", plane=base)
            else:
                index = self._index("plane")
                yield Member(
                    "plane",
                    index,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumOffsetParams(base=base, offset_mm=_mm(offset)),
                    ),
                    name=section,
                )
                plane = self.inputs.ref("plane", index, section)
        else:
            # The kernel's plane through +Z turned from YZ: normal (cos a,
            # sin a, 0) = along the run, sketch x = Z, y = (sin a, -cos a).
            angle = math.degrees(math.atan2(ay, ax)) % 360.0
            if self.turned is None:
                index = self._index("plane")
                yield Member(
                    "plane",
                    index,
                    DatumFeature(
                        type="datum",
                        version=1,
                        params=DatumAngleParams(
                            kind="angle",
                            line=DatumOriginAxisRef(kind="origin_axis", axis="Z"),
                            reference=DatumPlaneRef(kind="datum_plane", plane="YZ"),
                            angle_deg=angle,
                        ),
                    ),
                    name="turned",
                )
                self.turned = self.inputs.ref("plane", index, "turned")
            offset = origin[0] * ax + origin[1] * ay
            index = self._index("plane")
            yield Member(
                "plane",
                index,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetFromParams(
                        kind="offset_from", base=self.turned, offset_mm=_mm(offset)
                    ),
                ),
                name=section,
            )
            plane = self.inputs.ref("plane", index, section)
            direction = "normal"
            for v, z in profile:
                wx, wy = p.plan(panel.x0, v)
                points.append(_pt(_r(p.base + z), wx * ay - wy * ax))
        s_index = self._index("section")
        yield Member(
            "section",
            s_index,
            SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=plane, entities=list(_loop(points)), constraints=[]
                ),
            ),
            name=section,
        )
        yield Member(
            panel.role,
            self._index(panel.role),
            ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=self.inputs.ref("section", s_index, section),
                    distance_mm=_mm(_r(panel.x1 - panel.x0)),
                    operation="add",
                    direction=direction,
                    merge=False,
                ),
            ),
            self._metadata(panel),
            name=name,
        )


def style_of(inputs: ExpandInputs) -> Style:
    carcass = inputs.choice("carcass")
    return Style(
        face_frame=inputs.choice("construction") == "face_frame",
        product=_PRODUCT[carcass],
        material=_MATERIAL[carcass],
        grain=carcass == "plywood",
        banding=_BANDING[carcass],
    )


def expand_placed(
    inputs: ExpandInputs, place_of: Callable[[ExpandInputs, float], Placement]
) -> Iterator[Member]:
    """The run's members, its frame placed by *place_of* (its inputs and the
    run's length): 1.0.0's :func:`placement`, or a later release's."""
    boxes = read_boxes(inputs, _inches(inputs, "wall_bottom_mm"))
    style = style_of(inputs)
    panels = run_panels(boxes, style)
    place = place_of(inputs, sum(box.width for box in boxes))
    emitter = _Emitter(inputs, place)
    ordinal: dict[tuple[int, str], int] = {}
    for box, panel in panels:
        k = ordinal.get((box, panel.role), 0)
        ordinal[(box, panel.role)] = k + 1
        yield from emitter.panel(panel, f"box/{box}/{k}")


def expand(inputs: ExpandInputs) -> Iterator[Member]:
    return expand_placed(inputs, placement)


CABINETS_V1 = Plugin(MANIFEST, expand)
