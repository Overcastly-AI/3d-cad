"""documents drawing BOM — the DERIVED item list a balloon numbers (drawings §7).

``GET /api/v1/drawings/{drawing_id}/bom`` is a pure read model: the selected
sheet's single source document must be an ASSEMBLY, and its DIRECT instances roll
up into ``item_number``-ed lines. The load-bearing property this suite pins is the
identity decision — **item numbers are derived, never stored** — and its two
observable consequences:

* numbering follows the assembly's own stable instance ``order_index`` (first
  appearance), NOT the name-sorted order ``GET /assemblies/{id}/bom`` reports, so a
  part RENAME can never renumber a print while the two BOMs disagree on order by
  construction;
* a real graph edit (add / remove / reorder an instance) DOES renumber, and the
  echoed ``assembly_version`` moves with it — the staleness handle for a
  tip-tracking view (§2.3).

Every failure is typed rather than an empty list: a PART sheet is
``drawing_bom_source_not_assembly``, a viewless sheet ``sheet_has_no_views``, an
unknown/foreign sheet ``sheet_not_found``, and another owner's drawing a uniform
404. Same dialect posture as tests/test_drawings.py (SQLite always, real scratch
PostgreSQL with the actual migrations when available).
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents import db
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000020a"
OTHER = "6f3f6b64-0000-4000-8000-00000000020b"


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
    owner: str = OWNER,
) -> str:
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": expected_version,
            "ref_document_id": ref_document_id,
            "ref_document_kind": ref_document_kind,
            "name": name,
        },
        headers=_headers(owner),
    )
    assert response.status_code == 201, response.text
    instance_id: str = response.json()["instance"]["id"]
    return instance_id


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
) -> tuple[str, int]:
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets",
        json={"expected_version": expected_version, "name": name},
        headers=_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["sheet"]["id"], int(response.json()["doc_version"])


def _add_view(
    client: TestClient,
    drawing_id: str,
    sheet_id: str,
    ref_document_id: str,
    expected_version: int,
    *,
    ref_document_kind: str = "assembly",
    projection: str = "front",
    owner: str = OWNER,
) -> int:
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        json={
            "expected_version": expected_version,
            "ref_document_id": ref_document_id,
            "ref_document_kind": ref_document_kind,
            "projection": projection,
            "position": {"x_mm": 50.0, "y_mm": 50.0},
        },
        headers=_headers(owner),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["doc_version"])


def _bom(
    client: TestClient,
    drawing_id: str,
    *,
    sheet: str | None = None,
    owner: str = OWNER,
) -> Any:
    return client.get(
        f"/api/v1/drawings/{drawing_id}/bom",
        params={"sheet": sheet} if sheet is not None else None,
        headers=_headers(owner),
    )


def _drawing_of(
    client: TestClient,
    name: str,
    ref_document_id: str,
    *,
    ref_document_kind: str = "assembly",
) -> tuple[str, str]:
    """A one-sheet, one-view drawing of *ref_document_id* → (drawing_id, sheet_id)."""
    drawing_id = _create_drawing(client, name)
    sheet_id, version = _add_sheet(client, drawing_id, 0)
    _add_view(
        client,
        drawing_id,
        sheet_id,
        ref_document_id,
        version,
        ref_document_kind=ref_document_kind,
    )
    return drawing_id, sheet_id


def _rename_part(client: TestClient, part_id: str, name: str) -> None:
    """Rename a freshly-created (feature-less, ``tree_version`` 0) part."""
    response = client.patch(
        f"/api/v1/parts/{part_id}",
        json={"name": name, "expected_tree_version": 0},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text


def _reorder_instance(
    client: TestClient,
    assembly_id: str,
    instance_id: str,
    expected_version: int,
    order_index: int,
) -> None:
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        json={"expected_version": expected_version, "order_index": order_index},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text


def _delete_part_row(db_url: str, part_id: str) -> None:
    """Delete a part row DIRECTLY, bypassing the 409-with-dependents pre-check.

    The same forced state ``test_assemblies.py`` uses for its dangling-reference
    BOM case: instances reference a part by cross-document id, not a DB FK, so a
    delete/add race can leave a line whose document is gone. The drawing BOM must
    report it ``missing`` — with its item number and quantity intact — never 500.
    """

    async def run() -> None:
        engine = create_async_engine(async_dsn(db_url))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                part = await session.get(db.Part, uuid.UUID(part_id))
                assert part is not None
                await session.delete(part)
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


# --- the derived item list ---------------------------------------------------------


def test_bom_numbers_items_in_assembly_instance_order(client: TestClient) -> None:
    """Items are numbered by FIRST APPEARANCE in the assembly's instance order.

    Part names are chosen so alphabetical order is the REVERSE of insertion order:
    the drawing BOM must follow insertion (1 = zeta, 2 = alpha), proving the number
    comes from ``order_index`` and not from the name sort.
    """
    assembly_id = _create_assembly(client, "bom-order")
    zeta = _create_part(client, "zeta")
    alpha = _create_part(client, "alpha")

    _add_instance(client, assembly_id, zeta, 0, name="Zeta <1>")
    _add_instance(client, assembly_id, alpha, 1, name="Alpha <1>")
    _add_instance(client, assembly_id, zeta, 2, name="Zeta <2>")

    drawing_id, sheet_id = _drawing_of(client, "bom-order-dwg", assembly_id)
    response = _bom(client, drawing_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["drawing_id"] == drawing_id
    assert body["sheet_id"] == sheet_id
    assert body["assembly_id"] == assembly_id
    assert body["assembly_version"] == 3
    assert body["total_instances"] == 3
    assert body["lines"] == [
        {
            "item_number": 1,
            "ref_document_id": zeta,
            "ref_document_kind": "part",
            "name": "zeta",
            "missing": False,
            "quantity": 2,
            "item": "1",
            "level": 0,
            "total_quantity": 2,
        },
        {
            "item_number": 2,
            "ref_document_id": alpha,
            "ref_document_kind": "part",
            "name": "alpha",
            "missing": False,
            "quantity": 1,
            "item": "2",
            "level": 0,
            "total_quantity": 1,
        },
    ]


def test_bom_order_differs_from_the_name_sorted_assembly_bom(
    client: TestClient,
) -> None:
    """The two BOMs are deliberately different orderings of the same roll-up.

    ``/assemblies/{id}/bom`` sorts by resolved NAME (a display convenience);
    ``/drawings/{id}/bom`` numbers by instance ORDER (so a rename cannot renumber).
    Asserting they disagree here keeps a future "just reuse the other one"
    refactor from silently making item numbers name-dependent.
    """
    assembly_id = _create_assembly(client, "bom-two-orders")
    zeta = _create_part(client, "zeta")
    alpha = _create_part(client, "alpha")
    _add_instance(client, assembly_id, zeta, 0, name="Zeta <1>")
    _add_instance(client, assembly_id, alpha, 1, name="Alpha <1>")

    drawing_id, _ = _drawing_of(client, "bom-two-orders-dwg", assembly_id)

    assembly_bom = client.get(
        f"/api/v1/assemblies/{assembly_id}/bom", headers=_headers()
    ).json()
    assert [line["name"] for line in assembly_bom["lines"]] == ["alpha", "zeta"]

    drawing_bom = _bom(client, drawing_id).json()
    assert [line["name"] for line in drawing_bom["lines"]] == ["zeta", "alpha"]


def test_renaming_a_part_never_renumbers_the_drawing_bom(client: TestClient) -> None:
    """A RENAME re-sorts the assembly BOM but leaves every item number untouched.

    This is the whole point of numbering off ``order_index``: a released print
    balloons item 1, someone renames the part, and the print still means item 1.
    """
    assembly_id = _create_assembly(client, "bom-rename")
    zeta = _create_part(client, "zeta")
    alpha = _create_part(client, "alpha")
    _add_instance(client, assembly_id, zeta, 0, name="Zeta <1>")
    _add_instance(client, assembly_id, alpha, 1, name="Alpha <1>")

    drawing_id, _ = _drawing_of(client, "bom-rename-dwg", assembly_id)
    before = _bom(client, drawing_id).json()
    assert [(line["item_number"], line["ref_document_id"]) for line in before["lines"]]
    numbering = {
        line["ref_document_id"]: line["item_number"] for line in before["lines"]
    }

    # Flip the alphabetical order of the two parts.
    _rename_part(client, zeta, "aaa-zeta")
    _rename_part(client, alpha, "zzz-alpha")

    after = _bom(client, drawing_id).json()
    assert {
        line["ref_document_id"]: line["item_number"] for line in after["lines"]
    } == numbering
    assert [line["name"] for line in after["lines"]] == ["aaa-zeta", "zzz-alpha"]
    # The name-sorted assembly BOM DID flip — the rename was real.
    assembly_bom = client.get(
        f"/api/v1/assemblies/{assembly_id}/bom", headers=_headers()
    ).json()
    assert [line["name"] for line in assembly_bom["lines"]] == ["aaa-zeta", "zzz-alpha"]


def test_adding_an_instance_appends_without_renumbering_existing_items(
    client: TestClient,
) -> None:
    """A new part takes the NEXT item number; existing numbers are unchanged.

    The common assembly edit under a live drawing. ``assembly_version`` moves, so a
    client that cached a BOM can tell the source changed (§2.3 staleness handle).
    """
    assembly_id = _create_assembly(client, "bom-append")
    first = _create_part(client, "first")
    _add_instance(client, assembly_id, first, 0, name="First <1>")

    drawing_id, _ = _drawing_of(client, "bom-append-dwg", assembly_id)
    before = _bom(client, drawing_id).json()
    assert before["assembly_version"] == 1
    assert [line["item_number"] for line in before["lines"]] == [1]

    second = _create_part(client, "second")
    _add_instance(client, assembly_id, second, 1, name="Second <1>")

    after = _bom(client, drawing_id).json()
    assert after["assembly_version"] == 2
    assert [
        (line["item_number"], line["ref_document_id"]) for line in after["lines"]
    ] == [(1, first), (2, second)]


def test_reordering_instances_renumbers_and_says_so_via_the_version(
    client: TestClient,
) -> None:
    """A REORDER genuinely renumbers — an honest consequence, not a bug.

    Item numbers are a function of the assembly graph, so a deliberate reorder
    changes them (and bumps ``assembly_version``). Nothing downstream may cache a
    number: this test is the executable statement of that contract.
    """
    assembly_id = _create_assembly(client, "bom-reorder")
    first = _create_part(client, "first")
    second = _create_part(client, "second")
    _add_instance(client, assembly_id, first, 0, name="First <1>")
    later = _add_instance(client, assembly_id, second, 1, name="Second <1>")

    drawing_id, _ = _drawing_of(client, "bom-reorder-dwg", assembly_id)
    before = _bom(client, drawing_id).json()
    assert [
        (line["item_number"], line["ref_document_id"]) for line in before["lines"]
    ] == [(1, first), (2, second)]

    _reorder_instance(client, assembly_id, later, before["assembly_version"], 0)

    after = _bom(client, drawing_id).json()
    assert after["assembly_version"] > before["assembly_version"]
    assert [
        (line["item_number"], line["ref_document_id"]) for line in after["lines"]
    ] == [(1, second), (2, first)]


def test_bom_sub_assembly_is_one_top_level_line(client: TestClient) -> None:
    """A rigid sub-assembly instance is a single ``kind: 'assembly'`` item, and
    the drawing's parts list is the assembly BOM's TOP LEVEL: same documents,
    same quantities, same total (SolidWorks' default drawing BOM). The parts
    inside are on the assembly BOM's indented and parts-only views."""
    parent = _create_assembly(client, "bom-parent")
    child = _create_assembly(client, "bom-child")
    part = _create_part(client, "bom-leaf")
    _add_instance(client, child, part, 0, name="Leaf <1>")
    _add_instance(client, child, part, 1, name="Leaf <2>")
    _add_instance(
        client, parent, child, 0, ref_document_kind="assembly", name="Sub <1>"
    )
    _add_instance(
        client, parent, child, 1, ref_document_kind="assembly", name="Sub <2>"
    )

    drawing_id, _ = _drawing_of(client, "bom-nested-dwg", parent)
    body = _bom(client, drawing_id).json()
    assert body["total_instances"] == 2
    [line] = body["lines"]
    assert line["item_number"] == 1
    assert line["ref_document_kind"] == "assembly"
    assert line["ref_document_id"] == child
    assert line["name"] == "bom-child"
    assert line["quantity"] == 2

    assembly_bom = client.get(
        f"/api/v1/assemblies/{parent}/bom", headers=_headers()
    ).json()
    assert [(x["ref_document_id"], x["quantity"]) for x in assembly_bom["lines"]] == [
        (x["ref_document_id"], x["quantity"]) for x in body["lines"]
    ]
    assert assembly_bom["total_instances"] == body["total_instances"]
    assert assembly_bom["total_parts"] == 4


def test_bom_of_an_empty_assembly_is_an_empty_item_list(client: TestClient) -> None:
    """No instances → no lines, zero total — a true statement, and a 200."""
    assembly_id = _create_assembly(client, "bom-empty")
    drawing_id, sheet_id = _drawing_of(client, "bom-empty-dwg", assembly_id)
    body = _bom(client, drawing_id).json()
    assert body == {
        "drawing_id": drawing_id,
        "sheet_id": sheet_id,
        "assembly_id": assembly_id,
        "assembly_version": 0,
        "structure": "top_level",
        "lines": [],
        "total_instances": 0,
        "total_parts": 0,
    }


def test_bom_deleted_reference_keeps_its_number_and_is_flagged_missing(
    client: TestClient, any_db_url: str
) -> None:
    """A dangling reference stays a numbered line with ``missing`` true, never a 500.

    The quantity and the item number both survive (the instances still exist), so a
    balloon pointing at it renders as a flagged item rather than silently vanishing.
    """
    assembly_id = _create_assembly(client, "bom-dangling")
    live = _create_part(client, "live")
    doomed = _create_part(client, "doomed")
    _add_instance(client, assembly_id, live, 0, name="Live <1>")
    _add_instance(client, assembly_id, doomed, 1, name="Doomed <1>")
    _add_instance(client, assembly_id, doomed, 2, name="Doomed <2>")

    drawing_id, _ = _drawing_of(client, "bom-dangling-dwg", assembly_id)
    _delete_part_row(any_db_url, doomed)

    response = _bom(client, drawing_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_instances"] == 3
    assert body["lines"] == [
        {
            "item_number": 1,
            "ref_document_id": live,
            "ref_document_kind": "part",
            "name": "live",
            "missing": False,
            "quantity": 1,
            "item": "1",
            "level": 0,
            "total_quantity": 1,
        },
        {
            "item_number": 2,
            "ref_document_id": doomed,
            "ref_document_kind": "part",
            "name": None,
            "missing": True,
            "quantity": 2,
            "item": "2",
            "level": 0,
            "total_quantity": 2,
        },
    ]


# --- sheet selection ---------------------------------------------------------------


def test_sheet_query_selects_which_sheet_is_billed(client: TestClient) -> None:
    """``?sheet=`` bills that sheet's own assembly; omitting it bills the first.

    The same selector the compose/export routes take, so a multi-sheet drawing
    whose sheets draft different assemblies bills each one correctly.
    """
    first_assembly = _create_assembly(client, "bom-sheet-a")
    second_assembly = _create_assembly(client, "bom-sheet-b")
    part_a = _create_part(client, "part-a")
    part_b = _create_part(client, "part-b")
    _add_instance(client, first_assembly, part_a, 0, name="A <1>")
    _add_instance(client, second_assembly, part_b, 0, name="B <1>")

    drawing_id, sheet_a = _drawing_of(client, "bom-sheets-dwg", first_assembly)
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    sheet_b, version = _add_sheet(
        client, drawing_id, tree["doc_version"], name="Sheet 2"
    )
    _add_view(client, drawing_id, sheet_b, second_assembly, version)

    default_bom = _bom(client, drawing_id).json()
    assert default_bom["sheet_id"] == sheet_a
    assert default_bom["assembly_id"] == first_assembly
    assert [line["name"] for line in default_bom["lines"]] == ["part-a"]

    second_bom = _bom(client, drawing_id, sheet=sheet_b).json()
    assert second_bom["sheet_id"] == sheet_b
    assert second_bom["assembly_id"] == second_assembly
    assert [line["name"] for line in second_bom["lines"]] == ["part-b"]


# --- typed refusals ----------------------------------------------------------------


def test_part_sheet_has_no_bom_and_says_so(client: TestClient) -> None:
    """A PART drawing is a typed 422, NOT a 200 with an empty item list.

    An empty list would read as "this assembly has no parts" — a different and
    false statement. The refusal names the source so a client can explain it.
    """
    part_id = _create_part(client, "lonely-bracket")
    drawing_id, sheet_id = _drawing_of(
        client, "part-dwg", part_id, ref_document_kind="part"
    )
    response = _bom(client, drawing_id)
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "drawing_bom_source_not_assembly"
    assert error["details"]["sheet_id"] == sheet_id
    assert error["details"]["ref_document_id"] == part_id


def test_sheet_with_no_views_is_a_typed_422(client: TestClient) -> None:
    """Nothing laid out ⇒ no source document ⇒ ``sheet_has_no_views``."""
    drawing_id = _create_drawing(client, "bare-dwg")
    sheet_id, _ = _add_sheet(client, drawing_id, 0)
    response = _bom(client, drawing_id)
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "sheet_has_no_views"
    assert error["details"]["sheet_id"] == sheet_id


def test_drawing_with_no_sheets_is_sheet_not_found(client: TestClient) -> None:
    """No sheet to bill at all → 404 ``sheet_not_found`` (the drawing exists)."""
    drawing_id = _create_drawing(client, "sheetless-dwg")
    response = _bom(client, drawing_id)
    assert response.status_code == 404, response.text
    assert _error(response.json())["code"] == "sheet_not_found"


def test_foreign_sheet_id_is_sheet_not_found(client: TestClient) -> None:
    """A sheet id from ANOTHER drawing is a 404, not that drawing's BOM."""
    assembly_id = _create_assembly(client, "bom-foreign-sheet")
    mine, _ = _drawing_of(client, "mine-dwg", assembly_id)
    _, other_sheet = _drawing_of(client, "other-dwg", assembly_id)

    response = _bom(client, mine, sheet=other_sheet)
    assert response.status_code == 404, response.text
    assert _error(response.json())["code"] == "sheet_not_found"


def test_source_assembly_deleted_out_from_under_the_sheet_is_typed(
    client: TestClient, any_db_url: str
) -> None:
    """A vanished source assembly is a typed 422, never a 500 or a bare 404.

    The API refuses to delete a referenced document (409-with-dependents), so this
    forces the raced state at the persistence layer — the BOM must still explain
    itself rather than crash.
    """
    assembly_id = _create_assembly(client, "bom-doomed-assembly")
    drawing_id, sheet_id = _drawing_of(client, "doomed-src-dwg", assembly_id)

    async def drop() -> None:
        engine = create_async_engine(async_dsn(any_db_url))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                assembly = await session.get(db.Assembly, uuid.UUID(assembly_id))
                assert assembly is not None
                await session.delete(assembly)
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(drop())

    response = _bom(client, drawing_id)
    assert response.status_code == 422, response.text
    error = _error(response.json())
    assert error["code"] == "drawing_bom_source_missing"
    assert error["details"]["sheet_id"] == sheet_id


def test_bom_owner_isolation_is_a_uniform_404(client: TestClient) -> None:
    """Another owner's drawing is indistinguishable from an unknown one."""
    assembly_id = _create_assembly(client, "bom-mine")
    drawing_id, _ = _drawing_of(client, "mine-only-dwg", assembly_id)
    response = _bom(client, drawing_id, owner=OTHER)
    assert response.status_code == 404, response.text
    assert _error(response.json())["code"] == "drawing_not_found"


# --- the parts list's structure (DRAWING-PARTS-LIST-LEVEL) ----------------------


def _set_structure(
    client: TestClient, drawing_id: str, sheet_id: str, structure: str
) -> Any:
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    return client.patch(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
        json={
            "expected_version": tree["doc_version"],
            "parts_list_structure": structure,
        },
        headers=_headers(),
    )


def _bike(client: TestClient) -> dict[str, str]:
    """Frame, Fork, Crankset (2 arms), and 2 x Wheel (hub, rim, 32 spokes)."""
    ids = {
        name: _create_part(client, name)
        for name in ("Frame", "Fork", "Crank arm", "Hub", "Rim", "Spoke")
    }
    crankset = _create_assembly(client, "Crankset")
    _add_instance(client, crankset, ids["Crank arm"], 0, name="Arm <1>")
    _add_instance(client, crankset, ids["Crank arm"], 1, name="Arm <2>")
    wheel = _create_assembly(client, "Wheel")
    for version, name in enumerate(("Hub", "Rim", *["Spoke"] * 32)):
        _add_instance(client, wheel, ids[name], version, name=f"{name} <{version}>")
    bike = _create_assembly(client, "Bike")
    _add_instance(client, bike, ids["Frame"], 0, name="Frame <1>")
    _add_instance(client, bike, ids["Fork"], 1, name="Fork <1>")
    _add_instance(
        client, bike, crankset, 2, ref_document_kind="assembly", name="Crankset <1>"
    )
    for version in (3, 4):
        _add_instance(
            client,
            bike,
            wheel,
            version,
            ref_document_kind="assembly",
            name=f"Wheel <{version}>",
        )
    return ids | {"Crankset": crankset, "Wheel": wheel, "Bike": bike}


def _rows(body: dict[str, Any]) -> list[tuple[str, str | None, int, int]]:
    return [
        (line["item"], line["name"], line["quantity"], line["total_quantity"])
        for line in body["lines"]
    ]


def test_a_sheet_starts_top_level_and_stores_its_structure(
    client: TestClient,
) -> None:
    """Top level is the default (SolidWorks, Fusion); the choice is stored on the
    sheet, read back by the tree, and the BOM follows it on every read."""
    ids = _bike(client)
    drawing_id, sheet_id = _drawing_of(client, "bike-dwg", ids["Bike"])
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert tree["sheets"][0]["sheet"]["parts_list_structure"] == "top_level"
    body = _bom(client, drawing_id).json()
    assert body["structure"] == "top_level"
    assert _rows(body) == [
        ("1", "Frame", 1, 1),
        ("2", "Fork", 1, 1),
        ("3", "Crankset", 1, 1),
        ("4", "Wheel", 2, 2),
    ]
    assert [line["item_number"] for line in body["lines"]] == [1, 2, 3, 4]
    assert body["total_instances"] == 5
    assert body["total_parts"] == 2 + 2 + 2 * 34

    response = _set_structure(client, drawing_id, sheet_id, "indented")
    assert response.status_code == 200, response.text
    assert response.json()["sheet"]["parts_list_structure"] == "indented"
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers()).json()
    assert tree["sheets"][0]["sheet"]["parts_list_structure"] == "indented"
    assert _bom(client, drawing_id).json()["structure"] == "indented"


def test_indented_numbers_each_sub_assembly_under_its_top_level_item(
    client: TestClient,
) -> None:
    """The bike's acceptance: 4.3 Spoke 32 under the wheel (64 in all), and the
    top-level rows keep their top-level numbers."""
    ids = _bike(client)
    drawing_id, sheet_id = _drawing_of(client, "bike-indented", ids["Bike"])
    _set_structure(client, drawing_id, sheet_id, "indented")
    body = _bom(client, drawing_id).json()
    assert _rows(body) == [
        ("1", "Frame", 1, 1),
        ("2", "Fork", 1, 1),
        ("3", "Crankset", 1, 1),
        ("3.1", "Crank arm", 2, 2),
        ("4", "Wheel", 2, 2),
        ("4.1", "Hub", 1, 2),
        ("4.2", "Rim", 1, 2),
        ("4.3", "Spoke", 32, 64),
    ]
    assert [line["level"] for line in body["lines"]] == [0, 0, 0, 1, 0, 1, 1, 1]
    assert [line["item_number"] for line in body["lines"]] == [1, 2, 3, 1, 4, 1, 2, 3]

    # A rename re-sorts the assembly page's name-ordered BOM, never these numbers.
    _rename_part(client, ids["Hub"], "Zz hub")
    renamed = _bom(client, drawing_id).json()
    assert renamed["lines"][5]["item"] == "4.1"
    assert renamed["lines"][5]["name"] == "Zz hub"


def test_parts_only_lists_every_part_once_numbered_in_walk_order(
    client: TestClient,
) -> None:
    """Parts only: 64 spokes, numbered 1..n in the order the indented walk meets
    each part."""
    ids = _bike(client)
    drawing_id, sheet_id = _drawing_of(client, "bike-parts", ids["Bike"])
    _set_structure(client, drawing_id, sheet_id, "parts_only")
    body = _bom(client, drawing_id).json()
    assert body["structure"] == "parts_only"
    assert _rows(body) == [
        ("1", "Frame", 1, 1),
        ("2", "Fork", 1, 1),
        ("3", "Crank arm", 2, 2),
        ("4", "Hub", 2, 2),
        ("5", "Rim", 2, 2),
        ("6", "Spoke", 64, 64),
    ]
    assert all(line["level"] == 0 for line in body["lines"])
    assert body["total_parts"] == sum(line["quantity"] for line in body["lines"])


def test_an_unknown_structure_is_refused(client: TestClient) -> None:
    ids = _bike(client)
    drawing_id, sheet_id = _drawing_of(client, "bike-bad", ids["Bike"])
    response = _set_structure(client, drawing_id, sheet_id, "all_levels")
    assert response.status_code == 422, response.text
    assert _bom(client, drawing_id).json()["structure"] == "top_level"


def test_a_duplicated_drawing_keeps_its_structure(client: TestClient) -> None:
    ids = _bike(client)
    drawing_id, sheet_id = _drawing_of(client, "bike-dup", ids["Bike"])
    _set_structure(client, drawing_id, sheet_id, "parts_only")
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/duplicate", json={}, headers=_headers()
    )
    assert response.status_code == 201, response.text
    copy_id = response.json()["id"]
    assert _bom(client, copy_id).json()["structure"] == "parts_only"
