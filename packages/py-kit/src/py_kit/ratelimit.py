"""Redis-backed per-identity rate limiting (shared py-kit concern — DRY).

Cross-cutting security/availability plumbing, so it lives in py-kit once and
services install it (CLAUDE.md DRY rule). The gateway wires it onto the
OCCT-CPU compute routes to bound a single authenticated caller's request rate
(engineering audit F7's second half).

**Algorithm — sliding-window log.** Each identity gets a Redis sorted set
keyed ``{prefix}:{scope}:{identity}`` whose members are the wall-clock
timestamps (ms) of recent requests. On every call we, in ONE atomic
``MULTI``/``EXEC`` transaction: drop entries older than the window, record the
current request, count what remains, read the oldest survivor, and refresh the
key TTL. If the count exceeds the limit the request is denied and its
just-added entry removed (so a denied hammer does not itself hold the window
open). Unlike a fixed-window counter this has no double-burst at the window
boundary — a true rolling window.

**Wall clock on purpose.** Scores are ``time.time()`` (ms), not
``monotonic()``: the sorted set is shared across workers/replicas, so the
timestamps must be comparable between processes. NTP-synced hosts make this
correct; a single process/replica is trivially exact. The clock is injectable
so tests are deterministic without sleeping.

**Fail-open.** A limiter must never take the API down. Any Redis transport
error is logged (``rate_limit_backend_unavailable``) and the request is
allowed — an availability guard that fails safe rather than fail-closed, which
would convert a Redis blip into a full outage. The tradeoff (no limiting
during a Redis outage) is the right call for a DoS guard on an internal
service tier.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast
from uuid import uuid4

from py_kit.config import BaseServiceSettings
from py_kit.errors import RateLimitExceededError
from py_kit.logging import get_logger

_logger = get_logger("py_kit.ratelimit")

#: Default sorted-set key namespace.
DEFAULT_KEY_PREFIX = "ratelimit"


class _RedisPipeline(Protocol):
    """The subset of a redis-py async transaction pipeline the limiter drives."""

    def zremrangebyscore(self, key: str, min: float, max: float) -> _RedisPipeline: ...

    def zadd(self, key: str, mapping: Mapping[str, float]) -> _RedisPipeline: ...

    def zcard(self, key: str) -> _RedisPipeline: ...

    def zrange(
        self, key: str, start: int, end: int, withscores: bool = False
    ) -> _RedisPipeline: ...

    def pexpire(self, key: str, time: int) -> _RedisPipeline: ...

    async def execute(self) -> list[Any]: ...

    async def __aenter__(self) -> _RedisPipeline: ...

    async def __aexit__(self, *exc: object) -> None: ...


class RedisClient(Protocol):
    """The minimal async Redis surface the limiter needs.

    A structural type so both ``redis.asyncio.Redis`` (adapted at the seam in
    :meth:`RateLimiter.from_settings`) and a test double satisfy it.
    """

    def pipeline(self, transaction: bool = True) -> _RedisPipeline: ...

    async def zrem(self, key: str, *members: str) -> int: ...

    async def aclose(self) -> None: ...


class RateLimiter:
    """Sliding-window per-identity limiter over a Redis sorted set.

    ``limit`` requests are permitted per ``window_s`` seconds per identity.
    A non-positive ``limit`` disables enforcement (every call allowed).
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        limit: int,
        window_s: int,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._limit = limit
        self._window_s = window_s
        self._key_prefix = key_prefix
        self._clock = clock

    @classmethod
    def from_settings(cls, settings: BaseServiceSettings) -> RateLimiter | None:
        """Build a limiter from service settings, or ``None`` when inactive.

        Returns ``None`` (no limiting) when disabled via
        ``RATE_LIMIT_ENABLED=false`` or when ``REDIS_URL`` is unset — a
        limiter with no backing store cannot enforce anything, so it degrades
        to a logged no-op rather than failing startup (fail-open posture).
        """
        if not settings.rate_limit_enabled:
            return None
        if settings.redis_url is None:
            _logger.warning(
                "rate_limit_disabled_no_redis",
                hint="set REDIS_URL to enforce the per-user rate limit",
            )
            return None
        # Imported lazily so importing this module never hard-requires the
        # redis driver (it is an install-time dependency of services that opt
        # in). redis-py's overloaded command signatures do not structurally
        # match our minimal protocol, so we adapt at this one seam.
        from redis.asyncio import Redis

        # from_url is typed with a partially-unknown ``**kwargs`` upstream; the
        # str-DSN overload we use returns a plain ``Redis``.
        client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            settings.redis_url
        )
        return cls(
            cast(RedisClient, client),
            limit=settings.rate_limit_requests,
            window_s=settings.rate_limit_window_s,
        )

    async def check(self, identity: str, *, scope: str = "compute") -> None:
        """Record a request for *identity*; raise 429 when over the budget.

        Raises :class:`RateLimitExceededError` (429 + ``Retry-After``) on
        exceed. Fails open — allows the request — on any Redis error.
        """
        if self._limit <= 0:
            return
        now_ms = int(self._clock() * 1000)
        window_ms = self._window_s * 1000
        cutoff = now_ms - window_ms
        key = f"{self._key_prefix}:{scope}:{identity}"
        member = f"{now_ms}:{uuid4().hex}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zadd(key, {member: float(now_ms)})
                pipe.zcard(key)
                pipe.zrange(key, 0, 0, withscores=True)
                pipe.pexpire(key, window_ms)
                results = await pipe.execute()
        except Exception as exc:  # any backend error fails open (see module doc)
            _logger.warning(
                "rate_limit_backend_unavailable",
                scope=scope,
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        count = int(results[2])
        if count <= self._limit:
            return
        # Over budget: drop the entry we optimistically added so a denied
        # request does not keep the window saturated against legit callers.
        # Best-effort — a cleanup failure still denies the request.
        with contextlib.suppress(Exception):
            await self._redis.zrem(key, member)
        retry_after_s = self._retry_after(results[3], now_ms, window_ms)
        _logger.info(
            "rate_limit_exceeded",
            scope=scope,
            limit=self._limit,
            window_s=self._window_s,
            retry_after_s=retry_after_s,
        )
        raise RateLimitExceededError(
            f"Rate limit exceeded: at most {self._limit} requests per "
            f"{self._window_s}s.",
            retry_after_s=retry_after_s,
            details={
                "limit": self._limit,
                "window_s": self._window_s,
                "retry_after_s": retry_after_s,
            },
        )

    def _retry_after(self, oldest: Any, now_ms: int, window_ms: int) -> int:
        """Seconds until the oldest surviving entry ages out (≥ 1).

        Freeing the oldest slot is the soonest a denied caller can succeed;
        the client re-checks and, if still saturated, gets a fresh header.
        """
        if not oldest:
            return 1
        oldest_score = float(oldest[0][1])
        remaining_ms = oldest_score + window_ms - now_ms
        return max(1, math.ceil(remaining_ms / 1000))

    async def aclose(self) -> None:
        """Release the underlying Redis connection pool."""
        await self._redis.aclose()
