"""Per-request work-bound reject tests (engineering audit 2026-07-24 G2).

The rate limiter caps request FREQUENCY; the bounds under test cap the WORK a
single compute request can demand. Every bound is a documented constant on the
schema (contract-visible) and rejects at PARSE time — a pydantic
``ValidationError`` here, the py-kit 422 envelope over HTTP (the
``RequestValidationError`` handler in :mod:`py_kit.errors`) — never a kernel
blow-up or a 500. Each ceiling test pairs a just-over-bound reject with an
at-bound accept so the constants stay exact, and the under-bound behaviour is
covered by every existing suite (the goldens define legitimate usage).
"""

import uuid
from typing import Any

import pytest
from py_kit.schemas.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    MAX_ASSEMBLY_MATES,
    MAX_INTERFERENCE_INSTANCES,
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    EvaluatedMate,
    LockMate,
)
from py_kit.schemas.features import (
    MAX_LOFT_SECTIONS,
    MAX_PATTERN_COUNT,
    MAX_SELECTOR_REFS,
    MAX_TREE_FEATURES,
    CircularPatternParamsV1,
    LinearPatternParamsV1,
    LoftParamsV1,
)
from py_kit.schemas.geometry import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
    MIN_ANGULAR_DEFLECTION,
    MIN_LINEAR_DEFLECTION,
    ExportRequest,
    TessellateRequest,
    Vec3,
)
from py_kit.schemas.sketch import (
    MAX_SKETCH_CONSTRAINTS,
    MAX_SKETCH_ENTITIES,
    MAX_SPLINE_POINTS,
    SketchDefinition,
    SketchEditRequest,
    SketchSpline,
)
from py_kit.schemas.step_import import (
    MAX_IMPORT_ASSEMBLY_PRODUCTS,
    StepAssemblyImportRequest,
)
from pydantic import ValidationError

BOX: dict[str, Any] = {"shape": "box", "params": {"x": 1.0, "y": 1.0, "z": 1.0}}


# --- deflection floors ------------------------------------------------------------


def test_tessellate_linear_deflection_below_floor_rejected() -> None:
    with pytest.raises(ValidationError):
        TessellateRequest.model_validate(
            {**BOX, "linear_deflection": MIN_LINEAR_DEFLECTION / 10.0}
        )


def test_tessellate_linear_deflection_at_floor_accepted() -> None:
    request = TessellateRequest.model_validate(
        {**BOX, "linear_deflection": MIN_LINEAR_DEFLECTION}
    )
    assert request.linear_deflection == MIN_LINEAR_DEFLECTION


def test_export_deflections_below_floor_rejected() -> None:
    with pytest.raises(ValidationError):
        ExportRequest.model_validate(
            {**BOX, "format": "stl", "linear_deflection": 1e-9}
        )
    with pytest.raises(ValidationError):
        ExportRequest.model_validate(
            {**BOX, "format": "stl", "angular_deflection": MIN_ANGULAR_DEFLECTION / 10}
        )


def test_default_deflections_sit_above_their_floors() -> None:
    # The floors must never collide with the documented defaults.
    assert DEFAULT_LINEAR_DEFLECTION >= MIN_LINEAR_DEFLECTION
    assert DEFAULT_ANGULAR_DEFLECTION >= MIN_ANGULAR_DEFLECTION


def test_step_import_deflection_below_floor_rejected() -> None:
    with pytest.raises(ValidationError):
        StepAssemblyImportRequest(data="ISO-10303-21;", linear_deflection=1e-9)


# --- pattern count ceiling --------------------------------------------------------


def test_linear_pattern_count_over_ceiling_rejected() -> None:
    with pytest.raises(ValidationError):
        LinearPatternParamsV1(
            direction=Vec3(x=1.0, y=0.0, z=0.0),
            spacing_mm=10.0,
            count=MAX_PATTERN_COUNT + 1,
        )


