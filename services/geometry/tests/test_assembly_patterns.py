"""Component patterns (ASM-A3-PATTERN): copies placed after the solve.

The analytic exit gate is the ``assembly-component-patterns`` golden (one
pattern of each kind on real plates). This suite covers the rest of the
contract on the same model:

- a hole-driven pattern follows its driving part: a plate with a hole more or
  less places one copy more or less;
- a sub-assembly seed is copied whole, its parts keyed under the copy id, and a
  pattern inside a sub-assembly is placed when that sub-assembly is instanced;
- every failure is a typed per-pattern state and the rest still evaluates;
- the instance bound counts copies (at parse for linear / circular patterns,
  on expansion for hole-driven ones);
- interference, STEP export and the counts route see every copy.
"""

from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from geometry.assembly import count_patterns, evaluate_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.interference import check_interference
from geometry.assembly.transform import Pose
from geometry.main import app
from loft_wire.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
    nested_occurrence_id,
)
from loft_wire.component_patterns import pattern_copy_id
from pydantic import ValidationError

_GOLDEN = Path(__file__).resolve().parent.parent / "goldens-assembly"
_MODEL = EvaluateAssemblyRequest.model_validate_json(
    (_GOLDEN / "assembly-component-patterns" / "model.json").read_text("utf-8")
)

A = uuid.UUID(int=0xC1)
A2 = uuid.UUID(int=0xC5)
P = uuid.UUID(int=0xC2)
L = uuid.UUID(int=0xC3)
C = uuid.UUID(int=0xC4)
HOLES = uuid.UUID(int=0xD1)
ROW = uuid.UUID(int=0xD2)
RING = uuid.UUID(int=0xD3)
TOL = 1e-9


def _model() -> dict[str, Any]:
    return _MODEL.model_dump(mode="json")


def _only(model: dict[str, Any], pattern_id: uuid.UUID) -> dict[str, Any]:
    model["patterns"] = [
        p for p in model["patterns"] if p["pattern_id"] == str(pattern_id)
    ]
    return model


def _counts(request: EvaluateAssemblyRequest) -> dict[uuid.UUID, int | None]:
    return {
        state.pattern_id: state.count
        for state in evaluate_assembly(request).pattern_states
    }


