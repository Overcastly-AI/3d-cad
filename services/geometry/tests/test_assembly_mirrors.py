"""Mirror components (ASM-MIRROR-COMPONENT): twins placed after the solve.

The analytic exit gate is the ``assembly-component-mirror`` golden (an
asymmetric L mirrored three ways). This suite covers the rest of the contract
on the same model:

- every twin IS the mirror image: the twin's world body and the seed's world
  body reflected about the plane have no volume between them (a boolean check,
  independent of the placement formula), and every twin pose is proper;
- an opposite hand has the source's volume and its centroid reflected; a copy
  shares the seed's mesh, an opposite hand has its own;
- a copy of a part that is not symmetric about its assumed plane is flagged;
- twins follow an edit of the seed's part and a move of the seed;
- a sub-assembly seed is mirrored whole, its parts keyed under the twin id;
- every failure is a typed per-mirror state and the rest still evaluates;
- the instance bound counts twins.
"""

# The OCP wheel ships no type stubs; the directive scopes that to this file.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import Location, Plane
from fastapi.testclient import TestClient
from geometry.assembly import evaluate_assembly
from geometry.assembly.evaluate import solve_assembly
from geometry.assembly.transform import Pose
from geometry.kernel.export import placement_trsf
from geometry.kernel.types import BodyShape
from geometry.main import app
from loft_wire.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    EvaluateAssemblyRequest,
    occurrence_id,
)
from loft_wire.component_mirrors import mirror_copy_id
from pydantic import ValidationError

_GOLDEN = Path(__file__).resolve().parent.parent / "goldens-assembly"
_MODEL = EvaluateAssemblyRequest.model_validate_json(
    (_GOLDEN / "assembly-component-mirror" / "model.json").read_text("utf-8")
)

A = uuid.UUID(int=0xC1)
B = uuid.UUID(int=0xC2)
M1 = uuid.UUID(int=0xD1)
M2 = uuid.UUID(int=0xD2)
M3 = uuid.UUID(int=0xD3)
TOL = 1e-9

