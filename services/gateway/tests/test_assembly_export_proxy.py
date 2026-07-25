"""gateway ``POST /api/v1/geometry/assembly/export`` — the assembly-export proxy
(assemblies §4, commit ``b7408fd``).

Same harness as tests/test_assembly_evaluate_proxy.py (mock geometry transport,
real auth over SQLite), applied to the BYTES-returning export route (mirroring
tests/test_geometry_proxy.py's part ``/export``): the route is auth-gated (F7)
and rate-limited (``COMPUTE_RATE_LIMIT``), validates the shared
``ExportAssemblyRequest`` at the gateway, relays it to geometry's identity-free
``/api/v1/assembly/export`` hop (NO principal), and streams the STEP/STL bytes +
``Content-Disposition`` back byte-exact. A non-200 upstream envelope re-surfaces
verbatim through ``_raise_upstream_error``.
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
    EvaluatedInstance,
    ExportAssemblyRequest,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]


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


ASSEMBLY = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
INSTANCE_A = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
INSTANCE_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")

#: Fake export payloads per format — passthrough is asserted byte-exact.
EXPORT_BYTES: dict[str, bytes] = {
    "step": b"ISO-10303-21;\nfake assembly step\nEND-ISO-10303-21;\n",
    "stl": b"\x00" * 80 + b"\x0c\x00\x00\x00fake-binary-stl",
}


def _request(fmt: str) -> ExportAssemblyRequest:
    """A small two-instance export request (empty feature prefixes suffice for a
    proxy test — the gateway only validates + relays, geometry evaluates)."""
    return ExportAssemblyRequest(
        assembly_id=ASSEMBLY,
        version=1,
        format=fmt,  # type: ignore[arg-type]
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


@pytest.mark.parametrize("fmt", ["step", "stl"])
def test_assembly_export_proxies_file_and_content_disposition(
    db_url: str, fmt: str
) -> None:
    """A valid export forwards the shared ``ExportAssemblyRequest`` VERBATIM to
    geometry's identity-free hop and streams the file bytes + ``Content-Disposition``
    back byte-exact with the right media type."""
    seen: list[httpx.Request] = []
    payload = EXPORT_BYTES[fmt]
    disposition = f'attachment; filename="assembly.{fmt}"'

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

    request = _request(fmt)
    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/assembly/export",
            json=request.model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    assert response.content == payload  # byte-exact passthrough
    assert response.headers["content-type"] == EXPORT_MEDIA_TYPES[fmt]
    assert response.headers["content-disposition"] == disposition

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/assembly/export"
    assert ExportAssemblyRequest.model_validate_json(upstream.content) == request
    # Request id correlates logs; geometry is identity-free (RESEARCH §3).
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]
    assert PRINCIPAL_HEADER not in upstream.headers
    assert "authorization" not in upstream.headers


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=EXPORT_BYTES["step"])

    with make_client(db_url, handler) as client:
        response = client.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
        )

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


def test_invalid_request_rejected_at_gateway(db_url: str) -> None:
    """The shared DTO validates at the gateway — a bad format (or bad body) never
    goes upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=EXPORT_BYTES["step"])

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/assembly/export",
            headers=bearer,
            json={
                "assembly_id": str(ASSEMBLY),
                "version": 1,
                "instances": [],
                "format": "obj",
            },
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_upstream_envelope_error_is_resurfaced(db_url: str) -> None:
    """A non-200 upstream (e.g. geometry's ``assembly_export_no_body`` 422) is
    re-raised through ``_raise_upstream_error``, not swallowed."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "assembly_export_no_body",
                    "message": "The assembly produced no exportable body.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "assembly_export_no_body"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_geometry_unreachable_is_502(db_url: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        response = client.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}


def test_route_is_rate_limited(db_url: str) -> None:
    """The route carries the ``COMPUTE_RATE_LIMIT`` dependency (same posture as
    ``/assembly/evaluate`` + ``/export``): a denying limiter is a 429
    ``rate_limited`` envelope with ``Retry-After`` and NOTHING forwarded upstream."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=EXPORT_BYTES["step"],
            headers={"content-type": EXPORT_MEDIA_TYPES["step"]},
        )

    with make_client(db_url, handler, _BlockingLimiter()) as client:
        bearer = _register(client)
        blocked = client.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
            headers=bearer,
        )

    assert blocked.status_code == 429
    assert _envelope(blocked.json())["code"] == "rate_limited"
    assert blocked.headers["Retry-After"] == "60"
    # The blocked request never reached the geometry service.
    assert seen == []
