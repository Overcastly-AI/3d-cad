"""Sketch schema helpers — the typed over-constraint diagnosis (BACKLOG #6).

Covers :func:`loft_wire.sketch.classify_overconstraint`: a pure function
that turns the solver's already-computed ``conflicting``/``redundant`` sets
(:class:`SolvedSketch`) into a typed :class:`SketchConstraintDiagnosis` — the
structured shape a caller reads BY FIELD instead of parsing a message string.
This is the backend classification building block; wiring it onto the
``sketch_conflicting`` ``FeatureError`` and the solved-sketch payload (plus the
sketcher UI reading the typed field) is the follow-up leg.
"""

import pytest
from loft_wire.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    SketchFeature,
    SketchProjectionStatus,
    SolvedSketchData,
    feature_references,
)
from loft_wire.sketch import (
    EntityPointRef,
    PointDistanceConstraint,
    SketchConstraintDiagnosis,
    SketchDefinition,
    SolvedSketch,
    classify_overconstraint,
    spline_fit_index,
)
from pydantic import ValidationError


def _solved(
    status: str, *, conflicting: list[int], redundant: list[int]
) -> SolvedSketch:
    """A minimal SolvedSketch with the diagnosis fields set (entities empty)."""
    return SolvedSketch(
        status=status,  # pyright: ignore[reportArgumentType]
        entities=[],
        conflicting_constraints=conflicting,
        redundant_constraints=redundant,
    )


def test_conflicting_is_classified_unsolvable_with_named_ids() -> None:
    diag = classify_overconstraint(
        _solved("conflicting", conflicting=[2, 5], redundant=[])
    )
    assert isinstance(diag, SketchConstraintDiagnosis)
    assert diag.classification == "conflicting"
    assert diag.removable is False  # no solution until one is relaxed
    assert diag.conflicting_constraints == [2, 5]
    assert diag.suggested_fix is not None
    assert "2" in diag.suggested_fix  # names the first offending constraint


def test_overconstrained_is_classified_redundant_and_removable() -> None:
    diag = classify_overconstraint(
        _solved("overconstrained", conflicting=[], redundant=[3])
    )
    assert isinstance(diag, SketchConstraintDiagnosis)
    assert diag.classification == "redundant"
    assert diag.removable is True  # still solves once dropped
    assert diag.redundant_constraints == [3]
    assert diag.conflicting_constraints == []
    assert diag.suggested_fix == "Remove constraint 3"


def test_conflicting_carries_any_redundant_ids_planegcs_also_reported() -> None:
    diag = classify_overconstraint(
        _solved("conflicting", conflicting=[1], redundant=[4])
    )
    assert diag is not None
    assert diag.classification == "conflicting"
    assert diag.conflicting_constraints == [1]
    assert diag.redundant_constraints == [4]  # surfaced, but conflict dominates


def test_solved_statuses_have_no_overconstraint_diagnosis() -> None:
    """converged / underconstrained / diverged are not over-constraints → None."""
    for status in ("converged", "underconstrained", "diverged"):
        assert (
            classify_overconstraint(_solved(status, conflicting=[], redundant=[]))
            is None
        )


# --- fit-point references on EntityPointRef (constrainable splines v1.1) ----


def test_entity_point_ref_accepts_fixed_named_points() -> None:
    """The pre-spline point names are unchanged — additive extension, no
    regression to existing line/arc/circle/point references."""
    for name in ("start", "end", "center", "position"):
        assert EntityPointRef(entity="e1", point=name).point == name


def test_entity_point_ref_accepts_spline_fit_points() -> None:
    """A constraint addresses a spline's Nth fit point as ``"fitN"`` (zero-based,
    arbitrary index — the count is bounds-checked by the solver, not the field)."""
    for name in ("fit0", "fit1", "fit12", "fit100"):
        assert EntityPointRef(entity="e1", point=name).point == name


def test_entity_point_ref_rejects_malformed_point_names() -> None:
    """Neither a fixed name nor a well-formed ``"fitN"`` → a validation error
    (leading-zero forms are rejected so a fit index is canonical)."""
    for bad in ("fit", "fitx", "fit00", "fit01", "middle", ""):
        with pytest.raises(ValidationError):
            EntityPointRef(entity="e1", point=bad)


