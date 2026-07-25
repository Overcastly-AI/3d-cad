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
from build123d import Axis, Location, Plane, Solid, Vector
from fastapi.testclient import TestClient
from geometry.kernel.extrude import BooleanError, combine_body
from geometry.kernel.faces import planar_faces
from geometry.kernel.hole import (
    HoleInvalidDiameterError,
    HoleRecessInvalidError,
    HoleTooDeepError,
    bore_hole,
    cut_counterbore,
    cut_countersink,
)
from geometry.kernel.lumps import lump_count
from geometry.kernel.threads import (
    ISO_METRIC_PITCHES,
    ThreadBoreMismatchError,
    ThreadUnsupportedError,
    check_tap_drill_bore,
    resolve_iso_metric_thread,
)
from geometry.kernel.types import BodyShape
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


# --- Same-face reference resilience (FINDINGS #3) -----------------------------------

HOLE_A_ID = uuid.UUID("00000000-0000-0000-0000-0000000f00a1")
HOLE_B_ID = uuid.UUID("00000000-0000-0000-0000-0000000f00b1")


def _picked_top_signature(
    diameter_mm: float, position: tuple[float, float, float]
) -> Any:
    """The +Z top-face signature of the 40x25x10 block AFTER an off-centre through
    hole — the face a SIBLING hole would have been picked against (post-A). Built
    from the kernel body the feature layer produces for the same inputs."""
    box = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(box, (0.0, 0.0, 1.0))
    body = bore_hole(box, top, position, diameter_mm, through_all=True, depth_mm=None)
    return next(r.signature for r in planar_faces(body) if r.signature.normal.z > 0.5)


def _hole_from_signature(
    feature_id: uuid.UUID,
    signature: Any,
    position: tuple[float, float, float],
    diameter_mm: float,
) -> dict[str, Any]:
    """A hole input whose placement face carries an EXPLICIT captured signature
    (vs the pristine ``TOP_FACE`` tuple) — how a sibling hole picked on an
    already-drilled face is stored."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _face_ref(
                    EXTRUDE_ID,
                    (signature.normal.x, signature.normal.y, signature.normal.z),
                    (signature.centroid.x, signature.centroid.y, signature.centroid.z),
                    signature.area_mm2,
                ),
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "diameter_mm": diameter_mm,
                "depth": dict(THROUGH),
            },
        },
    }


def test_editing_one_holes_diameter_keeps_a_same_face_sibling_resolved() -> None:
    """FINDINGS #3 acceptance (end to end, through /evaluate): two holes on the
    SAME top face; editing hole A's diameter Ø6->Ø8 shifts that face's area &
    centroid, yet the sibling hole B on the same face STILL resolves — no
    ``subshape_unresolved``. Before the resilient re-match this orphaned B."""
    pos_a = (12.0, 8.0, 10.0)
    pos_b = (28.0, 17.0, 10.0)
    # B was picked against the top face AFTER hole A(Ø6) — its stored signature
    # carries the post-A area/centroid.
    sig_b = _picked_top_signature(6.0, pos_a)

    def tree(diameter_a: float) -> dict[str, Any]:
        return _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(HOLE_A_ID, TOP_FACE, pos_a, diameter_a, THROUGH),
                _hole_from_signature(HOLE_B_ID, sig_b, pos_b, 5.0),
            ]
        )

    # Initial build: both holes resolve and evaluate (B strict-matches post-A).
    initial = _post(tree(6.0))
    assert [r.status for r in initial.features] == ["ok", "ok", "ok", "ok"]
    assert initial.last_good_feature_id == HOLE_B_ID

    # EDIT hole A Ø6 -> Ø8: B on the SAME face still resolves (FINDINGS #3).
    edited = _post(tree(8.0))
    assert [r.status for r in edited.features] == ["ok", "ok", "ok", "ok"]
    assert edited.last_good_feature_id == HOLE_B_ID
    # The edit really changed the geometry (a bigger bore A removes more material).
    assert initial.properties is not None and edited.properties is not None
    assert edited.properties.volume < initial.properties.volume


# --- Slice 2: counterbore / countersink (analytic parity + regression) --------------


def _hole_typed(
    feature_id: uuid.UUID,
    diameter_mm: float,
    depth: dict[str, Any],
    hole_type: dict[str, Any],
) -> dict[str, Any]:
    """A hole input carrying an explicit ``type`` (counterbore/countersink/simple)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _face_ref(EXTRUDE_ID, *TOP_FACE),
                "position": {"x": 20.0, "y": 12.5, "z": 10.0},
                "diameter_mm": diameter_mm,
                "depth": depth,
                "type": hole_type,
            },
        },
    }


#: Counterbore Ø18 (R=9) 4 mm deep over a Ø10 (r=5) through-bore in the 10 mm block.
_CBORE_REMOVED = math.pi * RADIUS * RADIUS * 10.0 + math.pi * (9.0**2 - 5.0**2) * 4.0
#: Countersink Ø18 (R=9) 90° included over the same bore: bore + annular cone.
_CSINK_H = (9.0 - 5.0) / math.tan(math.radians(45.0))
_CSINK_FRUSTUM = math.pi * _CSINK_H / 3.0 * (9.0**2 + 9.0 * 5.0 + 5.0**2)
_CSINK_REMOVED = (
    math.pi * RADIUS * RADIUS * 10.0
    + _CSINK_FRUSTUM
    - math.pi * RADIUS * RADIUS * _CSINK_H
)


