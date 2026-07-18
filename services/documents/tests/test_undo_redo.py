"""documents undo/redo — verbatim snapshot restore (docs/design/undo-redo.md).

Correctness IS the deliverable of UR1, and the load-bearing property under
test is **byte-identical restore**: undo/redo must reproduce every feature id,
dependency edge, order_index, param payload and timestamp exactly — never
re-created entities with fresh ids (which would orphan ``feature_dependencies``
references on redo). Trees are compared as full serialized API responses with
only the legitimately-changing fields (``tree_version``, ``can_undo``,
``can_redo``) stripped, and dependency edges are additionally asserted straight
from the database.

Runs against SQLite (always) and the real migrated scratch PostgreSQL (see
conftest.py). Envelope helpers are intentionally self-contained — test modules
cannot import each other under ``--import-mode=importlib`` (see conftest
docstring), so the minimal payload builders are restated here.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents.db import FeatureDependency, PartSnapshot
from documents.history import HISTORY_MAX
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn, enable_sqlite_foreign_keys
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"

#: Fields of the tree response that legitimately change across undo/redo.
VOLATILE_TREE_FIELDS = frozenset({"tree_version", "can_undo", "can_redo"})


def _sketch_envelope() -> dict[str, Any]:
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "construction": False,
                    "id": "e1",
                    "kind": "circle",
                    "center": {"x": 0.0, "y": 0.0},
                    "radius": 12.0,
                }
            ],
            "constraints": [],
        },
    }


def _extrude_envelope(sketch_id: str, distance_mm: float = 10.0) -> dict[str, Any]:
    return {
        "type": "extrude",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": distance_mm,
            "operation": "add",
            "direction": "normal",
        },
    }


def _datum_envelope(offset_mm: float = 30.0) -> dict[str, Any]:
    return {
        "type": "datum",
        "version": 1,
        "params": {"base": "XY", "offset_mm": offset_mm, "flip": False},
    }


def _datum_on_face_envelope(target_id: str) -> dict[str, Any]:
    #: An on_face datum naming a face of an earlier body feature by SubshapeRef
    #: — materializes a feature_dependencies edge to `target_id`.
    return {
        "type": "datum",
        "version": 1,
        "params": {
            "kind": "on_face",
            "offset_mm": 0.0,
            "face": {
                "kind": "subshape",
                "feature_id": target_id,
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": {
                        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "centroid": {"x": 0.0, "y": 0.0, "z": 10.0},
                        "area_mm2": 452.4,
                    },
                },
            },
        },
    }


def _fillet_envelope(target_id: str) -> dict[str, Any]:
    #: A fillet with a PICKED edge (EdgeSubshapeRef) naming an edge of the
    #: extrude by feature id — the signature dependency case: this edge ref
    #: materializes a feature_dependencies row pointing at `target_id`.
    return {
        "type": "fillet",
        "version": 1,
        "params": {
            "radius_mm": 2.0,
            "edges": {
                "kind": "edges",
                "refs": [
                    {
                        "kind": "subshape",
                        "feature_id": target_id,
                        "subshape_type": "edge",
                        "selector": {
                            "selector_version": 1,
                            "signature": {
                                "curve": "circle",
                                "end_a": {"x": -12.0, "y": 0.0, "z": 10.0},
                                "end_b": {"x": -12.0, "y": 0.0, "z": 10.0},
                                "midpoint": {"x": 12.0, "y": 0.0, "z": 10.0},
                                "length_mm": 75.4,
                            },
                        },
                    }
                ],
            },
        },
    }


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {PRINCIPAL_HEADER: OWNER}


def _create_part(client: TestClient, name: str = "undo-block") -> str:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_feature(
    client: TestClient,
    part_id: str,
    name: str,
    feature: dict[str, Any],
    expected_tree_version: int,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": feature,
            "expected_tree_version": expected_tree_version,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _rename_feature(
    client: TestClient,
    part_id: str,
    feature_id: str,
    name: str,
    expected_tree_version: int,
) -> None:
    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        json={"expected_tree_version": expected_tree_version, "name": name},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text


def _tree(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}/features", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _undo(client: TestClient, part_id: str, expected: int) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/parts/{part_id}/undo",
        json={"expected_tree_version": expected},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _redo(client: TestClient, part_id: str, expected: int) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/parts/{part_id}/redo",
        json={"expected_tree_version": expected},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _stripped(tree: dict[str, Any]) -> dict[str, Any]:
    """The tree minus its legitimately-volatile fields: everything left —
    ids, order, names, params, timestamps, rollback bar — must be
    byte-identical across an undo/redo round trip."""
    return {k: v for k, v in tree.items() if k not in VOLATILE_TREE_FIELDS}


async def _fetch_all(url: str, statement: sa.Select[Any]) -> list[sa.Row[Any]]:
    engine = create_async_engine(async_dsn(url))
    enable_sqlite_foreign_keys(engine)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(statement)).all())
    finally:
        await engine.dispose()


def _edges(url: str) -> set[tuple[str, str]]:
    rows = asyncio.run(
        _fetch_all(
            url,
            sa.select(
                FeatureDependency.feature_id, FeatureDependency.references_feature_id
            ),
        )
    )
    return {(str(a), str(b)) for a, b in rows}


def _snapshot_stats(url: str) -> tuple[int, int | None, int | None]:
    """(count, floor seq, top seq) of the part_snapshots ring."""
    [row] = asyncio.run(
        _fetch_all(
            url,
            sa.select(
                sa.func.count(PartSnapshot.seq),
                sa.func.min(PartSnapshot.seq),
                sa.func.max(PartSnapshot.seq),
            ),
        )
    )
    return int(row[0]), row[1], row[2]


# --- byte-identical restore at any distance ---------------------------------------


def test_undo_redo_byte_identical_at_any_distance(
    client: TestClient, any_db_url: str
) -> None:
    """Build a 5-feature tree with real cross-references, walk the FULL
    history back and forward, comparing complete serialized trees at every
    step — ids, dependency edges, order and params all verbatim."""
    part_id = _create_part(client)
    states: list[dict[str, Any]] = [_stripped(_tree(client, part_id))]  # baseline

    sketch_id: str = _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)[
        "feature"
    ]["id"]
    states.append(_stripped(_tree(client, part_id)))
    extrude_id: str = _create_feature(
        client, part_id, "Extrude1", _extrude_envelope(sketch_id), 1
    )["feature"]["id"]
    states.append(_stripped(_tree(client, part_id)))
    datum_id: str = _create_feature(
        client, part_id, "DatumOnFace", _datum_on_face_envelope(extrude_id), 2
    )["feature"]["id"]
    states.append(_stripped(_tree(client, part_id)))
    fillet_id: str = _create_feature(
        client, part_id, "Fillet1", _fillet_envelope(extrude_id), 3
    )["feature"]["id"]
    states.append(_stripped(_tree(client, part_id)))
    _create_feature(client, part_id, "Datum2", _datum_envelope(), 4)
    states.append(_stripped(_tree(client, part_id)))
    # A param update and a rename are history steps too, not just creates.
    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{extrude_id}",
        json={
            "expected_tree_version": 5,
            "feature": _extrude_envelope(sketch_id, distance_mm=25.0),
        },
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    states.append(_stripped(_tree(client, part_id)))
    _rename_feature(client, part_id, sketch_id, "Base sketch", 6)
    states.append(_stripped(_tree(client, part_id)))

    original_edges = _edges(any_db_url)
    assert original_edges == {
        (extrude_id, sketch_id),
        (datum_id, extrude_id),
        (fillet_id, extrude_id),
    }

    # Walk all 7 steps back to the empty baseline...
    version = 7
    tree = _tree(client, part_id)
    for step_back in range(1, 8):
        tree = _undo(client, part_id, version)
        version += 1  # undo IS a document edit — tree_version bumps
        assert tree["tree_version"] == version
        assert _stripped(tree) == states[7 - step_back]
        assert tree["can_redo"] is True
    assert tree["features"] == []
    assert tree["can_undo"] is False
    assert _edges(any_db_url) == set()

    # ...and all 7 steps forward again: ids/edges verbatim at every distance.
    for step_forward in range(1, 8):
        tree = _redo(client, part_id, version)
        version += 1
        assert tree["tree_version"] == version
        assert _stripped(tree) == states[step_forward]
        assert tree["can_undo"] is True
    assert tree["can_redo"] is False
    assert _edges(any_db_url) == original_edges


# --- the signature dependency case ------------------------------------------------


def test_delete_undo_restores_dependency_to_original_id(
    client: TestClient, any_db_url: str
) -> None:
    """Delete + undo across a dependency: the fillet comes back with its
    ORIGINAL id and its edge pointing at the ORIGINAL extrude id.

    What delete does today (feature-tree.md §2.3): deleting a REFERENCED
    feature is refused 409-with-dependents (no cascade), so the deletable
    thing is the dependent itself. Restore therefore has exactly one effect
    to reverse — re-inserting the deleted row + its outgoing edges verbatim —
    and the 409 also proves the restored edge is live data, not display state.
    """
    part_id = _create_part(client)
    sketch_id: str = _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)[
        "feature"
    ]["id"]
    extrude_id: str = _create_feature(
        client, part_id, "Extrude1", _extrude_envelope(sketch_id), 1
    )["feature"]["id"]
    fillet_id: str = _create_feature(
        client, part_id, "Fillet1", _fillet_envelope(extrude_id), 2
    )["feature"]["id"]
    before_delete = _stripped(_tree(client, part_id))

    # Deleting the referenced extrude is a 409 — and NOT a history event.
    _, _, top_before = _snapshot_stats(any_db_url)
    conflict = client.delete(
        f"/api/v1/parts/{part_id}/features/{extrude_id}",
        params={"expected_tree_version": 3},
        headers=_headers(),
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "feature_has_dependents"
    assert _snapshot_stats(any_db_url)[2] == top_before

    # Delete the fillet (legal), then undo it.
    deleted = client.delete(
        f"/api/v1/parts/{part_id}/features/{fillet_id}",
        params={"expected_tree_version": 3},
        headers=_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    assert _edges(any_db_url) == {(extrude_id, sketch_id)}

    restored = _undo(client, part_id, 4)
    assert _stripped(restored) == before_delete
    assert [f["id"] for f in restored["features"]] == [
        sketch_id,
        extrude_id,
        fillet_id,
    ]
    # The load-bearing assertion: the restored fillet's dependency edge points
    # at the ORIGINAL extrude id (never a re-minted one).
    assert _edges(any_db_url) == {
        (extrude_id, sketch_id),
        (fillet_id, extrude_id),
    }
    # ...and it is live referential data: the extrude is protected again.
    conflict = client.delete(
        f"/api/v1/parts/{part_id}/features/{extrude_id}",
        params={"expected_tree_version": 5},
        headers=_headers(),
    )
    assert conflict.status_code == 409


# --- linear history: fresh edit truncates redo ------------------------------------


def test_fresh_edit_truncates_redo(client: TestClient) -> None:
    part_id = _create_part(client)
    _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)
    _create_feature(client, part_id, "Datum1", _datum_envelope(30.0), 1)

    undone = _undo(client, part_id, 2)  # back to sketch-only
    assert [f["name"] for f in undone["features"]] == ["Sketch1"]
    assert undone["can_redo"] is True

    # A fresh edit while undone drops the redo tail (linear history).
    _create_feature(client, part_id, "Datum2", _datum_envelope(60.0), 3)
    tree = _tree(client, part_id)
    assert tree["can_redo"] is False
    assert [f["name"] for f in tree["features"]] == ["Sketch1", "Datum2"]

    # Redo is now a clean no-op: same tree, version untouched, Datum1 gone
    # forever (branching history is out of scope).
    noop = _redo(client, part_id, 4)
    assert noop == tree


# --- boundaries: clean no-ops + can_undo/can_redo at every position ----------------


def test_boundary_no_ops_and_flags(client: TestClient) -> None:
    part_id = _create_part(client)

    # No history at all (history is seeded lazily on the first mutation):
    # both directions no-op cleanly and both flags are down.
    empty = _tree(client, part_id)
    assert (empty["can_undo"], empty["can_redo"]) == (False, False)
    assert empty["tree_version"] == 0
    assert _undo(client, part_id, 0) == empty
    assert _redo(client, part_id, 0) == empty

    _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)
    tree = _tree(client, part_id)
    assert (tree["can_undo"], tree["can_redo"]) == (True, False)

    at_baseline = _undo(client, part_id, 1)
    assert at_baseline["features"] == []
    assert (at_baseline["can_undo"], at_baseline["can_redo"]) == (False, True)

    # Undo at the floor: clean no-op — 200, version unchanged, not an error.
    noop = _undo(client, part_id, 2)
    assert noop == at_baseline

    at_top = _redo(client, part_id, 2)
    assert [f["name"] for f in at_top["features"]] == ["Sketch1"]
    assert (at_top["can_undo"], at_top["can_redo"]) == (True, False)

    # Redo at the top: clean no-op too.
    assert _redo(client, part_id, 3) == at_top


# --- optimistic concurrency -------------------------------------------------------


def test_stale_version_is_422_on_undo_and_redo(client: TestClient) -> None:
    part_id = _create_part(client)
    _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)

    for route in ("undo", "redo"):
        response = client.post(
            f"/api/v1/parts/{part_id}/{route}",
            json={"expected_tree_version": 0},  # current is 1
            headers=_headers(),
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "stale_tree_version"
        assert error["details"] == {"provided": 0, "current": 1}


# --- reorder + update round-trip --------------------------------------------------


def test_reorder_and_update_round_trip(client: TestClient) -> None:
    """The two non-create/delete mutations are history steps with verbatim
    restore too — order_index permutations and param payloads round-trip."""
    part_id = _create_part(client)
    sketch_id: str = _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)[
        "feature"
    ]["id"]
    datum_id: str = _create_feature(
        client, part_id, "Datum1", _datum_envelope(30.0), 1
    )["feature"]["id"]
    states = [_stripped(_tree(client, part_id))]

    reordered = client.put(
        f"/api/v1/parts/{part_id}/features/order",
        json={"expected_tree_version": 2, "order": [datum_id, sketch_id]},
        headers=_headers(),
    )
    assert reordered.status_code == 200, reordered.text
    states.append(_stripped(_tree(client, part_id)))
    assert [f["id"] for f in states[-1]["features"]] == [datum_id, sketch_id]

    updated = client.patch(
        f"/api/v1/parts/{part_id}/features/{datum_id}",
        json={"expected_tree_version": 3, "feature": _datum_envelope(75.0)},
        headers=_headers(),
    )
    assert updated.status_code == 200, updated.text
    states.append(_stripped(_tree(client, part_id)))

    assert _stripped(_undo(client, part_id, 4)) == states[1]  # update undone
    assert _stripped(_undo(client, part_id, 5)) == states[0]  # reorder undone
    tree = _tree(client, part_id)
    assert [f["id"] for f in tree["features"]] == [sketch_id, datum_id]
    assert tree["features"][1]["feature"]["params"]["offset_mm"] == 30.0

    assert _stripped(_redo(client, part_id, 6)) == states[1]
    assert _stripped(_redo(client, part_id, 7)) == states[2]
    tree = _tree(client, part_id)
    assert [f["id"] for f in tree["features"]] == [datum_id, sketch_id]
    assert tree["features"][0]["feature"]["params"]["offset_mm"] == 75.0


# --- rollback bar restores with the snapshot --------------------------------------


def test_rollback_bar_round_trips_through_snapshots(client: TestClient) -> None:
    """The bar is part of the serialized state: a create-while-rolled-back
    (which moves the bar to the new feature, §3) undoes back to the pre-op
    bar position and redoes forward again."""
    part_id = _create_part(client)
    sketch_id: str = _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)[
        "feature"
    ]["id"]
    _create_feature(client, part_id, "Datum1", _datum_envelope(30.0), 1)

    # Move the bar to the sketch (NOT a history event in v1 — view-state-like;
    # it still restores with each snapshot).
    response = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 2, "rollback_feature_id": sketch_id},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text

    # Create while rolled back: inserts after the bar and moves the bar to it.
    inserted_id: str = _create_feature(
        client, part_id, "Datum2", _datum_envelope(60.0), 3
    )["feature"]["id"]
    with_bar = _tree(client, part_id)
    assert with_bar["rollback_feature_id"] == inserted_id

    # Undo restores the ADJACENT SNAPSHOT verbatim — the state appended by the
    # Datum1 create, whose bar was still at the tip (None). The later bar move
    # was not a history event, so its position is NOT what undo returns to:
    # the bar restores to what the snapshot recorded (v1 semantics, module
    # docstring of documents.history).
    undone = _undo(client, part_id, 4)
    assert undone["rollback_feature_id"] is None
    assert [f["name"] for f in undone["features"]] == ["Sketch1", "Datum1"]

    redone = _redo(client, part_id, 5)
    assert redone["rollback_feature_id"] == inserted_id
    assert _stripped(redone) == _stripped(with_bar)


# --- bounded ring -----------------------------------------------------------------


def test_ring_prunes_oldest_at_cap(client: TestClient, any_db_url: str) -> None:
    """50+ mutations: the ring holds HISTORY_MAX snapshots, seqs stay
    contiguous, undo works across the whole retained window and stops
    cleanly at the (shifted) floor."""
    part_id = _create_part(client)
    sketch_id: str = _create_feature(
        client, part_id, "Rename 0", _sketch_envelope(), 0
    )["feature"]["id"]
    renames = HISTORY_MAX + 5  # 55 → 56 appends + baseline = 57 states
    for i in range(1, renames + 1):
        _rename_feature(client, part_id, sketch_id, f"Rename {i}", i)

    count, floor, top = _snapshot_stats(any_db_url)
    assert count == HISTORY_MAX
    assert top == renames + 1  # baseline seq 0 + one append per mutation
    assert floor == top - (HISTORY_MAX - 1)

    # Undo across the ENTIRE retained window (HISTORY_MAX - 1 steps)...
    version = renames + 1
    tree = _tree(client, part_id)
    for _ in range(HISTORY_MAX - 1):
        assert tree["can_undo"] is True
        tree = _undo(client, part_id, version)
        version += 1
    # ...landing on the ring's floor: the state after mutation #6 (0..6
    # dropped by pruning — you can undo within the window, not before it).
    assert tree["can_undo"] is False
    assert tree["features"][0]["name"] == f"Rename {renames - (HISTORY_MAX - 1)}"
    assert tree["features"][0]["id"] == sketch_id  # identity survives the walk

    # Below the floor: clean no-op, and redo still walks forward fine.
    assert _undo(client, part_id, version) == tree
    redone = _redo(client, part_id, version)
    assert redone["features"][0]["name"] == f"Rename {renames - (HISTORY_MAX - 2)}"


# --- failed mutations record nothing ----------------------------------------------


def test_failed_mutation_records_no_history(
    client: TestClient, any_db_url: str
) -> None:
    part_id = _create_part(client)
    _create_feature(client, part_id, "Sketch1", _sketch_envelope(), 0)
    stats = _snapshot_stats(any_db_url)

    stale = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Sketch2",
            "feature": _sketch_envelope(),
            "expected_tree_version": 0,
        },
        headers=_headers(),
    )
    assert stale.status_code == 422
    assert _snapshot_stats(any_db_url) == stats
    tree = _tree(client, part_id)
    assert (tree["can_undo"], tree["can_redo"]) == (True, False)
