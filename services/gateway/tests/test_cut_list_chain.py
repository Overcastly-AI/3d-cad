"""The cut list over the REAL 3-service chain (CUT-LIST).

The B1 deck, authored as ONE custom feature of the ``test.deck_b1`` fixture
plugin (installed in documents for this test; the DECK plugin does not exist
yet), through the public API in an inch document. The gateway joins
documents' member metadata with geometry's measurements: the part's cut list
must equal the buildings.md table and its CSV the hand-written one. An
assembly placing the deck twice lists every member twice (all levels, times
the quantity), and an assembly CSV downloads. Boots like
``test_assembly_extents_chain`` (all three apps in-process, scratch SQLite).
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from documents import custom_features
from documents.db import Base as DocumentsBase
from documents.main import DocumentsSettings
from documents.main import build_app as build_documents_app
from fastapi import FastAPI
from gateway.db import Base as GatewayBase
from gateway.main import GatewaySettings
from gateway.main import build_app as build_gateway_app
from geometry.main import GeometrySettings
from geometry.main import build_app as build_geometry_app
from loft_plugins import REGISTRY, PluginRegistry
from loft_plugins.testing_deck import DECK_B1
from loft_wire.cut_list import CutListResponse
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

pytestmark = pytest.mark.integration

TEST_JWT_SECRET = "cut-list-chain-jwt-secret-0123456789abcdef"
IN = 25.4

#: buildings.md B1, typed by hand: member, profile, qty, length (in), stock.
B1_TABLE = [
    ("Ledger", "2x10", 1, 192.0, 16),
    ("Rim", "2x10", 1, 192.0, 16),
    ("Beam", "2x10", 2, 192.0, 16),
    ("Joist", "2x10", 13, 141.0, 12),
    ("Post", "6x6", 3, 10.5, 8),
    ("Deck", "5/4x6", 26, 192.0, 16),
]

_PT = '"Southern pine, pressure-treated"'
B1_CSV = (
    "Item,Member,Profile,Section (in),Material,Qty,Length (in),"
    "Total length (in),Stock,Waste each (in)\r\n"
    f"1,Ledger,2x10,1.5 x 9.25,{_PT},1,192,192,16 ft,0\r\n"
    f"2,Rim,2x10,1.5 x 9.25,{_PT},1,192,192,16 ft,0\r\n"
    f"3,Beam,2x10,1.5 x 9.25,{_PT},2,192,384,16 ft,0\r\n"
    f"4,Joist,2x10,1.5 x 9.25,{_PT},13,141,1833,12 ft,3\r\n"
    f"5,Post,6x6,5.5 x 5.5,{_PT},3,10.5,31.5,8 ft,85.5\r\n"
    f"6,Deck,5/4x6,1 x 5.5,{_PT},26,192,4992,16 ft,0\r\n"
)


@pytest.fixture(autouse=True)
def _deck_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real plugins plus the deck fixture, for this test only."""
    registry = PluginRegistry([DECK_B1, REGISTRY.get("loft.twisted_prism", "1.0.0")])
    monkeypatch.setattr(custom_features, "PLUGINS", registry)


async def _create_schema(url: str, base: type[DeclarativeBase]) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    await engine.dispose()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.router.lifespan_context(app):
        yield


@contextlib.asynccontextmanager
async def _chain(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    documents_url = f"sqlite:///{tmp_path}/documents.db"
    gateway_url = f"sqlite:///{tmp_path}/gateway.db"
    await _create_schema(documents_url, DocumentsBase)
    await _create_schema(gateway_url, GatewayBase)
    geometry_app = build_geometry_app(GeometrySettings(s3_url=None))
    documents_app = build_documents_app(
        DocumentsSettings(postgres_url=documents_url, s3_url=None)
    )
    gateway_app = build_gateway_app(
        GatewaySettings(
            geometry_url="http://geometry.internal:8002",
            documents_url="http://documents.internal:8001",
            postgres_url=gateway_url,
            redis_url=None,
            loft_env="dev",
            jwt_secret=TEST_JWT_SECRET,
        ),
        geometry_transport=httpx.ASGITransport(geometry_app),
        documents_transport=httpx.ASGITransport(documents_app),
    )
    async with (
        _lifespan(geometry_app),
        _lifespan(documents_app),
        _lifespan(gateway_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway_app),
            base_url="http://gateway.test",
            timeout=120.0,
        ) as client,
    ):
        yield client


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "hunter2-passphrase"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _deck(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    part = await client.post(
        "/api/v1/parts", json={"name": "B1 deck", "length_unit": "in"}, headers=headers
    )
    assert part.status_code == 201, part.text
    part_id: str = part.json()["id"]
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "test.deck_b1",
            "plugin_version": "1.0.0",
            "inputs": {},
        },
    }
    created = await client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Deck", "feature": feature, "expected_tree_version": 0},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return part_id


