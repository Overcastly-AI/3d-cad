"""Geometry REST API (``/api/v1``) — thin, typed shell over the kernel layer.

Kernel code stays in :mod:`geometry.kernel`; this module only translates
between HTTP and DTOs. Endpoints are sync ``def`` on purpose: kernel work is
CPU-bound and runs on the threadpool, keeping the event loop free. The arq
queue path (``geometry.worker``) calls the same core function.
"""

from typing import Any

from fastapi import APIRouter, Response

# GLB_MEDIA_TYPE + PROPERTIES_HEADER live in py-kit (single source of truth,
# shared with the gateway proxy).
from py_kit.schemas.geometry import GLB_MEDIA_TYPE, PROPERTIES_HEADER

from geometry.kernel import evaluate_tessellation
from geometry.schemas import TessellateRequest, TessellationMetadata

router = APIRouter(prefix="/api/v1", tags=["geometry"])

_TESSELLATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "Binary glTF (GLB) mesh of the requested shape. The "
            f"`{PROPERTIES_HEADER}` header carries `TessellationMetadata` "
            "as compact JSON (see `POST /api/v1/tessellate/meta` for the "
            "same payload as a typed JSON body)."
        ),
        "content": {GLB_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "headers": {
            PROPERTIES_HEADER: {
                "description": "TessellationMetadata as compact JSON",
                "schema": {"type": "string"},
            }
        },
    }
}


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
