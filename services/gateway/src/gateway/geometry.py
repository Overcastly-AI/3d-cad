"""Gateway → geometry tessellation proxy (``/api/v1/geometry/*``).

apps/web talks ONLY to the gateway (CLAUDE.md service boundaries), so the
geometry API is surfaced here. Routes are typed with the shared py-kit DTOs —
the exact models the geometry service serves, never hand-duplicated — and
forward over the lifespan-managed httpx2 ``AsyncClient`` on ``app.state``.

Error strategy: transport failures (connect refused, timeout) become the
py-kit 502 ``upstream_unavailable`` envelope; upstream error *responses*
(already py-kit envelopes) are re-surfaced with their code/message/details
under the gateway's own request id. Raw stacks never reach the client.
"""

from typing import Any, NoReturn

import httpx2 as httpx
from fastapi import APIRouter, Request, Response
from py_kit import REQUEST_ID_HEADER, ApiError, UpstreamUnavailableError
from py_kit.schemas.geometry import (
    GLB_MEDIA_TYPE,
    PROPERTIES_HEADER,
    TessellateRequest,
    TessellationMetadata,
    tessellate_responses,
)

#: Upstream call budget — tessellation is CPU-bound and may take a while.
GEOMETRY_TIMEOUT_S = 30.0

router = APIRouter(prefix="/api/v1/geometry", tags=["geometry"])


def create_geometry_client(
    geometry_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build the upstream client (owned by the gateway app's lifespan).

    ``transport`` exists so tests can inject an ``httpx.MockTransport``;
    ``None`` (production) selects the default network transport.
    """
    return httpx.AsyncClient(
        base_url=geometry_url,
        timeout=GEOMETRY_TIMEOUT_S,
        transport=transport,
    )


async def _forward(
    http_request: Request, path: str, payload: TessellateRequest
) -> httpx.Response:
    """POST *payload* to the geometry service, mapping transport failures."""
    client: httpx.AsyncClient = http_request.app.state.geometry_client
    try:
        return await client.post(
            path,
            content=payload.model_dump_json(),
            headers={
                "content-type": "application/json",
                # Propagate the request id so gateway/geometry logs correlate.
                REQUEST_ID_HEADER: http_request.state.request_id,
            },
        )
    except httpx.HTTPError as exc:
        raise UpstreamUnavailableError(
            "Geometry service is unreachable.",
            # Exception *type* only — str(exc) may leak internal URLs.
            details={"reason": type(exc).__name__},
        ) from exc


def _raise_upstream_error(upstream: httpx.Response) -> NoReturn:
    """Re-surface a geometry error response in the gateway's envelope.

    Geometry already answers with the py-kit envelope; keep its code,
    message, and details (the gateway stamps its own request id). Anything
    non-envelope collapses to an opaque upstream_error with the same status.
    """
    try:
        error: dict[str, Any] = upstream.json()["error"]
        code = str(error["code"])
        message = str(error["message"])
        details = error.get("details")
    except (ValueError, KeyError, TypeError):
        code, message, details = (
            "upstream_error",
            "Geometry service returned an error.",
            None,
        )
    exc = ApiError(message, code=code, details=details)
    exc.status_code = upstream.status_code
    raise exc


_TESSELLATE_RESPONSES = tessellate_responses(
    "Binary glTF (GLB) mesh of the requested shape, proxied from the "
    f"geometry service. The `{PROPERTIES_HEADER}` header carries "
    "`TessellationMetadata` as compact JSON (see "
    "`POST /api/v1/geometry/tessellate/meta` for the same payload as "
    "a typed JSON body)."
)


@router.post("/tessellate", response_class=Response, responses=_TESSELLATE_RESPONSES)
async def tessellate(request: TessellateRequest, http_request: Request) -> Response:
    """Build + tessellate on the geometry service; pass the GLB through."""
    upstream = await _forward(http_request, "/api/v1/tessellate", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    headers: dict[str, str] = {}
    if PROPERTIES_HEADER in upstream.headers:
        headers[PROPERTIES_HEADER] = upstream.headers[PROPERTIES_HEADER]
    return Response(
        content=upstream.content,
        media_type=GLB_MEDIA_TYPE,
        headers=headers,
    )


@router.post("/tessellate/meta")
async def tessellate_meta(
    request: TessellateRequest, http_request: Request
) -> TessellationMetadata:
    """JSON twin of ``/tessellate``: mass properties + mesh stats, no mesh."""
    upstream = await _forward(http_request, "/api/v1/tessellate/meta", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return TessellationMetadata.model_validate_json(upstream.content)
