"""``/api/v1/assemblies`` — auth-protected assembly-graph aggregation over the
documents service.

Same posture as :mod:`gateway.parts` / :mod:`gateway.features` (apps/web talks
ONLY to the gateway, CLAUDE.md service boundaries): every route resolves the
caller through the JWT bearer dependency and forwards via
:func:`gateway.parts.forward_documents`, which attaches the verified principal
header (``X-Loft-User``). Documents owns owner-scoping, optimistic concurrency
(``expected_version`` → 422 on stale), the delete-with-dependents 409, and
uniform 404 visibility — the gateway proxies faithfully and re-surfaces those
envelopes verbatim under its own request id. DTOs are the shared py-kit
assembly models (single source of truth, never hand-duplicated), so request
bodies are fully validated at the gateway before anything goes upstream.

Every route is auth-gated from day one (``user: CurrentUser``) — heeding
engineering audit F7 (the tessellate/export unauthenticated-route class): an
assembly graph is a signed-in user's document, never anonymously reachable.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from py_kit.schemas.assemblies import (
    AssemblyCreate,
    AssemblyGraphResponse,
    AssemblyListResponse,
    AssemblyResponse,
    AssemblyUndoRedoRequest,
    AssemblyUpdate,
    InstanceCreate,
    InstanceMutationResponse,
    InstanceUpdate,
    MateCreate,
    MateMutationResponse,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])


# --- assembly routes --------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_assembly(
    request: AssemblyCreate, user: CurrentUser, http_request: Request
) -> AssemblyResponse:
    """Create an assembly owned by the caller (201; 409 envelope on duplicate name)."""
    upstream = await forward_documents(
        http_request, user, "POST", "/api/v1/assemblies", request.model_dump_json()
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyResponse.model_validate_json(upstream.content)


@router.get("")
async def list_assemblies(
    user: CurrentUser, http_request: Request
) -> AssemblyListResponse:
    """The caller's assemblies, oldest first."""
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/assemblies")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyListResponse.model_validate_json(upstream.content)


@router.get("/{assembly_id}")
async def get_assembly(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> AssemblyGraphResponse:
    """One owned assembly with its full instance + mate graph (uniform 404)."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/assemblies/{assembly_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)


@router.patch("/{assembly_id}")
async def update_assembly(
    assembly_id: uuid.UUID,
    request: AssemblyUpdate,
    user: CurrentUser,
    http_request: Request,
) -> AssemblyResponse:
    """Rename an assembly (bumps ``doc_version``; 422 stale / 409 name clash)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/assemblies/{assembly_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyResponse.model_validate_json(upstream.content)


@router.delete("/{assembly_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assembly(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete an owned assembly (204; 409 when instanced as a sub-assembly)."""
    upstream = await forward_documents(
        http_request, user, "DELETE", f"/api/v1/assemblies/{assembly_id}"
    )
    if upstream.status_code != status.HTTP_204_NO_CONTENT:
        raise_upstream_error(upstream, service=_SERVICE)


# --- instance routes --------------------------------------------------------------


@router.post("/{assembly_id}/instances", status_code=status.HTTP_201_CREATED)
async def create_instance(
    assembly_id: uuid.UUID,
    request: InstanceCreate,
    user: CurrentUser,
    http_request: Request,
) -> InstanceMutationResponse:
    """Add an instance referencing a part / sub-assembly (201).

    Documents enforces cross-document integrity (existence + acyclicity) and
    the optimistic-concurrency guard; its 422 envelopes (``ref_document_not_found``,
    ``assembly_cycle``, ``stale_assembly_version``) are re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/instances",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return InstanceMutationResponse.model_validate_json(upstream.content)


@router.patch("/{assembly_id}/instances/{instance_id}")
async def update_instance(
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
    request: InstanceUpdate,
    user: CurrentUser,
    http_request: Request,
) -> InstanceMutationResponse:
    """Re-place / rename / (un)ground / reorder an instance (bumps ``doc_version``)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return InstanceMutationResponse.model_validate_json(upstream.content)


@router.delete("/{assembly_id}/instances/{instance_id}")
async def delete_instance(
    assembly_id: uuid.UUID,
    instance_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Remove an instance (cascades mates naming it); returns the updated graph."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)


# --- mate routes ------------------------------------------------------------------


@router.post("/{assembly_id}/mates", status_code=status.HTTP_201_CREATED)
async def create_mate(
    assembly_id: uuid.UUID,
    request: MateCreate,
    user: CurrentUser,
    http_request: Request,
) -> MateMutationResponse:
    """Add a mate (201). Documents checks every named instance belongs to the
    assembly (``mate_instance_unknown`` / ``mate_self_reference`` 422 otherwise)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/mates",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return MateMutationResponse.model_validate_json(upstream.content)


@router.post("/{assembly_id}/undo")
async def undo_assembly(
    assembly_id: uuid.UUID,
    request: AssemblyUndoRedoRequest,
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Undo one assembly-graph history step (docs/design/undo-redo.md UR3).

    The restored graph comes back with its new ``doc_version`` (and
    ``can_undo``/``can_redo``); at the ring's floor this is documents' clean
    no-op (current graph, version unchanged). Stale ``expected_version`` →
    422, resurfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/undo",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)


@router.post("/{assembly_id}/redo")
async def redo_assembly(
    assembly_id: uuid.UUID,
    request: AssemblyUndoRedoRequest,
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Redo one assembly-graph history step (clean no-op at the ring's top)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/redo",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)


@router.delete("/{assembly_id}/mates/{mate_id}")
async def delete_mate(
    assembly_id: uuid.UUID,
    mate_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Remove a mate; returns the updated graph (bumps ``doc_version``)."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/assemblies/{assembly_id}/mates/{mate_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)
