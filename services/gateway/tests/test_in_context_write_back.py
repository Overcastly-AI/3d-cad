"""gateway.in_context — geometry's resolved in-context values reach documents
(ASM-A3-IN-CONTEXT).

Documents and geometry are ``httpx.MockTransport`` upstreams; auth runs for
real. After ``/geometry/assembly/evaluate``, each edited part whose links moved
gets ONE documents write of its changed values, as the caller; unchanged and
failed links are not written; a refused or failing write never fails the
evaluation; an assembly without links makes no documents call at all.
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
from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    EvaluatedInstance,
)
from loft_wire.in_context import InContextResolvedWrite, InContextStatus
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]

ASSEMBLY = uuid.UUID(int=0xA3)
PLATE = uuid.UUID(int=0xB2)
BLOCK = uuid.UUID(int=0xB3)
SKETCH = uuid.UUID(int=0xC1)
RAIL_OCC = uuid.UUID(int=0xD1)


def _circle(y: float) -> dict[str, Any]:
    return {
        "kind": "circle",
        "center": {"x": 12.5, "y": y, "z": -8.0},
        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
        "radius": 1.75,
    }


def _status(part: uuid.UUID, entity: str, **extra: Any) -> InContextStatus:
    return InContextStatus.model_validate(
        {
            "part_id": str(part),
            "feature_id": str(SKETCH),
            "entity_id": entity,
            "occurrence_id": str(RAIL_OCC),
            "state": "ok",
            "resolved": _circle(45.0),
            "changed": True,
        }
        | extra
    )


def _result(statuses: list[InContextStatus]) -> str:
    return EvaluateAssemblyResult(
        assembly_id=ASSEMBLY,
        version=1,
        instances=[],
        status="well_constrained",
        in_context=statuses,
    ).model_dump_json()


def _request() -> dict[str, Any]:
    return EvaluateAssemblyRequest(
        assembly_id=ASSEMBLY,
        version=1,
        instances=[
            EvaluatedInstance(
                instance_id=uuid.uuid4(), part_key=f"{PLATE}@tip", features=[]
            )
        ],
    ).model_dump(mode="json")


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


def _client(db_url: str, documents: Handler, geometry: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        documents_transport=httpx.MockTransport(documents),
        geometry_transport=httpx.MockTransport(geometry),
    )
    return TestClient(app, raise_server_exceptions=False)


def _bearer(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ic@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _evaluate(
    db_url: str, statuses: list[InContextStatus], documents_status: int = 200
) -> tuple[httpx.Response | Any, list[httpx.Request]]:
    writes: list[httpx.Request] = []

    def documents(request: httpx.Request) -> httpx.Response:
        writes.append(request)
        if documents_status != 200:
            return httpx.Response(documents_status, json={"error": {}})
        return httpx.Response(200, json={"written": 1, "skipped": 0})

    def geometry(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_result(statuses))

    with _client(db_url, documents, geometry) as client:
        response = client.post(
            "/api/v1/geometry/assembly/evaluate",
            json=_request(),
            headers=_bearer(client),
        )
    return response, writes


def test_changed_values_are_written_once_per_part(db_url: str) -> None:
    response, writes = _evaluate(
        db_url,
        [
            _status(PLATE, "p1"),
            _status(PLATE, "p2", changed=False),
            _status(
                PLATE, "p3", state="error", reason="component_missing", resolved=None
            ),
            _status(BLOCK, "b1"),
        ],
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["in_context"]) == 4
    assert sorted(w.url.path for w in writes) == sorted(
        [
            f"/api/v1/parts/{PLATE}/in-context/resolved",
            f"/api/v1/parts/{BLOCK}/in-context/resolved",
        ]
    )
    plate = next(w for w in writes if str(PLATE) in w.url.path)
    body = InContextResolvedWrite.model_validate_json(plate.content)
    assert [(i.entity_id, i.assembly_id, i.occurrence_id) for i in body.items] == [
        ("p1", ASSEMBLY, RAIL_OCC)
    ]
    assert json.loads(plate.content)["items"][0]["resolved"] == _circle(45.0)
    assert PRINCIPAL_HEADER in plate.headers


def test_no_links_no_documents_call(db_url: str) -> None:
    response, writes = _evaluate(db_url, [])
    assert response.status_code == 200
    assert "in_context" not in response.json()
    assert writes == []


def test_a_refused_write_never_fails_the_evaluation(db_url: str) -> None:
    response, writes = _evaluate(db_url, [_status(PLATE, "p1")], documents_status=404)
    assert response.status_code == 200, response.text
    assert len(writes) == 1
