"""Geometry REST API — GLB response, metadata header/twin, validation envelope.

The export endpoint has its own gate module (``test_export.py``); the
validation-envelope assertion is the shared conftest fixture.
"""

import math
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from geometry.schemas import TessellationMetadata
from py_kit.schemas.geometry import GLB_MEDIA_TYPE, PROPERTIES_HEADER

client = TestClient(app)

BOX_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}

#: Documented golden tolerance — see tests/test_kernel.py.
GOLDEN_TOL = 1e-7

#: Documented curved-geometry tolerance — see
#: goldens/cylinder-r10-h25/expected.json tolerance_rationale.
CURVED_TOL = 1e-9


def test_tessellate_returns_glb_with_properties_header() -> None:
    response = client.post("/api/v1/tessellate", json=BOX_REQUEST)

    assert response.status_code == 200
    assert response.headers["content-type"] == GLB_MEDIA_TYPE
    assert response.content[:4] == b"glTF"

    metadata = TessellationMetadata.model_validate_json(
        response.headers[PROPERTIES_HEADER]
    )
    assert metadata.properties.volume == pytest.approx(6000.0, abs=GOLDEN_TOL)
    assert metadata.properties.topology.faces == 6
    assert metadata.mesh.glb_bytes == len(response.content)


def test_tessellate_meta_twin_matches_header() -> None:
    binary = client.post("/api/v1/tessellate", json=BOX_REQUEST)
    meta = client.post("/api/v1/tessellate/meta", json=BOX_REQUEST)

    assert meta.status_code == 200
    from_header = TessellationMetadata.model_validate_json(
        binary.headers[PROPERTIES_HEADER]
    )
    from_body = TessellationMetadata.model_validate(meta.json())
    assert from_body == from_header


def test_tessellate_default_deflection() -> None:
    """linear_deflection is optional; the default produces a valid mesh."""
    request = {"shape": "box", "params": {"x": 1.0, "y": 1.0, "z": 1.0}}
    response = client.post("/api/v1/tessellate", json=request)

    assert response.status_code == 200
    assert response.content[:4] == b"glTF"


@pytest.mark.parametrize(
    "params",
    [
        {"x": 0.0, "y": 20.0, "z": 30.0},
        {"x": 10.0, "y": -5.0, "z": 30.0},
        {"x": 10.0, "y": 20.0},  # missing dimension
    ],
)
def test_tessellate_rejects_bad_params_with_envelope(
    params: dict[str, float],
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post(
        "/api/v1/tessellate", json={"shape": "box", "params": params}
    )

    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_tessellate_cylinder_returns_curved_mesh() -> None:
    """The cylinder kind works through the full HTTP path (golden numbers:
    goldens/cylinder-r10-h25 — the harness owns the tight assertions)."""
    response = client.post(
        "/api/v1/tessellate",
        json={"shape": "cylinder", "params": {"radius": 10.0, "height": 25.0}},
    )

    assert response.status_code == 200
    assert response.content[:4] == b"glTF"
    metadata = TessellationMetadata.model_validate_json(
        response.headers[PROPERTIES_HEADER]
    )
    assert metadata.properties.topology.faces == 3
    assert metadata.properties.volume == pytest.approx(2500 * math.pi, abs=CURVED_TOL)


@pytest.mark.parametrize(
    "payload",
    [
        # box kind with cylinder params
        {"shape": "box", "params": {"radius": 10.0, "height": 25.0}},
        # cylinder kind with box params
        {"shape": "cylinder", "params": {"x": 10.0, "y": 20.0, "z": 30.0}},
        # cylinder with non-positive params (Field(gt=0) validators)
        {"shape": "cylinder", "params": {"radius": 0.0, "height": 25.0}},
        {"shape": "cylinder", "params": {"radius": 10.0, "height": -1.0}},
    ],
)
def test_tessellate_rejects_mismatched_or_bad_shape_params(
    payload: dict[str, Any],
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    """The shape/params pairing is enforced at validation time (422 envelope),
    so mismatches never reach the kernel dispatch."""
    response = client.post("/api/v1/tessellate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_tessellate_rejects_unknown_shape(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post(
        "/api/v1/tessellate",
        json={"shape": "teapot", "params": {"x": 1.0, "y": 1.0, "z": 1.0}},
    )

    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_tessellate_rejects_non_positive_deflection(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post(
        "/api/v1/tessellate", json={**BOX_REQUEST, "linear_deflection": 0.0}
    )

    assert response.status_code == 422
    assert_validation_envelope(response.json())
