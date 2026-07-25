"""Pattern feature — API-level behavior of the linear/circular pattern (#7).

Covers the BACKLOG Ready #7 acceptance beyond the golden harness (the golden
``pattern-linear-3x-bar`` runs every parametrized gate in ``test_goldens.py`` /
``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates real
mass properties and a fetchable content-addressed mesh; a connected CIRCULAR
array is numerically checked; ``count == 1`` is a no-op; and every pattern
error path — ``no_target_body``, ``pattern_bad_count``, ``pattern_bad_spacing``,
``pattern_bad_direction``, ``pattern_bad_axis``, ``pattern_bad_angle``,
``pattern_disjoint`` — is a per-feature error pinned under the strict-prefix
rule (design §4.3), never a transport failure. A non-integer count is a
parse-time 422 (``count`` is typed ``int``).

v1 DESIGN DECISION (option B, docs/GEOMETRY-QA.md): a pattern replicates the
CURRENT body and unions the copies into the single body chain (§7.6). Numeric
assertions use the documented tree-golden tolerance (measured-then-set,
``goldens/pattern-linear-3x-bar/expected.json``), not ad-hoc epsilons.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "pattern-linear-3x-bar"
    / "model.json"
)

#: The documented tolerance of the pattern golden (expected.json
#: tolerance_rationale: measured EXACTLY 0.0 on every property; 1e-9 is the
#: reviewed ceiling). The planar-union pattern path is exact.
PATTERN_TOL = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fb")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
BODY_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
PATTERN_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")

XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def rect_sketch(
    feature_id: uuid.UUID, x0: float, y0: float, x1: float, y1: float
) -> dict[str, Any]:
    """A closed rectangle [x0,x1] x [y0,y1] on XY, entities at their analytic
    positions with no constraints (underconstrained → solver returns the input
    positions bitwise; same posture as the revolve suite's profile_sketch)."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    entities = [_line(f"e{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)]
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def extrude_input(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    operation: str = "add",
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": operation,
                "direction": "normal",
            },
        },
    }


