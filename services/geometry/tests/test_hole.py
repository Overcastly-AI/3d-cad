"""Hole feature (slice 1 — the simple hole) — API-level behaviour beyond goldens.

The golden ``hole-through-r5-40x25x10`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py`` (mass properties within the
documented tolerance, exact topology/mesh, byte-determinism). This module adds
the acceptance criteria the golden harness does not express:

* ANALYTIC VOLUME PARITY (the "green suite, wrong geometry" guard): a HoleFeature
  through-hole removes exactly ``pi*r^2*h`` AND matches a hand-built
  sketch+extrude-cut of the same bore, to the documented golden tolerance. A hole
  feature that registered but cut the wrong volume/direction FAILS here.
* CUT DIRECTION: the drill cuts INTO the material (opposite the face's outward
  normal), proven from both the top (+Z) and bottom (-Z) faces.
* TYPED DEGRADATION (never-500): off-body, over-deep-blind, unresolved face, and
  no-prior-body each degrade to a per-feature error under the strict-prefix rule.
* REGISTRY ROUND-TRIP: a HoleFeature loads through the shared FEATURE_REGISTRY
  (documents' persist/read path) and evaluates ok, persisting as last-good.

Numeric assertions use the documented golden tolerance (see
``goldens/hole-through-r5-40x25x10/expected.json``), never ad-hoc epsilons.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from py_kit.schemas.features import (
    FEATURE_REGISTRY,
    EvaluateTreeResult,
    HoleFeature,
    feature_references,
)

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "hole-through-r5-40x25x10"
    / "model.json"
)

#: Documented golden tolerance (expected.json: analytic quadric, ~1e-12 observed).
HOLE_TOL = 1e-9


def _approx(value: float) -> Any:
    """pytest.approx bound to the documented golden tolerance (no ad-hoc epsilon)."""
    return pytest.approx(value, abs=HOLE_TOL)


#: Block 40x25x10, hole diameter 10 (r=5).
BLOCK_VOLUME = 40.0 * 25.0 * 10.0
RADIUS = 5.0
THROUGH_REMOVED = math.pi * RADIUS * RADIUS * 10.0  # pi*r^2*thickness
THROUGH_VOLUME = BLOCK_VOLUME - THROUGH_REMOVED

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f0")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0001")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0002")
HOLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0003")

XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}

#: The 40x25x10 block's top (+Z) and bottom (-Z) planar-face signatures (area 1000).
TOP_FACE = ((0.0, 0.0, 1.0), (20.0, 12.5, 10.0), 1000.0)
BOTTOM_FACE = ((0.0, 0.0, -1.0), (20.0, 12.5, 0.0), 1000.0)


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def block_sketch(feature_id: uuid.UUID) -> dict[str, Any]:
    """A closed 40x25 rectangle profile (entities already at position)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    _line("e1", (0.0, 0.0), (40.0, 0.0)),
                    _line("e2", (40.0, 0.0), (40.0, 25.0)),
                    _line("e3", (40.0, 25.0), (0.0, 25.0)),
                    _line("e4", (0.0, 25.0), (0.0, 0.0)),
                ],
                "constraints": [],
            },
        },
    }


def extrude_add(
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _face_ref(
    feature_id: uuid.UUID,
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    area_mm2: float,
) -> dict[str, Any]:
    """A stage-1 face SubshapeRef — the SAME shape the on_face datum / shell use."""
    return {
        "kind": "subshape",
        "feature_id": str(feature_id),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "face",
                "surface": "plane",
                "normal": {"x": normal[0], "y": normal[1], "z": normal[2]},
                "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
                "area_mm2": area_mm2,
            },
        },
    }


def hole_input(
    feature_id: uuid.UUID,
    face: tuple[tuple[float, float, float], tuple[float, float, float], float],
    position: tuple[float, float, float],
    diameter_mm: float,
    depth: dict[str, Any],
    *,
    face_feature: uuid.UUID = EXTRUDE_ID,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _face_ref(face_feature, *face),
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "diameter_mm": diameter_mm,
                "depth": depth,
            },
        },
    }


def circle_cut_sketch(
    feature_id: uuid.UUID, center: tuple[float, float], radius: float
) -> dict[str, Any]:
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
                        "center": {"x": center[0], "y": center[1]},
                        "radius": radius,
                    }
                ],
                "constraints": [],
            },
        },
    }


def extrude_cut(
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": "cut",
                "direction": "normal",
            },
        },
    }


def _request(
    features: list[dict[str, Any]], *, tree_version: int = 3
) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": tree_version,
        "features": features,
    }


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


THROUGH: dict[str, Any] = {"kind": "through_all"}


def _blind(depth_mm: float) -> dict[str, Any]:
    return {"kind": "blind", "depth_mm": depth_mm}


# --- Analytic volume parity (the headline golden) ------------------------------------


