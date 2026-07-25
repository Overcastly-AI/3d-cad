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
from py_kit.errors import NotFoundError, ValidationApiError
from py_kit.schemas.assemblies import EvaluateAssemblyRequest
from py_kit.schemas.drawings import (
    ARTIFACT_MEDIA_TYPES,
    AnnotationCreate,
    AnnotationMutationResponse,
    ArtifactFormat,
    ComposeDrawingRequest,
    ComposedSheet,
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
from py_kit.schemas.features import EvaluatedFeatureInput, EvaluateTreeRequest

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
    sheet_content: SheetContent,
    artifact_format: ArtifactFormat,
    *,
    part: EvaluateTreeRequest | None = None,
    assembly: EvaluateAssemblyRequest | None = None,
) -> ComposeDrawingRequest:
    """Assemble the geometry `ComposeDrawingRequest` from persisted drawing state.

    Mirrors the on-screen sheet the frontend evaluates (``apps/web`` DrawingPage):
    composes the REQUESTED ``sheet_content`` (the drawing's first sheet by default —
    the multi-sheet switcher selects any sheet by id, see
    :func:`_aggregate_compose_request`) — its views (projection + placement + scale)
    become the :class:`SheetLayout`, its dimensions (each tagged with the projection
    of the view it annotates) become the measured inputs, and the source document's
    ``evaluation-request`` supplies the projection intent. Each placed view carries
    its persisted ``auto_place`` flag: ``True`` (default) lets the composer re-derive
    the anchor from the projected bounds (``boundsAwareLayout``), ``False`` honors the
    persisted drag-to-place ``position`` verbatim (drawing-export.md §4.2).

    Exactly ONE source is threaded (design §7): a PART view carries ``part`` (part id
    + tree version + feature prefix — geometry projects the single body); an ASSEMBLY
    view carries ``assembly`` (the resolved instance+mate graph — geometry projects the
    SOLVED assembly compound), with the inherited part fields then echoing the
    assembly's id/version + an empty feature list. Both fold their per-view HLR edges
    into the SAME sheet via the SAME ``place_sheet`` (the edges are the identical
    neutral :class:`ProjectedViewEdge` shape) — one composition path for both.
    """
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
                projection=v.projection,
                position=v.position,
                scale=v.scale,
                # Thread the persisted drag-to-place flag: a hand-placed view
                # (`auto_place=False`) is honored at its authored `position`; the
                # default `True` keeps bounds-aware auto-layout (§4.2).
                auto_place=v.auto_place,
            )
            for v in views
        ],
    )
    # Thread exactly one source (§7). An assembly view echoes the assembly's id +
    # version into the inherited part fields and an EMPTY feature list (geometry does
    # not evaluate them — it projects `assembly`); a part view carries the real prefix.
    if assembly is not None:
        part_id = assembly.assembly_id
        tree_version = assembly.version
        features: list[EvaluatedFeatureInput] = []
    else:
        assert part is not None, "a compose source (part or assembly) is required"
        part_id = part.part_id
        tree_version = part.tree_version
        features = part.features

    return ComposeDrawingRequest(
        part_id=part_id,
        tree_version=tree_version,
        features=features,
        assembly=assembly,
        views=[v.projection for v in views],
        # Thread each persisted view's section datum + flip into the per-view
        # `section_params` map (keyed by the view's INDEX into `views`, mirroring the
        # `views` comprehension above), so a stored `section` view actually cuts +
        # hatches instead of composing empty with `section_params_missing` (audit E1).
        # documents persists `section_params` PER-VIEW (`ViewResponse.section_params`,
        # NULL for every non-section view), so a non-section sheet yields an empty map
        # and composes byte-identically.
        section_params={
            index: view.section_params
            for index, view in enumerate(views)
            if view.section_params is not None
        },
        # A sheet composes at ONE scale (audit H2): documents refuses a view whose
        # scale differs from the sheet's (`sheet_view_scale_mismatch`) and
        # `_assert_single_source` re-checks it here, so view 0's scale IS the
        # sheet's scale rather than an unstated v1 simplification.
        scale=views[0].scale,
        dimensions=dimension_inputs,
        # The sheet's authored free-text notes (design §2.2), in stored order — placed
        # verbatim at their sheet points by `place_sheet` and drawn by every serializer
        # AND the on-screen DrawingSheet (which reads the same `ComposedSheet.notes`).
        # Without this the composed sheet carries no notes, so an authored note is
        # invisible in every export and on screen (WB-64 export-half left this unwired).
        annotations=[a.annotation for a in sheet_content.annotations],
        layout=layout,
        format=artifact_format,
    )


