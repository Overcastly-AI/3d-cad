"""INTERIOR-WALLS: partitions on plan lines, the backing the walls they meet
frame, and gypsum board (``loft.interior_wall`` 1.0.0, ``loft.wall`` 1.4.0).

Checked against ``docs/reference-parts/buildings.md`` B10, typed by hand:

* B10 is B7's outline sketch plus two lines, X 180 (P1, drawn from the back)
  and Y 132 (P2, drawn from the right to P1), one Interior wall feature and a
  2868 door hosted in P2: 2 partitions, 4 ladders of 3 blocks, P1 framed
  X 178.25..181.75 from Y 186.5 to 5.5 and P2 Y 130.25..133.75 from X 282.5
  to 181.75, the door's rough opening X 215..249, 20 gypsum panels;
* ``loft.wall`` 1.4.0 with no partition and no inside gypsum is 1.3.0 member
  for member, and with B10's partitions it is 1.3.0's bodies plus 9 blocks;
* 24 -> 28 ft leaves P1 at X 180 and P2 at Y 132, P2 148.75 long;
* the three-stud choice, 4x12 sheets, inside gypsum on the exterior walls,
  a separate partition sketch, and the refusals.

The geometry golden ``b10-partitions`` is written from here and pinned by
this module; ``services/geometry/tests/test_partitions_b10.py`` checks its
STEP against an independent script. Regenerate after a deliberate change (a
NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_interior_walls.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, PluginError, canonical_inputs
from loft_plugins.builtin.interior_wall import courses
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    EvaluateTreeRequest,
    ExpandedMember,
    SketchFeature,
)
from loft_wire.plugins import FeatureReferenceInput
from loft_wire.sketch import SketchLine

# test_building_outline's sketches, expansion and body probes. pytest runs in
# importlib mode, which puts no test directory on sys.path, so add this one.
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    DOOR,
    FLOOR,
    FLOOR_ID,
    GOLDENS,
    IN,
    ROOF,
    ROOF_ID,
    SKETCH_ID,
    WALL,
    WALLS_ID,
    b7_openings,
    bodies,
    boxes,
    envelope,
    expand,
    line,
    members_json,
    opening,
    overlaps,
    point_ref,
    rectangle,
    ref,
    request_of,
)

GOLDEN = "b10-partitions"
INTERIOR = REGISTRY.get("loft.interior_wall", "1.0.0")
WALL_1_4 = REGISTRY.get("loft.wall", "1.4.0")
DOOR_1_4 = REGISTRY.get("loft.door", "1.4.0")
INTERIOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000b710")
PARTITION_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000b711")
DOOR_NAME = "Door P2"
PART_ID = uuid.UUID("00000000-0000-0000-0000-000000010b10")

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]


# --- B10, as buildings.md types it ---------------------------------------------------


def partition_constraints(left: str = "e4", front: str = "e1") -> list[dict[str, Any]]:
    """P1 vertical, its start 180 from the left line; P2 horizontal, its
    start 132 from the front line (point-to-line dimensions, as a user
    dimensions a partition from a wall)."""
    return [
        {"kind": "vertical", "entity": "e5"},
        {"kind": "horizontal", "entity": "e6"},
        {
            "kind": "point_line_distance",
            "point": point_ref("e5", "start"),
            "line": left,
            "value_mm": 180 * IN,
        },
        {
            "kind": "point_line_distance",
            "point": point_ref("e6", "start"),
            "line": front,
            "value_mm": 132 * IN,
        },
    ]


def b10_sketch(
    length: float = 288.0,
    extra: list[dict[str, Any]] | None = None,
    lines: list[dict[str, Any]] | None = None,
) -> SketchFeature:
    """B7's 288 x 192 rectangle plus P1 (e5, X 180, drawn from the back to
    the front) and P2 (e6, Y 132, drawn from the right wall to P1). The
    partitions stay drawn where they were at 288 when *length* changes: a
    stored sketch's drawing is not re-solved, and the partitions follow the
    walls they meet, not their drawn ends."""
    raw = rectangle(length, 192).model_dump(mode="json")
    raw["params"]["entities"] += lines or [
        line("e5", (180, 192), (180, 0)),
        line("e6", (288, 132), (180, 132)),
    ]
    raw["params"]["constraints"] += partition_constraints() + (extra or [])
    return SketchFeature.model_validate(raw)


def partition_sketch() -> SketchFeature:
    """P1 and P2 alone, in a sketch of their own anchored on the origin."""
    raw: dict[str, Any] = {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "id": "origin",
                    "kind": "point",
                    "construction": True,
                    "position": {"x": 0.0, "y": 0.0},
                },
                line("e5", (180, 192), (180, 0)),
                line("e6", (288, 132), (180, 132)),
            ],
            "constraints": [
                {"kind": "fixed", "point": point_ref("origin", "position")},
                {"kind": "vertical", "entity": "e5"},
                {"kind": "horizontal", "entity": "e6"},
                {
                    "kind": "point_distance",
                    "a": point_ref("origin", "position"),
                    "b": point_ref("e5", "start"),
                    "direction": "horizontal",
                    "value_mm": 180 * IN,
                },
                {
                    "kind": "point_distance",
                    "a": point_ref("origin", "position"),
                    "b": point_ref("e6", "start"),
                    "direction": "vertical",
                    "value_mm": 132 * IN,
                },
            ],
        },
    }
    return SketchFeature.model_validate(raw)


def b10(
    length: float = 288.0,
    *,
    sketch: SketchFeature | None = None,
    interior: dict[str, Any] | None = None,
    walls: dict[str, Any] | None = None,
    wall_plugin: Any = WALL_1_4,
    door: dict[str, Any] | None = None,
    separate: bool = False,
    roof: bool = True,
    partitions: bool = True,
) -> Rows:
    """The tree: sketch, (the partitions' own sketch,) floor, walls hosting
    B7's openings and the Interior wall, the openings, the Interior wall
    hosting the 2868 door in P2 (measured 50.25 from P2's end, P1's face:
    X 232), the door, the roof."""
    sketch = sketch or b10_sketch(length)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    rows: Rows = [(SKETCH_ID, sketch, [])]
    if separate:
        own = partition_sketch()
        earlier[PARTITION_SKETCH_ID] = own
        rows.append((PARTITION_SKETCH_ID, own, []))

    def add(
        fid: uuid.UUID,
        plugin: Any,
        raw: dict[str, Any],
        hosted: tuple[Hosted, ...] = (),
    ) -> None:
        members = expand(plugin, fid, raw, dict(earlier), hosted)
        env = envelope(plugin, raw)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        rows.append((fid, env, members))

    add(FLOOR_ID, FLOOR, {"outline": ref(SKETCH_ID), **B7_FLOOR})
    wall_raw = {
        "outline": ref(SKETCH_ID),
        "floor": ref(FLOOR_ID),
        **B7_STUDS,
        **(walls or {}),
    }
    with_walls = {**earlier, WALLS_ID: envelope(wall_plugin, wall_raw)}
    hosted = [
        opening(p, name, WALLS_ID, {"wall_segment": [seg], **raw}, with_walls)
        for p, name, seg, raw in b7_openings(length)
    ]
    interior_raw = {"host_wall": ref(WALLS_ID), **(interior or {})}
    if separate:
        interior_raw["sketch"] = ref(PARTITION_SKETCH_ID)
    interior_inputs = canonical_inputs(INTERIOR.manifest, interior_raw)
    openings = list(hosted)
    if partitions:
        hosted.append(
            Hosted(
                INTERIOR_ID,
                INTERIOR.manifest.id,
                INTERIOR.manifest.version,
                "Interior walls",
                ExpandInputs(INTERIOR_ID, interior_inputs),
            )
        )
    add(WALLS_ID, wall_plugin, wall_raw, tuple(hosted))
    for h in openings:
        add(
            h.feature_id,
            REGISTRY.get(h.plugin_id, h.plugin_version),
            dict(h.inputs.values),
        )
    if not partitions:
        return rows
    with_interior = {**earlier, INTERIOR_ID: envelope(INTERIOR, interior_raw)}
    the_door = opening(
        DOOR_1_4,
        DOOR_NAME,
        INTERIOR_ID,
        {
            "wall_segment": ["e6"],
            "size": "door_2868",
            "measure_from": "end",
            "offset_mm": 50.25 * IN,
            **(door or {}),
        },
        with_interior,
    )
    add(INTERIOR_ID, INTERIOR, interior_raw, (the_door,))
    add(the_door.feature_id, DOOR_1_4, dict(the_door.inputs.values))
    if roof:
        add(
            ROOF_ID,
            ROOF,
            {"walls": [ref(WALLS_ID)], "slope_walls": ["e1", "e3"], **B7_ROOF},
        )
    return rows


def row(rows: Rows, fid: uuid.UUID) -> list[ExpandedMember]:
    return next(members for f, _, members in rows if f == fid)


def door_id() -> uuid.UUID:
    return uuid.uuid5(INTERIOR_ID, DOOR_NAME)


Box = tuple[float, ...]


def named(members: list[ExpandedMember], role: str, prefix: str) -> list[Box]:
    """The boxes of *role*'s bodies named under *prefix* (``e5/``)."""
    keep = [m for m in members if m.role in (role, "section", "level")]
    picked = {
        m.id for m in keep if m.role == role and (m.name or "").startswith(prefix)
    }
    out = [m for m in keep if m.role != role or m.id in picked]
    return sorted(boxes(out, (role,)))


# --- B10 ---------------------------------------------------------------------------


def test_b10_frames_two_partitions_a_door_and_four_ladders_of_twelve_blocks() -> None:
    rows = b10()
    interior = row(rows, INTERIOR_ID)
    walls = row(rows, WALLS_ID)
    bottom = Counter(
        (m.name or "").split("/")[0] for m in interior if m.role == "bottom_plate"
    )
    assert bottom == {"e5": 1, "e6": 2}  # P2's plate cut at the door
    blocks = [m for m in walls + interior if m.role == "block"]
    assert len(blocks) == 12
    ladders = Counter("/".join((m.name or "").split("/")[:-1]) for m in blocks)
    assert sorted(ladders.values()) == [3, 3, 3, 3]
    assert sorted(ladders) == sorted(
        [
            f"e1/backing/{INTERIOR_ID}/e5",
            f"e3/backing/{INTERIOR_ID}/e5",
            f"e2/backing/{INTERIOR_ID}/e6",
            "e5/backing/e6",
        ]
    )
    door = row(rows, door_id())
    assert Counter(m.role for m in door if m.metadata is not None) == {
        "frame": 1,
        "slab": 1,
    }
    frame = next(m for m in door if m.role == "frame")
    assert frame.metadata is not None and frame.metadata.unit is not None
    assert frame.metadata.unit.key == "door_2868"


#: P1's stud centres (Y), from its start at the back wall's inside face
#: (Y 186.5): 0.75, then every 16, the end stud flush at the front's (Y 5.5).
P1_STUDS = [
    185.75,
    170.5,
    154.5,
    138.5,
    122.5,
    106.5,
    90.5,
    74.5,
    58.5,
    42.5,
    26.5,
    10.5,
    6.25,
]
#: The walls stand on B7's subfloor (Z 11.46875); studs from the bottom
#: plate's top to the double top plate's underside.
BASE = 1.5 + 9.25 + 23 / 32
STUD_Z = (BASE + 1.5, BASE + 94.125)


def test_the_partitions_stand_where_buildings_md_puts_them() -> None:
    interior = row(b10(roof=False), INTERIOR_ID)
    p1 = named(interior, "stud", "e5/")
    assert [round((b[2] + b[3]) / 2, 6) for b in reversed(p1)] == P1_STUDS
    assert {(b[0], b[1], b[4], b[5]) for b in p1} == {(178.25, 181.75, *STUD_Z)}
    p2 = named(interior, "stud", "e6/") + named(interior, "king", "e6/")
    # Layout studs at P2's u 0.75, 16, 80, 96 and its end, from X 282.5; the
    # door's kings outside its jacks.
    assert sorted((b[0] + b[1]) / 2 for b in p2) == [
        182.5,
        186.5,
        202.5,
        212.75,
        251.25,
        266.5,
        281.75,
    ]
    assert {(b[2], b[3]) for b in p2} == {(130.25, 133.75)}
    jacks = named(interior, "jack", "e6/")
    assert [(b[0], b[1]) for b in jacks] == [(213.5, 215.0), (249.0, 250.5)]
    plates = named(interior, "top_plate", "")
    assert sorted((b[0], b[1], b[2], b[3]) for b in plates) == [
        (178.25, 181.75, 5.5, 186.5),
        (178.25, 181.75, 5.5, 186.5),
        (181.75, 282.5, 130.25, 133.75),
        (181.75, 282.5, 130.25, 133.75),
    ]


def test_each_ladder_spans_the_bay_flush_with_the_face_it_meets() -> None:
    """Three flat 2x4 blocks, 14.5 long, centred 24, 48 and 72 above the
    bottom plate's top: the front and back walls' bays X 176.75..191.25
    (studs at X 176 and 192), the right wall's and P1's Y 123.25..137.75."""
    rows = b10(roof=False)
    got = sorted(boxes(row(rows, WALLS_ID) + row(rows, INTERIOR_ID), ("block",)))
    zs = [(BASE + 1.5 + c - 1.75, BASE + 1.5 + c + 1.75) for c in (24, 48, 72)]
    want = sorted(
        (*xy, *z)
        for xy in (
            (176.75, 191.25, 4.0, 5.5),  # front, flush with Y 5.5
            (176.75, 191.25, 186.5, 188.0),  # back, flush with Y 186.5
            (282.5, 284.0, 123.25, 137.75),  # right, flush with X 282.5
            (180.25, 181.75, 123.25, 137.75),  # P1's +X face, X 181.75
        )
        for z in zs
    )
    assert got == want


def _area(member: ExpandedMember, members: list[ExpandedMember]) -> float:
    """A panel's net area (in^2): its sketch's loops by the shoelace."""
    sketches = {m.id: m.feature for m in members}
    profile = member.feature.params.profile.feature_id  # type: ignore[union-attr]
    sketch = sketches[profile]
    assert isinstance(sketch, SketchFeature)
    total = 0.0
    for e in sketch.params.entities:
        assert isinstance(e, SketchLine)
        total += e.start.x * e.end.y - e.end.x * e.start.y
    return abs(total) / 2 / IN**2


def test_gypsum_is_twenty_panels_of_48130_5_square_inches() -> None:
    """P1's west face 181 x 96 (two courses of 48 from the top plate, 1.125
    at the floor); its east face less P2's 3.5; P2's faces from the right
    wall to P1's board (X 182.25), 100.25 x 96 less the door's 34 x 81.375
    each: 17 376 + 17 040 + 2 x 6 857.25 = 48 130.5 in^2, 11 sheets of 4x8."""
    interior = row(b10(roof=False), INTERIOR_ID)
    panels = [m for m in interior if m.role == "finish"]
    assert len(panels) == 20
    assert {m.metadata.profile for m in panels if m.metadata} == {"1/2 gypsum"}
    area = sum(_area(m, interior) for m in panels)
    assert area == pytest.approx(48130.5, abs=1e-6)
    assert 10 < area / (48 * 96) < 11  # 10.445: 11 sheets
    assert courses(97.125) == [(49.125, 97.125), (1.125, 49.125)]
    assert courses(109.125) == [(61.125, 109.125), (13.125, 61.125), (0.5, 13.125)]
    assert courses(98.0) == [(50.0, 98.0), (2.0, 50.0)]


_NEW_IN_WALLS = ("block", "backing_stud", "finish")


def clashes(rows: Rows) -> list[tuple[Box, Box]]:
    """Pairs of bodies whose boxes overlap, one of them a partition's, a
    backing's or a gypsum panel's (the door's slab sits in its frame's box
    and a rafter's box is not the rafter: the geometry test probes those
    exactly)."""
    new = boxes(row(rows, INTERIOR_ID)) + boxes(row(rows, WALLS_ID), _NEW_IN_WALLS)
    walls = row(rows, WALLS_ID)
    old_roles = tuple({m.role for m in walls} - set(_NEW_IN_WALLS))
    old = boxes(row(rows, FLOOR_ID)) + boxes(walls, old_roles)
    old += [b for b in boxes(row(rows, door_id())) if b[5] - b[4] > 81]  # the frame
    bad = [
        (a, b)
        for a in new
        for b in (*new, *old)
        if a is not b
        and all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-6 for k in (0, 2, 4))
    ]
    return bad


