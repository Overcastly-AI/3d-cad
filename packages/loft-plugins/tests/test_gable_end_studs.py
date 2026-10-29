"""GABLE-END-STUDS: ``loft.roof`` 1.7.0 frames a gable's end walls up to the
roof, with gable studs on their layout and their sheathing carried up
(Chief Architect's Build Framing).

Checked against ``docs/reference-parts/buildings.md`` B7, typed by hand:

* B7 on its outline at 6/12 (2x8 rafters, the heel held to 29/12, plates
  topped at Z 108.59375): the rafters' underside over Y is 106.1770833 +
  min(Y, 192 - Y) / 2, their top plane 7.25 sqrt(1.25) above it;
* the left wall (e4, X 0..5.5) lays its studs out from the front (its start,
  Y 5.5): 11 gable studs at Y 21.5, 37.5, ..., 181.5. The right wall (e2,
  X 282.5..288) runs clockwise from the back (its start, Y 186.5): 11 at
  Y 170.5, 154.5, ..., 10.5, the mirror of the left;
* each stud is the wall's 2x6, 5.5 deep, cut to the underside, long point
  up: d / 2 - 2.416667 at its higher face, d from the nearer eave wall's
  outside face; 262.791667 in a gable, 2 134 in^3 (8.25 x (262.791667 -
  11 x 0.375));
* the wall's OSB carried up in its own columns and corner rips, Y -0.4375
  .. 192.4375, to the rafters' TOP plane (114.282829 + Y / 2 at the front),
  peaked at Y 96: 5 705.19 in^2 a gable;
* 8/12 re-cuts them (2d / 3 - 2.416667, 359.25 in a gable), 28 ft moves the
  right gable to X 330.5..336, None is 1.6.0 member for member, a hip and a
  typed bearing frame none, an update to 1.7.0 takes Gable ends' default.

The geometry golden ``b7-gable-ends`` and the kernel fixture
``gable-end-cases.json.gz`` are written from here and pinned by this module
(``services/geometry/tests/test_gable_ends_b7.py`` checks them exactly).
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_gable_end_studs.py``.
"""

import gzip
import json
import math
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, canonical_inputs, update_for, updated_inputs
from loft_plugins.updates import update_effect
from loft_wire.cut_list import ONE_PIECE_ROLES, CutListMember
from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.plugins import ChoiceInput
from loft_wire.sketch import SketchLine

sys.path.insert(0, str(Path(__file__).parent))
import itertools

from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    ROOF_ID,
    WALLS_ID,
    b7_openings,
    bodies,
    boxes,
    expand,
    house,
    members_json,
    members_of,
    rectangle,
    ref,
    request_of,
)
from test_ceiling_joists import B7_GABLE, Rows, b7_roofed, roof_of, roofed
from test_interior_walls import b10, titles

ROOF_1_6 = REGISTRY.get("loft.roof", "1.6.0")
ROOF_1_7 = REGISTRY.get("loft.roof", "1.7.0")
GOLDEN = "b7-gable-ends"
CASES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "gable-end-cases.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000ab1e5")

# --- B7's gable ends, typed from buildings.md ---------------------------------------

PLATE = 1.5 + 9.25 + 23 / 32 + 97.125  # 108.59375
DEPTH = 7.25  # 2x8 rafters
HEEL = DEPTH / 3  # the heel held to a third of the depth: 29/12
W = 192.0
OSB_T = 7 / 16


def underside(y: float, rise: int = 6) -> float:
    """The rafters' underside over Y: the heel's foot plus the run from the
    nearer eave wall's outside face at the pitch."""
    return PLATE - HEEL + min(y, W - y) * rise / 12


def top_plane(y: float, rise: int = 6) -> float:
    return underside(y, rise) + DEPTH * math.hypot(12, rise) / 12


LEFT = [21.5 + 16 * k for k in range(11)]  # e4, from the front
RIGHT = [170.5 - 16 * k for k in range(11)]  # e2, from the back


def long_point(c: float, rise: int = 6) -> float:
    """At the stud's higher face: the one nearer the ridge."""
    d = min(c + 0.75, W - (c - 0.75))
    return d * rise / 12 - HEEL


