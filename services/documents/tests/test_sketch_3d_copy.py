"""A 3D sketch survives Duplicate and ``.loft`` import detached (SKETCH-3D).

The lesson from WALL and HOLE: every id a feature stores must follow a copy.
A 3D sketch stores ids in its snaps (an earlier sketch's ``FeatureRef``, a
model vertex's ``EdgeSubshapeRef`` and its ``topo_name``), and a Pipe on its
lines stores the 3D sketch's id. A copy that kept any of them would be wired
back into the original. The sketch-local point and line ids are not document
ids and come through verbatim.
"""

import asyncio
import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000003d"


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url))
    with TestClient(build_app(DocumentsSettings(postgres_url=url))) as test_client:
        yield test_client


HEADERS = {PRINCIPAL_HEADER: OWNER}


def _add(
    client: TestClient, part: str, name: str, feature: dict[str, Any], v: int
) -> str:
    response = client.post(
        f"/api/v1/parts/{part}/features",
        json={"name": name, "feature": feature, "expected_tree_version": v},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _vec(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _seeded(client: TestClient) -> dict[str, str]:
    """Sketch1 (a square) <- Extrude1 <- 3DSketch1 (snapped to a Sketch1 point
    and an Extrude1 vertex) <- Pipe1 on its line."""
    response = client.post("/api/v1/parts", json={"name": "Frame"}, headers=HEADERS)
    assert response.status_code == 201, response.text
    part: str = response.json()["id"]
    square = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0)]
    sketch = _add(
        client,
        part,
        "Sketch1",
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": f"e{i}",
                        "kind": "line",
                        "start": {"x": a[0], "y": a[1]},
                        "end": {"x": b[0], "y": b[1]},
                    }
                    for i, (a, b) in enumerate(itertools.pairwise(square))
                ],
                "constraints": [],
            },
        },
        0,
    )
    extrude = _add(
        client,
        part,
        "Extrude1",
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch},
                "distance_mm": 10.0,
                "operation": "add",
            },
        },
        1,
    )
    vertex = {
        "kind": "vertex",
        "end": "b",
        "edge": {
            "kind": "subshape",
            "feature_id": extrude,
            "subshape_type": "edge",
            "selector": {
                "selector_version": 1,
                "signature": {
                    "curve": "line",
                    "end_a": _vec(40, 20, 0),
                    "end_b": _vec(40, 20, 10),
                    "midpoint": _vec(40, 20, 5),
                    "length_mm": 10.0,
                    "topo_name": f'["{extrude}:side:e1","{extrude}:side:e2"]',
                },
            },
        },
    }
    sketch_3d = _add(
        client,
        part,
        "3DSketch1",
        {
            "type": "sketch_3d",
            "version": 1,
            "params": {
                "entities": [
                    {
                        "id": "p1",
                        "kind": "point",
                        "position": _vec(40, 0, 0),
                        "snap": {
                            "kind": "sketch_point",
                            "sketch": {"kind": "feature", "feature_id": sketch},
                            "entity": "e0",
                            "point": "end",
                        },
                    },
                    {
                        "id": "p2",
                        "kind": "point",
                        "position": _vec(40, 20, 10),
                        "snap": vertex,
                    },
                    {"id": "p3", "kind": "point", "position": _vec(0, 60, 80)},
                    {"id": "l1", "kind": "line", "start": "p2", "end": "p3"},
                ],
                "constraints": [{"kind": "length", "line": "l1", "value_mm": 100.0}],
            },
        },
        2,
    )
    pipe = _add(
        client,
        part,
        "Pipe1",
        {
            "type": "pipe",
            "version": 1,
            "params": {
                "path": [
                    {
                        "kind": "sketch_curve",
                        "sketch": {"kind": "feature", "feature_id": sketch_3d},
                        "entity": "l1",
                    }
                ],
                "outer_diameter_mm": 10.0,
                "operation": "add",
            },
        },
        3,
    )
    return {
        "part": part,
        "sketch": sketch,
        "extrude": extrude,
        "sketch_3d": sketch_3d,
        "pipe": pipe,
    }


def _features(client: TestClient, part: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/parts/{part}/features", headers=HEADERS)
    assert response.status_code == 200, response.text
    features: list[dict[str, Any]] = response.json()["features"]
    return features


def _assert_detached(
    copied: list[dict[str, Any]], original: list[dict[str, Any]], ids: dict[str, str]
) -> None:
    sketch, extrude, sketch_3d, pipe = copied
    assert {f["id"] for f in copied}.isdisjoint(ids.values())
    params = sketch_3d["feature"]["params"]
    snap_sketch = params["entities"][0]["snap"]["sketch"]["feature_id"]
    edge = params["entities"][1]["snap"]["edge"]
    assert snap_sketch == sketch["id"]
    assert edge["feature_id"] == extrude["id"]
    topo = edge["selector"]["signature"]["topo_name"]
    assert topo == f'["{extrude["id"]}:side:e1","{extrude["id"]}:side:e2"]'
    path = pipe["feature"]["params"]["path"][0]
    assert path["sketch"]["feature_id"] == sketch_3d["id"]
    # Sketch-local ids and every number come through verbatim.
    want = original[2]["feature"]["params"]
    assert [e["id"] for e in params["entities"]] == ["p1", "p2", "p3", "l1"]
    assert params["constraints"] == want["constraints"]
    assert params["entities"][2] == want["entities"][2]
    assert path["entity"] == "l1"


def test_duplicate_rewires_every_id_in_a_3d_sketch_and_its_pipe(
    client: TestClient,
) -> None:
    ids = _seeded(client)
    original = _features(client, ids["part"])
    response = client.post(f"/api/v1/parts/{ids['part']}/duplicate", headers=HEADERS)
    assert response.status_code == 201, response.text
    _assert_detached(_features(client, response.json()["id"]), original, ids)
    # The copy's dependency edges are its own: the snapped sketch is guarded.
    copy = response.json()["id"]
    copied = _features(client, copy)
    refused = client.delete(
        f"/api/v1/parts/{copy}/features/{copied[2]['id']}",
        params={"expected_tree_version": 0},
        headers=HEADERS,
    )
    assert refused.status_code == 409, refused.text
    dependents = refused.json()["error"]["details"]["dependents"]
    assert [d["name"] for d in dependents] == ["Pipe1"]
    assert _features(client, ids["part"]) == original


def test_loft_import_round_trips_a_3d_sketch_detached(client: TestClient) -> None:
    ids = _seeded(client)
    original = _features(client, ids["part"])
    tree = client.get(f"/api/v1/parts/{ids['part']}/loft-tree", headers=HEADERS)
    assert tree.status_code == 200, tree.text
    response = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": ids["part"], "tree": tree.json()},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    _assert_detached(_features(client, response.json()["id"]), original, ids)
