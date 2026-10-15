"""gateway.in_context — geometry's resolved in-context values reach documents
(ASM-A3-IN-CONTEXT), from COMMITTED evaluations only.

Documents and geometry are ``httpx.MockTransport`` upstreams; auth runs for
real. With ``?write_back=true`` and a request that is the assembly as
documents stores it, each edited part whose links moved gets ONE documents
write of its changed values, carrying each link's whole identity. Never
written: an evaluation without the flag (the joint dialog's live preview), a
flagged one whose mates or poses differ from the stored assembly (a draft),
unchanged or failed links, and nothing at all for an assembly without links.
A refused write never fails the evaluation.
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
    Placement,
)
from loft_wire.geometry import Vec3
from loft_wire.in_context import InContextResolvedWrite, InContextStatus
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]

ASSEMBLY = uuid.UUID(int=0xA3)
PLATE = uuid.UUID(int=0xB2)
BLOCK = uuid.UUID(int=0xB3)
RAIL = uuid.UUID(int=0xB4)
SKETCH = uuid.UUID(int=0xC1)
RAIL_OCC = uuid.UUID(int=0xD1)
PLATE_OCC = uuid.UUID(int=0xD2)
EDGE = {
    "curve": "circle",
    "end_a": {"x": 189.25, "y": 0.0, "z": 8.0},
    "end_b": {"x": 189.25, "y": 0.0, "z": 8.0},
    "midpoint": {"x": 185.75, "y": 0.0, "z": 8.0},
    "length_mm": 10.995574287564276,
}


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
            "host_occurrence_id": str(PLATE_OCC),
            "referenced_part_id": str(RAIL),
            "edge": EDGE,
            "state": "ok",
            "resolved": _circle(45.0),
            "changed": True,
        }
        | extra
    )


def _result(statuses: list[InContextStatus]) -> str:
    return EvaluateAssemblyResult(
        assembly_id=ASSEMBLY,
        version=4,
        instances=[],
        status="well_constrained",
        in_context=statuses,
    ).model_dump_json()


def _request(rail_y: float = 40.0) -> EvaluateAssemblyRequest:
    return EvaluateAssemblyRequest(
        assembly_id=ASSEMBLY,
        version=4,
        instances=[
            EvaluatedInstance(
                instance_id=RAIL_OCC,
                part_key=f"{RAIL}@tip",
                features=[],
                grounded=True,
                placement=Placement(position=Vec3(x=25.0, y=rail_y, z=10.0)),
            ),
            EvaluatedInstance(
                instance_id=PLATE_OCC,
                part_key=f"{PLATE}@tip",
                features=[],
                grounded=True,
            ),
        ],
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
        json={
            "email": f"ic-{uuid.uuid4().hex[:8]}@example.com",
            "password": "hunter2-passphrase",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _evaluate(
    db_url: str,
    statuses: list[InContextStatus],
    *,
    request: EvaluateAssemblyRequest | None = None,
    write_back: bool = True,
    documents_status: int = 200,
) -> tuple[Any, list[httpx.Request]]:
    """Evaluate *request* (default: the stored assembly); the documents
    writes made, in order."""
    writes: list[httpx.Request] = []

    def documents(call: httpx.Request) -> httpx.Response:
        if call.url.path.endswith("/evaluation-request"):
            return httpx.Response(200, content=_request().model_dump_json())
        writes.append(call)
        if documents_status != 200:
            return httpx.Response(documents_status, json={"error": {}})
        return httpx.Response(200, json={"written": 1, "skipped": 0})

    def geometry(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_result(statuses))

    with _client(db_url, documents, geometry) as client:
        response = client.post(
            "/api/v1/geometry/assembly/evaluate",
            params={"write_back": "true"} if write_back else {},
            json=(request or _request()).model_dump(mode="json"),
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
    # Each item carries the link's whole identity.
    [item] = body.items
    assert (
        item.entity_id,
        item.assembly_id,
        item.host_occurrence_id,
        item.occurrence_id,
        item.part_id,
    ) == ("p1", ASSEMBLY, PLATE_OCC, RAIL_OCC, RAIL)
    assert item.edge.end_a.x == 189.25
    assert json.loads(plate.content)["items"][0]["resolved"] == _circle(45.0)
    assert PRINCIPAL_HEADER in plate.headers


def test_a_preview_without_the_flag_never_writes(db_url: str) -> None:
    """The joint dialog's live preview evaluates without ``write_back``."""
    response, writes = _evaluate(db_url, [_status(PLATE, "p1")], write_back=False)
    assert response.status_code == 200, response.text
    assert writes == []


def test_a_draft_that_differs_from_the_stored_assembly_never_writes(
    db_url: str,
) -> None:
    """A rail at a draft pose (a cancelled offset), even flagged: nothing is
    stored, so the part never keeps a pose the assembly does not have."""
    response, writes = _evaluate(
        db_url, [_status(PLATE, "p1")], request=_request(rail_y=52.0)
    )
    assert response.status_code == 200, response.text
    assert writes == []
    stale = _request().model_copy(update={"version": 3})
    response, writes = _evaluate(db_url, [_status(PLATE, "p1")], request=stale)
    assert writes == []


def test_no_links_no_documents_call(db_url: str) -> None:
    response, writes = _evaluate(db_url, [])
    assert response.status_code == 200
    assert "in_context" not in response.json()
    assert writes == []


def test_a_refused_write_never_fails_the_evaluation(db_url: str) -> None:
    response, writes = _evaluate(db_url, [_status(PLATE, "p1")], documents_status=404)
    assert response.status_code == 200, response.text
    assert len(writes) == 1
