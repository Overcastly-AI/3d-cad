"""Feature formulas: the envelope field and their resolution (RESEARCH §20).

:mod:`loft_wire.feature_expressions` (the ``expressions`` field and its
pointer check) and :mod:`loft_wire.feature_resolve` (evaluation against a
part's parameters, the geometry form, renames), plus the parameter-aware
:func:`loft_wire.expr.evaluate_driving_dimensions` and
:func:`loft_wire.expr.rename_references`.
"""

from typing import Any

import pytest
from loft_wire.expr import (
    ExpressionUnitError,
    Quantity,
    evaluate_driving_dimensions,
    rename_references,
)
from loft_wire.feature_resolve import (
    FeatureExpressionError,
    check_dimension_names,
    evaluation_input,
    for_geometry,
    normalize,
    parameter_references,
    parameter_values,
    rename_parameters,
    resolve_feature,
)
from loft_wire.features import (
    FEATURE_REGISTRY,
    EvaluatedFeatureInput,
    FeatureEnvelope,
)
from pydantic import ValidationError

SKETCH_ID = "00000000-0000-0000-0000-0000000001b1"
TABLE = {
    "D": Quantity(25.0, "length"),
    "W": Quantity(40.0, "length"),
    "A": Quantity(30.0, "angle"),
    "N": Quantity(3.0, "unitless"),
}


def _p(envelope: FeatureEnvelope) -> dict[str, Any]:
    """An envelope's params as JSON (the union of params types reads untyped)."""
    params: dict[str, Any] = envelope.params.model_dump(mode="json")
    return params


def _constraints(sketch: FeatureEnvelope) -> list[object]:
    constraints: list[object] = getattr(sketch.params, "constraints")  # noqa: B009
    return constraints


def _extrude(
    expressions: dict[str, str] | None = None, **params: Any
) -> FeatureEnvelope:
    return FEATURE_REGISTRY.load(
        "extrude",
        1,
        {
            "profile": {"kind": "feature", "feature_id": SKETCH_ID},
            "distance_mm": 10.0,
            "operation": "add",
            "direction": "normal",
            **params,
        },
        expressions=expressions,
    )


def _sketch(*constraints: dict[str, Any]) -> FeatureEnvelope:
    return FEATURE_REGISTRY.load(
        "sketch",
        1,
        {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "id": "e1",
                    "kind": "line",
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 10, "y": 0},
                },
                {
                    "id": "e2",
                    "kind": "line",
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 0, "y": 10},
                },
            ],
            "constraints": list(constraints),
        },
    )


def _dim(entity: str, value: float, expression: str | None = None, **kw: Any) -> Any:
    return {
        "kind": "distance",
        "entity": entity,
        "value_mm": value,
        "expression": expression,
        **kw,
    }


# --- the field --------------------------------------------------------------------


def test_no_expressions_leaves_the_dump_byte_identical() -> None:
    plain = _extrude()
    assert "expressions" not in plain.model_dump_json()
    assert _extrude({}).expressions is None
    assert _extrude({}).model_dump_json() == plain.model_dump_json()


@pytest.mark.parametrize(
    "pointer",
    [
        "distance_mm",  # not a pointer
        "/nope",  # no such field
        "/operation",  # a string
        "/merge",  # a bool
        "/profile",  # an object
        "/profile/feature_id",  # a string
        "/distance_mm/0",  # below a number
    ],
)
def test_a_pointer_must_hit_an_int_or_float_leaf(pointer: str) -> None:
    with pytest.raises(ValidationError):
        _extrude({pointer: "D"})


def test_list_pointers_are_checked_like_rfc_6901() -> None:
    sketch = _sketch(_dim("e1", 10.0))
    data = sketch.model_dump(mode="json")
    for pointer in ("/constraints/0/value_mm", "/entities/1/end/y"):
        type(sketch).model_validate({**data, "expressions": {pointer: "D"}})
    for pointer in ("/constraints/1/value_mm", "/constraints/00/value_mm"):
        with pytest.raises(ValidationError):
            type(sketch).model_validate({**data, "expressions": {pointer: "D"}})


def test_the_field_is_bounded() -> None:
    with pytest.raises(ValidationError):
        _extrude({"/distance_mm": "1" * 257})
    with pytest.raises(ValidationError):
        _extrude({"/distance_mm": ""})


# --- resolution -------------------------------------------------------------------


def test_a_resolved_number_lands_at_its_pointer_and_the_formula_stays() -> None:
    resolved = resolve_feature(_extrude({"/distance_mm": "D * 2 + 1 cm"}), TABLE)
    assert _p(resolved)["distance_mm"] == 60.0
    assert resolved.expressions == {"/distance_mm": "D * 2 + 1 cm"}


