"""py_kit.config — env-driven settings (12-factor)."""

import json
from collections.abc import Callable
from typing import ClassVar

import pytest
from py_kit.config import (
    DEV_ENV,
    BaseServiceSettings,
    credential_defect,
    is_dev_env,
    url_credential,
)
from py_kit.logging import configure_logging

_ENV_VARS = (
    "SERVICE_NAME",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "PORT",
    "LOFT_ENV",
    "REDIS_URL",
    "POSTGRES_URL",
    "S3_URL",
)

#: A DSN carrying this repo's published compose default (docker-compose.yml).
_DEFAULT_PASSWORD_DSN = "postgresql://loft:loft-dev-only@db:5432/loft_documents"
#: The same DSN with a credential a real deployment would actually use.
_REAL_PASSWORD_DSN = "postgresql://loft:cb6f0a1d9e4f7c2b8a35@db:5432/loft_documents"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults() -> None:
    settings = BaseServiceSettings()
    assert settings.loft_env is None
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


def test_loft_env_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Posture is a BASE field: every service reads the same LOFT_ENV."""
    monkeypatch.setenv("LOFT_ENV", "production")
    assert BaseServiceSettings().loft_env == "production"


class TestIsDevEnv:
    """Only the exact, explicitly-set value opts into dev posture."""

    def test_exact_value_is_dev(self) -> None:
        assert is_dev_env(DEV_ENV) is True

    @pytest.mark.parametrize(
        "value", [None, "", "DEV", "Dev", " dev", "development", "production", "prod"]
    )
    def test_everything_else_is_not_dev(self, value: str | None) -> None:
        # A typo'd or capitalised environment name must never weaken a deploy.
        assert is_dev_env(value) is False


class TestUrlCredential:
    """Only a password that is actually present gets judged."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (_DEFAULT_PASSWORD_DSN, "loft-dev-only"),
            ("redis://:s3cret@redis:6379/0", "s3cret"),
            ("http://loft-minio:loft-minio-dev-only@minio:9000", "loft-minio-dev-only"),
            # Percent-escapes are decoded, so an encoded blank reads as blank.
            ("postgresql://loft:%20%20@db:5432/loft", "  "),
            # No credential embedded at all — peer/IAM/out-of-band auth.
            ("postgresql://loft@/loft?host=/var/run/postgresql", None),
            ("redis://redis:6379/0", None),
            ("sqlite+aiosqlite:////tmp/documents.db", None),
            # Unparseable netloc: nothing to vouch for, and never a crash.
            ("postgresql://loft:pw@[::bad/loft", None),
        ],
    )
    def test_extracts_userinfo_password(self, url: str, expected: str | None) -> None:
        assert url_credential(url) == expected


class TestCredentialDefect:
    """The judgement itself, independent of where the value came from."""

    def test_unset_is_not_a_defect(self) -> None:
        assert credential_defect(None) is None

    @pytest.mark.parametrize("value", ["", "   ", "\n\t "])
    def test_blank_is_a_defect(self, value: str) -> None:
        defect = credential_defect(value)
        assert defect is not None
        assert "empty" in defect

    @pytest.mark.parametrize(
        "value",
        [
            "loft-dev-only",
            "loft-minio-dev-only",
            "MinioAdmin",
            " postgres ",
            "changeme",
        ],
    )
    def test_published_defaults_are_a_defect(self, value: str) -> None:
        # Case-insensitive, whitespace-tolerant: `POSTGRES_PASSWORD=Postgres `
        # is the same unchanged default as `postgres`.
        defect = credential_defect(value)
        assert defect is not None
        assert "publicly-known" in defect

    def test_real_credential_is_clean(self) -> None:
        assert credential_defect("cb6f0a1d9e4f7c2b8a35") is None


