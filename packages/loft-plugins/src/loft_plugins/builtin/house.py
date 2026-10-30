"""A house's walls and floor read from their stored inputs (BUILDING-OUTLINE).

What a roof, an opening or another wall reads of a ``loft.wall`` or a
``loft.floor``, for every released version: a 1.0-1.2 wall is one line typed
by its inputs; a 1.3.0 wall may stand on a picked floor (its base is the
floor's top, subfloor included) and may be an OUTLINE wall, one wall per line
of a sketch (:mod:`~loft_plugins.builtin.outline`), joined at the corners. A
1.2.0 floor may fill an outline (a rectangle). Hosting is by inputs, never
by expansions (RESEARCH §23), so these read the features' inputs and the
sketches before them, never their members.

**Outline walls** (Chief Architect's and Revit's exterior wall loop). The
outline is the framing's OUTSIDE face. Walking it clockwise, each line is a
wall framed to its right (the inside). Walls along the first line's direction
run THROUGH: to the corner at an outside corner, and on past it by a wall's
depth at an inside corner, closing it. The others FIT BETWEEN them: shortened
by a wall's depth at an outside corner, to the corner at an inside one. That
is B2's and B7's corner: the front and back walls run the full length, the
sides fit between (buildings.md).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace

from loft_wire.expr import Quantity
from loft_wire.features import AuthoredEnvelope, CustomFeature, FeatureRef
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import PLUGIN_INPUT_INVALID, semver_key
from loft_wire.sheet_goods import SHEET_GOODS_BY_KEY, SheetGood

from loft_plugins.api import ExpandInputs, InputValue, PluginError
from loft_plugins.builtin import floor as floor_v1
from loft_plugins.builtin import slab as slab_v1
from loft_plugins.builtin import wall as wall_v1
from loft_plugins.builtin.outline import (
    Outline,
    check_nameable,
    outline_sketch,
    read_outline,
    unsupported,
)

_DIGITS = 9
#: The releases that read an outline and a floor pick.
WALL_OUTLINE_VERSION = (1, 3, 0)
FLOOR_OUTLINE_VERSION = (1, 2, 0)
#: The floor release that frames across the walls it bears on.
FLOOR_SPAN_VERSION = (1, 3, 0)
#: The floor release that may stand on picked walls' top plates (SECOND-FLOOR).
FLOOR_ON_WALLS_VERSION = (1, 4, 0)


def _at_least(version: str, release: tuple[int, int, int]) -> bool:
    return semver_key(version) >= release


def _with(inputs: ExpandInputs, values: Mapping[str, InputValue]) -> ExpandInputs:
    return replace(inputs, values={**inputs.values, **values})


def stored_inputs(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity] | None = None,
) -> ExpandInputs:
    """A stored custom feature's inputs, with the features before it and
    the part's parameters."""
    return ExpandInputs(
        feature_id, dict(envelope.params.inputs), earlier, parameters=parameters or {}
    )


# --- Floors ------------------------------------------------------------------------


def floor_outline(inputs: ExpandInputs) -> Outline | None:
    """A floor's outline (1.2.0), or ``None`` for a typed rectangle."""
    if "outline" not in inputs.values:
        return None
    ref = inputs.optional_feature("outline")
    if ref is None:
        return None
    outline = read_outline(
        outline_sketch(ref, inputs.earlier, "outline"), "outline", inputs.parameters
    )
    if not outline.is_rectangle:
        raise unsupported(
            "Outline: a floor fills a rectangle (four lines, four outside "
            "corners); other shapes are a later rung.",
            "outline",
        )
    return outline


def floor_values(inputs: ExpandInputs) -> ExpandInputs:
    """A 1.2.0 floor's inputs with its outline written into the typed
    rectangle's (start corner, direction, width, depth), so it frames exactly
    as a typed floor does. The width runs along the outline's first line,
    walked counter-clockwise (the inside on its left), the depth across it,
    so the joist direction follows the drawing (1.3.0 reads the corners:
    :func:`floor_values_v1_3`)."""
    outline = floor_outline(inputs)
    if outline is None:
        return inputs
    first = outline.segments[0]
    # Counter-clockwise, the first line runs end -> start of its clockwise walk.
    corner = first.end
    direction = (first.direction_deg + 180.0) % 360.0
    depth = outline.segments[1].length
    return _with(
        inputs,
        {
            "start_x_mm": corner[0] * MM_PER_INCH,
            "start_y_mm": corner[1] * MM_PER_INCH,
            "direction_deg": direction,
            "width_mm": first.length * MM_PER_INCH,
            "depth_mm": depth * MM_PER_INCH,
        },
    )


