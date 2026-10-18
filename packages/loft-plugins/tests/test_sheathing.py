"""``loft.wall`` 1.2.0 and ``loft.floor`` 1.1.0: sheathing and subfloor (SHEATHING).

Checked against ``docs/reference-parts/buildings.md`` B2 and B5 and the
BACKLOG's acceptance, typed by hand: B2's four walls in 7/16 OSB are 12
panels with a net area of 45 893 in^2 (20 078.1875 in^3) once the door's
38 x 82.5 and the window's 24.5 x 36.5 are cut out; B5's subfloor is 6
panels, 12 420 in^3. The new versions' framing is the old versions'
expansion member for member (the wall's is WALL-MEMBER-RENUMBER's 1.1.0,
the floor's 1.0.0), so a stored wall or floor and its goldens
cannot move.

The geometry golden ``b5-shed-sheathed`` is B5's floor with its subfloor and
B2's sheathed walls (with the door and window) standing on the subfloor; the
golden test asserts its files are this expansion, so the kernel acceptance
(``services/geometry/tests/test_sheathing_b5.py``) reads files that cannot
drift. Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_sheathing.py``.
"""

import dataclasses
import gzip
import json
import math
import sys
import uuid
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, canonical_inputs, expand
from loft_plugins.builtin.floor import FloorSpec
from loft_plugins.builtin.sheathing import (
    face_plane,
    rect_minus_rects,
    strips,
    subfloor_panels,
    wall_panels,
)
from loft_plugins.builtin.wall import Opening, WallSpec
from loft_wire.cut_list import CutListMember
from loft_wire.datum_angle import DatumAngleParams
from loft_wire.features import (
    MAX_TREE_FEATURES,
    DatumFeature,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.sketch import SketchLine

IN = 25.4
WALL_V1 = REGISTRY.get("loft.wall", "1.0.0")
#: The framing 1.2.0 wraps: WALL-MEMBER-RENUMBER's place-named wall.
WALL_V1_1 = REGISTRY.get("loft.wall", "1.1.0")
WALL = REGISTRY.get("loft.wall", "1.2.0")
FLOOR_V1 = REGISTRY.get("loft.floor", "1.0.0")
FLOOR = REGISTRY.get("loft.floor", "1.1.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
GOLDEN = "b5-shed-sheathed"
#: The kernel sweep's requests (services/geometry/tests/test_sheathing_b5.py).
SWEEP_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "sheathing-sweep.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000005b5")
FLOOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000f500")

#: B2's four walls, clockwise (test_wall.py's), sheathed in 7/16 OSB.
B2_WALLS: dict[str, tuple[uuid.UUID, dict[str, Any]]] = {
    "front": (
        uuid.UUID("00000000-0000-0000-0000-00000000a521"),
        {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN},
    ),
    "left": (
        uuid.UUID("00000000-0000-0000-0000-00000000a522"),
        {"start_y_mm": 3.5 * IN, "direction_deg": 90.0, "length_mm": 113 * IN},
    ),
    "back": (
        uuid.UUID("00000000-0000-0000-0000-00000000a523"),
        {"start_y_mm": 120 * IN, "direction_deg": 0.0, "length_mm": 144 * IN},
    ),
    "right": (
        uuid.UUID("00000000-0000-0000-0000-00000000a524"),
        {
            "start_x_mm": 144 * IN,
            "start_y_mm": 116.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 113 * IN,
        },
    ),
}
OSB = {"sheathing": "osb_7_16"}
#: buildings.md B2's door (front wall, wall-local 72) and window (right side
#: wall, wall-local 56.5), every other input at the defaults.
B2_DOOR: dict[str, Any] = {"offset_mm": 72 * IN}
B2_WINDOW: dict[str, Any] = {"offset_mm": 56.5 * IN}


def hosted(plugin_id: str, name: str, host: uuid.UUID, raw: dict[str, Any]) -> Hosted:
    plugin = REGISTRY.get(plugin_id, "1.0.0")
    feature_id = uuid.uuid5(host, name)
    ref = FeatureRef(kind="feature", feature_id=host)
    inputs = canonical_inputs(plugin.manifest, {"host_wall": ref, **raw})
    return Hosted(
        feature_id, plugin_id, "1.0.0", name, ExpandInputs(feature_id, inputs)
    )


def wall(
    raw: dict[str, Any] | None = None,
    feature_id: uuid.UUID = B2_WALLS["front"][0],
    openings: tuple[Hosted, ...] = (),
    plugin: Any = WALL,
) -> list[ExpandedMember]:
    inputs = canonical_inputs(plugin.manifest, raw or {})
    return expand(plugin, feature_id, inputs, {}, hosted=openings)


def b2(base: float = 0.0, extra: dict[str, Any] | None = None) -> list[ExpandedMember]:
    """B2's four walls with the door and window, on *base*."""
    out: list[ExpandedMember] = []
    for name, (feature_id, raw) in B2_WALLS.items():
        openings: tuple[Hosted, ...] = ()
        if name == "front":
            openings = (hosted("loft.door", "Door 1", feature_id, B2_DOOR),)
        if name == "right":
            openings = (hosted("loft.window", "Window 1", feature_id, B2_WINDOW),)
        out += wall(
            {**raw, "elevation_mm": base * IN, **(extra or OSB)}, feature_id, openings
        )
    return out


def floor(
    raw: dict[str, Any] | None = None, plugin: Any = FLOOR
) -> list[ExpandedMember]:
    return expand(plugin, FLOOR_ID, canonical_inputs(plugin.manifest, raw or {}), {})


def floor_spec(raw: dict[str, Any] | None = None) -> FloorSpec:
    return FloorSpec.from_inputs(
        ExpandInputs(FLOOR_ID, canonical_inputs(FLOOR.manifest, raw or {}))
    )


#: Where B2's walls stand on B5's sheathed floor: the subfloor's top.
SUBFLOOR_TOP = 8.75 + 23 / 32


def golden_expansion() -> list[ExpandedMember]:
    return floor() + b2(SUBFLOOR_TOP)


TITLES = {
    role.role: role.title
    for plugin in (WALL, FLOOR)
    for role in plugin.manifest.members
}


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    expansion = golden_expansion()
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion],
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in expansion if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=TITLES[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def _dump(ms: list[ExpandedMember]) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in ms]


