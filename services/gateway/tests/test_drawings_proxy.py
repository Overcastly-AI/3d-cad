"""gateway.drawings — auth gating, principal forwarding, envelope passthrough.

Same harness as tests/test_assemblies_proxy.py: the documents upstream is an
``httpx.MockTransport``; auth runs for real (register → bearer token) over the
SQLite/aiosqlite test DB. Every drawing route is auth-gated (F7): a 401 per
route with nothing forwarded upstream, plus the documents 422/409/404 envelopes
re-surfaced verbatim.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.drawings import (
    AnnotationMutationResponse,
    AnnotationResponse,
    DrawingCreate,
    DrawingListResponse,
    DrawingResponse,
    DrawingTreeResponse,
    NoteAnnotationParams,
    SheetContent,
    SheetCreate,
    SheetMutationResponse,
    SheetPoint,
    SheetResponse,
    ViewCreate,
    ViewMutationResponse,
    ViewResponse,
    ViewScale,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)

DRAWING = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
SHEET = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
VIEW = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
DIMENSION = uuid.UUID("00000000-0000-0000-0000-0000000000f2")
ANNOTATION = uuid.UUID("00000000-0000-0000-0000-0000000000f3")


def _drawing(owner_id: uuid.UUID, name: str = "Bracket Drawing") -> DrawingResponse:
    return DrawingResponse(
        id=DRAWING,
        name=name,
        owner_id=owner_id,
        doc_version=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _sheet() -> SheetResponse:
    return SheetResponse(
        id=SHEET,
        drawing_id=DRAWING,
        name="Sheet 1",
        size="A4",
        orientation="landscape",
        projection="third_angle",
        title_block=None,
        order_index=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _view() -> ViewResponse:
    return ViewResponse(
        id=VIEW,
        sheet_id=SHEET,
        ref_document_id=uuid.uuid4(),
        ref_document_kind="part",
        ref_pinned_version=None,
        projection="front",
        scale=ViewScale(numerator=1, denominator=1),
        position=SheetPoint(x_mm=50.0, y_mm=50.0),
        order_index=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _annotation() -> AnnotationResponse:
    return AnnotationResponse(
        id=ANNOTATION,
        sheet_id=SHEET,
        order_index=0,
        annotation=NoteAnnotationParams(
            text="Break all sharp edges", position=SheetPoint(x_mm=10.0, y_mm=10.0)
        ),
    )


def _tree(owner_id: uuid.UUID) -> DrawingTreeResponse:
    return DrawingTreeResponse(
        drawing=_drawing(owner_id),
        doc_version=3,
        sheets=[
            SheetContent(
                sheet=_sheet(),
                views=[_view()],
                dimensions=[],
                annotations=[_annotation()],
            )
        ],
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


def make_client(db_url: str, handler: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://127.0.0.1:9",  # nothing listens; irrelevant here
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, documents_transport=httpx.MockTransport(handler))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _echo_documents(seen: list[httpx.Request]) -> Handler:
    """A canned documents drawing upstream: create/list/get/mutate/delete."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        owner_id = uuid.UUID(request.headers[PRINCIPAL_HEADER])
        path = request.url.path
        if request.method == "DELETE":
            if path == f"/api/v1/drawings/{DRAWING}":
                return httpx.Response(204)
            # sheet / view / dimension / annotation delete → the updated tree
            return httpx.Response(200, content=_tree(owner_id).model_dump_json())
        if request.method == "POST":
            if path.endswith("/views"):
                body_v = ViewMutationResponse(view=_view(), doc_version=2)
                return httpx.Response(201, content=body_v.model_dump_json())
            if path.endswith("/annotations"):
                body_a = AnnotationMutationResponse(
                    annotation=_annotation(), doc_version=2
                )
                return httpx.Response(201, content=body_a.model_dump_json())
            if path.endswith("/sheets"):
                body_s = SheetMutationResponse(sheet=_sheet(), doc_version=1)
                return httpx.Response(201, content=body_s.model_dump_json())
            name = DrawingCreate.model_validate_json(request.content).name
            return httpx.Response(
                201, content=_drawing(owner_id, name).model_dump_json()
            )
        if request.method == "PATCH":
            if "/sheets/" in path:
                body_ps = SheetMutationResponse(sheet=_sheet(), doc_version=1)
                return httpx.Response(200, content=body_ps.model_dump_json())
            if "/views/" in path:
                body_pv = ViewMutationResponse(view=_view(), doc_version=1)
                return httpx.Response(200, content=body_pv.model_dump_json())
            return httpx.Response(
                200,
                content=_drawing(owner_id, "Bracket Drawing v2").model_dump_json(),
            )
        # GET
        if path == "/api/v1/drawings":
            listing = DrawingListResponse(drawings=[_drawing(owner_id)])
            return httpx.Response(200, content=listing.model_dump_json())
        return httpx.Response(200, content=_tree(owner_id).model_dump_json())

    return handler


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


