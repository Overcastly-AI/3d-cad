"""``loft.roof`` 1.2.0: hip and valley roofs on walls picked as a footprint
(ROOF-VALLEY), and the ripped hip tail (ROOF-HIP-TAIL).

Numbers are typed from ``docs/reference-parts/buildings.md`` ("Hip and valley
conventions", B3 and B4), never read back from the plugin. The geometry
goldens ``b4-l-hip-valley`` and ``b4-wing-48`` are this plugin's expansion on
B4's six walls (``model.json``, member materials applied as documents sends
them) and their members' metadata (``members.json``); the first tests pin the
files, and the kernel sweep's fixture, to the plugin, so
``services/geometry/tests/test_roof_valley_b4.py`` reads files that cannot
drift. Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_roof_valley.py``.
"""

import gzip
import json
import math
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.builtin.roof_valley import MAX_ROOF_MEMBERS, ridge_layout
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    BooleanFeature,
    CustomFeature,
    DatumFeature,
    DatumMidplaneParams,
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
from loft_wire.plugins import PLUGIN_INPUT_INVALID, PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

IN = 25.4
R2 = math.sqrt(2.0)
ROOF = REGISTRY.get("loft.roof", "1.2.0")
ROOF_1_1 = REGISTRY.get("loft.roof", "1.1.0")
ROOF_1_0 = REGISTRY.get("loft.roof", "1.0.0")
WALL = REGISTRY.get("loft.wall", "1.0.0")
GEOMETRY = Path(__file__).resolve().parents[3] / "services" / "geometry"
GOLDENS = GEOMETRY / "goldens"
FIXTURES = GEOMETRY / "tests" / "fixtures"
#: The kernel overlap sweep's requests and walls (test_roof_valley_b4.py).
SWEEP_FIXTURE = FIXTURES / "roof-valley-sweep.json.gz"
#: B4's six walls from loft.wall, for the kernel's wall check.
WALLS_FIXTURE = FIXTURES / "b4-walls.json.gz"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b4")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")

#: A wall as typed into loft.wall: start x, start y (its outer face), direction
#: (deg), length, in inches; framing on the right (inside, walls clockwise).
WallRow = tuple[float, float, float, float]

#: buildings.md B4: outer faces round the L (0,120) (0,240) (240,240)
#: (240,0) (120,0) (120,120); back Y 236.5..240 X 0..240, right X 236.5..240
#: Y 0..236.5, wing front Y 0..3.5 X 120..236.5, wing left X 120..123.5 Y
#: 3.5..120, main front Y 120..123.5 X 0..123.5, left X 0..3.5 Y 123.5..236.5.
B4_WALLS: list[WallRow] = [
    (0, 240, 0, 240),
    (240, 236.5, 270, 236.5),
    (236.5, 0, 180, 116.5),
    (120, 3.5, 90, 116.5),
    (123.5, 120, 180, 123.5),
    (0, 123.5, 90, 113),
]
#: B4's edit: the wing 48 wide (X 192..240).
WING_48_WALLS: list[WallRow] = [
    (0, 240, 0, 240),
    (240, 236.5, 270, 236.5),
    (236.5, 0, 180, 44.5),
    (192, 3.5, 90, 116.5),
    (195.5, 120, 180, 195.5),
    (0, 123.5, 90, 113),
]
#: B2's four walls (B3's bearing), clockwise.
B2_WALLS: list[WallRow] = [
    (144, 0, 180, 144),
    (0, 3.5, 90, 113),
    (0, 120, 0, 144),
    (144, 116.5, 270, 113),
]
HIP = {"style": "hip"}
GOLDEN_WALLS: dict[str, list[WallRow]] = {
    "b4-l-hip-valley": B4_WALLS,
    "b4-wing-48": WING_48_WALLS,
}


def wall_id(index: int) -> uuid.UUID:
    return uuid.UUID(int=0xB4A11 * 256 + index)


def walls(rows: list[WallRow]) -> tuple[list[FeatureRef], dict[uuid.UUID, Any]]:
    """The walls as earlier features, and the references a pick stores."""
    refs: list[FeatureRef] = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for index, (x, y, direction, length) in enumerate(rows):
        inputs = canonical_inputs(
            WALL.manifest,
            {
                "start_x_mm": x * IN,
                "start_y_mm": y * IN,
                "direction_deg": float(direction),
                "length_mm": length * IN,
            },
        )
        feature_id = wall_id(index)
        earlier[feature_id] = CustomFeature.model_validate(
            {
                "type": "custom",
                "version": 1,
                "params": {
                    "plugin_id": "loft.wall",
                    "plugin_version": "1.0.0",
                    "inputs": inputs,
                },
            }
        )
        refs.append(FeatureRef(kind="feature", feature_id=feature_id))
    return refs, earlier


