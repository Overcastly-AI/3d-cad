"""CEILING-JOISTS: ``loft.roof`` 1.6.0 ties each inner common pair of a gable
with a ceiling joist on the plates (IRC R802.5.2, Chief Architect's Build
Framing).

Checked against ``docs/reference-parts/buildings.md`` B7, typed by hand:

* B7 on its outline at 6/12 (2x8 rafters at 24 in o.c., plates topped at
  Z 108.59375, 5.5 deep): 11 joists 2x8, X c + 0.75 .. c + 2.25 for c = 24,
  48, ..., 264, Y 0..192, each end snipped delta = 29/3 - 7.25 sqrt(1.25) =
  1.560920 down and 2 delta along, 2 088 - 3 delta^2 = 2 080.690584 in^3 a
  joist, 22 887.596423 in^3 for the 11;
* 24 -> 28 ft frames 13; 6/12 -> 8/12 re-snips them (delta 29/3 - 7.25
  sqrt(13) / 3, 1.5 delta along);
* Ceiling joists None, a hip and a typed bearing are 1.5.0 member for
  member, so a stored 1.5.0 roof is unchanged; every released version
  expands as before (their own tests and goldens);
* along Y the joist is on the rafter's +Y face; a layout common with no room
  before the end rafter takes its joist on its near face; a gable whose
  joist would reach the ridge board builds without joists and warns why;
* an update to 1.7.0 takes Ceiling joists' default, Beside each common
  (PLUGIN-UPDATE-ALL, reversing 0d22c34): B7's gable gains its 11 joists,
  and a gable whose joist cannot fit updates without them and warns;
* no joist's box meets another body's, in B7, at 28 ft and in B10 under the
  partitions (the geometry test probes every pair exactly).

The geometry golden ``b7-ceiling-joists`` and the kernel fixture
``ceiling-joist-cases.json.gz`` are written from here and pinned by this
module. Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_ceiling_joists.py``.
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
from loft_plugins import (
    REGISTRY,
    ExpandInputs,
    canonical_inputs,
    update_for,
    updated_inputs,
)
from loft_plugins.builtin.roof_outline import ceiling_joist_note
from loft_wire.cut_list import ONE_PIECE_ROLES, CutListMember
from loft_wire.features import AuthoredEnvelope, EvaluateTreeRequest, ExpandedMember
from loft_wire.plugins import ChoiceInput

# test_building_outline's and test_interior_walls' trees and body probes.
# pytest runs in importlib mode, which puts no test directory on sys.path.
sys.path.insert(0, str(Path(__file__).parent))
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
    envelope,
    expand,
    house,
    members_json,
    members_of,
    rectangle,
    ref,
    request_of,
)
from test_interior_walls import b10, titles

ROOF_1_5 = REGISTRY.get("loft.roof", "1.5.0")
ROOF_1_6 = REGISTRY.get("loft.roof", "1.6.0")
GOLDEN = "b7-ceiling-joists"
CASES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "ceiling-joist-cases.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000c0157")

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]
B7_GABLE = {"slope_walls": ["e1", "e3"], **B7_ROOF}

# --- B7's joists, typed from buildings.md -----------------------------------------

PLATE = 1.5 + 9.25 + 23 / 32 + 97.125  # 108.59375
DEPTH = 7.25  # 2x8


def delta(rise: int) -> float:
    """The snip's depth at the wall's outside face: the joist's top less the
    rafters' top plane there, plate - heel + plumb depth (the heel is held to
    a third of the rafter's depth, 29/12, at 6/12 and 8/12)."""
    return PLATE + DEPTH - (PLATE - DEPTH / 3 + DEPTH * math.hypot(12, rise) / 12)