def test_nothing_new_overlaps_anything() -> None:
    """Every partition, block and gypsum panel clear of every other body: in
    B10, at 28 ft and with three-stud corners."""
    for rows in (
        b10(roof=False),
        b10(336, roof=False),
        b10(interior={"backing": "three_stud"}, roof=False),
    ):
        assert clashes(rows) == []


# --- loft.wall 1.4.0 ------------------------------------------------------------------


def _signature(members: list[ExpandedMember]) -> list[tuple[Any, ...]]:
    return [
        (m.id, m.role, m.index, m.name, m.feature.model_dump(mode="json"), m.metadata)
        for m in members
    ]


def test_wall_1_4_0_without_partitions_is_1_3_0_member_for_member() -> None:
    sketch = rectangle(288, 192)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    raw = {"outline": ref(SKETCH_ID), **B7_STUDS}
    with_walls = {**earlier, WALLS_ID: envelope(WALL, raw)}
    hosted = tuple(
        opening(p, name, WALLS_ID, {"wall_segment": [seg], **o}, with_walls)
        for p, name, seg, o in b7_openings()
    )
    old = expand(WALL, WALLS_ID, raw, earlier, hosted)
    new = expand(WALL_1_4, WALLS_ID, raw, earlier, hosted)
    assert _signature(new) == _signature(old)


