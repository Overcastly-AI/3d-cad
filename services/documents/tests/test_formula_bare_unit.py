"""Bare numbers in formulas of a non-mm part (FORMULA-BARE-UNIT).

:mod:`loft_wire.bare_units` through documents. Pinned here:

* in an inch part, a feature formula ``wall + 1/2`` is stored as
  ``wall + 1 in/2`` and gives 6 in; ``W/2 + 3`` adds 3 in; ``W*2`` and ``W/2``
  are stored as typed; an mm part stores exactly what was typed;
* a parameter row and a sketch dimension entered in the part follow the same
  rule;
* a formula stored before the rule (seeded in mm, then the part re-united to
  inches) builds as before and carries ``expression_bare_mm``; saving the
  feature or the table again without touching it changes nothing; the fix
  is an ordinary edit, and undo restores the old formula and its warning.
"""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.bare_unit_scan import run_scan
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000002b7"}
IN = 25.4


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'documents.db'}"
    asyncio.run(_create_schema(url))
    with TestClient(build_app(DocumentsSettings(postgres_url=url))) as test_client:
        yield test_client


def _row(name: str, expression: str, row_id: str | None = None) -> dict[str, Any]:
    return {
        "id": row_id or str(uuid.uuid4()),
        "name": name,
        "expression": expression,
        "unit": "length",
    }


SKETCH: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0, "y": 0},
                "end": {"x": 40, "y": 0},
            },
            {
                "id": "e2",
                "kind": "line",
                "start": {"x": 0, "y": 5},
                "end": {"x": 40, "y": 5},
            },
        ],
        "constraints": [],
    },
}


def _extrude(sketch_id: str, formula: str) -> dict[str, Any]:
    return {
        "type": "extrude",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": 10.0,
            "operation": "add",
            "direction": "normal",
        },
        "expressions": {"/distance_mm": formula},
    }


