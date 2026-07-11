"""Geometry REST API (``/api/v1``) — thin, typed shell over the kernel layer.

Kernel code stays in :mod:`geometry.kernel`; this module only translates
between HTTP and DTOs. Endpoints are sync ``def`` on purpose: kernel work is
CPU-bound and runs on the threadpool, keeping the event loop free. The arq
queue path (``geometry.worker``) calls the same core function.
"""

from typing import Any

from fastapi import APIRouter, Response
from py_kit.errors import NotFoundError

# Media types, filename rule, and the shared OpenAPI responses blocks live in
# py-kit (single source of truth, shared with the gateway proxy).
from py_kit.schemas.features import EvaluateTreeRequest, EvaluateTreeResult
from py_kit.schemas.geometry import (
    EXPORT_MEDIA_TYPES,
    GLB_MEDIA_TYPE,
    PROPERTIES_HEADER,
    export_filename,
    export_responses,
    tessellate_responses,
)

from geometry.features import evaluate_tree
from geometry.kernel import evaluate_export, evaluate_tessellation
from geometry.mesh_store import fetch_mesh_glb
from geometry.schemas import ExportRequest, TessellateRequest, TessellationMetadata

router = APIRouter(prefix="/api/v1", tags=["geometry"])

_TESSELLATE_RESPONSES = tessellate_responses(
    "Binary glTF (GLB) mesh of the requested shape. The "
    f"`{PROPERTIES_HEADER}` header carries `TessellationMetadata` "
    "as compact JSON (see `POST /api/v1/tessellate/meta` for the "
    "same payload as a typed JSON body)."
)

_EXPORT_RESPONSES = export_responses(
    "The exported CAD file: STEP AP214 part 21 (`model/step`, exact B-rep) "
    "or binary STL (`model/stl`, faceted mesh). `Content-Disposition` "
    "carries the suggested download filename. Byte-deterministic: identical "
    "requests produce identical files."
)


@router.post("/tessellate", response_class=Response, responses=_TESSELLATE_RESPONSES)
def tessellate(request: TessellateRequest) -> Response:
    """Build a parametric shape, tessellate it, return the GLB mesh."""
    glb, metadata = evaluate_tessellation(request)
    return Response(
        content=glb,
        media_type=GLB_MEDIA_TYPE,
        headers={PROPERTIES_HEADER: metadata.model_dump_json()},
    )


@router.post("/tessellate/meta")
def tessellate_meta(request: TessellateRequest) -> TessellationMetadata:
    """JSON twin of ``/tessellate``: mass properties + mesh stats, no mesh."""
    _glb, metadata = evaluate_tessellation(request)
    return metadata


@router.post("/evaluate")
def evaluate(request: EvaluateTreeRequest) -> EvaluateTreeResult:
    """Evaluate an ordered feature-tree prefix (feature-tree design §4).

    Stateless: documents sends the full ordered, validated, current-version
    feature list (rollback bar already applied); the response is per-feature
    statuses plus object-storage artifact references, under the strict-prefix
    rule (§4.3 — first failure ``error``, the rest ``skipped``). A feature
    failure is a **200 with per-feature errors**; the py-kit error envelope
    stays reserved for transport/validation failures of this call itself.
    """
    return evaluate_tree(request).result


_MESH_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {GLB_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "description": (
            "Binary glTF (GLB) mesh addressed by an `EvaluateTreeResult."
            "mesh_glb_id` content hash (`sha256:<hex>`). 404 = evicted or "
            "unknown: re-evaluate the tree (results are pure functions of "
            "the request; feature-tree design §4.4/§7.8)."
        ),
    }
}


@router.get("/meshes/{mesh_glb_id}", response_class=Response, responses=_MESH_RESPONSES)
def fetch_mesh(mesh_glb_id: str) -> Response:
    """Fetch the GLB artifact a tree evaluation returned by content address.

    The interim §7.8 mesh-delivery path: `mesh_glb_id` is a pure content
    address, so this route keeps the same contract when the in-process store
    is replaced by object storage (docs/design/feature-tree.md §7.8).
    """
    glb = fetch_mesh_glb(mesh_glb_id)
    if glb is None:
        raise NotFoundError(
            "Mesh artifact unknown or evicted; re-evaluate the tree to regenerate it.",
            code="mesh_not_found",
        )
    return Response(content=glb, media_type=GLB_MEDIA_TYPE)


@router.post("/export", response_class=Response, responses=_EXPORT_RESPONSES)
def export(request: ExportRequest) -> Response:
    """Build a parametric shape and export it as a STEP or STL download."""
    data = evaluate_export(request)
    return Response(
        content=data,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(request)}"'
        },
    )
