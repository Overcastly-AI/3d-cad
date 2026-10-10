"""``/api/v1/parts/{id}/parameters`` through the gateway, over the REAL
documents app (in-process ASGI, scratch SQLite, no ports, no kernel).

What it proves: both routes exist on the gateway (apps/web talks only to the
gateway), they need a bearer, documents scopes them to the caller (another
account's part is a 404 for GET and PUT, and the PUT changes nothing), and the
documents 422 envelopes for a cycle and an unknown name come back verbatim.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx2 as httpx
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.router.lifespan_context(app):
        yield


async def _token(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@contextlib.asynccontextmanager
async def _gateway(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    documents_url = f"sqlite:///{tmp_path}/documents.db"
    gateway_url = f"sqlite:///{tmp_path}/gateway.db"
    await _create_schema(documents_url, DocumentsBase)
    await _create_schema(gateway_url, GatewayBase)
    documents_app = build_documents_app(
        DocumentsSettings(postgres_url=documents_url, s3_url=None)
    )
    gateway_app = build_gateway_app(
        GatewaySettings(
            geometry_url="http://127.0.0.1:9",  # nothing listens; never called
            documents_url="http://documents.internal:8001",
            postgres_url=gateway_url,
            redis_url=None,
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        documents_transport=httpx.ASGITransport(documents_app),
    )
    async with (
        _lifespan(documents_app),
        _lifespan(gateway_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway_app),
            base_url="http://gateway.test",
            timeout=30.0,
        ) as client,
    ):
        yield client


def _row(name: str, expression: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "expression": expression,
        "unit": "length",
    }


def test_parameters_through_the_gateway(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            owner = await _token(client, "loft@example.com")
            created = await client.post(
                "/api/v1/parts", json={"name": "Plate"}, headers=owner
            )
            assert created.status_code == 201, created.text
            path = f"/api/v1/parts/{created.json()['id']}/parameters"

            put = await client.put(
                path,
                json={
                    "expected_tree_version": 0,
                    "parameters": [_row("w", "40"), _row("h", "w / 2")],
                },
                headers=owner,
            )
            assert put.status_code == 200, put.text
            assert [row["value"] for row in put.json()["parameters"]] == [40.0, 20.0]
            got = await client.get(path, headers=owner)
            assert got.json() == put.json()

            for rows, code in [
                ([_row("a", "b"), _row("b", "a")], "expression_cycle"),
                ([_row("a", "nope + 1")], "expression_unknown_name"),
            ]:
                refused = await client.put(
                    path,
                    json={"expected_tree_version": 1, "parameters": rows},
                    headers=owner,
                )
                assert refused.status_code == 422, refused.text
                assert refused.json()["error"]["code"] == code
            cycle = await client.put(
                path,
                json={
                    "expected_tree_version": 1,
                    "parameters": [_row("a", "b"), _row("b", "a")],
                },
                headers=owner,
            )
            assert cycle.json()["error"]["details"]["chain"] == ["a", "b", "a"]

            # Another account: the same 404 as a part that does not exist.
            other = await _token(client, "other@example.com")
            assert (await client.get(path, headers=other)).status_code == 404
            foreign = await client.put(
                path,
                json={"expected_tree_version": 1, "parameters": []},
                headers=other,
            )
            assert foreign.status_code == 404, foreign.text
            assert (await client.get(path, headers=owner)).json() == put.json()

            # No bearer, nothing forwarded.
            assert (await client.get(path)).status_code == 401
            assert (
                await client.put(
                    path, json={"expected_tree_version": 1, "parameters": []}
                )
            ).status_code == 401

    asyncio.run(scenario())


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def test_feature_formulas_survive_the_gateway_and_guard_their_parameter(
    tmp_path: Path,
) -> None:
    """The gateway forwards a feature's `expressions` (it re-serializes the
    body), and a parameter still in use comes back as documents' 409."""

    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            owner = await _token(client, "loft@example.com")
            created = await client.post(
                "/api/v1/parts", json={"name": "Block"}, headers=owner
            )
            part = f"/api/v1/parts/{created.json()['id']}"
            put = await client.put(
                f"{part}/parameters",
                json={"expected_tree_version": 0, "parameters": [_row("D", "12")]},
                headers=owner,
            )
            assert put.status_code == 200, put.text
            sketch = {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        _line("e1", (0, 0), (40, 0)),
                        _line("e2", (40, 0), (40, 25)),
                        _line("e3", (40, 25), (0, 25)),
                        _line("e4", (0, 25), (0, 0)),
                    ],
                    "constraints": [],
                },
            }
            made = await client.post(
                f"{part}/features",
                json={"name": "S", "feature": sketch, "expected_tree_version": 1},
                headers=owner,
            )
            assert made.status_code == 201, made.text
            extrude = {
                "type": "extrude",
                "version": 1,
                "expressions": {"/distance_mm": "D * 2"},
                "params": {
                    "profile": {
                        "kind": "feature",
                        "feature_id": made.json()["feature"]["id"],
                    },
                    "distance_mm": 1.0,
                    "operation": "add",
                    "direction": "normal",
                },
            }
            made = await client.post(
                f"{part}/features",
                json={"name": "E", "feature": extrude, "expected_tree_version": 2},
                headers=owner,
            )
            assert made.status_code == 201, made.text
            stored = made.json()["feature"]["feature"]
            assert stored["expressions"] == {"/distance_mm": "D * 2"}
            assert stored["params"]["distance_mm"] == 24.0

            refused = await client.put(
                f"{part}/parameters",
                json={"expected_tree_version": 3, "parameters": []},
                headers=owner,
            )
            assert refused.status_code == 409, refused.text
            error = refused.json()["error"]
            assert error["code"] == "parameter_in_use"
            assert error["details"]["parameters"] == ["D"]

    asyncio.run(scenario())
