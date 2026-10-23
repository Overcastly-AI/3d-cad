"""ROOF-HIP-SHEATHING-NOTCH and ROOF-THROUGH-SHEATHING-UPDATE: roof 1.5.0
notches every tail out of the sheathing of the walls it bears on.

Checked against hand numbers (docs/reference-parts/buildings.md B2 and B3):

* the exact overlap (:mod:`loft_plugins.builtin.roof_sheathing`) of B3's hip
  with B2's OSB is 22 rafter tails x 1.5 x k (seat s + s^2 / 2) plus, at each
  corner, the hip's ripped tail over both walls' sheathing:
  2 sqrt 2 a s heel - k s a^2 + sqrt 2 k a s^2 (a the hip's half thickness,
  s the OSB's, k the pitch); B7's typed gable's is the round's 43.1006 in^3
  over 36 pairs;
* 1.5.0 on an outline: a hip notches every common, jack and hip from
  exactly the panels it overlaps (26 cuts, 30 panels), and is 1.3.0's hip
  member for member besides; a gable is 1.4.0's exactly; a roof on its
  typed bearing is 1.3.0's exactly;
* 1.5.0 on picked line walls (1.2.0, sheathed): the hip is notched the
  same way, the stored 1.3.0 roof's overlap is the warning's.

The geometry golden ``b3-outline-hip-sheathed`` is written from here and
pinned by this module; ``services/geometry/tests/test_roof_hip_sheathing.py``
checks it on the kernel against an independent script. Regenerate after a
deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_roof_sheathing.py``.
"""

import json
import math
import sys
import uuid
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError
from loft_plugins.builtin.roof_sheathing import (
    RoofMember,
    pairs,
    roof_bodies,
    through_sheathing,
    wall_panels,
)
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    ExpandedMember,
    ExtrudeFeature,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_building_outline as tb

ROOT = Path(__file__).resolve().parents[3]
GOLDENS = ROOT / "services" / "geometry" / "goldens"
GOLDEN = "b3-outline-hip-sheathed"

ROOF_1_3 = REGISTRY.get("loft.roof", "1.3.0")
ROOF_1_4 = REGISTRY.get("loft.roof", "1.4.0")
ROOF_1_5 = REGISTRY.get("loft.roof", "1.5.0")
WALL_1_2 = REGISTRY.get("loft.wall", "1.2.0")

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]

# --- Hand numbers (B3 on B2's sheathed walls) ----------------------------------------

K = Fraction(1, 2)  # 6/12
SEAT = Fraction(7, 2)  # the 2x4 plate: 3.5 (2x6 heel limit 5.5/3/0.5 = 11/3 more)
HEEL = SEAT * K  # 1.75
S = Fraction(7, 16)  # 7/16 OSB
T = Fraction(3, 2)
A = T / 2  # the hip's half thickness

#: One rafter tail through the OSB: t x the profile's area over -s..0,
#: below the plate's top (z = plate - (seat - d) k there).
TAIL = T * K * (SEAT * S + S * S / 2)
#: One corner hip's ripped tail through both walls' OSB: over the hip's
#: width |q| <= a, the band u in [|q| - s sqrt 2, |q|] along it, under the
#: plate by heel - k u / sqrt 2.
CORNER = (
    2 * math.sqrt(2) * float(A * S * HEEL)
    - float(K * S * A * A)
    + math.sqrt(2) * float(K * A * S * S)
)
NOTCHES = 22 * float(TAIL) + 4 * CORNER


def hip_house(walls: dict[str, Any], roof: Any = ROOF_1_5) -> Rows:
    """B2's outline (144 x 120, 2x4 at 16 in, 97.125 to the plate) with the
    walls' options, and B3's hip (6/12, 2x6 at 24 in, 2x8 ridge and hips,
    12 in overhang: every default) on it."""
    saved = tb.ROOF
    tb.ROOF = roof
    try:
        return tb.house(tb.rectangle(144, 120), [], walls, None, {"style": "hip"})
    finally:
        tb.ROOF = saved


def roof_of(rows: Rows) -> list[ExpandedMember]:
    return next(ms for fid, _, ms in rows if fid == tb.ROOF_ID)


def earlier_of(rows: Rows, before: uuid.UUID) -> dict[uuid.UUID, AuthoredEnvelope]:
    out: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, ms in rows:
        if fid == before:
            break
        out[fid] = env
        for m in ms:
            out[m.id] = m.feature
    return out


def notches_of(members: list[ExpandedMember]) -> list[ExpandedMember]:
    return [m for m in members if m.name is not None and m.name.startswith("tail/")]


# --- The overlap --------------------------------------------------------------------


def test_the_hand_numbers() -> None:
    # 1.5 x 1/2 x (3.5 x 7/16 + 49/512) = 1.22021484375 in^3 a tail.
    assert float(TAIL) == 1.22021484375
    assert pytest.approx(1.60259750604, abs=1e-10) == CORNER
    assert pytest.approx(33.25511658666, abs=1e-10) == NOTCHES


