"""BUILDING-OUTLINE: one sketch drives the walls and the floor, and the roof
picks the walls, each defining the slope or not (Chief Architect, Revit).

Checked against ``docs/reference-parts/buildings.md`` B2 and B7 and the
QA-B7-HOUSE round's build, typed by hand:

* the outline reader solves a fully dimensioned loop in closed form and
  refuses one it cannot (not closed, not horizontal or vertical, not fully
  defined, over-constrained);
* ``loft.wall`` 1.3.0 on B7's 288 x 192 outline is the round's four typed 2x6
  walls (front and back through, the sides fitted between, 181), door and
  windows and OSB, member for member; ``loft.floor`` 1.2.0 on it is the
  round's typed floor exactly; ``loft.roof`` 1.4.0 with the front and back
  defining slope is the round's typed gable exactly, and on B2's outline it
  is ``b2-roof-6-12``'s gable;
* the 288 -> 336 edit is one sketch-dimension edit: the walls, floor and roof
  follow, and a member keeps its id when another wall changes.

The geometry golden ``b7-outline`` and the kernel fixture
``outline-cases.json.gz`` are written from here and pinned by this module.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_building_outline.py``.
"""

import gzip
import itertools
import json
import math
import random
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, PluginError, canonical_inputs
from loft_plugins import expand as run
from loft_plugins.builtin.house import outline_walls, wall_outline
from loft_plugins.builtin.outline import read_outline
from loft_wire.cut_list import CutListMember
from loft_wire.expr import Quantity
from loft_wire.features import (
    AuthoredEnvelope,
    CustomFeature,
    DatumFeature,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    Feature,
    FeatureRef,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import SegmentsInput
from loft_wire.sketch import SketchLine

IN = 25.4
ROOT = Path(__file__).resolve().parents[3]
GOLDENS = ROOT / "services" / "geometry" / "goldens"
GOLDEN = "b7-outline"
CASES = ROOT / "services" / "geometry" / "tests" / "fixtures" / "outline-cases.json.gz"

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000007b7")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000b701")
FLOOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000b702")
WALLS_ID = uuid.UUID("00000000-0000-0000-0000-00000000b703")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-00000000b704")

WALL = REGISTRY.get("loft.wall", "1.3.0")
FLOOR = REGISTRY.get("loft.floor", "1.2.0")
ROOF = REGISTRY.get("loft.roof", "1.4.0")
WINDOW = REGISTRY.get("loft.window", "1.1.0")
DOOR = REGISTRY.get("loft.door", "1.1.0")
WALL_1_2 = REGISTRY.get("loft.wall", "1.2.0")
FLOOR_1_1 = REGISTRY.get("loft.floor", "1.1.0")
ROOF_1_3 = REGISTRY.get("loft.roof", "1.3.0")


def ref(feature_id: uuid.UUID) -> FeatureRef:
    return FeatureRef(kind="feature", feature_id=feature_id)


# --- Sketches, as the web's Rectangle tool and draw-time dimensions make them -------


def line(lid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": lid,
        "kind": "line",
        "start": {"x": a[0] * IN, "y": a[1] * IN},
        "end": {"x": b[0] * IN, "y": b[1] * IN},
    }


def point_ref(entity: str, point: str) -> dict[str, str]:
    return {"entity": entity, "point": point}


def loop_sketch(
    corners: list[tuple[float, float]],
    dims: dict[str, float],
    *,
    drawn: list[tuple[float, float]] | None = None,
    anchor: bool = True,
    extra: list[dict[str, Any]] | None = None,
    names: dict[str, str] | None = None,
) -> SketchFeature:
    """A closed loop e1..en through *corners* (inches), each line horizontal
    or vertical, its first corner on the origin (a fixed construction point,
    as ``sketch/datum.ts`` grounds it), and a length dimension on each line
    in *dims*. *drawn* places the entities elsewhere (a sketch saved before
    its last solve: the reader must use the dimensions, not the drawing)."""
    at = drawn or corners
    n = len(corners)
    entities: list[dict[str, Any]] = [
        {
            "id": "origin",
            "kind": "point",
            "construction": True,
            "position": {"x": 0.0, "y": 0.0},
        }
    ]
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed", "point": point_ref("origin", "position")}
    ]
    for k in range(n):
        lid = f"e{k + 1}"
        a, b = at[k], at[(k + 1) % n]
        entities.append(line(lid, a, b))
        p, q = corners[k], corners[(k + 1) % n]
        constraints.append(
            {"kind": "horizontal" if p[1] == q[1] else "vertical", "entity": lid}
        )
        constraints.append(
            {
                "kind": "coincident",
                "a": point_ref(lid, "end"),
                "b": point_ref(f"e{(k + 1) % n + 1}", "start"),
            }
        )
    if anchor:
        constraints.append(
            {
                "kind": "coincident",
                "a": point_ref("e1", "start"),
                "b": point_ref("origin", "position"),
            }
        )
    for lid, value in dims.items():
        dim: dict[str, Any] = {
            "kind": "distance",
            "entity": lid,
            "value_mm": value * IN,
        }
        if names and lid in names:
            dim["name"] = names[lid]
        constraints.append(dim)
    constraints += extra or []
    return SketchFeature.model_validate(
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": entities,
                "constraints": constraints,
            },
        }
    )


