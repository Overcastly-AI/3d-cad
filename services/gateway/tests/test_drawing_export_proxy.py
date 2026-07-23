"""gateway ``POST /api/v1/drawings/{id}/export`` — the server-composed drawing
export proxy (drawing-export.md §"Endpoints", Approach C).

Same two-hop harness as tests/test_evaluate_proxy.py (mock transports per
upstream, real auth over SQLite), applied to drawing composition: the route
fetches the drawing tree AND the referenced part's evaluation-request from
documents (principal attached), ASSEMBLES a ``ComposeDrawingRequest`` from that
persisted state, relays it to the identity-free geometry compose hop (NO
principal), and streams the artifact bytes + ``Content-Disposition`` back. It is
auth-gated (F7) and rate-limited; upstream envelopes (documents' 404, geometry's
``not_implemented`` for dxf) re-surface verbatim, and an unknown ``format`` is a
gateway-side 422.
"""

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.drawings import (
    ARTIFACT_MEDIA_TYPES,
    ComposeDrawingRequest,
    ComposedSheet,
    ComposedTitleBlock,
    DimensionEndpointRef,
    DimensionResponse,
    DrawingResponse,
    DrawingTreeResponse,
    LinearDimensionParams,
    PointToPointMeasurement,
    SheetContent,
    SheetResponse,
    ViewResponse,
    ViewScale,
)
from py_kit.schemas.features import (
    EdgeSignature,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    SketchFeature,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

DRAWING = uuid.UUID("00000000-0000-0000-0000-0000000000d0")
PART = uuid.UUID("00000000-0000-0000-0000-0000000000fa")
SHEET = uuid.UUID("00000000-0000-0000-0000-0000000000a0")
FRONT_VIEW = uuid.UUID("00000000-0000-0000-0000-0000000000b0")
TOP_VIEW = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DIM = uuid.UUID("00000000-0000-0000-0000-0000000000c0")
SKETCH = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

NOW = "2026-07-18T00:00:00Z"

SKETCH_ENVELOPE: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 40.0, "y": 0.0},
            }
        ],
        "constraints": [{"kind": "fixed", "point": {"entity": "e1", "point": "start"}}],
    },
}


def _edge_signature() -> EdgeSignature:
    """A minimal edge signature for the point-to-point dimension endpoints."""
    return EdgeSignature.model_validate(
        {
            "curve": "line",
            "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_b": {"x": 40.0, "y": 0.0, "z": 0.0},
            "midpoint": {"x": 20.0, "y": 0.0, "z": 0.0},
            "length_mm": 40.0,
        }
    )


def _dimension() -> LinearDimensionParams:
    sig = _edge_signature()
    return LinearDimensionParams(
        measurement=PointToPointMeasurement(
            a=DimensionEndpointRef(signature=sig, endpoint="end_a"),
            b=DimensionEndpointRef(signature=sig, endpoint="end_b"),
        ),
    )


def _drawing_tree() -> DrawingTreeResponse:
    """A one-sheet, two-view (front/top) drawing of PART with one linear dim."""
    drawing = DrawingResponse(
        id=DRAWING,
        name="Bracket — Detail",
        owner_id=uuid.uuid4(),
        doc_version=3,
        created_at=NOW,  # type: ignore[arg-type]
        updated_at=NOW,  # type: ignore[arg-type]
    )
    sheet = SheetResponse(
        id=SHEET,
        drawing_id=DRAWING,
        name="Sheet 1",
        size="A4",
        orientation="landscape",
        projection="third_angle",
        title_block=None,
        order_index=0,
        created_at=NOW,  # type: ignore[arg-type]
        updated_at=NOW,  # type: ignore[arg-type]
    )

    def view(view_id: uuid.UUID, projection: str, order: int) -> ViewResponse:
        return ViewResponse(
            id=view_id,
            sheet_id=SHEET,
            ref_document_id=PART,
            ref_document_kind="part",
            ref_pinned_version=None,
            projection=projection,  # type: ignore[arg-type]
            scale=ViewScale(numerator=1, denominator=2),
            position={"x_mm": 50.0 + order * 80.0, "y_mm": 60.0},  # type: ignore[arg-type]
            order_index=order,
            created_at=NOW,  # type: ignore[arg-type]
            updated_at=NOW,  # type: ignore[arg-type]
        )

    dim = DimensionResponse(
        id=DIM,
        sheet_id=SHEET,
        view_id=FRONT_VIEW,
        order_index=0,
        dimension=_dimension(),
    )
    return DrawingTreeResponse(
        drawing=drawing,
        doc_version=3,
        sheets=[
            SheetContent(
                sheet=sheet,
                views=[view(FRONT_VIEW, "front", 0), view(TOP_VIEW, "top", 1)],
                dimensions=[dim],
                annotations=[],
            )
        ],
    )


