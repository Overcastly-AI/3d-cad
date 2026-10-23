"""``loft.window`` and ``loft.door`` 1.3.0: picked by call size and drawn
(OPENING-UNITS, RESEARCH §23).

Checked by hand: the US catalogue's codes are their feet and inches and its
rough openings standard framing practice (a window's unit + 1/2 in, a door's
slab + 2 x 2-1/2 in); a picked size frames exactly what 1.2.0 frames for the
same typed size; the unit's two bodies sit where the drawing convention puts
them, in the wall's frame, on an axis wall and on one at 30 degrees; Custom
reads the typed size; "Rough opening only" draws nothing; and older
releases are untouched. B7 with every unit is the ``b7-units`` golden
(``test_b7_units.py``).
"""

import math
import uuid
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, PluginError, canonical_inputs, expand
from loft_plugins.builtin.wall import WallFrame, WallSpec
from loft_wire.datum_angle import DatumAngleParams
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    DatumFeature,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
    SketchFeature,
)
from loft_wire.opening_units import (
    DOOR_CODES,
    OPENING_UNITS,
    OPENING_UNITS_BY_KEY,
    WINDOW_CODES,
    code_size_in,
)
from loft_wire.plugins import ChoiceInput
from loft_wire.sketch import SketchLine

IN = 25.4
WALL = REGISTRY.get("loft.wall", "1.1.0")
WINDOW_1_2 = REGISTRY.get("loft.window", "1.2.0")
DOOR_1_2 = REGISTRY.get("loft.door", "1.2.0")
WINDOW = REGISTRY.get("loft.window", "1.3.0")
DOOR = REGISTRY.get("loft.door", "1.3.0")
WALL_ID = uuid.UUID("00000000-0000-0000-0000-0000000a3040")
OPENING_ID = uuid.UUID("00000000-0000-0000-0000-0000000a3041")

Point = tuple[float, float, float]


# --- The catalogue -----------------------------------------------------------------


def test_a_code_is_feet_and_inches_of_width_then_height() -> None:
    assert code_size_in("3040") == (36, 48)
    assert code_size_in("2030") == (24, 36)
    assert code_size_in("2630") == (30, 36)
    assert code_size_in("3068") == (36, 80)
    assert code_size_in("2468") == (28, 80)
    assert code_size_in("2868") == (32, 80)


def test_the_rough_openings_are_standard_framing_practice() -> None:
    """A window's rough opening is its unit + 1/2 in each way; a door's its
    slab + 2 in wide and 2-1/2 in tall: B2's and B7's typed openings."""
    by = OPENING_UNITS_BY_KEY
    assert (by["window_3040"].ro_width_in, by["window_3040"].ro_height_in) == (
        36.5,
        48.5,
    )
    assert (by["window_2030"].ro_width_in, by["window_2030"].ro_height_in) == (
        24.5,
        36.5,
    )
    assert (by["door_3068"].ro_width_in, by["door_3068"].ro_height_in) == (38, 82.5)
    assert (by["door_2868"].ro_width_in, by["door_2868"].ro_height_in) == (34, 82.5)
    for unit in OPENING_UNITS:
        w, h = code_size_in(unit.code)
        assert (unit.width_in, unit.height_in) == (w, h)
        assert unit.key == f"{unit.kind}_{unit.code}"
    assert {"2030", "3040", "3050"} <= set(WINDOW_CODES)
    assert {"2468", "2868", "3068"} <= set(DOOR_CODES)
    assert len(OPENING_UNITS) == len(OPENING_UNITS_BY_KEY)


# --- The release ---------------------------------------------------------------------


def test_1_3_0_adds_size_and_unit_and_keeps_every_older_input() -> None:
    for new, old in ((WINDOW, WINDOW_1_2), (DOOR, DOOR_1_2)):
        names = [i.name for i in new.manifest.inputs]
        old_names = [i.name for i in old.manifest.inputs]
        assert names[:5] == [
            "host_wall",
            "wall_segment",
            "measure_from",
            "offset_mm",
            "size",
        ]
        assert names[-1] == "draw_unit"
        assert [n for n in names if n not in ("size", "draw_unit")] == old_names
        size = new.manifest.inputs[4]
        assert isinstance(size, ChoiceInput)
        assert size.options[-1].value == "custom"
    window_size = WINDOW.manifest.inputs[4]
    door_size = DOOR.manifest.inputs[4]
    assert isinstance(window_size, ChoiceInput) and isinstance(door_size, ChoiceInput)
    assert window_size.default == "window_3040"
    assert door_size.default == "door_3068"
    assert [o.label for o in door_size.options][:2] == [
        "2068 (2'0\" x 6'8\")",
        "2468 (2'4\" x 6'8\")",
    ]


# --- Expanding on one wall -----------------------------------------------------------


def wall_env(raw: dict[str, Any]) -> CustomFeature:
    return CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": "loft.wall",
                "plugin_version": "1.1.0",
                "inputs": canonical_inputs(WALL.manifest, raw),
            },
        }
    )


