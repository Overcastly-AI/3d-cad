"""PLUGIN-UPDATE-ALL: every stored Build release updates to its newest, the
new inputs at their defaults, and the update names what it adds.

Onshape updates a custom feature to its Feature Studio's newest version,
mapping every input it can and taking the defaults of new parameters
(VISION, 2026-10-29). Checked by hand against
``docs/reference-parts/buildings.md``:

* B7 saved at batch48's releases (``b7-outline``: floor 1.2.0, walls
  1.3.0, the door and five windows 1.1.0, the roof 1.4.0): one Update all
  leaves no release out of date and is B7 built fresh today, member for
  member: the floor 1.3.0 on Long walls (byte for byte 1.2.0's), the walls
  1.4.0, the openings 1.5.0 (18 plies, 12 spacers) and the roof 1.6.0 with
  its 11 ceiling joists: 264 852.3789 + 1 769.625 + 1 179.75 + 22 887.596423
  = 290 689.350323 in³ (the kernel checks it on ``goldens/b7-update-all``,
  ``services/geometry/tests/test_update_all_b7.py``);
* the roof's update adds 11 ceiling joists, an opening's 2 header spacers
  and a header ply (its wall's), the floor and the walls nothing at all;
* a floor 1.2.0 on any outline 1.2.0 reads, or typed, Joists bear on frames
  the same joists, rims and sills;
* B1 at deck 1.1.0 gains 3 pier footings (3 pi 8² 12 = 7 238.23 in³, 8 bags
  of 80 lb) and 3 post bases, every other member as it was;
* B9 at foundation 1.0.0 lists 5 vents and 1 access door, and is 1.1.0's B9
  exactly (whose pours ``b9-crawl-space`` orders as 2.75 + 4.25 yd³);
* casework 1.0.0 is the newest and offered nothing; a newer release would
  be offered with its inputs as they are.

Regenerate the golden after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_update_all.py``.
"""

import math
import sys
import uuid
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from loft_plugins import (
    REGISTRY,
    ExpandInputs,
    Plugin,
    canonical_inputs,
    update_for,
    updated_inputs,
)
from loft_plugins.builtin import BUILTIN_PLUGINS
from loft_plugins.builtin.cabinets import CABINETS_V1
from loft_plugins.updates import declared_updates, update_effect
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    CustomFeature,
    CustomInputValue,
    EvaluateTreeRequest,
    ExpandedMember,
)
from loft_wire.foundation import concrete_bags

sys.path.insert(0, str(Path(__file__).parent))
import test_building_outline as outline
import test_crawl_space as crawl
import test_deck_footings as deck
from test_opening_update import Row, by_feature, pins, rebuild, update_all
from test_opening_update import (
    _titles as titles_of,  # pyright: ignore[reportPrivateUsage]
)

GOLDEN = "b7-update-all"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000007ba")
IN = outline.IN


def newest(plugin_id: str) -> Plugin:
    return REGISTRY.latest(plugin_id)


def custom_rows(rows: list[Row]) -> list[Row]:
    return [r for r in rows if isinstance(r[1], CustomFeature)]


def still_offered(rows: list[Row]) -> list[tuple[str, str]]:
    return [
        (env.params.plugin_id, env.params.plugin_version)
        for _, env, _ in custom_rows(rows)
        if isinstance(env, CustomFeature)
        and update_for(env.params.plugin_id, env.params.plugin_version, REGISTRY)
        is not None
    ]


# --- B7 ----------------------------------------------------------------------------

#: What B7's openings typed in 1.1.0 mean at 1.5.0: measured from the wall
#: start, the typed size, no unit drawn (B7's reference has none).
AS_TYPED = {"measure_from": "start", "size": "custom", "draw_unit": "none"}


@contextmanager
def built_today() -> Generator[None]:
    """test_building_outline's tree builder with every plugin at its newest."""
    with (
        mock.patch.object(outline, "FLOOR", newest("loft.floor")),
        mock.patch.object(outline, "WALL", newest("loft.wall")),
        mock.patch.object(outline, "ROOF", newest("loft.roof")),
    ):
        yield


