"""SECOND-FLOOR: ``loft.floor`` 1.4.0 on B7's walls, its stairwell framed,
the upper walls and roof on it, and a free stair through the well.

Chief Architect stacks floors on levels, frames the floor above on the walls
below (Build Floor) and cuts the well (Auto Stairwell); Revit hosts a floor
on a level and cuts a shaft. Checked against
``docs/reference-parts/buildings.md`` B7, typed by hand (inches):

* floor 1: PT 2x6 sills Z 0..1.5, 2x10 framing 1.5..10.75, 23/32 subfloor to
  11.46875; the walls 97.125 plate to plate, so their top plates' top is
  108.59375;
* floor 2 on the walls is floor 1 less its sills, raised 108.59375 - 1.5 =
  107.09375: joists Z 108.59375..117.84375, subfloor to 118.5625; the upper
  walls 118.5625..215.6875;
* the well, 43.5 x 120 clear (X 18.25..61.75, Y 36..156): the layout joists
  at X 16 (15.25..16.75) and 64 (63.25..64.75) are the outer trimmer plies,
  doubled inside (16.75..18.25, 61.75..63.25); the joists at X 32 and 48 are
  cut into 4 tails of 31.5 (Y 1.5..33 and 159..190.5) on 4 header plies
  2x10 x 43.5 (Y 33..36 and 156..159); 5 220 in^2 out of the subfloor;
* the roof is B7's, every member raised 107.09375;
* the stair, free: rise 107.09375 = 14 risers of 7.649554, 13 treads of 10
  (two 5/4x6 and a 1/8 gap, 11.125: a 1.125 nosing), closed risers, so each
  nosing sits 0.75 + 11.125 = 11.875 past its riser line and the head is cut
  plumb at u = 10 - 11.875 = -1.875 (the far header's face, Y 156): the top
  nosing at Y 154.125, the bottom riser line at Y 154.125 - (-1.875 + 13 x
  10) = 26. The near header's face (Y 36) is 118.125 from the top nosing,
  where the nosing line stands 107.09375 - 118.125 R / 10 = 2.1875 R =
  16.7333984375 above floor 1, under a ceiling 107.09375 - 9.96875 = 97.125:
  80.3916015625 in of headroom (IRC R311.7.2: 80). The spec's 81.83 (97.125 - 2R)
  put the floor's nosing on the header's face, which would hang the stair's
  head 1.875 in inside the header; and 80 in needs a well of 117.6131 from
  the floor's nosing, 119.4881 from header face to header face.

The geometry golden ``b7-second-floor`` is written from here and pinned by
this module (``services/geometry/tests/test_second_floor_b7.py`` checks it
against an independent script on STEP). Regenerate after a deliberate change
(a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_second_floor.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, update_for
from loft_plugins.api import ExpandInputs
from loft_plugins.builtin.stair import layout
from loft_plugins.updates import updated_inputs
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    EvaluateTreeRequest,
    ExpandedMember,
    SketchFeature,
)
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

sys.path.insert(0, str(Path(__file__).parent))
import test_building_outline as outline
from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    boxes,
    envelope,
    expand,
    members_json,
    opening,
    overlaps,
    rectangle,
    ref,
    request_of,
)

GOLDEN = "b7-second-floor"
PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000f102")
SKETCH_ID = outline.SKETCH_ID
FLOOR_ID = outline.FLOOR_ID
WALLS_ID = outline.WALLS_ID
FLOOR2_ID = uuid.UUID("00000000-0000-0000-0000-00000000b7f2")
WALLS2_ID = uuid.UUID("00000000-0000-0000-0000-00000000b7a2")
ROOF_ID = outline.ROOF_ID
STAIR_ID = uuid.UUID("00000000-0000-0000-0000-00000000b75a")

FLOOR = REGISTRY.get("loft.floor", "1.4.0")
FLOOR_1_3 = REGISTRY.get("loft.floor", "1.3.0")
WALL = REGISTRY.latest("loft.wall")
ROOF = REGISTRY.latest("loft.roof")
STAIR = REGISTRY.get("loft.stair", "1.0.0")

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]

# --- B7, typed from buildings.md (inches) ------------------------------------------

SUB = 1.5 + 9.25 + 23 / 32  # floor 1's subfloor top: 11.46875
PLATE = SUB + 97.125  # 108.59375
RAISE = PLATE - 1.5  # floor 2 is floor 1 less its 1.5 in sills: 107.09375
SUB2 = PLATE + 9.25 + 23 / 32  # 118.5625
RISER = RAISE / 14
TREAD = 10.0
HEAD = TREAD - (0.75 + 2 * 5.5 + 0.125)  # -1.875: the top riser line
NOSE_Y = 156.0 + HEAD  # 154.125: the head plumb on the far header's face
CEILING = RAISE - (9.25 + 23 / 32)  # 97.125 under floor 2's framing
OPENING = NOSE_Y - 36.0  # 118.125: the top nosing to the near header's face

WELL = {"stairwell": "framed"}  # 1.4.0's defaults are B7's well
STAIR_RAW: dict[str, Any] = {
    "rise_mm": RAISE * IN,
    "x_mm": 40 * IN,
    "y_mm": NOSE_Y * IN,
    "bottom_mm": SUB * IN,
    "direction": "neg_y",
    "tread_depth_mm": TREAD * IN,
    "risers": "closed",
    "opening_length_mm": OPENING * IN,
    "floor_depth_mm": (9.25 + 23 / 32) * IN,
}

#: What B7's 1.1.0 openings typed mean at 1.5.0 (test_update_all.AS_TYPED).
AS_TYPED = {"measure_from": "start", "size": "custom", "draw_unit": "none"}


def b7_openings() -> list[tuple[Any, str, str, dict[str, Any]]]:
    door, window = REGISTRY.latest("loft.door"), REGISTRY.latest("loft.window")
    return [
        (
            door if p.manifest.id == "loft.door" else window,
            name,
            seg,
            {**raw, **AS_TYPED},
        )
        for p, name, seg, raw in outline.b7_openings()
    ]


def tree(
    *,
    storeys: int = 2,
    floor2: dict[str, Any] | None = None,
    stair: bool = True,
) -> Rows:
    """B7 today (floor 1.4.0 on the outline, walls 1.5.0 on it with B7's
    openings), then floor 2 on those walls (*floor2* over B7's 2x10 and the
    well), the upper walls on it with no openings, the roof on them and the
    free stair. One storey: the roof on the walls."""
    sketch = rectangle(288, 192)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    rows: Rows = [(SKETCH_ID, sketch, [])]

    def add(fid: uuid.UUID, plugin: Any, raw: dict[str, Any], hosted: Any = ()) -> None:
        members = expand(plugin, fid, raw, dict(earlier), hosted)
        env = envelope(plugin, raw)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        rows.append((fid, env, members))

    on = ref(SKETCH_ID)
    add(FLOOR_ID, FLOOR, {"outline": on, **B7_FLOOR})
    walls = {"outline": on, "floor": ref(FLOOR_ID), **B7_STUDS}
    with_walls = {**earlier, WALLS_ID: envelope(WALL, walls)}
    hosted = [
        opening(p, name, WALLS_ID, {"wall_segment": [seg], **raw}, with_walls)
        for p, name, seg, raw in b7_openings()
    ]
    add(WALLS_ID, WALL, walls, tuple(hosted))
    for h in hosted:
        add(
            h.feature_id,
            REGISTRY.get(h.plugin_id, h.plugin_version),
            dict(h.inputs.values),
        )
    top = WALLS_ID
    if storeys == 2:
        raw = {"outline": on, "walls": [ref(WALLS_ID)], **B7_FLOOR, **WELL}
        add(FLOOR2_ID, FLOOR, {**raw, **(floor2 or {})})
        add(WALLS2_ID, WALL, {"outline": on, "floor": ref(FLOOR2_ID), **B7_STUDS})
        top = WALLS2_ID
    add(ROOF_ID, ROOF, {"walls": [ref(top)], "slope_walls": ["e1", "e3"], **B7_ROOF})
    if storeys == 2 and stair:
        add(STAIR_ID, STAIR, STAIR_RAW)
    return rows


def row(rows: Rows, fid: uuid.UUID) -> list[ExpandedMember]:
    return next(ms for f, _, ms in rows if f == fid)


def of(members: list[ExpandedMember], *roles: str) -> list[ExpandedMember]:
    """*members* of *roles*, with every member they are built on."""
    return [m for m in members if m.role in roles or m.metadata is None]


def raised(items: list[tuple[float, ...]], dz: float) -> list[tuple[float, ...]]:
    return sorted(
        tuple(round(v + (dz if k >= 4 else 0.0), 6) + 0.0 for k, v in enumerate(b))
        for b in items
    )


# --- The floor on the walls --------------------------------------------------------


def test_floor_2_is_floor_1_less_its_sills_raised_107_09375() -> None:
    rows = tree(floor2={"stairwell": "none"}, stair=False)
    first, second = row(rows, FLOOR_ID), row(rows, FLOOR2_ID)
    framing = ("joist", "rim", "subfloor")
    assert Counter(m.role for m in second if m.metadata) == Counter(
        {"joist": 19, "rim": 2, "subfloor": 14}
    )
    assert sorted(boxes(of(second, *framing))) == raised(
        boxes(of(first, *framing)), RAISE
    )
    joists = boxes(of(second, "joist"))
    assert {(b[4], b[5]) for b in joists} == {(108.59375, 117.84375)}
    assert max(b[5] for b in boxes(of(second, "subfloor"))) == SUB2 == 118.5625


def test_the_well_is_framed_between_the_joists_at_16_and_64() -> None:
    floor = row(tree(stair=False), FLOOR2_ID)
    z = (108.59375, 117.84375)

    def at(role: str) -> list[tuple[float, ...]]:
        return sorted(boxes(of(floor, role)))

    assert at("trimmer") == [
        (16.75, 18.25, 1.5, 190.5, *z),
        (61.75, 63.25, 1.5, 190.5, *z),
    ]
    assert at("header") == [
        (18.25, 61.75, y0, y0 + 1.5, *z) for y0 in (33.0, 34.5, 156.0, 157.5)
    ]
    assert at("tail_joist") == [
        (x, x + 1.5, y0, y1, *z)
        for x in (31.25, 47.25)
        for y0, y1 in ((1.5, 33.0), (159.0, 190.5))
    ]
    joists = at("joist")
    assert len(joists) == 17
    assert (15.25, 16.75, 1.5, 190.5, *z) in joists
    assert (63.25, 64.75, 1.5, 190.5, *z) in joists
    assert not [b for b in joists if 18.25 < b[0] < 61.75]
    assert overlaps([*boxes(of(floor, *(m.role for m in floor)))]) == []


def test_the_well_keeps_the_layout_ids() -> None:
    """joist/2 and joist/5 (the layout joists at X 16 and 64) are the outer
    plies; joist/3 and /4 (X 32, 48) became tail_joist/6..9."""
    floor = row(tree(stair=False), FLOOR2_ID)
    ids = Counter((m.role, m.index) for m in floor if m.metadata)
    assert ("joist", 2) in ids and ("joist", 5) in ids
    assert ("joist", 3) not in ids and ("joist", 4) not in ids
    assert sorted(i for r, i in ids if r == "tail_joist") == [6, 7, 8, 9]
    assert sorted(i for r, i in ids if r == "trimmer") == [0, 2]
    assert sorted(i for r, i in ids if r == "header") == [0, 1, 2, 3]


def _net_area(sketch: SketchFeature) -> float:
    """A sketch's loops' signed area (in^2): outer counter-clockwise, holes
    clockwise, so the net."""
    total = 0.0
    for e in sketch.params.entities:
        assert isinstance(e, SketchLine)
        total += e.start.x * e.end.y - e.end.x * e.start.y
    return total / 2 / IN**2


def test_the_subfloor_loses_the_well() -> None:
    """288 x 192 less 43.5 x 120 = 50 076 in^2; the panel the well crosses
    in row 2 (Y 96..144, X 0..96) is two pieces."""
    floor = row(tree(stair=False), FLOOR2_ID)
    sections = [
        m.feature
        for m in floor
        if m.role == "subfloor_section" and isinstance(m.feature, SketchFeature)
    ]
    assert len(sections) == 15
    assert sum(_net_area(s) for s in sections) == pytest.approx(
        288 * 192 - 43.5 * 120, abs=1e-6
    )
    assert 43.5 * 120 == 5220
    names = sorted(m.name or "" for m in floor if m.role == "subfloor")
    assert "row/2/0/0" in names and "row/2/0/1" in names


# --- The storey above --------------------------------------------------------------


def test_the_upper_walls_stand_on_floor_2() -> None:
    walls = row(tree(stair=False), WALLS2_ID)
    framing = boxes([m for m in walls if m.role != "sheathing" or m.metadata is None])
    assert min(b[4] for b in framing) == 118.5625
    assert max(b[5] for b in framing) == 215.6875 == SUB2 + 97.125


def test_the_roof_is_b7s_raised_107_09375() -> None:
    one, two = tree(storeys=1), tree(stair=False)
    roles = ("rafter", "ridge", "ceiling_joist", "gable_stud", "gable_sheathing")
    low, high = row(one, ROOF_ID), row(two, ROOF_ID)
    assert sorted(boxes(of(high, *roles))) == raised(boxes(of(low, *roles)), RAISE)
    assert Counter(m.role for m in high if m.metadata) == Counter(
        m.role for m in low if m.metadata
    )


# --- The stair through the well ----------------------------------------------------


def _stair(raw: dict[str, Any]) -> Any:
    inputs = canonical_inputs(STAIR.manifest, raw)
    return layout(ExpandInputs(STAIR_ID, inputs))


def test_the_stair_has_14_risers_and_13_treads_from_y_26_to_the_header() -> None:
    stair = _stair(STAIR_RAW)
    assert (stair.risers, stair.treads) == (14, 13)
    assert stair.riser == pytest.approx(7.649554, abs=1e-6)
    assert stair.top_line == HEAD == -1.875
    assert NOSE_Y - stair.top_line == 156.0  # the head on the far header's face
    assert NOSE_Y - stair.foot_u == 26.0  # the bottom riser line


def test_the_headroom_under_the_near_header_is_80_39_not_81_83() -> None:
    nosing = RAISE - OPENING * RISER / TREAD
    assert nosing == pytest.approx(2.1875 * RISER, abs=1e-12)
    assert CEILING == 97.125
    assert CEILING - nosing == 80.3916015625  # exactly: 97.125 - 2.1875 R
    assert round(CEILING - 2 * RISER, 2) == 81.83  # the spec's, a header off
    need = (RAISE - (CEILING - 80.0)) * TREAD / RISER
    assert round(need, 4) == 117.6131
    assert round(need - HEAD, 4) == 119.4881  # header face to header face
    _stair({**STAIR_RAW, "opening_length_mm": (need + 0.01) * IN})
    with pytest.raises(PluginError) as caught:
        _stair({**STAIR_RAW, "opening_length_mm": (need - 0.01) * IN})
    assert caught.value.message.startswith("IRC R311.7.2:")


#: The stair's square members (its stringers and rail are sloped: their boxes
#: are not their solids, so the kernel's exact check covers them).
SQUARE = ("tread", "riser", "handrail_post")


def test_the_stair_stands_in_the_well() -> None:
    """Every square stair body reaching floor 2's underside lies inside the
    well, none under floor 1's subfloor; the stringers' heads end on the far
    header's face."""
    stair = row(tree(), STAIR_ID)
    for b in boxes(of(stair, *SQUARE)):
        assert b[4] >= SUB - 1e-6
        assert b[0] >= 18.25 - 1e-6 and b[1] <= 61.75 + 1e-6
        if b[5] > PLATE + 1e-6:
            assert b[2] >= 36.0 - 1e-6 and b[3] <= 156.0 + 1e-6
    assert max(b[3] for b in boxes(of(stair, "stringer"))) == 156.0


