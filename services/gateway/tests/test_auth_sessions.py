"""gateway.auth sessions: refresh rotation, reuse detection, revocation, bounds.

The design is in :mod:`gateway.auth.security`. Each property below has a test
that fails when the property is removed from the code (the mutations are
listed in the commit that introduced this file):

- ROTATION: a refresh spends the presented token and sets a different one.
- REUSE: presenting a spent token revokes the WHOLE session, including the
  successor the legitimate client holds and every access token minted in it.
- REVOCATION: logout ends the refresh chain and the access tokens.
- EXPIRY: the idle window and the absolute bound are both enforced, and no
  cookie or access token is issued past the absolute bound.

Same dialect split as ``test_auth.py`` (SQLite here, Postgres in prod). Time
is moved by rewriting the expiry COLUMNS through the ORM rather than by
patching the clock: PyJWT reads the real clock, so a patched route clock would
mint tokens PyJWT then rejects for the wrong reason.
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import httpx2 as httpx
import jwt as pyjwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from gateway.auth import auth_router
from gateway.auth.routes import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from gateway.auth.security import (
    REFRESH_REUSE_INTERVAL_S,
    AuthConfig,
    create_access_token,
    refresh_expiry,
    resolve_auth_config,
)
from gateway.db import AuthSession, Base, RefreshToken
from gateway.main import GatewaySettings, build_app
from py_kit import RateLimitExceededError
from py_kit.db import async_dsn
from py_kit.ratelimit import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
PASSWORD = "session-test-passphrase-42"
EMAIL = "carol@example.com"
TOKEN_TTL_S = 900
IDLE_TTL_S = 3 * 3600
MAX_AGE_S = 48 * 3600


def _settings(postgres_url: str) -> GatewaySettings:
    return GatewaySettings(
        geometry_url="http://127.0.0.1:9",
        postgres_url=postgres_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
        jwt_ttl_s=TOKEN_TTL_S,
        session_idle_ttl_s=IDLE_TTL_S,
        session_max_age_s=MAX_AGE_S,
    )


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway-sessions.db"
    asyncio.run(_create_schema(url))
    return url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    # https: the refresh cookie is Secure, and a jar honouring that would not
    # send it back over plain http.
    app = build_app(_settings(db_url))
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _run_sql(db_url: str, statement: sa.Executable) -> None:
    """Apply one ORM statement to the test database (moves time, see top)."""

    async def run() -> None:
        engine = create_async_engine(async_dsn(db_url))
        async with AsyncSession(engine) as session:
            await session.execute(statement)
            await session.commit()
        await engine.dispose()

    asyncio.run(run())


def _scalar(db_url: str, statement: sa.Select[Any]) -> Any:
    async def run() -> Any:
        engine = create_async_engine(async_dsn(db_url))
        async with AsyncSession(engine) as session:
            value = (await session.execute(statement)).scalar_one()
        await engine.dispose()
        return value

    return asyncio.run(run())


def _set_cookie(response: httpx.Response) -> SimpleCookie:
    """The refresh Set-Cookie, parsed (exactly one expected)."""
    headers = [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{REFRESH_COOKIE_NAME}=")
    ]
    assert len(headers) == 1, response.headers.get_list("set-cookie")
    parsed = SimpleCookie()
    parsed.load(headers[0])
    return parsed


def _cookie_value(response: httpx.Response) -> str:
    value = _set_cookie(response)[REFRESH_COOKIE_NAME].value
    assert value, "expected a refresh token, got a deletion"
    return value


def _sign_in(
    client: TestClient, *, register: bool = True, email: str = EMAIL
) -> tuple[str, str]:
    """(access token, refresh cookie value) for a fresh sign-in."""
    path = "/api/v1/auth/register" if register else "/api/v1/auth/login"
    response = client.post(path, json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    return response.json()["access_token"], _cookie_value(response)


def _refresh(
    client: TestClient, cookie: str | None, *, bearer: str | None = None
) -> httpx.Response:
    """POST /refresh presenting exactly *cookie* (the jar is bypassed)."""
    client.cookies.clear()
    headers = {} if cookie is None else {"Cookie": f"{REFRESH_COOKIE_NAME}={cookie}"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    return client.post("/api/v1/auth/refresh", headers=headers)


def _refresh_cookie_headers(response: httpx.Response) -> list[str]:
    return [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{REFRESH_COOKIE_NAME}=")
    ]


def _me(client: TestClient, access_token: str) -> int:
    client.cookies.clear()
    return client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    ).status_code


def _assert_rejected(response: httpx.Response) -> None:
    """The one refresh failure: generic 401 invalid_token that clears the cookie."""
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "invalid_token"
    assert response.json()["error"]["message"] == "Invalid or expired token."
    cleared = _set_cookie(response)[REFRESH_COOKIE_NAME]
    assert cleared.value == ""
    assert cleared["max-age"] == "0"


def _claims(access_token: str) -> dict[str, Any]:
    claims: dict[str, Any] = pyjwt.decode(  # pyright: ignore[reportUnknownMemberType]
        access_token, options={"verify_signature": False}
    )
    return claims


# --- the cookie -----------------------------------------------------------------


def test_sign_in_sets_a_hardened_refresh_cookie_and_keeps_it_out_of_the_body(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201
    morsel = _set_cookie(response)[REFRESH_COOKIE_NAME]
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "strict"
    assert morsel["path"] == REFRESH_COOKIE_PATH
    assert int(morsel["max-age"]) == IDLE_TTL_S
    assert len(morsel.value) >= 43  # 256 random bits, url-safe base64
    assert morsel.value not in response.text  # never in a body script can read
    assert "refresh" not in response.json()


def test_the_refresh_token_is_stored_only_as_a_digest(
    client: TestClient, db_url: str
) -> None:
    _, cookie = _sign_in(client)
    stored = _scalar(db_url, sa.select(RefreshToken.token_hash))
    assert stored != cookie
    assert cookie not in stored
    assert len(stored) == 64


# --- rotation -----------------------------------------------------------------------


def test_refresh_rotates_the_cookie_and_mints_a_working_access_token(
    client: TestClient,
) -> None:
    access, cookie = _sign_in(client)
    response = _refresh(client, cookie)
    assert response.status_code == 200, response.text
    body = response.json()
    rotated = _cookie_value(response)
    assert rotated != cookie
    assert body["user"]["email"] == EMAIL
    assert body["expires_in"] == TOKEN_TTL_S
    # (Byte-equal to `access` when minted in the same second: a JWT is a pure
    # function of its claims. What matters is that it verifies.)
    assert _me(client, body["access_token"]) == 200
    # Same session: the rotation did not open a new one.
    assert _claims(body["access_token"])["sid"] == _claims(access)["sid"]
    # The successor is itself refreshable, and so on: a session is a chain.
    third = _refresh(client, rotated)
    assert third.status_code == 200
    assert _cookie_value(third) not in (cookie, rotated)


def test_refresh_without_a_cookie_is_rejected(client: TestClient) -> None:
    _sign_in(client)
    _assert_rejected(_refresh(client, None))


def test_refresh_with_an_unknown_token_is_rejected(client: TestClient) -> None:
    _sign_in(client)
    _assert_rejected(_refresh(client, "not-a-token-we-ever-issued"))


def test_an_access_token_is_not_a_refresh_token(client: TestClient) -> None:
    access, _ = _sign_in(client)
    _assert_rejected(_refresh(client, access))


# --- reuse detection -----------------------------------------------------------


def _spent_seconds_ago(db_url: str, seconds: float) -> None:
    """Move every spent token's ``used_at`` to *seconds* in the past."""
    when = datetime.now(UTC) - timedelta(seconds=seconds)
    _run_sql(
        db_url,
        sa.update(RefreshToken)
        .where(RefreshToken.used_at.is_not(None))
        .values(used_at=when),
    )