def members(
    raw: dict[str, Any] | None = None, rows: list[WallRow] | None = None
) -> list[ExpandedMember]:
    refs, earlier = walls(rows or [])
    inputs = dict(raw or {})
    if refs:
        inputs["walls"] = refs
    return expand(ROOF, ROOF_ID, canonical_inputs(ROOF.manifest, inputs), earlier)


def golden_request(
    expansion: list[ExpandedMember], part_id: uuid.UUID = PART_ID
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    titles = {role.role: role.title for role in ROOF.manifest.members}
    request = EvaluateTreeRequest(
        part_id=part_id,
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
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    return golden_request(members(HIP, GOLDEN_WALLS[name]))


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def _refusal(raw: dict[str, Any], rows: list[WallRow] | None = None) -> PluginError:
    with pytest.raises(PluginError) as caught:
        members(raw, rows)
    return caught.value


# --- Placing L footprints anywhere (the sweep) ------------------------------------


def l_outline(
    big_a: float, big_b: float, a: float, b: float
) -> list[tuple[float, float]]:
    """A canonical L (or a rectangle when a = 0), counter-clockwise."""
    if a == 0:
        return [(0, 0), (big_a, 0), (big_a, big_b), (0, big_b)]
    return [(a, 0), (big_a, 0), (big_a, big_b), (0, big_b), (0, b), (a, b)]


def placed(
    points: list[tuple[float, float]],
    turns: int,
    mirror: bool,
    offset: tuple[float, float],
) -> list[tuple[float, float]]:
    """*points* turned 90 deg *turns* times (after a mirror), then moved."""
    out: list[tuple[float, float]] = []
    for x, y in points:
        if mirror:
            x, y = y, x
        for _ in range(turns):
            x, y = -y, x
        out.append((round(x + offset[0], 9), round(y + offset[1], 9)))
    return list(reversed(out)) if mirror else out


def wall_rows(ccw: list[tuple[float, float]], width: float = 3.5) -> list[WallRow]:
    """Walls drawn clockwise round *ccw*, butted: at a convex corner the next
    wall starts one wall width past the corner, at a reflex corner one width
    before it (as B4's are)."""
    cw = list(reversed(ccw))
    rows: list[WallRow] = []
    for i, p in enumerate(cw):
        q, prev = cw[(i + 1) % len(cw)], cw[i - 1]
        d = (_sign(q[0] - p[0]), _sign(q[1] - p[1]))
        before = (_sign(p[0] - prev[0]), _sign(p[1] - prev[1]))
        convex = before[0] * d[1] - before[1] * d[0] < 0
        shift = width if convex else -width
        start = (p[0] + d[0] * shift, p[1] + d[1] * shift)
        length = abs(q[0] - start[0]) + abs(q[1] - start[1])
        angle = math.degrees(math.atan2(d[1], d[0])) % 360
        rows.append((start[0], start[1], angle, length))
    return rows


def _sign(value: float) -> int:
    return 0 if value == 0 else (1 if value > 0 else -1)


def wall_boxes(
    rows: list[WallRow], width: float = 3.5
) -> list[tuple[float, float, float, float]]:
    """Each wall's plan rectangle (x0, x1, y0, y1), framing on its right."""
    out: list[tuple[float, float, float, float]] = []
    for x, y, direction, length in rows:
        c = round(math.cos(math.radians(direction)))
        s = round(math.sin(math.radians(direction)))
        ex, ey = x + c * length, y + s * length
        ax, ay = s, -c
        xs = sorted((x, ex, x + ax * width, ex + ax * width))
        ys = sorted((y, ey, y + ay * width, ey + ay * width))
        out.append((xs[0], xs[-1], ys[0], ys[-1]))
    return out


def extra(
    rise: int = 6,
    overhang: float = 12.0,
    spacing: float = 24.0,
    rafter: str = "us_2x6",
    deep: str = "us_2x8",
) -> dict[str, Any]:
    return {
        "style": "hip",
        "pitch": f"rise_{rise}",
        "overhang_mm": overhang * IN,
        "spacing_mm": spacing * IN,
        "rafter_profile": rafter,
        "ridge_profile": deep,
        "hip_profile": deep,
        "valley_profile": deep,
    }


#: The overlap sweep (the DECK float class): name -> (L: A, B, a, b; turns,
#: mirror, offset; inputs). Equal and unequal arms (by exactly the 12 in
#: step), the smallest arms (48 wide, 24 proud), the wider arm just one
#: common longer than wide, 1/12 .. 24/12, overhangs 0, 1/16 and 36, 16,
#: 19.2 and 24 o.c., 2x4 and 2x8 commons, arms within float noise of equal,
#: every orientation, and a rectangle on walls.
SweepCase = tuple[
    tuple[float, float, float, float],
    int,
    bool,
    tuple[float, float],
    dict[str, Any],
]
SWEEP: dict[str, SweepCase] = {
    "l-equal-48-proud-24": ((72, 72, 24, 24), 0, False, (0, 0), extra()),
    "l-equal-short-arm-1-12-oh0": (
        (169.5, 168, 49.5, 48),
        1,
        False,
        (3, 5),
        extra(rise=1, overhang=0),
    ),
    "l-step-12-turned": ((240, 240, 132, 120), 2, False, (-7.25, 10.5), extra()),
    "l-wing-48-12-12-oh1_16": (
        (240, 240, 192, 120),
        3,
        True,
        (0, 0),
        extra(rise=12, overhang=1 / 16, deep="us_2x10"),
    ),
    "l-wing-48-24-12-2x4": (
        (240, 240, 192, 120),
        1,
        False,
        (12, 0),
        extra(rise=24, rafter="us_2x4", deep="us_2x10"),
    ),
    "l-300x260-16oc-mirrored": (
        (300, 260, 150, 110),
        2,
        True,
        (0, 0),
        extra(spacing=16),
    ),
    "l-300x260-19.2oc-oh36-2x8": (
        (300, 260, 150, 110),
        3,
        False,
        (0, 0),
        extra(spacing=19.2, overhang=36, rafter="us_2x8", deep="us_2x10"),
    ),
    "l-tall-wing-9-12": ((200, 300, 80, 200), 0, False, (0, 0), extra(rise=9)),
    "l-float-noise-equal": (
        (240, 240, 120, 120),
        0,
        False,
        (0.1, 1e6 / 3 - 333333.2),
        extra(rise=4, spacing=16),
    ),
    "l-odd-sizes-3-12-oh24": (
        (226.155, 320.39, 91.3, 185.535),
        3,
        False,
        (-41.5, 13.25),
        extra(rise=3, overhang=24, spacing=19.2),
    ),
    "rect-b3-on-walls-turned": ((144, 120, 0, 0), 1, False, (30, -20), extra()),
}


def sweep_case(name: str) -> tuple[list[WallRow], list[ExpandedMember]]:
    dims, turns, mirror, offset, raw = SWEEP[name]
    rows = wall_rows(placed(l_outline(*dims), turns, mirror, offset))
    return rows, members(raw, rows)


def sweep_fixture() -> str:
    """The sweep's requests and walls as geometry reads them (compact JSON)."""
    cases: list[dict[str, Any]] = []
    for name in SWEEP:
        rows, expansion = sweep_case(name)
        request, metadata = golden_request(expansion)
        cases.append(
            {
                "name": name,
                "plate_height": 97.125,
                "walls": [list(box) for box in wall_boxes(rows)],
                "bodies": len(metadata),
                "request": request.model_dump(mode="json"),
            }
        )
    return json.dumps(cases, separators=(",", ":")) + "\n"


def walls_fixture() -> str:
    """B4's six walls from loft.wall: their rows and their expansion."""
    refs, earlier = walls(B4_WALLS)
    expansion: list[ExpandedMember] = []
    for ref in refs:
        wall = earlier[ref.feature_id]
        assert isinstance(wall, CustomFeature)
        expansion += expand(WALL, ref.feature_id, wall.params.inputs, {})
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion],
        linear_deflection=0.1,
    )
    return (
        json.dumps(
            {"walls": B4_WALLS, "request": request.model_dump(mode="json")},
            separators=(",", ":"),
        )
        + "\n"
    )


