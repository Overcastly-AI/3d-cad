"""Gateway → upstream Loft-service forwarding (shared by geometry, parts).

Extracted on its second real use (geometry proxy → documents aggregation,
CLAUDE.md DRY rule). One error strategy everywhere, and since 2026-08-01 it
distinguishes the two failures it used to conflate:

* **the upstream could not be reached at all** (connect refused, DNS, the
  process is gone) → 502 ``upstream_unavailable``;
* **the upstream was reached and did not answer in time** → 504
  ``upstream_timeout``.

That split is CONC-3, and it was a real defect, not a nicety. A 200-feature
``/overlay`` costs 40.3 s on an idle machine with one user; the gateway gave up
at 30 s and told the modeler *"Geometry service is unreachable"* — about a
healthy process that was mid-rebuild and finished the same request correctly
moments later. The message sent people to look for an outage that did not
exist, three clicks in a row.

Upstream error *responses* (already py-kit envelopes) are re-surfaced with
their code/message/details under the gateway's own request id, including
``Retry-After`` when the upstream set one: geometry's 503
``service_overloaded`` carries a measured retry interval, and dropping the
header on the way through would turn actionable backpressure into a bare
error. Raw stacks never reach the client.
"""

import math
from typing import Any, Final, NoReturn

import httpx2 as httpx
from fastapi import Request
from py_kit import (
    REQUEST_ID_HEADER,
    ApiError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

#: Fallback retry hint (seconds) on a 504 when the client's budget cannot be
#: read off the transport. Small on purpose: the upstream is still working and
#: banking its checkpoint, so a prompt retry is the useful advice.
DEFAULT_TIMEOUT_RETRY_AFTER_S = 5

#: How long a pooled connection may sit idle here before we retire it (CI-3).
#:
#: This number's only job is to be **strictly below the upstream's own
#: keep-alive timeout**, and the margin is the whole fix. Both Loft upstreams
#: are uvicorn with no ``--timeout-keep-alive`` (docker-compose.dev.yml,
#: deploy/docker/service.Dockerfile), so they close an idle connection after
#: uvicorn's default of **5 s** — and httpx's own pool default is **5.0 s**
#: too. Equal timeouts are the idle keep-alive race: the client believes a
#: connection is reusable at the same instant the server is closing it, the
#: request lands on a socket the peer has already torn down, and the kernel
#: answers the unread bytes with RST. httpx surfaces that as ``ReadError``,
#: :func:`transport_failure` maps it to 502 ``upstream_unavailable``, and a
#: modeler is told "Documents service is unreachable" about a healthy service.
#: Measured on 2026-08-11 (commit aea990a, whose diff touches only
#: scripts/stage-doc-hunks.py and CLAUDE.md): e2e sketch-drag-draw died in
#: ``createPartViaApi`` with exactly that envelope, ``details.reason``
#: ``"ReadError"``.
#:
#: Retiring first CLOSES the race instead of papering over it, which is why
#: this is not the geometry treatment. :data:`gateway.affinity._WORKER_DOWN`
#: fails a ``ReadError`` over to another worker, and that is only sound
#: because geometry is a fan-out of interchangeable stateless processes.
#: Documents is a SINGLE instance with no peer to fail over to, and a
#: ``ReadError`` means the request WAS transmitted — so retrying a
#: ``POST /api/v1/parts`` would risk a duplicate part. Deliberately no retry
#: here: the client simply never offers the transport a stale connection.
#:
#: The cost of the margin is a fresh TCP handshake for connections idle
#: longer than this, on a link that is loopback in compose and intra-cluster
#: in k8s. Bursty traffic — a modeler editing features — keeps reusing.
UPSTREAM_KEEPALIVE_EXPIRY_S: Final = 2.0

#: httpx's pool defaults, with the expiry above swapped in. The two ceilings
#: are httpx's own documented defaults (100 / 20) and are pinned against the
#: library in tests/test_documents_keepalive.py, so a library change shows up
#: as a failing assertion rather than as a silently different pool.
UPSTREAM_LIMITS: Final = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=UPSTREAM_KEEPALIVE_EXPIRY_S,
)