def test_the_overlap_of_b3s_hip_with_b2s_osb_is_the_hand_figure() -> None:
    rows = hip_house(tb.OSB, ROOF_1_3)
    earlier = earlier_of(rows, tb.ROOF_ID)
    roof = roof_of(rows)
    bodies = roof_bodies(
        [RoofMember(m.id, m.role, m.name, m.feature) for m in roof], earlier
    )
    found = pairs(bodies, wall_panels([tb.WALLS_ID], earlier))
    by_role: Counter[str] = Counter()
    volume: dict[str, float] = {}
    for p in found:
        by_role[p.body.role] += 1
        volume[p.body.role] = volume.get(p.body.role, 0.0) + p.overlap.volume
    # Every common (4 ridge-end, 2 kings) and jack (16) crosses one panel;
    # each hip crosses the through wall's panel and the fitted wall's rip.
    assert by_role == Counter({"common": 6, "jack": 16, "hip": 8})
    assert volume["common"] == pytest.approx(6 * float(TAIL), abs=1e-9)
    assert volume["jack"] == pytest.approx(16 * float(TAIL), abs=1e-9)
    assert volume["hip"] == pytest.approx(4 * CORNER, abs=1e-9)
    warned = through_sheathing(roof, earlier)
    assert warned.pairs == 30
    assert warned.volume == pytest.approx(NOTCHES, abs=1e-9)
    assert not warned.approximate


def test_b7s_typed_gable_shares_the_rounds_43_in3_over_36_pairs() -> None:
    """The QA-B7 round's typed house: roof 1.3.0 on four 1.2.0 walls."""
    members = tb.round_b7()
    roof = [m for m in members if m.role in ("plane", "section", "rafter", "ridge")]
    walls = [m for m in members if m not in roof]
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {m.id: m.feature for m in walls}
    for side, raw in tb.ROUND_WALLS:
        fid = uuid.uuid5(tb.WALLS_ID, side)
        earlier[fid] = tb.envelope(
            WALL_1_2,
            {**raw, "elevation_mm": tb.SUBFLOOR_TOP * tb.IN, **tb.B7_STUDS},
        )
    # The floor's members came first; only the walls' sheathing counts.
    found = through_sheathing(roof, earlier)
    assert found.pairs == 36
    assert found.volume == pytest.approx(43.1005859375, abs=1e-9)


def test_an_outline_gable_at_1_4_has_nothing_left_to_warn() -> None:
    rows = tb.b7()
    found = through_sheathing(roof_of(rows), earlier_of(rows, tb.ROOF_ID))
    assert (found.volume, found.pairs) == (0.0, 0)


# --- 1.5.0 --------------------------------------------------------------------------


def test_a_hip_on_sheathed_outline_walls_notches_every_tail() -> None:
    """26 cuts: 6 commons and 16 jacks from their eave wall's panel, the 4
    hips from the through wall's panel and the fitted wall's corner rip;
    otherwise 1.3.0's hip member for member."""
    rows = hip_house(tb.OSB)
    roof = roof_of(rows)
    cuts = notches_of(roof)
    assert len(cuts) == 26
    kinds = Counter(str(m.name).split("/")[1] for m in cuts)
    assert kinds == Counter({"common": 6, "jack": 16, "hip": 4})
    walls = next(ms for fid, _, ms in rows if fid == tb.WALLS_ID)
    panels = {m.id: str(m.name) for m in walls if m.role == "sheathing"}
    hits = 0
    for m in cuts:
        assert isinstance(m.feature, ExtrudeFeature)
        params = m.feature.params
        assert params.operation == "cut"
        scope = params.cut_bodies
        assert isinstance(scope, list)
        hits += len(scope)
        names = sorted(panels[r.feature_id] for r in scope)
        if "/hip/" in str(m.name):
            assert params.extent == "symmetric"
            assert len(names) == 2
            assert any("/corner/" in n for n in names)
        else:
            assert params.extent == "one_side"
            assert len(names) == 1
    assert hits == 30
    typed = roof_of(hip_house(tb.OSB, ROOF_1_3))
    assert [m for m in roof if m not in cuts] == typed


def test_the_notches_leave_nothing_to_warn() -> None:
    rows = hip_house(tb.OSB)
    found = through_sheathing(roof_of(rows), earlier_of(rows, tb.ROOF_ID))
    assert (found.volume, found.pairs) == (0.0, 0)


def test_unsheathed_walls_get_no_notch() -> None:
    assert notches_of(roof_of(hip_house({}))) == []


def test_a_gable_on_an_outline_is_1_4_0s_exactly() -> None:
    raw = {"slope_walls": ["e1", "e3"], **tb.B7_ROOF}
    saved = tb.ROOF
    try:
        tb.ROOF = ROOF_1_5
        v15 = roof_of(tb.b7(roof=raw))
        tb.ROOF = ROOF_1_4
        v14 = roof_of(tb.b7(roof=raw))
    finally:
        tb.ROOF = saved
    assert v15 == v14
    assert len(notches_of(v15)) == 26


