"""Auth cryptography: argon2 password hashing, HS256 JWTs, secret posture.

Secret posture (documented honestly):

- ``LOFT_ENV`` is the ONE deployment-posture variable, owned by
  :mod:`py_kit.config` (:data:`py_kit.DEV_ENV` / :func:`py_kit.is_dev_env`)
  and shared with the datastore-credential guard on
  :class:`~py_kit.BaseServiceSettings` — the JWT rules below and that guard
  are deliberately the same policy, read from the same field.
  It has NO default. The dev fallback secret requires the exact,
  explicitly-set value ``LOFT_ENV=dev``: only then does an unset
  ``JWT_SECRET`` fall back to a fixed, publicly-known constant (so
  `just dev`/`just gen` work out of the box) — every dev token is therefore
  forgeable by anyone, which is fine for localhost and NOTHING else. A
  warning is logged whenever the fallback engages.
- With ``LOFT_ENV`` unset, or set to ANYTHING else (``production``,
  ``staging``, a typo…), an unset/empty/whitespace-only ``JWT_SECRET`` makes
  :func:`resolve_auth_config` raise, which :func:`gateway.main.build_app`
  calls first thing — the process refuses to boot. Fail-closed: an
  UNCONFIGURED deployment dies loudly instead of silently signing tokens
  with a repo-public secret, and misspelling the environment name cannot
  weaken a deployment either.
- The secret is ``.strip()``-ed before any check or use (a stray trailing
  newline from ``openssl rand -hex 32 >>`` must not silently change the
  signing key). A secret that is set but shorter than
  :data:`MIN_JWT_SECRET_LENGTH` after stripping is rejected in every
  environment (HS256 with a short secret is brute-forceable).

There is exactly one path to a usable secret — this module's
``resolve_auth_config`` — and routes read the result from ``app.state``,
which only ``build_app`` populates. No bypass exists to construct the app
with an unchecked secret (Next-Lane's fail-fast had one; ours is tested in
``tests/test_auth.py::TestStartupFailFast``).

Sessions and refresh (2026-09-24). A sign-in is a SESSION
(``gateway.db.AuthSession``), and the session is what lives for hours; the
access token is a short-lived view of it. The design, and why each piece is
there:

- **Two tokens.** The access token is the HS256 JWT above, sent as
  ``Authorization: Bearer`` (unchanged for every route and for loft-script).
  The refresh token is 256 random bits (:func:`new_refresh_token`), handed to
  the browser ONLY as an ``HttpOnly; Secure; SameSite=Strict`` cookie scoped
  to ``Path=/api/v1/auth``: script can never read it, it is never sent to any
  route but refresh/logout, and a cross-site page cannot make the browser
  send it at all. It is stored server-side as a SHA-256 digest only.
- **Rotation.** ``POST /auth/refresh`` spends the presented refresh token
  (``used_at`` is stamped by a conditional UPDATE, so two concurrent spends
  cannot both win) and issues a successor plus a fresh access token.
- **Reuse detection.** Presenting a refresh token that was ALREADY spent
  means two parties hold it, which is the signature of a copied token, so the
  whole session is revoked: thief and owner both lose it, and the owner signs
  in again. This is the refresh-rotation rule of the OAuth 2.0 Security BCP.
- **Revocation.** Access tokens carry ``sid`` (the session id), and
  :func:`gateway.auth.routes.get_current_user` re-checks the session on every
  request. Logout and reuse detection therefore end the access tokens too,
  not just the refresh chain. This closes the gap this module used to
  document ("a token stays valid until ``exp`` even after logout"). A token
  without ``sid`` (minted before this landed) is rejected: fail-closed, at the
  cost of one extra sign-in per user.
- **Bounded lifetime.** Each refresh token lives ``SESSION_IDLE_TTL_S``
  (sliding: every rotation restarts it), but never past the session's
  absolute ``expires_at`` = sign-in + ``SESSION_MAX_AGE_S``; access-token
  ``exp`` is capped by the same bound. No sequence of refreshes outlives it.

What is still NOT covered, stated plainly: tokens carry no ``aud``/``iss``
(single verifier today; required the day a second service verifies them). A
refresh token stolen and spent BEFORE its owner next refreshes buys the thief
the session until the owner's next refresh, which trips reuse detection and
ends it for both; the ``Secure``/``HttpOnly``/``SameSite`` cookie is what makes
stealing it hard in the first place.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from py_kit import DEV_ENV, get_logger, is_dev_env

_logger = get_logger("gateway.auth")

#: JWT signing algorithm — symmetric HS256; single-service verifier today.
JWT_ALGORITHM = "HS256"

#: Minimum length for an explicitly-configured JWT secret (bytes of entropy
#: matter, but length is the enforceable floor; `openssl rand -hex 32` → 64).
MIN_JWT_SECRET_LENGTH = 32

#: Dev-only fallback secret — PUBLIC by definition (it is in the repo).
#: Tokens signed with it are forgeable by anyone; see the module docstring.
DEV_JWT_SECRET = "loft-dev-only-jwt-secret-do-not-deploy-0000"


#: Default sliding window of a refresh token (24 h): a session survives a
#: closed laptop overnight, and every refresh restarts the window.
DEFAULT_SESSION_IDLE_TTL_S = 24 * 3600

#: Default absolute session lifetime (7 days): no chain of refreshes outlives
#: it, whatever the activity. A week of work, then one sign-in.
DEFAULT_SESSION_MAX_AGE_S = 7 * 24 * 3600


@dataclass(frozen=True)
class AuthConfig:
    """Resolved auth runtime config (secret validated, lifetimes in seconds)."""

    jwt_secret: str
    token_ttl_s: int
    session_idle_ttl_s: int = DEFAULT_SESSION_IDLE_TTL_S
    session_max_age_s: int = DEFAULT_SESSION_MAX_AGE_S


def _check_lifetimes(
    token_ttl_s: int, session_idle_ttl_s: int, session_max_age_s: int
) -> None:
    """Refuse lifetimes that are nonsensical or that silently undo refresh.

    An idle window shorter than the access token would expire the refresh
    token BEFORE the client needs it. That is the hard 1 h logout this design
    exists to remove, reintroduced by configuration and invisible until
    someone works past it, so it is a boot failure and not a warning.
    """
    if token_ttl_s <= 0:
        raise RuntimeError(f"JWT_TTL_S must be positive, got {token_ttl_s}")
    if session_idle_ttl_s < token_ttl_s:
        raise RuntimeError(
            f"SESSION_IDLE_TTL_S ({session_idle_ttl_s}) must be at least "
            f"JWT_TTL_S ({token_ttl_s}), or the refresh token expires before "
            "the access token it is meant to renew."
        )
    if session_max_age_s < session_idle_ttl_s:
        raise RuntimeError(
            f"SESSION_MAX_AGE_S ({session_max_age_s}) must be at least "
            f"SESSION_IDLE_TTL_S ({session_idle_ttl_s})."
        )


def resolve_auth_config(
    *,
    loft_env: str | None,
    jwt_secret: str | None,
    token_ttl_s: int,
    session_idle_ttl_s: int = DEFAULT_SESSION_IDLE_TTL_S,
    session_max_age_s: int = DEFAULT_SESSION_MAX_AGE_S,
) -> AuthConfig:
    """Validate the JWT secret posture; raise rather than boot weak.

    See the module docstring for the exact rules. Raises :class:`RuntimeError`
    (startup failure, never an HTTP response) so a misconfigured deployment
    dies loudly instead of serving forgeable tokens.
    """
    _check_lifetimes(token_ttl_s, session_idle_ttl_s, session_max_age_s)

    def config(secret: str) -> AuthConfig:
        return AuthConfig(
            jwt_secret=secret,
            token_ttl_s=token_ttl_s,
            session_idle_ttl_s=session_idle_ttl_s,
            session_max_age_s=session_max_age_s,
        )

    # ""/whitespace (e.g. `JWT_SECRET=` in compose, a stray newline) == unset;
    # the stripped value is also what gets used, so the checked secret and the
    # signing secret can never differ.
    secret = (jwt_secret or "").strip() or None
    if secret is None:
        if not is_dev_env(loft_env):
            raise RuntimeError(
                f"JWT_SECRET is required when LOFT_ENV={loft_env!r}. Either "
                "set a real secret (generate one with `openssl rand -hex 32`) "
                "or, for LOCAL DEV ONLY, opt into the forgeable fallback "
                f"explicitly with LOFT_ENV={DEV_ENV}."
            )
        _logger.warning(
            "jwt_dev_fallback_secret_in_use",
            hint="tokens are forgeable; set JWT_SECRET for anything non-local",
        )
        return config(DEV_JWT_SECRET)
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET is too short ({len(secret)} < {MIN_JWT_SECRET_LENGTH} "
            "characters); generate one with `openssl rand -hex 32`."
        )
    return config(secret)


# --- password hashing (argon2id, library defaults) --------------------------
#
# Everything here is CPU-bound by design (tens of milliseconds per call —
# that's the point). Async routes must offload these to a worker
# thread (`anyio.to_thread.run_sync`) or every concurrent login/register
# stalls the whole event loop for the duration of a hash.

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash *password* with argon2id (salted; safe to store/compare)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True iff *password* matches *password_hash*; never raises on mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates current argon2 parameters."""
    return _hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A throwaway hash to verify against when the email is unknown.

    Login burns the same argon2 verification cost whether or not the account
    exists, so response timing does not become an email-enumeration oracle.
    (Register necessarily reveals existence via 409 — a standard, accepted
    tradeoff; login should not add a second, quieter oracle.)
    """
    return hash_password(uuid.uuid4().hex)


def burn_dummy_verification(password: str) -> None:
    """Verify *password* against the throwaway hash; discard the result.

    One synchronous callable so login's unknown-email branch can offload the
    WHOLE burn — including minting the cached dummy hash on first use — to
    the same worker-thread path as a real verification (timing parity).
    """
    verify_password(dummy_password_hash(), password)


# --- JWT access tokens -------------------------------------------------------


class TokenError(Exception):
    """The presented token is invalid: expired, tampered, or malformed."""


@dataclass(frozen=True)
class AccessToken:
    """A minted access token and the lifetime the client should plan on."""

    token: str
    #: Seconds from issue to ``exp``: the ``expires_in`` of the token response.
    expires_in: int


@dataclass(frozen=True)
class AccessClaims:
    """The verified identity an access token asserts."""

    user_id: uuid.UUID
    session_id: uuid.UUID


def create_access_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    config: AuthConfig,
    *,
    now: datetime | None = None,
    not_after: datetime | None = None,
) -> AccessToken:
    """Mint an HS256 access token for *user_id* inside session *session_id*.

    ``exp`` is ``now + token_ttl_s``, capped at *not_after* (the session's
    absolute bound), so no access token outlives the session that minted it.
    ``now`` is injectable for tests.
    """
    issued_at = int((now or datetime.now(UTC)).timestamp())
    expires_at = issued_at + config.token_ttl_s
    if not_after is not None:
        expires_at = min(expires_at, int(as_utc(not_after).timestamp()))
    claims = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": issued_at,
        "exp": expires_at,
    }
    # PyJWT's `key` parameter is typed with a partially-unknown PyJWK union
    # upstream (hence the suppression); the str overload is what we use.
    token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        claims, config.jwt_secret, algorithm=JWT_ALGORITHM
    )
    return AccessToken(token=token, expires_in=max(0, expires_at - issued_at))


def decode_access_token(token: str, config: AuthConfig) -> AccessClaims:
    """Verify *token* and return the user and session it asserts.

    Pins the algorithm list (``alg`` confusion / ``none`` rejected by PyJWT),
    requires ``exp`` + ``sub`` + ``sid``. Raises :class:`TokenError` on any
    defect — callers translate to a generic 401 without detailing which check
    failed. Whether the session is still LIVE is the caller's check (it needs
    the database): see :func:`gateway.auth.routes.get_current_user`.
    """
    try:
        claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            config.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "sid"]},
        )
        return AccessClaims(
            user_id=uuid.UUID(str(claims["sub"])),
            session_id=uuid.UUID(str(claims["sid"])),
        )
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc
    except ValueError as exc:  # sub/sid present but not a UUID
        raise TokenError("invalid subject") from exc


# --- refresh tokens ------------------------------------------------------------

#: Random bytes in a refresh token: 256 bits (``token_urlsafe`` -> 43 chars).
REFRESH_TOKEN_BYTES = 32


def new_refresh_token() -> str:
    """A fresh, unguessable refresh token: the cookie value, never stored."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """The at-rest form of *token*: its SHA-256 hex digest.

    Unsalted and fast on purpose, unlike passwords: the input is 256 random
    bits, so there is no dictionary to run and the digest cannot be reversed.
    Lookup is by this digest (unique index), so it must be deterministic.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    """Normalise a timestamp to aware UTC.

    SQLite (the unit-test dialect) returns ``DateTime(timezone=True)`` values
    NAIVE and Postgres returns them aware. Every expiry comparison goes through
    here, so the security checks behave identically on both.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def session_expiry(now: datetime, config: AuthConfig) -> datetime:
    """The absolute end of a session signed in at *now*."""
    return now + timedelta(seconds=config.session_max_age_s)


def refresh_expiry(
    now: datetime, session_expires_at: datetime, config: AuthConfig
) -> datetime:
    """When a refresh token issued at *now* stops working: sliding, capped."""
    return min(
        now + timedelta(seconds=config.session_idle_ttl_s),
        as_utc(session_expires_at),
    )
