"""``loft.window`` and ``loft.door`` 1.4.0: a header the wall's thickness
(HEADER-PLIES, RESEARCH §23).

A built-up header is as thick as the wall it sits in (IRC R602.7): two
1-1/2 in plies and a 1/2 in spacer make a 2x4 wall's 3-1/2 in, and three
plies with two 1/2 in spacers a 2x6 wall's 5-1/2 in. 1.4.0's Header build
fills the wall by default, or keeps two plies with foam between (an
insulated header). Checked by hand: the plies' places in 2x4, 2x6 and 2x8
walls; older releases still frame two plies in a 2x6 wall; a 2x4 wall frames
the same whatever the build; no two members overlap over a sweep; and the
golden ``b2-2x6-walls-header-plies`` (B2's four walls in 2x6 with its door
and window at 1.4.0) is exactly the plugins' output. Its geometry acceptance
is ``services/geometry/tests/test_header_plies_b2.py``.

Regenerate the golden after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_header_plies.py``.
"""

import itertools
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, canonical_inputs, expand
from loft_plugins.builtin.wall import header_plies
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import ChoiceInput

# test_wall's body probe. pytest runs in importlib mode, which puts no test
# directory on sys.path, so add this one (as test_b7_units does).
sys.path.insert(0, str(Path(__file__).parent))
from test_wall import boxes

IN = 25.4
WALL = REGISTRY.get("loft.wall", "1.1.0")
WINDOW = REGISTRY.get("loft.window", "1.4.0")
DOOR = REGISTRY.get("loft.door", "1.4.0")
GOLDEN = "b2-2x6-walls-header-plies"
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000002b6")

Box = tuple[float, ...]


# --- The plies ---------------------------------------------------------------------


def test_the_plies_fill_the_wall_with_half_inch_spacers() -> None:
    """Face plies first (their names hold when the build changes), then the
    inner plies: 2x4 two (one 1/2 in spacer), 2x6 three (two 1/2 in
    spacers: 1.5 + 0.5 + 1.5 + 0.5 + 1.5 = 5.5), 2x8 three (1-3/8 in gaps,
    as four plies need 7.5 in)."""
    assert header_plies(3.5, 1.5, "fill") == [(0, 1.5), (2, 3.5)]
    assert header_plies(5.5, 1.5, "fill") == [(0, 1.5), (4, 5.5), (2, 3.5)]
    assert header_plies(7.25, 1.5, "fill") == [(0, 1.5), (5.75, 7.25), (2.875, 4.375)]
    for depth in (3.5, 5.5, 7.25):
        assert header_plies(depth, 1.5, "two_ply") == [(0, 1.5), (depth - 1.5, depth)]
        assert header_plies(depth, 1.5) == header_plies(depth, 1.5, "two_ply")


def test_1_4_0_adds_header_build_after_the_header() -> None:
    for new in (WINDOW, DOOR):
        old = REGISTRY.get(new.manifest.id, "1.3.0")
        names = [i.name for i in new.manifest.inputs]
        at = names.index("header_profile")
        assert names[at + 1] == "header_build"
        assert [n for n in names if n != "header_build"] == [
            i.name for i in old.manifest.inputs
        ]
        build = new.manifest.inputs[at + 1]
        assert isinstance(build, ChoiceInput)
        assert build.default == "fill"
        assert [o.value for o in build.options] == ["fill", "two_ply"]


# --- One wall ----------------------------------------------------------------------

WALL_ID = uuid.UUID("00000000-0000-0000-0000-0000000002b7")


def hosted(plugin: Any, name: str, host: uuid.UUID, raw: dict[str, Any]) -> Hosted:
    """A door or window naming *host* (a single wall), drawn as the rough
    opening only, measured from the wall's start, as documents hands it to
    the wall."""
    feature_id = uuid.uuid5(host, name)
    ref = FeatureRef(kind="feature", feature_id=host)
    values: dict[str, Any] = {"host_wall": ref, "measure_from": "start"}
    if plugin.manifest.version >= "1.3.0":
        values["draw_unit"] = "none"
    inputs = canonical_inputs(plugin.manifest, {**values, **raw})
    return Hosted(
        feature_id,
        plugin.manifest.id,
        plugin.manifest.version,
        name,
        ExpandInputs(feature_id, inputs),
    )


def wall(
    raw: dict[str, Any],
    openings: tuple[Hosted, ...] = (),
    feature_id: uuid.UUID = WALL_ID,
) -> list[ExpandedMember]:
    inputs = canonical_inputs(WALL.manifest, raw)
    return expand(WALL, feature_id, inputs, {}, hosted=openings)


