"""gateway.geometry — proxy passthrough, error mapping, settings override.

The tessellate/tessellate-meta/export routes are auth-gated (CPU-bound OCCT
work on a signed-in user's geometry — anonymous access is a DoS vector,
engineering audit F7), so this suite runs over real auth on SQLite (same
harness as tests/test_measure_proxy.py): register a user, pass the bearer on
the authenticated calls, and assert a bare call is a 401 with nothing
forwarded upstream. The principal never travels upstream (geometry is
identity-free, RESEARCH §3).
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit import REQUEST_ID_HEADER
from py_kit.db import async_dsn
from py_kit.schemas.geometry import (
    EXPORT_MEDIA_TYPES,
    GLB_MEDIA_TYPE,
    PROPERTIES_HEADER,
    BoundingBox,
    ExportRequest,
    MeshStats,
    ShapeProperties,
    TessellateRequest,
    TessellationMetadata,
    TopologyCounts,
    Vec3,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

BOX_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}

GLB = b"glTF\x02\x00\x00\x00fake-payload"

#: Fake export payloads per format — passthrough is asserted byte-exact.
EXPORT_BYTES: dict[str, bytes] = {
    "step": b"ISO-10303-21;\nfake step file\nEND-ISO-10303-21;\n",
    "stl": b"\x00" * 80 + b"\x0c\x00\x00\x00fake-binary-stl",
}


def export_request(fmt: str) -> dict[str, Any]:
    return {**BOX_REQUEST, "format": fmt, "angular_deflection": 0.1}


METADATA = TessellationMetadata(
    properties=ShapeProperties(
        volume=6000.0,
        surface_area=2200.0,
        centroid=Vec3(x=5.0, y=10.0, z=15.0),
        bounding_box=BoundingBox(
            min=Vec3(x=0.0, y=0.0, z=0.0), max=Vec3(x=10.0, y=20.0, z=30.0)
        ),
        topology=TopologyCounts(faces=6, edges=12, shells=1),
    ),
    mesh=MeshStats(vertices=24, triangles=12, glb_bytes=len(GLB)),
)

Handler = Callable[[httpx.Request], httpx.Response]


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def make_client(db_url: str, handler: Handler) -> TestClient:
    """Gateway TestClient over real auth whose upstream geometry client hits
    *handler*."""
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, geometry_transport=httpx.MockTransport(handler))
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def test_tessellate_proxies_glb_and_properties_header(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=GLB,
            headers={
                "content-type": GLB_MEDIA_TYPE,
                PROPERTIES_HEADER: METADATA.model_dump_json(),
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate", json=BOX_REQUEST, headers=bearer
        )

    assert response.status_code == 200
    assert response.content == GLB  # byte-exact passthrough
    assert response.headers["content-type"] == GLB_MEDIA_TYPE
    metadata = TessellationMetadata.model_validate_json(
        response.headers[PROPERTIES_HEADER]
    )
    assert metadata == METADATA

    [upstream] = seen
    assert upstream.url.path == "/api/v1/tessellate"
    assert TessellateRequest.model_validate_json(
        upstream.content
    ) == TessellateRequest.model_validate(BOX_REQUEST)
    # Request id propagates upstream so gateway/geometry logs correlate; the
    # principal never travels upstream (geometry is identity-free).
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_tessellate_meta_proxies_typed_json(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=METADATA.model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta", json=BOX_REQUEST, headers=bearer
        )

    assert response.status_code == 200
    assert TessellationMetadata.model_validate(response.json()) == METADATA
    [upstream] = seen
    assert upstream.url.path == "/api/v1/tessellate/meta"


@pytest.mark.parametrize("fmt", ["step", "stl"])
def test_export_proxies_file_and_content_disposition(db_url: str, fmt: str) -> None:
    seen: list[httpx.Request] = []
    payload = EXPORT_BYTES[fmt]
    disposition = f'attachment; filename="box.{fmt}"'

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": EXPORT_MEDIA_TYPES[fmt],
                "content-disposition": disposition,
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/export", json=export_request(fmt), headers=bearer
        )

    assert response.status_code == 200
    assert response.content == payload  # byte-exact passthrough
    assert response.headers["content-type"] == EXPORT_MEDIA_TYPES[fmt]
    assert response.headers["content-disposition"] == disposition

    [upstream] = seen
    assert upstream.url.path == "/api/v1/export"
    assert ExportRequest.model_validate_json(
        upstream.content
    ) == ExportRequest.model_validate(export_request(fmt))
    # Request id propagates upstream so gateway/geometry logs correlate.
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/geometry/tessellate", BOX_REQUEST),
        ("/api/v1/geometry/tessellate/meta", BOX_REQUEST),
        ("/api/v1/geometry/export", export_request("step")),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, path: str, payload: dict[str, Any]
) -> None:
    """Each CPU-bound geometry route is auth-gated (audit F7): a bare call is a
    401 and nothing reaches the geometry service."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=GLB)

    with make_client(db_url, handler) as client:
        response = client.post(path, json=payload)

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/geometry/tessellate", BOX_REQUEST),
        ("/api/v1/geometry/tessellate/meta", BOX_REQUEST),
        ("/api/v1/geometry/export", export_request("step")),
    ],
)
def test_upstream_down_maps_to_502_envelope(
    db_url: str, path: str, payload: dict[str, Any]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(path, json=payload, headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
    # Never a raw stack / internal URL.
    assert "Traceback" not in response.text
    assert "8002" not in response.text


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "code": "internal_error",
                    "message": "Kernel evaluation failed.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate", json=BOX_REQUEST, headers=bearer
        )

    assert response.status_code == 500
    error = _envelope(response.json())
    assert error["code"] == "internal_error"
    assert error["message"] == "Kernel evaluation failed."
    # The gateway stamps its own request id, not the upstream one.
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_upstream_non_envelope_error_is_opaque(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="<html>bad gateway</html>")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta", json=BOX_REQUEST, headers=bearer
        )

    assert response.status_code == 503
    error = _envelope(response.json())
    assert error["code"] == "upstream_error"
    assert "<html>" not in response.text


def test_invalid_request_rejected_at_the_gateway(db_url: str) -> None:
    """Shared DTOs validate at the gateway — bad input never goes upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate",
            headers=bearer,
            json={"shape": "box", "params": {"x": 0.0, "y": 1.0, "z": 1.0}},
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_invalid_export_format_rejected_at_the_gateway(db_url: str) -> None:
    """Unknown export format fails DTO validation — never goes upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/export",
            headers=bearer,
            json={**BOX_REQUEST, "format": "obj"},
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_geometry_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOMETRY_URL", "http://geometry.internal:9002")
    assert GatewaySettings().geometry_url == "http://geometry.internal:9002"