def _table(cut_list: CutListResponse, scale: int = 1) -> list[tuple[Any, ...]]:
    return [
        (
            line.member,
            line.profile,
            line.quantity // scale,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]


async def _assembly(
    client: httpx.AsyncClient, headers: dict[str, str], part_id: str
) -> tuple[str, int, list[str]]:
    assembly = await client.post(
        "/api/v1/assemblies",
        json={"name": "Two decks", "length_unit": "in"},
        headers=headers,
    )
    assert assembly.status_code == 201, assembly.text
    assembly_id: str = assembly.json()["id"]
    version: int = assembly.json()["doc_version"]
    instance_ids: list[str] = []
    for n in range(2):
        created = await client.post(
            f"/api/v1/assemblies/{assembly_id}/instances",
            json={
                "expected_version": version,
                "ref_document_id": part_id,
                "ref_document_kind": "part",
                "name": f"Deck <{n + 1}>",
                "placement": {
                    "position": {"x": 6000.0 * n, "y": 0.0, "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                "grounded": True,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        version = created.json()["doc_version"]
        instance_ids.append(created.json()["instance"]["id"])
    return assembly_id, version, instance_ids


def test_the_b1_cut_list_through_the_gateway(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with _chain(tmp_path) as client:
            owner = await _register(client, "framer@example.com")
            part_id = await _deck(client, owner)

            response = await client.get(
                f"/api/v1/parts/{part_id}/cut-list", headers=owner
            )
            assert response.status_code == 200, response.text
            cut_list = CutListResponse.model_validate_json(response.content)
            assert (cut_list.name, cut_list.length_unit) == ("B1 deck", "in")
            assert _table(cut_list) == B1_TABLE
            assert cut_list.total_quantity == 46

            csv = await client.get(
                f"/api/v1/parts/{part_id}/cut-list/csv", headers=owner
            )
            assert csv.status_code == 200, csv.text
            assert csv.headers["content-type"] == "text/csv; charset=utf-8"
            assert (
                'filename="B1 deck cut list.csv"' in csv.headers["content-disposition"]
            )
            assert csv.content.decode("utf-8") == B1_CSV

            assembly_id, version, decks = await _assembly(client, owner, part_id)
            response = await client.get(
                f"/api/v1/assemblies/{assembly_id}/cut-list", headers=owner
            )
            assert response.status_code == 200, response.text
            doubled = CutListResponse.model_validate_json(response.content)
            assert doubled.document_kind == "assembly"
            assert all(line.quantity % 2 == 0 for line in doubled.lines)
            assert _table(doubled, scale=2) == B1_TABLE
            assert doubled.total_quantity == 92
            csv = await client.get(
                f"/api/v1/assemblies/{assembly_id}/cut-list/csv", headers=owner
            )
            assert csv.status_code == 200, csv.text
            assert (
                csv.content.decode()
                .splitlines()[4]
                .startswith("4,Joist,2x10,1.5 x 9.25,")
            )
            assert ",26,141,3666,12 ft,3" in csv.content.decode()

            # Mirror both decks about YZ: deck 1 as a mirrored copy, deck 2 as
            # an opposite hand (its own BOM line, ASM-MIRROR-COMPONENT). A
            # mirror image has the same members, so all four decks list on
            # the same lines, each measured once per part.
            mirrored = await client.post(
                f"/api/v1/assemblies/{assembly_id}/mirrors",
                json={
                    "expected_version": version,
                    "mirror": {
                        "seed_instance_ids": decks,
                        "plane": {
                            "kind": "origin_plane",
                            "plane": "yz",
                            "offset_mm": -1000.0,
                        },
                        "opposite_hand_instance_ids": [decks[1]],
                    },
                },
                headers=owner,
            )
            assert mirrored.status_code == 201, mirrored.text
            bom = await client.get(
                f"/api/v1/assemblies/{assembly_id}/bom", headers=owner
            )
            hands = [
                line.get("opposite_hand", False) for line in bom.json()["parts_only"]
            ]
            assert sorted(hands) == [False, True]
            response = await client.get(
                f"/api/v1/assemblies/{assembly_id}/cut-list", headers=owner
            )
            assert response.status_code == 200, response.text
            four = CutListResponse.model_validate_json(response.content)
            assert _table(four, scale=4) == B1_TABLE
            assert all(line.quantity % 4 == 0 for line in four.lines)
            assert four.total_quantity == 184

            # Another account's part is the documents 404; no token is a 401.
            other = await _register(client, "other@example.com")
            foreign = await client.get(
                f"/api/v1/parts/{part_id}/cut-list", headers=other
            )
            assert foreign.status_code == 404
            anonymous = await client.get(f"/api/v1/parts/{part_id}/cut-list")
            assert anonymous.status_code == 401

    asyncio.run(scenario())