def run(
    plugin: Any, raw: dict[str, Any], wall: dict[str, Any] | None = None
) -> list[ExpandedMember]:
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {WALL_ID: wall_env(wall or {})}
    inputs = canonical_inputs(
        plugin.manifest,
        {"host_wall": FeatureRef(kind="feature", feature_id=WALL_ID), **raw},
    )
    return expand(plugin, OPENING_ID, inputs, earlier)


def world(members: list[ExpandedMember], role: str) -> list[Point]:
    """The world corners (in) of *role*'s body: its sketch's OUTER loop (the
    first four lines) at the plane, and swept by the extrude."""
    by_id = {m.id: m.feature for m in members}
    body = next(m for m in members if m.role == role)
    extrude = body.feature
    assert isinstance(extrude, ExtrudeFeature)
    sketch = by_id[extrude.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)

    def plane(ref: Any) -> tuple[Point, Point, Point, Point]:
        """origin, normal, sketch x, sketch y (world)."""
        if isinstance(ref, DatumPlaneRef):
            datum = None
            base, offset = ref.plane, 0.0
        else:
            datum = by_id[ref.feature_id]
            assert isinstance(datum, DatumFeature)
            params = datum.params
            if isinstance(params, DatumOffsetFromParams):
                turned = by_id[params.base.feature_id]
                assert isinstance(turned, DatumFeature)
                assert isinstance(turned.params, DatumAngleParams)
                a = math.radians(turned.params.angle_deg)
                n = (math.cos(a), math.sin(a), 0.0)
                o = params.offset_mm
                return (
                    (n[0] * o, n[1] * o, 0.0),
                    n,
                    (0.0, 0.0, 1.0),
                    (math.sin(a), -math.cos(a), 0.0),
                )
            assert isinstance(params, DatumOffsetParams)
            base, offset = params.base, params.offset_mm
        if base == "XZ":
            return (0.0, -offset, 0.0), (0.0, -1.0, 0.0), (1.0, 0, 0), (0, 0, 1.0)
        assert base == "YZ"
        return (offset, 0.0, 0.0), (1.0, 0.0, 0.0), (0, 1.0, 0), (0, 0, 1.0)

    origin, normal, sx, sy = plane(sketch.params.plane)
    d = extrude.params.distance_mm * (
        -1 if extrude.params.direction == "reverse" else 1
    )
    out: list[Point] = []
    for e in sketch.params.entities[:4]:
        assert isinstance(e, SketchLine)
        x, y = e.start.x, e.start.y
        for h in (0.0, d):
            p = tuple(
                (origin[k] + x * sx[k] + y * sy[k] + h * normal[k]) / IN
                for k in range(3)
            )
            out.append(tuple(round(c, 6) + 0.0 for c in p))  # type: ignore[arg-type]
    return sorted(out)


def corners(
    wall: dict[str, Any],
    u: tuple[float, float],
    v: tuple[float, float],
    z: tuple[float, float],
) -> list[Point]:
    """The world corners (in) of a box in *wall*'s frame."""
    spec = WallSpec.from_inputs(
        ExpandInputs(WALL_ID, canonical_inputs(WALL.manifest, wall))
    )
    frame = WallFrame.of(spec)
    out: list[Point] = []
    for uu in u:
        for vv in v:
            x, y = frame.plan(uu, vv)
            for zz in z:
                p = (x, y, spec.elevation + zz)
                out.append(tuple(round(c, 6) + 0.0 for c in p))  # type: ignore[arg-type]
    return sorted(out)


AXIS_WALL: dict[str, Any] = {"length_mm": 144 * IN}
ANGLED_WALL: dict[str, Any] = {
    "length_mm": 144 * IN,
    "start_x_mm": 10 * IN,
    "start_y_mm": -20 * IN,
    "direction_deg": 30.0,
    "elevation_mm": 11.46875 * IN,
}


@pytest.mark.parametrize("wall", [AXIS_WALL, ANGLED_WALL], ids=["axis", "angled"])
def test_a_2030_is_drawn_in_its_rough_opening(wall: dict[str, Any]) -> None:
    """At 72 from the start, a 2030 frames 24.5 x 36.5 under an 82.5 head
    (sill 46): the unit is 24 x 36 at u 60..84, z 46.25..82.25, its frame
    3.25 deep from the exterior face and its pane 32 x 20 x 1/4 at v
    1.5..1.75, 2 in inside the frame."""
    members = run(WINDOW, {"offset_mm": 72 * IN, "size": "window_2030"}, wall)
    assert [m.role for m in members if m.role in ("frame", "glazing")] == [
        "frame",
        "glazing",
    ]
    assert world(members, "frame") == corners(wall, (60, 84), (0, 3.25), (46.25, 82.25))
    assert world(members, "glazing") == corners(
        wall, (62, 82), (1.5, 1.75), (48.25, 80.25)
    )