# --- Reading an expansion ----------------------------------------------------------

Plane = tuple[str, float]  # ("YZ", x) or ("XZ", y) of a member's datum face


def by_id(expansion: list[ExpandedMember]) -> dict[uuid.UUID, ExpandedMember]:
    return {m.id: m for m in expansion}


def plane_of(expansion: list[ExpandedMember], member: ExpandedMember) -> Plane:
    """A rafter's or ridge's datum: a YZ plane at X (extruded +X) or an XZ
    plane at Y (extruded -Y), in inches."""
    ids = by_id(expansion)
    assert isinstance(member.feature, ExtrudeFeature)
    sketch = ids[member.feature.params.profile.feature_id].feature
    assert isinstance(sketch, SketchFeature)
    plane = sketch.params.plane
    if isinstance(plane, DatumPlaneRef):
        return (plane.plane, 0.0)
    datum = ids[plane.feature_id].feature
    assert isinstance(datum, DatumFeature)
    assert isinstance(datum.params, DatumOffsetParams)
    sign = 1 if datum.params.base == "YZ" else -1
    return (datum.params.base, round(sign * datum.params.offset_mm / IN, 9))


def outline(
    expansion: list[ExpandedMember], ref: FeatureRef
) -> list[tuple[float, float]]:
    """A sketch's closed polygon, in inches."""
    sketch = by_id(expansion)[ref.feature_id].feature
    assert isinstance(sketch, SketchFeature)
    lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
    for a, b in zip(lines, [*lines[1:], lines[0]], strict=True):
        assert a.end == b.start
    return [(e.start.x / IN, e.start.y / IN) for e in lines]


