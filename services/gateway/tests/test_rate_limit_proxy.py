"""Gateway per-user rate limiting on the OCCT-CPU compute routes (audit F7).

End-to-end over the real auth harness (SQLite): a per-authenticated-user
Redis-backed sliding-window limiter, injected here with an in-memory fake
Redis and a frozen clock, is wired onto the compute routes by ``build_app``.
Asserts: under the limit passes and forwards upstream; over the limit is a 429
``rate_limited`` envelope with ``Retry-After`` and NOTHING forwarded; the
window resets; two users have independent budgets; a Redis outage fails open.
"""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.ratelimit import RateLimiter
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

BOX_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}

GLB = b"glTF\x02\x00\x00\x00fake-payload"

Handler = Callable[[httpx.Request], httpx.Response]


# --- in-memory fake Redis (hermetic; no server, no new dependency) ----------


class FakePipeline:
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
    def __init__(self) -> None:
        self.store: dict[str, dict[str, float]] = {}
        self.fail = False

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    async def zrem(self, key: str, *members: str) -> int:
        if self.fail:
            raise ConnectionError("redis unavailable")
        entries = self.store.get(key, {})
        return sum(entries.pop(m, None) is not None for m in members)

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
            for member, score in args[1].items():
                entries[member] = float(score)
            return len(args[1])
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
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# --- harness ----------------------------------------------------------------


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def make_client(
    db_url: str, handler: Handler, limiter: RateLimiter | None
) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(handler),
        rate_limiter=limiter,
    )
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ok_handler(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=GLB)

    return handler


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    return body["error"]


def _tessellate(client: TestClient, bearer: dict[str, str]) -> httpx.Response:
    return client.post("/api/v1/geometry/tessellate", json=BOX_REQUEST, headers=bearer)


def test_over_limit_returns_429_and_forwards_nothing(db_url: str) -> None:
    seen: list[httpx.Request] = []
    limiter = RateLimiter(FakeRedis(), limit=2, window_s=60, clock=Clock())

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        bearer = _register(client, "alice@example.com")
        assert _tessellate(client, bearer).status_code == 200
        assert _tessellate(client, bearer).status_code == 200
        blocked = _tessellate(client, bearer)

    assert blocked.status_code == 429
    error = _envelope(blocked.json())
    assert error["code"] == "rate_limited"
    assert error["details"]["limit"] == 2
    # Precise back-off signal for the client.
    assert blocked.headers["Retry-After"] == "60"
    # The blocked request never reached the geometry service.
    assert len(seen) == 2


def test_under_limit_passes_through(db_url: str) -> None:
    seen: list[httpx.Request] = []
    limiter = RateLimiter(FakeRedis(), limit=5, window_s=60, clock=Clock())

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        bearer = _register(client, "alice@example.com")
        for _ in range(5):
            assert _tessellate(client, bearer).status_code == 200

    assert len(seen) == 5


def test_window_reset_restores_budget(db_url: str) -> None:
    seen: list[httpx.Request] = []
    clock = Clock()
    limiter = RateLimiter(FakeRedis(), limit=1, window_s=60, clock=clock)

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        bearer = _register(client, "alice@example.com")
        assert _tessellate(client, bearer).status_code == 200
        assert _tessellate(client, bearer).status_code == 429
        clock.t += 61  # window elapses
        assert _tessellate(client, bearer).status_code == 200

    assert len(seen) == 2


def test_per_user_isolation(db_url: str) -> None:
    seen: list[httpx.Request] = []
    limiter = RateLimiter(FakeRedis(), limit=1, window_s=60, clock=Clock())

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        alice = _register(client, "alice@example.com")
        bob = _register(client, "bob@example.com")
        assert _tessellate(client, alice).status_code == 200
        assert _tessellate(client, alice).status_code == 429  # alice exhausted
        # Bob's budget is untouched by alice hitting her limit.
        assert _tessellate(client, bob).status_code == 200

    assert len(seen) == 2


def test_backend_outage_fails_open(db_url: str) -> None:
    seen: list[httpx.Request] = []
    redis = FakeRedis()
    redis.fail = True  # Redis unreachable from the first call
    limiter = RateLimiter(redis, limit=1, window_s=60, clock=Clock())

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        bearer = _register(client, "alice@example.com")
        for _ in range(4):  # would all be blocked past a limit of 1
            assert _tessellate(client, bearer).status_code == 200

    # A limiter outage must not take the API down — every call served.
    assert len(seen) == 4


def test_unauthenticated_not_rate_limited_and_forwards_nothing(db_url: str) -> None:
    """No token → 401 before the limiter runs; anon never consumes budget."""
    seen: list[httpx.Request] = []
    limiter = RateLimiter(FakeRedis(), limit=1, window_s=60, clock=Clock())

    with make_client(db_url, _ok_handler(seen), limiter) as client:
        response = client.post("/api/v1/geometry/tessellate", json=BOX_REQUEST)

    assert response.status_code == 401
    assert seen == []
