"""``loft.deck`` 1.0.0: the B1 deck from one custom feature (DECK).

Layouts are checked against ``docs/reference-parts/buildings.md`` B1 and its
20 ft edit, typed from the spec by hand. The geometry goldens
``plugin-deck-v1-b1-12x16ft`` and ``plugin-deck-v1-b1-20ft`` are this
plugin's expansion (``model.json``, with the member materials documents sends)
and their members' metadata (``members.json``); the first test asserts the
files are exactly that, so the geometry acceptance
(``services/geometry/tests/test_deck_b1.py``) reads files that cannot drift.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_deck.py``.
"""

import itertools
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.builtin.deck import (
    baluster_count,
    board_count,
    equal_centres,
    joist_centres,
)
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
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

IN = 25.4
DECK = REGISTRY.get("loft.deck", "1.0.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-00000000dec1")

#: golden name -> raw inputs (inches x 25.4: what the form sends).
GOLDEN_INPUTS: dict[str, dict[str, Any]] = {
    "plugin-deck-v1-b1-12x16ft": {"width_mm": 192 * IN, "depth_mm": 144 * IN},
    "plugin-deck-v1-b1-20ft": {"width_mm": 240 * IN, "depth_mm": 144 * IN},
}


def members(raw: dict[str, Any] | None = None) -> list[ExpandedMember]:
    inputs = canonical_inputs(DECK.manifest, raw or {})
    return expand(DECK, DECK_ID, inputs, {})


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request (member materials applied, as documents
    sends them) and its members' cut-list metadata."""
    expansion = members(GOLDEN_INPUTS[name])
    titles = {role.role: role.title for role in DECK.manifest.members}
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


