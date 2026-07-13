"""geometry.main — probes + error-envelope smoke.

Kernel behaviour is covered by tests/test_kernel.py; the API surface by
tests/test_api.py; the worker task by tests/test_worker.py.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import GeometrySettings, app, build_app
from geometry.mesh_store import MeshStoreMultiWorkerError
from py_kit import InternalError


def test_default_settings() -> None:
    settings = GeometrySettings()
    assert settings.service_name == "geometry"
    assert settings.port == 8002
    assert settings.web_concurrency == 1  # single-worker default (§7.8 guard)


def test_build_app_boots_clean_on_single_worker() -> None:
    # The safe default topology stays healthy — the guard never fires at 1.
    service = build_app(GeometrySettings(web_concurrency=1))
    assert TestClient(service).get("/healthz").status_code == 200


def test_build_app_refuses_multiworker() -> None:
    # WEB_CONCURRENCY>1 would split the in-process mesh store across workers and
    # 404 evaluated meshes intermittently — fail loud at startup instead (F1).
    with pytest.raises(MeshStoreMultiWorkerError):
        build_app(GeometrySettings(web_concurrency=2))


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_redis_skipped_when_unconfigured() -> None:
    service = build_app(GeometrySettings(redis_url=None))
    response = TestClient(service).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"redis": "skipped"}}


def test_readyz_redis_reported_when_configured() -> None:
    service = build_app(GeometrySettings(redis_url="redis://redis:6379/0"))
    response = TestClient(service).get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"].startswith("configured")


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
        raise InternalError("Tessellation failed.")

    response = TestClient(service).get("/api/v1/boom")
    assert response.status_code == 500
    assert _envelope(response.json())["code"] == "internal_error"
