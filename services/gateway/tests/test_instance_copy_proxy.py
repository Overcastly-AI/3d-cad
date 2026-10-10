"""gateway ``POST /assemblies/{id}/instances/{instance_id}/copy`` proxy.

Same harness as tests/test_assemblies_proxy.py (self-contained: test modules
cannot import each other under ``--import-mode=importlib``): the documents
upstream is an ``httpx.MockTransport`` and auth runs for real over SQLite.
"""

import asyncio
import json
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
from loft_wire.assemblies import (
    InstanceMutationResponse,
    InstanceResponse,
    Placement,
)
from loft_wire.geometry import Vec3
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit import REQUEST_ID_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
ASSEMBLY = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
SOURCE = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
COPY = uuid.UUID("00000000-0000-0000-0000-0000000000b9")
PATH = f"/api/v1/assemblies/{ASSEMBLY}/instances/{SOURCE}/copy"


def _copy_response() -> InstanceMutationResponse:
    return InstanceMutationResponse(
        instance=InstanceResponse(
            id=COPY,
            assembly_id=ASSEMBLY,
            ref_document_id=uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
            ref_document_kind="part",
            ref_pinned_version=None,
            name="Hole plate <2>",
            placement=Placement(position=Vec3(x=20.0, y=0.0, z=0.0)),
            grounded=False,
            order_index=1,
            created_at=NOW,
            updated_at=NOW,
        ),
        doc_version=4,
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


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


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


def _echo(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, content=_copy_response().model_dump_json())

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


def test_unauthenticated_is_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo(seen)) as client:
        response = client.post(PATH, json={"expected_version": 0})
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


def test_forwards_principal_path_and_default_offset(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(PATH, json={"expected_version": 3}, headers=bearer)

    assert response.status_code == 201, response.text
    assert InstanceMutationResponse.model_validate(response.json()) == _copy_response()
    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == PATH
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    # The gateway validated the body and filled in the documented default.
    assert json.loads(upstream.content) == {
        "expected_version": 3,
        "offset": [20.0, 0.0, 0.0],
    }


def test_forwards_an_explicit_offset(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            PATH,
            json={"expected_version": 0, "offset": [0, -5.5, 12]},
            headers=bearer,
        )

    assert response.status_code == 201, response.text
    [upstream] = seen
    assert json.loads(upstream.content)["offset"] == [0.0, -5.5, 12.0]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_version": -1},
        {"expected_version": 0, "offset": [1.0, 2.0]},
        {"expected_version": 0, "offset": [1e9, 0.0, 0.0]},
        {"expected_version": 0, "offset": {"x": 1.0, "y": 0.0, "z": 0.0}},
    ],
)
def test_bad_body_is_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request], body: dict[str, Any]
) -> None:
    with make_client(db_url, _echo(seen)) as client:
        _, bearer = _register(client)
        response = client.post(PATH, json=body, headers=bearer)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_malformed_instance_id_is_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/instances/not-a-uuid/copy",
            json={"expected_version": 0},
            headers=bearer,
        )
    assert response.status_code == 422
    assert seen == []


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (404, "assembly_not_found"),
        (404, "instance_not_found"),
        (422, "stale_assembly_version"),
        (422, "instance_limit_exceeded"),
        (422, "ref_document_not_found"),
    ],
)
def test_upstream_envelope_is_resurfaced(
    db_url: str, status_code: int, code: str
) -> None:
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
        response = client.post(PATH, json={"expected_version": 0}, headers=bearer)

    assert response.status_code == status_code
    error = _envelope(response.json())
    assert error["code"] == code
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
