"""gateway ``POST /api/v1/geometry/drawing/evaluate`` — the drawing-view-evaluate
proxy (drawings §1.2/§4).

Same harness as tests/test_assembly_evaluate_proxy.py (mock geometry transport,
real auth over SQLite): the route is auth-gated (F7), validates the shared
``EvaluateDrawingViewsRequest`` at the gateway, passes the typed
``EvaluateDrawingViewsResult`` through, re-surfaces upstream envelopes, and maps
a transport failure to the 502 envelope. The principal never travels upstream
(geometry is identity-free, RESEARCH §3).
"""

import asyncio
import uuid
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
from py_kit.schemas.drawings import (
    DrawingViewResult,
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    ProjectedPoint,
    ProjectedViewEdge,
    ViewScale,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

PART = uuid.UUID("00000000-0000-0000-0000-0000000000d7")


def _request() -> EvaluateDrawingViewsRequest:
    """A minimal front+top request (an empty feature prefix suffices for a proxy
    test — the gateway only validates + relays, geometry evaluates)."""
    return EvaluateDrawingViewsRequest(
        part_id=PART,
        tree_version=1,
        features=[],
        views=["front", "top"],
        scale=ViewScale(numerator=1, denominator=1),
    )


def _result() -> EvaluateDrawingViewsResult:
    edge = ProjectedViewEdge(
        primitive="line",
        visible=True,
        start=ProjectedPoint(x_mm=0.0, y_mm=0.0),
        end=ProjectedPoint(x_mm=10.0, y_mm=0.0),
        midpoint=ProjectedPoint(x_mm=5.0, y_mm=0.0),
    )
    return EvaluateDrawingViewsResult(
        part_id=PART,
        tree_version=1,
        views=[
            DrawingViewResult(
                view="front", scale=ViewScale(numerator=1, denominator=1), edges=[edge]
            ),
            DrawingViewResult(
                view="top", scale=ViewScale(numerator=1, denominator=1), edges=[edge]
            ),
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


def test_drawing_evaluate_proxies_typed_result(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_result().model_dump_json())

    request = _request()
    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/drawing/evaluate",
            json=request.model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    result = EvaluateDrawingViewsResult.model_validate(response.json())
    assert result.part_error is None
    assert [v.view for v in result.views] == ["front", "top"]

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/drawing/evaluate"
    relayed = EvaluateDrawingViewsRequest.model_validate_json(upstream.content)
    assert relayed == request
    # Request id correlates logs; geometry is identity-free (RESEARCH §3).
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_result().model_dump_json())

    with make_client(db_url, handler) as client:
        response = client.post(
            "/api/v1/geometry/drawing/evaluate",
            json=_request().model_dump(mode="json"),
        )

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


def test_invalid_request_rejected_at_gateway(db_url: str) -> None:
    """The shared DTO validates at the gateway — bad input never goes upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_result().model_dump_json())

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/drawing/evaluate",
            headers=bearer,
            json={
                "part_id": "not-a-uuid",
                "tree_version": 1,
                "features": [],
                "views": ["front"],
            },
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/drawing/evaluate",
            json=_request().model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "validation_error"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_geometry_unreachable_is_502(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/drawing/evaluate",
            json=_request().model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
