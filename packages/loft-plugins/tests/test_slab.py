"""SLAB: ``loft.slab`` 1.0.0 and ``loft.wall`` 1.4.0 on it (RESEARCH §23).

Chief Architect and Revit build a slab on grade from the exterior wall loop;
the walls stand on its top and their bottom plates are bolted to it.
Checked against ``docs/reference-parts/buildings.md`` B8 and B2, typed by
hand:

* B8's slab on B7's outline is X 0..288, Y 0..192, Z -4..0 with a 12 in edge
  ring Z -12..-4 merged into it (one pour), its two #4 loops 912 in each;
* B2's plain slab is a typed 144 x 120 x 4 with the edge off, no rebar;
* ``loft.wall`` 1.4.0 on the slab is 1.3.0's outline walls on B7's floor,
  member for member, lowered by the subfloor's top (11.46875) to Z 0, and
  only its bottom plates change: each lists its anchor bolts; with no slab
  it is 1.3.0's wall exactly;
* the roof on those walls is B7's roof lowered the same;
* 288 -> 336 is one sketch-dimension edit: the slab and the walls follow.

The geometry goldens ``b8-slab-house`` and ``b2-slab-plain`` are written
from here and pinned by this module. Regenerate after a deliberate change (a
NEW plugin version) with ``uv run python packages/loft-plugins/tests/test_slab.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, PluginError, canonical_inputs
from loft_plugins.builtin.slab import inset, perimeter
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.materials import with_member_materials

# The B7 builders and body probes are test_building_outline's (pytest runs in
# importlib mode, which puts no test directory on sys.path).
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    ROOF,
    SKETCH_ID,
    SUBFLOOR_TOP,
    WALLS_ID,
    Body,
    b7,
    b7_openings,
    bodies,
    boxes,
    envelope,
    expand,
    members_json,
    members_of,
    opening,
    overlaps,
    rectangle,
    ref,
)

SLAB = REGISTRY.get("loft.slab", "1.0.0")
WALL_1_4 = REGISTRY.get("loft.wall", "1.4.0")
WALL_1_3 = REGISTRY.get("loft.wall", "1.3.0")

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000008b8")
B2_PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000008b2")
SLAB_ID = uuid.UUID("00000000-0000-0000-0000-00000000b801")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-00000000b804")
B8_GOLDEN = "b8-slab-house"
B2_GOLDEN = "b2-slab-plain"

Rows = list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]


def b8(length: float = 288.0, slab: dict[str, Any] | None = None) -> Rows:
    """B8: the sketch, the slab on it, the walls on the slab (1.4.0), B7's
    openings and roof: each row and its expansion, as documents builds them."""
    sketch = rectangle(length, 192)
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    rows: Rows = [(SKETCH_ID, sketch, [])]

    def add(fid: uuid.UUID, plugin: Any, raw: dict[str, Any], hosted: Any = ()) -> None:
        members = expand(plugin, fid, raw, dict(earlier), hosted)
        env = envelope(plugin, raw)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        rows.append((fid, env, members))

    add(SLAB_ID, SLAB, {"outline": ref(SKETCH_ID), **(slab or {})})
    wall_raw = {"outline": ref(SKETCH_ID), "floor": ref(SLAB_ID), **B7_STUDS}
    with_walls = {**earlier, WALLS_ID: envelope(WALL_1_4, wall_raw)}
    hosted = [
        opening(p, name, WALLS_ID, {"wall_segment": [seg], **raw}, with_walls)
        for p, name, seg, raw in b7_openings(length)
    ]
    add(WALLS_ID, WALL_1_4, wall_raw, tuple(hosted))
    for h in hosted:
        add(
            h.feature_id,
            REGISTRY.get(h.plugin_id, h.plugin_version),
            dict(h.inputs.values),
        )
    add(
        ROOF_ID,
        ROOF,
        {"walls": [ref(WALLS_ID)], "slope_walls": ["e1", "e3"], **B7_ROOF},
    )
    return rows


def slab_members(**raw: Any) -> list[ExpandedMember]:
    if "outline" in raw:
        return expand(SLAB, SLAB_ID, raw, {SKETCH_ID: rectangle(288, 192)})
    return expand(SLAB, SLAB_ID, raw, {})


def lowered(counter: Counter[Body], dz: float) -> Counter[Body]:
    out: Counter[Body] = Counter()
    for (profile, material, pts), n in counter.items():
        moved = tuple(sorted((x, y, round(z + dz, 6) + 0.0) for x, y, z in pts))
        out[(profile, material, moved)] += n
    return out


def slab_member(members: list[ExpandedMember]) -> ExpandedMember:
    return next(m for m in members if m.role == "slab")


# --- The slab -----------------------------------------------------------------------


def test_b8s_slab_is_the_plate_and_the_edge_ring_in_one_pour() -> None:
    members = slab_members(outline=ref(SKETCH_ID))
    assert [m.role for m in members] == ["section", "slab", "level", "section", "edge"]
    plate = slab_member(members)
    assert isinstance(plate.feature, ExtrudeFeature)
    assert plate.feature.params.merge is False
    assert plate.feature.params.direction == "reverse"
    assert plate.feature.params.distance_mm == pytest.approx(4 * IN)
    edge = members[-1]
    assert isinstance(edge.feature, ExtrudeFeature)
    assert edge.feature.params.merge is True  # fused into the plate's body
    assert edge.feature.params.distance_mm == pytest.approx(8 * IN)
    # The plate: X 0..288, Y 0..192, Z -4..0.
    assert boxes(members, ("slab",)) == [(0.0, 288.0, 0.0, 192.0, -4.0, 0.0)]
    # The ring's section: the outline and the outline inset 12 (X 12..276,
    # Y 12..180), on the plate's underside.
    ring = members[3].feature
    assert isinstance(ring, SketchFeature)
    corners = sorted(
        {
            (round(e.start.x / IN, 9), round(e.start.y / IN, 9))  # type: ignore[union-attr]
            for e in ring.params.entities
        }
    )
    assert corners == sorted(
        [
            (0, 0),
            (288, 0),
            (288, 192),
            (0, 192),
            (12, 12),
            (276, 12),
            (276, 180),
            (12, 180),
        ]
    )
    level = members[2].feature
    assert level.params.offset_mm == pytest.approx(-4 * IN)  # type: ignore[union-attr]


def test_b8s_slab_lists_its_concrete_and_two_912_in_loops() -> None:
    plate = slab_member(slab_members(outline=ref(SKETCH_ID)))
    meta = plate.metadata
    assert meta is not None
    assert (meta.profile, meta.material) == ("Ready-mix concrete", "concrete")
    assert meta.concrete is not None and meta.concrete.waste_percent == 5
    assert meta.rebar is not None
    assert [(round(r.length_mm / IN, 9), r.closed) for r in meta.rebar] == [
        (912.0, True),
        (912.0, True),
    ]


def test_b2s_plain_slab_is_a_box_with_no_rebar() -> None:
    members = slab_members(thickened_edge="no")
    assert [m.role for m in members] == ["section", "slab"]
    assert boxes(members) == [(0.0, 144.0, 0.0, 120.0, -4.0, 0.0)]
    meta = slab_member(members).metadata
    assert meta is not None and meta.rebar is None


def test_no_rebar_keeps_the_edge() -> None:
    members = slab_members(outline=ref(SKETCH_ID), edge_rebar="none")
    assert [m.role for m in members][-1] == "edge"
    meta = slab_member(members).metadata
    assert meta is not None and meta.rebar is None


def test_the_top_elevation_raises_the_slab() -> None:
    members = slab_members(thickened_edge="no", top_elevation_mm=6 * IN)
    assert boxes(members) == [(0.0, 144.0, 0.0, 120.0, 2.0, 6.0)]


def test_an_edge_no_deeper_than_the_slab_is_refused() -> None:
    with pytest.raises(PluginError, match="Edge depth") as error:
        slab_members(edge_depth_mm=4 * IN)
    assert error.value.input == "edge_depth_mm"


def test_an_l_insets_round_its_inside_corner() -> None:
    ell = [
        (0.0, 0.0),
        (240.0, 0.0),
        (240.0, 120.0),
        (144.0, 120.0),
        (144.0, 192.0),
        (0.0, 192.0),
    ]
    assert inset(ell, 12) == (
        (12.0, 12.0),
        (228.0, 12.0),
        (228.0, 108.0),
        (132.0, 108.0),
        (132.0, 180.0),
        (12.0, 180.0),
    )
    # A rectilinear loop's centreline loop is its perimeter less 8 x the inset.
    assert perimeter(inset(ell, 6)) == perimeter(ell) - 48


def test_an_outline_too_narrow_for_the_edge_is_refused() -> None:
    narrow = [(0.0, 0.0), (48.0, 0.0), (48.0, 20.0), (0.0, 20.0)]
    with pytest.raises(PluginError, match="too short"):
        inset(narrow, 12)


def test_the_waste_allowance_is_stored_and_listed() -> None:
    stored = canonical_inputs(SLAB.manifest, {})
    assert stored["waste_percent"] == 5
    meta = slab_member(slab_members(waste_percent=10)).metadata
    assert meta is not None and meta.concrete is not None
    assert meta.concrete.waste_percent == 10


# --- The walls on it ----------------------------------------------------------------


def above_slab(rows: Rows) -> list[ExpandedMember]:
    return [m for fid, _, ms in rows if fid != SLAB_ID for m in ms]


def test_b8s_walls_openings_and_roof_are_b7s_lowered_to_the_slab_top() -> None:
    """Every body above the slab is B7's (b7-outline) less its floor,
    lowered by the subfloor's top: the walls stand on the slab at Z 0."""
    house = b7()
    # Rows 0 and 1 are the sketch and the floor.
    floor_free = [m for _, _, ms in house[2:] for m in ms]
    want = lowered(bodies(floor_free), -SUBFLOOR_TOP)
    assert bodies(above_slab(b8())) == want
    assert sum(want.values()) == 217 - 39  # b7-outline less the floor's 39


