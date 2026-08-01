"""gateway.folders — auth gating, principal forwarding, envelope passthrough.

Same posture as tests/test_parts_proxy.py (documents is an
``httpx.MockTransport``; auth runs for real over the SQLite test DB). What is
worth asserting HERE, rather than upstream, is that filing stays reachable only
through an authenticated principal and that the two refusals a user acts on —
the non-empty-folder 409 and the cycle 422 — reach the browser with their
``details`` intact. A gateway that flattened those into a bare status would
leave the register with nothing to name.
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
from py_kit.schemas.folders import (
    DocumentMove,
    FolderCreate,
    FolderListResponse,
    FolderResponse,
)
from py_kit.schemas.materials import EMPTY_MATERIAL_ASSIGNMENT
from py_kit.schemas.parts import PRINCIPAL_HEADER, PartResponse
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
FOLDER_ID = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000f1")


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


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _folder(owner_id: uuid.UUID, name: str = "Gearbox") -> FolderResponse:
    return FolderResponse(
        id=FOLDER_ID,
        owner_id=owner_id,
        kind="part",
        name=name,
        parent_id=None,
        document_count=2,
        child_folder_count=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _part(owner_id: uuid.UUID, folder_id: uuid.UUID | None) -> PartResponse:
    return PartResponse(
        id=uuid.uuid4(),
        name="Bracket",
        owner_id=owner_id,
        folder_id=folder_id,
        length_unit="mm",
        materials=EMPTY_MATERIAL_ASSIGNMENT,
        tree_version=0,
        eval_state="never",
        last_eval_status=None,
        last_eval_at=None,
        last_eval_tree_version=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _echo_documents(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        owner_id = uuid.UUID(request.headers[PRINCIPAL_HEADER])
        path = request.url.path
        if path.endswith("/move") and "/parts/" in path:
            move = DocumentMove.model_validate_json(request.content)
            return httpx.Response(
                200, content=_part(owner_id, move.folder_id).model_dump_json()
            )
        if request.method == "POST" and path == "/api/v1/folders":
            name = FolderCreate.model_validate_json(request.content).name
            return httpx.Response(
                201, content=_folder(owner_id, name).model_dump_json()
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET":
            body = FolderListResponse(folders=[_folder(owner_id)])
            return httpx.Response(200, content=body.model_dump_json())
        return httpx.Response(200, content=_folder(owner_id).model_dump_json())

    return handler


def make_client(db_url: str, handler: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://127.0.0.1:9",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, documents_transport=httpx.MockTransport(handler))
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


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/folders"),
        ("GET", "/api/v1/folders?kind=part"),
        ("PATCH", f"/api/v1/folders/{FOLDER_ID}"),
        ("POST", f"/api/v1/folders/{FOLDER_ID}/move"),
        ("DELETE", f"/api/v1/folders/{FOLDER_ID}"),
        ("POST", f"/api/v1/parts/{uuid.uuid4()}/move"),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request], method: str, path: str
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.request(method, path, json={})
    assert response.status_code == 401
    assert seen == []


def test_create_and_list_forward_the_principal(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, headers = _register(client)
        created = client.post(
            "/api/v1/folders",
            json={"name": "Gearbox", "kind": "part", "parent_id": None},
            headers=headers,
        )
        listed = client.get("/api/v1/folders?kind=part", headers=headers)

    assert created.status_code == 201
    assert created.json()["name"] == "Gearbox"
    assert listed.status_code == 200
    # The counts the register prints came from the server, unchanged in transit.
    assert listed.json()["folders"][0]["document_count"] == 2
    assert {request.headers[PRINCIPAL_HEADER] for request in seen} == {user_id}
    # The drawer selector really is forwarded — a gateway that dropped it would
    # hand the parts register somebody's drawings tree.
    assert seen[-1].url.params["kind"] == "part"


def test_move_reports_the_folder_the_server_returned(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _user_id, headers = _register(client)
        moved = client.post(
            f"/api/v1/parts/{uuid.uuid4()}/move",
            json={"folder_id": str(FOLDER_ID)},
            headers=headers,
        )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == str(FOLDER_ID)


def test_folder_not_empty_409_reaches_the_browser_with_its_contents(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """The refusal is only useful if ``details.contents`` survives the hop."""
    contents = {
        "contents": [
            {"id": str(uuid.uuid4()), "name": "Bracket", "kind": "part"},
            {"id": str(uuid.uuid4()), "name": "Housings", "kind": "folder"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "folder_not_empty",
                    "message": "'Gearbox' still holds 2 item(s); move them out first.",
                    "details": contents,
                    "request_id": "upstream",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _user_id, headers = _register(client)
        refused = client.delete(f"/api/v1/folders/{FOLDER_ID}", headers=headers)

    assert refused.status_code == 409
    error = _envelope(refused.json())
    assert error["code"] == "folder_not_empty"
    assert error["details"] == contents


def test_cycle_422_reaches_the_browser(db_url: str, seen: list[httpx.Request]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "folder_cycle",
                    "message": "'Gearbox' cannot be moved inside itself.",
                    "details": None,
                    "request_id": "upstream",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _user_id, headers = _register(client)
        refused = client.post(
            f"/api/v1/folders/{FOLDER_ID}/move",
            json={"parent_id": str(FOLDER_ID)},
            headers=headers,
        )

    assert refused.status_code == 422
    assert _envelope(refused.json())["code"] == "folder_cycle"
