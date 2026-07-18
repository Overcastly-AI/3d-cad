"""Auth cryptography: argon2 password hashing, HS256 JWTs, secret posture.

Secret posture (documented honestly):

- ``LOFT_ENV`` has NO default. The dev fallback secret requires the exact,
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

Token scope (known limits, deliberate for a single-service verifier): access
tokens carry ``sub``/``iat``/``exp`` only — no ``aud``/``iss``/``jti`` — and
there is no revocation store, so a token stays valid until ``exp`` even
after logout/credential change. Both become REQUIRED work the moment a
second service verifies tokens (aud/iss confusion) or logout must actually
invalidate (jti + revocation list).
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
    *, loft_env: str | None, jwt_secret: str | None, token_ttl_s: int
) -> AuthConfig:
    """Validate the JWT secret posture; raise rather than boot weak.

    See the module docstring for the exact rules. Raises :class:`RuntimeError`
    (startup failure, never an HTTP response) so a misconfigured deployment
    dies loudly instead of serving forgeable tokens.
    """
    if token_ttl_s <= 0:
        raise RuntimeError(f"JWT_TTL_S must be positive, got {token_ttl_s}")
    # ""/whitespace (e.g. `JWT_SECRET=` in compose, a stray newline) == unset;
    # the stripped value is also what gets used, so the checked secret and the
    # signing secret can never differ.
    secret = (jwt_secret or "").strip() or None
    if secret is None:
        if loft_env != "dev":
            raise RuntimeError(
                f"JWT_SECRET is required when LOFT_ENV={loft_env!r}. Either "
                "set a real secret (generate one with `openssl rand -hex 32`) "
                "or, for LOCAL DEV ONLY, opt into the forgeable fallback "
                "explicitly with LOFT_ENV=dev."
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
