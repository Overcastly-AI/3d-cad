"""gateway.features — auth gating, principal + query forwarding, envelopes.

Same harness as tests/test_parts_proxy.py: the documents upstream is an
``httpx.MockTransport``; auth runs for real (register → bearer token) over
the SQLite test DB posture documented in tests/test_auth.py.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.features import (
    FeatureCreate,
    FeatureMutationResponse,
    FeatureResponse,
    FeatureSuppressRequest,
    FeatureTreeResponse,
    SketchFeature,
    UndoRedoRequest,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)

SKETCH_ENVELOPE: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [],
        "constraints": [],
    },
}


def _feature_response(part_id: uuid.UUID) -> FeatureResponse:
    return FeatureResponse(
        id=uuid.uuid4(),
        part_id=part_id,
        order_index=0,
        name="Sketch1",
        feature=SketchFeature.model_validate(SKETCH_ENVELOPE),
        rolled_back=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _tree(part_id: uuid.UUID, tree_version: int = 1) -> FeatureTreeResponse:
    return FeatureTreeResponse(
        part_id=part_id,
        tree_version=tree_version,
        rollback_feature_id=None,
        features=[_feature_response(part_id)],
        can_undo=False,
        can_redo=False,
    )


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/gateway.db"
    asyncio.run(_create_schema(url))
    return url


def make_client(db_url: str, handler: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://127.0.0.1:9",  # nothing listens; irrelevant here
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(settings, documents_transport=httpx.MockTransport(handler))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _echo_documents(seen: list[httpx.Request]) -> Handler:
    """A canned documents upstream for the feature routes."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        part_id = uuid.UUID(request.url.path.split("/")[4])
        if request.url.path.endswith(("/undo", "/redo")):
            body = UndoRedoRequest.model_validate_json(request.content)
            return httpx.Response(
                200,
                content=_tree(
                    part_id, body.expected_tree_version + 1
                ).model_dump_json(),
            )
        if request.method == "POST":
            body = FeatureCreate.model_validate_json(request.content)
            payload = FeatureMutationResponse(
                feature=_feature_response(part_id),
                tree_version=body.expected_tree_version + 1,
            )
            return httpx.Response(201, content=payload.model_dump_json())
        if request.method == "PATCH":
            payload = FeatureMutationResponse(
                feature=_feature_response(part_id), tree_version=2
            )
            return httpx.Response(200, content=payload.model_dump_json())
        if request.url.path.endswith("/features") or request.method in (
            "DELETE",
            "PUT",
        ):
            return httpx.Response(200, content=_tree(part_id).model_dump_json())
        return httpx.Response(200, content=_feature_response(part_id).model_dump_json())

    return handler


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


PART = uuid.uuid4()
FEATURE = uuid.uuid4()

CREATE_BODY = {
    "name": "Sketch1",
    "feature": SKETCH_ENVELOPE,
    "expected_tree_version": 0,
}


# --- auth gating -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", f"/api/v1/parts/{PART}/features", None),
        ("GET", f"/api/v1/parts/{PART}/features/{FEATURE}", None),
        ("POST", f"/api/v1/parts/{PART}/features", CREATE_BODY),
        (
            "PATCH",
            f"/api/v1/parts/{PART}/features/{FEATURE}",
            {"expected_tree_version": 0, "name": "x"},
        ),
        (
            "PATCH",
            f"/api/v1/parts/{PART}/features/{FEATURE}/suppress",
            {"expected_tree_version": 0, "suppressed": True},
        ),
        (
            "DELETE",
            f"/api/v1/parts/{PART}/features/{FEATURE}?expected_tree_version=0",
            None,
        ),
        (
            "PUT",
            f"/api/v1/parts/{PART}/features/order",
            {"expected_tree_version": 0, "order": []},
        ),
        (
            "PUT",
            f"/api/v1/parts/{PART}/rollback",
            {"expected_tree_version": 0, "rollback_feature_id": None},
        ),
        ("POST", f"/api/v1/parts/{PART}/undo", {"expected_tree_version": 0}),
        ("POST", f"/api/v1/parts/{PART}/redo", {"expected_tree_version": 0}),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str,
    seen: list[httpx.Request],
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


# --- forwarding ------------------------------------------------------------------


def test_create_feature_forwards_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(
            f"/api/v1/parts/{PART}/features", json=CREATE_BODY, headers=bearer
        )

    assert response.status_code == 201, response.text
    body = FeatureMutationResponse.model_validate(response.json())
    assert body.tree_version == 1
    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == f"/api/v1/parts/{PART}/features"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    parsed = FeatureCreate.model_validate_json(upstream.content)
    assert parsed.feature.type == "sketch"


