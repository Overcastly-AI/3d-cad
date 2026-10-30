"""``loft.deck`` 1.3.0: the guard opens at a stair (DECK-GUARD-OPENING).

buildings.md B1 with its guard on the open sides and its stair centred on
the rim at X 96, 36 in wide: Chief Architect's deck railing breaks where the
stair lands, so the front side's guard opens between the stair's outer
stringer faces, X 78 to X 114, with a 4x4 post each side (X 74.5..78 and
114..117.5). Each run either side, X 0..78 and X 114..192, is laid out as a
whole side is: posts at both ends, equally spaced, at most 6 ft apart.

By hand (inches), each 78 in run: posts at 1.75, 39, 76.25 (two bays of
37.25 on centres, under 72), so two 33.75 in bays; the front's rails are
4 x 33.75 = 135 a course, 192 - 36 (the opening) - 6 x 3.5 (six posts),
against 1.2.0's 3 x 59.3333 = 178 (192 - 4 x 3.5): 43 in less a course, 86
over the two. The sides keep their 2 bays of 66.75 a course. Balusters in a
33.75 bay: ceil((33.75 - 4) / 5.5) = 6 (1.2.0's 59.3333 bay held 11), so the
front's 33 become 24, the whole guard's 81 become 72; its posts 8 become 10.

A stair flush with the deck's corner (X 18, so X 0..36) ends the front's
guard on the corner post: a run from a corner too short for two posts is
the corner post alone, and a bay no wider than 4 in (IRC R312.1.3's sphere)
takes no rail.

The geometry goldens ``b1-stair-30-guard-opening`` and
``b1-stair-30-guard-corner`` are the two expansions (``model.json`` with
the member materials, ``members.json`` each member's metadata); the first
test pins them, so
``services/geometry/tests/test_deck_guard_opening_b1.py`` reads files that
cannot drift. Regenerate after a deliberate change (a NEW plugin version)
with ``uv run python packages/loft-plugins/tests/test_deck_guard_opening.py``.
"""