def circle_sketch(
    feature_id: uuid.UUID, cx: float, cy: float, radius: float
) -> dict[str, Any]:
    """A single circle on XY (one closed loop), no constraints (zero residual)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    {
                        "id": "c1",
                        "kind": "circle",
                        "center": {"x": cx, "y": cy},
                        "radius": radius,
                    }
                ],
                "constraints": [],
            },
        },
    }


def linear_pattern_input(
    feature_id: uuid.UUID,
    *,
    direction: tuple[float, float, float] = (1.0, 0.0, 0.0),
    spacing_mm: float = 6.0,
    count: int = 3,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {
                        "x": direction[0],
                        "y": direction[1],
                        "z": direction[2],
                    },
                    "spacing_mm": spacing_mm,
                    "count": count,
                }
            },
        },
    }


def circular_pattern_input(
    feature_id: uuid.UUID,
    *,
    axis_point: tuple[float, float, float] = (0.0, 0.0, 0.0),
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0),
    angle_deg: float = 360.0,
    count: int = 4,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "circular",
                    "axis_point": {
                        "x": axis_point[0],
                        "y": axis_point[1],
                        "z": axis_point[2],
                    },
                    "axis_direction": {
                        "x": axis_direction[0],
                        "y": axis_direction[1],
                        "z": axis_direction[2],
                    },
                    "angle_deg": angle_deg,
                    "count": count,
                }
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 3, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


def _cube_tree(pattern: dict[str, Any]) -> dict[str, Any]:
    """The unit-cube seed (10x10x10) then the given pattern feature."""
    return _request(
        [
            rect_sketch(SKETCH_ID, 0.0, 0.0, 10.0, 10.0),
            extrude_input(BODY_ID, SKETCH_ID, 10.0),
            pattern,
        ]
    )


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed pattern golden, posted verbatim: all three features ok,
    the fused bar volume 2200 mm^3, content-addressed mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (BODY_ID, "ok"),
        (PATTERN_ID, "ok"),
    ]
    assert result.last_good_feature_id == PATTERN_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(2200.0, abs=PATTERN_TOL)
    assert result.properties.surface_area == pytest.approx(1080.0, abs=PATTERN_TOL)
    assert result.properties.topology.faces == 6
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_with_body_is_byte_deterministic() -> None:
    """Same pattern tree → identical response bytes INCLUDING mesh_glb_id
    (a content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Valid pattern variants ----------------------------------------------------------


def test_circular_pattern_of_a_bar_forms_a_connected_plus() -> None:
    """A 4x12x8 bar centred on the world Z axis, circular-patterned 360°/4:
    the 90°/270° copies cross the seed into a connected PLUS solid. Volume =
    two crossed 4x12 rectangles minus the 4x4 centre overlap, x 8 mm high =
    (48 + 48 - 16) * 8 = 640 mm^3; symmetric AABB [-6,-6,0]..[6,6,8]."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -2.0, -6.0, 2.0, 6.0),
                extrude_input(BODY_ID, SKETCH_ID, 8.0),
                circular_pattern_input(PATTERN_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(640.0, abs=PATTERN_TOL)
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-6.0, abs=PATTERN_TOL)
    assert bbox.max.x == pytest.approx(6.0, abs=PATTERN_TOL)
    assert bbox.min.z == pytest.approx(0.0, abs=PATTERN_TOL)
    assert bbox.max.z == pytest.approx(8.0, abs=PATTERN_TOL)


def test_count_one_is_a_no_op_leaving_the_seed_body() -> None:
    """count == 1 (seed only) returns the body unchanged — the cube volume."""
    result = _post(_cube_tree(linear_pattern_input(PATTERN_ID, count=1)))

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(1000.0, abs=PATTERN_TOL)


def test_linear_pattern_along_y_shifts_the_whole_body() -> None:
    """A +Y linear pattern (count 3, spacing 6) of the unit cube is the bar
    along Y — the placement math is not X-specific."""
    result = _post(
        _cube_tree(linear_pattern_input(PATTERN_ID, direction=(0.0, 1.0, 0.0)))
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(2200.0, abs=PATTERN_TOL)
    bbox = result.properties.bounding_box
    assert bbox.max.y == pytest.approx(22.0, abs=PATTERN_TOL)
    assert bbox.max.x == pytest.approx(10.0, abs=PATTERN_TOL)


# --- Pattern-of-a-cut: array a CUT, not just a union (BACKLOG #3 / showcase F1) -------

HOLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
CUT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


def _drilled_plate_tree(pattern: dict[str, Any]) -> dict[str, Any]:
    """A 60x60x10 plate + a SINGLE r4 through-hole cut at (20,0), then *pattern*.

    The pattern's immediately-preceding body-affecting feature is the extrude
    CUT, so a circular/linear pattern here must array THAT CUT (option a) —
    remove a hole at each placement, not union whole-body copies.
    """
    return _request(
        [
            rect_sketch(SKETCH_ID, -30.0, -30.0, 30.0, 30.0),
            extrude_input(BODY_ID, SKETCH_ID, 10.0),
            circle_sketch(HOLE_ID, 20.0, 0.0, 4.0),
            extrude_input(CUT_ID, HOLE_ID, 10.0, operation="cut"),
            pattern,
        ]
    )


def test_circular_pattern_of_a_cut_removes_n_holes_not_adds_bodies() -> None:
    """The acceptance (BACKLOG #3): one hole-cut + circular pattern (count 6,
    360°) drills a 6-hole bolt circle — volume = plate minus SIX holes, and a
    single connected solid (12 faces), NOT six unioned plates."""
    result = _post(_drilled_plate_tree(circular_pattern_input(PATTERN_ID, count=6)))

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    plate = 60.0 * 60.0 * 10.0
    six_holes = 6 * math.pi * 4.0**2 * 10.0
    assert result.properties.volume == pytest.approx(plate - six_holes, abs=PATTERN_TOL)
    # A drilled plate is one solid with the six cylinder walls — not six bodies.
    assert result.properties.topology.faces == 12
    assert result.properties.topology.shells == 1
    # Centroid on the pattern axis (origin) by 6-fold symmetry.
    assert result.properties.centroid.x == pytest.approx(0.0, abs=PATTERN_TOL)
    assert result.properties.centroid.y == pytest.approx(0.0, abs=PATTERN_TOL)


def test_linear_pattern_of_a_cut_drills_a_row_of_holes() -> None:
    """A linear pattern after a hole-cut removes a ROW of holes (the cut path is
    not circular-specific): seed at (20,0) + copies at -X spacing 20, count 3 ->
    holes at x = 20, 0, -20, all interior to the 60-wide plate."""
    result = _post(
        _drilled_plate_tree(
            linear_pattern_input(
                PATTERN_ID, direction=(-1.0, 0.0, 0.0), spacing_mm=20.0, count=3
            )
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    plate = 60.0 * 60.0 * 10.0
    three_holes = 3 * math.pi * 4.0**2 * 10.0
    assert result.properties.volume == pytest.approx(
        plate - three_holes, abs=PATTERN_TOL
    )
    assert result.properties.topology.shells == 1


def test_cut_pattern_count_one_leaves_the_single_seed_hole() -> None:
    """count == 1 after a cut is a no-op: exactly the one seed hole remains
    (plate minus ONE hole), never the whole-body union fallback."""
    result = _post(_drilled_plate_tree(circular_pattern_input(PATTERN_ID, count=1)))

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    plate = 60.0 * 60.0 * 10.0
    one_hole = math.pi * 4.0**2 * 10.0
    assert result.properties.volume == pytest.approx(plate - one_hole, abs=PATTERN_TOL)


def test_add_pattern_after_a_cut_hole_still_unions_whole_body() -> None:
    """Regression guard for the inference boundary: when the LAST body-affecting
    feature is an ADD (not a cut), the pattern still UNIONS whole-body copies.
    Here a plate with one hole is additively extruded-bossed, THEN patterned —
    the boss (an add) is the source, so the pattern unions, it does not drill."""
    boss_sketch = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
    boss_extrude = uuid.UUID("00000000-0000-0000-0000-0000000000b3")
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 10.0, 10.0),
                extrude_input(BODY_ID, SKETCH_ID, 10.0),
                circle_sketch(HOLE_ID, 5.0, 5.0, 2.0),
                extrude_input(CUT_ID, HOLE_ID, 10.0, operation="cut"),
                # An ADD boss becomes the new source; the pattern must union.
                rect_sketch(boss_sketch, 0.0, 0.0, 10.0, 10.0),
                extrude_input(boss_extrude, boss_sketch, 10.0),
                linear_pattern_input(
                    PATTERN_ID, direction=(1.0, 0.0, 0.0), spacing_mm=6.0, count=3
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 7
    assert result.properties is not None
    # UNION of the whole holed body along +X (overlapping copies): the bar
    # spans x in [0, 22]; a drilled result would instead be < the seed volume.
    bbox = result.properties.bounding_box
    assert bbox.max.x == pytest.approx(22.0, abs=PATTERN_TOL)
    assert result.properties.volume > 1000.0


FILLET_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")


def _fillet_vertical_edges(feature_id: uuid.UUID, radius_mm: float) -> dict[str, Any]:
    """A fillet of the 4 Z-parallel edges (axis_parallel predicate) — a plain
    body-affecting feature to sit BETWEEN a cut and a pattern so the pattern's
    immediately-preceding source is a fillet, not the extrude-cut."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": "Z"},
                "radius_mm": radius_mm,
            },
        },
    }


