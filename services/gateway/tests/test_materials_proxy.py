"""gateway.materials — the library read apps/web is allowed to reach.

Same harness as tests/test_parts_proxy.py (real auth over a SQLite users DB,
``httpx.MockTransport`` documents upstream): what is under test here is that the
gateway has the route at all (apps/web talks only to the gateway, so a missing
twin is a 404 the material picker cannot work around), that it gates on auth
like every other gateway route, and that the density table arrives unaltered.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.materials import MATERIALS, MaterialLibraryResponse
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]


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


def _library(seen: list[httpx.Request]) -> Handler:
    """The documents materials route, canned."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = MaterialLibraryResponse(materials=list(MATERIALS))
        return httpx.Response(200, content=body.model_dump_json())

    return handler


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_library_reaches_the_web_app_through_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """The route EXISTS on the gateway and forwards to documents' twin.

    Guards the boundary regression this route was added for: without it the
    picker's only options are a 404 or reaching past the gateway.
    """
    with make_client(db_url, _library(seen)) as client:
        response = client.get("/api/v1/materials", headers=_register(client))

    assert response.status_code == 200
    library = MaterialLibraryResponse.model_validate(response.json())
    # Every density arrives byte-identical to the table geometry multiplies by
    # — a drifted density is a wrong mass nobody notices (materials.md §1).
    assert library.materials == list(MATERIALS)
    [upstream] = seen
    assert upstream.method == "GET"
    assert upstream.url.path == "/api/v1/materials"


def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _library(seen)) as client:
        response = client.get("/api/v1/materials")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert seen == []


def test_upstream_down_maps_to_502_envelope(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        response = client.get("/api/v1/materials", headers=_register(client))

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"
    assert "documents.internal" not in response.text