def test_linear_pattern_count_at_ceiling_accepted() -> None:
    params = LinearPatternParamsV1(
        direction=Vec3(x=1.0, y=0.0, z=0.0),
        spacing_mm=10.0,
        count=MAX_PATTERN_COUNT,
    )
    assert params.count == MAX_PATTERN_COUNT


def test_circular_pattern_count_over_ceiling_rejected() -> None:
    with pytest.raises(ValidationError):
        CircularPatternParamsV1(
            axis_point=Vec3(x=0.0, y=0.0, z=0.0),
            axis_direction=Vec3(x=0.0, y=0.0, z=1.0),
            angle_deg=360.0,
            count=MAX_PATTERN_COUNT + 1,
        )


def test_pattern_count_below_one_still_parses() -> None:
    # The LOWER bound deliberately stays a rebuild-time `pattern_bad_count`
    # (the module's cross-field-validation design note); only the DoS ceiling
    # is parse-time. count=0 must keep parsing so that contract holds.
    params = LinearPatternParamsV1(
        direction=Vec3(x=1.0, y=0.0, z=0.0), spacing_mm=10.0, count=0
    )
    assert params.count == 0


# --- feature-tree list ceiling ----------------------------------------------------


def _tree_payload(feature_count: int) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [],
                "constraints": [],
            },
        },
    }
    return {
        "part_id": str(uuid.uuid4()),
        "tree_version": 1,
        "features": [feature] * feature_count,
    }


def test_evaluate_tree_features_over_ceiling_rejected() -> None:
    from py_kit.schemas.features import EvaluateTreeRequest

    with pytest.raises(ValidationError):
        EvaluateTreeRequest.model_validate(_tree_payload(MAX_TREE_FEATURES + 1))


def test_evaluate_tree_features_at_ceiling_accepted() -> None:
    from py_kit.schemas.features import EvaluateTreeRequest

    request = EvaluateTreeRequest.model_validate(_tree_payload(MAX_TREE_FEATURES))
    assert len(request.features) == MAX_TREE_FEATURES


# --- loft / selector ceilings -----------------------------------------------------


def test_loft_profiles_over_ceiling_rejected() -> None:
    profiles = [
        {"kind": "feature", "feature_id": str(uuid.uuid4())}
        for _ in range(MAX_LOFT_SECTIONS + 1)
    ]
    with pytest.raises(ValidationError):
        LoftParamsV1.model_validate({"profiles": profiles, "operation": "add"})


def test_edge_selector_refs_over_ceiling_rejected() -> None:
    from py_kit.schemas.features import PickedEdgesSelector

    ref = {
        "kind": "subshape",
        "feature_id": str(uuid.uuid4()),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "curve": "line",
                "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
                "end_b": {"x": 1.0, "y": 0.0, "z": 0.0},
                "midpoint": {"x": 0.5, "y": 0.0, "z": 0.0},
                "length_mm": 1.0,
            },
        },
    }
    with pytest.raises(ValidationError):
        PickedEdgesSelector.model_validate(
            {"kind": "edges", "refs": [ref] * (MAX_SELECTOR_REFS + 1)}
        )


# --- sketch ceilings --------------------------------------------------------------


def _point_entity(index: int) -> dict[str, Any]:
    return {
        "id": f"e{index}",
        "kind": "point",
        "position": {"x": float(index), "y": 0.0},
    }


def test_sketch_entities_over_ceiling_rejected() -> None:
    entities = [_point_entity(i) for i in range(MAX_SKETCH_ENTITIES + 1)]
    with pytest.raises(ValidationError):
        SketchDefinition.model_validate({"entities": entities, "constraints": []})


def test_sketch_constraints_over_ceiling_rejected() -> None:
    constraint = {"kind": "fixed", "point": {"entity": "e0", "point": "position"}}
    with pytest.raises(ValidationError):
        SketchDefinition.model_validate(
            {
                "entities": [_point_entity(0)],
                "constraints": [constraint] * (MAX_SKETCH_CONSTRAINTS + 1),
            }
        )


