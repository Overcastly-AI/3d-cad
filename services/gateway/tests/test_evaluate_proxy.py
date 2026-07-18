"""gateway ``POST /api/v1/parts/{id}/evaluate`` — the two-hop aggregation.

Same harness as tests/test_features_proxy.py (mock transports per upstream,
real auth over SQLite), extended with a mocked geometry upstream: the route
must fetch the evaluation-ready list from documents (principal attached),
relay it verbatim to geometry (NO principal — geometry is identity-free),
and type the result back — resurfacing either upstream's envelope on failure.
"""

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from gateway.db import Base
from gateway.main import GatewaySettings, build_app
from py_kit.db import async_dsn
from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureResult,
    SketchFeature,
    SolvedSketchData,
)
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

PART = uuid.UUID("00000000-0000-0000-0000-0000000000fa")
SKETCH = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

SKETCH_ENVELOPE: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 40.0, "y": 0.0},
            }
        ],
        "constraints": [{"kind": "fixed", "point": {"entity": "e1", "point": "start"}}],
    },
}


def _evaluation_request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest(
        part_id=PART,
        tree_version=4,
        features=[
            EvaluatedFeatureInput(
                id=SKETCH, feature=SketchFeature.model_validate(SKETCH_ENVELOPE)
            )
        ],
    )


def _evaluation_result() -> EvaluateTreeResult:
    return EvaluateTreeResult(
        part_id=PART,
        tree_version=4,
        features=[
            FeatureResult(
                feature_id=SKETCH,
                status="ok",
                data=SolvedSketchData.model_validate(
                    {
                        "kind": "solved_sketch",
                        "status": "converged",
                        "entities": SKETCH_ENVELOPE["params"]["entities"],
                        "dof": 0,
                    }
                ),
            )
        ],
        mesh_glb_id=None,
        properties=None,
        last_good_feature_id=SKETCH,
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


def make_client(
    db_url: str, documents_handler: Handler, geometry_handler: Handler
) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry_handler),
        documents_transport=httpx.MockTransport(documents_handler),
    )
    return TestClient(app, raise_server_exceptions=False)


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


def _documents_ok(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_evaluation_request().model_dump_json())

    return handler


def _geometry_ok(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_evaluation_result().model_dump_json())

    return handler


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_ok(geometry_seen)
    ) as client:
        response = client.post(f"/api/v1/parts/{PART}/evaluate")

    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert documents_seen == []
    assert geometry_seen == []


def test_evaluate_relays_documents_list_to_geometry(db_url: str) -> None:
    """The full loop's gateway hop: principal to documents only, the §4.2
    request relayed byte-for-byte-equivalent to geometry, typed result back
    (solved-sketch ``data`` included)."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_ok(geometry_seen)
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    result = EvaluateTreeResult.model_validate(response.json())
    assert result.features[0].status == "ok"
    assert result.features[0].data is not None
    assert result.features[0].data.dof == 0

    [documents_request] = documents_seen
    assert documents_request.method == "GET"
    assert documents_request.url.path == f"/api/v1/parts/{PART}/evaluation-request"
    assert documents_request.headers[PRINCIPAL_HEADER] == user_id

    [geometry_request] = geometry_seen
    assert geometry_request.method == "POST"
    assert geometry_request.url.path == "/api/v1/evaluate"
    # Geometry is identity-free (RESEARCH §3): the principal stays behind.
    assert PRINCIPAL_HEADER not in geometry_request.headers
    relayed = EvaluateTreeRequest.model_validate_json(geometry_request.content)
    assert relayed == _evaluation_request()


def test_documents_error_resurfaced_and_geometry_never_called(db_url: str) -> None:
    geometry_seen: list[httpx.Request] = []

    def documents_404(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "part_not_found",
                    "message": "Part not found.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, documents_404, _geometry_ok(geometry_seen)) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "part_not_found"
    assert geometry_seen == []


def test_geometry_error_envelope_resurfaced(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []

    def geometry_422(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, _documents_ok(documents_seen), geometry_422) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"


def test_geometry_unreachable_is_502(db_url: str) -> None:
    documents_seen: list[httpx.Request] = []

    def geometry_down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with make_client(db_url, _documents_ok(documents_seen), geometry_down) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert error["details"] == {"reason": "ConnectError"}
