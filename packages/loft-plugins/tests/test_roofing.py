"""ROOFING: ``loft.roof`` 1.9.0's Roofing on a gable (Chief Architect's roof
plane sheathing and roofing layers, its Materials List squares and drip
edge).

Checked against ``docs/reference-parts/buildings.md`` B7, typed by hand
(inches; X along the ridge, Y across from the front wall's framing face):

* the rafters' top plane is ``106.1770833 + y / 2 + 7.25 sqrt 1.25``
  (the plate 108.59375 less the heel 29/12, the 2x8's plumb depth 8.106);
* the fascia is a 1x10 (8.106 > a 1x8's 7.25) on the tails' plumb cut at
  Y -12, its outer face Y -12.75, its top on the top plane there (107.9079);
* each plane's deck runs 108.75 in plan (96 + 12 + 0.75), 121.5862 on the
  slope, by 288.875 (X -7/16 .. 288 7/16, flush with the gable OSB): two
  48 in courses and a 25.5862 rip; each course's sheets end on a rafter
  centre (X 24 k), the even courses at X 72, 168 and 264 and the odd ones
  4 ft over at 24, 120 and 216 (the PM's sheets from the rake, 96 in long,
  end at X 95.5625, 5/16 in onto the rafter at 96: no nail holds there);
* each eave's fascia is two pieces jointed on the middle rafter, X 144;
* four 1x6 rake boards on the gable OSB's face (X -1 3/16 .. -7/16 and
  288 7/16 .. 289 3/16), the top in the deck's top plane, plumb-cut at
  Y -12.75 and at the ridge line Y 96; each is cut out of the end wall's
  corner board under it and the gable's lap.

The geometry golden ``b7-roofing`` and the kernel fixture
``roofing-cases.json.gz`` are written from here and pinned by this module
(``services/geometry/tests/test_roofing_b7.py`` checks them exactly, and the
cut list's bundles, rolls, sheets and sticks). Regenerate after a deliberate
change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_roofing.py``.
"""

import gzip
import itertools
import json
import math
import sys
import uuid
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from loft_plugins import REGISTRY, canonical_inputs, update_for
from loft_plugins.api import ExpandInputs
from loft_plugins.builtin.roof_outline import roofing_note, roofing_notes
from loft_plugins.updates import update_effect, updated_inputs
from loft_wire.cut_list import ROLE_SYSTEMS, CutListMember
from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.plugins import ChoiceInput, CountInput
from loft_wire.sketch import SketchLine

sys.path.insert(0, str(Path(__file__).parent))
import test_building_outline as outline
import test_siding_trim as siding
from test_building_outline import (
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    ROOF_ID,
    WALLS_ID,
    house,
    members_json,
    members_of,
    rectangle,
    ref,
    request_of,
)
from test_ceiling_joists import B7_GABLE, Rows, roof_of, roofed
from test_interior_walls import titles

ROOF_1_8 = REGISTRY.get("loft.roof", "1.8.0")
ROOF_1_9 = REGISTRY.get("loft.roof", "1.9.0")
GOLDEN = "b7-roofing"
CASES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "roofing-cases.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000700f")
SHINGLES = {"roofing": "asphalt_shingles"}
ROOFED = {**B7_GABLE, **SHINGLES}
ROOFING = ("deck", "fascia", "rake_board")

# --- B7's roof, typed from buildings.md (inches) --------------------------------------

PLATE = 1.5 + 9.25 + 23 / 32 + 97.125  # 108.59375
HEEL = 7.25 / 3  # the heel held to a third of the 2x8's depth: seat 29/6
COS = 2 / math.sqrt(5)  # 6/12
SIN = 1 / math.sqrt(5)
PLUMB = 7.25 * math.sqrt(1.25)
S = 7 / 16  # the OSB, the deck's and the gable's


def top_plane(y: float) -> float:
    """The rafters' top plane over Y (the front plane)."""
    return PLATE - HEEL + y / 2 + PLUMB