def test_pattern_after_an_intervening_fillet_unions_whole_body_not_recut() -> None:
    """Inference-boundary guard (the review 🟡): a cut -> fillet -> pattern tree
    must take the WHOLE-BODY UNION path, NOT re-cut the hole. The pattern's
    immediately-preceding body-affecting feature is the FILLET (an add-class
    mutate), not the extrude-cut, so ``_pattern_cut_tools`` returns ``None`` and
    the pattern unions whole-body copies of the filleted, drilled plate — this
    locks the ``isinstance(source, ExtrudeFeature) and operation == "cut"``
    boundary: a non-cut preceding feature => union.

    Discriminator: a +X linear pattern (spacing 6, count 3) UNIONS three
    overlapping copies of the 60x60 plate → the body EXTENDS to x=42 and GAINS
    material (volume well over one 36000 mm^3 plate). Were the boundary broken
    (the fillet ignored, the underlying cut re-inferred as the source), the
    pattern would instead drill 3 holes into the SINGLE plate: max.x would stay
    30 and the volume would DROP below 36000 (~34e3), which both asserts reject.
    """
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -30.0, -30.0, 30.0, 30.0),
                extrude_input(BODY_ID, SKETCH_ID, 10.0),
                circle_sketch(HOLE_ID, 20.0, 0.0, 4.0),
                extrude_input(CUT_ID, HOLE_ID, 10.0, operation="cut"),
                # The intervening fillet becomes the source; the pattern UNIONS.
                _fillet_vertical_edges(FILLET_ID, 4.0),
                linear_pattern_input(
                    PATTERN_ID, direction=(1.0, 0.0, 0.0), spacing_mm=6.0, count=3
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 6
    assert result.properties is not None
    bbox = result.properties.bounding_box
    # UNION extended the body along +X to 42 (a re-cut keeps the plate at 30).
    assert bbox.max.x == pytest.approx(42.0, abs=PATTERN_TOL)
    assert bbox.min.x == pytest.approx(-30.0, abs=PATTERN_TOL)
    # A whole-body union of three overlapping filleted plates >> one 36000 plate;
    # a 3-hole re-cut of the single plate would instead be < 36000 (~34e3).
    assert result.properties.volume > 40000.0
    assert result.properties.topology.shells == 1


# --- Pattern of a HOLE FEATURE: array the drill, not the whole body (FINDINGS #1) -----

HOLE_FEATURE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d2")

#: The 60x60 plate's +Z face signature (area 3600, centroid (0,0,10)).
PLATE_TOP_FACE: dict[str, Any] = {
    "kind": "subshape",
    "feature_id": str(BODY_ID),
    "subshape_type": "face",
    "selector": {
        "selector_version": 1,
        "signature": {
            "subshape_type": "face",
            "surface": "plane",
            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
            "centroid": {"x": 0.0, "y": 0.0, "z": 10.0},
            "area_mm2": 3600.0,
        },
    },
}


def hole_feature_input(
    feature_id: uuid.UUID, position: tuple[float, float, float], diameter_mm: float
) -> dict[str, Any]:
    """A through-all Hole FEATURE on the plate's +Z face (the flagship Hole, NOT a
    hand-sketched extrude-cut) — the source whose pattern FINDINGS #1 broke."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": PLATE_TOP_FACE,
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "diameter_mm": diameter_mm,
                "depth": {"kind": "through_all"},
            },
        },
    }


def test_pattern_of_a_hole_feature_arrays_the_cut_not_the_whole_body() -> None:
    """FINDINGS #1 regression: patterning a HOLE feature must array the CUT, not
    duplicate the whole body. Plate 60x60x10, a single r4 through-hole drilled by
    the Hole feature at (20,0), linear-patterned -X (spacing 20, count 3) -> three
    holes at x = 20, 0, -20 in ONE plate. Volume = plate minus THREE r4 through-
    holes; a single connected solid (9 faces).

    Discriminator vs the old bug: the pre-fix path unioned three whole-body copies
    of the drilled plate (measured ~59497 mm^3, body extended along -X), so this
    asserts BOTH the exact drilled volume (< one 36000 plate) AND the AABB
    unchanged from the single plate ([-30,30] in X) — a whole-body union would push
    min.x to -70.
    """
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -30.0, -30.0, 30.0, 30.0),
                extrude_input(BODY_ID, SKETCH_ID, 10.0),
                hole_feature_input(HOLE_FEATURE_ID, (20.0, 0.0, 10.0), 8.0),
                linear_pattern_input(
                    PATTERN_ID, direction=(-1.0, 0.0, 0.0), spacing_mm=20.0, count=3
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    plate = 60.0 * 60.0 * 10.0
    three_holes = 3 * math.pi * 4.0**2 * 10.0
    assert result.properties.volume == pytest.approx(
        plate - three_holes, abs=PATTERN_TOL
    )
    assert result.properties.topology.shells == 1
    assert result.properties.topology.faces == 9
    # AABB unchanged from the single plate — a whole-body union would extend -X.
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-30.0, abs=PATTERN_TOL)
    assert bbox.max.x == pytest.approx(30.0, abs=PATTERN_TOL)
    # Centroid on x=0 by the symmetric row {20,0,-20}, y=0.
    assert result.properties.centroid.x == pytest.approx(0.0, abs=PATTERN_TOL)
    assert result.properties.centroid.y == pytest.approx(0.0, abs=PATTERN_TOL)


# --- Pattern of a MULTI-REGION (#4) cut: replicate ALL tools (#4 x #3) ----------------

MULTI_HOLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a4")


def _multi_circle_sketch(
    feature_id: uuid.UUID, centers: list[tuple[float, float]], radius: float
) -> dict[str, Any]:
    """A sketch of N disjoint circles (N closed loops) → one multi-region cut
    (the #4 path: one extrude-cut feature removing N tools)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    {
                        "id": f"h{i + 1}",
                        "kind": "circle",
                        "center": {"x": cx, "y": cy},
                        "radius": radius,
                    }
                    for i, (cx, cy) in enumerate(centers)
                ],
                "constraints": [],
            },
        },
    }


