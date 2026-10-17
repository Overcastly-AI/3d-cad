"""``loft.window`` and ``loft.door`` 1.0.0 hosted in ``loft.wall`` (WINDOW-DOOR).

The framing rules of ``docs/reference-parts/buildings.md`` B2 in the wall's
own frame (u along the wall from its start, v across from the exterior face,
z up from its base), typed from the spec; the hosting contract (only later
features naming a wall reach it, a host that is missing or not a wall is
refused); and the coincident-member sweep the DECK review asked for: across
opening positions and sizes no two members overlap by any amount.
B2's goldens with the door and window are pinned in ``test_wall.py``.
"""

import itertools
import uuid
from collections import Counter
from typing import Any

import pytest
from loft_plugins import (
    REGISTRY,
    ExpandInputs,
    Hosted,
    PluginError,
    canonical_inputs,
    expand,
)
from loft_plugins.builtin.wall import Opening, Piece, WallSpec, wall_pieces
from loft_wire.features import (
    CustomFeature,
    CustomParamsV1,
    DatumFeature,
    DatumOffsetParams,
    ExtrudeFeature,
    FeatureRef,
)
from loft_wire.plugins import FeatureReferenceInput, PluginManifest

IN = 25.4
WALL = REGISTRY.get("loft.wall", "1.0.0")
DOOR = REGISTRY.get("loft.door", "1.0.0")
WINDOW = REGISTRY.get("loft.window", "1.0.0")
WALL_ID = uuid.UUID("00000000-0000-0000-0000-00000000a111")


def wall_spec(raw: dict[str, Any] | None = None) -> WallSpec:
    inputs = canonical_inputs(WALL.manifest, raw or {})
    return WallSpec.from_inputs(ExpandInputs(WALL_ID, inputs))


def opening_inputs(kind: str, raw: dict[str, Any]) -> dict[str, Any]:
    plugin = DOOR if kind == "door" else WINDOW
    ref = FeatureRef(kind="feature", feature_id=WALL_ID)
    return canonical_inputs(plugin.manifest, {"host_wall": ref, **raw})


def opening(kind: str, name: str = "", **raw_in: float) -> Opening:
    raw = {f"{k}_mm": v * IN for k, v in raw_in.items()}
    inputs = ExpandInputs(uuid.uuid4(), opening_inputs(kind, raw))
    return Opening.from_inputs(
        "door" if kind == "door" else "window", name or kind, inputs
    )


def hosted(kind: str, name: str, **raw_in: float) -> Hosted:
    raw = {f"{k}_mm": v * IN for k, v in raw_in.items()}
    feature_id = uuid.uuid5(WALL_ID, name)
    return Hosted(
        feature_id,
        f"loft.{kind}",
        "1.0.0",
        name,
        ExpandInputs(feature_id, opening_inputs(kind, raw)),
    )


def roles(pieces: list[Piece]) -> Counter[str]:
    return Counter(p.role for p in pieces)


def spans(pieces: list[Piece], role: str) -> list[tuple[float, ...]]:
    return [(p.u0, p.u1, p.v0, p.v1, p.z0, p.z1) for p in pieces if p.role == role]


#: buildings.md B2's front wall (144, wall-local = 144 - X) and right side
#: wall (113, wall-local = 116.5 - Y): the door centred on X 72 is local 72,
#: the window centred on Y 60 is local 56.5.
FRONT = wall_spec({"length_mm": 144 * IN})
SIDE = wall_spec({"length_mm": 113 * IN})


# --- B2, typed from the spec -------------------------------------------------------


def test_b2s_door() -> None:
    """Rough opening 38 x 82.5 at 53..91; jacks 81 at 51.5..53 and 91..92.5;
    kings outside them; a header of two 2x6 at 41 over 51.5..92.5, Z
    82.5..88; top cripples 6.125 at 64 and 80; the bottom plate in two 53s;
    8 layout studs, 2 kings, 2 jacks and 2 cripples."""
    got = wall_pieces(FRONT, [opening("door", offset=72)])
    assert roles(got) == {
        "stud": 8,
        "king": 2,
        "jack": 2,
        "header": 2,
        "cripple": 2,
        "top_plate": 2,
        "bottom_plate": 2,
    }
    assert spans(got, "jack") == [
        (51.5, 53, 0, 3.5, 1.5, 82.5),
        (91, 92.5, 0, 3.5, 1.5, 82.5),
    ]
    assert spans(got, "king") == [
        (50, 51.5, 0, 3.5, 1.5, 94.125),
        (92.5, 94, 0, 3.5, 1.5, 94.125),
    ]
    assert spans(got, "header") == [
        (51.5, 92.5, 0, 1.5, 82.5, 88),
        (51.5, 92.5, 2, 3.5, 82.5, 88),  # the 1/2 in spacer between
    ]
    assert spans(got, "cripple") == [
        (63.25, 64.75, 0, 3.5, 88, 94.125),
        (79.25, 80.75, 0, 3.5, 88, 94.125),
    ]
    assert spans(got, "bottom_plate") == [
        (0, 53, 0, 3.5, 0, 1.5),
        (91, 144, 0, 3.5, 0, 1.5),
    ]
    layout = [round((p.u0 + p.u1) / 2, 9) for p in got if p.role == "stud"]
    assert layout == [0.75, 16, 32, 48, 96, 112, 128, 143.25]