def test_delete_feature_forwards_concurrency_query_param(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(
            f"/api/v1/parts/{PART}/features/{FEATURE}",
            params={"expected_tree_version": 7},
            headers=bearer,
        )

    assert response.status_code == 200
    FeatureTreeResponse.model_validate(response.json())
    [upstream] = seen
    assert upstream.url.path == f"/api/v1/parts/{PART}/features/{FEATURE}"
    assert upstream.url.params["expected_tree_version"] == "7"


def test_suppress_feature_forwards_principal_body_and_bump(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """PATCH .../suppress forwards the principal + toggle body to documents and
    surfaces the returned tree_version bump."""
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.patch(
            f"/api/v1/parts/{PART}/features/{FEATURE}/suppress",
            json={"expected_tree_version": 1, "suppressed": True},
            headers=bearer,
        )

    assert response.status_code == 200, response.text
    assert FeatureMutationResponse.model_validate(response.json()).tree_version == 2
    [upstream] = seen
    assert upstream.method == "PATCH"
    assert upstream.url.path == f"/api/v1/parts/{PART}/features/{FEATURE}/suppress"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    parsed = FeatureSuppressRequest.model_validate_json(upstream.content)
    assert parsed.suppressed is True
    assert parsed.expected_tree_version == 1


def test_tree_and_rollback_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        tree = client.get(f"/api/v1/parts/{PART}/features", headers=bearer)
        rollback = client.put(
            f"/api/v1/parts/{PART}/rollback",
            json={"expected_tree_version": 0, "rollback_feature_id": None},
            headers=bearer,
        )
        reorder = client.put(
            f"/api/v1/parts/{PART}/features/order",
            json={"expected_tree_version": 0, "order": [str(FEATURE)]},
            headers=bearer,
        )

    for response in (tree, rollback, reorder):
        assert response.status_code == 200
        FeatureTreeResponse.model_validate(response.json())
    assert [request.method for request in seen] == ["GET", "PUT", "PUT"]


def test_undo_redo_forward_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """POST /undo and /redo forward the OCC body + principal; the restored
    tree (with can_undo/can_redo) passes back through the shared DTO."""
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        undo = client.post(
            f"/api/v1/parts/{PART}/undo",
            json={"expected_tree_version": 4},
            headers=bearer,
        )
        redo = client.post(
            f"/api/v1/parts/{PART}/redo",
            json={"expected_tree_version": 5},
            headers=bearer,
        )

    assert undo.status_code == 200, undo.text
    assert redo.status_code == 200, redo.text
    assert FeatureTreeResponse.model_validate(undo.json()).tree_version == 5
    assert FeatureTreeResponse.model_validate(redo.json()).tree_version == 6
    undo_request, redo_request = seen
    assert undo_request.method == "POST"
    assert undo_request.url.path == f"/api/v1/parts/{PART}/undo"
    assert redo_request.url.path == f"/api/v1/parts/{PART}/redo"
    for upstream, version in ((undo_request, 4), (redo_request, 5)):
        assert upstream.headers[PRINCIPAL_HEADER] == user_id
        parsed = UndoRedoRequest.model_validate_json(upstream.content)
        assert parsed.expected_tree_version == version


def test_undo_stale_version_envelope_is_resurfaced(db_url: str) -> None:
    """Documents' 422 stale_tree_version passes through verbatim on undo."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "stale_tree_version",
                    "message": "Stale tree version.",
                    "details": {"provided": 1, "current": 3},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/parts/{PART}/undo",
            json={"expected_tree_version": 1},
            headers=bearer,
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "stale_tree_version"
    assert error["details"] == {"provided": 1, "current": 3}


def test_dependents_conflict_envelope_is_resurfaced(db_url: str) -> None:
    """The 409-with-dependents from documents passes through verbatim."""
    dependents = [{"id": str(uuid.uuid4()), "name": "Extrude1"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "feature_has_dependents",
                    "message": "Feature 'Sketch1' is referenced.",
                    "details": {"dependents": dependents},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.delete(
            f"/api/v1/parts/{PART}/features/{FEATURE}",
            params={"expected_tree_version": 1},
            headers=bearer,
        )

    assert response.status_code == 409
    error = _envelope(response.json())
    assert error["code"] == "feature_has_dependents"
    assert error["details"] == {"dependents": dependents}


def test_invalid_body_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """Shared DTOs validate BEFORE anything goes upstream."""
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/parts/{PART}/features",
            json={
                "name": "Bad",
                "feature": {"type": "fillet", "version": 1, "params": {}},
                "expected_tree_version": 0,
            },
            headers=bearer,
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []
