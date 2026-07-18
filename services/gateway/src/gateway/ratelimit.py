"""Per-authenticated-user rate limiting for the gateway compute routes.

Thin wiring over the shared :class:`py_kit.ratelimit.RateLimiter` (the DRY
home for this cross-service concern). The limiter is keyed on the JWT-verified
:class:`~gateway.db.User` id, so the bound is per-principal — the right axis
now that the OCCT-CPU routes are all auth-gated (engineering audit F7). The
principal never travels upstream; only its id feeds the limiter key.

Applied as a route ``dependencies=[...]`` entry: it reuses the already-present
``get_current_user`` dependency (FastAPI caches it within a request, so auth
resolves once), adds no request/response schema, and therefore does not move
the OpenAPI contract. When no limiter is installed (``RATE_LIMIT_ENABLED``
false, or ``REDIS_URL`` unset) the dependency is a no-op — fail-open by
absence.
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.params import Depends as DependsMarker
from py_kit.ratelimit import RateLimiter

from gateway.auth import CurrentUser


def get_rate_limiter(request: Request) -> RateLimiter | None:
    """The installed limiter, or ``None`` when rate limiting is inactive.

    Set once by ``build_app``'s lifespan on ``app.state`` (built from settings
    or injected by tests); read-only here.
    """
    return getattr(request.app.state, "rate_limiter", None)


def rate_limited(scope: str = "compute") -> DependsMarker:
    """A FastAPI dependency enforcing the per-user limit for *scope*.

    Runs after auth (depends on the user), so an unauthenticated caller gets a
    401 and never consumes budget. On exceed the limiter raises the shared 429
    ``rate_limited`` envelope with ``Retry-After``.
    """

    async def dependency(
        user: CurrentUser,
        limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)],
    ) -> None:
        if limiter is None:
            return
        await limiter.check(str(user.id), scope=scope)

    return Depends(dependency)


#: Shared instance for the OCCT-CPU / compute surface — one per-user budget
#: across all the expensive routes, so a caller cannot dodge the cap by
#: fanning out across endpoints.
COMPUTE_RATE_LIMIT = rate_limited("compute")