def test_nothing_overlaps_in_the_house() -> None:
    rows = tree()
    floor2, stair = row(rows, FLOOR2_ID), row(rows, STAIR_ID)
    walls = row(rows, WALLS_ID)
    # The subfloor's notched panels are not their boxes either: the kernel's
    # exact check (test_second_floor_b7.py) covers them.
    framing = boxes(of(floor2, "joist", "tail_joist", "trimmer", "header", "rim"))
    items = [*framing, *boxes(of(stair, *SQUARE)), *boxes(walls)]
    assert overlaps(items) == []


# --- Refusals and the other cases --------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"well_width_at_mm": 2.0 * IN}, "well_width_at_mm"),
        ({"well_width_at_mm": 250.0 * IN}, "well_width_mm"),
        ({"well_depth_at_mm": 3.0 * IN}, "well_depth_at_mm"),
        ({"well_depth_mm": 160.0 * IN}, "well_depth_mm"),
    ],
)
def test_a_well_whose_framing_meets_the_edge_is_refused(
    raw: dict[str, Any], field: str
) -> None:
    with pytest.raises(PluginError) as caught:
        tree(floor2=raw, stair=False)
    assert caught.value.code == PLUGIN_INPUT_UNSUPPORTED
    assert caught.value.input == field


def test_walls_outside_the_floor_are_refused() -> None:
    small = {"outline": None, "width_mm": 200 * IN, "depth_mm": 192 * IN}
    with pytest.raises(PluginError) as caught:
        tree(floor2=small, stair=False)
    assert caught.value.input == "walls"
    assert "outside the floor" in caught.value.message


