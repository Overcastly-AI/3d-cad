"""``loft.floor`` 1.0.0: B5's framed floor from one custom feature (FLOOR-FRAME).

Layouts are checked against ``docs/reference-parts/buildings.md`` B5, typed
from the spec by hand. The geometry goldens ``b5-floor-2x8-16oc`` and
``-12oc`` are the floor's expansion, and ``b5-shed-walls-on-floor`` is the
floor with B2's four walls standing on it (their base elevation the joists'
top, 8.75); each is ``model.json`` (with the member materials documents
sends) and ``members.json`` (the members' metadata). The first test asserts
the files are exactly that, so the geometry acceptance
(``services/geometry/tests/test_floor_b5.py``) reads files that cannot drift.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_floor.py``.
"""

import gzip
import json
import random
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, canonical_inputs, expand
from loft_plugins.builtin.floor import (
    FloorFrame,
    FloorSpec,
    Piece,
    floor_pieces,
    joist_centres,
    joist_slots,
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
from loft_wire.sketch import SketchLine

IN = 25.4
FLOOR = REGISTRY.get("loft.floor", "1.0.0")
WALL = REGISTRY.get("loft.wall", "1.0.0")
GEOMETRY = Path(__file__).resolve().parents[3] / "services" / "geometry"
GOLDENS = GEOMETRY / "goldens"
#: The kernel overlap sweep's requests (services/geometry/tests/test_floor_b5.py).
SWEEP_FIXTURE = GEOMETRY / "tests" / "fixtures" / "floor-sweep.json.gz"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b5")
FLOOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000f100")

#: B2's four walls (test_wall.py's, clockwise), standing on the floor.
B2_WALLS: list[tuple[uuid.UUID, dict[str, Any]]] = [
    (
        uuid.UUID("00000000-0000-0000-0000-00000000a511"),
        {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN},
    ),
    (
        uuid.UUID("00000000-0000-0000-0000-00000000a512"),
        {"start_y_mm": 3.5 * IN, "direction_deg": 90.0, "length_mm": 113 * IN},
    ),
    (
        uuid.UUID("00000000-0000-0000-0000-00000000a513"),
        {"start_y_mm": 120 * IN, "direction_deg": 0.0, "length_mm": 144 * IN},
    ),
    (
        uuid.UUID("00000000-0000-0000-0000-00000000a514"),
        {
            "start_x_mm": 144 * IN,
            "start_y_mm": 116.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 113 * IN,
        },
    ),
]


def members(
    raw: dict[str, Any] | None = None, feature_id: uuid.UUID = FLOOR_ID
) -> list[ExpandedMember]:
    inputs = canonical_inputs(FLOOR.manifest, raw or {})
    return expand(FLOOR, feature_id, inputs, {})


def spec(raw: dict[str, Any] | None = None) -> FloorSpec:
    return FloorSpec.from_inputs(
        ExpandInputs(FLOOR_ID, canonical_inputs(FLOOR.manifest, raw or {}))
    )


def _walls_on_floor() -> list[ExpandedMember]:
    """B2's walls with their base elevation on the floor's joists (8.75)."""
    top = spec().framing_top
    assert top == 8.75
    out: list[ExpandedMember] = []
    for feature_id, raw in B2_WALLS:
        inputs = canonical_inputs(WALL.manifest, {**raw, "elevation_mm": top * IN})
        out += expand(WALL, feature_id, inputs, {})
    return out


#: golden name -> its expansion (the floor's members first).
GOLDEN_MEMBERS: dict[str, Callable[[], list[ExpandedMember]]] = {
    "b5-floor-2x8-16oc": lambda: members(),
    # The spec's edit: "joist spacing 16 -> 12".
    "b5-floor-2x8-12oc": lambda: members({"joist_spacing_mm": 12 * IN}),
    "b5-shed-walls-on-floor": lambda: members() + _walls_on_floor(),
}


#: Member titles by role, the floor's and the wall's (they share only "sill",
#: titled "Sill" by both).
TITLES = {
    role.role: role.title
    for plugin in (WALL, FLOOR)
    for role in plugin.manifest.members
}


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request and its members' cut-list metadata."""
    return request_for(GOLDEN_MEMBERS[name]())


def request_for(
    expansion: list[ExpandedMember],
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """The evaluation request of *expansion* (member materials applied, as
    documents sends them) and its members' cut-list metadata."""
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
            feature_id=m.id,
            role=m.role,
            title=TITLES[m.role],
            metadata=m.metadata,
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


#: The kernel overlap sweep: name -> raw inputs (mm as a form sends them).
#: Turned floors (30, -45, 117.3 degrees), joists along the width, odd sizes
#: and spacings, a layout joist touching the end joist, no sill, every joist
#: and sill size.
SWEEP: dict[str, dict[str, Any]] = {
    "turned30-144x120-oc16": {
        "start_x_mm": 10 * IN,
        "start_y_mm": 20 * IN,
        "direction_deg": 30.0,
    },
    "width-200x96-oc19.2-2x10": {
        "width_mm": 200 * IN,
        "depth_mm": 96 * IN,
        "joist_spacing_mm": 19.2 * IN,
        "joist_direction": "width",
        "joist_profile": "us_2x10",
    },
    "touching-130.25-oc16-2x12-sill2x4": {
        "width_mm": 130.25 * IN,
        "joist_profile": "us_2x12",
        "sill_profile": "us_2x4",
    },
    "turned-45-3000x2500mm-oc13.7-nosill-elev24": {
        "start_x_mm": -500.0,
        "start_y_mm": 333.3,
        "direction_deg": -45.0,
        "width_mm": 3000.0,
        "depth_mm": 2500.0,
        "joist_spacing_mm": 13.7 * IN,
        "sill_plate": "no",
        "elevation_mm": 24 * IN,
    },
    "turned117.3-width-2111.7x4000mm-oc24-2x6-sill2x8": {
        "direction_deg": 117.3,
        "width_mm": 2111.7,
        "depth_mm": 4000.0,
        "joist_spacing_mm": 24 * IN,
        "joist_direction": "width",
        "joist_profile": "us_2x6",
        "sill_profile": "us_2x8",
    },
    "axis-480x240-oc12-2x12": {
        "width_mm": 480 * IN,
        "depth_mm": 240 * IN,
        "joist_spacing_mm": 12 * IN,
        "joist_profile": "us_2x12",
    },
}


def sweep_fixture() -> str:
    """The sweep's requests as geometry reads them (compact JSON)."""
    cases: list[dict[str, Any]] = []
    for name, raw in SWEEP.items():
        request, metadata = request_for(members(raw))
        cases.append(
            {
                "name": name,
                "bodies": len(metadata),
                "request": request.model_dump(mode="json"),
            }
        )
    return json.dumps(cases, separators=(",", ":"), sort_keys=True)


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


Box = tuple[float, float, float, float, float, float]


def boxes(expansion: list[ExpandedMember]) -> dict[tuple[str, int], Box]:
    """Each axis-aligned body's box in inches (x0, x1, y0, y1, z0, z1), read
    from its section sketch, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: dict[tuple[str, int], Box] = {}
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
        for a, b in zip(lines, lines[1:] + lines[:1], strict=True):
            assert a.end == b.start  # a closed loop
        xs = {round(e.start.x / IN, 9) + 0.0 for e in lines}
        ys = {round(e.start.y / IN, 9) + 0.0 for e in lines}
        assert len(xs) == 2 and len(ys) == 2, m.role  # axis-aligned
        z1 = z0 + m.feature.params.distance_mm
        out[(m.role, m.index)] = (
            min(xs),
            max(xs),
            min(ys),
            max(ys),
            round(z0 / IN, 9) + 0.0,
            round(z1 / IN, 9) + 0.0,
        )
    return out


def _volume(box: Box) -> float:
    x0, x1, y0, y1, z0, z1 = box
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


# --- Goldens -----------------------------------------------------------------------


def test_the_sweep_fixture_is_the_plugins_expansion() -> None:
    assert gzip.decompress(SWEEP_FIXTURE.read_bytes()).decode() == sweep_fixture()


@pytest.mark.parametrize("name", sorted(GOLDEN_MEMBERS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- B5, coordinate by coordinate --------------------------------------------------


def test_the_default_floor_is_b5s() -> None:
    """buildings.md B5's floor: every bound typed from the spec."""
    got = boxes(members())
    assert Counter(role for role, _ in got) == {"joist": 10, "rim": 2, "sill": 4}
    assert got[("sill", 0)] == (0, 144, 0, 5.5, 0, 1.5)
    assert got[("sill", 1)] == (0, 144, 114.5, 120, 0, 1.5)
    assert got[("sill", 2)] == (0, 5.5, 5.5, 114.5, 0, 1.5)
    assert got[("sill", 3)] == (138.5, 144, 5.5, 114.5, 0, 1.5)
    assert got[("rim", 0)] == (0, 144, 0, 1.5, 1.5, 8.75)
    assert got[("rim", 1)] == (0, 144, 118.5, 120, 1.5, 8.75)
    centres = sorted(
        (box[0] + box[1]) / 2 for (role, _), box in got.items() if role == "joist"
    )
    assert centres == [0.75, 16, 32, 48, 64, 80, 96, 112, 128, 143.25]
    for (role, _), box in got.items():
        if role == "joist":
            assert box[2:] == (1.5, 118.5, 1.5, 8.75)
            assert box[1] - box[0] == 1.5
    volume = sum(_volume(b) for b in got.values())
    assert volume == pytest.approx(20030.25, abs=1e-9)
    by_role = Counter[str]()
    for (role, _), box in got.items():
        by_role[role] += round(_volume(box), 9)  # type: ignore[assignment]
    assert by_role == {"sill": 4174.5, "rim": 3132, "joist": 12723.75}


def test_the_12oc_edit_gives_13_joists() -> None:
    got = boxes(members({"joist_spacing_mm": 12 * IN}))
    centres = sorted(
        (box[0] + box[1]) / 2 for (role, _), box in got.items() if role == "joist"
    )
    assert centres == [0.75, *range(12, 133, 12), 143.25]
    assert len(centres) == 13
    volume = sum(_volume(b) for b in got.values())
    assert volume == pytest.approx(23847.375, abs=1e-9)


def test_walls_stand_on_the_joists() -> None:
    """B2's walls at base elevation 8.75 bear on the rims and end joists."""
    expansion = _walls_on_floor()
    walls = [boxes(chunk) for chunk in _per_wall(expansion)]
    bottoms = [w[("bottom_plate", 0)] for w in walls]
    assert len(bottoms) == 4
    assert all(b[4:] == (8.75, 10.25) for b in bottoms)
    assert max(b[5] for w in walls for b in w.values()) == 8.75 + 97.125


def _per_wall(expansion: list[ExpandedMember]) -> list[list[ExpandedMember]]:
    """The walls' expansions apart (each starts at its first level)."""
    chunks: list[list[ExpandedMember]] = []
    for m in expansion:
        if m.role == "level" and m.index == 0:
            chunks.append([])
        chunks[-1].append(m)
    return chunks


def test_metadata_is_plain_library_names() -> None:
    expansion = members()
    bodies = [m for m in expansion if isinstance(m.feature, ExtrudeFeature)]
    assert {
        (m.role, m.metadata.profile, m.metadata.material)
        for m in bodies
        if m.metadata is not None
    } == {
        ("joist", "2x8", "spf_lumber"),
        ("rim", "2x8", "spf_lumber"),
        ("sill", "2x6", "southern_pine_pt"),
    }
    assert all(m.metadata is not None for m in bodies)
    helpers = [m for m in expansion if not isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is None for m in helpers)


def test_roles_emit_in_the_cut_list_order() -> None:
    order = [m.role for m in members() if isinstance(m.feature, ExtrudeFeature)]
    assert list(dict.fromkeys(order)) == ["joist", "rim", "sill"]
    # Within the sills, the two full ones (144) list before the butted (109).
    sills = [p for p in floor_pieces(spec()) if p.role == "sill"]
    assert [p.a1 - p.a0 if p.index < 2 else p.b1 - p.b0 for p in sills] == [
        144,
        144,
        109,
        109,
    ]


# --- Determinism and stable ids ----------------------------------------------------


def test_the_expansion_is_deterministic() -> None:
    a = [m.model_dump(mode="json") for m in members()]
    b = [m.model_dump(mode="json") for m in members()]
    assert a == b


def test_joists_are_named_by_slot() -> None:
    """joist/0 and joist/1 are the end joists; joist/k+1 sits at k spacings."""
    got = boxes(members())
    assert got[("joist", 0)][:2] == (0, 1.5)
    assert got[("joist", 1)][:2] == (142.5, 144)
    for k in range(1, 9):
        assert got[("joist", k + 1)][:2] == (16 * k - 0.75, 16 * k + 0.75)


def test_widening_keeps_every_joists_id_on_its_joist() -> None:
    """A wider floor adds layout joists after the ones it had: the end joist
    and every layout joist keep their ids and their place from the start
    (unlike loft.deck 1.0.0's end joist, WALL-MEMBER-RENUMBER)."""
    before = {(m.role, m.index): m.id for m in members()}
    after_members = members({"width_mm": 192 * IN})
    after = {(m.role, m.index): m.id for m in after_members}
    wide = boxes(after_members)
    narrow = boxes(members())
    for k in range(10):
        assert before[("joist", k)] == after[("joist", k)]
        if k != 1:  # the far end joist moves with the far edge, keeping its id
            assert wide[("joist", k)][:2] == narrow[("joist", k)][:2]
    assert wide[("joist", 1)][:2] == (190.5, 192)
    assert Counter(r for r, _ in wide)["joist"] == 13


def test_the_joist_direction_turns_the_layout() -> None:
    """Joists along the width: rims along Y at X 0..1.5 and 142.5..144, joists
    142.5 - 1.5 = 141 long laid out along Y from Y 0 (120: 0.75, 16, ...,
    112, 119.25), sills full under the rims and butted between them."""
    got = boxes(members({"joist_direction": "width"}))
    assert got[("rim", 0)] == (0, 1.5, 0, 120, 1.5, 8.75)
    assert got[("rim", 1)] == (142.5, 144, 0, 120, 1.5, 8.75)
    assert got[("sill", 0)] == (0, 5.5, 0, 120, 0, 1.5)
    assert got[("sill", 2)] == (5.5, 138.5, 0, 5.5, 0, 1.5)
    centres = sorted(
        (box[2] + box[3]) / 2 for (role, _), box in got.items() if role == "joist"
    )
    assert centres == [0.75, *range(16, 113, 16), 119.25]
    for (role, _), box in got.items():
        if role == "joist":
            assert box[:2] == (1.5, 142.5)


def test_no_sill_drops_the_framing_to_the_base() -> None:
    got = boxes(members({"sill_plate": "no"}))
    assert Counter(role for role, _ in got) == {"joist": 10, "rim": 2}
    assert got[("rim", 0)][4:] == (0, 7.25)
    assert spec({"sill_plate": "no"}).framing_top == 7.25


def test_the_elevation_lifts_every_member() -> None:
    expansion = members({"elevation_mm": 24 * IN})
    got = boxes(expansion)
    assert got[("sill", 0)][4:] == (24, 25.5)
    assert got[("joist", 0)][4:] == (25.5, 32.75)
    assert [m.role for m in expansion].count("level") == 2


def test_a_turned_floor_is_the_axis_floor_rotated() -> None:
    """Every corner is the 0 degree floor's corner turned 30 degrees about the
    start (10, 20): cos 30 = sqrt(3)/2, sin 30 = 1/2, typed by hand."""
    raw = {"start_x_mm": 10 * IN, "start_y_mm": 20 * IN, "direction_deg": 30.0}
    c, s = 3**0.5 / 2, 0.5

    def plan(expansion: list[ExpandedMember]) -> dict[uuid.UUID, list[float]]:
        return {
            m.id: [
                v / IN
                for e in m.feature.params.entities
                if isinstance(e, SketchLine)
                for v in (e.start.x, e.start.y)
            ]
            for m in expansion
            if isinstance(m.feature, SketchFeature)
        }

    straight, turned = plan(members()), plan(members(raw))
    assert straight.keys() == turned.keys()
    for key, xy in straight.items():
        for i in range(0, len(xy), 2):
            x, y = xy[i], xy[i + 1]
            assert turned[key][i] == pytest.approx(10 + x * c - y * s, abs=1e-12)
            assert turned[key][i + 1] == pytest.approx(20 + x * s + y * c, abs=1e-12)


# --- Layout rules and the float class ----------------------------------------------


def test_joist_layout() -> None:
    assert joist_centres(144, 16, 1.5) == [0.75, *range(16, 129, 16), 143.25]
    assert joist_centres(144, 12, 1.5) == [0.75, *range(12, 133, 12), 143.25]
    assert joist_centres(120, 16, 1.5) == [0.75, *range(16, 113, 16), 119.25]
    # 130.25 = 8 x 16 + 2.25: slot 8's face touches the end joist and stays.
    assert joist_slots(130.25, 16, 1.5) == list(range(1, 9))
    assert joist_slots(130.25 - 1e-6, 16, 1.5) == list(range(1, 8))
    assert joist_centres(48, 24, 1.5) == [0.75, 24, 47.25]


def test_a_touching_joist_shares_the_end_joists_face() -> None:
    """A layout joist within 1e-9 in of the end joist takes its face exactly
    (no 1e-10 overlap for the kernel to find)."""
    floor = spec({"width_mm": (130.25 + 5e-10) * IN})
    pieces = {(p.role, p.index): p for p in floor_pieces(floor)}
    assert pieces[("joist", 9)].a1 == pieces[("joist", 1)].a0


def _overlaps(pieces: list[Piece]) -> list[tuple[Piece, Piece]]:
    """Every pair of pieces whose interiors meet (any positive overlap on all
    three axes, with no slack: touching is fine, 1e-15 is not)."""
    found: list[tuple[Piece, Piece]] = []
    for i, p in enumerate(pieces):
        for q in pieces[i + 1 :]:
            if (
                min(p.a1, q.a1) > max(p.a0, q.a0)
                and min(p.b1, q.b1) > max(p.b0, q.b0)
                and min(p.z1, q.z1) > max(p.z0, q.z0)
            ):
                found.append((p, q))
    return found


def test_no_two_members_overlap_over_a_sweep() -> None:
    """The coincident-member float class (DECK, WINDOW-DOOR): over random
    sizes in mm (as a form or a formula sends them), every spacing, both
    joist directions, every joist and sill size, no two members overlap at
    all and every member stays inside the floor's rectangle."""
    rng = random.Random(5)
    sizes = [48.0, 96.0, 130.25, 144.0, 120.0, 191.999999999, 960.0]
    for trial in range(400):
        width = rng.choice(sizes) if trial % 3 == 0 else rng.uniform(48, 960)
        depth = rng.choice(sizes) if trial % 5 == 0 else rng.uniform(48, 960)
        raw = {
            "width_mm": width * IN,
            "depth_mm": depth * IN,
            "joist_spacing_mm": rng.choice([8, 12, 13.7, 16, 19.2, 24]) * IN,
            "joist_direction": rng.choice(["depth", "width"]),
            "joist_profile": rng.choice(["us_2x6", "us_2x8", "us_2x10", "us_2x12"]),
            "sill_profile": rng.choice(["us_2x4", "us_2x6", "us_2x8"]),
            "sill_plate": rng.choice(["yes", "no"]),
            "elevation_mm": rng.uniform(-240, 1200) * IN,
        }
        floor = spec(raw)
        pieces = floor_pieces(floor)
        assert _overlaps(pieces) == [], raw
        for p in pieces:
            assert 0 <= p.a0 < p.a1 <= floor.span_a, (raw, p)
            assert 0 <= p.b0 < p.b1 <= floor.span_b, (raw, p)
        ids = [(p.role, p.index) for p in pieces]
        assert len(set(ids)) == len(ids)


def test_the_axis_floors_do_not_overlap_in_the_world() -> None:
    """On the axes the frame is exact, so the emitted boxes keep the local
    pieces' sharing: none overlaps at any of the four directions."""
    for direction in (0.0, 90.0, 180.0, 270.0, -90.0):
        for along in ("depth", "width"):
            got = list(
                boxes(
                    members(
                        {
                            "start_x_mm": 7 * IN,
                            "start_y_mm": -3 * IN,
                            "direction_deg": direction,
                            "joist_direction": along,
                            "width_mm": (130.25 + 5e-10) * IN,
                        }
                    )
                ).values()
            )
            for i, a in enumerate(got):
                for b in got[i + 1 :]:
                    assert not all(
                        min(a[k + 1], b[k + 1]) > max(a[k], b[k]) for k in (0, 2, 4)
                    ), (direction, along, a, b)


def test_the_frame_is_exact_on_the_axes() -> None:
    frame = FloorFrame.of(spec({"direction_deg": 90.0}))
    assert frame.a_axis == (0.0, 1.0)
    assert frame.b_axis == (-1.0, 0.0)
    assert frame.plan(144, 120) == (-120, 144)


def test_the_largest_densest_floor_fits_the_tree_bound() -> None:
    for along in ("depth", "width"):
        extreme = {
            "width_mm": 960 * IN,
            "depth_mm": 960 * IN,
            "joist_spacing_mm": 8 * IN,
            "joist_direction": along,
            "elevation_mm": 1 * IN,
        }
        assert len(members(extreme)) <= MAX_TREE_FEATURES // 3


if __name__ == "__main__":
    for name in sorted(GOLDEN_MEMBERS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
    SWEEP_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_FIXTURE.write_bytes(gzip.compress(sweep_fixture().encode(), mtime=0))
    sys.stdout.write(f"{SWEEP_FIXTURE.name}: {len(SWEEP)} cases\n")
