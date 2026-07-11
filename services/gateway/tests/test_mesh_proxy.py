"""gateway ``GET /api/v1/geometry/meshes/{mesh_glb_id}`` — the mesh-fetch proxy.

Same harness as tests/test_evaluate_proxy.py (mock geometry transport, real
auth over SQLite): the route must be auth-gated, validate the content address
at the gateway (nothing malformed goes upstream), pass a hit through
byte-exact with the GLB media type, re-surface the upstream ``mesh_not_found``
404 envelope verbatim (the client's re-evaluate signal, feature-tree design
§7.8), and map transport failure to the 502 envelope.
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
from py_kit.schemas.geometry import GLB_MEDIA_TYPE
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

GLB = b"glTF\x02\x00\x00\x00fake-mesh-payload"

#: A well-formed content address (value is arbitrary; the store is mocked).
MESH_ID = "sha256:" + "ab12" * 16

#: Geometry's miss envelope, exactly as services/geometry serves it.
NOT_FOUND_BODY: dict[str, Any] = {
    "error": {
        "code": "mesh_not_found",
        "message": (
            "Mesh artifact unknown or evicted; re-evaluate the tree to regenerate it."
        ),
        "details": None,
        "request_id": "upstream-id",
    }
}


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


def make_client(db_url: str, geometry_handler: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, geometry_transport=httpx.MockTransport(geometry_handler))
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


def _geometry_glb(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=GLB, headers={"content-type": GLB_MEDIA_TYPE}
        )

    return handler


def test_mesh_hit_proxies_glb_bytes_and_media_type(db_url: str) -> None:
    seen: list[httpx.Request] = []
    with make_client(db_url, _geometry_glb(seen)) as client:
        bearer = _register(client)
        response = client.get(f"/api/v1/geometry/meshes/{MESH_ID}", headers=bearer)

    assert response.status_code == 200
    assert response.content == GLB  # byte-exact passthrough
    assert response.headers["content-type"] == GLB_MEDIA_TYPE

    [upstream] = seen
    assert upstream.method == "GET"
    assert upstream.url.path == f"/api/v1/meshes/{MESH_ID}"
    # Request id propagates so gateway/geometry logs correlate; the
    # principal never does — geometry is identity-free (RESEARCH §3).
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_mesh_miss_resurfaces_mesh_not_found_verbatim(db_url: str) -> None:
    """Upstream 404 = the client's re-evaluate signal (§7.8): code and
    message pass through unchanged under the gateway's own request id."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=NOT_FOUND_BODY)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.get(f"/api/v1/geometry/meshes/{MESH_ID}", headers=bearer)

    assert response.status_code == 404
    error = _envelope(response.json())
    assert error["code"] == NOT_FOUND_BODY["error"]["code"]
    assert error["message"] == NOT_FOUND_BODY["error"]["message"]
    # The gateway stamps its own request id, not the upstream one.
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []
    with make_client(db_url, _geometry_glb(seen)) as client:
        response = client.get(f"/api/v1/geometry/meshes/{MESH_ID}")

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


@pytest.mark.parametrize(
    "bad_id",
    [
        "md5:" + "ab12" * 16,  # wrong scheme
        "sha256:" + "ab12" * 15,  # too short
        "sha256:" + "AB12" * 16,  # uppercase hex is not a canonical address
        "sha256:" + "zz12" * 16,  # non-hex
        "not-a-content-address",
    ],
)
def test_malformed_id_rejected_at_the_gateway(db_url: str, bad_id: str) -> None:
    """Non-`sha256:` ids fail path validation — never go upstream."""
    seen: list[httpx.Request] = []
    with make_client(db_url, _geometry_glb(seen)) as client:
        bearer = _register(client)
        response = client.get(f"/api/v1/geometry/meshes/{bad_id}", headers=bearer)

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_geometry_unreachable_is_502(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.get(f"/api/v1/geometry/meshes/{MESH_ID}", headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