def typed_joist(c: float, rise: int = 6) -> set[tuple[float, float, float]]:
    """The joist beside the common at *c*: its 12 corners (in)."""
    d = delta(rise)
    run = d / (rise / 12)
    top = PLATE + DEPTH
    side = [
        (0.0, PLATE),
        (192.0, PLATE),
        (192.0, top - d),
        (192.0 - run, top),
        (run, top),
        (0.0, top - d),
    ]
    return {
        (round(x, 6) + 0.0, round(y, 6) + 0.0, round(z, 6) + 0.0)
        for x in (c + 0.75, c + 2.25)
        for y, z in side
    }


def roofed(rows: Rows, raw: dict[str, Any], plugin: Any = ROOF_1_6) -> Rows:
    """*rows* with a roof on their walls appended, as documents builds it."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    full = {"walls": [ref(WALLS_ID)], **raw}
    members = expand(plugin, ROOF_ID, full, earlier)
    return [*rows, (ROOF_ID, envelope(plugin, full), members)]


def b7_roofed(
    length: float = 288.0, raw: dict[str, Any] | None = None, plugin: Any = ROOF_1_6
) -> Rows:
    rows = house(rectangle(length, 192), b7_openings(length), B7_STUDS, B7_FLOOR, None)
    return roofed(rows, B7_GABLE if raw is None else raw, plugin)


def roof_of(rows: Rows) -> list[ExpandedMember]:
    return next(ms for fid, _, ms in rows if fid == ROOF_ID)


def joists(rows: Rows) -> list[ExpandedMember]:
    return [m for m in roof_of(rows) if m.role == "ceiling_joist"]


def corners(members: list[ExpandedMember]) -> list[set[tuple[float, float, float]]]:
    found = bodies(members, ("ceiling_joist",))
    assert all(n == 1 for n in found.values())
    return sorted((set(pts) for _, _, pts in found), key=min)


# --- B7 ---------------------------------------------------------------------------


def test_b7_frames_eleven_joists_beside_the_inner_commons() -> None:
    rows = b7_roofed()
    members = members_of(rows)
    assert len(joists(rows)) == 11
    assert corners(members) == [typed_joist(c) for c in range(24, 265, 24)]
    for m in joists(rows):
        assert m.metadata is not None
        assert (m.metadata.profile, m.metadata.material) == ("2x8", "spf_lumber")
    assert [m.name for m in joists(rows)] == [f"slot/{n}" for n in range(1, 12)]


def test_the_snip_is_the_rafters_top_plane_at_the_wall() -> None:
    """At the wall's outside face the rafters' top is the heel's foot
    106.1770833 plus the plumb depth 7.25 sqrt(1.25): 114.282829. The joist's
    top is 115.84375: delta = 29/3 - 7.25 sqrt(1.25), and the snip runs 2
    delta along at 6/12. Each joist is 1.5 x 7.25 x 192 less two triangles
    of delta x 2 delta / 2, through 1.5: 2 088 - 3 delta^2."""
    d = delta(6)
    heel_foot = PLATE - DEPTH / 3
    assert heel_foot == pytest.approx(106.1770833, abs=1e-7)
    assert heel_foot + 7.25 * math.sqrt(1.25) == pytest.approx(114.282829, abs=1e-6)
    assert d == pytest.approx(29 / 3 - 7.25 * math.sqrt(1.25), abs=1e-12)
    assert d == pytest.approx(1.560920, abs=1e-6)
    volume = 1.5 * 7.25 * 192 - 3 * d * d
    assert volume == pytest.approx(2080.690584, abs=1e-6)
    assert 11 * volume == pytest.approx(22887.596423, abs=1e-6)


def test_28_ft_frames_thirteen() -> None:
    rows = b7_roofed(336)
    assert corners(members_of(rows)) == [typed_joist(c) for c in range(24, 313, 24)]


def test_8_12_re_snips_them() -> None:
    rows = b7_roofed(raw={**B7_GABLE, "pitch": "rise_8"})
    d = delta(8)
    assert d == pytest.approx(29 / 3 - 7.25 * math.sqrt(13) / 3, abs=1e-12)
    assert d == pytest.approx(0.953251, abs=1e-6)
    assert corners(members_of(rows)) == [typed_joist(c, 8) for c in range(24, 265, 24)]


def test_none_a_hip_and_a_typed_bearing_are_1_5_0_member_for_member() -> None:
    """A stored 1.5.0 roof expands as before, and 1.6.0 adds nothing but the
    joists: without them it is 1.5.0's expansion exactly."""
    none = {**B7_GABLE, "ceiling_joists": "none"}
    assert roof_of(b7_roofed(raw=none)) == roof_of(
        b7_roofed(raw=B7_GABLE, plugin=ROOF_1_5)
    )
    hip = house(rectangle(144, 120), [], {}, None, None)
    assert roof_of(roofed(hip, {"style": "hip"})) == roof_of(
        roofed(hip, {"style": "hip"}, ROOF_1_5)
    )
    typed = {"span_mm": 192 * IN, "length_mm": 288 * IN, **B7_ROOF}
    assert expand(ROOF_1_6, ROOF_ID, typed, {}) == expand(ROOF_1_5, ROOF_ID, typed, {})