def typed_stud(c: float, x0: float, rise: int = 6) -> set[tuple[float, float, float]]:
    side = [
        (c - 0.75, PLATE),
        (c + 0.75, PLATE),
        (c + 0.75, underside(c + 0.75, rise)),
        (c - 0.75, underside(c - 0.75, rise)),
    ]
    return {
        (round(x, 6) + 0.0, round(y, 6) + 0.0, round(z, 6) + 0.0)
        for x in (x0, x0 + 5.5)
        for y, z in side
    }


LEFT_COLUMNS = [-0.4375, 5.5, 53.5, 101.5, 149.5, 186.5, 192.4375]
RIGHT_COLUMNS = [-0.4375, 5.5, 42.5, 90.5, 138.5, 186.5, 192.4375]


def osb_area(rise: int = 6) -> float:
    """Y -0.4375 .. 192.4375 under the top plane, above the plate."""
    k = top_plane(0.0, rise) - PLATE
    half = W / 2 + OSB_T
    s = rise / 12
    return 2 * (k * half + s * ((W / 2) ** 2 - OSB_T**2) / 2)


# --- Probes ------------------------------------------------------------------------


def of_role(members: list[ExpandedMember], role: str) -> list[ExpandedMember]:
    return [m for m in members if m.role == role]


def stud_corners(rows: Rows) -> list[set[tuple[float, float, float]]]:
    """Each gable stud's 8 corners (in), sorted by (X, Y)."""
    found = bodies_of(rows, "gable_stud")
    return sorted(found, key=min)


def bodies_of(rows: Rows, role: str) -> list[set[tuple[float, float, float]]]:
    found = bodies(members_of(rows), (role,))
    assert all(n == 1 for n in found.values())
    return [set(pts) for _, _, pts in found]


def section_area(rows: Rows, member: ExpandedMember) -> float:
    """A body's sketch area (in^2), by the shoelace."""
    by_id = {m.id: m.feature for m in members_of(rows)}
    assert isinstance(member.feature, ExtrudeFeature)
    sketch = by_id[member.feature.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)
    lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
    total = sum(e.start.x * e.end.y - e.end.x * e.start.y for e in lines) / 2
    return abs(total) / IN**2


def b7_gabled(length: float = 288.0, raw: dict[str, Any] | None = None) -> Rows:
    return b7_roofed(length, raw, ROOF_1_7)


# --- B7 ---------------------------------------------------------------------------


def test_b7_frames_eleven_studs_a_gable_on_each_walls_layout() -> None:
    rows = b7_gabled()
    studs = of_role(roof_of(rows), "gable_stud")
    assert len(studs) == 22
    want = [typed_stud(c, 0.0) for c in LEFT] + [typed_stud(c, 282.5) for c in RIGHT]
    assert stud_corners(rows) == sorted(want, key=min)
    for m in studs:
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("2x6", "spf_lumber")
    names = [m.name for m in studs]
    # Clockwise from the front: the left wall (e4) first.
    assert names == [f"e4/slot/{n}" for n in range(1, 12)] + [
        f"e2/slot/{n}" for n in range(1, 12)
    ]


def test_the_right_wall_lays_out_from_the_back() -> None:
    """The PM's Y 21.5 .. 181.5 is the left gable's only: the right wall runs
    clockwise from the back, so its centres are Y 170.5 .. 10.5, the mirror,
    and its long points sum the same."""
    rows = b7_gabled()
    found = boxes(members_of(rows), ("gable_stud",))
    left = sorted((b[2] + b[3]) / 2 for b in found if b[0] == 0.0)
    right = sorted((b[2] + b[3]) / 2 for b in found if b[0] == 282.5)
    assert left == LEFT
    assert right == sorted(RIGHT)
    assert right == [W - c for c in reversed(left)]


