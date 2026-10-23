"""FLOOR-JOIST-SPAN: ``loft.floor`` 1.3.0's Joists bear on (RESEARCH §23).

Chief Architect frames a floor across its shorter span, and Revit's floor
has a picked span direction. 1.3.0 replaces Joist direction with Joists bear
on: Long walls (the default), Front and back, or Left and right, and reads
an outline's rectangle from its corners, not its first line. Checked against
B7's floor (docs/reference-parts/buildings.md, 288 x 192, 2x10 at 16 in),
typed by hand:

* drawn from any corner in either direction, the default frames the same 19
  joists at 189 across the 16 ft span, which is 1.2.0's floor on B7's
  rectangle exactly, and is the typed 1.1.0 floor at Along the depth;
* Left and right frames 13 joists at 285 (24 ft), rims at 192;
* a typed 1.3.0 floor frames the longer pair as the rims too, and its
  default is 1.1.0's at B5's defaults;
* stored 1.2.0 floors still follow their first line (byte-identical).

The geometry goldens ``b7-floor-long-walls`` and ``b7-floor-left-right`` are
written from here and pinned by this module. Regenerate after a deliberate
change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_floor_joist_span.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, canonical_inputs
from loft_plugins.builtin.house import floor_of
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import ChoiceInput

# The B7 builders and body probes are test_building_outline's (pytest runs in
# importlib mode, which puts no test directory on sys.path).
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    B7_FLOOR,
    FLOOR_ID,
    GOLDENS,
    IN,
    SKETCH_ID,
    TITLES,
    boxes,
    envelope,
    expand,
    loop_sketch,
    members_json,
    overlaps,
    rectangle,
    ref,
)

FLOOR_1_3 = REGISTRY.get("loft.floor", "1.3.0")
FLOOR_1_2 = REGISTRY.get("loft.floor", "1.2.0")
FLOOR_1_1 = REGISTRY.get("loft.floor", "1.1.0")

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000007f3")
GOLDEN_LONG = "b7-floor-long-walls"
GOLDEN_LEFT_RIGHT = "b7-floor-left-right"

#: B7's rectangle, counter-clockwise from the origin.
B7_CORNERS = [(0.0, 0.0), (288.0, 0.0), (288.0, 192.0), (0.0, 192.0)]


def drawn_from(start: int, clockwise: bool) -> SketchFeature:
    """B7's 288 x 192 rectangle drawn from corner *start* of
    :data:`B7_CORNERS`, either way round, its first two lines dimensioned
    and the corner at (0, 0) fixed on the origin."""
    corners = B7_CORNERS[start:] + B7_CORNERS[:start]
    if clockwise:
        corners = [corners[0], *reversed(corners[1:])]
    n = len(corners)
    dims = {
        f"e{k + 1}": abs(corners[k + 1][0] - corners[k][0])
        + abs(corners[k + 1][1] - corners[k][1])
        for k in (0, 1)
    }
    at_origin = corners.index((0.0, 0.0))
    anchor = {
        "kind": "coincident",
        "a": {"entity": f"e{at_origin + 1}", "point": "start"},
        "b": {"entity": "origin", "point": "position"},
    }
    assert n == 4
    return loop_sketch(corners, dims, anchor=False, extra=[anchor])


DRAWINGS = [(start, cw) for start in range(4) for cw in (False, True)]


def floor_on(
    sketch: SketchFeature, plugin: Any = FLOOR_1_3, **raw: Any
) -> list[ExpandedMember]:
    return expand(
        plugin,
        FLOOR_ID,
        {"outline": ref(SKETCH_ID), **B7_FLOOR, **raw},
        {SKETCH_ID: sketch},
    )


def lengths(members: list[ExpandedMember], role: str) -> Counter[float]:
    """Each *role* body's length along its longer plan side (in)."""
    out: Counter[float] = Counter()
    for x0, x1, y0, y1, *_ in boxes(members, (role,)):
        out[round(max(x1 - x0, y1 - y0), 6)] += 1
    return out


# --- The manifest -------------------------------------------------------------------


def test_joists_bear_on_replaces_joist_direction_in_place() -> None:
    old = [item.name for item in FLOOR_1_2.manifest.inputs]
    new = [item.name for item in FLOOR_1_3.manifest.inputs]
    assert new == [
        "joists_bear_on" if name == "joist_direction" else name for name in old
    ]
    bear = next(i for i in FLOOR_1_3.manifest.inputs if i.name == "joists_bear_on")
    assert isinstance(bear, ChoiceInput)
    assert bear.label == "Joists bear on"
    assert bear.default == "long_walls"
    assert [(o.value, o.label) for o in bear.options] == [
        ("long_walls", "Long walls"),
        ("front_back", "Front and back"),
        ("left_right", "Left and right"),
    ]
    assert bear.superseded_by is None  # used on a typed floor and an outline


# --- B7 on its outline --------------------------------------------------------------


@pytest.mark.parametrize(("start", "clockwise"), DRAWINGS)
def test_b7_frames_the_16_ft_span_however_it_is_drawn(
    start: int, clockwise: bool
) -> None:
    """Every drawing is the default on the Rectangle tool's drawing, which
    is 1.2.0's floor on it and the typed floor exactly: 19 joists at 189."""
    got = floor_on(drawn_from(start, clockwise))
    assert got == floor_on(rectangle(288, 192), FLOOR_1_2)
    assert got == expand(
        FLOOR_1_1,
        FLOOR_ID,
        {"width_mm": 288 * IN, "depth_mm": 192 * IN, **B7_FLOOR},
        {},
    )
    assert lengths(got, "joist") == Counter({189.0: 19})
    assert lengths(got, "rim") == Counter({288.0: 2})
    assert lengths(got, "sill") == Counter({288.0: 2, 181.0: 2})


