"""Loft's expression language (:mod:`loft_wire.expr`): grammar, units,
functions, name graphs, limits and hostile input.

Expected values are hand-derived: ``20*tan(15)`` is ``20*(2 - sqrt(3))`` =
5.35898384862245413 (the double nearest it is 5.358983848622454), an inch is
25.4 mm exactly, a foot 304.8 mm.
"""

from __future__ import annotations

import math

import pytest
from loft_wire import expr
from loft_wire.expr import (
    ANGLE,
    LENGTH,
    UNITLESS,
    ExpressionCycleError,
    ExpressionDomainError,
    ExpressionError,
    ExpressionLimitError,
    ExpressionNameError,
    ExpressionReferenceError,
    ExpressionSyntaxError,
    ExpressionUnitError,
    NamedExpression,
    Quantity,
    coerce,
    coerce_int,
    evaluate,
    evaluate_driving_dimensions,
    evaluate_parameters,
    parse,
    validate_name,
)
from loft_wire.sketch import (
    AngleConstraint,
    DistanceConstraint,
    HorizontalConstraint,
    SketchConstraint,
)


def _q(text: str, **names: Quantity) -> Quantity:
    return evaluate(text, names)


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", 42.0),
        (".5", 0.5),
        ("3.", 3.0),
        ("2+3*4", 14.0),
        ("(2+3)*4", 20.0),
        ("10-2-3", 5.0),
        ("20/4/5", 1.0),
        ("-(2+3)*2", -10.0),
        ("--5", 5.0),
        ("+7", 7.0),
        (" \t2 * ( 3 + 4 )\n", 14.0),
        ("pi", math.pi),
        ("2*pi", 2 * math.pi),
    ],
)
def test_arithmetic(text: str, expected: float) -> None:
    assert _q(text) == Quantity(expected, UNITLESS)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "2+",
        "2 3",
        "(2+3",
        "2+3)",
        "*2",
        "2**3",
        "2 % 3",
        "2.3.4",
        "1e3",
        "2^3",
        "sin",
        "sin()",
        "sin(1,2)",
        "atan2(1)",
        "max()",
        "f(1)",
        "mm",
        "2 mm mm",
        "(2) mm",
        "pi rad",
        "1,2",
        "sin(1,)",
    ],
)
def test_malformed_is_a_syntax_error(text: str) -> None:
    with pytest.raises(ExpressionSyntaxError):
        _q(text)


def test_references_exclude_constants_units_and_functions() -> None:
    parsed = parse("width/2 + sin(angle) * pi + 3 mm + max(a, b)")
    assert parsed.references() == {"width", "angle", "a", "b"}
    assert parsed.words >= {"sin", "pi", "mm", "max"}


def test_references_of_a_long_flat_chain_do_not_recurse() -> None:
    assert parse("+".join(["a"] * 128)).references() == {"a"}


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 mm", Quantity(10.0, LENGTH)),
        ("10mm", Quantity(10.0, LENGTH)),
        ("2 cm", Quantity(20.0, LENGTH)),
        ("1.5 m", Quantity(1500.0, LENGTH)),
        ("1 in", Quantity(25.4, LENGTH)),
        ("1 ft", Quantity(304.8, LENGTH)),
        ("30 deg", Quantity(30.0, ANGLE)),
        ("1 rad", Quantity(180.0 / math.pi, ANGLE)),
        ("1in + 14.6", Quantity(40.0, LENGTH)),  # bare number joins as mm
        ("10 deg + 5", Quantity(15.0, ANGLE)),
        ("10 mm * 3", Quantity(30.0, LENGTH)),
        ("3 * 10 mm", Quantity(30.0, LENGTH)),
        ("10 mm / 4", Quantity(2.5, LENGTH)),
        ("10 mm / 4 mm", Quantity(2.5, UNITLESS)),
        ("90 deg / 45 deg", Quantity(2.0, UNITLESS)),
        ("-(5 mm)", Quantity(-5.0, LENGTH)),
        ("1 m - 1 ft", Quantity(695.2, LENGTH)),
    ],
)
def test_units(text: str, expected: Quantity) -> None:
    assert _q(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "10 mm + 5 deg",
        "10 deg - 1 mm",
        "10 mm * 2 mm",
        "2 deg * 3 deg",
        "1 mm * 1 deg",
        "1 / 2 mm",
        "1 mm / 1 deg",
        "sin(10 mm)",
        "tan(1 in)",
        "asin(1 mm)",
        "atan(30 deg)",
        "sqrt(4 mm)",
        "atan2(1 mm, 1 deg)",
        "min(1 mm, 1 deg)",
        "deg(1 deg)",
        "deg(1 mm)",
        "rad(1 mm)",
    ],
)
def test_unit_clashes(text: str) -> None:
    with pytest.raises(ExpressionUnitError):
        _q(text)