def test_the_long_points_are_buildings_mds() -> None:
    """d / 2 - 29/12 at the higher face, measured from the plate's top."""
    assert pytest.approx(106.1770833, abs=1e-7) == PLATE - HEEL
    assert sum(long_point(c) for c in LEFT) == pytest.approx(262.791667, abs=1e-6)
    assert sum(long_point(c) for c in RIGHT) == pytest.approx(262.791667, abs=1e-6)
    rows = b7_gabled()
    found = boxes(members_of(rows), ("gable_stud",))
    for x0, centres in ((0.0, LEFT), (282.5, RIGHT)):
        mine = sorted(b[5] - PLATE for b in found if b[0] == x0)
        assert mine == pytest.approx(sorted(long_point(c) for c in centres), abs=1e-6)
    # Volume: 5.5 deep, 1.5 wide, the short point 0.75 under the long.
    volume = 8.25 * (262.791667 - 11 * 0.375)
    assert round(volume, 3) == 2134.0
    stud = of_role(roof_of(rows), "gable_stud")[0]
    assert section_area(rows, stud) * 5.5 == pytest.approx(
        5.5 * 1.5 * (long_point(170.5) - 0.375), abs=1e-6
    )


def test_each_stud_meets_the_rafters_underside_face_to_face() -> None:
    """Every top corner is on the underside plane: the gable-end rafter (X
    0..1.5, 286.5..288) bears on the cut tops, and nothing is above it."""
    for rise in (6, 8):
        rows = b7_gabled(raw={**B7_GABLE, "pitch": f"rise_{rise}"})
        for corners in stud_corners(rows):
            tops = [(y, z) for _, y, z in corners if z > PLATE]
            assert len(tops) == 4
            for y, z in tops:
                assert z == pytest.approx(underside(y, rise), abs=1e-6)


def test_the_osb_is_carried_up_to_the_roof_plane() -> None:
    """The wall's columns and corner rips continued, Y -0.4375 .. 192.4375
    outside the framing (X -0.4375..0 and 288..288.4375), from the plate's
    top to the rafters' top plane, peaked at Y 96."""
    rows = b7_gabled()
    panels = of_role(roof_of(rows), "gable_sheathing")
    assert len(panels) == 12
    found = boxes(members_of(rows), ("gable_sheathing",))
    for x0, x1, cuts in (
        (-0.4375, 0.0, LEFT_COLUMNS),
        (288.0, 288.4375, RIGHT_COLUMNS),
    ):
        mine = sorted(b for b in found if b[0] == x0)
        assert [(b[2], b[3]) for b in mine] == list(itertools.pairwise(cuts))
        for b in mine:
            assert (b[1], b[4]) == (x1, PLATE)
            high = 96.0 if b[2] < 96 < b[3] else min(b[3], W - b[2])
            assert b[5] == pytest.approx(top_plane(high), abs=1e-6)
    for m in panels:
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("7/16 OSB", "osb")
    assert [m.name for m in panels[:6]] == [
        "e4/exterior/0",
        "e4/exterior/1",
        "e4/exterior/2",
        "e4/exterior/3",
        "e4/corner/start",
        "e4/corner/end",
    ]
    area = sum(section_area(rows, m) for m in panels) / 2
    assert area == pytest.approx(osb_area(), abs=1e-6)
    assert round(osb_area(), 2) == 5705.19
    # The PM's 4 155.68 is the triangle under the UNDERSIDE: it leaves the
    # end rafter's outside face bare (91.1667^2 / 4 a half).
    assert round(2 * (96 - 29 / 6) ** 2 / 4, 2) == 4155.68


def test_8_12_re_cuts_them() -> None:
    rows = b7_gabled(raw={**B7_GABLE, "pitch": "rise_8"})
    want = [typed_stud(c, 0.0, 8) for c in LEFT] + [
        typed_stud(c, 282.5, 8) for c in RIGHT
    ]
    assert stud_corners(rows) == sorted(want, key=min)
    assert sum(long_point(c, 8) for c in LEFT) == pytest.approx(359.25, abs=1e-9)
    panels = of_role(roof_of(rows), "gable_sheathing")
    area = sum(section_area(rows, m) for m in panels) / 2
    assert area == pytest.approx(osb_area(8), abs=1e-6)
    assert round(osb_area(8), 2) == 7358.36


def test_28_ft_moves_the_right_gable() -> None:
    rows = b7_gabled(336)
    want = [typed_stud(c, 0.0) for c in LEFT] + [typed_stud(c, 330.5) for c in RIGHT]
    assert stud_corners(rows) == sorted(want, key=min)
    assert len(of_role(roof_of(rows), "ceiling_joist")) == 13


