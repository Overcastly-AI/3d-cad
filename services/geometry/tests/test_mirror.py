"""Mirror feature — API-level behavior of the reflect-and-union mirror (P2).

Covers the BACKLOG P2 mirror acceptance beyond the golden harness (the golden
``mirror-triangle-prism-2x`` runs every parametrized gate in ``test_goldens.py``
/ ``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates real
mass properties and a fetchable content-addressed mesh; the REFLECTION-vs-
translation proof is asserted numerically; the overlapping-merge and symmetric
(on-plane) cases are checked by hand-computed volume; the mirror plane resolves
through a `datum` FEATURE ref as well as an origin datum; and every error path —
``no_target_body`` and ``reference_unresolved`` — is a per-feature error pinned
under the strict-prefix rule (design §4.3), never a transport failure.

v1 DESIGN DECISION (option B, the reflective sibling of the ADD pattern): a
mirror reflects the CURRENT body about a plane and unions the reflection into the
single body chain (§7.6). UNLIKE a pattern it does NOT force one connected lump —
a body that clears the plane mirrors to a disjoint TWO-lump body (§MB-0). Numeric
assertions use the documented tree-golden tolerance (measured-then-set,
``goldens/mirror-triangle-prism-2x/expected.json``), not ad-hoc epsilons.
"""

import json
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
    / "mirror-triangle-prism-2x"
    / "model.json"
)

#: The documented tolerance of the mirror golden (expected.json
#: tolerance_rationale: measured EXACTLY 0.0 on every property except a 6.66e-16
#: float residual on centroid.y; 1e-9 is the reviewed planar ceiling).
MIRROR_TOL = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
BODY_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
MIRROR_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")
DATUM_ID = uuid.UUID("00000000-0000-0000-0000-00000000dddd")

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
    """A closed rectangle [x0,x1] x [y0,y1] on XY, unconstrained (solver returns
    the input positions bitwise — same posture as the pattern suite)."""
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
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float = 6.0
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


def mirror_input(feature_id: uuid.UUID, plane: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "mirror",
            "version": 1,
            "params": {"plane": plane},
        },
    }


def datum_offset_input(
    feature_id: uuid.UUID, base: str, offset_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": False},
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 3, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed mirror golden, posted verbatim: all three features ok, the
    disjoint two-lump body volume 72 mm^3 (2V), 2 shells, content-addressed
    mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (BODY_ID, "ok"),
        (MIRROR_ID, "ok"),
    ]
    assert result.last_good_feature_id == MIRROR_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(72.0, abs=MIRROR_TOL)
    assert result.properties.surface_area == pytest.approx(168.0, abs=MIRROR_TOL)
    # A disjoint reflection is a legitimately TWO-lump body (§MB-0), NOT a
    # pattern_disjoint error — the mirror does not force one connected lump.
    assert result.properties.topology.shells == 2
    assert result.properties.topology.faces == 10
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_is_byte_deterministic() -> None:
    """Same mirror tree → identical response bytes INCLUDING mesh_glb_id (a
    content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Reflection proof: a true reflection, not a translation --------------------------


def test_mirror_is_a_reflection_not_a_translation() -> None:
    """The reflection-vs-translation discriminator (BACKLOG P2 acceptance).

    A CHIRAL right-triangle prism (right angle at (2,0), legs to (5,0)/(2,4))
    extruded 6 mm sits entirely at x>0, then mirrored about YZ (x=0). Because
    Shape.mirror is a handedness-reversing isometry, the reflected right angle
    lands at x=-2 (nearest the plane), so the union is mirror-symmetric about
    x=0 → centroid.x is EXACTLY 0. A pure TRANSLATION of this chiral profile that
    reproduced the same disjoint bounding box [-5,5] (a -7 mm shift) would put the
    reflected right angle at x=-5 instead, giving combined centroid.x = -0.5 mm.
    So centroid.x == 0 (to 1e-9) machine-proves a reflection, not a translation;
    a translation would fail this assert by 0.5 mm.
    """
    result = _post(
        _request(
            [
                {
                    "id": str(SKETCH_ID),
                    "feature": {
                        "type": "sketch",
                        "version": 1,
                        "params": {
                            "plane": dict(XY_PLANE),
                            "entities": [
                                _line("e1", (2.0, 0.0), (5.0, 0.0)),
                                _line("e2", (5.0, 0.0), (2.0, 4.0)),
                                _line("e3", (2.0, 4.0), (2.0, 0.0)),
                            ],
                            "constraints": [],
                        },
                    },
                },
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # Reflection symmetry: centroid ON the mirror plane (a translation gives -0.5).
    assert result.properties.centroid.x == pytest.approx(0.0, abs=MIRROR_TOL)
    # The reflected lump occupies the REFLECTED coordinates x in [-5,-2]: the AABB
    # spans [-5,5] symmetric about x=0, and the source-only body was x in [2,5].
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-5.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(5.0, abs=MIRROR_TOL)
    assert result.properties.volume == pytest.approx(72.0, abs=MIRROR_TOL)


# --- Overlapping and symmetric (on-plane) cases handled sanely -----------------------


def test_overlapping_mirror_merges_to_one_solid() -> None:
    """A box straddling the mirror plane reflects into an OVERLAPPING copy that
    merges to ONE connected solid — the union volume is computed by hand.

    Box x in [-1,4], y in [0,4], z in [0,6] (V = 5*4*6 = 120). Mirror about YZ
    reflects it to x in [-4,1]; the two overlap in x in [-1,1] (width 2, volume
    2*4*6 = 48). Union = 120 + 120 - 48 = 192 mm^3 over x in [-4,4], and — the
    overlap merging the lumps — exactly ONE shell (not the disjoint 2)."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -1.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(192.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 1
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-4.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(4.0, abs=MIRROR_TOL)


