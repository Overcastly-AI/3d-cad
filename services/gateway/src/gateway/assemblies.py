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
    AssemblyBomResponse,
    AssemblyCreate,
    AssemblyExtentsResponse,
    AssemblyGraphResponse,
    AssemblyListResponse,
    AssemblyResponse,
    AssemblyUndoRedoRequest,
    AssemblyUpdate,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    InstanceCreate,
    InstanceMutationResponse,
    InstanceUpdate,
    MateCreate,
    MateMutationResponse,
)

from gateway.affinity import forward_geometry
from gateway.auth import CurrentUser
from gateway.parts import DEPENDENCY_CONFLICT_RESPONSE, forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: The OTHER upstream this module reaches, on the extents path only: an
#: assembly's SIZE is a mate solve, and geometry is the sole evaluator.
_GEOMETRY = "Geometry"

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


@router.get("/{assembly_id}/bom")
async def get_assembly_bom(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> AssemblyBomResponse:
    """The assembly's flat bill of materials (direct instances only; uniform 404).

    Documents aggregates the read model (one line per referenced document,
    quantity = shared-reference count, current name + kind, deleted-ref lines
    flagged ``missing``); the gateway proxies faithfully under the same
    auth/ownership posture as :func:`get_assembly`.
    """
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/assemblies/{assembly_id}/bom"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyBomResponse.model_validate_json(upstream.content)


@router.get("/{assembly_id}/extents", dependencies=[COMPUTE_RATE_LIMIT])
async def get_assembly_extents(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> AssemblyExtentsResponse:
    """How big this assembly is once its mates are SOLVED (assemblies §4).

    The two-hop aggregation ``POST /parts/{id}/evaluate`` already gives a part
    caller, narrowed to the one quantity a caller who holds only an id can
    otherwise not obtain: documents resolves the instance + mate graph
    (``/assemblies/{id}/evaluation-request`` — principal-scoped, so ownership
    and the uniform 404 come for free), geometry solves it, and the solved
    compound's AABB comes back with the status it was solved under. Rolling
    this by hand meant reproducing the whole graph-plus-part-trees read the
    assembly editor does, which is why a drawing sheet drafting an assembly
    could not fit its scale and overflowed its title block.

    **SOLVED, not seeded.** The bbox is the union over each instance's part
    bbox at its MATE-SOLVED world pose; the authored seed placements are what
    produce the wrong (usually far too large) answer, so this route deliberately
    pays for the solve rather than folding the graph's seeds client-side.

    A GET because it is a read: nothing is persisted, the same assembly yields
    the same extents (RESEARCH §9 determinism), and the caller sends no body.
    Rate-limited on the compute bucket all the same — a solve IS geometry CPU,
    whatever the verb.

    Cost note: geometry has no mesh-free solve route, so this pays for the
    per-unique-part tessellation as well. That is not free, but it is not waste
    either — the default ``linear_deflection`` is used deliberately, so the
    meshes warmed here are the SAME content-addressed meshes the viewport's own
    ``/geometry/assembly/evaluate`` asks for. A ``tessellate: false`` request
    flag is the follow-up if a profile ever shows this on a hot path.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/assemblies/{assembly_id}/evaluation-request",
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    evaluation_request = EvaluateAssemblyRequest.model_validate_json(upstream.content)

    evaluated = await forward_geometry(
        http_request,
        str(user.id),
        "POST",
        "/api/v1/assembly/evaluate",
        service=_GEOMETRY,
        json_content=evaluation_request.model_dump_json(),
    )
    if evaluated.status_code != status.HTTP_200_OK:
        raise_upstream_error(evaluated, service=_GEOMETRY)
    result = EvaluateAssemblyResult.model_validate_json(evaluated.content)
    return AssemblyExtentsResponse(
        assembly_id=result.assembly_id,
        version=result.version,
        bounding_box=result.bounding_box,
        status=result.status,
    )


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


@router.post("/{assembly_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_assembly(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> AssemblyResponse:
    """Copy an assembly's instances and mates — NOT the parts they name (201).

    Both assemblies reference the same parts afterwards, because an instance IS
    a reference: edit one of those parts and the change shows up in both. See
    :mod:`documents.duplicate` for the full statement of what a copy carries.
    The copy's name is the server's to assign and the created assembly is
    returned.
    """
    upstream = await forward_documents(
        http_request, user, "POST", f"/api/v1/assemblies/{assembly_id}/duplicate"
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyResponse.model_validate_json(upstream.content)


@router.delete(
    "/{assembly_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=DEPENDENCY_CONFLICT_RESPONSE,
)
async def delete_assembly(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete an owned assembly (204; 409 when instanced as a sub-assembly).

    The refusal NAMES the referencing documents in ``details.dependents``
    (:data:`~gateway.parts.DEPENDENCY_CONFLICT_RESPONSE`).
    """
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