def test_none_a_hip_and_a_typed_bearing_are_1_6_0_member_for_member() -> None:
    none = {**B7_GABLE, "gable_ends": "none"}
    assert roof_of(b7_gabled(raw=none)) == roof_of(
        b7_roofed(raw=B7_GABLE, plugin=ROOF_1_6)
    )
    hip = house(rectangle(144, 120), [], {}, None, None)
    assert roof_of(roofed(hip, {"style": "hip"}, ROOF_1_7)) == roof_of(
        roofed(hip, {"style": "hip"}, ROOF_1_6)
    )
    typed = {"span_mm": 192 * IN, "length_mm": 288 * IN, **B7_ROOF}
    assert expand(ROOF_1_7, ROOF_ID, typed, {}) == expand(ROOF_1_6, ROOF_ID, typed, {})


def test_the_gable_ends_follow_1_6_0s_members() -> None:
    """1.7.0 is 1.6.0's members in order, then per end wall (clockwise from
    the front: the left, then the right) its face plane, its studs and its
    panels. The left wall's face is the origin YZ plane, so it takes no
    datum; the right's is YZ offset 288."""
    old = roof_of(b7_roofed(raw=B7_GABLE, plugin=ROOF_1_6))
    new = roof_of(b7_gabled())
    assert new[: len(old)] == old
    tail = new[len(old) :]
    wall = ["section", "gable_stud"] * 11 + ["section", "gable_sheathing"] * 6
    assert [m.role for m in tail] == [*wall, "plane", *wall]
    first = tail[0]
    assert isinstance(first.feature, SketchFeature)
    assert first.feature.params.plane == DatumPlaneRef(kind="datum_plane", plane="YZ")
    plane = tail[len(wall)]
    assert plane.name == "gable/e2/face"
    assert isinstance(plane.feature, DatumFeature)
    assert isinstance(plane.feature.params, DatumOffsetParams)
    assert plane.feature.params.offset_mm == pytest.approx(288 * IN)


def test_unsheathed_walls_get_studs_only_in_their_own_lumber() -> None:
    """B2 on its outline (2x4 walls, no sheathing, 120 span): the studs are
    the wall's 2x4, 3.5 deep, and there is no gable sheathing."""
    rows = roofed(
        house(rectangle(144, 120), [], {}, None, None),
        {"slope_walls": ["e1", "e3"]},
        ROOF_1_7,
    )
    studs = of_role(roof_of(rows), "gable_stud")
    assert studs and not of_role(roof_of(rows), "gable_sheathing")
    assert {m.metadata.profile for m in studs if m.metadata} == {"2x4"}
    found = boxes(members_of(rows), ("gable_stud",))
    assert {(b[0], b[1]) for b in found} == {(0.0, 3.5), (140.5, 144.0)}


def test_along_y_the_gables_are_the_front_and_back() -> None:
    """B7 turned (192 x 288, the left and right walls defining slope, the
    ridge along Y): the front and back walls run through, so their OSB is
    their own face, X 0..192, with no corner rip; the studs stand on their
    layout, Y 0..5.5 and 282.5..288. A through wall lays out from its
    outside corner (X 192), so its slot/6 is at X 96, under the ridge, and is
    cut square to the board's underside."""
    rows = roofed(
        house(rectangle(192, 288), [], B7_STUDS, B7_FLOOR, None),
        {"slope_walls": ["e2", "e4"], **B7_ROOF},
        ROOF_1_7,
    )
    found = boxes(members_of(rows), ("gable_stud",))
    assert len(found) == 22
    assert {(b[2], b[3]) for b in found} == {(0.0, 5.5), (282.5, 288.0)}
    ridge = boxes(roof_of(rows), ("ridge",))[0]
    for b in found:
        c = (b[0] + b[1]) / 2
        want = ridge[4] - PLATE if c == 96.0 else long_point(c)
        assert b[5] - PLATE == pytest.approx(want, abs=1e-6)
    assert sum(1 for b in found if (b[0] + b[1]) / 2 == 96.0) == 2
    panels = boxes(members_of(rows), ("gable_sheathing",))
    assert min(b[0] for b in panels) == 0.0 and max(b[1] for b in panels) == 192.0
    assert {(b[2], b[3]) for b in panels} == {(-0.4375, 0.0), (288.0, 288.4375)}


