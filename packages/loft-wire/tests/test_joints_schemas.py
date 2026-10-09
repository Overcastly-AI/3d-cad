"""loft_wire.joints: the ``type="joint"`` mate, its limits, value and update.

Pins that every motion round-trips through the :data:`Mate` union, that bad
limits (min above max, or an axis the motion does not free) are refused, and
that the five legacy mates and a joint-free evaluation result still dump
byte-for-byte as they did before joints existed.
"""

import hashlib
import uuid
from typing import Any

import pytest
from loft_wire.assemblies import (
    EvaluateAssemblyResult,
    Mate,
    mate_instance_ids,
)
from loft_wire.geometry import Vec3
from loft_wire.joints import (
    JointLimits,
    JointMate,
    JointState,
    JointValue,
    MateUpdate,
    joint_limit_violation,
)
from pydantic import TypeAdapter, ValidationError

INST_A = "6f3f6b64-0000-4000-8000-0000000000a1"
INST_B = "6f3f6b64-0000-4000-8000-0000000000a2"

_MATE: TypeAdapter[Mate] = TypeAdapter(Mate)

FACE_SIG: dict[str, Any] = {
    "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
    "centroid": {"x": 20.0, "y": 12.5, "z": 10.0},
    "area_mm2": 1000.0,
}
CIRCLE_SIG: dict[str, Any] = {
    "curve": "circle",
    "end_a": {"x": 5.0, "y": 5.0, "z": 0.0},
    "end_b": {"x": 5.0, "y": 5.0, "z": 0.0},
    "midpoint": {"x": 5.0, "y": 5.0, "z": 0.0},
    "length_mm": 15.707963,
}
LINE_SIG: dict[str, Any] = {
    "curve": "line",
    "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
    "end_b": {"x": 10.0, "y": 0.0, "z": 0.0},
    "midpoint": {"x": 5.0, "y": 0.0, "z": 0.0},
    "length_mm": 10.0,
}


def _face(instance_id: str = INST_A) -> dict[str, Any]:
    return {"instance_id": instance_id, "kind": "face_centre", "signature": FACE_SIG}


def _circle(instance_id: str = INST_B) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "kind": "circle_centre",
        "signature": CIRCLE_SIG,
        "flip": True,
        "quarter_turns": 3,
    }


def _joint(motion: str, **over: Any) -> dict[str, Any]:
    return {"type": "joint", "motion": motion, "a": _face(), "b": _circle(), **over}


#: A limit and value set that suits each motion.
_SUITED: dict[str, dict[str, Any]] = {
    "rigid": {},
    "revolute": {
        "limits": {"rot_min_deg": -90.0, "rot_max_deg": 180.0},
        "value": {"rot_deg": 45.0},
    },
    "slider": {"limits": {"lin_min_mm": 0.0}, "value": {"lin_mm": 12.5}},
    "cylindrical": {
        "limits": {"rot_max_deg": 30.0, "lin_min_mm": -5.0, "lin_max_mm": 5.0},
        "value": {"rot_deg": 10.0, "lin_mm": 2.0},
    },
    "planar": {"limits": {"rot_min_deg": 0.0}, "value": {"rot_deg": 5.0}},
    "ball": {},
}


@pytest.mark.parametrize("motion", sorted(_SUITED))
def test_every_motion_round_trips(motion: str) -> None:
    payload = _joint(motion, offset_mm=1.5, angle_deg=-90.0, **_SUITED[motion])
    mate = _MATE.validate_python(payload)
    assert isinstance(mate, JointMate)
    assert mate.motion == motion
    again = _MATE.validate_json(_MATE.dump_json(mate))
    assert again == mate
    assert mate_instance_ids(mate) == (uuid.UUID(INST_A), uuid.UUID(INST_B))


def test_joint_defaults() -> None:
    mate = _MATE.validate_python(_joint("rigid"))
    assert isinstance(mate, JointMate)
    assert (mate.offset_mm, mate.angle_deg, mate.limits) == (0.0, 0.0, None)
    assert mate.value == JointValue()
    assert (mate.a.flip, mate.a.quarter_turns) == (False, 0)


def test_edge_point_origin_needs_at() -> None:
    edge = {"instance_id": INST_B, "kind": "edge_point", "signature": LINE_SIG}
    with pytest.raises(ValidationError, match="needs `at`"):
        _MATE.validate_python(_joint("slider", b=edge))
    for at in ("start", "mid", "end"):
        mate = _MATE.validate_python(_joint("slider", b={**edge, "at": at}))
        assert isinstance(mate, JointMate)
        assert mate.b.at == at
    with pytest.raises(ValidationError):
        _MATE.validate_python(_joint("slider", b={**edge, "at": "middle"}))


