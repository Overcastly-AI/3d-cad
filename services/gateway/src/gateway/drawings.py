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
from typing import Annotated, Any

import httpx2 as httpx
from fastapi import APIRouter, Query, Request, Response, status
from py_kit.errors import ValidationApiError
from py_kit.schemas.drawings import (
    ARTIFACT_MEDIA_TYPES,
    AnnotationCreate,
    AnnotationMutationResponse,
    ArtifactFormat,
    ComposeDrawingRequest,
    DimensionCreate,
    DimensionMutationResponse,
    DrawingCreate,
    DrawingDimensionInput,
    DrawingListResponse,
    DrawingResponse,
    DrawingTreeResponse,
    DrawingUpdate,
    SheetContent,
    SheetCreate,
    SheetLayout,
    SheetMutationResponse,
    SheetUpdate,
    SheetViewPlacement,
    ViewCreate,
    ViewMutationResponse,
    ViewProjection,
    ViewUpdate,
    artifact_filename,
)
from py_kit.schemas.features import EvaluateTreeRequest

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import forward, raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: The geometry upstream name (the compose hop, distinct from the documents hop).
_GEOMETRY = "Geometry"

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


# --- server-composed export (drawing-export.md §"Endpoints", Approach C) -----------
#
# The auth-gated, user-facing artifact route: turn a persisted `drawing_id` into a
# composed SVG/PDF/DXF the browser downloads. It is the drawing twin of the parts
# `/{part_id}/export` two-hop aggregation (gateway.features) — documents supplies
# the persisted STATE (the drawing's sheet/views/dimensions + the referenced part's
# evaluation-ready feature prefix), the gateway ASSEMBLES the `ComposeDrawingRequest`
# from it, and the stateless geometry service evaluates + places + serializes it. The
# principal reaches documents only (the compose hop is identity-free, RESEARCH §3);
# geometry's `not_implemented` (dxf) / per-format envelopes re-surface verbatim. This
# satisfies drawings.md §4.2 (assembled from persisted state, never client-composed).


def _compose_request(
    tree: DrawingTreeResponse,
    evaluation_request: EvaluateTreeRequest,
    artifact_format: ArtifactFormat,
) -> ComposeDrawingRequest:
    """Assemble the geometry `ComposeDrawingRequest` from persisted drawing state.

    Mirrors the on-screen sheet the frontend evaluates (``apps/web`` DrawingPage):
    v1 composes the drawing's FIRST sheet — its views (projection + placement +
    scale) become the :class:`SheetLayout`, its dimensions (each tagged with the
    projection of the view it annotates) become the measured inputs, and the
    referenced part's ``evaluation-request`` (part id + tree version + feature
    prefix) supplies the projection intent. The composer re-derives view anchors
    from the projected bounds (``boundsAwareLayout``), so the persisted per-view
    ``position`` rides along for generality but ``projection``/``scale`` drive v1.
    """
    sheet_content: SheetContent = tree.sheets[0]
    sheet = sheet_content.sheet
    views = sheet_content.views
    projection_by_view: dict[uuid.UUID, ViewProjection] = {
        v.id: v.projection for v in views
    }

    dimension_inputs: list[DrawingDimensionInput] = []
    for dim in sheet_content.dimensions:
        projection = projection_by_view.get(dim.view_id)
        if projection is None:
            continue  # a dimension on a view not on this sheet — nothing to place
        dimension_inputs.append(
            DrawingDimensionInput(id=dim.id, view=projection, dimension=dim.dimension)
        )

    layout = SheetLayout(
        size=sheet.size,
        orientation=sheet.orientation,
        projection=sheet.projection,
        title=tree.drawing.name,
        title_block=sheet.title_block,
        views=[
            SheetViewPlacement(
                projection=v.projection, position=v.position, scale=v.scale
            )
            for v in views
        ],
    )
    return ComposeDrawingRequest(
        part_id=evaluation_request.part_id,
        tree_version=evaluation_request.tree_version,
        features=evaluation_request.features,
        views=[v.projection for v in views],
        # v1 drafts a single shared scale across the standard views (the frontend's
        # `effectiveScaleValue`) — the first placed view carries it.
        scale=views[0].scale,
        dimensions=dimension_inputs,
        layout=layout,
        format=artifact_format,
    )


_EXPORT_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            media_type: {"schema": {"type": "string", "format": "binary"}}
            for media_type in ARTIFACT_MEDIA_TYPES.values()
        },
        "description": (
            "The server-composed drawing artifact, proxied byte-exact from the "
            "geometry service: SVG (`image/svg+xml`), PDF (`application/pdf`), or "
            "DXF (`image/vnd.dxf`). `Content-Disposition` carries the suggested "
            "download filename. Composition is deterministic — identical drawing "
            "state produces an identical artifact (drawing-export.md §determinism)."
        ),
    }
}


@router.post(
    "/{drawing_id}/export",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def export_drawing(
    drawing_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    format: Annotated[
        ArtifactFormat,
        Query(description="Artifact format to compose: svg | pdf | dxf"),
    ] = "svg",
) -> Response:
    """Compose the drawing into a downloadable SVG/PDF/DXF artifact (design §4.2).

    Auth-gated and rate-limited (an OCCT-CPU compose route, same posture as the
    parts export and the drawing-evaluate proxy — engineering audit F7). The
    two-hop aggregation: documents serves the drawing tree AND the referenced
    part's evaluation-ready feature prefix (principal attached, uniform 404 for an
    unknown/foreign drawing re-surfaced verbatim), the gateway assembles the
    :class:`ComposeDrawingRequest` from that persisted state, and the stateless
    geometry service (identity-free upstream) evaluates + places + serializes it.
    The artifact bytes stream back with geometry's ``Content-Type`` +
    ``Content-Disposition``; its per-format envelopes (e.g. ``not_implemented`` for
    ``dxf``) re-surface verbatim.
    """
    drawing_upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/drawings/{drawing_id}"
    )
    if drawing_upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(drawing_upstream, service=_SERVICE)
    tree = DrawingTreeResponse.model_validate_json(drawing_upstream.content)

    if not tree.sheets or not tree.sheets[0].views:
        raise ValidationApiError(
            "The drawing has no views to export; lay out its standard views first.",
            code="drawing_not_composable",
        )
    referenced_part_id = tree.sheets[0].views[0].ref_document_id

    part_upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/parts/{referenced_part_id}/evaluation-request",
    )
    if part_upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(part_upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(part_upstream.content)

    compose_request = _compose_request(tree, evaluation_request, format)

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    composed = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/drawing/compose",
        service=_GEOMETRY,
        json_content=compose_request.model_dump_json(),
    )
    if composed.status_code != status.HTTP_200_OK:
        raise_upstream_error(composed, service=_GEOMETRY)

    headers: dict[str, str] = {}
    if "content-disposition" in composed.headers:
        headers["Content-Disposition"] = composed.headers["content-disposition"]
    else:
        filename = artifact_filename(tree.drawing.name, format)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    media_type = composed.headers.get(
        "content-type", ARTIFACT_MEDIA_TYPES[format]
    )
    return Response(content=composed.content, media_type=media_type, headers=headers)