def cutter_of(
    expansion: list[ExpandedMember], member: ExpandedMember
) -> list[tuple[float, float]] | None:
    """The plan outline a member is intersected with, or None."""
    ids = by_id(expansion)
    for m in expansion:
        if (
            isinstance(m.feature, BooleanFeature)
            and m.feature.params.target.feature_id == member.id
            and m.feature.params.operation == "intersect"
        ):
            tool = ids[m.feature.params.tool.feature_id].feature
            assert isinstance(tool, ExtrudeFeature)
            return outline(expansion, tool.params.profile)
    return None


def section(
    expansion: list[ExpandedMember], member: ExpandedMember
) -> list[tuple[float, float]]:
    assert isinstance(member.feature, ExtrudeFeature)
    return outline(expansion, member.feature.params.profile)


def bodies(expansion: list[ExpandedMember]) -> Counter[str]:
    return Counter(
        m.role
        for m in expansion
        if isinstance(m.feature, ExtrudeFeature) and m.metadata is not None
    )


def _area(points: list[tuple[float, float]]) -> float:
    n = len(points)
    return abs(
        sum(
            points[i][0] * points[(i + 1) % n][1]
            - points[(i + 1) % n][0] * points[i][1]
            for i in range(n)
        )
        / 2
    )


# --- Fixtures pinned to the plugin -------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_WALLS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


def test_the_sweep_fixture_is_the_plugins_expansion() -> None:
    assert gzip.decompress(SWEEP_FIXTURE.read_bytes()).decode() == sweep_fixture()


def test_the_walls_fixture_is_the_wall_plugins_expansion() -> None:
    assert gzip.decompress(WALLS_FIXTURE.read_bytes()).decode() == walls_fixture()


# --- The version -------------------------------------------------------------------


def test_1_2_is_additive_and_the_latest() -> None:
    """1.2.0 keeps every 1.1.0 input (a stored roof's inputs are a 1.2.0
    roof's), adds the walls pick (a feature list of loft.wall, empty by
    default) and the valley size; 1.0.0 and 1.1.0 stay installed for stored
    roofs. (1.3.0, its members named by place, is what a new Roof is now
    inserted with: test_roof_member_names.py.)"""
    assert REGISTRY.latest("loft.roof").manifest.version == "1.3.0"
    old = {i.name for i in ROOF_1_1.manifest.inputs}
    new = [i.name for i in ROOF.manifest.inputs]
    assert old <= set(new) and set(new) - old == {"walls", "valley_profile"}
    picks = next(i for i in ROOF.manifest.inputs if i.name == "walls")
    assert picks.kind == "features"
    assert picks.plugin_ids == ["loft.wall"] and picks.min_items == 0
    valley = next(i for i in ROOF.manifest.inputs if i.name == "valley_profile")
    assert valley.kind == "choice" and valley.default == "us_2x8"
    stored = canonical_inputs(ROOF_1_1.manifest, {"style": "hip", "pitch": "rise_8"})
    assert "walls" not in canonical_inputs(ROOF.manifest, stored)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"pitch": "rise_8"},
        {"spacing_mm": 16 * IN, "overhang_mm": 0.0},
        {"pitch": "rise_12", "ridge_profile": "us_2x10", "span_mm": 200 * IN},
    ],
)
def test_gable_at_1_2_is_1_0_member_for_member(raw: dict[str, Any]) -> None:
    old = expand(ROOF_1_0, ROOF_ID, canonical_inputs(ROOF_1_0.manifest, raw), {})
    new = members({**raw, "style": "gable"})
    assert [m.model_dump(mode="json") for m in new] == [
        m.model_dump(mode="json") for m in old
    ]


def test_a_gable_on_picked_walls_is_refused() -> None:
    error = _refusal({"style": "gable"}, B2_WALLS)
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "walls"


def test_the_hip_on_b2s_walls_is_the_typed_hip() -> None:
    """Walls picked round B2's rectangle give the typed 1.2.0 hip member for
    member: the footprint is X 0..144, Y 0..120, plate 97.125 x 3.5."""
    typed = members(HIP)
    picked = members(HIP, B2_WALLS)
    assert [m.model_dump(mode="json") for m in picked] == [
        m.model_dump(mode="json") for m in typed
    ]
    assert bodies(typed) == {"common": 6, "jack": 16, "hip": 4, "ridge": 1}


# --- buildings.md B4, member by member ---------------------------------------------


def test_b4_has_the_specs_members() -> None:
    """52 members: 20 commons, 20 hip jacks, 4 valley jacks, 5 hips, 1
    valley, 2 ridges; the jacks and cut commons are intersected with their
    plan outline, each hip and the valley too, then their seats cut."""
    expansion = members(HIP, B4_WALLS)
    assert bodies(expansion) == {
        "common": 20,
        "jack": 20,
        "valley_jack": 4,
        "hip": 5,
        "valley": 1,
        "ridge": 2,
    }
    trims = [m.feature for m in expansion if isinstance(m.feature, BooleanFeature)]
    roles = {m.id: m.role for m in expansion}
    assert Counter(
        (roles[t.params.target.feature_id], t.params.operation) for t in trims
    ) == {
        ("common", "intersect"): 2,
        ("jack", "intersect"): 20,
        ("valley_jack", "intersect"): 4,
        ("hip", "intersect"): 5,
        ("hip", "subtract"): 5,
        ("valley", "intersect"): 1,
        ("valley", "subtract"): 1,
    }


