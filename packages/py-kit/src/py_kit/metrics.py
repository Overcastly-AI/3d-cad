"""Prometheus metrics — wired ONCE here, inherited by all three services.

Loft had `/healthz`, `/readyz` and structured logs, and nothing else. That is
enough to answer "is it up?" and nothing else, and for a CAD tool that is the
wrong question: `docs/PERF.md` measures a *legitimate* rebuild at 26 s on a
200-feature part, so an operator staring at a hung-looking UI cannot tell a big
part from an incident. This module exports the handful of numbers that make that
distinguishable — and deliberately not a generic HTTP dashboard.

WHAT IS EXPORTED, AND WHY EACH ONE EARNS ITS PLACE (the full operator-facing
version, with healthy-vs-struggling readings, is `docs/OBSERVABILITY.md`):

* **``loft_rebuild_duration_seconds``** — a HISTOGRAM, because the distribution
  is the whole story: docs/PERF.md measures 0.6 s at 25 features and 26 s at 200,
  so a mean over a mixed workload describes no request that ever happened. Bucket
  boundaries include **2 s**, the RESEARCH §9 interactive ceiling, so "what
  fraction of rebuilds felt instant" is one PromQL expression.
* **the rebuild cache** (hits / misses / stores / evictions) — the LRU is
  per-process (:mod:`geometry.rebuild_cache`), so an operator who raises
  ``WEB_CONCURRENCY`` splits it N ways and each worker sees a colder cache. This
  is the metric that says whether their worker count is fighting the cache, and
  there is no other way to see it.
* **``loft_feature_errors_total{code}``** — ``shell_thickness_too_large`` spiking
  is a user learning the tool; ``invalid_body`` spiking is a defect;
  ``import_parse_timeout`` spiking is a DoS bound biting real files (which it
  did, until PERF-3). Three very different pages, one metric.
* **STEP import duration + refusals** — the CPU ceiling was measured at ~3x
  headroom over the worst file the upload cap admits (docs/PERF.md PERF-3). A
  self-hoster whose users hit it deserves to see it rather than guess.
* **ordinary HTTP rate / latency / status, and process + GC basics** — the floor
  under all of the above.

A METRIC MUST NOT LIE. Two rules follow, and both shaped the code below:

1. **Instrument at a seam that cannot be bypassed.** Not at 85 individual
   ``FeatureError(...)`` raise sites (a counter that silently stops incrementing
   when someone adds an 86th is this repo's "gate that cannot fail" in another
   costume) but at the DTO every one of them constructs; not at each
   ``evaluate_tree`` caller but inside the prefix cache the evaluator consults
   unconditionally; not at each STEP reader but in the one bounded worker both
   readers run through.
2. **Every counter has a test that asserts its DELTA** — that the number MOVES
   when the event happens — never merely that the metric name is present.
   ``packages/py-kit/tests/test_metrics.py`` and
   ``services/geometry/tests/test_metrics_seams.py``.

CARDINALITY DISCIPLINE. A self-hoster runs one Prometheus on the same box as the
CAD kernel; blowing it up is a real way to hurt them. So: **no label is ever a
part id, user id, feature id, request id, or raw URL path.** The HTTP label is
the route TEMPLATE (``/api/v1/parts/{part_id}``) taken from the matched route,
and an unmatched path collapses to a single
:data:`UNMATCHED_ROUTE` — otherwise one scanner spraying random URLs would mint a
time series per URL. The one free-form label in the product (a feature error
``code``, a plain ``str`` on the contract DTO) is additionally capped at
:data:`MAX_DISTINCT_CODES` distinct values per process, with the overflow folded
into ``other``. There is deliberately no ``service`` label: each service serves
its own ``/metrics``, so the scrape's ``job``/``instance`` already carry that,
and a constant label on every series is pure waste. Full arithmetic in
``docs/OBSERVABILITY.md``.

EXPOSURE POSTURE — ``/metrics`` is NOT public by default. It reuses the ONE
posture variable this stack already has (``LOFT_ENV``, :mod:`py_kit.config`), so
it reads as the same policy as the JWT and datastore-credential guards rather
than a fourth thing to learn:

* ``LOFT_ENV=dev`` — open. A localhost stack should just work.
* anything else (i.e. any real deployment) — a bearer token is REQUIRED, and
  without ``METRICS_TOKEN`` configured the route answers **404**, not 403: a
  probe cannot even learn that metrics exist here.

Deliberately not IP-based. The tempting version — "allow loopback peers" — is
worse than useless behind a reverse proxy, which is how a self-hoster terminates
TLS: nginx on the same host connects from 127.0.0.1, so a loopback allowlist
would hand ``/metrics`` to the public internet while looking careful. A shared
secret is checkable and cannot be spoofed by topology.

The dependency is ``prometheus-client`` (**Apache-2.0**, no GPL/AGPL — CLAUDE.md
licence rule; and it has zero required runtime dependencies of its own, which is
the right shape for a self-host image).
"""

