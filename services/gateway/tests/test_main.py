"""gateway.main — skeleton probes + error-envelope smoke."""

from typing import Any

from fastapi.testclient import TestClient
from gateway.main import GatewaySettings, app, build_app
from py_kit import NotFoundError


def test_default_settings() -> None:
    settings = GatewaySettings()
    assert settings.service_name == "gateway"
    assert settings.port == 8000
    assert settings.geometry_url == "http://localhost:8002"


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_stays_ready_with_geometry_down() -> None:
    """The geometry check is report-only: unreachable upstream never fails
    readiness (see gateway.main), it is just annotated in the report."""
    settings = GatewaySettings(geometry_url="http://127.0.0.1:9")  # nothing listens
    response = TestClient(build_app(settings)).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"geometry": "unreachable"}}


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
        raise NotFoundError("No such thing.", details={"thing": "t1"})

    response = TestClient(service).get("/api/v1/boom")
    assert response.status_code == 404
    error = _envelope(response.json())
    assert error["code"] == "not_found"
    assert error["details"] == {"thing": "t1"}
