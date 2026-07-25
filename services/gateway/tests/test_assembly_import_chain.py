"""Assembly STEP upload over the REAL 3-service chain — gateway → geometry → documents.

The permanent cross-service integration gate for the untrusted-upload pillar
(BACKLOG P2: "Assembly import: permanent 3-service HTTP integration test"). The
shipped unit suites cover each half in isolation with the other side mocked
(``test_assembly_import_proxy.py`` mocks both upstreams;
``documents/tests/test_step_import.py`` constructs the geometry read by hand), so
nothing proved that the three services actually compose: that the REAL XCAF
reader's content addresses drive the REAL documents dedup, that the caps hold with
real payloads, and that the parts the import creates are genuinely modelable.

**How it boots (design decision).** All three FastAPI apps run IN-PROCESS behind
``httpx.ASGITransport`` — real HTTP semantics (methods, headers, status codes,
error envelopes, the streamed-body cap) over a real client stack, but no uvicorn,
no ports, no docker. Chosen over spawning uvicorns because it is hermetic
(nothing to leave running, no port collisions with a dev stack on :8000-:8002),
fast enough to live in the DEFAULT ``pytest`` run, and CI-safe with zero
orchestration — the point of the backlog item is that this runs in the normal
suite, not that a human boots something. Postgres is likewise not required: both
stateful services get a scratch SQLite file whose schema is created via
SQLAlchemy ``metadata.create_all`` (the migrations render Postgres-only DDL — see
CLAUDE.md's environment recipe and ``scripts/e2e.sh``, which do the same).
Geometry keeps its in-process LRU mesh store (no ``S3_URL``), and the gateway's
rate limiter is the fail-open no-op (no ``REDIS_URL``). The **deployed**
container path over the network is proven separately by
``scripts/compose-smoke.sh`` + the ``compose-stack-e2e`` CI job; this file owns
assembly-import CORRECTNESS across the service boundary.

Marked ``integration``: it exercises the real OCCT reader (the only gateway test
that does), so it is selectable/skippable (``-m 'not integration'``) — but it is
NOT excluded from the default run.

What it proves end-to-end, with STEP bytes manufactured by the shipped assembly
exporter (the mirror of a user's "open this assembly" upload):

* a repeated part is ONE part document with N placed, named instances — deduped
  by the reader's real content address, not a hand-written id;
* each product's B-rep crosses the gateway→documents hop ONCE per address (the
  shared-``bodies`` transport shape), not once per occurrence;
* the created parts are REAL: evaluating one through the gateway re-solves the
  imported body in the kernel to its authored volume;
* a flat single-body STEP takes the MB-4b fallback (``kind="part"``);
* the defences hold with real payloads: 401 before any hop, the streamed byte cap
  before geometry, the product-count cap before documents, and a name collision
  is a 409 that leaves NO orphan documents.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import NamedTuple

import httpx2 as httpx
import pytest
from build123d import Solid
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.kernel.export import (
    AssemblyComponent,
    export_step_assembly_bytes,
    export_step_bytes,
)
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from py_kit.db import async_dsn
from py_kit.schemas.features import EvaluateTreeResult
from py_kit.schemas.step_import import ImportAssemblyRequest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "integration-jwt-secret-0123456789abcdef"

#: Round-trip tolerance for the placements/volumes this gate compares: the
#: CLAUDE.md kernel linear tolerance (1e-7 mm), the SAME documented bound the
#: geometry suite's ``ROUNDTRIP_TOL`` uses — a ceiling, not a fitted epsilon
#: (docs/GEOMETRY-QA.md). Re-declared rather than imported because pytest's
#: importlib mode blocks cross-member test imports; loosening it is a reviewed
#: decision recorded in docs/GEOMETRY-QA.md, never a quick fix.
ROUNDTRIP_TOL = 1e-7

#: The authored assembly: TWO occurrences of one 10x20x30 bracket (volume 6000 —
#: the dedup case) plus a distinct 4x5x6 pin (volume 120), at distinct poses.
BRACKET_VOLUME = 6000.0
PIN_VOLUME = 120.0
PLACEMENTS = ((0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (0.0, 40.0, 0.0))


def _assembly_step() -> bytes:
    """An AP214 STEP with product structure: bracket, bracket (repeat), pin."""
    bracket = Solid.make_box(10, 20, 30)
    pin = Solid.make_box(4, 5, 6)
    bodies = (bracket, bracket, pin)
    names = ("Bracket", "Bracket", "Pin")
    return export_step_assembly_bytes(
        "chain-asm",
        [
            AssemblyComponent(
                name=name, body=body, translation=where, quaternion=(0, 0, 0, 1)
            )
            for name, body, where in zip(names, bodies, PLACEMENTS, strict=True)
        ],
    )


def _flat_step() -> bytes:
    """A single-body part STEP — no product structure (the MB-4b fallback input)."""
    return export_step_bytes(Solid.make_box(10, 20, 30))


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Delegating transport that records each upstream request body.

    Lets the test inspect what actually crossed a service boundary (e.g. that a
    repeated part's B-rep travelled ONCE) without mocking either side away.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, hops: list[bytes]) -> None:
        self._inner = inner
        self._hops = hops

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._hops.append(await request.aread())
        return await self._inner.handle_async_request(request)


class Chain(NamedTuple):
    """A booted 3-service chain: a client on the gateway + the recorded hops."""

    client: httpx.AsyncClient
    geometry_hops: list[bytes]
    documents_hops: list[bytes]


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    """Create a service's schema on a scratch SQLite file (see module docstring)."""
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run an app's startup/shutdown (ASGITransport does not drive lifespan)."""
    async with app.router.lifespan_context(app):
        yield