EAVE = -12.75
SLOPE = 108.75 / COS  # 121.5862
COURSES = [(0.0, 48.0), (48.0, 96.0), (96.0, SLOPE)]
EVEN = [-S, 72.0, 168.0, 264.0, 288 + S]
ODD = [-S, 24.0, 120.0, 216.0, 288 + S]


def b7_roofed(roof: dict[str, Any] | None = None, **kw: Any) -> Rows:
    """B7 today, sided in Lap, its roof at 1.9.0 with *roof*'s inputs."""
    return siding.b7_today(roof=ROOFED if roof is None else roof, **kw)


def of_role(rows: Rows, role: str) -> list[ExpandedMember]:
    return [m for m in roof_of(rows) if m.role == role]


def section_points(rows: Rows, member: ExpandedMember) -> list[tuple[float, float]]:
    by_id = {m.id: m.feature for m in members_of(rows)}
    assert isinstance(member.feature, ExtrudeFeature)
    sketch = by_id[member.feature.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)
    return [
        (e.start.x / IN, e.start.y / IN)
        for e in sketch.params.entities
        if isinstance(e, SketchLine)
    ]


def flat(points: list[tuple[float, float]]) -> list[float]:
    return [v for p in points for v in p]


def x_span(rows: Rows, member: ExpandedMember) -> tuple[float, float]:
    """A body's X extent: its plane's offset, then its extrusion."""
    by_id = {m.id: m.feature for m in members_of(rows)}
    assert isinstance(member.feature, ExtrudeFeature)
    sketch = by_id[member.feature.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)
    plane = sketch.params.plane
    x0 = 0.0
    if plane.kind == "feature":
        datum = by_id[plane.feature_id]
        assert isinstance(datum, DatumFeature)
        assert isinstance(datum.params, DatumOffsetParams)
        x0 = datum.params.offset_mm / IN
    return (round(x0, 9), round(x0 + member.feature.params.distance_mm / IN, 9))


# --- 1. None is 1.8.0; the manifest -----------------------------------------------


def test_roofing_none_is_1_8_0_member_for_member() -> None:
    """The default builds what 1.8.0 builds: sided, bare, at 8/12, a hip."""
    for walls, roof in (
        (None, B7_GABLE),
        (siding.NONE, B7_GABLE),
        (None, {**B7_GABLE, "pitch": "rise_8"}),
    ):
        rows = b7_roofed(roof, walls=walls)
        old = roofed(rows[:-1], roof, ROOF_1_8)
        assert roof_of(rows) == roof_of(old)
    with mock.patch.object(outline, "ROOF", ROOF_1_9):
        rows = house(siding.l_sketch(), [], outline.OSB, None, {"style": "hip"})
    with mock.patch.object(outline, "ROOF", ROOF_1_8):
        old = house(siding.l_sketch(), [], outline.OSB, None, {"style": "hip"})
    assert roof_of(rows) == roof_of(old)


def test_1_9_0_offers_roofing_none_by_default() -> None:
    inputs = {i.name: i for i in ROOF_1_9.manifest.inputs}
    old = [i.name for i in ROOF_1_8.manifest.inputs]
    assert [n for n in inputs if n not in old] == ["roofing", "roofing_waste_percent"]
    choice = inputs["roofing"]
    assert isinstance(choice, ChoiceInput)
    assert choice.default == "none"
    assert [o.label for o in choice.options] == ["None", "Asphalt shingles"]
    waste = inputs["roofing_waste_percent"]
    assert isinstance(waste, CountInput)
    assert (waste.default, waste.minimum, waste.maximum) == (10, 0, 30)
    roles = {r.role: r.title for r in ROOF_1_9.manifest.members}
    assert (roles["deck"], roles["fascia"], roles["rake_board"]) == (
        "Roof deck",
        "Fascia",
        "Rake board",
    )
    assert ROLE_SYSTEMS[("loft.roof", "deck")] == "roof"