def test_reusing_a_spent_refresh_token_revokes_the_whole_session(
    client: TestClient, db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    first_access, stolen = _sign_in(client)
    legit = _refresh(client, stolen)  # the owner rotates; `stolen` is now spent
    assert legit.status_code == 200
    successor = _cookie_value(legit)
    successor_access = legit.json()["access_token"]
    assert _me(client, successor_access) == 200
    _spent_seconds_ago(db_url, REFRESH_REUSE_INTERVAL_S + 1)

    _assert_rejected(_refresh(client, stolen))  # the copy is presented

    # Everything in the session is dead, the legitimate holder's too.
    _assert_rejected(_refresh(client, successor))
    assert _me(client, successor_access) == 401
    assert _me(client, first_access) == 401
    assert "refresh_token_reuse_detected" in capsys.readouterr().out


def test_reuse_revokes_only_the_session_it_happened_in(
    client: TestClient, db_url: str
) -> None:
    """Two sign-ins (two devices) are two sessions; one's theft is not the
    other's logout."""
    _, laptop = _sign_in(client)
    desk_access, desk = _sign_in(client, register=False)
    assert _refresh(client, laptop).status_code == 200
    _spent_seconds_ago(db_url, REFRESH_REUSE_INTERVAL_S + 1)
    _assert_rejected(_refresh(client, laptop))  # reuse on the laptop session
    assert _me(client, desk_access) == 200
    assert _refresh(client, desk).status_code == 200


# --- the reuse interval: an honest retry is answered, not punished ------------


def test_a_lost_rotation_response_can_be_retried(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The server spent T1 and issued T2, and the client never saw T2 (a lid
    closed, a proxy 502). Its retry with T1 renews from T2 instead of ending
    the session."""
    _, t1 = _sign_in(client)
    lost = _refresh(client, t1)
    assert lost.status_code == 200  # ...and its Set-Cookie never arrives

    retry = _refresh(client, t1)
    assert retry.status_code == 200, retry.text
    t3 = _cookie_value(retry)
    assert t3 not in (t1, _cookie_value(lost))
    assert _me(client, retry.json()["access_token"]) == 200
    assert _refresh(client, t3).status_code == 200  # the chain goes on
    assert "refresh_token_reuse_detected" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("seconds_ago", "answered"),
    [(REFRESH_REUSE_INTERVAL_S - 1, True), (REFRESH_REUSE_INTERVAL_S + 1, False)],
)
def test_the_reuse_interval_boundary(
    client: TestClient, db_url: str, seconds_ago: int, answered: bool
) -> None:
    _, t1 = _sign_in(client)
    assert _refresh(client, t1).status_code == 200
    _spent_seconds_ago(db_url, seconds_ago)
    retry = _refresh(client, t1)
    if answered:
        assert retry.status_code == 200, retry.text
    else:
        _assert_rejected(retry)
        assert _scalar(db_url, sa.select(AuthSession.revoked_at)) is not None


def test_inside_the_interval_a_used_successor_still_means_theft(
    client: TestClient, db_url: str
) -> None:
    """T1 -> T2 -> T3: the owner HAS used T2, so T1 coming back is not a lost
    response, it is a second holder. Revoked, even seconds later."""
    _, t1 = _sign_in(client)
    t2 = _cookie_value(_refresh(client, t1))
    assert _refresh(client, t2).status_code == 200
    _assert_rejected(_refresh(client, t1))
    assert _scalar(db_url, sa.select(AuthSession.revoked_at)) is not None


# --- identity: a shared browser never renews one user into another ------------

OTHER_EMAIL = "dave@example.com"


def test_refresh_refuses_a_tab_of_one_user_with_another_users_cookie(
    client: TestClient,
) -> None:
    """X's tab (bearer X) meets the cookie Y set by signing in last: refused,
    and Y's cookie is neither spent nor cleared."""
    x_access, _ = _sign_in(client)
    y_access, y_cookie = _sign_in(client, email=OTHER_EMAIL)

    response = _refresh(client, y_cookie, bearer=x_access)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_mismatch"
    assert _refresh_cookie_headers(response) == []  # Y's cookie left as it was

    # Y's own tab renews with that same, unspent cookie.
    renewed = _refresh(client, y_cookie, bearer=y_access)
    assert renewed.status_code == 200
    assert renewed.json()["user"]["email"] == OTHER_EMAIL


def test_an_expired_bearer_still_names_its_user(client: TestClient) -> None:
    """The tab asking for renewal holds an EXPIRED token by definition; its
    signature still says whose it is."""
    x_access, _ = _sign_in(client)
    _, y_cookie = _sign_in(client, email=OTHER_EMAIL)
    claims = _claims(x_access)
    config = AuthConfig(jwt_secret=TEST_JWT_SECRET, token_ttl_s=TOKEN_TTL_S)
    expired = create_access_token(
        uuid.UUID(claims["sub"]),
        uuid.UUID(claims["sid"]),
        config,
        now=datetime.now(UTC) - timedelta(seconds=TOKEN_TTL_S + 60),
    ).token
    assert _me(client, expired) == 401  # really expired
    response = _refresh(client, y_cookie, bearer=expired)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_mismatch"


def test_an_unverifiable_bearer_claims_nothing(client: TestClient) -> None:
    """A forged or garbled bearer is ignored (it cannot vouch for anyone), so
    the cookie alone decides, exactly as with no bearer at all."""
    _, cookie = _sign_in(client)
    attacker = AuthConfig(
        jwt_secret="attacker-controlled-secret-0123456789", token_ttl_s=3600
    )
    forged = create_access_token(uuid.uuid4(), uuid.uuid4(), attacker).token
    assert _refresh(client, cookie, bearer=forged).status_code == 200


def test_the_same_user_in_another_session_may_renew(client: TestClient) -> None:
    """Signing in again in another tab replaces the cookie; the older tab of the
    SAME person renews into the newer session rather than being thrown out."""
    first_access, _ = _sign_in(client)
    _, second_cookie = _sign_in(client, register=False)
    response = _refresh(client, second_cookie, bearer=first_access)
    assert response.status_code == 200
    renewed = _claims(response.json()["access_token"])
    assert renewed["sub"] == _claims(first_access)["sub"]


def test_logout_from_one_users_tab_leaves_another_users_cookie_alone(
    client: TestClient,
) -> None:
    x_access, _ = _sign_in(client)
    y_access, y_cookie = _sign_in(client, email=OTHER_EMAIL)
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {x_access}",
            "Cookie": f"{REFRESH_COOKIE_NAME}={y_cookie}",
        },
    )
    assert response.status_code == 204
    assert _refresh_cookie_headers(response) == []
    assert _me(client, x_access) == 401  # X is signed out
    assert _me(client, y_access) == 200  # Y is not
    assert _refresh(client, y_cookie, bearer=y_access).status_code == 200


