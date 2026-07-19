"""py_kit.schemas.features — envelopes, refs, registry/upcast totality.

The worked example asserted here is docs/design/feature-tree.md §6 verbatim
(40 x 25 mm rectangle on XY, extruded 10 mm) — the same rows the documents
service round-trips in its own suite.
"""

import uuid
from typing import Any, Literal

import pytest
from py_kit.schemas.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    DraftFeature,
    ExtrudeFeature,
    Feature,
    FeatureCreate,
    FeatureRef,
    FeatureResult,
    FeatureSchemaError,
    FeatureTypeRegistry,
    FeatureUpdate,
    FilletFeature,
    ShellFeature,
    SketchFeature,
    SketchParamsV1,
    SolvedSketchData,
    UnknownFeatureVersionError,
    feature_references,
    iter_feature_refs,
)
from py_kit.schemas.sketch import SketchDefinition, SketchLine
from pydantic import BaseModel, TypeAdapter, ValidationError

SKETCH_ID = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000aa")

#: §6 worked example — sketch params, verbatim.
SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "construction": False,
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        },
        {
            "construction": False,
            "id": "e2",
            "kind": "line",
            "start": {"x": 40.0, "y": 0.0},
            "end": {"x": 40.0, "y": 25.0},
        },
        {
            "construction": False,
            "id": "e3",
            "kind": "line",
            "start": {"x": 40.0, "y": 25.0},
            "end": {"x": 0.0, "y": 25.0},
        },
        {
            "construction": False,
            "id": "e4",
            "kind": "line",
            "start": {"x": 0.0, "y": 25.0},
            "end": {"x": 0.0, "y": 0.0},
        },
    ],
    "constraints": [
        {
            "kind": "coincident",
            "a": {"entity": "e1", "point": "end"},
            "b": {"entity": "e2", "point": "start"},
        },
        {"kind": "horizontal", "entity": "e1"},
        {"kind": "vertical", "entity": "e2"},
        {
            "kind": "distance",
            "entity": "e1",
            "value_mm": 40.0,
            "expression": None,
            "name": None,
            "driving": True,
        },
        {
            "kind": "distance",
            "entity": "e2",
            "value_mm": 25.0,
            "expression": None,
            "name": None,
            "driving": True,
        },
    ],
}

#: §6 worked example — extrude params, verbatim (feature id substituted).
EXTRUDE_PARAMS: dict[str, Any] = {
    "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
    "distance_mm": 10.0,
    "operation": "add",
    "direction": "normal",
    # Additive multi-body "Merge result" flag (design multi-body.md §MB-0),
    # defaults True — a dumped envelope carries it, so the verbatim round-trip
    # must include it.
    "merge": True,
}

#: Fillet params — round the vertical (Z-parallel) edges at r=5 (the golden
#: selector; a geometric predicate, NOT topological naming — design §2.4).
FILLET_PARAMS: dict[str, Any] = {
    "edges": {"kind": "axis_parallel", "axis": "Z"},
    "radius_mm": 5.0,
}

FEATURE_ADAPTER: TypeAdapter[SketchFeature | ExtrudeFeature | FilletFeature] = (
    TypeAdapter(Feature)
)


# --- envelopes (§1.3) -------------------------------------------------------------


def test_worked_example_sketch_round_trips_verbatim() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS}
    )
    assert isinstance(envelope, SketchFeature)
    assert envelope.model_dump(mode="json") == {
        "type": "sketch",
        "version": 1,
        "params": SKETCH_PARAMS,
    }


def test_worked_example_extrude_round_trips_verbatim() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "extrude", "version": 1, "params": EXTRUDE_PARAMS}
    )
    assert isinstance(envelope, ExtrudeFeature)
    assert envelope.params.profile.feature_id == SKETCH_ID
    assert envelope.model_dump(mode="json") == {
        "type": "extrude",
        "version": 1,
        "params": EXTRUDE_PARAMS,
    }