def fresh_b7() -> list[Row]:
    """B7 drawn today: buildings.md's inputs, every new input at its default."""
    door, window = newest("loft.door"), newest("loft.window")
    openings = [
        (
            door if p.manifest.id == "loft.door" else window,
            name,
            seg,
            {**raw, **AS_TYPED},
        )
        for p, name, seg, raw in outline.b7_openings()
    ]
    with built_today():
        return outline.house(
            outline.rectangle(288, 192),
            openings,
            outline.B7_STUDS,
            outline.B7_FLOOR,
            {"slope_walls": ["e1", "e3"], **outline.B7_ROOF},
        )


def test_one_update_all_leaves_nothing_out_of_date() -> None:
    stored = outline.b7()
    assert still_offered(stored) == pins(stored)  # every Build feature
    updated = update_all(stored)
    assert still_offered(updated) == []
    assert pins(updated) == [
        ("loft.floor", "1.3.0"),
        ("loft.wall", "1.4.0"),
        ("loft.door", "1.5.0"),
        *[("loft.window", "1.5.0")] * 5,
        ("loft.roof", "1.6.0"),
    ]


def test_b7_updated_is_b7_built_fresh_today() -> None:
    updated, fresh = update_all(outline.b7()), fresh_b7()
    assert [(f, ms) for f, _, ms in updated] == [(f, ms) for f, _, ms in fresh]
    floor = next(env for _, env, _ in custom_rows(updated))
    assert isinstance(floor, CustomFeature)
    assert floor.params.inputs["joists_bear_on"] == "long_walls"
    assert "joist_direction" not in floor.params.inputs


def test_the_floor_is_byte_for_byte_and_the_roof_adds_its_joists() -> None:
    before, after = by_feature(outline.b7()), by_feature(update_all(outline.b7()))
    assert after[outline.FLOOR_ID] == before[outline.FLOOR_ID]
    old, new = before[outline.ROOF_ID], after[outline.ROOF_ID]
    assert new[: len(old)] == old
    assert Counter(m.role for m in new[len(old) :]) == Counter(
        {"plane": 11, "section": 11, "ceiling_joist": 11}
    )
    bodies = Counter(m.role for m in outline.members_of(update_all(outline.b7())))
    assert (bodies["header"], bodies["spacer"], bodies["ceiling_joist"]) == (18, 12, 11)


def effect_of(rows: list[Row], fid: uuid.UUID) -> tuple[tuple[str, ...], bool]:
    """What updating *fid* alone adds and whether it changes anything: its
    members and its host's, stored and after the update (documents' offer)."""
    stored = {f: (e, ms) for f, e, ms in rows}
    moved = by_feature(_only(rows, fid))
    env = stored[fid][0]
    assert isinstance(env, CustomFeature)
    changed = [(env.params.plugin_id, stored[fid][1], moved[fid])]
    host = env.params.inputs.get("host_wall")
    if host is not None:
        host_id = host.feature_id  # type: ignore[union-attr]
        host_env = stored[host_id][0]
        assert isinstance(host_env, CustomFeature)
        changed.append((host_env.params.plugin_id, stored[host_id][1], moved[host_id]))
    effect = update_effect(changed, REGISTRY)
    return effect.adds, effect.changes


def _only(rows: list[Row], fid: uuid.UUID) -> list[Row]:
    """*rows* with only *fid* updated, the tree re-expanded."""
    out: list[tuple[uuid.UUID, Any]] = []
    earlier: dict[uuid.UUID, Any] = {}
    for f, env, members in rows:
        if f == fid and isinstance(env, CustomFeature):
            pin = env.params
            update = update_for(pin.plugin_id, pin.plugin_version, REGISTRY)
            assert update is not None
            target = REGISTRY.get(pin.plugin_id, update.to_version)
            context = ExpandInputs(f, dict(pin.inputs), dict(earlier))
            inputs = canonical_inputs(
                target.manifest, updated_inputs(update, pin.inputs, context)
            )
            params = pin.model_copy(
                update={"plugin_version": update.to_version, "inputs": inputs}
            )
            env = env.model_copy(update={"params": params})
        earlier[f] = env
        for m in members:
            earlier[m.id] = m.feature
        out.append((f, env))
    return rebuild(out)