def test_only_the_bottom_plates_list_bolts() -> None:
    walls = next(ms for fid, _, ms in b8() if fid == WALLS_ID)
    bolted = [m for m in walls if m.metadata is not None and m.metadata.anchor_bolts]
    assert {m.role for m in bolted} == {"bottom_plate"}
    plates = [m for m in walls if m.role == "bottom_plate"]
    assert len(bolted) == len(plates) == 5  # the front cut at the door
    lengths = sorted(
        round(b[1] - b[0] + b[3] - b[2] - 5.5, 6)
        for b in boxes(walls, ("bottom_plate",))
    )
    assert lengths == [125.0, 125.0, 181.0, 181.0, 288.0]


def test_on_a_slab_inside_gypsum_bolts_only_the_bottom_plates() -> None:
    """1.4.0's INTERIOR-WALLS finish and SLAB's bolts on one wall: the
    gypsum is hung as off a slab as off a floor, and only plates bolt."""
    sketch = rectangle(288, 192)
    slab = envelope(SLAB, {"outline": ref(SKETCH_ID)})
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch, SLAB_ID: slab}
    raw = {"outline": ref(SKETCH_ID), "floor": ref(SLAB_ID), **B7_STUDS}
    finished = expand(WALL_1_4, WALLS_ID, {**raw, "finish": "gypsum_1_2"}, earlier)
    bolted = {m.role for m in finished if m.metadata and m.metadata.anchor_bolts}
    assert bolted == {"bottom_plate"}
    assert any(m.metadata and m.metadata.material == "gypsum" for m in finished)
    # Gypsum's courses start from the same base: Z 0, the slab's top.
    plain = expand(WALL_1_4, WALLS_ID, raw, earlier)
    assert min(b[4] for b in boxes(finished)) == min(b[4] for b in boxes(plain))


