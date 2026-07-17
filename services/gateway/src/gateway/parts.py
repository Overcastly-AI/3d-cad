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

import httpx2 as httpx
from fastapi import APIRouter, Request, status
from py_kit.schemas.parts import (
    PRINCIPAL_HEADER,
    PartCreate,
    PartListResponse,
    PartResponse,
    PartUpdate,
)

from gateway.auth import CurrentUser
from gateway.db import User
from gateway.upstream import create_upstream_client, forward, raise_upstream_error

#: Upstream call budget — documents queries are cheap OLTP round-trips.
DOCUMENTS_TIMEOUT_S = 10.0

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
    """Rename and/or re-unit one of the caller's parts (bumps ``tree_version``).

    The document-unit selector (docs/design/units.md §U1) changes ``length_unit``
    through this route; 404 envelope for unknown/foreign ids, 422 on a stale
    ``expected_tree_version``, 409 on a duplicate name.
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


@router.delete("/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete one of the caller's parts (204; 404 for unknown/foreign ids)."""
    upstream = await forward_documents(
        http_request, user, "DELETE", f"/api/v1/parts/{part_id}"
    )
    if upstream.status_code != status.HTTP_204_NO_CONTENT:
        raise_upstream_error(upstream, service=_SERVICE)