# --- revocation (logout) ---------------------------------------------------------


def test_logout_revokes_the_refresh_chain_and_the_access_token(
    client: TestClient,
) -> None:
    access, cookie = _sign_in(client)
    assert _me(client, access) == 200
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"{REFRESH_COOKIE_NAME}={cookie}"},
    )
    assert response.status_code == 204
    cleared = _set_cookie(response)[REFRESH_COOKIE_NAME]
    assert cleared.value == "" and cleared["max-age"] == "0"
    assert cleared["path"] == REFRESH_COOKIE_PATH
    _assert_rejected(_refresh(client, cookie))
    # The access token dies with its session, not an hour later at `exp`.
    assert _me(client, access) == 401


def test_logout_by_bearer_alone_revokes_the_session(client: TestClient) -> None:
    """A client that ignores cookies (loft-script) can still end its session."""
    access, cookie = _sign_in(client)
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 204
    assert _me(client, access) == 401
    _assert_rejected(_refresh(client, cookie))


def test_logout_with_nothing_is_a_quiet_204(client: TestClient) -> None:
    client.cookies.clear()
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Cookie": f"{REFRESH_COOKIE_NAME}=garbage",
            "Authorization": "Bearer not.a.jwt",
        },
    )
    assert response.status_code == 204


def test_an_access_token_without_a_session_claim_is_rejected(
    client: TestClient,
) -> None:
    """Tokens minted before sessions existed carry no ``sid``: fail closed."""
    access, _ = _sign_in(client)
    claims = _claims(access)
    legacy = pyjwt.encode(  # pyright: ignore[reportUnknownMemberType]
        {"sub": claims["sub"], "iat": claims["iat"], "exp": claims["exp"]},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    assert _me(client, legacy) == 401


def test_a_token_naming_another_users_session_is_rejected(
    client: TestClient,
) -> None:
    access, _ = _sign_in(client)
    config = AuthConfig(jwt_secret=TEST_JWT_SECRET, token_ttl_s=TOKEN_TTL_S)
    mismatched = create_access_token(
        uuid.uuid4(), uuid.UUID(_claims(access)["sid"]), config
    ).token
    assert _me(client, mismatched) == 401


# --- expiry -------------------------------------------------------------------------


def test_an_idle_expired_refresh_token_is_rejected(
    client: TestClient, db_url: str
) -> None:
    _, cookie = _sign_in(client)
    past = datetime.now(UTC) - timedelta(seconds=1)
    _run_sql(db_url, sa.update(RefreshToken).values(expires_at=past))
    _assert_rejected(_refresh(client, cookie))


def test_the_absolute_bound_ends_refresh_and_access(
    client: TestClient, db_url: str
) -> None:
    access, cookie = _sign_in(client)
    past = datetime.now(UTC) - timedelta(seconds=1)
    _run_sql(db_url, sa.update(AuthSession).values(expires_at=past))
    _assert_rejected(_refresh(client, cookie))
    assert _me(client, access) == 401


def test_no_refresh_extends_a_session_past_its_absolute_bound(
    client: TestClient, db_url: str
) -> None:
    """Near the end of a session the cookie and the access token both shrink
    to fit it: a sliding window cannot slide past the wall."""
    _, cookie = _sign_in(client)
    remaining_s = 120  # < TOKEN_TTL_S and < IDLE_TTL_S
    end = datetime.now(UTC) + timedelta(seconds=remaining_s)
    _run_sql(db_url, sa.update(AuthSession).values(expires_at=end))
    response = _refresh(client, cookie)
    assert response.status_code == 200, response.text
    assert int(_set_cookie(response)[REFRESH_COOKIE_NAME]["max-age"]) <= remaining_s
    assert response.json()["expires_in"] <= remaining_s
    assert _claims(response.json()["access_token"])["exp"] <= int(end.timestamp())


def test_refresh_expiry_slides_but_is_capped() -> None:
    config = AuthConfig(
        jwt_secret=TEST_JWT_SECRET,
        token_ttl_s=TOKEN_TTL_S,
        session_idle_ttl_s=IDLE_TTL_S,
        session_max_age_s=MAX_AGE_S,
    )
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    far = now + timedelta(days=30)
    assert refresh_expiry(now, far, config) == now + timedelta(seconds=IDLE_TTL_S)
    near = now + timedelta(minutes=5)
    assert refresh_expiry(now, near, config) == near
    # Naive (SQLite) and aware (Postgres) session bounds compare the same.
    assert refresh_expiry(now, near.replace(tzinfo=None), config) == near


def test_expired_sessions_are_pruned_at_the_next_sign_in(
    client: TestClient, db_url: str
) -> None:
    _sign_in(client)
    past = datetime.now(UTC) - timedelta(seconds=1)
    _run_sql(db_url, sa.update(AuthSession).values(expires_at=past))
    _sign_in(client, register=False)
    assert _scalar(db_url, sa.select(sa.func.count()).select_from(AuthSession)) == 1
    assert _scalar(db_url, sa.select(sa.func.count()).select_from(RefreshToken)) == 1


# --- housekeeping and abuse bounds (review N1, N5) -----------------------------


class _CountingLimiter(RateLimiter):
    """An in-memory limiter: counts every check, refuses past *allow*."""

    def __init__(self, allow: int) -> None:  # no Redis behind it
        self.allow = allow
        self.calls: list[tuple[str, str]] = []

    async def check(self, identity: str, *, scope: str = "compute") -> None:
        self.calls.append((identity, scope))
        if len(self.calls) > self.allow:
            raise RateLimitExceededError("Slow down.", retry_after_s=7)


def test_login_and_refresh_are_rate_limited(db_url: str) -> None:
    limiter = _CountingLimiter(allow=2)
    app = build_app(_settings(db_url), rate_limiter=limiter)
    with TestClient(app, base_url="https://testserver") as limited_client:
        _, cookie = _sign_in(limited_client)  # register: not limited here
        assert limiter.calls == []
        cookie = _cookie_value(_refresh(limited_client, cookie))  # 1
        _sign_in(limited_client, register=False)  # 2: login
        refused = _refresh(limited_client, cookie)  # 3: over budget
        assert refused.status_code == 429
        assert refused.headers["Retry-After"] == "7"
        # Refused BEFORE the handler ran: nothing spent, nothing cleared, so
        # the same cookie works once the budget allows.
        assert _refresh_cookie_headers(refused) == []
        limiter.allow = 10
        assert _refresh(limited_client, cookie).status_code == 200
    assert limiter.calls == [("testclient", "auth")] * 4


def test_refresh_prunes_tokens_spent_longer_ago_than_the_idle_window(
    client: TestClient, db_url: str
) -> None:
    _, cookie = _sign_in(client)
    for _ in range(3):
        cookie = _cookie_value(_refresh(client, cookie))
    count = sa.select(sa.func.count()).select_from(RefreshToken)
    assert _scalar(db_url, count) == 4  # three spent + the live one
    _spent_seconds_ago(db_url, IDLE_TTL_S + 1)

    assert _refresh(client, cookie).status_code == 200
    # The three long-dead rows are gone; the one just spent and its successor
    # remain (reuse detection for them is intact).
    assert _scalar(db_url, count) == 2


def test_the_cookie_path_covers_every_route_that_reads_the_cookie() -> None:
    """Derived from the router: the cookie is sent to refresh and logout,
    and to nothing outside /api/v1/auth."""
    assert REFRESH_COOKIE_PATH == "/api/v1/auth"
    for path in ("/refresh", "/logout"):
        assert f"{auth_router.prefix}{path}".startswith(f"{REFRESH_COOKIE_PATH}/")


# --- configuration --------------------------------------------------------------


class TestLifetimeConfig:
    def test_idle_window_shorter_than_the_access_token_refuses_to_boot(self) -> None:
        with pytest.raises(RuntimeError, match="SESSION_IDLE_TTL_S"):
            resolve_auth_config(
                loft_env="dev",
                jwt_secret=TEST_JWT_SECRET,
                token_ttl_s=3600,
                session_idle_ttl_s=600,
            )

    def test_max_age_shorter_than_the_idle_window_refuses_to_boot(self) -> None:
        with pytest.raises(RuntimeError, match="SESSION_MAX_AGE_S"):
            resolve_auth_config(
                loft_env="dev",
                jwt_secret=TEST_JWT_SECRET,
                token_ttl_s=60,
                session_idle_ttl_s=7200,
                session_max_age_s=3600,
            )

    def test_lifetimes_flow_from_settings(self, db_url: str) -> None:
        config = build_app(_settings(db_url)).state.auth_config
        assert (config.session_idle_ttl_s, config.session_max_age_s) == (
            IDLE_TTL_S,
            MAX_AGE_S,
        )