class TestDatastoreCredentialGuard:
    """Fail closed on published/blank datastore credentials outside dev.

    Mirrors ``TestStartupFailFast`` in the gateway's auth tests: same policy,
    same LOFT_ENV field, different secret.
    """

    def test_real_credential_boots(self) -> None:
        settings = BaseServiceSettings(postgres_url=_REAL_PASSWORD_DSN)
        assert settings.postgres_url == _REAL_PASSWORD_DSN

    def test_no_datastores_configured_boots(self) -> None:
        assert BaseServiceSettings().postgres_url is None

    def test_url_without_credential_boots(self) -> None:
        # Peer auth / IAM / out-of-band credentials are legitimate; the guard
        # judges the password that IS there, and never demands one.
        url = "postgresql://loft@/loft?host=/var/run/postgresql"
        assert BaseServiceSettings(postgres_url=url).postgres_url == url

    def test_published_default_refuses_to_boot(self) -> None:
        with pytest.raises(RuntimeError) as excinfo:
            BaseServiceSettings(postgres_url=_DEFAULT_PASSWORD_DSN)
        assert "publicly-known" in str(excinfo.value)

    def test_published_default_refuses_under_a_named_environment(self) -> None:
        # LOFT_ENV set to anything but "dev" is a real deployment.
        with pytest.raises(RuntimeError, match="publicly-known"):
            BaseServiceSettings(
                loft_env="production", postgres_url=_DEFAULT_PASSWORD_DSN
            )

    @pytest.mark.parametrize("password", ["", "%20", "%20%09"])
    def test_blank_credential_refuses_to_boot(self, password: str) -> None:
        with pytest.raises(RuntimeError, match="empty/whitespace-only"):
            BaseServiceSettings(postgres_url=f"postgresql://loft:{password}@db/loft")

    @pytest.mark.parametrize(
        ("env_var", "build"),
        [
            (
                "REDIS_URL",
                lambda: BaseServiceSettings(
                    redis_url="redis://:loft-dev-only@redis:6379/0"
                ),
            ),
            (
                "S3_URL",
                lambda: BaseServiceSettings(
                    s3_url="http://loft-minio:loft-minio-dev-only@minio:9000"
                ),
            ),
        ],
    )
    def test_every_datastore_url_is_covered(
        self, env_var: str, build: Callable[[], BaseServiceSettings]
    ) -> None:
        # Not just POSTGRES_URL: every datastore endpoint the base owns.
        with pytest.raises(RuntimeError, match=env_var):
            build()

    def test_message_names_the_offending_variable_and_the_fix(self) -> None:
        # An error a self-hoster cannot act on is barely better than no error:
        # name the variable that is wrong, the knob that sets it, and the way
        # out. This assertion is the contract for that copy.
        with pytest.raises(RuntimeError) as excinfo:
            BaseServiceSettings(postgres_url=_DEFAULT_PASSWORD_DSN)
        message = str(excinfo.value)
        assert "POSTGRES_URL" in message  # the offending variable
        assert "POSTGRES_PASSWORD" in message  # where compose sources it
        assert "openssl rand -hex 32" in message  # how to generate one
        assert f"LOFT_ENV={DEV_ENV}" in message  # the explicit local-dev opt-out

    def test_dev_allows_the_default_with_a_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(BaseServiceSettings(loft_env=DEV_ENV))
        settings = BaseServiceSettings(
            loft_env=DEV_ENV, postgres_url=_DEFAULT_PASSWORD_DSN
        )
        assert settings.postgres_url == _DEFAULT_PASSWORD_DSN

        lines = [line for line in capsys.readouterr().out.splitlines() if line]
        record = json.loads(lines[-1])
        assert record["event"] == "dev_datastore_credential_in_use"
        assert record["level"] == "warning"
        assert record["variable"] == "POSTGRES_URL"

    def test_subclass_declares_extra_credential_fields(self) -> None:
        # Geometry's MinIO secret is the one datastore credential that does
        # not live inside a URL; a subclass opts it into the same guard.
        class GeometrySettings(BaseServiceSettings):
            datastore_credential_fields: ClassVar[tuple[str, ...]] = (
                "s3_secret_access_key",
            )
            s3_secret_access_key: str | None = None

        assert GeometrySettings().s3_secret_access_key is None
        assert GeometrySettings(s3_secret_access_key="cb6f0a1d9e4f").loft_env is None
        with pytest.raises(RuntimeError, match="S3_SECRET_ACCESS_KEY"):
            GeometrySettings(s3_secret_access_key="loft-minio-dev-only")
        with pytest.raises(RuntimeError, match="MINIO_ROOT_PASSWORD"):
            GeometrySettings(s3_secret_access_key="loft-minio-dev-only")
        with pytest.raises(RuntimeError, match="empty/whitespace-only"):
            GeometrySettings(s3_secret_access_key="   ")
