"""The extrude twist is deprecated: read-only legacy (loft_wire.legacy_twist).

Creating a twisted extrude, or setting or changing the twist on a PATCH, is a
422 ``extrude_twist_deprecated`` pointing to Sweep. A stored row that already
carries a twist (written before the deprecation; seeded here straight into the
table) still reads back verbatim, and a PATCH that carries its twist through
unchanged, or removes it, is allowed: no user's part changes or breaks.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents.db import Feature
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.legacy_twist import EXTRUDE_TWIST_DEPRECATED_MESSAGE
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn, enable_sqlite_foreign_keys
from sqlalchemy.ext.asyncio import create_async_engine

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-00000000000a"}

SQUARE = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {"id": "c1", "kind": "circle", "center": {"x": 0, "y": 0}, "radius": 5.0}
    ],
    "constraints": [],
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _extrude(sketch_id: str, **twist: Any) -> dict[str, Any]:
    params = {
        "profile": {"kind": "feature", "feature_id": sketch_id},
        "distance_mm": 10.0,
        "operation": "add",
        **twist,
    }
    return {"type": "extrude", "version": 1, "params": params}


def _post(client: TestClient, part_id: str, feature: dict[str, Any], v: int) -> Any:
    return client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "F", "feature": feature, "expected_tree_version": v},
        headers=HEADERS,
    )


def _patch(client: TestClient, part_id: str, fid: str, body: dict[str, Any]) -> Any:
    return client.patch(
        f"/api/v1/parts/{part_id}/features/{fid}", json=body, headers=HEADERS
    )


def _part_with_extrude(client: TestClient) -> tuple[str, str, str]:
    part = client.post("/api/v1/parts", json={"name": "p"}, headers=HEADERS)
    part_id: str = part.json()["id"]
    sketch = _post(
        client, part_id, {"type": "sketch", "version": 1, "params": SQUARE}, 0
    )
    sketch_id: str = sketch.json()["feature"]["id"]
    extrude = _post(client, part_id, _extrude(sketch_id), 1)
    assert extrude.status_code == 201, extrude.text
    return part_id, sketch_id, extrude.json()["feature"]["id"]


def _assert_refused(response: Any) -> None:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "extrude_twist_deprecated"
    assert error["message"] == EXTRUDE_TWIST_DEPRECATED_MESSAGE
    assert "Sweep" in error["message"]


def _seed_legacy_twist(url: str, feature_id: str, params: dict[str, Any]) -> None:
    """Write a twist into a stored row, as a pre-deprecation save did."""

    async def write() -> None:
        engine = create_async_engine(async_dsn(url))
        enable_sqlite_foreign_keys(engine)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(Feature)
                    .where(Feature.id == uuid.UUID(feature_id))
                    .values(params=params)
                )
        finally:
            await engine.dispose()

    asyncio.run(write())


def test_creating_a_twisted_extrude_is_refused(client: TestClient) -> None:
    part_id, sketch_id, _ = _part_with_extrude(client)
    _assert_refused(
        _post(client, part_id, _extrude(sketch_id, twist_angle_deg=30.0), 2)
    )
    # Every spelling of "no twist" is no twist, so it is not refused.
    assert (
        _post(client, part_id, _extrude(sketch_id, twist_angle_deg=0.0), 2).status_code
        == 201
    )


def test_patch_cannot_add_a_twist(client: TestClient) -> None:
    part_id, sketch_id, extrude_id = _part_with_extrude(client)
    body = {
        "expected_tree_version": 2,
        "feature": _extrude(sketch_id, twist_angle_deg=30.0),
    }
    _assert_refused(_patch(client, part_id, extrude_id, body))


def test_a_stored_legacy_twist_loads_keeps_and_cannot_change(
    client: TestClient, any_db_url: str
) -> None:
    part_id, sketch_id, extrude_id = _part_with_extrude(client)
    legacy = _extrude(
        sketch_id, twist_angle_deg=30.0, twist_center={"x": 1.0, "y": 2.0}
    )
    _seed_legacy_twist(any_db_url, extrude_id, legacy["params"])

    stored = client.get(
        f"/api/v1/parts/{part_id}/features/{extrude_id}", headers=HEADERS
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["feature"]["params"]["twist_angle_deg"] == 30.0
    assert stored.json()["feature"]["params"]["twist_center"] == {"x": 1.0, "y": 2.0}

    # Changing the angle, or only the axis, is refused; nothing is written.
    changed = _extrude(
        sketch_id, twist_angle_deg=45.0, twist_center={"x": 1.0, "y": 2.0}
    )
    _assert_refused(
        _patch(
            client,
            part_id,
            extrude_id,
            {"expected_tree_version": 2, "feature": changed},
        )
    )
    moved = _extrude(sketch_id, twist_angle_deg=30.0)
    _assert_refused(
        _patch(
            client, part_id, extrude_id, {"expected_tree_version": 2, "feature": moved}
        )
    )

    # A distance edit that carries the twist through unchanged is allowed.
    kept = _extrude(sketch_id, twist_angle_deg=30.0, twist_center={"x": 1.0, "y": 2.0})
    kept["params"]["distance_mm"] = 12.0
    response = _patch(
        client, part_id, extrude_id, {"expected_tree_version": 2, "feature": kept}
    )
    assert response.status_code == 200, response.text
    params = response.json()["feature"]["feature"]["params"]
    assert params["twist_angle_deg"] == 30.0
    assert params["distance_mm"] == 12.0

    # A rename leaves the params alone, and removing the twist is allowed.
    renamed = _patch(
        client, part_id, extrude_id, {"expected_tree_version": 3, "name": "Old"}
    )
    assert renamed.status_code == 200, renamed.text
    straight = _patch(
        client,
        part_id,
        extrude_id,
        {"expected_tree_version": 4, "feature": _extrude(sketch_id)},
    )
    assert straight.status_code == 200, straight.text
    assert "twist_angle_deg" not in straight.json()["feature"]["feature"]["params"]


def test_a_legacy_twist_about_the_origin_saved_without_its_axis_is_unchanged(
    client: TestClient, any_db_url: str
) -> None:
    """An explicit (0, 0) axis and an absent one are the same axis."""
    part_id, sketch_id, extrude_id = _part_with_extrude(client)
    origin = {"x": 0.0, "y": 0.0}
    legacy = _extrude(sketch_id, twist_angle_deg=30.0, twist_center=origin)
    _seed_legacy_twist(any_db_url, extrude_id, legacy["params"])

    absent = _extrude(sketch_id, twist_angle_deg=30.0)
    response = _patch(
        client, part_id, extrude_id, {"expected_tree_version": 2, "feature": absent}
    )
    assert response.status_code == 200, response.text
    assert response.json()["feature"]["feature"]["params"]["twist_angle_deg"] == 30.0
