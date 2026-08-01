"""Bounded admission control for CPU-bound routes (docs/PERF.md CONC-2).

WHY THIS EXISTS, in one measurement. Sixteen simultaneous 50-feature evaluates
were issued at one geometry worker on 2026-08-01. Thirteen of them finished
**within 0.4 s of each other, at 39-40 s**::

    completions (s): 29.3 35.2 36.4 37.4 37.9 39.2 39.4 39.4 39.4 39.5
                     39.5 39.5 39.5 39.5 39.6 39.6

That is *processor sharing*: every request creeps forward together instead of
one finishing while the others wait. It is the worst possible policy under a
client deadline, because it converts "some requests are late" into "every
request is late". Against the gateway's read timeout it delivered **1 of 16**
useful answers where a plain FIFO queue on the identical hardware delivers
**11 of 16** — same CPU, same work, 11x the output.

Nothing in the stack bounded the concurrency: httpx defaults to 100
connections, anyio's threadpool to 40 workers, and a geometry worker has
**one** effective core because OCP does not release the GIL (CONC-5). So the
fix is not a faster kernel, it is a queue.

WHAT THIS DOES

``AdmissionGate`` admits at most ``concurrency`` requests into the expensive
section at a time and makes the rest **wait in FIFO order** (asyncio's
``Semaphore`` wakes waiters in arrival order). Waiting costs a coroutine, not a
thread and not a core. Past the bound the gate **refuses**, and refuses
honestly:

* it refuses BEFORE any work starts, so nothing is computed and discarded —
  the CLAUDE.md "do not silently drop work" rule read literally: the only work
  this module discards is work it never began;
* it answers 503 ``service_overloaded`` with a ``Retry-After`` derived from the
  gate's own **measured** service time (an EWMA of recent completions), not
  from a constant somebody guessed;
* it never answers 502 "unreachable". The service is up. Saying otherwise is
  the CONC-3 defect in a different costume.

Three refusal reasons, deliberately distinguishable in the metric:

``queue_full``
    ``queue_depth`` requests are already waiting. A hard cap on memory and on
    how far ahead the queue can commit.
``predicted_wait``
    The queue is shorter than the cap, but at the measured service rate this
    arrival would not be served within ``max_wait_s``. Adaptive: the same queue
    depth is fine for 0.2 s sketch edits and hopeless for 40 s rebuilds, and
    only a measured service time can tell those apart.
``wait_timeout``
    It waited, the estimate was optimistic, and the budget ran out. The
    backstop that makes ``max_wait_s`` a real bound rather than a hope.

STATE, AND WHY IT CANNOT CROSS REQUESTS. Correctness under load is currently
clean (96 audited responses, zero crossed bodies —
``services/geometry/tests/test_concurrent_modelers.py``), and shared mutable
state is exactly how that would break. So: this object holds **two integers and
one float** — how many are running, how many are waiting, and the EWMA of
recent durations. It never touches a request, a body, a tree, or a result, and
there is no keyed storage of any kind for something to be looked up under the
wrong key. All of it is mutated only from the event-loop thread.
"""

import asyncio
import math
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from fastapi import Depends, Request
from fastapi.params import Depends as DependsMarker

from py_kit.errors import ClientGoneError, ServiceOverloadedError
from py_kit.logging import get_logger
from py_kit.metrics import (
    ADMISSION_ABANDONED,
    ADMISSION_IN_FLIGHT,
    ADMISSION_QUEUED,
    ADMISSION_REJECTED,
    ADMISSION_WAIT,
)

_logger = get_logger("py_kit.admission")

#: Weight of the newest sample in the service-time EWMA. 0.25 keeps the
#: estimate responsive to a change of part size (a few requests) without
#: letting one 40 s outlier dictate the next minute of admission decisions.
_EWMA_ALPHA: Final = 0.25

#: Floor on the advertised ``Retry-After``. Below one second the header is
#: meaningless (RFC 9110 delta-seconds is integral) and a stampede of
#: sub-second retries is worse than none.
_MIN_RETRY_AFTER_S: Final = 1

