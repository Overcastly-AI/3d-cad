"""py_kit.config — env-driven settings (12-factor)."""

import pytest
from py_kit.config import BaseServiceSettings

_ENV_VARS = (
    "SERVICE_NAME",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "PORT",
    "REDIS_URL",
    "POSTGRES_URL",
    "S3_URL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults() -> None:
    settings = BaseServiceSettings()
    assert settings.service_name == "loft-service"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.port == 8000
    assert settings.redis_url is None
    assert settings.postgres_url is None
    assert settings.s3_url is None


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "gateway")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    settings = BaseServiceSettings()
    assert settings.service_name == "gateway"
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"
    assert settings.port == 9001
    assert settings.redis_url == "redis://redis:6379/0"


def test_subclass_adds_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    class GatewaySettings(BaseServiceSettings):
        jwt_secret: str = "dev-secret"

    monkeypatch.setenv("JWT_SECRET", "s3cret")
    settings = GatewaySettings()
    assert settings.jwt_secret == "s3cret"
    assert settings.port == 8000  # base defaults still apply