def boxes(expansion: list[ExpandedMember]) -> dict[tuple[str, int], tuple[float, ...]]:
    """Each body's box, in inches: x0, x1, y0, y1, z0, z1, from its section
    sketch, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: dict[tuple[str, int], tuple[float, ...]] = {}
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
        xs = [p for e in lines for p in (e.start.x, e.end.x)]
        ys = [p for e in lines for p in (e.start.y, e.end.y)]
        z1 = z0 + m.feature.params.distance_mm
        out[(m.role, m.index)] = tuple(
            round(v / IN, 9) for v in (min(xs), max(xs), min(ys), max(ys), z0, z1)
        )
    return out


def _volume(box: tuple[float, ...]) -> float:
    x0, x1, y0, y1, z0, z1 = box
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


# --- Goldens -----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- B1, coordinate by coordinate --------------------------------------------------


def test_b1_is_the_default_deck() -> None:
    assert members() == members(GOLDEN_INPUTS["plugin-deck-v1-b1-12x16ft"])


def test_b1_members_are_the_specs() -> None:
    """buildings.md B1, every bound typed from the spec."""
    got = boxes(members())
    roles = Counter(role for role, _ in got)
    assert roles == {
        "ledger": 1,
        "rim": 1,
        "beam": 2,
        "joist": 13,
        "post": 3,
        "deck": 26,
    }
    assert got[("ledger", 0)] == (0, 192, 0, 1.5, 19.75, 29)
    assert got[("rim", 0)] == (0, 192, 142.5, 144, 19.75, 29)
    assert got[("beam", 0)] == (0, 192, 124.5, 126, 10.5, 19.75)
    assert got[("beam", 1)] == (0, 192, 126, 127.5, 10.5, 19.75)
    joist_x = [0.75, *range(16, 177, 16), 191.25]
    for i, x in enumerate(joist_x):
        assert got[("joist", i)] == (x - 0.75, x + 0.75, 1.5, 142.5, 19.75, 29)
    for i, x in enumerate([2.75, 96, 189.25]):
        assert got[("post", i)] == (x - 2.75, x + 2.75, 123.25, 128.75, 0, 10.5)
    for i in range(26):
        assert got[("deck", i)] == (0, 192, 5.625 * i, 5.625 * i + 5.5, 29, 30)
    assert got[("deck", 25)][3] - 144 == 2.125  # the last board's overhang
    assert sum(_volume(b) for b in got.values()) == pytest.approx(64497.75, abs=1e-6)


def test_the_20ft_edit_is_the_specs() -> None:
    got = boxes(members(GOLDEN_INPUTS["plugin-deck-v1-b1-20ft"]))
    for key in [("ledger", 0), ("rim", 0), ("beam", 0), ("beam", 1)]:
        assert got[key][:2] == (0, 240)
    assert all(got[("deck", i)][:2] == (0, 240) for i in range(26))
    joist_x = [0.75, *range(16, 225, 16), 239.25]
    assert [got[("joist", i)][0] + 0.75 for i in range(16)] == joist_x
    assert ("joist", 16) not in got
    posts = [got[("post", i)][0] + 2.75 for i in range(4)]
    assert posts == pytest.approx([2.75 + 234.5 * n / 3 for n in range(4)], abs=1e-9)
    assert posts[-1] == 237.25 and ("post", 4) not in got
    assert sum(_volume(b) for b in got.values()) == pytest.approx(80212.5, abs=1e-6)


def test_metadata_is_plain_library_names() -> None:
    """Profiles are the library's nominal names, materials library keys, and
    every body carries both (the cut list and mass read them)."""
    expansion = members()
    bodies = [m for m in expansion if isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is not None for m in bodies)
    profiles = {m.role: m.metadata.profile for m in bodies if m.metadata}
    assert profiles == {
        "ledger": "2x10",
        "rim": "2x10",
        "beam": "2x10",
        "joist": "2x10",
        "post": "6x6",
        "deck": "5/4x6",
    }
    assert {m.metadata.material for m in bodies if m.metadata} == {"southern_pine_pt"}
    helpers = [m for m in expansion if not isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is None for m in helpers)


def test_roles_emit_in_the_cut_list_tables_order() -> None:
    order = [m.role for m in members() if isinstance(m.feature, ExtrudeFeature)]
    first = list(dict.fromkeys(order))
    assert first == ["ledger", "rim", "beam", "joist", "post", "deck"]


# --- Determinism and stable ids ----------------------------------------------------


def test_the_expansion_is_deterministic() -> None:
    a = [m.model_dump(mode="json") for m in members()]
    b = [m.model_dump(mode="json") for m in members()]
    assert a == b


def test_member_ids_survive_the_width_edit() -> None:
    """``<feature-id>/<role>/<n>``: the ledger, the beam plies and joist 3 keep
    their ids from 16 to 20 ft; the new joists and post are new ids."""
    before = {(m.role, m.index): m.id for m in members()}
    after = {
        (m.role, m.index): m.id
        for m in members(GOLDEN_INPUTS["plugin-deck-v1-b1-20ft"])
    }
    for key in [("ledger", 0), ("beam", 1), ("joist", 3), ("deck", 25)]:
        assert before[key] == after[key]
    assert set(after) - set(before) >= {("joist", 13), ("joist", 15), ("post", 3)}


# --- Layout rules ------------------------------------------------------------------


def test_layout_helpers() -> None:
    assert joist_centres(192, 16, 1.5) == [0.75, *range(16, 177, 16), 191.25]
    # A layout joist that would overlap the end joist is dropped ...
    assert joist_centres(193, 16, 1.5)[-2:] == [176, 192.25]
    # ... one that only touches it stays (a doubled end).
    assert joist_centres(194.25, 16, 1.5)[-2:] == [192, 193.5]
    assert equal_centres(192, 5.5, 96) == [2.75, 96, 189.25]
    assert board_count(144, 0, 5.5, 0.125) == 26
    assert board_count(140.5, 0, 5.5, 0.125) == 25  # exactly reaches: 25 boards
    assert baluster_count(4.0) == 0
    assert baluster_count(4.1) == 1


def test_joist_spacing_drives_the_count() -> None:
    got = Counter(m.role for m in members({"joist_spacing_mm": 12 * IN}))
    assert got["joist"] == 17  # 0.75, 12, ..., 180, 191.25


def test_a_flush_beam_cuts_the_joists() -> None:
    expansion = members({"beam_position": "flush"})
    got = boxes(expansion)
    # Beam top flush with the joists; posts down to its underside.
    assert got[("beam", 0)][4:] == (19.75, 29)
    assert got[("post", 0)][5] == 19.75
    # Each joist line: 1.5..124.5 and 127.5..142.5.
    assert got[("joist", 0)][2:4] == (1.5, 124.5)
    assert got[("joist", 1)][2:4] == (127.5, 142.5)
    assert Counter(role for role, _ in got)["joist"] == 26


def test_freestanding_has_two_beams_and_a_house_side_rim() -> None:
    got = boxes(members({"attachment": "freestanding"}))
    assert ("ledger", 0) not in got
    assert got[("rim", 1)] == (0, 192, 0, 1.5, 19.75, 29)
    beam_y = sorted({got[("beam", i)][2] for i in range(4)})
    assert beam_y == [16.5, 18, 124.5, 126]
    assert Counter(role for role, _ in got)["post"] == 6


def test_joists_along_the_house_turn_the_framing() -> None:
    got = boxes(members({"attachment": "freestanding", "joist_direction": "along"}))
    # Joists run along X (0..192 between the rims at X 0..1.5, 190.5..192).
    assert got[("joist", 0)][:4] == (1.5, 190.5, 0, 1.5)
    assert got[("rim", 0)][:2] == (190.5, 192)
    # Boards run along Y, laid from X 0.
    assert got[("deck", 0)][:4] == (0, 5.5, 0, 144)


def test_no_rim_joists_run_to_the_edge() -> None:
    got = boxes(members({"rim_joists": "no"}))
    assert ("rim", 0) not in got
    assert got[("joist", 0)][2:4] == (1.5, 144)


def test_decking_overhang_extends_the_boards() -> None:
    got = boxes(members({"decking_overhang_mm": 1.5 * IN}))
    assert got[("deck", 0)][:2] == (-1.5, 193.5)
    assert Counter(role for role, _ in got)["deck"] == 26  # 146.125 >= 145.5


def test_blocking_sits_at_mid_span_between_the_joists() -> None:
    got = boxes(members({"blocking": "midspan"}))
    blocks = [v for (role, _), v in got.items() if role == "blocking"]
    assert len(blocks) == 12
    mid = (1.5 + 126) / 2  # ledger face to beam centre
    assert {(b[2], b[3]) for b in blocks} == {(mid - 0.75, mid + 0.75)}
    assert blocks[0][:2] == (1.5, 15.25)
    assert blocks[-1][:2] == (176.75, 190.5)


def test_material_inputs_reach_the_members() -> None:
    expansion = members({"post_material": "concrete", "decking_material": None})
    by_role = {m.role: m.metadata for m in expansion if m.metadata}
    assert by_role["post"].material == "concrete"
    assert by_role["joist"].material == "southern_pine_pt"


def test_the_guard_follows_buildings_md_rules() -> None:
    """Posts at every corner, <= 6 ft apart; rails top at 36 in above the
    decking; balusters with no clear gap over 4 in (checked by rules, as
    buildings.md asks, not by coordinates)."""
    got = boxes(members({"guard": "open_sides"}))
    posts = [v for (r, _), v in got.items() if r == "guard_post"]
    rails = [v for (r, _), v in got.items() if r == "rail"]
    balusters = [v for (r, _), v in got.items() if r == "baluster"]
    corners = {(0, 3.5, 140.5, 144), (188.5, 192, 140.5, 144)}
    assert corners <= {p[:4] for p in posts}
    assert all(p[4] == 30 and p[5] == 66 for p in posts)
    assert max(r[5] for r in rails) == 66
    assert min(r[4] for r in rails) - 30 < 4
    # Along each open side (left, front, right), from corner to corner,
    # consecutive posts are no more than 72 apart on centres.
    for fixed, value, axis, length in (
        (0, 0, 2, 144),
        (2, 140.5, 0, 192),
        (0, 188.5, 2, 144),
    ):
        s = sorted(p[axis] for p in posts if p[fixed] == value)
        assert s[0] == 0 and s[-1] == length - 3.5
        assert max(b - a for a, b in itertools.pairwise(s)) <= 72
    assert len(posts) == 8
    # Clear gaps between the members along every rail bay <= 4 in.
    for rail in rails:
        along = 0 if rail[1] - rail[0] > rail[3] - rail[2] else 2
        lo, hi = rail[along], rail[along + 1]
        inside = sorted(
            b[along]
            for b in balusters
            if b[along] >= lo
            and b[along + 1] <= hi
            and b[2 - along] >= rail[2 - along]
            and b[3 - along] <= rail[3 - along]
        )
        edges = [lo, *[e for s in inside for e in (s, s + 1.5)], hi]
        gaps = [edges[i + 1] - edges[i] for i in range(0, len(edges), 2)]
        assert max(gaps) <= 4 + 1e-9


def test_nothing_overlaps() -> None:
    """No two bodies interpenetrate, guard and blocking included (exact box
    test; the geometry acceptance repeats it on the kernel's bodies)."""
    for raw in [
        {},
        {"guard": "open_sides", "blocking": "midspan"},
        {"beam_position": "flush", "attachment": "freestanding"},
        {"attachment": "freestanding", "joist_direction": "along"},
        # A non-round metric deck (DECK review): a corner post's two sides
        # must agree on its centre to the bit, or it is emitted twice.
        {"width_mm": 4900, "depth_mm": 1300, "guard": "open_sides"},
        {
            "width_mm": 4900,
            "depth_mm": 1300,
            "guard": "open_sides",
            "attachment": "freestanding",
        },
    ]:
        items = list(boxes(members(raw)).items())
        for i, (ka, a) in enumerate(items):
            for kb, b in items[i + 1 :]:
                overlap = all(
                    min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-9 for k in (0, 2, 4)
                )
                assert not overlap, (raw, ka, kb)


def test_metric_sizes_never_double_a_guard_post() -> None:
    """Whole decimetre sizes from 1.3 to 4.9 m (the review's sweep found 72
    of 864 doubled a corner post): every guard post stands alone."""
    for width in range(1300, 4901, 100):
        for depth in range(1300, 4901, 400):
            got = boxes(
                members({"width_mm": width, "depth_mm": depth, "guard": "open_sides"})
            )
            posts = [v for (r, _), v in got.items() if r == "guard_post"]
            assert len({(round(p[0], 6), round(p[2], 6)) for p in posts}) == len(
                posts
            ), (width, depth)


# --- Refusals and caps -------------------------------------------------------------


def _refusal(raw: dict[str, Any]) -> PluginError:
    with pytest.raises(PluginError) as caught:
        members(raw)
    return caught.value


def test_a_ledger_cannot_carry_joists_along_the_house() -> None:
    error = _refusal({"joist_direction": "along"})
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "joist_direction"


def test_a_beam_must_clear_grade() -> None:
    error = _refusal({"height_mm": 18 * IN})
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "height_mm"


def test_a_flush_beam_must_sit_between_the_ledger_and_rim() -> None:
    error = _refusal({"beam_position": "flush", "beam_setback_mm": 1 * IN})
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "beam_setback_mm"


def test_two_beams_may_not_overlap() -> None:
    error = _refusal(
        {"attachment": "freestanding", "depth_mm": 48 * IN, "beam_setback_mm": 24 * IN}
    )
    assert error.input == "beam_setback_mm"


def test_a_large_deck_fits_the_tree_bound() -> None:
    """A 40 x 24 ft freestanding deck at 12 in o.c. with blocking and a guard
    expands inside the part's tree bound, and since the bound is 1500
    (SECOND-FLOOR) so does the extreme corner of the inputs' bounds (8 in
    o.c., 2x4 decking: 1 111 features); over it documents refuses the write
    with ``feature_limit_exceeded`` (RESEARCH §23 caps), never a partial deck."""
    large = {
        "width_mm": 480 * IN,
        "depth_mm": 288 * IN,
        "joist_spacing_mm": 12 * IN,
        "blocking": "midspan",
        "guard": "open_sides",
        "attachment": "freestanding",
    }
    assert len(members(large)) <= MAX_TREE_FEATURES
    extreme = {
        **large,
        "joist_spacing_mm": 8 * IN,
        "decking_profile": "us_2x4",
        "decking_gap_mm": 0.0,
    }
    assert len(members(extreme)) == 1111 <= MAX_TREE_FEATURES


if __name__ == "__main__":
    for name in sorted(GOLDEN_INPUTS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
