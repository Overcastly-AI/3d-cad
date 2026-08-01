"""The gateway stops calling a slow geometry service "unreachable" (CONC-3).

The defect this file pins was a *message*, and messages are where this stack
wastes a user's afternoon. Measured 2026-08-01, one user, idle machine: a
200-feature ``/overlay`` costs 40.3 s; the gateway gave up at 30 s and answered
**502 ``upstream_unavailable`` — "Geometry service is unreachable."** The
service was fine, the answer was computed, and the modeler was told to go look
for an outage. Three clicks, two false outage reports, one face selected.

Two things are asserted here, and the second matters more than the first:

* a timeout is a **504 ``upstream_timeout``** whose message does not claim the
  service is down and which carries a ``Retry-After``;
* a genuine connect failure is **still** a 502 ``upstream_unavailable``. A fix
  that made everything a 504 would trade one lie for another.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.geometry import DEFAULT_GEOMETRY_TIMEOUT_S
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

TESSELLATE_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
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


def make_client(db_url: str, handler: Handler) -> TestClient:
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


def test_the_budget_is_sized_from_the_measured_distribution() -> None:
    """The 200-feature ``/overlay`` that broke the old ceiling is 40.3 s, and a
    request may additionally sit in geometry's admission queue. The default has
    to clear both with headroom, or the fix is cosmetic."""
    assert DEFAULT_GEOMETRY_TIMEOUT_S >= 40.3 + 20.0


def test_a_slow_geometry_is_a_504_that_does_not_claim_an_outage(
    db_url: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta",
            json=TESSELLATE_REQUEST,
            headers=bearer,
        )

    assert response.status_code == 504
    error = response.json()["error"]
    assert error["code"] == "upstream_timeout"
    # The whole point: the message must not accuse the service of being down.
    assert "unreachable" not in error["message"].lower()
    assert "still working" in error["message"]
    # And it must tell the client the retry is worth making — the abandoned
    # rebuild's checkpoint reaches the cache, so the retry is cheaper.
    assert int(response.headers["Retry-After"]) >= 1
    assert error["details"]["budget_s"] == pytest.approx(DEFAULT_GEOMETRY_TIMEOUT_S)


def test_a_dead_geometry_is_STILL_a_502_unreachable(db_url: str) -> None:
    """Do not trade one lie for another: a refused connection really is an
    unreachable service, and collapsing both cases into 504 would hide it."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta",
            json=TESSELLATE_REQUEST,
            headers=bearer,
        )

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "upstream_unavailable"
    assert "unreachable" in error["message"].lower()


def test_the_budget_is_env_configurable(db_url: str) -> None:
    """The right ceiling is a function of the largest part an installation
    opens, which is not something this repo can know."""
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        geometry_timeout_s=12.5,
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    app = build_app(settings, geometry_transport=httpx.MockTransport(handler))
    with TestClient(app, raise_server_exceptions=False) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta",
            json=TESSELLATE_REQUEST,
            headers=bearer,
        )
    assert response.status_code == 504
    assert response.json()["error"]["details"]["budget_s"] == pytest.approx(12.5)


def test_an_overloaded_geometry_relays_503_and_its_retry_after(db_url: str) -> None:
    """CONC-2's answer must survive the hop: a 503 with a measured retry
    interval is honest backpressure; re-labelling it 502 would put us back
    where we started."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"Retry-After": "4"},
            json={
                "error": {
                    "code": "service_overloaded",
                    "message": "Geometry is at capacity.",
                    "details": {"reason": "predicted_wait", "queued": 8},
                    "request_id": "upstream",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/tessellate/meta",
            json=TESSELLATE_REQUEST,
            headers=bearer,
        )

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_overloaded"
    assert error["details"]["reason"] == "predicted_wait"
    assert response.headers["Retry-After"] == "4"
