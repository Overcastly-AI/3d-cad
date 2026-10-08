"""documents' half of DESIGN-INTENT-BACKFILL: serve the tree, write names safely.

What is under test is that the write is SAFE on stored user data, not that a
column can be set: it writes only where geometry's report still describes the
stored part (stale guard, per-ref digest guard, null-only), it is idempotent,
it is metadata (``updated_at`` pinned, dependencies unchanged, no undo step,
the head snapshot amended), it is journaled and revertible, and it serialises
with a concurrent tree edit on the part-row lock (Postgres) so exactly one of
the two lands.

Both dialects through ``any_db_url`` (SQLite always; real PostgreSQL 16 when
available, required in CI); the race is Postgres only, since SQLite ignores
``FOR UPDATE``.
"""

import asyncio
import copy
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents import db
from documents.features import update_feature
from documents.main import DocumentsSettings, build_app
from documents.ref_backfill import apply_ref_names_route
from fastapi.testclient import TestClient
from loft_wire.features import FeatureUpdate
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.ref_names import (
    RefNameOutcome,
    RefNamesApplyRequest,
    RefNamesReport,
    signature_digest,
)
from py_kit.db import async_dsn
from py_kit.errors import ValidationApiError
from py_kit.metrics import REGISTRY
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-0000000000bf"
OTHER = "6f3f6b64-0000-4000-8000-0000000000c0"


@pytest.fixture
def db_url(any_db_url: str) -> str:
    return any_db_url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=db_url))) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _v(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _edge_signature(x: float = 20.0) -> dict[str, Any]:
    return {
        "curve": "line",
        "end_a": _v(x, -12.5, 10.0),
        "end_b": _v(x, 12.5, 10.0),
        "midpoint": _v(x, 0.0, 10.0),
        "length_mm": 25.0,
        "adjacent_faces": [
            {"normal": _v(0, 0, 1), "centroid": _v(0, 0, 10), "area_mm2": 1000.0},
            {"normal": _v(1, 0, 0), "centroid": _v(x, 0, 5), "area_mm2": 250.0},
        ],
    }


def _fillet(extrude_id: str, signature: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "fillet",
        "version": 1,
        "params": {
            "edges": {
                "kind": "edges",
                "refs": [
                    {
                        "kind": "subshape",
                        "feature_id": extrude_id,
                        "subshape_type": "edge",
                        "selector": {"selector_version": 1, "signature": signature},
                    }
                ],
            },
            "radius_mm": 2.0,
        },
    }


def _create(
    client: TestClient, part_id: str, name: str, feature: dict[str, Any], version: int
) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": name, "feature": feature, "expected_tree_version": version},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _part(client: TestClient, name: str = "Old bracket") -> dict[str, str]:
    """A plate with a fillet on one picked edge stored WITHOUT a name."""
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    sketch_id = _create(
        client,
        part_id,
        "Sketch1",
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": "e1",
                        "kind": "line",
                        "start": {"x": -20, "y": -12.5},
                        "end": {"x": 20, "y": -12.5},
                    }
                ],
                "constraints": [],
            },
        },
        0,
    )
    extrude_id = _create(
        client,
        part_id,
        "Extrude1",
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch_id},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
        },
        1,
    )
    fillet_id = _create(
        client, part_id, "Fillet1", _fillet(extrude_id, _edge_signature()), 2
    )
    return {"part": part_id, "extrude": extrude_id, "fillet": fillet_id}