import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.api import ExpandInputs, Hosted
from loft_plugins.builtin.stair import stair_notes
from loft_plugins.updates import update_effect, update_for, updated_inputs
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
DECK = REGISTRY.get("loft.deck", "1.3.0")
STAIR = REGISTRY.get("loft.stair", "1.0.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
#: golden name -> the stair's raw inputs on B1 guarded: centred at X 96,
#: and flush with the deck's left corner at X 18 (X 0..36).
GOLDEN_STAIRS: dict[str, dict[str, Any]] = {
    "b1-stair-30-guard-opening": {},
    "b1-stair-30-guard-corner": {"position_mm": 18 * IN},
}
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-00000000dec1")
STAIR_ID = uuid.UUID("00000000-0000-0000-0000-0000000057a1")
SECOND_ID = uuid.UUID("00000000-0000-0000-0000-0000000057a2")
DECK_REF = FeatureRef(kind="feature", feature_id=DECK_ID)
GUARD = {"guard": "open_sides"}
GUARD_ROLES = ("guard_post", "rail", "baluster")


def deck_envelope(raw: dict[str, Any], version: str = "1.3.0") -> CustomFeature:
    m = REGISTRY.get("loft.deck", version).manifest
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


def hosted(raw: dict[str, Any], feature_id: uuid.UUID = STAIR_ID) -> Hosted:
    """A stair on the deck as documents hands it over: its canonical inputs."""
    inputs = canonical_inputs(STAIR.manifest, {"deck": DECK_REF, **raw})
    return Hosted(
        feature_id=feature_id,
        plugin_id=STAIR.manifest.id,
        plugin_version=STAIR.manifest.version,
        name=f"Stair {feature_id.int % 16}",
        inputs=ExpandInputs(feature_id, inputs),
    )


def deck(
    raw: dict[str, Any] | None = None,
    stairs: list[Hosted] | None = None,
    version: str = "1.3.0",
) -> list[ExpandedMember]:
    plugin = REGISTRY.get("loft.deck", version)
    inputs = canonical_inputs(plugin.manifest, raw or {})
    return expand(plugin, DECK_ID, inputs, {}, hosted=stairs or [])


def stair(
    deck_raw: dict[str, Any], raw: dict[str, Any] | None = None
) -> list[ExpandedMember]:
    inputs = canonical_inputs(STAIR.manifest, {"deck": DECK_REF, **(raw or {})})
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {DECK_ID: deck_envelope(deck_raw)}
    return expand(STAIR, STAIR_ID, inputs, earlier)


def boxes(expansion: list[ExpandedMember], role: str) -> dict[str, tuple[float, ...]]:
    """Each *role* member by name as its box (x0, x1, y0, y1, z0, z1), in
    inches, read from its rectangle, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: dict[str, tuple[float, ...]] = {}
    for m in expansion:
        if m.role != role:
            continue
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        lines = sketch.params.entities
        assert all(isinstance(e, SketchLine) for e in lines)
        xs = [e.start.x for e in lines if isinstance(e, SketchLine)]
        ys = [e.start.y for e in lines if isinstance(e, SketchLine)]
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            z0 = 0.0
        else:
            level = by_id[plane.feature_id].feature
            assert isinstance(level, DatumFeature)
            assert isinstance(level.params, DatumOffsetParams)
            z0 = level.params.offset_mm
        z1 = z0 + m.feature.params.distance_mm
        assert m.name is not None
        out[m.name] = tuple(
            round(v / IN, 6) for v in (min(xs), max(xs), min(ys), max(ys), z0, z1)
        )
    return out


def front(found: dict[str, tuple[float, ...]]) -> list[tuple[float, ...]]:
    """The members on the front side's line (Y 140.5..144), sorted by X."""
    return sorted(b for b in found.values() if b[2] >= 140.5 - 1e-6)


# --- The golden ---------------------------------------------------------------------


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B1 guarded with its stair: the deck's members (opened at the stair),
    then the stair's, with their materials, and their cut-list metadata."""
    raw = GOLDEN_STAIRS[name]
    plugins = [(DECK, deck(GUARD, [hosted(raw)])), (STAIR, stair(GUARD, raw))]
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


@pytest.mark.parametrize("name", sorted(GOLDEN_STAIRS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- 1.3.0 with no stair is 1.2.0; the frozen releases ignore stairs ----------------

NO_STAIR_CASES: list[dict[str, Any]] = [
    {},
    GUARD,
    {**GUARD, "width_mm": 240 * IN},
    {**GUARD, "attachment": "freestanding"},
    {**GUARD, "attachment": "freestanding", "joist_direction": "along"},
    {**GUARD, "footings": "none", "blocking": "midspan"},
]


@pytest.mark.parametrize("raw", NO_STAIR_CASES)
def test_with_no_stair_1_3_is_1_2_member_for_member(raw: dict[str, Any]) -> None:
    assert deck(raw) == deck(raw, version="1.2.0")


@pytest.mark.parametrize("raw", NO_STAIR_CASES)
def test_an_unguarded_deck_ignores_its_stair(raw: dict[str, Any]) -> None:
    if raw.get("guard") == "open_sides":
        raw = {**raw, "guard": "none"}
    assert deck(raw, [hosted({})]) == deck(raw, version="1.2.0")


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0"])
def test_the_frozen_releases_never_open_their_guard(version: str) -> None:
    """A stair offers its inputs to any deck it picks; 1.0.0-1.2.0 read none
    of them and expand byte for byte (their goldens pin them too)."""
    assert deck(GUARD, [hosted({})], version) == deck(GUARD, version=version)


# --- B1's opening, by hand ------------------------------------------------------------

RAIL_Y, POST_Y = (141.5, 143.0), (140.5, 144.0)
GUARD_Z, BOTTOM_Z, TOP_Z = (30.0, 66.0), (33.5, 37.0), (62.5, 66.0)


def test_b1s_guard_opens_between_the_outer_stringer_faces() -> None:
    members = deck(GUARD, [hosted({})])
    posts = front(boxes(members, "guard_post"))
    assert posts == [
        (x0, x0 + 3.5, *POST_Y, *GUARD_Z)
        for x0 in (0.0, 37.25, 74.5, 114.0, 151.25, 188.5)
    ]
    # The stair's outer stringers: X 78..79.5 and 112.5..114.
    stringers = sorted(boxes_side(stair(GUARD)))
    assert (stringers[0][0], stringers[-1][1]) == (78.0, 114.0)
    assert posts[2][1] == stringers[0][0] and posts[3][0] == stringers[-1][1]
    rails = front(boxes(members, "rail"))
    spans = sorted({(r[0], r[1]) for r in rails})
    assert spans == [(3.5, 37.25), (40.75, 74.5), (117.5, 151.25), (154.75, 188.5)]
    assert {(r[2], r[3], r[4], r[5]) for r in rails} == {
        (*RAIL_Y, *BOTTOM_Z),
        (*RAIL_Y, *TOP_Z),
    }
    # Nothing of the guard stands in the opening.
    for role in GUARD_ROLES:
        for b in front(boxes(members, role)):
            assert b[1] <= 78.0 + 1e-9 or b[0] >= 114.0 - 1e-9, (role, b)


def boxes_side(expansion: list[ExpandedMember]) -> list[tuple[float, float]]:
    """The stringers' X faces, read from their planes and extrudes: a
    stringer is a side profile on a YZ datum at its low face, 1.5 in thick."""
    by_id = {m.id: m for m in expansion}
    out: list[tuple[float, float]] = []
    for m in expansion:
        if m.role != "stringer":
            continue
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        assert isinstance(plane, FeatureRef)
        datum = by_id[plane.feature_id].feature
        assert isinstance(datum, DatumFeature)
        assert isinstance(datum.params, DatumOffsetParams)
        assert datum.params.base == "YZ"
        x0 = datum.params.offset_mm / IN
        out.append((round(x0, 6), round(x0 + m.feature.params.distance_mm / IN, 6)))
    return out


def test_the_rails_drop_by_the_opening_and_its_posts() -> None:
    """Rail length a course (in): 1.2.0's 133.5 + 178 + 133.5 = 445, 1.3.0's
    133.5 + 135 + 133.5 = 402; 43 less a course (36 opening + 2 x 3.5 posts),
    86 over the two courses."""

    def rail_total(members: list[ExpandedMember]) -> float:
        return sum(
            b[1] - b[0] + b[3] - b[2] - 1.5 for b in boxes(members, "rail").values()
        )

    before = deck(GUARD, version="1.2.0")
    after = deck(GUARD, [hosted({})])
    assert rail_total(before) == pytest.approx(2 * 445.0, abs=1e-9)
    assert rail_total(after) == pytest.approx(2 * 402.0, abs=1e-9)
    assert rail_total(before) - rail_total(after) == pytest.approx(86.0, abs=1e-9)
    lengths = Counter(
        round(b[1] - b[0] + b[3] - b[2] - 1.5, 4) for b in boxes(after, "rail").values()
    )
    assert lengths == Counter({66.75: 8, 33.75: 8})
    roles = Counter(m.role for m in after)
    old = Counter(m.role for m in before)
    assert (old["guard_post"], roles["guard_post"]) == (8, 10)
    assert (old["baluster"], roles["baluster"]) == (81, 72)
    assert (old["rail"], roles["rail"]) == (14, 16)
    # Everything but the front's guard is 1.2.0's, member for member, by id (its
    # corner posts are the sides' and keep their names).
    now = {m.id: m for m in after}
    for m in before:
        name = m.name or ""
        if not (name.startswith("front/") or "/front/" in name):
            assert (now[m.id].feature, now[m.id].metadata) == (m.feature, m.metadata), (
                name
            )


def test_balusters_leave_no_gap_over_4_in() -> None:
    """Each 33.75 bay holds 6 balusters, 3.5357 in apart (25.5 tall)."""
    found = front(boxes(deck(GUARD, [hosted({})]), "baluster"))
    assert len(found) == 24
    run = sorted(b for b in found if b[0] < 37.25)
    edges = [3.5, *(x for b in run for x in (b[0], b[1])), 37.25]
    gaps = [round(edges[i + 1] - edges[i], 6) for i in range(0, len(edges), 2)]
    assert gaps == pytest.approx([(33.75 - 9) / 7] * 7, abs=2e-6)
    assert all(b[4:] == (37.0, 62.5) for b in found)


def test_a_stair_on_the_left_edge_opens_the_left_side() -> None:
    """At 72 from the house: Y 54..90 on the left side (X 0..3.5), its runs
    54 and 54 in, posts at 1.75, 52.25 and 91.75, 142.25 each one bay."""
    members = deck(GUARD, [hosted({"edge": "left", "position_mm": 72 * IN})])
    left = sorted(b for b in boxes(members, "guard_post").values() if b[0] == 0.0)
    assert [(b[2], b[3]) for b in left] == [
        (0.0, 3.5), (50.5, 54.0), (90.0, 93.5), (140.5, 144.0),
    ]  # fmt: skip
    rails = sorted(
        {(b[2], b[3]) for b in boxes(members, "rail").values() if b[0] == 1.0}
    )
    assert rails == [(3.5, 50.5), (93.5, 140.5)]


def test_two_stairs_open_two_gaps() -> None:
    two = [
        hosted({"position_mm": 48 * IN}),
        hosted({"position_mm": 144 * IN}, SECOND_ID),
    ]
    posts = front(boxes(deck(GUARD, two), "guard_post"))
    assert [p[0] for p in posts] == [0.0, 26.5, 66.0, 122.5, 162.0, 188.5]


#: (edge -> its side's length): the front's posts stand on Y 140.5..144 and
#: run along X; the left side's on X 0..3.5, along Y.
EDGES: dict[str, float] = {"front": 192.0, "left": 144.0}


def along(edge: str, b: tuple[float, ...]) -> tuple[float, float] | None:
    """A guard member box's span along *edge*'s side, or None when off it."""
    if edge == "front":
        on = b[2] >= 140.5 - 1e-6 and b[3] <= 144 + 1e-6
        return (b[0], b[1]) if on else None
    return (b[2], b[3]) if b[0] >= -1e-6 and b[1] <= 3.5 + 1e-6 else None


def _near(
    members: list[ExpandedMember],
    roles: tuple[str, ...],
    edge: str,
    end: str,
    gap: float,
) -> list[tuple[float, float]]:
    """*roles*' spans on *edge* between its *end* corner and the stair, as
    spans measured from that corner."""
    length = EDGES[edge]
    reach = max(gap, 3.5)  # the corner post stands whatever the gap
    out: list[tuple[float, float]] = []
    for role in roles:
        for b in boxes(members, role).values():
            a = along(edge, b)
            if a is None:
                continue
            if end == "low" and a[1] <= reach + 1e-6:
                out.append(a)
            elif end == "high" and a[0] >= length - reach - 1e-6:
                out.append((round(length - a[1], 6), round(length - a[0], 6)))
    return sorted(out)


@pytest.mark.parametrize("edge", ["front", "left"])
@pytest.mark.parametrize("end", ["low", "high"])
@pytest.mark.parametrize(
    ("gap", "posts"),
    [
        # The stair's face *gap* in from the corner -> the posts there.
        (0.0, [(0.0, 3.5)]),  # flush: the corner post alone stays
        (3.0, [(0.0, 3.5)]),  # under two posts: the corner post alone
        (7.0, [(0.0, 3.5), (3.5, 7.0)]),  # two posts face to face
        (7.01, [(0.0, 3.5), (3.51, 7.01)]),  # 0.01 in apart: no sliver rail
        (11.0, [(0.0, 3.5), (7.5, 11.0)]),  # 4 in apart: the posts close it
        (11.5, [(0.0, 3.5), (8.0, 11.5)]),  # 4.5 in: two rails, a baluster
    ],
)
def test_a_stair_at_a_corner_ends_the_guard_on_the_corner_post(
    edge: str, end: str, gap: float, posts: list[tuple[float, float]]
) -> None:
    """A stair *gap* in from a corner of *edge* (front: X 0 or 192; left: the
    house's Y 0 or the front's 144): the run to the corner is the corner post
    alone under two posts' 7 in, and its two posts alone up to 4 in of clear
    span (IRC R312.1.3's sphere passes no narrower gap); the guard beyond the
    stair starts on its far stringer's face."""
    length = EDGES[edge]
    centre = gap + 18 if end == "low" else length - gap - 18
    members = deck(GUARD, [hosted({"edge": edge, "position_mm": centre * IN})])
    assert _near(members, ("guard_post",), edge, end, gap) == posts
    infill = _near(members, ("rail", "baluster"), edge, end, gap)
    if gap == 11.5:
        assert infill == [(8.0 - 4.5, 8.0)] * 2 + [(5.0, 6.5)]
    else:
        assert infill == []
    far = gap + 36
    beyond = _near(members, ("guard_post",), edge, end, length)
    assert (far, far + 3.5) in [(pytest.approx(a), pytest.approx(b)) for a, b in beyond]
    # Nothing stands in the opening but a corner post on the deck.
    inside = [
        a
        for a in _near(members, GUARD_ROLES, edge, end, length)
        if a[1] > gap + 1e-6 and a[0] < far - 1e-6
    ]
    assert inside == ([(0.0, 3.5)] if gap < 3.5 else [])


def test_a_run_between_two_stairs_too_short_for_its_posts_is_refused() -> None:
    two = [
        hosted({"position_mm": 60 * IN}),
        hosted({"position_mm": 100 * IN}, SECOND_ID),
    ]
    with pytest.raises(PluginError) as caught:
        deck(GUARD, two)
    assert caught.value.code == PLUGIN_INPUT_UNSUPPORTED
    assert caught.value.message.startswith("Stair 1 and Stair 2: only 4 in")


def test_a_stair_past_the_side_is_refused() -> None:
    """The deck narrowed under its stair (DECK-RESIZE-STAIR-REFUSAL)."""
    with pytest.raises(PluginError) as caught:
        deck({**GUARD, "width_mm": 100 * IN}, [hosted({})])
    assert caught.value.message.startswith("Stair 1 runs past the front side's end")


# --- The stair's warning --------------------------------------------------------------


def _notes(version: str, raw: dict[str, Any]) -> list[str]:
    inputs = canonical_inputs(STAIR.manifest, {"deck": DECK_REF})
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {DECK_ID: deck_envelope(raw, version)}
    return [code for code, _ in stair_notes(ExpandInputs(STAIR_ID, inputs, earlier))]


def test_the_stair_stops_warning_once_the_guard_opens() -> None:
    assert _notes("1.2.0", GUARD) == ["stair_deck_guard"]
    assert _notes("1.3.0", GUARD) == []
    assert _notes("1.3.0", {}) == []


def test_the_stair_is_the_same_on_either_deck() -> None:
    m = REGISTRY.get("loft.deck", "1.2.0").manifest
    older: dict[uuid.UUID, AuthoredEnvelope] = {
        DECK_ID: deck_envelope(GUARD, m.version)
    }
    inputs = canonical_inputs(STAIR.manifest, {"deck": DECK_REF})
    assert stair(GUARD) == expand(STAIR, STAIR_ID, inputs, older)


# --- The update -----------------------------------------------------------------------


def _update(version: str, raw: dict[str, Any], stairs: list[Hosted]) -> Any:
    update = update_for("loft.deck", version, REGISTRY)
    assert update is not None and update.to_version == "1.3.0"
    old = REGISTRY.get("loft.deck", version)
    moved = canonical_inputs(
        DECK.manifest, updated_inputs(update, canonical_inputs(old.manifest, raw))
    )
    before = deck(raw, stairs, version)
    after = deck(moved, stairs)
    return update, update_effect(
        [("loft.deck", before, after)], REGISTRY, update.relay_reason
    )


def test_a_deck_with_no_stair_updates_quietly() -> None:
    for raw, stairs in ((GUARD, []), ({}, [hosted({})])):
        _, effect = _update("1.2.0", raw, stairs)
        assert not effect.changes and effect.adds == () and effect.relays == ()


def test_a_guarded_deck_at_its_stair_re_lays_its_front_guard() -> None:
    """The front's posts but the corners, its rails and its balusters move:
    a re-lay, so the update is offered on its own (PLUGIN-UPDATE-ALL)."""
    update, effect = _update("1.2.0", GUARD, [hosted({})])
    assert update.summary == (
        "Opens the guard where a stair lands on the deck, with a post at "
        "each side; a deck with no stair is unchanged."
    )
    assert effect.changes
    assert effect.adds == ("2 guard posts", "2 rails")
    assert effect.relays == ("2 guard posts", "6 rails", "33 balusters")
    assert effect.sentence == (
        "Re-lays 2 guard posts, 6 rails and 33 balusters to open the guard at "
        "the stair. Adds 2 guard posts and 2 rails."
    )


def test_a_1_1_deck_gains_its_footings_and_its_opening() -> None:
    _, effect = _update("1.1.0", {**GUARD, "width_mm": 192 * IN}, [hosted({})])
    assert effect.adds == (
        "3 pier footings",
        "2 guard posts",
        "2 rails",
        "3 post bases",
    )
    assert effect.relays == ("2 guard posts", "6 rails", "33 balusters")
    _, quiet = _update("1.1.0", {}, [])
    assert quiet.adds == ("3 pier footings", "3 post bases") and quiet.relays == ()


def test_new_decks_are_1_3_0() -> None:
    assert REGISTRY.latest("loft.deck").manifest.version == "1.3.0"
    assert DECK.manifest.inputs == REGISTRY.get("loft.deck", "1.2.0").manifest.inputs


if __name__ == "__main__":
    for name in sorted(GOLDEN_STAIRS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