# --- auth gating (F7: every route rejects unauthenticated, nothing forwarded) ---


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/drawings"),
        ("GET", "/api/v1/drawings"),
        ("GET", f"/api/v1/drawings/{DRAWING}"),
        ("PATCH", f"/api/v1/drawings/{DRAWING}"),
        ("DELETE", f"/api/v1/drawings/{DRAWING}"),
        ("POST", f"/api/v1/drawings/{DRAWING}/sheets"),
        ("PATCH", f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}"),
        ("DELETE", f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}?expected_version=0"),
        ("POST", f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/views"),
        ("PATCH", f"/api/v1/drawings/{DRAWING}/views/{VIEW}"),
        ("DELETE", f"/api/v1/drawings/{DRAWING}/views/{VIEW}?expected_version=0"),
        ("POST", f"/api/v1/drawings/{DRAWING}/views/{VIEW}/dimensions"),
        (
            "DELETE",
            f"/api/v1/drawings/{DRAWING}/dimensions/{DIMENSION}?expected_version=0",
        ),
        ("POST", f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/annotations"),
        (
            "DELETE",
            f"/api/v1/drawings/{DRAWING}/annotations/{ANNOTATION}?expected_version=0",
        ),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request], method: str, path: str
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.request(method, path, json={"name": "Bracket Drawing"})
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


# --- happy paths: principal forwarding + typed passthrough ----------------------


def test_create_drawing_forwards_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(
            "/api/v1/drawings", json={"name": "Bracket Drawing"}, headers=bearer
        )

    assert response.status_code == 201, response.text
    body = DrawingResponse.model_validate(response.json())
    assert body.name == "Bracket Drawing"
    # The owner is the JWT-verified caller, derived at the gateway.
    assert str(body.owner_id) == user_id

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/drawings"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    assert DrawingCreate.model_validate_json(upstream.content).name == "Bracket Drawing"


def test_list_drawings_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.get("/api/v1/drawings", headers=bearer)

    assert response.status_code == 200
    drawings = DrawingListResponse.model_validate(response.json()).drawings
    assert len(drawings) == 1
    [upstream] = seen
    assert upstream.headers[PRINCIPAL_HEADER] == user_id


def test_get_drawing_tree_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get(f"/api/v1/drawings/{DRAWING}", headers=bearer)

    assert response.status_code == 200
    tree = DrawingTreeResponse.model_validate(response.json())
    assert len(tree.sheets) == 1
    assert len(tree.sheets[0].views) == 1
    assert len(tree.sheets[0].annotations) == 1
    [upstream] = seen
    assert upstream.url.path == f"/api/v1/drawings/{DRAWING}"


def test_crud_roundtrip_create_sheet_view_annotation_read(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """The integration flow: create drawing → add a sheet + a view + a note →
    read the tree, all through the authenticated gateway."""
    ref = uuid.uuid4()
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)

        created = client.post(
            "/api/v1/drawings", json={"name": "Bracket Drawing"}, headers=bearer
        )
        assert created.status_code == 201, created.text

        sheet = client.post(
            f"/api/v1/drawings/{DRAWING}/sheets",
            json=SheetCreate(expected_version=0, name="Sheet 1").model_dump(
                mode="json"
            ),
            headers=bearer,
        )
        assert sheet.status_code == 201, sheet.text
        SheetMutationResponse.model_validate(sheet.json())

        view = client.post(
            f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/views",
            json=ViewCreate(
                expected_version=1,
                ref_document_id=ref,
                ref_document_kind="part",
                projection="front",
                position=SheetPoint(x_mm=50.0, y_mm=50.0),
            ).model_dump(mode="json"),
            headers=bearer,
        )
        assert view.status_code == 201, view.text
        ViewMutationResponse.model_validate(view.json())

        note = client.post(
            f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/annotations",
            json={
                "expected_version": 2,
                "annotation": {
                    "type": "note",
                    "text": "Break all sharp edges",
                    "position": {"x_mm": 10.0, "y_mm": 10.0},
                },
            },
            headers=bearer,
        )
        assert note.status_code == 201, note.text
        AnnotationMutationResponse.model_validate(note.json())

        tree = client.get(f"/api/v1/drawings/{DRAWING}", headers=bearer)
        assert tree.status_code == 200
        DrawingTreeResponse.model_validate(tree.json())

    # Every hop forwarded the verified principal to the drawing CRUD API.
    assert {r.url.path for r in seen} == {
        "/api/v1/drawings",
        f"/api/v1/drawings/{DRAWING}/sheets",
        f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/views",
        f"/api/v1/drawings/{DRAWING}/sheets/{SHEET}/annotations",
        f"/api/v1/drawings/{DRAWING}",
    }


def test_update_drawing_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.patch(
            f"/api/v1/drawings/{DRAWING}",
            json={"expected_version": 0, "name": "Bracket Drawing v2"},
            headers=bearer,
        )
    assert response.status_code == 200
    assert DrawingResponse.model_validate(response.json()).name == "Bracket Drawing v2"
    [upstream] = seen
    assert upstream.method == "PATCH"


def test_delete_drawing_204(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(f"/api/v1/drawings/{DRAWING}", headers=bearer)
    assert response.status_code == 204
    assert response.content == b""
    [upstream] = seen
    assert upstream.method == "DELETE"


def test_delete_view_forwards_expected_version(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(
            f"/api/v1/drawings/{DRAWING}/views/{VIEW}?expected_version=3",
            headers=bearer,
        )
    assert response.status_code == 200
    DrawingTreeResponse.model_validate(response.json())
    [upstream] = seen
    assert upstream.url.params["expected_version"] == "3"


# --- upstream error surfaces (documents 422 / 409 / 404 re-surfaced) ------------


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (422, "stale_drawing_version"),
        (422, "ref_document_not_found"),
        (409, "drawing_name_taken"),
        (404, "drawing_not_found"),
    ],
)
def test_upstream_envelope_is_resurfaced(
    db_url: str, status_code: int, code: str
) -> None:
    """Documents 422 stale/ref / 409 name-taken / 404 non-owner pass through."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "code": code,
                    "message": "upstream said so.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.patch(
            f"/api/v1/drawings/{DRAWING}",
            json={"expected_version": 0, "name": "X"},
            headers=bearer,
        )

    assert response.status_code == status_code
    error = _envelope(response.json())
    assert error["code"] == code
    # The gateway stamps its own request id, not the upstream one.
    from py_kit import REQUEST_ID_HEADER

    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_upstream_down_maps_to_502_envelope(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/drawings", headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert "documents.internal" not in response.text


# --- gateway-side validation (never reaches upstream) ---------------------------


def test_invalid_body_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post("/api/v1/drawings", json={"name": "   "}, headers=bearer)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_malformed_drawing_id_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/drawings/not-a-uuid", headers=bearer)
    assert response.status_code == 422
    assert seen == []
