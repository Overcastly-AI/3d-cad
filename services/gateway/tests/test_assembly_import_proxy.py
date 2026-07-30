"""gateway assembly STEP upload — auth, size cap, product-count cap, forwarding.

Same harness as tests/test_step_import_proxy.py, but the upload drives TWO
upstream hops: an identity-free geometry ``/assembly/import`` read, then the
authenticated documents ``/step-import`` creation. Both upstreams are
``httpx.MockTransport`` handlers; auth runs for real (register → bearer) over
the SQLite test DB. The geometry mock returns a CONSTRUCTED
:class:`StepAssemblyImportResult` shaped like the real XCAF reader's output (the
true bytes round-trip is a geometry/e2e gate) so the gateway wiring — size cap
BEFORE forwarding, identity-free geometry hop, product-count cap BEFORE
documents, principal-attached documents hop, envelope pass-through — is proven
here.
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
    AssemblyGraphResponse,
    AssemblyResponse,
    InstanceResponse,
    Placement,
    Quat,
)
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.parts import PRINCIPAL_HEADER, PartResponse
from py_kit.schemas.step_import import (
    MAX_IMPORT_ASSEMBLY_PRODUCTS,
    AssemblyImportResult,
    ImportAssemblyRequest,
    ImportedProduct,
    SingleBodyImportResult,
    StepAssemblyImportRequest,
    StepAssemblyImportResult,
)
from sqlalchemy.ext.asyncio import create_async_engine

TEST_JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"
Handler = Callable[[httpx.Request], httpx.Response]
NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)

BODY_A = "sha256:" + "a" * 64
BODY_B = "sha256:" + "b" * 64

ASSEMBLY_STEP = (
    "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\n"
    "DATA;\n#1=NEXT_ASSEMBLY_USAGE_OCCURRENCE('','',$,#2,#3,$);\nENDSEC;\n"
    "END-ISO-10303-21;\n"
)


def _pos(x: float, y: float, z: float) -> Placement:
    return Placement(position=Vec3(x=x, y=y, z=z), orientation=Quat(x=0, y=0, z=0, w=1))


def _body_text(body_id: str) -> str:
    """A distinct STEP fragment per content address (so hops can be byte-counted)."""
    return f"ISO-10303-21;\nDATA;\n/* body {body_id[7:11]} */\nENDSEC;\n"


def _product(
    name: str | None, body_id: str | None, placement: Placement
) -> ImportedProduct:
    return ImportedProduct(
        name=name,
        placement=placement,
        body_step=None if body_id is None else _body_text(body_id),
        body_step_id=body_id,
        mesh_glb_id=None,
    )


def _assembly_read(products: list[ImportedProduct]) -> StepAssemblyImportResult:
    return StepAssemblyImportResult(has_assembly_structure=True, products=products)


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


def make_client(db_url: str, geometry: Handler, documents: Handler) -> TestClient:
    settings = GatewaySettings(
        geometry_url="http://geometry.internal:8002",
        documents_url="http://documents.internal:8001",
        postgres_url=db_url,
        loft_env="dev",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = build_app(
        settings,
        geometry_transport=httpx.MockTransport(geometry),
        documents_transport=httpx.MockTransport(documents),
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
    return error


def _geometry_returns(
    read: StepAssemblyImportResult, seen: list[httpx.Request]
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=read.model_dump_json())

    return handler


def _documents_echo(seen: list[httpx.Request]) -> Handler:
    """A canned documents upstream that creates an assembly graph from the read."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = ImportAssemblyRequest.model_validate_json(request.content)
        owner = uuid.UUID(request.headers[PRINCIPAL_HEADER])
        assembly_id = uuid.uuid4()
        # Dedup parts by body_step_id, one instance per product (mirrors docs).
        part_by_body: dict[str, uuid.UUID] = {}
        instances: list[InstanceResponse] = []
        for index, product in enumerate(body.result.products):
            assert product.body_step_id is not None
            part_id = part_by_body.setdefault(product.body_step_id, uuid.uuid4())
            instances.append(
                InstanceResponse(
                    id=uuid.uuid4(),
                    assembly_id=assembly_id,
                    ref_document_id=part_id,
                    ref_document_kind="part",
                    ref_pinned_version=None,
                    name=product.name or f"Instance <{index + 1}>",
                    placement=product.placement,
                    grounded=index == 0,
                    order_index=index,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        graph = AssemblyGraphResponse(
            assembly=AssemblyResponse(
                id=assembly_id,
                name=body.name,
                owner_id=owner,
                length_unit="mm",
                doc_version=len(instances),
                created_at=NOW,
                updated_at=NOW,
            ),
            doc_version=len(instances),
            instances=instances,
            mates=[],
            can_undo=False,
            can_redo=False,
        )
        result = AssemblyImportResult(
            assembly=graph, part_ids=list(part_by_body.values())
        )
        return httpx.Response(201, content=result.model_dump_json())

    return handler


def _documents_unreached() -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("documents must not be reached")

    return handler


def _geometry_unreached() -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("geometry must not be reached")

    return handler


# --- auth ------------------------------------------------------------------------


def test_unauthenticated_401_and_nothing_forwarded(db_url: str) -> None:
    geo_seen: list[httpx.Request] = []
    with make_client(
        db_url, _geometry_returns(_assembly_read([]), geo_seen), _documents_unreached()
    ) as client:
        response = client.post(
            "/api/v1/assemblies/import", content=ASSEMBLY_STEP.encode()
        )
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "unauthorized"
    assert geo_seen == []  # never even hit geometry


# --- happy path: an assembly with named instances at placements ------------------


def test_upload_creates_assembly_with_named_placed_instances(db_url: str) -> None:
    """A ≥2-instance read incl. a repeated part → an assembly; identity-free geo hop."""
    products = [
        _product("Bracket", BODY_A, _pos(0, 0, 0)),
        _product("Bracket", BODY_A, _pos(10, 0, 5)),  # repeated part
        _product("Pin", BODY_B, _pos(0, 7, 0)),
    ]
    geo_seen: list[httpx.Request] = []
    doc_seen: list[httpx.Request] = []
    with make_client(
        db_url,
        _geometry_returns(_assembly_read(products), geo_seen),
        _documents_echo(doc_seen),
    ) as client:
        user_id, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            params={"name": "Gearbox"},
            content=ASSEMBLY_STEP.encode(),
            headers=bearer,
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "assembly"
    instances = body["assembly"]["instances"]
    assert [inst["name"] for inst in instances] == ["Bracket", "Bracket", "Pin"]
    assert [inst["placement"]["position"]["x"] for inst in instances] == [
        0.0,
        10.0,
        0.0,
    ]
    assert len(body["part_ids"]) == 2  # repeated part deduped

    # Geometry hop carried the STEP text and NO principal (identity-free).
    [geo_req] = geo_seen
    assert geo_req.url.path == "/api/v1/assembly/import"
    assert PRINCIPAL_HEADER not in geo_req.headers
    assert StepAssemblyImportRequest.model_validate_json(geo_req.content).data == (
        ASSEMBLY_STEP
    )
    # Documents hop carried the verified principal + the geometry read verbatim.
    [doc_req] = doc_seen
    assert doc_req.url.path == "/api/v1/step-import"
    assert doc_req.headers[PRINCIPAL_HEADER] == user_id
    forwarded = ImportAssemblyRequest.model_validate_json(doc_req.content)
    assert forwarded.name == "Gearbox"
    assert len(forwarded.result.products) == 3
    # The repeated part's B-rep crossed BOTH hops once, not once per occurrence
    # (bodies are carried per content address — the transport reshape).
    assert set(forwarded.result.bodies) == {BODY_A, BODY_B}
    assert doc_req.content.decode().count("/* body aaaa */") == 1
    # …and each product still resolves its body through the shared map.
    assert [
        forwarded.result.body_step_for(product) for product in forwarded.result.products
    ] == [_body_text(BODY_A), _body_text(BODY_A), _body_text(BODY_B)]


def test_flat_single_body_fallback_passes_through(db_url: str) -> None:
    """A flat read → the documents single-body result is surfaced verbatim."""
    part_id = uuid.uuid4()

    def documents(request: httpx.Request) -> httpx.Response:
        result = SingleBodyImportResult(
            part=PartResponse(
                id=part_id,
                name="Widget",
                owner_id=uuid.UUID(request.headers[PRINCIPAL_HEADER]),
                length_unit="mm",
                # One import feature in, so the tree sits at version 1 (the same
                # token the sibling `tree_version` below reports).
                tree_version=1,
                # A freshly imported part has never been evaluated (§4.4a).
                eval_state="never",
                last_eval_status=None,
                last_eval_at=None,
                last_eval_tree_version=None,
                created_at=NOW,
                updated_at=NOW,
            ),
            tree_version=1,
        )
        return httpx.Response(201, content=result.model_dump_json())

    flat = StepAssemblyImportResult(
        has_assembly_structure=False,
        products=[_product("Widget", BODY_A, _pos(0, 0, 0))],
    )
    with make_client(db_url, _geometry_returns(flat, []), documents) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            params={"name": "Widget"},
            content=ASSEMBLY_STEP.encode(),
            headers=bearer,
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "part"
    assert body["part"]["id"] == str(part_id)


# --- size cap (before ANY upstream) ----------------------------------------------


def test_oversize_declared_length_is_422_before_forwarding(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gateway.step_import.MAX_STEP_UPLOAD_BYTES", 64)
    with make_client(db_url, _geometry_unreached(), _documents_unreached()) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            content=b"ISO-10303-21;" + b"x" * 200,
            headers=bearer,
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_too_large"


def test_empty_and_non_step_are_422_before_forwarding(db_url: str) -> None:
    with make_client(db_url, _geometry_unreached(), _documents_unreached()) as client:
        _, bearer = _register(client)
        empty = client.post(
            "/api/v1/assemblies/import", content=b"   \n ", headers=bearer
        )
        junk = client.post(
            "/api/v1/assemblies/import", content=b"not a step file", headers=bearer
        )
    assert empty.status_code == 422
    assert _envelope(empty.json())["code"] == "import_empty"
    assert junk.status_code == 422
    assert _envelope(junk.json())["code"] == "import_not_step"


# --- product-count cap (after geometry, BEFORE documents) ------------------------


def test_product_count_cap_rejects_before_documents(db_url: str) -> None:
    """A pathological occurrence count is rejected before documents is driven."""
    products = [
        _product(f"P{i}", "sha256:" + f"{i:064d}", _pos(float(i), 0, 0))
        for i in range(MAX_IMPORT_ASSEMBLY_PRODUCTS + 1)
    ]
    geo_seen: list[httpx.Request] = []
    with make_client(
        db_url,
        _geometry_returns(_assembly_read(products), geo_seen),
        _documents_unreached(),
    ) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            content=ASSEMBLY_STEP.encode(),
            headers=bearer,
        )
    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "import_too_many_products"
    assert error["details"]["max_products"] == MAX_IMPORT_ASSEMBLY_PRODUCTS
    assert len(geo_seen) == 1  # geometry was hit; documents was not


# --- upstream error pass-through -------------------------------------------------


def test_geometry_no_solid_envelope_is_resurfaced(db_url: str) -> None:
    def geometry(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "import_no_solid",
                    "message": "The imported STEP produced no solid body.",
                    "details": None,
                    "request_id": "geo-id",
                }
            },
        )

    with make_client(db_url, geometry, _documents_unreached()) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            content=ASSEMBLY_STEP.encode(),
            headers=bearer,
        )
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "import_no_solid"


def test_documents_name_collision_envelope_is_resurfaced(db_url: str) -> None:
    def documents(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "assembly_name_taken",
                    "message": "An assembly named 'Gearbox' already exists.",
                    "details": None,
                    "request_id": "doc-id",
                }
            },
        )

    products = [_product("Bracket", BODY_A, _pos(0, 0, 0))]
    with make_client(
        db_url, _geometry_returns(_assembly_read(products), []), documents
    ) as client:
        _, bearer = _register(client)
        response = client.post(
            "/api/v1/assemblies/import",
            params={"name": "Gearbox"},
            content=ASSEMBLY_STEP.encode(),
            headers=bearer,
        )
    assert response.status_code == 409
    assert _envelope(response.json())["code"] == "assembly_name_taken"
