"""ROOF-MEMBER-RENUMBER: ``loft.roof`` 1.3.0 names each member by its place,
so lengthening, re-spacing or re-pitching the roof never hands a member's id
to another member.

1.0.0 to 1.2.0 numbered members in emission order. Lengthening B3's hip roof
by one spacing turns 1.2.0's ``common/3`` from the front ridge-end common at X
60 into the left king common, and the 1.0.0 gable's ``rafter/12`` from the
front end rafter into a layout rafter. A feature on that member (a hole, as a
Boolean subtract whose target is the member) silently moved. 1.3.0 emits
1.2.0's members in 1.2.0's order, with the same geometry, under stable names:
a plane by the way its wall faces in the world (``front``, ``left_notch``), a
common by its slot on the ridge layout from the ridge-end common
(``front/ridge/start``, ``front/ridge/slot/2``, ``front/ridge/end``), a king
by its plane (``left/king``), a jack by the hip it runs to and its count from
the end common (``front/left/1``), a hip, valley or ridge by the two planes
it divides (``back/left``), the gable's rafters by side and slot
(``front/slot/3``).

The geometry goldens ``b3-hip-v1.3-*`` are B3 at 1.3.0 with a 1 in hole
through the front ridge-end common (before and after the roof is lengthened
by one spacing) and through the front jack at X 36 (at 6/12 and 8/12). The
first test asserts the files are exactly this module's models. Regenerate
after a deliberate change with
``uv run python packages/loft-plugins/tests/test_roof_member_names.py``.
"""

import itertools
import json
import math
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, canonical_inputs, expand
from loft_plugins.builtin.roof_footprint import Footprint, canonical
from loft_plugins.builtin.roof_valley import Dims, eave_members, frame_plan
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    CustomFeature,
    DatumFeature,
    DatumOffsetParams,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.lumber import lumber_profile
from loft_wire.materials import with_member_materials
from loft_wire.plugins import member_id
from loft_wire.sketch import Point2D, SketchCircle

IN = 25.4
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
ROOF_V1_0 = REGISTRY.get("loft.roof", "1.0.0")
ROOF_V1_2 = REGISTRY.get("loft.roof", "1.2.0")
ROOF_V1_3 = REGISTRY.get("loft.roof", "1.3.0")
WALL = REGISTRY.get("loft.wall", "1.1.0")
B3_PART = uuid.UUID("00000000-0000-0000-0000-0000000000b3")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
HIP = {"style": "hip"}

#: A wall as typed into loft.wall: start x, start y (its outer face), direction
#: (deg), length (in); framing on the right, walls drawn clockwise.
WallRow = tuple[float, float, float, float]
B2_WALLS: list[WallRow] = [
    (144, 0, 180, 144),
    (0, 3.5, 90, 113),
    (0, 120, 0, 144),
    (144, 116.5, 270, 113),
]
#: buildings.md B4's six walls round the L.
B4_WALLS: list[WallRow] = [
    (0, 240, 0, 240),
    (240, 236.5, 270, 236.5),
    (236.5, 0, 180, 116.5),
    (120, 3.5, 90, 116.5),
    (123.5, 120, 180, 123.5),
    (0, 123.5, 90, 113),
]
#: B4's edit, the wing 48 wide.
WING_48_WALLS: list[WallRow] = [
    (0, 240, 0, 240),
    (240, 236.5, 270, 236.5),
    (236.5, 0, 180, 44.5),
    (192, 3.5, 90, 116.5),
    (195.5, 120, 180, 195.5),
    (0, 123.5, 90, 113),
]


def walls(
    rows: list[WallRow], ids: list[uuid.UUID] | None = None
) -> tuple[list[FeatureRef], dict[uuid.UUID, Any]]:
    """The walls as earlier features (ids given or numbered), and the picks."""
    refs: list[FeatureRef] = []
    earlier: dict[uuid.UUID, Any] = {}
    for index, (x, y, direction, length) in enumerate(rows):
        feature_id = ids[index] if ids else uuid.UUID(int=0xB4A11 * 256 + index)
        inputs = canonical_inputs(
            WALL.manifest,
            {
                "start_x_mm": x * IN,
                "start_y_mm": y * IN,
                "direction_deg": float(direction),
                "length_mm": length * IN,
            },
        )
        earlier[feature_id] = CustomFeature.model_validate(
            {
                "type": "custom",
                "version": 1,
                "params": {
                    "plugin_id": "loft.wall",
                    "plugin_version": "1.1.0",
                    "inputs": inputs,
                },
            }
        )
        refs.append(FeatureRef(kind="feature", feature_id=feature_id))
    return refs, earlier