def rectangle(
    width: float, depth: float, *, drawn: tuple[float, float] | None = None
) -> SketchFeature:
    """The Rectangle tool from the origin: bottom, right, top, left (CCW),
    the bottom's and right side's lengths dimensioned."""

    def corners(w: float, d: float) -> list[tuple[float, float]]:
        return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

    return loop_sketch(
        corners(width, depth),
        {"e1": width, "e2": depth},
        drawn=None if drawn is None else corners(*drawn),
        names={"e1": "length", "e2": "width"},
    )


#: An L: 240 x 192 less the 96 x 72 notch at the back right (reflex at
#: (144, 120)), every side dimensioned but the two the loop closes.
L_CORNERS = [(0, 0), (240, 0), (240, 120), (144, 120), (144, 192), (0, 192)]


def l_sketch() -> SketchFeature:
    return loop_sketch(
        [(float(x), float(y)) for x, y in L_CORNERS],
        {"e1": 240, "e2": 120, "e3": 96, "e4": 72},
    )


# --- Features, expanded as documents expands them ----------------------------------


def envelope(plugin: Any, inputs: dict[str, Any]) -> CustomFeature:
    m = plugin.manifest
    return CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": m.id,
                "plugin_version": m.version,
                "inputs": canonical_inputs(m, inputs),
            },
        }
    )


def opening(
    plugin: Any,
    name: str,
    host: uuid.UUID,
    raw: dict[str, Any],
) -> Hosted:
    feature_id = uuid.uuid5(host, name)
    inputs = canonical_inputs(plugin.manifest, {"host_wall": ref(host), **raw})
    m = plugin.manifest
    return Hosted(feature_id, m.id, m.version, name, ExpandInputs(feature_id, inputs))


def expand(
    plugin: Any,
    feature_id: uuid.UUID,
    raw: dict[str, Any],
    earlier: dict[uuid.UUID, AuthoredEnvelope],
    hosted: tuple[Hosted, ...] = (),
) -> list[ExpandedMember]:
    inputs = canonical_inputs(plugin.manifest, raw)
    return run(plugin, feature_id, inputs, earlier, hosted=hosted)


OSB = {"sheathing": "osb_7_16"}
B7_STUDS = {"stud_profile": "us_2x6", **OSB}
B7_FLOOR = {"joist_profile": "us_2x10"}
B7_ROOF = {"rafter_profile": "us_2x8", "ridge_profile": "us_2x10"}
WIN_36_48 = {"width_mm": 36 * IN, "height_mm": 48 * IN}


def b7_openings(front: float = 288.0) -> list[tuple[Any, str, str, dict[str, Any]]]:
    """B7's openings on its outline walls: the front wall runs from its far
    end (X *front*) to X 0, so the door at X 144 and the windows at X 60 and
    228 sit *front* - X from its start (OPENING-FROM-END will measure them
    from either end); the back window at X 144; each side's centred."""
    return [
        (DOOR, "Door", "e1", {"offset_mm": (front - 144) * IN}),
        (WINDOW, "Window 1", "e1", {"offset_mm": (front - 60) * IN, **WIN_36_48}),
        (WINDOW, "Window 2", "e1", {"offset_mm": (front - 228) * IN, **WIN_36_48}),
        (WINDOW, "Window 3", "e3", {"offset_mm": 144 * IN, **WIN_36_48}),
        (WINDOW, "Window 4", "e4", {"offset_mm": 90.5 * IN}),
        (WINDOW, "Window 5", "e2", {"offset_mm": 90.5 * IN}),
    ]


