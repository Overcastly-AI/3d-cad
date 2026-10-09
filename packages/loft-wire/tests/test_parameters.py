"""loft_wire.parameters — the parameter table's wire types and evaluation.

The route tests (services/documents/tests/test_parameters.py) prove the HTTP
contract; this pins the evaluation that every writer of a table shares, and
that a tree without parameters keeps its ``tree.json`` bytes.
"""

import uuid
from typing import Any

import pytest
from loft_wire.expr import MAX_PARAMETERS
from loft_wire.loft_file import LoftTree, encode_tree
from loft_wire.parameters import (
    ParameterTableError,
    PartParameterInput,
    PartParametersUpdate,
    resolve_parameters,
)
from pydantic import ValidationError


def _row(name: str, expression: str, unit: str = "length", **extra: Any) -> Any:
    return PartParameterInput.model_validate(
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "expression": expression,
            "unit": unit,
            **extra,
        }
    )


def test_a_table_resolves_in_dependency_order_and_keeps_its_order() -> None:
    rows = [
        _row("half", "width / 2"),
        _row("width", "1 in + 14.6", comment="overall"),
        _row("draft", "atan(1)", "angle"),
        _row("count", "round(width / 10 mm)", "unitless"),
    ]
    resolved = resolve_parameters(rows)
    assert [row.name for row in resolved] == ["half", "width", "draft", "count"]
    assert [row.value for row in resolved] == pytest.approx([20.0, 40.0, 45.0, 4.0])
    assert resolved[1].comment == "overall"
    assert [row.id for row in resolved] == [row.id for row in rows]


def test_an_empty_table_is_valid() -> None:
    assert resolve_parameters([]) == []


@pytest.mark.parametrize(
    ("rows", "code", "parameter"),
    [
        ([("a", "2 +")], "expression_syntax", "a"),
        ([("a", "b * 2")], "expression_unknown_name", "a"),
        ([("sin", "2")], "expression_name_invalid", "sin"),
        ([("1a", "2")], "expression_name_invalid", "1a"),
        ([("a", "2"), ("a", "3")], "expression_name_invalid", "a"),
        ([("a", "1 / 0")], "expression_domain", None),
        ([("a", "10 deg")], "expression_units", None),
        ([("a", "__import__('os')")], "expression_syntax", "a"),
    ],
)
def test_a_bad_table_is_refused_with_a_stable_code(
    rows: list[tuple[str, str]], code: str, parameter: str | None
) -> None:
    with pytest.raises(ParameterTableError) as caught:
        resolve_parameters([_row(name, text) for name, text in rows])
    assert caught.value.code == code
    assert caught.value.parameter == parameter


def test_a_cycle_reports_its_chain() -> None:
    rows = [_row("a", "b + 1"), _row("b", "c + 1"), _row("c", "a + 1")]
    with pytest.raises(ParameterTableError) as caught:
        resolve_parameters(rows)
    assert caught.value.code == "expression_cycle"
    assert caught.value.chain == ("a", "b", "c", "a")


def test_a_repeated_id_is_refused() -> None:
    first = _row("a", "1")
    second = _row("b", "2").model_copy(update={"id": first.id})
    with pytest.raises(ParameterTableError) as caught:
        resolve_parameters([first, second])
    assert caught.value.code == "parameter_id_duplicate"


def test_more_than_the_cap_is_refused_at_the_wire_and_in_evaluation() -> None:
    rows = [_row(f"p{index}", "1") for index in range(MAX_PARAMETERS + 1)]
    with pytest.raises(ParameterTableError) as caught:
        resolve_parameters(rows)
    assert caught.value.code == "expression_too_complex"
    with pytest.raises(ValidationError):
        PartParametersUpdate(expected_tree_version=0, parameters=rows)
    assert len(resolve_parameters(rows[:MAX_PARAMETERS])) == MAX_PARAMETERS


def test_a_client_cannot_send_a_value() -> None:
    with pytest.raises(ValidationError):
        _row("a", "1", value=99.0)


def test_a_tree_without_parameters_keeps_its_bytes() -> None:
    tree = LoftTree(name="Bracket", features=[])
    tree_bytes, _ = encode_tree(tree)
    assert b"parameters" not in tree_bytes
    with_table = tree.model_copy(
        update={"parameters": resolve_parameters([_row("w", "40")])}
    )
    encoded, _ = encode_tree(with_table)
    assert b'"parameters"' in encoded
    assert LoftTree.model_validate_json(encoded) == with_table


def test_a_stored_value_is_re_derived_never_trusted() -> None:
    [stored] = resolve_parameters([_row("w", "40")])
    tampered = stored.model_copy(update={"value": 1e9})
    assert resolve_parameters([tampered])[0].value == 40.0
