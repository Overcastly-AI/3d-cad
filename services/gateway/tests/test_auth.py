"""gateway.auth — register/login/me, JWT posture, and secret-leak guards.

Test-vs-prod dialect split (stated honestly): production runs PostgreSQL via
asyncpg; this suite runs the SAME application code against SQLite via
aiosqlite (file-per-test), because the sandbox has no Postgres daemon. The
column types in :mod:`gateway.db` are dialect-portable on purpose. What that
split does NOT cover on the security path:

- The duplicate-email 409 relies on ``IntegrityError`` from the unique
  constraint. SQLite raises it too (asserted here), but the asyncpg
  ``UniqueViolationError`` → ``IntegrityError`` mapping itself is only
  exercised against real Postgres (compose stack / e2e).
- Native ``UUID`` / ``TIMESTAMPTZ`` column behavior and the ``now()`` server
  default are Postgres-rendered (verified via the alembic offline SQL), not
  executed here — SQLite always receives the client-side Python defaults.
- Concurrent-commit races on the unique constraint are not simulated.

Everything above the driver — hashing, JWT verify paths, uniform 401s,
envelope hygiene, log hygiene — is dialect-independent and covered here.
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from gateway.auth.security import (
    AuthConfig,
    create_access_token,
    hash_password,
    verify_password,
)
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

#: >= MIN_JWT_SECRET_LENGTH; distinctive so leak-assertions can grep for it.
TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

#: Deliberately distinctive — the leak tests assert this exact string never
#: appears in logs or response bodies.
PASSWORD = "hunter2-Sup3rSecret-passphrase"

EMAIL = "alice@example.com"

TOKEN_TTL_S = 3600

#: Matches the app's resolved config (same secret/TTL) so tests can mint
#: expired/foreign tokens without going through HTTP.
TEST_AUTH_CONFIG = AuthConfig(jwt_secret=TEST_JWT_SECRET, token_ttl_s=TOKEN_TTL_S)


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


def _settings(postgres_url: str | None) -> GatewaySettings:
    """Explicit values everywhere — ambient env vars must not steer tests."""
    return GatewaySettings(
        geometry_url="http://127.0.0.1:9",  # nothing listens; irrelevant here
        postgres_url=postgres_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
        jwt_ttl_s=TOKEN_TTL_S,
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A file-backed SQLite database with the users schema applied."""
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    """App over the test DB, with the lifespan running (engine owned)."""
    with TestClient(build_app(_settings(db_url))) as test_client:
        yield test_client


