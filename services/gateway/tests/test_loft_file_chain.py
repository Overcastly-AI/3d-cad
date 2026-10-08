"""``.loft`` export and import over the REAL 3-service chain (in-process ASGI).

Same boot as ``test_assembly_import_chain.py`` (geometry + documents + gateway
behind ``httpx.ASGITransport``, scratch SQLite, no ports). What it proves:

* an export is a real ``.loft``: the canonical members, the cached STEP body and
  the evaluated volume in the manifest — and the same part exports the SAME
  BYTES twice;
* an import rebuilds the part from ``tree.json`` to the same volume, with no
  warning; importing the same file twice gives a detached "copy";
* an ``import`` feature's STEP travels as a blob and comes back inline;
* a hand-edited tree imports with a warning; a newer major format, a newer
  ``param_version``, an oversize upload and a missing token are refused before
  anything is created.
"""

import asyncio
import contextlib
import io
import json
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from build123d import Solid
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.kernel.export import export_step_bytes
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from loft_wire import loft_file
from loft_wire.loft_file import canonical_json, sha256_hex
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"

#: The kernel linear tolerance (CLAUDE.md), as in the sibling chain test.
ROUNDTRIP_TOL = 1e-7


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


def _rect_sketch(width: float, height: float) -> dict[str, Any]:
    corners = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": f"e{index + 1}",
                "kind": "line",
                "construction": False,
                "start": {"x": corners[index][0], "y": corners[index][1]},
                "end": {
                    "x": corners[(index + 1) % 4][0],
                    "y": corners[(index + 1) % 4][1],
                },
            }
            for index in range(4)
        ],
        "constraints": [],
    }


async def _add(
    client: httpx.AsyncClient, part_id: str, name: str, feature: dict[str, Any]
) -> str:
    tree = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
    response = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": feature,
            "expected_tree_version": tree["tree_version"],
        },
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


async def _extruded_part(client: httpx.AsyncClient, name: str) -> str:
    """Sketch1 (40 x 25) <- Extrude1 (10): volume 10 000 mm^3."""
    part_id: str = (await client.post("/api/v1/parts", json={"name": name})).json()[
        "id"
    ]
    sketch = await _add(
        client,
        part_id,
        "Sketch1",
        {"type": "sketch", "version": 1, "params": _rect_sketch(40.0, 25.0)},
    )
    await _add(
        client,
        part_id,
        "Extrude1",
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
        },
    )
    return part_id


async def _volume(client: httpx.AsyncClient, part_id: str) -> float:
    response = await client.post(f"/api/v1/parts/{part_id}/evaluate")
    assert response.status_code == 200, response.text
    volume: float = response.json()["properties"]["volume"]
    return volume


async def _export(client: httpx.AsyncClient, part_id: str) -> bytes:
    response = await client.get(f"/api/v1/parts/{part_id}/export.loft")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == loft_file.LOFT_MEDIA_TYPE
    return response.content


