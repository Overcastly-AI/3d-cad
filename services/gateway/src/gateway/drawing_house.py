"""House drawings at the gateway (HOUSE-DRAWINGS): what a plan, an elevation and
a materials sheet need beyond a part's evaluation request.

The gateway is the one participant that can join them (CLAUDE.md boundaries):
documents knows each body's plugin member and the part's display unit
(``cut-list-request``), geometry measures the bodies, and the caller's price
book prices them. A sheet with a house view therefore reads the part through
``cut-list-request`` (the SAME evaluation request ``evaluation-request`` serves,
plus its members) and threads:

* the members (``DrawingMember``), so geometry finds the floor, the openings
  and the plates by role;
* the unit, so an imperial document prints feet-inch;
* for a ``materials`` view, the part's priced cut list as a yard order
  (:func:`loft_wire.yard_order.yard_order`), the SAME lines the cut-list panel
  shows.

``GET /drawings/{id}/materials/csv`` downloads that yard order as CSV.
"""

import uuid
from typing import Annotated, NamedTuple
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status
from loft_wire.cut_list import CutListPartRequest
from loft_wire.drawing_house import HOUSE_VIEWS, DrawingMember, YardOrder
from loft_wire.drawings import DrawingTreeResponse, SheetContent, ViewProjection
from loft_wire.yard_order import yard_order, yard_order_csv, yard_order_filename
from py_kit.errors import NotFoundError, ValidationApiError

from gateway.auth import CurrentUser
from gateway.cut_list import part_cut_list, part_cut_list_request
from gateway.db import User
from gateway.parts import forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])


class HouseInputs(NamedTuple):
    """What a house sheet's compose adds to the part's evaluation request."""

    request: CutListPartRequest
    members: list[DrawingMember]
    materials: YardOrder | None


def has_house_view(projections: list[ViewProjection]) -> bool:
    """True when a sheet places a plan, an elevation or a materials list."""
    return any(p in HOUSE_VIEWS for p in projections)


async def house_inputs(
    http_request: Request,
    user: User,
    part_id: uuid.UUID,
    projections: list[ViewProjection],
) -> HouseInputs:
    """Read the part with its members; price its cut list for a materials view."""
    request = await part_cut_list_request(http_request, user, part_id)
    members = [
        DrawingMember(feature_id=m.feature_id, plugin_id=m.plugin_id, role=m.role)
        for m in request.members
    ]
    materials = None
    if "materials" in projections:
        cut_list = await part_cut_list(http_request, user, part_id, request=request)
        materials = yard_order(cut_list)
    return HouseInputs(request, members, materials)


def _materials_sheet(
    tree: DrawingTreeResponse, sheet_id: uuid.UUID | None
) -> SheetContent:
    """The sheet whose materials list is asked for: *sheet_id*, else the
    drawing's first sheet with a materials view."""
    for content in tree.sheets:
        if sheet_id is not None and content.sheet.id != sheet_id:
            continue
        if any(v.projection == "materials" for v in content.views):
            return content
        if sheet_id is not None:
            break
    if sheet_id is not None and all(c.sheet.id != sheet_id for c in tree.sheets):
        raise NotFoundError(
            f"Sheet {sheet_id} is not part of drawing {tree.drawing.id}.",
            code="sheet_not_found",
            details={"sheet_id": str(sheet_id)},
        )
    raise ValidationApiError(
        "This sheet has no materials list; lay out the house set first.",
        code="drawing_no_materials",
    )


_CSV_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_200_OK: {
        "content": {"text/csv": {"schema": {"type": "string"}}},
        "description": "The sheet's materials list as CSV (RFC 4180, CRLF, UTF-8): "
        "System, Item, Qty, Size, Length, Material and Price, then the Total row; "
        "`Content-Disposition` names the file.",
    }
}


@router.get(
    "/{drawing_id}/materials/csv",
    response_class=Response,
    responses=_CSV_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def get_drawing_materials_csv(
    drawing_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    sheet: Annotated[
        uuid.UUID | None,
        Query(
            description="The materials sheet (a sheet id from the drawing tree); "
            "omit for the drawing's first sheet with a materials list.",
        ),
    ] = None,
) -> Response:
    """The materials list of a drawing's sheet as a CSV download: the drawn part's
    cut list as a yard order, priced from your price book, line for line the
    sheet and the cut-list panel."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/drawings/{drawing_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    tree = DrawingTreeResponse.model_validate_json(upstream.content)
    content = _materials_sheet(tree, sheet)
    view = next(v for v in content.views if v.projection == "materials")
    if view.ref_document_kind != "part":
        raise ValidationApiError(
            "A materials list drafts a part.", code="drawing_no_materials"
        )
    order = yard_order(await part_cut_list(http_request, user, view.ref_document_id))
    filename = yard_order_filename(order.name)
    return Response(
        content=yard_order_csv(order).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; "
            f'filename="{filename.encode("ascii", "replace").decode()}"; '
            f"filename*=UTF-8''{quote(filename)}"
        },
    )