def _register(
    client: TestClient, email: str = EMAIL, password: str = PASSWORD
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def _assert_same_user(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Same account, timestamp compared as an instant.

    SQLite dialect artifact (see module docstring): ``DateTime(timezone=True)``
    round-trips as a NAIVE datetime on SQLite, so ``created_at`` freshly
    committed (tz-aware, in-memory) and re-read (naive, from disk) serialize
    with/without the UTC suffix. Postgres/TIMESTAMPTZ has no such split.
    """
    assert a["id"] == b["id"]
    assert a["email"] == b["email"]

    def as_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    assert as_utc(a["created_at"]) == as_utc(b["created_at"])


# --- register / login happy paths -------------------------------------------


def test_register_returns_user_and_working_token(client: TestClient) -> None:
    body = _register(client)
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == TOKEN_TTL_S
    assert body["user"]["email"] == EMAIL
    uuid.UUID(body["user"]["id"])  # well-formed id
    assert "created_at" in body["user"]

    me = client.get("/api/v1/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    _assert_same_user(me.json(), body["user"])


def test_register_response_carries_no_credential_material(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201
    assert PASSWORD not in response.text
    assert "$argon2" not in response.text
    assert "password" not in response.json()["user"]


def test_register_normalizes_email_case(client: TestClient) -> None:
    body = _register(client, email="Alice@Example.COM")
    assert body["user"]["email"] == EMAIL

    login = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200


def test_login_happy_path(client: TestClient) -> None:
    registered = _register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    _assert_same_user(body["user"], registered["user"])
    assert body["token_type"] == "bearer"

    me = client.get("/api/v1/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200


# --- credential failures (uniform 401) ---------------------------------------


def test_login_wrong_password_401(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password-123"}
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    error = _envelope(response.json())
    assert error["code"] == "invalid_credentials"
    # Generic on purpose: must not say which of email/password was wrong.
    assert "password" not in error["message"].lower() or "email" in error["message"]
    assert PASSWORD not in response.text


def test_login_unknown_email_indistinguishable_from_wrong_password(
    client: TestClient,
) -> None:
    """Anti-enumeration: both failures return byte-identical envelopes
    (modulo request id), so the response body never reveals whether an
    account exists."""
    _register(client)
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password-123"}
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-123"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    a, b = _envelope(wrong_password.json()), _envelope(unknown_email.json())
    a.pop("request_id")
    b.pop("request_id")
    assert a == b


def test_register_duplicate_email_409(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "another-password-42"},
    )
    assert response.status_code == 409
    assert _envelope(response.json())["code"] == "email_taken"


def test_register_duplicate_email_case_insensitive(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ALICE@example.com", "password": "another-password-42"},
    )
    assert response.status_code == 409


# --- token defects on /me -----------------------------------------------------


def test_me_without_token_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _envelope(response.json())["code"] == "unauthorized"


def test_me_with_malformed_token_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers=_bearer("not.a.jwt"))
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "invalid_token"


def test_me_with_expired_token_401(client: TestClient) -> None:
    body = _register(client)
    user_id = uuid.UUID(body["user"]["id"])
    expired = create_access_token(
        user_id,
        TEST_AUTH_CONFIG,
        now=datetime.now(UTC) - timedelta(seconds=TOKEN_TTL_S + 60),
    )
    response = client.get("/api/v1/auth/me", headers=_bearer(expired))
    assert response.status_code == 401
    error = _envelope(response.json())
    assert error["code"] == "invalid_token"
    # Generic on purpose: expired vs. tampered vs. malformed all share one
    # message, so the response never discloses which check failed.
    malformed = client.get("/api/v1/auth/me", headers=_bearer("not.a.jwt"))
    assert error["message"] == _envelope(malformed.json())["message"]


def test_me_with_tampered_signature_401(client: TestClient) -> None:
    body = _register(client)
    attacker = AuthConfig(
        jwt_secret="attacker-controlled-secret-0123456789", token_ttl_s=3600
    )
    forged = create_access_token(uuid.UUID(body["user"]["id"]), attacker)
    assert forged != body["access_token"]
    response = client.get("/api/v1/auth/me", headers=_bearer(forged))
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "invalid_token"


def test_me_rejects_alg_none_token(client: TestClient) -> None:
    """`alg: none` confusion: an unsigned token with valid claims is rejected
    because decode pins ``algorithms=[HS256]``."""
    body = _register(client)
    now = int(datetime.now(UTC).timestamp())
    unsigned = pyjwt.encode(  # pyright: ignore[reportUnknownMemberType]
        {"sub": body["user"]["id"], "iat": now, "exp": now + 600},
        None,
        algorithm="none",
    )
    response = client.get("/api/v1/auth/me", headers=_bearer(unsigned))
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "invalid_token"


def test_me_with_token_for_deleted_user_401(client: TestClient) -> None:
    """A validly-signed token whose subject no longer exists is a 401, not a
    500 — the subject is re-checked against the store on every request."""
    _register(client)
    ghost = create_access_token(uuid.uuid4(), TEST_AUTH_CONFIG)
    response = client.get("/api/v1/auth/me", headers=_bearer(ghost))
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "invalid_token"


# --- password policy (422s must not echo the value) --------------------------


def test_register_short_password_422_without_echo(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": "short"}
    )
    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "validation_error"
    assert error["details"] == {"field": "password"}
    assert "short" not in response.text.replace(
        "at least", ""
    )  # the value itself is not echoed


def test_register_oversized_password_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": "x" * 300}
    )
    assert response.status_code == 422
    assert "x" * 300 not in response.text


def test_schema_validation_422_does_not_echo_password(client: TestClient) -> None:
    """pydantic-level 422 (bad email) with a real password in the payload:
    py-kit scrubs the ``input`` echo from validation details."""
    response = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "not-an-email" not in response.text  # input echo scrubbed entirely


# --- no credential material in logs ------------------------------------------


def test_no_password_or_hash_material_in_logs(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise register + login (success and failure) and assert neither the
    plaintext password nor any argon2 hash appears on the log stream
    (structlog renders to stdout) or in any response body."""
    responses = [
        client.post(
            "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
        ),
        client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}),
        client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-guess-1"}
        ),
        client.post(
            "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
        ),  # duplicate → 409 path
    ]
    logged = capsys.readouterr()
    stream = logged.out + logged.err
    for secret in (PASSWORD, "wrong-guess-1", "$argon2"):
        assert secret not in stream, f"credential material leaked to logs: {secret!r}"
        for response in responses:
            if secret is PASSWORD or secret == "$argon2":
                assert secret not in response.text