def test_b2s_window() -> None:
    """24.5 x 36.5 centred on local 56.5, head 82.5, sill at 46: header two
    2x6 at 27.5, jacks 81, a flat sill 24.5 at Z 44.5..46, top cripples 6.125
    and bottom cripples 43 at local 48 and 64; 6 layout studs, 2 kings, 2
    jacks, 4 cripples; the bottom plate whole."""
    got = wall_pieces(SIDE, [opening("window", offset=56.5)])
    assert roles(got) == {
        "stud": 6,
        "king": 2,
        "jack": 2,
        "header": 2,
        "cripple": 2,
        "sill": 1,
        "sill_cripple": 2,
        "top_plate": 2,
        "bottom_plate": 1,
    }
    assert spans(got, "sill") == [(44.25, 68.75, 0, 3.5, 44.5, 46)]
    assert [s[1] - s[0] for s in spans(got, "header")] == [27.5, 27.5]
    assert [s[5] - s[4] for s in spans(got, "jack")] == [81, 81]
    assert spans(got, "cripple") == [
        (47.25, 48.75, 0, 3.5, 88, 94.125),
        (63.25, 64.75, 0, 3.5, 88, 94.125),
    ]
    assert spans(got, "sill_cripple") == [
        (47.25, 48.75, 0, 3.5, 1.5, 44.5),
        (63.25, 64.75, 0, 3.5, 1.5, 44.5),
    ]
    assert spans(got, "bottom_plate") == [(0, 113, 0, 3.5, 0, 1.5)]


def test_the_three_edits() -> None:
    """Door moved 24 in: 7 layout studs and 3 top cripples (centres X 80, 96,
    112 = local 64, 48, 32); window 24 -> 30: header 33.5, sill 30.5, still 2
    and 2 cripples; door deleted: 10 full studs, one 144 bottom plate."""
    moved = wall_pieces(FRONT, [opening("door", offset=48)])
    assert roles(moved)["stud"] == 7
    assert roles(moved)["king"] == 2 and roles(moved)["jack"] == 2
    centres = sorted(144 - (s[0] + s[1]) / 2 for s in spans(moved, "cripple"))
    assert centres == [80, 96, 112]
    wide = wall_pieces(SIDE, [opening("window", offset=56.5, width=30)])
    assert [s[1] - s[0] for s in spans(wide, "header")] == [33.5, 33.5]
    assert [s[1] - s[0] for s in spans(wide, "sill")] == [30.5]
    assert roles(wide)["cripple"] == 2 and roles(wide)["sill_cripple"] == 2
    deleted = wall_pieces(FRONT, [])
    assert roles(deleted)["stud"] == 10
    assert spans(deleted, "bottom_plate") == [(0, 144, 0, 3.5, 0, 1.5)]


def test_no_member_crosses_an_opening() -> None:
    for wall, item in [
        (FRONT, opening("door", offset=72)),
        (FRONT, opening("door", offset=48)),
        (SIDE, opening("window", offset=56.5)),
        (SIDE, opening("window", offset=56.5, width=30)),
    ]:
        u0, u1 = item.centre - item.width / 2, item.centre + item.width / 2
        for p in wall_pieces(wall, [item]):
            inside = min(p.u1, u1) > max(p.u0, u0) and min(p.z1, item.head) > max(
                p.z0, item.sill
            )
            assert not inside, p


# --- The sweep: no coincident members, ever ----------------------------------------


def _overlaps(pieces: list[Piece]) -> list[tuple[Piece, Piece]]:
    """Pairs that share any volume at all (strictly positive on all three
    axes): touching is fine, one ulp of overlap is not."""
    out: list[tuple[Piece, Piece]] = []
    for a, b in itertools.combinations(pieces, 2):
        if (
            min(a.u1, b.u1) > max(a.u0, b.u0)
            and min(a.v1, b.v1) > max(a.v0, b.v0)
            and min(a.z1, b.z1) > max(a.z0, b.z0)
        ):
            out.append((a, b))
    return out


def _fits(wall: WallSpec, items: list[Opening]) -> list[Piece] | None:
    try:
        return wall_pieces(wall, items)
    except PluginError:
        return None


@pytest.mark.parametrize(
    "wall_raw",
    [
        {"length_mm": 144 * IN},
        {"length_mm": 113 * IN, "stud_spacing_mm": 24 * IN},
        {"length_mm": 157.3 * IN, "stud_profile": "us_2x6", "top_plate": "single"},
        {"length_mm": 3000.0, "stud_spacing_mm": 400.0, "elevation_mm": 7.0},
    ],
)
def test_no_members_overlap_across_positions_and_sizes(
    wall_raw: dict[str, Any],
) -> None:
    """Doors and windows at offsets in steps of 1.37 in (so their faces land
    near, on and past layout studs), several widths and heads, one and two at
    a time: every member at most touches its neighbours."""
    wall = wall_spec(wall_raw)
    built = 0
    widths = [12.5, 24.5, 30.0, 37.875, 71.0]
    offset = 1.0
    while offset < wall.length:
        for width, kind in itertools.product(widths, ("door", "window")):
            head = 70.0 + width / 8 if kind == "window" else 0.0
            item = (
                opening(kind, offset=offset, width=width - 0.5, head_height=head)
                if kind == "window"
                else opening(kind, offset=offset, width=width - 0.5)
            )
            pieces = _fits(wall, [item])
            if pieces is None:
                continue
            built += 1
            assert not _overlaps(pieces), (offset, width, kind)
        offset = round(offset + 1.37, 9)
    assert built > 50
    # Two openings side by side, their kings touching or close.
    first = opening("door", "Door 1", offset=30, width=30)
    for gap in (0.0, 1e-9, 0.1, 0.75, 1.5, 2.25, 16.0):
        second_centre = 30 + 15 + 3 + gap + 3 + 15
        second = opening("window", "Window 1", offset=second_centre, width=29.5)
        pieces = _fits(wall, [first, second])
        if pieces is not None:
            assert not _overlaps(pieces), gap


def test_levels_are_shared_by_rounded_height() -> None:
    """WALL-LEVEL-EQ: one datum per distinct bottom elevation, never two a
    hair apart, with a window whose sill sum lands an ulp off."""
    members = expand(
        WALL,
        WALL_ID,
        canonical_inputs(WALL.manifest, {"elevation_mm": 0.1 * IN}),
        {},
        hosted=(
            hosted("window", "W", offset=40, head_height=0.7 + 82.5, height=36.3),
            hosted("door", "D", offset=100.1, height=79.9),
        ),
    )
    offsets = [
        m.feature.params.offset_mm
        for m in members
        if isinstance(m.feature, DatumFeature)
        and isinstance(m.feature.params, DatumOffsetParams)
    ]
    rounded = [round(o / IN, 6) for o in offsets]
    assert len(set(rounded)) == len(rounded)


# --- Refusals ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("items", "field", "words"),
    [
        ([opening("door", offset=10)], "offset_mm", "end studs"),
        ([opening("window", offset=140)], "offset_mm", "end studs"),
        ([opening("window", offset=72, head_height=92)], "head_height_mm", "top plate"),
        ([opening("door", offset=72, height=88)], "height_mm", "top plate"),
        ([opening("window", offset=72, head_height=38)], "head_height_mm", "sill"),
        (
            [
                opening("door", "Door 1", offset=40),
                opening("door", "Door 2", offset=80),
            ],
            "offset_mm",
            "overlaps Door 1",
        ),
    ],
)
def test_an_opening_that_does_not_fit_is_refused_by_name(
    items: list[Opening], field: str, words: str
) -> None:
    with pytest.raises(PluginError) as caught:
        wall_pieces(FRONT, items)
    assert caught.value.code == "plugin_input_invalid"
    assert caught.value.input == field
    assert words in caught.value.message


def _wall_feature(plugin_id: str = "loft.wall") -> CustomFeature:
    plugin = REGISTRY.get(plugin_id, "1.0.0")
    return CustomFeature(
        type="custom",
        version=1,
        params=CustomParamsV1(
            plugin_id=plugin_id,
            plugin_version="1.0.0",
            inputs=canonical_inputs(plugin.manifest, {}),
        ),
    )


