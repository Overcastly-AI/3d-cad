"""CASEWORK-B10: ``loft.cabinets`` 1.1.0 on B10's finished faces.

Checked by hand against ``docs/reference-parts/casework.md`` C2 and C4 and
``buildings.md`` B10 (typed below, never read from the plugin):

* 1.1.0 is 1.0.0 box for box; only the run's frame moves: its backs on the
  face's gypsum (a 1.4.0 wall's Inside gypsum, a partition's), its Distance
  from the finished face's end. On B7 (no gypsum) a 1.1.0 run with a 1/2 in
  Back gap is 1.0.0's C2 panel for panel.
* C2 on B10 with the walls' inside gypsum on: the left wall's board is
  X 5.5..6 from Y 6 to the back wall's board at Y 186, so the base run starts
  at Y 186 and its filler is 3 (the back board takes the other 1/2 of 1.0.0's
  3.5), keeping the sink centred on the window at Y 96 and the run's end at
  Y 54; the wall run is Y 165..114 as before. 91 panels, 1.0.0's volume less
  1/2 x 3/4 x 79.5 of filler.
* C4 on P1's +X face (its left, P1 drawn from the back): V3021 Y 186..156,
  VDB1521 Y 156..141, backs at X 182.25; 6 036.17578125 in^3, 578.75 in of
  banding, 4 hinges and 3 pairs of 20 in slides; V3021 -> V3621 moves the
  VDB to Y 150..135, 0.75 clear of P2's board at Y 134.25.

The goldens ``c2-kitchen-b10-left-wall``, ``c4-vanity-b10-p1``,
``c4-v3621-b10-p1`` and ``b10-inside-gypsum`` (B10 with the walls' inside
gypsum, INTERIOR-WALLS-INSIDE-GYPSUM-GOLDEN) are written from here and pinned
by this module: ``uv run python packages/loft-plugins/tests/test_casework_b10.py``
(then ``npx prettier --write`` the cabinet goldens' members.json). Their
kernel acceptance is ``services/geometry/tests/test_casework_b10.py``.
"""

import gzip
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_wire.cut_list import CutListMember
from loft_wire.features import AuthoredEnvelope, ExpandedMember, FeatureRef
from loft_wire.plugins import ChoiceInput, FeatureReferenceInput

sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import ROOT, WALLS_ID, boxes, overlaps
from test_building_outline import members_json as house_members_json
from test_building_outline import request_of as house_request_of
from test_cabinets import (
    C2_BASE,
    C2_WALL,
    GOLDENS,
    IN,
    RUN_ID,
    WALL_RUN_ID,
    Bounds,
    banding_in,
    box,
    c2,
    hardware,
    members_json,
    placed,
    request_of,
    volume,
)
from test_interior_walls import INTERIOR_ID, Rows, b10, titles

V1 = REGISTRY.get("loft.cabinets", "1.0.0")
V1_1 = REGISTRY.get("loft.cabinets", "1.1.0")
C4_ID = uuid.UUID("00000000-0000-0000-0000-00000000c401")
HOUSE_PART_ID = uuid.UUID("00000000-0000-0000-0000-000000010b1a")
SUBFLOOR = 1.5 + 9.25 + 23 / 32
#: buildings.md B10: P1 framed X 178.25..181.75, its +X board to 182.25; P2
#: framed Y 130.25..133.75, its +Y board to 134.25.
P1_BOARD = 182.25
P2_BOARD = 134.25


def earlier_of(rows: Rows) -> dict[uuid.UUID, AuthoredEnvelope]:
    out: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        out[fid] = env
        for m in members:
            out[m.id] = m.feature
    return out


def run(rows: Rows, raw: dict[str, Any], fid: uuid.UUID) -> list[ExpandedMember]:
    inputs = canonical_inputs(V1_1.manifest, raw)
    return expand(V1_1, fid, inputs, earlier_of(rows))