def _loops(
    ms: list[ExpandedMember], role: str
) -> list[tuple[list[list[tuple[float, float]]], ExpandedMember]]:
    """Each *role* body's sketch loops (sketch x, y in inches) and its extrude."""
    by_id = {m.id: m for m in ms}
    out: list[tuple[list[list[tuple[float, float]]], ExpandedMember]] = []
    for m in ms:
        if m.role != role:
            continue
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
        assert len(lines) == len(sketch.params.entities)
        out.append((_split_loops(lines), m))
    return out


def _split_loops(lines: list[SketchLine]) -> list[list[tuple[float, float]]]:
    loops: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    first = None
    for line in lines:
        if first is None:
            first = line.start
        current.append((round(line.start.x / IN, 9), round(line.start.y / IN, 9)))
        if line.end == first:
            loops.append(current)
            current, first = [], None
    assert current == []
    return loops


def _area(loop: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            x0 * y1 - x1 * y0
            for (x0, y0), (x1, y1) in zip(loop, [*loop[1:], loop[0]], strict=True)
        )
        / 2
    )


def _net_area(loops: list[list[tuple[float, float]]]) -> float:
    areas = sorted((_area(loop) for loop in loops), reverse=True)
    return areas[0] - sum(areas[1:])


# --- Old versions stay byte-identical ----------------------------------------------


def test_the_new_versions_are_registered_and_latest() -> None:
    assert REGISTRY.latest("loft.wall").manifest.version == "1.2.0"
    assert REGISTRY.latest("loft.floor").manifest.version == "1.1.0"
    # The old ones are still there, unchanged, for the features pinned to them.
    assert WALL_V1.manifest.version == "1.0.0"
    assert FLOOR_V1.manifest.version == "1.0.0"
    assert [i.name for i in WALL.manifest.inputs][:-1] == [
        i.name for i in WALL_V1.manifest.inputs
    ]
    assert [i.name for i in FLOOR.manifest.inputs][:-1] == [
        i.name for i in FLOOR_V1.manifest.inputs
    ]