def _floor_inches(inputs: ExpandInputs, name: str) -> float:
    return round(inputs.number(name) / MM_PER_INCH, _DIGITS)


def floor_values_v1_3(inputs: ExpandInputs) -> ExpandInputs:
    """A 1.3.0 floor's inputs written as 1.2.0's typed rectangle and joist
    direction (FLOOR-JOIST-SPAN).

    An outline's rectangle is read from its corners, not its first line: the
    start corner is its least X and Y, the width along +X and the depth along
    +Y, so the same house drawn from any corner in either direction frames
    the same floor. *Joists bear on* picks the walls under the rims: Front
    and back (the width's edges; on an outline the walls facing -Y and +Y)
    run the joists along the depth, Left and right along the width, and Long
    walls the longer pair, so the joists span the shorter way (a square
    bears on the front and back)."""
    outline = floor_outline(inputs)
    if outline is None:
        values = inputs
        width = _floor_inches(inputs, "width_mm")
        depth = _floor_inches(inputs, "depth_mm")
    else:
        xs = [segment.start[0] for segment in outline.segments]
        ys = [segment.start[1] for segment in outline.segments]
        x0, y0 = min(xs) + 0.0, min(ys) + 0.0  # + 0.0: never -0.0
        width = round(max(xs) - x0, _DIGITS)
        depth = round(max(ys) - y0, _DIGITS)
        values = _with(
            inputs,
            {
                "start_x_mm": x0 * MM_PER_INCH,
                "start_y_mm": y0 * MM_PER_INCH,
                "direction_deg": 0.0,
                "width_mm": width * MM_PER_INCH,
                "depth_mm": depth * MM_PER_INCH,
            },
        )
    bearing = inputs.choice("joists_bear_on")
    if bearing == "front_back":
        along = "depth"
    elif bearing == "left_right":
        along = "width"
    elif bearing == "long_walls":
        along = "depth" if width >= depth else "width"
    else:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Joists bear on: pick Long walls, Front and back, or Left and right.",
            input="joists_bear_on",
        )
    return _with(values, {"joist_direction": along})


def _wall_corners(spec: wall_v1.WallSpec) -> list[tuple[float, float]]:
    """The plan corners of a wall's framing: its line and its depth to its
    framing side."""
    frame = wall_v1.WallFrame.of(spec)
    t = spec.thickness
    return [frame.plan(u, v) for u in (0.0, spec.length) for v in (0.0, t)]


def floor_on_walls(inputs: ExpandInputs) -> float | None:
    """The plate a 1.4.0 floor's picked walls carry it on (inches above Z 0:
    the top of their top plates), or ``None`` when no wall is picked.

    Every picked wall (an outline's walls are each of its lines) must stand
    under the floor's rectangle, *inputs* being written as 1.1.0's typed
    rectangle, and all of them at one plate height, as Chief Architect's
    Build Floor frames a floor on the walls of the level below and Revit
    hosts it on one level (SECOND-FLOOR)."""
    picks = inputs.features("walls") if "walls" in inputs.values else []
    if not picks:
        return None
    floor = floor_v1.FloorSpec.from_inputs(inputs)
    c, s = floor_v1.cos_sin(floor.direction_deg)
    plates: set[float] = set()
    for ref in picks:
        envelope = inputs.resolve(ref)
        if (
            not isinstance(envelope, CustomFeature)
            or envelope.params.plugin_id != "loft.wall"
        ):
            raise PluginError(
                PLUGIN_INPUT_INVALID, "On walls: pick earlier Walls.", input="walls"
            )
        for _, spec in wall_specs_of(
            ref.feature_id, envelope, inputs.earlier, inputs.parameters
        ):
            plates.add(round(spec.elevation + spec.height, _DIGITS))
            for x, y in _wall_corners(spec):
                dx, dy = x - floor.start_x, y - floor.start_y
                along, left = dx * c + dy * s, -dx * s + dy * c
                if not (
                    -1e-6 <= along <= floor.width + 1e-6
                    and -1e-6 <= left <= floor.depth + 1e-6
                ):
                    raise unsupported(
                        "On walls: a picked wall stands outside the floor; a "
                        "floor bears on walls under it (pick the storey "
                        "below's walls, and its outline or rectangle).",
                        "walls",
                    )
    if len(plates) != 1:
        raise unsupported(
            "On walls: the picked walls' top plates are at different heights; "
            "a floor bears on one plate height.",
            "walls",
        )
    return plates.pop()