def _assembly_drawing_tree() -> DrawingTreeResponse:
    """A one-sheet drawing whose single view references an ASSEMBLY (pin-ready
    schema member) — not composable by the part-only wire (D4)."""
    tree = _drawing_tree()
    view = tree.sheets[0].views[0]
    view.ref_document_kind = "assembly"
    tree.sheets[0].views = [view]
    return tree


def _empty_drawing_tree() -> DrawingTreeResponse:
    """A drawing with no sheet/views — nothing to compose."""
    drawing = DrawingResponse(
        id=DRAWING,
        name="Empty",
        owner_id=uuid.uuid4(),
        doc_version=0,
        created_at=NOW,  # type: ignore[arg-type]
        updated_at=NOW,  # type: ignore[arg-type]
    )
    return DrawingTreeResponse(drawing=drawing, doc_version=0, sheets=[])


def _evaluation_request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest(
        part_id=PART,
        tree_version=4,
        features=[
            EvaluatedFeatureInput(
                id=SKETCH, feature=SketchFeature.model_validate(SKETCH_ENVELOPE)
            )
        ],
    )


PDF_BYTES = b"%PDF-1.4\n%stub composed pdf\n%%EOF\n"


def _composed_sheet() -> ComposedSheet:
    """A minimal, well-formed `ComposedSheet` the geometry sheet hop returns."""
    return ComposedSheet(
        width_mm=297.0,
        height_mm=210.0,
        margin_mm=10.0,
        title="Bracket — Detail",
        scale_label="1:2",
        views=[],
        title_block=ComposedTitleBlock(
            x=200.0,
            y=170.0,
            width=87.0,
            height=30.0,
            split_x=250.0,
            mid_y=185.0,
            title="Bracket — Detail",
            scale="1:2",
            size="A4",
        ),
    )


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def make_client(
    db_url: str, documents_handler: Handler, geometry_handler: Handler
) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry_handler),
        documents_transport=httpx.MockTransport(documents_handler),
    )
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def _documents_ok(seen: list[httpx.Request]) -> Handler:
    """Documents that serves the drawing tree then the part evaluation-request."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == f"/api/v1/drawings/{DRAWING}":
            return httpx.Response(200, content=_drawing_tree().model_dump_json())
        if request.url.path == f"/api/v1/parts/{PART}/evaluation-request":
            return httpx.Response(200, content=_evaluation_request().model_dump_json())
        raise AssertionError(f"unexpected documents path {request.url.path}")

    return handler


def _geometry_pdf(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=PDF_BYTES,
            headers={
                "content-type": ARTIFACT_MEDIA_TYPES["pdf"],
                "content-disposition": 'attachment; filename="bracket-detail.pdf"',
            },
        )

    return handler


@pytest.mark.parametrize("query", ["", "?format=pdf", "?format=svg"])
def test_unauthenticated_401_and_nothing_forwarded(db_url: str, query: str) -> None:
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_pdf(geometry_seen)
    ) as client:
        response = client.post(f"/api/v1/drawings/{DRAWING}/export{query}")

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert documents_seen == []
    assert geometry_seen == []


def test_pdf_export_aggregates_and_streams_bytes(db_url: str) -> None:
    """A `format=pdf` export forwards a well-formed `ComposeDrawingRequest` (part
    tree + views + dimensions + layout + format) to geometry and streams the
    stub's bytes + `Content-Disposition` back."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_pdf(geometry_seen)
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=pdf", headers=bearer
        )

    assert response.status_code == 200, response.text
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith(ARTIFACT_MEDIA_TYPES["pdf"])
    assert response.headers["content-disposition"] == (
        'attachment; filename="bracket-detail.pdf"'
    )

    # Documents was hit twice (drawing tree, then part evaluation-request), each
    # carrying the principal — geometry never sees it (RESEARCH §3).
    drawing_req, part_req = documents_seen
    assert drawing_req.method == "GET"
    assert drawing_req.url.path == f"/api/v1/drawings/{DRAWING}"
    assert drawing_req.headers[PRINCIPAL_HEADER] == user_id
    assert part_req.method == "GET"
    assert part_req.url.path == f"/api/v1/parts/{PART}/evaluation-request"
    assert part_req.headers[PRINCIPAL_HEADER] == user_id

    [geometry_req] = geometry_seen
    assert geometry_req.method == "POST"
    assert geometry_req.url.path == "/api/v1/drawing/compose"
    assert PRINCIPAL_HEADER not in geometry_req.headers

    relayed = ComposeDrawingRequest.model_validate_json(geometry_req.content)
    # Part projection intent came from the evaluation-request.
    assert relayed.part_id == PART
    assert relayed.tree_version == 4
    assert [f.id for f in relayed.features] == [SKETCH]
    # Views + shared scale mirror the persisted sheet.
    assert relayed.views == ["front", "top"]
    assert relayed.scale == ViewScale(numerator=1, denominator=2)
    # The dimension is tagged with the projection of the view it annotates.
    assert [d.view for d in relayed.dimensions] == ["front"]
    assert [d.id for d in relayed.dimensions] == [DIM]
    # The layout is built from the drawing's sheet + views.
    assert relayed.format == "pdf"
    assert relayed.layout.size == "A4"
    assert relayed.layout.orientation == "landscape"
    assert relayed.layout.projection == "third_angle"
    assert relayed.layout.title == "Bracket — Detail"
    assert [v.projection for v in relayed.layout.views] == ["front", "top"]


