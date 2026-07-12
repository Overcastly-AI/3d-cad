"""gateway ``POST /api/v1/geometry/sketch/{trim,extend}`` — the edit proxies.

Same harness as tests/test_measure_proxy.py (mock geometry transport, real auth
over SQLite): the routes must be auth-gated, validate the shared
SketchEditRequest DTO at the gateway (a duplicate entity id never goes
upstream), pass the typed result through, re-surface upstream envelopes, and
map transport failure to the 502 envelope. The principal never travels upstream
(geometry is identity-free, RESEARCH §3).
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
from py_kit.schemas.parts import PRINCIPAL_HEADER
from py_kit.schemas.sketch import (
    Point2D,
    SketchEditRequest,
    SketchEditResult,
    SketchLine,
    SketchOffsetRequest,
    SketchOffsetResult,
)
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

TRIM_BODY: dict[str, Any] = {
    "entities": [
        {
            "id": "L",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 10.0, "y": 0.0},
        },
        {
            "id": "C",
            "kind": "line",
            "start": {"x": 5.0, "y": -5.0},
            "end": {"x": 5.0, "y": 5.0},
        },
    ],
    "target": "L",
    "pick": {"x": 2.0, "y": 0.0},
}

RESULT = SketchEditResult(
    entities=[
        SketchLine(
            id="L",
            kind="line",
            start=Point2D(x=5.0, y=0.0),
            end=Point2D(x=10.0, y=0.0),
        ),
    ]
)


OFFSET_BODY: dict[str, Any] = {
    "entities": [
        {
            "id": "L",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 10.0, "y": 0.0},
        },
    ],
    "target": "L",
    "distance": 2.0,
}

OFFSET_RESULT = SketchOffsetResult(
    entities=[
        SketchLine(
            id="L.2",
            kind="line",
            start=Point2D(x=0.0, y=2.0),
            end=Point2D(x=10.0, y=2.0),
        ),
    ]
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


def test_trim_proxies_typed_result(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/sketch/trim", json=TRIM_BODY, headers=bearer
        )

    assert response.status_code == 200
    assert SketchEditResult.model_validate(response.json()) == RESULT

    [upstream] = seen
    assert upstream.url.path == "/api/v1/sketch/trim"
    assert SketchEditRequest.model_validate_json(
        upstream.content
    ) == SketchEditRequest.model_validate(TRIM_BODY)
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_extend_proxies_to_correct_upstream_path(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/sketch/extend", json=TRIM_BODY, headers=bearer
        )

    assert response.status_code == 200
    [upstream] = seen
    assert upstream.url.path == "/api/v1/sketch/extend"


def test_offset_proxies_typed_result(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=OFFSET_RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/sketch/offset", json=OFFSET_BODY, headers=bearer
        )

    assert response.status_code == 200
    assert SketchOffsetResult.model_validate(response.json()) == OFFSET_RESULT

    [upstream] = seen
    assert upstream.url.path == "/api/v1/sketch/offset"
    assert SketchOffsetRequest.model_validate_json(
        upstream.content
    ) == SketchOffsetRequest.model_validate(OFFSET_BODY)
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_offset_requires_auth(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=OFFSET_RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        response = client.post("/api/v1/geometry/sketch/offset", json=OFFSET_BODY)

    assert response.status_code == 401
    assert seen == []


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    with make_client(db_url, handler) as client:
        response = client.post("/api/v1/geometry/sketch/trim", json=TRIM_BODY)

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


def test_duplicate_entity_id_rejected_at_gateway(db_url: str) -> None:
    """The shared DTO validates at the gateway — bad input never goes upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=RESULT.model_dump_json())

    dup = {
        "entities": [
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 1.0, "y": 0.0},
            },
            {
                "id": "L",
                "kind": "line",
                "start": {"x": 0.0, "y": 1.0},
                "end": {"x": 1.0, "y": 1.0},
            },
        ],
        "target": "L",
        "pick": {"x": 0.5, "y": 0.0},
    }
    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post("/api/v1/geometry/sketch/trim", headers=bearer, json=dup)

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "sketch_pick_not_on_target",
                    "message": "pick off curve",
                    "details": {},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/sketch/trim", json=TRIM_BODY, headers=bearer
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "sketch_pick_not_on_target"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_geometry_unreachable_is_502(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/sketch/trim", json=TRIM_BODY, headers=bearer
        )

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