import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Final

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from py_kit.config import BaseServiceSettings, is_dev_env

__all__ = [
    "ADMISSION_ABANDONED",
    "ADMISSION_IN_FLIGHT",
    "ADMISSION_QUEUED",
    "ADMISSION_REJECTED",
    "ADMISSION_WAIT",
    "MAX_DISTINCT_CODES",
    "METRICS_PATH",
    "REGISTRY",
    "UNMATCHED_ROUTE",
    "install_metrics",
    "note_rebuild",
    "observe_step_import",
    "record_feature_error",
    "record_rebuild_cache_eviction",
    "record_rebuild_cache_hit",
    "record_rebuild_cache_miss",
    "record_rebuild_cache_store",
]

#: Where the exposition lives. Infrastructure, like ``/healthz`` — deliberately
#: NOT under ``/api/v1`` and excluded from the OpenAPI schema, so it is not part
#: of the versioned contract and never reaches the generated TS client.
METRICS_PATH: Final = "/metrics"

#: The route label for a request that matched no route (404s, scanners, typos).
#: WITHOUT this collapse, ``route`` would be the raw URL path and one bot could
#: mint an unbounded number of time series in a self-hoster's Prometheus. It is
#: the single most important cardinality control in this module.
UNMATCHED_ROUTE: Final = "<unmatched>"

#: Cap on distinct ``code`` label values per process for feature errors. The
#: product has ~85 literal codes today and every one is a constant, so this is a
#: guard against a FUTURE interpolated code (``f"...{part_id}"``), not against
#: today's set — the failure it prevents is silent and unbounded, so it is worth
#: the eight lines. Overflow folds into ``other``: the total stays true even
#: when the breakdown stops being complete.
MAX_DISTINCT_CODES: Final = 128

#: Latency buckets, in seconds, sized for CAD rather than for a CRUD API.
#: Prometheus' default top bucket is 10 s, which would put EVERY rebuild of a
#: 100-feature part (7.5 s), a 200-feature part (26 s) and a 2 006-face STEP
#: export in the same terminal bucket — i.e. exactly the requests an operator
#: needs to tell apart would be indistinguishable. **2 s is a boundary on
#: purpose**: it is the RESEARCH §9 interactive ceiling, so
#: ``rate(..._bucket{le="2"}[5m]) / rate(..._count[5m])`` is literally "the
#: fraction of rebuilds that felt like a tool".
LATENCY_BUCKETS: Final = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    20.0,
    30.0,
    60.0,
    float("inf"),
)

#: STEP-import buckets. **20 s is a boundary on purpose**: it is
#: ``DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S``, the DoS ceiling, so an operator can see
#: imports approaching the wall before they start being refused by it.
STEP_IMPORT_BUCKETS: Final = (
    0.25,
    0.5,
    1.0,
    2.0,
    4.0,
    8.0,
    16.0,
    20.0,
    30.0,
    60.0,
    float("inf"),
)