def test_fillet_round_trips_and_selector_discriminates() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "fillet", "version": 1, "params": FILLET_PARAMS}
    )
    assert isinstance(envelope, FilletFeature)
    assert envelope.params.radius_mm == 5.0
    # EdgeSelector discriminates on ``kind``.
    assert envelope.params.edges.kind == "axis_parallel"
    assert envelope.model_dump(mode="json") == {
        "type": "fillet",
        "version": 1,
        "params": FILLET_PARAMS,
    }


def test_fillet_all_edges_selector_round_trips() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {
            "type": "fillet",
            "version": 1,
            "params": {"edges": {"kind": "all_edges"}, "radius_mm": 2.0},
        }
    )
    assert isinstance(envelope, FilletFeature)
    assert envelope.params.edges.kind == "all_edges"


def test_fillet_requires_positive_radius() -> None:
    bad = {**FILLET_PARAMS, "radius_mm": 0.0}
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python({"type": "fillet", "version": 1, "params": bad})


def test_fillet_unknown_edge_selector_rejected() -> None:
    bad = {"edges": {"kind": "teapot"}, "radius_mm": 5.0}
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python({"type": "fillet", "version": 1, "params": bad})


def test_fillet_has_no_feature_references() -> None:
    """Fillet operates on the implicit body chain (design §7.6) and selects
    edges geometrically (design §2.4): no FeatureRef, so no dependency edge —
    the self-check in feature_references() agrees with the schema walk."""
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "fillet", "version": 1, "params": FILLET_PARAMS}
    )
    assert feature_references(envelope) == ()
    assert list(iter_feature_refs(envelope)) == []


def test_legacy_kindless_datum_params_validate_as_offset() -> None:
    """Review 🟡 (sketch-on-face): the datum before-validator backward-compat
    contract (datum-planes §4/§7). A datum params blob persisted BEFORE the
    on_face variant carries no ``kind`` discriminator; DatumFeature injects
    ``kind: "offset"`` so it validates to a DatumOffsetParams IDENTICAL to the
    same blob with ``kind`` explicit — additive, no ``param_version`` bump, every
    legacy row unchanged."""
    legacy_params: dict[str, Any] = {"base": "XY", "offset_mm": 30.0, "flip": False}
    loaded = DatumFeature.model_validate(
        {"type": "datum", "version": 1, "params": legacy_params}  # NO kind
    )
    assert isinstance(loaded.params, DatumOffsetParams)
    assert loaded.params.kind == "offset"

    explicit = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "offset",
                "base": "XY",
                "offset_mm": 30.0,
                "flip": False,
            },
        }
    )
    # Byte-identical params both ways — the injected kind is the ONLY difference,
    # and it is the default, so the validated models are equal.
    assert loaded.params == explicit.params
    assert loaded.model_dump() == explicit.model_dump()

    # The registry read path (documents lazy-load) reaches the same model.
    via_registry = FEATURE_REGISTRY.load("datum", 1, legacy_params)
    assert via_registry.model_dump() == loaded.model_dump()


def _face_ref_payload(feature_id: uuid.UUID) -> dict[str, Any]:
    """A stage-1 planar-face SubshapeRef blob (the on_face/midplane side shape)."""
    return {
        "kind": "subshape",
        "feature_id": str(feature_id),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                "centroid": {"x": 0.0, "y": 0.0, "z": 10.0},
                "area_mm2": 1600.0,
            },
        },
    }


def test_offset_from_datum_references_its_base_datum() -> None:
    """Offset chaining (datum-planes §7): an ``offset_from`` datum surfaces its
    base FeatureRef as a `datum`-only slot — the rule that makes a self /
    forward / non-datum base a write-time 422 — and the generic walk finds the
    SAME ref, so the feature_references self-check stays balanced."""
    datum = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "offset_from",
                "base": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "offset_mm": 20.0,
                "flip": False,
            },
        }
    )
    assert isinstance(datum.params, DatumOffsetFromParams)
    (reference,) = feature_references(datum)
    assert reference.slot == "base"
    assert reference.ref.feature_id == SKETCH_ID
    assert reference.allowed_types == frozenset({"datum"})
    assert [ref.feature_id for ref in iter_feature_refs(datum)] == [SKETCH_ID]


