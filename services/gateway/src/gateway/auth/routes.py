"""``/api/v1/auth/*`` routes + the protected-route dependency.

Security invariants (asserted by tests/test_auth.py):

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
"""

from typing import Annotated

import anyio.to_thread
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from py_kit import (
    ConflictError,
    UnauthorizedError,
    ValidationApiError,
    get_logger,
)
from py_kit.db import SessionDep
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gateway.auth.schemas import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from gateway.auth.security import (
    AuthConfig,
    TokenError,
    burn_dummy_verification,
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from gateway.db import User

_logger = get_logger("gateway.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

#: One message for every credential failure — never say which part was wrong.
_INVALID_CREDENTIALS = "Invalid email or password."

#: One message for every token defect — never detail expired vs. tampered.
_INVALID_TOKEN = "Invalid or expired token."


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


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    config: AuthConfigDep,
    session: SessionDep,
) -> User:
    """Protected-route dependency: resolve the bearer token to a live user.

    401 (generic, with ``WWW-Authenticate: Bearer``) on a missing header,
    any token defect, or a subject that no longer exists.
    """
    if credentials is None:
        raise UnauthorizedError("Not authenticated.")
    try:
        user_id = decode_access_token(credentials.credentials, config)
    except TokenError:
        # Generic on purpose; the precise defect stays server-side.
        raise UnauthorizedError(_INVALID_TOKEN, code="invalid_token") from None
    user = await session.get(User, user_id)
    if user is None:
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


def _token_response(user: User, config: AuthConfig) -> AuthTokenResponse:
    return AuthTokenResponse(
        user=UserResponse.model_validate(user),
        access_token=create_access_token(user.id, config),
        expires_in=config.token_ttl_s,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest, config: AuthConfigDep, session: SessionDep
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
    return _token_response(user, config)


@router.post("/login")
async def login(
    request: LoginRequest, config: AuthConfigDep, session: SessionDep
) -> AuthTokenResponse:
    """Exchange email + password for an access token (uniform 401 on failure)."""
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
    return _token_response(user, config)


@router.get("/me")
async def me(user: CurrentUser) -> UserResponse:
    """The authenticated account (protected: bearer token required)."""
    return UserResponse.model_validate(user)
