"""Ceilings: gypsum board hung from a gable's ceiling joists (GYPSUM-SHEETS,
RESEARCH §23).

Revit's Ceiling is an element of its own, its boundary found from the room's
walls; Chief Architect's ceiling surface carries a gypsum layer; drywall
crews hang a ceiling first, across the joists, in 4x12 sheets with every end
joint on a joist (GA-216). ``loft.ceiling`` 1.0.0 is that: a feature after
the roof, which picks it, and hangs one board layer under its ceiling joists.

* **Where.** Under the joists (``loft.roof`` 1.6.0 and later, a gable on an
  outline wall, Ceiling joists Beside each common): the board's top on the
  joists' underside, which is the plates' top, inside the walls' finished
  faces (their framing, or their inside gypsum's face). A partition of an
  Interior wall on the same walls that reaches the board (B10's are as tall
  as the walls) is cut out with its gypsum, as the ceiling stops at it; a
  lower one is passed over.
* **Courses.** Across the joists: each course is a sheet's 48 in width
  along them, laid from the low wall (the front, for a ridge along X), the
  last a rip. Along a course the sheets run from the low end wall; a sheet
  that does not reach the far wall ends on the centre of the farthest joist
  it reaches, so the next starts there (B7: 277 in is 140 + 137, the joint
  on the joist at X 145.5).
* **Product.** 1/2 in sag-resistant ceiling board (the default) or 5/8 in
  Type X, from 4x12 sheets (the default) or 4x8. Each panel names the sheet
  it is hung from, so the cut list buys them as cut from it
  (``MemberMetadata.sheet``).

Refused (each says what to change): a roof that is not a gable on an
outline wall, one before 1.6.0, one with Ceiling joists None or with joists
that could not be framed, and joists farther apart than a sheet is long.

The feature is new, so nothing stored gains a ceiling: no update adds one
(PLUGIN-UPDATE-ALL), as an update adds no siding.
"""

import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from loft_wire.expr import Quantity
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    DatumFeature,
    DatumOffsetParams,
    FeatureRef,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    ChoiceOption,
    FeatureReferenceInput,
    PluginManifest,
    PluginMemberRole,
    semver_key,
)
from loft_wire.sheet_goods import (
    SHEET_GOODS_BY_KEY,
    SHEET_SIZES_BY_KEY,
    SheetGood,
    SheetSizeKey,
)
from loft_wire.sketch import Point2D

from loft_plugins.api import ExpandInputs, Member, Plugin, PluginError
from loft_plugins.builtin import house, sheathing
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.interior_wall import (
    INTERIOR_WALL,
    host_of,
    partitions_of,
)
from loft_plugins.builtin.roof import (
    STYLE_GABLE,
    GablePlace,
    inches,
    rafter_for,
)
from loft_plugins.builtin.roof_ceiling import (
    CEILING_BESIDE,
    joist_misfit,
    joist_positions,
)
from loft_plugins.builtin.roof_gable import GABLE_STUDS, clear_of_gables

CEILING = "loft.ceiling"
ROOF = "loft.roof"
#: The roof release that frames ceiling joists, and the one that clears
#: them off framed gable-end walls.
JOISTS_VERSION = (1, 6, 0)
GABLE_ENDS_VERSION = (1, 7, 0)
#: A course's width along the joists (in): a sheet's, hung across them.
COURSE = 48.0
_DIGITS = 9
_TOL = 1e-6


def _r(value: float) -> float:
    return round(value, _DIGITS) + 0.0


def _mm(value: float) -> float:
    return value * MM_PER_INCH


def _refuse(message: str, name: str = "roof") -> PluginError:
    return PluginError(PLUGIN_INPUT_UNSUPPORTED, message, input=name)


# --- The layout (pure, inches) ---------------------------------------------------------

#: A rectangle ``(a0, a1, b0, b1)``: ``a`` along the ridge (across the
#: joists), ``b`` along the joists.
Rect = tuple[float, float, float, float]