def test_spline_fit_index_decodes_only_fit_names() -> None:
    """``spline_fit_index`` returns the index for a fit name and None for a fixed
    named point — the discriminator the solver uses to decide which references
    target a spline fit point."""
    assert spline_fit_index("fit0") == 0
    assert spline_fit_index("fit7") == 7
    for named in ("start", "end", "center", "position"):
        assert spline_fit_index(named) is None


# --- SKETCH-POINT-DISTANCE ------------------------------------------------------


def test_point_dimensions_parse_and_round_trip() -> None:
    raw = {
        "entities": [],
        "constraints": [
            {
                "kind": "point_distance",
                "a": {"entity": "e1", "point": "start"},
                "b": {"entity": "e2", "point": "end", "sharp": "e3"},
                "direction": "horizontal",
                "value_mm": 12.5,
            },
            {
                "kind": "point_line_distance",
                "point": {"entity": "e4", "point": "position"},
                "line": "e1",
                "value_mm": 1.0,
                "name": "inset",
            },
        ],
    }
    sketch = SketchDefinition.model_validate(raw)
    again = SketchDefinition.model_validate_json(sketch.model_dump_json())
    assert again == sketch
    dumped = sketch.model_dump(mode="json")
    # An operand without a sharp dumps exactly as a plain EntityPointRef does.
    assert dumped["constraints"][0]["a"] == {"entity": "e1", "point": "start"}
    assert dumped["constraints"][0]["b"]["sharp"] == "e3"
    assert dumped["constraints"][1]["point"] == {"entity": "e4", "point": "position"}


def test_a_point_distance_defaults_to_aligned() -> None:
    dim = PointDistanceConstraint.model_validate(
        {
            "kind": "point_distance",
            "a": {"entity": "e1", "point": "start"},
            "b": {"entity": "e1", "point": "end"},
            "value_mm": 3,
        }
    )
    assert dim.direction == "aligned"


