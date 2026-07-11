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
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from py_kit.schemas.features import (
    FeatureCreate,
    FeatureMutationResponse,
    FeatureReorderRequest,
    FeatureResponse,
    FeatureTreeResponse,
    FeatureUpdate,
    RollbackBarMove,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

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
