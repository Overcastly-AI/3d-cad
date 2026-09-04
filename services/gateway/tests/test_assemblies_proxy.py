"""gateway.assemblies — auth gating, principal forwarding, envelope passthrough.

Same harness as tests/test_parts_proxy.py: the documents upstream is an
``httpx.MockTransport``; auth runs for real (register → bearer token) over the
SQLite/aiosqlite test DB. Every assembly route is auth-gated (F7): a 401 per
route with nothing forwarded upstream, plus the documents 422/409/404 envelopes
re-surfaced verbatim.
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
from py_kit.schemas.assemblies import (
    AssemblyBomResponse,
    AssemblyCreate,
    AssemblyGraphResponse,
    AssemblyListResponse,
    AssemblyResponse,
    AssemblyUndoRedoRequest,
    BomLine,
    InstanceCreate,
    InstanceMutationResponse,
    InstanceResponse,
    LockMate,
    MateCreate,
    MateMutationResponse,
    MateResponse,
    Placement,
)
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"

Handler = Callable[[httpx.Request], httpx.Response]

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)

ASSEMBLY = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
INSTANCE_A = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
INSTANCE_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


def _assembly(owner_id: uuid.UUID, name: str = "Gearbox") -> AssemblyResponse:
    return AssemblyResponse(
        id=ASSEMBLY,
        name=name,
        owner_id=owner_id,
        length_unit="mm",
        doc_version=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _instance(instance_id: uuid.UUID, name: str = "Bracket <1>") -> InstanceResponse:
    return InstanceResponse(
        id=instance_id,
        assembly_id=ASSEMBLY,
        ref_document_id=uuid.uuid4(),
        ref_document_kind="part",
        ref_pinned_version=None,
        name=name,
        placement=Placement(position=Vec3(x=0.0, y=0.0, z=0.0)),
        grounded=False,
        order_index=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _mate() -> MateResponse:
    return MateResponse(
        id=uuid.uuid4(),
        assembly_id=ASSEMBLY,
        order_index=0,
        mate=LockMate(a_instance_id=INSTANCE_A, b_instance_id=INSTANCE_B),
    )


def _graph(owner_id: uuid.UUID) -> AssemblyGraphResponse:
    return AssemblyGraphResponse(
        assembly=_assembly(owner_id),
        doc_version=3,
        instances=[_instance(INSTANCE_A), _instance(INSTANCE_B, "Bracket <2>")],
        mates=[_mate()],
        can_undo=True,
        can_redo=False,
    )


def _bom() -> AssemblyBomResponse:
    return AssemblyBomResponse(
        assembly_id=ASSEMBLY,
        lines=[
            BomLine(
                ref_document_id=uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
                ref_document_kind="part",
                name="Bracket",
                quantity=2,
            )
        ],
        total_instances=2,
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
    """A canned documents assembly upstream: create/list/get/mutate/delete."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        owner_id = uuid.UUID(request.headers[PRINCIPAL_HEADER])
        path = request.url.path
        if request.method == "DELETE":
            if path == f"/api/v1/assemblies/{ASSEMBLY}":
                return httpx.Response(204)
            # instance / mate delete → the updated graph
            return httpx.Response(200, content=_graph(owner_id).model_dump_json())
        if request.method == "POST":
            if path.endswith(("/undo", "/redo")):
                AssemblyUndoRedoRequest.model_validate_json(request.content)
                restored = _graph(owner_id).model_copy(
                    update={"doc_version": 4, "can_undo": False, "can_redo": True}
                )
                return httpx.Response(200, content=restored.model_dump_json())
            if path.endswith("/instances"):
                body = InstanceMutationResponse(
                    instance=_instance(INSTANCE_A), doc_version=1
                )
                return httpx.Response(201, content=body.model_dump_json())
            if path.endswith("/mates"):
                body_m = MateMutationResponse(mate=_mate(), doc_version=2)
                return httpx.Response(201, content=body_m.model_dump_json())
            name = AssemblyCreate.model_validate_json(request.content).name
            return httpx.Response(
                201, content=_assembly(owner_id, name).model_dump_json()
            )
        if request.method == "PATCH":
            if "/instances/" in path:
                body_i = InstanceMutationResponse(
                    instance=_instance(INSTANCE_A), doc_version=1
                )
                return httpx.Response(200, content=body_i.model_dump_json())
            return httpx.Response(
                200, content=_assembly(owner_id, "Gearbox v2").model_dump_json()
            )
        # GET
        if path == "/api/v1/assemblies":
            listing = AssemblyListResponse(assemblies=[_assembly(owner_id)])
            return httpx.Response(200, content=listing.model_dump_json())
        if path.endswith("/bom"):
            return httpx.Response(200, content=_bom().model_dump_json())
        return httpx.Response(200, content=_graph(owner_id).model_dump_json())

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