#: World plane (point, normal) of each golden mirror (see its derivation).
_PLANES = {
    uuid.UUID(int=0xD4): ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    M1: ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    M2: ((0.0, 0.0, 20.0), (0.0, 0.0, 1.0)),
    M3: ((70.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
}


def _model() -> dict[str, Any]:
    return _MODEL.model_dump(mode="json")


def _world(body: BodyShape, pose: Pose) -> BodyShape:
    trsf = placement_trsf(
        (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
        (float(pose.q[0]), float(pose.q[1]), float(pose.q[2]), float(pose.q[3])),
    )
    return body.moved(Location(trsf))


def _gap_volume(a: BodyShape, b: BodyShape) -> float:
    """The volume in one body and not the other (0 for the same solid)."""
    return float(a.cut(b).volume + b.cut(a).volume)


def test_every_twin_is_the_mirror_image_of_its_seed() -> None:
    solved = solve_assembly(_MODEL)
    by_id = {occ.occurrence_id: occ for occ in solved.occurrences}
    twins = [occ for occ in solved.occurrences if occ.mirror is not None]
    assert len(twins) == 3
    for twin in twins:
        assert twin.mirror is not None
        seed = by_id[twin.mirror.seed_instance_id]
        assert twin.body is not None and seed.body is not None
        point, normal = _PLANES[twin.mirror.mirror_id]
        pose = Pose.from_placement(twin.placement)
        assert np.linalg.det(pose.matrix()) == pytest.approx(1.0, abs=TOL)
        reflected = _world(seed.body, Pose.from_placement(seed.placement)).mirror(
            Plane(origin=point, z_dir=normal)
        )
        assert _gap_volume(_world(twin.body, pose), reflected) < 1e-6, twin.name


def test_opposite_hand_volume_centroid_and_meshes() -> None:
    result = evaluate_assembly(_MODEL)
    rows = {row.instance_id: row for row in result.instances}
    seed = rows[A]
    hand = rows[mirror_copy_id(M1, A)]
    copy_row = rows[mirror_copy_id(M2, B)]
    assert seed.properties is not None and hand.properties is not None
    assert hand.properties.volume == pytest.approx(seed.properties.volume, abs=TOL)
    assert hand.properties.surface_area == pytest.approx(
        seed.properties.surface_area, abs=1e-6
    )
    # Reflected about the L's own x = 30: centroid x 23.75 -> 36.25.
    assert hand.properties.centroid.x == pytest.approx(36.25, abs=TOL)
    assert hand.properties.bounding_box == seed.properties.bounding_box
    assert hand.mirror is not None and hand.mirror.opposite_hand
    assert copy_row.mirror is not None and not copy_row.mirror.opposite_hand
    # A copy is the seed's own part; an opposite hand is a derived part with
    # its own mesh, shared by both opposite hands of the L.
    assert copy_row.part_mesh_glb_id == seed.part_mesh_glb_id
    assert hand.part_mesh_glb_id != seed.part_mesh_glb_id
    assert rows[mirror_copy_id(M3, B)].part_mesh_glb_id == hand.part_mesh_glb_id


#: A Z-shaped plate (10 thick): point-symmetric in its sketch, so its centroid
#: sits at its box centre, yet it is NOT symmetric about its local X or Y
#: mid-plane (reflected, a Z is an S); it is only about its mid-thickness.
_Z: list[tuple[float, float]] = [
    (5, 0), (30, 0), (30, 10), (20, 10), (20, 30), (25, 30),
    (25, 40), (0, 40), (0, 30), (10, 30), (10, 10), (5, 10),
]  # fmt: skip


def _sketch(points: list[tuple[float, float]], feature_id: int) -> dict[str, Any]:
    entities = [
        {
            "id": f"e{i + 1}",
            "construction": False,
            "kind": "line",
            "start": {"x": float(a[0]), "y": float(a[1])},
            "end": {"x": float(b[0]), "y": float(b[1])},
        }
        for i, (a, b) in enumerate(zip(points, points[1:] + points[:1], strict=True))
    ]
    return {
        "id": str(uuid.UUID(int=feature_id)),
        "feature": {
            "suppressed": False,
            "type": "sketch",
            "version": 1,
            "params": {
                "entities": entities,
                "constraints": [],
                "plane": {"kind": "datum_plane", "plane": "XY"},
            },
        },
    }


def _extrude(sketch_id: int, feature_id: int, depth: float) -> dict[str, Any]:
    return {
        "id": str(uuid.UUID(int=feature_id)),
        "feature": {
            "suppressed": False,
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {
                    "kind": "feature",
                    "feature_id": str(uuid.UUID(int=sketch_id)),
                },
                "distance_mm": depth,
                "operation": "add",
                "direction": "normal",
                "merge": True,
            },
        },
    }


def _z_plate() -> list[dict[str, Any]]:
    return [_sketch(_Z, 0xA1), _extrude(0xA1, 0xB1, 10.0)]


def _stepped_l() -> list[dict[str, Any]]:
    """The golden's L with a 15-high block on its upright: symmetric about no
    mid-plane at all."""
    model = _model()
    features: list[dict[str, Any]] = copy.deepcopy(model["instances"][0]["features"])
    block = [(0.0, 20.0), (10.0, 20.0), (10.0, 30.0), (0.0, 30.0)]
    return [*features, _sketch(block, 0xA2), _extrude(0xA2, 0xB2, 15.0)]


def _copies_about_yz(features: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """A and B both made of *features*; one mirror copying A about YZ."""
    model = _model()
    for inst in model["instances"]:
        inst["features"] = features
        inst["part_key"] = key
    model["mirrors"] = [
        {
            "mirror_id": str(M1),
            "order_index": 0,
            "mirror": {
                "seed_instance_ids": [str(A)],
                "plane": {"kind": "origin_plane", "plane": "yz", "offset_mm": 0.0},
            },
        }
    ]
    return model


def _twin_gap(request: EvaluateAssemblyRequest, mirror: uuid.UUID) -> float:
    """Volume between every twin of *mirror* and its seed reflected about
    *mirror*'s plane (0 when every twin is the mirror image)."""
    solved = solve_assembly(request)
    by_id = {
        (occ.group_id, occ.path[1:]): occ
        for occ in solved.occurrences
        if occ.mirror is None and occ.pattern is None
    }
    point, normal = _PLANES[mirror]
    gap = 0.0
    for twin in solved.occurrences:
        if twin.mirror is None or twin.mirror.mirror_id != mirror:
            continue
        seed = by_id[(twin.mirror.seed_instance_id, twin.path[1:])]
        assert twin.body is not None and seed.body is not None
        reflected = _world(seed.body, Pose.from_placement(seed.placement)).mirror(
            Plane(origin=point, z_dir=normal)
        )
        gap += _gap_volume(
            _world(twin.body, Pose.from_placement(twin.placement)), reflected
        )
    return gap


def test_a_z_plate_copy_turns_about_its_mid_thickness() -> None:
    """The plane normal is the Z plate's local X, but a Z is not symmetric
    about its X mid-plane (its centroid is): the copy uses the axis it IS
    symmetric about, its mid-thickness, and is the exact mirror image."""
    request = EvaluateAssemblyRequest.model_validate(
        _copies_about_yz(_z_plate(), "part-z-plate@1")
    )
    (state,) = evaluate_assembly(request).mirror_states
    assert (state.placed, state.asymmetric) == (1, [])
    assert _twin_gap(request, M1) < 1e-6


def test_an_l_copy_is_a_mirror_image_and_a_fully_asymmetric_one_is_flagged() -> None:
    """The golden's L is symmetric about its mid-thickness, so its copy about
    YZ is a true mirror image. With a block on its upright it is symmetric
    about nothing: the copy is flagged for an opposite hand."""
    l_arm = EvaluateAssemblyRequest.model_validate(
        _copies_about_yz(_model()["instances"][0]["features"], "part-crank-arm-L@1")
    )
    (state,) = evaluate_assembly(l_arm).mirror_states
    assert state.asymmetric == []
    assert _twin_gap(l_arm, M1) < 1e-6

    stepped = EvaluateAssemblyRequest.model_validate(
        _copies_about_yz(_stepped_l(), "part-stepped-L@1")
    )
    (state,) = evaluate_assembly(stepped).mirror_states
    assert (state.placed, state.asymmetric) == (1, [A])
    assert _twin_gap(stepped, M1) > 100.0  # the flagged copy is not a mirror


def _thicker(features: list[dict[str, Any]], depth: float) -> list[dict[str, Any]]:
    out = copy.deepcopy(features)
    out[1]["feature"]["params"]["distance_mm"] = depth
    return out


def test_twins_follow_an_edit_of_the_part_and_a_move_of_the_seed() -> None:
    model = _model()
    for inst in model["instances"]:
        inst["features"] = _thicker(inst["features"], 16.0)
        inst["part_key"] = "part-crank-arm-L@2"
    model["instances"][1]["placement"]["position"]["x"] = 0.0
    request = EvaluateAssemblyRequest.model_validate(model)
    rows = {row.instance_id: row for row in evaluate_assembly(request).instances}
    hand = rows[mirror_copy_id(M1, A)]
    assert hand.properties is not None
    assert hand.properties.volume == pytest.approx(800.0 * 16.0, abs=1e-6)
    # B moved 10 in -X and is now 16 thick (mid-plane z = 8): its copy about
    # z = 20 sits at z = 2 * 20 - 16 = 24, and follows B to x = 0.
    twin = Pose.from_placement(rows[mirror_copy_id(M2, B)].placement)
    assert twin.t == pytest.approx([0.0, 50.0, 24.0], abs=TOL)
    # Its opposite hand about x = 70: t' = D_x((0, 110, 0) - p) + p.
    hand_b = Pose.from_placement(rows[mirror_copy_id(M3, B)].placement)
    assert hand_b.t == pytest.approx([140.0, 110.0, 0.0], abs=TOL)


def _wheel_model() -> dict[str, Any]:
    """The L twice inside a sub-assembly W, instanced at (0, 0, 50)."""
    base = _model()
    part = base["instances"][0]
    inner = [
        {**copy.deepcopy(part), "instance_id": str(uuid.UUID(int=0xE1))},
        {
            **copy.deepcopy(part),
            "instance_id": str(uuid.UUID(int=0xE2)),
            "placement": {
                "position": {"x": 0.0, "y": 40.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
        },
    ]
    sub = {
        "assembly_id": str(uuid.UUID(int=0xAB)),
        "version": 1,
        "instances": inner,
        "mates": [],
    }
    return {
        **base,
        "instances": [
            *base["instances"],
            {
                "instance_id": str(uuid.UUID(int=0xC3)),
                "part_key": "asm-w@1",
                "name": "W <1>",
                "features": [],
                "placement": {
                    "position": {"x": 0.0, "y": 0.0, "z": 50.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                "grounded": True,
                "sub_assembly": sub,
            },
        ],
        "mirrors": [
            {
                "mirror_id": str(uuid.UUID(int=0xD4)),
                "order_index": 0,
                "mirror": {
                    "seed_instance_ids": [str(uuid.UUID(int=0xC3))],
                    "plane": {"kind": "origin_plane", "plane": "xy", "offset_mm": 0.0},
                },
            }
        ],
    }


def test_a_sub_assembly_is_mirrored_whole() -> None:
    """W spans z 50..60 (its box centre z = 5 in its frame): its twin about
    XY is W turned D_z . I . D_z = I at z = -(50 + 10) = -60, and each part
    keeps its pose inside it, keyed under the twin id."""
    request = EvaluateAssemblyRequest.model_validate(_wheel_model())
    result = evaluate_assembly(request)
    twin_id = mirror_copy_id(uuid.UUID(int=0xD4), uuid.UUID(int=0xC3))
    rows = {row.instance_id: row for row in result.instances}
    for inner, at in (
        (uuid.UUID(int=0xE1), (10.0, 0.0)),
        (uuid.UUID(int=0xE2), (0.0, 40.0)),
    ):
        row = rows[occurrence_id((twin_id, inner))]
        assert row.path == [twin_id, inner]
        assert row.mirror is not None
        assert Pose.from_placement(row.placement).t == pytest.approx(
            [*at, -60.0], abs=TOL
        )
    assert (result.mirror_states[0].placed, result.mirror_states[0].asymmetric) == (
        1,
        [],
    )
    # Symmetric as a whole (both arms span z 0..10): its twin is the image.
    assert _twin_gap(request, uuid.UUID(int=0xD4)) < 1e-6


def test_an_asymmetric_sub_assembly_copy_is_flagged() -> None:
    model = _wheel_model()
    for inst in model["instances"][2]["sub_assembly"]["instances"]:
        inst["features"] = _stepped_l()
        inst["part_key"] = "part-stepped-L@1"
    request = EvaluateAssemblyRequest.model_validate(model)
    (state,) = evaluate_assembly(request).mirror_states
    assert state.asymmetric == [uuid.UUID(int=0xC3)]


def test_an_opposite_hand_of_a_sub_assembly_is_refused() -> None:
    model = _wheel_model()
    model["mirrors"][0]["mirror"]["opposite_hand_instance_ids"] = [
        str(uuid.UUID(int=0xC3))
    ]
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    (state,) = result.mirror_states
    assert (state.placed, state.error_code) == (0, "mirror_opposite_hand_needs_part")
    assert all(row.mirror is None for row in result.instances)


def _break(model: dict[str, Any], code: str) -> None:
    """Break the golden's face-plane mirror M3 so that it fails with *code*."""
    mirror: dict[str, Any] = model["mirrors"][2]["mirror"]
    plane: dict[str, Any] = mirror["plane"]
    if code == "mirror_reference_missing":
        plane["instance_id"] = str(uuid.UUID(int=0xFF))
    elif code == "subshape_unresolved":
        far = {"x": 500.0, "y": 500.0, "z": 500.0}
        plane["signature"].update(
            normal={"x": 0.0, "y": 0.0, "z": 1.0}, centroid=far, outer_centroid=far
        )
    else:
        mirror["seed_instance_ids"] = [str(uuid.UUID(int=0xFE))]
        mirror["opposite_hand_instance_ids"] = []


@pytest.mark.parametrize(
    "code", ["mirror_reference_missing", "subshape_unresolved", "mirror_seed_missing"]
)
def test_a_failing_mirror_is_a_typed_state(code: str) -> None:
    model = _model()
    _break(model, code)
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    states = {s.mirror_id: s for s in result.mirror_states}
    assert (states[M3].placed, states[M3].error_code) == (0, code)
    assert states[M1].error_code is None and states[M2].error_code is None
    assert len(result.instances) == 4


def test_the_instance_bound_counts_twins() -> None:
    """250 parts mirrored: 500 placed parts is the bound and parses; one
    more part is refused at parse."""
    base = _model()
    part = base["instances"][0]

    def model(n: int) -> dict[str, Any]:
        instances = [
            {**copy.deepcopy(part), "instance_id": str(uuid.UUID(int=0x1000 + i))}
            for i in range(n)
        ]
        return {
            **base,
            "instances": instances,
            "mirrors": [
                {
                    "mirror_id": str(uuid.UUID(int=0xD9 + k)),
                    "order_index": k,
                    "mirror": {
                        "seed_instance_ids": [
                            inst["instance_id"]
                            for inst in instances[k * 50 : k * 50 + 50]
                        ],
                        "plane": {"kind": "origin_plane", "plane": "yz"},
                    },
                }
                for k in range((n + 49) // 50)
            ],
        }

    assert MAX_ASSEMBLY_INSTANCES == 500
    EvaluateAssemblyRequest.model_validate(model(250))
    with pytest.raises(ValidationError, match="places 502 parts"):
        EvaluateAssemblyRequest.model_validate(model(251))


def test_the_evaluate_route_carries_twins_and_states() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assembly/evaluate", json=_MODEL.model_dump(mode="json")
        )
    assert response.status_code == 200, response.text
    body = response.json()
    twins = [row for row in body["instances"] if "mirror" in row]
    assert len(twins) == 3
    assert [s["placed"] for s in body["mirror_states"]] == [1, 1, 1]
    # A plain row carries no mirror key: requests and results without mirrors
    # serialize exactly as before.
    assert "mirror" not in body["instances"][0]