def floor_values_v1_4(inputs: ExpandInputs) -> ExpandInputs:
    """A 1.4.0 floor's inputs written as 1.1.0's typed floor: 1.3.0's
    rectangle and span and, on picked walls, their plate as its base
    elevation with no sill plates (its rims and end joists bear on the top
    plates, SECOND-FLOOR)."""
    values = floor_values_v1_3(inputs)
    plate = floor_on_walls(values)
    if plate is None:
        return values
    return _with(values, {"elevation_mm": plate * MM_PER_INCH, "sill_plate": "no"})


def floor_values_of(version: str, inputs: ExpandInputs) -> ExpandInputs:
    """A stored floor's inputs as the typed 1.1.0 floor its release frames."""
    if _at_least(version, FLOOR_ON_WALLS_VERSION):
        return floor_values_v1_4(inputs)
    if _at_least(version, FLOOR_SPAN_VERSION):
        return floor_values_v1_3(inputs)
    if _at_least(version, FLOOR_OUTLINE_VERSION):
        return floor_values(inputs)
    return inputs


@dataclass(frozen=True)
class FloorTop:
    """Where a wall on a floor stands: the top of its subfloor, or of its
    joists without one (inches above Z 0)."""

    spec: floor_v1.FloorSpec
    subfloor: SheetGood | None

    @property
    def top(self) -> float:
        thickness = 0.0 if self.subfloor is None else self.subfloor.thickness_in
        return round(self.spec.elevation + self.spec.framing_top + thickness, _DIGITS)


def floor_of(
    ref: FeatureRef, inputs: ExpandInputs, input_name: str = "floor"
) -> FloorTop:
    """The floor *ref* names (an earlier ``loft.floor``, any release)."""
    envelope = inputs.resolve(ref)
    if (
        not isinstance(envelope, CustomFeature)
        or envelope.params.plugin_id != "loft.floor"
    ):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "On floor: pick an earlier Floor.", input=input_name
        )
    values = stored_inputs(ref.feature_id, envelope, inputs.earlier, inputs.parameters)
    version = envelope.params.plugin_version
    values = floor_values_of(version, values)
    good = None
    if _at_least(version, (1, 1, 0)):
        good = SHEET_GOODS_BY_KEY.get(values.choice("subfloor"))  # type: ignore[call-overload]
    return FloorTop(floor_v1.FloorSpec.from_inputs(values), good)


# --- Walls -------------------------------------------------------------------------


def picked_slab(inputs: ExpandInputs) -> CustomFeature | None:
    """The ``loft.slab`` a wall's On floor names (1.4.0), or ``None``."""
    if "floor" not in inputs.values:
        return None
    ref = inputs.optional_feature("floor")
    if ref is None:
        return None
    envelope = inputs.resolve(ref)
    if isinstance(envelope, CustomFeature) and envelope.params.plugin_id == "loft.slab":
        return envelope
    return None


def _floor_elevation(inputs: ExpandInputs) -> dict[str, InputValue]:
    """The base elevation a 1.3.0 wall on a picked floor stands at, or a
    1.4.0 wall on a picked slab: the slab's top (SLAB)."""
    if "floor" not in inputs.values:
        return {}
    ref = inputs.optional_feature("floor")
    if ref is None:
        return {}
    slab = picked_slab(inputs)
    if slab is not None:
        values = stored_inputs(ref.feature_id, slab, inputs.earlier, inputs.parameters)
        return {"elevation_mm": slab_v1.slab_top(values) * MM_PER_INCH}
    return {"elevation_mm": floor_of(ref, inputs).top * MM_PER_INCH}


