"""Rigid sub-assemblies (ASM-A3 step 1): evaluate, solve, clash and export a
nested assembly.

The analytic exit gate is the ``assembly-nested-hinge-pair`` golden (two hinge
sub-assemblies plus a plate jointed to a part inside one). This suite covers the
rest of the contract on the same real plates:

- a sub-assembly moves as ONE body: its parts follow the instance pose, and its
  own joint is solved in its own frame first;
- nesting works to any depth, and every part comes back keyed by the occurrence
  id of its instance path;
- a mate between two parts of ONE rigid sub-assembly, or naming the
  sub-assembly itself by geometry, is a typed per-mate error, never a 500;
- the request bounds count PLACED parts and nesting depth;
- interference and STEP export see every nested part.
"""

from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from geometry.assembly import evaluate_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.interference import check_interference
from geometry.assembly.transform import Pose
from loft_wire.assemblies import (
    MAX_ASSEMBLY_DEPTH,
    MAX_ASSEMBLY_INSTANCES,
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
    nested_occurrence_id,
    occurrence_id,
)
from pydantic import ValidationError

_GOLDENS = Path(__file__).resolve().parent.parent / "goldens-assembly"
_NESTED = EvaluateAssemblyRequest.model_validate_json(
    (_GOLDENS / "assembly-nested-hinge-pair" / "model.json").read_text("utf-8")
)
_HINGE = EvaluateAssemblyRequest.model_validate_json(
    (_GOLDENS / "assembly-hinge-revolute" / "model.json").read_text("utf-8")
)

W1 = uuid.UUID(int=0xF1)
W2 = uuid.UUID(int=0xF2)
C = uuid.UUID(int=0xF3)
A = uuid.UUID(int=1)
B = uuid.UUID(int=2)
TOL = 1e-9


def _model() -> dict[str, Any]:
    return _NESTED.model_dump(mode="json")


def _placements(request: EvaluateAssemblyRequest) -> dict[uuid.UUID, Pose]:
    result = evaluate_assembly(request)
    return {
        row.instance_id: Pose.from_placement(row.placement) for row in result.instances
    }


def _assert_pose(got: Pose, want: Pose) -> None:
    assert got.t == pytest.approx(want.t, abs=TOL)
    assert got.matrix() == pytest.approx(want.matrix(), abs=TOL)


def test_rows_carry_the_path_and_the_occurrence_id() -> None:
    result = evaluate_assembly(_NESTED)
    paths = [(row.instance_id, row.path) for row in result.instances]
    assert paths == [
        (nested_occurrence_id(W1, A), [W1, A]),
        (nested_occurrence_id(W1, B), [W1, B]),
        (nested_occurrence_id(W2, A), [W2, A]),
        (nested_occurrence_id(W2, B), [W2, B]),
        (C, []),
    ]
    assert [s.instance_id for s in result.sub_assemblies] == [W1, W2]
    # A part instanced directly dumps exactly as before sub-assemblies existed.
    assert "path" not in result.instances[-1].model_dump()


def test_moving_the_sub_assembly_moves_everything_inside_it() -> None:
    """Re-seat W2 (grounded, so its seed IS its pose): both of its plates follow,
    each keeping its pose inside the hinge."""
    model = _model()
    moved = Pose(
        t=np.array([-40.0, 5.0, 7.0]),
        q=np.array([0.0, 0.0, 0.0, 1.0]),
    )
    model["instances"][1]["placement"] = moved.to_placement().model_dump(mode="json")
    got = _placements(EvaluateAssemblyRequest.model_validate(model))
    inside = _placements(_HINGE)
    for part in (A, B):
        _assert_pose(got[nested_occurrence_id(W2, part)], moved.compose(inside[part]))
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    pose_w2 = next(s for s in result.sub_assemblies if s.instance_id == W2)
    _assert_pose(Pose.from_placement(pose_w2.placement), moved)