def test_a_hip_and_a_flush_eave_take_no_roofing() -> None:
    """Hips and valleys are a later rung; an eave with no tails has no
    fascia to hang: both build 1.8.0's roof."""
    for raw in ({**ROOFED, "overhang_mm": 0.0},):
        rows = b7_roofed(raw)
        assert not any(m.role in ROOFING for m in roof_of(rows))
    with mock.patch.object(outline, "ROOF", ROOF_1_9):
        rows = house(
            siding.l_sketch(), [], outline.OSB, None, {"style": "hip", **SHINGLES}
        )
    assert not any(m.role in ROOFING for m in roof_of(rows))


def _note(rows: Rows, raw: dict[str, Any]) -> str | None:
    """The stored roof's ``roof_roofing_no_overhang`` text, as documents
    reads it: its canonical inputs over the features before it."""
    earlier: dict[uuid.UUID, Any] = {}
    for fid, env, members in rows[:-1]:
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    full = canonical_inputs(ROOF_1_9.manifest, {"walls": [ref(WALLS_ID)], **raw})
    return roofing_note(ExpandInputs(ROOF_ID, full, earlier))


@pytest.mark.parametrize(
    ("raw", "warns"),
    [
        ({**ROOFED, "overhang_mm": 0.0}, True),
        (ROOFED, False),
        ({**B7_GABLE, "overhang_mm": 0.0}, False),  # Roofing None
        ({**ROOFED, "overhang_mm": 0.0, "roofing": "none"}, False),
    ],
)
def test_roofing_on_a_flush_eave_is_noted(raw: dict[str, Any], warns: bool) -> None:
    """``roof_roofing_no_overhang``: Roofing picked on a gable with no eave
    overhang is named, not dropped silently, as ``wall_finish_no_sheathing``
    names a finish with no sheathing; the roof still builds, unroofed."""
    rows = b7_roofed(raw)
    assert not warns or not any(m.role in ROOFING for m in roof_of(rows))
    note = _note(rows, raw)
    assert (note is not None) == warns
    if note is not None:
        assert note.startswith("Roofing is Asphalt shingles, but this gable has")
        assert "give the eaves an overhang, or set Roofing to None" in note
    full = canonical_inputs(ROOF_1_9.manifest, {"walls": [ref(WALLS_ID)], **raw})
    # Its walls unresolved it is no gable on its walls: no note.
    assert roofing_notes(ExpandInputs(ROOF_ID, full, {})) == []


# --- 2. B7's deck, fascia and rake boards -------------------------------------------


def test_b7_is_decked_in_24_panels_jointed_on_rafters() -> None:
    """Three courses a plane up from the fascia's face, each in 4 sheets
    ending on rafter centres, staggered 4 ft; each square to the plane, its
    underside on the rafters' top plane."""
    rows = b7_roofed()
    deck = of_role(rows, "deck")
    assert len(deck) == 24
    for side in ("front", "back"):
        for k, (s0, s1) in enumerate(COURSES):
            joints = EVEN if k % 2 == 0 else ODD
            got = [
                x_span(rows, m)
                for m in deck
                if m.name is not None and m.name.startswith(f"{side}/{k}/")
            ]
            assert got == [
                (round(a, 9), round(b, 9)) for a, b in itertools.pairwise(joints)
            ]
            # The front course's section, by hand: up the slope from the
            # fascia's face, square to it, 7/16 thick.
            if side == "front":
                y0, z0 = EAVE, top_plane(EAVE)
                want = [
                    (y0 + s * COS - n * SIN, z0 + s * SIN + n * COS)
                    for s, n in ((s0, 0.0), (s1, 0.0), (s1, S), (s0, S))
                ]
                points = section_points(rows, deck[k * 4])
                assert flat(points) == pytest.approx(flat(want), abs=1e-9)
    assert top_plane(0.0) - PLUMB == pytest.approx(106.1770833, abs=1e-7)
    assert pytest.approx(121.5862, abs=1e-4) == SLOPE
    assert pytest.approx(70246.42, abs=0.01) == 2 * SLOPE * 288.875


