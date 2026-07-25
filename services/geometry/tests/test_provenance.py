"""Per-face feature provenance — face→feature attribution (FINDINGS #9).

The enabler for feature-localized selection: the geometry result must expose
which feature owns each face so the frontend highlights ONLY a selected feature's
faces (keeping the studio matcap) instead of clay-swapping the whole body. The
headline gate is the composed body of the acceptance criterion — a base extrude
plus a hole cut — where the hole's cylindrical wall must attribute to the HOLE and
the untouched base side faces to the EXTRUDE.

Determinism (RESEARCH §9): same tree → identical attribution. Tolerances are the
documented stage-1 face tolerances reused by :mod:`geometry.kernel.provenance`
(no ad-hoc epsilon): an authored part's faces differ by whole mm^2 / whole mm, far
beyond kernel jitter, so a match is unambiguous.
"""

import json
import math
import struct
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from build123d import CenterOf, Compound, GeomType, Solid
from fastapi.testclient import TestClient
from geometry.features import evaluate_tree
from geometry.kernel import attribute_faces, provenance
from geometry.kernel.types import BodyShape
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.overlay import OverlayRequest, OverlayResult

client = TestClient(app)

SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0001")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0002")
HOLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f0003")

#: The 40x25x10 block's top (+Z) planar-face signature — the drilled face.
TOP_FACE = ((0.0, 0.0, 1.0), (20.0, 12.5, 10.0), 1000.0)


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _block_and_hole_tree() -> dict[str, Any]:
    """A 40x25x10 block (sketch+extrude-add) with a through-hole cut in the top."""
    normal, centroid, area = TOP_FACE
    return {
        "part_id": "00000000-0000-0000-0000-0000000000f0",
        "tree_version": 1,
        "linear_deflection": 0.1,
        "features": [
            {
                "id": str(SKETCH_ID),
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": "XY"},
                        "entities": [
                            _line("e1", (0.0, 0.0), (40.0, 0.0)),
                            _line("e2", (40.0, 0.0), (40.0, 25.0)),
                            _line("e3", (40.0, 25.0), (0.0, 25.0)),
                            _line("e4", (0.0, 25.0), (0.0, 0.0)),
                        ],
                        "constraints": [],
                    },
                },
            },
            {
                "id": str(EXTRUDE_ID),
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                        "distance_mm": 10.0,
                        "operation": "add",
                        "direction": "normal",
                    },
                },
            },
            {
                "id": str(HOLE_ID),
                "feature": {
                    "type": "hole",
                    "version": 1,
                    "params": {
                        "face": {
                            "kind": "subshape",
                            "feature_id": str(EXTRUDE_ID),
                            "subshape_type": "face",
                            "selector": {
                                "selector_version": 1,
                                "signature": {
                                    "subshape_type": "face",
                                    "surface": "plane",
                                    "normal": {
                                        "x": normal[0],
                                        "y": normal[1],
                                        "z": normal[2],
                                    },
                                    "centroid": {
                                        "x": centroid[0],
                                        "y": centroid[1],
                                        "z": centroid[2],
                                    },
                                    "area_mm2": area,
                                },
                            },
                        },
                        "position": {"x": 20.0, "y": 12.5, "z": 10.0},
                        "diameter_mm": 10.0,
                        "depth": {"kind": "through_all"},
                    },
                },
            },
        ],
    }


def _glb_primitive_count(glb: bytes) -> int:
    """Number of glTF primitives in a binary GLB (one per B-rep face, OCCT)."""
    header = struct.Struct("<4sII")
    chunk = struct.Struct("<I4s")
    chunk_length, _chunk_type = chunk.unpack_from(glb, header.size)
    json_start = header.size + chunk.size
    document: dict[str, Any] = json.loads(
        glb[json_start : json_start + chunk_length].decode("utf-8")
    )
    return sum(len(mesh.get("primitives", [])) for mesh in document.get("meshes", []))


# --- kernel-level attribution ----------------------------------------------------


def test_hole_wall_attributes_to_hole_base_faces_to_extrude() -> None:
    """HEADLINE GATE (acceptance): on a base-extrude + hole-cut body, the hole's
    cylindrical wall attributes to the HOLE feature and the untouched base side
    faces to the EXTRUDE feature; the drilled top/bottom faces (re-cut by the
    bore) attribute to the HOLE."""
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(_block_and_hole_tree()),
        record_history=True,
    )
    assert evaluation.body is not None
    # Two body-affecting features → two snapshots, earliest first.
    assert [fid for fid, _shape in evaluation.body_history] == [EXTRUDE_ID, HOLE_ID]

    faces = evaluation.body.faces()
    owners = attribute_faces(evaluation.body, evaluation.body_history)
    assert len(owners) == len(faces)  # one owner per body.faces() entry
    # Every face is owned (no None) once a body-affecting feature has run.
    assert all(owner is not None for owner in owners)

    cylinder_owners: list[uuid.UUID | None] = []
    for face, owner in zip(faces, owners, strict=True):
        if face.geom_type != GeomType.PLANE:
            cylinder_owners.append(owner)
            continue
        normal = face.normal_at(face.center(CenterOf.MASS))
        if abs(normal.Z) < 0.5:
            # A side face (normal ⟂ Z) is untouched by the bore → the extrude.
            assert owner == EXTRUDE_ID
        else:
            # The drilled top/bottom (normal ‖ Z) were re-cut → the hole.
            assert owner == HOLE_ID

    # Exactly one cylindrical wall, owned by the hole that produced it.
    assert cylinder_owners == [HOLE_ID]


