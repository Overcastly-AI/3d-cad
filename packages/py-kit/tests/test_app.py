"""py_kit.app — factory, probes, request-id middleware, error envelope."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from py_kit.app import (
    COMPRESSION_MINIMUM_SIZE,
    REQUEST_ID_HEADER,
    create_app,
)
from py_kit.config import BaseServiceSettings
from py_kit.errors import ApiError, ConflictError, NotFoundError, UnauthorizedError
from pydantic import BaseModel, SecretStr


class _Payload(BaseModel):
    quantity: int


class _Credentials(BaseModel):
    secret: SecretStr


def _build_app() -> TestClient:
    app = create_app(
        BaseServiceSettings(service_name="test-svc"),
        title="Test Service",
        version="0.0.1",
    )

    @app.get("/api/v1/missing")
    async def missing() -> None:
        raise NotFoundError("Part not found.", details={"part_id": "p1"})

    @app.get("/api/v1/conflict")
    async def conflict() -> None:
        raise ConflictError("Name already taken.")

    @app.get("/api/v1/custom")
    async def custom() -> None:
        raise ApiError("Teapot.", code="teapot")

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise ValueError("secret internal state: db password")

    @app.post("/api/v1/items")
    async def items(payload: _Payload) -> dict[str, int]:
        return {"quantity": payload.quantity}

    @app.get("/api/v1/protected")
    async def protected() -> None:
        raise UnauthorizedError("Not authenticated.")

    @app.post("/api/v1/credentials")
    async def credentials(payload: _Credentials) -> dict[str, bool]:
        return {"ok": bool(payload.secret)}

    @app.get("/api/v1/big-blob")
    async def big_blob() -> Response:
        """Stand-in for the GLB mesh route: big and compressible."""
        return Response(content=_BIG_BLOB, media_type="model/gltf-binary")

    @app.get("/api/v1/small-blob")
    async def small_blob() -> Response:
        """One byte under the floor — must travel uncompressed."""
        return Response(content=_SMALL_BLOB, media_type="model/gltf-binary")

    return TestClient(app, raise_server_exceptions=False)


#: A GLB-ish payload: repetitive binary, like the interleaved float buffers a
#: real mesh ships (docs/PERF.md PERF-4 measured 5.2x-11.9x on actual GLBs).
_BIG_BLOB = (bytes(range(256)) * 4 + b"\x00" * 256) * 64
_SMALL_BLOB = bytes(range(256)) * ((COMPRESSION_MINIMUM_SIZE - 1) // 256)


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def test_healthz() -> None:
    response = _build_app().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_all_checks_pass() -> None:
    async def redis_ping() -> None:
        return None

    async def postgres_ping() -> None:
        return None

    app = create_app(
        BaseServiceSettings(),
        title="Test",
        version="0.0.1",
        readiness_checks=[redis_ping, postgres_ping],
    )
    response = TestClient(app).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"redis_ping": "ok", "postgres_ping": "ok"},
    }


def test_readyz_check_may_report_status_string() -> None:
    async def postgres() -> str:
        return "skipped"

    async def redis() -> None:
        return None

    app = create_app(
        BaseServiceSettings(),
        title="Test",
        version="0.0.1",
        readiness_checks=[postgres, redis],
    )
    response = TestClient(app).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"postgres": "skipped", "redis": "ok"},
    }


def test_readyz_failing_check_gives_503_with_detail() -> None:
    async def redis_ping() -> None:
        return None

    async def postgres_ping() -> None:
        raise RuntimeError("connection refused: postgres://loft:hunter2@db:5432/loft")

    app = create_app(
        BaseServiceSettings(),
        title="Test",
        version="0.0.1",
        readiness_checks=[redis_ping, postgres_ping],
    )
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["redis_ping"] == "ok"
    # Exception *type* only — /readyz is unauthenticated and the message could
    # embed credentials (e.g. a Postgres DSN).
    assert body["checks"]["postgres_ping"] == "error: RuntimeError"
    assert "connection refused" not in response.text
    assert "hunter2" not in response.text


def test_lifespan_passed_through_to_fastapi() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        events.append("start")
        yield
        events.append("stop")

    app = create_app(
        BaseServiceSettings(), title="Test", version="0.0.1", lifespan=lifespan
    )
    with TestClient(app) as client:
        assert events == ["start"]
        assert client.get("/healthz").status_code == 200
    assert events == ["start", "stop"]


def test_probes_not_in_openapi_schema() -> None:
    app = create_app(BaseServiceSettings(), title="Test", version="0.0.1")
    paths = app.openapi()["paths"]
    assert "/healthz" not in paths
    assert "/readyz" not in paths


def test_request_id_generated_and_echoed() -> None:
    client = _build_app()
    generated = client.get("/healthz").headers[REQUEST_ID_HEADER]
    assert generated  # generated when absent

    echoed = client.get("/healthz", headers={REQUEST_ID_HEADER: "req-abc"}).headers[
        REQUEST_ID_HEADER
    ]
    assert echoed == "req-abc"


def test_api_error_envelope() -> None:
    response = _build_app().get("/api/v1/missing")
    assert response.status_code == 404
    error = _envelope(response.json())
    assert error["code"] == "not_found"
    assert error["message"] == "Part not found."
    assert error["details"] == {"part_id": "p1"}
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_conflict_and_custom_code() -> None:
    client = _build_app()

    conflict = client.get("/api/v1/conflict")
    assert conflict.status_code == 409
    assert _envelope(conflict.json())["code"] == "conflict"

    custom = client.get("/api/v1/custom")
    assert custom.status_code == 500
    assert _envelope(custom.json())["code"] == "teapot"


def test_request_validation_error_envelope() -> None:
    response = _build_app().post("/api/v1/items", json={"quantity": "not-int"})
    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "validation_error"
    details = error["details"]
    assert isinstance(details, list) and details
    assert details[0]["loc"] == ["body", "quantity"]


def test_validation_error_never_echoes_input() -> None:
    """422 details are scrubbed to type/loc/msg — the offending input value
    (which may be a password or token) is never reflected back."""
    response = _build_app().post("/api/v1/items", json={"quantity": "hunter2-secret"})
    assert response.status_code == 422
    assert "hunter2-secret" not in response.text
    details = _envelope(response.json())["details"]
    assert all(set(item) <= {"type", "loc", "msg"} for item in details)

    # A missing sibling field must not drag the whole (secret-bearing) body
    # into the `input` echo either.
    response = _build_app().post(
        "/api/v1/credentials", json={"secrets": "hunter2-secret"}
    )
    assert response.status_code == 422
    assert "hunter2-secret" not in response.text


def test_unauthorized_error_sets_bearer_challenge() -> None:
    response = _build_app().get("/api/v1/protected")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _envelope(response.json())["code"] == "unauthorized"


def test_unknown_route_uses_envelope() -> None:
    response = _build_app().get("/api/v1/nope")
    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "http_error"


def test_unhandled_exception_is_opaque_500() -> None:
    response = _build_app().get("/api/v1/boom")
    assert response.status_code == 500
    error = _envelope(response.json())
    assert error["code"] == "internal_error"
    assert error["message"] == "Internal server error."
    assert error["details"] is None
    # No stack trace or internals leak to the client.
    text = response.text
    assert "secret internal state" not in text
    assert "ValueError" not in text
    assert "Traceback" not in text


# --- Response compression (docs/PERF.md PERF-4) -----------------------------
# These assert BEHAVIOUR (what comes back on the wire), not that a middleware
# is registered: the mesh route is the hottest binary path in the product and
# shipped raw until PERF-4, so the gate has to be "a big body is actually
# smaller", not "GZipMiddleware is in app.user_middleware".


def test_large_response_is_gzipped_and_byte_exact() -> None:
    """A mesh-sized body comes back compressed — and decodes to the original."""
    response = _build_app().get("/api/v1/big-blob", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    # The wire body is strictly smaller than the payload...
    wire_bytes = int(response.headers["content-length"])
    assert wire_bytes < len(_BIG_BLOB)
    # ...and httpx has transparently inflated it back to the exact bytes, which
    # is what keeps every existing byte-level consumer (the ts-client's
    # arrayBuffer parse, `metadata.mesh.glb_bytes == len(response.content)`)
    # correct across this change.
    assert response.content == _BIG_BLOB


def test_small_response_is_not_gzipped() -> None:
    """Below the floor, compression cannot save a round trip — so we don't."""
    response = _build_app().get(
        "/api/v1/small-blob", headers={"accept-encoding": "gzip"}
    )
    assert response.status_code == 200
    assert len(_SMALL_BLOB) < COMPRESSION_MINIMUM_SIZE
    assert "content-encoding" not in response.headers
    assert response.content == _SMALL_BLOB