def test_an_unsheathed_wall_is_the_1_1_0_wall() -> None:
    """Sheathing None (the default) expands exactly as 1.1.0, door and all."""
    door = (hosted("loft.door", "Door 1", B2_WALLS["front"][0], B2_DOOR),)
    raw = B2_WALLS["front"][1]
    assert _dump(wall(raw, openings=door)) == _dump(
        wall(raw, openings=door, plugin=WALL_V1_1)
    )


def test_a_sheathed_walls_framing_is_the_1_1_0_wall() -> None:
    """The panels come after the framing, which keeps 1.1.0's members and ids."""
    door = (hosted("loft.door", "Door 1", B2_WALLS["front"][0], B2_DOOR),)
    raw = B2_WALLS["front"][1]
    old = _dump(wall(raw, openings=door, plugin=WALL_V1_1))
    new = _dump(wall({**raw, **OSB}, openings=door))
    assert new[: len(old)] == old
    assert {m["role"] for m in new[len(old) :]} <= {
        "sheathing_plane",
        "sheathing_section",
        "sheathing",
    }


def test_an_unfloored_floor_is_the_1_0_0_floor() -> None:
    assert _dump(floor({"subfloor": "none"})) == _dump(floor(plugin=FLOOR_V1))
    old = _dump(floor(plugin=FLOOR_V1))
    new = _dump(floor())
    assert new[: len(old)] == old
    assert {m["role"] for m in new[len(old) :]} == {
        "subfloor_level",
        "subfloor_section",
        "subfloor",
    }


# --- B2's sheathing ---------------------------------------------------------------


def test_b2s_osb_is_12_panels_of_45_893_in2() -> None:
    ms = b2()
    panels = _loops(ms, "sheathing")
    assert len(panels) == 12
    area = sum(_net_area(loops) for loops, _ in panels)
    assert area == pytest.approx(45893, abs=1e-6)
    # The BACKLOG's figure, by hand: four walls' faces less the two ROs.
    assert 2 * 144 * 97.125 + 2 * 113 * 97.125 - 38 * 82.5 - 24.5 * 36.5 == 45893
    for _, m in panels:
        assert isinstance(m.feature, ExtrudeFeature)
        assert m.feature.params.distance_mm == pytest.approx(7 / 16 * IN, abs=1e-12)
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("7/16 OSB", "osb")
    volume = area * 7 / 16
    assert volume == pytest.approx(20078.1875, abs=1e-6)


def test_the_panels_are_48_from_each_walls_start_and_cut_round_the_openings() -> None:
    """Front wall (door, wall-local 53..91 x 0..82.5): 0..48, a U round the
    door in 48..96, 96..144. Right wall (window, wall-local 44.25..68.75 x
    46..82.5): notched 0..48 and 48..96, and 96..113."""
    front = WallSpec.from_inputs(
        ExpandInputs(PART_ID, canonical_inputs(WALL.manifest, B2_WALLS["front"][1]))
    )
    door = Opening("door", "Door 1", 72.0, 38.0, 0.0, 82.5, front.stud)
    regions = wall_panels(front, [door])
    assert [r.outer for r in regions] == [
        [(0.0, 0.0), (48.0, 0.0), (48.0, 97.125), (0.0, 97.125)],
        [
            (48.0, 0.0),
            (53.0, 0.0),
            (53.0, 82.5),
            (91.0, 82.5),
            (91.0, 0.0),
            (96.0, 0.0),
            (96.0, 97.125),
            (48.0, 97.125),
        ],
        [(96.0, 0.0), (144.0, 0.0), (144.0, 97.125), (96.0, 97.125)],
    ]
    assert all(r.holes == [] for r in regions)
    window = Opening("window", "Window 1", 56.5, 24.5, 46.0, 82.5, front.stud)
    side = WallSpec.from_inputs(
        ExpandInputs(PART_ID, canonical_inputs(WALL.manifest, B2_WALLS["right"][1]))
    )
    regions = wall_panels(side, [window])
    assert [r.outer[:2] for r in regions] == [
        [(0.0, 0.0), (48.0, 0.0)],
        [(48.0, 0.0), (96.0, 0.0)],
        [(96.0, 0.0), (113.0, 0.0)],
    ]
    assert [r.area for r in regions] == [
        48 * 97.125 - 3.75 * 36.5,
        48 * 97.125 - 20.75 * 36.5,
        17 * 97.125,
    ]


