"""``loft.wall`` 1.0.0: B2's four walls, no openings, from four Wall features
(STUD-WALL).

Layouts are checked against ``docs/reference-parts/buildings.md`` B2, typed
from the spec by hand. The geometry goldens ``b2-walls-no-openings-16oc`` and
``-24oc`` are four walls' expansions (``model.json``, with the member
materials documents sends) and their members' metadata (``members.json``);
the first test asserts the files are exactly that, so the geometry acceptance
(``services/geometry/tests/test_walls_b2.py``) reads files that cannot drift.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_wall.py``.
"""

import dataclasses
import json
import math
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, canonical_inputs, expand
from loft_plugins.builtin.wall import WallFrame, WallSpec, stud_centres
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    MAX_TREE_FEATURES,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.sketch import SketchLine

IN = 25.4
WALL = REGISTRY.get("loft.wall", "1.0.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
DEFAULT_SPEC = WallSpec.from_inputs(
    ExpandInputs(PART_ID, canonical_inputs(WALL.manifest, {}))
)

#: B2's four walls, drawn clockwise in plan (exterior on the left, framing to
#: the right): front along -X from (144, 0), left side along +Y from
#: (0, 3.5), back along +X from (0, 120), right side along -Y from
#: (144, 116.5). Name -> (feature id, raw inputs in inches x 25.4).
B2_WALLS: dict[str, tuple[uuid.UUID, dict[str, Any]]] = {
    "front": (
        uuid.UUID("00000000-0000-0000-0000-00000000a111"),
        {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN},
    ),
    "left": (
        uuid.UUID("00000000-0000-0000-0000-00000000a112"),
        {"start_y_mm": 3.5 * IN, "direction_deg": 90.0, "length_mm": 113 * IN},
    ),
    "back": (
        uuid.UUID("00000000-0000-0000-0000-00000000a113"),
        {"start_y_mm": 120 * IN, "direction_deg": 0.0, "length_mm": 144 * IN},
    ),
    "right": (
        uuid.UUID("00000000-0000-0000-0000-00000000a114"),
        {
            "start_x_mm": 144 * IN,
            "start_y_mm": 116.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 113 * IN,
        },
    ),
}

#: The 30 degree wall: the default 144 wall from (10, 20), turned 30 degrees
#: (checked against an independent build123d script in the geometry tests).
WALL_30_ID = uuid.UUID("00000000-0000-0000-0000-00000000a130")
WALL_30: dict[str, Any] = {
    "start_x_mm": 10 * IN,
    "start_y_mm": 20 * IN,
    "direction_deg": 30.0,
}


def members(
    raw: dict[str, Any] | None = None, feature_id: uuid.UUID | None = None
) -> list[ExpandedMember]:
    inputs = canonical_inputs(WALL.manifest, raw or {})
    return expand(WALL, feature_id or B2_WALLS["front"][0], inputs, {})


def b2(spacing: float = 16.0) -> dict[str, list[ExpandedMember]]:
    return {
        name: members({**raw, "stud_spacing_mm": spacing * IN}, feature_id)
        for name, (feature_id, raw) in B2_WALLS.items()
    }


#: golden name -> its walls' expansions.
GOLDEN_WALLS: dict[str, Callable[[], dict[str, list[ExpandedMember]]]] = {
    "b2-walls-no-openings-16oc": lambda: b2(16.0),
    "b2-walls-no-openings-24oc": lambda: b2(24.0),
    "plugin-wall-v1-144-30deg": lambda: {"wall": members(WALL_30, WALL_30_ID)},
}


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request (member materials applied, as documents
    sends them) and its members' cut-list metadata."""
    expansion = [m for ms in GOLDEN_WALLS[name]().values() for m in ms]
    titles = {role.role: role.title for role in WALL.manifest.members}
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
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def corners(
    expansion: list[ExpandedMember],
) -> dict[tuple[str, int], tuple[list[tuple[float, float]], float, float]]:
    """Each body's plan corners (in, in sketch order) and its z0, z1, from its
    section sketch, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: dict[tuple[str, int], tuple[list[tuple[float, float]], float, float]] = {}
    for m in expansion:
        if not isinstance(m.feature, ExtrudeFeature):
            continue
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            assert plane.plane == "XY"
            z0 = 0.0
        else:
            level = by_id[plane.feature_id].feature
            assert isinstance(level, DatumFeature)
            assert isinstance(level.params, DatumOffsetParams)
            assert level.params.base == "XY"
            z0 = level.params.offset_mm
        lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
        assert len(lines) == 4 == len(sketch.params.entities)
        for a, b in zip(lines, lines[1:] + lines[:1], strict=True):
            assert a.end == b.start  # a closed loop
        z1 = z0 + m.feature.params.distance_mm
        out[(m.role, m.index)] = (
            [(e.start.x / IN, e.start.y / IN) for e in lines],
            round(z0 / IN, 9),
            round(z1 / IN, 9),
        )
    return out


def boxes(expansion: list[ExpandedMember]) -> dict[tuple[str, int], tuple[float, ...]]:
    """Each axis-aligned body's box in inches: x0, x1, y0, y1, z0, z1."""
    out: dict[tuple[str, int], tuple[float, ...]] = {}
    for key, (plan, z0, z1) in corners(expansion).items():
        xs = [round(x, 9) for x, _ in plan]
        ys = [round(y, 9) for _, y in plan]
        assert len(set(xs)) == 2 and len(set(ys)) == 2, key  # axis-aligned
        out[key] = (min(xs), max(xs), min(ys), max(ys), z0, z1)
    return out


def _volume(box: tuple[float, ...]) -> float:
    x0, x1, y0, y1, z0, z1 = box
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


# --- Goldens -----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_WALLS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- B2, coordinate by coordinate --------------------------------------------------


def test_the_default_wall_is_b2s_144_wall_at_the_origin() -> None:
    got = boxes(members())
    assert Counter(role for role, _ in got) == {
        "stud": 10,
        "top_plate": 2,
        "bottom_plate": 1,
    }
    studs = [0.75, *range(16, 129, 16), 143.25]
    for i, x in enumerate(studs):
        assert got[("stud", i)] == (x - 0.75, x + 0.75, -3.5, 0, 1.5, 94.125)
    assert got[("top_plate", 0)] == (0, 144, -3.5, 0, 94.125, 95.625)
    assert got[("top_plate", 1)] == (0, 144, -3.5, 0, 95.625, 97.125)
    assert got[("bottom_plate", 0)] == (0, 144, -3.5, 0, 0, 1.5)


def test_b2_walls_are_the_specs() -> None:
    """buildings.md B2 with no openings: every bound typed from the spec."""
    walls = {name: boxes(ms) for name, ms in b2().items()}
    # Plates: front and back full 144 along X; sides 113 between them.
    plates = {
        "front": (0, 144, 0, 3.5),
        "back": (0, 144, 116.5, 120),
        "left": (0, 3.5, 3.5, 116.5),
        "right": (140.5, 144, 3.5, 116.5),
    }
    for name, plan in plates.items():
        got = walls[name]
        assert got[("bottom_plate", 0)] == (*plan, 0, 1.5), name
        assert got[("top_plate", 0)] == (*plan, 94.125, 95.625), name
        assert got[("top_plate", 1)] == (*plan, 95.625, 97.125), name
    # Studs from each wall's start: 0.75, then every 16, an end stud flush.
    long_layout: list[float] = [0.75, *range(16, 129, 16), 143.25]
    short_layout: list[float] = [0.75, *range(16, 97, 16), 112.25]
    # name -> (start along the wall's axis, its sense, across bounds, layout)
    starts: dict[str, tuple[float, float, float, float, list[float]]] = {
        "front": (144, -1, 0, 3.5, long_layout),
        "back": (0, 1, 116.5, 120, long_layout),
        "left": (3.5, 1, 0, 3.5, short_layout),
        "right": (116.5, -1, 140.5, 144, short_layout),
    }
    for name, (start, sense, lo, hi, layout) in starts.items():
        got = walls[name]
        assert Counter(role for role, _ in got)["stud"] == len(layout), name
        for i, u in enumerate(layout):
            c = start + sense * u
            along = (c - 0.75, c + 0.75)
            box = (*along, lo, hi) if name in ("front", "back") else (lo, hi, *along)
            assert got[("stud", i)] == (*box, 1.5, 94.125), (name, i)
    assert sum(Counter(r for r, _ in w)["stud"] for w in walls.values()) == 36
    volume = sum(_volume(b) for w in walls.values() for b in w.values())
    assert volume == pytest.approx(25601.625, abs=1e-6)


def test_the_24oc_edit_gives_26_studs() -> None:
    walls = {name: boxes(ms) for name, ms in b2(24.0).items()}
    studs = {n: Counter(r for r, _ in w)["stud"] for n, w in walls.items()}
    assert studs == {"front": 7, "back": 7, "left": 6, "right": 6}
    front = sorted(walls["front"][("stud", i)][0] + 0.75 for i in range(7))
    assert front == [0.75, 24, 48, 72, 96, 120, 143.25]  # from X 144, mirrored
    volume = sum(_volume(b) for w in walls.values() for b in w.values())
    assert volume == pytest.approx(20738.8125, abs=1e-6)


def test_metadata_is_plain_library_names() -> None:
    expansion = members()
    bodies = [m for m in expansion if isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is not None for m in bodies)
    by_role = {
        (m.role, m.metadata.profile, m.metadata.material) for m in bodies if m.metadata
    }
    assert by_role == {
        ("stud", "2x4", "spf_lumber"),
        ("top_plate", "2x4", "spf_lumber"),
        ("bottom_plate", "2x4", "southern_pine_pt"),
    }
    helpers = [m for m in expansion if not isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is None for m in helpers)


def test_roles_emit_in_the_cut_list_order() -> None:
    order = [m.role for m in members() if isinstance(m.feature, ExtrudeFeature)]
    assert list(dict.fromkeys(order)) == ["stud", "top_plate", "bottom_plate"]


# --- Determinism and stable ids ----------------------------------------------------


def test_the_expansion_is_deterministic() -> None:
    a = [m.model_dump(mode="json") for m in members()]
    b = [m.model_dump(mode="json") for m in members()]
    assert a == b


def test_member_ids_survive_the_spacing_edit() -> None:
    before = {(m.role, m.index): m.id for m in members()}
    after = {(m.role, m.index): m.id for m in members({"stud_spacing_mm": 24 * IN})}
    assert set(after) < set(before)
    for key in [("stud", 0), ("top_plate", 1), ("bottom_plate", 0)]:
        assert before[key] == after[key]


# --- Layout and placement rules ----------------------------------------------------


def test_stud_layout() -> None:
    assert stud_centres(144, 16, 1.5) == [0.75, *range(16, 129, 16), 143.25]
    assert stud_centres(113, 16, 1.5) == [0.75, 16, 32, 48, 64, 80, 96, 112.25]
    assert len(stud_centres(144, 24, 1.5)) == 7
    assert len(stud_centres(113, 24, 1.5)) == 6
    assert stud_centres(12, 16, 1.5) == [0.75, 11.25]


def test_a_single_top_plate_lengthens_the_studs() -> None:
    got = boxes(members({"top_plate": "single"}))
    assert ("top_plate", 1) not in got
    assert got[("stud", 0)][4:] == (1.5, 95.625)
    assert got[("top_plate", 0)][4:] == (95.625, 97.125)


def test_a_2x6_wall_is_5_5_deep() -> None:
    got = boxes(members({"stud_profile": "us_2x6"}))
    assert got[("bottom_plate", 0)][2:4] == (-5.5, 0)
    assert got[("stud", 0)][2:4] == (-5.5, 0)


def test_the_framing_side_flips_across_the_line() -> None:
    got = boxes(members({"side": "left"}))
    assert got[("bottom_plate", 0)][2:4] == (0, 3.5)


def test_the_elevation_lifts_every_member() -> None:
    got = boxes(members({"elevation_mm": 12 * IN}))
    assert got[("bottom_plate", 0)][4:] == (12, 13.5)
    assert got[("top_plate", 1)][4:] == (107.625, 109.125)
    levels = [m for m in members({"elevation_mm": 12 * IN}) if m.role == "level"]
    assert len(levels) == 4  # base, stud bottoms, two top plates


def test_a_30_degree_wall_is_the_axis_wall_turned() -> None:
    """Every corner is the 0 degree wall's corner rotated 30 degrees about
    the start (hand rotation, cos 30 = sqrt(3)/2, sin 30 = 1/2)."""
    start = (10.0, 20.0)
    straight = corners(members({}))
    turned = corners(members(WALL_30))
    c, s = math.sqrt(3) / 2, 0.5
    assert straight.keys() == turned.keys()
    for key, (plan, z0, z1) in straight.items():
        got_plan, got_z0, got_z1 = turned[key]
        assert (got_z0, got_z1) == (z0, z1)
        for (x, y), (gx, gy) in zip(plan, got_plan, strict=True):
            assert gx == pytest.approx(start[0] + x * c - y * s, abs=1e-12)
            assert gy == pytest.approx(start[1] + x * s + y * c, abs=1e-12)


def test_the_frame_is_exact_on_the_axes() -> None:
    for degrees, along in [
        (0.0, (1.0, 0.0)),
        (90.0, (0.0, 1.0)),
        (-90.0, (0.0, -1.0)),
        (180.0, (-1.0, 0.0)),
        (360.0, (1.0, 0.0)),
    ]:
        spec = dataclasses.replace(DEFAULT_SPEC, direction_deg=degrees)
        assert WallFrame.of(spec).along == along


def test_b2_walls_do_not_overlap() -> None:
    """No two bodies of the four walls interpenetrate (exact box test; the
    geometry acceptance repeats it on the kernel's bodies)."""
    for spacing in (16.0, 24.0):
        items = [
            ((name, *key), box)
            for name, ms in b2(spacing).items()
            for key, box in boxes(ms).items()
        ]
        for i, (ka, a) in enumerate(items):
            for kb, b in items[i + 1 :]:
                overlap = all(
                    min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-9 for k in (0, 2, 4)
                )
                assert not overlap, (ka, kb)


def test_the_longest_densest_wall_fits_the_tree_bound() -> None:
    extreme = {
        "length_mm": 960 * IN,
        "stud_spacing_mm": 8 * IN,
        "elevation_mm": 1 * IN,
    }
    assert len(members(extreme)) <= MAX_TREE_FEATURES // 3


if __name__ == "__main__":
    for name in sorted(GOLDEN_WALLS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