def span(members: list[ExpandedMember]) -> Bounds:
    bs = [p[3] for p in placed(members)]
    return (
        min(b[0] for b in bs),
        max(b[1] for b in bs),
        min(b[2] for b in bs),
        max(b[3] for b in bs),
        min(b[4] for b in bs),
        max(b[5] for b in bs),
    )


def house_boxes(rows: Rows) -> list[tuple[float, ...]]:
    """Every axis-aligned body of the house (its OSB, rafters, units and
    slab left to the kernel test, which probes them exactly)."""
    house = [m for _, _, ms in rows for m in ms]
    skip = {"sheathing", "rafter", "frame", "glazing", "slab"}
    return boxes(house, tuple({m.role for m in house} - skip))


def touching_nothing(members: list[ExpandedMember], rows: Rows) -> bool:
    panels = [p[3] for p in placed(members)]
    rest = house_boxes(rows)
    return overlaps(panels) == [] and all(
        not [p for p in overlaps([panel, *rest]) if p[0] == 0] for panel in panels
    )


# --- The manifest ---------------------------------------------------------------------


def test_1_1_0_picks_a_wall_or_a_partition_and_its_face() -> None:
    m = V1_1.manifest
    wall = next(i for i in m.inputs if i.name == "wall")
    assert isinstance(wall, FeatureReferenceInput)
    assert wall.plugin_ids == ["loft.wall", "loft.interior_wall"]
    face = next(i for i in m.inputs if i.name == "face")
    assert isinstance(face, ChoiceInput)
    assert [o.value for o in face.options] == ["left", "right"]
    names = [i.name for i in m.inputs]
    assert names.index("face") == names.index("wall_segment") + 1
    # Every other input and every role is 1.0.0's.
    assert [n for n in names if n != "face"] == [i.name for i in V1.manifest.inputs]
    assert m.members == V1.manifest.members
    assert (V1.manifest.version, m.version) == ("1.0.0", "1.1.0")
    assert REGISTRY.latest("loft.cabinets").manifest.version == "1.1.0"


def test_on_b7_a_1_1_0_run_with_a_half_inch_gap_is_1_0_0_s_c2() -> None:
    """No gypsum on B7's walls: the finished face is the framing, so 1.1.0
    with 1.0.0's Back gap of 1/2 places every panel where 1.0.0 does."""
    old = c2()
    from test_cabinets import b7_house

    _, earlier = b7_house()
    wall = {
        "wall": FeatureRef(kind="feature", feature_id=WALLS_ID),
        "wall_segment": ["e4"],
        "measure_from": "end",
        "gap_mm": 0.5 * IN,
    }
    new = expand(
        V1_1,
        RUN_ID,
        canonical_inputs(V1_1.manifest, {**wall, "boxes": C2_BASE}),
        dict(earlier),
    )
    assert placed(new) == placed(old["base"])
    assert [m.id for m in new] == [m.id for m in old["base"]]


# --- C2 on B10's left wall ------------------------------------------------------------

#: casework.md C2 on B10: the filler 3 (the back wall's board takes 1/2).
C2_B10_BASE = [box("filler", 3.0), *C2_BASE[1:]]


def b10_gypsum() -> Rows:
    return b10(walls={"finish": "gypsum_1_2"})


def c2_b10(
    base: list[dict[str, Any]] | None = None,
) -> dict[str, list[ExpandedMember]]:
    rows = b10_gypsum()
    wall = {
        "wall": FeatureRef(kind="feature", feature_id=WALLS_ID),
        "wall_segment": ["e4"],
        "measure_from": "end",
    }
    return {
        "base": run(rows, {**wall, "boxes": base or C2_B10_BASE}, RUN_ID),
        "wall": run(
            rows, {**wall, "offset_mm": 21.0 * IN, "boxes": C2_WALL}, WALL_RUN_ID
        ),
    }