def roof(
    version: str = "1.3.0",
    raw: dict[str, Any] | None = None,
    rows: list[WallRow] | None = None,
    ids: list[uuid.UUID] | None = None,
) -> list[ExpandedMember]:
    plugin = REGISTRY.get("loft.roof", version)
    inputs = dict(raw or {})
    earlier: dict[uuid.UUID, Any] = {}
    if rows:
        refs, earlier = walls(rows, ids)
        inputs["walls"] = refs
    return expand(plugin, ROOF_ID, canonical_inputs(plugin.manifest, inputs), earlier)


def by_name(members: list[ExpandedMember], role: str, name: str) -> ExpandedMember:
    found = [m for m in members if m.role == role and m.name == name]
    assert len(found) == 1, (role, name)
    return found[0]


def placement(members: list[ExpandedMember], member: ExpandedMember) -> Any:
    """A member's feature with every reference into the expansion replaced
    by the referenced member's own (recursively): where it is, whatever its
    id and its datums' ids."""
    table = {m.id: m for m in members}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            fields: dict[str, Any] = node  # pyright: ignore[reportUnknownVariableType]
            target = fields.get("feature_id")
            if fields.get("kind") == "feature" and target is not None:
                ref = uuid.UUID(str(target))
                if ref in table:
                    return walk(table[ref].feature.model_dump(mode="json"))
            return {k: walk(v) for k, v in fields.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]  # pyright: ignore[reportUnknownVariableType]
        return node

    return walk(member.feature.model_dump(mode="json"))


def plan_x(members: list[ExpandedMember], member: ExpandedMember) -> float:
    """A rafter's low-X face (in): its section's YZ datum offset."""
    place = placement(members, member)
    plane = place["params"]["profile"]["params"]["plane"]
    assert plane["params"]["base"] == "YZ"
    return round(plane["params"]["offset_mm"] / IN, 9)


# --- 1.3.0 is 1.2.0 renamed ---------------------------------------------------------


def _renamed(old: list[ExpandedMember], new: list[ExpandedMember]) -> None:
    """*new* is *old* member for member (role, index, feature, metadata), its
    references carried through the rename; only ids differ, and every new
    member has a name."""
    assert [(m.role, m.index) for m in new] == [(m.role, m.index) for m in old]
    assert all(m.name is not None for m in new)
    assert len({m.id for m in new}) == len(new)
    rename = {str(o.id): str(n.id) for o, n in zip(old, new, strict=True)}
    for o, n in zip(old, new, strict=True):
        dumped = json.dumps(o.feature.model_dump(mode="json"), sort_keys=True)
        for before, after in rename.items():
            dumped = dumped.replace(before, after)
        assert json.loads(dumped) == n.feature.model_dump(mode="json")
        assert o.metadata == n.metadata