def test_b10s_walls_are_1_3_0s_bodies_plus_nine_blocks() -> None:
    rows = b10(roof=False)
    old = b10(wall_plugin=WALL, roof=False, partitions=False)
    new_walls = bodies(row(rows, WALLS_ID))
    old_walls = bodies(row(old, WALLS_ID))
    blocks = bodies(row(rows, WALLS_ID), ("block",))
    assert sum(blocks.values()) == 9
    assert new_walls - blocks == old_walls


def test_28_ft_leaves_the_partitions_at_x_180_and_y_132() -> None:
    """One dimension, 288 -> 336: P1 stays at X 180, P2 at Y 132 and grows
    to 148.75 (X 181.75..330.5), the door stays at X 232, the right wall's
    ladder moves with it, and still nothing overlaps."""
    rows = b10(336, roof=False)
    interior = row(rows, INTERIOR_ID)
    plates = sorted((b[0], b[1], b[2], b[3]) for b in named(interior, "top_plate", ""))
    assert plates[0] == (178.25, 181.75, 5.5, 186.5)
    assert plates[-1] == (181.75, 330.5, 130.25, 133.75)
    assert plates[-1][1] - plates[-1][0] == 148.75
    jacks = named(interior, "jack", "e6/")
    assert [(b[0], b[1]) for b in jacks] == [(213.5, 215.0), (249.0, 250.5)]
    blocks = sorted(boxes(row(rows, WALLS_ID), ("block",)))
    assert {(b[0], b[1], b[2], b[3]) for b in blocks} == {
        (176.75, 191.25, 4.0, 5.5),
        (176.75, 191.25, 186.5, 188.0),
        (330.5, 332.0, 123.25, 137.75),
    }