# --- auth gating (F7: every route rejects unauthenticated, nothing forwarded) ---


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/assemblies"),
        ("GET", "/api/v1/assemblies"),
        ("GET", f"/api/v1/assemblies/{ASSEMBLY}"),
        ("GET", f"/api/v1/assemblies/{ASSEMBLY}/bom"),
        ("GET", f"/api/v1/assemblies/{ASSEMBLY}/extents"),
        ("PATCH", f"/api/v1/assemblies/{ASSEMBLY}"),
        ("DELETE", f"/api/v1/assemblies/{ASSEMBLY}"),
        ("POST", f"/api/v1/assemblies/{ASSEMBLY}/instances"),
        ("PATCH", f"/api/v1/assemblies/{ASSEMBLY}/instances/{INSTANCE_A}"),
        (
            "DELETE",
            f"/api/v1/assemblies/{ASSEMBLY}/instances/{INSTANCE_A}?expected_version=0",
        ),
        ("POST", f"/api/v1/assemblies/{ASSEMBLY}/mates"),
        (
            "DELETE",
            f"/api/v1/assemblies/{ASSEMBLY}/mates/{uuid.uuid4()}?expected_version=0",
        ),
        ("POST", f"/api/v1/assemblies/{ASSEMBLY}/undo"),
        ("POST", f"/api/v1/assemblies/{ASSEMBLY}/redo"),
    ],
)
def test_unauthenticated_401_and_nothing_forwarded(
    db_url: str, seen: list[httpx.Request], method: str, path: str
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        response = client.request(method, path, json={"name": "Gearbox"})
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert seen == []


# --- happy paths: principal forwarding + typed passthrough ----------------------


def test_create_assembly_forwards_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies", json={"name": "Gearbox"}, headers=bearer
        )

    assert response.status_code == 201, response.text
    body = AssemblyResponse.model_validate(response.json())
    assert body.name == "Gearbox"
    # The owner is the JWT-verified caller, derived at the gateway.
    assert str(body.owner_id) == user_id

    [upstream] = seen
    assert upstream.method == "POST"
    assert upstream.url.path == "/api/v1/assemblies"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id
    assert AssemblyCreate.model_validate_json(upstream.content).name == "Gearbox"


def test_list_assemblies_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.get("/api/v1/assemblies", headers=bearer)

    assert response.status_code == 200
    assemblies = AssemblyListResponse.model_validate(response.json()).assemblies
    assert len(assemblies) == 1
    [upstream] = seen
    assert upstream.headers[PRINCIPAL_HEADER] == user_id


def test_get_assembly_graph_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get(f"/api/v1/assemblies/{ASSEMBLY}", headers=bearer)

    assert response.status_code == 200
    graph = AssemblyGraphResponse.model_validate(response.json())
    assert len(graph.instances) == 2
    assert len(graph.mates) == 1
    [upstream] = seen
    assert upstream.url.path == f"/api/v1/assemblies/{ASSEMBLY}"


def test_get_assembly_bom_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        response = client.get(f"/api/v1/assemblies/{ASSEMBLY}/bom", headers=bearer)

    assert response.status_code == 200
    bom = AssemblyBomResponse.model_validate(response.json())
    assert bom.total_instances == 2
    assert [line.name for line in bom.lines] == ["Bracket"]
    assert bom.lines[0].quantity == 2
    [upstream] = seen
    assert upstream.method == "GET"
    assert upstream.url.path == f"/api/v1/assemblies/{ASSEMBLY}/bom"
    assert upstream.headers[PRINCIPAL_HEADER] == user_id


def test_crud_roundtrip_create_instances_mate_read(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """The integration flow: create assembly → add two instances + a lock mate →
    read the graph, all through the authenticated gateway."""
    ref_a, ref_b = uuid.uuid4(), uuid.uuid4()
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)

        created = client.post(
            "/api/v1/assemblies", json={"name": "Gearbox"}, headers=bearer
        )
        assert created.status_code == 201, created.text

        inst_a = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/instances",
            json=InstanceCreate(
                expected_version=0,
                ref_document_id=ref_a,
                ref_document_kind="part",
                name="Bracket <1>",
            ).model_dump(mode="json"),
            headers=bearer,
        )
        assert inst_a.status_code == 201, inst_a.text
        InstanceMutationResponse.model_validate(inst_a.json())

        inst_b = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/instances",
            json=InstanceCreate(
                expected_version=1,
                ref_document_id=ref_b,
                ref_document_kind="part",
                name="Bracket <2>",
            ).model_dump(mode="json"),
            headers=bearer,
        )
        assert inst_b.status_code == 201, inst_b.text

        mate = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/mates",
            json=MateCreate(
                expected_version=2,
                mate=LockMate(a_instance_id=INSTANCE_A, b_instance_id=INSTANCE_B),
            ).model_dump(mode="json"),
            headers=bearer,
        )
        assert mate.status_code == 201, mate.text
        MateMutationResponse.model_validate(mate.json())

        graph = client.get(f"/api/v1/assemblies/{ASSEMBLY}", headers=bearer)
        assert graph.status_code == 200
        AssemblyGraphResponse.model_validate(graph.json())

    # Every hop forwarded the verified principal to the assembly CRUD API.
    assert {r.url.path for r in seen} == {
        "/api/v1/assemblies",
        f"/api/v1/assemblies/{ASSEMBLY}/instances",
        f"/api/v1/assemblies/{ASSEMBLY}/mates",
        f"/api/v1/assemblies/{ASSEMBLY}",
    }