def test_the_deck_lists_shingles_underlayment_and_its_edges() -> None:
    """Every panel carries the 10 % allowance; the first of each plane its
    eave and two rakes, the front's the ridge too."""
    rows = b7_roofed()
    deck = of_role(rows, "deck")
    assert all(
        m.metadata is not None
        and m.metadata.roofing is not None
        and m.metadata.roofing.waste_percent == 10
        and m.metadata.profile == "7/16 OSB"
        and m.metadata.material == "osb"
        for m in deck
    )
    carried = {
        m.name: [(e.edge, round(e.length_in, 4)) for e in m.metadata.roofing.edges]
        for m in deck
        if m.metadata is not None
        and m.metadata.roofing is not None
        and m.metadata.roofing.edges
    }
    run, rake = 288.875, round(SLOPE, 4)
    assert carried == {
        "front/0/0": [("eave", run), ("rake", rake), ("rake", rake), ("ridge", run)],
        "back/0/0": [("eave", run), ("rake", rake), ("rake", rake)],
    }
    waste = b7_roofed({**ROOFED, "roofing_waste_percent": 15})
    assert {
        m.metadata.roofing.waste_percent
        for m in of_role(waste, "deck")
        if m.metadata is not None and m.metadata.roofing is not None
    } == {15}


def test_the_fascia_is_a_1x10_jointed_on_the_middle_rafter() -> None:
    rows = b7_roofed()
    fascia = of_role(rows, "fascia")
    assert [m.name for m in fascia] == ["front/0", "front/1", "back/0", "back/1"]
    assert {
        (m.metadata.profile, m.metadata.material)
        for m in fascia
        if m.metadata is not None
    } == {("1x10", "fibre_cement")}
    assert [x_span(rows, m) for m in fascia[:2]] == [(-S, 144.0), (144.0, 288 + S)]
    z = top_plane(EAVE)
    assert z == pytest.approx(107.9079, abs=1e-4)
    assert flat(section_points(rows, fascia[0])) == pytest.approx(
        flat([(EAVE, z - 9.25), (-12.0, z - 9.25), (-12.0, z), (EAVE, z)]), abs=1e-9
    )
    # Unsided, the trim is SPF.
    bare = b7_roofed(walls=siding.NONE)
    assert {
        m.metadata.material for m in of_role(bare, "fascia") if m.metadata is not None
    } == {"spf_lumber"}


def test_four_rake_boards_cut_into_the_corner_boards_and_gable_lap() -> None:
    rows = b7_roofed()
    rakes = of_role(rows, "rake_board")
    assert [m.name for m in rakes] == [
        "start/front",
        "start/back",
        "end/front",
        "end/back",
    ]
    assert [x_span(rows, m) for m in rakes] == [
        (-S - 0.75, -S),
        (-S - 0.75, -S),
        (288 + S, 288 + S + 0.75),
        (288 + S, 288 + S + 0.75),
    ]
    deck_top = [
        (y, top_plane(y) + S / COS) for y in (EAVE, 96.0)
    ]  # the deck's top plane
    drop = 5.5 / COS
    assert flat(section_points(rows, rakes[0])) == pytest.approx(
        flat(
            [
                (EAVE, deck_top[0][1] - drop),
                (96.0, deck_top[1][1] - drop),
                (96.0, deck_top[1][1]),
                (EAVE, deck_top[0][1]),
            ]
        ),
        abs=1e-9,
    )
    cuts = [m for m in roof_of(rows) if m.role == "cutter" and "rake" in (m.name or "")]
    assert [m.name for m in cuts] == [
        "rake/start/front",
        "rake/start/back",
        "rake/end/front",
        "rake/end/back",
    ]
    walls = siding.walls_of(rows)
    by_id = {m.id: m for m in [*walls, *roof_of(rows)]}
    for cut in cuts:
        assert isinstance(cut.feature, ExtrudeFeature)
        assert cut.feature.params.operation == "cut"
        hit = cut.feature.params.cut_bodies
        assert isinstance(hit, list)
        assert sorted(by_id[r.feature_id].role for r in hit) == [
            "corner_board",
            "gable_siding",
        ]
    # Unsided, there is nothing to cut.
    bare = b7_roofed(walls=siding.NONE)
    assert not any(
        m.role == "cutter" and "rake" in (m.name or "") for m in roof_of(bare)
    )


