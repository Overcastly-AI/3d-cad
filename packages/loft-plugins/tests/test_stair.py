"""``loft.stair`` 1.0.0 (STAIRS): B1's stair and the free interior check.

buildings.md B1 "Stair": centred on the rim at X 96, 36 in wide, from the
decking top (Z 30) to grade: 4 risers of 7.5 (ceil(30 / 7.75)), 3 treads of
11 in (33 in of run), 3 cut 2x12 stringers at X 78..79.5, 95.25..96.75 and
112.5..114 (17.25 o.c.), a throat of 11.25 - 7.5 x 11 / sqrt(7.5^2 + 11^2) =
5.0533 in, 6 tread boards 5/4x6 x 36 and a handrail. The decking at 36 in
gives 5 risers of 7.2, 4 treads (44 in) and a 5.2258 in throat; a free stair
of 107.09375 in gives 14 risers of 7.649554 and 13 treads.

Every number below is typed from the spec and the IRC by hand, never read
back from the plugin. The geometry goldens ``b1-stair-*`` and
``free-stair-107`` are the deck's and the stair's expansions (``model.json``
with the member materials documents sends, ``members.json`` each member's
metadata); the first test pins them, so
``services/geometry/tests/test_stair_b1.py`` reads files that cannot drift.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_stair.py``.
"""

import json
import math
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.api import ExpandInputs
from loft_plugins.builtin.stair import layout, stair_notes, stringer_profile
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
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

IN = 25.4
STAIR = REGISTRY.get("loft.stair", "1.0.0")
DECK = REGISTRY.get("loft.deck", "1.2.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-00000000dec1")
STAIR_ID = uuid.UUID("00000000-0000-0000-0000-0000000057a1")
DECK_REF = FeatureRef(kind="feature", feature_id=DECK_ID)

#: golden name -> (the deck's raw inputs or None for no deck, the stair's).
GOLDEN_INPUTS: dict[str, tuple[dict[str, Any] | None, dict[str, Any]]] = {
    "b1-stair-30": ({}, {"deck": DECK_REF}),
    "b1-stair-30-closed": ({}, {"deck": DECK_REF, "risers": "closed"}),
    "b1-stair-36": ({"height_mm": 36 * IN}, {"deck": DECK_REF}),
    "free-stair-107": (
        None,
        {"rise_mm": 107.09375 * IN, "risers": "closed"},
    ),
}


def deck_envelope(raw: dict[str, Any]) -> CustomFeature:
    m = DECK.manifest
    return CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": m.id,
                "plugin_version": m.version,
                "inputs": canonical_inputs(m, raw),
            },
        }
    )


def earlier(deck: dict[str, Any] | None = None) -> dict[uuid.UUID, AuthoredEnvelope]:
    return {DECK_ID: deck_envelope(deck or {})}


def stair(
    raw: dict[str, Any], deck: dict[str, Any] | None = None
) -> list[ExpandedMember]:
    inputs = canonical_inputs(STAIR.manifest, raw)
    return expand(STAIR, STAIR_ID, inputs, earlier(deck))


def lay(raw: dict[str, Any], deck: dict[str, Any] | None = None) -> Any:
    inputs = canonical_inputs(STAIR.manifest, raw)
    return layout(ExpandInputs(STAIR_ID, {"deck": None, **inputs}, earlier(deck)))


