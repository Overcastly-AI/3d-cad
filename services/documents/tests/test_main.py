"""documents.main — probes + error-envelope smoke.

Postgres readiness is the shared HARD py-kit check (py_kit.db): "skipped"
without POSTGRES_URL, a real ``SELECT 1`` otherwise — the ok/unreachable
paths need a running lifespan and live in tests/test_parts.py.
"""

from typing import Any

import pytest
from documents.main import DocumentsSettings, app, build_app
from fastapi.testclient import TestClient
from py_kit import ConflictError

#: The DSN compose builds from its published default POSTGRES_PASSWORD.
_DEFAULT_PASSWORD_DSN = "postgresql://loft:loft-dev-only@db:5432/loft_documents"


def test_default_settings() -> None:
    settings = DocumentsSettings()
    assert settings.service_name == "documents"
    assert settings.port == 8001


def test_refuses_the_published_default_postgres_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The parts store holds every user's model data; booting it behind a
    # password published in this repo is the failure the guard exists for.
    # LOFT_ENV is deleted explicitly: the gateway suite's conftest sets it
    # process-wide, and a whole-repo pytest run collects that conftest first.
    monkeypatch.delenv("LOFT_ENV", raising=False)
    with pytest.raises(RuntimeError, match="POSTGRES_URL"):
        DocumentsSettings(postgres_url=_DEFAULT_PASSWORD_DSN)
    with pytest.raises(RuntimeError, match="POSTGRES_URL"):
        DocumentsSettings(loft_env="production", postgres_url=_DEFAULT_PASSWORD_DSN)


def test_dev_allows_the_published_default_postgres_password() -> None:
    settings = DocumentsSettings(loft_env="dev", postgres_url=_DEFAULT_PASSWORD_DSN)
    assert settings.postgres_url == _DEFAULT_PASSWORD_DSN


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_postgres_skipped_when_unconfigured() -> None:
    service = build_app(DocumentsSettings(postgres_url=None))
    response = TestClient(service).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "skipped"}}


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
