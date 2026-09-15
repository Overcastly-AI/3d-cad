"""Gateway auth — email/password identity + JWT access tokens.

Gateway-owned per RESEARCH §3 (the gateway is the auth service). The DTOs
moved to :mod:`py_kit.schemas.auth` when the Python scripting client became
their second consumer (DRY rule: extract on the second real use) — a client
must not import the service package to speak its contract. Submodules:
:mod:`gateway.auth.security` (hashing, JWT, startup secret resolution),
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