def test_counterbore_matches_analytic_and_extrude_cut() -> None:
    """A counterbore removes EXACTLY π·r²·H + π·(R²-r²)·h_cbore (the bore plus the
    annular-difference recess), and its volume/area/topology match an independent
    hand-built two-step sketch+extrude-cut (Ø18 4 mm, then Ø10 through). The recess
    sits at the placement (top) face, so more mass is low: centroid z < 5."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                _hole_typed(
                    HOLE_ID,
                    10.0,
                    THROUGH,
                    {
                        "kind": "counterbore",
                        "cbore_diameter_mm": 18.0,
                        "cbore_depth_mm": 4.0,
                    },
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == _approx(BLOCK_VOLUME - _CBORE_REMOVED)
    assert (
        result.properties.topology.faces,
        result.properties.topology.edges,
        result.properties.topology.shells,
    ) == (9, 18, 1)
    # Recess at the top face -> centroid pulled below the mid-plane.
    assert result.properties.centroid.z < 5.0

    # Independent path: two extrude-cuts of the same bore + recess (from the bottom,
    # a true mirror image — so volume/area/topology agree but the centroid mirrors).
    cut = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                circle_cut_sketch(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00a1"), (20.0, 12.5), 9.0
                ),
                extrude_cut(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00a2"),
                    uuid.UUID("00000000-0000-0000-0000-0000000f00a1"),
                    4.0,
                ),
                circle_cut_sketch(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00b1"), (20.0, 12.5), 5.0
                ),
                extrude_cut(
                    uuid.UUID("00000000-0000-0000-0000-0000000f00b2"),
                    uuid.UUID("00000000-0000-0000-0000-0000000f00b1"),
                    10.0,
                ),
            ]
        )
    )
    assert cut.properties is not None
    assert result.properties.volume == _approx(cut.properties.volume)
    assert result.properties.surface_area == _approx(cut.properties.surface_area)
    assert result.properties.topology.faces == cut.properties.topology.faces
    assert result.properties.topology.edges == cut.properties.topology.edges


def test_countersink_matches_analytic_frustum() -> None:
    """A countersink removes EXACTLY the bore plus the annular cone (the frustum
    π·h/3·(R²+R·r+r²) minus the already-bored π·r²·h), with h set by the 90°
    included angle. 8 faces (block + cone + bore wall); recess at the top face."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                _hole_typed(
                    HOLE_ID,
                    10.0,
                    THROUGH,
                    {
                        "kind": "countersink",
                        "csink_diameter_mm": 18.0,
                        "csink_angle_deg": 90.0,
                    },
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == _approx(BLOCK_VOLUME - _CSINK_REMOVED)
    assert (
        result.properties.topology.faces,
        result.properties.topology.edges,
        result.properties.topology.shells,
    ) == (8, 17, 1)
    assert result.properties.centroid.z < 5.0


def test_simple_hole_omitted_type_is_byte_identical_to_explicit() -> None:
    """The additive `type` default is INERT: a simple hole with the field OMITTED
    (the slice-1 wire shape) and one with an explicit `{"kind":"simple"}` produce
    byte-identical evaluate responses (incl. mesh_glb_id) — the backward-compat
    regression proving slice 2 did not perturb the simple-hole geometry."""
    omitted = _request(
        [
            block_sketch(SKETCH_ID),
            extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
            hole_input(HOLE_ID, TOP_FACE, (20.0, 12.5, 10.0), 10.0, THROUGH),
        ]
    )
    explicit = _request(
        [
            block_sketch(SKETCH_ID),
            extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
            _hole_typed(HOLE_ID, 10.0, THROUGH, {"kind": "simple"}),
        ]
    )
    r_omitted = client.post("/api/v1/evaluate", json=omitted)
    r_explicit = client.post("/api/v1/evaluate", json=explicit)
    assert r_omitted.status_code == r_explicit.status_code == 200
    assert r_omitted.content == r_explicit.content
    # And still the exact slice-1 through-hole geometry (7/15/1, analytic volume).
    props = EvaluateTreeResult.model_validate(r_omitted.json()).properties
    assert props is not None
    assert props.volume == _approx(THROUGH_VOLUME)
    assert (props.topology.faces, props.topology.edges, props.topology.shells) == (
        7,
        15,
        1,
    )


# --- Typed degradation — per-feature errors, never 500 -------------------------------


def test_counterbore_not_larger_than_bore_is_hole_cbore_invalid() -> None:
    """A counterbore diameter <= the bore seats nothing -> hole_cbore_invalid
    (a per-feature error, tree still 200), never a raise or a wrong body."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                _hole_typed(
                    HOLE_ID,
                    10.0,
                    THROUGH,
                    {
                        "kind": "counterbore",
                        "cbore_diameter_mm": 8.0,
                        "cbore_depth_mm": 4.0,
                    },
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_cbore_invalid"


def test_countersink_not_larger_than_bore_is_hole_csink_invalid() -> None:
    """A countersink mouth <= the bore -> hole_csink_invalid (per-feature error)."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                _hole_typed(
                    HOLE_ID,
                    10.0,
                    THROUGH,
                    {
                        "kind": "countersink",
                        "csink_diameter_mm": 10.0,
                        "csink_angle_deg": 90.0,
                    },
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_csink_invalid"