def test_a_typed_roof_is_1_3_0s_exactly() -> None:
    for style in ("gable", "hip"):
        raw = {"style": style, **tb.B2_ROOF_TYPED}
        assert tb.expand(ROOF_1_5, tb.ROOF_ID, raw, {}) == tb.expand(
            ROOF_1_3, tb.ROOF_ID, raw, {}
        )


def test_a_small_overhang_inside_the_osb_is_refused_on_a_hip() -> None:
    """A 1/4 in overhang ends the hip's tail inside the 7/16 OSB, where its
    double cheeks cut it: the cut would not be the hip there."""
    saved = tb.ROOF
    tb.ROOF = ROOF_1_5
    try:
        with pytest.raises(PluginError, match="later rung"):
            tb.house(
                tb.rectangle(144, 120),
                [],
                tb.OSB,
                None,
                {"style": "hip", "overhang_mm": 0.25 * tb.IN},
            )
    finally:
        tb.ROOF = saved


def line_walls_hip(roof: Any) -> Rows:
    """B2's four walls typed as 1.2.0 line walls with OSB (b5-shed's,
    on the ground), and B3's hip picking them."""
    rows: Rows = []
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    ids: list[uuid.UUID] = []
    for side, raw in B2_WALLS:
        fid = uuid.uuid5(tb.WALLS_ID, side)
        full = {**raw, **tb.OSB}
        members = tb.expand(WALL_1_2, fid, full, dict(earlier))
        env = tb.envelope(WALL_1_2, full)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        rows.append((fid, env, members))
        ids.append(fid)
    raw_roof = {"style": "hip", "walls": [tb.ref(i) for i in ids]}
    members = tb.expand(roof, tb.ROOF_ID, raw_roof, dict(earlier))
    rows.append((tb.ROOF_ID, tb.envelope(roof, raw_roof), members))
    return rows


#: buildings.md B2 as the QA-B7 round types walls (framing on the right):
#: front and back run through, the sides fit between.
B2_WALLS: list[tuple[str, dict[str, Any]]] = [
    (
        "front",
        {"start_x_mm": 144 * tb.IN, "direction_deg": 180.0, "length_mm": 144 * tb.IN},
    ),
    (
        "left",
        {"start_y_mm": 3.5 * tb.IN, "direction_deg": 90.0, "length_mm": 113 * tb.IN},
    ),
    ("back", {"start_y_mm": 120 * tb.IN, "length_mm": 144 * tb.IN}),
    (
        "right",
        {
            "start_x_mm": 144 * tb.IN,
            "start_y_mm": 116.5 * tb.IN,
            "direction_deg": 270.0,
            "length_mm": 113 * tb.IN,
        },
    ),
]


def test_a_hip_on_picked_line_walls_is_notched_at_1_5_0() -> None:
    """The ROOF-THROUGH-SHEATHING-UPDATE path: a stored 1.3.0 hip on four
    sheathed line walls shares the hand figure with their OSB; the same
    inputs at 1.5.0 notch it all, and are 1.3.0's members besides."""
    old = line_walls_hip(ROOF_1_3)
    earlier = earlier_of(old, tb.ROOF_ID)
    found = through_sheathing(roof_of(old), earlier)
    assert found.pairs == 30
    assert found.volume == pytest.approx(NOTCHES, abs=1e-9)
    new = line_walls_hip(ROOF_1_5)
    roof = roof_of(new)
    cuts = notches_of(roof)
    assert len(cuts) == 26
    assert [m for m in roof if m not in cuts] == roof_of(old)
    after = through_sheathing(roof, earlier_of(new, tb.ROOF_ID))
    assert (after.volume, after.pairs) == (0.0, 0)


def test_an_l_hip_on_sheathed_outline_walls_frames_or_is_refused_whole() -> None:
    """On an L the valley cheek-cuts jacks near the inside corner: where a
    cut would meet a cheek inside the OSB the roof is refused (a later rung),
    otherwise every tail is notched and nothing is left to warn."""
    saved = tb.ROOF
    tb.ROOF = ROOF_1_5
    try:
        rows = tb.house(tb.l_sketch(), [], tb.OSB, None, {"style": "hip"})
    except PluginError as exc:
        assert "later rung" in exc.message
        return
    finally:
        tb.ROOF = saved
    found = through_sheathing(roof_of(rows), earlier_of(rows, tb.ROOF_ID))
    assert (found.volume, found.pairs) == (0.0, 0)
    assert notches_of(roof_of(rows))


# --- The golden ---------------------------------------------------------------------


def golden() -> tuple[Any, list[CutListMember]]:
    rows = hip_house(tb.OSB)
    titles = {
        role.role: role.title
        for plugin in (tb.WALL, ROOF_1_5)
        for role in plugin.manifest.members
    }
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in tb.members_of(rows)
        if m.metadata is not None
    ]
    return tb.request_of(rows), metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    assert (GOLDENS / GOLDEN / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (GOLDENS / GOLDEN / "members.json").read_text() == _members_json(metadata)


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(_members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