def test_format_defaults_to_svg(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []

    def geometry_svg(request: httpx.Request) -> httpx.Response:
        geometry_seen.append(request)
        return httpx.Response(
            200,
            content=b"<svg/>",
            headers={"content-type": ARTIFACT_MEDIA_TYPES["svg"]},
        )

    with make_client(db_url, _documents_ok(documents_seen), geometry_svg) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/export", headers=bearer)

    assert response.status_code == 200, response.text
    [geometry_req] = geometry_seen
    relayed = ComposeDrawingRequest.model_validate_json(geometry_req.content)
    assert relayed.format == "svg"
    # Geometry gave no Content-Disposition → the gateway derives one from the name.
    assert response.headers["content-disposition"] == (
        'attachment; filename="bracket-detail.svg"'
    )


def test_dxf_resurfaces_upstream_not_implemented_422(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []

    def geometry_422(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "not_implemented",
                    "message": "DXF export is not implemented yet.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, _documents_ok(documents_seen), geometry_422) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=dxf", headers=bearer
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "not_implemented"


def test_unknown_format_rejected_at_gateway(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_pdf(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=stp", headers=bearer
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    # A bad format never touches either upstream.
    assert documents_seen == []
    assert geometry_seen == []


def test_missing_or_foreign_drawing_is_404(db_url: str) -> None:
    """Documents' uniform 404 for an unknown/foreign drawing re-surfaces verbatim,
    and the part hop + geometry are never reached (owner isolation)."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []

    def documents_404(request: httpx.Request) -> httpx.Response:
        documents_seen.append(request)
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "drawing_not_found",
                    "message": "Drawing not found.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, documents_404, _geometry_pdf(geometry_seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=pdf", headers=bearer
        )

    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "drawing_not_found"
    # Only the drawing GET happened; the part evaluation-request + compose did not.
    assert [r.url.path for r in documents_seen] == [f"/api/v1/drawings/{DRAWING}"]
    assert geometry_seen == []


def test_drawing_without_views_is_422(db_url: str) -> None:
    """A laid-out-less drawing can't be composed — a gateway-side 422, no upstream
    part/compose call."""
    geometry_seen: list[httpx.Request] = []

    def documents_empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_empty_drawing_tree().model_dump_json())

    with make_client(db_url, documents_empty, _geometry_pdf(geometry_seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=pdf", headers=bearer
        )

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "drawing_not_composable"
    assert geometry_seen == []


def test_assembly_view_export_is_422_not_downstream_404(db_url: str) -> None:
    """A view referencing an assembly (pin-ready schema member) can't be composed by
    the part-only wire. The gateway rejects it FAST with a legible typed error
    BEFORE any part `evaluation-request` / geometry compose hop — never the opaque
    downstream 404 that the missing `/parts/{assembly_id}/evaluation-request` gave
    (engineering audit D4)."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []

    def documents_assembly(request: httpx.Request) -> httpx.Response:
        documents_seen.append(request)
        return httpx.Response(200, content=_assembly_drawing_tree().model_dump_json())

    with make_client(
        db_url, documents_assembly, _geometry_pdf(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/drawings/{DRAWING}/export?format=pdf", headers=bearer
        )

    assert response.status_code == 422, response.text
    error = _envelope(response.json())
    assert error["code"] == "assembly_views_unsupported"
    assert error["details"]["ref_document_kind"] == "assembly"
    # Only the drawing tree GET happened — no part evaluation-request, no compose.
    assert [r.url.path for r in documents_seen] == [f"/api/v1/drawings/{DRAWING}"]
    assert geometry_seen == []


def test_assembly_view_sheet_is_422_not_downstream_404(db_url: str) -> None:
    """The JSON `/sheet` proxy runs the SAME aggregation, so an assembly-kind view is
    rejected identically (typed 422, no part/compose hop)."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []

    def documents_assembly(request: httpx.Request) -> httpx.Response:
        documents_seen.append(request)
        return httpx.Response(200, content=_assembly_drawing_tree().model_dump_json())

    with make_client(
        db_url, documents_assembly, _geometry_sheet(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 422, response.text
    assert _envelope(response.json())["code"] == "assembly_views_unsupported"
    assert [r.url.path for r in documents_seen] == [f"/api/v1/drawings/{DRAWING}"]
    assert geometry_seen == []


# --- JSON sheet proxy (DE-1b — the model the DE-1c client renders from) ---------
def _geometry_sheet(seen: list[httpx.Request]) -> Handler:
    """Geometry's identity-free `/drawing/compose/sheet` hop, returning the model."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=_composed_sheet().model_dump_json(),
            headers={"content-type": "application/json"},
        )

    return handler


def test_sheet_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_sheet(geometry_seen)
    ) as client:
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet")

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert documents_seen == []
    assert geometry_seen == []


def test_sheet_aggregates_and_returns_composed_sheet_model(db_url: str) -> None:
    """The sheet proxy runs the SAME two-hop aggregation as `/export` (drawing tree
    + part evaluation-request, principal attached), relays a well-formed
    `ComposeDrawingRequest` to geometry's identity-free `/drawing/compose/sheet`, and
    returns the typed `ComposedSheet` JSON (not bytes)."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_sheet(geometry_seen)
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    sheet = ComposedSheet.model_validate_json(response.content)
    assert sheet == _composed_sheet()

    # Documents was hit twice (drawing tree, then part evaluation-request), each with
    # the principal; geometry never sees it (RESEARCH §3).
    drawing_req, part_req = documents_seen
    assert drawing_req.url.path == f"/api/v1/drawings/{DRAWING}"
    assert drawing_req.headers[PRINCIPAL_HEADER] == user_id
    assert part_req.url.path == f"/api/v1/parts/{PART}/evaluation-request"
    assert part_req.headers[PRINCIPAL_HEADER] == user_id

    [geometry_req] = geometry_seen
    assert geometry_req.method == "POST"
    assert geometry_req.url.path == "/api/v1/drawing/compose/sheet"
    assert PRINCIPAL_HEADER not in geometry_req.headers

    # The relayed request mirrors the persisted sheet — the SAME aggregation the
    # bytes `/export` route builds (views + tagged dimensions + layout).
    relayed = ComposeDrawingRequest.model_validate_json(geometry_req.content)
    assert relayed.part_id == PART
    assert relayed.tree_version == 4
    assert relayed.views == ["front", "top"]
    assert [d.view for d in relayed.dimensions] == ["front"]
    assert relayed.layout.title == "Bracket — Detail"


def test_sheet_missing_or_foreign_drawing_is_404(db_url: str) -> None:
    """Documents' uniform 404 re-surfaces verbatim; the part hop + geometry are never
    reached (owner isolation), same as `/export`."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []

    def documents_404(request: httpx.Request) -> httpx.Response:
        documents_seen.append(request)
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "drawing_not_found",
                    "message": "Drawing not found.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, documents_404, _geometry_sheet(geometry_seen)) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "drawing_not_found"
    assert [r.url.path for r in documents_seen] == [f"/api/v1/drawings/{DRAWING}"]
    assert geometry_seen == []


def test_sheet_drawing_without_views_is_422(db_url: str) -> None:
    """A drawing with no laid-out views is a gateway-side 422 (no part/compose hop)."""
    geometry_seen: list[httpx.Request] = []

    def documents_empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_empty_drawing_tree().model_dump_json())

    with make_client(db_url, documents_empty, _geometry_sheet(geometry_seen)) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/drawings/{DRAWING}/sheet", headers=bearer)

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "drawing_not_composable"
    assert geometry_seen == []
