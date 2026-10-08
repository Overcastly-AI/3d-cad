"""DESIGN-INTENT-BACKFILL over the REAL 3-service chain (in-process ASGI).

The three hard-parts QA trees (bracket base 60 -> 70, enclosure width
120 -> 130, impeller hub 40 -> 44), stored the way a part saved before
DESIGN-INTENT-REFS is stored: every pick WITHOUT a name. Opening the part
(one evaluate) must name every pick in the background, with exactly the
fields a fresh pick at the same sizes stores, and the size edit must then
rebuild every feature to the freshly picked part's volume. The control is
the same edit without that open: it must fail. Same boot as
``test_loft_file_chain.py`` (geometry + documents + gateway behind
``httpx.ASGITransport``, scratch SQLite, no ports).
"""

import asyncio
import contextlib
import importlib.util
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx2 as httpx
import pytest
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from loft_wire.features import FEATURE_REGISTRY
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"
_BUILDERS = Path(__file__).resolve().parents[2] / "geometry" / "tests"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _BUILDERS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: name -> (builder module, its size attribute names)
_PARTS = {
    "bracket": ("_bracket_builder", "AUTHORED_W", "REVISED_W"),
    "enclosure": ("_enclosure_builder", "AUTHORED_W", "REVISED_W"),
    "impeller": ("_impeller_builder", "AUTHORED_D", "REVISED_D"),
}


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.router.lifespan_context(app):
        yield


@contextlib.asynccontextmanager
async def _gateway(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    documents_url = f"sqlite:///{tmp_path}/documents.db"
    gateway_url = f"sqlite:///{tmp_path}/gateway.db"
    await _create_schema(documents_url, DocumentsBase)
    await _create_schema(gateway_url, GatewayBase)
    geometry_app = build_geometry_app(GeometrySettings(s3_url=None))
    documents_app = build_documents_app(
        DocumentsSettings(postgres_url=documents_url, s3_url=None)
    )
    gateway_app = build_gateway_app(
        GatewaySettings(
            geometry_url="http://geometry.internal:8002",
            documents_url="http://documents.internal:8001",
            postgres_url=gateway_url,
            redis_url=None,
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        geometry_transport=httpx.ASGITransport(geometry_app),
        documents_transport=httpx.ASGITransport(documents_app),
    )
    async with (
        _lifespan(geometry_app),
        _lifespan(documents_app),
        _lifespan(gateway_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway_app),
            base_url="http://gateway.test",
            timeout=300.0,
        ) as client,
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "backfill@example.com", "password": "hunter2-passphrase"},
        )
        assert response.status_code == 201, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


def _strip(value: Any) -> Any:
    def drop(node: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v for k, v in node.items() if k not in ("topo_name", "end_a_topo_name")
        }

    return json.loads(json.dumps(value), object_hook=drop)


def _remap(value: Any, ids: dict[str, str]) -> Any:
    """*value* with every builder feature id replaced by the stored one (in
    references AND inside names, which embed the naming feature's id)."""
    text = json.dumps(value)
    for old, new in ids.items():
        text = text.replace(old, new)
    return json.loads(text)


async def _store(
    client: httpx.AsyncClient, name: str, tree: list[dict[str, Any]]
) -> tuple[str, dict[str, str]]:
    """Store *tree* as a part, feature by feature; returns the part id and the
    builder-id -> stored-id map."""
    part_id: str = (await client.post("/api/v1/parts", json={"name": name})).json()[
        "id"
    ]
    ids: dict[str, str] = {}
    for index, item in enumerate(tree):
        feature = _remap(item["feature"], ids)
        response = await client.post(
            f"/api/v1/parts/{part_id}/features",
            json={
                "name": f"F{index + 1}",
                "feature": feature,
                "expected_tree_version": index,
            },
        )
        assert response.status_code == 201, response.text
        ids[item["id"]] = response.json()["feature"]["id"]
    return part_id, ids


def _picks(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every stored pick's signature in *params* (the backfill's walk)."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            mapping = cast(dict[str, Any], node)
            if mapping.get("kind") == "subshape" and "selector" in mapping:
                found.append(mapping["selector"]["signature"])
                return
            for value in mapping.values():
                walk(value)
        elif isinstance(node, list):
            for value in cast(list[Any], node):
                walk(value)

    walk(params)
    assert found
    return found