def headers(members: list[ExpandedMember]) -> list[tuple[float, float]]:
    """The header plies' across-wall bounds (Y, in) on an axis wall along X."""
    return [
        (round(b[2], 9) + 0.0, round(b[3], 9) + 0.0)
        for (role, _), b in boxes(members).items()
        if role == "header"
    ]


STUDS = {"2x4": "us_2x4", "2x6": "us_2x6", "2x8": "us_2x8"}


@pytest.mark.parametrize(
    ("stud", "build", "want"),
    [
        ("2x4", "fill", [(-1.5, 0), (-3.5, -2)]),
        ("2x4", "two_ply", [(-1.5, 0), (-3.5, -2)]),
        ("2x6", "fill", [(-1.5, 0), (-5.5, -4), (-3.5, -2)]),
        ("2x6", "two_ply", [(-1.5, 0), (-5.5, -4)]),
        ("2x8", "fill", [(-1.5, 0), (-7.25, -5.75), (-4.375, -2.875)]),
    ],
)
@pytest.mark.parametrize("plugin", [WINDOW, DOOR], ids=["window", "door"])
def test_a_1_4_0_opening_frames_its_build(
    plugin: Any, stud: str, build: str, want: list[tuple[float, float]]
) -> None:
    """The default wall runs along +X, its exterior face at Y 0 and its
    framing to -Y: the exterior ply first, then the interior, then the inner."""
    opening = hosted(
        plugin, "Opening", WALL_ID, {"offset_mm": 72 * IN, "header_build": build}
    )
    got = headers(wall({"stud_profile": STUDS[stud]}, (opening,)))
    assert got == want


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0", "1.3.0"])
def test_older_openings_keep_two_plies_in_a_2x6_wall(version: str) -> None:
    plugin = REGISTRY.get("loft.window", version)
    raw: dict[str, Any] = {"offset_mm": 72 * IN}
    if version == "1.0.0" or version == "1.1.0":
        feature_id = uuid.uuid5(WALL_ID, "Window")
        ref = FeatureRef(kind="feature", feature_id=WALL_ID)
        inputs = canonical_inputs(plugin.manifest, {"host_wall": ref, **raw})
        opening = Hosted(
            feature_id,
            "loft.window",
            version,
            "Window",
            ExpandInputs(feature_id, inputs),
        )
    else:
        opening = hosted(plugin, "Window", WALL_ID, raw)
    got = headers(wall({"stud_profile": "us_2x6"}, (opening,)))
    assert got == [(-1.5, 0), (-5.5, -4)]


def test_a_2x4_wall_frames_1_4_0_as_1_3_0() -> None:
    """In a 2x4 wall the filled header is 1.3.0's two plies: every member,
    id and section the same."""
    old = REGISTRY.get("loft.window", "1.3.0")
    raw = {"offset_mm": 72 * IN}
    new_members = wall({}, (hosted(WINDOW, "Window", WALL_ID, raw),))
    old_members = wall({}, (hosted(old, "Window", WALL_ID, raw),))
    assert [m.model_dump() for m in new_members] == [
        m.model_dump() for m in old_members
    ]


def test_the_face_plies_keep_their_ids_when_the_build_changes() -> None:
    def ids(build: str) -> list[uuid.UUID]:
        raw = {"offset_mm": 72 * IN, "header_build": build}
        members = wall({"stud_profile": "us_2x6"}, (hosted(WINDOW, "W", WALL_ID, raw),))
        return [m.id for m in members if m.role == "header"]

    two, three = ids("two_ply"), ids("fill")
    assert len(two) == 2 and len(three) == 3
    assert three[:2] == two


def _overlap(a: Box, b: Box) -> bool:
    return all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-9 for k in (0, 2, 4))


@pytest.mark.parametrize("stud", ["us_2x6", "us_2x8"])
def test_no_two_members_overlap_over_a_sweep(stud: str) -> None:
    """Doors and windows of every header depth, at positions across the
    layout, filled: no member enters another."""
    for offset, header, kind in itertools.product(
        (30.0, 41.0, 72.0, 97.5),
        ("us_2x6", "us_2x8", "us_2x10", "us_2x12"),
        (WINDOW, DOOR),
    ):
        raw = {"offset_mm": offset * IN, "header_profile": header}
        if kind is WINDOW:
            raw["size"] = "window_2030"
        opening = hosted(kind, "O", WALL_ID, raw)
        members = wall({"stud_profile": stud}, (opening,))
        got = list(boxes(members).values())
        assert sum(1 for m in members if m.role == "header") == 3
        for a, b in itertools.combinations(got, 2):
            assert not _overlap(a, b), (offset, header, kind.manifest.id, a, b)