def test_the_joists_follow_the_released_gable_then_its_notches() -> None:
    """1.6.0's members are 1.5.0's in order, then per joist its datum, its
    section and the joist."""
    old = roof_of(b7_roofed(raw=B7_GABLE, plugin=ROOF_1_5))
    new = roof_of(b7_roofed())
    assert new[: len(old)] == old
    tail = new[len(old) :]
    assert [m.role for m in tail] == ["plane", "section", "ceiling_joist"] * 11
    assert [m.name for m in tail[:3]] == ["yz/24.75", "ceiling_joist/slot/1", "slot/1"]


def test_along_y_the_joist_is_on_the_rafters_plus_y_face() -> None:
    """B2 on its outline turned (left and right defining slope, the ridge
    along Y, 144 long): commons at Y 24 .. 120, joists Y c + 0.75 .. c + 2.25,
    X 0..120."""
    rows = roofed(
        house(rectangle(120, 144), [], {}, None, None), {"slope_walls": ["e2", "e4"]}
    )
    found = boxes(roof_of(rows), ("ceiling_joist",))
    assert sorted(found) == [
        (0.0, 120.0, c + 0.75, c + 2.25, 97.125, 97.125 + 7.25)
        for c in range(24, 121, 24)
    ]


def test_a_common_hard_by_the_end_rafter_takes_its_joist_on_its_near_face() -> None:
    """At 291 the layout common at 288 is 1.5 from the end rafter (289.5..291):
    its joist goes on its -X face, X 285.75..287.25."""
    rows = roofed(house(rectangle(291, 192), [], B7_STUDS, B7_FLOOR, None), B7_GABLE)
    found = sorted(boxes(roof_of(rows), ("ceiling_joist",)))
    assert [(b[0], b[1]) for b in found] == [
        *((c + 0.75, c + 2.25) for c in range(24, 265, 24)),
        (285.75, 287.25),
    ]
    assert overlaps_any(rows) == []