def test_three_stud_corners_flank_each_partition() -> None:
    """Two studs of the wall's size either side of each partition, full
    height, in the wall it meets (P1's for P2), no blocks; the layout studs
    they would cut into dropped (none in B10: each flank lands in a bay)."""
    rows = b10(interior={"backing": "three_stud"}, roof=False)
    walls, interior = row(rows, WALLS_ID), row(rows, INTERIOR_ID)
    assert not [m for m in walls + interior if m.role == "block"]
    flanks = sorted(boxes(walls + interior, ("backing_stud",)))
    assert len(flanks) == 8
    front = [b for b in flanks if b[3] == 5.5]
    assert [(b[0], b[1]) for b in front] == [(176.75, 178.25), (181.75, 183.25)]
    p1 = [b for b in flanks if b[0] >= 178.25 and b[1] <= 181.75]
    assert [(b[2], b[3]) for b in p1] == [(128.75, 130.25), (133.75, 135.25)]


def test_4x12_sheets_hang_144_in_panels() -> None:
    interior = row(
        b10(interior={"finish_sheet": "sheet_4x12"}, roof=False), INTERIOR_ID
    )
    panels = boxes(interior, ("finish",))
    lengths = sorted({round(max(b[1] - b[0], b[3] - b[2]), 6) for b in panels})
    assert max(lengths) == 144
    area = sum(_area(m, interior) for m in interior if m.role == "finish")
    assert area == pytest.approx(48130.5, abs=1e-6)
    # GYPSUM-SHEETS: every panel names its 4x12, the 37 in ends too, so the
    # cut list nests them on 4x12s (one line), not on 4x8s.
    finish = [m for m in interior if m.role == "finish"]
    assert {m.metadata.sheet for m in finish if m.metadata is not None} == {"4x12"}


