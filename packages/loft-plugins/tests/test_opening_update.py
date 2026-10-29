"""OPENING-UPDATE: a stored feature updated to its newer release, and
``loft.window`` / ``loft.door`` 1.5.0's header spacers (RESEARCH §23).

Onshape updates a custom feature to its Feature Studio's newer version on
request; here an update carries the stored inputs to the newer release by an
explicit map (``loft_plugins.updates``). Checked by hand against
``docs/reference-parts/buildings.md`` B7:

* 1.5.0 has 1.4.0's inputs exactly, and draws a 1/2 in plywood spacer in each
  1/2 in gap of a filled header (two in 2x6, one in 2x4), none in a 2x8's
  1-3/8 in gaps, and an insulated header's foam;
* ``b7-outline`` (walls 1.3.0, door and windows 1.1.0, roof 1.4.0) updated:
  the walls (1.5.0) frame exactly what they did and add their Exterior
  finish (SIDING-TRIM), the roof notches it round its tails, and
  the six openings at 1.5.0 give 18 plies (the face plies keep their ids)
  and 12 spacers, 2 x 41, 6 x 39.5 and 4 x 27.5 (429 in, 2 359.5 in²,
  1 179.75 in³), 264 852.3789 + 1 769.625 + 1 179.75 = 267 801.7539 in³,
  with no two members overlapping;
* the floor (1.2.0) and the roof (1.4.0) take their own updates
  (PLUGIN-UPDATE-ALL, ``test_update_all.py``): with the openings and walls
  alone updated, the floor and the roof expand exactly as they did.

The geometry golden ``b7-opening-update`` (the walls and openings updated) is
written from here and pinned by this module; its kernel acceptance is
``services/geometry/tests/test_opening_update_b7.py``. Regenerate after a
deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_opening_update.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import (
    REGISTRY,
    ExpandInputs,
    Hosted,
    canonical_inputs,
    expand,
    host_of,
    settle_inputs,
    update_for,
    updated_inputs,
)
from loft_plugins.builtin.openings import header_infill
from loft_plugins.builtin.wall import Opening, WallSpec
from loft_plugins.updates import UPDATES, check_update_table
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
)

# The B7 builders and body probes are test_building_outline's (importlib
# mode puts no test directory on sys.path, so add this one).
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    GOLDENS,
    b7,
    boxes,
    members_json,
    members_of,
    overlaps,
    request_of,
)

GOLDEN = "b7-opening-update"
WINDOW = REGISTRY.get("loft.window", "1.5.0")
DOOR = REGISTRY.get("loft.door", "1.5.0")

Row = tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]


# --- The update table -------------------------------------------------------------


def test_every_update_names_two_released_versions_newer_last() -> None:
    check_update_table(REGISTRY)
    assert {(u.plugin_id, u.from_version, u.to_version) for u in UPDATES.values()} == {
        *(
            (plugin, version, "1.5.0")
            for plugin in ("loft.window", "loft.door")
            for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0")
        ),
        ("loft.wall", "1.2.0", "1.5.0"),
        ("loft.wall", "1.3.0", "1.5.0"),
        ("loft.wall", "1.4.0", "1.5.0"),
        ("loft.roof", "1.2.0", "1.8.0"),
        ("loft.roof", "1.3.0", "1.8.0"),
        ("loft.roof", "1.4.0", "1.8.0"),
        ("loft.roof", "1.5.0", "1.8.0"),
        ("loft.roof", "1.6.0", "1.8.0"),
        ("loft.roof", "1.7.0", "1.8.0"),
        ("loft.floor", "1.2.0", "1.3.0"),
        ("loft.deck", "1.1.0", "1.3.0"),
        ("loft.deck", "1.2.0", "1.3.0"),
        ("loft.foundation", "1.0.0", "1.1.0"),
        ("loft.cabinets", "1.0.0", "1.1.0"),
    }


def test_the_latest_and_the_unmapped_releases_are_offered_none() -> None:
    for plugin, version in (
        ("loft.window", "1.5.0"),
        ("loft.wall", "1.5.0"),
        ("loft.roof", "1.8.0"),
        ("loft.floor", "1.3.0"),
        ("loft.deck", "1.3.0"),
        ("loft.foundation", "1.1.0"),
        ("loft.cabinets", "1.1.0"),
        ("loft.wall", "1.0.0"),  # ordinal ids 1.1.0 renamed
        ("loft.deck", "1.0.0"),  # ordinal ids 1.1.0 renamed
        ("loft.floor", "1.1.0"),  # typed, before the outline
        ("loft.roof", "1.1.0"),  # typed, before the walls
    ):
        assert update_for(plugin, version, REGISTRY) is None, (plugin, version)


def test_an_old_opening_reads_as_it_built_and_fills_its_header() -> None:
    """1.1.0's offset from the start, no size and no unit become Measured
    from the wall start, Custom and Rough opening only; Header build Fill."""
    update = update_for("loft.window", "1.1.0", REGISTRY)
    assert update is not None
    stored = {"wall_segment": ["e1"], "offset_mm": 2286.0, "width_mm": 914.4}
    assert updated_inputs(update, stored) == {
        **stored,
        "measure_from": "start",
        "size": "custom",
        "draw_unit": "none",
        "header_build": "fill",
    }


def test_a_1_4_0_opening_keeps_its_own_header_build() -> None:
    update = update_for("loft.door", "1.4.0", REGISTRY)
    assert update is not None
    stored = {
        "measure_from": "end",
        "size": "door_3068",
        "header_build": "two_ply",
        "draw_unit": "draw",
    }
    assert updated_inputs(update, stored) == stored


def test_1_5_0_has_1_4_0s_inputs_and_adds_the_infill_roles() -> None:
    for new in (WINDOW, DOOR):
        old = REGISTRY.get(new.manifest.id, "1.4.0")
        assert new.manifest.inputs == old.manifest.inputs
        roles = [r.role for r in new.manifest.members]
        assert roles == [
            *(r.role for r in old.manifest.members),
            "header_level",
            "infill_section",
            "spacer",
            "foam",
        ]


# --- The infill ---------------------------------------------------------------------


def _wall(stud: str) -> WallSpec:
    raw = canonical_inputs(
        REGISTRY.get("loft.wall", "1.1.0").manifest, {"stud_profile": stud}
    )
    return WallSpec.from_inputs(ExpandInputs(uuid.uuid4(), raw))


def _door(wall: WallSpec, build: str) -> Opening:
    raw = canonical_inputs(
        DOOR.manifest,
        {
            "host_wall": FeatureRef(kind="feature", feature_id=uuid.uuid4()),
            "measure_from": "start",
            "header_build": build,
        },
    )
    return Opening.from_inputs("door", "Door", ExpandInputs(uuid.uuid4(), raw), wall)


@pytest.mark.parametrize(
    ("stud", "build", "want"),
    [
        # 2x6 filled: 1.5 + 0.5 + 1.5 + 0.5 + 1.5, the spacers at 1.5 and 3.5.
        ("us_2x6", "fill", [("spacer", 1.5, 2.0), ("spacer", 3.5, 4.0)]),
        # 2x4 filled: two plies and one 1/2 in spacer.
        ("us_2x4", "fill", [("spacer", 1.5, 2.0)]),
        # 2x8 filled: three plies, the 1-3/8 in gaps left open.
        ("us_2x8", "fill", []),
        # Insulated: the foam fills the gap between the face plies.
        ("us_2x6", "two_ply", [("foam", 1.5, 4.0)]),
        ("us_2x4", "two_ply", [("foam", 1.5, 2.0)]),
        ("us_2x8", "two_ply", [("foam", 1.5, 5.75)]),
    ],
)
def test_what_fills_the_header(
    stud: str, build: str, want: list[tuple[str, float, float]]
) -> None:
    """A 3068 door (rough opening 38 x 82.5 at 72 from the start): every
    strip spans the header, X 51.5..92.5 (41), and its depth, 82.5..88."""
    wall = _wall(stud)
    strips = header_infill(wall, _door(wall, build))
    assert [(s.role, s.v0, s.v1) for s in strips] == want
    for s in strips:
        assert (s.u0, s.u1, s.z0, s.z1) == (51.5, 92.5, 82.5, 88.0)


# --- B7 updated -------------------------------------------------------------------


def rebuild(rows: list[tuple[uuid.UUID, AuthoredEnvelope]]) -> list[Row]:
    """Expand *rows* in tree order as documents does: each custom feature with
    the features before it and the later ones it hosts (inputs only)."""
    hosts: dict[uuid.UUID, list[tuple[uuid.UUID, CustomFeature]]] = {}
    for fid, env in rows:
        if isinstance(env, CustomFeature):
            pin = env.params
            host = host_of(
                REGISTRY.get(pin.plugin_id, pin.plugin_version).manifest, pin.inputs
            )
            if host is not None:
                hosts.setdefault(host, []).append((fid, env))
    names = {fid: f"F{n}" for n, (fid, _) in enumerate(rows)}
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    out: list[Row] = []
    for fid, env in rows:
        members: list[ExpandedMember] = []
        if isinstance(env, CustomFeature):
            pin = env.params
            plugin = REGISTRY.get(pin.plugin_id, pin.plugin_version)
            hosted = tuple(
                Hosted(
                    h,
                    he.params.plugin_id,
                    he.params.plugin_version,
                    names[h],
                    ExpandInputs(h, he.params.inputs),
                )
                for h, he in hosts.get(fid, [])
            )
            members = expand(plugin, fid, pin.inputs, dict(earlier), hosted=hosted)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        out.append((fid, env, members))
    return out


def update_all(rows: list[Row], only: set[str] | None = None) -> list[Row]:
    """Every feature with an update (of a plugin in *only*, when given) moved
    to its target by its map, its inputs checked and settled against the
    target, then the tree re-expanded (documents' Update all, without the
    database)."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    updated: list[tuple[uuid.UUID, AuthoredEnvelope]] = []
    for fid, env, members in rows:
        if isinstance(env, CustomFeature) and (
            only is None or env.params.plugin_id in only
        ):
            pin = env.params
            update = update_for(pin.plugin_id, pin.plugin_version, REGISTRY)
            if update is not None:
                target = REGISTRY.get(pin.plugin_id, update.to_version)
                context = ExpandInputs(fid, dict(pin.inputs), dict(earlier))
                inputs = canonical_inputs(
                    target.manifest, updated_inputs(update, pin.inputs, context)
                )
                inputs = settle_inputs(target, fid, inputs, earlier)
                params = pin.model_copy(
                    update={"plugin_version": update.to_version, "inputs": inputs}
                )
                env = env.model_copy(update={"params": params})
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        updated.append((fid, env))
    return rebuild(updated)