def house(
    sketch: SketchFeature,
    openings: list[tuple[Any, str, str, dict[str, Any]]],
    walls: dict[str, Any],
    floor: dict[str, Any] | None,
    roof: dict[str, Any] | None,
) -> list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]:
    """The tree sketch, floor, walls on it, openings, roof: each row and its
    expansion, as documents' evaluation builds them."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch}
    rows: list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]] = [
        (SKETCH_ID, sketch, [])
    ]

    def add(
        fid: uuid.UUID,
        plugin: Any,
        raw: dict[str, Any],
        hosted: tuple[Hosted, ...] = (),
    ) -> None:
        members = expand(plugin, fid, raw, dict(earlier), hosted)
        env = envelope(plugin, raw)
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
        rows.append((fid, env, members))

    wall_raw = {"outline": ref(SKETCH_ID), **walls}
    if floor is not None:
        add(FLOOR_ID, FLOOR, {"outline": ref(SKETCH_ID), **floor})
        wall_raw["floor"] = ref(FLOOR_ID)
    hosted = [
        opening(p, name, WALLS_ID, {"wall_segment": [seg], **raw})
        for p, name, seg, raw in openings
    ]
    add(WALLS_ID, WALL, wall_raw, tuple(hosted))
    for h in hosted:
        plugin = REGISTRY.get(h.plugin_id, h.plugin_version)
        add(h.feature_id, plugin, dict(h.inputs.values))
    if roof is not None:
        add(ROOF_ID, ROOF, {"walls": [ref(WALLS_ID)], **roof})
    return rows


def b7(
    length: float = 288.0, roof: dict[str, Any] | None = None
) -> list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]:
    return house(
        rectangle(length, 192),
        b7_openings(length),
        B7_STUDS,
        B7_FLOOR,
        {"slope_walls": ["e1", "e3"], **B7_ROOF} if roof is None else roof,
    )


def members_of(
    rows: list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]],
) -> list[ExpandedMember]:
    return [m for _, _, ms in rows for m in ms]


# --- Bodies, placed in the world (for member-for-member comparisons) ---------------


Body = tuple[str | None, str | None, tuple[tuple[float, float, float], ...]]


def bodies(members: list[ExpandedMember]) -> Counter[Body]:
    """Each extrude member as (profile, material, its prism's corners in the
    world, rounded to 1e-6 in): what the kernel builds, without its ids."""
    by_id: dict[uuid.UUID, Feature] = {m.id: m.feature for m in members}

    def frame(plane: Any) -> tuple[str, float]:
        if isinstance(plane, DatumPlaneRef):
            return plane.plane, 0.0
        datum = by_id[plane.feature_id]
        assert isinstance(datum, DatumFeature)
        assert isinstance(datum.params, DatumOffsetParams)
        return datum.params.base, datum.params.offset_mm

    out: Counter[Body] = Counter()
    for m in members:
        if not isinstance(m.feature, ExtrudeFeature):
            continue
        if m.feature.params.operation == "cut":  # a notch: no body of its own
            continue
        sketch = by_id[m.feature.params.profile.feature_id]
        assert isinstance(sketch, SketchFeature)
        base, off = frame(sketch.params.plane)
        d = m.feature.params.distance_mm
        if m.feature.params.direction == "reverse":
            d = -d
        pts: list[tuple[float, float, float]] = []
        for e in sketch.params.entities:
            assert isinstance(e, SketchLine)
            x, y = e.start.x, e.start.y
            for h in (0.0, d):
                if base == "XY":
                    p = (x, y, off + h)
                elif base == "YZ":
                    p = (off + h, x, y)
                else:  # XZ: normal -Y, offset along it
                    p = (x, -(off + h), y)
                pts.append(tuple(round(c / IN, 6) + 0.0 for c in p))  # type: ignore[arg-type]
        meta = m.metadata
        out[
            (
                None if meta is None else meta.profile,
                None if meta is None else meta.material,
                tuple(sorted(pts)),
            )
        ] += 1
    return out


def boxes(members: list[ExpandedMember]) -> list[tuple[float, ...]]:
    """Each body's bounding box (in): x0, x1, y0, y1, z0, z1."""
    out: list[tuple[float, ...]] = []
    for _, _, pts in bodies(members).elements():
        xs, ys, zs = zip(*pts, strict=True)
        out.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    return out


def overlaps(items: list[tuple[float, ...]]) -> list[tuple[int, int]]:
    bad: list[tuple[int, int]] = []
    for i, j in itertools.combinations(range(len(items)), 2):
        a, b = items[i], items[j]
        if all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-6 for k in (0, 2, 4)):
            bad.append((i, j))
    return bad


# --- The round's typed B7 (house-b7.spec.ts, QA-B7-HOUSE) --------------------------

ROUND_WALLS: list[tuple[str, dict[str, Any]]] = [
    ("front", {"start_x_mm": 288 * IN, "direction_deg": 180.0, "length_mm": 288 * IN}),
    ("left", {"start_y_mm": 5.5 * IN, "direction_deg": 90.0, "length_mm": 181 * IN}),
    (
        "back",
        {"start_y_mm": 192 * IN, "direction_deg": 0.0, "length_mm": 288 * IN},
    ),
    (
        "right",
        {
            "start_x_mm": 288 * IN,
            "start_y_mm": 186.5 * IN,
            "direction_deg": 270.0,
            "length_mm": 181 * IN,
        },
    ),
]
ROUND_OPENINGS: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "front": [
        ("loft.door", "Door", {"offset_mm": 144 * IN}),
        ("loft.window", "Window 1", {"offset_mm": 228 * IN, **WIN_36_48}),
        ("loft.window", "Window 2", {"offset_mm": 60 * IN, **WIN_36_48}),
    ],
    "back": [("loft.window", "Window 3", {"offset_mm": 144 * IN, **WIN_36_48})],
    "left": [("loft.window", "Window 4", {"offset_mm": 90.5 * IN})],
    "right": [("loft.window", "Window 5", {"offset_mm": 90.5 * IN})],
}
SUBFLOOR_TOP = 1.5 + 9.25 + 23 / 32  # 11.46875
ROUND_FLOOR = {"width_mm": 288 * IN, "depth_mm": 192 * IN, **B7_FLOOR}


def round_b7() -> list[ExpandedMember]:
    """The round's 12 typed features: floor 1.1.0, four walls 1.2.0 on the
    subfloor's top typed by hand, the openings 1.0.0 and the typed gable."""
    out = expand(FLOOR_1_1, FLOOR_ID, ROUND_FLOOR, {})
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for side, raw in ROUND_WALLS:
        fid = uuid.uuid5(WALLS_ID, side)
        full = {**raw, "elevation_mm": SUBFLOOR_TOP * IN, **B7_STUDS}
        hosted = tuple(
            Hosted(
                uuid.uuid5(fid, name),
                pid,
                "1.0.0",
                name,
                ExpandInputs(
                    uuid.uuid5(fid, name),
                    canonical_inputs(
                        REGISTRY.get(pid, "1.0.0").manifest,
                        {"host_wall": ref(fid), **o},
                    ),
                ),
            )
            for pid, name, o in ROUND_OPENINGS[side]
        )
        out += expand(WALL_1_2, fid, full, dict(earlier), hosted)
        earlier[fid] = envelope(WALL_1_2, full)
    out += expand(
        ROOF_1_3,
        ROOF_ID,
        {
            "span_mm": 192 * IN,
            "length_mm": 288 * IN,
            "plate_height_mm": (SUBFLOOR_TOP + 97.125) * IN,
            "plate_width_mm": 5.5 * IN,
            **B7_ROOF,
        },
        {},
    )
    return out