# --- The golden: B2 in 2x6 ---------------------------------------------------------

#: B2's four walls in 2x6 (buildings.md B2's plan, 144 x 120 outside), drawn
#: clockwise as test_wall.py's B2: the front and back run through, the
#: sides fit between them, 5.5 in deep: front Y 0..5.5 along X from 144,
#: left X 0..5.5 from Y 5.5, back Y 114.5..120 from X 0, right X 138.5..144
#: from Y 114.5 down. Name -> (feature id, raw inputs in inches x 25.4).
B2_2X6: dict[str, tuple[uuid.UUID, dict[str, Any]]] = {
    "front": (
        uuid.UUID("00000000-0000-0000-0000-00000000b611"),
        {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN},
    ),
    "left": (
        uuid.UUID("00000000-0000-0000-0000-00000000b612"),
        {"start_y_mm": 5.5 * IN, "direction_deg": 90.0, "length_mm": 109 * IN},
    ),
    "back": (
        uuid.UUID("00000000-0000-0000-0000-00000000b613"),
        {"start_y_mm": 120 * IN, "direction_deg": 0.0, "length_mm": 144 * IN},
    ),
    "right": (
        uuid.UUID("00000000-0000-0000-0000-00000000b614"),
        {
            "start_x_mm": 144 * IN,
            "start_y_mm": 114.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 109 * IN,
        },
    ),
}

#: B2's door (a 3068: rough opening 38 x 82.5, centred on X 72, wall-local
#: 72 from X 144) and window (a 2030: 24.5 x 36.5 under an 82.5 head,
#: centred on Y 60: wall-local 114.5 - 60 = 54.5), each 1.4.0 at its
#: defaults (2x6 header, Fill the wall), drawn as the rough opening only.
B2_DOOR: dict[str, Any] = {"offset_mm": 72 * IN, "size": "door_3068"}
B2_WINDOW: dict[str, Any] = {"offset_mm": 54.5 * IN, "size": "window_2030"}


def b2_2x6() -> dict[str, list[ExpandedMember]]:
    front, right = B2_2X6["front"][0], B2_2X6["right"][0]
    openings = {
        "front": (hosted(DOOR, "Door 1", front, B2_DOOR),),
        "right": (hosted(WINDOW, "Window 1", right, B2_WINDOW),),
    }
    return {
        name: wall({**raw, "stud_profile": "us_2x6"}, openings.get(name, ()), fid)
        for name, (fid, raw) in B2_2X6.items()
    }


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """The golden's evaluation request (member materials applied, as
    documents sends them) and its members' cut-list metadata."""
    expansion = [m for ms in b2_2x6().values() for m in ms]
    titles = {role.role: role.title for role in WALL.manifest.members}
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
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / GOLDEN / "members.json").read_text() == _members_json(metadata)


def test_b2_in_2x6_frames_three_plies_per_opening() -> None:
    """Typed by hand: the door's three 41 in plies at Y 0..1.5, 4..5.5 and
    2..3.5 over Z 82.5..88, the window's three 27.5 in plies at X 138.5..140,
    142.5..144 and 140.5..142; 66 bodies in all."""
    walls = {name: boxes(ms) for name, ms in b2_2x6().items()}
    door = sorted(b for (r, _), b in walls["front"].items() if r == "header")
    assert door == [
        (51.5, 92.5, y0, y1, 82.5, 88) for y0, y1 in ((0, 1.5), (2, 3.5), (4, 5.5))
    ]
    window = sorted(b for (r, _), b in walls["right"].items() if r == "header")
    assert window == [
        (x0, x1, 46.25, 73.75, 82.5, 88)
        for x0, x1 in ((138.5, 140), (140.5, 142), (142.5, 144))
    ]
    roles = Counter(r for w in walls.values() for r, _ in w)
    assert roles == {
        "stud": 32,
        "king": 4,
        "jack": 4,
        "header": 6,
        "cripple": 4,
        "sill": 1,
        "sill_cripple": 2,
        "top_plate": 8,
        "bottom_plate": 5,
    }
    bodies = [
        m
        for ms in b2_2x6().values()
        for m in ms
        if isinstance(m.feature, ExtrudeFeature)
    ]
    assert len(bodies) == 66


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(_members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