@contextlib.asynccontextmanager
async def _chain(tmp_path: Path) -> AsyncGenerator[Chain]:
    """Boot geometry + documents + gateway in-process and yield a gateway client."""
    documents_url = f"sqlite:///{tmp_path}/documents.db"
    gateway_url = f"sqlite:///{tmp_path}/gateway.db"
    await _create_schema(documents_url, DocumentsBase)
    await _create_schema(gateway_url, GatewayBase)

    # Explicit s3_url=None: the in-process LRU mesh store, never a stray ambient
    # S3_URL from the developer's shell (hermetic).
    geometry_app = build_geometry_app(GeometrySettings(s3_url=None))
    documents_app = build_documents_app(
        DocumentsSettings(postgres_url=documents_url, s3_url=None)
    )
    geometry_hops: list[bytes] = []
    documents_hops: list[bytes] = []
    gateway_app = build_gateway_app(
        GatewaySettings(
            geometry_url="http://geometry.internal:8002",
            documents_url="http://documents.internal:8001",
            postgres_url=gateway_url,
            redis_url=None,  # fail-open no-op rate limiter
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        geometry_transport=_RecordingTransport(
            httpx.ASGITransport(geometry_app), geometry_hops
        ),
        documents_transport=_RecordingTransport(
            httpx.ASGITransport(documents_app), documents_hops
        ),
    )
    async with (
        _lifespan(geometry_app),
        _lifespan(documents_app),
        _lifespan(gateway_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway_app),
            base_url="http://gateway.test",
            timeout=60.0,
        ) as client,
    ):
        yield Chain(client, geometry_hops, documents_hops)


async def _register(client: httpx.AsyncClient) -> dict[str, str]:
    """Register a user through the real gateway auth route → bearer headers."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "chain@example.com", "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _upload(
    client: httpx.AsyncClient,
    data: bytes,
    *,
    name: str,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/assemblies/import",
        params={"name": name},
        content=data,
        headers=headers or {},
    )


def _error_code(response: httpx.Response) -> str:
    body = response.json()
    assert set(body) == {"error"}, body
    code: str = body["error"]["code"]
    return code


# --- the happy path: real reader → real dedup → real, modelable parts ------------


def test_chain_imports_repeated_part_once_and_parts_are_modelable(
    tmp_path: Path,
) -> None:
    """One upload → an assembly with 3 placed instances over 2 REAL part documents.

    The dedup is driven by the geometry reader's own content address (identical
    B-rep bytes for the two bracket occurrences), the placements survive the
    export→read→persist chain within the documented kernel tolerance, and the
    created part is genuinely modelable: evaluating it through the gateway
    re-solves the imported body in the kernel to its authored volume. The
    documents hop is checked to carry each body ONCE (the shared-``bodies``
    transport shape), which is the property a per-product body would break.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            headers = await _register(chain.client)
            response = await _upload(
                chain.client, _assembly_step(), name="Gearbox", headers=headers
            )
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["kind"] == "assembly"

            # Repeated part → ONE part document, THREE instances at their poses.
            assert len(body["part_ids"]) == 2
            instances = body["assembly"]["instances"]
            assert [inst["name"] for inst in instances] == [
                "Bracket",
                "Bracket",
                "Pin",
            ]
            for instance, (x, y, z) in zip(instances, PLACEMENTS, strict=True):
                position = instance["placement"]["position"]
                assert position["x"] == pytest.approx(x, abs=ROUNDTRIP_TOL)
                assert position["y"] == pytest.approx(y, abs=ROUNDTRIP_TOL)
                assert position["z"] == pytest.approx(z, abs=ROUNDTRIP_TOL)
            assert instances[0]["ref_document_id"] == instances[1]["ref_document_id"]
            assert instances[0]["ref_document_id"] != instances[2]["ref_document_id"]
            assert [inst["grounded"] for inst in instances] == [True, False, False]

            # The bracket's B-rep crossed the documents hop ONCE, not per instance:
            # TWO bodies for THREE products, and the payload embeds exactly two
            # STEP fragments (one per distinct content address).
            [documents_payload] = chain.documents_hops
            forwarded = ImportAssemblyRequest.model_validate_json(documents_payload)
            assert len(forwarded.result.products) == 3
            assert len(forwarded.result.bodies) == 2
            # One part-21 file trailer per embedded fragment: 2, not 3.
            assert documents_payload.decode().count("END-ISO-10303-21;") == 2
            # Every product still resolves its body through the shared map.
            assert all(
                forwarded.result.body_step_for(product) is not None
                for product in forwarded.result.products
            )

            # The imported parts are REAL: evaluate one through the chain and get
            # the authored volume back out of the kernel.
            volumes: list[float] = []
            for part_id in body["part_ids"]:
                evaluated = await chain.client.post(
                    f"/api/v1/parts/{part_id}/evaluate", headers=headers
                )
                assert evaluated.status_code == 200, evaluated.text
                result = EvaluateTreeResult.model_validate_json(evaluated.content)
                assert [feature.status for feature in result.features] == ["ok"]
                assert result.mesh_glb_id is not None
                assert result.properties is not None
                volumes.append(result.properties.volume)
            assert sorted(volumes) == [
                pytest.approx(PIN_VOLUME, abs=ROUNDTRIP_TOL),
                pytest.approx(BRACKET_VOLUME, abs=ROUNDTRIP_TOL),
            ]

    asyncio.run(scenario())


