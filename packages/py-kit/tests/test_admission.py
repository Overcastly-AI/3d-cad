"""py_kit.admission — the bounded queue, its refusals, and their honesty.

The property under test is not "there is a semaphore". It is the CONC-2 claim:
**under overload, a bounded FIFO queue delivers more useful answers than
processor sharing does**, and everything it refuses it refuses before spending
CPU and with a retry interval a client can act on.

So the tests here are mostly about ORDER and ARITHMETIC, and one of them
(``test_fifo_beats_processor_sharing_under_a_deadline``) reproduces the
measured 1-of-16-vs-11-of-16 result in miniature with a simulated service time,
because that number is the entire justification for the module existing.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from py_kit.admission import ADMISSION_CONTROL, AdmissionGate
from py_kit.app import create_app
from py_kit.config import BaseServiceSettings
from py_kit.errors import ClientGoneError, ServiceOverloadedError
from py_kit.metrics import REGISTRY

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _value(name: str, labels: dict[str, str] | None = None) -> float:
    sample = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if sample is None else sample


@asynccontextmanager
async def _occupied(gate: AdmissionGate) -> AsyncGenerator[None]:
    """Hold every slot of *gate* for the duration of the block.

    Needed because the depth cap governs WAITING, not arriving: an idle gate
    admits even at ``queue_depth=0``, so a refusal test has to make the gate
    genuinely busy rather than merely configure it small.
    """
    release = asyncio.Event()
    entered = asyncio.Event()
    occupancy = gate.stats().concurrency

    async def holder() -> None:
        async with gate.admit():
            entered.set()
            await release.wait()

    held = [asyncio.create_task(holder()) for _ in range(occupancy)]
    await entered.wait()
    while gate.stats().running < occupancy:
        await asyncio.sleep(0)
    try:
        yield
    finally:
        release.set()
        await asyncio.gather(*held)


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------


async def test_admits_immediately_when_idle() -> None:
    gate = AdmissionGate(concurrency=1, queue_depth=4, max_wait_s=5.0)
    async with gate.admit() as waited:
        assert waited == pytest.approx(0.0, abs=0.05)
        assert gate.stats().running == 1
    assert gate.stats().running == 0


async def test_concurrency_is_the_bound_not_a_suggestion() -> None:
    """At most ``concurrency`` bodies run at once — the whole point."""
    gate = AdmissionGate(
        concurrency=2, queue_depth=8, max_wait_s=30.0, initial_service_time_s=0.02
    )
    peak = 0
    live = 0

    async def worker() -> None:
        nonlocal peak, live
        async with gate.admit():
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak == 2


async def test_queue_is_fifo() -> None:
    """Arrival order is service order.

    This is the property that turns "everyone is late" into "some of you are
    served": processor sharing has no order at all, which is why 13 of 16
    requests finished within 0.4 s of each other at the deadline.
    """
    gate = AdmissionGate(concurrency=1, queue_depth=16, max_wait_s=10.0)
    served: list[int] = []
    entered = asyncio.Event()

    async def blocker() -> None:
        async with gate.admit():
            entered.set()
            await asyncio.sleep(0.05)

    async def arrival(index: int) -> None:
        async with gate.admit():
            served.append(index)

    block = asyncio.create_task(blocker())
    await entered.wait()
    arrivals: list[asyncio.Task[None]] = []
    for index in range(5):
        arrivals.append(asyncio.create_task(arrival(index)))
        # One event-loop turn between arrivals, so "arrival order" is defined.
        await asyncio.sleep(0)
    await asyncio.gather(block, *arrivals)
    assert served == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# the refusals — each distinguishable, each with a usable Retry-After
# ---------------------------------------------------------------------------


async def test_queue_full_refuses_before_doing_any_work() -> None:
    gate = AdmissionGate(
        concurrency=1, queue_depth=2, max_wait_s=30.0, initial_service_time_s=1.0
    )
    release = asyncio.Event()
    entered = asyncio.Event()

    async def holder() -> None:
        async with gate.admit():
            entered.set()
            await release.wait()

    async def waiter() -> None:
        async with gate.admit():
            pass

    held = asyncio.create_task(holder())
    await entered.wait()
    queued = [asyncio.create_task(waiter()) for _ in range(2)]
    await asyncio.sleep(0.01)
    assert gate.stats().queued == 2

    with pytest.raises(ServiceOverloadedError) as raised:
        async with gate.admit():
            pytest.fail("the third waiter must never enter the section")
    assert raised.value.status_code == 503
    assert raised.value.code == "service_overloaded"
    assert raised.value.details["reason"] == "queue_full"
    assert raised.value.retry_after_s >= 1
    assert raised.value.headers == {"Retry-After": str(raised.value.retry_after_s)}

    release.set()
    await asyncio.gather(held, *queued)


async def test_predicted_wait_refuses_using_the_MEASURED_service_time() -> None:
    """The adaptive bound: the same queue depth is fine for 0.2 s edits and
    hopeless for 40 s rebuilds, and only a measured rate can tell them apart."""
    gate = AdmissionGate(
        concurrency=1,
        queue_depth=50,
        max_wait_s=5.0,
        # Pretend each request costs 4 s: two ahead already blows a 5 s budget.
        initial_service_time_s=4.0,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with gate.admit():
            entered.set()
            await release.wait()

    async def waiter() -> None:
        async with gate.admit():
            pass

    held = asyncio.create_task(holder())
    await entered.wait()
    # One request may queue: it waits out the holder's 4 s and is served at the
    # budget. The SECOND would be served at 8 s, past the 5 s budget, so the
    # gate refuses it — at a queue depth of 50. That is the point: depth alone
    # cannot express "this queue is too slow for this deadline".
    first = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)
    assert gate.stats().queued == 1

    with pytest.raises(ServiceOverloadedError) as raised:
        async with gate.admit():
            pytest.fail("unreachable")
    assert raised.value.details["reason"] == "predicted_wait"
    assert raised.value.details["queued"] == 1
    assert raised.value.details["queue_depth"] == 50
    assert raised.value.retry_after_s == 8  # (1 queued + itself) x 4 s

    release.set()
    await asyncio.gather(held, first)


async def test_wait_timeout_is_the_backstop_when_the_estimate_was_optimistic() -> None:
    gate = AdmissionGate(
        concurrency=1,
        queue_depth=8,
        max_wait_s=0.05,
        # A wildly optimistic seed, so the predictive check lets it queue.
        initial_service_time_s=0.001,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with gate.admit():
            entered.set()
            await release.wait()

    held = asyncio.create_task(holder())
    await entered.wait()

    with pytest.raises(ServiceOverloadedError) as raised:
        async with gate.admit():
            pytest.fail("unreachable")
    assert raised.value.details["reason"] == "wait_timeout"
    # It waited and left: the queue must not leak the slot it never got.
    assert gate.stats().queued == 0

    release.set()
    await held


async def test_a_refused_request_leaves_the_gate_exactly_as_it_found_it() -> None:
    """No work started, no slot consumed, no counter drift — the "we do not
    silently drop work" rule is only true if refusal is genuinely free."""
    gate = AdmissionGate(concurrency=1, queue_depth=0, max_wait_s=1.0)
    async with _occupied(gate):
        before = gate.stats()
        with pytest.raises(ServiceOverloadedError):
            async with gate.admit():
                pytest.fail("unreachable")
        assert gate.stats() == before