def test_references_carry_their_kind() -> None:
    width = Quantity(40.0, LENGTH)
    assert _q("width/2", width=width) == Quantity(20.0, LENGTH)
    assert _q("width/width", width=width) == Quantity(1.0, UNITLESS)
    with pytest.raises(ExpressionUnitError):
        _q("width*width", width=width)
    with pytest.raises(ExpressionUnitError):
        _q("sin(width)", width=width)


def test_coerce_to_field_kind() -> None:
    assert coerce(Quantity(5.0, UNITLESS), LENGTH) == 5.0  # bare = mm
    assert coerce(Quantity(5.0, UNITLESS), ANGLE) == 5.0  # bare = deg
    assert coerce(Quantity(5.0, LENGTH), LENGTH) == 5.0
    with pytest.raises(ExpressionUnitError, match="evaluates to a length"):
        coerce(Quantity(5.0, LENGTH), ANGLE, "angle")
    with pytest.raises(ExpressionUnitError, match="evaluates to an angle"):
        coerce(Quantity(5.0, ANGLE), LENGTH)
    with pytest.raises(ExpressionUnitError):
        coerce(Quantity(5.0, LENGTH), UNITLESS)


def test_coerce_int() -> None:
    assert coerce_int(Quantity(7.0, UNITLESS)) == 7
    assert coerce_int(_q("0.1*3*10")) == 3  # 3.0000000000000004, within 1e-9
    assert coerce_int(Quantity(-2.0 + 1e-10, UNITLESS)) == -2
    with pytest.raises(ExpressionDomainError, match="whole number"):
        coerce_int(Quantity(2.5, UNITLESS))
    with pytest.raises(ExpressionDomainError):
        coerce_int(Quantity(2.0 + 2e-9, UNITLESS))
    with pytest.raises(ExpressionUnitError):
        coerce_int(Quantity(3.0, LENGTH))


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20*tan(15)", Quantity(5.358983848622454, UNITLESS)),
        ("tan(45)", Quantity(math.tan(math.pi / 4), UNITLESS)),
        ("sin(30)", Quantity(math.sin(math.radians(30)), UNITLESS)),
        ("sin(30 deg)", Quantity(math.sin(math.radians(30)), UNITLESS)),
        ("cos(deg(pi/3))", Quantity(math.cos(math.pi / 3), UNITLESS)),
        ("asin(1)", Quantity(90.0, ANGLE)),
        ("acos(0)", Quantity(90.0, ANGLE)),
        ("atan(1)", Quantity(45.0, ANGLE)),
        ("atan2(1, 1)", Quantity(45.0, ANGLE)),
        ("atan2(-3 mm, 0 mm)", Quantity(-90.0, ANGLE)),
        ("sqrt(16)", Quantity(4.0, UNITLESS)),
        ("abs(-3 mm)", Quantity(3.0, LENGTH)),
        ("min(3 mm, 1 in, 5)", Quantity(3.0, LENGTH)),
        ("max(3 mm, 1 in)", Quantity(25.4, LENGTH)),
        ("max(7)", Quantity(7.0, UNITLESS)),
        ("round(2.5)", Quantity(3.0, UNITLESS)),  # half away from zero
        ("round(-2.5)", Quantity(-3.0, UNITLESS)),
        ("round(2.4999)", Quantity(2.0, UNITLESS)),
        ("round(-0.2)", Quantity(0.0, UNITLESS)),
        ("floor(-1.5)", Quantity(-2.0, UNITLESS)),
        ("ceil(1.2 mm)", Quantity(2.0, LENGTH)),
        ("rad(180)", Quantity(math.pi, UNITLESS)),
        ("rad(90 deg)", Quantity(math.pi / 2, UNITLESS)),
        ("deg(pi)", Quantity(180.0, ANGLE)),
        ("sin(deg(pi/2))", Quantity(1.0, UNITLESS)),
    ],
)
def test_functions(text: str, expected: Quantity) -> None:
    assert _q(text) == expected


def test_results_must_be_finite() -> None:
    # 256 characters of digits cannot overflow a double; names can.
    big = Quantity(1e200, UNITLESS)
    with pytest.raises(ExpressionDomainError, match="non-finite"):
        _q("w*w", w=big)
    with pytest.raises(ExpressionDomainError, match="non-finite"):
        _q("w + 1", w=Quantity(math.nan, LENGTH))
    with pytest.raises(ExpressionDomainError, match="non-finite"):
        _q("w", w=Quantity(math.inf, LENGTH))


