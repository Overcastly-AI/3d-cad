"""Feature formulas over the part's parameters (PART-PARAMETERS step 4).

:mod:`documents.feature_expressions`, RESEARCH §20. Pinned here:

* a write stores the resolved number at each pointer; a syntax error, an
  unknown name, a unit clash, a non-integer count, a value its field refuses
  and a pointer that misses a number are 422s that write nothing;
* a sketch dimension reads its sketch's dimensions, then the parameters, and
  may not take a parameter's name;
* the evaluation request carries numbers only (``expressions`` gone) and
  follows a parameter edit; a value that no longer fits its field, or a
  parameter that no longer exists, is a 200 with that feature's
  ``input_error`` and its last good numbers;
* a parameter PUT re-resolves, renames references token by token, refuses
  (409) deleting a parameter in use, and is one undo step; the same table again
  changes nothing;
* undo, duplicate, named versions and ``.loft`` export/import keep the
  formulas; a file or a version from before them still works.
"""

import asyncio
import copy
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.loft_file import LoftTree, LoftVersionList, pack_part, read_loft
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-0000000001a4"


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


HEADERS = {PRINCIPAL_HEADER: OWNER}


def _row(name: str, expression: str, unit: str = "length", **extra: Any) -> Any:
    return {
        "id": extra.pop("id", str(uuid.uuid4())),
        "name": name,
        "expression": expression,
        "unit": unit,
        **extra,
    }


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _sketch(constraints: list[Any] | None = None) -> dict[str, Any]:
    """A 40 x 25 rectangle on XY."""
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                _line("e1", (0, 0), (40, 0)),
                _line("e2", (40, 0), (40, 25)),
                _line("e3", (40, 25), (0, 25)),
                _line("e4", (0, 25), (0, 0)),
            ],
            "constraints": constraints or [],
        },
    }


def _extrude(sketch_id: str, expressions: dict[str, str] | None = None) -> Any:
    feature: dict[str, Any] = {
        "type": "extrude",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": 10.0,
            "operation": "add",
            "direction": "normal",
        },
    }
    if expressions is not None:
        feature["expressions"] = expressions
    return feature


