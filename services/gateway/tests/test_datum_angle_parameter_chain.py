"""A plane at an angle whose angle is a part parameter (DATUM-PLANE-ANGLE).

Real gateway, documents and geometry apps in process (no ports, scratch
SQLite). The part: an angle parameter ``A = 25``; a plane at an angle about
the origin Y axis from XY with ``expressions={"/angle_deg": "A"}``; a circle of
radius 10 at the plane's origin; an extrude of 20 along the plane normal.

Hand values (RESEARCH §18): the XY normal +Z turned ``a`` right-handed about
+Y is ``n = (sin a, 0, cos a)``, so the cylinder's centroid is ``10 n``:

* A = 25: (4.226183, 0, 9.063078);
* A = 40: (6.427876, 0, 7.660444);

and the volume is pi 10^2 20 = 6283.185 at every angle. Editing the parameter
moves the plane, the sketch on it and the solid; undo puts them back.
"""

import asyncio
import contextlib
import math
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
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"
VOLUME = math.pi * 10.0**2 * 20.0


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


def _datum() -> Any:
    return {
        "type": "datum",
        "version": 1,
        "expressions": {"/angle_deg": "A"},
        "params": {
            "kind": "angle",
            "line": {"kind": "origin_axis", "axis": "Y"},
            "reference": {"kind": "datum_plane", "plane": "XY"},
            "angle_deg": 0.0,
            "flip": False,
        },
    }


def _sketch(datum_id: str) -> Any:
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "feature", "feature_id": datum_id},
            "entities": [
                {"id": "c", "kind": "circle", "center": {"x": 0, "y": 0}, "radius": 10}
            ],
            "constraints": [],
        },
    }


def _extrude(sketch_id: str) -> Any:
    return {
        "type": "extrude",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": 20.0,
            "operation": "add",
            "direction": "normal",
        },
    }


def _expected_centroid(angle_deg: float) -> tuple[float, float, float]:
    a = math.radians(angle_deg)
    return (10.0 * math.sin(a), 0.0, 10.0 * math.cos(a))


def test_the_angle_parameter_turns_the_plane_and_the_solid_on_it(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with _gateway(tmp_path) as client:
            part = (await client.post("/api/v1/parts", json={"name": "P"})).json()
            base = f"/api/v1/parts/{part['id']}"

            async def put_angle(expression: str, version: int) -> None:
                response = await client.put(
                    f"{base}/parameters",
                    json={
                        "expected_tree_version": version,
                        "parameters": [
                            {
                                "id": row_id,
                                "name": "A",
                                "expression": expression,
                                "unit": "angle",
                            }
                        ],
                    },
                )
                assert response.status_code == 200, response.text

            row_id = str(uuid.uuid4())
            await put_angle("25", 0)

            async def add(name: str, feature: Any, version: int) -> str:
                made = await client.post(
                    f"{base}/features",
                    json={
                        "name": name,
                        "feature": feature,
                        "expected_tree_version": version,
                    },
                )
                assert made.status_code == 201, made.text
                return made.json()["feature"]["id"]

            datum_id = await add("Plane", _datum(), 1)
            sketch_id = await add("S", _sketch(datum_id), 2)
            await add("E", _extrude(sketch_id), 3)

            async def evaluate(angle_deg: float) -> None:
                stored = (await client.get(f"{base}/features")).json()
                datum = stored["features"][0]["feature"]
                assert datum["expressions"] == {"/angle_deg": "A"}
                assert datum["params"]["angle_deg"] == angle_deg
                response = await client.post(f"{base}/evaluate")
                assert response.status_code == 200, response.text
                result = response.json()
                assert [f["status"] for f in result["features"]] == ["ok"] * 3
                props = result["properties"]
                assert abs(props["volume"] - VOLUME) < 1e-6 * VOLUME
                centroid = props["centroid"]
                got = (centroid["x"], centroid["y"], centroid["z"])
                for g, e in zip(got, _expected_centroid(angle_deg), strict=True):
                    assert abs(g - e) < 1e-6, (got, angle_deg)

            await evaluate(25.0)
            await put_angle("40", 4)
            await evaluate(40.0)

            undone = await client.post(
                f"{base}/undo", json={"expected_tree_version": 5}
            )
            assert undone.status_code == 200, undone.text
            await evaluate(25.0)

    asyncio.run(scenario())