def test_4x8_panels_name_no_sheet() -> None:
    """4x8 is the shortest gypsum sheet, the cut list's pick for every panel
    it covers, so the default's panels name none: byte for byte as before."""
    interior = row(b10(roof=False), INTERIOR_ID)
    finish = [m for m in interior if m.role == "finish"]
    assert finish and all(
        m.metadata is not None and m.metadata.sheet is None for m in finish
    )
    walls = row(
        b10(walls={"finish": "gypsum_1_2", "finish_sheet": "sheet_4x12"}, roof=False),
        WALLS_ID,
    )
    inside = [m for m in walls if m.role == "finish"]
    assert inside and {m.metadata.sheet for m in inside if m.metadata} == {"4x12"}


def test_inside_gypsum_on_the_walls_closes_every_corner_without_overlap() -> None:
    """Wall 1.4.0's inside gypsum: the front and back boards run between the
    side walls' framing (X 5.5..282.5), the sides' stop at them (Y 6..186),
    each cut at the partitions meeting it; the partitions' boards stop at it
    (P1 Y 6..186, P2 from X 282)."""
    rows = b10(walls={"finish": "gypsum_1_2"}, roof=False)
    walls, interior = row(rows, WALLS_ID), row(rows, INTERIOR_ID)
    inside = boxes(walls, ("finish",))
    front = [b for b in inside if b[2] == 5.5 and b[3] == 6.0]
    assert min(b[0] for b in front) == 5.5 and max(b[1] for b in front) == 282.5
    left = [b for b in inside if b[0] == 5.5 and b[1] == 6.0]
    assert min(b[2] for b in left) == 6.0 and max(b[3] for b in left) == 186.0
    # The front board is cut out where P1 meets it.
    assert not [b for b in front if b[0] < 179.0 < b[1]]
    p1 = [b for b in boxes(interior, ("finish",)) if b[1] <= 178.25]
    assert min(b[2] for b in p1) == 6.0 and max(b[3] for b in p1) == 186.0
    assert clashes(rows) == []
    assert overlaps(boxes(walls)) == []


