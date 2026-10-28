"""CRAWL-SPACE: ``loft.foundation`` under B7 (RESEARCH §23); 1.1.0 lists
the vents and access door (FOUNDATION-TAKEOFF), 1.0.0 is pinned byte for byte.

Chief Architect and Revit build a crawl space's stem wall on a continuous
footing from the exterior wall loop, the floor framed on top. Checked
against ``docs/reference-parts/buildings.md`` B9, typed by hand:

* the footing X -4..292, Y -4..196 less X 12..276, Y 12..180,
  Z -34.5..-26.5, and the stem on it: X 0..288, Y 0..192 less X 8..280,
  Y 8..184, Z -26.5..0, a pour each;
* grade Z -22.5: the joists' underside (Z 1.5, on B7's 1.5 in sill) less the
  24 in crawl height; the footing's bottom 12 in below it;
* 5 vents 16 x 8 (Z -8..0) at X 24, 144 and 264 on the front and X 24 and
  264 on the back; the 24 x 16 access (Z -16..0) centred on the back;
* two #4 loops of 968 and 888 in; anchor bolts for the floor's sills
  (288, 288, 181, 181): 5 + 5 + 4 + 4 = 18;
* B7's floor, walls, openings and roof are b7-outline's, member for member;
* crawl 24 -> 30 lowers the stem's bottom and the footing 6 in and moves
  nothing above Z 0; 288 -> 336 is one sketch edit and takes 6 vents;
* 1.1.0's stem lists 5 vents 16 x 8 and 1 access door 24 x 16 (6 vents at
  336), and is otherwise 1.0.0's expansion, which
  ``goldens/foundation-v1.0.0-b9-members.json`` pins.

The geometry golden ``b9-crawl-space`` is written from here and pinned by
this module. Regenerate after a deliberate change (a NEW plugin version)
with ``uv run python packages/loft-plugins/tests/test_crawl_space.py``.
"""

import math
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs
from loft_plugins.builtin.crawl_space import (
    crawl_area_in2,
    foundation_spec,
    openings,
    vent_count,
)
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    DatumFeature,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.foundation import anchor_bolt_count, rebar_sticks
from loft_wire.materials import with_member_materials

sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    FLOOR,
    FLOOR_ID,
    GOLDENS,
    IN,
    ROOF,
    SKETCH_ID,
    WALL,
    b7,
    bodies,
    boxes,
    envelope,
    expand,
    members_json,
    members_of,
    overlaps,
    rectangle,
    ref,
)

FOUNDATION = REGISTRY.get("loft.foundation", "1.1.0")
FOUNDATION_V1_0 = REGISTRY.get("loft.foundation", "1.0.0")
#: B9 at 1.0.0, as CRAWL-SPACE released it: model.json's features and these
#: members, byte for byte.
GOLDEN_V1_0 = Path(__file__).parent / "goldens" / "foundation-v1.0.0-b9-members.json"

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000009b9")
FOUNDATION_ID = uuid.UUID("00000000-0000-0000-0000-00000000b905")
GOLDEN = "b9-crawl-space"

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]


def _earlier(rows: Rows) -> dict[uuid.UUID, AuthoredEnvelope]:
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    return earlier


def b9(length: float = 288.0, plugin: Any = FOUNDATION, **raw: Any) -> Rows:
    """B9: B7 as built (b7-outline's rows), then ONE foundation on its
    outline under its floor."""
    rows = b7(length)
    inputs = {"outline": ref(SKETCH_ID), "floor": ref(FLOOR_ID), **raw}
    members = expand(plugin, FOUNDATION_ID, inputs, _earlier(rows))
    rows.append((FOUNDATION_ID, envelope(plugin, inputs), members))
    return rows


def foundation_members(rows: Rows) -> list[ExpandedMember]:
    return next(ms for fid, _, ms in rows if fid == FOUNDATION_ID)


def by_role(members: list[ExpandedMember], role: str) -> list[ExpandedMember]:
    return [m for m in members if m.role == role]