def notes(raw: dict[str, Any], deck: dict[str, Any] | None = None) -> list[str]:
    inputs = canonical_inputs(STAIR.manifest, raw)
    found = stair_notes(ExpandInputs(STAIR_ID, {"deck": None, **inputs}, earlier(deck)))
    return [code for code, _ in found]


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's request (the deck's members, then the stair's, with their
    materials) and every member's cut-list metadata."""
    deck_raw, stair_raw = GOLDEN_INPUTS[name]
    plugins: list[tuple[Any, list[ExpandedMember]]] = []
    if deck_raw is not None:
        deck_inputs = canonical_inputs(DECK.manifest, deck_raw)
        plugins.append((DECK, expand(DECK, DECK_ID, deck_inputs, {})))
    plugins.append((STAIR, stair(stair_raw, deck_raw)))
    every = [m for _, expansion in plugins for m in expansion]
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in every],
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in every if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )
    metadata: list[CutListMember] = []
    for plugin, expansion in plugins:
        titles = {role.role: role.title for role in plugin.manifest.members}
        metadata += [
            CutListMember(
                feature_id=m.id,
                role=m.role,
                title=titles[m.role],
                plugin_id=plugin.manifest.id,
                metadata=m.metadata,
            )
            for m in expansion
            if m.metadata is not None
        ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- The spec's numbers, by hand ---------------------------------------------------


def throat(riser: float, tread: float, depth: float = 11.25) -> float:
    return depth - riser * tread / math.hypot(riser, tread)


def test_b1_four_risers_three_treads_and_its_throat() -> None:
    got = lay({"deck": DECK_REF})
    assert (got.risers, got.treads) == (4, 3)
    assert got.riser == 7.5 and got.tread == 11.0 and got.run == 33.0
    assert got.throat == pytest.approx(11.25 - 82.5 / math.sqrt(177.25), abs=1e-12)
    assert round(got.throat, 4) == 5.0533
    assert got.throat == pytest.approx(throat(7.5, 11), abs=1e-12)


def test_decking_at_36_gives_five_risers_of_7_2() -> None:
    got = lay({"deck": DECK_REF}, {"height_mm": 36 * IN})
    assert (got.risers, got.treads, got.run) == (5, 4, 44.0)
    assert got.riser == pytest.approx(7.2, abs=1e-12)
    # 11.25 - 79.2 / sqrt(172.84) = 5.225749: the spec's 5.2258 mis-rounded.
    assert round(got.throat, 4) == 5.2257
    assert got.throat == pytest.approx(throat(7.2, 11), abs=1e-12)


def test_a_free_107_stair_gives_14_risers() -> None:
    got = lay({"rise_mm": 107.09375 * IN, "risers": "closed"})
    assert (got.risers, got.treads) == (14, 13)
    assert math.ceil(107.09375 / 7.75) == 14
    assert round(got.riser, 6) == 7.649554
    assert got.riser == pytest.approx(107.09375 / 14, abs=1e-12)
    # The spec gives no throat here; by the same formula it is under DCA6's 5.
    assert round(got.throat, 4) == 4.9697


def _boxes(expansion: list[ExpandedMember], role: str) -> list[tuple[float, ...]]:
    """Each *role* box as (x0, x1, y0, y1, z0, z1) in inches, read from its
    rectangle, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: list[tuple[float, ...]] = []
    for m in expansion:
        if m.role != role:
            continue
        assert isinstance(m.feature, ExtrudeFeature)
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
        xs = [p.x for e in lines for p in (e.start, e.end)]
        ys = [p.y for e in lines for p in (e.start, e.end)]
        z1 = z0 + m.feature.params.distance_mm
        out.append(
            tuple(
                round(v / IN, 9) for v in (min(xs), max(xs), min(ys), max(ys), z0, z1)
            )
        )
    return out


def _sides(expansion: list[ExpandedMember], role: str) -> list[tuple[str, float]]:
    """Each side-profiled *role* member as (its plane's base, its offset in)."""
    by_id = {m.id: m for m in expansion}
    out: list[tuple[str, float]] = []
    for m in expansion:
        if m.role != role:
            continue
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            out.append((plane.plane, 0.0))
        else:
            datum = by_id[plane.feature_id].feature
            assert isinstance(datum, DatumFeature)
            assert isinstance(datum.params, DatumOffsetParams)
            out.append((datum.params.base, round(datum.params.offset_mm / IN, 9)))
    return out


def test_b1_stringers_hang_at_x_78_95_25_and_112_5() -> None:
    expansion = stair({"deck": DECK_REF})
    assert _sides(expansion, "stringer") == [("YZ", 78), ("YZ", 95.25), ("YZ", 112.5)]
    names = [m.name for m in expansion if m.role == "stringer"]
    assert names == ["left", "inner/1", "right"]
    # 17.25 o.c.: (114 - 1.5) / 2 between the outer centres 78.75 and 113.25.
    assert (113.25 - 78.75) / 2 == 17.25


def test_b1_stringer_profile_is_typed_from_the_rim() -> None:
    """The deck's last board ends at Y 146.125 (25 x 5.625 + 5.5), 2.125 past
    the rim's face at Y 144: the top nosing. Tread boards are 2 x 5.5 + 1/8 =
    11.125 deep, so each tread's riser line is 0.125 behind its nosing's
    tread above (u = -0.125 for the top). Treads seat at 7.5 j - 1; the
    stringer's head is level under the decking (Z 29) and plumb on the rim;
    its foot is level on grade; its bottom edge is 11.25 x sqrt(177.25) / 11
    below the line through the tooth points."""
    got = lay({"deck": DECK_REF})
    drop = 11.25 * math.sqrt(177.25) / 11
    slope = 7.5 / 11
    top = 29.0  # the top line through (-0.125, 29), (10.875, 21.5), ...
    foot = -0.125 + (top - drop) / slope
    want = [
        (-2.125, 29.0),
        (-0.125, 29.0),
        (-0.125, 21.5),
        (10.875, 21.5),
        (10.875, 14.0),
        (21.875, 14.0),
        (21.875, 6.5),
        (32.875, 6.5),
        (32.875, 0.0),
        (foot, 0.0),
        (-2.125, top + 2 * slope - drop),
    ]
    assert _flat(stringer_profile(got)) == pytest.approx(_flat(want), abs=1e-9)


def _flat(points: list[tuple[float, ...]]) -> list[float]:
    return [v for p in points for v in p]


def _noses(boxes: list[tuple[float, ...]]) -> list[float]:
    """Each tread's front edge (Y): its boards share a top."""
    fronts: dict[float, float] = {}
    for box in boxes:
        fronts[box[5]] = max(fronts.get(box[5], box[3]), box[3])
    return sorted(fronts.values())


def test_b1_treads_are_six_boards_of_36() -> None:
    boxes = _boxes(stair({"deck": DECK_REF}), "tread")
    nose = 146.125
    want = [
        (
            78.0,
            114.0,
            nose - 0.125 + (3 - j) * 11 + b * 5.625,
            None,
            7.5 * j - 1,
            7.5 * j,
        )
        for j in (1, 2, 3)
        for b in (0, 1)
    ]
    assert len(boxes) == 6
    for got, (x0, x1, y0, _, z0, z1) in zip(boxes, want, strict=True):
        assert got == pytest.approx((x0, x1, y0, y0 + 5.5, z0, z1), abs=1e-9)
        assert got[1] - got[0] == 36
    # Nosing to nosing 11 in, the deck's edge to the top tread included.
    assert _noses(boxes) == pytest.approx([157.125, 168.125, 179.125], abs=1e-9)


def test_closed_risers_are_ripped_1x8s_under_each_tread() -> None:
    """Closed, each nosing sits 0.75 + 11.125 past its riser line, so the top
    riser line is 0.875 behind the deck's edge (Y 145.25) and riser k stands
    on the riser cut at Y 145.25 + (4 - k) x 11, from the tread below to the
    one above: 7.5 - 1 = 6.5 in, a ripped 1x8; the top one under the
    decking (Z 22.5..29)."""
    expansion = stair({"deck": DECK_REF, "risers": "closed"})
    want = [(78, 114, 145.25 + (4 - k) * 11, None, 7.5 * (k - 1), 7.5 * k - 1)
            for k in (1, 2, 3)] + [(78, 114, 145.25, None, 22.5, 29.0)]  # fmt: skip
    risers = _boxes(expansion, "riser")
    assert len(risers) == 4
    for got, (x0, x1, y0, _, z0, z1) in zip(risers, want, strict=True):
        assert got == pytest.approx((x0, x1, y0, y0 + 0.75, z0, z1), abs=1e-9)
    # Each tread butts its riser board; its nosing passes the board below by
    # 11.875 - 11 - 0.75 = 1/8 in, and nosing to nosing is still 11.
    treads = _boxes(expansion, "tread")
    assert min(t[2] for t in treads) == pytest.approx(146.0, abs=1e-9)
    assert _noses(treads) == pytest.approx([157.125, 168.125, 179.125], abs=1e-9)
    meta = {m.metadata.profile for m in expansion if m.role == "riser" and m.metadata}
    assert meta == {"1x8"}


def test_the_handrail_stands_36_above_the_nosings_on_posts() -> None:
    expansion = stair({"deck": DECK_REF})
    assert _sides(expansion, "handrail") == [("YZ", 78)]
    posts = _boxes(expansion, "handrail_post")
    # 4x4s outside the left stringer at both ends of the 33 in rail, each up
    # to the rail's top over its upper face: 30 - u x 7.5 / 11 + 36.
    assert _flat(posts) == pytest.approx(
        [
            *(74.5, 78, 146.125, 149.625, 0, 66),
            *(74.5, 78, 175.625, 179.125, 0, 66 - 29.5 * 7.5 / 11),
        ],
        abs=1e-9,
    )


def test_every_member_lists_its_lumber() -> None:
    profiles = {
        (m.role, m.metadata.profile, m.metadata.material)
        for m in stair({"deck": DECK_REF, "risers": "closed"})
        if m.metadata is not None
    }
    assert profiles == {
        ("stringer", "2x12", "southern_pine_pt"),
        ("tread", "5/4x6", "southern_pine_pt"),
        ("riser", "1x8", "southern_pine_pt"),
        ("handrail", "2x2", "southern_pine_pt"),
        ("handrail_post", "4x4", "southern_pine_pt"),
    }


def test_a_side_edge_runs_out_along_x() -> None:
    """On the right edge (X 192, the end joist's face, no decking overhang),
    the stair runs +X, its stringers on XZ planes."""
    expansion = stair({"deck": DECK_REF, "edge": "right", "position_mm": 72 * IN})
    planes = _sides(expansion, "stringer")
    assert {base for base, _ in planes} == {"XZ"}
    # Looking down +X the left is +Y: the left stringer is the high-Y one.
    assert [-offset for _, offset in planes] == [88.5, 71.25, 54.0]
    treads = _boxes(expansion, "tread")
    assert {(t[2], t[3]) for t in treads} == {(54.0, 90.0)}
    # With no overhang the top riser line is the end joist's face, so the
    # top step is the whole 11.125 in pack (1/8 in over the others, inside
    # R311.7.5.2's 3/8).
    assert min(t[0] for t in treads) == 192.0
    fronts = sorted({t[1] for t in treads})
    assert fronts[1] - 192 == pytest.approx(11.125, abs=1e-9)


def test_the_left_edge_runs_out_along_minus_x() -> None:
    """On the left edge (X 0, the end joist's face) the stair runs -X; looking
    down it the left is -Y, so the left stringer is the low-Y one and the
    handrail's posts stand below Y 54."""
    expansion = stair({"deck": DECK_REF, "edge": "left", "position_mm": 72 * IN})
    planes = _sides(expansion, "stringer")
    assert [-offset for _, offset in planes] == [54.0, 71.25, 88.5]
    treads = _boxes(expansion, "tread")
    assert max(t[1] for t in treads) == 0.0
    assert {(t[2], t[3]) for t in treads} == {(54.0, 90.0)}
    posts = _boxes(expansion, "handrail_post")
    assert {(p[2], p[3]) for p in posts} == {(50.5, 54.0)}


def test_a_freestanding_deck_with_joists_along_the_house() -> None:
    """Joists along the house run their boards along Y in rows across X, so
    the front's overhang is the typed one and its end joist carries the
    stringers; without rims a side has nothing to hang them on."""
    deck = {"attachment": "freestanding", "joist_direction": "along"}
    got = lay({"deck": DECK_REF}, deck)
    assert got.site.overhang == 0.0
    assert got.site.origin == (96.0, 144.0)
    error = _refused(
        {"deck": DECK_REF, "edge": "right", "position_mm": 72 * IN},
        {**deck, "rim_joists": "no"},
    )
    assert error.input == "edge"


def test_counts_by_role() -> None:
    roles = Counter(m.role for m in stair({"deck": DECK_REF}))
    assert (roles["stringer"], roles["tread"], roles["riser"]) == (3, 6, 0)
    assert (roles["handrail"], roles["handrail_post"]) == (1, 2)
    free = Counter(m.role for m in stair(GOLDEN_INPUTS["free-stair-107"][1]))
    # 13 treads of 2 boards, 13 risers (the top one is the header's face),
    # 3 posts on the 143 in rail (no more than 72 apart).
    assert (free["tread"], free["riser"], free["handrail_post"]) == (26, 13, 3)


def test_a_deck_height_edit_keeps_every_tread_name() -> None:
    low = {m.name: m.id for m in stair({"deck": DECK_REF}) if m.role == "tread"}
    high = {
        m.name: m.id
        for m in stair({"deck": DECK_REF}, {"height_mm": 36 * IN})
        if m.role == "tread"
    }
    assert set(low) < set(high)
    assert all(high[name] == low[name] for name in low)


# --- Refusals, by IRC section ------------------------------------------------------


def _refused(raw: dict[str, Any], deck: dict[str, Any] | None = None) -> PluginError:
    with pytest.raises(PluginError) as caught:
        stair(raw, deck)
    assert caught.value.code == PLUGIN_INPUT_UNSUPPORTED
    return caught.value


@pytest.mark.parametrize(
    ("raw", "section", "field"),
    [
        ({"width_mm": 32 * IN}, "R311.7.1", "width_mm"),
        ({"max_riser_mm": 8 * IN, "rise_mm": 16 * IN}, "R311.7.5.1", "max_riser_mm"),
        ({"tread_depth_mm": 9.5 * IN}, "R311.7.5.2", "tread_depth_mm"),
        ({"tread_depth_mm": 10.5 * IN}, "R311.7.5.3", "tread_depth_mm"),
        ({"rise_mm": 60 * IN}, "R311.7.5.1", "risers"),
        ({"handrail": "none"}, "R311.7.8", "handrail"),
        ({"handrail_height_mm": 33 * IN}, "R311.7.8.1", "handrail_height_mm"),
        (
            {
                "rise_mm": 107.09375 * IN,
                "risers": "closed",
                "opening_length_mm": 120 * IN,
            },
            "R311.7.2",
            "opening_length_mm",
        ),
    ],
)
def test_a_layout_that_breaks_r311_7_is_refused_by_section(
    raw: dict[str, Any], section: str, field: str
) -> None:
    error = _refused(raw)
    assert error.message.startswith(f"IRC {section}:"), error.message
    assert error.input == field


def test_the_headroom_check_passes_a_long_enough_opening() -> None:
    """Headroom under the opening's far edge: the ceiling (107.09375 - 9.25)
    less the nosing line there. 80 in needs 80 + 9.25 - 107.09375 + L R / T
    >= 0 ... L >= (107.09375 - 97.84375 + 80) x 11 / R."""
    riser = 107.09375 / 14
    need = (80 - 97.84375 + 107.09375) * 11 / riser
    ok = {"rise_mm": 107.09375 * IN, "risers": "closed"}
    assert stair({**ok, "opening_length_mm": (need + 0.01) * IN})
    error = _refused({**ok, "opening_length_mm": (need - 0.01) * IN})
    assert error.message.startswith("IRC R311.7.2:")


def test_closed_risers_on_a_flush_side_are_refused_for_variance() -> None:
    """The right edge has no decking overhang, so closed risers would make the
    top step 0.875 in deeper: past R311.7.5.2's 3/8 in variance."""
    error = _refused(
        {"deck": DECK_REF, "edge": "right", "position_mm": 72 * IN, "risers": "closed"}
    )
    assert error.message.startswith("IRC R311.7.5.2:")
    assert error.input == "risers"


def test_a_stair_past_the_deck_corner_or_without_a_rim_is_refused() -> None:
    assert _refused({"deck": DECK_REF, "position_mm": 10 * IN}).input == "position_mm"
    error = _refused({"deck": DECK_REF}, {"rim_joists": "no"})
    assert error.input == "edge"


def test_three_risers_need_no_handrail() -> None:
    expansion = stair({"rise_mm": 21 * IN, "handrail": "none"})
    assert not [m for m in expansion if m.role.startswith("handrail")]


# --- Warnings ----------------------------------------------------------------------


def test_b1_builds_without_a_warning() -> None:
    assert notes({"deck": DECK_REF}) == []
    assert notes({"deck": DECK_REF}, {"height_mm": 36 * IN}) == []


def test_the_free_stair_warns_of_its_throat_span_and_guard() -> None:
    assert notes(GOLDEN_INPUTS["free-stair-107"][1]) == [
        "stair_throat_thin",
        "stair_stringer_span",
        "stair_guard_required",
    ]


def test_a_cut_stringer_over_6_ft_warns_by_its_span() -> None:
    """DCA6: cut stringers span at most 6'-0" between supports. The free
    stair's stringers run from the header's face (u -0.875) to the bottom
    riser (u 142.125): 143 in, 11'-11". B1's run from the rim's face
    (u -2.125) to u 32.875, 35 in, and its 36 in edit 46 in, do not warn."""
    inputs = canonical_inputs(STAIR.manifest, GOLDEN_INPUTS["free-stair-107"][1])
    found = dict(stair_notes(ExpandInputs(STAIR_ID, {"deck": None, **inputs}, {})))
    assert found["stair_stringer_span"] == (
        "Cut stringers span 11'-11\" horizontally; DCA6 limits cut stringers "
        "to 6'-0\" between supports. Add a landing or an intermediate "
        "support, or use solid stringers."
    )
    # A free stair spans its treads' run: 9 risers of 7.5 (67.5 in) give 8
    # treads, 88 in (warns); 7 risers (52.5 in) give 6, 66 in (does not).
    assert "stair_stringer_span" in notes({"rise_mm": 67.5 * IN, "risers": "closed"})
    assert "stair_stringer_span" not in notes(
        {"rise_mm": 52.5 * IN, "risers": "closed"}
    )
    for deck in ({}, {"height_mm": 36 * IN}):
        assert "stair_stringer_span" not in notes({"deck": DECK_REF}, deck)


def test_a_guarded_deck_warns_that_its_guard_crosses_the_stair() -> None:
    assert notes({"deck": DECK_REF}, {"guard": "open_sides"}) == ["stair_deck_guard"]


def test_a_refused_layout_has_no_notes() -> None:
    assert notes({"width_mm": 30 * IN}) == []


if __name__ == "__main__":
    for name in sorted(GOLDEN_INPUTS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
