"""gateway ``POST /api/v1/geometry/assembly/interference`` — the assembly
interference-check proxy (assemblies §4, commit ``e46db16``).

Same harness as tests/test_assembly_evaluate_proxy.py (mock geometry transport,
real auth over SQLite): the route is auth-gated (F7) and rate-limited
(``COMPUTE_RATE_LIMIT``), validates the shared ``EvaluateAssemblyRequest`` at the
gateway, relays it to geometry's identity-free ``/api/v1/assembly/interference``
hop (NO principal), and passes the typed ``InterferenceResult`` JSON through
verbatim. A non-200 upstream envelope re-surfaces through
``_raise_upstream_error``; a transport failure maps to the 502 envelope.
"""

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit import REQUEST_ID_HEADER
from py_kit.db import async_dsn
from py_kit.errors import RateLimitExceededError
from py_kit.ratelimit import RateLimiter, RedisClient
from py_kit.schemas.assemblies import (
    ClashPair,
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    InterferenceResult,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

ASSEMBLY = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
INSTANCE_A = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
INSTANCE_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


class _BlockingLimiter(RateLimiter):
    """A limiter whose every ``check`` denies — proves the route RUNS the
    ``COMPUTE_RATE_LIMIT`` dependency (a route without it never calls ``check``,
    so the request would 200 through instead of 429)."""

    def __init__(self) -> None:
        super().__init__(cast(RedisClient, None), limit=1, window_s=60)

    async def check(self, identity: str, *, scope: str = "compute") -> None:
        raise RateLimitExceededError(
            "Rate limit exceeded.",
            retry_after_s=60,
            details={"limit": 1, "window_s": 60, "retry_after_s": 60},
        )


def _request() -> EvaluateAssemblyRequest:
    """A small two-instance request (empty feature prefixes suffice for a proxy
    test — the gateway only validates + relays, geometry solves + scans)."""
    return EvaluateAssemblyRequest(
        assembly_id=ASSEMBLY,
        version=1,
        instances=[
            EvaluatedInstance(
                instance_id=INSTANCE_A,
                part_key=f"{uuid.uuid4()}@tip",
                features=[],
                grounded=True,
            ),
            EvaluatedInstance(
                instance_id=INSTANCE_B,
                part_key=f"{uuid.uuid4()}@tip",
                features=[],
            ),
        ],
    )


def _result() -> InterferenceResult:
    """A one-clash result — the pass-through fidelity target."""
    return InterferenceResult(
        assembly_id=ASSEMBLY,
        version=1,
        clashes=[
            ClashPair(
                instance_a=INSTANCE_A,
                instance_b=INSTANCE_B,
                overlap_volume_mm3=12.5,
            )
        ],
        status="well_constrained",
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


def make_client(
    db_url: str, geometry_handler: Handler, limiter: RateLimiter | None = None
) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry_handler),
        rate_limiter=limiter,
    )
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


def test_interference_proxies_typed_result(db_url: str) -> None:
    """A valid request forwards the shared DTO VERBATIM to geometry's identity-free
    hop and passes the typed ``InterferenceResult`` JSON through verbatim."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_result().model_dump_json())

    request = _request()
    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/assembly/interference",
            json=request.model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    result = InterferenceResult.model_validate(response.json())
    assert result == _result()
    assert result.status == "well_constrained"
    assert [(c.instance_a, c.instance_b) for c in result.clashes] == [
        (INSTANCE_A, INSTANCE_B)
    ]

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/assembly/interference"
    relayed = EvaluateAssemblyRequest.model_validate_json(upstream.content)
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
            "/api/v1/geometry/assembly/interference",
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
            "/api/v1/geometry/assembly/interference",
            headers=bearer,
            json={"assembly_id": "not-a-uuid", "version": 1, "instances": []},
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    """A non-200 upstream envelope is re-raised through ``_raise_upstream_error``,
    not swallowed."""

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
            "/api/v1/geometry/assembly/interference",
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
            "/api/v1/geometry/assembly/interference",
            json=_request().model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}


def test_route_is_rate_limited(db_url: str) -> None:
    """The route carries the ``COMPUTE_RATE_LIMIT`` dependency (same posture as
    ``/assembly/evaluate``): a denying limiter is a 429 ``rate_limited`` envelope
    with ``Retry-After`` and NOTHING forwarded upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_result().model_dump_json())

    with make_client(db_url, handler, _BlockingLimiter()) as client:
        bearer = _register(client)
        blocked = client.post(
            "/api/v1/geometry/assembly/interference",
            json=_request().model_dump(mode="json"),
            headers=bearer,
        )

    assert blocked.status_code == 429
    assert _envelope(blocked.json())["code"] == "rate_limited"
    assert blocked.headers["Retry-After"] == "60"
    # The blocked request never reached the geometry service.
    assert seen == []