def test_the_sub_assembly_joint_is_solved_in_its_own_frame() -> None:
    """The hinge's B is SEEDED displaced; inside the parent it still sits where
    the hinge's own revolute joint puts it (rigid sub-assembly semantics)."""
    got = _placements(_NESTED)
    inside = _placements(_HINGE)
    _assert_pose(got[nested_occurrence_id(W1, B)], inside[B])
    assert inside[B].t == pytest.approx([24.5, 0.5, 10.0], abs=TOL)


def test_three_levels_deep() -> None:
    """A frame holding a hinge, held by a bike: the plate's id is the occurrence
    id of the whole path and its pose composes all three placements."""
    frame_id, bike_hinge, bike_frame = (uuid.UUID(int=n) for n in (0xA0, 0xA1, 0xA2))
    hinge = _HINGE.model_dump(mode="json")
    lift = Pose(t=np.array([0.0, 0.0, 30.0]), q=np.array([0.0, 0.0, 0.0, 1.0]))
    frame: dict[str, Any] = {
        "assembly_id": str(frame_id),
        "version": 1,
        "instances": [
            {
                "instance_id": str(bike_hinge),
                "part_key": "hinge@tip",
                "features": [],
                "grounded": True,
                "placement": lift.to_placement().model_dump(mode="json"),
                "sub_assembly": hinge,
            }
        ],
    }
    shift = Pose(t=np.array([5.0, -5.0, 0.0]), q=np.array([0.0, 0.0, 0.0, 1.0]))
    bike = EvaluateAssemblyRequest.model_validate(
        {
            "assembly_id": str(uuid.UUID(int=0xB1)),
            "version": 1,
            "instances": [
                {
                    "instance_id": str(bike_frame),
                    "part_key": "frame@tip",
                    "features": [],
                    "grounded": True,
                    "placement": shift.to_placement().model_dump(mode="json"),
                    "sub_assembly": frame,
                }
            ],
        }
    )
    got = _placements(bike)
    inside = _placements(_HINGE)
    plate_b = occurrence_id([bike_frame, bike_hinge, B])
    assert plate_b == nested_occurrence_id(
        bike_frame, nested_occurrence_id(bike_hinge, B)
    )
    _assert_pose(got[plate_b], shift.compose(lift).compose(inside[B]))
    rows = evaluate_assembly(bike).instances
    assert [row.path for row in rows] == [
        [bike_frame, bike_hinge, A],
        [bike_frame, bike_hinge, B],
    ]


def test_a_mate_inside_one_rigid_sub_assembly_is_refused_per_mate() -> None:
    model = _model()
    joint = model["mates"][0]["mate"]
    joint["b"]["instance_id"] = str(nested_occurrence_id(W1, A))
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert [e.error.code for e in result.mate_errors] == ["mate_within_sub_assembly"]
    # Everything still places; C just floats at its seed.
    assert len(result.instances) == 5
    assert all(row.error is None for row in result.instances)


def test_a_geometric_ref_to_the_sub_assembly_itself_is_unresolved() -> None:
    """A sub-assembly has no faces of its own: a joint must name a part in it."""
    model = _model()
    model["mates"][0]["mate"]["a"]["instance_id"] = str(W1)
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert [e.error.code for e in result.mate_errors] == ["mate_unresolved"]
    assert (
        "pick a face or edge of a part inside it" in result.mate_errors[0].error.message
    )


def test_a_lock_to_the_sub_assembly_itself_holds_the_whole_unit() -> None:
    """Lock names instances, not geometry, so it may name a sub-assembly."""
    model = _model()
    model["instances"][1]["grounded"] = False
    model["mates"].append(
        {
            "mate_id": str(uuid.UUID(int=0x7E2)),
            "order_index": 1,
            "mate": {
                "type": "lock",
                "a_instance_id": str(W1),
                "b_instance_id": str(W2),
            },
        }
    )
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert result.mate_errors == []
    assert result.status == "well_constrained"


