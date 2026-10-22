"""Bare numbers in a non-mm part (FORMULA-BARE-UNIT).

Pinned here: where a part's unit is written into a formula (a term added to,
subtracted from or compared with a length, a length field's whole value) and
where it is not (factors, divisors, counts, angles, trig arguments, an mm
part); that the written text evaluates under the unchanged grammar to what a
Fusion user meant; that a formula left as stored keeps its text; and that a
stored one is reported with its fix.
"""

import uuid
from typing import Any

import pytest
from loft_wire.bare_units import (
    feature_warnings,
    parameter_warnings,
    write_parameter_units,
    write_units,
)
from loft_wire.expr import ExpressionLimitError, Quantity, bare_lengths, evaluate
from loft_wire.feature_resolve import FeatureExpressionError
from loft_wire.features import AuthoredEnvelope, ExtrudeFeature, SketchFeature
from loft_wire.parameters import PartParameterInput, resolve_parameters

IN = 25.4
KINDS: dict[str, Any] = {"wall": "length", "W": "length", "n": "unitless", "a": "angle"}
WALL = {"wall": Quantity(5.5 * IN, "length"), "W": Quantity(48 * IN, "length")}


def _fixed(text: str, field: Any = "length", unit: str = "in") -> str | None:
    found = bare_lengths(text, unit, field, KINDS)
    return None if found is None else found.text


@pytest.mark.parametrize(
    ("text", "fixed"),
    [
        ("wall + 1/2", "wall + 1 in/2"),
        ("W/2 + 3", "W/2 + 3 in"),
        ("3 + W/2", "3 in + W/2"),
        ("wall - 1.5", "wall - 1.5 in"),
        ("1/2", "1 in/2"),
        ("2*(W + 1)", "2*(W + 1 in)"),
        ("-(1+2)", "-(1 in+2 in)"),
        ("wall + -2", "wall + -2 in"),
        ("max(wall, 3)", "max(wall, 3 in)"),
        ("round(wall + 1)", "round(wall + 1 in)"),
        ("wall + n", "wall + n*1 in"),
        ("wall + pi", "wall + pi*1 in"),
        ("wall + sqrt(2)", "wall + sqrt(2)*1 in"),
    ],
)
def test_a_term_added_to_a_length_takes_the_part_unit(text: str, fixed: str) -> None:
    assert _fixed(text) == fixed


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("W*2", "length"),
        ("W/2", "length"),
        ("2*W", "length"),
        ("wall + 1 in", "length"),
        ("wall + 25 mm", "length"),
        ("W/wall", "unitless"),
        ("n + 1", "unitless"),
        ("a + 3", "angle"),
        ("30", "angle"),
        ("atan(1/2)", "angle"),
        ("W*sin(30)", "length"),
        ("wall + 1 +", "length"),  # does not parse: its own resolution says so
        ("Q + 1", "length"),  # unknown name
        ("wall + 30 deg", "length"),  # a unit clash stays a unit clash
    ],
)
def test_factors_divisors_angles_and_bad_text_stay_as_written(
    text: str, field: Any
) -> None:
    assert _fixed(text, field) is None


def test_a_sum_inside_a_ratio_is_looked_into() -> None:
    assert _fixed("(wall+1)/W", "unitless") == "(wall+1 in)/W"
    # A ratio as a length field's whole value is a length in the part unit,
    # and the sum inside it still gets its own unit.
    assert _fixed("(wall+1)/W") == "(wall+1 in)/W*1 in"
    assert _fixed("n*2") == "n*1 in*2"
    assert _fixed("-(W/wall)") == "-(W/wall)*1 in"


def test_an_mm_part_writes_nothing() -> None:
    assert _fixed("wall + 1/2", unit="mm") is None


def test_the_written_text_reads_in_the_part_unit_under_the_same_grammar() -> None:
    assert evaluate("wall + 1/2", WALL).value == pytest.approx(5.5 * IN + 0.5)
    assert evaluate("wall + 1 in/2", WALL).value == pytest.approx(6 * IN)
    assert evaluate(_fixed("W/2 + 3") or "", WALL).value == pytest.approx(27 * IN)
    assert _fixed("wall + 1/2", unit="ft") == "wall + 1 ft/2"
    assert _fixed("wall + 1/2", unit="cm") == "wall + 1 cm/2"


def test_the_literals_name_each_whole_term() -> None:
    found = bare_lengths("wall + 1/2 - (3)", "in", "length", KINDS)
    assert found is not None
    assert found.literals == ("1/2", "(3)")


def test_a_unit_past_the_cap_is_refused() -> None:
    text = "wall" + "+1" * 126
    with pytest.raises(ExpressionLimitError):
        bare_lengths(text, "in", "length", KINDS)


# --- features ----------------------------------------------------------------


