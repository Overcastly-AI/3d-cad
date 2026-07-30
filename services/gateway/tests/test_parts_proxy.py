"""gateway.parts — auth gating, principal forwarding, envelope passthrough.

The documents upstream is an ``httpx.MockTransport``; auth runs for real
(register → bearer token) over the same SQLite/aiosqlite test DB posture as
tests/test_auth.py (dialect split documented there).
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
from py_kit import REQUEST_ID_HEADER
from py_kit.db import async_dsn
from py_kit.schemas.parts import (
    PRINCIPAL_HEADER,
    PartCreate,
    PartListResponse,
    PartResponse,
    PartUpdate,
)
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)


def _part(owner_id: uuid.UUID, name: str = "Bracket") -> PartResponse:
    return PartResponse(
        id=uuid.uuid4(),
        name=name,
        owner_id=owner_id,
        length_unit="mm",
        # A fresh part sits at tree_version 0 — the staleness denominator every
        # part response now carries (feature-tree.md §1.2).
        tree_version=0,
        # Never evaluated (feature-tree.md §4.4a): the register's rebuild-health
        # column rides on every part response, and its all-null form is the only
        # claim a part nobody evaluated may make.
        eval_state="never",
        last_eval_status=None,
        last_eval_at=None,
        last_eval_tree_version=None,
        created_at=NOW,
        updated_at=NOW,
    )


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A file-backed SQLite database with the users schema applied."""
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def make_client(db_url: str, handler: Handler) -> TestClient:
    """Gateway TestClient whose documents upstream hits *handler*."""
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
    """A canned documents upstream: 201/200/204 with typed bodies."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        owner_id = uuid.UUID(request.headers[PRINCIPAL_HEADER])
        if request.method == "POST":
            name = PartCreate.model_validate_json(request.content).name
            return httpx.Response(201, content=_part(owner_id, name).model_dump_json())
        if request.method == "PATCH":
            update = PartUpdate.model_validate_json(request.content)
            part = _part(owner_id)
            if update.length_unit is not None:
                part.length_unit = update.length_unit
            return httpx.Response(200, content=part.model_dump_json())
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/api/v1/parts":
            body = PartListResponse(parts=[_part(owner_id)])
            return httpx.Response(200, content=body.model_dump_json())
        return httpx.Response(200, content=_part(owner_id).model_dump_json())

    return handler


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    """Register an account; return (user_id, bearer headers)."""
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


# --- auth gating ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/parts"),
        ("GET", "/api/v1/parts"),
        ("GET", f"/api/v1/parts/{uuid.uuid4()}"),
        ("DELETE", f"/api/v1/parts/{uuid.uuid4()}"),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request], method: str, path: str
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.request(method, path, json={"name": "Bracket"})
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


# --- happy paths: principal forwarding + typed passthrough ----------------------


def test_create_part_forwards_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(
            "/api/v1/parts", json={"name": "Bracket"}, headers=bearer
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Bracket"
    # The owner is the JWT-verified caller — derived at the gateway, never
    # from anything the client sent in the parts request.
    assert body["owner_id"] == user_id

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/parts"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    assert PartCreate.model_validate_json(upstream.content).name == "Bracket"
    # Request id propagates upstream so gateway/documents logs correlate.
    assert upstream.headers[REQUEST_ID_HEADER] == response.headers[REQUEST_ID_HEADER]


def test_list_parts_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.get("/api/v1/parts", headers=bearer)

    assert response.status_code == 200
    parts = PartListResponse.model_validate(response.json()).parts
    assert len(parts) == 1
    assert str(parts[0].owner_id) == user_id
    [upstream] = seen
    assert upstream.headers[PRINCIPAL_HEADER] == user_id


def test_get_part_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    part_id = uuid.uuid4()
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get(f"/api/v1/parts/{part_id}", headers=bearer)

    assert response.status_code == 200
    PartResponse.model_validate(response.json())
    [upstream] = seen
    assert upstream.url.path == f"/api/v1/parts/{part_id}"


def test_delete_part_204_empty_body(db_url: str, seen: list[httpx.Request]) -> None:
    part_id = uuid.uuid4()
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(f"/api/v1/parts/{part_id}", headers=bearer)

    assert response.status_code == 204
    assert response.content == b""
    [upstream] = seen
    assert upstream.method == "DELETE"
    assert upstream.url.path == f"/api/v1/parts/{part_id}"


def test_update_part_forwards_unit(db_url: str, seen: list[httpx.Request]) -> None:
    """The document-unit selector (units.md §U1) PATCHes length_unit through
    the gateway; the principal + body forward and the response re-surfaces."""
    part_id = uuid.uuid4()
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.patch(
            f"/api/v1/parts/{part_id}",
            json={"expected_tree_version": 0, "length_unit": "in"},
            headers=bearer,
        )

    assert response.status_code == 200
    assert PartResponse.model_validate(response.json()).length_unit == "in"
    [upstream] = seen
    assert upstream.method == "PATCH"
    assert upstream.url.path == f"/api/v1/parts/{part_id}"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    assert PartUpdate.model_validate_json(upstream.content).length_unit == "in"


# --- upstream error surfaces -----------------------------------------------------


def test_upstream_envelope_is_resurfaced(db_url: str) -> None:
    """Documents 404/409 envelopes pass through with their status + code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "part_not_found",
                    "message": "Part not found.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.get(f"/api/v1/parts/{uuid.uuid4()}", headers=bearer)

    assert response.status_code == 404
    error = _envelope(response.json())
    assert error["code"] == "part_not_found"
    assert error["message"] == "Part not found."
    # The gateway stamps its own request id, not the upstream one.
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_upstream_down_maps_to_502_envelope(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/parts", headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
    # Never a raw stack / internal URL.
    assert "Traceback" not in response.text
    assert "documents.internal" not in response.text


# --- gateway-side validation (never reaches upstream) ----------------------------


def test_invalid_body_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post("/api/v1/parts", json={"name": "   "}, headers=bearer)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_malformed_part_id_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/parts/not-a-uuid", headers=bearer)
    assert response.status_code == 422
    assert seen == []


def test_documents_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENTS_URL", "http://documents.internal:9001")
    assert GatewaySettings().documents_url == "http://documents.internal:9001"