# --- The outline reader -------------------------------------------------------------


def test_a_rectangle_reads_clockwise_from_its_first_line() -> None:
    outline = read_outline(rectangle(288, 192))
    assert [(s.line_id, s.start, s.end, s.facing) for s in outline.segments] == [
        ("e1", (288.0, 0.0), (0.0, 0.0), "front"),
        ("e4", (0.0, 0.0), (0.0, 192.0), "left"),
        ("e3", (0.0, 192.0), (288.0, 192.0), "back"),
        ("e2", (288.0, 192.0), (288.0, 0.0), "right"),
    ]
    assert outline.is_rectangle


def test_the_dimensions_not_the_drawing_place_the_outline() -> None:
    """A sketch saved before its last solve still holds the drawn corners
    (300 x 200); the dimensions (288 x 192) are what the solver will give."""
    stale = read_outline(rectangle(288, 192, drawn=(300, 200)))
    assert stale == read_outline(rectangle(288, 192))


def test_a_clockwise_drawing_reads_the_same_loop() -> None:
    cw = loop_sketch([(0, 0), (0, 192), (288, 192), (288, 0)], {"e1": 192, "e2": 288})
    segs = read_outline(cw).segments
    assert [(s.start, s.end) for s in segs] == [
        ((0.0, 0.0), (0.0, 192.0)),
        ((0.0, 192.0), (288.0, 192.0)),
        ((288.0, 192.0), (288.0, 0.0)),
        ((288.0, 0.0), (0.0, 0.0)),
    ]


def test_point_distances_midpoints_and_equal_sides_define_it_too() -> None:
    """No line lengths: a horizontal point distance for the width, a
    point-to-line distance for the depth, then a square made with equal."""
    sketch = loop_sketch(
        [(0, 0), (100, 0), (100, 60), (0, 60)],
        {},
        drawn=[(0, 0), (90, 0), (90, 50), (0, 50)],
        extra=[
            {
                "kind": "point_distance",
                "a": point_ref("e1", "start"),
                "b": point_ref("e2", "start"),
                "direction": "horizontal",
                "value_mm": 100 * IN,
            },
            {
                "kind": "point_line_distance",
                "point": point_ref("e3", "start"),
                "line": "e1",
                "value_mm": 60 * IN,
            },
        ],
    )
    assert [s.start for s in read_outline(sketch).segments] == [
        (100.0, 0.0),
        (0.0, 0.0),
        (0.0, 60.0),
        (100.0, 60.0),
    ]
    square = loop_sketch(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        {"e1": 50},
        drawn=[(0, 0), (50, 0), (50, 40), (0, 40)],
        extra=[{"kind": "equal", "a": "e1", "b": "e2"}],
    )
    assert read_outline(square).segments[1].end == (0.0, 50.0)


def _with_length(expression: str) -> SketchFeature:
    """B7's outline, its 288 dimension now driven by *expression* (its
    stored value still 288, as a client saving the formula leaves it)."""
    raw = rectangle(288, 192).model_dump(mode="json")
    for c in raw["params"]["constraints"]:
        if c.get("name") == "length":
            c["expression"] = expression
    return SketchFeature.model_validate(raw)


def test_dimension_formulas_are_read_as_the_solver_sizes_them() -> None:
    """``336 in`` and a part parameter ``L`` both move the far side; the
    stored 288 beside the formula is not read."""
    for expression, table in (
        ("336 in", {}),
        ("L", {"L": Quantity(336 * IN, "length")}),
    ):
        segments = read_outline(_with_length(expression), "outline", table).segments
        assert segments[0].start == (336.0, 0.0)


@pytest.mark.parametrize("expression", ["1 in / 0", "10 kg", "L"])
def test_a_dimension_formula_that_does_not_evaluate_is_the_walls_error(
    expression: str,
) -> None:
    """Fusion flags a sick feature rather than keep a stale size: walls on an
    outline whose dimension does not evaluate are refused, naming it."""
    walls = {"outline": ref(SKETCH_ID)}
    with pytest.raises(PluginError, match="dimension 'length'") as refused:
        expand(WALL, WALLS_ID, walls, {SKETCH_ID: _with_length(expression)})
    assert refused.value.input == "outline"


def test_an_l_reads_its_inside_corner() -> None:
    outline = read_outline(l_sketch())
    assert len(outline.segments) == 6
    convex = [outline.convex_at_start(k) for k in range(6)]
    assert convex.count(False) == 1
    assert not outline.is_rectangle