def wall_values(inputs: ExpandInputs) -> ExpandInputs:
    """A 1.3.0 wall's inputs with a picked floor's top as its base elevation
    (a line wall then frames exactly as a 1.2.0 wall typed so)."""
    return _with(inputs, _floor_elevation(inputs))


def wall_outline(inputs: ExpandInputs) -> Outline | None:
    """A 1.3.0 wall's outline, or ``None`` for a line wall."""
    if "outline" not in inputs.values:
        return None
    ref = inputs.optional_feature("outline")
    if ref is None:
        return None
    outline = read_outline(
        outline_sketch(ref, inputs.earlier, "outline"), "outline", inputs.parameters
    )
    check_nameable(outline, "outline")
    return outline


@dataclass(frozen=True)
class OutlineWall:
    """One wall of an outline: its line, its spec, and how its two ends meet
    the walls beside it."""

    line_id: str
    spec: wall_v1.WallSpec
    #: The wall runs through (along the first line's direction).
    through: bool
    convex_start: bool
    convex_end: bool


def outline_walls(inputs: ExpandInputs, outline: Outline) -> list[OutlineWall]:
    """The walls of *outline* (module docstring), clockwise from the
    sketch's first line, with *inputs*' stud, height, layout and materials."""
    base = wall_v1.WallSpec.from_inputs(wall_values(inputs))
    t = base.thickness
    first = outline.segments[0].direction
    out: list[OutlineWall] = []
    for k, segment in enumerate(outline.segments):
        d = segment.direction
        through = d in (first, (-first[0], -first[1]))
        convex_start = outline.convex_at_start(k)
        convex_end = outline.convex_at_end(k)
        if through:
            grow_start = 0.0 if convex_start else t
            grow_end = 0.0 if convex_end else t
        else:
            grow_start = -t if convex_start else 0.0
            grow_end = -t if convex_end else 0.0
        length = round(segment.length + grow_start + grow_end, _DIGITS)
        start = (
            round(segment.start[0] - d[0] * grow_start, _DIGITS) + 0.0,
            round(segment.start[1] - d[1] * grow_start, _DIGITS) + 0.0,
        )
        if not 12.0 - 1e-9 <= length <= 960.0 + 1e-9:
            raise unsupported(
                f"Outline: {outline.label(k)} would be {length:g} in long; a wall "
                "is 12 to 960 in.",
                "outline",
            )
        spec = replace(
            base,
            start_x=start[0],
            start_y=start[1],
            direction_deg=segment.direction_deg,
            length=length,
            side="right",
        )
        out.append(
            OutlineWall(segment.line_id, spec, through, convex_start, convex_end)
        )
    return out


def wall_specs_of(
    feature_id: uuid.UUID,
    envelope: CustomFeature,
    earlier: Mapping[uuid.UUID, AuthoredEnvelope],
    parameters: Mapping[str, Quantity] | None = None,
) -> list[tuple[str | None, wall_v1.WallSpec]]:
    """The walls a stored ``loft.wall`` of any release stands for, as a roof,
    an opening or another wall reads them: one line wall (``None``), or one
    per outline line (its sketch id)."""
    inputs = stored_inputs(feature_id, envelope, earlier, parameters)
    if not _at_least(envelope.params.plugin_version, WALL_OUTLINE_VERSION):
        return [(None, wall_v1.WallSpec.from_inputs(inputs))]
    outline = wall_outline(inputs)
    if outline is None:
        return [(None, wall_v1.WallSpec.from_inputs(wall_values(inputs)))]
    return [(w.line_id, w.spec) for w in outline_walls(inputs, outline)]


def is_outline_wall(envelope: AuthoredEnvelope | None) -> bool:
    """Whether *envelope* is a ``loft.wall`` drawn on an outline."""
    return (
        isinstance(envelope, CustomFeature)
        and envelope.params.plugin_id == "loft.wall"
        and _at_least(envelope.params.plugin_version, WALL_OUTLINE_VERSION)
        and envelope.params.inputs.get("outline") is not None
    )
