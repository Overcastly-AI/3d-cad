"""Session affinity for the geometry fan-out (docs/PERF.md CONC-1).

THE MEASUREMENT. Four modelers, four geometry workers, four cores, the same
50-feature tray, three routing policies:

| dispatch    | wall s | cache hit | edit p50 | speedup vs. 1 worker |
| ----------- | -----: | --------: | -------: | -------------------: |
| **sticky**  | 19.0   | **0.40**  | 2 559 ms | **3.75x**            |
| roundrobin  | 34.5   | 0.125     | 2 916 ms | 2.06x                |
| random      | 58.9   | 0.075     | 4 753 ms | 1.21x                |

Sticky routing is not a tuning knob, it is most of what fan-out is worth. With
it, four modelers on four workers pay what ONE modeler pays on an idle machine
(2 559 ms per edit against 2 113 ms). Without it the rebuild cache dilutes by
roughly 1/N — 0.40 → 0.075 at four workers — because the checkpoint a modeler's
next click needs is in a process their next click will not reach. That costs
1.8x; unbalanced arrivals cost another 1.7x on top, because a worker with no
internal parallelism (CONC-5) cannot absorb two simultaneous requests while its
neighbours idle.

Compose DNS round-robin and a shared listening socket both give you the bottom
row. This module gives you the top one.

THE KEY IS THE USER, NOT THE PART, and that is a deliberate choice against the
obvious alternative. A working modeler occupies **two** cache lineages — the
evaluate lineage and the ``record_history`` lineage a face pick resumes from —
and every route that reaches geometry already carries the verified principal,
while only some carry a part id. Hashing on the user therefore (a) keeps a
modeler's two lineages in the same process, which is the property the 0.40 hit
rate is made of, (b) needs no DTO change and so cannot drift from the contract,
and (c) is exactly the mapping the ``sticky`` row above measured. Hashing on
part id would spread one person's two lineages across two workers on the routes
that lack the id — the dilution this module exists to prevent, reintroduced at
the seam. The key is a parameter, so a future part-level policy is a one-line
change here and nowhere else.

RENDEZVOUS (HIGHEST-RANDOM-WEIGHT) HASHING, NOT MODULO. ``hash(user) % N``
remaps *every* key when N changes; HRW remaps only the 1/N that belonged to the
worker that left. Scaling from three workers to four therefore costs one
modeler in four a cold cache instead of costing all of them one.

HOW IT DEGRADES — the question that matters more than the happy path:

* **A worker is down.** Its transport failure marks it unhealthy for
  ``FAILURE_COOLDOWN_S`` and the request is immediately retried on the
  next-preferred worker (HRW gives a deterministic, evenly-spread second
  choice, so a dead worker's modelers do not all pile onto one survivor). The
  modeler gets an answer from a cold cache: **slower, never stranded.** Only
  when the retry also fails does the envelope surface.
* **Every worker is down.** The pool refuses to strand anyone: with no healthy
  candidate it picks the top-ranked worker anyway and lets the real transport
  error surface as the honest 502, rather than inventing a "no backend"
  failure of its own.
* **The set changes** (``--scale geometry=N``, a rolling restart). HRW moves
  1/N of modelers; the rest keep their checkpoints. Nothing is invalidated,
  because the affinity is an optimisation and every worker can serve every
  request — a re-routed modeler pays one cold rebuild, once.
* **A worker is SATURATED** (503 ``service_overloaded`` from its admission
  gate) — deliberately NOT re-routed. Failing over on overload is how a
  fan-out turns a busy worker into a busy fleet: it would spray one modeler's
  lineage across every process at exactly the moment cache locality is worth
  most, and it would answer backpressure by generating more load. The 503 is
  relayed with its ``Retry-After`` instead (CONC-2).

The pool holds **one httpx client per worker URL and a failure deadline per
worker**. No request state, no per-user storage: the routing decision is a pure
function of ``(key, url set, healthy set)``, so nothing here can associate one
modeler's data with another's.
"""

import hashlib
import time
from typing import Final

import httpx2 as httpx
from fastapi import Request
from py_kit import get_logger

from gateway.upstream import create_upstream_client, send_upstream, transport_failure

_logger = get_logger("gateway.affinity")

#: How long a worker stays out of the preferred set after a transport failure.
#: Short on purpose: this is a hint that stops a dead process from being
#: re-picked on every request in a burst, not a circuit breaker with a state
#: machine. A worker that came back is re-tried within ten seconds, and the
#: cost of being wrong in either direction is one cold rebuild.
FAILURE_COOLDOWN_S: Final = 10.0


