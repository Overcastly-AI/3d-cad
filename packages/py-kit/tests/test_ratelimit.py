"""py_kit.ratelimit — sliding-window limiter over a fake Redis sorted set.

Hermetic: an in-memory async double stands in for redis-py (no server, no new
dependency), and an injected clock makes the window deterministic without
sleeping. Covers under/over limit, the 429 envelope + Retry-After, window
reset, per-identity isolation, the disabled path, and fail-open on a backend
error.
"""

import asyncio
from collections.abc import Coroutine, Mapping
from typing import Any

import pytest
from py_kit.config import BaseServiceSettings
from py_kit.errors import RateLimitExceededError
from py_kit.ratelimit import RateLimiter


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Drive an async scenario to completion (suite convention — no plugin)."""
    return asyncio.run(coro)


class FakePipeline:
    """Minimal transaction pipeline: queue commands, run atomically on exec."""

    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def zremrangebyscore(self, key: str, min: float, max: float) -> "FakePipeline":
        self._ops.append(("zremrangebyscore", (key, min, max)))
        return self

    def zadd(self, key: str, mapping: Mapping[str, float]) -> "FakePipeline":
        self._ops.append(("zadd", (key, dict(mapping))))
        return self

    def zcard(self, key: str) -> "FakePipeline":
        self._ops.append(("zcard", (key,)))
        return self

    def zrange(
        self, key: str, start: int, end: int, withscores: bool = False
    ) -> "FakePipeline":
        self._ops.append(("zrange", (key, start, end, withscores)))
        return self

    def pexpire(self, key: str, time: int) -> "FakePipeline":
        self._ops.append(("pexpire", (key, time)))
        return self

    async def execute(self) -> list[Any]:
        if self._redis.fail:
            raise ConnectionError("redis unavailable")
        return [self._redis.run(name, args) for name, args in self._ops]


class FakeRedis:
    """In-memory sorted sets: ``{key: {member: score}}``."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, float]] = {}
        self.fail = False

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    async def zrem(self, key: str, *members: str) -> int:
        if self.fail:
            raise ConnectionError("redis unavailable")
        entries = self.store.get(key, {})
        removed = 0
        for member in members:
            if entries.pop(member, None) is not None:
                removed += 1
        return removed

    async def aclose(self) -> None:
        return None

    def run(self, name: str, args: tuple[Any, ...]) -> Any:
        entries = self.store.setdefault(args[0], {})
        if name == "zremrangebyscore":
            _, low, high = args
            drop = [m for m, s in entries.items() if low <= s <= high]
            for m in drop:
                del entries[m]
            return len(drop)
        if name == "zadd":
            added = 0
            for member, score in args[1].items():
                if member not in entries:
                    added += 1
                entries[member] = float(score)
            return added
        if name == "zcard":
            return len(entries)
        if name == "zrange":
            _, start, end, withscores = args
            ordered = sorted(entries.items(), key=lambda kv: kv[1])
            window = ordered[start:] if end == -1 else ordered[start : end + 1]
            return [(m, s) for m, s in window] if withscores else [m for m, _ in window]
        if name == "pexpire":
            return True
        raise AssertionError(f"unexpected command {name}")


class Clock:
    """A movable wall clock (seconds) for deterministic windows."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def make_limiter(
    redis: FakeRedis, clock: Clock, *, limit: int = 3, window_s: int = 60
) -> RateLimiter:
    return RateLimiter(redis, limit=limit, window_s=window_s, clock=clock)


def test_under_limit_allows() -> None:
    async def scenario() -> None:
        limiter = make_limiter(FakeRedis(), Clock(), limit=3)
        for _ in range(3):
            await limiter.check("user-a")  # no raise up to the limit

    run(scenario())


def test_over_limit_raises_429_with_retry_after() -> None:
    async def scenario() -> None:
        limiter = make_limiter(FakeRedis(), Clock(), limit=3, window_s=60)
        for _ in range(3):
            await limiter.check("user-a")
        with pytest.raises(RateLimitExceededError) as excinfo:
            await limiter.check("user-a")
        error = excinfo.value
        assert error.status_code == 429
        assert error.code == "rate_limited"
        # Retry-After ≈ full window when the burst lands at one instant.
        assert error.retry_after_s == 60
        assert error.headers is not None
        assert error.headers["Retry-After"] == "60"
        assert error.details == {"limit": 3, "window_s": 60, "retry_after_s": 60}

    run(scenario())


def test_window_resets_after_elapsed_time() -> None:
    async def scenario() -> None:
        clock = Clock()
        limiter = make_limiter(FakeRedis(), clock, limit=3, window_s=60)
        for _ in range(3):
            await limiter.check("user-a")
        with pytest.raises(RateLimitExceededError):
            await limiter.check("user-a")
        clock.t += 61  # whole window elapses → old entries age out
        for _ in range(3):
            await limiter.check("user-a")  # budget restored

    run(scenario())


def test_denied_request_does_not_consume_a_slot() -> None:
    """A rejected call must not itself hold the window open."""

    async def scenario() -> None:
        redis = FakeRedis()
        limiter = make_limiter(redis, Clock(), limit=3, window_s=60)
        for _ in range(3):
            await limiter.check("user-a")
        for _ in range(5):  # hammer past the limit
            with pytest.raises(RateLimitExceededError):
                await limiter.check("user-a")
        # Exactly the 3 allowed entries remain — the denials were cleaned up.
        key = next(iter(redis.store))
        assert len(redis.store[key]) == 3

    run(scenario())


def test_identities_are_isolated() -> None:
    async def scenario() -> None:
        limiter = make_limiter(FakeRedis(), Clock(), limit=3)
        for _ in range(3):
            await limiter.check("user-a")
        with pytest.raises(RateLimitExceededError):
            await limiter.check("user-a")
        # A different principal has its own untouched budget.
        for _ in range(3):
            await limiter.check("user-b")

    run(scenario())


def test_scopes_are_isolated() -> None:
    async def scenario() -> None:
        limiter = make_limiter(FakeRedis(), Clock(), limit=1)
        await limiter.check("user-a", scope="tessellate")
        with pytest.raises(RateLimitExceededError):
            await limiter.check("user-a", scope="tessellate")
        # A different scope is a separate bucket.
        await limiter.check("user-a", scope="export")

    run(scenario())


def test_non_positive_limit_disables() -> None:
    async def scenario() -> None:
        limiter = make_limiter(FakeRedis(), Clock(), limit=0)
        for _ in range(100):
            await limiter.check("user-a")  # never enforced

    run(scenario())


def test_fails_open_when_backend_errors() -> None:
    async def scenario() -> None:
        redis = FakeRedis()
        redis.fail = True
        limiter = make_limiter(redis, Clock(), limit=1)
        # Every call would exceed a limit of 1, but the backend is down → allow.
        for _ in range(5):
            await limiter.check("user-a")

    run(scenario())


def test_from_settings_returns_none_when_disabled() -> None:
    settings = BaseServiceSettings(rate_limit_enabled=False, redis_url="redis://x")
    assert RateLimiter.from_settings(settings) is None


def test_from_settings_returns_none_without_redis() -> None:
    settings = BaseServiceSettings(rate_limit_enabled=True, redis_url=None)
    assert RateLimiter.from_settings(settings) is None