class Part:
    """A part under test, tracking its tree_version."""

    def __init__(self, client: TestClient, part_id: str | None = None) -> None:
        self.client = client
        if part_id is None:
            response = client.post(
                "/api/v1/parts", json={"name": f"P {uuid.uuid4()}"}, headers=HEADERS
            )
            assert response.status_code == 201, response.text
            part_id = str(response.json()["id"])
        self.id: str = part_id
        self.version = self.tree()["tree_version"]

    def tree(self) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def put(self, rows: list[Any]) -> Any:
        """PUT the table; a row read back from GET is sent without its value."""
        inputs = [{k: v for k, v in row.items() if k != "value"} for row in rows]
        response = self.client.put(
            f"/api/v1/parts/{self.id}/parameters",
            json={"expected_tree_version": self.version, "parameters": inputs},
            headers=HEADERS,
        )
        if response.status_code == 200:
            self.version = response.json()["tree_version"]
        return response

    def rows(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/parameters", headers=HEADERS
        )
        rows: list[dict[str, Any]] = response.json()["parameters"]
        return rows

    def add(self, feature: Any, name: str = "F") -> Any:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": name,
                "feature": feature,
                "expected_tree_version": self.version,
            },
            headers=HEADERS,
        )
        if response.status_code == 201:
            self.version = response.json()["tree_version"]
        return response

    def patch(self, feature_id: str, feature: Any) -> Any:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            json={"feature": feature, "expected_tree_version": self.version},
            headers=HEADERS,
        )
        if response.status_code == 200:
            self.version = response.json()["tree_version"]
        return response

    def step(self, direction: str) -> None:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/{direction}",
            json={"expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = response.json()["tree_version"]

    def request(self) -> dict[str, Any]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/evaluation-request", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def feature(self, index: int) -> dict[str, Any]:
        feature: dict[str, Any] = self.tree()["features"][index]["feature"]
        return feature


def _box(client: TestClient, depth: str = "D") -> tuple[Part, str, str]:
    """A part with D = 10 and an extrude whose distance is ``= depth``."""
    part = Part(client)
    assert part.put([_row("D", "10")]).status_code == 200
    sketch = part.add(_sketch(), "Sketch1")
    assert sketch.status_code == 201, sketch.text
    sketch_id = sketch.json()["feature"]["id"]
    extrude = part.add(_extrude(sketch_id, {"/distance_mm": depth}), "Extrude1")
    assert extrude.status_code == 201, extrude.text
    return part, sketch_id, extrude.json()["feature"]["id"]


# --- write ------------------------------------------------------------------------


def test_a_write_stores_the_resolved_number_and_keeps_the_formula(
    client: TestClient,
) -> None:
    part, _, _ = _box(client, "D * 2 + 0.5 in")
    extrude = part.feature(1)
    assert extrude["params"]["distance_mm"] == pytest.approx(32.7)
    assert extrude["expressions"] == {"/distance_mm": "D * 2 + 0.5 in"}
    # A feature without formulas reads exactly as before: no key at all.
    assert "expressions" not in part.feature(0)


@pytest.mark.parametrize(
    ("expressions", "code"),
    [
        ({"/distance_mm": "D +"}, "expression_syntax"),
        ({"/distance_mm": "Depth"}, "expression_unknown_name"),
        ({"/distance_mm": "30 deg"}, "expression_units"),
        ({"/distance_mm": "-D"}, "parameter_value_invalid"),
    ],
)
def test_a_formula_that_does_not_resolve_is_a_422_and_writes_nothing(
    client: TestClient, expressions: dict[str, str], code: str
) -> None:
    part, sketch_id, _ = _box(client)
    before = part.tree()
    response = part.add(_extrude(sketch_id, expressions))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert part.tree() == before


@pytest.mark.parametrize(
    "pointer", ["/operation", "/nope", "/profile/feature_id", "distance_mm", ""]
)
def test_a_pointer_must_hit_a_number(client: TestClient, pointer: str) -> None:
    part, sketch_id, _ = _box(client)
    response = part.add(_extrude(sketch_id, {pointer: "D"}))
    assert response.status_code == 422, response.text


def test_an_int_field_takes_a_whole_plain_number(client: TestClient) -> None:
    part, _, _ = _box(client)
    [d] = part.rows()
    assert part.put([d, _row("N", "6 / 2", "unitless")]).status_code == 200
    pattern: dict[str, Any] = {
        "type": "pattern",
        "version": 1,
        "params": {
            "pattern": {
                "kind": "linear",
                "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                "count": 2,
                "spacing_mm": 50.0,
            }
        },
    }
    for text, code in (("N / 4", "expression_domain"), ("D", "expression_units")):
        bad = copy.deepcopy(pattern)
        bad["expressions"] = {"/pattern/count": text}
        response = part.add(bad)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == code
    pattern["expressions"] = {"/pattern/count": "N", "/pattern/spacing_mm": "D * 5"}
    response = part.add(pattern)
    assert response.status_code == 201, response.text
    params = response.json()["feature"]["feature"]["params"]["pattern"]
    assert params["count"] == 3
    assert params["spacing_mm"] == 50.0


def test_a_sketch_dimension_reads_its_sketch_then_the_parameters(
    client: TestClient,
) -> None:
    part = Part(client)
    assert part.put([_row("W", "60")]).status_code == 200
    dims = [
        {"kind": "distance", "entity": "e1", "value_mm": 40.0, "name": "len",
         "expression": "W"},
        {"kind": "distance", "entity": "e2", "value_mm": 25.0, "expression": "len / 4"},
    ]  # fmt: skip
    response = part.add(_sketch(dims))
    assert response.status_code == 201, response.text
    feature = response.json()["feature"]["feature"]
    stored = feature["params"]["constraints"]
    assert [c["value_mm"] for c in stored] == [60.0, 15.0]
    # Stored form: a formula that reads a parameter moves to the value's
    # pointer, so params hold a number any client can hand geometry; a formula
    # over the sketch's own dimensions stays where it was written.
    assert [c["expression"] for c in stored] == [None, "len / 4"]
    assert feature["expressions"] == {"/constraints/0/value_mm": "W"}
    # Geometry gets the number where the formula read a parameter, and the
    # formula over the sketch's own dimensions as before.
    sent = part.request()["features"][0]["feature"]["params"]["constraints"]
    assert [(c["value_mm"], c["expression"]) for c in sent] == [
        (60.0, None),
        (15.0, "len / 4"),
    ]
    # A dimension may not take a parameter's name, and a parameter may not
    # take a dimension's.
    clash = [{"kind": "distance", "entity": "e1", "value_mm": 40.0, "name": "W"}]
    response = part.add(_sketch(clash))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "expression_name_invalid"
    response = part.put([_row("W", "60"), _row("len", "1")])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "expression_name_invalid"


# --- evaluation request -----------------------------------------------------------


def test_the_evaluation_request_carries_numbers_only_and_follows_a_parameter(
    client: TestClient,
) -> None:
    part, _, _ = _box(client)
    [row] = part.rows()
    first = part.request()["features"][1]
    assert "expressions" not in first["feature"]
    assert first["feature"]["params"]["distance_mm"] == 10.0
    assert "input_error" not in first

    assert part.put([{**row, "expression": "25"}]).status_code == 200
    second = part.request()["features"][1]
    assert second["feature"]["params"]["distance_mm"] == 25.0
    # The PUT stored the re-resolved number too, as one tree edit.
    assert part.feature(1)["params"]["distance_mm"] == 25.0


def test_an_out_of_range_value_is_a_sick_feature_not_a_500(client: TestClient) -> None:
    part, _, _ = _box(client)
    [row] = part.rows()
    response = part.put([{**row, "expression": "-5"}])
    assert response.status_code == 200, response.text
    entry = part.request()["features"][1]
    assert entry["input_error"]["code"] == "parameter_value_invalid"
    # Its last good numbers ride along; the stored row kept them too.
    assert entry["feature"]["params"]["distance_mm"] == 10.0
    assert "expressions" not in entry["feature"]
    assert part.feature(1)["params"]["distance_mm"] == 10.0
    # Back in range: healthy again.
    assert part.put([{**row, "expression": "12"}]).status_code == 200
    entry = part.request()["features"][1]
    assert "input_error" not in entry
    assert entry["feature"]["params"]["distance_mm"] == 12.0


# --- parameter PUT ----------------------------------------------------------------


def test_a_rename_rewrites_every_reference_token_by_token(client: TestClient) -> None:
    part = Part(client)
    d = _row("D", "10")
    dd = _row("DD", "3")
    assert part.put([d, dd]).status_code == 200
    dims = [{"kind": "distance", "entity": "e1", "value_mm": 40.0,
             "expression": "D * 4"}]  # fmt: skip
    sketch_id = part.add(_sketch(dims)).json()["feature"]["id"]
    assert part.add(_extrude(sketch_id, {"/distance_mm": "D+DD"})).status_code == 201

    response = part.put([{**d, "name": "Depth"}, dd])
    assert response.status_code == 200, response.text
    assert part.feature(1)["expressions"] == {"/distance_mm": "Depth+DD"}
    assert part.feature(0)["expressions"] == {"/constraints/0/value_mm": "Depth * 4"}
    assert "input_error" not in part.request()["features"][1]
    # A swap is a swap.
    response = part.put([{**d, "name": "DD"}, {**dd, "name": "Depth"}])
    assert response.status_code == 200, response.text
    assert part.feature(1)["expressions"] == {"/distance_mm": "DD+Depth"}


#: 57 characters: renaming W to it grows "W+W+W+W+W" to 289, past the 256 cap.
LONG = "Overall_width_of_the_mounting_bracket_including_flanges_x"


@pytest.mark.parametrize("where", ["extrude", "sketch dimension"])
def test_a_rename_past_the_formula_cap_is_a_422_that_stores_nothing(
    client: TestClient, where: str
) -> None:
    """Review blocker: the rename used to store a formula no read could load
    (GET dropped it, /loft-tree and /versions answered 500, a sketch's PUT
    500'd). It must be refused, naming the feature and the pointer."""
    part = Part(client)
    w = _row("W", "10")
    assert part.put([w]).status_code == 200
    if where == "extrude":
        sketch_id = part.add(_sketch(), "S").json()["feature"]["id"]
        made = part.add(_extrude(sketch_id, {"/distance_mm": "W+W+W+W+W"}), "E")
        pointer, index = "/distance_mm", 1
    else:
        dims = [{"kind": "distance", "entity": "e1", "value_mm": 40.0,
                 "expression": "W+W+W+W+W"}]  # fmt: skip
        made = part.add(_sketch(dims), "S")
        pointer, index = "/constraints/0/value_mm", 0
    assert made.status_code == 201, made.text
    before = (part.tree(), part.rows())

    response = part.put([{**w, "name": LONG}])
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "expression_too_complex"
    assert error["details"]["pointer"] == pointer
    assert error["details"]["feature_id"] == made.json()["feature"]["id"]
    assert (part.tree(), part.rows()) == before
    assert part.feature(index)["expressions"] == {pointer: "W+W+W+W+W"}
    for path in ("loft-tree", "evaluation-request"):
        got = client.get(f"/api/v1/parts/{part.id}/{path}", headers=HEADERS)
        assert got.status_code == 200, got.text
    saved = client.post(
        f"/api/v1/parts/{part.id}/versions", json={"name": "v"}, headers=HEADERS
    )
    assert saved.status_code == 201, saved.text
    # A name that fits is fine.
    assert part.put([{**w, "name": "Width"}]).status_code == 200
    renamed = {pointer: "Width+Width+Width+Width+Width"}
    assert part.feature(index)["expressions"] == renamed


def test_a_dimension_with_a_pointer_and_its_own_formula_is_a_422(
    client: TestClient,
) -> None:
    """One of the two would be silently ignored; refuse it at write."""
    part = Part(client)
    assert part.put([_row("W", "60")]).status_code == 200
    sketch = _sketch(
        [{"kind": "distance", "entity": "e1", "value_mm": 40.0, "expression": "30"}]
    )
    sketch["expressions"] = {"/constraints/0/value_mm": "W"}
    response = part.add(sketch)
    assert response.status_code == 422, response.text
    assert "own expression" in response.text


def test_deleting_a_parameter_in_use_is_a_409_naming_the_features(
    client: TestClient,
) -> None:
    part, _, extrude_id = _box(client)
    before = part.version
    response = part.put([])
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "parameter_in_use"
    assert error["details"]["parameters"] == ["D"]
    assert [f["id"] for f in error["details"]["features"]] == [extrude_id]
    assert part.version == before and [r["name"] for r in part.rows()] == ["D"]
    # An unused parameter goes.
    [d] = part.rows()
    assert part.put([d, _row("spare", "1")]).status_code == 200
    assert part.put([d]).status_code == 200


def test_the_same_table_again_is_a_no_op(client: TestClient) -> None:
    part, _, _ = _box(client)
    rows = part.rows()
    tree = part.tree()
    response = part.put(rows)
    assert response.status_code == 200
    assert response.json()["tree_version"] == tree["tree_version"]
    after = part.tree()
    assert (after["can_undo"], after["tree_version"]) == (True, tree["tree_version"])
    # Undo steps back over the feature write, not over a phantom table edit.
    part.step("undo")
    assert len(part.tree()["features"]) == 1


def test_feature_and_parameter_undo_interleave(client: TestClient) -> None:
    """Every edit is one step, whichever kind, and undo/redo walk them in order."""
    part, _, extrude_id = _box(client)  # PUT D=10, sketch, extrude = D
    [d] = part.rows()
    assert part.put([{**d, "expression": "20"}]).status_code == 200  # step 4
    extrude = part.feature(1)
    extrude["expressions"] = {"/distance_mm": "D / 2"}
    assert part.patch(extrude_id, extrude).status_code == 200  # step 5
    assert part.put([{**d, "expression": "30"}]).status_code == 200  # step 6

    def state() -> tuple[float, float, dict[str, str] | None]:
        feature = part.feature(1)
        return (
            part.rows()[0]["value"],
            feature["params"]["distance_mm"],
            feature.get("expressions"),
        )

    trail = [
        (30.0, 15.0, {"/distance_mm": "D / 2"}),
        (20.0, 10.0, {"/distance_mm": "D / 2"}),
        (20.0, 20.0, {"/distance_mm": "D"}),
        (10.0, 10.0, {"/distance_mm": "D"}),
    ]
    assert state() == trail[0]
    for expected in trail[1:]:
        part.step("undo")
        assert state() == expected
    for expected in reversed(trail[:-1]):
        part.step("redo")
        assert state() == expected


# --- carriers ---------------------------------------------------------------------


def test_duplicate_keeps_the_formulas(client: TestClient) -> None:
    part, _, _ = _box(client)
    response = client.post(f"/api/v1/parts/{part.id}/duplicate", headers=HEADERS)
    assert response.status_code == 201, response.text
    twin = Part(client, response.json()["id"])
    assert twin.feature(1)["expressions"] == {"/distance_mm": "D"}
    [d] = twin.rows()
    assert twin.put([{**d, "expression": "7"}]).status_code == 200
    assert twin.request()["features"][1]["feature"]["params"]["distance_mm"] == 7.0


def _save(part: Part, name: str) -> None:
    response = part.client.post(
        f"/api/v1/parts/{part.id}/versions", json={"name": name}, headers=HEADERS
    )
    assert response.status_code == 201, response.text


def _restore(part: Part, seq: int) -> None:
    response = part.client.post(
        f"/api/v1/parts/{part.id}/versions/{seq}/restore",
        json={"expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    part.version = response.json()["tree_version"]


def test_a_named_version_keeps_the_formulas(client: TestClient) -> None:
    part, _, extrude_id = _box(client)
    _save(part, "Rev A")
    extrude = part.feature(1)
    extrude.pop("expressions")
    assert part.patch(extrude_id, extrude).status_code == 200
    assert "expressions" not in part.feature(1)
    _restore(part, 1)
    assert part.feature(1)["expressions"] == {"/distance_mm": "D"}


def test_a_version_from_before_parameters_restores_to_working_numbers(
    client: TestClient,
) -> None:
    part = Part(client)
    sketch_id = part.add(_sketch()).json()["feature"]["id"]
    extrude_id = part.add(_extrude(sketch_id)).json()["feature"]["id"]
    _save(part, "Before parameters")
    assert part.put([_row("D", "33")]).status_code == 200
    extrude = part.feature(1)
    extrude["expressions"] = {"/distance_mm": "D"}
    assert part.patch(extrude_id, extrude).status_code == 200
    _restore(part, 1)
    assert part.rows() == []
    entry = part.request()["features"][1]
    assert "input_error" not in entry
    assert entry["feature"]["params"]["distance_mm"] == 10.0


def _export(part: Part) -> bytes:
    tree = part.client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=HEADERS)
    listed = part.client.get(f"/api/v1/parts/{part.id}/loft-versions", headers=HEADERS)
    assert tree.status_code == 200 and listed.status_code == 200
    return pack_part(
        document_id=uuid.UUID(part.id),
        tree=LoftTree.model_validate(tree.json()),
        loft_version="test",
        versions=LoftVersionList.model_validate(listed.json()).versions,
    )


def _import(client: TestClient, tree: Any, versions: list[Any] | None = None) -> Part:
    response = client.post(
        "/api/v1/parts/import-loft",
        json={
            "document_id": str(uuid.uuid4()),
            "tree": tree,
            "versions": versions or [],
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return Part(client, response.json()["id"])


def test_a_loft_round_trip_keeps_the_formulas(client: TestClient) -> None:
    part, _, _ = _box(client)
    _save(part, "Rev A")
    archive = read_loft(_export(part))
    assert archive.tree.features[1].expressions == {"/distance_mm": "D"}
    assert archive.versions[0].tree.features[1].expressions == {"/distance_mm": "D"}
    copy_ = _import(
        client,
        archive.tree.model_dump(mode="json"),
        [v.model_dump(mode="json") for v in archive.versions],
    )
    assert copy_.feature(1)["expressions"] == {"/distance_mm": "D"}
    _restore(copy_, 1)
    assert copy_.feature(1)["expressions"] == {"/distance_mm": "D"}


def test_an_old_loft_without_formulas_imports_and_a_missing_parameter_is_sick(
    client: TestClient,
) -> None:
    part, _, _ = _box(client)
    tree = part.client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=HEADERS).json()
    old = copy.deepcopy(tree)
    for feature in old["features"]:
        feature.pop("expressions", None)
    old.pop("parameters")
    imported = _import(client, old)
    assert "expressions" not in imported.feature(1)
    assert imported.request()["features"][1]["feature"]["params"]["distance_mm"] == 10

    # A file whose formulas name a parameter its table lacks still opens; the
    # feature is sick with its last good numbers, the request a 200.
    orphan = copy.deepcopy(tree)
    orphan.pop("parameters")
    imported = _import(client, orphan)
    entry = imported.request()["features"][1]
    assert entry["input_error"]["code"] == "parameter_unresolved"
    assert entry["feature"]["params"]["distance_mm"] == 10.0


# --- Postgres ---------------------------------------------------------------------


def test_formulas_on_postgres_with_the_migrated_schema(pg_url: str) -> None:
    """Write, PUT re-resolve, rename, undo and a version on the real JSONB."""
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        part, _, _ = _box(client, "D * 2")
        [d] = part.rows()
        _save(part, "Rev A")
        assert part.put([{**d, "name": "Depth", "expression": "7"}]).status_code == 200
        assert part.feature(1)["expressions"] == {"/distance_mm": "Depth * 2"}
        assert part.request()["features"][1]["feature"]["params"]["distance_mm"] == 14
        part.step("undo")
        assert part.feature(1)["expressions"] == {"/distance_mm": "D * 2"}
        assert part.feature(1)["params"]["distance_mm"] == 20.0
        _restore(part, 1)
        assert part.feature(1)["expressions"] == {"/distance_mm": "D * 2"}
        assert part.put([]).status_code == 409
