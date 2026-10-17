"""Cut lists of parts and assemblies, as JSON and CSV (CUT-LIST).

The gateway is the one participant that can join the three facts a cut list
needs (CLAUDE.md boundaries): documents serves each part's evaluation request
with its plugin members' metadata (``cut-list-request``), geometry MEASURES
every body (``/bodies/extents``), and the grouping is
:mod:`loft_wire.cut_list`, applied here. An assembly's cut list is every part
at every level (the BOM's parts-only view, component patterns resolved),
each part's pieces times its placed quantity, grouped across the assembly; a
mirrored copy or opposite hand counts with its source part, and a deleted part
the assembly still places is listed in ``missing`` rather than dropped.

Every line is priced from the CALLER's price book (PRICE-BOOK,
:func:`loft_wire.cut_list.price_lines`): unit price per stock piece, extended
price and the total of the priced lines, with an unpriced line null.

The CSV is the same lines in the document's display unit, as a download,
with the price columns and a Total row.
"""

import asyncio
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Request, Response, status
from loft_wire.assemblies import MAX_ASSEMBLY_INSTANCES, AssemblyGraphResponse
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMissing,
    CutListPartRequest,
    CutListPiece,
    CutListResponse,
    cut_list_csv,
    cut_list_filename,
    cut_list_response,
    part_pieces,
)
from py_kit import ValidationApiError

from gateway.affinity import forward_geometry
from gateway.assemblies import get_assembly_bom
from gateway.auth import CurrentUser
from gateway.db import User
from gateway.parts import forward_documents
from gateway.price_book import caller_price_book
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"
_GEOMETRY = "Geometry"

#: The CSV download's OpenAPI response (it is not JSON).
_CSV_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_200_OK: {
        "content": {"text/csv": {"schema": {"type": "string"}}},
        "description": "The cut list as CSV (RFC 4180, CRLF, UTF-8), lengths in "
        "the document's display unit; `Content-Disposition` names the file.",
    }
}

parts_router = APIRouter(prefix="/api/v1/parts", tags=["cut-list"])
assemblies_router = APIRouter(prefix="/api/v1/assemblies", tags=["cut-list"])


async def _part_pieces(
    http_request: Request, user: User, part_id: uuid.UUID, count: int = 1
) -> tuple[CutListPartRequest, list[CutListPiece]]:
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/cut-list-request"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    request = CutListPartRequest.model_validate_json(upstream.content)
    measured = await forward_geometry(
        http_request,
        str(user.id),
        "POST",
        "/api/v1/bodies/extents",
        service=_GEOMETRY,
        json_content=request.evaluation.model_dump_json(),
    )
    if measured.status_code != status.HTTP_200_OK:
        raise_upstream_error(measured, service=_GEOMETRY)
    extents = BodyExtentsResult.model_validate_json(measured.content)
    pieces = part_pieces(
        extents, request.members, request.evaluation.materials, count=count
    )
    return request, pieces


async def part_cut_list(
    http_request: Request, user: User, part_id: uuid.UUID
) -> CutListResponse:
    request, pieces = await _part_pieces(http_request, user, part_id)
    return cut_list_response(
        document_id=part_id,
        document_kind="part",
        name=request.name,
        length_unit=request.length_unit,
        pieces=pieces,
        price_book=await caller_price_book(http_request, user),
    )


#: Parts measured at once for an assembly's cut list. Each is a geometry
#: evaluation, so the fan-out is bounded (the unique parts are already bounded
#: by ``MAX_ASSEMBLY_INSTANCES``, which the BOM read enforces).
CUT_LIST_CONCURRENCY = 4


async def assembly_cut_list(
    http_request: Request, user: User, assembly_id: uuid.UUID
) -> CutListResponse:
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/assemblies/{assembly_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    assembly = AssemblyGraphResponse.model_validate_json(upstream.content).assembly
    bom = await get_assembly_bom(assembly_id, user, http_request)
    # One measurement per PART: an opposite-hand line (ASM-MIRROR-COMPONENT)
    # names its source part, and a mirror image has the same profiles,
    # materials and lengths, so its pieces join the source's lines.
    quantities: dict[uuid.UUID, int] = {}
    missing: dict[uuid.UUID, int] = {}
    for line in bom.parts_only:
        bucket = missing if line.missing else quantities
        bucket[line.ref_document_id] = (
            bucket.get(line.ref_document_id, 0) + line.quantity
        )
    if len(quantities) > MAX_ASSEMBLY_INSTANCES:  # the BOM read bounds it first
        raise ValidationApiError(
            "The assembly places too many parts for a cut list.",
            code="cut_list_too_large",
        )
    gate = asyncio.Semaphore(CUT_LIST_CONCURRENCY)

    async def measure(part_id: uuid.UUID, count: int) -> list[CutListPiece]:
        async with gate:
            return (await _part_pieces(http_request, user, part_id, count))[1]

    measured = await asyncio.gather(
        *(measure(part_id, count) for part_id, count in quantities.items())
    )
    return cut_list_response(
        document_id=assembly_id,
        document_kind="assembly",
        name=assembly.name,
        length_unit=assembly.length_unit,
        pieces=[piece for pieces in measured for piece in pieces],
        missing=[
            CutListMissing(ref_document_id=part_id, quantity=count)
            for part_id, count in missing.items()
        ],
        price_book=await caller_price_book(http_request, user),
    )


def _csv(cut_list: CutListResponse) -> Response:
    filename = cut_list_filename(cut_list.name)
    return Response(
        content=cut_list_csv(cut_list).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; "
            f'filename="{filename.encode("ascii", "replace").decode()}"; '
            f"filename*=UTF-8''{quote(filename)}"
        },
    )


@parts_router.get("/{part_id}/cut-list", dependencies=[COMPUTE_RATE_LIMIT])
async def get_part_cut_list(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> CutListResponse:
    """The part's cut list: its bodies grouped by member, profile, material
    and measured length, with quantity, total length and stock length
    (SolidWorks' weldment cut list). Every length is measured from its body;
    a body that is no plugin member is matched to a library profile by its
    exact section, else listed as unclassified with its measured size. Each
    line is priced from your price book on the stock pieces bought; a line
    the book does not price is null, and `unpriced_lines` counts them."""
    return await part_cut_list(http_request, user, part_id)


@parts_router.get(
    "/{part_id}/cut-list/csv",
    response_class=Response,
    responses=_CSV_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def get_part_cut_list_csv(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """The part's cut list as a CSV download, in the part's display unit."""
    return _csv(await part_cut_list(http_request, user, part_id))


@assemblies_router.get("/{assembly_id}/cut-list", dependencies=[COMPUTE_RATE_LIMIT])
async def get_assembly_cut_list(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> CutListResponse:
    """The assembly's cut list: every part at every level (component
    patterns counted), each part's members times its quantity, grouped
    across the assembly as one list (Chief Architect's materials list),
    priced from your price book; the total is the sum of the priced lines."""
    return await assembly_cut_list(http_request, user, assembly_id)


@assemblies_router.get(
    "/{assembly_id}/cut-list/csv",
    response_class=Response,
    responses=_CSV_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def get_assembly_cut_list_csv(
    assembly_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """The assembly's cut list as a CSV download, in its display unit."""
    return _csv(await assembly_cut_list(http_request, user, assembly_id))