def test_each_update_names_what_it_adds() -> None:
    rows = outline.b7()
    names = {fid: env for fid, env, _ in custom_rows(rows)}
    door = next(
        f
        for f, e in names.items()
        if isinstance(e, CustomFeature) and e.params.plugin_id == "loft.door"
    )
    assert effect_of(rows, outline.ROOF_ID) == (("11 ceiling joists",), True)
    assert effect_of(rows, door) == (("2 header spacers", "1 header ply"), True)
    # The floor and the walls change nothing: no badge, but Update all.
    assert effect_of(rows, outline.FLOOR_ID) == ((), False)
    assert effect_of(rows, outline.WALLS_ID) == ((), False)


# --- The floor's map ----------------------------------------------------------------

W, D = 288.0, 192.0
DRAWINGS = {
    "the rectangle tool": [(0.0, 0.0), (W, 0.0), (W, D), (0.0, D)],
    "clockwise, up first": [(0.0, 0.0), (0.0, D), (W, D), (W, 0.0)],
}
FRAMING = ("joist", "rim", "sill")


def _floor_update(
    raw: dict[str, Any], earlier: dict[uuid.UUID, Any]
) -> tuple[list[ExpandedMember], list[ExpandedMember], str]:
    old, new = REGISTRY.get("loft.floor", "1.2.0"), newest("loft.floor")
    update = update_for("loft.floor", "1.2.0", REGISTRY)
    assert update is not None and update.to_version == new.manifest.version
    stored = canonical_inputs(old.manifest, raw)
    context = ExpandInputs(outline.FLOOR_ID, stored, earlier)
    moved = canonical_inputs(new.manifest, updated_inputs(update, stored, context))
    before = outline.expand(old, outline.FLOOR_ID, stored, earlier)
    after = outline.expand(new, outline.FLOOR_ID, moved, earlier)
    return before, after, str(moved["joists_bear_on"])


@pytest.mark.parametrize("drawing", sorted(DRAWINGS))
@pytest.mark.parametrize("direction", ["depth", "width"])
def test_joists_bear_on_frames_the_same_joists_on_an_outline(
    drawing: str, direction: str
) -> None:
    corners = DRAWINGS[drawing]
    sketch = outline.loop_sketch(
        corners,
        {
            "e1": math.dist(corners[0], corners[1]),
            "e2": math.dist(corners[1], corners[2]),
        },
    )
    earlier: dict[uuid.UUID, Any] = {outline.SKETCH_ID: sketch}
    raw = {
        "outline": outline.ref(outline.SKETCH_ID),
        **outline.B7_FLOOR,
        "joist_direction": direction,
    }
    before, after, bear_on = _floor_update(raw, earlier)
    assert outline.bodies(after, FRAMING) == outline.bodies(before, FRAMING)
    # 1.2.0 ran the width along the first line: the rectangle tool's is the
    # front (X), the other drawing's the left side (Y).
    along_x = (direction == "width") == (drawing == "the rectangle tool")
    assert bear_on == ("left_right" if along_x else "long_walls")
    if drawing == "the rectangle tool":
        assert after == before  # B7's own drawing: byte for byte


@pytest.mark.parametrize("degrees", [0.0, 90.0, 180.0, 30.0])
@pytest.mark.parametrize("direction", ["depth", "width"])
def test_a_typed_floor_keeps_its_joists_byte_for_byte(
    degrees: float, direction: str
) -> None:
    raw = {
        "start_x_mm": 100.0,
        "direction_deg": degrees,
        "width_mm": 120 * IN,
        "depth_mm": 200 * IN,
        "joist_direction": direction,
    }
    before, after, bear_on = _floor_update(raw, {})
    assert after == before
    # Across the 120 in width is the shorter span: Long walls.
    assert bear_on == ("long_walls" if direction == "width" else "front_back")


# --- B1's deck ----------------------------------------------------------------------

B1 = deck.GOLDEN_INPUTS["plugin-deck-v1.2-b1-footings-16ft"]


def _deck_update() -> tuple[list[ExpandedMember], list[ExpandedMember]]:
    old = REGISTRY.get("loft.deck", "1.1.0")
    update = update_for("loft.deck", "1.1.0", REGISTRY)
    assert update is not None and update.to_version == "1.2.0"
    stored = canonical_inputs(old.manifest, B1)
    moved = canonical_inputs(
        newest("loft.deck").manifest, updated_inputs(update, stored)
    )
    return deck.members(B1, "1.1.0"), deck.members(moved, "1.2.0")