def test_c2_stands_on_b10_s_left_wall_gypsum() -> None:
    """The base run from the back wall's board (Y 186) to Y 54, its backs on
    the left wall's board (X 6), on the subfloor; the sink centred on the
    window at Y 96; the wall run Y 165..114, 54 above the subfloor."""
    runs = c2_b10()
    base, wall = runs["base"], runs["wall"]
    x0, _, y0, y1, z0, z1 = span(base)
    assert (x0, y0, y1, z0) == (6.0, 54.0, 186.0, SUBFLOOR)
    assert z1 == pytest.approx(SUBFLOOR + 84)
    assert span(wall)[:5] == (6.0, 18.75, 114.0, 165.0, SUBFLOOR + 54)
    sink_sides = sorted(p[3][2] for p in placed(base) if p[0] == "side")[2:4]
    assert (sink_sides[0] + sink_sides[1] + 0.75) / 2 == 96.0
    filler = [p[3] for p in placed(base) if p[0] == "filler"]
    assert filler == [(30.0, 30.75, 183.0, 186.0, SUBFLOOR + 4.5, SUBFLOOR + 84)]
    # 91 panels; 1.0.0's C2 on B7 less 1/2 of its 3.5 x 79.5 filler.
    assert len(placed(base)) + len(placed(wall)) == 91
    old = c2()
    want = volume(old["base"]) + volume(old["wall"]) - 0.5 * 0.75 * 79.5
    assert volume(base) + volume(wall) == pytest.approx(want, abs=1e-9)
    assert hardware(base) == {"hinge": 13, "slide_22": 5}
    assert hardware(wall) == {"hinge": 4}


def test_c2_on_b10_touches_nothing() -> None:
    """No panel overlaps another or any of B10's bodies: its gypsum (the
    left and back boards), studs, blocks and partitions."""
    rows = b10_gypsum()
    runs = c2_b10()
    both = runs["base"] + runs["wall"]
    assert touching_nothing(both, rows)
    gypsum = [b for b in boxes([m for _, _, ms in rows for m in ms], ("finish",))]
    left = [b for b in gypsum if b[0] == 5.5 and b[1] == 6.0]
    back = [b for b in gypsum if b[2] == 186.0 and b[3] == 186.5]
    assert left and back
    assert max(b[3] for b in left) == 186.0


def test_c2_b24_to_b21_on_b10_ends_at_57() -> None:
    before = c2_b10()["base"]
    after = c2_b10([*C2_B10_BASE[:-1], box("base", 21)])["base"]
    assert span(after)[2] == 57.0
    assert {m.id for m in after} == {m.id for m in before}
    last = {m.id for m in before if (m.name or "").startswith("box/5/")}
    old = dict(
        zip((m.id for m in before if m.role in _BODY), placed(before), strict=True)
    )
    new = dict(
        zip((m.id for m in after if m.role in _BODY), placed(after), strict=True)
    )
    changed = {fid for fid in old if old[fid] != new[fid]}
    assert changed and changed <= last


_BODY = {role.role for role in V1.manifest.members} - {"level", "plane", "section"}


def test_a_run_must_fit_the_finished_face() -> None:
    """The left wall's finished face is its board, Y 6..186: 181 - 2 x 1/2.
    The 132 in run fits it from 48 in, not from 48.5."""
    rows = b10_gypsum()
    wall = {
        "wall": FeatureRef(kind="feature", feature_id=WALLS_ID),
        "wall_segment": ["e4"],
    }
    run(rows, {**wall, "offset_mm": 48 * IN, "boxes": C2_B10_BASE}, RUN_ID)
    with pytest.raises(PluginError, match="does not fit the 180 in finished face"):
        run(rows, {**wall, "offset_mm": 48.5 * IN, "boxes": C2_B10_BASE}, RUN_ID)


def test_a_through_wall_s_face_runs_between_the_walls_it_meets() -> None:
    """B7's back wall runs through, X 0..288 outside, but its inside face
    (no gypsum) runs X 5.5..282.5, between the side walls': a run from its
    start stands in the room's corner, where 1.0.0's stood in the side
    wall's framing."""
    from test_cabinets import b7_house

    _, earlier = b7_house()
    raw = {
        "wall": FeatureRef(kind="feature", feature_id=WALLS_ID),
        "wall_segment": ["e3"],
        "boxes": [box("base", 24)],
    }
    new = expand(V1_1, RUN_ID, canonical_inputs(V1_1.manifest, raw), dict(earlier))
    old = expand(V1, RUN_ID, canonical_inputs(V1.manifest, raw), dict(earlier))
    assert (span(new)[0], span(new)[1], span(new)[3]) == (5.5, 29.5, 186.5)
    assert span(old)[:2] == (0.0, 24.0)


