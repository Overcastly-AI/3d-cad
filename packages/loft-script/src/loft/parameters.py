"""Part parameters and formula arguments from a script (RESEARCH §20).

PART-PARAMETERS step 6. A part's parameter table is Fusion 360's Change
Parameters: named values (``W = 40``, ``H = W - 15``) whose formulas any
dimension or feature field may use. :class:`loft.Part` exposes the table
(``parameters``, ``set_parameter``, ``rename_parameter``,
``delete_parameter``); this module holds the pure half, with no transport:

* the table edits, each producing the WHOLE table a ``PUT`` replaces (rows
  keep their ``id``, so a rename is one the server rewrites references for);
* formula arguments. A numeric builder argument takes ``float | str``: a
  number is sent as it always was, and a string is a formula. A feature
  field's formula goes to the envelope's ``expressions`` at its JSON pointer
  (``{"/distance_mm": "D"}``); a sketch dimension's goes in the dimension's
  own ``expression``. The DTOs still need a number beside each formula, so it
  is evaluated here with the shared library (:mod:`loft_wire.expr`) against
  the part's table. Documents re-resolves every formula on write; its number
  is the one stored.

A formula that cannot evaluate here is refused before anything is sent, as
:class:`~loft.errors.InvalidExpression` with the code the server would give.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence

from loft_wire.expr import (
    ANGLE,
    LENGTH,
    UNITLESS,
    DimensionLike,
    ExpressionCycleError,
    ExpressionDomainError,
    ExpressionError,
    ExpressionReferenceError,
    Quantity,
    coerce,
    evaluate,
    parse,
)
from loft_wire.feature_expressions import leaf_kind
from loft_wire.parameters import ParameterUnit, PartParameter, PartParameterInput

from loft.errors import InvalidExpression, ParameterNotFound

__all__ = [
    "Numeric",
    "Once",
    "ParameterValues",
    "dimension_value",
    "expression_error",
    "field_number",
    "field_numbers",
    "infer_unit",
    "quantities",
    "renamed",
    "with_parameter",
    "without",
]

#: A numeric builder argument: a number (mm, degrees or plain, by the field),
#: or a formula over the part's parameters such as ``"D"`` or ``"W/2 + 3"``.
Numeric = float | str

#: Fetches the part's parameters by name, typed. Called at most once per
#: builder call, and only when a formula names something.
ParameterValues = Callable[[], Mapping[str, Quantity]]


def quantities(rows: Sequence[PartParameter]) -> dict[str, Quantity]:
    """name -> typed value (mm, degrees or plain) of a stored table."""
    return {row.name: Quantity(row.value, row.unit) for row in rows}


def expression_error(
    exc: ExpressionError,
    *,
    pointer: str | None = None,
    expression: str | None = None,
) -> InvalidExpression:
    """The typed refusal for a formula the shared library rejected."""
    details: dict[str, object] = {}
    if pointer is not None:
        details["pointer"] = pointer
    if expression is not None:
        details["expression"] = expression
    if isinstance(exc, ExpressionCycleError):
        details["chain"] = list(exc.chain)
    return InvalidExpression(str(exc), code=exc.code, details=details)


class Once:
    """A parameter fetch run on first use and then remembered, so one builder
    call with several formulas reads the table at most once."""

    def __init__(self, fetch: ParameterValues) -> None:
        self._fetch = fetch
        self._values: Mapping[str, Quantity] | None = None

    def __call__(self) -> Mapping[str, Quantity]:
        if self._values is None:
            self._values = self._fetch()
        return self._values


def _lookup(
    values: ParameterValues, own: Mapping[str, Quantity] | None = None
) -> Callable[[str], Quantity]:
    def resolve(name: str) -> Quantity:
        if own is not None and name in own:
            return own[name]
        table = values()
        if name not in table:
            raise ExpressionReferenceError(f"unknown parameter {name!r}")
        return table[name]

    return resolve


def field_numbers(
    fields: Mapping[str, Numeric | None],
    values: ParameterValues,
    *,
    kept: Mapping[str, str] | None = None,
) -> tuple[dict[str, float | None], dict[str, str] | None]:
    """Split top-level params fields into numbers and ``expressions``.

    A number (or ``None``) passes through and drops any formula that drove the
    field, as typing a number over a formula does in the UI. A string is
    evaluated for its field's unit (``*_mm`` a length, ``*_deg`` an angle) and
    its formula is kept at ``/<field>``. ``kept`` is the envelope's stored
    ``expressions``, whose other pointers are carried unchanged.
    """
    once = Once(values)
    numbers: dict[str, float | None] = {}
    formulas = dict(kept or {})
    for field, value in fields.items():
        pointer = f"/{field}"
        formulas.pop(pointer, None)
        if not isinstance(value, str):
            numbers[field] = value
            continue
        kind = leaf_kind([field], 0.0)  # a float leaf: never "int"
        assert kind != "int"
        try:
            quantity = parse(value).evaluate(_lookup(once))
            numbers[field] = coerce(quantity, kind, f"expression for {pointer}")
        except ExpressionError as exc:
            raise expression_error(exc, pointer=pointer, expression=value) from exc
        formulas[pointer] = value
    return numbers, formulas or None


def field_number(
    field: str,
    value: Numeric,
    values: ParameterValues,
    *,
    kept: Mapping[str, str] | None = None,
) -> tuple[float, dict[str, str] | None]:
    """:func:`field_numbers` for one required field."""
    numbers, formulas = field_numbers({field: value}, values, kept=kept)
    number = numbers[field]
    assert number is not None
    return number, formulas


def dimension_value(
    text: str,
    constraints: Sequence[object],
    values: ParameterValues,
    *,
    is_angle: bool = False,
) -> float:
    """The number a sketch dimension's formula gives, beside its expression.

    Read as documents and geometry read it
    (:func:`loft_wire.expr.evaluate_driving_dimensions`): the sketch's own
    driving dimensions by NUMBER, unitless, then the part's parameters, typed.
    The result is mm (degrees for an angle) and must be > 0.
    """
    dims = [c for c in constraints if isinstance(c, DimensionLike)]
    names = frozenset(c.name for c in dims if c.name is not None)
    own = {
        c.name: Quantity(c.value, UNITLESS)
        for c in dims
        if c.name is not None and c.is_driving
    }
    try:
        quantity = parse(text, names=names, legacy_text=True).evaluate(
            _lookup(Once(values), own)
        )
        value = coerce(quantity, ANGLE if is_angle else LENGTH, "dimension")
        if value <= 0.0:
            raise ExpressionDomainError(
                f"dimension evaluates to {value}; a dimension must be > 0"
            )
    except ExpressionError as exc:
        raise expression_error(exc, expression=text) from exc
    return value


def _inputs(rows: Sequence[PartParameter]) -> list[PartParameterInput]:
    fields = set(PartParameterInput.model_fields)
    return [PartParameterInput(**row.model_dump(include=fields)) for row in rows]


def _index(rows: Sequence[PartParameter], name: str) -> int:
    for index, row in enumerate(rows):
        if row.name == name:
            return index
    raise ParameterNotFound(
        f"the part has no parameter {name!r}",
        details={"parameter": name, "parameters": [row.name for row in rows]},
    )


def infer_unit(
    expression: str, rows: Sequence[PartParameter], current: ParameterUnit
) -> ParameterUnit:
    """The web panel's rule: a row keeps its kind (a new row is a length, as
    in Fusion) unless its formula evaluates to a length or an angle. A formula
    that does not evaluate keeps ``current``; the server gives the verdict."""
    try:
        kind = evaluate(expression, quantities(rows)).kind
    except ExpressionError:
        return current
    return current if kind == UNITLESS else kind


def with_parameter(
    rows: Sequence[PartParameter],
    name: str,
    expression: str,
    *,
    comment: str | None = None,
    unit: ParameterUnit | None = None,
) -> list[PartParameterInput]:
    """The table with *name* set to *expression*: updated in place (same id,
    same position, comment kept unless given) or appended as a new row."""
    table = _inputs(rows)
    try:
        index = _index(rows, name)
    except ParameterNotFound:
        table.append(
            PartParameterInput(
                id=uuid.uuid4(),
                name=name,
                expression=expression,
                unit=unit or infer_unit(expression, rows, LENGTH),
                comment=comment or "",
            )
        )
        return table
    row = table[index]
    table[index] = PartParameterInput.model_validate(
        {
            **row.model_dump(),
            "expression": expression,
            "unit": unit or infer_unit(expression, rows, row.unit),
            "comment": row.comment if comment is None else comment,
        }
    )
    return table


def renamed(
    rows: Sequence[PartParameter], old: str, new: str
) -> list[PartParameterInput]:
    """The table with *old* renamed to *new*, keeping the row's id: the server
    matches ids, and rewrites every formula that reads *old*."""
    table = _inputs(rows)
    index = _index(rows, old)
    table[index] = PartParameterInput.model_validate(
        {**table[index].model_dump(), "name": new}
    )
    return table


def without(rows: Sequence[PartParameter], name: str) -> list[PartParameterInput]:
    """The table with *name* removed."""
    index = _index(rows, name)
    return [row for i, row in enumerate(_inputs(rows)) if i != index]