def test_a_feature_without_formulas_is_the_same_object() -> None:
    plain = _extrude()
    assert resolve_feature(plain, TABLE) is plain
    assert for_geometry(plain) is plain
    assert evaluation_input(plain, TABLE) == (plain, None)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("D +", "expression_syntax"),
        ("Q", "expression_unknown_name"),
        ("A", "expression_units"),
        ("-D", "parameter_value_invalid"),
        ("D / 0", "expression_domain"),
    ],
)
def test_a_formula_that_does_not_resolve_is_typed(text: str, code: str) -> None:
    with pytest.raises(FeatureExpressionError) as caught:
        resolve_feature(_extrude({"/distance_mm": text}), TABLE)
    assert caught.value.code == code


def test_bare_numbers_take_the_fields_unit_and_ints_must_be_whole() -> None:
    twist = _extrude({"/distance_mm": "12"})
    assert _p(resolve_feature(twist, TABLE))["distance_mm"] == 12.0
    pattern = FEATURE_REGISTRY.load(
        "pattern",
        1,
        {
            "pattern": {
                "kind": "circular",
                "axis_point": {"x": 0, "y": 0, "z": 0},
                "axis_direction": {"x": 0, "y": 0, "z": 1},
                "angle_deg": 90.0,
                "count": 2,
            }
        },
        expressions={"/pattern/count": "N + 1.0000000001", "/pattern/angle_deg": "A*3"},
    )
    resolved = resolve_feature(pattern, TABLE)
    assert _p(resolved)["pattern"]["count"] == 4
    assert _p(resolved)["pattern"]["angle_deg"] == 90.0
    for text, code in (("N / 2", "expression_domain"), ("D", "expression_units")):
        bad = pattern.model_copy(update={"expressions": {"/pattern/count": text}})
        with pytest.raises(FeatureExpressionError) as caught:
            resolve_feature(bad, TABLE)
        assert caught.value.code == code


def test_the_evaluation_input_is_numbers_only_or_sick_with_its_last_good_values() -> (
    None
):
    feature = _extrude({"/distance_mm": "D"})
    sent, error = evaluation_input(feature, TABLE)
    assert error is None and sent.expressions is None
    assert _p(sent)["distance_mm"] == 25.0

    sent, error = evaluation_input(feature, {"D": Quantity(-1.0, "length")})
    assert error is not None and error.code == "parameter_value_invalid"
    assert _p(sent)["distance_mm"] == 10.0 and sent.expressions is None

    sent, error = evaluation_input(feature, {})
    assert error is not None and error.code == "parameter_unresolved"


def test_the_geometry_form_keys_on_the_resolved_value() -> None:
    feature = _extrude({"/distance_mm": "D"})
    ten = evaluation_input(feature, {"D": Quantity(10.0, "length")})[0]
    twenty = evaluation_input(feature, {"D": Quantity(20.0, "length")})[0]
    again = evaluation_input(feature, {"D": Quantity(10.0, "length")})[0]
    assert ten.model_dump_json() != twenty.model_dump_json()
    assert ten.model_dump_json() == again.model_dump_json()
    # ...and a formula-driven 10 keys exactly like a typed 10.
    assert ten.model_dump_json() == _extrude().model_dump_json()


# --- sketch dimensions ------------------------------------------------------------


def test_a_sketch_dimension_reads_its_sketch_first_then_the_parameters() -> None:
    sketch = _sketch(
        _dim("e1", 10.0, "W", name="len"), _dim("e2", 10.0, "len / 4 + D / 5")
    )
    assert parameter_references(sketch) == {"W", "D"}
    resolved = resolve_feature(sketch, TABLE)
    values = [c["value_mm"] for c in _p(resolved)["constraints"]]
    assert values == [40.0, 15.0]
    sent = for_geometry(resolved)
    texts = [c.get("expression") for c in _p(sent)["constraints"]]
    assert texts == [None, None]


def test_a_dimension_over_dimensions_only_keeps_its_formula_for_geometry() -> None:
    sketch = _sketch(_dim("e1", 10.0, "W", name="len"), _dim("e2", 10.0, "len / 4"))
    sent = for_geometry(resolve_feature(sketch, TABLE))
    texts = [c.get("expression") for c in _p(sent)["constraints"]]
    assert texts == [None, "len / 4"]
    # A sketch that names no parameter is untouched, formulas and all.
    own = _sketch(_dim("e1", 10.0, name="len"), _dim("e2", 5.0, "len / 2"))
    assert resolve_feature(own, TABLE) is own and for_geometry(own) is own


def test_a_dimension_reads_a_parameter_typed() -> None:
    angle = [
        {"kind": "angle", "a": "e1", "b": "e2", "value_deg": 45.0, "expression": "D"}
    ]
    with pytest.raises(ExpressionUnitError):
        evaluate_driving_dimensions(_constraints(_sketch(*angle)), TABLE)
    # Without a table, every stored sketch evaluates exactly as before.
    plain = _sketch(_dim("e1", 10.0, name="w"), _dim("e2", 1.0, "w*2"))
    assert evaluate_driving_dimensions(_constraints(plain)) == {0: 10.0, 1: 20.0}


def test_a_dimension_may_not_take_a_parameters_name() -> None:
    sketch = _sketch(_dim("e1", 10.0, name="W"))
    with pytest.raises(FeatureExpressionError) as caught:
        check_dimension_names(sketch, TABLE)
    assert caught.value.code == "expression_name_invalid"
    check_dimension_names(sketch, ["D"])