def test_1_2_0_followed_the_first_line() -> None:
    """The bug: 1.2.0 on B7 drawn from a corner up its left side framed 24 ft
    joists. Its expansion stays as stored."""
    got = floor_on(drawn_from(3, False), FLOOR_1_2)
    assert lengths(got, "joist") == Counter({285.0: 13})


@pytest.mark.parametrize(("start", "clockwise"), DRAWINGS)
def test_front_and_back_and_left_and_right_turn_the_joists(
    start: int, clockwise: bool
) -> None:
    sketch = drawn_from(start, clockwise)
    front_back = floor_on(sketch, joists_bear_on="front_back")
    assert front_back == floor_on(sketch)
    left_right = floor_on(sketch, joists_bear_on="left_right")
    assert left_right == expand(
        FLOOR_1_1,
        FLOOR_ID,
        {
            "width_mm": 288 * IN,
            "depth_mm": 192 * IN,
            "joist_direction": "width",
            **B7_FLOOR,
        },
        {},
    )
    # Joists along X: 0.75, 16 .. 176, 191.25 along Y; 1.5 .. 286.5 long.
    assert lengths(left_right, "joist") == Counter({285.0: 13})
    assert lengths(left_right, "rim") == Counter({192.0: 2})
    assert lengths(left_right, "sill") == Counter({192.0: 2, 277.0: 2})
    centres = sorted(
        (y0 + y1) / 2 for _, _, y0, y1, *_ in boxes(left_right, ("joist",))
    )
    assert centres == [0.75, *(16.0 * k for k in range(1, 12)), 191.25]
    # 15 panels: six 48 rows along X, each 96 + 96 or 48 + 96 + 48 along Y.
    assert len(boxes(left_right, ("subfloor",))) == 15
    assert overlaps(boxes(left_right)) == []


def test_a_square_bears_on_the_front_and_back() -> None:
    sketch = loop_sketch(
        [(0.0, 0.0), (192.0, 0.0), (192.0, 192.0), (0.0, 192.0)],
        {"e1": 192, "e2": 192},
    )
    assert floor_on(sketch) == floor_on(sketch, joists_bear_on="front_back")


def test_off_the_origin_the_rectangle_starts_at_its_least_corner() -> None:
    sketch = drawn_from(2, True).model_dump(mode="json")
    for e in sketch["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": -24 * IN, "y": 36 * IN}
    got = floor_on(SketchFeature.model_validate(sketch))
    xs = [v for b in boxes(got) for v in b[:2]]
    ys = [v for b in boxes(got) for v in b[2:4]]
    assert (min(xs), max(xs), min(ys), max(ys)) == (-24.0, 264.0, 36.0, 228.0)
    assert lengths(got, "joist") == Counter({189.0: 19})


# --- A typed floor ------------------------------------------------------------------


def test_a_typed_floor_bears_on_its_long_walls() -> None:
    def typed(plugin: Any, **raw: Any) -> list[ExpandedMember]:
        return expand(plugin, FLOOR_ID, raw, {})

    # B5's defaults (144 x 120): the joists along the depth, as before.
    assert typed(FLOOR_1_3) == typed(FLOOR_1_1)
    deep = {"width_mm": 120 * IN, "depth_mm": 144 * IN}
    assert typed(FLOOR_1_3, **deep) == typed(FLOOR_1_1, **deep, joist_direction="width")
    assert typed(FLOOR_1_3, **deep, joists_bear_on="front_back") == typed(
        FLOOR_1_1, **deep
    )
    assert typed(FLOOR_1_3, joists_bear_on="left_right") == typed(
        FLOOR_1_1, joist_direction="width"
    )


def test_a_wall_on_a_1_3_0_floor_stands_on_its_subfloor() -> None:
    sketch = drawn_from(1, True)
    for bearing in ("long_walls", "left_right"):
        stored = envelope(
            FLOOR_1_3,
            {"outline": ref(SKETCH_ID), **B7_FLOOR, "joists_bear_on": bearing},
        )
        # A 1.3.0 floor stores no joist_direction: floor_of must rewrite it.
        inputs = ExpandInputs(uuid.uuid4(), {}, {SKETCH_ID: sketch, FLOOR_ID: stored})
        assert floor_of(ref(FLOOR_ID), inputs).top == 1.5 + 9.25 + 23 / 32


# --- The goldens --------------------------------------------------------------------


def golden(bearing: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B7's floor alone on its outline drawn from the back-left corner down
    its left side (the drawing 1.2.0 turned), bearing on *bearing*."""
    sketch = drawn_from(3, False)
    members = floor_on(sketch, joists_bear_on=bearing)
    features = [EvaluatedFeatureInput(id=SKETCH_ID, feature=sketch)]
    features += [EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members]
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=features,
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in members if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=TITLES[m.role], metadata=m.metadata
        )
        for m in members
        if m.metadata is not None
    ]
    return request, metadata


GOLDEN_BEARINGS = {GOLDEN_LONG: "long_walls", GOLDEN_LEFT_RIGHT: "left_right"}


@pytest.mark.parametrize("name", sorted(GOLDEN_BEARINGS))
def test_the_golden_is_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(GOLDEN_BEARINGS[name])
    folder = GOLDENS / name
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_canonical_inputs_store_the_default() -> None:
    stored = canonical_inputs(FLOOR_1_3.manifest, {})
    assert stored["joists_bear_on"] == "long_walls"
    assert "joist_direction" not in stored


if __name__ == "__main__":
    for name, bearing in GOLDEN_BEARINGS.items():
        request, metadata = golden(bearing)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
    _ = AuthoredEnvelope  # re-exported for type checkers of callers