def _loops(members: list[ExpandedMember], cut: ExpandedMember) -> list[Any]:
    """A cut's section: its plan corners (in) and its plane's Z (in)."""
    by_id = {m.id: m.feature for m in members}
    assert isinstance(cut.feature, ExtrudeFeature)
    sketch = by_id[cut.feature.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)
    plane = sketch.params.plane
    z = 0.0
    if not isinstance(plane, DatumPlaneRef):
        datum = by_id[plane.feature_id]
        assert isinstance(datum, DatumFeature)
        z = float(datum.params.offset_mm) / IN  # type: ignore[union-attr]  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType]
    xs = [round(e.start.x / IN, 6) for e in sketch.params.entities]  # type: ignore[union-attr]
    ys = [round(e.start.y / IN, 6) for e in sketch.params.entities]  # type: ignore[union-attr]
    depth = cut.feature.params.distance_mm / IN
    return [min(xs), max(xs), min(ys), max(ys), round(z - depth, 6), round(z, 6)]


def openings_of(members: list[ExpandedMember], role: str) -> list[list[float]]:
    return [_loops(members, m) for m in by_role(members, role)]


# --- The foundation -----------------------------------------------------------------


def test_b9s_footing_and_stem_are_a_pour_each() -> None:
    members = foundation_members(b9())
    assert [m.role for m in members[:6]] == [
        "level",
        "section",
        "footing",
        "section",
        "stem",
        "level",
    ]
    stem, footing = by_role(members, "stem")[0], by_role(members, "footing")[0]
    for pour in (stem, footing):
        assert isinstance(pour.feature, ExtrudeFeature)
        assert pour.feature.params.merge is False  # a body each
        assert pour.metadata is not None and pour.metadata.concrete is not None
    # The stem: X 0..288, Y 0..192, Z -26.5..0; the footing under it.
    assert boxes(members, ("stem",)) == [(0.0, 288.0, 0.0, 192.0, -26.5, 0.0)]
    assert boxes(members, ("footing",)) == [(-4.0, 292.0, -4.0, 196.0, -34.5, -26.5)]


def test_b9s_grade_and_crawl() -> None:
    rows = b9()
    spec = foundation_spec_of(rows)
    assert (spec.top, spec.sill, spec.crawl) == (0.0, 1.5, 24.0)
    assert spec.grade == -22.5
    assert (spec.footing_bottom, spec.footing_top) == (-34.5, -26.5)
    # The crawl: 272 x 176 = 47 872 in^2 (332.4 ft^2) needs 2.22 ft^2 net.
    assert crawl_area_in2(spec) == 272 * 176
    assert pytest.approx(2.2163, abs=1e-4) == 47872 / 144 / 150
    assert vent_count(spec) == 5 == math.ceil(47872 / 150 / 72)


def foundation_spec_of(rows: Rows, **raw: Any) -> Any:
    from loft_plugins import ExpandInputs

    inputs = {"outline": ref(SKETCH_ID), "floor": ref(FLOOR_ID), **raw}
    earlier = _earlier([r for r in rows if r[0] != FOUNDATION_ID])
    values = canonical_inputs(FOUNDATION.manifest, inputs)
    return foundation_spec(ExpandInputs(FOUNDATION_ID, values, earlier))


def test_b9s_five_vents_and_the_access_are_cut_from_the_stems_top() -> None:
    members = foundation_members(b9())
    # Each tool runs 1 in past the stem's faces and its top.
    assert openings_of(members, "vent") == [
        [16.0, 32.0, -1.0, 9.0, -8.0, 1.0],
        [136.0, 152.0, -1.0, 9.0, -8.0, 1.0],
        [256.0, 272.0, -1.0, 9.0, -8.0, 1.0],
        [256.0, 272.0, 183.0, 193.0, -8.0, 1.0],
        [16.0, 32.0, 183.0, 193.0, -8.0, 1.0],
    ]
    assert openings_of(members, "access") == [[132.0, 156.0, 183.0, 193.0, -16.0, 1.0]]
    stem = by_role(members, "stem")[0]
    for m in [*by_role(members, "vent"), *by_role(members, "access")]:
        assert isinstance(m.feature, ExtrudeFeature)
        assert m.feature.params.operation == "cut"
        assert m.feature.params.cut_bodies == [ref(stem.id)]