def test_the_opening_checks_its_host_and_fit() -> None:
    door_id = uuid.UUID("00000000-0000-0000-0000-0000000d0001")
    good = opening_inputs("door", {"offset_mm": 72 * IN})
    assert expand(DOOR, door_id, good, {WALL_ID: _wall_feature()}) == []
    # Missing, not custom, not a wall.
    with pytest.raises(PluginError, match="names no earlier feature"):
        expand(DOOR, door_id, good, {})
    datum = DatumFeature(
        type="datum",
        version=1,
        params=DatumOffsetParams(base="XY", offset_mm=1.0),
    )
    with pytest.raises(PluginError, match=r"names a datum, not a loft\.wall"):
        expand(DOOR, door_id, good, {WALL_ID: datum})
    with pytest.raises(PluginError, match=r"names a loft\.deck, not a loft\.wall"):
        expand(DOOR, door_id, good, {WALL_ID: _wall_feature("loft.deck")})
    # Past the wall's end: refused on the door's own offset.
    far = opening_inputs("door", {"offset_mm": 130 * IN})
    with pytest.raises(PluginError) as caught:
        expand(DOOR, door_id, far, {WALL_ID: _wall_feature()})
    assert caught.value.input == "offset_mm"


def test_hosted_order_and_unknown_hosted_plugins_change_nothing() -> None:
    inputs = canonical_inputs(WALL.manifest, {})
    door = hosted("door", "Door 1", offset=100)
    window = hosted("window", "Window 1", offset=36)
    stranger = Hosted(uuid.uuid4(), "loft.outlet", "1.0.0", "Outlet", door.inputs)
    a = expand(WALL, WALL_ID, inputs, {}, hosted=(door, window))
    b = expand(WALL, WALL_ID, inputs, {}, hosted=(window, stranger, door))
    assert [m.model_dump(mode="json") for m in a] == [
        m.model_dump(mode="json") for m in b
    ]
    future = Hosted(door.feature_id, "loft.door", "2.0.0", "Door 1", door.inputs)
    with pytest.raises(PluginError, match=r"cannot frame loft\.door 2\.0\.0"):
        expand(WALL, WALL_ID, inputs, {}, hosted=(future,))


def test_a_wall_with_openings_keeps_its_stud_ids() -> None:
    """Openings take their own roles, so studs, plates and their ids keep
    their indices where the layout is unchanged before the opening."""
    inputs = canonical_inputs(WALL.manifest, {})
    plain = {(m.role, m.index): m.id for m in expand(WALL, WALL_ID, inputs, {})}
    framed = {
        (m.role, m.index): m.id
        for m in expand(
            WALL, WALL_ID, inputs, {}, hosted=(hosted("door", "D", offset=72),)
        )
    }
    for key in [("stud", 0), ("stud", 3), ("top_plate", 1), ("bottom_plate", 0)]:
        assert plain[key] == framed[key]
    bodies = [
        m
        for m in expand(
            WALL, WALL_ID, inputs, {}, hosted=(hosted("window", "W", offset=72),)
        )
        if isinstance(m.feature, ExtrudeFeature)
    ]
    titles = {r.role: r.title for r in WALL.manifest.members}
    assert {titles[m.role] for m in bodies} == {
        "Stud",
        "Jack",
        "Header",
        "Cripple",
        "Sill",
        "Top plate",
        "Bottom plate",
    }
    assert {
        m.metadata.profile for m in bodies if m.role == "header" and m.metadata
    } == {"2x6"}


# --- The wire half -----------------------------------------------------------------


def test_a_host_input_names_custom_features_of_named_plugins() -> None:
    host = DOOR.manifest.host_input()
    assert host is not None and host.name == "host_wall"
    assert host.plugin_ids == ["loft.wall"] and host.feature_types == ["custom"]
    with pytest.raises(ValueError, match="host input"):
        FeatureReferenceInput(
            kind="feature",
            name="wall",
            label="Wall",
            feature_types=["datum"],
            plugin_ids=None,
            host=True,
        )
    with pytest.raises(ValueError, match="plugin_ids needs"):
        FeatureReferenceInput(
            kind="feature",
            name="plane",
            label="Plane",
            feature_types=["datum"],
            plugin_ids=["loft.wall"],
        )
    twice = DOOR.manifest.model_dump(mode="json")
    twice["inputs"].append({**twice["inputs"][0], "name": "second_wall"})
    with pytest.raises(ValueError, match="more than one host"):
        PluginManifest.model_validate(twice)
