"""gateway ``POST /api/v1/parts/{id}/evaluate`` — the two-hop aggregation.

Same harness as tests/test_features_proxy.py (mock transports per upstream,
real auth over SQLite), extended with a mocked geometry upstream: the route
must fetch the evaluation-ready list from documents (principal attached),
relay it verbatim to geometry (NO principal — geometry is identity-free),
and type the result back — resurfacing either upstream's envelope on failure.

It also owns the last-evaluate BOOKKEEPING (feature-tree.md §4.4a): the gateway
writes the verdict back to documents because it is the only participant holding
both the verified principal and geometry's actual answer. The tests below pin
the two properties that make that safe — the verdict is DERIVED from the
per-feature statuses (never taken from a caller), and a bookkeeping failure of
any kind leaves the user's evaluate a clean 200.
"""

import asyncio
import json
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
    FeatureError,
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


def _documents_ok(seen: list[httpx.Request], *, record_status: int = 200) -> Handler:
    """Documents: the evaluation-ready list, plus the bookkeeping PUT.

    ``record_status`` lets a test make ONLY the bookkeeping write fail. The
    gateway never parses that response body (it is fire-and-forget), so the
    happy path answers a bare 200.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/last-evaluation"):
            return httpx.Response(record_status, json={})
        return httpx.Response(200, content=_evaluation_request().model_dump_json())

    return handler


def _recorded(seen: list[httpx.Request]) -> list[dict[str, Any]]:
    """The bodies of the bookkeeping writes documents saw."""
    return [
        json.loads(request.content)
        for request in seen
        if request.url.path.endswith("/last-evaluation")
    ]


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

    documents_request = documents_seen[0]
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


def test_the_client_gets_the_version_the_body_was_built_from(db_url: str) -> None:
    """PROVENANCE reaches the browser, not just the bookkeeping write.

    The verdict stamped onto the part row (below) and the ``tree_version`` the
    CLIENT reads off this response are the same number — the version documents
    composed the request from. That is what lets a viewport compare the body it
    is displaying against ``PartResponse.tree_version`` and know whether it is
    current, instead of concluding "up to date" from the absence of an in-flight
    request (docs/UI-REVIEW.md F2).
    """
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_ok(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    served = response.json()
    composed_from = _evaluation_request().tree_version
    assert served["tree_version"] == composed_from
    # …and the same stamp went onto the row, so the two sides of the comparison
    # can never disagree about which tree the last body came from.
    assert _recorded(documents_seen) == [
        {"tree_version": composed_from, "status": "ok"}
    ]


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


def test_a_clean_evaluate_records_ok_against_the_version_it_ran_on(
    db_url: str,
) -> None:
    """The bookkeeping write (§4.4a): documents' own route, the verified
    principal attached, stamped with the tree_version geometry echoed back — so
    the stored verdict names the tree it describes and cannot be forged by a
    browser."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, _documents_ok(documents_seen), _geometry_ok(geometry_seen)
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    [record] = [
        request
        for request in documents_seen
        if request.url.path.endswith("/last-evaluation")
    ]
    assert record.method == "PUT"
    assert record.url.path == f"/api/v1/parts/{PART}/last-evaluation"
    assert record.headers[PRINCIPAL_HEADER] == user_id
    assert json.loads(record.content) == {"tree_version": 4, "status": "ok"}


def test_a_feature_error_records_failed(db_url: str) -> None:
    """'failed' is DERIVED from the per-feature statuses, not reported."""
    documents_seen: list[httpx.Request] = []

    def geometry_with_failure(_request: httpx.Request) -> httpx.Response:
        result = _evaluation_result()
        result.features = [
            FeatureResult(
                feature_id=SKETCH,
                status="error",
                error=FeatureError(
                    code="sketch_conflicting", message="over-constrained"
                ),
            )
        ]
        return httpx.Response(200, content=result.model_dump_json())

    with make_client(db_url, _documents_ok(documents_seen), geometry_with_failure) as (
        client
    ):
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    assert _recorded(documents_seen) == [{"tree_version": 4, "status": "failed"}]


def test_a_suppressed_or_skipped_feature_is_not_a_failure(db_url: str) -> None:
    """Only ``error`` is a failure (§4.3): a deliberately suppressed feature, and
    a downstream ``skipped`` one, must not paint a part broken."""
    documents_seen: list[httpx.Request] = []

    def geometry_mixed(_request: httpx.Request) -> httpx.Response:
        result = _evaluation_result()
        result.features = [
            FeatureResult(feature_id=SKETCH, status="suppressed"),
            FeatureResult(feature_id=uuid.uuid4(), status="skipped"),
        ]
        return httpx.Response(200, content=result.model_dump_json())

    with make_client(db_url, _documents_ok(documents_seen), geometry_mixed) as client:
        _, bearer = _register(client)
        assert (
            client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer).status_code
            == 200
        )

    assert _recorded(documents_seen) == [{"tree_version": 4, "status": "ok"}]


def test_a_rejected_bookkeeping_write_still_leaves_a_clean_200(db_url: str) -> None:
    """A successful rebuild must never surface as an error because a status
    column could not be written."""
    documents_seen: list[httpx.Request] = []
    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url,
        _documents_ok(documents_seen, record_status=500),
        _geometry_ok(geometry_seen),
    ) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    assert EvaluateTreeResult.model_validate(response.json()).features[0].status == "ok"
    assert len(_recorded(documents_seen)) == 1


def test_an_unreachable_documents_after_the_fact_still_leaves_a_clean_200(
    db_url: str,
) -> None:
    """The transport failure that would be a 502 on the aggregation hop is
    swallowed on the bookkeeping hop — the result is already on the wire."""
    calls: list[httpx.Request] = []

    def documents_then_dead(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/last-evaluation"):
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, content=_evaluation_request().model_dump_json())

    geometry_seen: list[httpx.Request] = []
    with make_client(
        db_url, documents_then_dead, _geometry_ok(geometry_seen)
    ) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 200, response.text
    assert len(calls) == 2  # the read hop, then the attempted write


def test_a_failed_evaluate_records_nothing(db_url: str) -> None:
    """No answer from geometry means no verdict to store — the previous record
    stands (and reads ``stale`` once the tree moves), rather than being
    overwritten with a guess."""
    documents_seen: list[httpx.Request] = []

    def geometry_500(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "code": "internal_error",
                    "message": "boom",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, _documents_ok(documents_seen), geometry_500) as client:
        _, bearer = _register(client)
        response = client.post(f"/api/v1/parts/{PART}/evaluate", headers=bearer)

    assert response.status_code == 500
    assert _recorded(documents_seen) == []


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
