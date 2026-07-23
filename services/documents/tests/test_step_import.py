"""documents step-import — assembly/single-body creation from a geometry read.

Runs the SAME application code against SQLite (always) and a real scratch
PostgreSQL with the actual migrations applied — see conftest.py for the dialect
split. Exercises the SLICE-2b documents contract (docs/design/step-import.md):
turning a :class:`~py_kit.schemas.step_import.StepAssemblyImportResult` into a
real Loft graph — an assembly with deduped parts + named instances at their
placements, or the single-body MB-4b fallback — atomically (a rejected import
leaves no orphan documents).

The geometry read is CONSTRUCTED here as plain pydantic (no kernel, no OCP): the
true STEP-bytes round-trip (``export_step_assembly_bytes`` → geometry reader →
this endpoint) is a geometry/e2e gate. These tests own the documents logic:
dedup by ``body_step_id``, placement/name preservation, the fallback, the
count/no-solid caps, name-collision atomicity, and auth.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.schemas.assemblies import Placement, Quat
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.parts import PRINCIPAL_HEADER
from py_kit.schemas.step_import import (
    MAX_IMPORT_ASSEMBLY_PRODUCTS,
    ImportAssemblyRequest,
    ImportedProduct,
    StepAssemblyImportResult,
)

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"

BODY_A = "sha256:" + "a" * 64
BODY_B = "sha256:" + "b" * 64
STEP_A = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n/* body A */\nENDSEC;\n"
STEP_B = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n/* body B */\nENDSEC;\n"


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _pos(x: float, y: float, z: float) -> Placement:
    return Placement(position=Vec3(x=x, y=y, z=z), orientation=Quat(x=0, y=0, z=0, w=1))


def _product(
    *,
    name: str | None,
    body_id: str | None,
    body_step: str | None,
    placement: Placement,
) -> ImportedProduct:
    return ImportedProduct(
        name=name,
        placement=placement,
        body_step=body_step,
        body_step_id=body_id,
        mesh_glb_id=None,
    )


def _post_import(
    client: TestClient,
    *,
    name: str,
    has_structure: bool,
    products: list[ImportedProduct],
    owner: str = OWNER,
    with_principal: bool = True,
) -> Any:
    request = ImportAssemblyRequest(
        name=name,
        result=StepAssemblyImportResult(
            has_assembly_structure=has_structure, products=products
        ),
    )
    headers = _headers(owner) if with_principal else {}
    return client.post(
        "/api/v1/step-import",
        content=request.model_dump_json(),
        headers={"content-type": "application/json", **headers},
    )


def _error(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


# --- assembly: dedup + named instances at placements ------------------------------


def test_assembly_import_dedups_parts_and_places_instances(client: TestClient) -> None:
    """A ≥2-instance assembly incl. a REPEATED part → one part doc / two instances.

    Three products: two occurrences of ONE body (BODY_A) at distinct placements
    plus a third distinct body (BODY_B). The repeated body collapses to ONE part
    document referenced by TWO instances; every instance keeps its name and
    placement.
    """
    products = [
        _product(
            name="Bracket", body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)
        ),
        _product(
            name="Bracket", body_id=BODY_A, body_step=STEP_A, placement=_pos(10, 0, 5)
        ),
        _product(name="Pin", body_id=BODY_B, body_step=STEP_B, placement=_pos(0, 7, 0)),
    ]
    response = _post_import(
        client, name="Gearbox", has_structure=True, products=products
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "assembly"

    # Two deduped part documents (BODY_A once, BODY_B once).
    assert len(body["part_ids"]) == 2
    parts = client.get("/api/v1/parts", headers=_headers()).json()["parts"]
    assert len(parts) == 2

    instances = body["assembly"]["instances"]
    assert len(instances) == 3
    assert [inst["name"] for inst in instances] == ["Bracket", "Bracket", "Pin"]
    assert [inst["placement"]["position"] for inst in instances] == [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"x": 10.0, "y": 0.0, "z": 5.0},
        {"x": 0.0, "y": 7.0, "z": 0.0},
    ]
    # The repeated part: instances 0 and 1 reference ONE part; instance 2 another.
    assert instances[0]["ref_document_id"] == instances[1]["ref_document_id"]
    assert instances[0]["ref_document_id"] != instances[2]["ref_document_id"]
    # The first instance is grounded (the imported anchor); the rest float.
    assert [inst["grounded"] for inst in instances] == [True, False, False]

    # Each part carries exactly the import feature seeded from its body_step.
    shared_part = instances[0]["ref_document_id"]
    tree = client.get(
        f"/api/v1/parts/{shared_part}/features", headers=_headers()
    ).json()
    assert len(tree["features"]) == 1
    feature = tree["features"][0]["feature"]
    assert feature["type"] == "import"
    assert feature["params"]["data"] == STEP_A


def test_assembly_import_names_instances_from_fallback_when_unnamed(
    client: TestClient,
) -> None:
    """A product with no PRODUCT name gets a positional instance name."""
    products = [
        _product(name=None, body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)),
        _product(name=None, body_id=BODY_B, body_step=STEP_B, placement=_pos(1, 0, 0)),
    ]
    response = _post_import(client, name="Rig", has_structure=True, products=products)
    assert response.status_code == 201, response.text
    names = [inst["name"] for inst in response.json()["assembly"]["instances"]]
    assert names == ["Instance <1>", "Instance <2>"]


# --- single-body fallback (MB-4b, backward compatible) ----------------------------


def test_flat_single_body_fallback(client: TestClient) -> None:
    """A flat STEP (no product structure) → one single-body part, no assembly."""
    products = [
        _product(
            name="Widget", body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)
        )
    ]
    response = _post_import(
        client, name="Widget Part", has_structure=False, products=products
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "part"
    assert body["part"]["name"] == "Widget Part"
    assert body["tree_version"] == 1

    assert (
        client.get("/api/v1/assemblies", headers=_headers()).json()["assemblies"] == []
    )
    parts = client.get("/api/v1/parts", headers=_headers()).json()["parts"]
    assert len(parts) == 1
    tree = client.get(
        f"/api/v1/parts/{parts[0]['id']}/features", headers=_headers()
    ).json()
    assert tree["features"][0]["feature"]["params"]["data"] == STEP_A


# --- rejections leave NO orphan documents (atomicity) -----------------------------


def test_no_solid_products_422_no_orphans(client: TestClient) -> None:
    products = [
        _product(name="Empty", body_id=None, body_step=None, placement=_pos(0, 0, 0))
    ]
    response = _post_import(client, name="Void", has_structure=True, products=products)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "import_no_solid"
    assert (
        client.get("/api/v1/assemblies", headers=_headers()).json()["assemblies"] == []
    )
    assert client.get("/api/v1/parts", headers=_headers()).json()["parts"] == []


def test_product_count_cap_422_no_orphans(client: TestClient) -> None:
    products = [
        _product(
            name=f"P{i}",
            body_id="sha256:" + f"{i:064d}",
            body_step=STEP_A,
            placement=_pos(float(i), 0, 0),
        )
        for i in range(MAX_IMPORT_ASSEMBLY_PRODUCTS + 1)
    ]
    response = _post_import(client, name="Huge", has_structure=True, products=products)
    assert response.status_code == 422
    error = _error(response.json())
    assert error["code"] == "import_too_many_products"
    assert error["details"]["max_products"] == MAX_IMPORT_ASSEMBLY_PRODUCTS
    assert (
        client.get("/api/v1/assemblies", headers=_headers()).json()["assemblies"] == []
    )
    assert client.get("/api/v1/parts", headers=_headers()).json()["parts"] == []


def test_assembly_name_collision_409_no_orphans(client: TestClient) -> None:
    """An assembly-name clash rolls back BEFORE any part is created."""
    made = client.post("/api/v1/assemblies", json={"name": "Dup"}, headers=_headers())
    assert made.status_code == 201, made.text
    products = [
        _product(
            name="Bracket", body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)
        )
    ]
    response = _post_import(client, name="Dup", has_structure=True, products=products)
    assert response.status_code == 409
    assert _error(response.json())["code"] == "assembly_name_taken"
    # The would-be part never persisted (early flush + rollback).
    assert client.get("/api/v1/parts", headers=_headers()).json()["parts"] == []


# --- auth ------------------------------------------------------------------------


def test_missing_principal_is_401(client: TestClient) -> None:
    products = [
        _product(
            name="Bracket", body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)
        )
    ]
    response = _post_import(
        client,
        name="Gearbox",
        has_structure=True,
        products=products,
        with_principal=False,
    )
    assert response.status_code == 401
    assert _error(response.json())["code"] == "missing_principal"


def test_owner_scoping_part_names_dont_collide_across_owners(
    client: TestClient,
) -> None:
    """Two owners can each import a part with the SAME name (per-owner uniqueness)."""
    products = [
        _product(
            name="Bracket", body_id=BODY_A, body_step=STEP_A, placement=_pos(0, 0, 0)
        )
    ]
    first = _post_import(client, name="A1", has_structure=True, products=products)
    assert first.status_code == 201, first.text
    other = "6f3f6b64-0000-4000-8000-00000000000b"
    second = _post_import(
        client, name="A2", has_structure=True, products=products, owner=other
    )
    assert second.status_code == 201, second.text
