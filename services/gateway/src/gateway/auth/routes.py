"""``/api/v1/auth/*`` routes + the protected-route dependency.

Security invariants (asserted by tests/test_auth.py and
tests/test_auth_sessions.py):

- Plaintext passwords and argon2 hashes never appear in log lines, error
  envelopes, or response bodies — logs carry user ids only.
- Login failures are uniform: unknown email and wrong password return the
  same 401 body, and both burn one argon2 verification so timing does not
  enumerate accounts.
- Duplicate email is enforced by the DB unique constraint (race-free), not a
  read-then-write check.
- Argon2 work (hash/verify — CPU-bound on purpose) always runs in a worker
  thread via ``anyio.to_thread.run_sync``, never on the event loop; the
  anti-enumeration dummy burn takes the same offloaded path.
- Sessions (see :mod:`gateway.auth.security` for the design): every sign-in
  opens an :class:`~gateway.db.AuthSession`; the refresh token travels ONLY in
  the ``HttpOnly; Secure; SameSite=Strict`` cookie and is never in a body;
  a refresh token is spent exactly once; a second spend revokes the session;
  every access token is re-checked against its live session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

import anyio.to_thread
from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loft_wire.auth import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from py_kit import (
    ConflictError,
    UnauthorizedError,
    ValidationApiError,
    get_logger,
)
from py_kit.db import SessionDep
from py_kit.ratelimit import RateLimiter
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.auth.security import (
    REFRESH_REUSE_INTERVAL_S,
    AccessClaims,
    AuthConfig,
    TokenError,
    as_utc,
    burn_dummy_verification,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    password_needs_rehash,
    refresh_expiry,
    session_expiry,
    verify_password,
)
from gateway.db import AuthSession, RefreshToken, User

_logger = get_logger("gateway.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

#: One message for every credential failure — never say which part was wrong.
_INVALID_CREDENTIALS = "Invalid email or password."

#: One message for every token defect — never detail expired vs. tampered.
_INVALID_TOKEN = "Invalid or expired token."

#: The refresh cookie belongs to a different user than the bearer asking.
_SESSION_MISMATCH = "This browser is signed in as a different account now."

#: The refresh cookie. Its name is not a secret; its value is.
REFRESH_COOKIE_NAME = "loft_refresh"

#: The cookie is sent to the auth routes and nowhere else: a proxied feature
#: call, a mesh fetch, an upstream log line never carries it. Derived from the
#: router, so moving the routes cannot strand the cookie on a dead path.
REFRESH_COOKIE_PATH = router.prefix


def get_auth_config(request: Request) -> AuthConfig:
    """The resolved auth config — set exclusively by ``build_app``."""
    config: AuthConfig = request.app.state.auth_config
    return config


AuthConfigDep = Annotated[AuthConfig, Depends(get_auth_config)]

_bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="Access token from `/api/v1/auth/register` or `/api/v1/auth/login`.",
)

BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
]

RefreshCookie = Annotated[
    str | None,
    Cookie(
        alias=REFRESH_COOKIE_NAME,
        description=(
            "Refresh token, set by register/login/refresh as an HttpOnly, "
            "Secure, SameSite=Strict cookie. Browsers send it automatically; "
            "it is never readable by script and never appears in a body."
        ),
    ),
]


def _session_is_live(auth_session: AuthSession, now: datetime) -> bool:
    """Not revoked and inside its absolute lifetime."""
    return auth_session.revoked_at is None and as_utc(auth_session.expires_at) > now


async def get_current_user(
    credentials: BearerCredentials,
    config: AuthConfigDep,
    session: SessionDep,
) -> User:
    """Protected-route dependency: resolve the bearer token to a live user.

    401 (generic, with ``WWW-Authenticate: Bearer``) on a missing header, any
    token defect, a subject that no longer exists, or a session that was
    revoked (logout, refresh reuse) or has outlived its absolute bound. The
    session check is what makes logout real for access tokens, not only for
    the refresh chain.
    """
    if credentials is None:
        raise UnauthorizedError("Not authenticated.")
    try:
        claims = decode_access_token(credentials.credentials, config)
    except TokenError:
        # Generic on purpose; the precise defect stays server-side.
        raise UnauthorizedError(_INVALID_TOKEN, code="invalid_token") from None
    row = (
        (
            await session.execute(
                select(User, AuthSession)
                .join(AuthSession, AuthSession.user_id == User.id)
                .where(User.id == claims.user_id, AuthSession.id == claims.session_id)
            )
        )
        .tuples()
        .one_or_none()
    )
    if row is None:
        raise UnauthorizedError(_INVALID_TOKEN, code="invalid_token")
    user, auth_session = row
    if not _session_is_live(auth_session, datetime.now(UTC)):
        raise UnauthorizedError(_INVALID_TOKEN, code="invalid_token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def check_password_cap(password: str) -> None:
    """Enforce the length cap WITHOUT echoing the value (see schemas.py).

    Applied wherever a password reaches argon2 — register AND login — so an
    oversized payload can never buy a giant hash computation (CPU DoS).
    """
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationApiError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters.",
            details={"field": "password"},
        )


def check_password_policy(password: str) -> None:
    """Enforce the full length policy (floor + cap) for new passwords."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationApiError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters.",
            details={"field": "password"},
        )
    check_password_cap(password)