def _extrude(text: str) -> ExtrudeFeature:
    return ExtrudeFeature.model_validate(
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(uuid.uuid4())},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
            "expressions": {"/distance_mm": text},
        }
    )


def _sketch(*expressions: tuple[str, str]) -> SketchFeature:
    lines = [
        {
            "id": f"e{i}",
            "kind": "line",
            "start": {"x": 0, "y": i},
            "end": {"x": 9, "y": i},
        }
        for i in range(2)
    ]
    constraints = [
        {
            "kind": "distance",
            "entity": f"e{i}",
            "value_mm": 10.0,
            "name": name,
            "expression": text,
        }
        for i, (name, text) in enumerate(expressions)
    ]
    return SketchFeature.model_validate(
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": lines,
                "constraints": constraints,
            },
        }
    )


def _expr(envelope: AuthoredEnvelope) -> str:
    return (envelope.expressions or {})["/distance_mm"]


def test_a_new_feature_formula_is_written_in_the_part_unit() -> None:
    written = write_units(_extrude("wall + 1/2"), "in", WALL)
    assert _expr(written) == "wall + 1 in/2"


def test_an_mm_part_and_a_formula_left_as_stored_keep_their_bytes() -> None:
    feature = _extrude("wall + 1/2")
    assert write_units(feature, "mm", WALL) is feature
    assert write_units(feature, "in", WALL, stored=feature) is feature
    edited = write_units(_extrude("wall + 1/4"), "in", WALL, stored=feature)
    assert _expr(edited) == "wall + 1 in/4"


def test_a_sketch_dimension_counts_as_a_length_in_mm() -> None:
    sketch = _sketch(("d1", "30"), ("d2", "d1 + 2"))
    written = write_units(sketch, "in", {})
    dims = [c.expression for c in written.params.constraints]  # type: ignore[attr-defined]
    assert dims == ["30 in", "d1 + 2 in"]
    # Re-saved as stored, the old text stays (each text matched once).
    old = _sketch(("d1", "30"), ("d2", "d1 + 2"))
    assert write_units(old, "in", {}, stored=old) is old


def test_a_cap_overflow_on_write_names_the_field() -> None:
    with pytest.raises(FeatureExpressionError) as caught:
        write_units(_extrude("wall" + "+1" * 126), "in", WALL)
    assert caught.value.pointer == "/distance_mm"


def test_a_stored_feature_formula_is_flagged_with_both_readings() -> None:
    [warning] = feature_warnings(_extrude("wall + 1/2"), "in", WALL)
    assert warning.code == "expression_bare_mm"
    assert (warning.pointer, warning.literals) == ("/distance_mm", ["1/2"])
    assert warning.fixed_expression == "wall + 1 in/2"
    assert warning.value == pytest.approx(5.5 * IN + 0.5)
    assert warning.fixed_value == pytest.approx(6 * IN)
    assert "`1/2`" in warning.message and "6 in" in warning.message
    assert feature_warnings(_extrude("wall + 1/2"), "mm", WALL) == []
    assert feature_warnings(_extrude("wall + 1 in/2"), "in", WALL) == []


def test_a_stored_sketch_dimension_is_flagged_at_its_constraint() -> None:
    [warning] = feature_warnings(_sketch(("d1", "40 mm"), ("d2", "d1 + 2")), "in", {})
    assert warning.pointer == "/constraints/1/expression"
    assert warning.value == pytest.approx(42)
    assert warning.fixed_value == pytest.approx(40 + 2 * IN)


# --- parameters ----------------------------------------------------------------


def _rows(*rows: tuple[str, str]) -> list[PartParameterInput]:
    return [
        PartParameterInput(id=uuid.uuid4(), name=name, expression=text, unit="length")
        for name, text in rows
    ]


def test_a_parameter_entered_is_written_and_one_left_as_stored_is_not() -> None:
    rows = _rows(("wall", "5.5 in"), ("outer", "wall + 1/2"))
    written = write_parameter_units(rows, [], "in")
    assert [r.expression for r in written] == ["5.5 in", "wall + 1 in/2"]
    stored = [r.model_dump(mode="json") for r in rows]
    assert write_parameter_units(rows, stored, "in") == rows
    assert write_parameter_units(rows, [], "mm") == rows


def test_a_stored_parameter_is_flagged_with_its_fix() -> None:
    rows = _rows(("wall", "5.5 in"), ("outer", "wall + 1/2"))
    stored = [r.model_dump(mode="json") for r in resolve_parameters(rows)]
    [warning] = parameter_warnings(stored, "in")
    assert warning.parameter_id == rows[1].id and warning.pointer is None
    assert warning.fixed_expression == "wall + 1 in/2"
    assert warning.fixed_value == pytest.approx(6 * IN)
    assert parameter_warnings(stored, "mm") == []