def test_offset_params_still_reject_a_feature_ref_base() -> None:
    """Wire-compat guard: chaining is a SEPARATE kind, NOT a widened ``offset``
    base (the ts-client justification on DatumOffsetFromParams) — an ``offset``
    payload smuggling a FeatureRef base stays a validation error, so the
    existing offset shape (and its generated client type) is unchanged."""
    with pytest.raises(ValidationError):
        DatumFeature.model_validate(
            {
                "type": "datum",
                "version": 1,
                "params": {
                    "kind": "offset",
                    "base": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                    "offset_mm": 20.0,
                },
            }
        )


def test_midplane_slots_follow_each_side_kind() -> None:
    """Midplane sides (datum-planes §7a): an origin-plane side carries NO ref,
    a FeatureRef side is a `datum`-only slot, and a picked-face side is a
    body-affecting SubshapeRef slot (the on_face rule) — each side judged by
    its own kind, and the walk/self-check stays balanced."""
    mixed = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "midplane",
                "a": {"kind": "datum_plane", "plane": "XY"},
                "b": {"kind": "feature", "feature_id": str(SKETCH_ID)},
            },
        }
    )
    assert isinstance(mixed.params, DatumMidplaneParams)
    (reference,) = feature_references(mixed)
    assert reference.slot == "b"
    assert reference.allowed_types == frozenset({"datum"})

    other = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000ab")
    faces = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "midplane",
                "a": _face_ref_payload(SKETCH_ID),
                "b": _face_ref_payload(other),
            },
        }
    )
    references = feature_references(faces)
    assert [r.slot for r in references] == ["a", "b"]
    assert [r.ref.feature_id for r in references] == [SKETCH_ID, other]
    assert all(r.allowed_types == BODY_AFFECTING_FEATURE_TYPES for r in references)


def test_midplane_side_rejects_an_edge_subshape_ref() -> None:
    """Only PLANAR-FACE subshape refs are valid midplane sides: an EDGE ref
    (subshape_type 'edge') is a request-validation error, never a silent
    misread (the MidplaneSide union admits the face SubshapeRef only)."""
    edge_ref: dict[str, Any] = {
        "kind": "subshape",
        "feature_id": str(SKETCH_ID),
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
        DatumFeature.model_validate(
            {
                "type": "datum",
                "version": 1,
                "params": {
                    "kind": "midplane",
                    "a": {"kind": "datum_plane", "plane": "XY"},
                    "b": edge_ref,
                },
            }
        )


def test_picked_edge_fillet_materializes_edge_dependencies() -> None:
    """The topo-naming §10 wiring: a fillet with a PICKED edge selector surfaces
    each EdgeSubshapeRef as a dependency on a body-affecting feature (allowed
    types = BODY_AFFECTING_FEATURE_TYPES), and the generic walk finds the SAME
    refs so the feature_references self-check stays balanced. Predicate fillets
    still carry no ref (test_fillet_has_no_feature_references) — backward-compat."""
    ref_id = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000ed")
    fillet = FilletFeature.model_validate(
        {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": str(ref_id),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": {
                                    "curve": "line",
                                    "end_a": {"x": 0.0, "y": 0.0, "z": 10.0},
                                    "end_b": {"x": 40.0, "y": 0.0, "z": 10.0},
                                    "midpoint": {"x": 20.0, "y": 0.0, "z": 10.0},
                                    "length_mm": 40.0,
                                },
                            },
                        }
                    ],
                },
                "radius_mm": 5.0,
            },
        }
    )
    (reference,) = feature_references(fillet)
    assert reference.slot == "edges[0]"
    assert reference.ref.feature_id == ref_id
    assert reference.allowed_types == BODY_AFFECTING_FEATURE_TYPES
    # The generic walk finds exactly the same ref (self-check balanced).
    assert [r.feature_id for r in iter_feature_refs(fillet)] == [ref_id]


