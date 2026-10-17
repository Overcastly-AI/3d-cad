"""Library thumbnails over the REAL 3-service chain (LIBRARY-THUMBNAILS).

Boots geometry + documents + gateway in-process exactly as
:mod:`tests.test_assembly_extents_chain` does (``httpx.ASGITransport``, scratch
SQLite via ``metadata.create_all``, in-process LRU stores, fail-open limiter)
and drives ``GET /api/v1/{parts,assemblies,drawings}/{id}/thumbnail`` as a user
would. What is pinned:

- the owner gets a PNG with a revalidation ``ETag`` and ``private, no-cache``;
  replaying the ETag is a ``304``;
- an edit changes the ETag AND the picture;
- a part whose tree fails is a 422 ``thumbnail_failed`` — not the picture of
  the body it had before the failing feature was added;
- ANOTHER user gets the uniform 404 for each kind, with or without an ETag
  (a revalidation is ownership-checked too).
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
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
from loft_wire.thumbnails import THUMBNAIL_FAILED
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "thumbnail-chain-jwt-secret-0123456789abcdef"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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
async def _chain(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
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
            timeout=120.0,
        ) as client,
    ):
        yield client


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _sketch(points: list[tuple[float, float]], *, closed: bool = True) -> Any:
    count = len(points)
    segments = count if closed else count - 1
    return {
        "name": "Profile",
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": f"e{index}",
                        "kind": "line",
                        "start": {"x": points[index][0], "y": points[index][1]},
                        "end": {
                            "x": points[(index + 1) % count][0],
                            "y": points[(index + 1) % count][1],
                        },
                    }
                    for index in range(segments)
                ],
                "constraints": [],
            },
        },
    }


def _extrude(sketch_id: str, depth: float) -> Any:
    return {
        "name": "Body",
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch_id},
                "distance_mm": depth,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


SQUARE = [(0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0)]


async def _add_feature(
    client: httpx.AsyncClient, headers: dict[str, str], part_id: str, body: Any
) -> dict[str, Any]:
    current = await client.get(f"/api/v1/parts/{part_id}", headers=headers)
    created = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={**body, "expected_tree_version": current.json()["tree_version"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    feature: dict[str, Any] = created.json()["feature"]
    return feature


async def _block_part(
    client: httpx.AsyncClient, headers: dict[str, str], name: str
) -> str:
    part = await client.post("/api/v1/parts", json={"name": name}, headers=headers)
    assert part.status_code == 201, part.text
    part_id: str = part.json()["id"]
    sketch = await _add_feature(client, headers, part_id, _sketch(SQUARE))
    await _add_feature(client, headers, part_id, _extrude(sketch["id"], 10.0))
    return part_id


def _assert_png(response: httpx.Response) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(PNG_MAGIC)
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["etag"].startswith('"')


def test_part_thumbnail_revalidates_and_follows_edits(tmp_path: Path) -> None:
    asyncio.run(_part_thumbnail_revalidates_and_follows_edits(tmp_path))


async def _part_thumbnail_revalidates_and_follows_edits(tmp_path: Path) -> None:
    async with _chain(tmp_path) as client:
        owner = await _register(client, "owner@example.com")
        part_id = await _block_part(client, owner, "Block")
        url = f"/api/v1/parts/{part_id}/thumbnail"

        first = await client.get(url, headers=owner)
        _assert_png(first)
        etag = first.headers["etag"]

        again = await client.get(url, headers={**owner, "If-None-Match": etag})
        assert again.status_code == 304
        assert again.headers["etag"] == etag
        assert again.content == b""

        # An edit: a second, taller boss on the same sketch changes the model.
        sketch = await _add_feature(
            client, owner, part_id, _sketch([(0, 0), (10, 0), (10, 10), (0, 10)])
        )
        await _add_feature(client, owner, part_id, _extrude(sketch["id"], 40.0))
        edited = await client.get(url, headers={**owner, "If-None-Match": etag})
        _assert_png(edited)
        assert edited.headers["etag"] != etag
        assert edited.content != first.content


def test_a_failed_part_has_no_picture(tmp_path: Path) -> None:
    asyncio.run(_a_failed_part_has_no_picture(tmp_path))


async def _a_failed_part_has_no_picture(tmp_path: Path) -> None:
    async with _chain(tmp_path) as client:
        owner = await _register(client, "owner@example.com")
        part_id = await _block_part(client, owner, "Block")
        url = f"/api/v1/parts/{part_id}/thumbnail"
        _assert_png(await client.get(url, headers=owner))

        # An extrude of an OPEN profile fails; the body before it still exists.
        open_sketch = await _add_feature(
            client, owner, part_id, _sketch(SQUARE, closed=False)
        )
        await _add_feature(client, owner, part_id, _extrude(open_sketch["id"], 5.0))
        failed = await client.get(url, headers=owner)
        assert failed.status_code == 422, failed.text
        assert failed.json()["error"]["code"] == THUMBNAIL_FAILED


def test_assembly_and_drawing_thumbnails_render(tmp_path: Path) -> None:
    asyncio.run(_assembly_and_drawing_thumbnails_render(tmp_path))


async def _assembly_and_drawing_thumbnails_render(tmp_path: Path) -> None:
    async with _chain(tmp_path) as client:
        owner = await _register(client, "owner@example.com")
        part_id = await _block_part(client, owner, "Block")
        assembly_id = await _assembly_of(client, owner, part_id)
        drawing_id = await _drawing_of(client, owner, part_id)
        _assert_png(
            await client.get(
                f"/api/v1/assemblies/{assembly_id}/thumbnail", headers=owner
            )
        )
        _assert_png(
            await client.get(f"/api/v1/drawings/{drawing_id}/thumbnail", headers=owner)
        )


def test_another_owner_cannot_see_a_thumbnail(tmp_path: Path) -> None:
    asyncio.run(_another_owner_cannot_see_a_thumbnail(tmp_path))


async def _another_owner_cannot_see_a_thumbnail(tmp_path: Path) -> None:
    async with _chain(tmp_path) as client:
        owner = await _register(client, "owner@example.com")
        intruder = await _register(client, "intruder@example.com")
        part_id = await _block_part(client, owner, "Secret block")
        assembly_id = await _assembly_of(client, owner, part_id)
        drawing_id = await _drawing_of(client, owner, part_id)
        urls = [
            f"/api/v1/parts/{part_id}/thumbnail",
            f"/api/v1/assemblies/{assembly_id}/thumbnail",
            f"/api/v1/drawings/{drawing_id}/thumbnail",
        ]
        for url in urls:
            mine = await client.get(url, headers=owner)
            _assert_png(mine)
            theirs = await client.get(url, headers=intruder)
            assert theirs.status_code == 404, (url, theirs.text)
            assert not theirs.content.startswith(PNG_MAGIC)
            # Holding the owner's ETag does not turn a foreign id into a 304.
            replay = await client.get(
                url, headers={**intruder, "If-None-Match": mine.headers["etag"]}
            )
            assert replay.status_code == 404, (url, replay.text)
            anonymous = await client.get(url)
            assert anonymous.status_code == 401


async def _assembly_of(
    client: httpx.AsyncClient, headers: dict[str, str], part_id: str
) -> str:
    assembly = await client.post(
        "/api/v1/assemblies", json={"name": "Stack"}, headers=headers
    )
    assert assembly.status_code == 201, assembly.text
    assembly_id: str = assembly.json()["id"]
    created = await client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": assembly.json()["doc_version"],
            "ref_document_id": part_id,
            "ref_document_kind": "part",
            "name": "Block <1>",
            "placement": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "grounded": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return assembly_id


async def _drawing_of(
    client: httpx.AsyncClient, headers: dict[str, str], part_id: str
) -> str:
    drawing = await client.post(
        "/api/v1/drawings", json={"name": "Block drawing"}, headers=headers
    )
    assert drawing.status_code == 201, drawing.text
    drawing_id: str = drawing.json()["id"]
    tree = (await client.get(f"/api/v1/drawings/{drawing_id}", headers=headers)).json()
    version: int = tree["drawing"]["doc_version"]
    if tree["sheets"]:
        sheet_id: str = tree["sheets"][0]["sheet"]["id"]
    else:
        sheet = await client.post(
            f"/api/v1/drawings/{drawing_id}/sheets",
            json={"expected_version": version, "name": "Sheet 1"},
            headers=headers,
        )
        assert sheet.status_code == 201, sheet.text
        sheet_id = sheet.json()["sheet"]["id"]
        version = sheet.json()["doc_version"]
    view = await client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        json={
            "expected_version": version,
            "ref_document_id": part_id,
            "ref_document_kind": "part",
            "projection": "iso",
            "position": {"x_mm": 120.0, "y_mm": 100.0},
        },
        headers=headers,
    )
    assert view.status_code == 201, view.text
    return drawing_id
