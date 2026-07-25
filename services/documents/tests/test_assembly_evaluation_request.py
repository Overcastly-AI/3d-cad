"""documents assembly evaluation-request — the design §4/§7 graph handover.

``GET /api/v1/assemblies/{assembly_id}/evaluation-request`` must serve exactly
what the geometry service solves: the instance + mate graph resolved to the
reused ``EvaluateAssemblyRequest`` — each PART instance carrying its referenced
part's rollback-applied, upcast feature prefix (the SAME
``documents.features.evaluation_prefix`` the part evaluation-request serves —
one implementation, DRY), the dedup ``part_key``, the authored seed placement +
grounded flag, and the mates in ``order_index`` order.

Degradation is typed, never a 500 (design §4): a rigid SUB-ASSEMBLY instance
(nested flatten deferred in v1) and a dangling part reference each contribute an
EMPTY feature prefix, which geometry reports as that instance's typed
``no_body`` (dropped from the projection; the rest still project).

Same dialect posture as tests/test_assemblies.py: SQLite always, real scratch
PostgreSQL (actual migrations) when server binaries are available.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents.db import Part
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn
from py_kit.schemas.assemblies import EvaluateAssemblyRequest, LockMate
from py_kit.schemas.features import SketchFeature
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"

#: A minimal valid sketch body (one line, one anchor) — this suite tests the
#: documents-side graph resolution, not solving.
SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        },
    ],
    "constraints": [
        {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
    ],
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _create_part(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_sketch(client: TestClient, part_id: str, name: str, version: int) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
            "expected_tree_version": version,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _create_assembly(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/assemblies", json={"name": name}, headers=_headers()
    )
    assert response.status_code == 201, response.text
    assembly_id: str = response.json()["id"]
    return assembly_id


def _add_instance(
    client: TestClient,
    assembly_id: str,
    ref_document_id: str,
    expected_version: int,
    *,
    ref_document_kind: str = "part",
    name: str = "Part <1>",
    grounded: bool = False,
    placement: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "ref_document_id": ref_document_id,
        "ref_document_kind": ref_document_kind,
        "name": name,
        "grounded": grounded,
    }
    if placement is not None:
        payload["placement"] = placement
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json=payload,
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    instance_id: str = response.json()["instance"]["id"]
    return instance_id


def _evaluation_request(
    client: TestClient, assembly_id: str
) -> EvaluateAssemblyRequest:
    response = client.get(
        f"/api/v1/assemblies/{assembly_id}/evaluation-request", headers=_headers()
    )
    assert response.status_code == 200, response.text
    return EvaluateAssemblyRequest.model_validate(response.json())


def test_resolves_the_graph_to_an_evaluate_assembly_request(
    client: TestClient,
) -> None:
    """Two instances of ONE part + a lock mate resolve to the full request shape:
    shared dedup part_key, per-instance feature prefix / seed placement / grounded
    flag, the mate in order, and doc_version as the correlation key."""
    part_id = _create_part(client, "plate")
    feature_id = _create_sketch(client, part_id, "Sketch1", 0)
    assembly_id = _create_assembly(client, "stack")
    instance_a = _add_instance(
        client, assembly_id, part_id, 0, name="Plate <1>", grounded=True
    )
    instance_b = _add_instance(
        client,
        assembly_id,
        part_id,
        1,
        name="Plate <2>",
        placement={
            "position": {"x": 10.0, "y": 0.0, "z": 5.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    )
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {
                "type": "lock",
                "a_instance_id": instance_a,
                "b_instance_id": instance_b,
            },
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text

    request = _evaluation_request(client, assembly_id)

    assert request.assembly_id == uuid.UUID(assembly_id)
    assert request.version == 3  # == doc_version after 2 instances + 1 mate
    first, second = request.instances
    assert [str(i.instance_id) for i in request.instances] == [instance_a, instance_b]
    # The dedup key: both instances of one tip-tracked part share it (design §4).
    assert first.part_key == second.part_key == f"{part_id}@tip"
    # Each carries the part's evaluation-ready feature prefix (reused verbatim).
    for instance in request.instances:
        assert [str(item.id) for item in instance.features] == [feature_id]
        assert isinstance(instance.features[0].feature, SketchFeature)
    # The human-readable instance name rides along so the STEP export writes it as
    # the PRODUCT name (round-trip identity), never the instance UUID (FINDINGS #7).
    assert first.name == "Plate <1>"
    assert second.name == "Plate <2>"
    # Authored seed pose + grounded flag ride along for the solver.
    assert first.grounded is True
    assert second.grounded is False
    assert second.placement.position.x == 10.0
    assert second.placement.position.z == 5.0
    # The mate graph, in order_index order.
    (mate,) = request.mates
    assert mate.order_index == 0
    assert isinstance(mate.mate, LockMate)
    assert str(mate.mate.a_instance_id) == instance_a
    assert str(mate.mate.b_instance_id) == instance_b


def test_rollback_bar_applies_to_the_instanced_part_prefix(client: TestClient) -> None:
    """The instanced part's prefix is the SAME rollback-applied list its own
    evaluation-request serves (§3 — geometry never learns rollback exists)."""
    part_id = _create_part(client, "plate")
    first = _create_sketch(client, part_id, "Sketch1", 0)
    _create_sketch(client, part_id, "Sketch2", 1)
    response = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 2, "rollback_feature_id": first},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text

    assembly_id = _create_assembly(client, "stack")
    _add_instance(client, assembly_id, part_id, 0, grounded=True)

    (instance,) = _evaluation_request(client, assembly_id).instances
    assert [str(item.id) for item in instance.features] == [first]


def test_sub_assembly_instance_contributes_an_empty_prefix(client: TestClient) -> None:
    """v1 defers NESTED flatten: a rigid sub-assembly instance resolves with an
    EMPTY feature prefix (geometry reports its typed per-instance ``no_body`` and
    projects the rest) — never a 500. Single-LEVEL assemblies are fully resolved."""
    part_id = _create_part(client, "plate")
    _create_sketch(client, part_id, "Sketch1", 0)
    inner_id = _create_assembly(client, "inner")
    _add_instance(client, inner_id, part_id, 0, grounded=True)
    outer_id = _create_assembly(client, "outer")
    _add_instance(client, outer_id, part_id, 0, name="Plate <1>", grounded=True)
    _add_instance(
        client,
        outer_id,
        inner_id,
        1,
        ref_document_kind="assembly",
        name="Inner <1>",
    )

    part_instance, sub_instance = _evaluation_request(client, outer_id).instances
    assert len(part_instance.features) == 1  # the part instance fully resolves
    assert sub_instance.features == []  # nested flatten deferred (typed no_body)
    assert sub_instance.part_key == f"{inner_id}@tip"


def test_dangling_part_reference_contributes_an_empty_prefix(
    client: TestClient, any_db_url: str
) -> None:
    """A referenced part DELETED while still instanced (bypassing the API's
    409-with-dependents — the BOM's documented dangling case) degrades to an empty
    prefix (geometry: typed ``no_body``), never a 500."""
    part_id = _create_part(client, "plate")
    _create_sketch(client, part_id, "Sketch1", 0)
    assembly_id = _create_assembly(client, "stack")
    _add_instance(client, assembly_id, part_id, 0, grounded=True)

    async def delete_part_row() -> None:
        engine = create_async_engine(async_dsn(any_db_url))
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.delete(Part).where(Part.id == uuid.UUID(part_id))
                )
        finally:
            await engine.dispose()

    asyncio.run(delete_part_row())

    (instance,) = _evaluation_request(client, assembly_id).instances
    assert instance.features == []


def test_foreign_and_unknown_assemblies_are_a_uniform_404(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "stack")
    for target, headers in (
        (assembly_id, {PRINCIPAL_HEADER: OTHER}),  # foreign assembly
        (str(uuid.uuid4()), _headers()),  # unknown assembly
    ):
        response = client.get(
            f"/api/v1/assemblies/{target}/evaluation-request", headers=headers
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "assembly_not_found"


def test_missing_principal_is_401(client: TestClient) -> None:
    response = client.get(f"/api/v1/assemblies/{uuid.uuid4()}/evaluation-request")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_principal"