#: Feature-count bands for the rebuild histogram's ``tree_size`` label. Chosen
#: to straddle the wall docs/PERF.md measured rather than to be round: "fine"
#: (<=25), "a modeller waits" (26-50), "painful" (51-100), "unusable" (101-200),
#: past the measured corpus (201+). Six bounded values — a raw feature count
#: would be a fine label too and is exactly the kind of creeping cardinality
#: this module refuses.
_TREE_SIZE_BANDS: Final[tuple[tuple[int, str], ...]] = (
    (10, "1-10"),
    (25, "11-25"),
    (50, "26-50"),
    (100, "51-100"),
    (200, "101-200"),
)
_TREE_SIZE_OVERFLOW: Final = "201+"

#: A DEDICATED registry, not ``prometheus_client.REGISTRY``. The default registry
#: is process-global and any dependency may register into it; owning ours keeps
#: the exposition exactly what this module declares and lets tests read a
#: sample's value without racing another test's collectors.
REGISTRY: Final = CollectorRegistry()

# Process + GC basics. ProcessCollector reads /proc (Linux; a no-op elsewhere)
# for RSS, CPU seconds, open FDs; GCCollector reports collections and
# uncollectable objects per generation — the two things that make "the service
# got slow" separable into "it is swapping", "it is CPU-saturated" and "it is
# thrashing the allocator", which on an OCCT workload is a real question
# (docs/PERF.md: ~500 MiB of OCCT baseline RSS before any part is loaded).
ProcessCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)
GCCollector(registry=REGISTRY)

SERVICE_INFO: Final = Info(
    "loft_service",
    "Identity of the process serving this /metrics endpoint.",
    registry=REGISTRY,
)

# --- HTTP -------------------------------------------------------------------

