"""documents assembly undo/redo — verbatim snapshot restore (undo-redo.md UR3).

The assembly sibling of tests/test_undo_redo.py, run at the same rigor: the
load-bearing property is **byte-identical restore** — undo/redo must
reproduce every instance id, mate id, order_index, placement, mate param and
timestamp exactly, never re-minted ids (a mate's instance references live
inside its params JSONB, so re-created instances would orphan every mate on
redo). Graphs are compared as full serialized API responses with only the
legitimately-changing fields (``doc_version``, ``can_undo``, ``can_redo``,
the assembly header's ``updated_at``) stripped.

UR3 also covers the assembly PATCH (unlike UR1, where a part rename stays
outside history): the snapshot carries the mutable header fields
``name``/``length_unit``, so undoing a rename/re-unit restores them.

Runs against SQLite (always) and the real migrated scratch PostgreSQL (see
conftest.py). Envelope helpers are intentionally self-contained — test
modules cannot import each other under ``--import-mode=importlib``.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents.db import AssemblySnapshot
from documents.history_core import HISTORY_MAX
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn, enable_sqlite_foreign_keys
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"

#: Top-level graph-response fields that legitimately change across undo/redo.
VOLATILE_GRAPH_FIELDS = frozenset({"doc_version", "can_undo", "can_redo"})

#: Assembly-header fields that legitimately change (the row is UPDATEd on
#: every mutation, so its OCC counter and ``updated_at`` move; ``name`` and
#: ``length_unit`` do NOT belong here — they restore with the snapshot).
VOLATILE_HEADER_FIELDS = frozenset({"doc_version", "updated_at"})


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {PRINCIPAL_HEADER: OWNER}


def _create_part(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_assembly(client: TestClient, name: str = "undo-gearbox") -> str:
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
    name: str,
    grounded: bool = False,
    placement: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "ref_document_id": ref_document_id,
        "ref_document_kind": "part",
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


def _face_ref(instance_id: str, z_mm: float) -> dict[str, Any]:
    return {
        "kind": "face",
        "instance_id": instance_id,
        "signature": {
            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
            "centroid": {"x": 0.0, "y": 0.0, "z": z_mm},
            "area_mm2": 100.0,
        },
    }


def _distance_mate(a_instance: str, b_instance: str) -> dict[str, Any]:
    return {
        "type": "distance",
        "a": _face_ref(a_instance, 10.0),
        "b": _face_ref(b_instance, 0.0),
        "distance_mm": 12.5,
    }


def _lock_mate(a_instance: str, b_instance: str) -> dict[str, Any]:
    return {
        "type": "lock",
        "a_instance_id": a_instance,
        "b_instance_id": b_instance,
    }


def _add_mate(
    client: TestClient,
    assembly_id: str,
    mate: dict[str, Any],
    expected_version: int,
) -> str:
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={"expected_version": expected_version, "mate": mate},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    mate_id: str = response.json()["mate"]["id"]
    return mate_id


def _graph(client: TestClient, assembly_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _undo(client: TestClient, assembly_id: str, expected: int) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/undo",
        json={"expected_version": expected},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _redo(client: TestClient, assembly_id: str, expected: int) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/redo",
        json={"expected_version": expected},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _rename_instance(
    client: TestClient,
    assembly_id: str,
    instance_id: str,
    name: str,
    expected_version: int,
) -> None:
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        json={"expected_version": expected_version, "name": name},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text


def _stripped(graph: dict[str, Any]) -> dict[str, Any]:
    """The graph minus its legitimately-volatile fields: everything left —
    instance/mate ids, order, names, placements, params, timestamps, the
    header name/length_unit — must be byte-identical across a round trip."""
    stripped = {k: v for k, v in graph.items() if k not in VOLATILE_GRAPH_FIELDS}
    stripped["assembly"] = {
        k: v for k, v in graph["assembly"].items() if k not in VOLATILE_HEADER_FIELDS
    }
    return stripped


def _assert_same_response(noop: dict[str, Any], reference: dict[str, Any]) -> None:
    """Full-equality assertion for boundary no-ops, modulo one SQLite test-
    dialect quirk: a COMMITTING response serializes the header's in-memory
    tz-aware ``updated_at`` (``...Z``) while a later read-only response
    returns SQLite's naive re-read of the SAME instant (no suffix). Postgres
    is tz-aware on both sides. Everything else — every id, placement, param,
    timestamp, the doc_version and both flags — must match exactly."""
    assert _stripped(noop) == _stripped(reference)
    assert noop["doc_version"] == reference["doc_version"]
    assert (noop["can_undo"], noop["can_redo"]) == (
        reference["can_undo"],
        reference["can_redo"],
    )


async def _fetch_all(url: str, statement: sa.Select[Any]) -> list[sa.Row[Any]]:
    engine = create_async_engine(async_dsn(url))
    enable_sqlite_foreign_keys(engine)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(statement)).all())
    finally:
        await engine.dispose()


def _snapshot_stats(url: str) -> tuple[int, int | None, int | None]:
    """(count, floor seq, top seq) of the assembly_snapshots ring."""
    [row] = asyncio.run(
        _fetch_all(
            url,
            sa.select(
                sa.func.count(AssemblySnapshot.seq),
                sa.func.min(AssemblySnapshot.seq),
                sa.func.max(AssemblySnapshot.seq),
            ),
        )
    )
    return int(row[0]), row[1], row[2]


# --- byte-identical restore at any distance ---------------------------------------


def test_undo_redo_byte_identical_at_any_distance(client: TestClient) -> None:
    """Build a real assembly — 2 placed instances + a distance mate (with face
    signatures) + a lock mate, an instance re-place, a header PATCH and a mate
    delete — then walk the FULL history back and forward, comparing complete
    serialized graphs at every step: ids, placements, params and order all
    verbatim."""
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")
    assembly_id = _create_assembly(client)
    states: list[dict[str, Any]] = [_stripped(_graph(client, assembly_id))]  # baseline

    instance_a = _add_instance(
        client, assembly_id, part_a, 0, name="Plate <1>", grounded=True
    )
    states.append(_stripped(_graph(client, assembly_id)))
    instance_b = _add_instance(
        client,
        assembly_id,
        part_b,
        1,
        name="Plate <2>",
        placement={
            "position": {"x": 10.0, "y": 0.0, "z": 5.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.7071, "w": 0.7071},
        },
    )
    states.append(_stripped(_graph(client, assembly_id)))
    _add_mate(client, assembly_id, _distance_mate(instance_a, instance_b), 2)
    states.append(_stripped(_graph(client, assembly_id)))
    lock_id = _add_mate(client, assembly_id, _lock_mate(instance_a, instance_b), 3)
    states.append(_stripped(_graph(client, assembly_id)))

    # A re-place + a header PATCH are history steps too, not just creates.
    replaced = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_b}",
        json={
            "expected_version": 4,
            "name": "Plate <2> moved",
            "placement": {
                "position": {"x": -3.5, "y": 2.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
        },
        headers=_headers(),
    )
    assert replaced.status_code == 200, replaced.text
    states.append(_stripped(_graph(client, assembly_id)))
    patched = client.patch(
        f"/api/v1/assemblies/{assembly_id}",
        json={"expected_version": 5, "name": "undo-gearbox v2", "length_unit": "in"},
        headers=_headers(),
    )
    assert patched.status_code == 200, patched.text
    states.append(_stripped(_graph(client, assembly_id)))
    deleted = client.delete(
        f"/api/v1/assemblies/{assembly_id}/mates/{lock_id}",
        params={"expected_version": 6},
        headers=_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    states.append(_stripped(_graph(client, assembly_id)))

    # Walk all 7 steps back to the empty baseline...
    version = 7
    graph = _graph(client, assembly_id)
    for step_back in range(1, 8):
        graph = _undo(client, assembly_id, version)
        version += 1  # undo IS a document edit — doc_version bumps
        assert graph["doc_version"] == version
        assert _stripped(graph) == states[7 - step_back]
        assert graph["can_redo"] is True
    assert graph["instances"] == []
    assert graph["mates"] == []
    assert graph["assembly"]["name"] == "undo-gearbox"
    assert graph["assembly"]["length_unit"] == "mm"
    assert graph["can_undo"] is False

    # ...and all 7 steps forward again: ids/placements verbatim at every
    # distance, the header PATCH re-applied on its redo step.
    for step_forward in range(1, 8):
        graph = _redo(client, assembly_id, version)
        version += 1
        assert graph["doc_version"] == version
        assert _stripped(graph) == states[step_forward]
        assert graph["can_undo"] is True
    assert graph["can_redo"] is False
    assert graph["assembly"]["name"] == "undo-gearbox v2"
    assert graph["assembly"]["length_unit"] == "in"


# --- the mate-references-instances case -------------------------------------------


def test_delete_mate_undo_restores_original_ids(client: TestClient) -> None:
    """Delete + undo across the mate graph: the distance mate comes back with
    its ORIGINAL id, order_index, distance and face refs still pointing at the
    ORIGINAL instance ids — live data a new mate op validates against."""
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")
    assembly_id = _create_assembly(client)
    instance_a = _add_instance(
        client, assembly_id, part_a, 0, name="Plate <1>", grounded=True
    )
    instance_b = _add_instance(client, assembly_id, part_b, 1, name="Plate <2>")
    mate_id = _add_mate(client, assembly_id, _distance_mate(instance_a, instance_b), 2)
    before_delete = _stripped(_graph(client, assembly_id))

    deleted = client.delete(
        f"/api/v1/assemblies/{assembly_id}/mates/{mate_id}",
        params={"expected_version": 3},
        headers=_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["mates"] == []

    restored = _undo(client, assembly_id, 4)
    assert _stripped(restored) == before_delete
    [mate] = restored["mates"]
    assert mate["id"] == mate_id  # never re-minted
    assert mate["order_index"] == 0
    assert mate["mate"]["type"] == "distance"
    assert mate["mate"]["distance_mm"] == 12.5
    # The load-bearing assertion: the restored mate's refs point at the
    # ORIGINAL instance ids (verbatim restore keeps the graph coherent).
    assert mate["mate"]["a"]["instance_id"] == instance_a
    assert mate["mate"]["b"]["instance_id"] == instance_b


# --- instance delete cascades mates; undo reverses exactly that -------------------


def test_instance_delete_cascade_and_undo_restores_both(client: TestClient) -> None:
    """What deleting a mated instance does today (assemblies.py): the mates
    naming it are cascade-removed documents-side (no 409 — a mate is an edge,
    meaningless without both endpoints) and survivors are renumbered dense.
    Undo must reverse exactly that: the instance AND both its mates return
    with original ids, placements and order."""
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")
    assembly_id = _create_assembly(client)
    instance_a = _add_instance(
        client, assembly_id, part_a, 0, name="Plate <1>", grounded=True
    )
    instance_b = _add_instance(client, assembly_id, part_b, 1, name="Plate <2>")
    distance_id = _add_mate(
        client, assembly_id, _distance_mate(instance_a, instance_b), 2
    )
    lock_id = _add_mate(client, assembly_id, _lock_mate(instance_b, instance_a), 3)
    before_delete = _stripped(_graph(client, assembly_id))

    deleted = client.delete(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_b}",
        params={"expected_version": 4},
        headers=_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    after_delete = deleted.json()
    # Cascade semantics asserted, not assumed: both mates named instance_b.
    assert [i["id"] for i in after_delete["instances"]] == [instance_a]
    assert after_delete["mates"] == []

    restored = _undo(client, assembly_id, 5)
    assert _stripped(restored) == before_delete
    assert [i["id"] for i in restored["instances"]] == [instance_a, instance_b]
    assert [m["id"] for m in restored["mates"]] == [distance_id, lock_id]
    assert [m["order_index"] for m in restored["mates"]] == [0, 1]

    # The restored graph is live referential data: a new mate naming the
    # restored instance validates cleanly against membership.
    _add_mate(client, assembly_id, _lock_mate(instance_a, instance_b), 6)


# --- linear history: fresh edit truncates redo ------------------------------------


def test_fresh_edit_truncates_redo(client: TestClient) -> None:
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")
    assembly_id = _create_assembly(client)
    _add_instance(client, assembly_id, part_a, 0, name="Plate <1>")
    _add_instance(client, assembly_id, part_b, 1, name="Plate <2>")

    undone = _undo(client, assembly_id, 2)  # back to one instance
    assert [i["name"] for i in undone["instances"]] == ["Plate <1>"]
    assert undone["can_redo"] is True

    # A fresh edit while undone drops the redo tail (linear history).
    _add_instance(client, assembly_id, part_b, 3, name="Plate <3>")
    graph = _graph(client, assembly_id)
    assert graph["can_redo"] is False
    assert [i["name"] for i in graph["instances"]] == ["Plate <1>", "Plate <3>"]

    # Redo is now a clean no-op: same graph, version untouched, Plate <2>
    # gone forever (branching history is out of scope).
    noop = _redo(client, assembly_id, 4)
    assert noop == graph


# --- boundaries: clean no-ops + can_undo/can_redo at every position ----------------


def test_boundary_no_ops_and_flags(client: TestClient) -> None:
    part_a = _create_part(client, "plate-a")
    assembly_id = _create_assembly(client)

    # No history at all (seeded lazily on the first mutation): both
    # directions no-op cleanly and both flags are down.
    empty = _graph(client, assembly_id)
    assert (empty["can_undo"], empty["can_redo"]) == (False, False)
    assert empty["doc_version"] == 0
    assert _undo(client, assembly_id, 0) == empty
    assert _redo(client, assembly_id, 0) == empty

    _add_instance(client, assembly_id, part_a, 0, name="Plate <1>")
    graph = _graph(client, assembly_id)
    assert (graph["can_undo"], graph["can_redo"]) == (True, False)

    at_baseline = _undo(client, assembly_id, 1)
    assert at_baseline["instances"] == []
    assert (at_baseline["can_undo"], at_baseline["can_redo"]) == (False, True)

    # Undo at the floor: clean no-op — 200, version unchanged, not an error.
    _assert_same_response(_undo(client, assembly_id, 2), at_baseline)

    at_top = _redo(client, assembly_id, 2)
    assert [i["name"] for i in at_top["instances"]] == ["Plate <1>"]
    assert (at_top["can_undo"], at_top["can_redo"]) == (True, False)

    # Redo at the top: clean no-op too.
    _assert_same_response(_redo(client, assembly_id, 3), at_top)


# --- optimistic concurrency -------------------------------------------------------


def test_stale_version_is_422_on_undo_and_redo(client: TestClient) -> None:
    part_a = _create_part(client, "plate-a")
    assembly_id = _create_assembly(client)
    _add_instance(client, assembly_id, part_a, 0, name="Plate <1>")

    for route in ("undo", "redo"):
        response = client.post(
            f"/api/v1/assemblies/{assembly_id}/{route}",
            json={"expected_version": 0},  # current is 1
            headers=_headers(),
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "stale_assembly_version"
        assert error["details"] == {"provided": 0, "current": 1}


# --- header PATCH: undoing a rename that collides is a friendly 409 ---------------


def test_undo_rename_collision_is_409(client: TestClient) -> None:
    """UR3 snapshots carry the header name; restoring an older name that
    another assembly has since taken hits the per-owner unique constraint and
    surfaces as the same ``assembly_name_taken`` 409 the PATCH uses."""
    assembly_id = _create_assembly(client, "original-name")
    renamed = client.patch(
        f"/api/v1/assemblies/{assembly_id}",
        json={"expected_version": 0, "name": "renamed"},
        headers=_headers(),
    )
    assert renamed.status_code == 200, renamed.text
    _create_assembly(client, "original-name")  # takes the old name

    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/undo",
        json={"expected_version": 1},
        headers=_headers(),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "assembly_name_taken"
    # Nothing moved: the graph still shows the post-rename state.
    graph = _graph(client, assembly_id)
    assert graph["assembly"]["name"] == "renamed"
    assert graph["doc_version"] == 1


# --- bounded ring -----------------------------------------------------------------


def test_ring_prunes_oldest_at_cap(client: TestClient, any_db_url: str) -> None:
    """50+ mutations: the ring holds HISTORY_MAX snapshots, seqs stay
    contiguous, undo works across the whole retained window and stops
    cleanly at the (shifted) floor."""
    part_a = _create_part(client, "plate-a")
    assembly_id = _create_assembly(client)
    instance_a = _add_instance(client, assembly_id, part_a, 0, name="Rename 0")
    renames = HISTORY_MAX + 5  # 55 → 56 appends + baseline = 57 states
    for i in range(1, renames + 1):
        _rename_instance(client, assembly_id, instance_a, f"Rename {i}", i)

    count, floor, top = _snapshot_stats(any_db_url)
    assert count == HISTORY_MAX
    assert top == renames + 1  # baseline seq 0 + one append per mutation
    assert floor == top - (HISTORY_MAX - 1)

    # Undo across the ENTIRE retained window (HISTORY_MAX - 1 steps)...
    version = renames + 1
    graph = _graph(client, assembly_id)
    for _ in range(HISTORY_MAX - 1):
        assert graph["can_undo"] is True
        graph = _undo(client, assembly_id, version)
        version += 1
    # ...landing on the ring's floor: the state after mutation #6 (0..6
    # dropped by pruning — you can undo within the window, not before it).
    assert graph["can_undo"] is False
    assert graph["instances"][0]["name"] == f"Rename {renames - (HISTORY_MAX - 1)}"
    assert graph["instances"][0]["id"] == instance_a  # identity survives

    # Below the floor: clean no-op, and redo still walks forward fine.
    _assert_same_response(_undo(client, assembly_id, version), graph)
    redone = _redo(client, assembly_id, version)
    assert redone["instances"][0]["name"] == f"Rename {renames - (HISTORY_MAX - 2)}"


# --- failed mutations record nothing ----------------------------------------------


def test_failed_mutation_records_no_history(
    client: TestClient, any_db_url: str
) -> None:
    part_a = _create_part(client, "plate-a")
    assembly_id = _create_assembly(client)
    _add_instance(client, assembly_id, part_a, 0, name="Plate <1>")
    stats = _snapshot_stats(any_db_url)

    stale = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": 0,
            "ref_document_id": part_a,
            "ref_document_kind": "part",
            "name": "Plate <2>",
        },
        headers=_headers(),
    )
    assert stale.status_code == 422
    assert _snapshot_stats(any_db_url) == stats
    graph = _graph(client, assembly_id)
    assert (graph["can_undo"], graph["can_redo"]) == (True, False)