def test_old_sketches_dump_byte_identically() -> None:
    """The change is additive: a stored sketch without the new kinds is untouched."""
    stored = (
        '{"entities":[{"id":"e1","construction":false,"kind":"line",'
        '"start":{"x":0.0,"y":0.0},"end":{"x":10.0,"y":0.0}}],'
        '"constraints":[{"expression":null,"name":null,"driving":null,'
        '"value_mm":10.0,"kind":"distance","entity":"e1"},'
        '{"kind":"fixed","point":{"entity":"e1","point":"start"}},'
        '{"kind":"coincident","a":{"entity":"e1","point":"end"},'
        '"b":{"entity":"e1","point":"start"}}]}'
    )
    assert SketchDefinition.model_validate_json(stored).model_dump_json() == stored


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            {
                "kind": "point_distance",
                "a": {"entity": "e1", "point": "start"},
                "b": {"entity": "e1", "point": "start"},
                "value_mm": 1,
            },
            "two different points",
        ),
        (
            {
                "kind": "point_line_distance",
                "point": {"entity": "e1", "point": "end"},
                "line": "e1",
                "value_mm": 1,
            },
            "always on the line",
        ),
        (
            {
                "kind": "point_line_distance",
                "point": {"entity": "e2", "point": "end", "sharp": "e1"},
                "line": "e1",
                "value_mm": 1,
            },
            "always on the line",
        ),
        (
            {
                "kind": "point_line_distance",
                "point": {"entity": "e2", "point": "end", "sharp": "e2"},
                "line": "e1",
                "value_mm": 1,
            },
            "TWO different lines",
        ),
        (
            {
                "kind": "point_line_distance",
                "point": {"entity": "e2", "point": "center", "sharp": "e3"},
                "line": "e1",
                "value_mm": 1,
            },
            "start or end",
        ),
        (
            {
                "kind": "point_distance",
                "a": {"entity": "e1", "point": "start"},
                "b": {"entity": "e2", "point": "start"},
                "direction": "diagonal",
                "value_mm": 1,
            },
            "direction",
        ),
        (
            {
                "kind": "point_line_distance",
                "point": {"entity": "e2", "point": "start"},
                "line": "e1",
                "value_mm": 0,
            },
            "greater than 0",
        ),
    ],
)
def test_malformed_point_dimensions_are_refused(
    raw: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        SketchDefinition.model_validate({"entities": [], "constraints": [raw]})


# --- SKETCH-PROJECT-EDGES: a projected entity's link ------------------------------

_EDGE_ANCHOR = "00000000-0000-4000-8000-0000000000ed"


def _projection() -> dict[str, object]:
    point = {"x": 0.0, "y": 0.0, "z": 5.0}
    return {
        "edge": {
            "kind": "subshape",
            "feature_id": _EDGE_ANCHOR,
            "subshape_type": "edge",
            "selector": {
                "selector_version": 1,
                "signature": {
                    "subshape_type": "edge",
                    "curve": "line",
                    "end_a": point,
                    "end_b": {"x": 120.0, "y": 0.0, "z": 5.0},
                    "midpoint": {"x": 60.0, "y": 0.0, "z": 5.0},
                    "length_mm": 120.0,
                    "adjacent_faces": None,
                    "topo_name": None,
                    "end_a_topo_name": None,
                },
            },
        }
    }


def _projected_sketch() -> dict[str, object]:
    origin, far = {"x": 0.0, "y": 0.0}, {"x": 120.0, "y": 0.0}
    return {
        "entities": [
            {
                "id": "p1",
                "construction": False,
                "projection": _projection(),
                "kind": "line",
                "start": origin,
                "end": far,
            },
            {
                "id": "p2",
                "construction": False,
                "projection": _projection(),
                "kind": "arc",
                "center": origin,
                "start": far,
                "end": {"x": 0.0, "y": 120.0},
            },
            {
                "id": "p3",
                "construction": True,
                "projection": _projection(),
                "kind": "circle",
                "center": origin,
                "radius": 3.0,
            },
        ],
        "constraints": [],
    }


def test_a_projection_round_trips() -> None:
    raw = _projected_sketch()
    sketch = SketchDefinition.model_validate(raw)
    assert sketch.model_dump(mode="json") == raw
    assert SketchDefinition.model_validate_json(sketch.model_dump_json()) == sketch
    line = sketch.entities[0]
    assert line.projection is not None
    assert str(line.projection.edge.feature_id) == _EDGE_ANCHOR


def test_a_sketch_without_projections_dumps_byte_identically() -> None:
    """The link is omitted when absent, so stored sketches and the rebuild cache
    keys built from them do not change by a byte."""
    stored = (
        '{"entities":[{"id":"a","construction":false,"kind":"arc",'
        '"center":{"x":0.0,"y":0.0},"start":{"x":1.0,"y":0.0},'
        '"end":{"x":0.0,"y":1.0}},{"id":"c","construction":true,"kind":"circle",'
        '"center":{"x":0.0,"y":0.0},"radius":2.0},{"id":"p","construction":false,'
        '"kind":"point","position":{"x":3.0,"y":4.0}},{"id":"s",'
        '"construction":false,"kind":"spline","points":[{"x":0.0,"y":0.0},'
        '{"x":1.0,"y":1.0}]}],"constraints":[]}'
    )
    assert SketchDefinition.model_validate_json(stored).model_dump_json() == stored


@pytest.mark.parametrize(
    "entity",
    [
        {"id": "q", "kind": "point", "position": {"x": 0.0, "y": 0.0}},
        {
            "id": "s",
            "kind": "spline",
            "points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
        },
    ],
    ids=["point", "spline"],
)
def test_only_a_line_arc_or_circle_can_be_projected(entity: dict[str, object]) -> None:
    linked = {**entity, "projection": _projection()}
    with pytest.raises(ValidationError, match="line, an arc or a circle"):
        SketchDefinition.model_validate({"entities": [linked], "constraints": []})


def test_feature_references_lists_each_projection_slot() -> None:
    """Each link is a dependency on the anchor body feature: deleting it is a
    409, and a reorder re-checks that it is strictly backward."""
    feature = SketchFeature.model_validate(
        {
            "type": "sketch",
            "version": 1,
            "params": {
                **_projected_sketch(),
                "plane": {"kind": "datum_plane", "plane": "XY"},
            },
        }
    )
    references = feature_references(feature)
    assert [r.slot for r in references] == [
        "projection:p1",
        "projection:p2",
        "projection:p3",
    ]
    assert {str(r.ref.feature_id) for r in references} == {_EDGE_ANCHOR}
    assert all(r.allowed_types == BODY_AFFECTING_FEATURE_TYPES for r in references)


def test_solved_sketch_data_projections_default_empty() -> None:
    data = SolvedSketchData(status="converged", entities=[])
    assert data.projections == []
    status = SketchProjectionStatus(entity="p1", state="sick", reason="no_body")
    assert status.tier is None
