"""documents.main — skeleton probes + error-envelope smoke."""

from typing import Any

from documents.main import DocumentsSettings, app, build_app
from fastapi.testclient import TestClient
from py_kit import ConflictError


def test_default_settings() -> None:
    settings = DocumentsSettings()
    assert settings.service_name == "documents"
    assert settings.port == 8001


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_postgres_skipped_when_unconfigured() -> None:
    service = build_app(DocumentsSettings(postgres_url=None))
    response = TestClient(service).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "skipped"}}


def test_readyz_postgres_reported_when_configured() -> None:
    service = build_app(
        DocumentsSettings(postgres_url="postgresql://loft:loft@db:5432/loft")
    )
    response = TestClient(service).get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"].startswith("configured")


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def test_unknown_route_uses_error_envelope() -> None:
    response = TestClient(app).get("/api/v1/nope")
    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "http_error"


def test_api_error_renders_envelope() -> None:
    service = build_app()

    @service.get("/api/v1/boom")
    async def boom() -> None:
        raise ConflictError("Name already taken.")

    response = TestClient(service).get("/api/v1/boom")
    assert response.status_code == 409
    assert _envelope(response.json())["code"] == "conflict"
