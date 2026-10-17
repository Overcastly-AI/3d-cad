"""gateway.assembly_mirrors — component mirror writes proxied to documents.

Documents and geometry are ``httpx.MockTransport`` upstreams; auth runs for
real. A mirror's count needs no evaluation, so every write goes to documents
only (geometry is never called), carrying the body verbatim; documents'
refusals re-surface with their own code; the BOM's opposite-hand line passes
through.
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
from loft_wire.assemblies import AssemblyBomResponse, BomLine
from loft_wire.component_mirrors import MirrorMutationResponse, MirrorResponse
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]

ASSEMBLY = uuid.UUID(int=0xA6)
ARM = uuid.UUID(int=0xB6)
MIRROR = uuid.UUID(int=0xC6)
PART = uuid.UUID(int=0xE6)


def _mirror() -> dict[str, Any]:
    return {
        "seed_instance_ids": [str(ARM)],
        "plane": {"kind": "origin_plane", "plane": "yz", "offset_mm": 0.0},
        "opposite_hand_instance_ids": [str(ARM)],
    }


def _line(opposite: bool) -> BomLine:
    return BomLine(
        ref_document_id=PART,
        ref_document_kind="part",
        name="Crank arm (opposite hand)" if opposite else "Crank arm",
        quantity=1,
        opposite_hand=opposite,
    )


def _documents(seen: list[httpx.Request], refuse: str | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if refuse is not None:
            body = {"error": {"code": refuse, "message": "no", "request_id": "x"}}
            return httpx.Response(422, json=body)
        if path.endswith("/mirrors") or path.endswith(f"/mirrors/{MIRROR}"):
            if request.method == "DELETE":
                return httpx.Response(404)
            mirror = json.loads(request.content)["mirror"]
            response = MirrorMutationResponse(
                mirror=MirrorResponse.model_validate(
                    {
                        "id": str(MIRROR),
                        "assembly_id": str(ASSEMBLY),
                        "order_index": 0,
                        "mirror": mirror,
                    }
                ),
                doc_version=5,
            )
            status = 201 if request.method == "POST" else 200
            return httpx.Response(status, content=response.model_dump_json())
        if path == f"/api/v1/assemblies/{ASSEMBLY}/bom":
            lines = [_line(False), _line(True)]
            bom = AssemblyBomResponse(
                assembly_id=ASSEMBLY,
                lines=lines,
                total_instances=2,
                indented=[],
                parts_only=lines,
                total_parts=2,
            )
            return httpx.Response(200, content=bom.model_dump_json())
        return httpx.Response(404)

    return handler


def _geometry(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500)

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
        json={"email": "mirror@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_mirror_writes_go_to_documents_only(db_url: str) -> None:
    docs: list[httpx.Request] = []
    geo: list[httpx.Request] = []
    with _client(db_url, _documents(docs), _geometry(geo)) as client:
        bearer = _bearer(client)
        created = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/mirrors",
            json={"expected_version": 4, "mirror": _mirror()},
            headers=bearer,
        )
        updated = client.patch(
            f"/api/v1/assemblies/{ASSEMBLY}/mirrors/{MIRROR}",
            json={"expected_version": 5, "mirror": _mirror()},
            headers=bearer,
        )
        deleted = client.delete(
            f"/api/v1/assemblies/{ASSEMBLY}/mirrors/{MIRROR}",
            params={"expected_version": 6},
            headers=bearer,
        )
        bom = client.get(f"/api/v1/assemblies/{ASSEMBLY}/bom", headers=bearer)
    assert created.status_code == 201, created.text
    assert created.json()["mirror"]["mirror"] == _mirror()
    assert updated.status_code == 200, updated.text
    assert deleted.status_code == 404  # documents' answer, re-surfaced
    assert geo == []
    assert [r.method for r in docs] == ["POST", "PATCH", "DELETE", "GET"]
    assert docs[2].url.params["expected_version"] == "6"
    assert json.loads(docs[0].content)["mirror"] == _mirror()
    lines = bom.json()["lines"]
    assert [(line["name"], line.get("opposite_hand", False)) for line in lines] == [
        ("Crank arm", False),
        ("Crank arm (opposite hand)", True),
    ]


def test_a_documents_refusal_keeps_its_code(db_url: str) -> None:
    with _client(
        db_url, _documents([], "mirror_opposite_hand_needs_part"), _geometry([])
    ) as client:
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/mirrors",
            json={"expected_version": 4, "mirror": _mirror()},
            headers=_bearer(client),
        )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "mirror_opposite_hand_needs_part"