class Part:
    def __init__(self, client: TestClient, unit: str) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"P {uuid.uuid4()}", "length_unit": unit},
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = int(self.tree()["tree_version"])

    def tree(self) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def table(self) -> dict[str, Any]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/parameters", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def put(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        inputs = [{k: v for k, v in row.items() if k != "value"} for row in rows]
        response = self.client.put(
            f"/api/v1/parts/{self.id}/parameters",
            json={"expected_tree_version": self.version, "parameters": inputs},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        self.version = int(body["tree_version"])
        return body

    def add(self, feature: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": "F",
                "feature": feature,
                "expected_tree_version": self.version,
            },
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        self.version = int(body["tree_version"])
        return body["feature"]

    def patch(self, feature_id: str, feature: dict[str, Any]) -> dict[str, Any]:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            json={"feature": feature, "expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        self.version = int(body["tree_version"])
        return body["feature"]

    def unit(self, unit: str) -> None:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}",
            json={"length_unit": unit, "expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])

    def undo(self) -> None:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/undo",
            json={"expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])


def _walled(client: TestClient, unit: str) -> tuple[Part, str]:
    part = Part(client, unit)
    part.put([_row("wall", "5.5 in"), _row("W", "48 in")])
    return part, part.add(SKETCH)["id"]


@pytest.mark.parametrize(
    ("typed", "stored", "inches"),
    [
        ("wall + 1/2", "wall + 1 in/2", 6.0),
        ("W/2 + 3", "W/2 + 3 in", 27.0),
        ("W*2", "W*2", 96.0),
        ("W/2", "W/2", 24.0),
    ],
)
def test_an_inch_part_reads_a_bare_term_in_inches(
    client: TestClient, typed: str, stored: str, inches: float
) -> None:
    part, sketch_id = _walled(client, "in")
    feature = part.add(_extrude(sketch_id, typed))
    assert feature["feature"]["expressions"] == {"/distance_mm": stored}
    assert feature["feature"]["params"]["distance_mm"] == pytest.approx(inches * IN)
    assert "formula_warnings" not in feature


def test_an_mm_part_stores_exactly_what_was_typed(client: TestClient) -> None:
    part, sketch_id = _walled(client, "mm")
    feature = part.add(_extrude(sketch_id, "wall + 1/2"))
    assert feature["feature"]["expressions"] == {"/distance_mm": "wall + 1/2"}
    assert feature["feature"]["params"]["distance_mm"] == pytest.approx(5.5 * IN + 0.5)
    assert "formula_warnings" not in part.tree()["features"][1]


def test_a_parameter_and_a_sketch_dimension_follow_the_same_rule(
    client: TestClient,
) -> None:
    part, _ = _walled(client, "in")
    rows = part.table()["parameters"]
    body = part.put([*rows, _row("outer", "wall + 1/2")])
    outer = body["parameters"][2]
    assert outer["expression"] == "wall + 1 in/2"
    assert outer["value"] == pytest.approx(6 * IN)
    assert [r["expression"] for r in body["parameters"][:2]] == ["5.5 in", "48 in"]
    sketch: dict[str, Any] = {
        **SKETCH,
        "params": {
            **SKETCH["params"],
            "constraints": [
                {"kind": "distance", "entity": "e1", "value_mm": 40, "name": "d1"},
                {
                    "kind": "distance",
                    "entity": "e2",
                    "value_mm": 41,  # the client's mm reading
                    "expression": "d1 + 1",
                },
            ],
        },
    }
    stored = part.add(sketch)["feature"]["params"]["constraints"]
    assert stored[1]["expression"] == "d1 + 1 in"
    # The stored value is the new text's, not the client's mm reading.
    assert stored[1]["value_mm"] == pytest.approx(40 + IN)
    assert stored[0]["value_mm"] == 40


def _seeded(client: TestClient) -> tuple[Part, str, dict[str, Any]]:
    """An inch part with a stored ``wall + 1/2`` (written while it was mm)."""
    part, sketch_id = _walled(client, "mm")
    feature = part.add(_extrude(sketch_id, "wall + 1/2"))
    part.put([*part.table()["parameters"], _row("outer", "wall + 1/2")])
    part.unit("in")
    return part, feature["id"], feature["feature"]


def test_a_stored_formula_builds_as_before_and_is_flagged(client: TestClient) -> None:
    part, _, _ = _seeded(client)
    extrude = part.tree()["features"][1]
    assert extrude["feature"]["expressions"] == {"/distance_mm": "wall + 1/2"}
    assert extrude["feature"]["params"]["distance_mm"] == pytest.approx(5.5 * IN + 0.5)
    [warning] = extrude["formula_warnings"]
    assert warning["code"] == "expression_bare_mm"
    assert warning["pointer"] == "/distance_mm"
    assert warning["literals"] == ["1/2"]
    assert warning["fixed_expression"] == "wall + 1 in/2"
    assert warning["fixed_value"] == pytest.approx(6 * IN)
    table = part.table()
    [row_warning] = table["formula_warnings"]
    assert row_warning["parameter_id"] == table["parameters"][2]["id"]
    assert row_warning["fixed_expression"] == "wall + 1 in/2"


def test_saving_again_untouched_rewrites_nothing(client: TestClient) -> None:
    part, feature_id, envelope = _seeded(client)
    # Another field edited: the stored formula keeps its text and meaning.
    edited = {**envelope, "params": {**envelope["params"], "operation": "add"}}
    again = part.patch(feature_id, edited)
    assert again["feature"]["expressions"] == {"/distance_mm": "wall + 1/2"}
    assert again["formula_warnings"][0]["code"] == "expression_bare_mm"
    rows = part.table()["parameters"]
    assert part.put(rows)["parameters"][2]["expression"] == "wall + 1/2"


def test_read_as_in_is_an_edit_that_undo_restores(client: TestClient) -> None:
    part, feature_id, envelope = _seeded(client)
    [warning] = part.tree()["features"][1]["formula_warnings"]
    fixed = {**envelope, "expressions": {"/distance_mm": warning["fixed_expression"]}}
    after = part.patch(feature_id, fixed)
    assert after["feature"]["expressions"] == {"/distance_mm": "wall + 1 in/2"}
    assert after["feature"]["params"]["distance_mm"] == pytest.approx(6 * IN)
    assert "formula_warnings" not in after
    part.undo()
    restored = part.tree()["features"][1]
    assert restored["feature"]["expressions"] == {"/distance_mm": "wall + 1/2"}
    assert restored["feature"]["params"]["distance_mm"] == pytest.approx(5.5 * IN + 0.5)
    assert restored["formula_warnings"][0]["fixed_expression"] == "wall + 1 in/2"


def test_the_scan_counts_stored_formulas_and_changes_nothing(
    client: TestClient, tmp_path: Path
) -> None:
    part, _, _ = _seeded(client)
    _walled(client, "in")  # a clean inch part: nothing to report
    before = part.tree()
    report = asyncio.run(run_scan(f"sqlite:///{tmp_path / 'documents.db'}"))
    assert report.parts_scanned == 2
    assert (report.parts_with_warnings, report.feature_formulas) == (1, 1)
    assert report.parameter_formulas == 1
    assert part.tree() == before