def test_a_separate_sketch_before_the_walls_frames_the_same_partitions() -> None:
    same = b10(separate=True, roof=False)
    base = b10(roof=False)
    assert bodies(row(same, INTERIOR_ID)) == bodies(row(base, INTERIOR_ID))
    assert bodies(row(same, WALLS_ID)) == bodies(row(base, WALLS_ID))


# --- Refusals ------------------------------------------------------------------------


def _refused(sketch: SketchFeature, words: str) -> None:
    with pytest.raises(PluginError, match=words):
        b10(sketch=sketch, roof=False)


def test_a_partition_not_fully_defined_is_refused() -> None:
    raw = b10_sketch().model_dump(mode="json")
    raw["params"]["constraints"] = [
        c
        for c in raw["params"]["constraints"]
        if not (c["kind"] == "point_line_distance" and c["point"]["entity"] == "e6")
    ]
    _refused(SketchFeature.model_validate(raw), "e6's position is not fully defined")


def test_a_slanted_partition_is_refused() -> None:
    raw = b10_sketch().model_dump(mode="json")
    raw["params"]["constraints"] = [
        c for c in raw["params"]["constraints"] if c.get("entity") != "e6"
    ]
    _refused(SketchFeature.model_validate(raw), "e6 is not constrained horizontal")


def test_a_partition_drawn_outside_the_walls_is_refused() -> None:
    sketch = b10_sketch(
        lines=[line("e5", (180, 192), (180, 0)), line("e6", (400, 132), (300, 132))]
    )
    _refused(sketch, "e6 meets no wall")