def test_a_well_off_the_layout_frames_both_plies() -> None:
    """At X 20 (to 63.5) the trimmers' outer plies (17..18.5, 65..66.5) are
    no layout joist's: all four plies are framed, the joist at 64 (63.25..
    64.75, under the far plies) is left out, the ones at 32 and 48 are cut
    and the one at 16 (to 16.75) stays."""
    floor = row(tree(floor2={"well_width_at_mm": 20 * IN}, stair=False), FLOOR2_ID)
    trimmers = sorted(b[:2] for b in boxes(of(floor, "trimmer")))
    assert trimmers == [(17.0, 18.5), (18.5, 20.0), (63.5, 65.0), (65.0, 66.5)]
    xs = sorted(b[0] for b in boxes(of(floor, "joist")))
    assert 63.25 not in xs and 15.25 in xs
    assert len(boxes(of(floor, "tail_joist"))) == 4
    assert overlaps(boxes(of(floor, *(m.role for m in floor)))) == []


def test_joists_along_the_width_turn_the_well() -> None:
    """Bearing on the side walls the joists run along X: the trimmers run
    along X beside Y 36 and 156, the headers across X 18.25 and 61.75."""
    raw = {"joists_bear_on": "left_right", "well_depth_at_mm": 40 * IN}
    raw["well_depth_mm"] = 112 * IN
    floor = row(tree(floor2=raw, stair=False), FLOOR2_ID)
    trimmers = boxes(of(floor, "trimmer"))
    assert all(b[1] - b[0] == 285.0 for b in trimmers)
    headers = sorted(b[:4] for b in boxes(of(floor, "header")))
    assert headers[0] == (15.25, 16.75, 40.0, 152.0)
    assert overlaps(boxes(of(floor, *(m.role for m in floor)))) == []


