"""WALL-MEMBER-RENUMBER: ``loft.wall`` 1.1.0 and ``loft.deck`` 1.1.0 name each
member by its place in the layout, so an edit elsewhere never hands its id to
another member.

1.0.0 numbered members in emission order: moving B2's door 24 in turned the
front wall's ``stud/6`` from the stud at 128 along the wall into the end stud
at 143.25, and widening B1 turned ``joist/12`` from the end joist into a layout
joist. A feature on that member (a hole, as a Boolean subtract whose target is
the stud) silently moved to another member or cut nothing. 1.1.0 emits the
same members in the same order, with the same geometry, under stable names:
``stud/slot/8``, ``stud/end``, ``king/opening/<door-id>/0``, ``joist/end``.

The geometry goldens ``b2-walls-v1.1-hole-*`` and ``plugin-deck-v1.1-b1-*``
are B2's walls and B1's deck at 1.1.0 with a 1 in hole through the stud at
128 and the end joist, before and after the edit (the hole a Boolean subtract
targeting the member by id). The first test asserts the files are exactly
this module's models. Regenerate after a deliberate change with
``uv run python packages/loft-plugins/tests/test_member_names.py``.
"""

import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, canonical_inputs, expand
from loft_plugins.builtin.wall import Opening, WallSpec, wall_pieces
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import member_id
from loft_wire.sketch import Point2D, SketchCircle, SketchLine

IN = 25.4
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
WALL_V1 = REGISTRY.get("loft.wall", "1.0.0")
WALL_V1_1 = REGISTRY.get("loft.wall", "1.1.0")
DECK_V1 = REGISTRY.get("loft.deck", "1.0.0")
DECK_V1_1 = REGISTRY.get("loft.deck", "1.1.0")

#: The part and features of B2's walls, as test_wall.py draws them: clockwise
#: in plan, framing to the right. Name -> (feature id, raw inputs).
B2_PART = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
B2_WALLS: dict[str, tuple[uuid.UUID, dict[str, Any]]] = {
    "front": (
        uuid.UUID("00000000-0000-0000-0000-00000000a111"),
        {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN},
    ),
    "left": (
        uuid.UUID("00000000-0000-0000-0000-00000000a112"),
        {"start_y_mm": 3.5 * IN, "direction_deg": 90.0, "length_mm": 113 * IN},
    ),
    "back": (
        uuid.UUID("00000000-0000-0000-0000-00000000a113"),
        {"start_y_mm": 120 * IN, "direction_deg": 0.0, "length_mm": 144 * IN},
    ),
    "right": (
        uuid.UUID("00000000-0000-0000-0000-00000000a114"),
        {
            "start_x_mm": 144 * IN,
            "start_y_mm": 116.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 113 * IN,
        },
    ),
}
B1_PART = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-00000000dec1")


def _hosted(plugin_id: str, name: str, host: uuid.UUID, raw: dict[str, Any]) -> Hosted:
    """A door or window naming *host*, as documents hands it to the wall."""
    plugin = REGISTRY.get(plugin_id, "1.0.0")
    feature_id = uuid.uuid5(host, name)
    ref = FeatureRef(kind="feature", feature_id=host)
    inputs = canonical_inputs(plugin.manifest, {"host_wall": ref, **raw})
    return Hosted(
        feature_id, plugin_id, "1.0.0", name, ExpandInputs(feature_id, inputs)
    )


def b2(
    version: str = "1.1.0",
    spacing: float = 16.0,
    door: dict[str, Any] | None = None,
    window: dict[str, Any] | None = None,
) -> dict[str, list[ExpandedMember]]:
    """B2's four walls at *version*, the door in the front wall and the
    window in the right side wall when given (raw inputs)."""
    plugin = REGISTRY.get("loft.wall", version)
    openings: dict[str, tuple[Hosted, ...]] = {}
    if door is not None:
        openings["front"] = (
            _hosted("loft.door", "Door 1", B2_WALLS["front"][0], door),
        )
    if window is not None:
        openings["right"] = (
            _hosted("loft.window", "Window 1", B2_WALLS["right"][0], window),
        )
    return {
        name: expand(
            plugin,
            feature_id,
            canonical_inputs(plugin.manifest, {**raw, "stud_spacing_mm": spacing * IN}),
            {},
            hosted=openings.get(name, ()),
        )
        for name, (feature_id, raw) in B2_WALLS.items()
    }