def parse_worker_urls(configured: str) -> list[str]:
    """Split the comma-separated ``GEOMETRY_URL`` into base URLs.

    One variable rather than two (``GEOMETRY_URL`` + a ``GEOMETRY_URLS``) so
    there is no question of which wins: a single URL is the one-worker case of
    a list, and every existing deployment keeps working unchanged.
    """
    urls = [part.strip().rstrip("/") for part in configured.split(",")]
    kept = [url for url in urls if url]
    if not kept:
        raise ValueError("GEOMETRY_URL must name at least one base URL")
    # Deduplicate, order-preserving: a repeated URL would win the HRW draw
    # twice as often and silently skew the fan-out.
    seen: set[str] = set()
    unique: list[str] = []
    for url in kept:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _rank(key: str, url: str) -> bytes:
    """The HRW weight of *url* for *key* — a stable, uniform pseudo-random draw.

    blake2b rather than :func:`hash`: Python's string hash is salted per
    process, so two gateway replicas would disagree about where a modeler
    belongs and each would hold half their lineages.
    """
    return hashlib.blake2b(f"{key}\x00{url}".encode(), digest_size=16).digest()


class GeometryPool:
    """One client per geometry worker, plus the mapping from modeler to worker."""

    def __init__(
        self,
        urls: list[str],
        *,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._urls = urls
        self._timeout_s = timeout_s
        self._clients = {
            url: create_upstream_client(url, timeout_s=timeout_s, transport=transport)
            for url in urls
        }
        self._unhealthy_until: dict[str, float] = {}

    @property
    def timeout_s(self) -> float:
        """The per-request read budget these clients were built with."""
        return self._timeout_s

    @property
    def urls(self) -> list[str]:
        """The configured worker base URLs, in configuration order."""
        return list(self._urls)

    @property
    def size(self) -> int:
        return len(self._urls)

    def client(self, url: str) -> httpx.AsyncClient:
        """The lifespan-owned client for one worker URL."""
        return self._clients[url]

    def healthy_urls(self) -> list[str]:
        """Workers not currently inside a failure cooldown."""
        now = time.monotonic()
        return [url for url in self._urls if self._unhealthy_until.get(url, 0.0) <= now]

    def pick(self, key: str, *, exclude: frozenset[str] = frozenset()) -> str:
        """The worker this modeler belongs on, by rendezvous hash.

        Prefers healthy workers; falls back to the full set rather than
        stranding a modeler when everything is in cooldown (a cooldown is a
        hint, and "no backend" is a failure this layer must never invent).
        """
        candidates = [url for url in self.healthy_urls() if url not in exclude]
        if not candidates:
            candidates = [url for url in self._urls if url not in exclude]
        if not candidates:
            candidates = list(self._urls)
        return max(candidates, key=lambda url: _rank(key, url))

    def mark_down(self, url: str, reason: str) -> None:
        """Take *url* out of the preferred set for :data:`FAILURE_COOLDOWN_S`."""
        self._unhealthy_until[url] = time.monotonic() + FAILURE_COOLDOWN_S
        _logger.warning("geometry_worker_unhealthy", worker=url, reason=reason)

    def mark_up(self, url: str) -> None:
        """Clear a cooldown after a successful call."""
        if self._unhealthy_until.pop(url, None) is not None:
            _logger.info("geometry_worker_recovered", worker=url)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()


#: Transport failures that mean "this PROCESS is not answering", i.e. another
#: worker would do better. A READ timeout is deliberately excluded: it means
#: the worker accepted the work and is busy with it, so re-routing would
#: duplicate a 40-second rebuild onto a second core and throw away the
#: checkpoint the first one is about to bank (docs/PERF.md §5).
_WORKER_DOWN: Final = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


def geometry_pool(http_request: Request) -> GeometryPool:
    """The lifespan-owned pool on ``app.state``."""
    pool: GeometryPool = http_request.app.state.geometry_pool
    return pool


async def forward_geometry(
    http_request: Request,
    affinity_key: str,
    method: str,
    path: str,
    *,
    service: str,
    json_content: str | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """Forward to the geometry worker this modeler is pinned to.

    Falls over to the next-preferred worker **once**, and only when the failure
    says the process is not answering (see :data:`_WORKER_DOWN`). One retry, not
    a sweep: a fleet-wide retry loop turns a slow upstream into an amplified
    load spike, and the second-choice worker is already a different process on
    (in the shipped topology) a different core.
    """
    pool = geometry_pool(http_request)
    target = pool.pick(affinity_key)
    try:
        response = await send_upstream(
            pool.client(target),
            http_request,
            method,
            path,
            json_content=json_content,
            params=params,
        )
    except httpx.HTTPError as exc:
        failover = isinstance(exc, _WORKER_DOWN) and pool.size > 1
        if not failover:
            raise transport_failure(
                exc, service=service, budget_s=pool.timeout_s
            ) from exc
        pool.mark_down(target, type(exc).__name__)
        standby = pool.pick(affinity_key, exclude=frozenset({target}))
        _logger.info("geometry_failover", from_worker=target, to_worker=standby)
        try:
            response = await send_upstream(
                pool.client(standby),
                http_request,
                method,
                path,
                json_content=json_content,
                params=params,
            )
        except httpx.HTTPError as retry_exc:
            pool.mark_down(standby, type(retry_exc).__name__)
            raise transport_failure(
                retry_exc, service=service, budget_s=pool.timeout_s
            ) from retry_exc
        pool.mark_up(standby)
        return response
    pool.mark_up(target)
    return response