# --- Updates: a floor 1.3.0 is 1.4.0 member for member -----------------------------


def test_a_floor_1_3_0_updates_quietly_to_1_4_0() -> None:
    update = update_for("loft.floor", "1.3.0", REGISTRY)
    assert update is not None and update.to_version == "1.4.0"
    assert update_for("loft.floor", "1.2.0", REGISTRY).to_version == "1.4.0"  # type: ignore[union-attr]
    sketch = rectangle(288, 192)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    raw = canonical_inputs(FLOOR_1_3.manifest, {"outline": ref(SKETCH_ID), **B7_FLOOR})
    before = expand(FLOOR_1_3, FLOOR_ID, raw, earlier)
    mapped = updated_inputs(update, raw, ExpandInputs(FLOOR_ID, raw, earlier))
    after = expand(FLOOR, FLOOR_ID, mapped, earlier)
    assert [m.model_dump() for m in after] == [m.model_dump() for m in before]


# --- The golden --------------------------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    out: list[CutListMember] = []
    for _, env, members in rows:
        params = getattr(env, "params", None)
        plugin_id = getattr(params, "plugin_id", None)
        if plugin_id is None:
            continue
        manifest = REGISTRY.get(plugin_id, params.plugin_version).manifest  # type: ignore[union-attr]
        titles = {r.role: r.title for r in manifest.members}
        out += [
            CutListMember(
                feature_id=m.id,
                role=m.role,
                title=titles[m.role],
                plugin_id=plugin_id,
                metadata=m.metadata,
            )
            for m in members
            if m.metadata is not None
        ]
    return out


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    rows = tree()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_counts() -> None:
    """B7 today (b7-update-all's 280 bodies less its roof's 26 rafters,
    ridge, 11 ceiling joists, 22 gable studs and 12 gable panels: 208);
    floor 2 (17 joists, 4 tails, 2 trimmers, 4 headers, 2 rims and 15
    subfloor pieces: 44); the upper walls with no openings (front and back
    19 studs, 3 plates and 6 panels each; the sides 13 studs, 3 plates, 4
    panels and 2 corner rips: 100); the roof's 72; the stair's 3 stringers,
    26 tread boards, 13 risers, its rail and 3 posts (46): 470."""
    _, metadata = golden()
    count = Counter((m.plugin_id, m.role) for m in metadata)
    assert len(metadata) == 208 + 44 + 100 + 72 + 46 == 470
    floors = {r: n for (p, r), n in count.items() if p == "loft.floor"}
    assert floors == {
        "joist": 19 + 17,
        "rim": 4,
        "sill": 4,
        "subfloor": 14 + 15,
        "tail_joist": 4,
        "trimmer": 2,
        "header": 4,
    }
    stair = {r: n for (p, r), n in count.items() if p == "loft.stair"}
    assert stair == {
        "stringer": 3,
        "tread": 26,
        "riser": 13,
        "handrail": 1,
        "handrail_post": 3,
    }


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(
        f"{GOLDEN}: {len(request.features)} features, {len(metadata)} bodies\n"
    )