def test_chain_flat_step_falls_back_to_single_body_part(tmp_path: Path) -> None:
    """A flat (structure-less) STEP → the MB-4b single-body part, no assembly."""

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            headers = await _register(chain.client)
            response = await _upload(
                chain.client, _flat_step(), name="Widget", headers=headers
            )
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["kind"] == "part"
            assert body["part"]["name"] == "Widget"
            assert body["tree_version"] == 1

            listed = await chain.client.get("/api/v1/assemblies", headers=headers)
            assert listed.json()["assemblies"] == []
            evaluated = await chain.client.post(
                f"/api/v1/parts/{body['part']['id']}/evaluate", headers=headers
            )
            assert evaluated.status_code == 200, evaluated.text
            result = EvaluateTreeResult.model_validate_json(evaluated.content)
            assert result.properties is not None
            assert result.properties.volume == pytest.approx(
                BRACKET_VOLUME, abs=ROUNDTRIP_TOL
            )

    asyncio.run(scenario())


# --- the defences, with real payloads on the real chain ---------------------------


def test_chain_rejects_unauthenticated_upload_before_any_hop(tmp_path: Path) -> None:
    """No bearer → 401 and NEITHER upstream is touched (nothing is parsed)."""

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            response = await _upload(chain.client, _assembly_step(), name="Gearbox")
            assert response.status_code == 401
            assert _error_code(response) == "unauthorized"
            assert chain.geometry_hops == []
            assert chain.documents_hops == []

    asyncio.run(scenario())


def test_chain_oversize_upload_is_capped_before_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The streamed byte cap fires at the gateway — geometry never sees the bytes."""

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            headers = await _register(chain.client)
            monkeypatch.setattr("gateway.step_import.MAX_STEP_UPLOAD_BYTES", 512)
            response = await _upload(
                chain.client, _assembly_step(), name="Gearbox", headers=headers
            )
            assert response.status_code == 422
            assert _error_code(response) == "import_too_large"
            assert chain.geometry_hops == []
            assert chain.documents_hops == []

    asyncio.run(scenario())


def test_chain_product_count_cap_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over the occurrence ceiling → 422 after geometry, BEFORE documents.

    The real read returns 3 products; with the ceiling lowered to 2 the gateway
    rejects and documents is never driven, so no partial assembly exists.
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            headers = await _register(chain.client)
            monkeypatch.setattr("gateway.step_import.MAX_IMPORT_ASSEMBLY_PRODUCTS", 2)
            response = await _upload(
                chain.client, _assembly_step(), name="Gearbox", headers=headers
            )
            assert response.status_code == 422
            error = response.json()["error"]
            assert error["code"] == "import_too_many_products"
            assert error["details"]["max_products"] == 2
            assert len(chain.geometry_hops) == 1  # geometry ran; documents did not
            assert chain.documents_hops == []
            assemblies = await chain.client.get("/api/v1/assemblies", headers=headers)
            assert assemblies.json()["assemblies"] == []
            parts = await chain.client.get("/api/v1/parts", headers=headers)
            assert parts.json()["parts"] == []

    asyncio.run(scenario())


def test_chain_name_collision_is_409_leaving_no_orphan_documents(
    tmp_path: Path,
) -> None:
    """Re-importing under a taken name → 409, and the second attempt persists NOTHING.

    The atomicity claim across the real boundary: the part count is unchanged by
    the rejected import (no orphan parts from the rolled-back transaction).
    """

    async def scenario() -> None:
        async with _chain(tmp_path) as chain:
            headers = await _register(chain.client)
            data = _assembly_step()
            first = await _upload(chain.client, data, name="Gearbox", headers=headers)
            assert first.status_code == 201, first.text

            second = await _upload(chain.client, data, name="Gearbox", headers=headers)
            assert second.status_code == 409
            assert _error_code(second) == "assembly_name_taken"

            parts = await chain.client.get("/api/v1/parts", headers=headers)
            assert len(parts.json()["parts"]) == 2  # only the first import's parts
            assemblies = await chain.client.get("/api/v1/assemblies", headers=headers)
            assert len(assemblies.json()["assemblies"]) == 1

    asyncio.run(scenario())