# --- database posture ---------------------------------------------------------


def test_auth_routes_503_without_database_configured() -> None:
    settings = _settings(postgres_url=None)
    with TestClient(build_app(settings)) as client:
        response = client.post(
            "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
        )
    assert response.status_code == 503
    assert _envelope(response.json())["code"] == "database_unavailable"


def test_readyz_reports_postgres_ok_with_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["postgres"] == "ok"


def test_readyz_503_when_database_unreachable_without_dsn_leak() -> None:
    """HARD readiness: a dead DB is a 503, and the body carries the exception
    *type* only — never the DSN (it embeds credentials)."""
    settings = _settings(
        postgres_url="postgresql://loft:hunter2-dsn-password@127.0.0.1:9/loft"
    )
    with TestClient(build_app(settings)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["postgres"].startswith("error: ")
    assert "hunter2-dsn-password" not in response.text
    assert "127.0.0.1" not in response.text


# --- startup fail-fast on the JWT secret --------------------------------------


class TestStartupFailFast:
    """`build_app` must refuse to construct the app on a bad secret posture —
    referenced from gateway/auth/security.py's module docstring."""

    def test_non_dev_env_without_secret_refuses_to_boot(self) -> None:
        settings = GatewaySettings(loft_env="production", jwt_secret=None)
        with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
            build_app(settings)

    def test_empty_secret_counts_as_unset(self) -> None:
        settings = GatewaySettings(loft_env="staging", jwt_secret="")
        with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
            build_app(settings)

    def test_typoed_env_name_fails_closed(self) -> None:
        """Only the exact string "dev" opts into the fallback — a typo like
        "Dev" must NOT silently weaken a deployment."""
        settings = GatewaySettings(loft_env="Dev", jwt_secret=None)
        with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
            build_app(settings)

    def test_short_secret_rejected_in_every_env(self) -> None:
        for env in ("dev", "production"):
            settings = GatewaySettings(loft_env=env, jwt_secret="too-short")
            with pytest.raises(RuntimeError, match="too short"):
                build_app(settings)

    def test_nonpositive_ttl_rejected(self) -> None:
        settings = GatewaySettings(
            loft_env="dev", jwt_secret=TEST_JWT_SECRET, jwt_ttl_s=0
        )
        with pytest.raises(RuntimeError, match="JWT_TTL_S"):
            build_app(settings)

    def test_dev_without_secret_boots_with_logged_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        settings = GatewaySettings(loft_env="dev", jwt_secret=None)
        app = build_app(settings)
        assert app.state.auth_config.jwt_secret  # fallback engaged
        assert "jwt_dev_fallback_secret_in_use" in capsys.readouterr().out

    def test_valid_secret_boots_in_production_env(self) -> None:
        settings = GatewaySettings(loft_env="production", jwt_secret=TEST_JWT_SECRET)
        assert build_app(settings).state.auth_config.jwt_secret == TEST_JWT_SECRET


# --- hashing unit checks -------------------------------------------------------


def test_hash_password_salted_and_verifiable() -> None:
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second  # salted: same input, different hashes
    assert first.startswith("$argon2id$")
    assert verify_password(first, PASSWORD)
    assert not verify_password(first, PASSWORD + "x")


def test_verify_password_survives_garbage_hash() -> None:
    assert not verify_password("not-a-real-hash", PASSWORD)