def _three_hole_plate(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The plate made 60 long with a third r5 hole at (44, 12.5)."""
    out = copy.deepcopy(features)
    entities = out[0]["feature"]["params"]["entities"]
    for entity in entities:
        for key in ("start", "end"):
            if entity.get(key, {}).get("x") == 40.0:
                entity[key]["x"] = 60.0
    entities.append(
        {
            "id": "h3",
            "construction": False,
            "kind": "circle",
            "center": {"x": 44.0, "y": 12.5},
            "radius": 5.0,
        }
    )
    return out


def test_a_hole_pattern_follows_the_driving_part() -> None:
    """Edit the plate (A and A2 share it) to three holes: the pattern places
    three per plate, and the new copy sits over the new hole."""
    model = _only(_model(), HOLES)
    assert _counts(EvaluateAssemblyRequest.model_validate(model)) == {HOLES: 4}
    for inst in model["instances"]:
        inst["features"] = _three_hole_plate(inst["features"])
        inst["part_key"] = "part-plate-3holes@1"
    request = EvaluateAssemblyRequest.model_validate(model)
    assert _counts(request) == {HOLES: 6}
    poses = {
        row.instance_id: Pose.from_placement(row.placement)
        for row in evaluate_assembly(request).instances
    }
    # Copy 2 on A is its hole 3: (44 - 12, 0, 0) from the seed at (0, 0, 10).
    assert poses[pattern_copy_id(HOLES, P, 2)].t == pytest.approx(
        [32.0, 0.0, 10.0], abs=TOL
    )


def test_copies_are_tagged_and_follow_the_seed_joint() -> None:
    """Re-seat the seed by its joint (P's seed pose moves, its joint does not):
    the copies stay where the joint puts the seed; each row names its pattern."""
    model = _only(_model(), HOLES)
    model["instances"][2]["placement"]["position"] = {"x": 300.0, "y": 0, "z": 0}
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    rows = {row.instance_id: row for row in result.instances}
    first = rows[pattern_copy_id(HOLES, P, 1)]
    assert first.pattern is not None
    assert (first.pattern.pattern_id, first.pattern.seed_instance_id) == (HOLES, P)
    assert first.pattern.index == 1
    assert Pose.from_placement(first.placement).t == pytest.approx(
        [16.0, 0.0, 10.0], abs=TOL
    )
    assert "pattern" not in rows[P].model_dump()


def _wheel_with_ring() -> dict[str, Any]:
    """The golden with only the ring pattern: a 'wheel' of four plates."""
    return _only(_model(), RING)


def test_a_sub_assembly_seed_is_copied_whole() -> None:
    """A linear pattern of a sub-assembly (the ring wheel) copies all four of
    its plates, each keyed under the copy's id."""
    wheel = EvaluateAssemblyRequest.model_validate(_wheel_with_ring())
    wheel_inst = uuid.UUID(int=0x77)
    parent: dict[str, Any] = {
        "assembly_id": str(uuid.UUID(int=0xFA)),
        "version": 1,
        "instances": [
            {
                "instance_id": str(wheel_inst),
                "part_key": "wheel@tip",
                "features": [],
                "grounded": True,
                "sub_assembly": wheel.model_dump(mode="json"),
            }
        ],
        "patterns": [
            {
                "pattern_id": str(ROW),
                "order_index": 0,
                "pattern": {
                    "type": "linear",
                    "seed_instance_ids": [str(wheel_inst)],
                    "direction": {"kind": "origin_axis", "axis": "z"},
                    "count": 2,
                    "spacing_mm": 500.0,
                },
            }
        ],
    }
    request = EvaluateAssemblyRequest.model_validate(parent)
    result = evaluate_assembly(request)
    # 5 instances + 3 ring copies in the wheel = 8 plates, twice.
    assert len(result.instances) == 16
    copy_id = pattern_copy_id(ROW, wheel_inst, 1)
    copied = [row for row in result.instances if row.pattern is not None]
    assert len(copied) == 8
    assert all(row.path[0] == copy_id for row in copied)
    rows = {row.instance_id: row for row in result.instances}
    original = rows[nested_occurrence_id(wheel_inst, C)]
    twin = rows[nested_occurrence_id(copy_id, C)]
    assert Pose.from_placement(twin.placement).t == pytest.approx(
        Pose.from_placement(original.placement).t + np.array([0.0, 0.0, 500.0]),
        abs=TOL,
    )
    # A copy of a ring copy inside the wheel: its id nests the inner copy id.
    inner = pattern_copy_id(RING, C, 2)
    assert nested_occurrence_id(copy_id, inner) in rows
    # The counts route reports both levels, each pattern once.
    counts = {c.pattern_id: c.count for c in count_patterns(request).counts}
    assert counts == {ROW: 2, RING: 4}


def test_a_failed_reference_places_nothing_and_says_why() -> None:
    model = _model()
    model["patterns"][1]["pattern"]["direction"]["instance_id"] = str(uuid.UUID(int=9))
    model["patterns"][0]["pattern"]["also_on"] = [str(L)]  # same part: fine
    model["patterns"][2]["pattern"]["seed_instance_ids"] = [str(uuid.UUID(int=8))]
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    states = {s.pattern_id: s for s in result.pattern_states}
    assert states[ROW].count is None
    assert states[ROW].error_code == "pattern_reference_missing"
    assert states[RING].error_code == "pattern_seed_missing"
    assert states[HOLES].count == 4
    assert len(result.instances) == 5 + 3


def test_a_stale_edge_is_a_typed_subshape_error() -> None:
    model = _only(_model(), RING)
    signature = model["patterns"][0]["pattern"]["axis"]["signature"]
    for key in ("end_a", "end_b", "midpoint"):
        signature[key]["z"] = 55.0
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert result.pattern_states[0].error_code == "subshape_unresolved"
    assert len(result.instances) == 5


def test_a_driver_of_another_part_is_refused() -> None:
    model = _only(_model(), HOLES)
    model["instances"][1]["part_key"] = "another-part@1"
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert result.pattern_states[0].error_code == "pattern_driver_mismatch"


def test_the_bound_counts_explicit_copies_at_parse() -> None:
    model = _only(_model(), ROW)
    model["patterns"][0]["pattern"]["count"] = MAX_ASSEMBLY_INSTANCES
    with pytest.raises(ValidationError, match="places"):
        EvaluateAssemblyRequest.model_validate(model)


def test_a_hole_pattern_past_the_bound_places_nothing() -> None:
    """Seeds whose copies would pass the bound: the pattern is refused whole."""
    model = _only(_model(), HOLES)
    seeds: list[str] = []
    template = model["instances"][2]
    for n in range(40):
        inst = copy.deepcopy(template)
        inst["instance_id"] = str(uuid.UUID(int=0x1000 + n))
        model["instances"].append(inst)
        seeds.append(inst["instance_id"])
    # 40 seeds x (2 holes x 8 driving plates - 1) copies = 600: past the bound.
    model["patterns"][0]["pattern"]["seed_instance_ids"] = seeds
    model["patterns"][0]["pattern"]["also_on"] = [str(A2), str(L), str(C)] + [
        str(uuid.UUID(int=0x2000 + n)) for n in range(4)
    ]
    for n in range(4):
        driver = copy.deepcopy(model["instances"][0])
        driver["instance_id"] = str(uuid.UUID(int=0x2000 + n))
        model["instances"].append(driver)
    assert MAX_ASSEMBLY_INSTANCES < 40 * 15
    model["mates"] = []
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    state = result.pattern_states[0]
    assert (state.count, state.error_code) == (None, "pattern_too_large")
    assert len(result.instances) == len(model["instances"])


def test_interference_sees_the_copies() -> None:
    """The hole pattern's copies overlap their seed (16 mm apart, 40 long)."""
    result = check_interference(
        EvaluateAssemblyRequest.model_validate(_only(_model(), HOLES))
    )
    pairs = {(clash.instance_a, clash.instance_b) for clash in result.clashes}
    assert (P, pattern_copy_id(HOLES, P, 1)) in pairs


_NAUO = re.compile(rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\(")


def test_step_export_holds_every_copy() -> None:
    request = ExportAssemblyRequest.model_validate(
        {**_model(), "format": "step", "name": "Patterned plates"}
    )
    data = export_assembly(request)
    assert len(_NAUO.findall(data)) == 13


def test_named_step_export_does_not_carry_the_writer_counter() -> None:
    """Named copies write long occurrence lines that OCCT wraps, and where it
    wraps depended on the digits of its process-global occurrence counter: the
    same request exported later in a worker came out with different bytes. The
    wrap is joined before the counter is renumbered, so it no longer does."""
    model = _model()
    for n, inst in enumerate(model["instances"], start=1):
        inst["name"] = f"Plate <{n}>"
    request = ExportAssemblyRequest.model_validate(
        {**model, "format": "step", "name": "Patterned plates"}
    )
    first = export_assembly(request)
    # Push OCCT's counter through more digits (13 occurrences per write).
    for _ in range(8):
        export_assembly(request)
    assert export_assembly(request) == first


def test_the_counts_route_answers_every_pattern() -> None:
    response = TestClient(app).post(
        "/api/v1/assembly/pattern-counts", json=_MODEL.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    assert [(c["pattern_id"], c["count"]) for c in response.json()["counts"]] == [
        (str(HOLES), 4),
        (str(ROW), 3),
        (str(RING), 4),
    ]