CASES: dict[str, tuple[dict[str, Any], list[WallRow] | None]] = {
    "b2 gable": ({}, None),
    "b2 gable 8/12 16 oc no overhang": (
        {"pitch": "rise_8", "spacing_mm": 16 * IN, "overhang_mm": 0.0},
        None,
    ),
    "b2 gable 19.2 oc 200 span": (
        {"spacing_mm": 19.2 * IN, "span_mm": 200 * IN, "ridge_profile": "us_2x10"},
        None,
    ),
    "b3": (HIP, None),
    "b3 8/12": ({**HIP, "pitch": "rise_8"}, None),
    "b3 168 16 oc oh 0": (
        {**HIP, "length_mm": 168 * IN, "spacing_mm": 16 * IN, "overhang_mm": 0.0},
        None,
    ),
    "b3 on walls": (HIP, B2_WALLS),
    "b4": (HIP, B4_WALLS),
    "b4 wing 48": (HIP, WING_48_WALLS),
    "b4 12/12 19.2 oc oh 36": (
        {
            **HIP,
            "pitch": "rise_12",
            "spacing_mm": 19.2 * IN,
            "overhang_mm": 36 * IN,
            "ridge_profile": "us_2x10",
            "hip_profile": "us_2x10",
            "valley_profile": "us_2x10",
        },
        B4_WALLS,
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_1_3_roof_is_the_1_2_roof_renamed(case: str) -> None:
    raw, rows = CASES[case]
    _renamed(roof("1.2.0", raw, rows), roof("1.3.0", raw, rows))


def test_1_3_is_the_latest_and_takes_1_2s_inputs() -> None:
    # 1.4.0 (BUILDING-OUTLINE, test_building_outline.py) and 1.5.0
    # (ROOF-HIP-SHEATHING-NOTCH, test_roof_sheathing.py) and 1.6.0
    # (CEILING-JOISTS, test_ceiling_joists.py) are newer still.
    assert REGISTRY.latest("loft.roof").manifest.version == "1.6.0"
    assert ROOF_V1_3.manifest.inputs == ROOF_V1_2.manifest.inputs
    assert ROOF_V1_3.manifest.members == ROOF_V1_2.manifest.members
    assert ROOF_V1_3.renumbered_roles == frozenset()
    for version in ("1.0.0", "1.1.0", "1.2.0"):
        assert REGISTRY.get("loft.roof", version).renumbered_roles


# --- Names survive the edits that renumbered 1.2.0 ---------------------------------


def test_lengthening_the_hip_roof_keeps_the_ridge_end_common() -> None:
    """B3 144 -> 168 (one spacing): under 1.2.0 common/3 is the front
    ridge-end common at X 60 before and the left king common after; under
    1.3.0 front/ridge/start is that common at both lengths, and every member
    of the left half keeps its name and place."""
    old144 = roof("1.2.0", HIP)
    old168 = roof("1.2.0", {**HIP, "length_mm": 168 * IN})
    c3 = next(m for m in old144 if (m.role, m.index) == ("common", 3))
    c3_after = next(m for m in old168 if (m.role, m.index) == ("common", 3))
    assert c3.id == c3_after.id
    assert plan_x(old144, c3) == 59.25
    assert placement(old144, c3) != placement(old168, c3_after)  # the left king

    new144, new168 = roof(raw=HIP), roof(raw={**HIP, "length_mm": 168 * IN})
    a = by_name(new144, "common", "front/ridge/start")
    b = by_name(new168, "common", "front/ridge/start")
    assert a.id == b.id == member_id(ROOF_ID, "common", 0, "front/ridge/start")
    assert plan_x(new144, a) == plan_x(new168, b) == 59.25
    for role, name in [
        ("common", "back/ridge/start"),
        ("common", "left/king"),
        ("jack", "front/left/1"),
        ("jack", "front/left/2"),
        ("jack", "left/front/1"),
        ("hip", "front/left"),
    ]:
        x, y = by_name(new144, role, name), by_name(new168, role, name)
        assert x.id == y.id and placement(new144, x) == placement(new168, y), name
    # The far end moved with the end: its names followed it.
    end144 = by_name(new144, "common", "front/ridge/end")
    end168 = by_name(new168, "common", "front/ridge/end")
    assert (plan_x(new144, end144), plan_x(new168, end168)) == (83.25, 107.25)
    assert plan_x(new168, by_name(new168, "common", "front/ridge/slot/1")) == 83.25


def test_a_pitch_change_keeps_every_name() -> None:
    """B3 and B4 6/12 -> 8/12: the same names, the jack at X 36 among them,
    and the jack stays at X 36 (only its profile changes)."""
    for rows in (None, B4_WALLS):
        six, eight = (
            roof(raw=HIP, rows=rows),
            roof(raw={**HIP, "pitch": "rise_8"}, rows=rows),
        )
        assert [(m.role, m.name, m.id) for m in six] == [
            (m.role, m.name, m.id) for m in eight
        ]
    six, eight = roof(raw=HIP), roof(raw={**HIP, "pitch": "rise_8"})
    jack6, jack8 = (
        by_name(six, "jack", "front/left/1"),
        by_name(eight, "jack", "front/left/1"),
    )
    assert plan_x(six, jack6) == plan_x(eight, jack8) == 35.25


def test_lengthening_the_gable_keeps_its_rafters() -> None:
    """B2's gable 144 -> 168: 1.0.0's rafter/12 is the front end rafter at
    143.25, then the layout rafter at 144; 1.3.0's front/end follows the end
    and front/slot/5 (X 120) stays."""
    old144, old168 = roof("1.0.0"), roof("1.0.0", {"length_mm": 168 * IN})
    r12 = next(m for m in old144 if (m.role, m.index) == ("rafter", 12))
    r12_after = next(m for m in old168 if (m.role, m.index) == ("rafter", 12))
    assert (plan_x(old144, r12), plan_x(old168, r12_after)) == (142.5, 143.25)

    new144, new168 = roof(), roof(raw={"length_mm": 168 * IN})
    for name in ("front/start", "front/slot/3", "back/slot/5", "front/end"):
        assert by_name(new144, "rafter", name).id == by_name(new168, "rafter", name).id
    assert plan_x(new168, by_name(new168, "rafter", "front/slot/6")) == 143.25
    assert plan_x(new168, by_name(new168, "rafter", "front/end")) == 166.5
    slot5 = by_name(new144, "rafter", "back/slot/5")
    assert placement(new144, slot5) == placement(
        new168, by_name(new168, "rafter", "back/slot/5")
    )


def test_overhang_and_spacing_keep_the_names_of_what_stays() -> None:
    """A slot is n x spacing from its origin, so the names of the members a
    change keeps are kept; a new spacing re-lays the slots in place."""
    base = {m.name for m in roof(raw=HIP, rows=B4_WALLS) if m.role == "common"}
    deep = roof(raw={**HIP, "overhang_mm": 24 * IN}, rows=B4_WALLS)
    assert {m.name for m in deep if m.role == "common"} == base
    tight = roof(raw={**HIP, "spacing_mm": 16 * IN}, rows=B4_WALLS)
    names = {m.name for m in tight if m.role == "common"}
    assert {"back/ridge/start", "back/ridge/end", "left/king"} <= names
    assert (
        by_name(tight, "common", "back/ridge/slot/1").id
        == by_name(roof(raw=HIP, rows=B4_WALLS), "common", "back/ridge/slot/1").id
    )


def test_re_picking_the_walls_keeps_every_name() -> None:
    """The walls picked in any order, or redrawn as new wall features in the
    same place, frame the same members under the same names: a plane is
    named by the way its wall faces in the world, not by the pick."""
    base = roof(raw=HIP, rows=B4_WALLS)
    names = [(m.role, m.name) for m in base]
    for order in ([3, 4, 5, 0, 1, 2], [5, 4, 3, 2, 1, 0]):
        rows = [B4_WALLS[i] for i in order]
        again = roof(raw=HIP, rows=rows)
        assert [(m.role, m.name, m.id) for m in again] == [
            (m.role, m.name, m.id) for m in base
        ]
    fresh = [uuid.uuid5(ROOF_ID, f"wall {i}") for i in range(6)]
    redrawn = roof(raw=HIP, rows=B4_WALLS, ids=fresh)
    assert [(m.role, m.name) for m in redrawn] == names
    # No name embeds a feature id, so a copy or import re-mints them whole.
    assert not any(str(w) in str(m.name) for m in redrawn for w in fresh)


def test_names_are_places() -> None:
    gable = roof()
    assert [m.name for m in gable if m.role == "rafter"][:4] == [
        "front/start",
        "back/start",
        "front/slot/1",
        "back/slot/1",
    ]
    assert by_name(gable, "ridge", "back/front").role == "ridge"
    b4 = roof(raw=HIP, rows=B4_WALLS)
    assert sorted(str(m.name) for m in b4 if m.role == "hip") == [
        "back/left",
        "back/right",
        "front/left_notch",
        "front/right",
        "front_notch/left",
    ]
    assert [m.name for m in b4 if m.role == "valley"] == ["front_notch/left_notch"]
    assert sorted(str(m.name) for m in b4 if m.role == "ridge") == [
        "back/front_notch",
        "left_notch/right",
    ]
    wing = roof(raw=HIP, rows=WING_48_WALLS)
    assert "front_notch/right" in {m.name for m in wing if m.role == "hip"}
    assert [m.name for m in wing if m.role == "cripple"] == ["front_notch/right/1"]
    # Every cutter and trim is named after the member it cuts.
    jack = by_name(b4, "jack", "front/right/1")
    trim = next(
        m
        for m in b4
        if isinstance(m.feature, BooleanFeature)
        and m.feature.params.target.feature_id == jack.id
    )
    assert trim.name == "jack/front/right/1/0"


# --- Coincident layout lines: the float class (1.3.0 merges within 1e-9) -----------


def _l_plan(spacing: float, w2: float, b: float, a: float, named: bool) -> list[Any]:
    """An L whose arms differ by two spacings (so the wing's jacks from the
    king run onto the flush ridge-end common), framed; its layout lines."""
    w1 = w2 + 2 * spacing
    big_a, big_b = a + w2, b + w1
    if big_a - w1 < 1.5:
        big_a = w1 + 30 + a
        a = big_a - w2
    corners = ((a, 0.0), (big_a, 0.0), (big_a, big_b), (0.0, big_b), (0.0, b), (a, b))
    shape = canonical(Footprint(corners, 97.125, 3.5), 1.5)
    deep = lumber_profile("us_2x8")
    dims = Dims(
        6, 97.125, 3.5, spacing, 12.0, lumber_profile("us_2x6"), deep, deep, deep
    )
    plan = frame_plan(shape, dims, named)
    return [m for e in plan.eaves for m in eave_members(e, dims)]


def test_layout_lines_an_ulp_apart_frame_one_member() -> None:
    """The wing's jacks laid out from the king reach the flush ridge-end
    common's place by another sum, an ulp off it: 1.2.0 laid out TWO
    coincident commons there (overlapping solids, two cut-list lines). 1.3.0
    counts layout lines within 1e-9 in as one; 1.2.0 still lays the twin out,
    to keep its numbering, and marks it dropped (ROOF-L-DOUBLED-COMMON). Over
    64 constructed L footprints 1.2.0 marks a twin in 25, and neither frames
    two members at one place."""
    doubled = {False: 0, True: 0}
    twins = 0
    cases = list(
        itertools.product(
            (16.0, 19.2, 12.7, 17.1),
            (48.0, 50.3, 61.7, 72.9),
            (37.3, 51.1),
            (24.0, 33.3),
        )
    )
    for spacing, w2, b, a in cases:
        for named in (False, True):
            laid_out = _l_plan(spacing, w2, b, a, named)
            twins += any(m.twin for m in laid_out)
            rafters = [m for m in laid_out if not m.twin]
            centres = sorted((m.eave.origin, m.eave.inward, m.centre) for m in rafters)
            if any(
                p[:2] == q[:2] and q[2] - p[2] < 1e-9
                for p, q in itertools.pairwise(centres)
            ):
                doubled[named] += 1
    assert len(cases) == 64
    assert doubled == {False: 0, True: 0}
    assert twins == 25


# --- The goldens: a hole that stays in its member -----------------------------------


def drill(
    part: uuid.UUID, target: uuid.UUID, x: float, y: float, z: float
) -> list[EvaluatedFeatureInput]:
    """A 1 in hole along X through the rafter *target* names, centred at
    (x, y, z) in: a circle at (y, z) on a YZ datum through *x*, extruded
    symmetric 3 in (past both faces of the 1.5 in rafter) as a new body and
    subtracted from the target (Fusion's Combine > Cut). The tool is consumed."""
    ids = {n: uuid.uuid5(part, f"hole/{n}") for n in ("datum", "sketch", "tool", "cut")}
    return [
        EvaluatedFeatureInput(
            id=ids["datum"],
            feature=DatumFeature(
                type="datum",
                version=1,
                params=DatumOffsetParams(base="YZ", offset_mm=x * IN),
            ),
        ),
        EvaluatedFeatureInput(
            id=ids["sketch"],
            feature=SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=FeatureRef(kind="feature", feature_id=ids["datum"]),
                    entities=[
                        SketchCircle(
                            id="c1",
                            kind="circle",
                            center=Point2D(x=y * IN, y=z * IN),
                            radius=0.5 * IN,
                        )
                    ],
                    constraints=[],
                ),
            ),
        ),
        EvaluatedFeatureInput(
            id=ids["tool"],
            feature=ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=FeatureRef(kind="feature", feature_id=ids["sketch"]),
                    distance_mm=3 * IN,
                    operation="add",
                    merge=False,
                    extent="symmetric",
                ),
            ),
        ),
        EvaluatedFeatureInput(
            id=ids["cut"],
            feature=BooleanFeature(
                type="boolean",
                version=1,
                params=BooleanParamsV1(
                    operation="subtract",
                    target=FeatureRef(kind="feature", feature_id=target),
                    tool=FeatureRef(kind="feature", feature_id=ids["tool"]),
                ),
            ),
        ),
    ]


