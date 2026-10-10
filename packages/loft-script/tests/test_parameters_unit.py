"""Formula arguments and parameter errors, with no server (PART-PARAMETERS step 6).

The stack test (``test_parameters.py``) proves a formula drives real geometry;
these pin the pure half: a number passes through untouched, a string goes to
``expressions`` at the right pointer (or to a dimension's own ``expression``)
with the number it gives beside it, and every refusal is typed with the
server's code.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import loft
import loft_wire.expr
import pytest
from loft.errors import (
    Conflict,
    InvalidExpression,
    InvalidRequest,
    LoftError,
    ParameterInUse,
    ParameterNotFound,
    StaleDocument,
)
from loft.parameters import (
    dimension_value,
    field_number,
    field_numbers,
    infer_unit,
    renamed,
    with_parameter,
    without,
)
from loft.part import Part
from loft.sketch import XY, Sketch
from loft_wire.expr import Quantity
from loft_wire.parameters import PartParameter
from loft_wire.sketch import DistanceConstraint

TABLE = {
    "W": Quantity(40.0, "length"),
    "H": Quantity(25.0, "length"),
    "A": Quantity(30.0, "angle"),
}


class _Fetch:
    """A parameter fetch that counts its calls."""

    def __init__(self, table: dict[str, Quantity] | None = None) -> None:
        self.table = TABLE if table is None else table
        self.calls = 0

    def __call__(self) -> dict[str, Quantity]:
        self.calls += 1
        return self.table


def _rows() -> list[PartParameter]:
    return [
        PartParameter(
            id=uuid.uuid4(), name="W", expression="40", unit="length", value=40.0
        ),
        PartParameter(
            id=uuid.uuid4(),
            name="H",
            expression="W - 15",
            unit="length",
            comment="follows W",
            value=25.0,
        ),
    ]


# --- feature fields: float stays, str goes to expressions --------------------


def test_a_number_passes_through_with_no_expressions_and_no_fetch() -> None:
    fetch = _Fetch()
    assert field_number("distance_mm", 12.5, fetch) == (12.5, None)
    assert fetch.calls == 0


def test_a_formula_goes_to_its_pointer_with_its_value_beside_it() -> None:
    fetch = _Fetch()
    number, formulas = field_number("distance_mm", "W/2 + 3", fetch)
    assert number == 23.0
    assert formulas == {"/distance_mm": "W/2 + 3"}
    assert fetch.calls == 1


def test_a_formula_with_no_names_reads_no_table() -> None:
    fetch = _Fetch()
    number, formulas = field_number("distance_mm", "1 in", fetch)
    assert (number, formulas) == (25.4, {"/distance_mm": "1 in"})
    assert fetch.calls == 0


def test_an_angle_field_takes_an_angle_and_refuses_a_length() -> None:
    assert field_number("angle_deg", "A + 15", _Fetch())[0] == 45.0
    with pytest.raises(InvalidExpression) as caught:
        field_number("angle_deg", "W", _Fetch())
    assert caught.value.code == "expression_units"
    assert caught.value.pointer == "/angle_deg"
    assert caught.value.status is None  # refused before anything was sent


def test_a_number_replaces_a_stored_formula_and_others_are_kept() -> None:
    kept = {"/distance_mm": "D", "/other_mm": "W"}
    numbers, formulas = field_numbers({"distance_mm": 7.0}, _Fetch(), kept=kept)
    assert numbers == {"distance_mm": 7.0}
    assert formulas == {"/other_mm": "W"}
    _, formulas = field_numbers({"distance_mm": "H"}, _Fetch(), kept=kept)
    assert formulas == {"/distance_mm": "H", "/other_mm": "W"}


def test_none_and_the_last_formula_removed_leave_no_expressions() -> None:
    numbers, formulas = field_numbers(
        {"twist_angle_deg": None}, _Fetch(), kept={"/twist_angle_deg": "A"}
    )
    assert numbers == {"twist_angle_deg": None}
    assert formulas is None


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("W +", "expression_syntax"),
        ("Nope", "expression_unknown_name"),
        ("W / 0", "expression_domain"),
        ("x" * 300, "expression_too_complex"),
        ("__import__('os')", "expression_syntax"),
    ],
)
def test_a_bad_formula_is_typed_with_the_shared_code(text: str, code: str) -> None:
    with pytest.raises(InvalidExpression) as caught:
        field_number("distance_mm", text, _Fetch())
    assert caught.value.code == code
    assert isinstance(caught.value, InvalidRequest)
    assert caught.value.as_dict()["details"]["expression"] == text


# --- sketch dimensions: the formula stays in the dimension -------------------


def test_a_dimension_reads_its_own_sketch_first_then_parameters() -> None:
    half = DistanceConstraint(kind="distance", entity="e1", value_mm=20.0, name="W")
    # The sketch's own `W` (20, unitless) wins over the parameter `W` (40 mm).
    assert dimension_value("W*2", [half], _Fetch()) == 40.0
    assert dimension_value("H + 1", [half], _Fetch()) == 26.0


def test_a_dimension_must_be_positive_and_a_length() -> None:
    with pytest.raises(InvalidExpression) as caught:
        dimension_value("W - 50", [], _Fetch())
    assert caught.value.code == "expression_domain"
    with pytest.raises(InvalidExpression) as caught:
        dimension_value("A", [], _Fetch())
    assert caught.value.code == "expression_units"


class _StubPart:
    def __init__(self) -> None:
        self.parameter_values = _Fetch()


def test_rect_puts_each_formula_in_its_own_dimension_and_reads_once() -> None:
    stub = _StubPart()
    sketch = Sketch(cast(Part, stub), XY)
    sketch.rect("W", "H")
    dims = [c for c in sketch.constraints if isinstance(c, DistanceConstraint)]
    assert [(d.value_mm, d.expression) for d in dims] == [(40.0, "W"), (25.0, "H")]
    assert stub.parameter_values.calls == 1
    xs = {p for e in sketch.entities for p in (e.start.x, e.end.x)}  # type: ignore[union-attr]
    assert xs == {0.0, 40.0}  # drawn at the size the formulas give now


def test_rect_with_numbers_is_unchanged_and_reads_nothing() -> None:
    stub = _StubPart()
    sketch = Sketch(cast(Part, stub), XY)
    sketch.rect(40, 25)
    dims = [c for c in sketch.constraints if isinstance(c, DistanceConstraint)]
    assert [(d.value_mm, d.expression) for d in dims] == [(40, None), (25, None)]
    assert stub.parameter_values.calls == 0


def test_circle_by_diameter_formula_halves_the_number_not_the_text() -> None:
    sketch = Sketch(cast(Part, _StubPart()), XY)
    sketch.circle((0, 0), diameter="W/4")
    (circle,) = sketch.entities
    (dim,) = sketch.constraints
    assert circle.radius == 5.0  # type: ignore[union-attr]
    assert (dim.kind, dim.value_mm, dim.expression) == ("diameter", 10.0, "W/4")  # type: ignore[union-attr]


def test_a_formula_needs_its_dimension() -> None:
    sketch = Sketch(cast(Part, _StubPart()), XY)
    with pytest.raises(ValueError, match="dimension=True"):
        sketch.rect("W", 10, dimension=False)
    with pytest.raises(ValueError, match="not both"):
        sketch.distance("e1", "W", expression="H")


# --- the table edits ---------------------------------------------------------


def test_set_updates_in_place_keeping_id_unit_and_comment() -> None:
    rows = _rows()
    table = with_parameter(rows, "H", "W - 10")
    assert [(r.id, r.name, r.expression) for r in table] == [
        (rows[0].id, "W", "40"),
        (rows[1].id, "H", "W - 10"),
    ]
    assert table[1].comment == "follows W"
    assert with_parameter(rows, "H", "5", comment="")[1].comment == ""


def test_set_appends_a_new_row_whose_unit_follows_its_formula() -> None:
    rows = _rows()
    assert with_parameter(rows, "D", "25")[-1].unit == "length"
    assert with_parameter(rows, "T", "30 deg")[-1].unit == "angle"
    assert with_parameter(rows, "N", "4", unit="unitless")[-1].unit == "unitless"
    assert infer_unit("W / H", rows, "length") == "length"  # unitless keeps


def test_rename_keeps_the_row_id_and_delete_drops_the_row() -> None:
    rows = _rows()
    table = renamed(rows, "W", "Width")
    assert (table[0].id, table[0].name) == (rows[0].id, "Width")
    assert [r.name for r in without(rows, "W")] == ["H"]


def test_an_unknown_name_is_parameter_not_found() -> None:
    with pytest.raises(ParameterNotFound) as caught:
        renamed(_rows(), "Q", "R")
    assert caught.value.code == "parameter_not_found"
    assert caught.value.details["parameters"] == ["W", "H"]


# --- server refusals ---------------------------------------------------------


def _envelope(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def test_a_422_cycle_is_invalid_expression_with_its_chain() -> None:
    body = _envelope(
        "expression_cycle", "a -> b -> a", {"parameter": "a", "chain": ["a", "b", "a"]}
    )
    error = LoftError.from_response(422, body, fallback="x")
    assert isinstance(error, InvalidExpression)
    assert (error.code, error.message, error.status) == (
        "expression_cycle",
        "a -> b -> a",
        422,
    )
    assert (error.parameter, error.chain) == ("a", ("a", "b", "a"))


@pytest.mark.parametrize(
    "code",
    [
        "expression_syntax",
        "expression_unknown_name",
        "expression_units",
        "expression_domain",
        "expression_too_complex",
        "expression_name_invalid",
        "parameter_value_invalid",
        "parameter_id_duplicate",
    ],
)
def test_every_parameter_422_is_typed(code: str) -> None:
    error = LoftError.from_response(422, _envelope(code, "no", {}), fallback="x")
    assert type(error) is InvalidExpression
    assert error.code == code


def test_a_stale_422_is_still_stale() -> None:
    body = _envelope("stale_tree_version", "moved", {})
    assert type(LoftError.from_response(422, body, fallback="x")) is StaleDocument


def test_a_409_parameter_in_use_lists_the_features() -> None:
    feature = {"id": str(uuid.uuid4()), "name": "Extrude", "parameters": ["D"]}
    body = _envelope(
        "parameter_in_use",
        "Parameter 'D' is used by 1 feature(s); remove those references first.",
        {"parameters": ["D"], "features": [feature]},
    )
    error = LoftError.from_response(409, body, fallback="x")
    assert isinstance(error, ParameterInUse)
    assert isinstance(error, Conflict)
    assert error.parameters == ("D",)
    assert error.features == (feature,)
    assert error.message.startswith("Parameter 'D' is used by 1 feature")


def test_loft_expr_is_the_shared_library() -> None:
    assert loft.expr.evaluate is loft_wire.expr.evaluate
    assert loft.expr.evaluate("20*tan(15)").value == pytest.approx(5.358983848622)
    assert loft.expr.evaluate("W/2", {"W": Quantity(40, "length")}) == Quantity(
        20.0, "length"
    )