def test_attribution_is_deterministic() -> None:
    """Same tree → identical attribution (RESEARCH §9)."""
    tree = EvaluateTreeRequest.model_validate(_block_and_hole_tree())
    first = evaluate_tree(tree, record_history=True)
    second = evaluate_tree(tree, record_history=True)
    assert first.body is not None and second.body is not None
    assert attribute_faces(first.body, first.body_history) == attribute_faces(
        second.body, second.body_history
    )


def test_glb_has_one_primitive_per_brep_face() -> None:
    """The frontend maps a body.faces() index to a GLB primitive (one glTF
    primitive per B-rep face). Lock that count parity so the attribution index —
    body.faces() order == OverlayFace.index — aligns with the mesh face set."""
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(_block_and_hole_tree())
    )
    assert evaluation.glb is not None and evaluation.body is not None
    assert evaluation.result.properties is not None
    face_count = len(evaluation.body.faces())
    assert _glb_primitive_count(evaluation.glb) == face_count
    assert face_count == evaluation.result.properties.topology.faces


# --- Cost: opt-in history, indexed matching, bounded work (audit H4) -------------


def test_only_an_opted_in_caller_records_body_history() -> None:
    """AUDIT H4(a): recording body history is OPT-IN, so the eight non-overlay
    `evaluate_tree` call sites (tessellate, export, measure, drawing compose,
    per-instance assembly evaluation, the golden harness) stop retaining an
    intermediate B-rep per body-affecting feature they never read.

    The evaluated GEOMETRY must be identical either way — the flag governs what is
    KEPT, never what is built — so this asserts the default keeps nothing while the
    mesh id (a content hash of the deterministic GLB) and mass properties match the
    recording run byte for byte."""
    tree = EvaluateTreeRequest.model_validate(_block_and_hole_tree())
    plain = evaluate_tree(tree)
    recording = evaluate_tree(tree, record_history=True)

    assert plain.body_history == []  # nothing retained on the hot path
    assert [fid for fid, _shape in recording.body_history] == [EXTRUDE_ID, HOLE_ID]
    # Same geometry: same content-addressed mesh, same mass properties.
    assert plain.result.mesh_glb_id == recording.result.mesh_glb_id
    assert plain.result.properties == recording.result.properties
    assert plain.glb == recording.glb


def test_the_overlay_endpoint_is_the_only_route_that_pays_for_history() -> None:
    """The flag's wiring: `/api/v1/overlay` still returns full attribution (so the
    opt-in did not silently disable the feature), while `/api/v1/evaluate` — the
    tessellate hot path — is unaffected."""
    tree = _block_and_hole_tree()
    payload = OverlayRequest.model_validate({"tree": tree}).model_dump(mode="json")
    overlay = OverlayResult.model_validate(
        client.post("/api/v1/overlay", json=payload).json()
    )
    assert all(face.feature_id is not None for face in overlay.faces)

    evaluate = client.post("/api/v1/evaluate", json=tree)
    assert evaluate.status_code == 200
    # The evaluate response never carried provenance and still does not.
    assert "feature_id" not in evaluate.json().get("bodies", [{}])[0]