def _select_sheet(
    tree: DrawingTreeResponse, sheet_id: uuid.UUID | None
) -> SheetContent:
    """Pick which sheet to compose — the requested ``sheet_id``, else the first.

    Multi-sheet support (Drawings #21 backend): the compose/export routes accept an
    optional ``sheet`` query param (a sheet id from the drawing tree). When omitted
    the FIRST sheet composes — byte-identical to the pre-multi-sheet single-sheet
    behaviour (back-compat). An unknown/foreign ``sheet_id`` is a ``sheet_not_found``
    404 (the sheet is not part of this drawing); a drawing/sheet with no laid-out
    views is a ``drawing_not_composable`` 422.
    """
    if not tree.sheets:
        raise ValidationApiError(
            "The drawing has no sheets to export; add a sheet and lay out its "
            "standard views first.",
            code="drawing_not_composable",
        )

    if sheet_id is None:
        sheet_content = tree.sheets[0]
    else:
        sheet_content = next((s for s in tree.sheets if s.sheet.id == sheet_id), None)
        if sheet_content is None:
            raise NotFoundError(
                f"Sheet {sheet_id} is not part of drawing {tree.drawing.id}.",
                code="sheet_not_found",
                details={"sheet_id": str(sheet_id)},
            )

    if not sheet_content.views:
        raise ValidationApiError(
            "The sheet has no views to export; lay out its standard views first.",
            code="drawing_not_composable",
        )
    _assert_single_source(sheet_content)
    return sheet_content


def _assert_single_source(sheet_content: SheetContent) -> None:
    """Refuse to compose a sheet whose views disagree on source or scale (**H2**).

    ``ComposeDrawingRequest`` carries exactly ONE source document and ONE scale, so
    :func:`_compose_request` necessarily reduces the sheet to ``views[0]``. documents
    now enforces the matching write-time invariant (``sheet_source_document_mismatch``
    / ``sheet_view_scale_mismatch`` — ``documents.drawings._ensure_sheet_source``);
    this is the READ-side backstop for rows written before that guard (or by any
    future writer): the composed artifact would otherwise project EVERY view from
    view 0's part at view 0's scale while keeping the other views' captions — a
    silently wrong drawing a shop would cut from. Refusing with the SAME typed codes
    the write path uses is the honest outcome; per-view sources/scales are a
    separate slice (BACKLOG), not a silent default.
    """
    source = sheet_content.views[0]
    for view in sheet_content.views[1:]:
        if (
            view.ref_document_id != source.ref_document_id
            or view.ref_document_kind != source.ref_document_kind
        ):
            raise ValidationApiError(
                "This sheet's views reference different documents, which cannot be "
                "composed as one sheet; keep one part or assembly per sheet.",
                code="sheet_source_document_mismatch",
                details={
                    "sheet_id": str(sheet_content.sheet.id),
                    "sheet_ref_document_id": str(source.ref_document_id),
                    "view_id": str(view.id),
                    "ref_document_id": str(view.ref_document_id),
                },
            )
        if view.scale != source.scale:
            raise ValidationApiError(
                "This sheet's views carry different scales, which cannot be "
                "composed as one sheet; per-view scale is not composed in v1.",
                code="sheet_view_scale_mismatch",
                details={
                    "sheet_id": str(sheet_content.sheet.id),
                    "sheet_scale": (
                        f"{source.scale.numerator}:{source.scale.denominator}"
                    ),
                    "view_id": str(view.id),
                    "scale": f"{view.scale.numerator}:{view.scale.denominator}",
                },
            )