def sheet_runs(
    first: float, last: float, joists: Sequence[float], length: float
) -> list[tuple[float, float]]:
    """A course's sheets along ``a`` from *first* to *last*: each as long as
    a sheet (*length*) reaches, ended on the centre of the farthest of the
    *joists* (centres) it reaches unless it reaches *last*. ``ValueError``
    when no joist lies within a sheet of a start."""
    out: list[tuple[float, float]] = []
    start = first
    while last - start > length + _TOL:
        reach = [c for c in joists if start + _TOL < c <= start + length + _TOL]
        if not reach:
            raise ValueError(start)
        end = _r(max(reach))
        out.append((start, end))
        start = end
    out.append((start, last))
    return out


def ceiling_regions(
    room: Rect,
    joists: Sequence[float],
    length: float,
    cuts: Sequence[Rect] = (),
) -> list[tuple[str, sheathing.Region]]:
    """The ceiling's panels in ``(a, b)``: courses of :data:`COURSE` from
    ``b0``, each cut into sheets (:func:`sheet_runs`) less *cuts*, named
    ``<course>/<sheet>/<k>``."""
    a0, a1, b0, b1 = room
    runs = sheet_runs(a0, a1, joists, length)
    out: list[tuple[str, sheathing.Region]] = []
    for row, (v0, v1) in enumerate(sheathing.strips(b1 - b0, COURSE)):
        for col, (u0, u1) in enumerate(runs):
            pieces = sheathing.rect_minus_rects(
                (u0, u1, _r(b0 + v0), _r(b0 + v1)), cuts
            )
            pieces.sort(
                key=lambda r: (min(y for _, y in r.outer), min(x for x, _ in r.outer))
            )
            out += [(f"{row}/{col}/{k}", r) for k, r in enumerate(pieces)]
    return out


# --- Reading the roof, the walls and the partitions ------------------------------------


@dataclass(frozen=True)
class Under:
    """What a ceiling hangs under: the plates' top (the joists' underside),
    the room inside the walls' finished faces in ``(a, b)``, the joists'
    centres along ``a``, whether ``a`` is world X, and the partitions'
    footprints (with their gypsum) that reach the board."""

    plate: float
    room: Rect
    joists: tuple[float, ...]
    along_x: bool
    partitions: tuple[tuple[Rect, float], ...]


def _gable_of(
    roof: ExpandInputs, earlier: Mapping[uuid.UUID, AuthoredEnvelope]
) -> tuple[uuid.UUID, ExpandInputs, list[house.OutlineWall], list[str]]:
    """The roof's outline wall: its feature, inputs, walls and the two lines
    that define the slope; refused unless the roof is a gable on it."""
    picks = roof.features("walls")
    outlines = [p for p in picks if house.is_outline_wall(roof.resolve(p))]
    if len(picks) != 1 or len(outlines) != 1:
        raise _refuse(
            "Roof: a ceiling hangs from a gable's ceiling joists on an outline "
            "wall; pick a roof whose Walls is one outline wall."
        )
    ref = outlines[0]
    envelope = earlier.get(ref.feature_id)
    assert isinstance(envelope, CustomFeature)
    wall_inputs = house.stored_inputs(
        ref.feature_id, envelope, earlier, roof.parameters
    )
    outline = house.wall_outline(wall_inputs)
    assert outline is not None
    if roof.choice("style") != STYLE_GABLE or not outline.is_rectangle:
        raise _refuse(
            "Roof: a ceiling hangs from a gable's ceiling joists (a hip frames "
            "none yet); pick a gable."
        )
    slope = roof.segments("slope_walls")
    if len(slope) != 2:
        raise _refuse("Roof: its gable names no two walls that define the slope.")
    return ref.feature_id, wall_inputs, house.outline_walls(wall_inputs, outline), slope


def _partition_rects(
    wall_id: uuid.UUID,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity],
) -> list[tuple[tuple[float, float, float, float], float]]:
    """Each partition of every Interior wall on the walls *wall_id*, as its
    plan box ``(x0, x1, y0, y1)`` with its gypsum, and its top."""
    out: list[tuple[tuple[float, float, float, float], float]] = []
    for fid, other in earlier.items():
        if not isinstance(other, CustomFeature) or other.params.plugin_id != (
            INTERIOR_WALL
        ):
            continue
        theirs = house.stored_inputs(fid, other, earlier, parameters)
        ref = theirs.optional_feature("host_wall")
        if ref is None or ref.feature_id != wall_id:
            continue
        found = partitions_of(
            theirs, host_of(ref, earlier, parameters), earlier, parameters
        )
        g = 0.0 if found.finish is None else found.finish.thickness_in
        for p in found.layout.partitions:
            frame = wall_v1.WallFrame.of(p.spec)
            points = [
                frame.plan(u, v)
                for u in (0.0, p.spec.length)
                for v in (-g, p.spec.thickness + g)
            ]
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            box = (_r(min(xs)), _r(max(xs)), _r(min(ys)), _r(max(ys)))
            out.append((box, _r(p.spec.elevation + p.spec.height)))
    return out