def test_pattern_of_a_multi_region_cut_replicates_all_tools() -> None:
    """#4 x #3 composition — ``_pattern_cut_tools`` returning a tool-list > 1,
    end to end. A SINGLE multi-region cut (TWO disjoint r3 holes at x=15,
    y=+/-10) patterned -X (spacing 20, count 3) replicates BOTH tools at every
    placement → holes at x in {15,-5,-25} times y in {+/-10} = 2 x 3 = SIX
    holes, not two. Volume matches the analytic (plate minus six r3 through-
    holes), the topology proves exactly six holes, and the result is
    byte-deterministic (RESEARCH §9)."""
    payload = _request(
        [
            rect_sketch(SKETCH_ID, -30.0, -30.0, 30.0, 30.0),
            extrude_input(BODY_ID, SKETCH_ID, 10.0),
            _multi_circle_sketch(MULTI_HOLE_ID, [(15.0, 10.0), (15.0, -10.0)], 3.0),
            extrude_input(CUT_ID, MULTI_HOLE_ID, 10.0, operation="cut"),
            linear_pattern_input(
                PATTERN_ID, direction=(-1.0, 0.0, 0.0), spacing_mm=20.0, count=3
            ),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    # Determinism: the multi-tool cut path is a pure function of the tree.
    assert first.content == second.content

    result = EvaluateTreeResult.model_validate(first.json())
    assert [r.status for r in result.features] == ["ok"] * 5
    assert result.properties is not None
    plate = 60.0 * 60.0 * 10.0
    six_holes = 6 * math.pi * 3.0**2 * 10.0
    assert result.properties.volume == pytest.approx(plate - six_holes, abs=PATTERN_TOL)
    # 2 caps + 4 side walls + 6 cylinder walls = 12 faces ⇒ exactly SIX holes
    # (each tool of the 2-region cut replicated across all three placements).
    assert result.properties.topology.faces == 12
    assert result.properties.topology.shells == 1
    # y=+/-10 holes mirror about y=0 → centroid.y is exactly 0 by symmetry.
    assert result.properties.centroid.y == pytest.approx(0.0, abs=PATTERN_TOL)


# --- A patterned cut that can reach NOTHING is never a silent no-op (CM-2) ------------
#
# The pattern half of the reading `mirror_cut` shipped in `fa30220`
# (`test_extrude_cut_then_mirror_about_a_clearing_plane_completes_the_part`):
# "array the removal" is only the user's meaning when a replicated tool can reach
# the body. When none can, the request is "array the BODY" — whose copies already
# carry the seed cut. Found by the composition matrix (GEOMETRY-QA 2026-07-25,
# CM-2); the pre-fix kernel returned the input body with every feature `ok`.

PLATE_40_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
POCKET_40_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b5")


def _pocketed_40_plate(pattern: dict[str, Any]) -> dict[str, Any]:
    """A 40x40x10 plate with an 8x20 through-pocket at x in [4,12], then *pattern*.

    14400 mm^3 (16000 - 1600). Deliberately 40 wide so a +X step of 40 puts every
    replicated POCKET TOOL beyond the +X face — the CM-2 shape.
    """
    return _request(
        [
            rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
            extrude_input(BODY_ID, SKETCH_ID, 10.0),
            rect_sketch(POCKET_40_ID, 4.0, 10.0, 12.0, 30.0),
            extrude_input(PLATE_40_ID, POCKET_40_ID, 10.0, operation="cut"),
            pattern,
        ]
    )


def test_linear_pattern_of_a_cut_that_clears_the_body_replicates_the_body() -> None:
    """CM-2 (P0): a +X step of 40 on a 40-wide pocketed plate must NOT be a no-op.

    Every copy of the pocket tool lands at x in [44,52] — entirely beyond the
    body — so ``body.cut(...)`` removed nothing and the pre-fix pattern returned
    the untouched 14400.0 mm^3 plate with all five features `ok`. The kernel now
    reads an unreachable removal as "replicate the BODY" (the SHARED
    ``removal_reaches_body`` predicate ``mirror_cut`` already used): an 80 mm part
    with a pocket in EACH half, 28800 mm^3, fused across the shared x=40 face into
    one solid. Volume (2x), bbox (2x in x) and the face count each fail on the old
    behaviour.
    """
    result = _post(
        _pocketed_40_plate(
            linear_pattern_input(
                PATTERN_ID, direction=(1.0, 0.0, 0.0), spacing_mm=40.0, count=2
            )
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 5
    assert result.properties is not None
    # 2 * (40*40*10 - 8*20*10); the silent no-op returned 14400.
    assert result.properties.volume == pytest.approx(28800.0, abs=PATTERN_TOL)
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(0.0, abs=PATTERN_TOL)
    assert bbox.max.x == pytest.approx(80.0, abs=PATTERN_TOL)
    # 6 outer faces + 4 walls per through-pocket x 2 = 14; the no-op body had 10.
    assert result.properties.topology.faces == 14
    assert result.properties.topology.shells == 1
    # The two pockets sit at x in [4,12] and [44,52] — a TRANSLATION, not a
    # reflection — so the centroid is off the 80 mm bar's own midplane by exactly
    # (32000*40 - 1600*8 - 1600*48) / 28800 = 41.333...
    assert result.properties.centroid.x == pytest.approx(
        (32000.0 * 40.0 - 1600.0 * 8.0 - 1600.0 * 48.0) / 28800.0, abs=PATTERN_TOL
    )


def test_circular_pattern_of_a_cut_that_clears_the_body_replicates_the_body() -> None:
    """CM-2, the ROTATED twin — the same fallback in ``circular_pattern_cut``.

    The pocketed 40 mm plate spun 180° about the Z axis through (0, 20) — the mid
    of its own -X edge: the rotated pocket tool lands in x in [-12,-4], where
    there is no material, so the cut could remove nothing (the pre-fix silent
    no-op). The BODY replicate lands the plate at x in [-40,0] sharing the whole
    x=0 face, so it fuses into one 80x40 lump of 28800 mm^3 with a pocket in each
    half.
    """
    result = _post(
        _pocketed_40_plate(
            circular_pattern_input(
                PATTERN_ID,
                axis_point=(0.0, 20.0, 0.0),
                axis_direction=(0.0, 0.0, 1.0),
                angle_deg=360.0,
                count=2,
            )
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 5
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(28800.0, abs=PATTERN_TOL)
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-40.0, abs=PATTERN_TOL)
    assert bbox.max.x == pytest.approx(40.0, abs=PATTERN_TOL)
    # Point-symmetric about (0, 20) ⇒ the centroid sits exactly there.
    assert result.properties.centroid.x == pytest.approx(0.0, abs=PATTERN_TOL)
    assert result.properties.centroid.y == pytest.approx(20.0, abs=PATTERN_TOL)


def test_patterned_cut_keeps_the_cut_path_when_one_copy_reaches() -> None:
    """The fallback's BOUNDARY: reachable ANYWHERE ⇒ still the cut path.

    Same 40 mm pocketed plate, count 3 at +X spacing 16: copy 1 (x in [20,28])
    lands inside the body and copy 2 (x in [36,44]) half-clears the +X face. One
    copy reaching is enough to keep "array the removal", so the body must LOSE
    material (16000 - 1600 - 1600 - 800 = 12000) and stay 40 mm wide — never grow
    to an 80/120 mm whole-body replicate.
    """
    result = _post(
        _pocketed_40_plate(
            linear_pattern_input(
                PATTERN_ID, direction=(1.0, 0.0, 0.0), spacing_mm=16.0, count=3
            )
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 5
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(12000.0, abs=PATTERN_TOL)
    assert result.properties.bounding_box.max.x == pytest.approx(40.0, abs=PATTERN_TOL)


# --- Error paths are per-feature values, never transport failures ---------------------


def _pattern_error(result: EvaluateTreeResult) -> str:
    """The pattern feature's error code, asserting the strict-prefix shape:
    the pattern is the error, the seed body is preserved as last-good."""
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    return error.code


def test_pattern_before_any_body_is_no_target_body() -> None:
    """A pattern with no prior body-affecting feature → no_target_body."""
    result = _post(_request([linear_pattern_input(PATTERN_ID)]))

    assert result.features[0].status == "error"
    error = result.features[0].error
    assert error is not None
    assert error.code == "no_target_body"
    assert result.mesh_glb_id is None


def test_zero_count_is_pattern_bad_count() -> None:
    """count < 1 → pattern_bad_count; the seed extrude stays as last-good."""
    result = _post(_cube_tree(linear_pattern_input(PATTERN_ID, count=0)))
    assert _pattern_error(result) == "pattern_bad_count"
    # Strict-prefix: the last-good body (the extrude) is still tessellated.
    assert result.last_good_feature_id == BODY_ID
    assert result.mesh_glb_id is not None


def test_zero_spacing_is_pattern_bad_spacing() -> None:
    """Linear spacing 0 → pattern_bad_spacing (instances would coincide)."""
    result = _post(_cube_tree(linear_pattern_input(PATTERN_ID, spacing_mm=0.0)))
    assert _pattern_error(result) == "pattern_bad_spacing"


def test_negative_spacing_is_pattern_bad_spacing() -> None:
    result = _post(_cube_tree(linear_pattern_input(PATTERN_ID, spacing_mm=-6.0)))
    assert _pattern_error(result) == "pattern_bad_spacing"


def test_zero_length_direction_is_pattern_bad_direction() -> None:
    """A zero-length linear direction vector → pattern_bad_direction."""
    result = _post(
        _cube_tree(linear_pattern_input(PATTERN_ID, direction=(0.0, 0.0, 0.0)))
    )
    assert _pattern_error(result) == "pattern_bad_direction"


def test_zero_length_axis_is_pattern_bad_axis() -> None:
    """A zero-length circular axis direction → pattern_bad_axis."""
    result = _post(
        _cube_tree(circular_pattern_input(PATTERN_ID, axis_direction=(0.0, 0.0, 0.0)))
    )
    assert _pattern_error(result) == "pattern_bad_axis"


def test_zero_angle_with_multiple_instances_is_pattern_bad_angle() -> None:
    """angle 0 with count > 1 → pattern_bad_angle (copies collapse on seed)."""
    result = _post(_cube_tree(circular_pattern_input(PATTERN_ID, angle_deg=0.0)))
    assert _pattern_error(result) == "pattern_bad_angle"


def test_over_360_angle_is_pattern_bad_angle() -> None:
    """A sweep > 360° with count > 1 → pattern_bad_angle."""
    result = _post(_cube_tree(circular_pattern_input(PATTERN_ID, angle_deg=540.0)))
    assert _pattern_error(result) == "pattern_bad_angle"


def test_disjoint_instances_are_pattern_disjoint() -> None:
    """Spacing wider than the 10 mm cube leaves separated lumps — a single body
    chain is required in v1 (§7.6), so this is pattern_disjoint, NOT a body."""
    result = _post(
        _cube_tree(linear_pattern_input(PATTERN_ID, spacing_mm=20.0, count=2))
    )
    assert _pattern_error(result) == "pattern_disjoint"
    # The seed body is still the last-good artifact (strict-prefix rule).
    assert result.last_good_feature_id == BODY_ID


def test_non_integer_count_is_a_parse_error() -> None:
    """A non-integer count is a request-validation failure (422), not a
    per-feature error — `count` is typed `int`."""
    payload = _cube_tree(linear_pattern_input(PATTERN_ID))
    payload["features"][2]["feature"]["params"]["pattern"]["count"] = 2.5
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 422