def test_a_stud_under_the_ridge_is_cut_square_to_it() -> None:
    """A 171 span puts the left wall's slot/5 (Y 85.5) under the ridge board
    (Y 84.75..86.25): that stud is cut flat at the board's underside, a
    ridge post."""
    rows = roofed(
        house(rectangle(288, 171), [], B7_STUDS, B7_FLOOR, None),
        B7_GABLE,
        ROOF_1_7,
    )
    ridge = boxes(roof_of(rows), ("ridge",))[0]
    assert ridge[2:4] == (84.75, 86.25)
    posts = [c for c in stud_corners(rows) if min(y for _, y, _ in c) == 84.75]
    assert len(posts) == 2  # one a gable
    for corners in posts:
        assert {z for _, _, z in corners if z > PLATE} == {ridge[4]}


def test_a_joist_on_an_end_walls_plate_is_not_framed() -> None:
    """At 291 the layout common at 288 sits over the right wall (X 285.5..
    291); 1.6.0 puts its joist on its near face, X 285.75..287.25, on that
    wall's plate. With the gable framed the end wall carries the ceiling
    there, so 1.7.0 frames the other 11 only."""
    rows = roofed(
        house(rectangle(291, 192), [], B7_STUDS, B7_FLOOR, None), B7_GABLE, ROOF_1_7
    )
    found = sorted(boxes(roof_of(rows), ("ceiling_joist",)))
    assert [(b[0], b[1]) for b in found] == [
        (c + 0.75, c + 2.25) for c in range(24, 265, 24)
    ]
    none = roofed(
        house(rectangle(291, 192), [], B7_STUDS, B7_FLOOR, None),
        {**B7_GABLE, "gable_ends": "none"},
        ROOF_1_7,
    )
    assert len(of_role(roof_of(none), "ceiling_joist")) == 12


# --- The update and the manifest --------------------------------------------------


def test_an_update_from_1_6_0_takes_the_new_default() -> None:
    """VISION 2026-10-29: an update takes the new release's defaults, so it
    may add members, and says so. B7 stored at 1.6.0 updates to the roof a
    new 1.7.0 gable is."""
    update = update_for("loft.roof", "1.6.0", REGISTRY)
    assert update is not None and update.to_version == "1.7.0"
    assert "gable studs" in update.summary and "sheathing" in update.summary
    rows = house(rectangle(288, 192), b7_openings(), B7_STUDS, B7_FLOOR, None)
    stored = canonical_inputs(ROOF_1_6.manifest, {"walls": [ref(WALLS_ID)], **B7_GABLE})
    moved = canonical_inputs(ROOF_1_7.manifest, updated_inputs(update, stored))
    assert moved["gable_ends"] == "studs_sheathing"
    assert roof_of(roofed(rows, moved, ROOF_1_7)) == roof_of(
        roofed(rows, B7_GABLE, ROOF_1_7)
    )
    assert update_for("loft.roof", "1.7.0", REGISTRY) is None


def test_the_update_names_what_it_adds_and_re_lays() -> None:
    """B7 at 1.6.0 gains 22 gable studs and 12 panels and re-lays nothing; at
    291 its joist on the right wall's plate goes, a re-lay, so that update
    is offered on its own (PLUGIN-UPDATE-ALL)."""
    for length, adds, relays in (
        (288, ("22 gable studs", "12 gable sheathing panels"), ()),
        (291, ("22 gable studs", "12 gable sheathing panels"), ("1 ceiling joist",)),
    ):
        rows = house(rectangle(length, 192), [], B7_STUDS, B7_FLOOR, None)
        before = roof_of(roofed(rows, B7_GABLE, ROOF_1_6))
        after = roof_of(roofed(rows, B7_GABLE, ROOF_1_7))
        effect = update_effect([("loft.roof", before, after)], REGISTRY)
        assert (effect.adds, effect.relays) == (adds, relays), length