# ---------------------------------------------------------------------------
# abandoned work
# ---------------------------------------------------------------------------


async def test_a_disconnected_client_does_not_get_a_core_spent_on_it() -> None:
    gate = AdmissionGate(concurrency=1, queue_depth=4, max_wait_s=5.0)
    before = _value("loft_admission_abandoned_total")

    async def gone() -> bool:
        return True

    with pytest.raises(ClientGoneError):
        async with gate.admit(is_disconnected=gone):
            pytest.fail("must not run work for a client that left")
    assert _value("loft_admission_abandoned_total") - before == 1.0
    # The slot it briefly held is returned, not leaked.
    async with gate.admit():
        pass


async def test_a_connected_client_is_not_mistaken_for_a_gone_one() -> None:
    gate = AdmissionGate(concurrency=1, queue_depth=4, max_wait_s=5.0)

    async def still_here() -> bool:
        return False

    async with gate.admit(is_disconnected=still_here):
        assert gate.stats().running == 1


# ---------------------------------------------------------------------------
# the measured claim, in miniature
# ---------------------------------------------------------------------------


async def test_fifo_beats_processor_sharing_under_a_deadline() -> None:
    """docs/PERF.md CONC-2, reproduced at 1/100th scale.

    Sixteen requests, each costing 0.05 s of exclusive service, against a 0.30 s
    client deadline. Processor sharing (all sixteen interleaved) finishes every
    one of them at ~0.80 s, i.e. **zero** inside the deadline. FIFO finishes
    them one at a time, so the first six land. Same total work, same wall clock
    to drain — completely different amount of it delivered.
    """
    service_s = 0.05
    deadline_s = 0.30
    requests = 16

    # Processor sharing: everyone progresses together, so everyone finishes at
    # requests * service_s. Modelled, not measured, because that is exactly what
    # the shipped behaviour was — and the model is the arithmetic in the doc.
    shared_completion_s = requests * service_s
    delivered_shared = requests if shared_completion_s <= deadline_s else 0

    gate = AdmissionGate(
        concurrency=1,
        queue_depth=requests,
        max_wait_s=10.0,
        initial_service_time_s=service_s,
    )
    started = time.monotonic()
    completions: list[float] = []

    async def request() -> None:
        try:
            async with gate.admit():
                await asyncio.sleep(service_s)
        except ServiceOverloadedError:
            return
        completions.append(time.monotonic() - started)

    await asyncio.gather(*(request() for _ in range(requests)))
    delivered_fifo = sum(1 for done in completions if done <= deadline_s)

    assert delivered_shared == 0
    assert delivered_fifo >= 4, completions
    assert delivered_fifo > delivered_shared


