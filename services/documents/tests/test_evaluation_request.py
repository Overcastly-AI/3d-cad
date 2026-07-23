"""documents evaluation-request — the design §4.2 list documents hands over.

``GET /api/v1/parts/{part_id}/evaluation-request`` must serve exactly what
the geometry service is allowed to see: the ordered feature list with the
rollback bar already applied (§3 — geometry never learns rollback exists)
and every params blob upcast to its current version (§1.4 — nothing but
current-version params ever leaves the repository layer).

Same dialect posture as tests/test_features.py: SQLite always, real scratch
PostgreSQL (actual migrations) when server binaries are available.
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
from py_kit.db import async_dsn
from py_kit.schemas.features import (
    FEATURE_REGISTRY,
    EvaluateTreeRequest,
    JsonObject,
    SketchFeature,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"

#: A minimal valid sketch body (one line, one anchor) — this suite tests the
#: documents-side list assembly, not solving.
SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        },
    ],
    "constraints": [
        {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
    ],
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _create_part(client: TestClient) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": "demo-block"}, headers=_headers()
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_sketch(client: TestClient, part_id: str, name: str, version: int) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
            "expected_tree_version": version,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _evaluation_request(client: TestClient, part_id: str) -> EvaluateTreeRequest:
    response = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=_headers()
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeRequest.model_validate(response.json())


def test_serves_the_ordered_current_tree(client: TestClient) -> None:
    """Full tree (bar at the tip): every feature, evaluation order, validated
    current-version envelopes, tree_version as the correlation key."""
    part_id = _create_part(client)
    first = _create_sketch(client, part_id, "Sketch1", 0)
    second = _create_sketch(client, part_id, "Sketch2", 1)

    request = _evaluation_request(client, part_id)

    assert request.part_id == uuid.UUID(part_id)
    assert request.tree_version == 2
    assert [str(item.id) for item in request.features] == [first, second]
    for item in request.features:
        assert isinstance(item.feature, SketchFeature)
        assert item.feature.version == 1


def test_rollback_bar_is_applied_before_handover(client: TestClient) -> None:
    """§3/§4.2: only the prefix up to and including the bar is handed over —
    geometry receives a rolled-back tree simply as a shorter list."""
    part_id = _create_part(client)
    first = _create_sketch(client, part_id, "Sketch1", 0)
    second = _create_sketch(client, part_id, "Sketch2", 1)

    response = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 2, "rollback_feature_id": first},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text

    rolled_back = _evaluation_request(client, part_id)
    assert [str(item.id) for item in rolled_back.features] == [first]
    assert rolled_back.tree_version == 3  # the bar move bumped it (§3)

    response = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 3, "rollback_feature_id": None},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert [str(item.id) for item in _evaluation_request(client, part_id).features] == [
        first,
        second,
    ]


@pytest.fixture
def sketch_v0_upcast() -> Iterator[None]:
    """Register a synthetic sketch v0→v1 upcast (pretend v0 lacked
    ``constraints``), removed again after the test — the module registry is
    process-global state."""

    def upcast(params: JsonObject) -> JsonObject:
        return {**params, "constraints": []}

    FEATURE_REGISTRY.register_upcast("sketch", 0, upcast)
    FEATURE_REGISTRY.validate_chains()
    try:
        yield
    finally:
        FEATURE_REGISTRY._upcasts.pop(("sketch", 0))  # pyright: ignore[reportPrivateUsage]


def _rewrite_row_to_v0(url: str, feature_id: str) -> None:
    """Downgrade a stored row to the synthetic v0 shape, bypassing the API
    (which can only write current versions) — this is what an old row left
    behind by a param_version bump looks like (§1.4)."""
    v0_params = {k: v for k, v in SKETCH_PARAMS.items() if k != "constraints"}

    async def run() -> None:
        engine = create_async_engine(async_dsn(url))
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(Feature)
                    .where(Feature.id == uuid.UUID(feature_id))
                    .values(param_version=0, params=v0_params)
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_old_param_versions_are_upcast_on_read(
    client: TestClient, any_db_url: str, sketch_v0_upcast: None
) -> None:
    """§1.4: geometry only ever sees current-version params — a stored v0 row
    leaves documents as a validated v1 envelope."""
    part_id = _create_part(client)
    feature_id = _create_sketch(client, part_id, "Sketch1", 0)
    _rewrite_row_to_v0(any_db_url, feature_id)

    request = _evaluation_request(client, part_id)

    (item,) = request.features
    assert isinstance(item.feature, SketchFeature)
    assert item.feature.version == 1
    assert item.feature.params.constraints == []  # filled by the upcast
    assert [entity.id for entity in item.feature.params.entities] == ["e1"]


def test_created_suppressed_feature_carries_suppressed_to_geometry(
    client: TestClient,
) -> None:
    """The load-bearing end-to-end proof: a feature stored with suppressed=true
    reaches geometry as a suppressed envelope in the evaluation-request (without
    this the whole feature is a dead capability — feature-tree.md §4.3a)."""
    part_id = _create_part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Sketch1",
            "feature": {
                "type": "sketch",
                "version": 1,
                "suppressed": True,
                "params": SKETCH_PARAMS,
            },
            "expected_tree_version": 0,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text

    (item,) = _evaluation_request(client, part_id).features
    assert isinstance(item.feature, SketchFeature)
    assert item.feature.suppressed is True


def test_suppress_toggle_marks_the_evaluation_request(client: TestClient) -> None:
    """Toggling a stored feature suppressed flips the flag geometry receives on
    the evaluation-request envelope (geometry-then-skips is a slice-1 concern)."""
    part_id = _create_part(client)
    feature_id = _create_sketch(client, part_id, "Sketch1", 0)

    assert _evaluation_request(client, part_id).features[0].feature.suppressed is False

    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{feature_id}/suppress",
        json={"expected_tree_version": 1, "suppressed": True},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text

    (item,) = _evaluation_request(client, part_id).features
    assert item.feature.suppressed is True


def test_foreign_and_unknown_parts_are_a_uniform_404(client: TestClient) -> None:
    part_id = _create_part(client)
    for target, headers in (
        (part_id, {PRINCIPAL_HEADER: OTHER}),  # foreign part
        (str(uuid.uuid4()), _headers()),  # unknown part
    ):
        response = client.get(
            f"/api/v1/parts/{target}/evaluation-request", headers=headers
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "part_not_found"


def test_missing_principal_is_401(client: TestClient) -> None:
    response = client.get(f"/api/v1/parts/{uuid.uuid4()}/evaluation-request")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_principal"