def test_symmetric_body_mirror_is_a_no_op() -> None:
    """A body already SYMMETRIC about the mirror plane reflects onto itself — the
    union is the body itself, unchanged (the on-plane case handled sanely by
    clean() collapsing the coincident geometry). Box x in [-3,3] mirrored about
    YZ stays the same 6*4*6 = 144 mm^3 solid, 1 shell."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -3.0, 0.0, 3.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(144.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 1
    assert result.properties.topology.faces == 6


# --- The mirror plane resolves through a datum FEATURE ref ----------------------------


def test_mirror_about_an_offset_datum_feature_plane() -> None:
    """The plane FeatureRef path: a mirror about an earlier OFFSET datum feature
    reflects the body across that datum's plane. The XZ origin datum's normal is
    -Y, so an offset of +8 slides the plane to y=-8 (build123d Plane.XZ.z_dir =
    -Y). A box at y in [0,4] reflected across y=-8 lands at y in [-20,-16] —
    disjoint 2V (2*96 = 192), symmetric about y=-8 (centroid.y = -8). Proves the
    datum-feature plane resolves through the same funnel a sketch plane uses."""
    result = _post(
        _request(
            [
                # A datum plane parallel to XZ, slid +8 mm along its normal (-Y).
                datum_offset_input(DATUM_ID, "XZ", 8.0),
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID,
                    {"kind": "feature", "feature_id": str(DATUM_ID)},
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    # Box V = 4*4*6 = 96; disjoint mirror = 192; the two lumps at y in [0,4] and
    # y in [-20,-16] straddle y=-8 symmetrically → centroid.y = -8, 2 shells.
    assert result.properties.volume == pytest.approx(192.0, abs=MIRROR_TOL)
    assert result.properties.centroid.y == pytest.approx(-8.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 2


# --- Error paths are per-feature values, never transport failures ---------------------


def test_mirror_before_any_body_is_no_target_body() -> None:
    """A mirror with no prior body-affecting feature → no_target_body (the same
    posture as a pattern before any body)."""
    result = _post(
        _request([mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"})])
    )

    assert result.features[0].status == "error"
    error = result.features[0].error
    assert error is not None
    assert error.code == "no_target_body"
    assert result.mesh_glb_id is None


def test_mirror_plane_referencing_a_missing_feature_is_reference_unresolved() -> None:
    """A plane FeatureRef that resolves to no earlier datum of this prefix →
    reference_unresolved pinned to the referenced feature; the seed body stays
    last-good (strict-prefix rule)."""
    missing = uuid.UUID("00000000-0000-0000-0000-0000000000ee")
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(missing)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == missing
    # Strict-prefix: the last-good body (the extrude) is still tessellated.
    assert result.last_good_feature_id == BODY_ID
    assert result.mesh_glb_id is not None


def test_mirror_plane_referencing_a_non_datum_feature_is_reference_unresolved() -> None:
    """A plane FeatureRef pointing at a non-`datum` feature (the extrude body) is
    not a resolvable plane → reference_unresolved (geometry re-checks the slot's
    datum-only rule; it must not trust its callers)."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(BODY_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == BODY_ID
