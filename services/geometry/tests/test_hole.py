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
    HoleError,
    HoleTooDeepError,
    bore_hole,
)
from geometry.kernel.lumps import lump_count
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT (geometry-QA 2026-07-23): a NEGATIVE diameter raises a raw OCCT "
        "Standard_ConstructionError from Solid.make_cylinder, NOT a typed HoleError "
        "— it would escape _evaluate_hole's HoleError/BooleanError handlers as a 500. "
        "UNREACHABLE from the API today (HoleParamsV1.diameter_mm is Field(gt=0)), so "
        "this is a defence-in-depth gap, not a P0. Flip to a plain raises() when the "
        "kernel guards diameter/radius > 0 with a typed HoleError."
    ),
)
def test_negative_diameter_is_typed_hole_error() -> None:
    """bore_hole should reject a non-positive diameter with a typed HoleError."""
    body = _block(40.0, 25.0, 10.0)
    top = _face_plane_with_normal(body, (0.0, 0.0, 1.0))
    with pytest.raises(HoleError):
        bore_hole(body, top, (20.0, 12.5, 10.0), -10.0, through_all=True, depth_mm=None)


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