async def _aggregate_compose_request(
    drawing_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    artifact_format: ArtifactFormat,
    sheet_id: uuid.UUID | None = None,
) -> ComposeDrawingRequest:
    """The shared two-hop aggregation behind both the export and the sheet route.

    Fetches the drawing tree AND the referenced part/assembly's evaluation-request
    from documents (principal attached, uniform 404 re-surfaced verbatim), then
    assembles the geometry :class:`ComposeDrawingRequest` from that persisted state.
    The REQUESTED sheet (``sheet_id`` — a sheet id from the drawing tree; the FIRST
    sheet when omitted, back-compat) is selected by :func:`_select_sheet`; its first
    view's source-document KIND selects the hop: a part view fetches
    ``/parts/{id}/evaluation-request`` (§4.2), an assembly view
    ``/assemblies/{id}/evaluation-request`` (§7) threaded as ``assembly``. A sheet
    with no laid-out views is a gateway-side ``drawing_not_composable`` 422, an
    unknown ``sheet_id`` a ``sheet_not_found`` 404 (no document hop, no compose).
    ``artifact_format`` rides along for the bytes ``/export`` route; the JSON
    ``/sheet`` route passes the default and ignores it.
    """
    drawing_upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/drawings/{drawing_id}"
    )
    if drawing_upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(drawing_upstream, service=_SERVICE)
    tree = DrawingTreeResponse.model_validate_json(drawing_upstream.content)

    sheet_content = _select_sheet(tree, sheet_id)
    # Composes the selected sheet's single source document. "The sheet's views share
    # ONE document at ONE scale" is an ENFORCED invariant, not an assumption (audit
    # H2): documents refuses the divergent write and `_select_sheet` re-checks the
    # read (`_assert_single_source`), so view 0 is the sheet's source rather than an
    # arbitrary pick. Its kind selects the documents evaluation-request hop + the
    # compose source (design §7).
    source_view = sheet_content.views[0]
    referenced_document_id = source_view.ref_document_id

    if source_view.ref_document_kind == "assembly":
        # Assembly-kind view (§7): resolve the referenced assembly's instance+mate
        # graph → the reused `EvaluateAssemblyRequest` (documents owns the graph read
        # + per-instance part-prefix resolution; the kernel-free INTENT posture), and
        # thread it as the compose source so geometry projects the SOLVED assembly
        # compound and folds its per-view HLR edges into the sheet exactly as a part
        # view. Replaces the old fast-reject `assembly_views_unsupported` 422.
        assembly_upstream = await forward_documents(
            http_request,
            user,
            "GET",
            f"/api/v1/assemblies/{referenced_document_id}/evaluation-request",
        )
        if assembly_upstream.status_code != status.HTTP_200_OK:
            raise_upstream_error(assembly_upstream, service=_SERVICE)
        assembly_request = EvaluateAssemblyRequest.model_validate_json(
            assembly_upstream.content
        )
        return _compose_request(
            tree, sheet_content, artifact_format, assembly=assembly_request
        )

    part_upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/parts/{referenced_document_id}/evaluation-request",
    )
    if part_upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(part_upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(part_upstream.content)

    return _compose_request(
        tree, sheet_content, artifact_format, part=evaluation_request
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
    sheet: Annotated[
        uuid.UUID | None,
        Query(
            description="Which sheet to compose (a sheet id from the drawing tree); "
            "omit to compose the FIRST sheet (back-compat). An unknown/foreign id is "
            "a `sheet_not_found` 404.",
        ),
    ] = None,
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
    compose_request = await _aggregate_compose_request(
        drawing_id, user, http_request, format, sheet_id=sheet
    )

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
        filename = artifact_filename(compose_request.layout.title, format)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    media_type = composed.headers.get("content-type", ARTIFACT_MEDIA_TYPES[format])
    return Response(content=composed.content, media_type=media_type, headers=headers)


@router.post(
    "/{drawing_id}/sheet",
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def compose_drawing_sheet(
    drawing_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    sheet: Annotated[
        uuid.UUID | None,
        Query(
            description="Which sheet to compose (a sheet id from the drawing tree); "
            "omit to compose the FIRST sheet (back-compat). An unknown/foreign id is "
            "a `sheet_not_found` 404.",
        ),
    ] = None,
) -> ComposedSheet:
    """Compose the drawing into the placed ``ComposedSheet`` MODEL (design §4.2, DE-1b).

    The JSON-model twin of ``/{drawing_id}/export``: the SAME auth-gated,
    rate-limited two-hop aggregation (drawing tree + referenced part's
    evaluation-ready feature prefix from documents, principal attached; the compose
    hop is identity-free), but it calls geometry's ``/drawing/compose/sheet`` and
    returns the typed :class:`ComposedSheet` (placed views/edges/dimensions/title
    block in sheet-mm) instead of serialized bytes. This is the single placement
    source the DE-1c frontend cutover renders from — deleting the browser's
    duplicate placement engine. Deterministic (RESEARCH §9); the gateway just relays.
    """
    compose_request = await _aggregate_compose_request(
        drawing_id, user, http_request, "svg", sheet_id=sheet
    )

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    composed = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/drawing/compose/sheet",
        service=_GEOMETRY,
        json_content=compose_request.model_dump_json(),
    )
    if composed.status_code != status.HTTP_200_OK:
        raise_upstream_error(composed, service=_GEOMETRY)
    return ComposedSheet.model_validate_json(composed.content)
