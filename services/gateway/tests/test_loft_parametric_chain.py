"""``.loft`` 1.2: a parametric part over the REAL 3-service chain (RESEARCH §20).

Same in-process boot as ``test_loft_file_chain.py`` (geometry + documents +
gateway behind ``httpx.ASGITransport``, scratch SQLite, no ports). The frozen
fixture ``packages/loft-wire/tests/fixtures/golden-v1.2.loft`` is the part
:func:`_build` makes, exported by this chain: parameters ``W`` = 50 mm and
``D`` = 5 mm; a rectangle whose width dimension ``width`` is ``= W`` and whose
height is ``= width / 2``; an extrude ``= D * 2``; and the named version
"Rev A", saved at ``W`` = 40. Volume W * W/2 * 2D: 12 500 mm^3 (Rev A 8 000).

It was written once with ``LOFT_WRITE_GOLDEN_V1_2=1`` and is never
regenerated: a format change gets a new fixture, as 1.0 and 1.1 did. What it
proves:

* import -> export -> import (a fresh install) -> export gives identical
  bytes, and the trees and versions are the fixture's own bytes;
* the imported part re-drives: a changed parameter changes the volume by hand;
* a format 1.1 reader (``extra="ignore"``, newer minor read) imports the
  numbers: no parameters, no formulas, the same volume, no warning.
"""

import asyncio
import contextlib
import io
import json
import os
import zipfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

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
from loft_wire import loft_file
from loft_wire.loft_file import LoftTree
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"
ROUNDTRIP_TOL = 1e-7

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "loft-wire"
    / "tests"
    / "fixtures"
    / "golden-v1.2.loft"
)
W_ID = "5a1e0c3e-7c1f-4d8a-9b21-0f6c2a1d4e01"
D_ID = "5a1e0c3e-7c1f-4d8a-9b21-0f6c2a1d4e02"


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
    """One install: its own databases under *tmp_path*."""
    tmp_path.mkdir(parents=True, exist_ok=True)
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
            timeout=60.0,
        ) as client,
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "loft@example.com", "password": "hunter2-passphrase"},
        )
        assert response.status_code == 201, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _coincident(a: str, b: str) -> Any:
    return {
        "kind": "coincident",
        "a": {"entity": a, "point": "end"},
        "b": {"entity": b, "point": "start"},
    }


def _sketch() -> Any:
    """A fully constrained rectangle: width ``= W``, height ``= width / 2``."""
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                _line("e1", (0, 0), (40, 0)),
                _line("e2", (40, 0), (40, 20)),
                _line("e3", (40, 20), (0, 20)),
                _line("e4", (0, 20), (0, 0)),
            ],
            "constraints": [
                _coincident("e1", "e2"),
                _coincident("e2", "e3"),
                _coincident("e3", "e4"),
                _coincident("e4", "e1"),
                {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
                {"kind": "horizontal", "entity": "e1"},
                {"kind": "horizontal", "entity": "e3"},
                {"kind": "vertical", "entity": "e2"},
                {"kind": "vertical", "entity": "e4"},
                {
                    "kind": "distance",
                    "entity": "e1",
                    "value_mm": 40.0,
                    "name": "width",
                    "expression": "W",
                },
                {
                    "kind": "distance",
                    "entity": "e2",
                    "value_mm": 20.0,
                    "expression": "width / 2",
                },
            ],
        },
    }


def _extrude(sketch_id: str) -> Any:
    return {
        "type": "extrude",
        "version": 1,
        "expressions": {"/distance_mm": "D * 2"},
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": 10.0,
            "operation": "add",
            "direction": "normal",
        },
    }


async def _tree_version(client: httpx.AsyncClient, part_id: str) -> int:
    tree = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
    version: int = tree["tree_version"]
    return version


async def _add(client: httpx.AsyncClient, part_id: str, name: str, feature: Any) -> str:
    response = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": feature,
            "expected_tree_version": await _tree_version(client, part_id),
        },
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


async def _set_parameters(
    client: httpx.AsyncClient, part_id: str, w: str, d: str
) -> None:
    response = await client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={
            "expected_tree_version": await _tree_version(client, part_id),
            "parameters": [
                {"id": W_ID, "name": "W", "expression": w, "unit": "length"},
                {"id": D_ID, "name": "D", "expression": d, "unit": "length"},
            ],
        },
    )
    assert response.status_code == 200, response.text


async def _build(client: httpx.AsyncClient) -> str:
    """The fixture's part (module docstring)."""
    created = await client.post("/api/v1/parts", json={"name": "Parametric plate"})
    assert created.status_code == 201, created.text
    part_id: str = created.json()["id"]
    await _set_parameters(client, part_id, "40 mm", "5 mm")
    sketch_id = await _add(client, part_id, "Sketch1", _sketch())
    await _add(client, part_id, "Extrude1", _extrude(sketch_id))
    saved = await client.post(
        f"/api/v1/parts/{part_id}/versions",
        json={"name": "Rev A", "message": "W = 40", "author": "Ada Lovelace"},
    )
    assert saved.status_code == 201, saved.text
    await _set_parameters(client, part_id, "50 mm", "5 mm")
    return part_id