def test_b4_layout_is_the_specs() -> None:
    """Commons: back X 60..180 and right Y 60..180 every 24, main front X 60,
    84, 108 and wing left Y 60, 84, 108, kings on Y 180 (left) and X 180
    (wing front); valley jacks main front X 132, 156 and wing left Y 132,
    156; the ridges X 59.25..180.75 on Y 180 and Y 59.25..179.25 on X 180."""
    expansion = members(HIP, B4_WALLS)
    got = {
        (m.role, m.index): plane_of(expansion, m)
        for m in expansion
        if m.role in ("common", "valley_jack", "ridge")
        and isinstance(m.feature, ExtrudeFeature)
    }
    commons = Counter(p for (role, _), p in got.items() if role == "common")
    want: Counter[Plane] = Counter()
    for x in range(60, 181, 24):  # back
        want[("YZ", x - 0.75)] += 1
    for x in (60, 84, 108, 180):  # main front, the wing front's king
        want[("YZ", x - 0.75)] += 1
    for y in range(60, 181, 24):  # right
        want[("XZ", y + 0.75)] += 1
    for y in (60, 84, 108, 180):  # wing left, the left wall's king
        want[("XZ", y + 0.75)] += 1
    assert commons == want
    valley_jacks = Counter(p for (role, _), p in got.items() if role == "valley_jack")
    assert valley_jacks == {
        ("YZ", 131.25): 1,
        ("YZ", 155.25): 1,
        ("XZ", 132.75): 1,
        ("XZ", 156.75): 1,
    }
    ridges = [m for m in expansion if m.role == "ridge"]
    assert [plane_of(expansion, r) for r in ridges] == [
        ("YZ", 59.25),
        ("XZ", 179.25),
    ]
    lengths = [
        r.feature.params.distance_mm / IN
        for r in ridges
        if isinstance(r.feature, ExtrudeFeature)
    ]
    assert lengths == [pytest.approx(121.5, abs=1e-9), pytest.approx(120, abs=1e-9)]


def test_hip_jacks_sit_12_and_36_from_each_hips_corner() -> None:
    expansion = members(HIP, B4_WALLS)
    jacks = Counter(
        plane_of(expansion, m)
        for m in expansion
        if m.role == "jack" and isinstance(m.feature, ExtrudeFeature)
    )
    want: Counter[Plane] = Counter()
    for x in (12, 36, 204, 228):  # back, both corners
        want[("YZ", x - 0.75)] += 1
    for x in (12, 36):  # main front, from (0, 120)
        want[("YZ", x - 0.75)] += 1
    for x in (132, 156, 204, 228):  # wing front, from (120, 0) and (240, 0)
        want[("YZ", x - 0.75)] += 1
    for y in (132, 156, 204, 228):  # left, from (0, 120) and (0, 240)
        want[("XZ", y + 0.75)] += 1
    for y in (12, 36, 204, 228):  # right, from (240, 0) and (240, 240)
        want[("XZ", y + 0.75)] += 1
    for y in (12, 36):  # wing left, from (120, 0)
        want[("XZ", y + 0.75)] += 1
    assert jacks == want


def _cheek_run(
    expansion: list[ExpandedMember], member: ExpandedMember, ridge_face: float
) -> float:
    """A valley-side member's centre run, from the cheek its plan cutter
    makes at its centre to *ridge_face* (both along its own run)."""
    cutter = cutter_of(expansion, member)
    assert cutter is not None
    slanted = [
        (a, b)
        for a, b in zip(cutter, [*cutter[1:], cutter[0]], strict=True)
        if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9
    ]
    assert len(slanted) == 1  # the cheek: one 45 deg edge
    (a, b) = slanted[0]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    along_x = plane_of(expansion, member)[0] == "XZ"
    return abs(ridge_face - (mid[0] if along_x else mid[1]))