def test_sketch_edit_request_entities_over_ceiling_rejected() -> None:
    entities = [_point_entity(i) for i in range(MAX_SKETCH_ENTITIES + 1)]
    with pytest.raises(ValidationError):
        SketchEditRequest.model_validate(
            {"entities": entities, "target": "e0", "pick": {"x": 0.0, "y": 0.0}}
        )


def test_spline_points_over_ceiling_rejected() -> None:
    points = [{"x": float(i), "y": 0.0} for i in range(MAX_SPLINE_POINTS + 1)]
    with pytest.raises(ValidationError):
        SketchSpline.model_validate({"id": "s1", "kind": "spline", "points": points})


# --- assembly ceilings ------------------------------------------------------------


def _instance() -> EvaluatedInstance:
    return EvaluatedInstance(instance_id=uuid.uuid4(), part_key="p@tip", features=[])


def test_assembly_instances_over_ceiling_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluateAssemblyRequest(
            assembly_id=uuid.uuid4(),
            version=1,
            instances=[_instance() for _ in range(MAX_ASSEMBLY_INSTANCES + 1)],
        )


def test_assembly_mates_over_ceiling_rejected() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    mate = EvaluatedMate(
        mate_id=uuid.uuid4(),
        order_index=0,
        mate=LockMate(type="lock", a_instance_id=a, b_instance_id=b),
    )
    with pytest.raises(ValidationError):
        EvaluateAssemblyRequest(
            assembly_id=uuid.uuid4(),
            version=1,
            instances=[_instance(), _instance()],
            mates=[mate] * (MAX_ASSEMBLY_MATES + 1),
        )


def test_interference_cap_is_tighter_than_the_parse_cap() -> None:
    # The route-level interference ceiling must stay BELOW the field-level
    # instance ceiling, or the handler check would be dead code.
    assert MAX_INTERFERENCE_INSTANCES < MAX_ASSEMBLY_INSTANCES


def test_import_products_cap_tied_to_assembly_instances_cap() -> None:
    # An import may never create more instances than one assembly compute
    # request accepts (the audit-G2 tie); drift here re-opens the gap.
    assert MAX_IMPORT_ASSEMBLY_PRODUCTS == MAX_ASSEMBLY_INSTANCES


# --- drawing ceilings -------------------------------------------------------------


def _drawing_payload(views: int) -> dict[str, Any]:
    return {
        "part_id": str(uuid.uuid4()),
        "tree_version": 1,
        "features": [],
        "views": ["front"] * views,
    }


def test_drawing_views_over_ceiling_rejected() -> None:
    from py_kit.schemas.drawings import MAX_DRAWING_VIEWS, EvaluateDrawingViewsRequest

    with pytest.raises(ValidationError):
        EvaluateDrawingViewsRequest.model_validate(
            _drawing_payload(MAX_DRAWING_VIEWS + 1)
        )


def test_drawing_dimensions_over_ceiling_rejected() -> None:
    from py_kit.schemas.drawings import (
        MAX_DRAWING_DIMENSIONS,
        EvaluateDrawingViewsRequest,
    )

    dimension = {
        "view": "front",
        "dimension": {
            "type": "linear",
            "measurement": {
                "mode": "edge_length",
                "edge": {
                    "curve": "line",
                    "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "end_b": {"x": 1.0, "y": 0.0, "z": 0.0},
                    "midpoint": {"x": 0.5, "y": 0.0, "z": 0.0},
                    "length_mm": 1.0,
                },
            },
            "placement": {"offset_mm": 10.0},
        },
    }
    payload = _drawing_payload(1)
    payload["dimensions"] = [dimension] * (MAX_DRAWING_DIMENSIONS + 1)
    with pytest.raises(ValidationError):
        EvaluateDrawingViewsRequest.model_validate(payload)