def test_b1_gains_three_footings_eight_bags_and_three_post_bases() -> None:
    before, after = _deck_update()
    assert after == deck.members(B1)  # B1 built today
    effect = update_effect([("loft.deck", before, after)], REGISTRY)
    assert effect.adds == ("3 pier footings", "3 post bases")
    assert effect.sentence == "Adds 3 pier footings and 3 post bases."
    piers = deck.piers(after)
    assert piers == [(x, 126, 8, -12, 0) for x in (2.75, 96, 189.25)]
    volume = sum(math.pi * r * r * (z1 - z0) for _, _, r, z0, z1 in piers)
    assert round(volume, 2) == 7238.23
    assert concrete_bags(volume * IN**3, 5) == 8
    footings = [m for m in after if m.role == "footing"]
    assert [
        m.metadata.concrete.post_base
        for m in footings
        if m.metadata and m.metadata.concrete
    ] == ["post_base_6x6"] * 3


def test_b1_keeps_every_other_member() -> None:
    """Every 1.1.0 member keeps its id, feature and metadata (a named
    member's running index counts the levels before it, so it is not
    compared); what is new is the piers, their level and their sections."""
    before, after = _deck_update()
    by_id = {m.id: m for m in after}
    assert all(by_id[m.id].model_copy(update={"index": m.index}) == m for m in before)
    old = {m.id for m in before}
    assert Counter(m.role for m in after if m.id not in old) == Counter(
        {"footing": 3, "section": 3, "level": 1}
    )


# --- B9's crawl space ---------------------------------------------------------------


def test_b9_at_1_0_0_lists_five_vents_and_one_access_door() -> None:
    stored = crawl.b9(plugin=crawl.FOUNDATION_V1_0)
    updated = update_all(stored, {"loft.foundation"})
    assert crawl.foundation_members(updated) == crawl.foundation_members(crawl.b9())
    effect = update_effect(
        [
            (
                "loft.foundation",
                crawl.foundation_members(stored),
                crawl.foundation_members(updated),
            )
        ],
        REGISTRY,
    )
    assert effect.adds == ("5 foundation vents", "1 access door")
    assert effect.changes


# --- Casework -----------------------------------------------------------------------


def test_casework_1_0_0_is_the_newest_and_a_newer_one_would_take_its_inputs() -> None:
    assert update_for("loft.cabinets", "1.0.0", REGISTRY) is None
    later = Plugin(
        CABINETS_V1.manifest.model_copy(update={"version": "1.1.0"}),
        CABINETS_V1.expand,
    )
    table = {
        (u.plugin_id, u.from_version): u
        for u in declared_updates((*BUILTIN_PLUGINS, later))
    }
    update = table[("loft.cabinets", "1.0.0")]
    assert update.to_version == "1.1.0"
    stored: dict[str, CustomInputValue] = {"construction": "frameless", "boxes": []}
    assert updated_inputs(update, stored) == stored


# --- The golden ---------------------------------------------------------------------


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B7 from its outline after one Update all: what documents stores and
    sends to geometry."""
    rows = update_all(outline.b7())
    titles = titles_of()
    metadata: list[CutListMember] = []
    for _, env, members in custom_rows(rows):
        assert isinstance(env, CustomFeature)
        plugin_id: Any = env.params.plugin_id
        metadata += [
            CutListMember(
                feature_id=m.id,
                role=m.role,
                title=titles[(plugin_id, m.role)],
                plugin_id=plugin_id,
                metadata=m.metadata,
            )
            for m in members
            if m.metadata is not None
        ]
    request = outline.request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata


def test_the_golden_is_the_updated_expansion() -> None:
    request, metadata = golden()
    folder = outline.GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == outline.members_json(metadata)


def test_the_golden_has_b7s_bodies_the_plies_spacers_and_joists() -> None:
    _, metadata = golden()
    assert len(metadata) == 217 + 6 + 12 + 11


if __name__ == "__main__":
    request, metadata = golden()
    (outline.GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (outline.GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (outline.GOLDENS / GOLDEN / "members.json").write_text(
        outline.members_json(metadata)
    )
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