def by_feature(rows: list[Row]) -> dict[uuid.UUID, list[ExpandedMember]]:
    return {fid: members for fid, _, members in rows}


def pins(rows: list[Row]) -> list[tuple[str, str]]:
    return [
        (env.params.plugin_id, env.params.plugin_version)
        for _, env, _ in rows
        if isinstance(env, CustomFeature)
    ]


def test_the_stored_b7_rebuilds_as_its_golden() -> None:
    """The rebuild above is documents' expansion: B7 as stored is b7()."""
    stored = b7()
    assert rebuild([(f, e) for f, e, _ in stored]) == stored


def test_a_typed_wall_1_2_0_updates_to_the_same_members() -> None:
    """B2's front wall typed at 1.2.0 with its OSB and a 1.0.0 door: at
    1.5.0, same inputs, it frames the same members under the same ids, then
    takes the new Exterior finish's default (SIDING-TRIM): its siding and
    the door's three casing pieces."""
    wall_id = uuid.UUID("00000000-0000-0000-0000-0000000002f0")
    door_id = uuid.UUID("00000000-0000-0000-0000-0000000002f1")
    raw = {
        "start_x_mm": 144 * 25.4,
        "direction_deg": 180.0,
        "length_mm": 144 * 25.4,
        "sheathing": "osb_7_16",
    }
    door = REGISTRY.get("loft.door", "1.0.0")
    hosted = (
        Hosted(
            door_id,
            "loft.door",
            "1.0.0",
            "Door",
            ExpandInputs(
                door_id,
                canonical_inputs(
                    door.manifest,
                    {
                        "host_wall": FeatureRef(kind="feature", feature_id=wall_id),
                        "offset_mm": 72 * 25.4,
                    },
                ),
            ),
        ),
    )
    update = update_for("loft.wall", "1.2.0", REGISTRY)
    assert update is not None and update.to_version == "1.5.0"
    old = REGISTRY.get("loft.wall", "1.2.0")
    new = REGISTRY.get("loft.wall", "1.5.0")
    stored = canonical_inputs(old.manifest, raw)
    moved = canonical_inputs(new.manifest, updated_inputs(update, stored))
    before = expand(old, wall_id, stored, {}, hosted=hosted)
    after = expand(new, wall_id, moved, {}, hosted=hosted)
    assert len(before) > 0 and after[: len(before)] == before
    added = Counter(m.role for m in after[len(before) :] if m.metadata is not None)
    assert added == Counter({"siding": 1, "casing": 3})