HTTP_REQUESTS: Final = Counter(
    "loft_http_requests",
    "HTTP requests completed, by method, matched route template and status.",
    ("method", "route", "status"),
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION: Final = Histogram(
    "loft_http_request_duration_seconds",
    "Wall time from first byte of request to last byte of response handed to "
    "the server, by method and matched route template.",
    ("method", "route"),
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)

HTTP_REQUESTS_IN_FLIGHT: Final = Gauge(
    "loft_http_requests_in_flight",
    "Requests currently being served. Sustained values near the worker count "
    "mean the process is saturated, not merely busy.",
    registry=REGISTRY,
)

# --- rebuild ----------------------------------------------------------------

REBUILD_DURATION: Final = Histogram(
    "loft_rebuild_duration_seconds",
    "Wall time of an HTTP request that evaluated at least one feature tree, by "
    "how much of the tree the prefix cache served and how big the tree was. "
    "This is what a modeller waits, so it includes tessellation and response "
    "encoding, not an isolated kernel timing.",
    ("cache", "tree_size"),
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)

REBUILD_FEATURES_EVALUATED: Final = Counter(
    "loft_rebuild_features_evaluated",
    "Features actually evaluated by the kernel (cache misses did the work).",
    registry=REGISTRY,
)

REBUILD_FEATURES_RESUMED: Final = Counter(
    "loft_rebuild_features_resumed",
    "Features NOT re-evaluated because a cached prefix supplied them. The "
    "product's headline saving: resumed/(resumed+evaluated) is the fraction of "
    "kernel work the rebuild cache is removing.",
    registry=REGISTRY,
)

REBUILD_CACHE_HITS: Final = Counter(
    "loft_rebuild_cache_hits",
    "Rebuilds that resumed from a cached feature-tree prefix.",
    registry=REGISTRY,
)

REBUILD_CACHE_MISSES: Final = Counter(
    "loft_rebuild_cache_misses",
    "Rebuilds that found no usable cached prefix and rebuilt from feature 0.",
    registry=REGISTRY,
)

REBUILD_CACHE_STORES: Final = Counter(
    "loft_rebuild_cache_stores",
    "Checkpoints handed to the prefix cache once their evaluation was released.",
    registry=REGISTRY,
)

REBUILD_CACHE_EVICTIONS: Final = Counter(
    "loft_rebuild_cache_evictions",
    "Checkpoints dropped because the per-process LRU was full. Sustained "
    "evictions alongside a poor hit rate mean the working set exceeds the "
    "cache, usually because worker count split it.",
    registry=REGISTRY,
)

# --- feature evaluation -----------------------------------------------------

FEATURE_ERRORS: Final = Counter(
    "loft_feature_errors",
    "Feature evaluations that failed, by machine-readable error code.",
    ("code",),
    registry=REGISTRY,
)

# --- STEP import ------------------------------------------------------------

STEP_IMPORT_DURATION: Final = Histogram(
    "loft_step_import_duration_seconds",
    "Wall time of the bounded, killable STEP parse worker, by outcome.",
    ("outcome",),
    buckets=STEP_IMPORT_BUCKETS,
    registry=REGISTRY,
)

STEP_IMPORT_REFUSALS: Final = Counter(
    "loft_step_import_refusals",
    "STEP imports refused by a resource bound rather than by bad input: "
    "cpu_timeout (the RLIMIT_CPU DoS ceiling), wall_timeout (the wedged-child "
    "backstop), too_many_products (the assembly occurrence ceiling).",
    ("reason",),
    registry=REGISTRY,
)


# --- admission control ------------------------------------------------------
#
# The queue in front of the OCCT routes (:mod:`py_kit.admission`, docs/PERF.md
# CONC-2). These four exist because "the service is slow" and "the service is
# shedding load" look identical from the outside and demand opposite responses:
# the first is a part-size problem, the second is a worker-count problem. The
# queue gauge is the number an operator sizes `--scale geometry=N` from, and
# the rejection counter — broken out by REASON — says whether the bound that
# bit was the depth cap, the measured-rate prediction, or the wait budget.

ADMISSION_IN_FLIGHT: Final = Gauge(
    "loft_admission_in_flight",
    "Requests currently INSIDE the bounded CPU section (<= the configured "
    "concurrency). Pinned at the bound means the worker is saturated.",
    registry=REGISTRY,
)

ADMISSION_QUEUED: Final = Gauge(
    "loft_admission_queued",
    "Requests waiting for admission to the bounded CPU section. Persistently "
    "above zero means this worker has more modelers than it can serve.",
    registry=REGISTRY,
)

ADMISSION_WAIT: Final = Histogram(
    "loft_admission_wait_seconds",
    "Time spent queueing before admission — the latency the queue ADDS, "
    "separable from the rebuild time itself (loft_rebuild_duration_seconds).",
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)

ADMISSION_REJECTED: Final = Counter(
    "loft_admission_rejected",
    "Requests refused (503 service_overloaded) before any work started, by "
    "reason: queue_full (the depth cap), predicted_wait (the measured service "
    "rate says it cannot be served in the budget), wait_timeout (it waited and "
    "the budget ran out).",
    ("reason",),
    registry=REGISTRY,
)

ADMISSION_ABANDONED: Final = Counter(
    "loft_admission_abandoned",
    "Requests dropped at the front of the queue because the client had already "
    "disconnected — CPU this worker did NOT spend on an answer nobody would "
    "read.",
    registry=REGISTRY,
)


# --- cardinality guard ------------------------------------------------------

_codes_lock: Final = threading.Lock()
_seen_codes: set[str] = set()


def _bounded_code(code: str) -> str:
    """*code*, or ``"other"`` once this process has seen too many distinct ones.

    See :data:`MAX_DISTINCT_CODES`. Once the cap is reached the set stops
    growing, so the guard's own memory is bounded too.
    """
    with _codes_lock:
        if code in _seen_codes:
            return code
        if len(_seen_codes) >= MAX_DISTINCT_CODES:
            return "other"
        _seen_codes.add(code)
        return code


# --- domain recorders -------------------------------------------------------
#
# These are Loft-domain events, not generic HTTP plumbing, and they live in
# py-kit for the reason every cross-service seam does (CLAUDE.md DRY): the
# alternative is each service growing its own registry, its own metric names and
# its own middleware, i.e. three copies of a thing that must agree to be
# scrapeable at all. The call sites stay one line each in the service that owns
# the event.


def record_feature_error(code: str) -> None:
    """Count one failed feature evaluation.

    Called from :meth:`py_kit.schemas.features.FeatureError.model_post_init` —
    the contract DTO every feature failure in the product is rendered through.
    """
    FEATURE_ERRORS.labels(code=_bounded_code(code)).inc()


def record_rebuild_cache_hit() -> None:
    """Count a prefix-cache hit (called by ``PrefixCache.take``)."""
    REBUILD_CACHE_HITS.inc()


def record_rebuild_cache_miss() -> None:
    """Count a prefix-cache miss (called by ``PrefixCache.take``)."""
    REBUILD_CACHE_MISSES.inc()


def record_rebuild_cache_store() -> None:
    """Count a checkpoint entering the cache (called by ``PrefixCache.store``)."""
    REBUILD_CACHE_STORES.inc()


def record_rebuild_cache_eviction() -> None:
    """Count an LRU eviction (called by ``PrefixCache.store``)."""
    REBUILD_CACHE_EVICTIONS.inc()


def observe_step_import(seconds: float, *, outcome: str) -> None:
    """Record one bounded STEP parse: its duration and, if refused, why.

    Called from ``geometry.kernel.imports.run_bounded_parse_worker`` — the single
    seam both the single-body reader and the assembly XCAF reader run their
    untrusted parse through, so neither can grow a path that skips this.
    """
    STEP_IMPORT_DURATION.labels(outcome=outcome).observe(seconds)
    if outcome in ("cpu_timeout", "wall_timeout", "too_many_products"):
        STEP_IMPORT_REFUSALS.labels(reason=outcome).inc()


# --- rebuild attribution ----------------------------------------------------


@dataclass
class _RebuildProfile:
    """What the feature-tree rebuilds inside ONE request added up to.

    Mutable and stored in a :class:`~contextvars.ContextVar` because the two
    halves live in different places: the middleware knows when the request
    started and ended, and only the prefix cache knows how many features were
    evaluated versus resumed. FastAPI runs sync route handlers via
    ``run_in_threadpool``, which COPIES the context — so the worker thread sees
    this same object and its mutations are visible back here, whereas rebinding
    the ContextVar inside the thread would not be. That is why the shared state
    is an object rather than a counter in the variable itself.
    """

    rebuilds: int = 0
    evaluated: int = 0
    resumed: int = 0
    largest_tree: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def note(self, *, features: int, resumed: int) -> None:
        with self.lock:
            self.rebuilds += 1
            self.evaluated += features - resumed
            self.resumed += resumed
            self.largest_tree = max(self.largest_tree, features)

    @property
    def cache_label(self) -> str:
        """``hit`` when nothing had to be evaluated, ``miss`` when nothing was
        resumed, ``partial`` in between (the append case: one new feature on a
        long cached prefix)."""
        if self.evaluated == 0:
            return "hit"
        if self.resumed == 0:
            return "miss"
        return "partial"


_rebuild_profile: ContextVar[_RebuildProfile | None] = ContextVar(
    "loft_rebuild_profile", default=None
)


def note_rebuild(*, features: int, resumed: int) -> None:
    """Record that a feature tree of *features* features was rebuilt, *resumed*
    of them supplied by the prefix cache.

    Also moves the two feature counters, which — unlike the duration histogram —
    are exact and meaningful outside an HTTP request (a worker, a CLI, a test).
    The duration is attributed by the middleware, which is the only party that
    knows when the request began; a rebuild with no request around it is counted
    but not timed, and ``docs/OBSERVABILITY.md`` says so rather than pretending
    otherwise.
    """
    REBUILD_FEATURES_EVALUATED.inc(features - resumed)
    REBUILD_FEATURES_RESUMED.inc(resumed)
    profile = _rebuild_profile.get()
    if profile is not None:
        profile.note(features=features, resumed=resumed)


def _tree_size_label(features: int) -> str:
    for upper, label in _TREE_SIZE_BANDS:
        if features <= upper:
            return label
    return _TREE_SIZE_OVERFLOW


# --- ASGI middleware --------------------------------------------------------


class MetricsMiddleware:
    """Pure-ASGI request instrumentation (NOT ``BaseHTTPMiddleware``).

    ``BaseHTTPMiddleware`` wraps every request in an anyio task group and a
    streaming bridge; that cost is fine for the one request-id middleware the
    factory already pays for, and gratuitous for a stopwatch. This is the raw
    three-argument form, so the added work per request is a ``perf_counter``
    pair, a dict lookup and two metric updates — measured in
    ``docs/OBSERVABILITY.md``.

    THE ROUTE LABEL IS THE TEMPLATE, NOT THE PATH — and it is read from
    ``scope["route"]``, which FastAPI sets on the SHARED scope dict when a route
    matches, so an outer middleware sees it after the inner call returns.
    ``route.path`` is the fully-prefixed template
    (``/api/v1/parts/{part_id}``), which matters: since FastAPI 0.139
    ``include_router`` does NOT flatten its routes into ``app.routes`` (they hide
    behind ``_IncludedRouter``), so the obvious "build an endpoint → path map
    from ``app.routes``" walks right past every API route in the product and
    labels them all ``<unmatched>``. That version was written, and it passed its
    unit tests — because those registered routes with ``@app.get`` rather than
    through a router. It was caught by pointing it at the real gateway.
    ``test_route_label_survives_include_router`` now pins the real shape.
    A request that matched nothing has no ``route`` and collapses to
    :data:`UNMATCHED_ROUTE`.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    @staticmethod
    def _template_for(route: object | None) -> str:
        """The matched route's path template, or :data:`UNMATCHED_ROUTE`."""
        path = getattr(route, "path", None)
        return path if isinstance(path, str) else UNMATCHED_ROUTE

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = 500  # an exception escaping the app is a 500 to the client
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        profile = _RebuildProfile()
        token = _rebuild_profile.set(profile)
        HTTP_REQUESTS_IN_FLIGHT.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            HTTP_REQUESTS_IN_FLIGHT.dec()
            _rebuild_profile.reset(token)
            method = str(scope.get("method", "GET"))
            route = self._template_for(scope.get("route"))
            HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(elapsed)
            if profile.rebuilds:
                REBUILD_DURATION.labels(
                    cache=profile.cache_label,
                    tree_size=_tree_size_label(profile.largest_tree),
                ).observe(elapsed)


# --- exposition -------------------------------------------------------------


def metrics_authorized(request: Request, settings: BaseServiceSettings) -> bool:
    """Whether *request* may read ``/metrics`` (see the module docstring).

    ``LOFT_ENV=dev`` is open; every other posture requires the configured
    ``METRICS_TOKEN`` as an RFC 6750 bearer token. Compared with
    :func:`secrets.compare_digest` — a scrape endpoint is hit continuously, which
    is exactly the setting where a timing oracle on a shared secret is worth
    something to an attacker.
    """
    if is_dev_env(settings.loft_env):
        return True
    token = settings.metrics_token
    if token is None or not token.strip():
        return False
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    # Local import keeps the module's import cost to what a service always needs.
    from secrets import compare_digest

    return compare_digest(presented.strip(), token.strip())


def install_metrics(app: FastAPI, settings: BaseServiceSettings) -> None:
    """Add request instrumentation and the ``/metrics`` route to *app*.

    Called by :func:`py_kit.app.create_app`, so no service registers it and no
    service can forget to. A no-op when ``METRICS_ENABLED=false``: the middleware
    is not installed (zero per-request cost, not merely unrecorded) and the route
    does not exist, which is the same 404 an unauthorized caller sees.
    """
    if not settings.metrics_enabled:
        return

    SERVICE_INFO.info({"service": settings.service_name, "version": app.version})

    # Registered LAST, so it is OUTERMOST (Starlette applies user middleware
    # outermost-last): the measured time then includes gzip and the request-id
    # middleware, i.e. everything the client actually waits for, and the in-flight
    # gauge counts a request from the moment it enters the app.
    app.add_middleware(MetricsMiddleware)

    # Sync def ON PURPOSE: FastAPI runs it in the threadpool, so serialising a
    # few thousand samples cannot stall the event loop and every other in-flight
    # request with it.
    @app.get(METRICS_PATH, include_in_schema=False)
    def metrics(request: Request) -> Response:
        """Prometheus text exposition (see the module docstring for posture)."""
        if not metrics_authorized(request, settings):
            # 404, not 403: an unauthorized prober learns nothing, and the answer
            # is identical to a stack with METRICS_ENABLED=false.
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        return Response(
            content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST
        )
