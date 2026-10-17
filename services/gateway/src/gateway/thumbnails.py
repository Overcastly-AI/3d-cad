"""``GET /api/v1/{parts,assemblies,drawings}/{id}/thumbnail`` — library thumbnails.

The registers and the assembly Add panel show a picture of each document
(LIBRARY-THUMBNAILS; Fusion's Data Panel, Onshape's document list). Each route
is the same two-hop aggregation the kind's evaluate already makes:

1. **documents** serves the evaluation request for the CURRENT tree — principal
   attached, so a document the caller does not own is the uniform 404 and no
   other owner's picture can be asked for, cached or not;
2. **geometry** renders it (``/api/v1/thumbnail/{kind}``), cached there by the
   content address of that request, so a tree is rendered once.

**Revalidation, not expiry.** The ``ETag`` is a hash of the same inputs the
geometry cache is keyed on, and the response says ``Cache-Control: private,
no-cache``: the browser keeps the PNG but asks again on every use, and a current
picture costs one documents read and a ``304`` — no geometry hop at all. That is
what keeps the picture honest when something OTHER than the document's own
version changes it (an assembly's child part was edited; a drawing's part was),
and why a version in the URL would not do. Because the documents read comes
first, a revalidation is ownership-checked too.

A document that fails to build or has nothing to draw is geometry's 422
(``thumbnail_failed`` / ``thumbnail_empty``) re-surfaced; the web draws its
placeholder. Rate-limited on its own ``thumbnail`` bucket: opening a register
fetches one per row, and that must not spend the modelling ``compute`` budget.
"""

import hashlib
import uuid

from fastapi import APIRouter, Request, Response, status
from loft_wire.assemblies import EvaluateAssemblyRequest
from loft_wire.features import EvaluateTreeRequest
from loft_wire.thumbnails import (
    THUMBNAIL_MEDIA_TYPE,
    THUMBNAIL_RENDERER_VERSION,
    thumbnail_responses,
)
from pydantic import BaseModel

from gateway.affinity import forward_geometry
from gateway.auth import CurrentUser
from gateway.db import User
from gateway.drawings import aggregate_compose_request
from gateway.parts import forward_documents
from gateway.ratelimit import rate_limited
from gateway.upstream import raise_upstream_error

router = APIRouter(prefix="/api/v1", tags=["thumbnails"])

#: Requests per rate-limit window. Larger than the compute budget (120): one
#: register view is one request per row, and most are 304 revalidations that
#: never reach geometry, whose own admission gate bounds the real renders.
THUMBNAIL_RATE_LIMIT_REQUESTS = 600

THUMBNAIL_RATE_LIMIT = rate_limited("thumbnail", limit=THUMBNAIL_RATE_LIMIT_REQUESTS)

_RESPONSES = thumbnail_responses(
    "A 256x256 PNG of the document's current state: an isometric render of a "
    "part or assembly, or the first sheet of a drawing. `ETag` + `Cache-Control: "
    "private, no-cache`; a conditional request whose `If-None-Match` matches is a "
    "304. A document that does not build is a 422 `thumbnail_failed`, one with "
    "nothing to draw a 422 `thumbnail_empty`.",
    revalidates=True,
)


def thumbnail_etag(kind: str, request: BaseModel) -> str:
    """A strong ETag over everything the picture is a function of."""
    digest = hashlib.sha256(f"{kind}/{THUMBNAIL_RENDERER_VERSION}\n".encode())
    digest.update(request.model_dump_json().encode("utf-8"))
    return f'"{digest.hexdigest()[:40]}"'


def _matches(http_request: Request, etag: str) -> bool:
    header = http_request.headers.get("if-none-match")
    if header is None:
        return False
    candidates = {
        candidate.strip().removeprefix("W/") for candidate in header.split(",")
    }
    return etag in candidates or "*" in candidates


async def _serve(
    kind: str, request: BaseModel, user: User, http_request: Request
) -> Response:
    etag = thumbnail_etag(kind, request)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if _matches(http_request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    rendered = await forward_geometry(
        http_request,
        str(user.id),
        "POST",
        f"/api/v1/thumbnail/{kind}",
        service="Geometry",
        json_content=request.model_dump_json(),
    )
    if rendered.status_code != status.HTTP_200_OK:
        raise_upstream_error(rendered, service="Geometry")
    return Response(
        content=rendered.content, media_type=THUMBNAIL_MEDIA_TYPE, headers=headers
    )


async def _documents_read(http_request: Request, user: User, path: str) -> bytes:
    upstream = await forward_documents(http_request, user, "GET", path)
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service="Documents")
    return upstream.content


@router.get(
    "/parts/{part_id}/thumbnail",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[THUMBNAIL_RATE_LIMIT],
)
async def part_thumbnail(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """The thumbnail of one of the caller's parts (404 for unknown/foreign ids)."""
    body = await _documents_read(
        http_request, user, f"/api/v1/parts/{part_id}/evaluation-request"
    )
    request = EvaluateTreeRequest.model_validate_json(body)
    return await _serve("part", request, user, http_request)


@router.get(
    "/assemblies/{assembly_id}/thumbnail",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[THUMBNAIL_RATE_LIMIT],
)
async def assembly_thumbnail(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """The thumbnail of one of the caller's assemblies, at its solved placements."""
    body = await _documents_read(
        http_request, user, f"/api/v1/assemblies/{assembly_id}/evaluation-request"
    )
    request = EvaluateAssemblyRequest.model_validate_json(body)
    return await _serve("assembly", request, user, http_request)


@router.get(
    "/drawings/{drawing_id}/thumbnail",
    response_class=Response,
    responses=_RESPONSES,
    dependencies=[THUMBNAIL_RATE_LIMIT],
)
async def drawing_thumbnail(
    drawing_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """The thumbnail of the first sheet of one of the caller's drawings."""
    plan = await aggregate_compose_request(drawing_id, user, http_request, "svg")
    return await _serve("drawing", plan.request, user, http_request)