def test_a_wall_run_past_a_partition_meeting_it_is_refused() -> None:
    """B10's back wall from its board's start (X 5.5): 7 x B24 would end
    at X 173.5, clear of P1 (X 178.25..181.75 with its boards from 177.75);
    8 would pass it."""
    rows = b10()
    raw = {
        "wall": FeatureRef(kind="feature", feature_id=WALLS_ID),
        "wall_segment": ["e3"],
    }
    run(rows, {**raw, "boxes": [box("base", 24)] * 7}, RUN_ID)
    with pytest.raises(PluginError, match="would pass partition e5"):
        run(rows, {**raw, "boxes": [box("base", 24)] * 8}, RUN_ID)


# --- C4 on P1 -------------------------------------------------------------------------

VDB1521 = box("vanity", 15, fronts="drawers")


def c4(vanity: float = 30, **raw: Any) -> list[ExpandedMember]:
    rows = b10()
    return run(
        rows,
        {
            "wall": FeatureRef(kind="feature", feature_id=INTERIOR_ID),
            "wall_segment": ["e5"],
            "face": "left",
            "offset_mm": 0.5 * IN,
            "carcass": "melamine",
            "boxes": [box("vanity", vanity, shelves=0), VDB1521],
            **raw,
        },
        C4_ID,
    )


THICK = {"3/4 melamine": 0.75, "1/2 plywood": 0.5, "1/4 plywood": 0.25}


def _areas(members: list[ExpandedMember]) -> dict[str, float]:
    out: dict[str, float] = {}
    for _, prod, _, _, vol in placed(members):
        assert prod is not None
        out[prod] = out.get(prod, 0.0) + vol / THICK[prod]
    return out


def test_c4_vdb1521_by_hand() -> None:
    """casework.md C4: sides 2 x (21 x 34.5 - 3 x 4.5), back 13.5 x 30,
    bottom 13.5 x 20.25, stretchers 2 x 13.5 x 4, toe kick 13.5 x 4.5,
    fronts 14.875 x (6 + 2 x 11.8125); drawer boxes 12.5 wide on 20 in slides
    (inside depth 20.25), sides 4, 9.8125, 9.8125 high, each 2 x 20 + 2 x
    11.5 long, bottoms 12.5 x 20."""
    members = c4()
    vdb = [
        m for m in members if (m.name or "").startswith("box/1/") or m.role not in _BODY
    ]
    areas = _areas(vdb)
    assert areas["3/4 melamine"] == pytest.approx(
        1422 + 405 + 273.375 + 108 + 60.75 + 14.875 * 29.625, abs=1e-9
    )
    assert areas["3/4 melamine"] == pytest.approx(2709.796875, abs=1e-9)
    assert areas["1/2 plywood"] == pytest.approx(63 * 23.625, abs=1e-9)
    assert areas["1/4 plywood"] == pytest.approx(3 * 12.5 * 20, abs=1e-9)
    assert volume(vdb) == pytest.approx(2964.03515625, abs=1e-9)
    assert banding_in(vdb) == pytest.approx(60 + 13.5 + 13.5 + 41.75 + 106.75)
    assert hardware(vdb) == {"slide_20": 3}
    # The boxes: 12.5 wide in the 13.5 opening, 20 deep from Y 1 of the
    # carcass (X 183.25..203.25), their sides 4 and 9.8125 high.
    boxes_ = [p[3] for p in placed(vdb) if p[0] == "drawer_bottom"]
    assert {(b[0], b[1], round(b[3] - b[2], 9)) for b in boxes_} == {
        (183.25, 203.25, 12.5)
    }
    sides = sorted(
        round(p[3][5] - p[3][4], 9) for p in placed(vdb) if p[0] == "drawer_side"
    )
    assert sides == [4.0, 4.0, 9.8125, 9.8125, 9.8125, 9.8125]