def _many_face_body(boxes: int) -> Compound:
    """A compound of *boxes* unit cubes on a 2 mm lattice — ``6 * boxes`` planar
    faces, all distinct, built without any boolean (cheap, deterministic)."""
    side = math.ceil(boxes ** (1 / 2))
    solids = [
        Solid.make_box(1.0, 1.0, 1.0).translate((i % side * 2.0, i // side * 2.0, 0.0))
        for i in range(boxes)
    ]
    return Compound(solids)


def test_attribution_work_is_linear_in_face_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUDIT H4(b) SIZE GATE: the matcher is INDEXED, not scanned.

    The shipped implementation compared each final face against every fingerprint
    of every snapshot until one matched — ``O(F x S x F_snapshot)``. A single
    20k-face STEP import (one snapshot) therefore cost ~2e8 pure-Python
    `fingerprints_match` calls inside one authenticated request.

    Asserted as an OPERATION COUNT, not wall-clock: a timing bound flakes under CI
    contention (see the benchmark suite's ceiling policy), while the call count is
    contention-invariant and fails LOUDLY on the quadratic path. With 600 faces the
    old matcher averages ~F/2 comparisons per face (~180000 total); the indexed one
    probes 27 cells holding at most a handful of candidates each, so 4 calls per
    face is generous headroom and still ~75x below the old cost."""
    body = _many_face_body(100)
    faces = len(body.faces())
    assert faces == 600

    calls = 0
    # The fingerprint type is module-private (it never crosses a boundary), so the
    # counting wrapper is typed structurally and delegates to the real matcher.
    real_matches: Callable[..., bool] = provenance.fingerprints_match

    def counting_matches(candidate: object, target: object) -> bool:
        nonlocal calls
        calls += 1
        return real_matches(candidate, target)

    monkeypatch.setattr(provenance, "fingerprints_match", counting_matches)
    history: list[tuple[uuid.UUID, BodyShape]] = [(EXTRUDE_ID, body)]
    owners = attribute_faces(body, history)

    assert owners == [EXTRUDE_ID] * faces  # every face resolves, same as before
    assert calls <= 4 * faces, f"{calls} match calls for {faces} faces is not linear"


def test_attribution_degrades_past_the_documented_face_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUDIT H4: past MAX_PROVENANCE_FACES the pass is SKIPPED, not run and not
    refused. Attribution is a rendering nicety, so it degrades to all-null —
    exactly the pre-provenance behaviour, which the frontend already handles by
    falling back to whole-body selection — instead of pinning a worker (or taking
    the whole picking overlay away from a large imported body with a 422).

    The bound counts the TOTAL fingerprint budget (final faces + every snapshot's
    faces), which is what the GProp cost actually scales with."""
    body = _many_face_body(4)
    faces = len(body.faces())
    history: list[tuple[uuid.UUID, BodyShape]] = [(EXTRUDE_ID, body)]

    # Budget = 24 final + 24 snapshot = 48; a bound just under it must degrade.
    monkeypatch.setattr(provenance, "MAX_PROVENANCE_FACES", 2 * faces - 1)
    assert attribute_faces(body, history) == [None] * faces
    # ... and exactly at the budget it still attributes (the bound is inclusive).
    monkeypatch.setattr(provenance, "MAX_PROVENANCE_FACES", 2 * faces)
    assert attribute_faces(body, history) == [EXTRUDE_ID] * faces


def test_overlay_still_picks_when_attribution_is_bounded_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degradation is PARTIAL: a body past the bound loses `feature_id` only. The
    vertices / edges / face signatures the measure, sketch-on-face and edge-pick
    flows depend on are still returned in full, and the request is a 200."""
    monkeypatch.setattr(provenance, "MAX_PROVENANCE_FACES", 1)
    payload = OverlayRequest.model_validate(
        {"tree": _block_and_hole_tree()}
    ).model_dump(mode="json")
    response = client.post("/api/v1/overlay", json=payload)

    assert response.status_code == 200, response.text
    overlay = OverlayResult.model_validate(response.json())
    assert all(face.feature_id is None for face in overlay.faces)
    # The drilled block's faces are all still there (6 box faces + the hole wall).
    assert len(overlay.faces) == 7
    assert overlay.vertices and overlay.edges
    assert any(face.signature is not None for face in overlay.faces)


# --- HTTP overlay carries the attribution ---------------------------------------


def test_overlay_endpoint_populates_feature_id() -> None:
    """The overlay endpoint threads attribution onto OverlayFace.feature_id: the
    non-planar (cylindrical) face resolves to the hole, and at least one planar
    side face to the extrude — the map the frontend consumes."""
    payload = OverlayRequest.model_validate(
        {"tree": _block_and_hole_tree()}
    ).model_dump(mode="json")
    response = client.post("/api/v1/overlay", json=payload)
    assert response.status_code == 200, response.text
    overlay = OverlayResult.model_validate(response.json())

    # Every face carries an owner; indices are body.faces() ordinals.
    assert all(face.feature_id is not None for face in overlay.faces)
    assert [face.index for face in overlay.faces] == list(range(len(overlay.faces)))

    non_planar = [face for face in overlay.faces if face.signature is None]
    assert len(non_planar) == 1  # the hole wall
    assert non_planar[0].feature_id == HOLE_ID

    # The base owns at least the four side faces.
    extrude_faces = [f for f in overlay.faces if f.feature_id == EXTRUDE_ID]
    assert len(extrude_faces) >= 4


def test_overlay_feature_id_is_deterministic_over_http() -> None:
    payload = OverlayRequest.model_validate(
        {"tree": _block_and_hole_tree()}
    ).model_dump(mode="json")
    first = client.post("/api/v1/overlay", json=payload)
    second = client.post("/api/v1/overlay", json=payload)
    assert first.status_code == 200
    assert first.content == second.content