def test_hole_through_matches_extrude_cut_and_analytic() -> None:
    """A HoleFeature through-hole removes EXACTLY pi*r^2*h, equals the analytic
    block-minus-cylinder, AND equals a hand-built sketch+extrude-cut of the same
    bore — the "green suite, wrong geometry" guard. Identical topology too."""
    hole = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(HOLE_ID, TOP_FACE, (20.0, 12.5, 10.0), 10.0, THROUGH),
            ]
        )
    )
    assert [r.status for r in hole.features] == ["ok", "ok", "ok"]
    assert hole.last_good_feature_id == HOLE_ID
    assert hole.properties is not None

    # Independent path: a circle sketch extrude-CUT through the same block.
    cut = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                circle_cut_sketch(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00c1"), (20.0, 12.5), 5.0
                ),
                extrude_cut(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00c2"),
                    uuid.UUID("00000000-0000-0000-0000-0000000f00c1"),
                    10.0,
                ),
            ]
        )
    )
    assert [r.status for r in cut.features] == ["ok", "ok", "ok", "ok"]
    assert cut.properties is not None

    # Analytic parity: block - pi*r^2*h.
    assert hole.properties.volume == _approx(THROUGH_VOLUME)
    # Feature-vs-sketch-cut parity: the two independent paths agree.
    assert hole.properties.volume == _approx(cut.properties.volume)
    assert hole.properties.surface_area == _approx(cut.properties.surface_area)
    # Same B-rep topology as the trusted cut path.
    assert (
        hole.properties.topology.faces,
        hole.properties.topology.edges,
        hole.properties.topology.shells,
    ) == (7, 15, 1)
    assert hole.properties.topology.faces == cut.properties.topology.faces
    # The hole is interior — the block envelope is unchanged.
    assert hole.properties.bounding_box.max.x == _approx(40.0)
    assert hole.properties.bounding_box.max.z == _approx(10.0)
    assert hole.mesh_glb_id is not None and hole.mesh_glb_id.startswith("sha256:")


def test_golden_hole_tree_is_byte_deterministic() -> None:
    """Same tree -> identical response bytes incl. mesh_glb_id (RESEARCH §9)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Cut direction: INTO the solid, from either face --------------------------------


def test_hole_cuts_into_solid_from_top_and_bottom_faces() -> None:
    """The drill direction is the INWARD face normal, chosen automatically: a
    through-hole from the top (+Z, cuts down) and from the bottom (-Z, cuts up)
    both remove exactly the same pi*r^2*h cylinder. If the direction were the
    outward normal the bore would cut into empty space and remove nothing."""
    for face, position in (
        (TOP_FACE, (20.0, 12.5, 10.0)),
        (BOTTOM_FACE, (20.0, 12.5, 0.0)),
    ):
        result = _post(
            _request(
                [
                    block_sketch(SKETCH_ID),
                    extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                    hole_input(HOLE_ID, face, position, 10.0, THROUGH),
                ]
            )
        )
        assert [r.status for r in result.features] == ["ok", "ok", "ok"]
        assert result.properties is not None
        assert result.properties.volume == _approx(THROUGH_VOLUME)


def test_blind_hole_removes_exact_pocket_and_keeps_bottom_intact() -> None:
    """A blind hole drills exactly depth_mm into the material: removed volume is
    pi*r^2*depth (not the full thickness), and the far face stays solid (8 faces:
    6 block + bore lateral + bore bottom cap, vs a through-hole's 7)."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(HOLE_ID, TOP_FACE, (20.0, 12.5, 10.0), 10.0, _blind(6.0)),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == _approx(
        BLOCK_VOLUME - math.pi * RADIUS * RADIUS * 6.0
    )
    assert result.properties.topology.faces == 8
    # bottom face intact -> envelope still reaches z=0.
    assert result.properties.bounding_box.min.z == _approx(0.0)


# --- Typed degradation — per-feature errors, never 500 -------------------------------


def test_hole_off_body_is_typed_error() -> None:
    """A placement point off the face removes no material -> hole_off_body, and
    the tree still returns 200 (a value, not a transport failure)."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(HOLE_ID, TOP_FACE, (100.0, 100.0, 10.0), 10.0, THROUGH),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_off_body"


def test_blind_hole_over_deep_is_typed_error() -> None:
    """A blind depth exceeding the 10 mm thickness cannot form its full pocket ->
    hole_too_deep (use a through-all hole), never a silently-through body."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(HOLE_ID, TOP_FACE, (20.0, 12.5, 10.0), 10.0, _blind(20.0)),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_too_deep"


def test_hole_unresolved_face_is_subshape_unresolved() -> None:
    """A face signature that matches no current planar face (e.g. a non-existent
    centroid) degrades exactly as the on_face datum does — subshape_unresolved."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(
                    HOLE_ID,
                    ((0.0, 0.0, 1.0), (999.0, 999.0, 10.0), 1000.0),
                    (20.0, 12.5, 10.0),
                    10.0,
                    THROUGH,
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "subshape_unresolved"


def test_hole_with_no_prior_body_is_no_prior_body() -> None:
    """Hole modifies the single body chain (§7.6): a sketch-only prefix ->
    no_prior_body, the hole error, nothing downstream to skip."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                hole_input(HOLE_ID, TOP_FACE, (20.0, 12.5, 10.0), 10.0, THROUGH),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "error"]
    assert result.features[1].error is not None
    assert result.features[1].error.code == "no_prior_body"


# --- Registry round-trip: create -> persist/load -> evaluate -------------------------


def test_hole_feature_registry_roundtrip() -> None:
    """A HoleFeature loads through the shared FEATURE_REGISTRY (documents'
    persist/read path) to the current version, and its placement FACE materialises
    into a feature-dependency edge (deleting the face's feature is a
    409-with-dependents; a reorder re-checks strict-backward)."""
    assert FEATURE_REGISTRY.current_version("hole") == 1
    params = {
        "face": _face_ref(EXTRUDE_ID, *TOP_FACE),
        "position": {"x": 20.0, "y": 12.5, "z": 10.0},
        "diameter_mm": 10.0,
        "depth": {"kind": "through_all"},
    }
    loaded = FEATURE_REGISTRY.load("hole", 1, params)
    assert isinstance(loaded, HoleFeature)
    assert loaded.params.diameter_mm == 10.0
    refs = feature_references(loaded)
    assert len(refs) == 1
    assert refs[0].slot == "face"
    assert refs[0].ref.feature_id == EXTRUDE_ID