def _feature(client: TestClient, part_id: str, feature_id: str) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/parts/{part_id}/features/{feature_id}", headers=_headers()
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _get_part(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _request(client: TestClient, part_id: str, **params: str) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/parts/{part_id}/ref-names-request",
        params=params,
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _report(
    client: TestClient, ids: dict[str, str], *, name: str = "x:start|x:e2"
) -> RefNamesReport:
    """The report geometry would send for the fillet's one ref."""
    body = _request(client, ids["part"])
    fillet = next(f for f in body["request"]["features"] if f["id"] == ids["fillet"])
    signature = fillet["feature"]["params"]["edges"]["refs"][0]["selector"]["signature"]
    return RefNamesReport(
        tree_version=body["tree_version"],
        kernel="test-kernel",
        outcomes=[
            RefNameOutcome(
                feature_id=uuid.UUID(ids["fillet"]),
                path="/edges/refs/0",
                kind="edge",
                signature_sha256=signature_digest(signature),
                outcome="named",
                topo_name=name,
                end_a_topo_name="x:e1",
                adjacent_topo_names=["x:start", "x:e2"],
            )
        ],
    )


def _apply(
    client: TestClient,
    part_id: str,
    report: RefNamesReport,
    *,
    tree_version: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/parts/{part_id}/ref-names",
        content=RefNamesApplyRequest(
            tree_version=report.tree_version if tree_version is None else tree_version,
            report=report,
            dry_run=dry_run,
        ).model_dump_json(),
        headers={**_headers(), "content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _signature(feature: dict[str, Any]) -> dict[str, Any]:
    sig: dict[str, Any] = feature["feature"]["params"]["edges"]["refs"][0]["selector"][
        "signature"
    ]
    return sig


def _rows(url: str, query: Any) -> list[Any]:
    async def run() -> list[Any]:
        engine = create_async_engine(async_dsn(url))
        try:
            async with engine.connect() as connection:
                return list((await connection.execute(query)).all())
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _writes(result: str) -> float:
    value = REGISTRY.get_sample_value(
        "loft_ref_backfill_writes_total", {"result": result}
    )
    return 0.0 if value is None else value


# --- the request -------------------------------------------------------------------


def test_the_request_is_the_whole_tree_and_needed_only_while_pending(
    client: TestClient,
) -> None:
    ids = _part(client)
    # Roll the bar back past the fillet: the request must still carry it.
    moved = client.put(
        f"/api/v1/parts/{ids['part']}/rollback",
        json={"rollback_feature_id": ids["extrude"], "expected_tree_version": 3},
        headers=_headers(),
    )
    assert moved.status_code == 200, moved.text
    body = _request(client, ids["part"])
    assert body["needed"] is True
    assert body["ref_names_checked_version"] is None
    assert [f["id"] for f in body["request"]["features"]][-1] == ids["fillet"]
    assert body["request"]["tree_version"] == body["tree_version"] == 4
    # Checked (an empty report marks it) -> not needed, unless forced.
    empty = RefNamesReport(tree_version=4, kernel="k", outcomes=[])
    assert _apply(client, ids["part"], empty)["result"] == "unchanged"
    assert _get_part(client, ids["part"])["tree_version"] == 4
    later = _request(client, ids["part"])
    assert later == {
        "needed": False,
        "tree_version": 4,
        "ref_names_checked_version": 4,
        "request": None,
    }
    assert _request(client, ids["part"], force="true")["needed"] is True


def test_another_owner_cannot_read_or_write(client: TestClient) -> None:
    ids = _part(client)
    response = client.get(
        f"/api/v1/parts/{ids['part']}/ref-names-request", headers=_headers(OTHER)
    )
    assert response.status_code == 404


# --- the write ---------------------------------------------------------------------


def test_a_report_writes_only_null_names_as_metadata(
    client: TestClient, db_url: str
) -> None:
    ids = _part(client)
    part_before = _get_part(client, ids["part"])
    fillet_before = _feature(client, ids["part"], ids["fillet"])
    report = _report(client, ids)
    written_before = _writes("written")
    result = _apply(client, ids["part"], report)
    assert result == {
        "result": "written",
        "tree_version": 4,
        "refs_written": 1,
        "refs_signature_changed": 0,
        "refs_already_named": 0,
        "features_written": 1,
    }
    assert _writes("written") - written_before == 1
    fillet = _feature(client, ids["part"], ids["fillet"])
    sig = _signature(fillet)
    assert sig["topo_name"] == "x:start|x:e2"
    assert sig["end_a_topo_name"] == "x:e1"
    assert [f["topo_name"] for f in sig["adjacent_faces"]] == ["x:start", "x:e2"]
    # Every geometric field is what was stored.
    old = _signature(fillet_before)
    for key in ("curve", "end_a", "end_b", "midpoint", "length_mm"):
        assert sig[key] == old[key]
    # Metadata, not an edit.
    part = _get_part(client, ids["part"])
    assert part["tree_version"] == part_before["tree_version"] + 1
    assert part["updated_at"] == part_before["updated_at"]
    assert fillet["updated_at"] == fillet_before["updated_at"]
    deps = _rows(
        db_url,
        sa.select(db.FeatureDependency.references_feature_id).where(
            db.FeatureDependency.feature_id == uuid.UUID(ids["fillet"])
        ),
    )
    assert [str(row[0]) for row in deps] == [ids["extrude"]]
    checked = _rows(
        db_url,
        sa.select(db.Part.ref_names_checked_version).where(
            db.Part.id == uuid.UUID(ids["part"])
        ),
    )
    assert checked[0][0] == 4


def test_the_write_amends_the_head_snapshot_without_an_undo_step(
    client: TestClient, db_url: str
) -> None:
    ids = _part(client)
    seqs_before = _rows(
        db_url,
        sa.select(db.PartSnapshot.seq).where(
            db.PartSnapshot.part_id == uuid.UUID(ids["part"])
        ),
    )
    _apply(client, ids["part"], _report(client, ids))
    snapshots = _rows(
        db_url,
        sa.select(db.PartSnapshot.seq, db.PartSnapshot.state)
        .where(db.PartSnapshot.part_id == uuid.UUID(ids["part"]))
        .order_by(db.PartSnapshot.seq),
    )
    assert [row[0] for row in snapshots] == sorted(row[0] for row in seqs_before)
    head = snapshots[-1][1]
    fillet = next(f for f in head["features"] if f["id"] == ids["fillet"])
    assert (
        fillet["params"]["edges"]["refs"][0]["selector"]["signature"]["topo_name"]
        == "x:start|x:e2"
    )
    # Undo walks back to the tree before the fillet, verbatim; redo returns the
    # NAMED fillet (an un-amended head would silently drop the names here).
    for step, version in (("undo", 4), ("redo", 5)):
        response = client.post(
            f"/api/v1/parts/{ids['part']}/{step}",
            json={"expected_tree_version": version},
            headers=_headers(),
        )
        assert response.status_code == 200, response.text
    assert _signature(_feature(client, ids["part"], ids["fillet"]))["topo_name"] == (
        "x:start|x:e2"
    )


def test_the_write_is_journaled_and_revertible(client: TestClient, db_url: str) -> None:
    ids = _part(client)
    stored_before = _rows(
        db_url,
        sa.select(db.Feature.params, db.Feature.param_version).where(
            db.Feature.id == uuid.UUID(ids["fillet"])
        ),
    )[0]
    report = _report(client, ids)
    _apply(client, ids["part"], report)
    journal = _rows(
        db_url,
        sa.select(
            db.RefNameBackfill.kind,
            db.RefNameBackfill.tree_version_before,
            db.RefNameBackfill.tree_version_after,
            db.RefNameBackfill.params_before,
            db.RefNameBackfill.params_after,
            db.RefNameBackfill.report,
            db.RefNameBackfill.kernel,
            db.RefNameBackfill.report_sha256,
        ).where(db.RefNameBackfill.part_id == uuid.UUID(ids["part"])),
    )
    assert len(journal) == 1
    kind, v0, v1, before, after, stored_report, kernel, digest = journal[0]
    assert (kind, v0, v1, kernel) == ("backfill", 3, 4, "test-kernel")
    assert before == {
        ids["fillet"]: {"param_version": stored_before[1], "params": stored_before[0]}
    }
    assert after[ids["fillet"]]["params"]["edges"]["refs"][0]["selector"]["signature"][
        "topo_name"
    ] == ("x:start|x:e2")
    assert RefNamesReport.model_validate(stored_report) == report
    assert len(digest) == 64

    reverted = client.post(
        f"/api/v1/parts/{ids['part']}/ref-names/revert", headers=_headers()
    )
    assert reverted.status_code == 200, reverted.text
    assert reverted.json() == {
        "result": "reverted",
        "tree_version": 5,
        "features_restored": 1,
        "features_skipped": 0,
    }
    restored = _rows(
        db_url,
        sa.select(db.Feature.params, db.Feature.param_version).where(
            db.Feature.id == uuid.UUID(ids["fillet"])
        ),
    )[0]
    assert tuple(restored) == tuple(stored_before)
    again = client.post(
        f"/api/v1/parts/{ids['part']}/ref-names/revert", headers=_headers()
    )
    assert again.json()["result"] == "nothing_to_revert"
    kinds = _rows(
        db_url,
        sa.select(db.RefNameBackfill.kind, db.RefNameBackfill.reverted_at)
        .where(db.RefNameBackfill.part_id == uuid.UUID(ids["part"]))
        .order_by(db.RefNameBackfill.tree_version_after),
    )
    assert [k for k, _at in kinds] == ["backfill", "revert"]
    assert kinds[0][1] is not None


def test_a_stale_report_writes_nothing(client: TestClient) -> None:
    ids = _part(client)
    report = _report(client, ids)
    # A size edit lands while geometry runs.
    renamed = client.patch(
        f"/api/v1/parts/{ids['part']}/features/{ids['fillet']}",
        json={"expected_tree_version": 3, "name": "Fillet A"},
        headers=_headers(),
    )
    assert renamed.status_code == 200, renamed.text
    stale_before = _writes("stale")
    result = _apply(client, ids["part"], report)
    assert result["result"] == "stale"
    assert result["refs_written"] == 0
    assert _writes("stale") - stale_before == 1
    assert (
        _signature(_feature(client, ids["part"], ids["fillet"])).get("topo_name")
        is None
    )
    # Still pending: the next open retries.
    assert _request(client, ids["part"])["needed"] is True


def test_a_re_picked_ref_is_left_alone(client: TestClient) -> None:
    ids = _part(client)
    report = _report(client, ids)
    repick = client.patch(
        f"/api/v1/parts/{ids['part']}/features/{ids['fillet']}",
        json={
            "expected_tree_version": 3,
            "feature": _fillet(ids["extrude"], _edge_signature(19.0)),
        },
        headers=_headers(),
    )
    assert repick.status_code == 200, repick.text
    result = _apply(client, ids["part"], report, tree_version=4)
    # The report was for version 3: stale. Re-issued against 4 with the old
    # digest, the per-ref guard refuses it.
    assert result["result"] == "stale"
    moved = report.model_copy(update={"tree_version": 4})
    result = _apply(client, ids["part"], moved)
    assert result["result"] == "unchanged"
    assert result["refs_signature_changed"] == 1
    assert (
        _signature(_feature(client, ids["part"], ids["fillet"])).get("topo_name")
        is None
    )


def test_applying_twice_is_idempotent(client: TestClient) -> None:
    ids = _part(client)
    report = _report(client, ids)
    assert _apply(client, ids["part"], report)["result"] == "written"
    after_first = _feature(client, ids["part"], ids["fillet"])
    # The same request again is stale; re-aimed at the new version, the
    # stored signature now carries the name and is not written again.
    assert _apply(client, ids["part"], report)["result"] == "stale"
    again = _apply(client, ids["part"], report.model_copy(update={"tree_version": 4}))
    assert again["result"] == "unchanged"
    assert again["refs_written"] == 0
    assert _feature(client, ids["part"], ids["fillet"]) == after_first
    assert _get_part(client, ids["part"])["tree_version"] == 4


def test_a_name_already_present_is_never_overwritten(client: TestClient) -> None:
    ids = _part(client)
    named_sig = dict(_edge_signature(), topo_name="kept")
    repick = client.patch(
        f"/api/v1/parts/{ids['part']}/features/{ids['fillet']}",
        json={
            "expected_tree_version": 3,
            "feature": _fillet(ids["extrude"], named_sig),
        },
        headers=_headers(),
    )
    assert repick.status_code == 200, repick.text
    body = _request(client, ids["part"], force="true")
    assert body["needed"] is False
    report = RefNamesReport(
        tree_version=4,
        kernel="k",
        outcomes=[
            RefNameOutcome(
                feature_id=uuid.UUID(ids["fillet"]),
                path="/edges/refs/0",
                kind="edge",
                signature_sha256=signature_digest(dict(named_sig, topo_name=None)),
                outcome="named",
                topo_name="other",
            )
        ],
    )
    result = _apply(client, ids["part"], report)
    assert result["refs_written"] == 0
    assert _signature(_feature(client, ids["part"], ids["fillet"]))["topo_name"] == (
        "kept"
    )


def test_a_dry_run_writes_nothing(client: TestClient) -> None:
    ids = _part(client)
    before = _feature(client, ids["part"], ids["fillet"])
    result = _apply(client, ids["part"], _report(client, ids), dry_run=True)
    assert result["result"] == "dry_run"
    assert result["refs_written"] == 1
    assert _feature(client, ids["part"], ids["fillet"]) == before
    assert _get_part(client, ids["part"])["tree_version"] == 3
    assert _request(client, ids["part"])["needed"] is True


def test_a_current_verdict_follows_the_bump(client: TestClient) -> None:
    ids = _part(client)
    recorded = client.put(
        f"/api/v1/parts/{ids['part']}/last-evaluation",
        json={"tree_version": 3, "status": "ok"},
        headers=_headers(),
    )
    assert recorded.status_code == 200, recorded.text
    _apply(client, ids["part"], _report(client, ids))
    part = _get_part(client, ids["part"])
    assert part["tree_version"] == 4
    assert part["eval_state"] == "ok"


def test_a_stale_verdict_stays_stale(client: TestClient) -> None:
    ids = _part(client)
    recorded = client.put(
        f"/api/v1/parts/{ids['part']}/last-evaluation",
        json={"tree_version": 2, "status": "ok"},
        headers=_headers(),
    )
    assert recorded.status_code == 200, recorded.text
    _apply(client, ids["part"], _report(client, ids))
    assert _get_part(client, ids["part"])["eval_state"] == "stale"


def test_the_sweep_lists_pending_parts_with_owners(client: TestClient) -> None:
    first = _part(client, "A")
    second = _part(client, "B")
    listed = client.get("/api/v1/ref-backfill/parts").json()["parts"]
    assert [p["part_id"] for p in listed] == [first["part"], second["part"]]
    assert {p["owner_id"] for p in listed} == {OWNER}
    _apply(client, first["part"], _report(client, first))
    listed = client.get("/api/v1/ref-backfill/parts").json()["parts"]
    assert [p["part_id"] for p in listed] == [second["part"]]
    one = client.get(
        "/api/v1/ref-backfill/parts", params={"part_id": first["part"]}
    ).json()["parts"]
    assert [p["ref_names_checked_version"] for p in one] == [4]
    assert (
        len(
            client.get("/api/v1/ref-backfill/parts", params={"limit": 1}).json()[
                "parts"
            ]
        )
        == 1
    )


# --- the race (Postgres: FOR UPDATE serialises the two) -----------------------------


async def _race(url: str, ids: dict[str, str], report: RefNamesReport) -> list[str]:
    engine = create_async_engine(async_dsn(url))
    owner = uuid.UUID(OWNER)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def edit() -> str:
            async with maker() as session:
                try:
                    await update_feature(
                        uuid.UUID(ids["part"]),
                        uuid.UUID(ids["fillet"]),
                        FeatureUpdate.model_validate(
                            {
                                "expected_tree_version": 3,
                                "feature": _fillet(
                                    ids["extrude"], _edge_signature(18.0)
                                ),
                            }
                        ),
                        owner,
                        session,
                    )
                    return "edit:ok"
                except ValidationApiError as exc:
                    await session.rollback()
                    return f"edit:{exc.code}"

        async def backfill() -> str:
            async with maker() as session:
                result = await apply_ref_names_route(
                    uuid.UUID(ids["part"]),
                    RefNamesApplyRequest(tree_version=3, report=report),
                    owner,
                    session,
                )
                return f"backfill:{result.result}"

        return list(await asyncio.gather(edit(), backfill()))
    finally:
        await engine.dispose()


def test_a_concurrent_edit_and_backfill_serialise_and_one_wins(
    pg_url: str,
) -> None:
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        ids = _part(client)
        report = _report(client, ids)
        outcome = sorted(asyncio.run(_race(pg_url, ids, report)))
        sig = _signature(_feature(client, ids["part"], ids["fillet"]))
        part = _get_part(client, ids["part"])
    assert part["tree_version"] == 4
    if outcome == ["backfill:written", "edit:stale_tree_version"]:
        assert sig["topo_name"] == "x:start|x:e2"
        assert sig["end_a"]["x"] == 20.0
    else:
        assert outcome == ["backfill:stale", "edit:ok"]
        assert sig.get("topo_name") is None
        assert sig["end_a"]["x"] == 18.0


def test_report_fields_survive_a_json_round_trip() -> None:
    report = RefNamesReport(tree_version=1, kernel="k", outcomes=[])
    assert RefNamesReport.model_validate_json(report.model_dump_json()) == report
    assert copy.deepcopy(report) == report