@pytest.mark.parametrize(
    ("case", "words"),
    [
        ("unanchored", "not fully defined"),
        ("undimensioned", "not fully defined"),
        ("open", "one closed loop"),
        ("slanted", "horizontal or vertical"),
        ("conflict", "disagree"),
        ("circle", "loop of straight lines"),
        ("plane", "in plan"),
    ],
)
def test_an_outline_it_cannot_read_is_refused(case: str, words: str) -> None:
    corners = [(0.0, 0.0), (288.0, 0.0), (288.0, 192.0), (0.0, 192.0)]
    sketch = {
        "unanchored": lambda: loop_sketch(
            corners, {"e1": 288, "e2": 192}, anchor=False
        ),
        "undimensioned": lambda: loop_sketch(corners, {"e1": 288}),
        "conflict": lambda: loop_sketch(corners, {"e1": 288, "e2": 192, "e3": 280}),
    }.get(case, lambda: rectangle(288, 192))()
    raw = sketch.model_dump(mode="json")
    if case == "open":
        raw["params"]["constraints"] = [
            c
            for c in raw["params"]["constraints"]
            if not (c["kind"] == "coincident" and c["a"]["entity"] == "e4")
        ]
    if case == "slanted":
        raw["params"]["constraints"] = [
            c for c in raw["params"]["constraints"] if c.get("entity") != "e2"
        ]
    if case == "circle":
        raw["params"]["entities"].append(
            {"id": "e9", "kind": "circle", "center": {"x": 1, "y": 1}, "radius": 1}
        )
    if case == "plane":
        raw["params"]["plane"] = {"kind": "datum_plane", "plane": "XZ"}
        envelope_ = SketchFeature.model_validate(raw)
        with pytest.raises(PluginError, match=words):
            expand(WALL, WALLS_ID, {"outline": ref(SKETCH_ID)}, {SKETCH_ID: envelope_})
        return
    with pytest.raises(PluginError, match=words) as refused:
        read_outline(SketchFeature.model_validate(raw))
    assert refused.value.input == "outline"


# --- Walls, floor and roof on B7's outline = the round's typed build ---------------


def test_b7_on_its_outline_is_the_rounds_typed_build_member_for_member() -> None:
    """217 bodies: the floor 39 (19 joists, 2 rims, 4 sills, 14 subfloor
    panels), the walls 151 (with 24 OSB panels: 20 and 4 corner rips) and
    the roof 27 (26 rafters, the ridge), each the round's body exactly."""
    outline = bodies(members_of(b7()))
    typed = bodies(round_b7())
    assert outline == typed
    assert sum(outline.values()) == 217


def test_each_rafter_tail_is_notched_out_of_the_eave_walls_sheathing() -> None:
    """The heel is on the framing's face, so each tail crosses the 7/16 OSB
    below the plate's top (the round's build shares 43.1006 in^3 between
    them). The roof notches every tail out of the panels it crosses: 26
    rafters, the five at the panel joints (X 48 .. 240) crossing two panels."""
    roof = next(ms for fid, _, ms in b7() if fid == ROOF_ID)
    cuts = [m for m in roof if m.role == "cutter"]
    assert len(cuts) == 26
    widths = Counter(
        len(m.feature.params.cut_bodies or [])
        for m in cuts
        if isinstance(m.feature, ExtrudeFeature)
    )
    assert widths == Counter({1: 16, 2: 10})
    walls = next(ms for fid, _, ms in b7() if fid == WALLS_ID)
    panels = {m.id: m.name for m in walls if m.role == "sheathing"}
    for m in cuts:
        assert isinstance(m.feature, ExtrudeFeature)
        assert m.feature.params.operation == "cut"
        scope = m.feature.params.cut_bodies
        assert isinstance(scope, list)
        for target in scope:
            assert target.feature_id in panels
            side = "e1" if "front" in str(m.name) else "e3"
            assert str(panels[target.feature_id]).startswith(f"{side}/exterior/")
    unsheathed = house(
        rectangle(288, 192),
        [],
        {"stud_profile": "us_2x6"},
        None,
        {"slope_walls": ["e1", "e3"], **B7_ROOF},
    )
    assert not any(m.role == "cutter" for _, _, ms in unsheathed for m in ms)


def test_the_floor_on_the_outline_is_the_typed_floor_exactly() -> None:
    rows = b7()
    floor = next(ms for fid, _, ms in rows if fid == FLOOR_ID)
    assert floor == expand(FLOOR_1_1, FLOOR_ID, ROUND_FLOOR, {})


def test_the_roof_on_the_outline_is_the_typed_gable_exactly() -> None:
    """Front (e1) and back (e3) define the slope: span 192, length 288, the
    plate read from the walls on the subfloor (108.59375, 5.5 deep)."""
    roof = next(ms for fid, _, ms in b7() if fid == ROOF_ID)
    typed = expand(
        ROOF_1_3,
        ROOF_ID,
        {
            "span_mm": 192 * IN,
            "length_mm": 288 * IN,
            "plate_height_mm": (SUBFLOOR_TOP + 97.125) * IN,
            "plate_width_mm": 5.5 * IN,
            **B7_ROOF,
        },
        {},
    )
    # Its members are the typed gable's, then the tail notches.
    assert [m for m in roof if m.role != "cutter"] == typed


def test_a_line_wall_on_a_floor_is_the_typed_wall_exactly() -> None:
    """SHEATHING-WALL-BASE: On floor stands a line wall on the subfloor's top,
    as typing 11.46875 did."""
    floor = envelope(FLOOR_1_1, ROUND_FLOOR)
    picked = expand(
        WALL,
        WALLS_ID,
        {**ROUND_WALLS[0][1], **B7_STUDS, "floor": ref(FLOOR_ID)},
        {FLOOR_ID: floor},
    )
    typed = expand(
        WALL_1_2,
        WALLS_ID,
        {**ROUND_WALLS[0][1], **B7_STUDS, "elevation_mm": SUBFLOOR_TOP * IN},
        {},
    )
    assert picked == typed