def test_valley_jacks_are_the_specs() -> None:
    """From the valley's face (0.75 off its line, 1.061 along a wall) to the
    ridge's face: runs 46.189 and 22.189, lines 51.641 and 24.808, 26.833
    apart (buildings.md B4)."""
    expansion = members(HIP, B4_WALLS)
    unit = math.hypot(12, 6) / 12
    runs = sorted(
        _cheek_run(expansion, m, 179.25)
        for m in expansion
        if m.role == "valley_jack" and isinstance(m.feature, ExtrudeFeature)
    )
    assert runs == [
        pytest.approx(r, abs=5e-4) for r in (22.189, 22.189, 46.189, 46.189)
    ]
    lines = [r * unit for r in runs]
    assert lines[0] == pytest.approx(24.808, abs=5e-4)
    assert lines[3] == pytest.approx(51.641, abs=5e-4)
    assert lines[3] - lines[0] == pytest.approx(26.833, abs=5e-4)
    for m in expansion:
        if m.role != "valley_jack" or not isinstance(m.feature, ExtrudeFeature):
            continue
        # No birdsmouth: a parallelogram, its bottom above the plate.
        profile = section(expansion, m)
        assert len(profile) == 4 and min(z for _, z in profile) > 97.125


def test_the_commons_whose_tails_cross_the_valley_are_cut_at_its_face() -> None:
    """Main front X 108 and wing left Y 108: the tail is cheek-cut 1.061 past
    the fascia (the valley's face); line 78.474."""
    expansion = members(HIP, B4_WALLS)
    cut = [
        m
        for m in expansion
        if m.role == "common"
        and isinstance(m.feature, ExtrudeFeature)
        and cutter_of(expansion, m) is not None
    ]
    assert sorted(plane_of(expansion, m) for m in cut) == [
        ("XZ", 108.75),
        ("YZ", 107.25),
    ]
    for m in cut:
        # From the cheek (Y or X 109.061 at the centre) to the ridge face.
        run = _cheek_run(expansion, m, 179.25)
        assert run == pytest.approx(70.189, abs=5e-4)
        assert run * math.hypot(12, 6) / 12 == pytest.approx(78.474, abs=5e-4)


def _midplane(expansion: list[ExpandedMember], member: ExpandedMember) -> None:
    assert isinstance(member.feature, ExtrudeFeature)
    assert member.feature.params.extent == "symmetric"
    sketch = by_id(expansion)[member.feature.params.profile.feature_id].feature
    assert isinstance(sketch, SketchFeature)
    plane = sketch.params.plane
    assert isinstance(plane, FeatureRef)
    datum = by_id(expansion)[plane.feature_id].feature
    assert isinstance(datum, DatumFeature)
    assert isinstance(datum.params, DatumMidplaneParams)


def test_hips_and_the_valley_are_on_midplanes() -> None:
    expansion = members(HIP, B4_WALLS)
    lines = [m for m in expansion if m.role in ("hip", "valley")]
    assert Counter(m.role for m in lines) == {"hip": 5, "valley": 1}
    for m in lines:
        _midplane(expansion, m)
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("2x8", "spf_lumber")


def test_the_valley_is_notched_at_the_fascias_corner_and_not_dropped() -> None:
    """Its plan: a V notch on (108, 108) and a double cheek at the ridges'
    inside corner (179.25, 179.25); its top's centreline on the valley line,
    the planes' height at the reflex corner (97.125 + 4.399), not dropped."""
    expansion = members(HIP, B4_WALLS)
    valley = next(m for m in expansion if m.role == "valley")
    plan = cutter_of(expansion, valley)
    assert plan is not None
    rounded = {(round(x, 6), round(y, 6)) for x, y in plan}
    assert (108.0, 108.0) in rounded and (179.25, 179.25) in rounded
    # The notch is concave: its apex is the plan's nearest point to the corner
    # along the valley, its edges run past it on both fascias.
    s = [(x + y) / R2 for x, y in plan]
    apex = (108.0 + 108.0) / R2
    assert min(s) < apex - 0.5
    hap = 5.5 * math.hypot(12, 6) / 12 - 1.75
    profile = section(expansion, valley)
    # The midplane's u is Z: the top's highest point is the valley line at
    # its top (run 59.25 x sqrt 2 + PAST from the corner, rising 0.354 per inch).
    assert max(z for z, _ in profile) > 97.125 + hap + 0.5 * 59.25


@pytest.mark.parametrize(("rise", "drop"), [(6, 0.265), (8, 0.354)])
def test_tails_are_ripped_to_the_commons_depth(rise: int, drop: float) -> None:
    """ROOF-HIP-TAIL: a hip's or valley's tail is ripped parallel to its top,
    to the commons' plumb cut less the drop on its centreline (6/12: 6.149
    - 0.265 = 5.884), stepping to its full depth inside the walls."""
    expansion = members({**HIP, "pitch": f"rise_{rise}"}, B4_WALLS)
    plumb = 5.5 * math.hypot(12, rise) / 12
    full = 7.25 * math.hypot(12 * R2, rise) / (12 * R2)
    ripped = plumb - 0.75 * rise / 12 / R2
    assert ripped == pytest.approx(plumb - drop, abs=5e-4)
    for m in expansion:
        if m.role not in ("hip", "valley") or not isinstance(m.feature, ExtrudeFeature):
            continue
        profile = section(expansion, m)
        assert len(profile) == 6
        depths = sorted(
            {
                round(abs(z1 - z0), 6)
                for (z0, v0), (z1, v1) in zip(
                    profile, [*profile[1:], profile[0]], strict=True
                )
                if abs(v0 - v1) < 1e-9
            }
        )
        # Plumb edges: the tail's (ripped), the step's (full less ripped) and
        # the far end's (full).
        assert depths == sorted(
            {round(ripped, 6), round(full - ripped, 6), round(full, 6)}
        )