def test_update_assembly_passthrough(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.patch(
            f"/api/v1/assemblies/{ASSEMBLY}",
            json={"expected_version": 0, "name": "Gearbox v2"},
            headers=bearer,
        )
    assert response.status_code == 200
    assert AssemblyResponse.model_validate(response.json()).name == "Gearbox v2"
    [upstream] = seen
    assert upstream.method == "PATCH"


def test_delete_assembly_204(db_url: str, seen: list[httpx.Request]) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(f"/api/v1/assemblies/{ASSEMBLY}", headers=bearer)
    assert response.status_code == 204
    assert response.content == b""
    [upstream] = seen
    assert upstream.method == "DELETE"


def test_delete_instance_forwards_expected_version(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.delete(
            f"/api/v1/assemblies/{ASSEMBLY}/instances/{INSTANCE_A}?expected_version=3",
            headers=bearer,
        )
    assert response.status_code == 200
    AssemblyGraphResponse.model_validate(response.json())
    [upstream] = seen
    assert upstream.url.params["expected_version"] == "3"


def test_undo_redo_forward_principal_and_body(
    db_url: str, seen: list[httpx.Request]
) -> None:
    """POST /undo and /redo forward the OCC body + principal; the restored
    graph (with can_undo/can_redo) passes back through the shared DTO."""
    with make_client(db_url, _echo_documents(seen)) as client:
        user_id, bearer = _register(client)
        undo = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/undo",
            json={"expected_version": 4},
            headers=bearer,
        )
        redo = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/redo",
            json={"expected_version": 5},
            headers=bearer,
        )

    assert undo.status_code == 200, undo.text
    assert redo.status_code == 200, redo.text
    for response in (undo, redo):
        graph = AssemblyGraphResponse.model_validate(response.json())
        assert graph.doc_version == 4
        assert (graph.can_undo, graph.can_redo) == (False, True)
    undo_request, redo_request = seen
    assert undo_request.method == "POST"
    assert undo_request.url.path == f"/api/v1/assemblies/{ASSEMBLY}/undo"
    assert redo_request.url.path == f"/api/v1/assemblies/{ASSEMBLY}/redo"
    for upstream, version in ((undo_request, 4), (redo_request, 5)):
        assert upstream.headers[PRINCIPAL_HEADER] == user_id
        parsed = AssemblyUndoRedoRequest.model_validate_json(upstream.content)
        assert parsed.expected_version == version


def test_undo_stale_version_envelope_is_resurfaced(db_url: str) -> None:
    """Documents' 422 stale_assembly_version passes through verbatim on undo."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "stale_assembly_version",
                    "message": "Stale assembly version.",
                    "details": {"provided": 0, "current": 2},
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.post(
            f"/api/v1/assemblies/{ASSEMBLY}/undo",
            json={"expected_version": 0},
            headers=bearer,
        )

    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "stale_assembly_version"
    assert error["details"] == {"provided": 0, "current": 2}


# --- upstream error surfaces (documents 422 / 409 / 404 re-surfaced) ------------


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (422, "stale_assembly_version"),
        (409, "assembly_has_dependents"),
        (404, "assembly_not_found"),
    ],
)
def test_upstream_envelope_is_resurfaced(
    db_url: str, status_code: int, code: str
) -> None:
    """Documents 422 stale / 409 dependents / 404 non-owner pass through intact."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "code": code,
                    "message": "upstream said so.",
                    "details": None,
                    "request_id": "upstream-id",
                }
            },
        )

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.patch(
            f"/api/v1/assemblies/{ASSEMBLY}",
            json={"expected_version": 0, "name": "X"},
            headers=bearer,
        )

    assert response.status_code == status_code
    error = _envelope(response.json())
    assert error["code"] == code
    # The gateway stamps its own request id, not the upstream one.
    from py_kit import REQUEST_ID_HEADER

    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_upstream_down_maps_to_502_envelope(db_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(db_url, handler) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/assemblies", headers=bearer)

    assert response.status_code == 502
    error = _envelope(response.json())
    assert error["code"] == "upstream_unavailable"
    assert "documents.internal" not in response.text


# --- gateway-side validation (never reaches upstream) ---------------------------


def test_invalid_body_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies", json={"name": "   "}, headers=bearer
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
    assert seen == []


def test_malformed_assembly_id_rejected_at_the_gateway(
    db_url: str, seen: list[httpx.Request]
) -> None:
    with make_client(db_url, _echo_documents(seen)) as client:
        _, bearer = _register(client)
        response = client.get("/api/v1/assemblies/not-a-uuid", headers=bearer)
    assert response.status_code == 422
    assert seen == []
