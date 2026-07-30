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


class TestMinioCredentialPosture:
    """The MinIO root password is the one datastore credential outside a URL.

    Geometry declares it to py-kit's dev-credential guard
    (``datastore_credential_fields``), so the published compose default is
    refused unless ``LOFT_ENV=dev`` — same policy as the gateway's JWT
    posture, one shared ``LOFT_ENV``.
    """

    def test_published_default_refuses_to_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # LOFT_ENV is deleted explicitly: the gateway suite's conftest sets it
        # process-wide, and a whole-repo pytest run collects that conftest first.
        monkeypatch.delenv("LOFT_ENV", raising=False)
        with pytest.raises(RuntimeError, match="S3_SECRET_ACCESS_KEY"):
            GeometrySettings(s3_secret_access_key="loft-minio-dev-only")
        with pytest.raises(RuntimeError, match="MINIO_ROOT_PASSWORD"):
            GeometrySettings(
                loft_env="production", s3_secret_access_key="loft-minio-dev-only"
            )

    def test_dev_allows_the_default(self) -> None:
        settings = GeometrySettings(
            loft_env="dev", s3_secret_access_key="loft-minio-dev-only"
        )
        assert settings.s3_secret_access_key == "loft-minio-dev-only"

    def test_real_credential_boots(self) -> None:
        settings = GeometrySettings(s3_secret_access_key="cb6f0a1d9e4f7c2b8a35")
        assert settings.s3_secret_access_key == "cb6f0a1d9e4f7c2b8a35"

    def test_unset_credential_boots(self) -> None:
        # Unset = boto3's default credential chain (IAM role, AWS_* env); the
        # guard demands a credential from nobody, it only judges the one set.
        assert GeometrySettings().s3_secret_access_key is None


def test_build_app_boots_clean_on_single_worker() -> None:
    # The safe default topology stays healthy — the guard never fires at 1.
    service = build_app(GeometrySettings(web_concurrency=1))
    assert TestClient(service).get("/healthz").status_code == 200


def test_build_app_refuses_multiworker() -> None:
    # WEB_CONCURRENCY>1 would split the in-process mesh store across workers and
    # 404 evaluated meshes intermittently — fail loud at startup instead (F1).
    with pytest.raises(MeshStoreMultiWorkerError):
        build_app(GeometrySettings(web_concurrency=2))


def test_build_app_lifts_guard_when_s3_configured() -> None:
    # With S3_URL set the shared S3/MinIO store is installed, so multi-worker is
    # safe and the single-worker guard is lifted (§7.8 swap; audit F6). No MinIO
    # is contacted — boto3.client() opens no connection and /healthz never
    # touches the store. Restore the LRU global afterward so no S3 backend leaks.
    from geometry.mesh_store import MeshStore, configure_mesh_store

    try:
        service = build_app(
            GeometrySettings(
                web_concurrency=4,
                s3_url="http://s3.local:9000",
                s3_bucket="loft",
                s3_access_key_id="x",
                s3_secret_access_key="y",
            )
        )
        assert TestClient(service).get("/healthz").status_code == 200
    finally:
        backend = configure_mesh_store(None, "loft")
        assert isinstance(backend, MeshStore)


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
