"""Auth DTOs — the ``/api/v1/auth/*`` contract (single source of truth).

These pydantic models drive the generated OpenAPI/ts-client (`just gen`).
Passwords arrive as ``SecretStr`` so the value can never leak through a
repr/log, and — deliberately — carry NO schema-level length constraints:
pydantic 422s echo the offending input in their details, so the length policy
is enforced in the route layer instead, where the error message is written
without the value (see :func:`gateway.auth.routes.check_password_policy`).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

#: Password policy bounds. The floor is NIST-baseline; the cap prevents
#: multi-megabyte passwords from becoming an argon2 CPU-DoS vector.
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
    password: SecretStr = Field(description="Account password")


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
