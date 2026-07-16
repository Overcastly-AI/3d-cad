"""``/api/v1/drawings`` — auth-protected drawing-layout aggregation over the
documents service.

Same posture as :mod:`gateway.assemblies` / :mod:`gateway.parts` (apps/web talks
ONLY to the gateway, CLAUDE.md service boundaries): every route resolves the
caller through the JWT bearer dependency and forwards via
:func:`gateway.parts.forward_documents`, which attaches the verified principal
header (``X-Loft-User``). Documents owns owner-scoping, optimistic concurrency
(``expected_version`` → 422 on stale), the delete-with-dependents 409, the
cross-document ``ref_document_not_found`` 422, the kernel-free dimension
write-checks, and uniform 404 visibility — the gateway proxies faithfully and
re-surfaces those envelopes verbatim under its own request id. DTOs are the
shared py-kit drawing models (single source of truth, never hand-duplicated), so
request bodies are fully validated at the gateway before anything goes upstream.

Every route is auth-gated from day one (``user: CurrentUser``) — heeding
engineering audit F7 (the tessellate/export unauthenticated-route class): a
drawing is a signed-in user's document, never anonymously reachable.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from py_kit.schemas.drawings import (
    AnnotationCreate,
    AnnotationMutationResponse,
    DimensionCreate,
    DimensionMutationResponse,
    DrawingCreate,
    DrawingListResponse,
    DrawingResponse,
    DrawingTreeResponse,
    DrawingUpdate,
    SheetCreate,
    SheetMutationResponse,
    SheetUpdate,
    ViewCreate,
    ViewMutationResponse,
    ViewUpdate,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])


# --- drawing routes ---------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_drawing(
    request: DrawingCreate, user: CurrentUser, http_request: Request
) -> DrawingResponse:
    """Create a drawing owned by the caller (201; 409 envelope on duplicate name)."""
    upstream = await forward_documents(
        http_request, user, "POST", "/api/v1/drawings", request.model_dump_json()
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingResponse.model_validate_json(upstream.content)


@router.get("")
async def list_drawings(
    user: CurrentUser, http_request: Request
) -> DrawingListResponse:
    """The caller's drawings, oldest first."""
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/drawings")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingListResponse.model_validate_json(upstream.content)


@router.get("/{drawing_id}")
async def get_drawing(
    drawing_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> DrawingTreeResponse:
    """One owned drawing with its full sheet/view/dimension/annotation tree."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/drawings/{drawing_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingTreeResponse.model_validate_json(upstream.content)


@router.patch("/{drawing_id}")
async def update_drawing(
    drawing_id: uuid.UUID,
    request: DrawingUpdate,
    user: CurrentUser,
    http_request: Request,
) -> DrawingResponse:
    """Rename a drawing (bumps ``doc_version``; 422 stale / 409 name clash)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/drawings/{drawing_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingResponse.model_validate_json(upstream.content)


@router.delete("/{drawing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drawing(
    drawing_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete an owned drawing (204; uniform 404 for unknown/foreign ids).

    A drawing is a pure LEAF (nothing references it), so its entire
    sheet/view/dimension/annotation layout CASCADEs — no dependents pre-check.
    """
    upstream = await forward_documents(
        http_request, user, "DELETE", f"/api/v1/drawings/{drawing_id}"
    )
    if upstream.status_code != status.HTTP_204_NO_CONTENT:
        raise_upstream_error(upstream, service=_SERVICE)


# --- sheet routes -----------------------------------------------------------------


@router.post("/{drawing_id}/sheets", status_code=status.HTTP_201_CREATED)
async def create_sheet(
    drawing_id: uuid.UUID,
    request: SheetCreate,
    user: CurrentUser,
    http_request: Request,
) -> SheetMutationResponse:
    """Add a sheet to a drawing (append at the tip; 422 on a stale version)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/drawings/{drawing_id}/sheets",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return SheetMutationResponse.model_validate_json(upstream.content)


@router.patch("/{drawing_id}/sheets/{sheet_id}")
async def update_sheet(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: SheetUpdate,
    user: CurrentUser,
    http_request: Request,
) -> SheetMutationResponse:
    """Update a sheet's header (bumps ``doc_version``; 422 on empty/stale)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return SheetMutationResponse.model_validate_json(upstream.content)


@router.delete("/{drawing_id}/sheets/{sheet_id}")
async def delete_sheet(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> DrawingTreeResponse:
    """Delete a sheet (cascades its views/dimensions/annotations); returns the tree."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingTreeResponse.model_validate_json(upstream.content)


# --- view routes ------------------------------------------------------------------


@router.post(
    "/{drawing_id}/sheets/{sheet_id}/views", status_code=status.HTTP_201_CREATED
)
async def create_view(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: ViewCreate,
    user: CurrentUser,
    http_request: Request,
) -> ViewMutationResponse:
    """Add a view referencing a part / assembly (append at the tip).

    Documents enforces cross-document integrity (the referenced document must
    exist and belong to the caller); its ``ref_document_not_found`` 422 and the
    ``stale_drawing_version`` 422 are re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return ViewMutationResponse.model_validate_json(upstream.content)


@router.patch("/{drawing_id}/views/{view_id}")
async def update_view(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    request: ViewUpdate,
    user: CurrentUser,
    http_request: Request,
) -> ViewMutationResponse:
    """Re-frame / re-scale / re-place a view (bumps ``doc_version``)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return ViewMutationResponse.model_validate_json(upstream.content)


@router.delete("/{drawing_id}/views/{view_id}")
async def delete_view(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> DrawingTreeResponse:
    """Delete a view (cascades the dimensions it carries); returns the tree."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingTreeResponse.model_validate_json(upstream.content)


# --- dimension routes -------------------------------------------------------------


@router.post(
    "/{drawing_id}/views/{view_id}/dimensions", status_code=status.HTTP_201_CREATED
)
async def create_dimension(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    request: DimensionCreate,
    user: CurrentUser,
    http_request: Request,
) -> DimensionMutationResponse:
    """Add a dimension to a view (append at the tip, ordered per sheet).

    Documents runs the kernel-free write-time checks (a diameter/radius must
    name a circular edge, an angular dimension two straight edges); its
    ``dimension_requires_circular_edge`` / ``dimension_requires_straight_edges``
    422 envelopes are re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return DimensionMutationResponse.model_validate_json(upstream.content)


@router.delete("/{drawing_id}/dimensions/{dimension_id}")
async def delete_dimension(
    drawing_id: uuid.UUID,
    dimension_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> DrawingTreeResponse:
    """Delete a dimension; returns the updated tree (bumps ``doc_version``)."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/drawings/{drawing_id}/dimensions/{dimension_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingTreeResponse.model_validate_json(upstream.content)


# --- annotation routes ------------------------------------------------------------


@router.post(
    "/{drawing_id}/sheets/{sheet_id}/annotations", status_code=status.HTTP_201_CREATED
)
async def create_annotation(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: AnnotationCreate,
    user: CurrentUser,
    http_request: Request,
) -> AnnotationMutationResponse:
    """Add an annotation (v1: a note) to a sheet (append at the tip)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return AnnotationMutationResponse.model_validate_json(upstream.content)


@router.delete("/{drawing_id}/annotations/{annotation_id}")
async def delete_annotation(
    drawing_id: uuid.UUID,
    annotation_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> DrawingTreeResponse:
    """Delete an annotation; returns the updated tree (bumps ``doc_version``)."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/drawings/{drawing_id}/annotations/{annotation_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingTreeResponse.model_validate_json(upstream.content)