#: Ceiling on the advertised ``Retry-After``. A number larger than this is not
#: actionable advice, it is an outage report; cap it and let the client decide.
_MAX_RETRY_AFTER_S: Final = 300


@dataclass(frozen=True)
class AdmissionStats:
    """A point-in-time read of the gate (for ``/readyz`` reports and tests)."""

    running: int
    queued: int
    service_time_s: float
    concurrency: int
    queue_depth: int


class AdmissionGate:
    """A bounded FIFO queue in front of an expensive, non-parallel section.

    ``concurrency`` is how many requests may be *inside* the section at once.
    For OCCT work the honest value is **1 per effective core of this process**,
    and a geometry worker has exactly one (CONC-5): admitting a second request
    does not make it finish sooner, it makes both finish later.

    ``queue_depth`` is how many may WAIT. ``max_wait_s`` is the longest a
    request may wait before the gate gives up on it — the knob that decides
    whether the answer to overload is "everyone waits forever" or "some of you
    get served and the rest get told when to come back".

    ``initial_service_time_s`` seeds the EWMA so the very first burst, before
    any completion has been observed, is still judged against something
    plausible rather than against zero.
    """

    def __init__(
        self,
        *,
        concurrency: int = 1,
        queue_depth: int = 8,
        max_wait_s: float = 20.0,
        initial_service_time_s: float = 2.0,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if queue_depth < 0:
            raise ValueError("queue_depth must be >= 0")
        if max_wait_s <= 0:
            raise ValueError("max_wait_s must be > 0")
        self._concurrency = concurrency
        self._queue_depth = queue_depth
        self._max_wait_s = max_wait_s
        self._service_time_s = max(initial_service_time_s, 0.001)
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = 0
        self._queued = 0

    # --- introspection ------------------------------------------------------

    def stats(self) -> AdmissionStats:
        """Current occupancy — read by the readiness report and by tests."""
        return AdmissionStats(
            running=self._running,
            queued=self._queued,
            service_time_s=self._service_time_s,
            concurrency=self._concurrency,
            queue_depth=self._queue_depth,
        )

    def estimated_wait_s(self, *, arriving: bool = True) -> float:
        """How long a request arriving now would wait, at the measured rate.

        ``queued`` requests are ahead of it and drain ``concurrency`` at a time;
        a full section adds the tail of the batch currently inside. Counting a
        whole service time for that tail rather than half of one is deliberate:
        an estimate that is too low turns into a ``wait_timeout`` refusal AFTER
        the caller has already waited, which is the one refusal that wastes the
        caller's time.
        """
        ahead = self._queued + (1 if arriving else 0)
        drain = math.ceil(ahead / self._concurrency)
        inflight_tail = 1 if self._semaphore.locked() else 0
        return (drain - 1 + inflight_tail) * self._service_time_s if ahead else 0.0

    # --- admission ----------------------------------------------------------

    def _retry_after(self, wait_s: float) -> int:
        return max(_MIN_RETRY_AFTER_S, min(_MAX_RETRY_AFTER_S, math.ceil(wait_s)))

    def _refuse(self, reason: str, wait_s: float) -> ServiceOverloadedError:
        ADMISSION_REJECTED.labels(reason=reason).inc()
        retry_after_s = self._retry_after(wait_s)
        _logger.warning(
            "admission_refused",
            reason=reason,
            running=self._running,
            queued=self._queued,
            service_time_s=round(self._service_time_s, 3),
            retry_after_s=retry_after_s,
        )
        return ServiceOverloadedError(
            "Geometry is at capacity and this request would not be served in "
            f"time (about {retry_after_s} s of work is already queued ahead of "
            "it). Nothing was computed and discarded — retry after the "
            "interval in Retry-After.",
            retry_after_s=retry_after_s,
            details={
                "reason": reason,
                "running": self._running,
                "queued": self._queued,
                "concurrency": self._concurrency,
                "queue_depth": self._queue_depth,
                "retry_after_s": retry_after_s,
            },
        )

    @asynccontextmanager
    async def admit(
        self, *, is_disconnected: Callable[[], Awaitable[bool]] | None = None
    ) -> AsyncGenerator[float]:
        """Enter the expensive section, or raise :class:`ServiceOverloadedError`.

        Yields the seconds spent queueing (0.0 when admitted immediately).

        ``is_disconnected`` is checked once, AFTER admission: a request that
        waited its turn while the browser gave up would otherwise burn a full
        core producing an answer with no reader. Checking it here rather than
        while waiting is deliberate — a queued request costs a coroutine, a
        running one costs the machine.
        """
        # The depth cap governs WAITING, not arriving: a free slot is served
        # even at ``queue_depth=0``, which is what makes 0 mean "never queue,
        # shed instead" rather than "refuse everything".
        if self._semaphore.locked() and self._queued >= self._queue_depth:
            raise self._refuse("queue_full", self.estimated_wait_s())
        predicted = self.estimated_wait_s()
        if predicted > self._max_wait_s:
            raise self._refuse("predicted_wait", predicted)

        started = time.monotonic()
        self._queued += 1
        ADMISSION_QUEUED.inc()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), self._max_wait_s)
        except TimeoutError as exc:
            raise self._refuse("wait_timeout", self.estimated_wait_s()) from exc
        finally:
            self._queued -= 1
            ADMISSION_QUEUED.dec()

        waited = time.monotonic() - started
        ADMISSION_WAIT.observe(waited)

        if is_disconnected is not None and await is_disconnected():
            self._semaphore.release()
            ADMISSION_ABANDONED.inc()
            _logger.info("admission_abandoned", waited_s=round(waited, 3))
            raise ClientGoneError("Client disconnected before its turn came up.")

        self._running += 1
        ADMISSION_IN_FLIGHT.inc()
        service_started = time.monotonic()
        try:
            yield waited
        finally:
            self._observe_service(time.monotonic() - service_started)
            self._running -= 1
            ADMISSION_IN_FLIGHT.dec()
            self._semaphore.release()

    def _observe_service(self, seconds: float) -> None:
        """Fold one completion into the service-time EWMA."""
        self._service_time_s = (
            _EWMA_ALPHA * seconds + (1.0 - _EWMA_ALPHA) * self._service_time_s
        )