# --- renames ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "renames", "want"),
    [
        ("w*width", {"w": "x"}, "x*width"),
        ("  w + 2 mm ", {"w": "x"}, "  x + 2 mm "),
        ("a+b", {"a": "b", "b": "a"}, "b+a"),
        ("max(w, w2)", {"w": "W"}, "max(W, w2)"),
        ("w $", {"w": "x"}, "w $"),  # does not tokenize: left alone
    ],
)
def test_rename_references_is_token_wise(
    text: str, renames: dict[str, str], want: str
) -> None:
    assert rename_references(text, renames) == want


def test_a_rename_reaches_expressions_and_dimension_formulas() -> None:
    feature = _extrude({"/distance_mm": "D + DD"})
    assert rename_parameters(feature, {"D": "Depth"}).expressions == {
        "/distance_mm": "Depth + DD"
    }
    sketch = _sketch(_dim("e1", 10.0, "W*2", name="len"), _dim("e2", 1.0, "len"))
    renamed = rename_parameters(sketch, {"W": "Width", "len": "nope"})
    texts = [c.get("expression") for c in _p(renamed)["constraints"]]
    assert texts == ["Width*2", "len"]  # the sketch's own name is not a parameter


def test_parameter_values_reads_stored_rows() -> None:
    rows = [{"name": "W", "value": 40, "unit": "length"}]
    assert parameter_values(rows) == {"W": Quantity(40.0, "length")}


# --- the stored form (review of step 4) -------------------------------------------


def test_normalize_moves_a_parameter_formula_to_its_value_pointer() -> None:
    sketch = _sketch(
        _dim("e1", 10.0, "W / 2", name="len"),
        _dim("e2", 10.0, "len / 4"),
        {"kind": "angle", "a": "e1", "b": "e2", "value_deg": 45.0, "expression": "A"},
    )
    stored = normalize(sketch)
    assert stored.expressions == {
        "/constraints/0/value_mm": "W / 2",
        "/constraints/2/value_deg": "A",
    }
    assert [c.get("expression") for c in _p(stored)["constraints"]] == [
        None,
        "len / 4",
        None,
    ]
    assert normalize(stored) is stored
    assert parameter_references(stored) == {"W", "A"}
    # Resolution reads the moved formula with the sketch, as before.
    resolved = resolve_feature(stored, TABLE)
    assert [c["value_mm"] for c in _p(resolved)["constraints"][:2]] == [20.0, 5.0]
    assert _p(resolved)["constraints"][2]["value_deg"] == 30.0
    legacy = _p(resolve_feature(sketch, TABLE))["constraints"]
    assert [c.get("value_mm", c.get("value_deg")) for c in legacy] == [20.0, 5.0, 30.0]
    sent = for_geometry(resolved)
    assert sent.expressions is None
    assert [c.get("expression") for c in _p(sent)["constraints"]] == [
        None,
        "len / 4",
        None,
    ]
    # A sketch over its own dimensions only has nothing to move.
    own = _sketch(_dim("e1", 10.0, name="len"), _dim("e2", 5.0, "len / 2"))
    assert normalize(own) is own


def test_a_pointer_on_a_dimension_with_its_own_formula_is_refused() -> None:
    data = _sketch(_dim("e1", 10.0, "5")).model_dump(mode="json")
    data["expressions"] = {"/constraints/0/value_mm": "W"}
    with pytest.raises(ValidationError, match="own expression"):
        type(_sketch()).model_validate(data)


@pytest.mark.parametrize("where", ["envelope", "moved", "own"])
def test_a_rename_past_the_cap_is_refused_naming_the_pointer(where: str) -> None:
    long = "x" * 60
    if where == "envelope":
        feature = _extrude({"/distance_mm": "W+W+W+W+W"})
        pointer = "/distance_mm"
    elif where == "moved":
        feature = normalize(_sketch(_dim("e1", 10.0, "W+W+W+W+W")))
        pointer = "/constraints/0/value_mm"
    else:  # a tree stored before normalize: the dimension's own expression
        feature = _sketch(_dim("e1", 10.0, "W+W+W+W+W"))
        pointer = "/constraints/0/expression"
    with pytest.raises(FeatureExpressionError) as caught:
        rename_parameters(feature, {"W": long})
    assert (caught.value.code, caught.value.pointer) == (
        "expression_too_complex",
        pointer,
    )
    renamed = rename_parameters(feature, {"W": "Width"})
    assert "Width+Width" in renamed.model_dump_json()


def test_geometry_never_receives_formulas() -> None:
    """A request built from a stored tree keys the cache like documents'."""
    stored = _extrude({"/distance_mm": "D"})
    sent = EvaluatedFeatureInput(id=SKETCH_ID, feature=stored)  # type: ignore[arg-type]
    assert sent.feature.expressions is None
    assert (
        sent.model_dump_json()
        == (
            EvaluatedFeatureInput(id=SKETCH_ID, feature=_extrude())  # type: ignore[arg-type]
        ).model_dump_json()
    )
