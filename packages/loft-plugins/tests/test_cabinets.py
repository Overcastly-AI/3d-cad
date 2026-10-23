"""``loft.cabinets`` 1.0.0: a cabinet run as one feature (CASEWORK, RESEARCH §23).

Checked by hand against ``docs/reference-parts/casework.md``: C1's B24 is its
panel table to the 1/64 in (typed below from the table, never from the
plugin), 3 526.66796875 in^3 with 282.4375 in (23.54 ft) of banding, two
hinges and one pair of 22 in slides; 24 -> 27 in is 3 820.10546875 in^3 and
303.4375 in with the same hardware; the face-frame B24 is worked by hand
here. C2's runs stand on B7's left wall (B10's partitions are not built:
INTERIOR-WALLS) with the backs at its gypsum line, X 6, touching nothing;
B24 -> B21 moves only the last box. C3's V3021 is typed and worked by hand.

The geometry goldens are written from here and pinned by this module:
regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_cabinets.py`` (then
``npx prettier --write`` the members.json files). Their kernel
acceptance is ``services/geometry/tests/test_casework.py``.
"""

import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.builtin.cabinets import hinges_for, slide_for
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    DatumFeature,
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
from loft_wire.plugins import ListInput
from loft_wire.sketch import SketchLine

sys.path.insert(0, str(Path(__file__).parent))
from test_b7_units import b7_units
from test_building_outline import WALLS_ID, boxes, overlaps

IN = 25.4
CABINETS = REGISTRY.get("loft.cabinets", "1.0.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-00000000c101")
WALL_RUN_ID = uuid.UUID("00000000-0000-0000-0000-00000000c102")
TITLES = {role.role: role.title for role in CABINETS.manifest.members}

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1


def cabinets(
    raw: dict[str, Any],
    earlier: dict[uuid.UUID, AuthoredEnvelope] | None = None,
    feature_id: uuid.UUID = RUN_ID,
) -> list[ExpandedMember]:
    inputs = canonical_inputs(CABINETS.manifest, raw)
    return expand(CABINETS, feature_id, inputs, earlier or {})


def box(kind: str, width: float, **fields: Any) -> dict[str, Any]:
    return {"type": kind, "width_mm": width * IN, **fields}


# --- Bodies, placed in the world ----------------------------------------------------


def _area(points: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(points, points[1:] + points[:1], strict=True)
        )
        / 2
    )