def test_c4_stands_on_p1_s_gypsum_and_touches_nothing() -> None:
    members = c4()
    assert span(members) == (P1_BOARD, 204.0, 141.0, 186.0, SUBFLOOR, SUBFLOOR + 34.5)
    sides = sorted({(p[3][2], p[3][3]) for p in placed(members) if p[0] == "side"})
    assert sides == [(141.0, 141.75), (155.25, 156.0), (156.0, 156.75), (185.25, 186.0)]
    assert volume(members) == pytest.approx(6036.17578125, abs=1e-9)
    assert banding_in(members) == pytest.approx(578.75, abs=1e-9)
    assert round(banding_in(members) / 12, 2) == 48.23
    assert hardware(members) == {"hinge": 4, "slide_20": 3}
    assert {p[2] for p in placed(members)} == {"melamine", "plywood"}
    assert touching_nothing(members, b10())


def test_c4_v3021_to_v3621_moves_only_the_vdb_clear_of_p2() -> None:
    before, after = c4(), c4(36)
    assert span(after)[2] == 135.0
    assert span(after)[2] - P2_BOARD == 0.75
    vdb = [
        p[3]
        for m, p in zip(_bodies(after), placed(after), strict=True)
        if (m.name or "").startswith("box/1/")
    ]
    assert min(b[2] for b in vdb) == 135.0 and max(b[3] for b in vdb) == 150.0
    assert {m.id for m in after} == {m.id for m in before}
    assert volume(after) == pytest.approx(3488.390625 + 2964.03515625, abs=1e-9)
    assert touching_nothing(after, b10())


def _bodies(members: list[ExpandedMember]) -> list[ExpandedMember]:
    return [m for m in members if m.role in _BODY]


def test_a_run_past_p2_is_refused_naming_it() -> None:
    """V3621 + a 21 in VDB would end at Y 129: through P2 and its boards
    (Y 129.75..134.25)."""
    with pytest.raises(PluginError, match="would pass partition e6") as err:
        c4(
            36,
            boxes=[box("vanity", 36, shelves=0), box("vanity", 21, fronts="drawers")],
        )
    assert err.value.input == "offset_mm"


def test_p1_s_right_face_is_its_minus_x_side() -> None:
    members = c4(face="right")
    assert span(members)[:4] == (156.0, 177.75, 141.0, 186.0)


def test_a_partition_needs_its_line() -> None:
    with pytest.raises(PluginError, match="pick the partition"):
        c4(wall_segment=[])


# --- A B24 in every corner -----------------------------------------------------------

#: B10's faces a run may stand on: each wall's inside face and each
#: partition's two, from either end.
FACES: list[tuple[str, str, str | None]] = [
    *((seg, "wall", None) for seg in ("e1", "e2", "e3", "e4")),
    *((seg, "partition", face) for seg in ("e5", "e6") for face in ("left", "right")),
]
CORNERS = (
    ROOT
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "casework-b10-corners.json.gz"
)


def corner_runs(rows: Rows) -> list[tuple[str, list[ExpandedMember]]]:
    """A B24 at Distance 0 from each end of each face of B10: in its
    finished corner, so touching the boards (or framing) there."""
    out: list[tuple[str, list[ExpandedMember]]] = []
    for seg, kind, face in FACES:
        for end in ("start", "end"):
            name = f"{seg}/{face or 'inside'}/{end}"
            host = WALLS_ID if kind == "wall" else INTERIOR_ID
            raw: dict[str, Any] = {
                "wall": FeatureRef(kind="feature", feature_id=host),
                "wall_segment": [seg],
                "measure_from": end,
                "boxes": [box("base", 24)],
            }
            if face is not None:
                raw["face"] = face
            out.append((name, run(rows, raw, uuid.uuid5(RUN_ID, name))))
    return out


