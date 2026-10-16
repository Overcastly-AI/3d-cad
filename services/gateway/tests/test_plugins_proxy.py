"""gateway.plugins: the plugin manifests apps/web builds the Build toolbar
and custom-feature forms from (RESEARCH §23), proxied from documents and
auth-gated like every route. Harness as tests/test_materials_proxy.py."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from loft_plugins import REGISTRY
from loft_wire.plugins import PluginCatalog
from py_kit.db import async_dsn
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


def _catalog(seen: list[httpx.Request]) -> Handler:
    """The documents plugins route, canned."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=REGISTRY.catalog().model_dump_json())

    return handler


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_the_catalog_reaches_the_web_app_through_the_gateway(db_url: str) -> None:
    seen: list[httpx.Request] = []
    with make_client(db_url, _catalog(seen)) as client:
        response = client.get("/api/v1/plugins", headers=_register(client))
    assert response.status_code == 200, response.text
    assert PluginCatalog.model_validate(response.json()) == REGISTRY.catalog()
    [upstream] = seen
    assert (upstream.method, upstream.url.path) == ("GET", "/api/v1/plugins")


def test_unauthenticated_is_401_and_nothing_is_forwarded(db_url: str) -> None:
    seen: list[httpx.Request] = []
    with make_client(db_url, _catalog(seen)) as client:
        response = client.get("/api/v1/plugins")
    assert response.status_code == 401
    assert seen == []