def _golden(
    raw: dict[str, Any], role: str, name: str, x: float
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B3 at 1.3.0 (typed bearing, *raw* over B3's inputs) with a 1 in hole
    along X through the member (role, name), centred at (x, 20, 110) in: 20
    in from the front wall, between the rafter's edges at 6/12 and 8/12."""
    expansion = roof(raw={**HIP, **raw})
    member = by_name(expansion, role, name)
    titles = {r.role: r.title for r in ROOF_V1_3.manifest.members}
    request = EvaluateTreeRequest(
        part_id=B3_PART,
        tree_version=1,
        features=[
            *(EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion),
            *drill(B3_PART, member.id, x, 20.0, 110.0),
        ],
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


#: The front ridge-end common is X 59.25..60.75 at both lengths; the front
#: jack nearest the left hip's ridge end is X 35.25..36.75 at both pitches.
GOLDENS_1_3: dict[
    str, Callable[[], tuple[EvaluateTreeRequest, list[CutListMember]]]
] = {
    "b3-hip-v1.3-hole-common": lambda: _golden({}, "common", "front/ridge/start", 60),
    "b3-hip-v1.3-168-hole-common": lambda: _golden(
        {"length_mm": 168 * IN}, "common", "front/ridge/start", 60
    ),
    "b3-hip-v1.3-hole-jack": lambda: _golden({}, "jack", "front/left/1", 36),
    "b3-hip-v1.3-8-12-hole-jack": lambda: _golden(
        {"pitch": "rise_8"}, "jack", "front/left/1", 36
    ),
}


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


@pytest.mark.parametrize("name", sorted(GOLDENS_1_3))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = GOLDENS_1_3[name]()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


def test_the_hole_targets_one_member_before_and_after_each_edit() -> None:
    def target(name: str) -> uuid.UUID:
        request, _ = GOLDENS_1_3[name]()
        cut = request.features[-1].feature
        assert isinstance(cut, BooleanFeature)
        return cut.params.target.feature_id

    common = member_id(ROOF_ID, "common", 0, "front/ridge/start")
    assert target("b3-hip-v1.3-hole-common") == common
    assert target("b3-hip-v1.3-168-hole-common") == common
    jack = member_id(ROOF_ID, "jack", 0, "front/left/1")
    assert target("b3-hip-v1.3-hole-jack") == jack
    assert target("b3-hip-v1.3-8-12-hole-jack") == jack


def test_the_hole_is_inside_its_rafter_at_both_pitches() -> None:
    """(y 20, z 110) lies at least 0.5 in (the radius) inside the rafter's
    edges, 20 in from the wall, at 6/12 and 8/12 (buildings.md's commons:
    the bottom edge through the seat's inner corner at the plate)."""
    for rise, seat in ((6, 3.5), (8, 2.75)):
        k = rise / 12
        bottom = 97.125 + (20 - seat) * k
        top = bottom + 5.5 * math.hypot(12, rise) / 12
        assert bottom + 0.5 < 110 < top - 0.5, rise


if __name__ == "__main__":
    for name in sorted(GOLDENS_1_3):
        request, metadata = GOLDENS_1_3[name]()
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