def deck(version: str = "1.1.0", **raw: Any) -> list[ExpandedMember]:
    plugin = REGISTRY.get("loft.deck", version)
    inputs = canonical_inputs(
        plugin.manifest, {"width_mm": 192 * IN, "depth_mm": 144 * IN, **raw}
    )
    return expand(plugin, DECK_ID, inputs, {})


B2_DOOR = {"offset_mm": 72 * IN}
B2_DOOR_MOVED = {"offset_mm": 48 * IN}
B2_WINDOW = {"offset_mm": 56.5 * IN}


def by_name(members: list[ExpandedMember], role: str, name: str) -> ExpandedMember:
    found = [m for m in members if m.role == role and m.name == name]
    assert len(found) == 1, (role, name)
    return found[0]


def plan_box(
    members: list[ExpandedMember], member: ExpandedMember
) -> tuple[float, ...]:
    """A member's plan rectangle (in): x0, x1, y0, y1, from its section."""
    assert isinstance(member.feature, ExtrudeFeature)
    section = next(
        m for m in members if m.id == member.feature.params.profile.feature_id
    )
    assert isinstance(section.feature, SketchFeature)
    lines = [e for e in section.feature.params.entities if isinstance(e, SketchLine)]
    xs = [round(p / IN, 9) for e in lines for p in (e.start.x, e.end.x)]
    ys = [round(p / IN, 9) for e in lines for p in (e.start.y, e.end.y)]
    return (min(xs), max(xs), min(ys), max(ys))


# --- The hole: a Boolean subtract whose target is the member ----------------------


def _id(part: uuid.UUID, name: str) -> uuid.UUID:
    return uuid.uuid5(part, name)


def drill(
    part: uuid.UUID,
    target: uuid.UUID,
    plane: DatumPlaneRef | tuple[str, float],
    centre: tuple[float, float],
    through: float,
) -> list[EvaluatedFeatureInput]:
    """A 1 in hole through the body *target* names, as a multi-body user cuts
    one body (Fusion's Combine > Cut): a circle sketched on *plane* (an origin
    plane, or ``(base, offset in)`` for an offset datum) at *centre* (in, the
    plane's own x and y), extruded symmetric *through* in as a new body and
    subtracted from the target. The tool body is consumed."""
    entries: list[EvaluatedFeatureInput] = []
    if isinstance(plane, DatumPlaneRef):
        sketch_plane: DatumPlaneRef | FeatureRef = plane
    else:
        base, offset = plane
        datum = _id(part, "hole/datum")
        assert base in ("XY", "XZ", "YZ")
        entries.append(
            EvaluatedFeatureInput(
                id=datum,
                feature=DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(
                        base=base,  # pyright: ignore[reportArgumentType]
                        offset_mm=offset * IN,
                    ),
                ),
            )
        )
        sketch_plane = FeatureRef(kind="feature", feature_id=datum)
    sketch, tool, cut = (_id(part, f"hole/{n}") for n in ("sketch", "tool", "cut"))
    entries += [
        EvaluatedFeatureInput(
            id=sketch,
            feature=SketchFeature(
                type="sketch",
                version=1,
                params=SketchParamsV1(
                    plane=sketch_plane,
                    entities=[
                        SketchCircle(
                            id="c1",
                            kind="circle",
                            center=Point2D(x=centre[0] * IN, y=centre[1] * IN),
                            radius=0.5 * IN,
                        )
                    ],
                    constraints=[],
                ),
            ),
        ),
        EvaluatedFeatureInput(
            id=tool,
            feature=ExtrudeFeature(
                type="extrude",
                version=1,
                params=ExtrudeParamsV1(
                    profile=FeatureRef(kind="feature", feature_id=sketch),
                    distance_mm=through * IN,
                    operation="add",
                    merge=False,
                    extent="symmetric",
                ),
            ),
        ),
        EvaluatedFeatureInput(
            id=cut,
            feature=BooleanFeature(
                type="boolean",
                version=1,
                params=BooleanParamsV1(
                    operation="subtract",
                    target=FeatureRef(kind="feature", feature_id=target),
                    tool=FeatureRef(kind="feature", feature_id=tool),
                ),
            ),
        ),
    ]
    return entries