def test_b9_lists_its_concrete_two_loops_and_18_bolts() -> None:
    members = foundation_members(b9())
    footing = by_role(members, "footing")[0].metadata
    meta = by_role(members, "stem")[0].metadata
    assert footing is not None and meta is not None
    for pour in (footing, meta):
        assert (pour.profile, pour.material) == ("Ready-mix concrete", "concrete")
        assert pour.concrete is not None and pour.concrete.waste_percent == 5
    # The footing carries its bars, the stem the bolts cast into it.
    assert meta.rebar is None and footing.anchor_bolts is None
    assert footing.rebar is not None
    loops = [(round(r.length_mm / IN, 9), r.closed) for r in footing.rebar]
    assert loops == [(968.0, True), (888.0, True)]
    assert sum(rebar_sticks(length, True) for length, _ in loops) == 10
    assert meta.anchor_bolts is not None
    assert meta.anchor_bolts.plates_mm is not None
    sills = [round(mm / IN, 9) for mm in meta.anchor_bolts.plates_mm]
    assert sills == [288.0, 288.0, 181.0, 181.0]  # the floor's
    assert [anchor_bolt_count(s) for s in sills] == [5, 5, 4, 4]
    assert meta.anchor_bolts.count(0.0) == 18


def test_b7_above_it_is_b7_member_for_member() -> None:
    rows = b9()
    above = [m for fid, _, ms in rows if fid != FOUNDATION_ID for m in ms]
    assert bodies(above) == bodies(members_of(b7()))


def test_nothing_overlaps_and_the_sills_sit_on_the_stem() -> None:
    rows = b9()
    framing = [m for m in members_of(rows) if m.role not in ("rafter", "ridge")]
    # The stem's and footing's boxes enclose the crawl, so probe the floor's
    # sills against the stem's ring by hand; the geometry golden probes solids.
    items = boxes([m for m in framing if m.role not in ("stem", "footing")])
    assert overlaps(items) == []
    floor = next(ms for fid, _, ms in rows if fid == FLOOR_ID)
    sills = boxes(floor, ("sill",))
    assert len(sills) == 4
    assert all(z0 == 0.0 for *_, z0, _ in sills)
    for x0, x1, y0, y1, _, _ in sills:
        # Each 5.5 in sill lies on the 8 in stem, flush with its outside face.
        assert min(x1 - x0, y1 - y0) == 5.5
        on_front_back = y1 <= 8 or y0 >= 184
        on_sides = x1 <= 8 or x0 >= 280
        assert on_front_back or on_sides


def test_a_taller_crawl_lowers_only_the_footing_and_stem() -> None:
    low, high = b9(), b9(crawl_height_mm=30 * IN)
    members = foundation_members(high)
    assert boxes(members, ("stem",)) == [(0.0, 288.0, 0.0, 192.0, -32.5, 0.0)]
    assert boxes(members, ("footing",)) == [(-4.0, 292.0, -4.0, 196.0, -40.5, -32.5)]
    assert openings_of(members, "vent") == openings_of(foundation_members(low), "vent")
    rest = [r for r in high if r[0] != FOUNDATION_ID]
    assert bodies(members_of(rest)) == bodies(members_of(b7()))


def test_the_length_edit_takes_six_vents() -> None:
    rows = b9(336)
    members = foundation_members(rows)
    assert boxes(members, ("stem",)) == [(0.0, 336.0, 0.0, 192.0, -26.5, 0.0)]
    # 320 x 176 = 391.1 ft^2: ceil(375.5 / 72) = 6. The sixth goes on the
    # longest line without the access after the front: the sides tie at 192
    # and left ranks before right.
    assert len(by_role(members, "vent")) == 6
    assert openings_of(members, "vent") == [
        [16.0, 32.0, -1.0, 9.0, -8.0, 1.0],
        [160.0, 176.0, -1.0, 9.0, -8.0, 1.0],
        [304.0, 320.0, -1.0, 9.0, -8.0, 1.0],
        [304.0, 320.0, 183.0, 193.0, -8.0, 1.0],
        [16.0, 32.0, 183.0, 193.0, -8.0, 1.0],
        [-1.0, 9.0, 88.0, 104.0, -8.0, 1.0],
    ]
    assert openings_of(members, "access") == [[156.0, 180.0, 183.0, 193.0, -16.0, 1.0]]
    meta = by_role(members, "stem")[0].metadata
    assert meta is not None and meta.anchor_bolts is not None
    assert meta.anchor_bolts.count(0.0) == 6 + 6 + 4 + 4
    assert [(o.item, o.quantity) for o in meta.foundation_openings or ()] == [
        ("foundation_vent", 6),
        ("crawl_access_door", 1),
    ]


