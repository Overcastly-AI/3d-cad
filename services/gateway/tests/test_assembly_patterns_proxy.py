"""gateway.assembly_patterns — component patterns across documents + geometry.

Documents and geometry are ``httpx.MockTransport`` upstreams; auth runs for
real. A hole-driven pattern write asks geometry for its count first and passes
it to documents as ``driven_count`` (refusing typed past the bound); a BOM that
reports unresolved hole-driven patterns is read again with geometry's counts,
for the assembly BOM and a drawing's parts list alike; linear and circular
patterns never touch geometry.
"""

import asyncio
import json
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
from loft_wire.assemblies import (
    AssemblyBomResponse,
    BomLine,
    EvaluateAssemblyRequest,
    EvaluatedInstance,
)
from loft_wire.component_patterns import (
    EvaluatedPattern,
    PatternCount,
    PatternCountsResult,
    PatternMutationResponse,
    PatternResponse,
)
from loft_wire.drawings import DrawingBomLine, DrawingBomResponse
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]

ASSEMBLY = uuid.UUID(int=0xA5)
DRAWING = uuid.UUID(int=0xD5)
RAIL = uuid.UUID(int=0xB1)
SCREW = uuid.UUID(int=0xB2)
HOLES = uuid.UUID(int=0xC1)
NOW = datetime(2026, 10, 15, tzinfo=UTC)


def _hole_pattern() -> dict[str, Any]:
    return {
        "type": "hole",
        "seed_instance_ids": [str(SCREW)],
        "seed_hole": {
            "instance_id": str(RAIL),
            "signature": {
                "curve": "circle",
                "end_a": {"x": 3.0, "y": 0.0, "z": 0.0},
                "end_b": {"x": 3.0, "y": 0.0, "z": 0.0},
                "midpoint": {"x": -3.0, "y": 0.0, "z": 0.0},
                "length_mm": 18.84955592153876,
            },
        },
    }


def _evaluation_request() -> EvaluateAssemblyRequest:
    return EvaluateAssemblyRequest(
        assembly_id=ASSEMBLY,
        version=3,
        instances=[
            EvaluatedInstance(instance_id=RAIL, part_key="rail@tip", features=[]),
            EvaluatedInstance(instance_id=SCREW, part_key="screw@tip", features=[]),
        ],
        patterns=[
            EvaluatedPattern.model_validate(
                {"pattern_id": str(HOLES), "order_index": 0, "pattern": _hole_pattern()}
            )
        ],
    )


def _mutation(body: bytes) -> str:
    pattern = json.loads(body)["pattern"]
    response = PatternMutationResponse(
        pattern=PatternResponse.model_validate(
            {
                "id": str(HOLES),
                "assembly_id": str(ASSEMBLY),
                "order_index": 0,
                "pattern": pattern,
            }
        ),
        doc_version=4,
    )
    return response.model_dump_json()


def _line(quantity: int) -> BomLine:
    return BomLine(
        ref_document_id=uuid.UUID(int=7),
        ref_document_kind="part",
        name="M3x8",
        quantity=quantity,
    )


