"""Component patterns, documents side (ASM-A3-PATTERN).

- A pattern is ONE entry of the assembly: create, replace and delete it, each
  a version bump and an undo step; the graph and the evaluation request carry
  it; an assembly without patterns reads exactly as before.
- Typed expressions are evaluated on write and their numbers stored.
- Seeds must be instances of the assembly and references parts of it.
- The BOM counts copies, at every level: A3's linear stage reads top level 11
  lines / 45 instances and parts only 16 / 73 once its two hole-driven patterns
  are resolved; unresolved ones count their seeds and are listed.
- The instance bound counts copies, for the assembly and every one above it.
- Deleting a seed or a reference instance cascades; duplicate re-maps ids.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.assemblies import EvaluateAssemblyRequest, nested_occurrence_id
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-0000000000b7"
HEADERS = {PRINCIPAL_HEADER: OWNER}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _post(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def _graph(client: TestClient, assembly: str) -> Any:
    return client.get(f"/api/v1/assemblies/{assembly}", headers=HEADERS).json()


def _version(client: TestClient, assembly: str) -> int:
    return int(_graph(client, assembly)["doc_version"])


def _part(client: TestClient, name: str) -> str:
    return str(_post(client, "/api/v1/parts", {"name": name})["id"])


def _assembly(client: TestClient, name: str) -> str:
    return str(_post(client, "/api/v1/assemblies", {"name": name})["id"])


def _instance(
    client: TestClient, assembly: str, ref: str, name: str, kind: str = "part"
) -> str:
    body = {
        "expected_version": _version(client, assembly),
        "ref_document_id": ref,
        "ref_document_kind": kind,
        "name": name,
    }
    return str(
        _post(client, f"/api/v1/assemblies/{assembly}/instances", body)["instance"][
            "id"
        ]
    )


def _edge(curve: str = "circle") -> dict[str, Any]:
    if curve == "line":
        return {
            "curve": "line",
            "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_b": {"x": 40.0, "y": 0.0, "z": 0.0},
            "midpoint": {"x": 20.0, "y": 0.0, "z": 0.0},
            "length_mm": 40.0,
        }
    return {
        "curve": "circle",
        "end_a": {"x": 5.0, "y": 0.0, "z": 0.0},
        "end_b": {"x": 5.0, "y": 0.0, "z": 0.0},
        "midpoint": {"x": -5.0, "y": 0.0, "z": 0.0},
        "length_mm": 31.41592653589793,
    }


def _linear(seeds: list[str], count: int = 3, **extra: object) -> dict[str, Any]:
    return {
        "type": "linear",
        "seed_instance_ids": seeds,
        "direction": {"kind": "origin_axis", "axis": "x"},
        "count": count,
        "spacing_mm": 25.0,
        **extra,
    }


def _circular(seeds: list[str], axis_on: str, count: int = 4) -> dict[str, Any]:
    return {
        "type": "circular",
        "seed_instance_ids": seeds,
        "axis": {"kind": "edge", "instance_id": axis_on, "signature": _edge()},
        "count": count,
    }


def _holes(
    seeds: list[str], driver: str, also_on: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "hole",
        "seed_instance_ids": seeds,
        "seed_hole": {"instance_id": driver, "signature": _edge()},
        "also_on": also_on or [],
    }


def _create(
    client: TestClient, assembly: str, pattern: dict[str, Any], query: str = ""
) -> Any:
    return client.post(
        f"/api/v1/assemblies/{assembly}/patterns{query}",
        json={"expected_version": _version(client, assembly), "pattern": pattern},
        headers=HEADERS,
    )


def _pattern(
    client: TestClient, assembly: str, pattern: dict[str, Any], query: str = ""
) -> str:
    response = _create(client, assembly, pattern, query)
    assert response.status_code == 201, response.text
    return str(response.json()["pattern"]["id"])


def _bom(
    client: TestClient, assembly: str, counts: dict[str, int] | None = None
) -> Any:
    params = {"pattern_count": [f"{k}:{v}" for k, v in (counts or {}).items()]}
    response = client.get(
        f"/api/v1/assemblies/{assembly}/bom", params=params, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_pattern_is_one_entry_with_its_numbers_resolved(client: TestClient) -> None:
    plate = _part(client, "Plate")
    stage = _assembly(client, "Stage")
    base = _instance(client, stage, plate, "Plate <1>")
    assert "patterns" not in _graph(client, stage)  # reads exactly as before
    before = _version(client, stage)
    pattern_id = _pattern(
        client,
        stage,
        _linear([base], count=2, count_expr="12 / 2 + 1", spacing_expr="1 in"),
    )
    graph = _graph(client, stage)
    assert graph["doc_version"] == before + 1
    (stored,) = graph["patterns"]
    assert stored["id"] == pattern_id
    assert stored["pattern"]["count"] == 7
    assert stored["pattern"]["spacing_mm"] == pytest.approx(25.4)
    assert stored["pattern"]["count_expr"] == "12 / 2 + 1"

    request = EvaluateAssemblyRequest.model_validate(
        client.get(
            f"/api/v1/assemblies/{stage}/evaluation-request", headers=HEADERS
        ).json()
    )
    assert [str(p.pattern_id) for p in request.patterns] == [pattern_id]

    # Replace it (same id), then undo and redo the replace.
    response = client.patch(
        f"/api/v1/assemblies/{stage}/patterns/{pattern_id}",
        json={
            "expected_version": _version(client, stage),
            "pattern": _circular([base], base, count=6),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert _graph(client, stage)["patterns"][0]["pattern"]["type"] == "circular"
    undo = client.post(
        f"/api/v1/assemblies/{stage}/undo",
        json={"expected_version": _version(client, stage)},
        headers=HEADERS,
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["patterns"][0]["pattern"]["type"] == "linear"
    redo = client.post(
        f"/api/v1/assemblies/{stage}/redo",
        json={"expected_version": _version(client, stage)},
        headers=HEADERS,
    )
    assert redo.json()["patterns"][0]["pattern"]["count"] == 6

    deleted = client.delete(
        f"/api/v1/assemblies/{stage}/patterns/{pattern_id}",
        params={"expected_version": _version(client, stage)},
        headers=HEADERS,
    )
    assert deleted.status_code == 200, deleted.text
    assert "patterns" not in deleted.json()
    assert [i["id"] for i in deleted.json()["instances"]] == [base]


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"count_expr": "2 mm"}, "expression_units"),
        ({"count_expr": "2.5"}, "expression_domain"),
        ({"spacing_expr": "-3 mm"}, "pattern_value_invalid"),
        ({"count_expr": "width"}, "expression_unknown_name"),
    ],
)
def test_a_bad_expression_is_refused_on_its_field(
    client: TestClient, extra: dict[str, str], code: str
) -> None:
    plate = _part(client, "Plate")
    stage = _assembly(client, "Stage")
    base = _instance(client, stage, plate, "Plate <1>")
    response = _create(client, stage, {**_linear([base]), **extra})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code


def test_seeds_and_references_must_belong(client: TestClient) -> None:
    plate = _part(client, "Plate")
    screw = _part(client, "Screw")
    stage = _assembly(client, "Stage")
    wheel = _assembly(client, "Wheel")
    _instance(client, wheel, plate, "Plate <1>")
    base = _instance(client, stage, plate, "Plate <1>")
    bolt = _instance(client, stage, screw, "Screw <1>")
    sub = _instance(client, stage, wheel, "Wheel <1>", kind="assembly")
    stranger = str(uuid.uuid4())

    def code(pattern: dict[str, Any]) -> str:
        response = _create(client, stage, pattern)
        assert response.status_code == 422, response.text
        return str(response.json()["error"]["code"])

    assert code(_linear([stranger])) == "pattern_seed_unknown"
    assert code(_circular([bolt], stranger)) == "pattern_reference_unknown"
    assert code(_circular([bolt], sub)) == "pattern_needs_part"
    assert code(_holes([base], bolt, also_on=[sub])) == "pattern_needs_part"
    other = _instance(client, stage, plate, "Plate <2>")
    assert code(_holes([other], bolt, also_on=[base])) == "pattern_driver_mismatch"
    # A seed may be a sub-assembly; a reference may be a part inside one.
    inner = _graph(client, wheel)["instances"][0]["id"]
    nested = str(nested_occurrence_id(uuid.UUID(sub), uuid.UUID(inner)))
    _pattern(client, stage, _circular([sub, bolt], nested))


def _a3(client: TestClient) -> dict[str, str]:
    """A3's linear stage, structurally: 16 parts, the carriage a sub-assembly,
    the rail and block screws hole-driven patterns, the motor and T8-nut
    screws and the M5s circular / linear patterns."""
    names = [
        "Base plate", "Rail", "M3x8", "Motor plate", "Idler plate", "M5x16",
        "NEMA 17", "M3x10", "Coupler", "T8 lead screw", "Carriage plate",
        "Carriage block", "M3x6", "Nut bracket", "M4x10", "T8 nut",
    ]  # fmt: skip
    part = {name: _part(client, name) for name in names}
    carriage = _assembly(client, "Carriage")
    _instance(client, carriage, part["Carriage plate"], "Carriage plate <1>")
    blocks = [
        _instance(client, carriage, part["Carriage block"], f"Carriage block <{n}>")
        for n in range(1, 5)
    ]
    m3x6 = _instance(client, carriage, part["M3x6"], "M3x6 <1>")
    block_screws = _pattern(
        client, carriage, _holes([m3x6], blocks[0], blocks[1:]), "?driven_count=16"
    )
    _instance(client, carriage, part["Nut bracket"], "Nut bracket <1>")
    m4 = _instance(client, carriage, part["M4x10"], "M4x10 <1>")
    _pattern(client, carriage, _linear([m4], count=2))
    nut = _instance(client, carriage, part["T8 nut"], "T8 nut <1>")
    nut_screw = _instance(client, carriage, part["M3x10"], "M3x10 <1>")
    _pattern(client, carriage, _circular([nut_screw], nut))

    stage = _assembly(client, "Linear stage")
    base = _instance(client, stage, part["Base plate"], "Base plate <1>")
    rails = [_instance(client, stage, part["Rail"], f"Rail <{n}>") for n in (1, 2)]
    screw = _instance(client, stage, part["M3x8"], "M3x8 <1>")
    rail_screws = _pattern(
        client, stage, _holes([screw], rails[0], rails[1:]), "?driven_count=28"
    )
    _instance(client, stage, part["Motor plate"], "Motor plate <1>")
    _instance(client, stage, part["Idler plate"], "Idler plate <1>")
    m5 = _instance(client, stage, part["M5x16"], "M5x16 <1>")
    _pattern(client, stage, _linear([m5], count=4))
    motor = _instance(client, stage, part["NEMA 17"], "NEMA 17 <1>")
    m3x10 = _instance(client, stage, part["M3x10"], "M3x10 <1>")
    _pattern(client, stage, _circular([m3x10], motor))
    _instance(client, stage, part["Coupler"], "Coupler <1>")
    _instance(client, stage, part["T8 lead screw"], "T8 lead screw <1>")
    _instance(client, stage, carriage, "Carriage <1>", kind="assembly")
    del base
    return {
        "stage": stage,
        "carriage": carriage,
        "rail_screws": rail_screws,
        "block_screws": block_screws,
    }


def test_a3_bom_counts_every_copy(client: TestClient) -> None:
    a3 = _a3(client)
    bom = _bom(client, a3["stage"], {a3["rail_screws"]: 28, a3["block_screws"]: 16})
    assert (len(bom["lines"]), bom["total_instances"]) == (11, 45)
    assert (len(bom["parts_only"]), bom["total_parts"]) == (16, 73)
    assert "unresolved_patterns" not in bom
    quantity = {line["name"]: line["quantity"] for line in bom["parts_only"]}
    assert quantity["M3x8"] == 28
    assert quantity["M3x6"] == 16
    assert quantity["M3x10"] == 8  # four on the motor, four on the T8 nut
    # Indented: the carriage's block screws are 16 inside it.
    indented = {(row["level"], row["name"]): row for row in bom["indented"]}
    assert indented[(1, "M3x6")]["quantity"] == 16

    # Unresolved (geometry could not say): seeds only, and named.
    bare = _bom(client, a3["stage"])
    assert bare["total_instances"] == 45 - 27
    assert sorted(bare["unresolved_patterns"]) == sorted(
        [a3["rail_screws"], a3["block_screws"]]
    )


def test_the_instance_bound_counts_copies_at_every_ancestor(client: TestClient) -> None:
    plate = _part(client, "Plate")
    wheel = _assembly(client, "Wheel")
    spoke = _instance(client, wheel, plate, "Spoke <1>")
    bike = _assembly(client, "Bike")
    for n in (1, 2):
        _instance(client, bike, wheel, f"Wheel <{n}>", kind="assembly")
    # Alone the wheel would hold 300 spokes; the bike holds two wheels.
    response = _create(client, wheel, _linear([spoke], count=300))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "assembly_too_large"
    assert "patterns" not in _graph(client, wheel)  # rolled back
    _pattern(client, wheel, _linear([spoke], count=32))
    # A hole-driven pattern counts by the count the gateway resolved.
    hub = _instance(client, wheel, plate, "Hub <1>")
    response = _create(client, wheel, _holes([spoke], hub), "?driven_count=250")
    assert response.json()["error"]["code"] == "assembly_too_large"


def test_deleting_a_seed_or_a_reference_cascades(client: TestClient) -> None:
    plate = _part(client, "Plate")
    stage = _assembly(client, "Stage")
    a = _instance(client, stage, plate, "Plate <1>")
    b = _instance(client, stage, plate, "Plate <2>")
    hub = _instance(client, stage, plate, "Plate <3>")
    two_seeds = _pattern(client, stage, _linear([a, b]))
    ring = _pattern(client, stage, _circular([a], hub))

    def delete(instance: str) -> Any:
        response = client.delete(
            f"/api/v1/assemblies/{stage}/instances/{instance}",
            params={"expected_version": _version(client, stage)},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        return response.json()

    graph = delete(hub)  # the ring's axis is gone: the ring goes
    assert [p["id"] for p in graph["patterns"]] == [two_seeds]
    graph = delete(b)  # one seed left
    assert graph["patterns"][0]["pattern"]["seed_instance_ids"] == [a]
    graph = delete(a)  # no seeds left
    assert "patterns" not in graph
    del ring


def test_duplicate_remaps_the_pattern(client: TestClient) -> None:
    plate = _part(client, "Plate")
    stage = _assembly(client, "Stage")
    a = _instance(client, stage, plate, "Plate <1>")
    hub = _instance(client, stage, plate, "Plate <2>")
    _pattern(client, stage, _circular([a], hub))
    copy = _post(client, f"/api/v1/assemblies/{stage}/duplicate", {})["id"]
    graph = _graph(client, copy)
    new_a, new_hub = (i["id"] for i in graph["instances"])
    (pattern,) = graph["patterns"]
    assert pattern["pattern"]["seed_instance_ids"] == [new_a]
    assert pattern["pattern"]["axis"]["instance_id"] == new_hub
