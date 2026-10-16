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
from loft_wire.assemblies import (
    AssemblyGraphResponse,
    EvaluatedInstance,
    ExportAssemblyRequest,
)
from loft_wire.geometry import EXPORT_MEDIA_TYPES
from loft_wire.omitted_occurrences import (
    OMITTED_OCCURRENCES_HEADER,
)
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit import REQUEST_ID_HEADER
from py_kit.db import async_dsn
from py_kit.errors import RateLimitExceededError
from py_kit.ratelimit import RateLimiter, RedisClient
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]


class _BlockingLimiter(RateLimiter):
    """A limiter whose every ``compute`` check denies — proves the route RUNS
    the ``COMPUTE_RATE_LIMIT`` dependency (a route without it never calls
    ``check``, so the request would 200 through instead of 429). The ``auth``
    scope (register, which sets the test up) is let through."""

    def __init__(self) -> None:
        super().__init__(cast(RedisClient, None), limit=1, window_s=60)

    async def check(
        self, identity: str, *, scope: str = "compute", limit: int | None = None
    ) -> None:
        if scope != "compute":
            return
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


def _no_stored_assembly(_request: httpx.Request) -> httpx.Response:
    """Documents' uniform 404: the assembly is not the caller's (or not stored),
    so an unnamed export keeps the id fallback."""
    return httpx.Response(
        404,
        json={
            "error": {
                "code": "not_found",
                "message": "Assembly not found.",
                "details": None,
                "request_id": "documents-id",
            }
        },
    )


def make_client(
    db_url: str,
    geometry_handler: Handler,
    limiter: RateLimiter | None = None,
    documents_handler: Handler = _no_stored_assembly,
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
        documents_transport=httpx.MockTransport(documents_handler),
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


def test_assembly_export_passes_the_omitted_occurrences_header_through(
    db_url: str,
) -> None:
    """ASM-FAILED-PART-API: geometry names the occurrences a short file leaves
    out; the proxy forwards the header verbatim (like ``X-Loft-Properties``),
    and a file without one gets none."""
    value = (
        '{"count":2,"parts":[{"name":"Crank arm","part_document_id":null,'
        '"code":"no_body","occurrences":2}],"complete":true}'
    )
    sent: list[dict[str, str]] = [
        {OMITTED_OCCURRENCES_HEADER: value},
        {},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=EXPORT_BYTES["step"],
            headers={"content-type": EXPORT_MEDIA_TYPES["step"], **sent.pop(0)},
        )

    with make_client(db_url, handler) as client:
        bearer = _register(client)
        body = _request("step").model_dump(mode="json")
        url = "/api/v1/geometry/assembly/export"
        short = client.post(url, json=body, headers=bearer)
        full = client.post(url, json=body, headers=bearer)
        assert short.status_code == 200, short.text
        assert short.headers[OMITTED_OCCURRENCES_HEADER] == value
        assert full.status_code == 200, full.text
        assert OMITTED_OCCURRENCES_HEADER not in full.headers


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


def _graph(name: str) -> dict[str, Any]:
    """The stored assembly's graph as documents returns it (only the name is
    read)."""
    now = "2026-10-16T00:00:00Z"
    return AssemblyGraphResponse.model_validate(
        {
            "assembly": {
                "id": str(ASSEMBLY),
                "name": name,
                "owner_id": str(uuid.uuid4()),
                "length_unit": "mm",
                "doc_version": 3,
                "created_at": now,
                "updated_at": now,
            },
            "doc_version": 3,
            "instances": [],
            "mates": [],
            "can_undo": False,
            "can_redo": False,
        }
    ).model_dump(mode="json")


def _passthrough(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=EXPORT_BYTES["step"])

    return handler


def test_an_unnamed_export_takes_the_stored_assembly_name(db_url: str) -> None:
    """BIKE2-STEP-FLAT: an API caller exporting an assembly's evaluation
    request sends no name, and the STEP root product was the assembly's UUID.
    The gateway reads the caller's stored assembly and names the export after
    it, as the web does."""
    geometry: list[httpx.Request] = []
    documents: list[httpx.Request] = []

    def stored(request: httpx.Request) -> httpx.Response:
        documents.append(request)
        return httpx.Response(200, json=_graph("Bike"))

    with make_client(db_url, _passthrough(geometry), documents_handler=stored) as c:
        bearer = _register(c)
        response = c.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    [lookup] = documents
    assert (lookup.method, lookup.url.path) == ("GET", f"/api/v1/assemblies/{ASSEMBLY}")
    assert PRINCIPAL_HEADER in lookup.headers  # owner-scoped read
    [upstream] = geometry
    sent = ExportAssemblyRequest.model_validate_json(upstream.content)
    assert sent.name == "Bike"
    assert [i.instance_id for i in sent.instances] == [INSTANCE_A, INSTANCE_B]


def test_a_named_export_does_not_read_the_assembly(db_url: str) -> None:
    geometry: list[httpx.Request] = []
    documents: list[httpx.Request] = []

    def stored(request: httpx.Request) -> httpx.Response:
        documents.append(request)
        return httpx.Response(200, json=_graph("Stored name"))

    request = _request("step").model_copy(update={"name": "Sent name"})
    with make_client(db_url, _passthrough(geometry), documents_handler=stored) as c:
        bearer = _register(c)
        response = c.post(
            "/api/v1/geometry/assembly/export",
            json=request.model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    assert documents == []
    assert ExportAssemblyRequest.model_validate_json(geometry[0].content) == request


def test_an_unparseable_stored_assembly_keeps_the_id_fallback(db_url: str) -> None:
    """A 200 from documents that is not an assembly graph must not turn the
    export into a 500: the name is a nicety, so the request goes on unnamed."""
    geometry: list[httpx.Request] = []

    def garbled(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not json")

    with make_client(db_url, _passthrough(geometry), documents_handler=garbled) as c:
        bearer = _register(c)
        response = c.post(
            "/api/v1/geometry/assembly/export",
            json=_request("step").model_dump(mode="json"),
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    [upstream] = geometry
    assert ExportAssemblyRequest.model_validate_json(upstream.content).name is None