@pytest.mark.parametrize(
    ("origin", "message"),
    [
        ({"kind": "face_centre", "signature": CIRCLE_SIG}, "planar-face"),
        ({"kind": "circle_centre", "signature": FACE_SIG}, "edge signature"),
        ({"kind": "circle_centre", "signature": LINE_SIG}, "circular edge"),
        ({"kind": "face_centre", "signature": FACE_SIG, "at": "mid"}, "edge_point"),
        (
            {"kind": "face_centre", "signature": FACE_SIG, "quarter_turns": 4},
            "quarter_turns",
        ),
        ({"kind": "vertex", "signature": FACE_SIG}, "kind"),
    ],
)
def test_malformed_origin_is_rejected(origin: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _MATE.validate_python(_joint("rigid", a={"instance_id": INST_A, **origin}))


@pytest.mark.parametrize(
    "limits",
    [
        {"rot_min_deg": 10.0, "rot_max_deg": 5.0},
        {"lin_min_mm": 1.0, "lin_max_mm": 0.0},
    ],
)
def test_min_above_max_is_rejected(limits: dict[str, float]) -> None:
    with pytest.raises(ValidationError, match="exceeds"):
        _MATE.validate_python(_joint("cylindrical", limits=limits))


@pytest.mark.parametrize(
    ("motion", "limits"),
    [
        ("revolute", {"lin_max_mm": 5.0}),
        ("slider", {"rot_max_deg": 5.0}),
        ("planar", {"lin_min_mm": 0.0}),
        ("rigid", {"rot_min_deg": 0.0}),
        ("ball", {"rot_max_deg": 30.0}),
    ],
)
def test_limits_that_do_not_apply_are_rejected(
    motion: str, limits: dict[str, float]
) -> None:
    with pytest.raises(ValidationError, match="takes no"):
        _MATE.validate_python(_joint(motion, limits=limits))


@pytest.mark.parametrize(
    ("motion", "value"),
    [("revolute", {"lin_mm": 1.0}), ("slider", {"rot_deg": 1.0}), ("ball", {})],
)
def test_values_that_do_not_apply_are_rejected(
    motion: str, value: dict[str, float]
) -> None:
    if not value:
        value = {"rot_deg": 1.0}
    with pytest.raises(ValidationError, match="has no"):
        _MATE.validate_python(_joint(motion, value=value))


@pytest.mark.parametrize(
    "over",
    [
        {"offset_mm": float("inf")},
        {"angle_deg": float("nan")},
        {"value": {"rot_deg": 1e9}},
        {"limits": {"rot_max_deg": float("inf")}},
    ],
)
def test_non_finite_and_unbounded_numbers_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _MATE.validate_python(_joint("revolute", **over))


def test_limit_violation_names_the_limit() -> None:
    revolute = JointMate.model_validate(
        _joint(
            "revolute",
            limits={"rot_min_deg": -10.0, "rot_max_deg": 180.0},
            value={"rot_deg": 200.0},
        )
    )
    assert joint_limit_violation(revolute, "Revolute 1") == (
        "Revolute 1: 200° exceeds max 180°"
    )
    slider = JointMate.model_validate(
        _joint("slider", limits={"lin_min_mm": 0.0}, value={"lin_mm": -2.5})
    )
    assert joint_limit_violation(slider, "Slider 2") == (
        "Slider 2: -2.5 mm is below min 0 mm"
    )
    inside = JointMate.model_validate(_joint("revolute", **_SUITED["revolute"]))
    assert joint_limit_violation(inside, "Revolute 1") is None
    assert joint_limit_violation(JointMate.model_validate(_joint("ball")), "B") is None


def test_mate_update_applies_fields_and_distinguishes_null_limits() -> None:
    joint = JointMate.model_validate(_joint("revolute", **_SUITED["revolute"]))
    update = MateUpdate.model_validate(
        {
            "expected_version": 3,
            "value": {"rot_deg": 90.0},
            "flip": False,
            "quarter_turns": 1,
            "offset_mm": 2.0,
        }
    )
    patched = update.apply_to(joint)
    assert patched.value.rot_deg == 90.0
    assert patched.limits == joint.limits  # absent: unchanged
    assert (patched.b.flip, patched.b.quarter_turns, patched.offset_mm) == (
        False,
        1,
        2.0,
    )
    assert patched.a == joint.a
    cleared = MateUpdate.model_validate({"expected_version": 3, "limits": None})
    assert not cleared.is_empty()
    assert cleared.apply_to(joint).limits is None
    assert MateUpdate.model_validate({"expected_version": 3}).is_empty()


def test_mate_update_revalidates_the_whole_joint() -> None:
    joint = JointMate.model_validate(_joint("revolute"))
    update = MateUpdate.model_validate(
        {"expected_version": 0, "value": {"lin_mm": 1.0}}
    )
    with pytest.raises(ValidationError, match="has no linear value"):
        update.apply_to(joint)
    assert JointLimits().has_rotation() is False


# --- legacy payloads stay byte-identical -------------------------------------------

_LEGACY_FACE = {"kind": "face", "signature": FACE_SIG}
_LEGACY_AXIS = {"kind": "axis", "signature": CIRCLE_SIG}

#: sha256 of each legacy payload's JSON dump, captured from the wire BEFORE the
#: joint member joined the union (ef2370a).
_LEGACY: list[tuple[dict[str, Any], str]] = [
    (
        {
            "type": "coincident",
            "a": {**_LEGACY_FACE, "instance_id": INST_A},
            "b": {**_LEGACY_FACE, "instance_id": INST_B},
            "flush": False,
        },
        "580c8fe7624f81e617437f0eeb0b959cb0ab6ec174a3c66e1fd197eb9c7184fd",
    ),
    (
        {
            "type": "concentric",
            "a": {**_LEGACY_AXIS, "instance_id": INST_A},
            "b": {**_LEGACY_AXIS, "instance_id": INST_B},
        },
        "00894350e731dfb38f185a702e30dea12c440f6b06a395945e72b62399f93044",
    ),
    (
        {
            "type": "distance",
            "a": {**_LEGACY_FACE, "instance_id": INST_A},
            "b": {**_LEGACY_FACE, "instance_id": INST_B},
            "distance_mm": 12.5,
        },
        "6685463d9436d3f25f25fdcfe54d4fad73abfc165adbc5eda188bd8b75f609da",
    ),
    (
        {
            "type": "angle",
            "a": {**_LEGACY_FACE, "instance_id": INST_A},
            "b": {**_LEGACY_FACE, "instance_id": INST_B},
            "angle_deg": 30.0,
        },
        "654eb95c7075bd38ed7275927b760cc1d7e1efb2dfc821378e622bbbbe7cc69d",
    ),
    (
        {"type": "lock", "a_instance_id": INST_A, "b_instance_id": INST_B},
        "f662e125f583ebb0ca9cc91f2d21ff7fbf4cc46f3e28abfe04512ec3a1d6239d",
    ),
]


@pytest.mark.parametrize(("payload", "digest"), _LEGACY)
def test_legacy_mates_dump_byte_identically(
    payload: dict[str, Any], digest: str
) -> None:
    dumped = _MATE.dump_json(_MATE.validate_python(payload))
    assert hashlib.sha256(dumped).hexdigest() == digest


def test_result_without_joints_dumps_byte_identically() -> None:
    result = EvaluateAssemblyResult(
        assembly_id=uuid.UUID(INST_A),
        version=3,
        instances=[],
        status="well_constrained",
    )
    assert result.model_dump_json() == (
        '{"assembly_id":"6f3f6b64-0000-4000-8000-0000000000a1","version":3,'
        '"instances":[],"status":"well_constrained","diagnosis":null,'
        '"mate_errors":[],"properties":null,"bounding_box":null}'
    )


def test_result_with_joints_dumps_joint_states() -> None:
    state = JointState(
        mate_id=uuid.UUID(INST_B),
        rot_deg=45.0,
        axis_world=Vec3(x=0.0, y=0.0, z=1.0),
    )
    result = EvaluateAssemblyResult(
        assembly_id=uuid.UUID(INST_A),
        version=3,
        instances=[],
        status="well_constrained",
        joint_states=[state],
    )
    dumped = result.model_dump(mode="json")
    assert dumped["joint_states"] == [
        {
            "mate_id": INST_B,
            "rot_deg": 45.0,
            "lin_mm": None,
            "at_limit": False,
            "axis_world": {"x": 0.0, "y": 0.0, "z": 1.0},
        }
    ]
    assert EvaluateAssemblyResult.model_validate(dumped) == result