def _stored(feature: dict[str, Any]) -> dict[str, Any]:
    """*feature*'s params exactly as documents stores them (validated, dumped)."""
    envelope = FEATURE_REGISTRY.load(
        feature["type"], feature["version"], feature["params"]
    )
    return envelope.params.model_dump(mode="json")


async def _params(client: httpx.AsyncClient, part_id: str) -> list[dict[str, Any]]:
    tree = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
    return [f["feature"]["params"] for f in tree["features"]]


async def _resize(
    client: httpx.AsyncClient, part_id: str, sketch: dict[str, Any], ids: dict[str, str]
) -> None:
    tree = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
    first = tree["features"][0]
    response = await client.patch(
        f"/api/v1/parts/{part_id}/features/{first['id']}",
        json={
            "expected_tree_version": tree["tree_version"],
            "feature": _remap(sketch["feature"], ids),
        },
    )
    assert response.status_code == 200, response.text


async def _evaluate(client: httpx.AsyncClient, part_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/parts/{part_id}/evaluate")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _at_ids(module: str, ids: dict[str, str]) -> ModuleType:
    """A fresh copy of the builder whose feature ids are the STORED ones, so
    its picks (and the names they carry, which embed feature ids and, for a
    split face, a digest of its neighbours' names) are what a pick on the
    stored part would capture: the oracle."""
    builder = _load(module)
    for attr in dir(builder):
        value = getattr(builder, attr)
        if isinstance(value, uuid.UUID) and str(value) in ids:
            setattr(builder, attr, uuid.UUID(ids[str(value)]))
    return builder


def _ids(tree: list[dict[str, Any]], stored: list[str]) -> dict[str, str]:
    return {item["id"]: new for item, new in zip(tree, stored, strict=True)}


@pytest.mark.parametrize("name", sorted(_PARTS))
def test_opening_an_old_part_names_its_picks_and_the_edit_then_rebuilds(
    tmp_path: Path, name: str
) -> None:
    module, authored_attr, revised_attr = _PARTS[name]
    builder = _load(module)
    authored, revised = getattr(builder, authored_attr), getattr(builder, revised_attr)
    fresh = builder.authored_tree(authored)

    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id, ids = await _store(client, name, _strip(fresh))
            control_id, control_ids = await _store(client, f"{name}-ctl", _strip(fresh))
            oracle = _at_ids(module, ids)
            picked = oracle.authored_tree(authored)
            assert [item["id"] for item in picked] == list(ids.values())

            # CONTROL: edited without ever being opened, the part fails.
            await _resize(
                client, control_id, builder.revised(fresh, revised)[0], control_ids
            )
            control = await _evaluate(client, control_id)
            assert any(f["status"] == "error" for f in control["features"])

            # Open: the evaluate backfills in the background.
            opened = await _evaluate(client, part_id)
            assert {f["status"] for f in opened["features"]} == {"ok"}
            part = (await client.get(f"/api/v1/parts/{part_id}")).json()
            assert part["tree_version"] == len(
                fresh
            )  # metadata: no bump under the user
            assert part["eval_state"] == "ok"  # the verdict is still current
            named = await _params(client, part_id)
            # Field for field what a fresh pick on the stored part captures.
            assert named == [_stored(item["feature"]) for item in picked]
            assert all(sig.get("topo_name") for sig in _picks(named))

            # A second open changes nothing (checked, and idempotent anyway).
            await _evaluate(client, part_id)
            again = (await client.get(f"/api/v1/parts/{part_id}")).json()
            assert again["tree_version"] == part["tree_version"]

            # The QA edit now rebuilds every feature, to the freshly picked
            # part's body (the oracle, rebuilt in process at the same request).
            await _resize(client, part_id, builder.revised(fresh, revised)[0], ids)
            edited = await _evaluate(client, part_id)
            assert {f["status"] for f in edited["features"]} == {"ok"}
            rebuilt = oracle.evaluate(oracle.revised(picked, revised), 90)
            want = rebuilt.result.properties.volume
            assert edited["properties"]["volume"] == pytest.approx(
                want, rel=1e-12, abs=1e-9
            )

    asyncio.run(scenario())


def test_ids_in_names_are_remapped_consistently() -> None:
    assert _remap({"a": "x-1:outer"}, {"x-1": str(uuid.UUID(int=5))}) == {
        "a": f"{uuid.UUID(int=5)}:outer"
    }
    assert _ids([{"id": "a"}], ["b"]) == {"a": "b"}