def _normalize_email(email: str) -> str:
    """Lowercase the whole address — one account per email, case-insensitive."""
    return email.lower()


# --- the refresh cookie -------------------------------------------------------


def _set_refresh_cookie(
    response: Response, token: str, expires_at: datetime, now: datetime
) -> None:
    """Hand the browser its refresh token. The ONLY way the token leaves us."""
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=max(0, int((expires_at - now).total_seconds())),
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Tell the browser to drop the refresh cookie (same attributes, expired)."""
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _refresh_rejected() -> UnauthorizedError:
    """The one refresh failure: generic 401 that also clears the cookie.

    Error envelopes are rendered as a fresh response, so the cookie deletion
    has to travel as a header on the error itself.
    """
    carrier = Response()
    _clear_refresh_cookie(carrier)
    return UnauthorizedError(
        _INVALID_TOKEN,
        code="invalid_token",
        headers={
            "WWW-Authenticate": "Bearer",
            "Set-Cookie": carrier.headers["set-cookie"],
        },
    )


# --- sessions -----------------------------------------------------------------


def _bearer_identity(
    credentials: HTTPAuthorizationCredentials | None, config: AuthConfig
) -> AccessClaims | None:
    """Who a bearer token was issued to, expired or not; None if unverifiable."""
    if credentials is None:
        return None
    try:
        return decode_access_token(credentials.credentials, config, verify_exp=False)
    except TokenError:
        return None


async def _session_of_refresh_token(
    session: AsyncSession, refresh_token: str
) -> AuthSession | None:
    """The session a presented refresh token belongs to (spent or not)."""
    token_row = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token)
            )
        )
    ).scalar_one_or_none()
    if token_row is None:
        return None
    return await session.get(AuthSession, token_row.session_id)


async def _issue_refresh_token(
    session: AsyncSession,
    auth_session: AuthSession,
    config: AuthConfig,
    now: datetime,
) -> tuple[str, datetime, uuid.UUID]:
    """Add a fresh refresh token to *auth_session*; plaintext, expiry, row id."""
    plaintext = new_refresh_token()
    expires_at = refresh_expiry(now, auth_session.expires_at, config)
    row_id = uuid.uuid4()
    session.add(
        RefreshToken(
            id=row_id,
            session_id=auth_session.id,
            token_hash=hash_refresh_token(plaintext),
            created_at=now,
            expires_at=expires_at,
        )
    )
    return plaintext, expires_at, row_id


async def _conditional_spend(
    session: AsyncSession, token_id: uuid.UUID, now: datetime
) -> bool:
    """Stamp ``used_at`` iff the token is still unspent; True if WE spent it.

    A conditional UPDATE, so of two concurrent presentations of one token
    exactly one wins. An UPDATE yields a CursorResult (rowcount); `execute` is
    typed as the general Result, hence the cast.
    """
    spent = cast(
        "CursorResult[Any]",
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.used_at.is_(None))
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        ),
    )
    return spent.rowcount == 1


async def _spend(
    session: AsyncSession, token_row: RefreshToken, now: datetime
) -> RefreshToken | None:
    """Spend *token_row*, or its successor inside the reuse interval.

    Returns the row that was actually spent, or None for REUSE (the caller
    revokes). The retry case: *token_row* was spent less than
    REFRESH_REUSE_INTERVAL_S ago and the token issued in its place has never
    been used, i.e. the client never received it. Spending that successor
    renews the session exactly as the lost response would have.
    """
    if await _conditional_spend(session, token_row.id, now):
        return token_row
    await session.refresh(token_row)  # the winner's commit: used_at, successor
    if token_row.used_at is None or token_row.replaced_by_id is None:
        return None
    if now - as_utc(token_row.used_at) > timedelta(seconds=REFRESH_REUSE_INTERVAL_S):
        return None
    successor = await session.get(RefreshToken, token_row.replaced_by_id)
    if successor is None or not await _conditional_spend(session, successor.id, now):
        return None
    _logger.info(
        "refresh_retried_within_reuse_interval",
        session_id=str(token_row.session_id),
    )
    return successor


def _token_response(
    user: User, auth_session: AuthSession, config: AuthConfig, now: datetime
) -> AuthTokenResponse:
    access = create_access_token(
        user.id, auth_session.id, config, now=now, not_after=auth_session.expires_at
    )
    return AuthTokenResponse(
        user=UserResponse.model_validate(user),
        access_token=access.token,
        expires_in=access.expires_in,
    )


async def _start_session(
    session: AsyncSession, user: User, config: AuthConfig, response: Response
) -> AuthTokenResponse:
    """Open a session for *user*: the access token in the body, refresh in a cookie.

    Also prunes the user's sessions that have passed their absolute bound —
    their rows (and their spent refresh tokens, by cascade) can never
    authenticate anything again, so this keeps the tables bounded per user
    without a background job.
    """
    now = datetime.now(UTC)
    await session.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.expires_at < now
        )
    )
    auth_session = AuthSession(
        user_id=user.id, created_at=now, expires_at=session_expiry(now, config)
    )
    session.add(auth_session)
    await session.flush()  # assigns auth_session.id for the token FK
    plaintext, refresh_expires_at, _ = await _issue_refresh_token(
        session, auth_session, config, now
    )
    await session.commit()
    _set_refresh_cookie(response, plaintext, refresh_expires_at, now)
    return _token_response(user, auth_session, config, now)


async def _revoke(session: AsyncSession, auth_session: AuthSession) -> None:
    """End *auth_session* and everything minted from it (idempotent)."""
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
    await session.commit()


# --- routes -------------------------------------------------------------------


async def limit_auth_attempts(request: Request, config: AuthConfigDep) -> None:
    """Rate-limit the unauthenticated auth routes per client address.

    The same py-kit limiter as the compute routes, in its own ``auth`` scope
    and with its own budget (``AUTH_RATE_LIMIT_REQUESTS``, see
    :data:`gateway.auth.security.DEFAULT_AUTH_RATE_LIMIT_REQUESTS`). It
    cannot be keyed on a user, because there is none yet; it is keyed on the
    connecting address. Behind a reverse proxy that is the proxy's, so all
    clients share one bucket: conservative (it cannot be spoofed with a
    header), and a 429 on refresh is "try again", never a sign-out
    (apps/web/src/auth/refresh.ts). No-op when rate limiting is off.

    The limiter is read from ``app.state`` directly rather than through
    ``gateway.ratelimit.get_rate_limiter``: that module imports
    ``gateway.auth`` for ``CurrentUser``, so importing it here would be a
    cycle.
    """
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    client = request.client.host if request.client is not None else "unknown"
    await limiter.check(client, scope="auth", limit=config.rate_limit_requests)


AUTH_RATE_LIMIT = Depends(limit_auth_attempts)


@router.post(
    "/register", status_code=status.HTTP_201_CREATED, dependencies=[AUTH_RATE_LIMIT]
)
async def register(
    request: RegisterRequest,
    config: AuthConfigDep,
    session: SessionDep,
    response: Response,
) -> AuthTokenResponse:
    """Create an account and sign it in (201, envelope 409 on duplicate)."""
    password = request.password.get_secret_value()
    check_password_policy(password)
    user = User(
        email=_normalize_email(request.email),
        # Offloaded: argon2 is CPU-bound and must not stall the event loop.
        password_hash=await anyio.to_thread.run_sync(hash_password, password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "An account with this email already exists.", code="email_taken"
        ) from None
    _logger.info("user_registered", user_id=str(user.id))
    return await _start_session(session, user, config, response)


@router.post("/login", dependencies=[AUTH_RATE_LIMIT])
async def login(
    request: LoginRequest,
    config: AuthConfigDep,
    session: SessionDep,
    response: Response,
) -> AuthTokenResponse:
    """Exchange email + password for an access token (uniform 401 on failure).

    Also sets the refresh cookie that ``/auth/refresh`` renews the session
    with; a client that ignores cookies (loft-script) simply signs in again
    when its access token expires.
    """
    password = request.password.get_secret_value()
    check_password_cap(password)  # same DoS guard as register (cap only)
    result = await session.execute(
        select(User).where(User.email == _normalize_email(request.email))
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Burn the same argon2 cost as a real check (anti-enumeration
        # timing), on the same offloaded worker-thread path.
        await anyio.to_thread.run_sync(burn_dummy_verification, password)
        raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")
    if not await anyio.to_thread.run_sync(
        verify_password, user.password_hash, password
    ):
        raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")
    if password_needs_rehash(user.password_hash):
        # Transparent parameter upgrade on successful login (offloaded).
        user.password_hash = await anyio.to_thread.run_sync(hash_password, password)
        await session.commit()
    _logger.info("user_logged_in", user_id=str(user.id))
    return await _start_session(session, user, config, response)


@router.post("/refresh", dependencies=[AUTH_RATE_LIMIT])
async def refresh(
    config: AuthConfigDep,
    session: SessionDep,
    response: Response,
    credentials: BearerCredentials,
    refresh_token: RefreshCookie = None,
) -> AuthTokenResponse:
    """Rotate the refresh cookie and mint a fresh access token.

    The presented refresh token is spent (single use) and a successor is set
    in its place. Every failure is the same generic 401 ``invalid_token`` and
    clears the cookie: a missing or unknown token, an expired one, a session
    that was revoked or has reached its absolute bound — and REUSE, a token
    that was already spent, which additionally revokes the whole session
    because two parties holding one token means it was copied.
    """
    if not refresh_token:
        raise _refresh_rejected()
    now = datetime.now(UTC)
    token_row = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token)
            )
        )
    ).scalar_one_or_none()
    if token_row is None:
        raise _refresh_rejected()
    auth_session = await session.get(AuthSession, token_row.session_id)
    if auth_session is None or not _session_is_live(auth_session, now):
        raise _refresh_rejected()
    # Whose renewal is this? On a shared browser the cookie belongs to whoever
    # signed in LAST, and an earlier user's tab must not be renewed into it:
    # it would carry that user's screen, and resend that user's failed write,
    # as somebody else. A bearer (expired is fine; forged is not) naming a
    # different user is refused WITHOUT spending or clearing the cookie, which
    # stays valid for its owner. A missing or unverifiable bearer adds no
    # claim either way.
    bearer = _bearer_identity(credentials, config)
    if bearer is not None and bearer.user_id != auth_session.user_id:
        _logger.warning(
            "refresh_identity_mismatch",
            user_id=str(auth_session.user_id),
            bearer_user_id=str(bearer.user_id),
        )
        raise UnauthorizedError(_SESSION_MISMATCH, code="session_mismatch")
    spent_row = await _spend(session, token_row, now)
    if spent_row is None:
        await _revoke(session, auth_session)
        _logger.warning(
            "refresh_token_reuse_detected",
            user_id=str(auth_session.user_id),
            session_id=str(auth_session.id),
        )
        raise _refresh_rejected()
    if as_utc(spent_row.expires_at) <= now:
        await session.commit()  # keep it spent; it is dead either way
        raise _refresh_rejected()
    user = await session.get(User, auth_session.user_id)
    if user is None:  # pragma: no cover - the FK cascade removes the session
        raise _refresh_rejected()
    plaintext, refresh_expires_at, successor_id = await _issue_refresh_token(
        session, auth_session, config, now
    )
    await session.flush()  # the successor row exists before it is linked
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == spent_row.id)
        .values(replaced_by_id=successor_id)
        .execution_options(synchronize_session=False)
    )
    # Prune this session's tokens spent longer ago than the idle window. Such
    # a token expired before it could be spent again anyway (it lived at most
    # the idle window from issue), so presenting it again is refused whether
    # or not the row exists; only the reuse ALARM for it is given up. A
    # week-long session refreshing hourly otherwise keeps ~170 dead rows.
    await session.execute(
        delete(RefreshToken)
        .where(
            RefreshToken.session_id == auth_session.id,
            RefreshToken.used_at.is_not(None),
            RefreshToken.used_at < now - timedelta(seconds=config.session_idle_ttl_s),
        )
        # Rows loaded in this session (naive on SQLite) are not re-evaluated
        # in Python against an aware `now`; the database decides.
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    _set_refresh_cookie(response, plaintext, refresh_expires_at, now)
    _logger.info(
        "auth_session_refreshed",
        user_id=str(user.id),
        session_id=str(auth_session.id),
    )
    return _token_response(user, auth_session, config, now)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    config: AuthConfigDep,
    session: SessionDep,
    response: Response,
    credentials: BearerCredentials,
    refresh_token: RefreshCookie = None,
) -> None:
    """End the session: revoke it server-side and clear the refresh cookie.

    The session is found from the bearer token (signature verified, expiry
    not required: an expired token still names its own session), from the
    refresh cookie, or both. Revocation ends the refresh chain AND every
    access token minted from it (see :func:`get_current_user`). When the
    bearer and the cookie belong to DIFFERENT users, only the bearer's session
    ends and the cookie is left alone — it is someone else's sign-in. Always
    204 — idempotent, and it says nothing about whether the credentials were
    any good.
    """
    bearer = _bearer_identity(credentials, config)
    targets: list[AuthSession] = []
    if bearer is not None:
        own = await session.get(AuthSession, bearer.session_id)
        if own is not None and own.user_id == bearer.user_id:
            targets.append(own)
    cookie_is_someone_elses = False
    if refresh_token:
        cookie_session = await _session_of_refresh_token(session, refresh_token)
        if cookie_session is not None:
            # A shared browser: the cookie can belong to whoever signed in
            # last, while this tab's bearer is an earlier user's. Signing the
            # earlier user out must not sign the later one out.
            if bearer is not None and cookie_session.user_id != bearer.user_id:
                cookie_is_someone_elses = True
            else:
                targets.append(cookie_session)
    for auth_session in {target.id: target for target in targets}.values():
        await _revoke(session, auth_session)
        _logger.info(
            "auth_session_revoked",
            user_id=str(auth_session.user_id),
            session_id=str(auth_session.id),
        )
    if not cookie_is_someone_elses:
        _clear_refresh_cookie(response)


@router.get("/me")
async def me(user: CurrentUser) -> UserResponse:
    """The authenticated account (protected: bearer token required)."""
    return UserResponse.model_validate(user)
