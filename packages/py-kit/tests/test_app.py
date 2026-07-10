"""py_kit.app — factory, probes, request-id middleware, error envelope."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from py_kit.app import REQUEST_ID_HEADER, create_app
from py_kit.config import BaseServiceSettings
from py_kit.errors import ApiError, ConflictError, NotFoundError
from pydantic import BaseModel


class _Payload(BaseModel):
    quantity: int


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

    return TestClient(app, raise_server_exceptions=False)


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