def _shell_with_faces(refs: list[dict[str, Any]]) -> ShellFeature:
    return ShellFeature.model_validate(
        {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": 2.0,
                "faces": {"kind": "faces", "refs": refs},
            },
        }
    )


def test_shell_face_refs_materialize_face_dependencies() -> None:
    """A shell's picked-face selector surfaces each face SubshapeRef as a
    dependency on a body-affecting feature (allowed types =
    BODY_AFFECTING_FEATURE_TYPES) — the SAME wiring as the on_face datum and the
    picked-edge fillet — and the generic walk finds the SAME refs so the
    feature_references self-check stays balanced."""
    ref_id = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000e5")
    shell = _shell_with_faces(
        [
            {
                "kind": "subshape",
                "feature_id": str(ref_id),
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": {
                        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "centroid": {"x": 20.0, "y": 12.5, "z": 10.0},
                        "area_mm2": 1000.0,
                    },
                },
            }
        ]
    )
    (reference,) = feature_references(shell)
    assert reference.slot == "faces[0]"
    assert reference.ref.feature_id == ref_id
    assert reference.allowed_types == BODY_AFFECTING_FEATURE_TYPES
    assert [r.feature_id for r in iter_feature_refs(shell)] == [ref_id]


def test_shell_empty_faces_is_sealed_hollow_with_no_references() -> None:
    """DESIGN DECISION: an empty picked-face list is a valid SEALED hollow, not a
    422 — so it carries NO ref, NO dependency edge (tree order is its only tie to
    the prior body-affecting feature), and the self-check stays balanced."""
    shell = _shell_with_faces([])
    assert feature_references(shell) == ()
    assert list(iter_feature_refs(shell)) == []


def _draft_with_faces(refs: list[dict[str, Any]]) -> DraftFeature:
    return DraftFeature.model_validate(
        {
            "type": "draft",
            "version": 1,
            "params": {
                "angle_deg": 5.0,
                "neutral_plane": {"base": "XY"},
                "faces": {"kind": "faces", "refs": refs},
            },
        }
    )


def test_draft_face_refs_materialize_face_dependencies() -> None:
    """A draft's picked-face selector surfaces each face SubshapeRef as a
    dependency on a body-affecting feature (allowed types =
    BODY_AFFECTING_FEATURE_TYPES) — the SAME wiring as shell / the on_face datum
    — and the generic walk finds the SAME refs so the feature_references
    self-check stays balanced."""
    ref_id = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000d5")
    draft = _draft_with_faces(
        [
            {
                "kind": "subshape",
                "feature_id": str(ref_id),
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": {
                        "normal": {"x": 1.0, "y": 0.0, "z": 0.0},
                        "centroid": {"x": 40.0, "y": 20.0, "z": 10.0},
                        "area_mm2": 800.0,
                    },
                },
            }
        ]
    )
    (reference,) = feature_references(draft)
    assert reference.slot == "faces[0]"
    assert reference.ref.feature_id == ref_id
    assert reference.allowed_types == BODY_AFFECTING_FEATURE_TYPES
    assert [r.feature_id for r in iter_feature_refs(draft)] == [ref_id]


def test_draft_neutral_plane_defaults_are_the_base_datum() -> None:
    """The v1 neutral plane needs only ``base``; ``offset_mm``/``flip`` default to
    a plane ON the origin datum (pull = its normal). The neutral plane carries NO
    reference (a principal datum, independent of topological naming), so a draft's
    only refs are its picked faces."""
    draft = _draft_with_faces([])
    assert draft.params.neutral_plane.base == "XY"
    assert draft.params.neutral_plane.offset_mm == 0.0
    assert draft.params.neutral_plane.flip is False
    # empty faces carries no ref — the self-check stays balanced.
    assert feature_references(draft) == ()
    assert list(iter_feature_refs(draft)) == []