def test_an_empty_outline_and_floor_is_the_1_2_0_wall_and_1_1_0_floor() -> None:
    raw = {**ROUND_WALLS[1][1], **B7_STUDS}
    assert expand(WALL, WALLS_ID, raw, {}) == expand(WALL_1_2, WALLS_ID, raw, {})
    assert expand(FLOOR, FLOOR_ID, B7_FLOOR, {}) == expand(
        FLOOR_1_1, FLOOR_ID, B7_FLOOR, {}
    )


def test_outline_walls_run_through_along_the_first_line_and_fit_between() -> None:
    sketch = rectangle(288, 192)
    inputs = ExpandInputs(
        WALLS_ID,
        canonical_inputs(WALL.manifest, {"outline": ref(SKETCH_ID), **B7_STUDS}),
        {SKETCH_ID: sketch},
    )
    outline = wall_outline(inputs)
    assert outline is not None
    walls = outline_walls(inputs, outline)
    assert [
        (
            w.line_id,
            w.through,
            w.spec.start_x,
            w.spec.start_y,
            w.spec.direction_deg,
            w.spec.length,
        )
        for w in walls
    ] == [
        ("e1", True, 288.0, 0.0, 180.0, 288.0),
        ("e4", False, 0.0, 5.5, 90.0, 181.0),
        ("e3", True, 0.0, 192.0, 0.0, 288.0),
        ("e2", False, 288.0, 186.5, 270.0, 181.0),
    ]


def test_members_are_named_under_their_line() -> None:
    walls = next(ms for fid, _, ms in b7() if fid == WALLS_ID)
    names = {m.name for m in walls}
    studs = {m.name for m in walls if m.role == "stud"}
    assert "e1/slot/9" not in studs  # replaced by the door's framing at X 144
    assert "e1/slot/9" in names  # the top cripple standing at that slot
    assert {"e1/start", "e4/end", "e3/course/2", "e2/corner/end"} <= names
    assert all(
        m.name is not None and m.name.split("/")[0] in {"e1", "e2", "e3", "e4"}
        for m in walls
    )


# --- Edit 1: 288 -> 336 is one sketch-dimension edit -------------------------------


def test_the_length_edit_is_one_dimension_and_every_member_follows() -> None:
    """The round's 28 ft cut list: 22 joists, rims and sills at 336, 16
    subfloor panels, 66 studs, 26 OSB panels, 30 rafters, a 336 ridge: 234
    bodies. The front openings keep X 60, 144 and 228 here because their
    offsets are re-typed from the front wall's start (OPENING-FROM-END will
    hold them from the X 0 end); the back and side openings are untouched."""
    rows = b7(336)
    members = members_of(rows)
    assert sum(bodies(members).values()) == 234
    roles = Counter(m.role for m in members if m.metadata is not None)
    assert roles["joist"] == 22
    assert roles["subfloor"] == 16
    assert roles["sheathing"] == 26
    assert roles["rafter"] == 30
    # Boxes are exact for the floor and walls (a rafter's box takes in the
    # plate its birdsmouth sits on: the kernel case checks the roof).
    framing = [m for m in members if m.role not in ("rafter", "ridge")]
    assert overlaps(boxes(framing)) == []


def test_a_member_keeps_its_id_when_another_wall_changes() -> None:
    """The left wall (e4) and the back wall's first members do not move when
    the right side moves out 48 in: same ids, same bodies."""

    def walls(length: float) -> dict[str, ExpandedMember]:
        ms = next(ms for fid, _, ms in b7(length) if fid == WALLS_ID)
        return {f"{m.role} {m.name}": m for m in ms}

    def same(a: ExpandedMember, b: ExpandedMember) -> bool:
        # A named member is its id, feature and metadata; its index only counts.
        return (a.id, a.feature, a.metadata) == (b.id, b.feature, b.metadata)

    before, after = walls(288), walls(336)
    left = [n for n in before if n.startswith("section e4/")]
    assert left and all(same(before[n], after[n]) for n in before if " e4/" in n)
    assert same(before["section e3/stud/slot/1"], after["section e3/stud/slot/1"])
    # The right wall's start stud moved out with the wall, under its name.
    moved = "section e2/stud/start"
    assert before[moved].id == after[moved].id
    assert not same(before[moved], after[moved])


# --- Roofs on outlines --------------------------------------------------------------


B2_ROOF_TYPED = {"span_mm": 120 * IN, "length_mm": 144 * IN}


def test_b2s_gable_on_its_outline_is_the_typed_gable() -> None:
    """ROOF-GABLE-WALLS: B2's walls drawn as one outline, the front and back
    defining slope, frame b2-roof-6-12's gable member for member (its
    plate is 97.125 high and 3.5 deep)."""
    rows = house(rectangle(144, 120), [], {}, None, {"slope_walls": ["e1", "e3"]})
    roof = next(ms for fid, _, ms in rows if fid == ROOF_ID)
    typed = expand(ROOF_1_3, ROOF_ID, B2_ROOF_TYPED, {})
    assert roof == typed
    v1 = expand(REGISTRY.get("loft.roof", "1.0.0"), ROOF_ID, B2_ROOF_TYPED, {})
    assert bodies(roof) == bodies(v1)


