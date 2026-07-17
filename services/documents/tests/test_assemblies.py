"""documents assemblies — CRUD, acyclicity, OCC, auth, 409-with-dependents.

Runs the SAME application code against SQLite (always) and a real scratch
PostgreSQL with the actual migrations applied (0001+0002+0003) — see conftest.py
for the dialect split. Exercises docs/design/assemblies.md §1: the instance +
mate CRUD round-trip, write-time acyclicity (self + transitive cycle),
optimistic concurrency (stale ``expected_version`` → 422), owner-scoped auth
(non-owner → uniform 404), and the cross-document 409-with-dependents on
deleting a still-instanced part / sub-assembly.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents import db
from documents.assemblies import create_instance
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit import ValidationApiError
from py_kit.db import async_dsn, enable_sqlite_foreign_keys
from py_kit.schemas.assemblies import InstanceCreate
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _error(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


def _create_part(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_assembly(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/assemblies", json={"name": name}, headers=_headers(owner)
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
    owner: str = OWNER,
) -> Any:
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "ref_document_id": ref_document_id,
        "ref_document_kind": ref_document_kind,
        "name": name,
        "grounded": grounded,
    }
    if placement is not None:
        payload["placement"] = placement
    return client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json=payload,
        headers=_headers(owner),
    )


# --- CRUD round-trip --------------------------------------------------------------


def test_assembly_crud_round_trip(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "gearbox")
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")

    r1 = _add_instance(client, assembly_id, part_a, 0, name="Plate <1>", grounded=True)
    assert r1.status_code == 201, r1.text
    assert r1.json()["doc_version"] == 1
    instance_a = r1.json()["instance"]["id"]

    r2 = _add_instance(
        client,
        assembly_id,
        part_b,
        1,
        name="Plate <2>",
        placement={
            "position": {"x": 10.0, "y": 0.0, "z": 5.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    )
    assert r2.status_code == 201, r2.text
    instance_b = r2.json()["instance"]["id"]

    rm = client.post(
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
    assert rm.status_code == 201, rm.text
    assert rm.json()["doc_version"] == 3

    graph = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()
    assert graph["doc_version"] == 3
    assert graph["assembly"]["name"] == "gearbox"
    assert graph["assembly"]["owner_id"] == OWNER

    instances = graph["instances"]
    assert [i["order_index"] for i in instances] == [0, 1]
    assert instances[0]["ref_document_id"] == part_a
    assert instances[0]["grounded"] is True
    assert instances[0]["ref_pinned_version"] is None
    assert instances[0]["placement"]["orientation"] == {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "w": 1.0,
    }
    assert instances[1]["ref_document_id"] == part_b
    assert instances[1]["placement"]["position"] == {"x": 10.0, "y": 0.0, "z": 5.0}

    mates = graph["mates"]
    assert len(mates) == 1
    assert mates[0]["mate"]["type"] == "lock"
    assert mates[0]["mate"]["a_instance_id"] == instance_a
    assert mates[0]["mate"]["b_instance_id"] == instance_b


# --- length_unit (docs/design/units.md §U1) ------------------------------------


def test_assembly_defaults_to_mm(client: TestClient) -> None:
    """An assembly created without a unit reads back canonical mm."""
    assembly_id = _create_assembly(client, "no-unit")
    header = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()[
        "assembly"
    ]
    assert header["length_unit"] == "mm"


def test_assembly_create_with_unit_round_trips(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assemblies",
        json={"name": "imperial-asm", "length_unit": "in"},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["length_unit"] == "in"
    assembly_id = response.json()["id"]
    header = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()[
        "assembly"
    ]
    assert header["length_unit"] == "in"


def test_assembly_create_invalid_unit_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assemblies",
        json={"name": "bad-unit", "length_unit": "furlong"},
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "validation_error"


def test_update_assembly_unit_persists_and_bumps_version(client: TestClient) -> None:
    """mm→in via PATCH persists and bumps doc_version (a document edit)."""
    assembly_id = _create_assembly(client, "unit-edit")
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}",
        json={"expected_version": 0, "length_unit": "in"},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["length_unit"] == "in"
    assert response.json()["doc_version"] == 1

    graph = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()
    assert graph["assembly"]["length_unit"] == "in"
    assert graph["doc_version"] == 1


def test_update_assembly_empty_422(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "empty-edit")
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}",
        json={"expected_version": 0},
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "empty_assembly_update"


def test_list_assemblies_owner_scoped(client: TestClient) -> None:
    _create_assembly(client, "mine-1")
    _create_assembly(client, "mine-2")
    _create_assembly(client, "theirs", owner=OTHER)

    body = client.get("/api/v1/assemblies", headers=_headers()).json()
    assert [a["name"] for a in body["assemblies"]] == ["mine-1", "mine-2"]


def test_duplicate_assembly_name_is_409(client: TestClient) -> None:
    _create_assembly(client, "dup")
    response = client.post(
        "/api/v1/assemblies", json={"name": "dup"}, headers=_headers()
    )
    assert response.status_code == 409
    assert _error(response.json())["code"] == "assembly_name_taken"


# --- acyclicity -------------------------------------------------------------------


def test_direct_self_reference_is_rejected(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "self")
    response = _add_instance(
        client, assembly_id, assembly_id, 0, ref_document_kind="assembly"
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "assembly_cycle"


def test_transitive_cycle_is_rejected(client: TestClient) -> None:
    a = _create_assembly(client, "outer")
    b = _create_assembly(client, "inner")
    # A instances B as a sub-assembly (A -> B).
    r1 = _add_instance(client, a, b, 0, ref_document_kind="assembly", name="B in A")
    assert r1.status_code == 201, r1.text
    # B instancing A (B -> A) would close the cycle A -> B -> A.
    r2 = _add_instance(client, b, a, 0, ref_document_kind="assembly", name="A in B")
    assert r2.status_code == 422
    assert _error(r2.json())["code"] == "assembly_cycle"


def test_reference_to_missing_document_is_422(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "dangle")
    missing = "6f3f6b64-0000-4000-8000-0000000000ff"
    response = _add_instance(client, assembly_id, missing, 0)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


def test_cannot_instance_another_owners_part(client: TestClient) -> None:
    #: Owner-scoped references (§1.2): a foreign part is treated as missing.
    assembly_id = _create_assembly(client, "borrow")
    foreign_part = _create_part(client, "foreign", owner=OTHER)
    response = _add_instance(client, assembly_id, foreign_part, 0)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


# --- optimistic concurrency -------------------------------------------------------


def test_stale_expected_version_is_422(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "occ")
    part = _create_part(client, "occ-part")
    _add_instance(client, assembly_id, part, 0)  # bumps to doc_version 1
    # Re-using the stale version 0 must be rejected.
    stale = _add_instance(client, assembly_id, part, 0, name="again")
    assert stale.status_code == 422
    assert _error(stale.json())["code"] == "stale_assembly_version"


# --- auth -------------------------------------------------------------------------


def test_non_owner_gets_uniform_404(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "private")
    response = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers(OTHER))
    assert response.status_code == 404
    assert _error(response.json())["code"] == "assembly_not_found"


def test_missing_principal_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/assemblies")
    assert response.status_code == 401


# --- 409-with-dependents ----------------------------------------------------------


def test_delete_instanced_part_is_409(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "uses-part")
    part = _create_part(client, "shared-part")
    _add_instance(client, assembly_id, part, 0)

    response = client.delete(f"/api/v1/parts/{part}", headers=_headers())
    assert response.status_code == 409
    error = _error(response.json())
    assert error["code"] == "part_has_dependents"
    assert error["details"]["dependents"][0]["name"] == "uses-part"


def test_delete_instanced_sub_assembly_is_409(client: TestClient) -> None:
    parent = _create_assembly(client, "parent")
    child = _create_assembly(client, "child")
    _add_instance(client, parent, child, 0, ref_document_kind="assembly", name="child")

    response = client.delete(f"/api/v1/assemblies/{child}", headers=_headers())
    assert response.status_code == 409
    assert _error(response.json())["code"] == "assembly_has_dependents"


def test_delete_unreferenced_part_still_succeeds(client: TestClient) -> None:
    part = _create_part(client, "lonely")
    response = client.delete(f"/api/v1/parts/{part}", headers=_headers())
    assert response.status_code == 204


# --- instance / mate mutation -----------------------------------------------------


def test_update_instance_replaces_placement(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "move")
    part = _create_part(client, "movable")
    r = _add_instance(client, assembly_id, part, 0)
    instance_id = r.json()["instance"]["id"]

    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        json={
            "expected_version": 1,
            "placement": {
                "position": {"x": 3.0, "y": 4.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "grounded": True,
        },
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    instance = response.json()["instance"]
    assert instance["placement"]["position"] == {"x": 3.0, "y": 4.0, "z": 0.0}
    assert instance["grounded"] is True


def test_reorder_instances(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "reorder")
    p1 = _create_part(client, "r1")
    p2 = _create_part(client, "r2")
    p3 = _create_part(client, "r3")
    i1 = _add_instance(client, assembly_id, p1, 0, name="first").json()["instance"][
        "id"
    ]
    _add_instance(client, assembly_id, p2, 1, name="second")
    _add_instance(client, assembly_id, p3, 2, name="third")

    # Move the first instance to the end (order_index 2).
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{i1}",
        json={"expected_version": 3, "order_index": 2},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert _graph_names(client, assembly_id) == ["second", "third", "first"]


def _graph_names(client: TestClient, assembly_id: str) -> list[str]:
    graph = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()
    return [i["name"] for i in graph["instances"]]


def test_mate_rejects_unknown_instance(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "badmate")
    part = _create_part(client, "bm")
    i1 = _add_instance(client, assembly_id, part, 0).json()["instance"]["id"]
    stranger = "6f3f6b64-0000-4000-8000-0000000000ee"

    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 1,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": stranger},
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "mate_instance_unknown"


def test_delete_instance_cascades_dependent_mate(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "cascade")
    p1 = _create_part(client, "c1")
    p2 = _create_part(client, "c2")
    i1 = _add_instance(client, assembly_id, p1, 0).json()["instance"]["id"]
    i2 = _add_instance(client, assembly_id, p2, 1, name="c2").json()["instance"]["id"]
    client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": i2},
        },
        headers=_headers(),
    )

    response = client.delete(
        f"/api/v1/assemblies/{assembly_id}/instances/{i1}?expected_version=3",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    graph = response.json()
    assert len(graph["instances"]) == 1
    assert graph["mates"] == []  # the lock mate went with its endpoint


def test_mate_rejects_self_reference(client: TestClient) -> None:
    #: A mate constraining an instance to itself (a==b) is degenerate → 422.
    assembly_id = _create_assembly(client, "selfmate")
    part = _create_part(client, "sm")
    i1 = _add_instance(client, assembly_id, part, 0).json()["instance"]["id"]

    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 1,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": i1},
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "mate_self_reference"


# --- cascade delete ---------------------------------------------------------------


def _row_count(
    url: str, model: type[db.Instance] | type[db.Mate], assembly_id: str
) -> int:
    """Count *model* rows for *assembly_id* via a direct (app-independent) engine."""

    async def run() -> int:
        engine = create_async_engine(async_dsn(url))
        enable_sqlite_foreign_keys(engine)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(sa.func.count())
                    .select_from(model)
                    .where(model.assembly_id == uuid.UUID(assembly_id))
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_delete_assembly_cascades_instances_and_mates(
    client: TestClient, any_db_url: str
) -> None:
    """Deleting an assembly removes its instances + mates (DB ON DELETE CASCADE).

    Asserted on BOTH dialects (any_db_url): the cascade is a Postgres FK on
    ``instances``/``mates`` and — because py-kit turns SQLite FK enforcement ON
    — the SQLite test dialect too, so an ORM/pragma regression that silently
    orphaned rows would fail here rather than at eval.
    """
    assembly_id = _create_assembly(client, "doomed")
    p1 = _create_part(client, "d1")
    p2 = _create_part(client, "d2")
    i1 = _add_instance(client, assembly_id, p1, 0).json()["instance"]["id"]
    i2 = _add_instance(client, assembly_id, p2, 1, name="d2").json()["instance"]["id"]
    rm = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": i2},
        },
        headers=_headers(),
    )
    assert rm.status_code == 201, rm.text

    assert _row_count(any_db_url, db.Instance, assembly_id) == 2
    assert _row_count(any_db_url, db.Mate, assembly_id) == 1

    response = client.delete(f"/api/v1/assemblies/{assembly_id}", headers=_headers())
    assert response.status_code == 204, response.text

    assert _row_count(any_db_url, db.Instance, assembly_id) == 0
    assert _row_count(any_db_url, db.Mate, assembly_id) == 0


# --- acyclicity concurrency (Postgres advisory lock closes the TOCTOU) ------------


async def _reciprocal_add(url: str) -> tuple[list[str], int]:
    """Two concurrent SAME-OWNER reciprocal sub-assembly adds against real PG.

    Drives :func:`create_instance` directly with two independent sessions/
    transactions (the HTTP TestClient is serial and commits per request, so it
    cannot express the interleaving) — "B into A" and "A into B" run under
    ``asyncio.gather``. The per-owner advisory lock must serialize them so the
    loser sees the winner's committed edge and is rejected. Returns each call's
    outcome plus the surviving instance count.
    """
    owner = uuid.UUID(OWNER)
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    engine = create_async_engine(async_dsn(url))
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as setup:
            setup.add(db.Assembly(id=a_id, owner_id=owner, name="A"))
            setup.add(db.Assembly(id=b_id, owner_id=owner, name="B"))
            await setup.commit()

        async def add(assembly_id: uuid.UUID, ref_id: uuid.UUID, name: str) -> str:
            async with maker() as session:
                request = InstanceCreate(
                    expected_version=0,
                    ref_document_id=ref_id,
                    ref_document_kind="assembly",
                    name=name,
                )
                try:
                    await create_instance(assembly_id, request, owner, session)
                    return "ok"
                except ValidationApiError as exc:
                    await session.rollback()
                    return exc.code

        results = await asyncio.gather(
            add(a_id, b_id, "B in A"),
            add(b_id, a_id, "A in B"),
        )

        async with maker() as check:
            total = await check.scalar(
                sa.select(sa.func.count()).select_from(db.Instance)
            )
        return list(results), int(total or 0)
    finally:
        await engine.dispose()


def test_concurrent_reciprocal_add_cannot_persist_cycle(pg_url: str) -> None:
    """Regression for the acyclicity TOCTOU (Postgres only).

    Without the per-owner ``pg_advisory_xact_lock`` both reciprocal adds run
    their unlocked :func:`_reaches` walk, miss each other's uncommitted edge,
    and both commit → a persisted A→B→A cycle (two instances). With it, exactly
    one succeeds and the other is rejected ``assembly_cycle``; one edge remains.
    """
    results, instance_count = asyncio.run(_reciprocal_add(pg_url))
    assert sorted(results) == ["assembly_cycle", "ok"]
    assert instance_count == 1  # only the winner's edge; no cycle persisted
