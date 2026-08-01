"""py_kit.schemas.assemblies — placement, mates, refs, CRUD DTOs.

Validates the docs/design/assemblies.md §1.5 shapes: the quaternion/placement
defaults, the discriminated mate-geometry and mate unions (each of the five mate
kinds, malformed refs rejected), and the ``mate_instance_ids`` membership helper
the documents service checks writes against.
"""

import uuid
from typing import Any

import pytest
from py_kit.schemas.assemblies import (
    IDENTITY_PLACEMENT,
    AngleMate,
    CoincidentMate,
    ConcentricMate,
    DistanceMate,
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
    InstanceCreate,
    LockMate,
    Mate,
    MateAxisRef,
    MateFaceRef,
    MateGeometryRef,
    Placement,
    Quat,
    assembly_export_filename,
    assembly_export_root_name,
    mate_instance_ids,
)
from pydantic import TypeAdapter, ValidationError

INST_A = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000a1")
INST_B = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000a2")

_MATE_ADAPTER: TypeAdapter[Mate] = TypeAdapter(Mate)
_REF_ADAPTER: TypeAdapter[MateGeometryRef] = TypeAdapter(MateGeometryRef)

#: A stage-1 planar-face signature (reused verbatim from features).
FACE_SIG: dict[str, Any] = {
    "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
    "centroid": {"x": 20.0, "y": 12.5, "z": 10.0},
    "area_mm2": 1000.0,
}

#: A stage-1 circular-edge signature (curve == "circle").
AXIS_SIG: dict[str, Any] = {
    "curve": "circle",
    "end_a": {"x": 5.0, "y": 5.0, "z": 0.0},
    "end_b": {"x": 5.0, "y": 5.0, "z": 0.0},
    "midpoint": {"x": 5.0, "y": 5.0, "z": 0.0},
    "length_mm": 15.707963,
}


def _face_ref(instance_id: uuid.UUID = INST_A) -> dict[str, Any]:
    return {"kind": "face", "instance_id": str(instance_id), "signature": FACE_SIG}


def _axis_ref(instance_id: uuid.UUID = INST_A) -> dict[str, Any]:
    return {"kind": "axis", "instance_id": str(instance_id), "signature": AXIS_SIG}


# --- placement + quaternion -------------------------------------------------------


def test_placement_defaults_to_identity_orientation() -> None:
    placement = Placement.model_validate({"position": {"x": 1.0, "y": 2.0, "z": 3.0}})
    assert placement.orientation == Quat(x=0.0, y=0.0, z=0.0, w=1.0)
    assert IDENTITY_PLACEMENT.position.x == 0.0
    assert IDENTITY_PLACEMENT.orientation.w == 1.0


def test_quaternion_requires_all_four_components() -> None:
    with pytest.raises(ValidationError):
        Quat.model_validate({"x": 0.0, "y": 0.0, "z": 0.0})  # missing w


# --- mate-geometry ref discrimination ---------------------------------------------


def test_face_ref_carries_planar_signature() -> None:
    ref = _REF_ADAPTER.validate_python(_face_ref())
    assert isinstance(ref, MateFaceRef)
    assert ref.signature.area_mm2 == 1000.0


def test_axis_ref_carries_edge_signature() -> None:
    ref = _REF_ADAPTER.validate_python(_axis_ref())
    assert isinstance(ref, MateAxisRef)
    assert ref.signature.curve == "circle"


def test_unknown_ref_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _REF_ADAPTER.validate_python({"kind": "vertex", "instance_id": str(INST_A)})


def test_face_ref_with_edge_signature_is_rejected() -> None:
    #: A face ref carrying an edge signature is malformed — the wrong signature
    #: shape must not silently validate.
    with pytest.raises(ValidationError):
        _REF_ADAPTER.validate_python(
            {"kind": "face", "instance_id": str(INST_A), "signature": AXIS_SIG}
        )


# --- the five mate kinds ----------------------------------------------------------


def test_coincident_mate_round_trips() -> None:
    mate = _MATE_ADAPTER.validate_python(
        {"type": "coincident", "a": _face_ref(INST_A), "b": _face_ref(INST_B)}
    )
    assert isinstance(mate, CoincidentMate)
    assert mate.flush is True  # default
    assert mate_instance_ids(mate) == (INST_A, INST_B)


def test_concentric_mate_round_trips() -> None:
    mate = _MATE_ADAPTER.validate_python(
        {"type": "concentric", "a": _axis_ref(INST_A), "b": _axis_ref(INST_B)}
    )
    assert isinstance(mate, ConcentricMate)
    assert mate_instance_ids(mate) == (INST_A, INST_B)


