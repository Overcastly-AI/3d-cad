"""``/api/v1/parts`` — auth-protected aggregation over the documents service.

apps/web talks ONLY to the gateway (CLAUDE.md service boundaries), so parts
CRUD is surfaced here. Every route resolves the caller through the JWT bearer
dependency (:mod:`gateway.auth`) and forwards to documents with the resulting
user id in the ``X-Loft-User`` principal header — documents is internal (not
publicly exposed) and trusts that header; the JWT itself never crosses the
boundary. DTOs are the shared py-kit models the documents service serves,
never hand-duplicated; bodies pass through as-parsed, and upstream 404/409
envelopes are re-surfaced verbatim under the gateway's request id.
"""

import uuid
from typing import Any

import httpx2 as httpx
from fastapi import APIRouter, Request, status
from py_kit.schemas.parts import (
    PRINCIPAL_HEADER,
    PartCreate,
    PartListResponse,
    PartResponse,
    PartUpdate,
)
from py_kit.schemas.workspace import DependencyConflictEnvelope

from gateway.auth import CurrentUser
from gateway.db import User
from gateway.upstream import create_upstream_client, forward, raise_upstream_error

#: Upstream call budget — documents queries are cheap OLTP round-trips.
DOCUMENTS_TIMEOUT_S = 10.0

#: The documented 409 of every document delete that can be refused over
#: references (parts, assemblies — a drawing is a leaf and has none).
#:
#: Declaring the model is what makes the refusal ACTIONABLE end to end: it puts
#: :class:`~py_kit.schemas.workspace.DocumentDependents` in the OpenAPI contract
#: and therefore in the generated TS client, so the register lists the assemblies
#: and drawings that hold the reference — the whole point of refusing — from a
#: typed payload instead of hopefully parsing an untyped ``details`` blob.
DEPENDENCY_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": DependencyConflictEnvelope,
        "description": (
            "Still referenced by other documents; `details.dependents` names them."
        ),
    }
}

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/parts", tags=["parts"])


def create_documents_client(
    documents_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The documents upstream client (see :func:`create_upstream_client`)."""
    return create_upstream_client(
        documents_url, timeout_s=DOCUMENTS_TIMEOUT_S, transport=transport
    )


async def forward_documents(
    http_request: Request,
    user: User,
    method: str,
    path: str,
    json_content: str | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """Forward to documents with the authenticated principal attached.

    Shared by the parts and features aggregation routers (DRY) — one place
    owns the principal-header contract with the documents service.
    """
    client: httpx.AsyncClient = http_request.app.state.documents_client
    return await forward(
        client,
        http_request,
        method,
        path,
        service=_SERVICE,
        json_content=json_content,
        headers={PRINCIPAL_HEADER: str(user.id)},
        params=params,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_part(
    request: PartCreate, user: CurrentUser, http_request: Request
) -> PartResponse:
    """Create a part owned by the caller (201; 409 envelope on duplicate name)."""
    upstream = await forward_documents(
        http_request, user, "POST", "/api/v1/parts", request.model_dump_json()
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartResponse.model_validate_json(upstream.content)


@router.get("")
async def list_parts(user: CurrentUser, http_request: Request) -> PartListResponse:
    """The caller's parts, oldest first."""
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/parts")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartListResponse.model_validate_json(upstream.content)


@router.get("/{part_id}")
async def get_part(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> PartResponse:
    """One of the caller's parts (404 envelope for unknown/foreign ids)."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartResponse.model_validate_json(upstream.content)


@router.patch("/{part_id}")
async def update_part(
    part_id: uuid.UUID,
    request: PartUpdate,
    user: CurrentUser,
    http_request: Request,
) -> PartResponse:
    """Rename, re-unit and/or re-material one of the caller's parts.

    Bumps ``tree_version``. The document-unit selector (docs/design/units.md
    §U1) changes ``length_unit`` through this route and the material picker
    (docs/design/materials.md §2) changes ``materials`` — the latter is the one
    header edit that invalidates the recorded evaluate, because mass is derived
    from it. 404 envelope for unknown/foreign ids, 422 on a stale
    ``expected_tree_version`` or an update naming no field, 409 on a duplicate
    name.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/parts/{part_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_part(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> PartResponse:
    """Copy a part and its WHOLE feature tree at its current version (201).

    Exactly what a duplicate does and does not copy is documented once, upstream
    (:mod:`documents.duplicate`); the short version is: every feature, its
    params, its dependency edges and the travel stop, plus the display unit and
    materials — but not the undo history and not the last-evaluate record (the
    copy has never been built, and its register row says so).

    No request body: the copy's name is the server's to assign (``"<name>
    copy"``, then ``" copy 2"``…) and the created part is returned, so the
    register renders the name that was actually taken rather than one it
    predicted. 409 if that name is somehow taken anyway; rename and retry.
    """
    upstream = await forward_documents(
        http_request, user, "POST", f"/api/v1/parts/{part_id}/duplicate"
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartResponse.model_validate_json(upstream.content)


@router.delete(
    "/{part_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=DEPENDENCY_CONFLICT_RESPONSE,
)
async def delete_part(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete one of the caller's parts (204; 404 for unknown/foreign ids).

    409 while an assembly still instances it or a drawing still projects it,
    with the referencing documents NAMED in ``details.dependents`` — see
    :data:`DEPENDENCY_CONFLICT_RESPONSE`.
    """
    upstream = await forward_documents(
        http_request, user, "DELETE", f"/api/v1/parts/{part_id}"
    )
    if upstream.status_code != status.HTTP_204_NO_CONTENT:
        raise_upstream_error(upstream, service=_SERVICE)