def test_update_all_moves_every_pin_to_the_newest() -> None:
    assert pins(update_all(b7())) == [
        ("loft.floor", "1.3.0"),
        ("loft.wall", "1.5.0"),
        *[("loft.door", "1.5.0")],
        *[("loft.window", "1.5.0")] * 5,
        ("loft.roof", "1.8.0"),
    ]


def test_with_the_openings_and_walls_updated_floor_and_roof_are_as_they_were() -> None:
    """The floor is as it was. The roof (1.4.0) frames every member as it
    did; each tail's notch also cuts the siding or corner board the walls'
    new Exterior finish puts under it (SIDING-TRIM), listed after the
    sheathing panels it cut before."""
    before, after = by_feature(b7()), by_feature(update_all(b7(), WALLS_OPENINGS))
    fids = [fid for fid, env, _ in b7() if isinstance(env, CustomFeature)]
    floor, roof = fids[0], fids[-1]
    assert after[floor] == before[floor]
    assert [m.id for m in after[roof]] == [m.id for m in before[roof]]
    for old, new in zip(before[roof], after[roof], strict=True):
        if old.role != "cutter":
            assert new == old
            continue
        assert isinstance(old.feature, ExtrudeFeature)
        assert isinstance(new.feature, ExtrudeFeature)
        was, now = old.feature.params.cut_bodies, new.feature.params.cut_bodies
        assert isinstance(was, list) and isinstance(now, list)
        assert now[: len(was)] == was and len(now) == len(was) + 1