def create_upstream_client(
    base_url: str,
    *,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build an upstream client (owned by the gateway app's lifespan).

    ``transport`` exists so tests can inject an ``httpx.MockTransport``;
    ``None`` (production) selects the default network transport.

    **Asks upstreams for ``identity``** (httpx would otherwise advertise
    ``gzip, deflate``). The gateway BUFFERS every upstream body and re-emits
    it, so anything geometry compresses the gateway immediately decompresses
    and then re-compresses for the browser — two compressions and a
    decompression per mesh fetch, for a link that is loopback in compose and
    intra-cluster in k8s. Measured on the docs/PERF.md N=200 tray (1 117 KiB):
    compressing at geometry costs **20.6 ms** plus **3.6 ms** to inflate here,
    to save **2.6 ms** of internal transfer — a ~24 ms net loss on the scarcest
    resource in the stack (geometry CPU is what rebuild is bound by). Browser
    compression is unaffected: py-kit's ``GZipMiddleware`` still gzips the
    gateway's OWN response, which is the hop that faces the wire that matters.
    See docs/PERF.md PERF-4.

    **Retires idle pooled connections early** (:data:`UPSTREAM_LIMITS`) so a
    request is never written onto a keep-alive connection the upstream is
    closing at that moment — CI-3, the 502 ``upstream_unavailable`` that
    modelers saw about a healthy documents service. ``limits`` is ignored when
    a ``transport`` is injected: a ``MockTransport`` has no connection pool.
    """
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout_s,
        transport=transport,
        limits=UPSTREAM_LIMITS,
        headers={"accept-encoding": "identity"},
    )


def _read_budget_s(client: httpx.AsyncClient) -> float | None:
    """The client's read timeout, for the 504 message. Best-effort by design."""
    read: object = getattr(getattr(client, "timeout", None), "read", None)
    return float(read) if isinstance(read, (int, float)) else None


def transport_failure(
    exc: httpx.HTTPError, *, service: str, budget_s: float | None = None
) -> ApiError:
    """Map a transport failure to the envelope that is TRUE of it.

    A timeout means "we stopped waiting", which is a statement about the
    gateway's patience, not about the upstream's health — and it matters that
    the client hears the difference, because the two have opposite remedies
    (retry vs. go find out what is down). The 504 also says the thing that is
    operationally useful and was previously invisible: **the upstream did not
    stop working.** Nothing here cancels it, on purpose — geometry banks the
    abandoned rebuild's checkpoint in its per-process rebuild cache as it
    completes, and the measured consequence is that the retry is served from
    that checkpoint (40.3 s cold → 22.7 s on the retry, docs/PERF.md §5). Free
    progress; cancelling would throw it away.
    """
    if isinstance(exc, httpx.TimeoutException):
        budget = f"within {budget_s:.0f} s" if budget_s is not None else "in time"
        retry_after_s = (
            max(1, math.ceil(budget_s / 4))
            if budget_s
            else DEFAULT_TIMEOUT_RETRY_AFTER_S
        )
        return UpstreamTimeoutError(
            f"{service} did not answer {budget}. It is still working on this "
            "request — this is a large part, not an outage — and its progress "
            "is cached, so retrying costs less than the first attempt.",
            retry_after_s=retry_after_s,
            details={"reason": type(exc).__name__, "budget_s": budget_s},
        )
    return UpstreamUnavailableError(
        f"{service} service is unreachable.",
        # Exception *type* only — str(exc) may leak internal URLs.
        details={"reason": type(exc).__name__},
    )


async def send_upstream(
    client: httpx.AsyncClient,
    http_request: Request,
    method: str,
    path: str,
    *,
    json_content: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """Forward to an upstream, letting ``httpx.HTTPError`` propagate RAW.

    The seam :mod:`gateway.affinity` needs: deciding whether to re-route a
    modeler to a different geometry worker requires knowing *which* transport
    failure happened, and that information is destroyed the moment the failure
    becomes an envelope. Callers that do not route use :func:`forward`.
    """
    request_headers: dict[str, str] = {
        REQUEST_ID_HEADER: http_request.state.request_id,
        **(headers or {}),
    }
    if json_content is not None:
        request_headers["content-type"] = "application/json"
    return await client.request(
        method,
        path,
        content=json_content,
        headers=request_headers,
        params=params,
    )


async def forward(
    client: httpx.AsyncClient,
    http_request: Request,
    method: str,
    path: str,
    *,
    service: str,
    json_content: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """Forward to an upstream service, mapping transport failures to envelopes.

    The gateway request id is always propagated so per-service logs
    correlate; ``json_content`` is a pre-serialized DTO body (the routes
    validate with the shared py-kit models before anything goes upstream);
    ``params`` are query parameters, already validated the same way.
    """
    try:
        return await send_upstream(
            client,
            http_request,
            method,
            path,
            json_content=json_content,
            headers=headers,
            params=params,
        )
    except httpx.HTTPError as exc:
        raise transport_failure(
            exc, service=service, budget_s=_read_budget_s(client)
        ) from exc


def raise_upstream_error(upstream: httpx.Response, *, service: str) -> NoReturn:
    """Re-surface an upstream error response in the gateway's envelope.

    Loft services answer with the py-kit envelope; keep the upstream code,
    message, and details (the gateway stamps its own request id). Anything
    non-envelope collapses to an opaque ``upstream_error`` with the same
    status.

    ``Retry-After`` is relayed when present. Geometry's admission control
    computes it from that worker's own measured service time (CONC-2), so it is
    the one header in the stack whose value the gateway could not reconstruct
    and must not silently drop.
    """
    try:
        error: dict[str, Any] = upstream.json()["error"]
        code = str(error["code"])
        message = str(error["message"])
        details = error.get("details")
    except (ValueError, KeyError, TypeError):
        code, message, details = (
            "upstream_error",
            f"{service} service returned an error.",
            None,
        )
    retry_after = upstream.headers.get("retry-after")
    exc = ApiError(
        message,
        code=code,
        details=details,
        headers={"Retry-After": retry_after} if retry_after else None,
    )
    exc.status_code = upstream.status_code
    raise exc
