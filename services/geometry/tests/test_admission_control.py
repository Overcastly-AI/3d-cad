"""Every OCCT route is behind the admission queue, and the queue answers 503.

Two tests, and the first one is the important one because it is the one that
cannot rot. The failure this file guards against is not "the gate is broken" —
it is "someone adds a 22nd expensive route and forgets the dependency", which
no functional test would notice and which reopens CONC-2 for that route only.
So the coverage test enumerates the router and demands that every POST route is
either GATED or on an explicit, justified exemption list.

The exemptions are asserted by name for the same reason: a silent exemption
list that anybody can append to is not a control.
"""

import asyncio
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from geometry.api import router
from geometry.main import GeometrySettings, build_app
from py_kit.admission import ADMISSION_CONTROL, AdmissionGate

#: Routes that deliberately do NOT queue, with the reason each one is safe.
#: See the module docstring of ``geometry.api`` for the full argument.
UNGATED = {
    # An object-store read; consumes none of the resource the gate protects,
    # and queueing a 3 ms artifact fetch behind a 40 s rebuild would make the
    # cheapest operation in the product the slowest.
    "/api/v1/meshes/{mesh_glb_id}",
    # These only ENQUEUE onto the warm scheduler and return; the speculation
    # runs on that scheduler's own bounded thread. Gating them would make a
    # prefetch wait for the rebuild it exists to get ahead of.
    "/api/v1/warm",
    "/api/v1/warm/cancel",
}

TESSELLATE_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}


def _gated(route: APIRoute) -> bool:
    return any(
        getattr(dependency, "dependency", None) is ADMISSION_CONTROL.dependency
        for dependency in route.dependencies
    )


def test_every_expensive_route_is_behind_the_queue() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert routes, "the geometry router lost its routes"

    ungated = {route.path for route in routes if not _gated(route)}
    assert ungated == UNGATED, (
        "a geometry route changed its admission posture — every OCCT route must "
        "carry ADMISSION_CONTROL (docs/PERF.md CONC-2), and every exemption must "
        "be justified in UNGATED above. Unexpectedly ungated: "
        f"{sorted(ungated - UNGATED)}; newly gated (update UNGATED): "
        f"{sorted(UNGATED - ungated)}"
    )


def test_the_gate_is_installed_from_settings_with_the_measured_default() -> None:
    app = build_app(GeometrySettings(loft_env="dev"))
    gate: AdmissionGate | None = app.state.admission_gate
    assert gate is not None
    # One effective core per worker: OCP does not release the GIL (CONC-5).
    assert gate.stats().concurrency == 1


def test_a_saturated_worker_answers_503_not_a_slow_200() -> None:
    """The shipped behaviour under overload, end to end through the real app.

    Without the queue this request would have been ADMITTED and would have
    shared the core with everything else, so that all of them miss the client's
    deadline together. With it, the honest answer arrives immediately and says
    when to come back.

    Driven over ASGI rather than ``TestClient`` because the gate is an asyncio
    object: the worker has to be genuinely occupied by a live request in the
    SAME event loop as the one under test, and a sync client cannot express
    that without reaching into the gate's internals — which would test the
    poke, not the route.
    """
    settings = GeometrySettings(
        loft_env="dev",
        admission_concurrency=1,
        admission_queue_depth=0,
        admission_max_wait_s=1.0,
    )
    app = build_app(settings)
    gate: AdmissionGate = app.state.admission_gate

    async def scenario() -> httpx.Response:
        occupied = asyncio.Event()
        release = asyncio.Event()

        async def hold() -> None:
            async with gate.admit():
                occupied.set()
                await release.wait()

        holder = asyncio.create_task(hold())
        await occupied.wait()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://geometry"
        ) as client:
            response = await client.post(
                "/api/v1/tessellate/meta", json=TESSELLATE_REQUEST
            )
        release.set()
        await holder
        return response

    response = asyncio.run(scenario())

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_overloaded"
    assert error["details"]["reason"] == "queue_full"
    assert int(response.headers["Retry-After"]) >= 1
    # It must never read as an outage — that is CONC-3's defect in a new costume.
    assert "unreachable" not in error["message"].lower()


def test_an_idle_worker_is_unaffected_by_the_queue() -> None:
    """A bound that changes the uncontended path is a regression, not a fix."""
    app = build_app(GeometrySettings(loft_env="dev"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/tessellate/meta", json=TESSELLATE_REQUEST)
    assert response.status_code == 200
    assert response.json()["properties"]["volume"] == pytest.approx(6000.0)