def test_b9s_stem_lists_5_vents_and_1_access_door() -> None:
    meta = by_role(foundation_members(b9()), "stem")[0].metadata
    assert meta is not None and meta.foundation_openings is not None
    assert [
        (o.item, round(o.width_mm / IN, 9), round(o.height_mm / IN, 9), o.quantity)
        for o in meta.foundation_openings
    ] == [("foundation_vent", 16.0, 8.0, 5), ("crawl_access_door", 24.0, 16.0, 1)]
    # A typed vent size is listed as cut.
    wide = by_role(foundation_members(b9(vent_width_mm=14 * IN)), "stem")[0]
    assert wide.metadata is not None and wide.metadata.foundation_openings
    assert wide.metadata.foundation_openings[0].size == "14 x 8"


def test_1_1_0_is_1_0_0_but_the_listed_openings() -> None:
    new, old = (foundation_members(b9(plugin=p)) for p in (FOUNDATION, FOUNDATION_V1_0))
    assert [(m.id, m.role, m.feature) for m in new] == [
        (m.id, m.role, m.feature) for m in old
    ]
    for a, b in zip(new, old, strict=True):
        if a.metadata is None or b.metadata is None:
            assert a.metadata is b.metadata
            continue
        assert a.metadata.model_copy(update={"foundation_openings": None}) == b.metadata
    assert all(
        m.metadata is None or m.metadata.foundation_openings is None for m in old
    )


def test_with_no_floor_the_top_is_z0_over_a_15_in_sill() -> None:
    sketch = rectangle(288, 192)
    raw = {"outline": ref(SKETCH_ID)}
    members = expand(FOUNDATION, FOUNDATION_ID, raw, {SKETCH_ID: sketch})
    assert boxes(members, ("stem",)) == [(0.0, 288.0, 0.0, 192.0, -26.5, 0.0)]
    meta = by_role(members, "stem")[0].metadata
    assert meta is not None and meta.anchor_bolts is not None
    plates = meta.anchor_bolts.plates_mm or []
    assert [round(mm / IN, 9) for mm in plates] == [288.0, 192.0, 288.0, 192.0]


def test_a_typed_rectangle_builds_too() -> None:
    members = expand(FOUNDATION, FOUNDATION_ID, {}, {})
    assert boxes(members, ("stem",)) == [(0.0, 144.0, 0.0, 120.0, -26.5, 0.0)]
    # 128 x 104 = 92.4 ft^2 needs 0.62 ft^2: the four corners' vents do.
    assert len(by_role(members, "vent")) == 4


def test_the_floor_must_fill_the_same_outline() -> None:
    earlier = _earlier(b7())
    other = uuid.UUID("00000000-0000-0000-0000-00000000b906")
    earlier[other] = rectangle(240, 192)
    with pytest.raises(PluginError, match="same outline") as error:
        expand(
            FOUNDATION,
            FOUNDATION_ID,
            {"outline": ref(other), "floor": ref(FLOOR_ID)},
            earlier,
        )
    assert error.value.input == "floor"


def test_an_access_below_grade_is_refused() -> None:
    with pytest.raises(PluginError, match="below grade") as error:
        expand(FOUNDATION, FOUNDATION_ID, {"crawl_height_mm": 14 * IN}, {})
    assert error.value.input == "access_height_mm"
    # 17.5 in leaves the 16 in access's bottom on grade: it builds.
    expand(FOUNDATION, FOUNDATION_ID, {"crawl_height_mm": 17.5 * IN}, {})