def test_with_no_slab_1_4_0_is_1_3_0() -> None:
    sketch = rectangle(288, 192)
    raw = {"outline": ref(SKETCH_ID), **B7_STUDS}
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    assert expand(WALL_1_4, WALLS_ID, raw, earlier) == expand(
        WALL_1_3, WALLS_ID, raw, earlier
    )


def test_1_3_0_cannot_pick_a_slab() -> None:
    pick = next(i for i in WALL_1_3.manifest.inputs if i.name == "floor")
    assert pick.plugin_ids == ["loft.floor"]  # type: ignore[union-attr]
    pick = next(i for i in WALL_1_4.manifest.inputs if i.name == "floor")
    assert pick.plugin_ids == ["loft.floor", "loft.slab"]  # type: ignore[union-attr]
    # 1.4.0 adds INTERIOR-WALLS' inside gypsum after 1.3.0's inputs, in order.
    assert [i.name for i in WALL_1_4.manifest.inputs] == [
        *(i.name for i in WALL_1_3.manifest.inputs),
        "finish",
        "finish_sheet",
    ]


def framing(rows: Rows) -> list[ExpandedMember]:
    """Every member but the rafters and ridge: boxes are exact for the slab
    and walls (a rafter's box takes in the plate its birdsmouth sits on; the
    geometry golden probes the solids)."""
    return [m for m in members_of(rows) if m.role not in ("rafter", "ridge")]


