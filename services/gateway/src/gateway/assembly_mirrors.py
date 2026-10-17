"""``/api/v1/assemblies/{id}/mirrors`` (ASM-MIRROR-COMPONENT).

Component mirrors are stored by documents and placed by geometry. Unlike a
hole-driven pattern, a mirror's count needs no evaluation (one twin per seed),
so the gateway only proxies the writes, under the same auth and ownership
posture as the rest of an assembly; documents' refusals re-surface verbatim.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from loft_wire.assemblies import AssemblyGraphResponse
from loft_wire.component_mirrors import (
    MirrorCreate,
    MirrorMutationResponse,
    MirrorUpdate,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])


@router.post("/{assembly_id}/mirrors", status_code=status.HTTP_201_CREATED)
async def create_mirror(
    assembly_id: uuid.UUID,
    request: MirrorCreate,
    user: CurrentUser,
    http_request: Request,
) -> MirrorMutationResponse:
    """Add a component mirror (201)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/mirrors",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return MirrorMutationResponse.model_validate_json(upstream.content)


@router.patch("/{assembly_id}/mirrors/{mirror_id}")
async def update_mirror(
    assembly_id: uuid.UUID,
    mirror_id: uuid.UUID,
    request: MirrorUpdate,
    user: CurrentUser,
    http_request: Request,
) -> MirrorMutationResponse:
    """Replace a mirror's definition (same id, same place)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/assemblies/{assembly_id}/mirrors/{mirror_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return MirrorMutationResponse.model_validate_json(upstream.content)


@router.delete("/{assembly_id}/mirrors/{mirror_id}")
async def delete_mirror(
    assembly_id: uuid.UUID,
    mirror_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Delete a mirror and its twins; returns the updated graph."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/assemblies/{assembly_id}/mirrors/{mirror_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)