def test_probe_bodies_are_never_gzipped() -> None:
    """/healthz is ~15 bytes: gzip would make it BIGGER (measured 15 -> 35)."""
    response = _build_app().get("/healthz", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_client_without_gzip_support_gets_identity() -> None:
    """A client that does not advertise gzip still gets the raw bytes."""
    response = _build_app().get(
        "/api/v1/big-blob", headers={"accept-encoding": "identity"}
    )
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.content == _BIG_BLOB


def test_compressed_response_keeps_content_length_and_request_id() -> None:
    """Compression must not cost the length header or the request id.

    ``Content-Length`` survives only because gzip is registered INSIDE the
    request-id ``BaseHTTPMiddleware`` — outside it, gzip sees a stream and
    falls back to chunked, and the browser loses download progress on a
    multi-megabyte mesh. Measured both orders; this pins the working one.
    """
    response = _build_app().get("/api/v1/big-blob", headers={"accept-encoding": "gzip"})
    # Present, and it is the COMPRESSED length (not the payload's) — i.e. the
    # single-shot path ran, not the chunked fallback.
    assert int(response.headers["content-length"]) < len(_BIG_BLOB)
    assert response.headers[REQUEST_ID_HEADER]
    # Caches must key on the encoding or they will serve gzip to a client that
    # cannot read it.
    assert response.headers["vary"] == "Accept-Encoding"
