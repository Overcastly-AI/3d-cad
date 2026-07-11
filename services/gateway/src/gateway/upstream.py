"""Gateway → upstream Loft-service forwarding (shared by geometry, parts).

Extracted on its second real use (geometry proxy → documents aggregation,
CLAUDE.md DRY rule). One error strategy everywhere: transport failures
(connect refused, timeout) become the py-kit 502 ``upstream_unavailable``
envelope; upstream error *responses* (already py-kit envelopes) are
re-surfaced with their code/message/details under the gateway's own request
id. Raw stacks never reach the client.
"""

from typing import Any, NoReturn

import httpx2 as httpx
from fastapi import Request
from py_kit import REQUEST_ID_HEADER, ApiError, UpstreamUnavailableError


def create_upstream_client(
    base_url: str,
    *,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build an upstream client (owned by the gateway app's lifespan).

    ``transport`` exists so tests can inject an ``httpx.MockTransport``;
    ``None`` (production) selects the default network transport.
    """
    return httpx.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)


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
    """Forward to an upstream service, mapping transport failures to 502.

    The gateway request id is always propagated so per-service logs
    correlate; ``json_content`` is a pre-serialized DTO body (the routes
    validate with the shared py-kit models before anything goes upstream);
    ``params`` are query parameters, already validated the same way.
    """
    request_headers: dict[str, str] = {
        REQUEST_ID_HEADER: http_request.state.request_id,
        **(headers or {}),
    }
    if json_content is not None:
        request_headers["content-type"] = "application/json"
    try:
        return await client.request(
            method,
            path,
            content=json_content,
            headers=request_headers,
            params=params,
        )
    except httpx.HTTPError as exc:
        raise UpstreamUnavailableError(
            f"{service} service is unreachable.",
            # Exception *type* only — str(exc) may leak internal URLs.
            details={"reason": type(exc).__name__},
        ) from exc


def raise_upstream_error(upstream: httpx.Response, *, service: str) -> NoReturn:
    """Re-surface an upstream error response in the gateway's envelope.

    Loft services answer with the py-kit envelope; keep the upstream code,
    message, and details (the gateway stamps its own request id). Anything
    non-envelope collapses to an opaque ``upstream_error`` with the same
    status.
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
    exc = ApiError(message, code=code, details=details)
    exc.status_code = upstream.status_code
    raise exc