def _documents(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        counts = request.url.params.get_list("pattern_count")
        if path.endswith("/evaluation-request"):
            return httpx.Response(200, content=_evaluation_request().model_dump_json())
        if path.endswith("/patterns"):
            return httpx.Response(201, content=_mutation(request.content))
        if path == f"/api/v1/assemblies/{ASSEMBLY}/bom":
            quantity = 28 if counts == [f"{HOLES}:28"] else 1
            bom = AssemblyBomResponse(
                assembly_id=ASSEMBLY,
                lines=[_line(quantity)],
                total_instances=quantity,
                indented=[],
                parts_only=[_line(quantity)],
                total_parts=quantity,
                unresolved_patterns=[] if counts else [HOLES],
            )
            return httpx.Response(200, content=bom.model_dump_json())
        if path == f"/api/v1/drawings/{DRAWING}/bom":
            quantity = 28 if counts == [f"{HOLES}:28"] else 1
            drawing = DrawingBomResponse(
                drawing_id=DRAWING,
                sheet_id=uuid.UUID(int=0x5),
                assembly_id=ASSEMBLY,
                assembly_version=3,
                structure="top_level",
                lines=[
                    DrawingBomLine(
                        item_number=1,
                        item="1",
                        level=0,
                        total_quantity=quantity,
                        ref_document_id=uuid.UUID(int=7),
                        ref_document_kind="part",
                        name="M3x8",
                        quantity=quantity,
                    )
                ],
                total_instances=quantity,
                total_parts=quantity,
                unresolved_patterns=[] if counts else [HOLES],
            )
            return httpx.Response(200, content=drawing.model_dump_json())
        return httpx.Response(404)

    return handler


def _geometry(
    seen: list[httpx.Request], count: int | None, code: str | None = None
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/api/v1/assembly/pattern-counts"
        probe = EvaluateAssemblyRequest.model_validate_json(request.content)
        result = PatternCountsResult(
            counts=[
                PatternCount(
                    pattern_id=p.pattern_id,
                    count=count,
                    error_code=code,
                    error_message=None if code is None else "nope",
                )
                for p in probe.patterns
            ]
        )
        return httpx.Response(200, content=result.model_dump_json())

    return handler


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
        json={"email": "pat@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_a_hole_pattern_write_carries_geometry_count(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    with _client(db_url, _documents(docs), _geometry(geo, 14)) as client:
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/patterns",
            json={"expected_version": 3, "pattern": _hole_pattern()},
            headers=_bearer(client),
        )
    assert response.status_code == 201, response.text
    (probe,) = geo
    # The stored pattern plus the candidate, which gets its own id.
    assert len(EvaluateAssemblyRequest.model_validate_json(probe.content).patterns) == 2
    write = docs[-1]
    assert write.method == "POST"
    assert write.url.params["driven_count"] == "14"


def test_a_linear_pattern_write_skips_geometry(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    linear = {
        "type": "linear",
        "seed_instance_ids": [str(SCREW)],
        "direction": {"kind": "origin_axis", "axis": "x"},
        "count": 3,
        "spacing_mm": 25.0,
    }
    with _client(db_url, _documents(docs), _geometry(geo, 3)) as client:
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/patterns",
            json={"expected_version": 3, "pattern": linear},
            headers=_bearer(client),
        )
    assert response.status_code == 201, response.text
    assert geo == []
    assert "driven_count" not in docs[-1].url.params


@pytest.mark.parametrize(
    ("count", "code", "expected"),
    [
        (None, "pattern_too_large", "assembly_too_large"),
        (None, "subshape_unresolved", "subshape_unresolved"),
    ],
)
def test_a_hole_pattern_geometry_refuses_is_typed(
    db_url: str, count: int | None, code: str, expected: str
) -> None:
    docs: list[httpx.Request] = []
    with _client(db_url, _documents(docs), _geometry([], count, code)) as client:
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/patterns",
            json={"expected_version": 3, "pattern": _hole_pattern()},
            headers=_bearer(client),
        )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == expected
    assert all(r.method == "GET" for r in docs)  # nothing written


def test_the_bom_resolves_hole_driven_counts(db_url: str) -> None:
    docs: list[httpx.Request] = []
    with _client(db_url, _documents(docs), _geometry([], 28)) as client:
        bearer = _bearer(client)
        bom = client.get(f"/api/v1/assemblies/{ASSEMBLY}/bom", headers=bearer)
        drawing = client.get(
            f"/api/v1/drawings/{DRAWING}/bom",
            params={"sheet": str(uuid.UUID(int=5))},
            headers=bearer,
        )
    assert bom.status_code == 200, bom.text
    assert bom.json()["total_instances"] == 28
    assert "unresolved_patterns" not in bom.json()
    assert drawing.status_code == 200, drawing.text
    assert drawing.json()["total_instances"] == 28
    last = docs[-1]
    assert last.url.params["sheet"] == str(uuid.UUID(int=5))
    assert last.url.params.get_list("pattern_count") == [f"{HOLES}:28"]


def test_an_unresolvable_count_leaves_the_bom_honest(db_url: str) -> None:
    with _client(db_url, _documents([]), _geometry([], None, "no_body")) as client:
        bom = client.get(f"/api/v1/assemblies/{ASSEMBLY}/bom", headers=_bearer(client))
    assert bom.status_code == 200, bom.text
    assert bom.json()["unresolved_patterns"] == [str(HOLES)]
    assert bom.json()["total_instances"] == 1
