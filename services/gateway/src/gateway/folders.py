"""``/api/v1/folders`` (+ the three document ``/move`` routes) — filing (#WS2).

Auth-protected aggregation over the documents service, exactly the posture
:mod:`gateway.parts` documents: apps/web talks ONLY to the gateway, every route
resolves the caller through the JWT bearer dependency and forwards with the
verified principal attached, and DTOs are the shared py-kit models
(:mod:`py_kit.schemas.folders`) rather than hand-duplicated shapes.

The three ``/move`` routes live here beside the folder CRUD rather than in
``gateway.parts`` / ``.assemblies`` / ``.drawings``: filing is one verb over
three nouns, and the documents side implements it once for the same reason.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from py_kit.schemas.assemblies import AssemblyResponse
from py_kit.schemas.drawings import DrawingResponse
from py_kit.schemas.folders import (
    DocumentMove,
    FolderCreate,
    FolderKind,
    FolderListResponse,
    FolderMove,
    FolderNotEmptyEnvelope,
    FolderRename,
    FolderResponse,
)
from py_kit.schemas.parts import PartResponse

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: The documented 409 of the folder delete: a folder that still holds things is
#: refused, and ``details.contents`` NAMES them. Declaring the model puts
#: :class:`~py_kit.schemas.folders.FolderContents` in the OpenAPI contract and
#: therefore in the generated TS client, so the register lists what is inside
#: from a type — the same treatment the document delete's dependents payload
#: gets, because a user should meet one refusal grammar, not two.
FOLDER_NOT_EMPTY_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": FolderNotEmptyEnvelope,
        "description": "Folder still holds items; `details.contents` names them.",
    }
}

router = APIRouter(prefix="/api/v1/folders", tags=["folders"])
parts_router = APIRouter(prefix="/api/v1/parts", tags=["parts"])
assemblies_router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])
drawings_router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(
    request: FolderCreate, user: CurrentUser, http_request: Request
) -> FolderResponse:
    """Create a folder in one drawer (201; 409 on a duplicate sibling name)."""
    upstream = await forward_documents(
        http_request, user, "POST", "/api/v1/folders", request.model_dump_json()
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return FolderResponse.model_validate_json(upstream.content)


@router.get("")
async def list_folders(
    user: CurrentUser,
    http_request: Request,
    kind: Annotated[FolderKind, Query(description="Which drawer's tree to return")],
) -> FolderListResponse:
    """The caller's whole folder tree for one drawer, name-ordered."""
    upstream = await forward_documents(
        http_request, user, "GET", "/api/v1/folders", params={"kind": kind}
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FolderListResponse.model_validate_json(upstream.content)


@router.patch("/{folder_id}")
async def rename_folder(
    folder_id: uuid.UUID,
    request: FolderRename,
    user: CurrentUser,
    http_request: Request,
) -> FolderResponse:
    """Rename a folder (404 unknown/foreign; 409 duplicate sibling name)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/folders/{folder_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FolderResponse.model_validate_json(upstream.content)


@router.post("/{folder_id}/move")
async def move_folder(
    folder_id: uuid.UUID,
    request: FolderMove,
    user: CurrentUser,
    http_request: Request,
) -> FolderResponse:
    """Re-parent a folder; ``parent_id: null`` moves it to the root.

    422 ``folder_cycle`` when the destination is the folder itself or one of its
    own descendants — a move that would put the subtree somewhere no register
    view can reach.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/folders/{folder_id}/move",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FolderResponse.model_validate_json(upstream.content)


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=FOLDER_NOT_EMPTY_RESPONSE,
)
async def delete_folder(
    folder_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> None:
    """Delete an EMPTY folder (204); 409 naming its contents when it is not.

    Never a cascade: a folder delete cannot take documents with it, so the
    refusal names what to move out first (see :data:`FOLDER_NOT_EMPTY_RESPONSE`).
    """
    upstream = await forward_documents(
        http_request, user, "DELETE", f"/api/v1/folders/{folder_id}"
    )
    if upstream.status_code != status.HTTP_204_NO_CONTENT:
        raise_upstream_error(upstream, service=_SERVICE)


@parts_router.post("/{part_id}/move")
async def move_part(
    part_id: uuid.UUID,
    request: DocumentMove,
    user: CurrentUser,
    http_request: Request,
) -> PartResponse:
    """File a part into a folder, or un-file it with ``folder_id: null``.

    Returns the part as STORED, so the register renders where the server put it.
    Filing is not a document edit: it moves neither ``tree_version`` nor
    ``updated_at``, so LAST WORKED keeps meaning "someone worked on it".
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/move",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartResponse.model_validate_json(upstream.content)


@assemblies_router.post("/{assembly_id}/move")
async def move_assembly(
    assembly_id: uuid.UUID,
    request: DocumentMove,
    user: CurrentUser,
    http_request: Request,
) -> AssemblyResponse:
    """File an assembly into a folder, or un-file it — see :func:`move_part`."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/assemblies/{assembly_id}/move",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return AssemblyResponse.model_validate_json(upstream.content)


@drawings_router.post("/{drawing_id}/move")
async def move_drawing(
    drawing_id: uuid.UUID,
    request: DocumentMove,
    user: CurrentUser,
    http_request: Request,
) -> DrawingResponse:
    """File a drawing into a folder, or un-file it — see :func:`move_part`."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/drawings/{drawing_id}/move",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return DrawingResponse.model_validate_json(upstream.content)