def test_unknown_feature_type_rejected() -> None:
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python(
            {"type": "no_such_feature_type", "version": 1, "params": {}}
        )


def test_extrude_requires_positive_distance() -> None:
    bad = {**EXTRUDE_PARAMS, "distance_mm": 0.0}
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python(
            {"type": "extrude", "version": 1, "params": bad}
        )


def test_extrude_direction_defaults_to_normal() -> None:
    params = {k: v for k, v in EXTRUDE_PARAMS.items() if k != "direction"}
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "extrude", "version": 1, "params": params}
    )
    assert isinstance(envelope, ExtrudeFeature)
    assert envelope.params.direction == "normal"


def test_geom_ref_discriminates_on_kind() -> None:
    params = SketchParamsV1.model_validate(
        {
            "plane": {"kind": "datum_plane", "plane": "XZ"},
            "entities": [],
            "constraints": [],
        }
    )
    assert isinstance(params.plane, DatumPlaneRef)
    with pytest.raises(ValidationError):
        SketchParamsV1.model_validate(
            {"plane": {"kind": "subshape"}, "entities": [], "constraints": []}
        )


def test_feature_update_requires_something_to_update() -> None:
    with pytest.raises(ValidationError):
        FeatureUpdate.model_validate({"expected_tree_version": 0})
    FeatureUpdate.model_validate({"expected_tree_version": 0, "name": "Sketch2"})


def test_feature_create_rejects_negative_expected_version() -> None:
    with pytest.raises(ValidationError):
        FeatureCreate.model_validate(
            {
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
                "expected_tree_version": -1,
            }
        )


# --- typed sketch params (§1.4 finalized by BACKLOG #3) -----------------------------


def test_sketch_params_are_typed_solver_input() -> None:
    """SketchParamsV1 extends SketchDefinition: persisted params ARE valid
    solver input, with fully-typed entities/constraints (no open JSON)."""
    params = SketchParamsV1.model_validate(SKETCH_PARAMS)
    assert isinstance(params, SketchDefinition)
    assert [type(entity) for entity in params.entities] == [SketchLine] * 4
    assert [constraint.kind for constraint in params.constraints] == [
        "coincident",
        "horizontal",
        "vertical",
        "distance",
        "distance",
    ]


@pytest.mark.parametrize(
    "corrupt",
    [
        {"entities": [{"id": "e9", "kind": "hexagon", "sides": 6}]},  # unknown kind
        {"constraints": [{"kind": "tangent", "entity": "e1"}]},  # unknown constraint
        {"constraints": [{"kind": "distance", "entity": "e1", "value_mm": -1.0}]},
    ],
    ids=["unknown-entity-kind", "unknown-constraint-kind", "negative-dimension"],
)
def test_malformed_sketch_bodies_rejected_at_validation(
    corrupt: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        SketchParamsV1.model_validate({**SKETCH_PARAMS, **corrupt})


def test_duplicate_entity_ids_rejected_in_sketch_params() -> None:
    """The SketchDefinition unique-id rule (design §2.4) applies to persisted
    params too — documents rejects the write, geometry the request."""
    bad = {**SKETCH_PARAMS, "entities": SKETCH_PARAMS["entities"] * 2}
    with pytest.raises(ValidationError, match="Duplicate sketch entity id"):
        SketchParamsV1.model_validate(bad)


def test_construction_defaults_false_on_pre_field_sketches() -> None:
    """Totality (design §1.4): a sketch persisted BEFORE the construction
    field — its entities lack the key — still loads through the registry and
    reads ``construction=False`` on every entity. ``construction`` is an
    additive optional field (design §1.3), so there is no ``param_version``
    bump: the upcast is the pydantic default and no stored sketch is
    unreadable."""
    pre_field: dict[str, Any] = {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 40.0, "y": 0.0},
            },
            {
                "id": "c1",
                "kind": "circle",
                "center": {"x": 0.0, "y": 0.0},
                "radius": 5.0,
            },
        ],
        "constraints": [],
    }
    loaded = FEATURE_REGISTRY.load("sketch", 1, pre_field)
    assert isinstance(loaded, SketchFeature)
    assert [entity.construction for entity in loaded.params.entities] == [False, False]
    # And the dump is canonical — the default is materialized on the wire.
    dumped = loaded.model_dump(mode="json")["params"]["entities"]
    assert all(entity["construction"] is False for entity in dumped)


