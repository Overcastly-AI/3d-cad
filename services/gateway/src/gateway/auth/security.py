"""Auth cryptography: argon2 password hashing, HS256 JWTs, secret posture.

Secret posture (documented honestly):

- ``LOFT_ENV`` defaults to ``"dev"``. In dev only, an unset ``JWT_SECRET``
  falls back to a fixed, publicly-known constant so `just dev`/`just gen`
  work out of the box — every dev token is therefore forgeable by anyone,
  which is fine for localhost and NOTHING else. A warning is logged whenever
  the fallback engages.
- In ANY other ``LOFT_ENV`` value (``production``, ``staging``, a typo…) an
  unset/empty ``JWT_SECRET`` makes :func:`resolve_auth_config` raise, which
  :func:`gateway.main.build_app` calls first thing — the process refuses to
  boot. Fail-closed: only the exact string ``"dev"`` opts into the fallback,
  so misspelling the environment name cannot silently weaken a deployment.
- An explicitly-set secret shorter than :data:`MIN_JWT_SECRET_LENGTH` is
  rejected in every environment (HS256 with a short secret is brute-forceable).

There is exactly one path to a usable secret — this module's
``resolve_auth_config`` — and routes read the result from ``app.state``,
which only ``build_app`` populates. No bypass exists to construct the app
with an unchecked secret (Next-Lane's fail-fast had one; ours is tested in
``tests/test_auth.py::TestStartupFailFast``).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from py_kit import get_logger

_logger = get_logger("gateway.auth")

#: JWT signing algorithm — symmetric HS256; single-service verifier today.
JWT_ALGORITHM = "HS256"

#: Minimum length for an explicitly-configured JWT secret (bytes of entropy
#: matter, but length is the enforceable floor; `openssl rand -hex 32` → 64).
MIN_JWT_SECRET_LENGTH = 32

#: Dev-only fallback secret — PUBLIC by definition (it is in the repo).
#: Tokens signed with it are forgeable by anyone; see the module docstring.
DEV_JWT_SECRET = "loft-dev-only-jwt-secret-do-not-deploy-0000"


@dataclass(frozen=True)
class AuthConfig:
    """Resolved auth runtime config (secret validated, TTL in seconds)."""

    jwt_secret: str
    token_ttl_s: int


def resolve_auth_config(
    *, loft_env: str, jwt_secret: str | None, token_ttl_s: int
) -> AuthConfig:
    """Validate the JWT secret posture; raise rather than boot weak.

    See the module docstring for the exact rules. Raises :class:`RuntimeError`
    (startup failure, never an HTTP response) so a misconfigured deployment
    dies loudly instead of serving forgeable tokens.
    """
    if token_ttl_s <= 0:
        raise RuntimeError(f"JWT_TTL_S must be positive, got {token_ttl_s}")
    secret = jwt_secret or None  # "" (e.g. `JWT_SECRET=` in compose) == unset
    if secret is None:
        if loft_env != "dev":
            raise RuntimeError(
                f"JWT_SECRET is required when LOFT_ENV={loft_env!r} (only "
                "LOFT_ENV=dev may run without one). Generate one with "
                "`openssl rand -hex 32`."
            )
        _logger.warning(
            "jwt_dev_fallback_secret_in_use",
            hint="tokens are forgeable; set JWT_SECRET for anything non-local",
        )
        return AuthConfig(jwt_secret=DEV_JWT_SECRET, token_ttl_s=token_ttl_s)
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET is too short ({len(secret)} < {MIN_JWT_SECRET_LENGTH} "
            "characters); generate one with `openssl rand -hex 32`."
        )
    return AuthConfig(jwt_secret=secret, token_ttl_s=token_ttl_s)


# --- password hashing (argon2id, library defaults) --------------------------

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


# --- JWT access tokens -------------------------------------------------------


class TokenError(Exception):
    """The presented token is invalid: expired, tampered, or malformed."""


def create_access_token(
    user_id: uuid.UUID, config: AuthConfig, *, now: datetime | None = None
) -> str:
    """Mint an HS256 access token for *user_id* (``now`` injectable for tests)."""
    issued_at = int((now or datetime.now(UTC)).timestamp())
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + config.token_ttl_s,
    }
    # PyJWT's `key` parameter is typed with a partially-unknown PyJWK union
    # upstream (hence the suppression); the str overload is what we use.
    return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        claims, config.jwt_secret, algorithm=JWT_ALGORITHM
    )


def decode_access_token(token: str, config: AuthConfig) -> uuid.UUID:
    """Verify *token* and return its subject user id.

    Pins the algorithm list (``alg`` confusion / ``none`` rejected by PyJWT),
    requires ``exp`` + ``sub``. Raises :class:`TokenError` on any defect —
    callers translate to a generic 401 without detailing which check failed.
    """
    try:
        claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            config.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return uuid.UUID(str(claims["sub"]))
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc
    except ValueError as exc:  # sub present but not a UUID
        raise TokenError("invalid subject") from exc