# --- 3. The update and the badge -----------------------------------------------------


def test_the_update_adds_nothing_and_picking_roofing_names_it() -> None:
    """Roofing is a material the user picks, as siding is (VISION
    2026-10-30): every roof updates to 1.9.0 quietly; picking Asphalt
    shingles is the user's edit, and its nouns are the badge's."""
    for version in ("1.4.0", "1.5.0", "1.6.0", "1.7.0", "1.8.0"):
        update = update_for("loft.roof", version, REGISTRY)
        assert update is not None and update.to_version == "1.9.0", version
        assert "Roofing, None until you pick Asphalt shingles" in update.summary
        moved = canonical_inputs(
            ROOF_1_9.manifest, updated_inputs(update, {"style": "gable"})
        )
        assert moved["roofing"] == "none"
    rows = b7_roofed(B7_GABLE)
    stored = roof_of(roofed(rows[:-1], B7_GABLE, ROOF_1_8))
    effect = update_effect([("loft.roof", stored, roof_of(rows))], REGISTRY)
    assert (effect.adds, effect.relays, effect.changes) == ((), (), False)
    after = roof_of(b7_roofed())
    effect = update_effect([("loft.roof", roof_of(rows), after)], REGISTRY)
    assert effect.adds == ("24 roof deck panels", "4 fascia boards", "4 rake boards")
    assert effect.relays == ()


# --- The golden and the kernel's cases ------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    names = {
        **titles(),
        **{
            (p.manifest.id, r.role): r.title
            for p in (
                REGISTRY.latest("loft.floor"),
                siding.WALL_1_5,
                ROOF_1_9,
                REGISTRY.latest("loft.door"),
                REGISTRY.latest("loft.window"),
            )
            for r in p.manifest.members
        },
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
    """B7 drawn today, sided in Lap and roofed in asphalt shingles."""
    rows = b7_roofed()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def _counts(rows: Rows) -> dict[str, int]:
    found = Counter(m.role for m in members_of(rows))
    cuts = sum(
        1 for m in members_of(rows) if m.role == "cutter" and "rake" in (m.name or "")
    )
    return {**{r: found[r] for r in ROOFING}, "rake_cut": cuts}


def built_cases() -> Iterator[tuple[str, Rows]]:
    moved = rectangle(192, 288).model_dump(mode="json")
    for e in moved["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    yield "b7-8-12", b7_roofed({**ROOFED, "pitch": "rise_8"})
    yield "b7-336", siding.b7_today(336, roof=ROOFED)
    yield "b7-vinyl", b7_roofed(walls=siding.VINYL)
    yield "b7-unsided", b7_roofed(walls=siding.NONE)
    yield "b7-unsheathed", b7_roofed(walls={"sheathing": "none"})
    yield "b7-no-gable-ends", b7_roofed({**ROOFED, "gable_ends": "none"})
    with (
        mock.patch.object(outline, "WALL", siding.LAPPED),
        mock.patch.object(outline, "ROOF", ROOF_1_9),
    ):
        yield (
            "along-y-moved",
            house(
                SketchFeature.model_validate(moved),
                [],
                B7_STUDS,
                {},
                {"slope_walls": ["e2", "e4"], **B7_ROOF, **SHINGLES},
            ),
        )


def cases() -> str:
    """B7 at 8/12, at 28 ft, in vinyl, unsided, unsheathed and with no gable
    ends, and a lapped house turned off the origin (its ridge along Y);
    each with its counts."""
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            **_counts(rows),
            "request": request_of(rows).model_dump(mode="json"),
        }
        for name, rows in built_cases()
    ]
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_is_b7_sided_and_roofed() -> None:
    """b7-siding's 329 bodies, then 24 deck panels, 4 fascia boards and 4
    rake boards: 361."""
    _, metadata = golden()
    assert len(metadata) == 329 + 24 + 4 + 4 == 361
    count = Counter(m.title for m in metadata)
    assert (count["Roof deck"], count["Fascia"], count["Rake board"]) == (24, 4, 4)


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