def test_new_roofs_are_1_7_0_and_frame_the_gable_ends() -> None:
    assert REGISTRY.latest("loft.roof").manifest.version == "1.7.0"
    inputs = {i.name: i for i in ROOF_1_7.manifest.inputs}
    choice = inputs["gable_ends"]
    assert isinstance(choice, ChoiceInput)
    assert choice.default == "studs_sheathing"
    assert [o.label for o in choice.options] == ["Studs and sheathing", "None"]
    old = [i.name for i in ROOF_1_6.manifest.inputs]
    assert [n for n in inputs if n not in old] == ["gable_ends"]
    roles = {r.role: r.title for r in ROOF_1_7.manifest.members}
    assert roles["gable_stud"] == "Gable stud"
    assert roles["gable_sheathing"] == "Sheathing"
    assert "gable_stud" in ONE_PIECE_ROLES


# --- No overlaps --------------------------------------------------------------------


def b10_gabled() -> Rows:
    return roofed(b10(roof=False), B7_GABLE, ROOF_1_7)


def test_the_gable_osb_is_outside_the_framing() -> None:
    """Exact here: the panels' boxes meet no other body's but face to face
    (the sloped studs' boxes meet the rafters', so the geometry test probes
    every pair exactly)."""
    for rows in (b7_gabled(), b7_gabled(336), b10_gabled()):
        members = members_of(rows)
        mine = boxes(members, ("gable_sheathing",))
        roles = tuple({m.role for m in members} - {"gable_sheathing"})
        others = boxes(members, roles)
        assert [
            (a, b)
            for a in mine
            for b in [*others, *mine]
            if a is not b
            and all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-6 for k in (0, 2, 4))
        ] == []


# --- The golden and the kernel's cases ------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    names = {
        **titles(),
        **{("loft.roof", r.role): r.title for r in ROOF_1_7.manifest.members},
    }
    out: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        for m in members:
            if m.metadata is not None:
                out.append(
                    CutListMember(
                        feature_id=m.id,
                        role=m.role,
                        title=names[(str(plugin_id), m.role)],
                        plugin_id=plugin_id,
                        metadata=m.metadata,
                    )
                )
    return out


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """b7-ceiling-joists' tree with its roof at 1.7.0, every default kept."""
    rows = b7_gabled()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def _count(rows: Rows, role: str) -> int:
    return sum(1 for m in members_of(rows) if m.role == role)


def cases() -> str:
    """B7 at 28 ft and at 8/12, B10, B7 at 291 (a joist left off the end
    wall), a 171 span (a ridge post) and B7 turned off the origin (the ridge
    along Y, through gable walls); each with its counts."""
    moved = rectangle(192, 288).model_dump(mode="json")
    for e in moved["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    built = {
        "b7-336": b7_gabled(336),
        "b7-8-12": b7_gabled(raw={**B7_GABLE, "pitch": "rise_8"}),
        "b10": b10_gabled(),
        "b7-291": roofed(
            house(rectangle(291, 192), [], B7_STUDS, B7_FLOOR, None),
            B7_GABLE,
            ROOF_1_7,
        ),
        "ridge-post-171": roofed(
            house(rectangle(288, 171), [], B7_STUDS, B7_FLOOR, None),
            B7_GABLE,
            ROOF_1_7,
        ),
        "along-y-moved": roofed(
            house(SketchFeature.model_validate(moved), [], B7_STUDS, {}, None),
            {"slope_walls": ["e2", "e4"], **B7_ROOF},
            ROOF_1_7,
        ),
    }
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            "studs": _count(rows, "gable_stud"),
            "panels": _count(rows, "gable_sheathing"),
            "joists": _count(rows, "ceiling_joist"),
            "request": request_of(rows).model_dump(mode="json"),
        }
        for name, rows in built.items()
    ]
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_is_b7_with_its_joists_and_gable_ends() -> None:
    """b7-ceiling-joists' 228 bodies plus 22 studs and 12 panels: 262."""
    _, metadata = golden()
    assert len(metadata) == 228 + 22 + 12 == 262
    count = Counter(m.title for m in metadata)
    assert count["Gable stud"] == 22
    assert count["Ceiling joist"] == 11


def test_the_kernel_cases_are_the_plugins_expansion() -> None:
    assert gzip.decompress(CASES.read_bytes()).decode() == cases()


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
    CASES.write_bytes(gzip.compress(cases().encode(), mtime=0))
    sys.stdout.write(f"{CASES.name}\n")