def test_b4_is_the_same_in_every_orientation() -> None:
    """B4's walls turned and mirrored frame the same members: the same roles,
    sections and cutters (by area), on whatever axes."""

    def signature(expansion: list[ExpandedMember]) -> list[tuple[str, float, float]]:
        out: list[tuple[str, float, float]] = []
        for m in expansion:
            if not isinstance(m.feature, ExtrudeFeature) or m.metadata is None:
                continue
            cutter = cutter_of(expansion, m)
            out.append(
                (
                    m.role,
                    round(_area(section(expansion, m)), 6),
                    round(_area(cutter), 6) if cutter else 0.0,
                )
            )
        return sorted(out)

    base = signature(members(HIP, B4_WALLS))
    for turns in range(4):
        for mirror in (False, True):
            rows = wall_rows(
                placed(l_outline(240, 240, 120, 120), turns, mirror, (5, 7))
            )
            assert signature(members(HIP, rows)) == base, (turns, mirror)


# --- B4's 48 in wing ---------------------------------------------------------------


def test_the_48_wing_frames_one_hip_valley_cripple() -> None:
    """The wing ridge runs 24; the valley (192, 120)-(216, 144) ends on a hip
    running to the main ridge's end; the main front gets 1 hip-valley cripple
    at X 204, run 21.879, line 24.461, cheek-cut both ends."""
    expansion = members(HIP, WING_48_WALLS)
    assert bodies(expansion) == {
        "common": 25,
        "jack": 13,
        "cripple": 1,
        "hip": 6,
        "valley": 1,
        "ridge": 2,
    }
    cripple = next(
        m
        for m in expansion
        if m.role == "cripple" and isinstance(m.feature, ExtrudeFeature)
    )
    assert plane_of(expansion, cripple) == ("YZ", 203.25)
    plan = cutter_of(expansion, cripple)
    assert plan is not None
    slanted = [
        (a, b)
        for a, b in zip(plan, [*plan[1:], plan[0]], strict=True)
        if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9
    ]
    assert len(slanted) == 2  # a cheek at each end
    ends = sorted((a[1] + b[1]) / 2 for a, b in slanted)
    run = ends[1] - ends[0]
    assert run == pytest.approx(21.879, abs=5e-4)
    assert run * math.hypot(12, 6) / 12 == pytest.approx(24.461, abs=5e-4)
    # The wing's ridge: 24 run (its top 12 in above the planes' eave height).
    ridges = [m for m in expansion if m.role == "ridge"]
    assert [plane_of(expansion, r) for r in ridges] == [("YZ", 59.25), ("XZ", 144.75)]


# --- The layout --------------------------------------------------------------------


def test_the_ridge_layout_is_on_centres_from_the_ridge_end() -> None:
    """B4: commons every 24 from the ridge-end common's centre (60, 84, ...,
    180); the far one flush, a layout common that would overlap it dropped."""
    assert ridge_layout(60, 180, 24, 1.5) == [60, 84, 108, 132, 156, 180]
    assert ridge_layout(60, 84, 24, 1.5) == [60, 84]
    assert ridge_layout(60, 85, 24, 1.5) == [60, 85]  # 84 overlaps 85: dropped
    assert ridge_layout(60, 61.5, 24, 1.5) == [60, 61.5]


def test_spacing_and_pitch_keep_ids_and_determinism() -> None:
    a = [m.model_dump(mode="json") for m in members(HIP, B4_WALLS)]
    assert a == [m.model_dump(mode="json") for m in members(HIP, B4_WALLS)]
    before = [(m.role, m.index, m.id) for m in members(HIP, B4_WALLS)]
    after = [
        (m.role, m.index, m.id) for m in members({**HIP, "pitch": "rise_8"}, B4_WALLS)
    ]
    assert before == after


def test_the_largest_roof_expands_well_inside_the_time_cap() -> None:
    """ROOF-HIP-SIZE: the member cap bounds the work; the biggest L that fits
    it expands in well under the registry's 2 s."""
    rows = wall_rows(l_outline(400, 400, 200, 200))
    start = time.monotonic()
    expansion = members({**HIP, "spacing_mm": 24 * IN}, rows)
    assert time.monotonic() - start < 1.0
    assert sum(bodies(expansion).values()) <= MAX_ROOF_MEMBERS


# --- Refusals ----------------------------------------------------------------------


def _with(rows: list[WallRow], index: int, row: WallRow) -> list[WallRow]:
    return [row if i == index else r for i, r in enumerate(rows)]