def under(inputs: ExpandInputs) -> Under:
    """What the ceiling's roof pick hangs it under (:class:`Under`)."""
    ref = inputs.feature("roof")
    envelope = inputs.resolve(ref)
    if not isinstance(envelope, CustomFeature) or envelope.params.plugin_id != ROOF:
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Roof: pick an earlier Roof.", input="roof"
        )
    version = semver_key(envelope.params.plugin_version)
    if version < JOISTS_VERSION:
        raise _refuse(
            f"Roof: Roof {envelope.params.plugin_version} frames no ceiling "
            "joists; update it to 1.6.0 or later."
        )
    roof = house.stored_inputs(
        ref.feature_id, envelope, inputs.earlier, inputs.parameters
    )
    if roof.choice("ceiling_joists") != CEILING_BESIDE:
        raise _refuse(
            "Roof: its Ceiling joists is None; set it to Beside each common to "
            "hang a ceiling from them."
        )
    wall_id, wall_inputs, walls, slope = _gable_of(roof, inputs.earlier)
    spec = walls[0].spec
    plate = _r(spec.elevation + spec.height)
    t = spec.thickness
    by_line = {w.line_id: w for w in walls}
    if any(line not in by_line for line in slope):
        raise _refuse("Roof: its Defines slope names a line that is not a wall.")
    eave = by_line[slope[0]].spec
    along_x = abs(round(eave.direction_deg % 180.0, 6)) == 0.0
    xs = [w.spec.start_x for w in walls] + [
        w.spec.start_x + w.spec.length * wall_v1.WallFrame.of(w.spec).along[0]
        for w in walls
    ]
    ys = [w.spec.start_y for w in walls] + [
        w.spec.start_y + w.spec.length * wall_v1.WallFrame.of(w.spec).along[1]
        for w in walls
    ]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span, length = (y1 - y0, x1 - x0) if along_x else (x1 - x0, y1 - y0)
    place = GablePlace(_r(x0), _r(y0), along_x)
    rafter = rafter_for(
        int(roof.choice("pitch").removeprefix("rise_")),
        roof.lumber("rafter_profile"),
        roof.lumber("ridge_profile"),
        _r(span),
        plate,
        t,
        inches("overhang_mm", roof),
    )
    if joist_misfit(roof, rafter) is not None:
        raise _refuse(
            "Roof: its ceiling joists could not be framed (they would pass the "
            "ridge board), so there is nothing to hang a ceiling from."
        )
    clear: list[tuple[float, float]] = []
    if version >= GABLE_ENDS_VERSION and roof.choice("gable_ends") == GABLE_STUDS:
        ends = [w for w in walls if w.line_id not in slope]
        clear = clear_of_gables(ends, place)
    tj = roof.lumber("ceiling_joist_profile").thickness_in
    centres = tuple(
        _r(at + tj / 2) for _, at in joist_positions(roof, _r(length), place, clear)
    )
    good = (
        SHEET_GOODS_BY_KEY.get(wall_inputs.choice("finish"))  # type: ignore[call-overload]
        if "finish" in wall_inputs.values
        else None
    )
    g = 0.0 if good is None else good.thickness_in
    inner = (_r(x0 + t + g), _r(x1 - t - g), _r(y0 + t + g), _r(y1 - t - g))
    room = inner if along_x else (inner[2], inner[3], inner[0], inner[1])
    partitions = tuple(
        ((box if along_x else (box[2], box[3], box[0], box[1])), top)
        for box, top in _partition_rects(wall_id, inputs.earlier, inputs.parameters)
    )
    return Under(plate, room, centres, along_x, partitions)


# --- loft.ceiling 1.0.0 -----------------------------------------------------------------


