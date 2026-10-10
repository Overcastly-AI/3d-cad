"""A parametric part reaches geometry as numbers on EVERY path (RESEARCH §20).

The evaluation request is not the only way a stored tree reaches geometry:
the web builds its measure and pick (overlay) requests from ``GET
/features`` (apps/web/src/measure/geometry.ts ``buildEvaluateTree``), and
the reference backfill builds its own from the stored rows
(:mod:`documents.ref_backfill`). Before the stored form was normalized, a
sketch dimension ``= W`` reached geometry as the text ``W`` on those paths and
failed ``sketch_invalid: unknown dimension name 'W'``.

Real documents and geometry apps, in process (no ports): the part is a
rectangle whose width dimension is ``= W`` (written as the sketcher writes
it, in the dimension's own ``expression``), extruded ``= D``.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import httpx2 as httpx
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"
OWNER = "6f3f6b64-0000-4000-8000-0000000001c7"
W = 60.0


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.router.lifespan_context(app):
        yield


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
    """A fully constrained 40 x 25 drawing whose width is ``= W``."""
    return {
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
                    "expression": "W",
                },
                {"kind": "distance", "entity": "e2", "value_mm": 25.0},
            ],
        },
    }


def _extrude(sketch_id: str) -> Any:
    return {
        "type": "extrude",
        "version": 1,
        "expressions": {"/distance_mm": "D"},
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": 1.0,
            "operation": "add",
            "direction": "normal",
        },
    }


def _fillet(extrude_id: str) -> Any:
    """A round on the box's vertical edge at the origin, picked without a
    history name, so the backfill has something to name."""
    signature = {
        "curve": "line",
        "end_a": {"x": 0, "y": 0, "z": 0},
        "end_b": {"x": 0, "y": 0, "z": 10},
        "midpoint": {"x": 0, "y": 0, "z": 5},
        "length_mm": 10.0,
    }
    return {
        "type": "fillet",
        "version": 1,
        "params": {
            "edges": {
                "kind": "edges",
                "refs": [
                    {
                        "kind": "subshape",
                        "feature_id": extrude_id,
                        "subshape_type": "edge",
                        "selector": {"selector_version": 1, "signature": signature},
                    }
                ],
            },
            "radius_mm": 1.0,
        },
    }


def _parameters(version: int) -> Any:
    return {
        "expected_tree_version": version,
        "parameters": [
            {"id": str(uuid.uuid4()), "name": n, "expression": e, "unit": "length"}
            for n, e in (("W", str(W)), ("D", "10"))
        ],
    }


def _no_parameter_text(feature: Any) -> None:
    """What a web client builds a geometry request from: params that geometry
    can read without the part's parameter table."""
    for constraint in feature["params"].get("constraints", []):
        assert constraint.get("expression") in (None,), constraint


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


def test_measure_and_pick_requests_built_from_the_tree_solve(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part = (await client.post("/api/v1/parts", json={"name": "P"})).json()
            base = f"/api/v1/parts/{part['id']}"
            assert (
                await client.put(f"{base}/parameters", json=_parameters(0))
            ).status_code == 200
            made = await client.post(
                f"{base}/features",
                json={"name": "S", "feature": _sketch(), "expected_tree_version": 1},
            )
            assert made.status_code == 201, made.text
            sketch_id = made.json()["feature"]["id"]
            made = await client.post(
                f"{base}/features",
                json={
                    "name": "E",
                    "feature": _extrude(sketch_id),
                    "expected_tree_version": 2,
                },
            )
            assert made.status_code == 201, made.text

            tree = (await client.get(f"{base}/features")).json()
            sketch = tree["features"][0]["feature"]
            _no_parameter_text(sketch)
            # The formula is kept, in the stored form: at the value's pointer.
            assert sketch["expressions"] == {"/constraints/9/value_mm": "W"}
            assert sketch["params"]["constraints"][9]["value_mm"] == W
            # apps/web/src/measure/geometry.ts buildEvaluateTree, verbatim.
            request = {
                "part_id": tree["part_id"],
                "tree_version": tree["tree_version"],
                "linear_deflection": 0.1,
                "features": [
                    {"id": f["id"], "feature": f["feature"]} for f in tree["features"]
                ],
            }
            overlay = await client.post(
                "/api/v1/geometry/overlay", json={"tree": request}
            )
            assert overlay.status_code == 200, overlay.text
            edges = overlay.json()["edges"]
            assert max(v["x"] for v in overlay.json()["vertices"]) == W
            corner = next(
                i
                for i, e in enumerate(edges)
                if e["start"]["x"] == e["end"]["x"] == W
                and e["start"]["y"] == e["end"]["y"] == 0.0
            )
            measured = await client.post(
                "/api/v1/geometry/measure",
                json={
                    "a": {"kind": "point", "position": {"x": 0, "y": 0, "z": 0}},
                    "b": {"kind": "edge", "index": corner},
                    "tree": request,
                },
            )
            assert measured.status_code == 200, measured.text
            assert abs(measured.json()["distance"] - W) < 1e-9

    asyncio.run(scenario())


@contextlib.contextmanager
def _documents_and_geometry(
    tmp_path: Path,
) -> Generator[tuple[TestClient, TestClient]]:
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url, DocumentsBase))
    documents_app = build_documents_app(DocumentsSettings(postgres_url=url))
    geometry_app = build_geometry_app(GeometrySettings(s3_url=None))
    with TestClient(documents_app) as documents, TestClient(geometry_app) as geometry:
        documents.headers[PRINCIPAL_HEADER] = OWNER
        yield documents, geometry


def test_the_reference_backfill_request_builds_in_geometry(tmp_path: Path) -> None:
    with _documents_and_geometry(tmp_path) as (documents, geometry):
        part = documents.post("/api/v1/parts", json={"name": "P"}).json()
        base = f"/api/v1/parts/{part['id']}"
        assert (
            documents.put(f"{base}/parameters", json=_parameters(0)).status_code == 200
        )
        version = 1
        ids: list[str] = []
        for name in ("S", "E", "F"):
            if name == "S":
                feature = _sketch()
            elif name == "E":
                feature = _extrude(ids[-1])
            else:
                feature = _fillet(ids[-1])
            made = documents.post(
                f"{base}/features",
                json={
                    "name": name,
                    "feature": feature,
                    "expected_tree_version": version,
                },
            )
            assert made.status_code == 201, made.text
            ids.append(made.json()["feature"]["id"])
            version = made.json()["tree_version"]

        need = documents.get(f"{base}/ref-names-request")
        assert need.status_code == 200, need.text
        assert need.json()["needed"] is True
        request = need.json()["request"]
        _no_parameter_text(request["features"][0]["feature"])
        assert "expressions" not in request["features"][1]["feature"]
        assert request["features"][1]["feature"]["params"]["distance_mm"] == 10.0

        report = geometry.post("/api/v1/ref-names", json=request)
        assert report.status_code == 200, report.text
        [outcome] = report.json()["outcomes"]
        assert outcome["outcome"] == "named", outcome