def test_distance_mate_round_trips() -> None:
    mate = _MATE_ADAPTER.validate_python(
        {
            "type": "distance",
            "a": _face_ref(INST_A),
            "b": _face_ref(INST_B),
            "distance_mm": 12.5,
        }
    )
    assert isinstance(mate, DistanceMate)
    assert mate.distance_mm == 12.5


def test_angle_mate_round_trips() -> None:
    mate = _MATE_ADAPTER.validate_python(
        {
            "type": "angle",
            "a": _face_ref(INST_A),
            "b": _face_ref(INST_B),
            "angle_deg": 30.0,
        }
    )
    assert isinstance(mate, AngleMate)
    assert mate.angle_deg == 30.0


def test_lock_mate_round_trips() -> None:
    mate = _MATE_ADAPTER.validate_python(
        {
            "type": "lock",
            "a_instance_id": str(INST_A),
            "b_instance_id": str(INST_B),
        }
    )
    assert isinstance(mate, LockMate)
    assert mate_instance_ids(mate) == (INST_A, INST_B)


def test_concentric_mate_rejects_face_refs() -> None:
    #: concentric names AXES; a planar-face ref in an axis slot is malformed.
    with pytest.raises(ValidationError):
        _MATE_ADAPTER.validate_python(
            {"type": "concentric", "a": _face_ref(INST_A), "b": _face_ref(INST_B)}
        )


def test_unknown_mate_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _MATE_ADAPTER.validate_python(
            {"type": "weld", "a_instance_id": str(INST_A), "b_instance_id": str(INST_B)}
        )


def test_distance_mate_rejects_non_finite() -> None:
    with pytest.raises(ValidationError):
        _MATE_ADAPTER.validate_python(
            {
                "type": "distance",
                "a": _face_ref(INST_A),
                "b": _face_ref(INST_B),
                "distance_mm": float("inf"),
            }
        )


# --- CRUD DTOs --------------------------------------------------------------------


def test_instance_create_defaults_placement_and_grounded() -> None:
    request = InstanceCreate.model_validate(
        {
            "expected_version": 0,
            "ref_document_id": str(INST_A),
            "ref_document_kind": "part",
            "name": "Bracket <1>",
        }
    )
    assert request.placement == IDENTITY_PLACEMENT
    assert request.grounded is False


def test_instance_create_rejects_unknown_ref_kind() -> None:
    with pytest.raises(ValidationError):
        InstanceCreate.model_validate(
            {
                "expected_version": 0,
                "ref_document_id": str(INST_A),
                "ref_document_kind": "drawing",
                "name": "x",
            }
        )


# --- audit N4: the assembly deliverable says what it is ---------------------------


def _export_assembly_request(**over: object) -> ExportAssemblyRequest:
    return ExportAssemblyRequest.model_validate(
        {
            "assembly_id": "22222222-2222-2222-2222-222222222222",
            "version": 1,
            "instances": [],
            "format": "step",
            **over,
        }
    )


def test_assembly_export_filename_prefers_the_document_name() -> None:
    """`motor-mount-assembly.step` — the same slug rule the part/drawing use."""
    named = _export_assembly_request(name="Motor Mount Assembly")
    assert assembly_export_filename(named) == "motor-mount-assembly.step"


def test_unnamed_assembly_exports_do_not_overwrite_each_other() -> None:
    """The fallback is keyed to the assembly ID, not the constant `assembly.step`.

    The audit's concrete complaint: EVERY assembly downloaded as `assembly.step`,
    so exporting two silently overwrote the first in the browser's Downloads.
    """
    a = _export_assembly_request()
    b = _export_assembly_request(assembly_id="33333333-3333-3333-3333-333333333333")
    assert assembly_export_filename(a) == f"assembly-{a.assembly_id}.step"
    assert assembly_export_filename(a) != assembly_export_filename(b)


def test_assembly_export_root_name_falls_back_to_the_id() -> None:
    """The root PRODUCT is the assembly's name, or its id — never nothing."""
    named = _export_assembly_request(name="Motor Mount Assembly")
    assert assembly_export_root_name(named) == "Motor Mount Assembly"
    unnamed = _export_assembly_request()
    assert assembly_export_root_name(unnamed) == str(unnamed.assembly_id)


def test_evaluate_assembly_request_has_no_name_field() -> None:
    """Export-only, for the same reason the part export's name is: a name must
    never be an input to the SOLVE."""
    assert "name" not in EvaluateAssemblyRequest.model_fields