@pytest.mark.parametrize(
    ("rows", "words"),
    [
        (B4_WALLS[:5], "5 walls picked"),
        (_with(B4_WALLS, 2, (236.5, 0, 180, 100)), "do not close one loop"),
        (_with(B4_WALLS, 0, (0, 240, 30, 240)), "multiples of 90"),
        (
            wall_rows(
                [
                    (48, 0),
                    (96, 0),
                    (96, 48),
                    (144, 48),
                    (144, 96),
                    (0, 96),
                    (0, 48),
                    (48, 48),
                ]
            ),
            "8 walls picked",
        ),
        (wall_rows(l_outline(240, 240, 130, 120)), "differ by at least 12"),
        (wall_rows(l_outline(240, 240, 200, 120)), "at least 48 in wide"),
        (wall_rows(l_outline(240, 240, 120, 20)), "24 in proud"),
        (wall_rows(l_outline(800, 240, 680, 120)), "over 720 in"),
        (wall_rows(l_outline(121, 120, 0, 0)), "plus one rafter"),
    ],
)
def test_footprints_this_rung_cannot_frame_are_refused(
    rows: list[WallRow], words: str
) -> None:
    error = _refusal(HIP, rows)
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "walls"
    assert words in error.message


def test_a_wall_framed_outside_the_outline_is_refused() -> None:
    refs, earlier = walls(B4_WALLS)
    wall = earlier[refs[1].feature_id]
    assert isinstance(wall, CustomFeature)
    flipped = wall.params.model_copy(
        update={"inputs": {**wall.params.inputs, "side": "left"}}
    )
    earlier[refs[1].feature_id] = wall.model_copy(update={"params": flipped})
    raw = canonical_inputs(ROOF.manifest, {**HIP, "walls": refs})
    with pytest.raises(PluginError) as caught:
        expand(ROOF, ROOF_ID, raw, earlier)
    assert caught.value.input == "walls" and "flip its" in caught.value.message


def test_walls_on_different_plates_are_refused() -> None:
    refs, earlier = walls(B4_WALLS)
    wall = earlier[refs[3].feature_id]
    assert isinstance(wall, CustomFeature)
    taller = wall.params.model_copy(
        update={"inputs": {**wall.params.inputs, "height_mm": 109.125 * IN}}
    )
    earlier[refs[3].feature_id] = wall.model_copy(update={"params": taller})
    raw = canonical_inputs(ROOF.manifest, {**HIP, "walls": refs})
    with pytest.raises(PluginError) as caught:
        expand(ROOF, ROOF_ID, raw, earlier)
    assert caught.value.input == "walls" and "different heights" in caught.value.message


def test_a_pick_that_is_not_a_wall_is_refused() -> None:
    refs, earlier = walls(B4_WALLS)
    raw = canonical_inputs(
        ROOF.manifest,
        {
            **HIP,
            "walls": [*refs[:5], FeatureRef(kind="feature", feature_id=uuid.uuid4())],
        },
    )
    with pytest.raises(PluginError) as caught:
        expand(ROOF, ROOF_ID, raw, earlier)
    assert caught.value.code == PLUGIN_INPUT_INVALID and caught.value.input == "walls"
    with pytest.raises(PluginError, match="twice"):
        canonical_inputs(ROOF.manifest, {**HIP, "walls": [refs[0], refs[0]]})


def test_a_valley_shallower_than_the_commons_plumb_cut_is_refused() -> None:
    error = _refusal({**HIP, "valley_profile": "us_2x6"}, B4_WALLS)
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "valley_profile"
    # A rectangle has no valley: its size is not read.
    assert members({**HIP, "valley_profile": "us_2x6"}, B2_WALLS)


def test_a_roof_of_too_many_members_is_refused() -> None:
    """ROOF-HIP-SIZE: 1.1.0's largest typed hip (480 x 720 at 12 o.c., 201
    members) is refused at 1.2.0, naming the spacing."""
    error = _refusal(
        {
            **HIP,
            "span_mm": 480 * IN,
            "length_mm": 720 * IN,
            "spacing_mm": 12 * IN,
            "ridge_profile": "us_2x8",
        }
    )
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "spacing_mm"
    assert str(MAX_ROOF_MEMBERS) in error.message


def test_a_typed_hip_shorter_than_its_span_is_refused() -> None:
    error = _refusal({**HIP, "length_mm": 121 * IN})
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "length_mm"


if __name__ == "__main__":
    for name in sorted(GOLDEN_WALLS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    SWEEP_FIXTURE.write_bytes(gzip.compress(sweep_fixture().encode(), mtime=0))
    sys.stdout.write(f"{SWEEP_FIXTURE.name}: {len(SWEEP)} cases\n")
    WALLS_FIXTURE.write_bytes(gzip.compress(walls_fixture().encode(), mtime=0))
    sys.stdout.write(f"{WALLS_FIXTURE.name}: {len(B4_WALLS)} walls\n")