def test_construction_flag_round_trips_when_set() -> None:
    """A construction entity survives validate → dump unchanged (the sketcher
    reads it back to render the centerline dashed/muted)."""
    marked = {**SKETCH_PARAMS["entities"][0], "construction": True}
    params = SketchParamsV1.model_validate(
        {**SKETCH_PARAMS, "entities": [marked, *SKETCH_PARAMS["entities"][1:]]}
    )
    assert params.entities[0].construction is True
    assert all(entity.construction is False for entity in params.entities[1:])
    assert params.model_dump(mode="json")["entities"][0]["construction"] is True


# --- FeatureResult.data union (§7.10, BACKLOG #3) ------------------------------------


def _solved_sketch_data() -> dict[str, Any]:
    return {
        "kind": "solved_sketch",
        "status": "converged",
        "entities": SKETCH_PARAMS["entities"],
        "dof": 0,
        "conflicting_constraints": [],
        "redundant_constraints": [],
        "dimensions": [],
        "diagnosis": None,
    }


def test_feature_result_data_round_trips() -> None:
    wire = {
        "feature_id": str(SKETCH_ID),
        "status": "ok",
        "error": None,
        "data": _solved_sketch_data(),
    }
    result = FeatureResult.model_validate(wire)
    assert isinstance(result.data, SolvedSketchData)
    assert result.data.kind == "solved_sketch"
    assert result.data.dof == 0
    assert result.model_dump(mode="json") == wire


def test_feature_result_data_defaults_to_none() -> None:
    """Additive: pre-#3 payloads (no ``data`` key) still validate."""
    result = FeatureResult.model_validate(
        {"feature_id": str(SKETCH_ID), "status": "skipped"}
    )
    assert result.data is None
    assert result.model_dump(mode="json")["data"] is None


def test_feature_result_data_kind_tag_is_enforced() -> None:
    """The union tag is load-bearing (future variants discriminate on it):
    a wrong ``kind`` is rejected, never silently coerced."""
    with pytest.raises(ValidationError):
        FeatureResult.model_validate(
            {
                "feature_id": str(SKETCH_ID),
                "status": "ok",
                "data": {**_solved_sketch_data(), "kind": "solved_extrude"},
            }
        )


# --- reference helpers (§2.2/§2.3) --------------------------------------------------


def _extrude() -> ExtrudeFeature:
    return ExtrudeFeature.model_validate(
        {"type": "extrude", "version": 1, "params": EXTRUDE_PARAMS}
    )


def _sketch() -> SketchFeature:
    return SketchFeature.model_validate(
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS}
    )


def test_extrude_profile_slot_accepts_sketches_only() -> None:
    (reference,) = feature_references(_extrude())
    assert reference.slot == "profile"
    assert reference.ref.feature_id == SKETCH_ID
    assert reference.allowed_types == frozenset({"sketch"})


def test_sketch_on_datum_plane_has_no_feature_refs() -> None:
    assert feature_references(_sketch()) == ()
    assert list(iter_feature_refs(_sketch())) == []


def test_sketch_plane_feature_ref_accepts_datum() -> None:
    # Offset/datum planes (Ready #2) widened the sketch-plane FeatureRef slot
    # from frozenset() (no referenceable plane feature in v1) to {"datum"}: a
    # sketch may now sit on a datum-plane feature. The design review confirmed
    # this is the sole reference-graph change (walker/self-check stay balanced).
    sketch = SketchFeature.model_validate(
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "entities": [],
                "constraints": [],
            },
        }
    )
    (reference,) = feature_references(sketch)
    assert reference.slot == "plane"
    assert reference.allowed_types == frozenset({"datum"})


