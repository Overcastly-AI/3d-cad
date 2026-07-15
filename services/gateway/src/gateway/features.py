"""``/api/v1/parts/{part_id}/features`` — auth-protected feature-tree
aggregation over the documents service.

Same posture as :mod:`gateway.parts` (apps/web talks ONLY to the gateway):
every route resolves the caller through the JWT bearer dependency and
forwards via :func:`gateway.parts.forward_documents`, which attaches the
verified principal header. DTOs are the shared py-kit feature models —
never hand-duplicated — so request bodies are fully validated at the gateway
before anything goes upstream, and upstream 404/409/422 envelopes (including
the ``feature_has_dependents`` conflict and ``stale_tree_version``) are
re-surfaced verbatim under the gateway's request id.

``POST /{part_id}/evaluate`` is the one two-hop aggregation: documents builds
the evaluation-ready request (rollback + upcasts applied), the gateway relays
it to the geometry service, and the typed ``EvaluateTreeResult`` — solved
sketch payloads included — returns to the caller. This keeps "the web app
talks only to the gateway" true for feature evaluation without documents ever
calling geometry itself.
"""

import uuid
from typing import Annotated

import httpx2 as httpx
from fastapi import APIRouter, Query, Request, Response, status
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExportTreeRequest,
    FeatureCreate,
    FeatureMutationResponse,
    FeatureReorderRequest,
    FeatureResponse,
    FeatureTreeResponse,
    FeatureUpdate,
    RollbackBarMove,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, ExportFormat, export_responses

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import forward, raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: The geometry hop of the evaluate aggregation (error surfaces name it).
_GEOMETRY = "Geometry"

router = APIRouter(prefix="/api/v1/parts", tags=["features"])


@router.get("/{part_id}/features")
async def get_feature_tree(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> FeatureTreeResponse:
    """The part's ordered feature tree (404 for unknown/foreign parts)."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/features"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.get("/{part_id}/features/{feature_id}")
async def get_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
) -> FeatureResponse:
    """One feature of the caller's part."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/features/{feature_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/features", status_code=status.HTTP_201_CREATED)
async def create_feature(
    part_id: uuid.UUID,
    request: FeatureCreate,
    user: CurrentUser,
    http_request: Request,
) -> FeatureMutationResponse:
    """Create a feature (201; 422 envelope on stale version / bad refs)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/features",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)


@router.patch("/{part_id}/features/{feature_id}")
async def update_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    request: FeatureUpdate,
    user: CurrentUser,
    http_request: Request,
) -> FeatureMutationResponse:
    """Rename and/or replace a feature's params."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)


@router.delete("/{part_id}/features/{feature_id}")
async def delete_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    expected_tree_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Delete a feature (409 envelope listing dependents when referenced)."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        params={"expected_tree_version": str(expected_tree_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.put("/{part_id}/features/order")
async def reorder_features(
    part_id: uuid.UUID,
    request: FeatureReorderRequest,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Apply a full permutation of the tree (backward-only refs re-checked)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        f"/api/v1/parts/{part_id}/features/order",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/evaluate", dependencies=[COMPUTE_RATE_LIMIT])
async def evaluate_part(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> EvaluateTreeResult:
    """Evaluate the part's current feature tree (feature-tree design §4).

    The full loop behind one authenticated call: documents serves the
    evaluation-ready list (rollback bar applied, params upcast — §4.2), the
    gateway forwards it verbatim to the stateless geometry service, and the
    typed result comes back with per-feature statuses and solved-sketch
    ``data`` payloads (§7.10). Feature failures are a 200 with per-feature
    errors (§4.3); the error envelope here means the aggregation itself
    failed (404 unknown part, 502 unreachable upstream, ...).
    """
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/evaluation-request"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(upstream.content)

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    evaluated = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/evaluate",
        service=_GEOMETRY,
        json_content=evaluation_request.model_dump_json(),
    )
    if evaluated.status_code != status.HTTP_200_OK:
        raise_upstream_error(evaluated, service=_GEOMETRY)
    return EvaluateTreeResult.model_validate_json(evaluated.content)


_EXPORT_RESPONSES = export_responses(
    "The exported CAD file of the part's current evaluated body, proxied "
    "byte-exact from the geometry service: STEP AP214 part 21 (`model/step`, "
    "exact B-rep) or binary STL (`model/stl`, faceted mesh). "
    "`Content-Disposition` carries the suggested download filename. A tree "
    "that evaluates to no body is a 422 `tree_export_failed` envelope."
)


@router.post(
    "/{part_id}/export",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def export_part(
    part_id: uuid.UUID,
    format: Annotated[
        ExportFormat, Query(description="Export file format: STEP or STL")
    ],
    user: CurrentUser,
    http_request: Request,
) -> Response:
    """Export the part's current evaluated body as a STEP or STL download.

    The export twin of :func:`evaluate_part` and the same two-hop aggregation:
    documents serves the evaluation-ready feature list (rollback bar applied,
    params upcast — §4.2), the gateway wraps it with the requested format into
    an ``ExportTreeRequest`` and relays it to the stateless geometry service's
    tree-export route, and the file bytes stream back byte-exact. Auth-scoped
    like every parts route (the principal reaches documents, never geometry).
    A tree with no body is the geometry service's 422 ``tree_export_failed``
    envelope, re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/evaluation-request"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(upstream.content)
    export_request = ExportTreeRequest.model_validate(
        {**evaluation_request.model_dump(mode="json"), "format": format}
    )

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    exported = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/export/tree",
        service=_GEOMETRY,
        json_content=export_request.model_dump_json(),
    )
    if exported.status_code != status.HTTP_200_OK:
        raise_upstream_error(exported, service=_GEOMETRY)
    headers: dict[str, str] = {}
    if "content-disposition" in exported.headers:
        headers["Content-Disposition"] = exported.headers["content-disposition"]
    return Response(
        content=exported.content,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers=headers,
    )


@router.put("/{part_id}/rollback")
async def move_rollback_bar(
    part_id: uuid.UUID,
    request: RollbackBarMove,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Move the rollback bar (null = bar at the tip)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        f"/api/v1/parts/{part_id}/rollback",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)