#: Where the gate lives on ``app.state``. One attribute name, read by the
#: dependency below and written once by a service's lifespan — the same shape
#: as ``rate_limiter`` (:mod:`py_kit.ratelimit`).
ADMISSION_GATE_ATTR: Final = "admission_gate"


def get_admission_gate(request: Request) -> AdmissionGate | None:
    """The installed gate, or ``None`` when admission control is off."""
    return getattr(request.app.state, ADMISSION_GATE_ATTR, None)


async def _admission_dependency(request: Request) -> AsyncIterator[None]:
    """Hold a slot in the gate for the whole handler (a ``yield`` dependency).

    ``None`` installed is a deliberate no-op rather than an error: unit suites,
    ``documents``, and a single-user localhost stack have nothing to admit, and
    a bound that only exists when configured is one less thing to get wrong.
    """
    gate = get_admission_gate(request)
    if gate is None:
        yield
        return
    async with gate.admit(is_disconnected=request.is_disconnected):
        yield


def admission_controlled() -> DependsMarker:
    """Route dependency: queue this route behind the process's admission gate.

    Applied as ``dependencies=[ADMISSION_CONTROL]`` on the expensive routes. It
    declares no request or response schema, so it does **not** move the OpenAPI
    contract (same posture as the gateway's ``COMPUTE_RATE_LIMIT``).
    """
    return Depends(_admission_dependency)


#: Shared marker for the CPU-bound surface — one queue per process, across all
#: the expensive routes, so a caller cannot dodge the bound by fanning out
#: across endpoints.
ADMISSION_CONTROL: Final = admission_controlled()