def test_round_never_returns_negative_zero() -> None:
    assert math.copysign(1.0, _q("round(-0.2)").value) == 1.0


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("1/0", "division by zero"),
        ("1/(2-2)", "division by zero"),
        ("sqrt(-1)", "negative"),
        ("asin(2)", "outside"),
        ("acos(-1.5)", "outside"),
        ("tan(90)", "undefined"),
        ("tan(-270 deg)", "undefined"),
        ("atan2(0, 0)", "undefined"),
    ],
)
def test_domain_errors(text: str, match: str) -> None:
    with pytest.raises(ExpressionDomainError, match=match):
        _q(text)


# ---------------------------------------------------------------------------
# Limits and hostile input: every one a typed error, nothing executes
# ---------------------------------------------------------------------------


def test_length_limit() -> None:
    assert _q("1" + "+1" * 127) == Quantity(128.0, UNITLESS)  # 255 chars
    with pytest.raises(ExpressionLimitError, match="257 characters"):
        parse("1" + "+1" * 128)


@pytest.mark.parametrize(
    "text",
    [
        "(" * 250 + "1" + ")" * 250,
        "-" * 2000 + "1",
        "1" + "+1" * 2000,
        "sin(" * 100 + "1" + ")" * 100,
    ],
)
def test_too_long_or_too_deep_is_a_limit_error(text: str) -> None:
    with pytest.raises(ExpressionLimitError):
        parse(text)


def test_depth_guard_below_the_length_limit() -> None:
    # 151 unary minuses fit in 256 characters but nest past 150.
    with pytest.raises(ExpressionLimitError, match="nests deeper"):
        parse("-" * 151 + "1")
    assert _q("-" * 140 + "1") == Quantity(1.0, UNITLESS)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('true')",
        "eval(1)",
        "exec(1)",
        "open(1)",
        "getattr(x, y)",
        "x.__class__",
        "pi.real",
        "lambda: 1",
        "[1]",
        "{1}",
        "1; 2",
        "1 if 1 else 2",
        "a == b",
        "\x00",
        "\u0663",  # a non-ASCII digit float() would accept
        "\uff11",  # fullwidth digit
        "\uff11 mm",
        "1\u00a0+ 1",  # non-breaking space
        "\u03c0",
        "'1'",
        "`1`",
        "#1",
    ],
)
def test_hostile_strings_raise_typed_errors(text: str) -> None:
    with pytest.raises(ExpressionError):
        _q(text, x=Quantity(1.0, UNITLESS), y=Quantity(1.0, UNITLESS))


@pytest.mark.parametrize("name", ["eval", "exec", "pow", "log", "exp", "hypot", "Sin"])
def test_functions_off_the_whitelist(name: str) -> None:
    with pytest.raises(ExpressionSyntaxError, match="unknown function"):
        parse(f"{name}(1)")


def test_unknown_name_without_a_table() -> None:
    with pytest.raises(ExpressionReferenceError, match="unknown name 'w'"):
        _q("w*2")


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["w", "_x", "Height_2", "a" * 64, "M", "In", "PI"])
def test_valid_names(name: str) -> None:
    assert validate_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", "2w", "a-b", "a b", "a" * 65, "é", "w\n", *sorted(expr.RESERVED_WORDS)],
)
def test_invalid_names(name: str) -> None:
    with pytest.raises(ExpressionNameError):
        validate_name(name)


# ---------------------------------------------------------------------------
# Parameter tables: order, kinds, cycles
# ---------------------------------------------------------------------------


def _row(name: str, text: str, kind: expr.Kind = LENGTH) -> NamedExpression:
    return NamedExpression(name=name, expression=text, kind=kind)


def test_parameters_resolve_in_any_order() -> None:
    values = evaluate_parameters(
        [
            _row("depth", "width/2 + 1 in"),
            _row("width", "40"),
            _row("teeth", "20", UNITLESS),
            _row("beta", "asin(0.5)", ANGLE),
            _row("pitch_r", "teeth * 2 / 2 / cos(beta)"),
        ]
    )
    assert list(values) == ["depth", "width", "teeth", "beta", "pitch_r"]
    assert values["width"] == Quantity(40.0, LENGTH)
    assert values["depth"] == Quantity(45.4, LENGTH)
    assert values["beta"] == Quantity(30.000000000000004, ANGLE)
    assert values["pitch_r"].kind == LENGTH
    assert values["pitch_r"].value == pytest.approx(20 / math.cos(math.pi / 6))


@pytest.mark.parametrize(
    ("rows", "chain"),
    [
        ([_row("a", "a+1")], ("a", "a")),
        ([_row("a", "b"), _row("b", "a")], ("a", "b", "a")),
        (
            [_row("a", "b"), _row("b", "c"), _row("c", "a*2"), _row("d", "1")],
            ("a", "b", "c", "a"),
        ),
        ([_row("x", "y"), _row("y", "z"), _row("z", "y")], ("y", "z", "y")),
    ],
)
def test_cycles_report_their_chain(
    rows: list[NamedExpression], chain: tuple[str, ...]
) -> None:
    with pytest.raises(ExpressionCycleError) as excinfo:
        evaluate_parameters(rows)
    assert excinfo.value.chain == chain
    assert " -> ".join(chain) in str(excinfo.value)