def test_slot_map_drift_fails_loudly() -> None:
    """A ref the generic walk finds but the slot map misses must raise, never
    silently drop a dependency edge (self-check in feature_references)."""
    smuggled = SketchParamsV1.model_construct(
        plane=DatumPlaneRef(kind="datum_plane", plane="XY"),
        entities=[FeatureRef(kind="feature", feature_id=SKETCH_ID)],  # pyright: ignore[reportArgumentType]
        constraints=[],
    )
    sketch = SketchFeature.model_construct(type="sketch", version=1, params=smuggled)
    with pytest.raises(FeatureSchemaError, match="out of sync"):
        feature_references(sketch)


# --- registry + upcasts (§1.4) ------------------------------------------------------


class _WidgetParamsV2(BaseModel):
    size: int
    color: str


class _WidgetV2(BaseModel):
    type: Literal["widget"]
    version: Literal[2]
    params: _WidgetParamsV2


def test_module_registry_serves_current_versions() -> None:
    assert FEATURE_REGISTRY.current_version("sketch") == 1
    assert FEATURE_REGISTRY.current_version("extrude") == 1
    assert FEATURE_REGISTRY.current_version("fillet") == 1
    loaded = FEATURE_REGISTRY.load("extrude", 1, EXTRUDE_PARAMS)
    assert isinstance(loaded, ExtrudeFeature)
    with pytest.raises(UnknownFeatureVersionError):
        FEATURE_REGISTRY.current_version("no_such_feature_type")


def test_upcast_chain_reaches_current_version() -> None:
    """The documented path (design §1.4): a v1 row lazily upcast on read,
    the new required field filled from the old version's implicit behavior."""
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.register_upcast("widget", 1, lambda params: {**params, "color": "gray"})
    registry.validate_chains()

    loaded = registry.load("widget", 1, {"size": 3})
    assert loaded.version == 2
    assert loaded.params == _WidgetParamsV2(size=3, color="gray")
    # Current-version rows pass through untouched.
    assert registry.load("widget", 2, {"size": 1, "color": "red"}).params.color == "red"


def test_chain_gaps_are_rejected_at_validate_time() -> None:
    """Totality enforcement: a registered chain with a hole cannot import."""

    class _GadgetV3(BaseModel):
        type: Literal["gadget"]
        version: Literal[3]
        params: _WidgetParamsV2

    registry: FeatureTypeRegistry[_GadgetV3] = FeatureTypeRegistry()
    registry.register(_GadgetV3)
    registry.register_upcast(
        "gadget", 1, lambda params: params
    )  # 1→2 only; 2→3 missing
    with pytest.raises(FeatureSchemaError, match="gaps"):
        registry.validate_chains()


def test_upcast_beyond_current_version_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.register_upcast("widget", 2, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="beyond"):
        registry.validate_chains()


def test_upcast_for_unregistered_type_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register_upcast("widget", 1, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="unregistered"):
        registry.validate_chains()


def test_missing_upcast_link_fails_at_load() -> None:
    """A stored version with no registered path to current raises — the row
    is unloadable and must fail loudly, never guess."""
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.validate_chains()
    with pytest.raises(UnknownFeatureVersionError, match="no upcast"):
        registry.load("widget", 1, {"size": 3})


def test_params_newer_than_current_fail_at_load() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    with pytest.raises(UnknownFeatureVersionError, match="NEWER"):
        registry.load("widget", 3, {"size": 3})


def test_duplicate_registrations_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    with pytest.raises(FeatureSchemaError, match="twice"):
        registry.register(_WidgetV2)
    registry.register_upcast("widget", 1, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="twice"):
        registry.register_upcast("widget", 1, lambda params: params)
