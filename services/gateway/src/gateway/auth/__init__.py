"""Gateway auth — email/password identity + JWT access tokens.

Gateway-owned per RESEARCH §3 (the gateway is the auth service); single
consumer today, so nothing here lives in py-kit yet (DRY rule: extract on the
second real use). Submodules: :mod:`gateway.auth.security` (hashing, JWT,
startup secret resolution), :mod:`gateway.auth.schemas` (DTOs → contract),
:mod:`gateway.auth.routes` (``/api/v1/auth/*`` + the protected-route
dependency).
"""

from gateway.auth.routes import CurrentUser, get_current_user
from gateway.auth.routes import router as auth_router
from gateway.auth.security import AuthConfig, resolve_auth_config

__all__ = [
    "AuthConfig",
    "CurrentUser",
    "auth_router",
    "get_current_user",
    "resolve_auth_config",
]
