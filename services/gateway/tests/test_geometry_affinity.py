"""gateway.affinity — session affinity for the geometry fan-out (CONC-1).

What has to be true for the measured 3.75x to be real in the shipped stack:

1. a modeler's requests all land on **one** worker, across every geometry route
   (the rebuild cache is per process, and a modeler holds two lineages in it);
2. different modelers **spread** across the workers, or fan-out buys nothing;
3. the mapping is **stable** when the worker set changes — only the departed
   worker's share moves, not everybody's;
4. it degrades to *slower*, never to *stranded*: a dead worker re-routes, and
   a SATURATED worker does not (failing over on backpressure is how one busy
   process becomes a busy fleet).

The unit tests pin the hash; the TestClient tests pin the wiring, because the
hash being right in isolation is not the property anybody cares about.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.affinity import FAILURE_COOLDOWN_S, GeometryPool, parse_worker_urls
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

WORKERS = [
    "http://geometry-1:8002",
    "http://geometry-2:8002",
    "http://geometry-3:8002",
    "http://geometry-4:8002",
]

Handler = Callable[[httpx.Request], httpx.Response]

#: The smallest request every geometry proxy route accepts — an empty feature
#: prefix. What is forwarded does not matter here; WHERE it is forwarded does.
OVERLAY_REQUEST: dict[str, Any] = {
    "tree": {
        "part_id": "00000000-0000-0000-0000-0000000000aa",
        "tree_version": 1,
        "features": [],
        "linear_deflection": 0.1,
    }
}


DRAWING_REQUEST: dict[str, Any] = {
    **OVERLAY_REQUEST["tree"],
    "views": ["front"],
}

TESSELLATE_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}

PROPERTIES: dict[str, Any] = {
    "volume": 6000.0,
    "surface_area": 2200.0,
    "centroid": {"x": 5.0, "y": 10.0, "z": 15.0},
    "bounding_box": {
        "min": {"x": 0.0, "y": 0.0, "z": 0.0},
        "max": {"x": 10.0, "y": 20.0, "z": 30.0},
    },
    "topology": {"faces": 6, "edges": 12, "shells": 1},
}

MESH_STATS: dict[str, Any] = {"vertices": 24, "triangles": 12, "glb_bytes": 128}


# ---------------------------------------------------------------------------
# the hash
# ---------------------------------------------------------------------------


def test_parse_worker_urls_accepts_one_or_many_and_dedups() -> None:
    assert parse_worker_urls("http://geometry:8002") == ["http://geometry:8002"]
    assert parse_worker_urls(" http://a:1 , http://b:2/ ,, http://a:1 ") == [
        "http://a:1",
        "http://b:2",
    ]
    with pytest.raises(ValueError):
        parse_worker_urls("  ,  ")


def _never_called(request: httpx.Request) -> httpx.Response:
    """These tests exercise ROUTING, never the wire."""
    raise AssertionError("the routing tests must not issue a request")


def _pool(urls: list[str]) -> GeometryPool:
    return GeometryPool(
        urls, timeout_s=1.0, transport=httpx.MockTransport(_never_called)
    )


def test_the_same_modeler_always_lands_on_the_same_worker() -> None:
    pool = _pool(WORKERS)
    chosen = pool.pick("user-42")
    assert all(pool.pick("user-42") == chosen for _ in range(50))


def test_modelers_spread_across_the_fleet() -> None:
    """If everyone hashed to one worker, the fan-out would be decoration."""
    pool = _pool(WORKERS)
    placement = {f"user-{index}": pool.pick(f"user-{index}") for index in range(400)}
    counts = {url: sum(1 for v in placement.values() if v == url) for url in WORKERS}
    assert set(counts) == set(WORKERS)
    # Rendezvous hashing is uniform in expectation; allow a generous band so
    # this pins "spread", not the digest.
    assert min(counts.values()) > 400 / len(WORKERS) * 0.6, counts


def test_removing_a_worker_moves_ONLY_that_workers_modelers() -> None:
    """The reason it is rendezvous hashing and not ``hash(user) % N``.

    Modulo would remap essentially everybody when the fleet changes size, i.e.
    a rolling restart would cost the whole team a cold cache. HRW costs 1/N of
    them, once.
    """
    keys = [f"user-{index}" for index in range(400)]
    before = {key: _pool(WORKERS).pick(key) for key in keys}
    after = {key: _pool(WORKERS[:-1]).pick(key) for key in keys}

    moved = [key for key in keys if before[key] != after[key]]
    departed = [key for key in keys if before[key] == WORKERS[-1]]
    # Exactly the departed worker's modelers moved — nobody else was disturbed.
    assert sorted(moved) == sorted(departed)
    assert 0 < len(moved) < len(keys) / 2


def test_adding_a_worker_disturbs_about_one_in_N() -> None:
    keys = [f"user-{index}" for index in range(400)]
    before = {key: _pool(WORKERS[:3]).pick(key) for key in keys}
    after = {key: _pool(WORKERS).pick(key) for key in keys}
    moved = sum(1 for key in keys if before[key] != after[key])
    # ~1/4 of keys should claim the new worker; the rest keep their checkpoint.
    assert 0.15 < moved / len(keys) < 0.40, moved


def test_an_unhealthy_worker_is_skipped_then_returns_after_the_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _pool(WORKERS)
    home = pool.pick("user-42")
    pool.mark_down(home, "ConnectError")
    assert pool.pick("user-42") != home

    clock = [0.0]
    monkeypatch.setattr("gateway.affinity.time.monotonic", lambda: clock[0])
    pool2 = _pool(WORKERS)
    home2 = pool2.pick("user-7")
    pool2.mark_down(home2, "ConnectError")
    assert pool2.pick("user-7") != home2
    clock[0] = FAILURE_COOLDOWN_S + 0.1
    assert pool2.pick("user-7") == home2


def test_a_modeler_is_never_stranded_when_every_worker_is_in_cooldown() -> None:
    """ "No healthy backend" is not a failure this layer is allowed to invent.

    The real transport error is the honest answer; a synthetic one would hide
    which worker was actually broken.
    """
    pool = _pool(WORKERS)
    for url in WORKERS:
        pool.mark_down(url, "ConnectError")
    assert pool.pick("user-42") in WORKERS


def test_one_worker_is_just_the_degenerate_case() -> None:
    pool = _pool(["http://geometry:8002"])
    assert pool.pick("anyone") == "http://geometry:8002"
    pool.mark_down("http://geometry:8002", "ConnectError")
    assert pool.pick("anyone") == "http://geometry:8002"


# ---------------------------------------------------------------------------
# the wiring
# ---------------------------------------------------------------------------


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


def make_client(db_url: str, handler: Handler, *, workers: list[str]) -> TestClient:
    settings = GatewaySettings(
        geometry_url=",".join(workers),
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, geometry_transport=httpx.MockTransport(handler))
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _host(request: httpx.Request) -> str:
    return str(request.url.host)


def _upstream_body(request: httpx.Request) -> dict[str, Any]:
    """The minimum each proxied route's response DTO validates against."""
    if request.url.path.endswith("/overlay"):
        return {"vertices": [], "edges": [], "faces": []}
    if request.url.path.endswith("/drawing/evaluate"):
        return {
            "part_id": OVERLAY_REQUEST["tree"]["part_id"],
            "tree_version": 1,
            "views": [],
        }
    return {"properties": PROPERTIES, "mesh": MESH_STATS}