def test_the_walls_frame_what_they_framed_and_the_middle_plies() -> None:
    """Wall 1.5.0 frames 1.3.0's members exactly, every id kept; the six
    filled headers add one middle ply each (and its section), and the
    Exterior finish its siding (SIDING-TRIM: test_siding_trim.py)."""
    stored, updated = b7(), update_all(b7())
    walls = [fid for fid, env, _ in stored if isinstance(env, CustomFeature)][1]
    before = {m.id: m for m in by_feature(stored)[walls]}
    after = {m.id: m for m in by_feature(updated)[walls]}
    # The same member, feature and metadata under every id (a named member's
    # running index counts the plies before it, so it is not compared).
    assert all(
        after[i].model_copy(update={"index": m.index}) == m for i, m in before.items()
    )
    added = Counter(m.role for i, m in after.items() if i not in before)
    assert added == Counter(
        {
            "header": 6,
            "section": 6,
            "siding_plane": 4,
            "siding_section": 4 + 8 + 23,
            "siding": 4,
            "corner_board": 8,
            "casing": 23,
        }
    )


HEADER_LENGTHS = Counter({41.0: 3, 39.5: 9, 27.5: 6})
SPACER_LENGTHS = Counter({41.0: 2, 39.5: 6, 27.5: 4})
VOLUME_IN3 = 264852.3788656 + 1769.625 + 1179.75