@pytest.mark.parametrize("wall", [AXIS_WALL, ANGLED_WALL], ids=["axis", "angled"])
def test_a_3068_door_stands_on_the_base_round_its_slab(wall: dict[str, Any]) -> None:
    """A 3068 at 72 frames 38 x 82.5: the unit is 37.5 x 82 at u 53.25..90.75
    on the wall's base, the frame the wall's 3.5 depth, the 36 x 80 slab 1.75
    thick at the face over a 1.25 threshold."""
    members = run(DOOR, {"offset_mm": 72 * IN}, wall)
    assert world(members, "frame") == corners(wall, (53.25, 90.75), (0, 3.5), (0, 82))
    assert world(members, "slab") == corners(wall, (54, 90), (0, 1.75), (1.25, 81.25))


def test_each_body_carries_the_unit() -> None:
    members = run(WINDOW, {"offset_mm": 72 * IN})
    meta = {m.role: m.metadata for m in members if m.metadata is not None}
    frame, glazing = meta["frame"], meta["glazing"]
    assert frame is not None and glazing is not None
    assert (frame.profile, frame.material) == ("3040", "pvc")
    assert (glazing.profile, glazing.material) == ("3040", "glass")
    assert frame.unit is not None and glazing.unit is not None
    assert (frame.unit.kind, frame.unit.key, frame.unit.counted) == (
        "window",
        "window_3040",
        True,
    )
    assert glazing.unit.counted is False
    door = {m.role: m.metadata for m in run(DOOR, {"offset_mm": 72 * IN})}
    assert door["frame"] is not None and door["frame"].material == "spf_lumber"
    assert door["slab"] is not None and door["slab"].material == "spf_lumber"


def test_custom_reads_the_typed_size_and_is_not_priced() -> None:
    raw = {
        "offset_mm": 72 * IN,
        "size": "custom",
        "width_mm": 30 * IN,
        "height_mm": 40 * IN,
    }
    members = run(WINDOW, raw)
    frame = next(m for m in members if m.role == "frame")
    assert frame.metadata is not None and frame.metadata.unit is not None
    assert frame.metadata.profile == "30 x 40 in"
    assert frame.metadata.unit.key is None
    # Head 82.5, RO 30.5 x 40.5: the unit at z 42.25..82.25.
    assert world(members, "frame") == corners(
        AXIS_WALL, (57, 87), (0, 3.25), (42.25, 82.25)
    )


def test_rough_opening_only_draws_nothing() -> None:
    assert run(WINDOW, {"offset_mm": 72 * IN, "draw_unit": "none"}) == []
    assert run(DOOR, {"offset_mm": 72 * IN, "draw_unit": "none"}) == []


def test_a_custom_door_needs_room_for_its_frame() -> None:
    raw = {
        "offset_mm": 72 * IN,
        "size": "custom",
        "ro_width_allowance_mm": 1.0 * IN,
    }
    with pytest.raises(PluginError, match="does not fit") as refused:
        run(DOOR, raw)
    assert refused.value.input == "ro_width_allowance_mm"
    assert run(DOOR, {**raw, "draw_unit": "none"}) == []


def framing(plugin: Any, raw: dict[str, Any]) -> list[Any]:
    """The wall's members with *plugin*'s opening hosted in it."""
    from loft_plugins import Hosted

    inputs = canonical_inputs(
        plugin.manifest,
        {"host_wall": FeatureRef(kind="feature", feature_id=WALL_ID), **raw},
    )
    m = plugin.manifest
    hosted = Hosted(OPENING_ID, m.id, m.version, "W", ExpandInputs(OPENING_ID, inputs))
    members = expand(
        WALL, WALL_ID, canonical_inputs(WALL.manifest, AXIS_WALL), {}, hosted=(hosted,)
    )
    return [(x.role, x.name, x.feature) for x in members]


@pytest.mark.parametrize(
    ("plugin", "old", "size", "typed"),
    [
        (
            WINDOW,
            WINDOW_1_2,
            "window_3040",
            {"width_mm": 36 * IN, "height_mm": 48 * IN},
        ),
        (
            WINDOW,
            WINDOW_1_2,
            "window_2030",
            {"width_mm": 24 * IN, "height_mm": 36 * IN},
        ),
        (DOOR, DOOR_1_2, "door_3068", {"width_mm": 36 * IN, "height_mm": 80 * IN}),
        (DOOR, DOOR_1_2, "door_2868", {"width_mm": 32 * IN, "height_mm": 80 * IN}),
    ],
)
def test_a_picked_size_frames_what_1_2_0_frames_typed(
    plugin: Any, old: Any, size: str, typed: dict[str, Any]
) -> None:
    at = {"measure_from": "start", "offset_mm": 72 * IN}
    assert framing(plugin, {**at, "size": size}) == framing(old, {**at, **typed})
    assert framing(plugin, {**at, "size": "custom", **typed}) == framing(
        old, {**at, **typed}
    )


def test_an_unknown_size_is_refused_on_its_field() -> None:
    with pytest.raises(PluginError) as refused:
        run(WINDOW, {"offset_mm": 72 * IN, "size": "door_3068"})
    assert refused.value.input == "size"