def _golden(
    part: uuid.UUID,
    expansion: list[ExpandedMember],
    hole: list[EvaluatedFeatureInput],
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    plugin = WALL_V1_1 if part == B2_PART else DECK_V1_1
    titles = {role.role: role.title for role in plugin.manifest.members}
    request = EvaluateTreeRequest(
        part_id=part,
        tree_version=1,
        features=[
            *(EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion),
            *hole,
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


def _wall_golden(
    door: dict[str, Any],
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B2 at 1.1.0 with its window and *door*, and a hole along Y through the
    front wall's stud at 128 along the wall (world X 16) at Z 48."""
    walls = b2(door=door, window=B2_WINDOW)
    stud = by_name(walls["front"], "stud", "slot/8")
    hole = drill(
        B2_PART, stud.id, DatumPlaneRef(kind="datum_plane", plane="XZ"), (16, 48), 7
    )
    return _golden(B2_PART, [m for ms in walls.values() for m in ms], hole)


def _deck_golden(width_ft: int) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B1 at 1.1.0, *width_ft* wide, and a hole along X through the end joist
    (its centre plane X = width - 0.75) at Y 72, mid-depth Z 24.375."""
    width = width_ft * 12
    members = deck(width_mm=width * IN)
    joist = by_name(members, "joist", "end")
    hole = drill(B1_PART, joist.id, ("YZ", width - 0.75), (72, 24.375), 3)
    return _golden(B1_PART, members, hole)


GOLDENS_1_1: dict[
    str, Callable[[], tuple[EvaluateTreeRequest, list[CutListMember]]]
] = {
    "b2-walls-v1.1-hole-stud-128": lambda: _wall_golden(B2_DOOR),
    "b2-walls-v1.1-hole-door-moved-24": lambda: _wall_golden(B2_DOOR_MOVED),
    "plugin-deck-v1.1-b1-16ft-hole-end-joist": lambda: _deck_golden(16),
    "plugin-deck-v1.1-b1-20ft-hole-end-joist": lambda: _deck_golden(20),
}


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


@pytest.mark.parametrize("name", sorted(GOLDENS_1_1))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = GOLDENS_1_1[name]()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


def test_the_hole_targets_one_member_before_and_after_each_edit() -> None:
    """The acceptance: the same id names the stud at 128 with the door at 72
    and at 48, and the end joist at 16 and at 20 ft."""

    def target(name: str) -> uuid.UUID:
        request, _ = GOLDENS_1_1[name]()
        cut = request.features[-1].feature
        assert isinstance(cut, BooleanFeature)
        return cut.params.target.feature_id

    stud = member_id(B2_WALLS["front"][0], "stud", 0, "slot/8")
    assert target("b2-walls-v1.1-hole-stud-128") == stud
    assert target("b2-walls-v1.1-hole-door-moved-24") == stud
    end = member_id(DECK_ID, "joist", 0, "end")
    assert target("plugin-deck-v1.1-b1-16ft-hole-end-joist") == end
    assert target("plugin-deck-v1.1-b1-20ft-hole-end-joist") == end


# --- 1.1.0 is 1.0.0 renamed ---------------------------------------------------------


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


WALL_CASES: dict[str, dict[str, Any]] = {
    "b2 16 oc": {},
    "b2 24 oc": {"spacing": 24.0},
    "b2 door and window": {"door": B2_DOOR, "window": B2_WINDOW},
    "b2 door moved": {"door": B2_DOOR_MOVED, "window": B2_WINDOW},
    "b2 window 30": {"door": B2_DOOR, "window": {**B2_WINDOW, "width_mm": 30 * IN}},
    "b2 19.2 oc with openings": {
        "spacing": 19.2,
        "door": B2_DOOR,
        "window": B2_WINDOW,
    },
}


@pytest.mark.parametrize("case", sorted(WALL_CASES))
def test_a_1_1_wall_is_the_1_0_wall_renamed(case: str) -> None:
    old, new = b2("1.0.0", **WALL_CASES[case]), b2("1.1.0", **WALL_CASES[case])
    for name in B2_WALLS:
        _renamed(old[name], new[name])


DECK_CASES: dict[str, dict[str, Any]] = {
    "b1": {},
    "b1 20 ft": {"width_mm": 240 * IN},
    "freestanding": {"attachment": "freestanding"},
    "freestanding along": {"attachment": "freestanding", "joist_direction": "along"},
    "flush beam, blocking, no rims": {
        "beam_position": "flush",
        "blocking": "midspan",
        "rim_joists": "no",
    },
    "freestanding flush, 3 plies": {
        "attachment": "freestanding",
        "beam_position": "flush",
        "beam_plies": 3,
    },
    "guard": {"guard": "open_sides"},
    "guard freestanding 20 ft": {
        "guard": "open_sides",
        "attachment": "freestanding",
        "width_mm": 240 * IN,
    },
}


@pytest.mark.parametrize("case", sorted(DECK_CASES))
def test_a_1_1_deck_is_the_1_0_deck_renamed(case: str) -> None:
    _renamed(deck("1.0.0", **DECK_CASES[case]), deck("1.1.0", **DECK_CASES[case]))


# --- Names survive the edits that renumbered 1.0.0 ---------------------------------


def test_moving_the_door_renames_no_stud_it_does_not_touch() -> None:
    """B2's first edit, door 72 -> 48 along the front wall: under 1.0.0
    stud/6 is the stud at 128 before and the end stud at 143.25 after; under
    1.1.0 every stud outside both framings keeps its name, id and place, and
    the moved door's members keep theirs (named after the door)."""
    old_before = b2("1.0.0", door=B2_DOOR)["front"]
    old_after = b2("1.0.0", door=B2_DOOR_MOVED)["front"]
    stud6 = next(m for m in old_before if (m.role, m.index) == ("stud", 6))
    moved6 = next(m for m in old_after if (m.role, m.index) == ("stud", 6))
    assert stud6.id == moved6.id
    # wall-local 128 is world X 16; the end stud at 143.25 is world X 0.75.
    assert plan_box(old_before, stud6)[:2] == (15.25, 16.75)
    assert plan_box(old_after, moved6)[:2] == (0.0, 1.5)

    before = b2(door=B2_DOOR)["front"]
    after = b2(door=B2_DOOR_MOVED)["front"]
    stud = by_name(before, "stud", "slot/8")
    assert by_name(after, "stud", "slot/8").id == stud.id
    for name in ("start", "slot/1", "slot/6", "slot/7", "slot/8", "end"):
        a, b = by_name(before, "stud", name), by_name(after, "stud", name)
        assert a.id == b.id and plan_box(before, a) == plan_box(after, b), name
    door = _hosted("loft.door", "Door 1", B2_WALLS["front"][0], B2_DOOR).feature_id
    for role in ("king", "jack", "header"):
        for k in (0, 1):
            name = f"opening/{door}/{k}"
            assert by_name(before, role, name).id == by_name(after, role, name).id


def test_widening_the_deck_keeps_the_end_joist() -> None:
    """B1's 16 -> 20 ft edit: under 1.0.0 joist/12 is the end joist at 16 ft
    and a layout joist at 20 ft; under 1.1.0 joist/end is the end joist at
    both widths, and every layout joist keeps its slot."""
    old16, old20 = deck("1.0.0"), deck("1.0.0", width_mm=240 * IN)
    j12 = next(m for m in old16 if (m.role, m.index) == ("joist", 12))
    j12_after = next(m for m in old20 if (m.role, m.index) == ("joist", 12))
    assert plan_box(old16, j12)[:2] == (190.5, 192.0)
    assert plan_box(old20, j12_after)[:2] == (191.25, 192.75)

    new16, new20 = deck(), deck(width_mm=240 * IN)
    end16, end20 = by_name(new16, "joist", "end"), by_name(new20, "joist", "end")
    assert end16.id == end20.id
    assert plan_box(new16, end16)[:2] == (190.5, 192.0)
    assert plan_box(new20, end20)[:2] == (238.5, 240.0)
    for n in range(1, 12):
        a, b = (
            by_name(new16, "joist", f"slot/{n}"),
            by_name(new20, "joist", f"slot/{n}"),
        )
        assert a.id == b.id and plan_box(new16, a) == plan_box(new20, b)
    assert by_name(new20, "joist", "slot/14").name == "slot/14"


def test_names_are_places_not_counts() -> None:
    """A layout member is named by its slot (n x spacing from the start);
    a flush beam's bays, ply lines, posts, boards and guard members by
    where they are."""
    walls = b2(door=B2_DOOR)
    names = [m.name for m in walls["front"] if m.role == "stud"]
    assert names == [
        "start",
        "slot/1",
        "slot/2",
        "slot/3",
        "slot/6",
        "slot/7",
        "slot/8",
        "end",
    ]
    levels = sorted(str(m.name) for m in walls["front"] if m.role == "level")
    assert levels == ["z/1.5", "z/82.5", "z/88", "z/94.125", "z/95.625"]
    bottom = [m.name for m in walls["front"] if m.role == "bottom_plate"]
    door = _hosted("loft.door", "Door 1", B2_WALLS["front"][0], B2_DOOR).feature_id
    assert bottom == ["start", f"opening/{door}"]
    free = deck(attachment="freestanding", beam_position="flush")
    assert [m.name for m in free if m.role == "beam"] == [
        "house/ply/0",
        "house/ply/1",
        "outer/ply/0",
        "outer/ply/1",
    ]
    joists = [str(m.name) for m in free if m.role == "joist"]
    assert joists[:3] == ["start/bay/0", "start/bay/1", "start/bay/2"]
    assert joists[-1] == "end/bay/2"
    guard = deck(guard="open_sides")
    posts = [m.name for m in guard if m.role == "guard_post"]
    assert posts[0] == "left/0" and "front/1" in posts and posts[-1] == "right/2"


# --- Coincident faces: the float class (1.1.0 compares with a tolerance) ---------


def _door_wall(offset_mm: float) -> tuple[WallSpec, Opening]:
    """A 400 in wall on 400 mm centres with a 600 mm door at *offset_mm*."""
    wall = WallSpec.from_inputs(
        ExpandInputs(
            uuid.uuid4(),
            canonical_inputs(
                WALL_V1.manifest, {"stud_spacing_mm": 400.0, "length_mm": 400 * IN}
            ),
        )
    )
    door = REGISTRY.get("loft.door", "1.0.0")
    ref = FeatureRef(kind="feature", feature_id=uuid.uuid4())
    inputs = canonical_inputs(
        door.manifest, {"host_wall": ref, "width_mm": 600.0, "offset_mm": offset_mm}
    )
    return wall, Opening.from_inputs("door", "Door", ExpandInputs(uuid.uuid4(), inputs))


@pytest.mark.parametrize(
    ("offset_mm", "role", "exact", "v1_0"),
    [
        # The 4th layout stud's left face is the left jack's outer face: it
        # lies wholly under the header, so it is a cripple.
        (1944.45, "cripple", 2, 1),
        # The 7th layout stud's left face is the right king's outer face: it
        # touches the framing without entering it, so it stays.
        (2379.35, "stud", 25, 24),
    ],
)
def test_a_stud_that_touches_the_framing_is_kept(
    offset_mm: float, role: str, exact: int, v1_0: int
) -> None:
    """The coincident-member float class: two faces that meet exactly in
    decimal (400 mm centres, a 600 mm door) are an ulp apart in floats, and
    1.0.0's exact comparison drops the stud (or the cripple). 1.1.0 counts
    faces within 1e-9 in as touching; 1.0.0 is pinned as it was released. A
    sweep of 2 044 such constructed touching cases (doors and windows, six
    spacings, seven widths) finds 1.1.0 equal to exact arithmetic in all and
    1.0.0 wrong in 203."""
    wall, door = _door_wall(offset_mm)
    count = sum(p.role == role for p in wall_pieces(wall, [door], named=True))
    assert count == exact
    assert sum(p.role == role for p in wall_pieces(wall, [door])) == v1_0


if __name__ == "__main__":
    for name in sorted(GOLDENS_1_1):
        request, metadata = GOLDENS_1_1[name]()
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