async def _volume(client: httpx.AsyncClient, part_id: str) -> float:
    response = await client.post(f"/api/v1/parts/{part_id}/evaluate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["status"] for f in body["features"]] == ["ok", "ok"], body["features"]
    volume: float = body["properties"]["volume"]
    return volume


async def _export(client: httpx.AsyncClient, part_id: str) -> bytes:
    response = await client.get(f"/api/v1/parts/{part_id}/export.loft")
    assert response.status_code == 200, response.text
    return response.content


async def _import(client: httpx.AsyncClient, data: bytes) -> str:
    response = await client.post(
        "/api/v1/parts/import",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["warnings"] == []
    part_id: str = response.json()["part"]["id"]
    return part_id


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _manifest_of_this_build(members: dict[str, bytes]) -> dict[str, Any]:
    """The manifest without what names the build that wrote it."""
    manifest = json.loads(members["manifest.json"])
    manifest.pop("loft_version")
    manifest["members"].pop("cache/body.step")
    manifest["cache"].pop("step_sha256")
    return dict(manifest)


def test_write_the_frozen_fixture(tmp_path: Path) -> None:
    """Writes golden-v1.2.loft, once, when asked; otherwise does nothing."""
    if os.environ.get("LOFT_WRITE_GOLDEN_V1_2") != "1":
        pytest.skip("the 1.2 fixture is frozen; LOFT_WRITE_GOLDEN_V1_2=1 writes it")

    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _build(client)
            assert await _volume(client, part_id) == pytest.approx(12_500.0)
            FIXTURE.write_bytes(await _export(client, part_id))

    asyncio.run(scenario())


def test_export_import_re_export_is_byte_identical(tmp_path: Path) -> None:
    fixture = FIXTURE.read_bytes()
    frozen = _members(fixture)

    async def scenario() -> None:
        async with _gateway(tmp_path / "a") as client:
            part_id = await _import(client, fixture)
            assert await _volume(client, part_id) == pytest.approx(
                12_500.0, abs=ROUNDTRIP_TOL
            )
            first = await _export(client, part_id)
            assert await _export(client, part_id) == first
        async with _gateway(tmp_path / "b") as client:
            again = await _export(client, await _import(client, first))
        assert again == first

        exported = _members(first)
        assert list(exported) == list(frozen)
        assert json.loads(exported["manifest.json"])["format_version"] == "1.2"
        for name in frozen:
            if name not in ("manifest.json", "cache/body.step"):
                assert exported[name] == frozen[name], name
        assert _manifest_of_this_build(exported) == _manifest_of_this_build(frozen)

    asyncio.run(scenario())


def test_the_imported_part_re_drives(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _import(client, FIXTURE.read_bytes())
            rows = (await client.get(f"/api/v1/parts/{part_id}/parameters")).json()
            assert [(r["name"], r["value"]) for r in rows["parameters"]] == [
                ("W", 50.0),
                ("D", 5.0),
            ]
            features = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
            sketch, extrude = (f["feature"] for f in features["features"])
            assert extrude["expressions"] == {"/distance_mm": "D * 2"}
            dims = [c for c in sketch["params"]["constraints"] if "value_mm" in c]
            assert [d["expression"] for d in dims] == ["W", "width / 2"]

            # Volume W * W/2 * 2D, by hand.
            await _set_parameters(client, part_id, "60 mm", "5 mm")
            assert await _volume(client, part_id) == pytest.approx(
                60 * 30 * 10, abs=ROUNDTRIP_TOL
            )
            await _set_parameters(client, part_id, "60 mm", "7.5 mm")
            assert await _volume(client, part_id) == pytest.approx(
                60 * 30 * 15, abs=ROUNDTRIP_TOL
            )

    asyncio.run(scenario())


@contextlib.contextmanager
def _as_a_1_1_reader() -> Generator[None]:
    """The 1.1 reader's tree models, which predate parameters: a newer minor
    is read and the keys 1.2 added are ignored (``extra="ignore"``)."""
    parse_tree = loft_file._parse_tree  # pyright: ignore[reportPrivateUsage]

    def parse_as_1_1(data: bytes, *, member: str) -> LoftTree:
        raw = json.loads(data)
        raw.pop("parameters", None)
        for feature in raw["features"]:
            feature.pop("expressions", None)
            feature.pop("dimension_expressions", None)
        return parse_tree(json.dumps(raw).encode(), member=member)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(loft_file, "LOFT_FORMAT_MINOR", 1)
        patch.setattr(loft_file, "_parse_tree", parse_as_1_1)
        yield


def test_a_1_1_reader_imports_the_numbers(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            with _as_a_1_1_reader():
                part_id = await _import(client, FIXTURE.read_bytes())
            rows = (await client.get(f"/api/v1/parts/{part_id}/parameters")).json()
            assert rows["parameters"] == []
            features = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
            sketch, extrude = (f["feature"] for f in features["features"])
            assert "expressions" not in extrude
            assert extrude["params"]["distance_mm"] == 10.0
            dims = [c for c in sketch["params"]["constraints"] if "value_mm" in c]
            # The formula over the sketch's own dimension stays: every Loft
            # evaluates it. The one that named W is the number it resolved to.
            assert [(d["expression"], d["value_mm"]) for d in dims] == [
                (None, 50.0),
                ("width / 2", 25.0),
            ]
            assert await _volume(client, part_id) == pytest.approx(
                12_500.0, abs=ROUNDTRIP_TOL
            )

    asyncio.run(scenario())