def placed(
    members: list[ExpandedMember],
) -> list[tuple[str, str | None, str | None, Bounds, float]]:
    """Each extrude as (role, profile, material, its world box (in), its
    volume (in^3)), from its sketch's plane, loop and distance: what the
    kernel builds. Axis planes only (an angled run is the kernel test's)."""
    by_id = {m.id: m.feature for m in members}
    out: list[tuple[str, str | None, str | None, Bounds, float]] = []
    for m in members:
        if not isinstance(m.feature, ExtrudeFeature):
            continue
        sketch = by_id[m.feature.params.profile.feature_id]
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            base, offset = plane.plane, 0.0
        else:
            datum = by_id[plane.feature_id]
            assert isinstance(datum, DatumFeature)
            assert isinstance(datum.params, DatumOffsetParams)
            base, offset = datum.params.base, datum.params.offset_mm
        d = m.feature.params.distance_mm
        if m.feature.params.direction == "reverse":
            d = -d
        loop: list[tuple[float, float]] = []
        pts: list[tuple[float, float, float]] = []
        for e in sketch.params.entities:
            assert isinstance(e, SketchLine)
            loop.append((e.start.x / IN, e.start.y / IN))
            for h in (0.0, d):
                x, y, o = e.start.x, e.start.y, offset + h
                p = {"XY": (x, y, o), "YZ": (o, x, y), "XZ": (x, -o, y)}[base]
                pts.append(tuple(c / IN for c in p))  # type: ignore[arg-type]
        xs, ys, zs = zip(*pts, strict=True)
        bounds = tuple(
            round(v, 6) + 0.0
            for v in (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
        )
        meta = m.metadata
        out.append(
            (
                m.role,
                None if meta is None else meta.profile,
                None if meta is None else meta.material,
                bounds,  # type: ignore[arg-type]
                round(_area(loop) * abs(d) / IN, 9),
            )
        )
    return out


def volume(members: list[ExpandedMember]) -> float:
    return sum(p[4] for p in placed(members))


def banding_in(members: list[ExpandedMember]) -> float:
    return sum(
        m.metadata.banding.length_mm / IN
        for m in members
        if m.metadata is not None and m.metadata.banding is not None
    )


def hardware(members: list[ExpandedMember]) -> Counter[str]:
    out: Counter[str] = Counter()
    for m in members:
        for item in (m.metadata.hardware or []) if m.metadata else []:
            out[item.key] += item.quantity
    return out


# --- The manifest -------------------------------------------------------------------


def test_the_manifest_lists_its_boxes() -> None:
    m = CABINETS.manifest
    boxes_input = next(i for i in m.inputs if i.name == "boxes")
    assert isinstance(boxes_input, ListInput)
    assert boxes_input.item_label == "Box" and boxes_input.min_items == 1
    assert [f.name for f in boxes_input.fields] == [
        "type",
        "width_mm",
        "height",
        "fronts",
        "doors",
        "drawers",
        "drawer_height_mm",
        "shelves",
    ]
    # The typed position is hidden once a wall is picked.
    hidden = {i.name for i in m.inputs if i.superseded_by == "wall"}
    assert hidden == {"x_mm", "y_mm", "z_mm", "direction_deg"}
    assert m.id == "loft.cabinets" and m.version == "1.0.0"


def test_a_new_run_is_one_b24() -> None:
    inputs = canonical_inputs(CABINETS.manifest, {})
    assert inputs["boxes"] == [
        {
            "type": "base",
            "width_mm": 24 * IN,
            "height": "standard",
            "fronts": "standard",
            "doors": "auto",
            "drawers": 3,
            "drawer_height_mm": 6 * IN,
            "shelves": 1,
        }
    ]


# --- C1: B24 frameless, to the panel ------------------------------------------------

NOTCHED = 24 * 34.5 - 3 * 4.5  # a side's face less its toe notch, in^2

#: casework.md C1's table: role, product, box (in), volume (in^3).
C1_TABLE: list[tuple[str, str, Bounds, float]] = [
    ("side", "3/4 plywood", (0, 0.75, 0, 24, 0, 34.5), 0.75 * NOTCHED),
    ("side", "3/4 plywood", (23.25, 24, 0, 24, 0, 34.5), 0.75 * NOTCHED),
    ("back", "3/4 plywood", (0.75, 23.25, 0, 0.75, 4.5, 34.5), 22.5 * 30 * 0.75),
    ("bottom", "3/4 plywood", (0.75, 23.25, 0.75, 24, 4.5, 5.25), 22.5 * 23.25 * 0.75),
    ("stretcher", "3/4 plywood", (0.75, 23.25, 20, 24, 33.75, 34.5), 22.5 * 4 * 0.75),
    ("stretcher", "3/4 plywood", (0.75, 23.25, 0.75, 4.75, 33.75, 34.5), 67.5),
    ("toe_kick", "3/4 plywood", (0.75, 23.25, 20.25, 21, 0, 4.5), 22.5 * 4.5 * 0.75),
    (
        "shelf",
        "3/4 plywood",
        (0.78125, 23.21875, 0.75, 23, 16.5, 17.25),
        22.4375 * 22.25 * 0.75,
    ),
    (
        "drawer_front",
        "3/4 plywood",
        (0.0625, 23.9375, 24, 24.75, 28.4375, 34.4375),
        23.875 * 6 * 0.75,
    ),
    (
        "door",
        "3/4 plywood",
        (0.0625, 23.9375, 24, 24.75, 4.5625, 28.3125),
        23.875 * 23.75 * 0.75,
    ),
    ("drawer_side", "1/2 plywood", (1.25, 1.75, 2, 24, 29, 33), 22 * 4 * 0.5),
    ("drawer_side", "1/2 plywood", (22.25, 22.75, 2, 24, 29, 33), 22 * 4 * 0.5),
    ("drawer_end", "1/2 plywood", (1.75, 22.25, 23.5, 24, 29, 33), 20.5 * 4 * 0.5),
    ("drawer_end", "1/2 plywood", (1.75, 22.25, 2, 2.5, 29, 33), 20.5 * 4 * 0.5),
    ("drawer_bottom", "1/4 plywood", (1.25, 22.75, 2, 24, 28.75, 29), 21.5 * 22 * 0.25),
]


def c1(width: float = 24, **run: Any) -> list[ExpandedMember]:
    return cabinets({"boxes": [box("base", width)], **run})


def _rows(members: list[ExpandedMember]) -> Counter[tuple[str, str | None, Bounds]]:
    return Counter((role, prof, bounds) for role, prof, _, bounds, _ in placed(members))


def test_c1_is_casework_md_s_table_panel_for_panel() -> None:
    members = c1()
    want = Counter(
        (role, prod, tuple(float(v) for v in b)) for role, prod, b, _ in C1_TABLE
    )
    assert _rows(members) == want
    by_box = {(role, bounds): vol for role, _, _, bounds, vol in placed(members)}
    for role, _, bounds, vol in C1_TABLE:
        assert by_box[(role, bounds)] == pytest.approx(vol, abs=1e-9)
    # Every panel is plywood: the carcass and fronts 3/4, the drawer box 1/2
    # on a 1/4 bottom.
    assert {p[2] for p in placed(members)} == {"plywood"}


def test_c1_volume_banding_and_hardware() -> None:
    members = c1()
    thick = {"3/4 plywood": 0.75, "1/2 plywood": 0.5, "1/4 plywood": 0.25}
    areas: dict[str, float] = {}
    for _, prod, _, _, vol in placed(members):
        assert prod is not None
        areas[prod] = areas.get(prod, 0.0) + vol / thick[prod]
    assert areas == {
        "3/4 plywood": pytest.approx(4317.890625),
        "1/2 plywood": pytest.approx(340),
        "1/4 plywood": pytest.approx(473),
    }
    assert volume(members) == pytest.approx(3526.66796875, abs=1e-9)
    # 2 x 30 sides + bottom + front stretcher + shelf + the door's and the
    # drawer front's perimeters: 282.4375 in, 23.54 ft.
    assert banding_in(members) == pytest.approx(
        2 * 30 + 22.5 + 22.5 + 22.4375 + 95.25 + 59.75, abs=1e-9
    )
    assert round(banding_in(members) / 12, 2) == 23.54
    assert hardware(members) == {"hinge": 2, "slide_22": 1}


def test_c1_widened_to_27_grows_every_panel_across_by_3() -> None:
    members = c1(27)
    assert volume(members) == pytest.approx(3820.10546875, abs=1e-9)
    assert banding_in(members) == pytest.approx(303.4375, abs=1e-9)
    assert round(banding_in(members) / 12, 2) == 25.29
    assert hardware(members) == {"hinge": 2, "slide_22": 1}
    widths = {(role, round(b[1] - b[0], 6)) for role, _, _, b, _ in placed(members)}
    assert {("back", 25.5), ("door", 26.875), ("drawer_front", 26.875)} <= widths
    assert ("drawer_bottom", 24.5) in widths
    # The same members, by name: widening keeps every panel's id.
    assert [m.id for m in c1()] == [m.id for m in members]


def test_c1_face_frame_by_hand() -> None:
    """The same carcass with a 1x2 white oak frame on its front (stiles 30,
    rails 21 at the top, between the fronts and at the bottom) and 1/2 in
    overlay fronts: the drawer's opening 5 tall (Z 28..33), the door's
    20.5 (6..26.5), so a 22 x 6 drawer front and a 22 x 21.5 door at
    Y 24.75..25.5; the drawer box 1 in inside its 21 x 5 opening (20 wide,
    4 tall on its bottom); the shelf centred in the door bay (5.25..26.5).
    The carcass's front edges are behind the frame, so only the shelf and
    the fronts are banded."""
    members = c1(construction="face_frame")
    rows = {(r, b) for r, _, _, b, _ in placed(members)}
    assert ("stile", (0.0, 1.5, 24.0, 24.75, 4.5, 34.5)) in rows
    assert ("stile", (22.5, 24.0, 24.0, 24.75, 4.5, 34.5)) in rows
    rails = sorted(b for r, b in rows if r == "rail")
    assert rails == [(1.5, 22.5, 24.0, 24.75, z0, z0 + 1.5) for z0 in (4.5, 26.5, 33.0)]
    assert ("drawer_front", (1.0, 23.0, 24.75, 25.5, 27.5, 33.5)) in rows
    assert ("door", (1.0, 23.0, 24.75, 25.5, 5.5, 27.0)) in rows
    assert ("shelf", (0.78125, 23.21875, 0.75, 23.0, 15.5, 16.25)) in rows
    assert ("drawer_bottom", (2.0, 22.0, 2.0, 24.0, 28.5, 28.75)) in rows
    frame = {p for p in placed(members) if p[0] in ("stile", "rail")}
    assert {(p[1], p[2]) for p in frame} == {("1x2", "white_oak")}
    carcass = 4317.890625 - 23.875 * 23.75 - 23.875 * 6  # less the fronts
    fronts = 22 * 21.5 + 22 * 6
    frame_in3 = (2 * 30 + 3 * 21) * 1.5 * 0.75
    drawer = 2 * 22 * 3.75 * 0.5 + 2 * 19 * 3.75 * 0.5 + 20 * 22 * 0.25
    assert volume(members) == pytest.approx(
        (carcass + fronts) * 0.75 + frame_in3 + drawer, abs=1e-9
    )
    assert volume(members) == pytest.approx(3561.58203125, abs=1e-9)
    assert banding_in(members) == pytest.approx(22.4375 + 2 * (22 + 21.5) + 2 * 28)
    assert hardware(members) == {"hinge": 2, "slide_22": 1}


# --- The rules ----------------------------------------------------------------------


def test_blum_hinges_by_door_height_and_the_longest_slide() -> None:
    assert [hinges_for(h) for h in (23.75, 35.4, 35.5, 63, 70, 78.7, 90)] == [
        2,
        2,
        3,
        3,
        4,
        4,
        5,
    ]
    with pytest.raises(PluginError, match=r"94\.5"):
        hinges_for(95)
    assert [slide_for(d) for d in (23.25, 20.25, 12, 11.9, 30)] == [
        22,
        20,
        12,
        None,
        24,
    ]


@pytest.mark.parametrize(
    ("row", "words"),
    [
        (box("base", 25), "9 to 48 in wide, in 3 in steps"),
        (box("base", 6), "9 to 48 in wide"),
        (box("wall", 24, height="h84"), "30, 36, 42 in high"),
        (box("wall", 24, fronts="drawers"), "takes no drawers"),
        (box("base", 24, fronts="stacked_doors"), "takes no stacked doors"),
        (box("vanity", 30, height="h36"), "34.5, 30.5 in high"),
    ],
)
def test_a_box_out_of_its_sizes_is_refused_by_number(
    row: dict[str, Any], words: str
) -> None:
    with pytest.raises(PluginError, match="Box 2: .*" + words) as err:
        cabinets({"boxes": [box("base", 24), row]})
    assert err.value.input == "boxes"


def test_fillers_alone_are_not_a_run() -> None:
    with pytest.raises(PluginError, match="needs a box"):
        cabinets({"boxes": [box("filler", 3)]})


def test_a_filler_stands_in_line_with_its_neighbours_fronts() -> None:
    members = cabinets({"boxes": [box("filler", 3.5), box("base", 18)]})
    fillers = [p for p in placed(members) if p[0] == "filler"]
    assert [f[3] for f in fillers] == [(0.0, 3.5, 24.0, 24.75, 4.5, 34.5)]
    sides = sorted(p[3][0] for p in placed(members) if p[0] == "side")
    assert sides == [3.5, 20.75]


def test_a_run_s_boxes_never_overlap() -> None:
    members = cabinets(
        {
            "boxes": [
                box("filler", 3.5),
                box("tall", 18),
                box("base", 24, fronts="drawers"),
                box("base", 27),
                box("base", 36, fronts="false_door", shelves=0),
                box("vanity", 30),
            ]
        }
    )
    assert overlaps([p[3] for p in placed(members)]) == []


# --- C2: a kitchen on B7's left wall -------------------------------------------------

#: B7's left wall (outline line e4) runs from Y 5.5 to the back wall's face
#: at Y 186.5, its framing X 0..5.5 on a subfloor at Z 11.46875; its inside
#: gypsum (INTERIOR-WALLS, not built) is the Back gap: the backs at X 6.
SUBFLOOR = 1.5 + 9.25 + 23 / 32
B7_LEFT = {
    "wall_segment": ["e4"],
    "measure_from": "end",
    "gap_mm": 0.5 * IN,
}
C2_BASE = [
    box("filler", 3.5),
    box("tall", 18),
    box("base", 24, fronts="drawers"),
    box("base", 27),
    box("base", 36, fronts="false_door", shelves=0),
    box("base", 24),
]
C2_WALL = [
    box("wall", 24, shelves=2),
    box("wall", 27, shelves=2),
]


def b7_house() -> tuple[list[ExpandedMember], dict[uuid.UUID, AuthoredEnvelope]]:
    rows = b7_units()
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    members: list[ExpandedMember] = []
    for fid, env, ms in rows:
        earlier[fid] = env
        for m in ms:
            earlier[m.id] = m.feature
        members += ms
    return members, earlier


def c2(base: list[dict[str, Any]] | None = None) -> dict[str, list[ExpandedMember]]:
    _, earlier = b7_house()
    wall = {"wall": FeatureRef(kind="feature", feature_id=WALLS_ID), **B7_LEFT}
    runs = {
        "base": cabinets({**wall, "boxes": base or C2_BASE}, dict(earlier), RUN_ID),
        "wall": cabinets(
            {**wall, "offset_mm": 21.5 * IN, "boxes": C2_WALL},
            dict(earlier),
            WALL_RUN_ID,
        ),
    }
    return runs


def _span(members: list[ExpandedMember]) -> Bounds:
    bs = [p[3] for p in placed(members)]
    return (
        min(b[0] for b in bs),
        max(b[1] for b in bs),
        min(b[2] for b in bs),
        max(b[3] for b in bs),
        min(b[4] for b in bs),
        max(b[5] for b in bs),
    )


def test_c2_runs_stand_on_b7_s_left_wall() -> None:
    """The base run from the back wall's face (Y 186.5) to Y 54, 132.5 long,
    its backs at X 6, its sides and toe kicks on the subfloor; the tall
    box's lower door in line with the base doors; the sink base centred on
    the window at Y 96; the wall run Y 165..114, its bottom 54 above the
    subfloor."""
    runs = c2()
    base, wall = runs["base"], runs["wall"]
    x0, _, y0, y1, z0, z1 = _span(base)
    assert (x0, y0, y1, z0) == (6.0, 54.0, 186.5, SUBFLOOR)
    assert z1 == pytest.approx(SUBFLOOR + 84)
    assert _span(wall)[:5] == (6.0, 18.75, 114.0, 165.0, SUBFLOOR + 54)
    doors = [p[3] for p in placed(base) if p[0] == "door"]
    tops = {round(d[5] - SUBFLOOR, 6) for d in doors}
    # The tall box's lower door, B27's and B24's doors share one top (28.3125)
    # and the sink base's doors sit under its false front, at the same top.
    assert 28.3125 in tops
    sink_sides = sorted(p[3][2] for p in placed(base) if p[0] == "side")[2:4]
    assert sink_sides == [78.0, 113.25]
    assert (sink_sides[0] + sink_sides[1] + 0.75) / 2 == 96.0
    assert hardware(base) == {
        "hinge": 2 * 2 + 3 + 2 + 2 + 2,  # T1884 (2 + 3), B27, SB36 (2 x 2), B24
        "slide_22": 3 + 1 + 1,  # DB24's three drawers, B27's, B24's
    }
    # W2430 and W2730 one door each (auto: one door to 27 in, as C1 widened).
    assert hardware(wall) == {"hinge": 2 + 2}


def test_c2_touches_nothing_in_b7() -> None:
    """No cabinet panel overlaps another, nor any of B7's members (its OSB
    and rafters left to the kernel test, which probes them exactly)."""
    runs = c2()
    house, _ = b7_house()
    panels = [p[3] for run in runs.values() for p in placed(run)]
    assert overlaps(panels) == []
    skip = {"sheathing", "rafter", "frame", "glazing", "slab"}
    rest = boxes(house, tuple({m.role for m in house} - skip))
    for panel in panels:
        assert [p for p in overlaps([panel, *rest]) if p[0] == 0] == []


def test_c2_b24_to_b21_is_one_edit_and_nothing_else_moves() -> None:
    before = c2()["base"]
    after = c2([*C2_BASE[:-1], box("base", 21)])["base"]
    assert _span(after)[2] == 57.0
    moved = {m.id for m in after} ^ {m.id for m in before}
    assert moved == set()  # the same members, by name
    old = {m.id: p for m, p in zip(_extrudes(before), placed(before), strict=True)}
    new = {m.id: p for m, p in zip(_extrudes(after), placed(after), strict=True)}
    last = {m.id for m in before if m.name is not None and m.name.startswith("box/5/")}
    changed = {fid for fid in old if old[fid] != new[fid]}
    assert changed and changed <= last


def _extrudes(members: list[ExpandedMember]) -> list[ExpandedMember]:
    return [m for m in members if isinstance(m.feature, ExtrudeFeature)]


def test_an_outline_wall_needs_its_line_and_a_run_must_fit_it() -> None:
    _, earlier = b7_house()
    wall = FeatureRef(kind="feature", feature_id=WALLS_ID)
    with pytest.raises(PluginError, match="Wall line: pick the line"):
        cabinets({"wall": wall, "boxes": C2_BASE}, dict(earlier))
    with pytest.raises(PluginError, match="does not fit the 181 in wall") as err:
        cabinets(
            {**B7_LEFT, "wall": wall, "offset_mm": 60 * IN, "boxes": C2_BASE},
            dict(earlier),
        )
    assert err.value.input == "offset_mm"


# --- C3: a melamine vanity at a typed position ---------------------------------------

V3021 = [box("vanity", 30, shelves=0)]


def test_c3_v3021_frameless_by_hand() -> None:
    """30 wide, 21 deep, 34.5 high on its toe kick: two 14.875 x 23.75 doors
    under a 29.875 x 6 false front, 3/4 melamine with PVC banding."""
    members = cabinets(
        {"x_mm": 12 * IN, "y_mm": 24 * IN, "carcass": "melamine", "boxes": V3021}
    )
    assert {(p[1], p[2]) for p in placed(members)} == {("3/4 melamine", "melamine")}
    sides = 2 * 0.75 * (21 * 34.5 - 3 * 4.5)
    back, bottom = 28.5 * 30, 28.5 * 20.25
    stretchers, toe = 2 * 28.5 * 4, 28.5 * 4.5
    fronts = 29.875 * 6 + 2 * 14.875 * 23.75
    want = sides + (back + bottom + stretchers + toe + fronts) * 0.75
    assert volume(members) == pytest.approx(want, abs=1e-9)
    assert volume(members) == pytest.approx(3072.140625, abs=1e-9)
    assert _span(members) == (12.0, 42.0, 24.0, 45.75, 0.0, 34.5)
    assert banding_in(members) == pytest.approx(
        2 * 30 + 28.5 + 28.5 + 2 * (29.875 + 6) + 2 * 2 * (14.875 + 23.75)
    )
    bands = {
        m.metadata.banding.material
        for m in members
        if m.metadata and m.metadata.banding
    }
    assert bands == {"pvc"}
    grains = [m.metadata.grain for m in members if m.metadata is not None]
    assert set(grains) == {None}  # melamine has no grain: its panels may turn
    assert hardware(members) == {"hinge": 4}


def test_c3_v3021_face_frame_by_hand() -> None:
    members = cabinets(
        {"carcass": "melamine", "construction": "face_frame", "boxes": V3021}
    )
    rows = {(r, b) for r, _, _, b, _ in placed(members)}
    assert ("false_front", (1.0, 29.0, 21.75, 22.5, 27.5, 33.5)) in rows
    assert ("door", (1.0, 14.9375, 21.75, 22.5, 5.5, 27.0)) in rows
    assert ("door", (15.0625, 29.0, 21.75, 22.5, 5.5, 27.0)) in rows
    sides = 2 * 0.75 * (21 * 34.5 - 3 * 4.5)
    carcass = 28.5 * 30 + 28.5 * 20.25 + 2 * 28.5 * 4 + 28.5 * 4.5
    fronts = 28 * 6 + 2 * 13.9375 * 21.5
    frame = (2 * 30 + 3 * 27) * 1.5 * 0.75
    assert volume(members) == pytest.approx(
        sides + (carcass + fronts) * 0.75 + frame, abs=1e-9
    )
    assert hardware(members) == {"hinge": 4}


# --- The goldens ---------------------------------------------------------------------


def request_of(members: list[ExpandedMember]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members],
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in members if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )


def members_json(members: list[ExpandedMember]) -> str:
    items = [
        CutListMember(
            feature_id=m.id,
            role=m.role,
            title=TITLES[m.role],
            plugin_id="loft.cabinets",
            metadata=m.metadata,
        ).model_dump(mode="json")
        for m in members
        if m.metadata is not None
    ]
    return json.dumps(items, indent=2) + "\n"


def golden_members() -> dict[str, list[ExpandedMember]]:
    runs = c2()
    typed = {"x_mm": 12 * IN, "y_mm": 24 * IN, "carcass": "melamine", "boxes": V3021}
    return {
        "c1-b24-frameless-casework": c1(),
        "c1-b27-frameless-casework": c1(27),
        "c1-b24-face-frame-casework": c1(construction="face_frame"),
        # C1 on a run turned 30 degrees about (12, 24): its notched sides on
        # a plane turned about Z.
        "c1-b24-turned-30-casework": c1(x_mm=12 * IN, y_mm=24 * IN, direction_deg=30.0),
        "c2-kitchen-b7-left-wall": runs["base"] + runs["wall"],
        "c3-v3021-melamine-frameless": cabinets(typed),
        "c3-v3021-melamine-face-frame": cabinets(
            {**typed, "construction": "face_frame"}
        ),
    }


@pytest.mark.parametrize("name", sorted(golden_members()))
def test_the_goldens_are_the_plugin_s_expansion(name: str) -> None:
    members = golden_members()[name]
    folder = GOLDENS / name
    assert (folder / "model.json").read_text() == request_of(members).model_dump_json(
        indent=2
    ) + "\n"
    # Compared as JSON: the file is prettier's layout (its grain vectors on
    # one line), the content the plugin's.
    assert json.loads((folder / "members.json").read_text()) == json.loads(
        members_json(members)
    )


def test_a_stored_run_keeps_its_inputs() -> None:
    env = CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": "loft.cabinets",
                "plugin_version": "1.0.0",
                "inputs": canonical_inputs(CABINETS.manifest, {"boxes": C2_BASE}),
            },
        }
    )
    dumped = env.model_dump(mode="json")["params"]["inputs"]["boxes"]
    assert [row["type"] for row in dumped] == [b["type"] for b in C2_BASE]


if __name__ == "__main__":
    for name, members in golden_members().items():
        folder = GOLDENS / name
        folder.mkdir(exist_ok=True)
        (folder / "model.json").write_text(
            request_of(members).model_dump_json(indent=2) + "\n"
        )
        (folder / "members.json").write_text(members_json(members))