def corners() -> str:
    """Each house golden's corner runs as one request (geometry probes
    them exactly against the golden's solids)."""
    cases = [
        {
            "house": house,
            "runs": [name for name, _ in runs],
            "request": request_of([m for _, ms in runs for m in ms]).model_dump(
                mode="json"
            ),
        }
        for house, runs in (
            ("b10-partitions", corner_runs(b10())),
            ("b10-inside-gypsum", corner_runs(b10_gypsum())),
        )
    ]
    return json.dumps(cases, indent=1) + NEWLINE


NEWLINE = chr(10)


@pytest.mark.parametrize("gypsum", [False, True])
def test_a_b24_in_every_corner_touches_nothing(gypsum: bool) -> None:
    """At Distance 0 from either end of each wall's inside face and each
    partition's two faces, with the walls' gypsum and without: the run
    stands in the finished corner and meets no board, stud or block. The
    front and back walls run through: their boards pass under the side
    walls' to the framing, so their finished face stops 1/2 in short."""
    rows = b10_gypsum() if gypsum else b10()
    runs = corner_runs(rows)
    for name, members in runs:
        assert touching_nothing(members, rows), name
    ends = {name: span(ms) for name, ms in runs}
    g = 0.5 if gypsum else 0.0
    assert ends["e3/inside/start"][0] == 5.5 + g
    assert ends["e3/inside/end"][1] == 282.5 - g
    assert ends["e1/inside/start"][1] == 282.5 - g
    assert ends["e1/inside/end"][0] == 5.5 + g
    assert ends["e4/inside/end"][3] == 186.5 - g
    assert ends["e2/inside/start"][3] == 186.5 - g


def test_the_corner_fixture_is_the_plugin_s_expansion() -> None:
    assert gzip.decompress(CORNERS.read_bytes()).decode() == corners()


# --- The goldens ----------------------------------------------------------------------


def b10_gypsum_golden() -> tuple[Any, list[CutListMember]]:
    rows = b10_gypsum()
    names = titles()
    metadata: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        metadata += [
            CutListMember(
                feature_id=m.id,
                role=m.role,
                title=names[(str(plugin_id), m.role)],
                plugin_id=plugin_id,
                metadata=m.metadata,
            )
            for m in members
            if m.metadata is not None
        ]
    request = house_request_of(rows).model_copy(update={"part_id": HOUSE_PART_ID})
    return request, metadata


def golden_members() -> dict[str, list[ExpandedMember]]:
    runs = c2_b10()
    return {
        "c2-kitchen-b10-left-wall": runs["base"] + runs["wall"],
        "c4-vanity-b10-p1": c4(),
        "c4-v3621-b10-p1": c4(36),
    }


@pytest.mark.parametrize("name", sorted(golden_members()))
def test_the_goldens_are_the_plugin_s_expansion(name: str) -> None:
    members = golden_members()[name]
    folder = GOLDENS / name
    assert (folder / "model.json").read_text() == request_of(members).model_dump_json(
        indent=2
    ) + "\n"
    assert json.loads((folder / "members.json").read_text()) == json.loads(
        members_json(members)
    )


def test_the_house_golden_is_the_plugins_expansion() -> None:
    request, metadata = b10_gypsum_golden()
    folder = GOLDENS / "b10-inside-gypsum"
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == house_members_json(metadata)


if __name__ == "__main__":
    CORNERS.write_bytes(gzip.compress(corners().encode(), mtime=0))
    for name, members in golden_members().items():
        folder = GOLDENS / name
        folder.mkdir(exist_ok=True)
        (folder / "model.json").write_text(
            request_of(members).model_dump_json(indent=2) + "\n"
        )
        (folder / "members.json").write_text(members_json(members))
    request, metadata = b10_gypsum_golden()
    folder = GOLDENS / "b10-inside-gypsum"
    folder.mkdir(exist_ok=True)
    (folder / "model.json").write_text(request.model_dump_json(indent=2) + "\n")
    (folder / "members.json").write_text(house_members_json(metadata))
