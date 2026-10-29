"""gateway house drawings (HOUSE-DRAWINGS): a sheet with a plan, an elevation or
a materials list reads its part through ``cut-list-request`` and threads the
members, the unit and the priced yard order into the compose; the materials
list downloads as CSV.

The same mock-transport harness as ``test_drawing_export_proxy.py`` (its
helpers are imported): documents serves the drawing tree, the part's
cut-list-request and the caller's price book; geometry measures the bodies and
composes the sheet.
"""

import csv
import io
import sys
import uuid
from pathlib import Path

import httpx2 as httpx
from loft_wire.cut_list import (
    BodyExtent,
    BodyExtentsResult,
    CutListMember,
    CutListPartRequest,
)
from loft_wire.drawings import ComposeDrawingRequest, DrawingTreeResponse
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.plugins import MemberMetadata
from loft_wire.price_book import EMPTY_PRICE_BOOK

sys.path.insert(0, str(Path(__file__).parent))
from test_drawing_export_proxy import (
    DRAWING,
    PART,
    SHEET,
    Handler,
    _composed_sheet,  # pyright: ignore[reportPrivateUsage]
    _drawing_tree,  # pyright: ignore[reportPrivateUsage]
    _evaluation_request,  # pyright: ignore[reportPrivateUsage]
    _register,  # pyright: ignore[reportPrivateUsage]
    db_url,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    make_client,
)

STUD = uuid.UUID("00000000-0000-0000-0000-00000000057d")
IN = 25.4


def _house_tree(*projections: str) -> DrawingTreeResponse:
    """The export suite's one-sheet drawing, its views re-pointed at house views."""
    tree = _drawing_tree()
    template = tree.sheets[0].views[0]
    tree.sheets[0].views = [
        template.model_copy(
            update={"id": uuid.uuid4(), "projection": p, "order_index": i}
        )
        for i, p in enumerate(projections)
    ]
    tree.sheets[0].dimensions = []
    return tree


def _cut_list_request() -> CutListPartRequest:
    return CutListPartRequest(
        part_id=PART,
        name="B7",
        length_unit="in",
        members=[
            CutListMember(
                feature_id=STUD,
                role="stud",
                title="Stud",
                plugin_id="loft.wall",
                metadata=MemberMetadata(profile="2x6", material="spf_lumber"),
            )
        ],
        evaluation=_evaluation_request(),
    )


def _documents(seen: list[httpx.Request], tree: DrawingTreeResponse) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == f"/api/v1/drawings/{DRAWING}":
            return httpx.Response(200, content=tree.model_dump_json())
        if path == f"/api/v1/parts/{PART}/cut-list-request":
            return httpx.Response(200, content=_cut_list_request().model_dump_json())
        if path == "/api/v1/price-book":
            return httpx.Response(200, content=EMPTY_PRICE_BOOK.model_dump_json())
        raise AssertionError(f"unexpected documents path {path}")

    return handler


def _geometry(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/bodies/extents":
            extents = BodyExtentsResult(
                part_id=PART,
                tree_version=4,
                bodies=[
                    BodyExtent(
                        base_feature_id=STUD,
                        extents_mm=(1.5 * IN, 5.5 * IN, 92.625 * IN),
                        volume_mm3=1.5 * 5.5 * 92.625 * IN**3,
                    )
                ],
            )
            return httpx.Response(200, content=extents.model_dump_json())
        if request.url.path == "/api/v1/drawing/compose/sheet":
            return httpx.Response(200, content=_composed_sheet().model_dump_json())
        raise AssertionError(f"unexpected geometry path {request.url.path}")

    return handler


def test_a_plan_sheet_threads_members_and_the_unit(db_url: str) -> None:  # noqa: F811
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    tree = _house_tree("plan")
    with make_client(
        db_url, _documents(documents_seen, tree), _geometry(geometry_seen)
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 200, response.text
    drawing_req, part_req = documents_seen
    assert part_req.url.path == f"/api/v1/parts/{PART}/cut-list-request"
    assert part_req.headers[PRINCIPAL_HEADER] == user_id
    [compose] = geometry_seen
    relayed = ComposeDrawingRequest.model_validate_json(compose.content)
    assert relayed.views == ["plan"]
    assert relayed.layout.length_unit == "in"
    assert [(m.feature_id, m.plugin_id, m.role) for m in relayed.members] == [
        (STUD, "loft.wall", "stud")
    ]
    assert relayed.materials is None
    assert relayed.features == _evaluation_request().features
    assert drawing_req.url.path == f"/api/v1/drawings/{DRAWING}"


def test_a_materials_sheet_carries_the_priced_yard_order(db_url: str) -> None:  # noqa: F811
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    tree = _house_tree("materials")
    with make_client(
        db_url, _documents(documents_seen, tree), _geometry(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 200, response.text
    # The cut-list-request is read ONCE and reused for the cut list.
    paths = [r.url.path for r in documents_seen]
    assert paths.count(f"/api/v1/parts/{PART}/cut-list-request") == 1
    extents, compose = geometry_seen
    assert extents.url.path == "/api/v1/bodies/extents"
    relayed = ComposeDrawingRequest.model_validate_json(compose.content)
    assert relayed.materials is not None
    [line] = relayed.materials.lines
    assert (line.item, line.qty, line.size, line.length) == ("Stud", "1", "2x6", "8 ft")
    # The empty book prices nothing: blank, never $0.
    assert line.price == "" and line.price_cents is None
    assert relayed.materials.total_label == "Total of priced lines, 1 unpriced"


def test_the_materials_list_downloads_as_csv(db_url: str) -> None:  # noqa: F811
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    tree = _house_tree("materials")
    with make_client(
        db_url, _documents(documents_seen, tree), _geometry(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.get(
            f"/api/v1/drawings/{DRAWING}/materials/csv?sheet={SHEET}", headers=bearer
        )
        missing = client.get(
            f"/api/v1/drawings/{DRAWING}/materials/csv?sheet={uuid.uuid4()}",
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "B7 materials.csv" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:3] == ["System", "Item", "Qty"]
    assert rows[1][:5] == ["Walls", "Stud", "1", "2x6", "8 ft"]
    assert rows[-1][0] == "Total of priced lines, 1 unpriced"
    assert missing.status_code == 404


def test_a_sheet_without_a_materials_list_has_no_csv(db_url: str) -> None:  # noqa: F811
    tree = _house_tree("plan")
    with make_client(db_url, _documents([], tree), _geometry([])) as client:
        _, bearer = _register(client)
        response = client.get(
            f"/api/v1/drawings/{DRAWING}/materials/csv", headers=bearer
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "drawing_no_materials"
