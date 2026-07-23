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
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    ExportAssemblyRequest,
    InterferenceResult,
)
from py_kit.schemas.drawings import (
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
)
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
from py_kit.schemas.overlay import OverlayRequest, OverlayResult
from py_kit.schemas.sketch import (
    SketchChamferRequest,
    SketchCornerResult,
    SketchEditRequest,
    SketchEditResult,
    SketchFilletRequest,
    SketchMirrorRequest,
    SketchMirrorResult,
    SketchOffsetRequest,
    SketchOffsetResult,
)
from pydantic import BaseModel

from gateway.auth import CurrentUser
from gateway.ratelimit import COMPUTE_RATE_LIMIT
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


# Auth-protected: tessellation/export are CPU-bound OCCT work on a signed-in
# user's geometry — an unauthenticated route is an anonymous DoS vector
# (engineering audit F7). The ``user: CurrentUser`` dependency mirrors the
# sibling stateless proxies (measure/overlay/mesh-fetch); the geometry hop
# itself stays identity-free, so the principal never travels upstream
# (RESEARCH §3). Kept out of the docstring so the generated OpenAPI
# description — and thus the committed contracts — does not drift.
@router.post(
    "/tessellate",
    response_class=Response,
    responses=_TESSELLATE_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def tessellate(
    request: TessellateRequest, user: CurrentUser, http_request: Request
) -> Response:
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


# Auth-protected, identity-free upstream (same posture as ``/tessellate``).
@router.post("/tessellate/meta", dependencies=[COMPUTE_RATE_LIMIT])
async def tessellate_meta(
    request: TessellateRequest, user: CurrentUser, http_request: Request
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


# Auth-protected (same rationale + posture as ``/tessellate`` above — audit F7).
@router.post(
    "/export",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def export(
    request: ExportRequest, user: CurrentUser, http_request: Request
) -> Response:
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


_ASSEMBLY_EXPORT_RESPONSES = export_responses(
    "The exported assembly CAD file, proxied byte-exact from the geometry "
    "service: STEP AP214 part 21 (`model/step`, exact B-rep with product "
    "structure — each instance a named PRODUCT at its solved placement) or "
    "binary STL (`model/stl`, faceted mesh). `Content-Disposition` carries the "
    "suggested download filename. Byte-deterministic: identical requests "
    "produce identical files."
)


# Auth-protected (same rationale + posture as ``/export`` above — audit F7).
@router.post(
    "/assembly/export",
    response_class=Response,
    responses=_ASSEMBLY_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def assembly_export(
    request: ExportAssemblyRequest, user: CurrentUser, http_request: Request
) -> Response:
    """Proxy an assembly export to the geometry service; pass the file through.

    Auth-protected (an assembly graph belongs to a signed-in user); the geometry
    hop stays identity-free, so the principal never travels upstream (same
    posture as ``/export`` + ``/assembly/evaluate``, RESEARCH §3). The shared
    :class:`ExportAssemblyRequest` DTO validates at the gateway before anything
    goes upstream. Geometry solves the assembly and composes it into ONE
    multi-instance STEP (AP214 product structure) or STL; a body-less assembly is
    a 422 ``assembly_export_no_body`` envelope, re-surfaced verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/assembly/export", request)
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


@router.post("/assembly/evaluate", dependencies=[COMPUTE_RATE_LIMIT])
async def assembly_evaluate(
    request: EvaluateAssemblyRequest, user: CurrentUser, http_request: Request
) -> EvaluateAssemblyResult:
    """Proxy an assembly evaluation to the geometry service (assemblies §4).

    Auth-protected (an assembly graph belongs to a signed-in user); the
    geometry hop stays identity-free, so the principal never travels upstream
    (same posture as measure/overlay, RESEARCH §3). The shared
    :class:`EvaluateAssemblyRequest` DTO validates at the gateway before
    anything goes upstream. Geometry evaluates each unique part once (shared
    content-addressed mesh), solves the mate graph, and returns per-instance
    ``{shared mesh id, solved placement}`` plus an analytic combined roll-up. A
    bad part / mate / solve is a 200 with a typed per-entry error or a
    non-``well_constrained`` status (design §4); the envelope stays reserved
    for transport/validation failures of this call itself.
    """
    upstream = await _forward(http_request, "/api/v1/assembly/evaluate", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return EvaluateAssemblyResult.model_validate_json(upstream.content)


@router.post("/assembly/interference", dependencies=[COMPUTE_RATE_LIMIT])
async def assembly_interference(
    request: EvaluateAssemblyRequest, user: CurrentUser, http_request: Request
) -> InterferenceResult:
    """Proxy an assembly interference check to the geometry service (assemblies §4).

    Auth-protected (an assembly graph belongs to a signed-in user); the geometry
    hop stays identity-free, so the principal never travels upstream (same posture
    as ``/assembly/evaluate`` + measure/overlay, RESEARCH §3). The shared
    :class:`EvaluateAssemblyRequest` DTO validates at the gateway before anything
    goes upstream. Geometry solves the assembly and runs a pairwise
    ``BRepAlgoAPI_Common`` over the solved world-placed instance bodies, returning
    the clash list ``[{instance_a, instance_b, overlap_volume_mm3}]`` (each pair
    once, a merely-touching pair is NO clash) plus the solve status/diagnosis. A
    non-overlapping assembly is ``clashes: []``; a bad part/mate/solve is a 200
    with a typed status and a (possibly empty) clash list (design §4), never a
    4xx/5xx from the check itself. The envelope stays reserved for
    transport/validation failures of this call.
    """
    upstream = await _forward(http_request, "/api/v1/assembly/interference", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return InterferenceResult.model_validate_json(upstream.content)


@router.post("/drawing/evaluate", dependencies=[COMPUTE_RATE_LIMIT])
async def drawing_evaluate(
    request: EvaluateDrawingViewsRequest, user: CurrentUser, http_request: Request
) -> EvaluateDrawingViewsResult:
    """Proxy a drawing-view evaluation to the geometry service (drawings §1.2/§4).

    Auth-protected (a drawing belongs to a signed-in user); the geometry hop
    stays identity-free, so the principal never travels upstream (same posture
    as measure/overlay + assembly-evaluate, RESEARCH §3). The shared
    :class:`EvaluateDrawingViewsRequest` DTO validates at the gateway before
    anything goes upstream. Geometry evaluates the referenced part body once
    (reusing ``evaluate_tree``) then runs exact HLR per requested view, returning
    per-view canonically-ordered neutral 2D edges OR a typed per-view projection
    error. A feature/HLR failure is a 200 with a typed per-view (or whole-part)
    error (design §1.5/§4); the envelope stays reserved for transport/validation
    failures of this call itself.
    """
    upstream = await _forward(http_request, "/api/v1/drawing/evaluate", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return EvaluateDrawingViewsResult.model_validate_json(upstream.content)


@router.post("/measure", dependencies=[COMPUTE_RATE_LIMIT])
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


@router.post("/overlay", dependencies=[COMPUTE_RATE_LIMIT])
async def overlay(
    request: OverlayRequest, user: CurrentUser, http_request: Request
) -> OverlayResult:
    """Proxy a stateless selection-overlay query to the geometry service.

    Auth-protected (the overlay describes a signed-in user's part geometry);
    the geometry hop itself stays identity-free, so the principal never goes
    upstream (same posture as the measure + mesh-fetch proxies, RESEARCH §3).
    The shared :class:`OverlayRequest` DTO validates at the gateway. Upstream
    envelopes (``tree_overlay_failed``, ``overlay_failed``) are re-surfaced
    verbatim. The response carries the body's exact pickable vertices + edges,
    the edge list index-aligned with ``/measure``'s ``EdgeTarget.index``.
    """
    upstream = await _forward(http_request, "/api/v1/overlay", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return OverlayResult.model_validate_json(upstream.content)


@router.post("/sketch/trim", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_trim(
    request: SketchEditRequest, user: CurrentUser, http_request: Request
) -> SketchEditResult:
    """Proxy a stateless sketch trim to the geometry service.

    Auth-protected (the edit rewrites a signed-in user's sketch); the geometry
    hop stays identity-free, so the principal never travels upstream (same
    posture as measure/overlay, RESEARCH §3). The shared ``SketchEditRequest``
    DTO validates at the gateway (a duplicate entity id is a 422 here and never
    reaches geometry); upstream envelopes (``sketch_target_not_found``,
    ``sketch_pick_not_on_target``, ``sketch_unsupported_entity``, …) are
    re-surfaced verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/trim", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchEditResult.model_validate_json(upstream.content)


@router.post("/sketch/extend", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_extend(
    request: SketchEditRequest, user: CurrentUser, http_request: Request
) -> SketchEditResult:
    """Proxy a stateless sketch extend to the geometry service.

    Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
    Upstream envelopes (``sketch_extend_no_target``, ``sketch_unsupported_entity``,
    ``sketch_target_not_found``, ``sketch_degenerate_result``) are re-surfaced
    verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/extend", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchEditResult.model_validate_json(upstream.content)


@router.post("/sketch/offset", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_offset(
    request: SketchOffsetRequest, user: CurrentUser, http_request: Request
) -> SketchOffsetResult:
    """Proxy a stateless sketch offset to the geometry service.

    Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
    The shared ``SketchOffsetRequest`` DTO validates at the gateway (a duplicate
    entity id is a 422 here and never reaches geometry); upstream envelopes
    (``sketch_target_not_found``, ``sketch_unsupported_entity``,
    ``sketch_offset_zero_distance``, ``sketch_degenerate_result``) are
    re-surfaced verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/offset", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchOffsetResult.model_validate_json(upstream.content)


@router.post("/sketch/mirror", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_mirror(
    request: SketchMirrorRequest, user: CurrentUser, http_request: Request
) -> SketchMirrorResult:
    """Proxy a stateless sketch mirror to the geometry service.

    Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
    The shared ``SketchMirrorRequest`` DTO validates at the gateway (a duplicate
    entity id, or an empty ``targets`` list, is a 422 here and never reaches
    geometry); upstream envelopes (``sketch_target_not_found``,
    ``sketch_mirror_axis_not_line``, ``sketch_mirror_degenerate_axis``,
    ``sketch_unsupported_entity``) are re-surfaced verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/mirror", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchMirrorResult.model_validate_json(upstream.content)


@router.post("/sketch/fillet", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_fillet(
    request: SketchFilletRequest, user: CurrentUser, http_request: Request
) -> SketchCornerResult:
    """Proxy a stateless sketch corner fillet to the geometry service.

    Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
    The shared ``SketchFilletRequest`` DTO validates at the gateway (a duplicate
    entity id, or a non-positive/non-finite radius, is a 422 here and never
    reaches geometry); upstream envelopes (``sketch_target_not_found``,
    ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
    ``sketch_corner_too_large``, ``sketch_degenerate_result``) are re-surfaced
    verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/fillet", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchCornerResult.model_validate_json(upstream.content)


@router.post("/sketch/chamfer", dependencies=[COMPUTE_RATE_LIMIT])
async def sketch_chamfer(
    request: SketchChamferRequest, user: CurrentUser, http_request: Request
) -> SketchCornerResult:
    """Proxy a stateless sketch corner chamfer to the geometry service.

    Auth-protected and identity-free upstream (same posture as ``sketch/trim``).
    The shared ``SketchChamferRequest`` DTO validates at the gateway (a duplicate
    entity id, or a non-positive/non-finite distance, is a 422 here and never
    reaches geometry); upstream envelopes (``sketch_target_not_found``,
    ``sketch_unsupported_entity``, ``sketch_corner_not_found``,
    ``sketch_corner_too_large``, ``sketch_degenerate_result``) are re-surfaced
    verbatim.
    """
    upstream = await _forward(http_request, "/api/v1/sketch/chamfer", request)
    if upstream.status_code != 200:
        _raise_upstream_error(upstream)
    return SketchCornerResult.model_validate_json(upstream.content)