def test_nothing_overlaps() -> None:
    assert overlaps(boxes(framing(b8()))) == []


def test_the_length_edit_is_one_dimension() -> None:
    rows = b8(336)
    grown = members_of(rows)
    assert boxes(grown, ("slab",)) == [(0.0, 336.0, 0.0, 192.0, -4.0, 0.0)]
    meta = slab_member(grown).metadata
    assert meta is not None and meta.rebar is not None
    assert [round(r.length_mm / IN, 9) for r in meta.rebar] == [1008.0, 1008.0]
    assert overlaps(boxes(framing(rows))) == []


def test_a_slab_read_from_its_inputs_sets_the_wall_base() -> None:
    from loft_plugins.builtin.house import wall_values

    sketch = rectangle(288, 192)
    slab = envelope(SLAB, {"outline": ref(SKETCH_ID), "top_elevation_mm": 2 * IN})
    inputs = ExpandInputs(
        WALLS_ID,
        canonical_inputs(WALL_1_4.manifest, {"floor": ref(SLAB_ID)}),
        {SKETCH_ID: sketch, SLAB_ID: slab},
    )
    assert wall_values(inputs).number("elevation_mm") == pytest.approx(2 * IN)


# --- The goldens --------------------------------------------------------------------


TITLES = {
    role.role: role.title
    for plugin in (WALL_1_4, ROOF, SLAB)
    for role in plugin.manifest.members
}
PLUGINS = {
    role.role: plugin.manifest.id
    for plugin in (WALL_1_4, ROOF, SLAB)
    for role in plugin.manifest.members
}


def request_of(part: uuid.UUID, rows: Rows) -> EvaluateTreeRequest:
    features: list[EvaluatedFeatureInput] = []
    for fid, env, members in rows:
        if isinstance(env, SketchFeature):
            features.append(EvaluatedFeatureInput(id=fid, feature=env))
        features += [EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members]
    expansion = members_of(rows)
    return EvaluateTreeRequest(
        part_id=part,
        tree_version=1,
        features=features,
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in expansion if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )


def metadata_of(rows: Rows) -> list[CutListMember]:
    """Each body's metadata with its plugin (the cut list's system)."""
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
                    plugin_id=plugin_id or PLUGINS.get(m.role),
                    metadata=m.metadata,
                )
            )
    return out


def b2_rows() -> Rows:
    members = slab_members(thickened_edge="no")
    return [(SLAB_ID, envelope(SLAB, {"thickened_edge": "no"}), members)]


def goldens() -> dict[str, tuple[EvaluateTreeRequest, list[CutListMember]]]:
    house = b8()
    plain = b2_rows()
    return {
        B8_GOLDEN: (request_of(PART_ID, house), metadata_of(house)),
        B2_GOLDEN: (request_of(B2_PART_ID, plain), metadata_of(plain)),
    }


@pytest.mark.parametrize("name", [B8_GOLDEN, B2_GOLDEN])
def test_the_golden_is_the_plugins_expansion(name: str) -> None:
    request, metadata = goldens()[name]
    folder = GOLDENS / name
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


if __name__ == "__main__":
    for name, (request, metadata) in goldens().items():
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