async def _import(client: httpx.AsyncClient, data: bytes) -> httpx.Response:
    return await client.post(
        "/api/v1/parts/import",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _rezip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_export_then_import_round_trips_the_part(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _extruded_part(client, "Bracket")
            data = await _export(client, part_id)
            assert await _export(client, part_id) == data  # same part, same bytes

            members = _members(data)
            assert list(members) == ["manifest.json", "tree.json", "cache/body.step"]
            manifest = json.loads(members["manifest.json"])
            assert manifest["document_id"] == part_id
            assert manifest["cache"]["properties"]["volume_mm3"] == pytest.approx(
                10_000.0, abs=ROUNDTRIP_TOL
            )
            assert members["cache/body.step"].startswith(b"ISO-10303-21")

            response = await _import(client, data)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["warnings"] == []
            copy = body["part"]
            assert copy["name"] == "Bracket copy"  # same install: ids re-minted
            assert copy["id"] != part_id
            assert await _volume(client, copy["id"]) == pytest.approx(
                manifest["cache"]["properties"]["volume_mm3"], abs=ROUNDTRIP_TOL
            )
            # The copy's own tree is the original's, ids aside.
            again = json.loads(_members(await _export(client, copy["id"]))["tree.json"])
            original = json.loads(members["tree.json"])
            for tree in (again, original):
                for feature in tree["features"]:
                    feature.pop("id")
                    feature["params"].pop("profile", None)
                tree.pop("name")
            assert again == original

            second = await _import(client, data)
            assert second.status_code == 201, second.text
            assert second.json()["part"]["name"] == "Bracket copy 2"

    asyncio.run(scenario())


def test_an_import_feature_travels_as_a_blob(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id: str = (
                await client.post("/api/v1/parts", json={"name": "Imported"})
            ).json()["id"]
            step = export_step_bytes(Solid.make_box(10, 20, 30))
            uploaded = await client.post(
                f"/api/v1/parts/{part_id}/features/import",
                params={"expected_tree_version": 0},
                content=step,
            )
            assert uploaded.status_code == 201, uploaded.text

            members = _members(await _export(client, part_id))
            digest = sha256_hex(step)
            assert members[f"blobs/sha256-{digest}.step"] == step
            tree = json.loads(members["tree.json"])
            assert tree["features"][0]["params"]["data"] == (
                f"loft-blob:sha256:{digest}"
            )

            response = await _import(client, _rezip(members))
            assert response.status_code == 201, response.text
            assert response.json()["warnings"] == []
            copy_id = response.json()["part"]["id"]
            assert await _volume(client, copy_id) == pytest.approx(
                6000.0, abs=ROUNDTRIP_TOL
            )
            features = (await client.get(f"/api/v1/parts/{copy_id}/features")).json()
            assert features["features"][0]["feature"]["params"]["data"] == (
                step.decode()
            )

    asyncio.run(scenario())


def test_a_hand_edited_tree_imports_with_a_warning(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _extruded_part(client, "Plate")
            members = _members(await _export(client, part_id))
            tree = json.loads(members["tree.json"])
            tree["features"][1]["params"]["distance_mm"] = 20.0
            members["tree.json"] = canonical_json(tree)

            response = await _import(client, _rezip(members))
            assert response.status_code == 201, response.text
            assert [w["code"] for w in response.json()["warnings"]] == [
                "loft_tree_edited"
            ]
            copy_id = response.json()["part"]["id"]
            assert await _volume(client, copy_id) == pytest.approx(
                20_000.0, abs=ROUNDTRIP_TOL
            )

    asyncio.run(scenario())


def test_refusals_create_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _extruded_part(client, "Plate")
            members = _members(await _export(client, part_id))

            newer = dict(members)
            manifest = json.loads(newer["manifest.json"])
            manifest["format_version"] = "2.0"
            newer["manifest.json"] = canonical_json(manifest)
            response = await _import(client, _rezip(newer))
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == "loft_format_too_new"

            too_new = dict(members)
            tree = json.loads(too_new["tree.json"])
            tree["features"][1]["param_version"] = 2
            too_new["tree.json"] = canonical_json(tree)
            response = await _import(client, _rezip(too_new))
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == "loft_feature_too_new"
            assert response.json()["error"]["details"]["feature_name"] == "Extrude1"

            response = await _import(
                client, b"\0" * (loft_file.MAX_LOFT_UPLOAD_BYTES + 1)
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "loft_too_large"

            response = await _import(client, b"not a zip")
            assert response.json()["error"]["code"] == "loft_not_zip"

            parts = (await client.get("/api/v1/parts")).json()["parts"]
            assert [p["name"] for p in parts] == ["Plate"]

            anonymous = await client.post(
                "/api/v1/parts/import",
                content=_rezip(members),
                headers={"Authorization": ""},
            )
            assert anonymous.status_code == 401
            foreign = await client.get(
                f"/api/v1/parts/{part_id}/export.loft", headers={"Authorization": ""}
            )
            assert foreign.status_code == 401

    asyncio.run(scenario())


async def _set_distance(client: httpx.AsyncClient, part_id: str, mm: float) -> None:
    tree = (await client.get(f"/api/v1/parts/{part_id}/features")).json()
    extrude = tree["features"][1]
    response = await client.patch(
        f"/api/v1/parts/{part_id}/features/{extrude['id']}",
        json={
            "feature": {
                **extrude["feature"],
                "params": {**extrude["feature"]["params"], "distance_mm": mm},
            },
            "expected_tree_version": tree["tree_version"],
        },
    )
    assert response.status_code == 200, response.text


def test_named_versions_save_restore_and_travel_in_the_loft(tmp_path: Path) -> None:
    """LOFT-VERSIONS end to end: save, list, restore (undoable, rebuilt to the
    version's volume), owner-scoped, and carried through export -> import with
    their numbers; a format 1.0 reader's view (no versions/) still imports."""

    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part_id = await _extruded_part(client, "Bracket")
            base = f"/api/v1/parts/{part_id}"
            saved = await client.post(
                f"{base}/versions",
                json={"name": "Rev A", "message": "10 mm", "author": "Ada"},
            )
            assert saved.status_code == 201, saved.text
            assert saved.json()["seq"] == 1
            await _set_distance(client, part_id, 20.0)
            assert (
                await client.post(f"{base}/versions", json={"name": "Rev B"})
            ).json()["seq"] == 2
            listed = (await client.get(f"{base}/versions")).json()["versions"]
            assert [(v["seq"], v["author"]) for v in listed] == [(2, None), (1, "Ada")]
            assert "loft@example.com" not in json.dumps(listed)
            assert await _volume(client, part_id) == pytest.approx(
                20_000.0, abs=ROUNDTRIP_TOL
            )

            tree = (await client.get(f"{base}/features")).json()
            restored = await client.post(
                f"{base}/versions/1/restore",
                json={"expected_tree_version": tree["tree_version"]},
            )
            assert restored.status_code == 200, restored.text
            assert restored.json()["can_undo"] is True
            assert await _volume(client, part_id) == pytest.approx(
                10_000.0, abs=ROUNDTRIP_TOL
            )
            undone = await client.post(
                f"{base}/undo",
                json={"expected_tree_version": restored.json()["tree_version"]},
            )
            assert undone.status_code == 200, undone.text
            assert await _volume(client, part_id) == pytest.approx(
                20_000.0, abs=ROUNDTRIP_TOL
            )

            data = await _export(client, part_id)
            assert await _export(client, part_id) == data
            members = _members(data)
            assert list(members) == [
                "manifest.json",
                "tree.json",
                "versions/index.json",
                "versions/1.tree.json",
                "versions/2.tree.json",
                "cache/body.step",
            ]
            assert json.loads(members["manifest.json"])["format_version"] == "1.1"
            index = json.loads(members["versions/index.json"])
            assert "loft@example.com" not in members["versions/index.json"].decode()
            assert [v["name"] for v in index["versions"]] == ["Rev A", "Rev B"]

            response = await _import(client, data)
            assert response.status_code == 201, response.text
            assert response.json()["warnings"] == []
            copy_id = response.json()["part"]["id"]
            copied = (await client.get(f"/api/v1/parts/{copy_id}/versions")).json()
            assert [(v["seq"], v["name"]) for v in copied["versions"]] == [
                (2, "Rev B"),
                (1, "Rev A"),
            ]
            copy_tree = (await client.get(f"/api/v1/parts/{copy_id}/features")).json()
            restored = await client.post(
                f"/api/v1/parts/{copy_id}/versions/1/restore",
                json={"expected_tree_version": copy_tree["tree_version"]},
            )
            assert restored.status_code == 200, restored.text
            assert await _volume(client, copy_id) == pytest.approx(
                10_000.0, abs=ROUNDTRIP_TOL
            )

            # What a format 1.0 Loft sees: the same file without versions/.
            older = {
                name: content
                for name, content in members.items()
                if not name.startswith("versions/")
            }
            manifest = json.loads(older["manifest.json"])
            manifest["format_version"] = "1.0"
            manifest["members"] = {
                name: digest
                for name, digest in manifest["members"].items()
                if not name.startswith("versions/")
            }
            older["manifest.json"] = canonical_json(manifest)
            response = await _import(client, _rezip(older))
            assert response.status_code == 201, response.text
            old_id = response.json()["part"]["id"]
            assert (await client.get(f"/api/v1/parts/{old_id}/versions")).json() == {
                "versions": []
            }

            # Another account sees none of it.
            other = await client.post(
                "/api/v1/auth/register",
                json={"email": "other@example.com", "password": "hunter2-passphrase"},
            )
            headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
            for method, path, body in [
                ("POST", f"{base}/versions", {"name": "Mine"}),
                ("GET", f"{base}/versions", None),
                ("POST", f"{base}/versions/1/restore", {"expected_tree_version": 0}),
            ]:
                foreign = await client.request(method, path, json=body, headers=headers)
                assert foreign.status_code == 404, (path, foreign.text)
            anonymous = await client.get(
                f"{base}/versions", headers={"Authorization": ""}
            )
            assert anonymous.status_code == 401
            bad_seq = await client.post(
                f"{base}/versions/0/restore", json={"expected_tree_version": 0}
            )
            assert bad_seq.status_code == 422

    asyncio.run(scenario())