def note_of(rows: Rows, raw: dict[str, Any]) -> str | None:
    """The stored roof's ``ceiling_joists_omitted`` text, as documents reads
    it: the roof's canonical inputs over the features before it."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    full = canonical_inputs(ROOF_1_6.manifest, {"walls": [ref(WALLS_ID)], **raw})
    return ceiling_joist_note(ExpandInputs(ROOF_ID, full, earlier))


#: B7 at 1/12 (the reviewer's case): 2x8 rafters seated 5.5, a 2x10 ridge.
#: The ridge's underside is the plate + (95.25 - 5.5) / 12 + 7.25 sqrt(145)
#: / 12 - 9.25 = the plate + 5.5044, under a 2x8 joist's 7.25 top but over a
#: 2x6's 5.5.
B7_1_12 = {**B7_GABLE, "pitch": "rise_1"}


def test_a_new_gable_whose_joist_cannot_fit_builds_without_it_and_warns() -> None:
    """Chief warns rather than blocks: the 1/12 gable builds, frames no
    ceiling joist, is the None roof member for member, and the warning says
    why and names the deepest joist that fits."""
    rows = house(rectangle(288, 192), b7_openings(), B7_STUDS, B7_FLOOR, None)
    built = roof_of(roofed(rows, B7_1_12))
    assert not any(m.role == "ceiling_joist" for m in built)
    assert built == roof_of(roofed(rows, {**B7_1_12, "ceiling_joists": "none"}))
    note = note_of(rows, B7_1_12)
    assert note is not None
    assert "ridge board" in note and "Z 115.844" in note and "Z 114.098" in note
    assert "2x6 or shallower" in note and "None" in note
    # A 2x6 fits under it, and the warning goes.
    six = {**B7_1_12, "ceiling_joist_profile": "us_2x6"}
    assert len(joists(roofed(rows, six))) == 11
    assert note_of(rows, six) is None
    assert note_of(rows, B7_GABLE) is None
    assert note_of(rows, {**B7_1_12, "ceiling_joists": "none"}) is None


def test_with_no_joist_that_fits_the_warning_asks_for_pitch_or_ridge() -> None:
    """A 48 in span at 1/12 on 2x4 rafters and a 2x6 ridge: the ridge's
    underside is 0.51 below the plates, so no joist passes under it."""
    rows = house(rectangle(96, 48), [], {}, None, None)
    raw = {
        "slope_walls": ["e1", "e3"],
        "pitch": "rise_1",
        "rafter_profile": "us_2x4",
        "ridge_profile": "us_2x6",
        "ceiling_joist_profile": "us_2x4",
    }
    assert joists(roofed(rows, raw)) == []
    note = note_of(rows, raw)
    assert note is not None and "steeper pitch or a deeper ridge board" in note


# --- Updating a stored roof -----------------------------------------------------------


def test_an_update_takes_ceiling_joists_beside_each_common() -> None:
    """An update takes the new release's defaults (PLUGIN-UPDATE-ALL): every
    roof 1.2.0-1.5.0 is offered the newest, 1.7.0 (GABLE-END-STUDS), with
    its inputs as they are, so Ceiling joists is its default, Beside each
    common, and the summary says it ties a gable with them."""
    newest = REGISTRY.get("loft.roof", "1.7.0")
    for version in ("1.2.0", "1.3.0", "1.4.0", "1.5.0"):
        update = update_for("loft.roof", version, REGISTRY)
        assert update is not None and update.to_version == "1.7.0", version
        assert "ceiling joist" in update.summary.lower()
        stored = {"style": "gable", "pitch": "rise_6"}
        assert updated_inputs(update, stored) == stored
        moved = canonical_inputs(newest.manifest, updated_inputs(update, stored))
        assert moved["ceiling_joists"] == "beside_common"


def test_an_updated_gable_gains_its_joists_and_one_that_cannot_fit_warns() -> None:
    """B7's gable stored at 1.4.0: updated by the map at 6/12 it is 1.7.0's
    new roof exactly, 1.5.0's members then 11 joists (then its gable ends,
    GABLE-END-STUDS); at 1/12 (a 2x8 joist
    would pass its 2x10 ridge) the update still succeeds, builds 1.5.0's
    roof with no joist and warns why, never a refusal."""
    rows = house(rectangle(288, 192), b7_openings(), B7_STUDS, B7_FLOOR, None)
    old = REGISTRY.get("loft.roof", "1.4.0")
    update = update_for("loft.roof", "1.4.0", REGISTRY)
    assert update is not None
    for raw, joists_built in ((B7_GABLE, 11), (B7_1_12, 0)):
        stored = canonical_inputs(old.manifest, {"walls": [ref(WALLS_ID)], **raw})
        newest = REGISTRY.get("loft.roof", "1.7.0")
        moved = canonical_inputs(newest.manifest, updated_inputs(update, stored))
        after = roof_of(roofed(rows, moved, newest))
        before = roof_of(roofed(rows, dict(stored), ROOF_1_5))
        assert after[: len(before)] == before
        assert sum(m.role == "ceiling_joist" for m in after) == joists_built
        assert after == roof_of(roofed(rows, raw, newest))
    assert note_of(rows, B7_1_12) is not None
    assert note_of(rows, B7_GABLE) is None


# --- No overlaps --------------------------------------------------------------------


def overlaps_any(rows: Rows) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    """Each joist's box against every other body's (a rafter's box is its
    box, and the joist is beside it, so boxes suffice here; the geometry
    test probes every pair exactly)."""
    members = members_of(rows)
    mine = boxes(members, ("ceiling_joist",))
    roles = tuple({m.role for m in members} - {"ceiling_joist"})
    others = boxes(members, roles) + mine
    return [
        (a, b)
        for a in mine
        for b in others
        if a is not b
        and all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-6 for k in (0, 2, 4))
    ]


def b10_roofed(length: float = 288.0) -> Rows:
    return roofed(b10(length, roof=False), B7_GABLE)


@pytest.mark.parametrize("case", ["b7", "b7-336", "b10", "b10-336"])
def test_no_joist_box_meets_another_body(case: str) -> None:
    rows = {
        "b7": b7_roofed,
        "b7-336": lambda: b7_roofed(336),
        "b10": b10_roofed,
        "b10-336": lambda: b10_roofed(336),
    }[case]()
    assert joists(rows)
    assert overlaps_any(rows) == []


# --- The manifest ---------------------------------------------------------------------


def test_1_6_0_defaults_to_joists_beside_each_common() -> None:
    # New roofs are 1.7.0 (GABLE-END-STUDS), which keeps these inputs.
    inputs = {i.name: i for i in ROOF_1_6.manifest.inputs}
    choice = inputs["ceiling_joists"]
    assert isinstance(choice, ChoiceInput)
    assert choice.default == "beside_common"
    assert [o.label for o in choice.options] == ["Beside each common", "None"]
    size = inputs["ceiling_joist_profile"]
    assert isinstance(size, ChoiceInput) and size.default == "us_2x8"
    assert inputs["ceiling_joist_material"].default == "spf_lumber"  # type: ignore[union-attr]
    old = [i.name for i in ROOF_1_5.manifest.inputs]
    assert [n for n in inputs if n not in old] == [
        "ceiling_joists",
        "ceiling_joist_profile",
        "ceiling_joist_material",
    ]
    roles = {r.role: r.title for r in ROOF_1_6.manifest.members}
    assert roles["ceiling_joist"] == "Ceiling joist"
    # One piece of stock, never spliced (NO-SPLICE-SPANS).
    assert "ceiling_joist" in ONE_PIECE_ROLES


# --- The golden and the kernel's cases ------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    names = {
        **titles(),
        **{("loft.roof", r.role): r.title for r in ROOF_1_6.manifest.members},
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
    """b7-outline's tree with its roof at 1.6.0, every default kept."""
    rows = b7_roofed()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def cases() -> str:
    """B7 at 28 ft and at 8/12, and B10 under the joists; each with its body
    count and its joists' count."""
    built = {
        "b7-336": b7_roofed(336),
        "b7-8-12": b7_roofed(raw={**B7_GABLE, "pitch": "rise_8"}),
        "b10": b10_roofed(),
    }
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            "joists": len(joists(rows)),
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


def test_the_golden_is_b7_outline_with_the_joists() -> None:
    """The same tree as b7-outline but the roof's pin: 217 bodies plus 11."""
    _, metadata = golden()
    assert len(metadata) == 228
    assert Counter(m.title for m in metadata)["Ceiling joist"] == 11


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
