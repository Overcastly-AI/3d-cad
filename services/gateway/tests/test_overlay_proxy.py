"""gateway ``POST /api/v1/geometry/overlay`` — the stateless overlay proxy.

Same harness as tests/test_measure_proxy.py (mock geometry transport, real auth
over SQLite): the route must be auth-gated, validate the shared OverlayRequest
DTO at the gateway, pass a typed result through, re-surface upstream envelopes,
and map transport failure to the 502 envelope. The principal never travels
upstream (geometry is identity-free, RESEARCH §3).
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
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.overlay import OverlayEdge, OverlayRequest, OverlayResult
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

TREE: dict[str, Any] = {
    "part_id": "00000000-0000-0000-0000-0000000000fb",
    "tree_version": 4,
    "features": [
        {
            "id": "00000000-0000-0000-0000-00000000aaaa",
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        {
                            "id": "e1",
                            "kind": "line",
                            "start": {"x": 0.0, "y": 0.0},
                            "end": {"x": 10.0, "y": 0.0},
                        },
                        {
                            "id": "e2",
                            "kind": "line",
                            "start": {"x": 10.0, "y": 0.0},
                            "end": {"x": 10.0, "y": 10.0},
                        },
                        {
                            "id": "e3",
                            "kind": "line",
                            "start": {"x": 10.0, "y": 10.0},
                            "end": {"x": 0.0, "y": 10.0},
                        },
                        {
                            "id": "e4",
                            "kind": "line",
                            "start": {"x": 0.0, "y": 10.0},
                            "end": {"x": 0.0, "y": 0.0},
                        },
                    ],
                    "constraints": [],
                },
            },
        },
        {
            "id": "00000000-0000-0000-0000-00000000bbbb",
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {
                        "kind": "feature",
                        "feature_id": "00000000-0000-0000-0000-00000000aaaa",
                    },
                    "distance_mm": 5.0,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ],
    "linear_deflection": 0.1,
}

OVERLAY_REQUEST: dict[str, Any] = {"tree": TREE}

RESULT = OverlayResult(
    vertices=[Vec3(x=0.0, y=0.0, z=0.0), Vec3(x=10.0, y=0.0, z=0.0)],
    edges=[
        OverlayEdge(
            kind="line",
            start=Vec3(x=0.0, y=0.0, z=0.0),
            end=Vec3(x=10.0, y=0.0, z=0.0),
            polyline=[Vec3(x=0.0, y=0.0, z=0.0), Vec3(x=10.0, y=0.0, z=0.0)],
        )
    ],
)


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


def test_overlay_proxies_typed_result(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )

    assert response.status_code == 200
    assert OverlayResult.model_validate(response.json()) == RESULT

    [upstream] = seen
    assert upstream.url.path == "/api/v1/overlay"
    assert OverlayRequest.model_validate_json(
        upstream.content
    ) == OverlayRequest.model_validate(OVERLAY_REQUEST)
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        response = client.post("/api/v1/geometry/overlay", json=OVERLAY_REQUEST)

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    """An upstream tree_overlay_failed 422 passes through under our request id."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "tree_overlay_failed",
                    "message": "nothing to overlay",
                    "details": {"reason": "no_body"},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "tree_overlay_failed"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_geometry_unreachable_is_502(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