def _good(inputs: ExpandInputs) -> SheetGood:
    good = SHEET_GOODS_BY_KEY.get(inputs.choice("finish"))  # type: ignore[call-overload]
    if good is None or good.material != "gypsum":
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Board: pick a gypsum board.", input="finish"
        )
    return good


def _sheet(inputs: ExpandInputs) -> SheetSizeKey:
    key = inputs.choice("finish_sheet").removeprefix("sheet_")
    if key not in ("4x8", "4x12"):
        raise PluginError(
            PLUGIN_INPUT_INVALID, f"{key!r} is not a gypsum sheet.", input="finish_sheet"
        )
    return key  # type: ignore[return-value]


def expand_v1(inputs: ExpandInputs) -> Iterator[Member]:
    """The ceiling's level at the board's underside, then each panel: its
    outline sketch on the level and its extrude up to the joists."""
    good = _good(inputs)
    sheet = _sheet(inputs)
    found = under(inputs)
    bottom = _r(found.plate - good.thickness_in)
    cuts = [box for box, top in found.partitions if top > bottom + _TOL]
    try:
        regions = ceiling_regions(
            found.room,
            found.joists,
            SHEET_SIZES_BY_KEY[sheet].length_in,
            cuts,
        )
    except ValueError:
        raise _refuse(
            f"Roof: its ceiling joists are more than a {sheet} sheet apart, so "
            "a sheet's end would land between them; hang 4x12 sheets or close "
            "the joist spacing.",
            "finish_sheet",
        ) from None
    level = Member(
        "ceiling_level",
        0,
        DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(base="XY", offset_mm=_mm(bottom)),
        ),
        name="underside",
    )
    yield level
    plane: FeatureRef = inputs.ref("ceiling_level", 0, "underside")
    for index, (name, region) in enumerate(regions):
        loops = [
            [
                Point2D(x=_mm(a), y=_mm(b))
                if found.along_x
                else Point2D(x=_mm(b), y=_mm(a))
                for a, b in loop
            ]
            for loop in (region.outer, *region.holes)
        ]
        yield from sheathing.panel_members(
            inputs,
            ("ceiling_section", "ceiling"),
            index,
            plane,
            loops,
            good,
            False,
            f"panel/{name}",
            sheet,
        )


MANIFEST_V1 = PluginManifest(
    id=CEILING,
    version="1.0.0",
    title="Ceiling",
    description="Gypsum board hung under a gable's ceiling joists, across them "
    "in 48 in courses with every end joint on a joist, stopped at the walls' "
    "finished faces and the partitions (Revit Ceiling, Chief Architect).",
    inputs=[
        FeatureReferenceInput(
            kind="feature",
            name="roof",
            label="Roof",
            description="The gable whose ceiling joists the board hangs from: "
            "it finds the room inside its walls and the partitions on them.",
            feature_types=["custom"],
            plugin_ids=[ROOF],
        ),
        ChoiceInput(
            kind="choice",
            name="finish",
            label="Board",
            description="1/2 in sag-resistant ceiling board spans 24 in "
            "joists (GA-216); 5/8 in Type X where a rating asks for it.",
            options=[
                ChoiceOption(
                    value="gypsum_ceiling_1_2", label="1/2 ceiling gypsum (sag-resistant)"
                ),
                ChoiceOption(value="gypsum_5_8", label="5/8 gypsum (Type X)"),
            ],
            default="gypsum_ceiling_1_2",
        ),
        ChoiceInput(
            kind="choice",
            name="finish_sheet",
            label="Gypsum sheets",
            description="The sheet the ceiling is hung from, across the "
            "joists: its length is each panel's longest.",
            options=[
                ChoiceOption(value="sheet_4x12", label="4x12"),
                ChoiceOption(value="sheet_4x8", label="4x8"),
            ],
            default="sheet_4x12",
        ),
    ],
    members=[
        PluginMemberRole(role="ceiling_level", title="Ceiling level"),
        PluginMemberRole(role="ceiling_section", title="Ceiling section"),
        PluginMemberRole(
            role="ceiling",
            title="Ceiling",
            description="One ceiling board panel, the partitions cut out.",
        ),
    ],
)

CEILING_V1 = Plugin(MANIFEST_V1, expand_v1)

__all__ = [
    "CEILING_V1",
    "Under",
    "ceiling_regions",
    "sheet_runs",
    "under",
]