def test_counterbore_deeper_than_body_is_hole_too_deep() -> None:
    """A counterbore recess deeper than the 10 mm block cannot form its annulus ->
    hole_too_deep (reuses the bore's over-deep posture), never a silent breakthrough."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                _hole_typed(
                    HOLE_ID,
                    10.0,
                    THROUGH,
                    {
                        "kind": "counterbore",
                        "cbore_diameter_mm": 18.0,
                        "cbore_depth_mm": 14.0,
                    },
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_too_deep"


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
    """A face signature whose supporting PLANE exists on no current face degrades
    exactly as the on_face datum does — subshape_unresolved. The +Z plane at z=99
    matches nothing, so neither the strict signature nor the resilient coplanar
    re-match (FINDINGS #3) resolves it — an honest error, never a wrong face."""
    result = _post(
        _request(
            [
                block_sketch(SKETCH_ID),
                extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
                hole_input(
                    HOLE_ID,
                    ((0.0, 0.0, 1.0), (20.0, 12.5, 99.0), 1000.0),
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


# --- Kernel-level geometric guards (geometry-QA 2026-07-23) ---------------------------
#
# The golden ``hole-through-r5-40x25x10`` and the API tests above only exercise a
# Ø10 through-hole at the CENTRE of an AXIS-ALIGNED (+Z / -Z) face of a prismatic
# block. These guards drive :func:`geometry.kernel.bore_hole` DIRECTLY (the same
# entry the feature layer calls, past the schema) over the cases that single
# centred/axis-aligned golden structurally cannot catch: a tilted placement face
# (would expose a hardcoded/transposed drill axis), a partial edge breakout
# (partial-volume correctness + valid-solid invariant), a stepped body with an
# internal air gap (through-all must clear ALL solid segments, not the gap), a
# flat blind bottom off-centre, an oversize/degenerate diameter (typed, never a
# raw kernel raise reachable from the UI), and cross-restart determinism.
#
# Tolerance: analytic-volume parity uses abs=1e-6 mm^3 (KERNEL_VOL_TOL). The
# measured residual on every case below is <=1.5e-12 mm^3 (observed 2026-07-23,
# build123d 0.11.1 / OCCT 7.9); 1e-6 sits ~6 orders above that float-noise floor
# and >8 orders below the whole-mm^3 volumes a real bore removes, so it never
# false-passes a wrong-volume bore. It is a NEW assertion (not a loosening of the
# golden's 1e-9) sized for the boolean residual on rotated/stepped bodies.

KERNEL_VOL_TOL = 1e-6


def _kvol(value: float) -> Any:
    return pytest.approx(value, abs=KERNEL_VOL_TOL)


def _block(dx: float, dy: float, dz: float) -> Solid:
    """A dx*dy*dz box with its min corner at the origin (top face +Z at z=dz)."""
    return Solid.make_box(dx, dy, dz)


def _face_plane_with_normal(
    body: Any, normal: tuple[float, float, float], *, tol: float = 1e-6
) -> Plane:
    """The deterministic sketch plane of the planar face whose OUTWARD normal is
    ``normal`` (the SAME record :func:`resolve_face_plane` would return). Asserts
    exactly one such face so the test never silently drills the wrong face."""
    want = Vector(*normal).normalized()
    matches = [
        r.plane for r in planar_faces(body) if (r.plane.z_dir - want).length < tol
    ]
    assert len(matches) == 1, (
        f"expected 1 face with normal {normal}, got {len(matches)}"
    )
    return matches[0]


def _circular_segment_area(radius: float, dist: float) -> float:
    """Area of the disk (``radius``) lying BEYOND a chord ``dist`` from centre
    (the part clipped off when the bore centre sits ``dist`` inside an edge)."""
    return radius * radius * math.acos(dist / radius) - dist * math.sqrt(
        radius * radius - dist * dist
    )


def test_hole_axis_follows_nonaxis_aligned_face_normal() -> None:
    """A through-hole on a face whose normal is NOT +-X/+-Y/+-Z drills along that
    face normal (into the solid), removing EXACTLY pi*r^2*thickness. A hardcoded
    -Z axis or a transposed normal would remove the wrong volume (or nothing).

    The 40x25x10 block is rotated 30deg about global X, so the (formerly +Z) top
    face now has normal (0, -sin30, cos30) and the drill axis must track it."""
    body = _block(40.0, 25.0, 10.0).rotate(Axis((0, 0, 0), (1, 0, 0)), 30.0)
    top = _face_plane_with_normal(
        body, (0.0, -math.sin(math.radians(30)), math.cos(math.radians(30)))
    )
    before = float(body.volume)
    drilled = bore_hole(
        body,
        top,
        (top.origin.X, top.origin.Y, top.origin.Z),
        10.0,
        through_all=True,
        depth_mm=None,
    )
    removed = before - float(drilled.volume)
    assert removed == _kvol(math.pi * RADIUS * RADIUS * 10.0)
    # A clean through-bore: same 7/15/1 topology as the axis-aligned golden, 1 lump.
    assert (
        len(drilled.faces()),
        len(drilled.edges()),
        len(drilled.shells()),
    ) == (7, 15, 1)
    assert lump_count(drilled) == 1


def test_hole_partial_breakout_matches_analytic_partial_volume() -> None:
    """A through-hole whose bore partially EXITS the side wall removes LESS than
    pi*r^2*h: exactly the volume of the disk-segment still inside the body. The
    result stays a single valid solid (positive volume, one lump) — it must never
    silently produce an invalid body. Centre 3 mm from the x=0 wall, r=5 => the
    bore pokes 2 mm past the wall."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    before = float(body.volume)
    drilled = bore_hole(
        body, top, (3.0, 12.5, 10.0), 10.0, through_all=True, depth_mm=None
    )
    removed = before - float(drilled.volume)
    full = math.pi * RADIUS * RADIUS * 10.0
    inside_area = math.pi * RADIUS * RADIUS - _circular_segment_area(RADIUS, 3.0)
    assert removed == _kvol(inside_area * 10.0)
    assert removed < full  # strictly less than a fully-embedded bore
    assert float(drilled.volume) > 0.0
    assert lump_count(drilled) == 1
    assert len(drilled.shells()) == 1


def test_blind_hole_partial_edge_breakout_is_too_deep_error() -> None:
    """A BLIND bore that overhangs the face edge removes less than its analytic
    pocket, so it cannot form its full depth -> HoleTooDeepError (the documented
    over-deep/overhang posture), never a silently short pocket."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    with pytest.raises(HoleTooDeepError):
        bore_hole(body, top, (3.0, 12.5, 10.0), 10.0, through_all=False, depth_mm=4.0)


def test_through_all_clears_stepped_body_segments_only() -> None:
    """Through-all on a NON-prismatic body with an internal air gap clears ALL
    solid along the axis and removes the SUM of the solid segments — NOT the gap.

    A C-channel (two 3 mm flanges at z in [0,3] and [12,15], joined by a web at
    x in [0,3]) is ONE solid with a 9 mm gap. Drilling Ø6 at x=20 (clear of the
    web) passes flange1 (3 mm), the 9 mm gap, then flange2 (3 mm): the correct
    removed volume is pi*r^2*(3+3), NOT pi*r^2*15 (which would wrongly fill the
    gap) and NOT pi*r^2*3 (a through-all that stopped at the first solid)."""
    bottom = _block(40.0, 25.0, 3.0)
    top_flange = _block(40.0, 25.0, 3.0).located(Location((0.0, 0.0, 12.0)))
    web = _block(3.0, 25.0, 15.0)
    body = combine_body(combine_body(bottom, web, "add"), top_flange, "add")
    assert lump_count(body) == 1
    # Two +Z faces exist (the top flange at z=15 and the exposed step at z=3);
    # drill from the highest so the axis spans BOTH flanges and the air gap.
    top = max(
        (
            r.plane
            for r in planar_faces(body)
            if (r.plane.z_dir - Vector(0, 0, 1)).length < 1e-6
        ),
        key=lambda p: p.origin.Z,
    )
    before = float(body.volume)
    drilled = bore_hole(
        body, top, (20.0, 12.5, 15.0), 6.0, through_all=True, depth_mm=None
    )
    removed = before - float(drilled.volume)
    r = 3.0
    assert removed == _kvol(math.pi * r * r * (3.0 + 3.0))
    assert removed < math.pi * r * r * 15.0  # did not fill the 9 mm air gap
    assert lump_count(drilled) == 1


def test_blind_hole_flat_bottom_sits_at_exact_depth_off_center() -> None:
    """An OFF-CENTRE blind hole (flat-drill v1) leaves a flat bottom cap at
    exactly ``depth`` below the face and the far face intact: removed volume is
    pi*r^2*depth, and a +Z planar cap of area pi*r^2 sits at z = thickness-depth.
    Off-centre so the golden's on-axis-centroid symmetry can't hide a mistake."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    radius, depth = 4.0, 6.5
    drilled = bore_hole(
        body, top, (12.0, 10.0, 10.0), 2.0 * radius, through_all=False, depth_mm=depth
    )
    removed = 40.0 * 25.0 * 10.0 - float(drilled.volume)
    assert removed == _kvol(math.pi * radius * radius * depth)
    assert abs(drilled.bounding_box().min.Z) < KERNEL_VOL_TOL
    caps = [
        r
        for r in planar_faces(drilled)
        if (r.plane.z_dir - Vector(0, 0, 1)).length < 1e-6
        and abs(r.signature.area_mm2 - math.pi * radius * radius) < 1e-3
    ]
    assert len(caps) == 1, "exactly one +Z bore-bottom cap"
    assert abs(caps[0].plane.origin.Z - (10.0 - depth)) < KERNEL_VOL_TOL


def test_oversize_diameter_degrades_to_typed_boolean_error() -> None:
    """A bore whose diameter covers the WHOLE face consumes the entire body: the
    lump-preserving cut leaves no material -> a typed BooleanError (mapped to
    ``boolean_failed`` at the feature layer), never an invalid solid or a 500."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    with pytest.raises(BooleanError):
        bore_hole(body, top, (20.0, 12.5, 10.0), 100.0, through_all=True, depth_mm=None)


def test_negative_diameter_is_typed_hole_error() -> None:
    """bore_hole rejects a non-positive diameter with a typed HoleError BEFORE it
    reaches OCCT (FINDINGS #23). Guarded in :func:`bore_tool` (the shared drill
    builder), so the pattern/mirror reconstruction path is covered too. Formerly
    xfail: a raw OCCT ``Standard_ConstructionError`` would escape the feature
    layer's HoleError handlers as a 500. Unreachable from the API
    (``HoleParamsV1.diameter_mm`` is ``Field(gt=0)``) — this is defence-in-depth."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    with pytest.raises(HoleInvalidDiameterError):
        bore_hole(body, top, (20.0, 12.5, 10.0), -10.0, through_all=True, depth_mm=None)
    # a zero diameter is likewise a non-drill, not a raw kernel raise.
    with pytest.raises(HoleInvalidDiameterError):
        bore_hole(body, top, (20.0, 12.5, 10.0), 0.0, through_all=True, depth_mm=None)


def test_bore_hole_is_deterministic_across_repeated_kernel_eval() -> None:
    """The drilled body is a pure function of its inputs (RESEARCH §9): N repeats
    yield byte-identical volume, surface area, and topology metadata. Complements
    the API byte-determinism golden and the manually-verified cross-restart check
    (two fresh interpreters produced identical volume/SA reprs, 2026-07-23)."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    signatures: set[tuple[str, str, int, int, int]] = set()
    for _ in range(8):
        drilled = bore_hole(
            body, top, (20.0, 12.5, 10.0), 10.0, through_all=True, depth_mm=None
        )
        signatures.add(
            (
                repr(float(drilled.volume)),
                repr(float(drilled.area)),
                len(drilled.faces()),
                len(drilled.edges()),
                len(drilled.shells()),
            )
        )
    assert len(signatures) == 1


# --- Slice 2 recess cuts — kernel-level analytic + degradation (off-centre) ----------
#
# Drive cut_counterbore / cut_countersink DIRECTLY (past the schema) on an
# already-drilled body, OFF-CENTRE and off axis-aligned so the golden's centred +Z
# symmetry cannot hide an axis/normal mistake, and over the degradation paths the
# API tests reach only through the evaluator.


def _drilled(
    body: Solid, position: tuple[float, float, float], diameter: float
) -> BodyShape:
    """A through-bored body at ``position`` (the recess cut's precondition)."""
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    return bore_hole(body, top, position, diameter, through_all=True, depth_mm=None)


def test_cut_counterbore_removes_exact_annulus_off_center_and_tilted() -> None:
    """Off-centre counterbore on a 30°-tilted block removes EXACTLY
    π·(R²-r²)·h_cbore beyond the bore — proving the recess tracks the face normal
    (not a hardcoded axis) and the analytic annulus, staying one valid lump."""
    body = _block(40.0, 25.0, 10.0).rotate(Axis((0, 0, 0), (1, 0, 0)), 30.0)
    normal = (0.0, -math.sin(math.radians(30)), math.cos(math.radians(30)))
    top = _face_plane_with_normal(body, normal)
    # A point on the (tilted) top face, off the centroid axis.
    pos = top.origin + top.x_dir * 6.0
    bored = bore_hole(
        body, top, (pos.X, pos.Y, pos.Z), 8.0, through_all=True, depth_mm=None
    )
    after_bore = float(bored.volume)
    recessed = cut_counterbore(
        bored,
        top,
        (pos.X, pos.Y, pos.Z),
        bore_diameter_mm=8.0,
        cbore_diameter_mm=16.0,
        cbore_depth_mm=3.0,
    )
    removed = after_bore - float(recessed.volume)
    assert removed == _kvol(math.pi * (8.0**2 - 4.0**2) * 3.0)
    assert lump_count(recessed) == 1


def test_cut_countersink_removes_exact_annular_cone_off_center() -> None:
    """Off-centre countersink removes EXACTLY the frustum minus the already-bored
    inner cylinder (π·h/3·(R²+R·r-2r²)), with h from the 82° included angle — the
    other fastener standard, so a non-45° slope exercises the tan(angle/2) math."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    pos = (12.0, 9.0, 10.0)
    bored = bore_hole(body, top, pos, 6.0, through_all=True, depth_mm=None)
    after_bore = float(bored.volume)
    recessed = cut_countersink(
        bored,
        top,
        pos,
        bore_diameter_mm=6.0,
        csink_diameter_mm=12.0,
        csink_angle_deg=82.0,
    )
    removed = after_bore - float(recessed.volume)
    r_bore, r_csink = 3.0, 6.0
    h = (r_csink - r_bore) / math.tan(math.radians(41.0))
    frustum = math.pi * h / 3.0 * (r_csink**2 + r_csink * r_bore + r_bore**2)
    expected = frustum - math.pi * r_bore * r_bore * h
    assert removed == _kvol(expected)
    assert lump_count(recessed) == 1


def test_cut_counterbore_not_larger_than_bore_raises_recess_invalid() -> None:
    """A counterbore diameter <= the bore is a typed HoleRecessInvalidError
    (the feature layer maps it to hole_cbore_invalid), never a raw geometry op."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleRecessInvalidError):
        cut_counterbore(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            cbore_diameter_mm=10.0,
            cbore_depth_mm=3.0,
        )


def test_cut_countersink_not_larger_than_bore_raises_recess_invalid() -> None:
    """A countersink mouth <= the bore is a typed HoleRecessInvalidError."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleRecessInvalidError):
        cut_countersink(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            csink_diameter_mm=9.0,
            csink_angle_deg=90.0,
        )


def test_cut_counterbore_deeper_than_body_raises_too_deep() -> None:
    """A counterbore recess deeper than the block cannot form its full annulus ->
    HoleTooDeepError (mapped to hole_too_deep), never a silent breakthrough."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleTooDeepError):
        cut_counterbore(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            cbore_diameter_mm=18.0,
            cbore_depth_mm=14.0,
        )


# --- Slice 2 recess — adversarial gaps past the axis-aligned goldens ------------------
# (geometry-QA 2026-07-23, commit d82cd27) The counterbore/countersink goldens and the
# recess kernel tests above cover a CENTRED +Z counterbore (tilted for the counterbore
# annulus) and a 82° axis-aligned countersink. These guards push the recesses over the
# cases those cannot reach: a countersink on a NON-axis-aligned face (coaxial along the
# FACE normal, not world Z — a hardcoded-axis bug surfaces here), the real drill-point
# angle standards (60/82/90/118°) against the h=(R-r)/tan(θ/2) frustum, the shallow-cone
# (θ→180°) and over-steep (deep-cone) limits, the r→R degenerate mouth, the counterbore
# recess that breaks fully through (depth == thickness) vs over-thickness, a recess that
# overhangs the face edge, a blind-bore + counterbore stack, and recess determinism.
# Every measured residual below is ≤5e-12 mm³ (observed 2026-07-23, build123d 0.11.1 /
# OCCT 7.9); KERNEL_VOL_TOL (1e-6) sits ~6 orders above that and >8 below the bore's
# whole-mm³ removal, so it never false-passes a wrong-volume recess.


def _csink_annular_cone(r_bore: float, r_csink: float, angle_deg: float) -> float:
    """Analytic ANNULAR-cone volume a countersink removes beyond an existing bore:
    the frustum π·h/3·(R²+R·r+r²) minus the already-bored inner cylinder π·r²·h,
    with the cone depth h=(R-r)/tan(θ/2) the included angle θ implies."""
    h = (r_csink - r_bore) / math.tan(math.radians(angle_deg / 2.0))
    frustum = math.pi * h / 3.0 * (r_csink**2 + r_csink * r_bore + r_bore**2)
    return frustum - math.pi * r_bore * r_bore * h


def test_cut_countersink_tracks_tilted_face_normal() -> None:
    """A countersink on a 30°-tilted face sinks its cone COAXIAL WITH THE BORE
    along the FACE normal (not world Z): the removed material equals the analytic
    annular cone exactly, one valid lump. Only the counterbore had a tilted-face
    guard; a hardcoded/transposed cone axis would surface here as a wrong volume."""
    body = _block(40.0, 25.0, 10.0).rotate(Axis((0, 0, 0), (1, 0, 0)), 30.0)
    normal = (0.0, -math.sin(math.radians(30)), math.cos(math.radians(30)))
    top = _face_plane_with_normal(body, normal)
    pos = top.origin + top.x_dir * 6.0  # off the centroid axis, on the tilted face
    bored = bore_hole(
        body, top, (pos.X, pos.Y, pos.Z), 6.0, through_all=True, depth_mm=None
    )
    after_bore = float(bored.volume)
    recessed = cut_countersink(
        bored,
        top,
        (pos.X, pos.Y, pos.Z),
        bore_diameter_mm=6.0,
        csink_diameter_mm=12.0,
        csink_angle_deg=90.0,
    )
    removed = after_bore - float(recessed.volume)
    assert removed == _kvol(_csink_annular_cone(3.0, 6.0, 90.0))
    assert lump_count(recessed) == 1


def test_cut_countersink_angle_sweep_matches_analytic_frustum() -> None:
    """The four real drill-point standards (60°, 82°, 90°, 118° included) each
    remove EXACTLY π·h/3·(R²+R·r+r²)-π·r²·h with h=(R-r)/tan(θ/2): a Ø12 mouth over
    a Ø6 bore in a 10 mm block. Exercises the tan(θ/2) slope across the fastener
    range (a fixed 45°/90° special-case would drift at 60/82/118°); 8 faces each."""
    for angle in (60.0, 82.0, 90.0, 118.0):
        body = _block(40.0, 25.0, 10.0)
        top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
        pos = (20.0, 12.5, 10.0)
        bored = bore_hole(body, top, pos, 6.0, through_all=True, depth_mm=None)
        after_bore = float(bored.volume)
        recessed = cut_countersink(
            bored,
            top,
            pos,
            bore_diameter_mm=6.0,
            csink_diameter_mm=12.0,
            csink_angle_deg=angle,
        )
        removed = after_bore - float(recessed.volume)
        assert removed == _kvol(_csink_annular_cone(3.0, 6.0, angle)), (
            f"angle {angle}° removed {removed}"
        )
        assert len(recessed.faces()) == 8
        assert lump_count(recessed) == 1


def test_cut_countersink_shallow_angle_is_valid_shallow_frustum() -> None:
    """A very SHALLOW cone — 150° included (half-angle 75°, cone depth only
    (R-r)/tan(75°) ≈ 0.80 mm) — still forms the correct thin frustum, not a
    degenerate sliver: removed matches the analytic annular cone, one lump."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    pos = (20.0, 12.5, 10.0)
    bored = bore_hole(body, top, pos, 6.0, through_all=True, depth_mm=None)
    after_bore = float(bored.volume)
    recessed = cut_countersink(
        bored,
        top,
        pos,
        bore_diameter_mm=6.0,
        csink_diameter_mm=12.0,
        csink_angle_deg=150.0,
    )
    removed = after_bore - float(recessed.volume)
    assert removed == _kvol(_csink_annular_cone(3.0, 6.0, 150.0))
    assert lump_count(recessed) == 1


def test_cut_countersink_steep_angle_deep_cone_is_too_deep() -> None:
    """An over-steep included angle drives the cone deeper than the material: at
    20° the implied depth (R-r)/tan(10°) ≈ 17 mm exceeds the 10 mm block, so the
    cone would break through -> HoleTooDeepError, never a silently short cone."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 6.0)
    with pytest.raises(HoleTooDeepError):
        cut_countersink(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=6.0,
            csink_diameter_mm=12.0,
            csink_angle_deg=20.0,
        )


def test_cut_countersink_diameter_equals_bore_is_recess_invalid() -> None:
    """The degenerate mouth r→R (countersink diameter EXACTLY the bore, cone depth
    h→0) seats nothing -> HoleRecessInvalidError, never a zero-height cone tool /
    invalid solid. The `radius <= bore_radius` guard trips on the equality."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleRecessInvalidError):
        cut_countersink(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            csink_diameter_mm=10.0,
            csink_angle_deg=90.0,
        )


def test_cut_countersink_cone_deeper_than_blind_bore_is_valid_solid() -> None:
    """A cone that outreaches a SHORT blind bore (bore 2 mm, 90° cone depth 4 mm)
    cuts the annulus PLUS the fresh material below the bore bottom: removed is
    GREATER than the through-bore annular formula (which pre-subtracts a full-depth
    cylinder), and the result stays a single valid positive-volume solid — the
    boolean does not fail when the cone tip passes the bore floor."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    pos = (20.0, 12.5, 10.0)
    bored = bore_hole(body, top, pos, 10.0, through_all=False, depth_mm=2.0)
    after_bore = float(bored.volume)
    recessed = cut_countersink(
        bored,
        top,
        pos,
        bore_diameter_mm=10.0,
        csink_diameter_mm=18.0,
        csink_angle_deg=90.0,
    )
    removed = after_bore - float(recessed.volume)
    # Cone (4 mm) reaches past the bore floor (2 mm): more than the annular cone
    # that assumes a full-depth bore beneath it.
    assert removed > _csink_annular_cone(5.0, 9.0, 90.0)
    assert float(recessed.volume) > 0.0
    assert lump_count(recessed) == 1


def test_cut_counterbore_depth_equals_thickness_is_through_recess() -> None:
    """A counterbore whose depth EQUALS the body thickness breaks the recess fully
    through the far face (a Ø-cbore through step): the coincident far-face boolean
    is clean — removed is the full annulus π·(R²-r²)·thickness, one valid lump. The
    boundary case between a seated recess and a `hole_too_deep` over-thickness one."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    after_bore = float(bored.volume)
    recessed = cut_counterbore(
        bored,
        top,
        (20.0, 12.5, 10.0),
        bore_diameter_mm=10.0,
        cbore_diameter_mm=18.0,
        cbore_depth_mm=10.0,
    )
    removed = after_bore - float(recessed.volume)
    assert removed == _kvol(math.pi * (9.0**2 - 5.0**2) * 10.0)
    assert lump_count(recessed) == 1


def test_cut_counterbore_just_over_thickness_is_too_deep() -> None:
    """A counterbore a hair deeper than the thickness (10.001 mm on a 10 mm block)
    cannot form its full annulus in the material -> HoleTooDeepError. Pins the
    boundary just ABOVE the exact-thickness through-recess that IS allowed."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (20.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleTooDeepError):
        cut_counterbore(
            bored,
            top,
            (20.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            cbore_diameter_mm=18.0,
            cbore_depth_mm=10.001,
        )


def test_cut_counterbore_recess_edge_overhang_is_too_deep() -> None:
    """A counterbore whose wider recess pokes past the side wall (bore Ø10 fully
    inside at x=6, but the Ø18 recess spans x∈[-3,15], 3 mm past the x=0 wall)
    removes LESS than its full analytic annulus, so — like a blind pocket that
    overhangs — it degrades to HoleTooDeepError (the documented edge-overhang
    posture), never a silently partial recess. Note the deliberate asymmetry: a
    THROUGH-bore is allowed to break out an edge (partial volume), but a RECESS is
    held to its full analytic annulus, so an edge-overhanging recess is rejected."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    bored = _drilled(body, (6.0, 12.5, 10.0), 10.0)
    with pytest.raises(HoleTooDeepError):
        cut_counterbore(
            bored,
            top,
            (6.0, 12.5, 10.0),
            bore_diameter_mm=10.0,
            cbore_diameter_mm=18.0,
            cbore_depth_mm=4.0,
        )


def test_blind_bore_plus_counterbore_volumes_sum() -> None:
    """A BLIND bore (8 mm deep) with a counterbore recess (Ø18, 4 mm) at the face:
    the bore removes π·r²·8, the recess the annulus π·(R²-r²)·4, and the total
    removed is their sum to machine precision — the recess seats at the face while
    the bore bottom stays blind at 8 mm (10 faces: 6 block + bore wall + bore
    bottom cap + cbore wall + cbore flat-bottom annulus), one lump."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    pos = (20.0, 12.5, 10.0)
    bored = bore_hole(body, top, pos, 10.0, through_all=False, depth_mm=8.0)
    bore_removed = 10000.0 - float(bored.volume)
    recessed = cut_counterbore(
        bored,
        top,
        pos,
        bore_diameter_mm=10.0,
        cbore_diameter_mm=18.0,
        cbore_depth_mm=4.0,
    )
    total_removed = 10000.0 - float(recessed.volume)
    exp_bore = math.pi * RADIUS * RADIUS * 8.0
    exp_annulus = math.pi * (9.0**2 - 5.0**2) * 4.0
    assert bore_removed == _kvol(exp_bore)
    assert total_removed == _kvol(exp_bore + exp_annulus)
    assert len(recessed.faces()) == 10
    assert lump_count(recessed) == 1


def test_recess_cuts_are_deterministic_across_repeats() -> None:
    """Counterbore and countersink recesses are pure functions of their inputs
    (RESEARCH §9): N rebuilds yield byte-identical volume, area, and topology
    metadata. Complements the bore determinism guard and the manually-verified
    cross-restart check (two fresh interpreters produced identical CB/CS
    volume/area/topology reprs, geometry-QA 2026-07-23)."""
    sigs: set[tuple[str, str, int, int, int, str, str, int, int, int]] = set()
    for _ in range(6):
        body = _block(40.0, 25.0, 10.0)
        top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
        pos = (20.0, 12.5, 10.0)
        bored = bore_hole(body, top, pos, 10.0, through_all=True, depth_mm=None)
        cb = cut_counterbore(
            bored,
            top,
            pos,
            bore_diameter_mm=10.0,
            cbore_diameter_mm=18.0,
            cbore_depth_mm=4.0,
        )
        cs = cut_countersink(
            bored,
            top,
            pos,
            bore_diameter_mm=10.0,
            csink_diameter_mm=18.0,
            csink_angle_deg=90.0,
        )
        sigs.add(
            (
                repr(float(cb.volume)),
                repr(float(cb.area)),
                len(cb.faces()),
                len(cb.edges()),
                len(cb.shells()),
                repr(float(cs.volume)),
                repr(float(cs.area)),
                len(cs.faces()),
                len(cs.edges()),
                len(cs.shells()),
            )
        )
    assert len(sigs) == 1


# --- Slice 2 TAIL: TAPPED holes — a cosmetic thread callout over the tap drill -------
#
# The v1 thread representation is COSMETIC (decision + rationale + the modelled-
# thread upgrade path: geometry/kernel/threads.py): the kernel cuts the tap-drill
# bore and carries the designation as metadata. These tests hold that decision to
# its two promises — the geometry is EXACTLY the bore (byte-identical to the same
# hole untapped), and a callout the kernel cannot honour is a TYPED error rather
# than a plain hole wearing a thread nobody can cut.

#: The golden's tapped hole: M10x1.5 -> tap drill D - P = 8.5 mm (r = 4.25).
M10_TAP_DRILL = 8.5
_TAPPED_REMOVED = math.pi * (M10_TAP_DRILL / 2.0) ** 2 * 10.0


def _thread(nominal_diameter_mm: float, pitch_mm: float) -> dict[str, Any]:
    return {
        "standard": "iso_metric",
        "nominal_diameter_mm": nominal_diameter_mm,
        "pitch_mm": pitch_mm,
    }


def _tapped_hole(
    diameter_mm: float,
    thread: dict[str, Any] | None,
    hole_type: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A centred through-hole on the block's top face, optionally tapped."""
    params: dict[str, Any] = {
        "face": _face_ref(EXTRUDE_ID, *TOP_FACE),
        "position": {"x": 20.0, "y": 12.5, "z": 10.0},
        "diameter_mm": diameter_mm,
        "depth": dict(THROUGH),
    }
    if thread is not None:
        params["thread"] = thread
    if hole_type is not None:
        params["type"] = hole_type
    return {
        "id": str(HOLE_ID),
        "feature": {"type": "hole", "version": 1, "params": params},
    }


def _tapped_tree(
    diameter_mm: float,
    thread: dict[str, Any] | None,
    hole_type: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _request(
        [
            block_sketch(SKETCH_ID),
            extrude_add(EXTRUDE_ID, SKETCH_ID, 10.0),
            _tapped_hole(diameter_mm, thread, hole_type),
        ]
    )


def test_tapped_hole_removes_exactly_the_tap_drill_bore() -> None:
    """An M10x1.5 tapped through-hole removes EXACTLY π·(8.5/2)²·10 — the ISO tap
    drill D - P — and keeps the plain through-hole's 7/15/1 topology. The golden
    `hole-tapped-m10x1.5-40x25x10` pins the same body through the harness; this
    asserts it over the REST evaluate path with the analytic value."""
    result = _post(_tapped_tree(M10_TAP_DRILL, _thread(10.0, 1.5)))

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == _approx(BLOCK_VOLUME - _TAPPED_REMOVED)
    assert (
        result.properties.topology.faces,
        result.properties.topology.edges,
        result.properties.topology.shells,
    ) == (7, 15, 1)
    # A through bore is symmetric about the mid-plane (unlike a recess).
    assert result.properties.centroid.z == _approx(5.0)


def test_tapped_hole_is_byte_identical_to_the_same_bore_untapped() -> None:
    """THE COSMETIC DECISION, made assertable: adding a thread callout to a hole
    changes NO geometry. The evaluate response for a Ø8.5 hole with an M10x1.5
    thread is byte-for-byte the response for the same Ø8.5 hole with no thread —
    same mesh id, same mass properties, same topology.

    This is what makes a tapped hole free to mirror, pattern, shell and export:
    downstream sees the bore it always saw. It also fails loudly the day someone
    "improves" the tap into geometry without giving it its own golden."""
    tapped = client.post(
        "/api/v1/evaluate", json=_tapped_tree(M10_TAP_DRILL, _thread(10.0, 1.5))
    )
    untapped = client.post("/api/v1/evaluate", json=_tapped_tree(M10_TAP_DRILL, None))

    assert tapped.status_code == untapped.status_code == 200
    assert tapped.content == untapped.content


def test_tapped_hole_may_also_be_counterbored() -> None:
    """Threading is ORTHOGONAL to the recess (why `thread` is its own field and
    not a fourth `HoleType` member): a counterbored TAPPED hole — a cap screw head
    sunk over an M10x1.5 tapped bore — is one feature, and removes exactly the
    bore plus the annular recess."""
    result = _post(
        _tapped_tree(
            M10_TAP_DRILL,
            _thread(10.0, 1.5),
            {"kind": "counterbore", "cbore_diameter_mm": 18.0, "cbore_depth_mm": 4.0},
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    annulus = math.pi * (9.0**2 - (M10_TAP_DRILL / 2.0) ** 2) * 4.0
    assert result.properties.volume == _approx(BLOCK_VOLUME - _TAPPED_REMOVED - annulus)
    assert result.properties.centroid.z < 5.0


@pytest.mark.parametrize(
    ("nominal_mm", "pitch_mm", "why"),
    [
        (10.0, 1.4, "1.4 is not a standard pitch for M10 (1.5/1.25/1.0/0.75)"),
        (7.0, 1.0, "M7 is not in the ISO 261 series"),
        (10.0, 0.5, "0.5 is a pitch of M4/M5, never of M10"),
    ],
)
def test_unhonourable_designation_is_hole_thread_unsupported(
    nominal_mm: float, pitch_mm: float, why: str
) -> None:
    """A designation the kernel cannot honour is a TYPED per-feature error — never
    a silent fallback to an untapped hole (which would ship a part whose drawing
    calls out a thread nobody can cut). The tree still answers 200, and the
    strict-prefix rule leaves the last-good body at the un-drilled block."""
    result = _post(_tapped_tree(M10_TAP_DRILL, _thread(nominal_mm, pitch_mm)))

    assert [r.status for r in result.features] == ["ok", "ok", "error"], why
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_thread_unsupported"
    # Validated BEFORE any geometry: the body is the plain block, not a bore.
    assert result.properties is not None
    assert result.properties.volume == _approx(BLOCK_VOLUME)


@pytest.mark.parametrize(
    ("bore_mm", "why"),
    [
        (10.0, "a bore AT the nominal diameter leaves no material to tap"),
        (12.0, "a bore wider than the nominal diameter is not a tapped hole"),
        (6.0, "a bore below the minor diameter 8.376mm cannot admit the tap"),
    ],
)
def test_bore_the_thread_cannot_be_tapped_in_is_hole_thread_mismatch(
    bore_mm: float, why: str
) -> None:
    """An M10x1.5 callout on a bore outside [minor, nominal) is
    `hole_thread_mismatch` — the silent-wrong class this slice closes (a Ø12 hole
    labelled M10 is a drawing that lies). Body untouched."""
    result = _post(_tapped_tree(bore_mm, _thread(10.0, 1.5)))

    assert [r.status for r in result.features] == ["ok", "ok", "error"], why
    assert result.features[2].error is not None
    assert result.features[2].error.code == "hole_thread_mismatch"
    assert result.properties is not None
    assert result.properties.volume == _approx(BLOCK_VOLUME)


def test_tapped_hole_registry_roundtrip_keeps_the_designation() -> None:
    """A tapped hole survives the shared FEATURE_REGISTRY (documents' persist/read
    path) with its designation intact, and evaluates ok — the thread is params,
    which is exactly how a drawing/BOM callout will read it."""
    envelope = _tapped_hole(M10_TAP_DRILL, _thread(10.0, 1.5))["feature"]
    loaded = FEATURE_REGISTRY.load(
        envelope["type"], envelope["version"], envelope["params"]
    )
    assert isinstance(loaded, HoleFeature)
    thread = loaded.params.thread
    assert thread is not None
    assert (thread.standard, thread.nominal_diameter_mm, thread.pitch_mm) == (
        "iso_metric",
        10.0,
        1.5,
    )
    result = _post(_tapped_tree(M10_TAP_DRILL, _thread(10.0, 1.5)))
    assert [r.status for r in result.features] == ["ok", "ok", "ok"]


# --- Kernel-level: the ISO 261 table and its derived diameters -----------------------


@pytest.mark.parametrize(
    ("nominal_mm", "pitch_mm", "designation", "tap_drill_mm"),
    [
        (3.0, 0.5, "M3x0.5", 2.5),
        (4.0, 0.7, "M4x0.7", 3.3),
        (5.0, 0.8, "M5x0.8", 4.2),
        (6.0, 1.0, "M6x1", 5.0),
        (8.0, 1.25, "M8x1.25", 6.75),
        (10.0, 1.5, "M10x1.5", 8.5),
        (12.0, 1.75, "M12x1.75", 10.25),
        (10.0, 1.25, "M10x1.25", 8.75),
    ],
)
def test_tap_drill_matches_the_published_metric_table(
    nominal_mm: float, pitch_mm: float, designation: str, tap_drill_mm: float
) -> None:
    """The ISO tap-drill rule D - P, cross-checked against the published metric
    tap-drill values (M6 -> 5.0, M10x1.5 -> 8.5, M4 -> 3.3 ...). These are the
    numbers a machinist expects; a wrong derivation here would put a wrong bore in
    every tapped hole the app authors."""
    thread = resolve_iso_metric_thread(nominal_mm, pitch_mm)
    assert thread.designation == designation
    assert thread.tap_drill_diameter_mm == _approx(tap_drill_mm)
    # The minor diameter (100% thread) is always below the tap drill and above 0.
    assert 0.0 < thread.minor_diameter_mm < thread.tap_drill_diameter_mm


def test_every_table_entry_resolves_and_its_tap_drill_is_tappable() -> None:
    """Sweep the WHOLE committed ISO 261 table: every (nominal, pitch) resolves,
    and every one of those threads accepts its own D - P tap drill within the
    tappable band. A table typo (a pitch too coarse for its diameter) shows up
    here as a mismatch rather than in a user's part."""
    for nominal_mm, pitches in ISO_METRIC_PITCHES.items():
        assert pitches, f"M{nominal_mm} has no pitches"
        for pitch_mm in pitches:
            thread = resolve_iso_metric_thread(nominal_mm, pitch_mm)
            assert (
                thread.minor_diameter_mm
                < thread.tap_drill_diameter_mm
                < thread.nominal_diameter_mm
            ), thread.designation
            # Never raises: a thread must accept its own recommended tap drill.
            check_tap_drill_bore(thread, thread.tap_drill_diameter_mm)


def test_a_shop_tables_rounded_drill_is_accepted_but_a_wrong_one_is_not() -> None:
    """The accepted bore band is [minor, nominal), not an exact D - P match: a
    shop table's rounded stock drill (6.8 mm for M8x1.25, where D - P is 6.75) is
    a legitimate tapped hole, while a bore below the minor diameter or at/above
    the nominal diameter is not."""
    thread = resolve_iso_metric_thread(8.0, 1.25)
    check_tap_drill_bore(thread, 6.8)  # stock drill — accepted
    check_tap_drill_bore(thread, thread.minor_diameter_mm)  # 100% thread — accepted
    with pytest.raises(ThreadBoreMismatchError):
        check_tap_drill_bore(thread, 6.0)  # below the minor diameter
    with pytest.raises(ThreadBoreMismatchError):
        check_tap_drill_bore(thread, 8.0)  # at the nominal diameter


def test_unknown_designations_raise_the_typed_kernel_error() -> None:
    """The kernel half of `hole_thread_unsupported`: an off-series diameter and an
    off-standard pitch both raise :class:`ThreadUnsupportedError`, and the message
    names what IS available (a dead end with directions, not a bare refusal)."""
    with pytest.raises(ThreadUnsupportedError) as off_series:
        resolve_iso_metric_thread(7.0, 1.0)
    assert "ISO 261" in str(off_series.value)

    with pytest.raises(ThreadUnsupportedError) as off_pitch:
        resolve_iso_metric_thread(10.0, 1.4)
    # Names the pitches M10 IS standardised at, so the message is a way forward.
    assert "1.5" in str(off_pitch.value)


def test_thread_resolution_is_deterministic() -> None:
    """RESEARCH §9: the same designation resolves to identical derived diameters
    across repeats (pure closed-form arithmetic over the committed table — no
    iteration order, no search)."""
    resolved = {
        (
            repr(t.tap_drill_diameter_mm),
            repr(t.minor_diameter_mm),
            t.designation,
        )
        for t in (resolve_iso_metric_thread(10.0, 1.5) for _ in range(5))
    }
    assert len(resolved) == 1