def test_panels_lie_outside_the_exterior_face() -> None:
    """Front wall (along -X from (144, 0), framing toward +Y): its panels are
    on the XZ plane (Y 0), extruded toward -Y; the back wall's at Y 120,
    toward +Y; the side walls' on YZ at X 0 (toward -X) and X 144 (+X)."""
    planes = {}
    for name, (feature_id, raw) in B2_WALLS.items():
        ms = wall({**raw, **OSB}, feature_id)
        by_id = {m.id: m for m in ms}
        extrude = next(m for m in ms if m.role == "sheathing")
        assert isinstance(extrude.feature, ExtrudeFeature)
        sketch = by_id[extrude.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            planes[name] = (plane.plane, 0.0, extrude.feature.params.direction)
        else:
            datum = by_id[plane.feature_id].feature
            assert isinstance(datum, DatumFeature)
            assert isinstance(datum.params, DatumOffsetParams)
            planes[name] = (
                datum.params.base,
                round(datum.params.offset_mm / IN, 9),
                extrude.feature.params.direction,
            )
    # XZ's normal is -Y and its offset moves it to Y = -offset; YZ's is +X.
    assert planes == {
        "front": ("XZ", 0.0, "normal"),
        "back": ("XZ", -120.0, "reverse"),
        "left": ("YZ", 0.0, "reverse"),
        "right": ("YZ", 144.0, "normal"),
    }


def test_a_turned_walls_panels_sit_on_its_face() -> None:
    """A 30 degree wall's plane is through +Z at 120 degrees from YZ (its
    outward normal), slid to the face; each sketch point maps back to the
    face's world point."""
    raw = {"start_x_mm": 10 * IN, "start_y_mm": 20 * IN, "direction_deg": 30.0, **OSB}
    ms = wall(raw)
    datums = [m for m in ms if m.role == "sheathing_plane"]
    assert len(datums) == 2
    turned, slid = datums[0].feature, datums[1].feature
    assert isinstance(turned, DatumFeature) and isinstance(slid, DatumFeature)
    assert isinstance(turned.params, DatumAngleParams)
    assert turned.params.angle_deg == pytest.approx(120.0, abs=1e-12)
    assert isinstance(slid.params, DatumOffsetFromParams)
    spec = WallSpec.from_inputs(
        ExpandInputs(PART_ID, canonical_inputs(WALL.manifest, raw))
    )
    plane = face_plane(spec)
    a = math.radians(120.0)
    normal = (math.cos(a), math.sin(a))
    # The face line passes through the start: offset = start . normal.
    assert slid.params.offset_mm / IN == pytest.approx(
        10 * normal[0] + 20 * normal[1], abs=1e-12
    )
    # Sketch y along the face is the along-wall distance plus start . along.
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    p = plane.sketch_point(48.0, 10.0)
    assert p.x / IN == pytest.approx(10.0, abs=1e-12)
    assert p.y / IN == pytest.approx(10 * c + 20 * s + 48.0, abs=1e-9)


def test_the_e2e_wall_is_three_4x9_panels() -> None:
    """A default 144 wall with OSB: 3 panels of 48 x 97.125 (3 sheets of 4x9
    by area: 13 986 / 5 184 = 2.70)."""
    panels = _loops(wall(OSB), "sheathing")
    assert len(panels) == 3
    assert [_net_area(loops) for loops, _ in panels] == [48 * 97.125] * 3
    assert math.ceil(3 * 48 * 97.125 / (48 * 108)) == 3


# --- B5's subfloor -----------------------------------------------------------------


def test_b5s_subfloor_is_6_panels_staggered_4_ft() -> None:
    """144 x 120, joists along the depth (Y): rows Y 0..48, 48..96, 96..120;
    96 long across the joists, the middle row starting with a 48."""
    assert subfloor_panels(floor_spec()) == [
        (0.0, 96.0, 0.0, 48.0),
        (96.0, 144.0, 0.0, 48.0),
        (0.0, 48.0, 48.0, 96.0),
        (48.0, 144.0, 48.0, 96.0),
        (0.0, 96.0, 96.0, 120.0),
        (96.0, 144.0, 96.0, 120.0),
    ]
    panels = _loops(floor(), "subfloor")
    assert len(panels) == 6
    assert sum(_net_area(loops) for loops, _ in panels) == 144 * 120
    assert 144 * 120 * Fraction(23, 32) == 12420
    by_id = {m.id: m for m in floor()}
    for _, m in panels:
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        assert isinstance(sketch.params.plane, FeatureRef)
        level = by_id[sketch.params.plane.feature_id].feature
        assert isinstance(level, DatumFeature)
        assert isinstance(level.params, DatumOffsetParams)
        assert level.params.offset_mm / IN == pytest.approx(8.75, abs=1e-12)
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("23/32 plywood", "plywood")


def test_the_subfloor_runs_across_the_joists_either_way() -> None:
    """Joists along the width: the panels' 96 runs along Y."""
    spec = floor_spec({"joist_direction": "width"})
    panels = subfloor_panels(spec)
    assert panels[0] == (0.0, 96.0, 0.0, 48.0)  # (a, b): a is now the depth
    assert spec.span_a == 120 and spec.span_b == 144
    assert sum((a1 - a0) * (b1 - b0) for a0, a1, b0, b1 in panels) == 144 * 120


# --- The panel outline -------------------------------------------------------------


def test_a_cut_inside_a_panel_is_a_hole() -> None:
    (region,) = rect_minus_rects((0, 48, 0, 96), [(10, 30, 40, 70)])
    assert region.outer == [(0, 0), (48, 0), (48, 96), (0, 96)]
    assert region.holes == [[(10, 40), (10, 70), (30, 70), (30, 40)]]
    assert region.area == 48 * 96 - 20 * 30


def test_a_cut_across_a_panel_splits_it() -> None:
    regions = rect_minus_rects((48, 96, 0, 96), [(40, 100, 30, 60)])
    assert [r.outer for r in regions] == [
        [(48, 0), (96, 0), (96, 30), (48, 30)],
        [(48, 60), (96, 60), (96, 96), (48, 96)],
    ]


def test_a_cut_outside_a_panel_leaves_it_whole() -> None:
    (region,) = rect_minus_rects((0, 48, 0, 96), [(50, 60, 0, 80)])
    assert region.outer == [(0, 0), (48, 0), (48, 96), (0, 96)]


def test_strips() -> None:
    assert strips(144.0, 48.0) == [(0, 48), (48, 96), (96, 144)]
    assert strips(113.0, 48.0) == [(0, 48), (48, 96), (96, 113)]
    assert strips(144.0, 96.0, 48.0) == [(0, 48), (48, 144)]
    assert strips(40.0, 96.0, 48.0) == [(0, 40)]
    # No sub-micron sliver: a hair past a joint stays with the last panel.
    assert strips(144.000000002, 48.0) == [(0, 48), (48, 96), (96, 144.000000002)]
    assert strips(143.999999998, 48.0) == [(0, 48), (48, 96), (96, 143.999999998)]


def test_an_opening_a_hair_off_a_joint_takes_the_joint() -> None:
    (region,) = rect_minus_rects((0, 48, 0, 96), [(10, 48.000000001, 40, 70)])
    assert region.outer == [
        (0, 0),
        (48, 0),
        (48, 40),
        (10, 40),
        (10, 70),
        (48, 70),
        (48, 96),
        (0, 96),
    ]
    assert rect_minus_rects((48, 96, 0, 96), [(10, 48.000000001, 40, 70)]) == [
        rect_minus_rects((48, 96, 0, 96), [])[0]
    ]


def test_every_wall_panel_tiles_the_face_less_the_openings() -> None:
    """Over walls of every length 12..300 (step 0.5), the panels tile the
    face exactly, one per started 48 in."""
    spec = WallSpec.from_inputs(
        ExpandInputs(PART_ID, canonical_inputs(WALL.manifest, {}))
    )
    for half in range(24, 601):
        length = half / 2
        s = dataclasses.replace(spec, length=length)
        regions = wall_panels(s, [])
        assert sum(r.area for r in regions) == pytest.approx(length * 97.125, abs=1e-9)
        assert len(regions) == math.ceil(length / 48 - 1e-9)


# --- The kernel sweep ---------------------------------------------------------------

SWEEP_WALL = uuid.UUID("00000000-0000-0000-0000-00000000a5e0")

#: name -> (wall inputs, door inputs or None, window inputs or None), or a
#: floor's inputs. Turned walls (30, 117.3 degrees) with a door and a window
#: across a panel joint, a window inside one panel (a hole), a left-side
#: wall in plywood, a turned floor and one with joists along the width.
SWEEP: dict[str, dict[str, Any]] = {
    "wall-turned30-door-window": {
        "wall": {
            "start_x_mm": 10 * IN,
            "start_y_mm": 20 * IN,
            "direction_deg": 30.0,
            "length_mm": 192 * IN,
            **OSB,
        },
        "door": {"offset_mm": 30 * IN},
        "window": {"offset_mm": 96 * IN},
    },
    "wall-turned117.3-left-plywood-hole": {
        "wall": {
            "start_x_mm": -300.0,
            "direction_deg": 117.3,
            "length_mm": 3000.0,
            "side": "left",
            "elevation_mm": 9 * IN,
            "sheathing": "plywood_15_32",
        },
        "window": {"offset_mm": 72 * IN, "width_mm": 20 * IN},
    },
    "wall-axis-2x6-window-hole": {
        "wall": {
            "start_y_mm": 50 * IN,
            "direction_deg": -90.0,
            "length_mm": 100 * IN,
            "stud_profile": "us_2x6",
            "height_mm": 109.125 * IN,
            **OSB,
        },
        "window": {"offset_mm": 24 * IN, "width_mm": 16 * IN},
    },
    "floor-turned30": {
        "floor": {
            "start_x_mm": 10 * IN,
            "start_y_mm": 20 * IN,
            "direction_deg": 30.0,
            "width_mm": 200 * IN,
            "depth_mm": 130 * IN,
        },
    },
    "floor-width-oc12-nosill": {
        "floor": {
            "width_mm": 150 * IN,
            "depth_mm": 100 * IN,
            "joist_direction": "width",
            "joist_spacing_mm": 12 * IN,
            "sill_plate": "no",
        },
    },
}


def sweep_expansion(case: dict[str, Any]) -> list[ExpandedMember]:
    if "floor" in case:
        return floor(case["floor"])
    openings: list[Hosted] = []
    if "door" in case:
        openings.append(hosted("loft.door", "Door 1", SWEEP_WALL, case["door"]))
    if "window" in case:
        openings.append(hosted("loft.window", "Window 1", SWEEP_WALL, case["window"]))
    return wall(case["wall"], SWEEP_WALL, tuple(openings))


def sweep_fixture() -> str:
    """The sweep's requests as geometry reads them, with each case's panel
    count and their net volume (in^3, from the sketches' loops)."""
    cases: list[dict[str, Any]] = []
    for name, case in SWEEP.items():
        expansion = sweep_expansion(case)
        request = EvaluateTreeRequest(
            part_id=PART_ID,
            tree_version=1,
            features=[
                EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion
            ],
        )
        role = "subfloor" if "floor" in case else "sheathing"
        panels = _loops(expansion, role)
        volume = 0.0
        for loops, m in panels:
            assert isinstance(m.feature, ExtrudeFeature)
            volume += _net_area(loops) * m.feature.params.distance_mm / IN
        cases.append(
            {
                "name": name,
                "bodies": sum(
                    1 for m in expansion if isinstance(m.feature, ExtrudeFeature)
                ),
                "panels": len(panels),
                "panel_volume_in3": round(volume, 6),
                "request": request.model_dump(mode="json"),
            }
        )
    return json.dumps(cases, separators=(",", ":"), sort_keys=True)


def test_the_sweep_fixture_is_the_plugins_expansion() -> None:
    assert gzip.decompress(SWEEP_FIXTURE.read_bytes()).decode() == sweep_fixture()


def test_a_window_inside_one_panel_is_a_hole() -> None:
    """wall-axis-2x6-window-hole: the window (16 + 0.5 wide, wall-local
    15.75..32.25) lies inside the first panel, which is one loop and a hole."""
    panels = _loops(sweep_expansion(SWEEP["wall-axis-2x6-window-hole"]), "sheathing")
    assert [len(loops) for loops, _ in panels] == [2, 1, 1]


# --- The golden --------------------------------------------------------------------


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / GOLDEN / "members.json").read_text() == _members_json(metadata)