def test_partitions_that_cross_or_meet_end_to_end_are_refused() -> None:
    crossing = b10_sketch(
        lines=[line("e5", (180, 192), (180, 0)), line("e6", (288, 132), (100, 132))]
    )
    _refused(crossing, "e5 and e6 cross")
    corner = b10_sketch(
        lines=[line("e5", (180, 192), (180, 132)), line("e6", (288, 132), (180, 132))]
    )
    _refused(corner, "only in a T")


def test_backing_in_an_openings_framing_is_refused() -> None:
    """P1 at X 144 meets the front wall in its door's framing."""
    raw = b10_sketch(
        lines=[line("e5", (144, 192), (144, 0)), line("e6", (288, 132), (144, 132))]
    ).model_dump(mode="json")
    for c in raw["params"]["constraints"]:
        if c["kind"] == "point_line_distance" and c["point"]["entity"] == "e5":
            c["value_mm"] = 144 * IN
    with pytest.raises(PluginError, match="in an opening's framing"):
        b10(sketch=SketchFeature.model_validate(raw), roof=False)


def test_walls_before_1_4_0_cannot_host_partitions() -> None:
    with pytest.raises(PluginError, match=r"update the walls to 1\.4\.0"):
        b10(wall_plugin=WALL, roof=False)


def test_a_partition_sketch_after_the_walls_is_refused() -> None:
    rows = b10(roof=False)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        if fid == INTERIOR_ID:
            break
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    earlier[PARTITION_SKETCH_ID] = partition_sketch()  # after the walls
    raw = {"host_wall": ref(WALLS_ID), "sketch": ref(PARTITION_SKETCH_ID)}
    with pytest.raises(PluginError, match="before the exterior walls"):
        expand(INTERIOR, INTERIOR_ID, raw, earlier)


# --- Manifests ------------------------------------------------------------------------


def test_a_1_4_0_door_may_stand_in_a_partition() -> None:
    host = next(i for i in DOOR_1_4.manifest.inputs if i.name == "host_wall")
    assert isinstance(host, FeatureReferenceInput)
    assert host.plugin_ids == ["loft.wall", "loft.interior_wall"]
    old = next(i for i in DOOR.manifest.inputs if i.name == "host_wall")
    assert isinstance(old, FeatureReferenceInput) and old.plugin_ids == ["loft.wall"]
    window = REGISTRY.get("loft.window", "1.4.0").manifest
    win_host = next(i for i in window.inputs if i.name == "host_wall")
    assert isinstance(win_host, FeatureReferenceInput)
    assert win_host.plugin_ids == ["loft.wall"]


def test_the_interior_wall_defaults_are_buildings_md_b10s() -> None:
    values = canonical_inputs(INTERIOR.manifest, {"host_wall": ref(WALLS_ID)})
    assert values["stud_profile"] == "us_2x4"
    assert values["stud_spacing_mm"] == pytest.approx(16 * IN)
    assert values["backing"] == "ladder"
    assert values["finish"] == "gypsum_1_2"
    assert values["finish_sheet"] == "sheet_4x8"
    assert values["bottom_plate_material"] == "spf_lumber"
    assert "sketch" not in values
    wall = canonical_inputs(WALL_1_4.manifest, {})
    assert wall["finish"] == "none"
    assert [i.name for i in WALL_1_4.manifest.inputs][:-2] == [
        i.name for i in WALL.manifest.inputs
    ]
    # The same 1.4.0 stands on a slab too (SLAB, test_slab.py).
    pick = next(i for i in WALL_1_4.manifest.inputs if i.name == "floor")
    assert pick.plugin_ids == ["loft.floor", "loft.slab"]  # type: ignore[union-attr]


# --- The golden -----------------------------------------------------------------------


def titles() -> dict[tuple[str, str], str]:
    return {
        (plugin.manifest.id, role.role): role.title
        for plugin in (
            FLOOR,
            WALL_1_4,
            ROOF,
            INTERIOR,
            DOOR_1_4,
            REGISTRY.get("loft.window", "1.1.0"),
            DOOR,
        )
        for role in plugin.manifest.members
    }


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    rows = b10()
    names = titles()
    metadata: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        for m in members:
            if m.metadata is None:
                continue
            metadata.append(
                CutListMember(
                    feature_id=m.id,
                    role=m.role,
                    title=names[(str(plugin_id), m.role)],
                    plugin_id=plugin_id,
                    metadata=m.metadata,
                )
            )
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