def _length(box: tuple[float, ...]) -> float:
    return round(max(box[1] - box[0], box[3] - box[2]), 6)


def test_b7_updated_has_18_plies_and_12_spacers() -> None:
    """18 plies 5.5 deep (was 12) and 12 spacers 1/2 x 5.5 of 1/2 plywood:
    2 x 41, 6 x 39.5 and 4 x 27.5, 429 in, 2 359.5 in², 1 179.75 in³."""
    members = members_of(update_all(b7()))
    plies = boxes(members, ("header",))
    spacers = boxes(members, ("spacer",))
    assert Counter(_length(b) for b in plies) == HEADER_LENGTHS
    assert Counter(_length(b) for b in spacers) == SPACER_LENGTHS
    assert sum(_length(b) for b in spacers) == 429
    for box in spacers:
        dims = sorted(round(box[k + 1] - box[k], 6) for k in (0, 2, 4))
        assert dims[:2] == [0.5, 5.5]
    assert 0.5 * 5.5 * 429 == 1179.75 and 5.5 * 429 == 2359.5
    meta = {
        (m.metadata.profile, m.metadata.material)
        for m in members
        if m.role == "spacer" and m.metadata is not None
    }
    assert meta == {("1/2 plywood", "plywood")}


def test_the_face_plies_keep_their_ids() -> None:
    before = {m.id for m in members_of(b7()) if m.role == "header"}
    after = {m.id for m in members_of(update_all(b7())) if m.role == "header"}
    assert len(before) == 12 and len(after) == 18 and before < after


def test_no_two_framing_members_overlap_and_the_volume_adds_up() -> None:
    """The spacers meet their plies face to face: no box of the walls'
    framing or the spacers overlaps another (the OSB and rafters are checked
    on the kernel, as b7-outline's are). The added volume is the 6 plies
    (8.25 x 214.5 = 1 769.625) and the spacers (1 179.75)."""
    members = members_of(update_all(b7(), WALLS_OPENINGS))
    # The siding's box spans its cased openings, and the notched corner
    # boards' the rafter tails': the kernel probes those exactly.
    skip = {"sheathing", "rafter", "common", "ridge", "subfloor"}
    skip |= {"siding", "corner_board", "casing"}
    roles = tuple({m.role for m in members} - skip)
    assert overlaps(boxes(members, roles)) == []
    old = boxes(members_of(b7()), ("header",))
    new = boxes(members, ("header", "spacer"))

    def volume(items: list[tuple[float, ...]]) -> float:
        return sum((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in items)

    assert volume(new) - volume(old) == pytest.approx(1769.625 + 1179.75, abs=1e-9)
    assert pytest.approx(267801.7538656, abs=1e-7) == VOLUME_IN3


# --- The golden ---------------------------------------------------------------------


def _titles() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for plugin_id in (
        "loft.floor",
        "loft.wall",
        "loft.roof",
        "loft.window",
        "loft.door",
    ):
        latest = REGISTRY.latest(plugin_id)
        for role in latest.manifest.members:
            out[(plugin_id, role.role)] = role.title
    return out


#: The plugins OPENING-UPDATE's golden updates (b7-update-all updates all).
WALLS_OPENINGS = {"loft.wall", "loft.window", "loft.door"}


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B7 from its outline with its walls and openings updated: what the app
    stores and sends to geometry after that one update step."""
    rows = update_all(b7(), WALLS_OPENINGS)
    titles = _titles()
    metadata: list[CutListMember] = []
    for _, env, members in rows:
        if not isinstance(env, CustomFeature):
            continue
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
    return request_of(rows), metadata


def test_the_golden_is_the_updated_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_has_b7s_bodies_and_eighteen_more() -> None:
    """And the walls' exterior finish (SIDING-TRIM): 4 siding layers, 8
    corner boards and 23 casing pieces."""
    _, metadata = golden()
    assert len(metadata) == 217 + 6 + 12 + 4 + 8 + 23


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
