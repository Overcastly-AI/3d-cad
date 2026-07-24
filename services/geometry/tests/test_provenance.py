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
import struct
import uuid
from typing import Any

from build123d import CenterOf, GeomType
from fastapi.testclient import TestClient
from geometry.features import evaluate_tree
from geometry.kernel import attribute_faces
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
        EvaluateTreeRequest.model_validate(_block_and_hole_tree())
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
    first = evaluate_tree(tree)
    second = evaluate_tree(tree)
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
