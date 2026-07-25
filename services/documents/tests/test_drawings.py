"""documents drawings — CRUD, OCC, auth, dimension validation, 409-dependents.

Runs the SAME application code against SQLite (always) and a real scratch
PostgreSQL with the actual migrations applied (0001…0004) — see conftest.py for
the dialect split. Exercises docs/design/drawings.md §2/§3: the sheet → view →
dimension/annotation CRUD round-trip, cross-document existence + owner-scoping of
a view's referenced part, optimistic concurrency (stale ``expected_version`` →
422), owner-scoped auth (non-owner → uniform 404), the write-time dimension
semantic checks (diameter/radius need a circular edge; angular needs straight
edges), the view→dimensions cascade + dense renumber, and the cross-document
409-with-dependents when deleting a part a drawing view references.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from documents import db
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn, enable_sqlite_foreign_keys
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000010a"
OTHER = "6f3f6b64-0000-4000-8000-00000000010b"


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


def _edge_sig(curve: str = "line", length_mm: float = 40.0) -> dict[str, Any]:
    """A valid EdgeSignature payload (reused shipped machinery, design §3.3)."""
    return {
        "curve": curve,
        "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
        "end_b": {"x": 40.0, "y": 0.0, "z": 0.0},
        "midpoint": {"x": 20.0, "y": 0.0, "z": 0.0},
        "length_mm": length_mm,
    }


def _create_part(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_drawing(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/drawings", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    drawing_id: str = response.json()["id"]
    return drawing_id


def _add_sheet(
    client: TestClient,
    drawing_id: str,
    expected_version: int,
    *,
    name: str = "Sheet 1",
    owner: str = OWNER,
    **extra: Any,
) -> Any:
    payload: dict[str, Any] = {"expected_version": expected_version, "name": name}
    payload.update(extra)
    return client.post(
        f"/api/v1/drawings/{drawing_id}/sheets", json=payload, headers=_headers(owner)
    )


def _add_view(
    client: TestClient,
    drawing_id: str,
    sheet_id: str,
    ref_document_id: str,
    expected_version: int,
    *,
    projection: str = "front",
    ref_document_kind: str = "part",
    position: dict[str, float] | None = None,
    owner: str = OWNER,
    **extra: Any,
) -> Any:
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "ref_document_id": ref_document_id,
        "ref_document_kind": ref_document_kind,
        "projection": projection,
        "position": position or {"x_mm": 50.0, "y_mm": 50.0},
    }
    payload.update(extra)
    return client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        json=payload,
        headers=_headers(owner),
    )


# --- CRUD round-trip --------------------------------------------------------------


def test_drawing_crud_round_trip(client: TestClient) -> None:
    part = _create_part(client, "bracket")
    drawing_id = _create_drawing(client, "bracket-detail")

    rs = _add_sheet(client, drawing_id, 0, size="A3", orientation="portrait")
    assert rs.status_code == 201, rs.text
    assert rs.json()["doc_version"] == 1
    sheet_id = rs.json()["sheet"]["id"]

    rv = _add_view(
        client,
        drawing_id,
        sheet_id,
        part,
        1,
        projection="iso",
        scale={"numerator": 1, "denominator": 2},
    )
    assert rv.status_code == 201, rv.text
    assert rv.json()["doc_version"] == 2
    view = rv.json()["view"]
    view_id = view["id"]
    assert view["ref_pinned_version"] is None
    assert view["scale"] == {"numerator": 1, "denominator": 2}
    assert view["projection"] == "iso"
    assert view["position"] == {"x_mm": 50.0, "y_mm": 50.0}

    rd = client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {
                "type": "diameter",
                "edge": _edge_sig("circle", 31.4),
            },
        },
        headers=_headers(),
    )
    assert rd.status_code == 201, rd.text
    assert rd.json()["doc_version"] == 3
    assert rd.json()["dimension"]["dimension"]["type"] == "diameter"

    ra = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations",
        json={
            "expected_version": 3,
            "annotation": {
                "type": "note",
                "text": "Break all sharp edges",
                "position": {"x_mm": 10.0, "y_mm": 20.0},
            },
        },
        headers=_headers(),
    )
    assert ra.status_code == 201, ra.text
    assert ra.json()["doc_version"] == 4

    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert tree["doc_version"] == 4
    assert tree["drawing"]["name"] == "bracket-detail"
    assert tree["drawing"]["owner_id"] == OWNER
    assert len(tree["sheets"]) == 1
    content = tree["sheets"][0]
    assert content["sheet"]["size"] == "A3"
    assert content["sheet"]["orientation"] == "portrait"
    assert [v["id"] for v in content["views"]] == [view_id]
    assert content["dimensions"][0]["view_id"] == view_id
    assert content["dimensions"][0]["dimension"]["edge"]["curve"] == "circle"
    assert content["annotations"][0]["annotation"]["text"] == "Break all sharp edges"


def test_list_drawings_owner_scoped(client: TestClient) -> None:
    _create_drawing(client, "mine-1")
    _create_drawing(client, "mine-2")
    _create_drawing(client, "theirs", owner=OTHER)

    body = client.get("/api/v1/drawings", headers=_headers()).json()
    assert [d["name"] for d in body["drawings"]] == ["mine-1", "mine-2"]


def test_duplicate_drawing_name_is_409(client: TestClient) -> None:
    _create_drawing(client, "dup")
    response = client.post("/api/v1/drawings", json={"name": "dup"}, headers=_headers())
    assert response.status_code == 409
    assert _error(response.json())["code"] == "drawing_name_taken"


# --- cross-document integrity -----------------------------------------------------


def test_view_reference_to_missing_document_is_422(client: TestClient) -> None:
    drawing_id = _create_drawing(client, "dangle")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    missing = "6f3f6b64-0000-4000-8000-0000000000ff"
    response = _add_view(client, drawing_id, sheet_id, missing, 1)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


def test_view_cannot_reference_another_owners_part(client: TestClient) -> None:
    drawing_id = _create_drawing(client, "borrow")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    foreign_part = _create_part(client, "foreign", owner=OTHER)
    response = _add_view(client, drawing_id, sheet_id, foreign_part, 1)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


def test_delete_part_referenced_by_drawing_view_is_409(client: TestClient) -> None:
    part = _create_part(client, "shared-part")
    drawing_id = _create_drawing(client, "uses-part")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    _add_view(client, drawing_id, sheet_id, part, 1)

    response = client.delete(f"/api/v1/parts/{part}", headers=_headers())
    assert response.status_code == 409
    error = _error(response.json())
    assert error["code"] == "part_has_dependents"
    dependents = error["details"]["dependents"]
    assert dependents[0]["name"] == "uses-part"
    assert dependents[0]["kind"] == "drawing"


def _datum_envelope(offset_mm: float = 30.0) -> dict[str, Any]:
    """An offset datum plane feature (the section-view cutting-plane target)."""
    return {
        "type": "datum",
        "version": 1,
        "params": {"base": "XY", "offset_mm": offset_mm, "flip": False},
    }


def _add_feature(
    client: TestClient, part_id: str, name: str, feature: dict[str, Any], expected: int
) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": name, "feature": feature, "expected_tree_version": expected},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def test_undo_removing_sectioned_feature_blocked_like_delete(
    client: TestClient,
) -> None:
    """Audit P2 #16 — undo must honour the SAME cross-document protection a direct
    delete does. A drawing section view whose cutting plane is a FeatureRef into a
    datum feature depends on that feature; both a direct delete AND an undo that
    would remove the datum are blocked with a typed 409, so the section view never
    silently breaks (a `failed: true` empty box on the print)."""
    part = _create_part(client, "sectioned")
    # One part mutation → tree_version 1; undo from here reverts to the empty tree,
    # removing the datum the section view references.
    datum_id = _add_feature(client, part, "Plane1", _datum_envelope(), 0)

    drawing_id = _create_drawing(client, "section-detail")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    rv = _add_view(
        client,
        drawing_id,
        sheet_id,
        part,
        1,
        projection="section",
        section_params={
            "plane": {"kind": "feature", "feature_id": datum_id},
            "flip": False,
        },
    )
    assert rv.status_code == 201, rv.text

    # Direct delete of the depended-on datum is blocked and lists the drawing.
    deleted = client.delete(
        f"/api/v1/parts/{part}/features/{datum_id}",
        params={"expected_tree_version": 1},
        headers=_headers(),
    )
    assert deleted.status_code == 409, deleted.text
    del_err = _error(deleted.json())
    assert del_err["code"] == "feature_has_dependents"
    assert {d["name"]: d.get("kind") for d in del_err["details"]["dependents"]} == {
        "section-detail": "drawing"
    }

    # Undo would remove that SAME datum → now blocked identically (was silent).
    undone = client.post(
        f"/api/v1/parts/{part}/undo",
        json={"expected_tree_version": 1},
        headers=_headers(),
    )
    assert undone.status_code == 409, undone.text
    undo_err = _error(undone.json())
    assert undo_err["code"] == "part_restore_conflict"
    assert undo_err["details"]["reason"] == "section_view_feature_missing"
    assert undo_err["details"]["feature_id"] == datum_id
    assert undo_err["details"]["drawing_name"] == "section-detail"

    # Both were refused, not applied: the datum survives and tree_version is unmoved
    # — the section view is NOT silently broken.
    tree = client.get(f"/api/v1/parts/{part}/features", headers=_headers()).json()
    assert [f["id"] for f in tree["features"]] == [datum_id]
    assert tree["tree_version"] == 1


# --- optimistic concurrency -------------------------------------------------------


def test_stale_expected_version_is_422(client: TestClient) -> None:
    drawing_id = _create_drawing(client, "occ")
    _add_sheet(client, drawing_id, 0)  # bumps to doc_version 1
    stale = _add_sheet(client, drawing_id, 0, name="again")
    assert stale.status_code == 422
    assert _error(stale.json())["code"] == "stale_drawing_version"


# --- auth -------------------------------------------------------------------------


def test_non_owner_gets_uniform_404(client: TestClient) -> None:
    drawing_id = _create_drawing(client, "private")
    response = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers(OTHER))
    assert response.status_code == 404
    assert _error(response.json())["code"] == "drawing_not_found"


def test_missing_principal_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/drawings")
    assert response.status_code == 401


# --- dimension validation (write-time, typed 422) ---------------------------------


def test_diameter_dimension_requires_circular_edge(client: TestClient) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "dim")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {"type": "diameter", "edge": _edge_sig("line")},
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "dimension_requires_circular_edge"


def test_angular_dimension_requires_straight_edges(client: TestClient) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "dim2")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {
                "type": "angular",
                "edge_a": _edge_sig("line"),
                "edge_b": _edge_sig("circle"),
            },
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "dimension_requires_straight_edges"


def test_linear_point_to_point_dimension_round_trips(client: TestClient) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "dim3")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {
                "type": "linear",
                "measurement": {
                    "mode": "point_to_point",
                    "a": {"signature": _edge_sig(), "endpoint": "end_a"},
                    "b": {"signature": _edge_sig(), "endpoint": "end_b"},
                },
            },
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    dim = response.json()["dimension"]["dimension"]
    assert dim["measurement"]["mode"] == "point_to_point"
    assert dim["measurement"]["a"]["endpoint"] == "end_a"


# --- mutation + cascade -----------------------------------------------------------


def test_update_view_reframes(client: TestClient) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "reframe")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        json={
            "expected_version": 2,
            "projection": "top",
            "position": {"x_mm": 120.0, "y_mm": 30.0},
        },
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    view = response.json()["view"]
    assert view["projection"] == "top"
    assert view["position"] == {"x_mm": 120.0, "y_mm": 30.0}


def test_view_defaults_to_auto_place(client: TestClient) -> None:
    """A view created without `auto_place` defaults to bounds-aware auto-layout
    (back-compat) — the flag is present and True on the response."""
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "auto")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]
    assert view["auto_place"] is True


def test_drag_to_place_position_persists_and_survives_reload(
    client: TestClient,
) -> None:
    """The drag-to-place write path: PATCH position + auto_place=false persists a
    hand-placed view, and the position + flag survive a fresh tree read (reload)."""
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "drag")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        json={
            "expected_version": 2,
            "position": {"x_mm": 137.5, "y_mm": 88.25},
            "auto_place": False,
        },
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    view = response.json()["view"]
    assert view["position"] == {"x_mm": 137.5, "y_mm": 88.25}
    assert view["auto_place"] is False

    # Reload: a fresh tree read still carries the authored position + honored flag.
    reloaded = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    reloaded_view = reloaded["sheets"][0]["views"][0]
    assert reloaded_view["position"] == {"x_mm": 137.5, "y_mm": 88.25}
    assert reloaded_view["auto_place"] is False

    # And auto_place can be toggled back to auto-layout on its own.
    back = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        json={"expected_version": 3, "auto_place": True},
        headers=_headers(),
    )
    assert back.status_code == 200, back.text
    assert back.json()["view"]["auto_place"] is True


def test_delete_view_cascades_dimensions_and_renumbers(client: TestClient) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "cascade")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    v1 = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]
    v2 = _add_view(client, drawing_id, sheet_id, part, 2, projection="top").json()[
        "view"
    ]["id"]

    # Two dimensions on v1 (sheet order 0,1), one on v2 (sheet order 2).
    for ev in (3, 4):
        client.post(
            f"/api/v1/drawings/{drawing_id}/views/{v1}/dimensions",
            json={
                "expected_version": ev,
                "dimension": {
                    "type": "linear",
                    "measurement": {"mode": "edge_length", "edge": _edge_sig()},
                },
            },
            headers=_headers(),
        )
    client.post(
        f"/api/v1/drawings/{drawing_id}/views/{v2}/dimensions",
        json={
            "expected_version": 5,
            "dimension": {
                "type": "linear",
                "measurement": {"mode": "edge_length", "edge": _edge_sig()},
            },
        },
        headers=_headers(),
    )

    # Delete v1 → its two dimensions cascade; v2's remaining dimension renumbers.
    response = client.delete(
        f"/api/v1/drawings/{drawing_id}/views/{v1}?expected_version=6",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    tree = response.json()
    content = tree["sheets"][0]
    assert [v["id"] for v in content["views"]] == [v2]
    assert [v["order_index"] for v in content["views"]] == [0]
    assert len(content["dimensions"]) == 1
    assert content["dimensions"][0]["order_index"] == 0
    assert content["dimensions"][0]["view_id"] == v2


def test_delete_sheet_cascades(client: TestClient, any_db_url: str) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "doomed")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]
    client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {
                "type": "linear",
                "measurement": {"mode": "edge_length", "edge": _edge_sig()},
            },
        },
        headers=_headers(),
    )

    assert _row_count(any_db_url, db.View, "sheet_id", sheet_id) == 1
    assert _row_count(any_db_url, db.Dimension, "sheet_id", sheet_id) == 1

    response = client.delete(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}?expected_version=3",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["sheets"] == []
    assert _row_count(any_db_url, db.View, "sheet_id", sheet_id) == 0
    assert _row_count(any_db_url, db.Dimension, "sheet_id", sheet_id) == 0


def test_delete_drawing_cascades_all(client: TestClient, any_db_url: str) -> None:
    part = _create_part(client, "p")
    drawing_id = _create_drawing(client, "gone")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    _add_view(client, drawing_id, sheet_id, part, 1)

    response = client.delete(f"/api/v1/drawings/{drawing_id}", headers=_headers())
    assert response.status_code == 204, response.text
    assert _row_count(any_db_url, db.Sheet, "drawing_id", drawing_id) == 0


def _row_count(
    url: str,
    model: type[db.Sheet] | type[db.View] | type[db.Dimension],
    column: str,
    scope_id: str,
) -> int:
    """Count *model* rows scoped by *column* via a direct (app-independent) engine."""

    async def run() -> int:
        engine = create_async_engine(async_dsn(url))
        enable_sqlite_foreign_keys(engine)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(sa.func.count())
                    .select_from(model)
                    .where(getattr(model, column) == uuid.UUID(scope_id))
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(run())


# --- one sheet, one source document, one scale (engineering audit H2) -------------


def test_view_referencing_another_document_on_the_same_sheet_is_422(
    client: TestClient,
) -> None:
    """A sheet composes from ONE document; a second source is a typed 422, not a
    silently mis-projected export (`documents.drawings._ensure_sheet_source`)."""
    part_a = _create_part(client, "part-a")
    part_b = _create_part(client, "part-b")
    drawing_id = _create_drawing(client, "two-parts")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    assert _add_view(client, drawing_id, sheet_id, part_a, 1).status_code == 201

    response = _add_view(client, drawing_id, sheet_id, part_b, 2, projection="right")
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "sheet_source_document_mismatch"
    assert error["details"]["sheet_ref_document_id"] == part_a
    assert error["details"]["ref_document_id"] == part_b

    # The rejected write left the sheet untouched (one view, version unchanged).
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert len(tree["sheets"][0]["views"]) == 1
    assert tree["doc_version"] == 2


def test_view_with_a_different_scale_on_the_same_sheet_is_422(
    client: TestClient,
) -> None:
    part = _create_part(client, "one-part")
    drawing_id = _create_drawing(client, "two-scales")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    assert (
        _add_view(
            client,
            drawing_id,
            sheet_id,
            part,
            1,
            scale={"numerator": 1, "denominator": 2},
        ).status_code
        == 201
    )

    response = _add_view(
        client,
        drawing_id,
        sheet_id,
        part,
        2,
        projection="top",
        scale={"numerator": 1, "denominator": 1},
    )
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "sheet_view_scale_mismatch"
    assert error["details"]["sheet_scale"] == "1:2"
    assert error["details"]["scale"] == "1:1"


def test_second_view_matching_source_and_scale_is_accepted(client: TestClient) -> None:
    """The guard rejects DIVERGENCE only — a consistent multi-view sheet (what the
    frontend's standard layout writes) is unaffected."""
    part = _create_part(client, "consistent")
    drawing_id = _create_drawing(client, "standard-layout")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    scale = {"numerator": 1, "denominator": 2}
    version = 1
    for projection in ("front", "top", "right", "iso"):
        response = _add_view(
            client,
            drawing_id,
            sheet_id,
            part,
            version,
            projection=projection,
            scale=scale,
        )
        assert response.status_code == 201, response.text
        version = response.json()["doc_version"]
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert [v["projection"] for v in tree["sheets"][0]["views"]] == [
        "front",
        "top",
        "right",
        "iso",
    ]


def test_rescaling_one_view_of_a_multi_view_sheet_is_422(client: TestClient) -> None:
    part = _create_part(client, "rescale")
    drawing_id = _create_drawing(client, "rescale-one")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    first = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]
    assert (
        _add_view(client, drawing_id, sheet_id, part, 2, projection="top").status_code
        == 201
    )

    response = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{first}",
        json={"expected_version": 3, "scale": {"numerator": 1, "denominator": 4}},
        headers=_headers(),
    )
    assert response.status_code == 422, response.text
    assert _error(response.json())["code"] == "sheet_view_scale_mismatch"

    # Re-placing that same view (no scale change) still works.
    ok = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{first}",
        json={
            "expected_version": 3,
            "position": {"x_mm": 120.0, "y_mm": 90.0},
            "auto_place": False,
        },
        headers=_headers(),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["view"]["auto_place"] is False