def test_an_empty_sub_assembly_places_nothing_and_does_not_fail() -> None:
    model = _model()
    # A different document, so a different key (one key = one document).
    model["instances"][1]["part_key"] = "empty-assembly@1"
    model["instances"][1]["sub_assembly"]["instances"] = []
    model["instances"][1]["sub_assembly"]["mates"] = []
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert len(result.instances) == 3
    assert result.status == "well_constrained"
    assert [s.instance_id for s in result.sub_assemblies] == [W1, W2]


def test_a_bodyless_part_inside_reports_its_error_on_its_occurrence() -> None:
    model = _model()
    model["instances"][1]["part_key"] = "broken-hinge@1"
    model["instances"][1]["sub_assembly"]["mates"] = []
    model["instances"][1]["sub_assembly"]["instances"][1]["features"] = []
    model["instances"][1]["sub_assembly"]["instances"][1]["part_key"] = "empty@1"
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    failed = [row for row in result.instances if row.error is not None]
    assert [(row.instance_id, row.error.code) for row in failed if row.error] == [
        (nested_occurrence_id(W2, B), "no_body")
    ]
    assert failed[0].path == [W2, B]


def _nest(depth: int) -> dict[str, Any]:
    request: dict[str, Any] = _HINGE.model_dump(mode="json")
    for level in range(depth - 1):
        request = {
            "assembly_id": str(uuid.UUID(int=0xD000 + level)),
            "version": 1,
            "instances": [
                {
                    "instance_id": str(uuid.UUID(int=0xE000 + level)),
                    "part_key": f"level-{level}@tip",
                    "features": [],
                    "sub_assembly": request,
                }
            ],
        }
    return request


def test_nesting_depth_is_bounded() -> None:
    assert EvaluateAssemblyRequest.model_validate(_nest(MAX_ASSEMBLY_DEPTH))
    with pytest.raises(ValidationError, match="levels deep"):
        EvaluateAssemblyRequest.model_validate(_nest(MAX_ASSEMBLY_DEPTH + 1))


def test_the_instance_bound_counts_placed_parts() -> None:
    """Each sub-assembly instance places two plates: half the bound of hinge
    instances is fine, one more is over."""
    hinge = _HINGE.model_dump(mode="json")

    def request(n: int) -> dict[str, Any]:
        return {
            "assembly_id": str(uuid.UUID(int=0xC0)),
            "version": 1,
            "instances": [
                {
                    "instance_id": str(uuid.UUID(int=0x10000 + i)),
                    "part_key": "hinge@tip",
                    "features": [],
                    "sub_assembly": hinge,
                }
                for i in range(n)
            ],
        }

    assert EvaluateAssemblyRequest.model_validate(request(MAX_ASSEMBLY_INSTANCES // 2))
    with pytest.raises(ValidationError, match="places"):
        EvaluateAssemblyRequest.model_validate(request(MAX_ASSEMBLY_INSTANCES // 2 + 1))


def test_interference_pairs_nested_parts_by_occurrence_id() -> None:
    """Drop W2 onto W1: each of W2's plates clashes with its twin in W1."""
    model = _model()
    model["instances"][1]["placement"] = copy.deepcopy(
        model["instances"][0]["placement"]
    )
    result = check_interference(EvaluateAssemblyRequest.model_validate(model))
    pairs = {(clash.instance_a, clash.instance_b) for clash in result.clashes}
    assert (nested_occurrence_id(W1, A), nested_occurrence_id(W2, A)) in pairs
    assert (nested_occurrence_id(W1, B), nested_occurrence_id(W2, B)) in pairs


_NAUO = re.compile(rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\(")


def test_step_export_holds_every_nested_part() -> None:
    request = ExportAssemblyRequest.model_validate(
        {**_model(), "format": "step", "name": "Nested hinges"}
    )
    data = export_assembly(request)
    assert len(_NAUO.findall(data)) == 5
