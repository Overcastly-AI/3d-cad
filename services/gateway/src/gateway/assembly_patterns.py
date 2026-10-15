"""``/api/v1/assemblies/{id}/patterns`` and the pattern counts (ASM-A3).

Component patterns are stored by documents and placed by geometry. One thing
needs both: a HOLE-DRIVEN pattern's count is the driving part's hole count,
which only an evaluation knows, while the bill of materials and the instance
bound are documents' read models. The gateway joins them, as it does for an
assembly's extents:

- writing a hole-driven pattern, the gateway asks geometry for its count
  (``/assembly/pattern-counts`` over the assembly's evaluation request with
  the new definition in place) and passes it to documents as
  ``driven_count``, which documents counts against the instance bound for the
  assembly and every assembly containing it. A count past the bound is the
  typed ``assembly_too_large``; a pattern geometry cannot place is refused
  with geometry's own code;
- reading a BOM (the assembly's, or a drawing's parts list), when documents
  reports hole-driven patterns it could not count, the gateway resolves them
  the same way and reads the BOM again with the counts, so the BOM follows a
  part edit that adds or removes holes. One that still does not resolve stays
  in ``unresolved_patterns``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from loft_wire.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    AssemblyGraphResponse,
    EvaluateAssemblyRequest,
)
from loft_wire.component_patterns import (
    ComponentPatternParams,
    EvaluatedPattern,
    HoleComponentPattern,
    PatternCountsResult,
    PatternCreate,
    PatternMutationResponse,
    PatternUpdate,
)
from py_kit import ValidationApiError

from gateway.affinity import forward_geometry
from gateway.auth import CurrentUser
from gateway.db import User
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"
_GEOMETRY = "Geometry"

router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])


async def _evaluation_request(
    http_request: Request, user: User, assembly_id: uuid.UUID
) -> EvaluateAssemblyRequest:
    upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/assemblies/{assembly_id}/evaluation-request",
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return EvaluateAssemblyRequest.model_validate_json(upstream.content)


async def _counts(
    http_request: Request, user: User, request: EvaluateAssemblyRequest
) -> PatternCountsResult:
    upstream = await forward_geometry(
        http_request,
        str(user.id),
        "POST",
        "/api/v1/assembly/pattern-counts",
        service=_GEOMETRY,
        json_content=request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_GEOMETRY)
    return PatternCountsResult.model_validate_json(upstream.content)


async def resolved_counts(
    http_request: Request, user: User, assembly_id: uuid.UUID
) -> list[str]:
    """``pattern_count`` query values (``<pattern id>:<count>``) for every
    pattern of the assembly that geometry can count, at every level."""
    request = await _evaluation_request(http_request, user, assembly_id)
    result = await _counts(http_request, user, request)
    return [
        f"{state.pattern_id}:{state.count}"
        for state in result.counts
        if state.count is not None
    ]


async def _driven_count(
    http_request: Request,
    user: User,
    assembly_id: uuid.UUID,
    pattern: ComponentPatternParams,
    pattern_id: uuid.UUID | None,
) -> dict[str, str] | None:
    """The ``driven_count`` query for a hole-driven pattern write, or 422."""
    if not isinstance(pattern, HoleComponentPattern):
        return None
    request = await _evaluation_request(http_request, user, assembly_id)
    candidate_id = pattern_id or uuid.uuid4()
    others = [p for p in request.patterns if p.pattern_id != candidate_id]
    candidate = EvaluatedPattern(
        pattern_id=candidate_id,
        order_index=max((p.order_index for p in others), default=-1) + 1,
        pattern=pattern,
    )
    probe = request.model_copy(update={"patterns": [*others, candidate]})
    result = await _counts(http_request, user, probe)
    state = next(s for s in result.counts if s.pattern_id == candidate_id)
    if state.error_code == "pattern_too_large" or (
        state.count is not None and state.count > MAX_ASSEMBLY_INSTANCES
    ):
        raise ValidationApiError(
            state.error_message
            or f"This pattern would place more than {MAX_ASSEMBLY_INSTANCES} "
            "components; at most that many can be evaluated at once.",
            code="assembly_too_large",
            details={"max_instances": MAX_ASSEMBLY_INSTANCES},
        )
    if state.count is None:
        raise ValidationApiError(
            state.error_message or "The pattern's holes could not be found.",
            code=state.error_code or "pattern_unresolved",
        )
    return {"driven_count": str(state.count)}


@router.post("/{assembly_id}/patterns", status_code=status.HTTP_201_CREATED)
async def create_pattern(
    assembly_id: uuid.UUID,
    request: PatternCreate,
    user: CurrentUser,
    http_request: Request,
) -> PatternMutationResponse:
    """Add a component pattern (201). A hole-driven pattern is counted by
    geometry first; documents' refusals re-surface verbatim."""
    params = await _driven_count(http_request, user, assembly_id, request.pattern, None)
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/patterns",
        request.model_dump_json(),
        params=params,
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return PatternMutationResponse.model_validate_json(upstream.content)


@router.patch("/{assembly_id}/patterns/{pattern_id}")
async def update_pattern(
    assembly_id: uuid.UUID,
    pattern_id: uuid.UUID,
    request: PatternUpdate,
    user: CurrentUser,
    http_request: Request,
) -> PatternMutationResponse:
    """Replace a pattern's definition (same id, same place)."""
    params = await _driven_count(
        http_request, user, assembly_id, request.pattern, pattern_id
    )
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/assemblies/{assembly_id}/patterns/{pattern_id}",
        request.model_dump_json(),
        params=params,
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PatternMutationResponse.model_validate_json(upstream.content)


@router.delete("/{assembly_id}/patterns/{pattern_id}")
async def delete_pattern(
    assembly_id: uuid.UUID,
    pattern_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> AssemblyGraphResponse:
    """Delete a pattern and its copies; returns the updated graph."""
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/assemblies/{assembly_id}/patterns/{pattern_id}",
        params={"expected_version": str(expected_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyGraphResponse.model_validate_json(upstream.content)