def test_a_hip_on_the_outline_is_the_typed_hip() -> None:
    """B3 (144 x 120, 2x4 walls 97.125): every wall defines the slope."""
    rows = house(rectangle(144, 120), [], {}, None, {"style": "hip"})
    roof = next(ms for fid, _, ms in rows if fid == ROOF_ID)
    typed = expand(ROOF_1_3, ROOF_ID, {"style": "hip", **B2_ROOF_TYPED}, {})
    assert roof == typed


def test_the_gable_follows_the_outline_off_the_origin_and_along_y() -> None:
    """Left and right defining slope: the ridge runs along Y, the rafters on
    XZ planes; moved off the origin it is the same roof, moved."""
    sketch = rectangle(120, 144)
    raw = sketch.model_dump(mode="json")
    rows = house(sketch, [], {}, None, {"slope_walls": ["e2", "e4"]})
    roof = next(ms for fid, _, ms in rows if fid == ROOF_ID)
    turned = bodies(roof)
    # The same roof along X is B2's: swap X and Y in every body.
    typed = bodies(expand(ROOF_1_3, ROOF_ID, B2_ROOF_TYPED, {}))
    swapped = Counter(
        {
            (p, mat, tuple(sorted((y, x, z) for x, y, z in pts))): n
            for (p, mat, pts), n in typed.items()
        }
    )
    assert turned == swapped
    # Moved 24 in +X and 36 in +Y: the origin point fixed there.
    for e in raw["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    rows = house(
        SketchFeature.model_validate(raw), [], {}, None, {"slope_walls": ["e2", "e4"]}
    )
    moved = bodies(next(ms for fid, _, ms in rows if fid == ROOF_ID))
    shifted = Counter(
        {
            (
                p,
                mat,
                tuple(
                    sorted((round(x + 24, 6), round(y + 36, 6), z) for x, y, z in pts)
                ),
            ): n
            for (p, mat, pts), n in turned.items()
        }
    )
    assert moved == shifted


@pytest.mark.parametrize(
    ("roof", "words"),
    [
        ({"slope_walls": ["e1"]}, "two opposite walls"),
        ({"slope_walls": ["e1", "e2"]}, "two opposite walls"),
        ({"style": "hip", "slope_walls": ["e1", "e2"]}, "every wall"),
        ({"slope_walls": ["e1", "e9"]}, "not a line of the outline"),
    ],
)
def test_defines_slope_is_refused_where_it_frames_nothing(
    roof: dict[str, Any], words: str
) -> None:
    with pytest.raises(PluginError, match=words):
        house(rectangle(144, 120), [], {}, None, roof)


def test_a_hip_on_sheathed_outline_walls_is_refused() -> None:
    """Its tails and hips would pass through the OSB; notching them is a
    later rung, so it is refused rather than built interfering."""
    with pytest.raises(PluginError, match="sheathed outline walls"):
        house(rectangle(144, 120), [], OSB, None, {"style": "hip"})


def test_a_gable_on_an_l_is_refused_and_a_hip_frames_it() -> None:
    with pytest.raises(PluginError, match="rectangular"):
        house(l_sketch(), [], {}, None, {"slope_walls": ["e1", "e3"]})
    rows = house(l_sketch(), [], {}, None, {"style": "hip"})
    roof = next(ms for fid, _, ms in rows if fid == ROOF_ID)
    assert any(m.role == "valley" for m in roof)


# --- Openings -----------------------------------------------------------------------


def test_an_opening_names_its_wall_of_the_outline() -> None:
    with pytest.raises(PluginError, match="pick the wall"):
        house(
            rectangle(288, 192),
            [(WINDOW, "Window", "e9", {"offset_mm": 60 * IN})],
            B7_STUDS,
            None,
            None,
        )
    old = Hosted(
        uuid.uuid5(WALLS_ID, "old"),
        "loft.window",
        "1.0.0",
        "Old window",
        ExpandInputs(
            uuid.uuid5(WALLS_ID, "old"),
            canonical_inputs(
                REGISTRY.get("loft.window", "1.0.0").manifest,
                {"host_wall": ref(WALLS_ID)},
            ),
        ),
    )
    sketch = rectangle(288, 192)
    with pytest.raises(PluginError, match="cannot name one wall"):
        expand(WALL, WALLS_ID, {"outline": ref(SKETCH_ID)}, {SKETCH_ID: sketch}, (old,))


def test_an_opening_checks_its_fit_on_its_wall_of_the_outline() -> None:
    sketch = rectangle(288, 192)
    walls = envelope(WALL, {"outline": ref(SKETCH_ID), **B7_STUDS})
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {SKETCH_ID: sketch, WALLS_ID: walls}
    fits = {"host_wall": ref(WALLS_ID), "wall_segment": ["e4"], "offset_mm": 90.5 * IN}
    assert expand(WINDOW, uuid.uuid4(), fits, earlier) == []
    # 170 along the 181 side wall: its king passes the end stud.
    with pytest.raises(PluginError, match="end studs"):
        expand(WINDOW, uuid.uuid4(), {**fits, "offset_mm": 170 * IN}, earlier)
    # The same offset on the 288 front wall fits.
    assert (
        expand(
            WINDOW,
            uuid.uuid4(),
            {**fits, "wall_segment": ["e1"], "offset_mm": 170 * IN},
            earlier,
        )
        == []
    )
    one_line = envelope(WALL, {**ROUND_WALLS[0][1]})
    with pytest.raises(PluginError, match="leave Wall empty"):
        expand(WINDOW, uuid.uuid4(), fits, {WALLS_ID: one_line})