# ---------------------------------------------------------------------------
# metrics move
# ---------------------------------------------------------------------------


async def test_metrics_move_on_admission_and_on_refusal() -> None:
    gate = AdmissionGate(
        concurrency=1, queue_depth=0, max_wait_s=1.0, initial_service_time_s=0.01
    )
    waits_before = _value("loft_admission_wait_seconds_count")
    rejects_before = _value("loft_admission_rejected_total", {"reason": "queue_full"})

    async with gate.admit():
        assert _value("loft_admission_in_flight") == 1.0
    assert _value("loft_admission_in_flight") == 0.0
    assert _value("loft_admission_wait_seconds_count") - waits_before == 1.0

    async with _occupied(gate):
        with pytest.raises(ServiceOverloadedError):
            async with gate.admit():
                pytest.fail("unreachable")
    assert (
        _value("loft_admission_rejected_total", {"reason": "queue_full"})
        - rejects_before
        == 1.0
    )


# ---------------------------------------------------------------------------
# wiring: the FastAPI dependency and the app-factory install
# ---------------------------------------------------------------------------


def _app(**overrides: Any) -> FastAPI:
    settings = BaseServiceSettings(
        service_name="test-admission", loft_env="dev", **overrides
    )
    app = create_app(settings, title="t", version="0")

    @app.post("/expensive", dependencies=[ADMISSION_CONTROL])
    def expensive() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def test_factory_installs_the_gate_from_settings() -> None:
    app = _app(admission_concurrency=3, admission_queue_depth=11)
    gate = app.state.admission_gate
    assert isinstance(gate, AdmissionGate)
    assert gate.stats().concurrency == 3
    assert gate.stats().queue_depth == 11


def test_admission_can_be_switched_off_and_the_route_still_serves() -> None:
    app = _app(admission_enabled=False)
    assert app.state.admission_gate is None
    with TestClient(app) as client:
        assert client.post("/expensive").status_code == 200


def test_gated_route_serves_normally_when_there_is_no_contention() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post("/expensive")
    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


def test_the_503_reaches_the_client_as_the_shared_envelope() -> None:
    """A refusal must render as the py-kit envelope with a Retry-After header,
    not as an opaque 500 — a client that cannot parse the backpressure cannot
    obey it."""
    app = _app(admission_queue_depth=0)
    # Occupy the only slot so the next arrival is refused deterministically.
    gate: AdmissionGate = app.state.admission_gate

    async def occupy() -> None:
        async with gate.admit():
            await asyncio.sleep(3600)

    with TestClient(app) as client:
        loop = asyncio.new_event_loop()
        try:
            # Enter the gate on a scratch loop; the semaphore is plain state, so
            # the TestClient's own loop sees it as taken.
            task = loop.create_task(occupy())
            loop.run_until_complete(asyncio.sleep(0.01))
            response = client.post("/expensive")
            task.cancel()
        finally:
            loop.close()

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "service_overloaded"
    assert body["details"]["reason"] == "queue_full"
    assert int(response.headers["Retry-After"]) >= 1
    assert "unreachable" not in body["message"].lower()
