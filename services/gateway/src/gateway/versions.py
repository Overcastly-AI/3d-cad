"""``/api/v1/parts/{part_id}/versions`` — named part versions (LOFT-VERSIONS).

Thin, auth-gated forwards over :mod:`documents.versions`, like every feature
route: the caller is resolved from the JWT, documents scopes the part to that
owner (another owner's part is a 404), and upstream 404/409/422 envelopes are
re-surfaced verbatim. Bodies are the shared :mod:`loft_wire.versions` models,
validated here before anything goes upstream.

The author recorded with a version is the display name the caller sends, and
nothing else: the gateway never adds the account's email or id to it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Request, status
from loft_wire.features import FeatureTreeResponse
from loft_wire.versions import (
    MAX_PART_VERSION_SEQ,
    PartVersion,
    PartVersionCreate,
    PartVersionListResponse,
    PartVersionRestore,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/parts", tags=["versions"])


@router.post("/{part_id}/versions", status_code=status.HTTP_201_CREATED)
async def save_part_version(
    part_id: uuid.UUID,
    request: PartVersionCreate,
    user: CurrentUser,
    http_request: Request,
) -> PartVersion:
    """Save the part's current tree as a named version (201).

    Versions are never pruned: past the per-part cap a save is refused with
    409 `part_version_limit`. A stale `expected_tree_version` is a 422.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/versions",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartVersion.model_validate_json(upstream.content)


@router.get("/{part_id}/versions")
async def list_part_versions(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> PartVersionListResponse:
    """The part's named versions, newest first."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/versions"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartVersionListResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/versions/{seq}/restore")
async def restore_part_version(
    part_id: uuid.UUID,
    seq: Annotated[int, Path(ge=1, le=MAX_PART_VERSION_SEQ)],
    request: PartVersionRestore,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Make a saved version the part's tree, as one undoable edit.

    The response is the restored tree with its new `tree_version`; undo walks
    back to the tree before the restore. Later versions are kept. A stale
    `expected_tree_version` is a 422; a restore that would break a drawing's
    section view is a 409 `part_restore_conflict`.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/versions/{seq}/restore",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)