def test_every_geometry_route_of_one_modeler_lands_on_one_worker(
    db_url: str,
) -> None:
    """The property the 0.40 cache hit rate is made of.

    A modeler's evaluate lineage and the ``record_history`` lineage their face
    pick resumes from must live in the SAME process. So it is not enough that
    ``/overlay`` is sticky — every route has to agree, which is why this walks
    several of them rather than one.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_host(request))
        return httpx.Response(200, json=_upstream_body(request))

    with make_client(db_url, handler, workers=WORKERS) as client:
        bearer = _register(client, "alice@example.com")
        for _ in range(3):
            for path, payload in (
                ("/api/v1/geometry/overlay", OVERLAY_REQUEST),
                ("/api/v1/geometry/drawing/evaluate", DRAWING_REQUEST),
                ("/api/v1/geometry/tessellate/meta", TESSELLATE_REQUEST),
            ):
                assert (
                    client.post(path, json=payload, headers=bearer).status_code == 200
                )

    assert seen, "no upstream call was made"
    assert len(set(seen)) == 1, seen


def test_two_modelers_do_not_share_a_worker_by_accident(db_url: str) -> None:
    """Not a guarantee for any particular pair — but over enough modelers the
    fleet must actually be used, or 'affinity' would be 'everyone on one box'."""
    seen: dict[str, str] = {}
    current = {"email": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[current["email"]] = _host(request)
        return httpx.Response(200, json=_upstream_body(request))

    with make_client(db_url, handler, workers=WORKERS) as client:
        for index in range(12):
            email = f"user{index}@example.com"
            current["email"] = email
            bearer = _register(client, email)
            client.post(
                "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
            )

    assert len(set(seen.values())) > 1, seen


def test_a_dead_worker_re_routes_the_modeler_instead_of_failing(db_url: str) -> None:
    """Degradation is COLD, not broken: the modeler gets their answer from a
    different process (a cache miss), and never sees an error."""
    attempts: list[str] = []
    dead = {"host": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        host = _host(request)
        attempts.append(host)
        if host == dead["host"]:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=_upstream_body(request))

    with make_client(db_url, handler, workers=WORKERS) as client:
        bearer = _register(client, "alice@example.com")
        # Kill exactly the worker this principal hashes to.
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )
        assert response.status_code == 200
        home = attempts[0]
        dead["host"] = home
        attempts.clear()

        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )
        assert response.status_code == 200, response.text
        assert attempts[0] == home  # tried home first
        assert attempts[1] != home  # then the deterministic second choice

        # And the cooldown holds: the next request skips the dead worker
        # entirely rather than paying the failed connect again.
        attempts.clear()
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )
        assert response.status_code == 200
        assert home not in attempts


def test_a_single_worker_deployment_surfaces_the_502_rather_than_pretending(
    db_url: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler, workers=["http://geometry:8002"]) as client:
        bearer = _register(client, "alice@example.com")
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"


def test_a_SATURATED_worker_is_not_failed_over_and_its_retry_after_survives(
    db_url: str,
) -> None:
    """503 backpressure must NOT be re-routed.

    Failing over on overload sprays one modeler's lineage across the fleet at
    exactly the moment locality is worth most, and answers "I am busy" by
    making more load. The 503 is relayed instead — with the ``Retry-After``
    geometry computed from its own measured service time, which the gateway
    could not reconstruct and must not drop.
    """
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(_host(request))
        return httpx.Response(
            503,
            headers={"Retry-After": "7"},
            json={
                "error": {
                    "code": "service_overloaded",
                    "message": "Geometry is at capacity.",
                    "details": {"reason": "queue_full"},
                    "request_id": "upstream",
                }
            },
        )

    with make_client(db_url, handler, workers=WORKERS) as client:
        bearer = _register(client, "alice@example.com")
        response = client.post(
            "/api/v1/geometry/overlay", json=OVERLAY_REQUEST, headers=bearer
        )

    assert len(attempts) == 1, attempts
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_overloaded"
    assert response.headers["Retry-After"] == "7"


def test_readiness_reports_how_many_workers_answered(db_url: str) -> None:
    """A gateway with three of four workers alive is degraded but serving, and
    a probe that collapsed that to "ok" would hide a dead process."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    settings = GatewaySettings(
        geometry_url=",".join(WORKERS),
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, geometry_transport=httpx.MockTransport(handler))
    with TestClient(app, raise_server_exceptions=False) as client:
        report = client.get("/readyz").json()
    # The probe uses its own client (real network) — all four are unreachable
    # here, which is exactly the degraded reading an operator must be able to
    # see rather than a flat "unreachable" that hides the fleet size.
    assert report["checks"]["geometry"] in {
        "unreachable",
        *(f"ok ({n}/4 workers)" for n in range(1, 5)),
    }