def test_rescaling_the_only_view_of_a_sheet_is_allowed(client: TestClient) -> None:
    part = _create_part(client, "lone")
    drawing_id = _create_drawing(client, "lone-view")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    view_id = _add_view(client, drawing_id, sheet_id, part, 1).json()["view"]["id"]

    response = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}",
        json={"expected_version": 2, "scale": {"numerator": 1, "denominator": 4}},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["view"]["scale"] == {"numerator": 1, "denominator": 4}


# --- one view per projection per sheet (engineering audit H3) ---------------------


def test_duplicate_projection_on_one_sheet_is_422(client: TestClient) -> None:
    """The compose layer + the frontend key views by PROJECTION, so a second
    `section` view collapsed to one composed view and made a drag-to-place PATCH
    write to the OTHER row. Now a typed refusal (uq_views_sheet_projection)."""
    part = _create_part(client, "sectioned")
    drawing_id = _create_drawing(client, "two-sections")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    first = _add_view(
        client,
        drawing_id,
        sheet_id,
        part,
        1,
        projection="section",
        section_params={
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "flip": False,
        },
    )
    assert first.status_code == 201, first.text

    response = _add_view(
        client,
        drawing_id,
        sheet_id,
        part,
        2,
        projection="section",
        section_params={
            "plane": {"kind": "datum_plane", "plane": "YZ"},
            "flip": False,
        },
    )
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "duplicate_view_projection"
    assert error["details"]["projection"] == "section"
    assert error["details"]["existing_view_id"] == first.json()["view"]["id"]

    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert len(tree["sheets"][0]["views"]) == 1


