"""Auth DTOs — the ``/api/v1/auth/*`` contract (single source of truth).

These pydantic models drive the generated OpenAPI/ts-client (``just gen``).
Passwords arrive as ``SecretStr`` so the value can never leak through a
repr/log, and — deliberately — carry NO schema-level length constraints:
pydantic 422s echo the offending input in their details, so the length policy
is enforced in the route layer instead, where the error message is written
without the value (see :func:`gateway.auth.routes.check_password_policy`).

**Why these live in py-kit and not in the gateway.** They were gateway-local
while the gateway was their only consumer, with an explicit note that they
would move on the second real use (CLAUDE.md DRY: extract on the second real
use, not the first imagined one). ``packages/loft-script`` is that second use:
the Python scripting client has to POST a ``RegisterRequest`` and parse an
``AuthTokenResponse``, and a CLIENT importing the SERVICE package to do it
would invert the dependency — pulling FastAPI, SQLAlchemy, asyncpg and argon2
into a library whose entire point is that it is just another HTTP caller. Every
other boundary DTO in this package is here for the same reason: the models are
the wire, and the wire belongs to nobody in particular.

The gateway is still the auth SERVICE (RESEARCH §3); only the shapes moved.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

#: Password policy bounds. The floor is NIST-baseline (register only); the
#: cap prevents multi-megabyte passwords from becoming an argon2 CPU-DoS
#: vector and applies to EVERY route that feeds argon2 — register and login.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 256


class RegisterRequest(BaseModel):
    """Create an account. Policy: 8-256 chars, enforced in the route."""

    email: EmailStr = Field(description="Account email; unique, case-insensitive")
    password: SecretStr = Field(
        description=f"Plaintext password, {PASSWORD_MIN_LENGTH}-"
        f"{PASSWORD_MAX_LENGTH} characters (never stored; argon2id-hashed)"
    )


class LoginRequest(BaseModel):
    """Exchange email + password for an access token."""

    email: EmailStr = Field(description="Account email")
    password: SecretStr = Field(
        description=f"Account password (at most {PASSWORD_MAX_LENGTH} "
        "characters — same cap as register, enforced in the route)"
    )


class UserResponse(BaseModel):
    """Public view of an account — no credential material, ever."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class AuthTokenResponse(BaseModel):
    """A signed-in identity: the user plus a bearer access token."""

    user: UserResponse
    access_token: str = Field(description="JWT for `Authorization: Bearer <token>`")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")