def test_the_segments_input_is_on_the_wire() -> None:
    picks = {i.name: i for i in WINDOW.manifest.inputs}
    seg = picks["wall_segment"]
    assert isinstance(seg, SegmentsInput)
    assert (seg.outline_input, seg.min_items, seg.max_items) == ("host_wall", 0, 1)
    slope = next(i for i in ROOF.manifest.inputs if i.name == "slope_walls")
    assert isinstance(slope, SegmentsInput) and slope.outline_input == "walls"
    wall_inputs = {i.name: i for i in WALL.manifest.inputs}
    assert wall_inputs["start_x_mm"].superseded_by == "outline"
    assert wall_inputs["elevation_mm"].superseded_by == "floor"
    assert next(iter(wall_inputs)) == "outline"
    # Stored as plain line ids, and refused when repeated.
    stored = canonical_inputs(
        WINDOW.manifest, {"host_wall": ref(WALLS_ID), "wall_segment": ["e2"]}
    )
    assert stored["wall_segment"] == ["e2"]
    with pytest.raises(PluginError, match="at most 1"):
        canonical_inputs(
            WINDOW.manifest, {"host_wall": ref(WALLS_ID), "wall_segment": ["e2", "e3"]}
        )


# --- No overlaps on any rectilinear outline -----------------------------------------


def random_outline(rng: random.Random) -> list[tuple[float, float]]:
    """A random rectilinear loop: a rectangle with up to two corners notched."""
    w = rng.choice([144.0, 192.0, 240.0, 301.5])
    d = rng.choice([120.0, 168.0, 200.25])
    pts = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    notches = rng.sample(range(4), rng.randint(0, 2))
    out: list[tuple[float, float]] = []
    for k, (x, y) in enumerate(pts):
        if k not in notches or k == 0:
            out.append((x, y))
            continue
        a = rng.choice([24.0, 48.5, 60.0])
        b = rng.choice([24.0, 36.25, 50.0])
        sx = -1 if x > 0 else 1
        sy = -1 if y > 0 else 1
        if k == 1:
            out += [(x + sx * a, y), (x + sx * a, y + sy * b), (x, y + sy * b)]
        elif k == 2:
            out += [(x, y + sy * b), (x + sx * a, y + sy * b), (x + sx * a, y)]
        else:
            out += [(x + sx * a, y), (x + sx * a, y + sy * b), (x, y + sy * b)]
    return out


def random_house(seed: int) -> list[ExpandedMember]:
    rng = random.Random(seed)
    corners = random_outline(rng)
    n = len(corners)
    dims = {
        f"e{k + 1}": math.dist(corners[k], corners[(k + 1) % n]) for k in range(n - 2)
    }
    sketch = loop_sketch(corners, dims)
    studs = rng.choice(["us_2x4", "us_2x6"])
    rows = house(
        sketch,
        [],
        {
            "stud_profile": studs,
            "sheathing": rng.choice(["none", "osb_7_16", "plywood_15_32"]),
        },
        None,
        None,
    )
    return members_of(rows)


@pytest.mark.parametrize("seed", range(40))
def test_no_two_outline_members_overlap(seed: int) -> None:
    """Rectangles and notched rectangles, 2x4 and 2x6, every sheathing: no
    two bodies' boxes overlap (every outline member is a box, and every
    panel a box less openings), and each wall is framed."""
    members = random_house(seed)
    assert overlaps(boxes(members)) == []


# --- The golden and the kernel cases ------------------------------------------------


TITLES = {
    role.role: role.title
    for plugin in (WALL, FLOOR, ROOF)
    for role in plugin.manifest.members
}


def request_of(
    rows: list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]],
) -> EvaluateTreeRequest:
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


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    rows = b7()
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=TITLES[m.role], metadata=m.metadata
        )
        for m in members_of(rows)
        if m.metadata is not None
    ]
    return request_of(rows), metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def cases() -> str:
    """The kernel's cases: B7 at 336, B2 on an outline with its gable, an L
    with a hip on 2x4 outline walls, and a gable along Y off the origin on
    sheathed 2x6 walls (its tails notched out of the side walls' OSB and
    corner rips); each with its body count."""
    moved = rectangle(120, 144).model_dump(mode="json")
    for e in moved["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    built = {
        "b7-336": b7(336),
        "b2-outline-gable": house(
            rectangle(144, 120), [], {}, None, {"slope_walls": ["e1", "e3"]}
        ),
        "l-outline-hip": house(l_sketch(), [], {}, None, {"style": "hip"}),
        "gable-along-y-moved": house(
            SketchFeature.model_validate(moved),
            [],
            {"stud_profile": "us_2x6", **OSB},
            {},
            {"slope_walls": ["e2", "e4"]},
        ),
    }
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            "request": request_of(rows).model_dump(mode="json"),
        }
        for name, rows in built.items()
    ]
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    assert (GOLDENS / GOLDEN / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (GOLDENS / GOLDEN / "members.json").read_text() == _members_json(metadata)


def test_the_kernel_cases_are_the_plugins_expansion() -> None:
    assert gzip.decompress(CASES.read_bytes()).decode() == cases()


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(_members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
    CASES.write_bytes(gzip.compress(cases().encode(), mtime=0))
    sys.stdout.write(f"{CASES.name}\n")