def test_duplicate_projection_on_another_sheet_is_allowed(client: TestClient) -> None:
    """Uniqueness is PER SHEET — two sheets may each carry a front view."""
    part = _create_part(client, "two-sheets-part")
    drawing_id = _create_drawing(client, "two-sheets")
    sheet_a = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    sheet_b = _add_sheet(client, drawing_id, 1, name="Sheet 2").json()["sheet"]["id"]
    assert _add_view(client, drawing_id, sheet_a, part, 2).status_code == 201
    assert _add_view(client, drawing_id, sheet_b, part, 3).status_code == 201


def test_reprojecting_a_view_onto_an_existing_projection_is_422(
    client: TestClient,
) -> None:
    part = _create_part(client, "reproject")
    drawing_id = _create_drawing(client, "reproject-clash")
    sheet_id = _add_sheet(client, drawing_id, 0).json()["sheet"]["id"]
    assert _add_view(client, drawing_id, sheet_id, part, 1).status_code == 201
    top = _add_view(client, drawing_id, sheet_id, part, 2, projection="top").json()

    response = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{top['view']['id']}",
        json={"expected_version": 3, "projection": "front"},
        headers=_headers(),
    )
    assert response.status_code == 422, response.text
    assert _error(response.json())["code"] == "duplicate_view_projection"

    # Re-projecting onto a FREE projection still works, as does a no-op re-write
    # of the view's own projection.
    ok = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{top['view']['id']}",
        json={"expected_version": 3, "projection": "right"},
        headers=_headers(),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["view"]["projection"] == "right"
    same = client.patch(
        f"/api/v1/drawings/{drawing_id}/views/{top['view']['id']}",
        json={"expected_version": 4, "projection": "right"},
        headers=_headers(),
    )
    assert same.status_code == 200, same.text