def test_the_golden_has_every_member() -> None:
    expansion = golden_expansion()
    bodies = Counter(m.role for m in expansion if isinstance(m.feature, ExtrudeFeature))
    assert bodies["sheathing"] == 12
    assert bodies["subfloor"] == 6
    assert bodies["joist"] == 10
    # The floor's 16, its 6 panels, B2's 64 framing members (door and
    # window framed) and 12 panels.
    assert sum(bodies.values()) == 16 + 6 + 64 + 12


def test_the_longest_sheathed_wall_fits_the_tree_bound() -> None:
    extreme = {
        "length_mm": 960 * IN,
        "stud_spacing_mm": 8 * IN,
        "elevation_mm": 1 * IN,
        **OSB,
    }
    assert len(wall(extreme)) <= MAX_TREE_FEATURES // 3
    big = {"width_mm": 960 * IN, "depth_mm": 960 * IN, "joist_spacing_mm": 8 * IN}
    # An 80 x 80 ft floor at 8 in o.c. is 676 features with its 420 panels'
    # sketches and extrudes: inside the whole tree's bound, not a third of it.
    assert len(floor(big)) <= MAX_TREE_FEATURES


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(_members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
    SWEEP_FIXTURE.write_bytes(gzip.compress(sweep_fixture().encode(), mtime=0))
    sys.stdout.write(f"{SWEEP_FIXTURE.name}: {len(SWEEP)} cases\n")


def test_panels_are_named_by_place_and_keep_their_ids_when_the_door_moves() -> None:
    """Every panel, section and plane is named (``exterior/<col>/<row>``),
    so moving B2's door 24 in keeps each panel's id on the panel at that
    place, as 1.1.0 keeps each stud's (WALL-MEMBER-RENUMBER)."""
    host, raw = B2_WALLS["front"]

    def ids(door: dict[str, Any]) -> dict[str, Any]:
        ms = wall({**raw, **OSB}, host, (hosted("loft.door", "Door 1", host, door),))
        return {m.name or "": m.id for m in ms if m.role == "sheathing"}

    here, moved = ids(B2_DOOR), ids({"offset_mm": 96 * IN})
    assert sorted(here) == ["exterior/0/0", "exterior/1/0", "exterior/2/0"]
    assert here == moved
    named = [m for m in wall({**raw, **OSB}, host) if m.role.startswith("sheathing")]
    assert all(m.name is not None for m in named)


def test_a_window_across_a_strip_splits_it_into_rows() -> None:
    """A window spanning a whole strip leaves a piece below and above it:
    ``exterior/1/0`` and ``exterior/1/1``."""
    host, raw = B2_WALLS["front"]
    window = hosted(
        "loft.window", "Window 1", host, {"offset_mm": 72 * IN, "width_mm": 60 * IN}
    )
    names = [
        m.name for m in wall({**raw, **OSB}, host, (window,)) if m.role == "sheathing"
    ]
    assert names == [
        "exterior/0/0",
        "exterior/1/0",
        "exterior/1/1",
        "exterior/2/0",
    ]


def test_subfloor_panels_are_named_by_row_and_column() -> None:
    names = [m.name for m in floor() if m.role == "subfloor"]
    assert names == [f"row/{r}/{c}" for r in range(3) for c in range(2)]
