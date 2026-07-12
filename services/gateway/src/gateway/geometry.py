"""Gateway → geometry proxy (``/api/v1/geometry/*``): tessellation, export,
mesh fetch.

apps/web talks ONLY to the gateway (CLAUDE.md service boundaries), so the
geometry API is surfaced here. Routes are typed with the shared py-kit DTOs —
the exact models the geometry service serves, never hand-duplicated — and
forward over the lifespan-managed httpx2 ``AsyncClient`` on ``app.state``
using the shared :mod:`gateway.upstream` plumbing (502 on transport failure,
upstream envelopes re-surfaced).
"""

from typing import Annotated, Any, NoReturn

import httpx2 as httpx
from fastapi import APIRouter, Path, Request, Response
from py_kit.schemas.geometry import (
    EXPORT_MEDIA_TYPES,
    GLB_MEDIA_TYPE,
    PROPERTIES_HEADER,
    ExportRequest,
    TessellateRequest,
    TessellationMetadata,
    export_responses,
    tessellate_responses,
)
from py_kit.schemas.measure import MeasureRequest, MeasureResult
from pydantic import BaseModel

from gateway.auth import CurrentUser
from gateway.upstream import create_upstream_client, forward, raise_upstream_error

#: Upstream call budget — tessellation is CPU-bound and may take a while.
GEOMETRY_TIMEOUT_S = 30.0

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Geometry"

router = APIRouter(prefix="/api/v1/geometry", tags=["geometry"])


def create_geometry_client(
    geometry_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The geometry upstream client (see :func:`create_upstream_client`)."""
    return create_upstream_client(
        geometry_url, timeout_s=GEOMETRY_TIMEOUT_S, transport=transport
    )


async def _forward(
    http_request: Request, path: str, payload: BaseModel
) -> httpx.Response:
    """POST *payload* to the geometry service, mapping transport failures."""
    client: httpx.AsyncClient = http_request.app.state.geometry_client
    return await forward(
        client,
        http_request,
        "POST",
        path,
        service=_SERVICE,
        json_content=payload.model_dump_json(),
    )


def _raise_upstream_error(upstream: httpx.Response) -> NoReturn:
    """Re-surface a geometry error response (see :func:`raise_upstream_error`)."""
    raise_upstream_error(upstream, service=_SERVICE)


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


#: Exact shape of a ``mesh_glb_id`` content address (feature-tree design
#: §4.4/§7.8: ``sha256:<hex digest of the GLB bytes>``). Enforced at the
#: gateway so malformed ids are rejected here (422) and never go upstream —
#: same posture as the DTO-validated POST routes.
MESH_GLB_ID_PATTERN = r"^sha256:[0-9a-f]{64}$"

_MESH_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {GLB_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "description": (
            "Binary glTF (GLB) mesh addressed by an `EvaluateTreeResult."
            "mesh_glb_id` content hash (`sha256:<hex>`), proxied byte-exact "
            "from the geometry service. A 404 `mesh_not_found` envelope "
            "means evicted or unknown: re-evaluate the tree to regenerate "
            "the artifact (feature-tree design §4.4/§7.8)."
        ),
    }
}


@router.get("/meshes/{mesh_glb_id}", response_class=Response, responses=_MESH_RESPONSES)
async def fetch_mesh(
    mesh_glb_id: Annotated[
        str,
        Path(
            pattern=MESH_GLB_ID_PATTERN,
            description="Content address of the GLB artifact (`sha256:<hex>`), "
            "from `EvaluateTreeResult.mesh_glb_id`.",
        ),
    ],
    user: CurrentUser,
    http_request: Request,
) -> Response:
    """Fetch an evaluated body's GLB artifact through the gateway.

    Auth-protected (the artifact comes from a signed-in user's part
    evaluation); the geometry hop itself stays identity-free, so the
    principal never goes upstream. Upstream 404 ``mesh_not_found`` is the
    client's re-evaluate signal and is re-surfaced verbatim (§7.8).
    """
    client: httpx.AsyncClient = http_request.app.state.geometry_client
    upstream = await forward(
        client,
        http_request,
        "GET",
        f"/api/v1/meshes/{mesh_glb_id}",
        service=_SERVICE,
    )
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return Response(content=upstream.content, media_type=GLB_MEDIA_TYPE)


_EXPORT_RESPONSES = export_responses(
    "The exported CAD file, proxied byte-exact from the geometry service: "
    "STEP AP214 part 21 (`model/step`, exact B-rep) or binary STL "
    "(`model/stl`, faceted mesh). `Content-Disposition` carries the suggested "
    "download filename. Byte-deterministic: identical requests produce "
    "identical files."
)


@router.post("/export", response_class=Response, responses=_EXPORT_RESPONSES)
async def export(request: ExportRequest, http_request: Request) -> Response:
    """Build + export on the geometry service; pass the file bytes through."""
    upstream = await _forward(http_request, "/api/v1/export", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    headers: dict[str, str] = {}
    if "content-disposition" in upstream.headers:
        headers["Content-Disposition"] = upstream.headers["content-disposition"]
    return Response(
        content=upstream.content,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers=headers,
    )


@router.post("/measure")
async def measure(
    request: MeasureRequest, user: CurrentUser, http_request: Request
) -> MeasureResult:
    """Proxy a stateless distance measurement to the geometry service.

    Auth-protected (a measurement reads a signed-in user's part geometry);
    the geometry hop itself stays identity-free, so the principal never goes
    upstream (same posture as the mesh-fetch proxy, RESEARCH §3). The shared
    :class:`MeasureRequest` DTO validates at the gateway — a malformed target
    or an edge target with no ``tree`` is a 422 here and never reaches
    geometry. Upstream envelopes (``tree_measure_failed``,
    ``edge_index_out_of_range``, …) are re-surfaced verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/measure", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return MeasureResult.model_validate_json(upstream.content)