def test_a_long_chain_does_not_hit_the_recursion_limit() -> None:
    rows = [_row("p0", "1")] + [_row(f"p{i}", f"p{i - 1}+1") for i in range(1, 200)]
    assert evaluate_parameters(rows)["p199"] == Quantity(200.0, LENGTH)


def test_parameter_table_errors() -> None:
    with pytest.raises(ExpressionReferenceError, match="unknown parameter 'nope'"):
        evaluate_parameters([_row("a", "nope")])
    with pytest.raises(ExpressionNameError, match="defined twice"):
        evaluate_parameters([_row("a", "1"), _row("a", "2")])
    with pytest.raises(ExpressionNameError, match="reserved"):
        evaluate_parameters([_row("sin", "1")])
    with pytest.raises(ExpressionUnitError, match="parameter 'ang'"):
        evaluate_parameters([_row("ang", "10 mm", ANGLE)])
    with pytest.raises(ExpressionUnitError):
        evaluate_parameters([_row("n", "1 in", UNITLESS)])
    with pytest.raises(ExpressionLimitError, match="at most 200"):
        evaluate_parameters([_row(f"p{i}", "1") for i in range(201)])


# ---------------------------------------------------------------------------
# Sketch dimensions
# ---------------------------------------------------------------------------


def _dist(entity: str, value: float, **kw: object) -> DistanceConstraint:
    return DistanceConstraint.model_validate(
        {"kind": "distance", "entity": entity, "value_mm": value, **kw}
    )


def _angle(expression: str) -> AngleConstraint:
    return AngleConstraint(
        kind="angle", a="e1", b="e2", value_deg=1.0, expression=expression
    )


def test_sketch_dimension_trig_and_units() -> None:
    constraints: list[SketchConstraint] = [
        HorizontalConstraint(kind="horizontal", entity="e1"),
        _dist("e1", 1.0, name="w", expression="1in + 14.6"),
        _dist("e2", 1.0, expression="20*tan(15)"),
        _angle("atan(1)"),
    ]
    assert evaluate_driving_dimensions(constraints) == {
        1: 40.0,
        2: 5.358983848622454,
        3: 45.0,
    }


def test_sketch_references_read_numbers_as_before_units() -> None:
    """A length dimension referenced by an angle reads its NUMBER (stored
    sketches keep evaluating as they did)."""
    values = evaluate_driving_dimensions(
        [_dist("e1", 20.0, name="half"), _angle("half*2")]
    )
    assert values == {0: 20.0, 1: 40.0}


@pytest.mark.parametrize(
    ("constraints", "error", "match"),
    [
        ([_dist("e1", 1.0, expression="30 deg")], ExpressionUnitError, "angle"),
        ([_angle("10 mm")], ExpressionUnitError, "length"),
        ([_dist("e1", 1.0, expression="nope")], ExpressionReferenceError, "nope"),
        (
            [
                _dist("e1", 10.0, name="meas", driving=False),
                _dist("e2", 1, expression="meas"),
            ],
            ExpressionReferenceError,
            "driven dimension 'meas'",
        ),
        (
            [_dist("e1", 3.0, name="pi"), _dist("e2", 1.0, expression="2*pi")],
            ExpressionNameError,
            "'pi' is reserved",
        ),
        (
            [
                _dist("e1", 1.0, name="a", expression="b"),
                _dist("e2", 1, name="b", expression="a"),
            ],
            ExpressionCycleError,
            "a -> b -> a",
        ),
        ([_dist("e1", 1.0, expression="tan(15)-1")], ExpressionDomainError, "> 0"),
        ([_angle("90*2")], ExpressionDomainError, "< 180"),
    ],
)
def test_sketch_dimension_errors(
    constraints: list[SketchConstraint], error: type[ExpressionError], match: str
) -> None:
    with pytest.raises(error, match=match):
        evaluate_driving_dimensions(constraints)


def test_a_dimension_named_like_a_unit_is_fine_until_referenced() -> None:
    assert evaluate_driving_dimensions([_dist("e1", 5.0, name="mm")]) == {0: 5.0}
    with pytest.raises(ExpressionNameError, match="'m' is reserved"):
        evaluate_driving_dimensions(
            [_dist("e1", 5.0, name="m"), _dist("e2", 1.0, expression="m/2")]
        )


def test_a_driven_dimension_with_a_bad_expression_is_never_parsed() -> None:
    values = evaluate_driving_dimensions(
        [_dist("e1", 5.0), _dist("e2", 5.0, expression="((", driving=False)]
    )
    assert values == {0: 5.0}