def test_a_footing_narrower_than_the_stem_is_refused() -> None:
    with pytest.raises(PluginError, match="narrower") as error:
        expand(
            FOUNDATION,
            FOUNDATION_ID,
            {"footing_width_mm": 8 * IN, "stem_thickness_mm": 10 * IN},
            {},
        )
    assert error.value.input == "footing_width_mm"


def test_vents_that_overlap_the_access_are_refused() -> None:
    with pytest.raises(PluginError, match="overlap"):
        expand(
            FOUNDATION,
            FOUNDATION_ID,
            {"width_mm": 72 * IN, "depth_mm": 72 * IN, "access_width_mm": 48 * IN},
            {},
        )


def test_an_l_vents_every_corner() -> None:
    from test_building_outline import l_sketch

    members = expand(
        FOUNDATION, FOUNDATION_ID, {"outline": ref(SKETCH_ID)}, {SKETCH_ID: l_sketch()}
    )
    # Six corners; 224 x 104 + 128 x 72 = 32 512 in^2 needs only 3.01 vents.
    assert len(by_role(members, "vent")) == 6
    spec = foundation_spec_of_l()
    assert crawl_area_in2(spec) == 224 * 104 + 128 * 72
    vents, access = openings(spec)
    assert len(vents) == 6
    assert access.line.facing == "back"
    assert (access.line.length, access.at) == (144.0, 72.0)  # the longer back


def foundation_spec_of_l() -> Any:
    from loft_plugins import ExpandInputs
    from test_building_outline import l_sketch

    values = canonical_inputs(FOUNDATION.manifest, {"outline": ref(SKETCH_ID)})
    return foundation_spec(ExpandInputs(FOUNDATION_ID, values, {SKETCH_ID: l_sketch()}))


def test_the_defaults_are_the_founders() -> None:
    stored = canonical_inputs(FOUNDATION.manifest, {})
    assert stored["crawl_height_mm"] == pytest.approx(24 * IN)
    assert stored["stem_thickness_mm"] == pytest.approx(8 * IN)
    assert stored["footing_width_mm"] == pytest.approx(16 * IN)
    assert stored["footing_thickness_mm"] == pytest.approx(8 * IN)
    assert stored["footing_depth_mm"] == pytest.approx(12 * IN)
    assert stored["access_width_mm"] == pytest.approx(24 * IN)
    assert stored["access_height_mm"] == pytest.approx(16 * IN)
    assert (stored["waste_percent"], stored["access_wall"]) == (5, "back")


# --- The golden ---------------------------------------------------------------------

PLUGINS = (WALL, FLOOR, ROOF, FOUNDATION)
TITLES = {role.role: role.title for p in PLUGINS for role in p.manifest.members}
OWNERS = {role.role: p.manifest.id for p in PLUGINS for role in p.manifest.members}


def request_of(rows: Rows) -> EvaluateTreeRequest:
    features: list[EvaluatedFeatureInput] = []
    for fid, env, members in rows:
        if isinstance(env, SketchFeature):
            features.append(EvaluatedFeatureInput(id=fid, feature=env))
        features += [EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members]
    expansion = members_of(rows)
    return EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=features,
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in expansion if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )


def metadata_of(rows: Rows) -> list[CutListMember]:
    out: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        for m in members:
            if m.metadata is None:
                continue
            out.append(
                CutListMember(
                    feature_id=m.id,
                    role=m.role,
                    title=TITLES.get(m.role, m.role),
                    plugin_id=plugin_id or OWNERS.get(m.role),
                    metadata=m.metadata,
                )
            )
    return out


def test_1_0_0_is_byte_for_byte_as_released() -> None:
    rows = b9(plugin=FOUNDATION_V1_0)
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request_of(rows).model_dump_json(
        indent=2
    ) + "\n"
    assert GOLDEN_V1_0.read_text() == members_json(metadata_of(rows))


def test_the_golden_is_the_plugins_expansion() -> None:
    rows = b9()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request_of(rows).model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata_of(rows))


if __name__ == "__main__":
    built = b9()
    request = request_of(built)
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata_of(built)))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
