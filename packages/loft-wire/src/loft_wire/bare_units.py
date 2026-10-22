"""Bare numbers in a non-mm part (FORMULA-BARE-UNIT, RESEARCH §20).

The grammar reads a bare number as mm, so in an inch part ``wall + 1/2``
added half a millimetre. Fusion reads a bare number in the document unit.
Loft gets Fusion's reading without a grammar version or a per-part switch:
documents writes the part's unit into the text of every formula a write
ENTERS (``wall + 1/2`` is stored as ``wall + 1 in/2``,
:func:`loft_wire.expr.bare_lengths`), so stored text keeps one meaning and a
later unit change moves nothing. Only where Fusion reads a number as a
length: a term added to, subtracted from or compared with a length, or a
length field's whole value. Factors, divisors, counts and angles stay plain.

A formula the write leaves as stored (same pointer, same text; a sketch
dimension's text that the stored sketch already has; a parameter row with
the same id and text) is never rewritten: it is reported by
:func:`feature_warnings` / :func:`parameter_warnings` with its fix, and the
fix is an ordinary edit. In an mm part nothing here does anything.
"""

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, cast

from loft_wire.expr import (
    ANGLE,
    LENGTH,
    UNITLESS,
    UNITS,
    BareLengths,
    DimensionLike,
    ExpressionError,
    ExpressionLimitError,
    Kind,
    NamedExpression,
    Quantity,
    bare_lengths,
    coerce,
    evaluate_driving_dimensions,
    evaluate_parameters,
    parse,
)
from loft_wire.feature_expressions import PointerError, leaf_kind, locate, parse_pointer
from loft_wire.feature_resolve import FeatureExpressionError
from loft_wire.features import AuthoredEnvelope
from loft_wire.formula_warning import EXPRESSION_BARE_MM, FormulaWarning
from loft_wire.parameters import ParameterTableError, PartParameterInput

_LENGTH_KEYS = frozenset({"x", "y", "z", "radius"})


def _field_kind(params: Any, pointer: str) -> Kind | None:
    """What the field at *pointer* measures, or None when it is not one a
    formula may drive. Named by its field: a ``*_mm`` input a client sent as
    a JSON integer is still a length."""
    try:
        tokens = parse_pointer(pointer)
        _, _, leaf = locate(params, tokens)
        kind = leaf_kind(tokens, leaf)
    except PointerError:
        return None
    name = tokens[-1]
    if name.endswith("_mm") or name in _LENGTH_KEYS:
        return LENGTH
    if name.endswith("_deg"):
        return ANGLE
    return UNITLESS if kind == "int" else kind


def _dimensions(envelope: AuthoredEnvelope) -> list[tuple[int, DimensionLike]]:
    if envelope.type != "sketch":
        return []
    constraints = cast(list[object], getattr(envelope.params, "constraints", []))
    return [(i, c) for i, c in enumerate(constraints) if isinstance(c, DimensionLike)]


def _dimension_scope(
    envelope: AuthoredEnvelope, kinds: Mapping[str, Kind]
) -> tuple[frozenset[str], dict[str, Kind]]:
    """A sketch's own names, and every name's kind: a dimension is a length in
    mm (an angle dimension an angle), and wins over a parameter."""
    dims = _dimensions(envelope)
    names = frozenset(c.name for _, c in dims if c.name is not None)
    scope = dict(kinds)
    for _, dim in dims:
        if dim.name is not None:
            scope[dim.name] = ANGLE if dim.kind == "angle" else LENGTH
    return names, scope


def _kinds(parameters: Mapping[str, Quantity]) -> dict[str, Kind]:
    return {name: q.kind for name, q in parameters.items()}


def _fixed(
    text: str, unit: str, field: Kind, scope: Mapping[str, Kind], **kw: Any
) -> str:
    found = bare_lengths(text, unit, field, scope, **kw)
    return text if found is None else found.text


def write_units[E: AuthoredEnvelope](
    envelope: E,
    unit: str,
    parameters: Mapping[str, Quantity],
    stored: AuthoredEnvelope | None = None,
) -> E:
    """*envelope* with the part's *unit* written into every formula this write
    enters; a formula left as *stored* keeps its text. The same object when
    nothing changes (always in an mm part). Raises
    :class:`~loft_wire.feature_resolve.FeatureExpressionError` when the unit
    takes a formula past the length cap."""
    if unit == "mm":
        return envelope
    kinds = _kinds(parameters)
    update: dict[str, Any] = {}
    before = (stored.expressions if stored is not None else None) or {}
    expressions = dict(envelope.expressions or {})
    params: Any = (
        cast(Any, envelope.params).model_dump(mode="json") if expressions else {}
    )
    for pointer, text in expressions.items():
        if before.get(pointer) == text:
            continue
        field = _field_kind(params, pointer)
        if field is None:
            continue
        try:
            expressions[pointer] = _fixed(text, unit, field, kinds)
        except ExpressionLimitError as exc:
            raise FeatureExpressionError(
                f"{pointer}: {exc}", code=exc.code, pointer=pointer
            ) from exc
    if expressions != (envelope.expressions or {}):
        update["expressions"] = expressions
    dims = _dimensions(envelope)
    if dims:
        kept = Counter(
            dim.expression
            for _, dim in (_dimensions(stored) if stored is not None else [])
            if dim.expression is not None
        )
        names, scope = _dimension_scope(envelope, kinds)
        constraints = list(cast(list[Any], getattr(envelope.params, "constraints")))  # noqa: B009
        changed = False
        for index, dim in dims:
            text = dim.expression
            if text is None or not dim.is_driving:
                continue
            if kept[text] > 0:
                kept[text] -= 1
                continue
            field = ANGLE if dim.kind == "angle" else LENGTH
            try:
                fixed = _fixed(text, unit, field, scope, names=names, legacy_text=True)
            except ExpressionLimitError as exc:
                pointer = f"/constraints/{index}/expression"
                raise FeatureExpressionError(
                    f"{pointer}: {exc}", code=exc.code, pointer=pointer
                ) from exc
            if fixed != text:
                constraints[index] = constraints[index].model_copy(
                    update={"expression": fixed}
                )
                changed = True
        if changed:
            # The unit moves the value: store what the new text gives, for the
            # rewritten dimension and every formula reading it. A sketch that
            # reads no parameter is not re-resolved later, so this is where
            # its value_mm stops being the client's mm reading. A sketch whose
            # dimensions do not evaluate (a division by zero, a cycle) is
            # refused, as a parameter-reading one is: storing the text with
            # the client's mm values would build what the text does not say.
            try:
                values = evaluate_driving_dimensions(constraints, parameters)
            except ExpressionError as exc:
                raise FeatureExpressionError(str(exc), code=exc.code) from exc
            for index, dim in dims:
                if index in values and constraints[index].expression is not None:
                    field = "value_deg" if dim.kind == "angle" else "value_mm"
                    constraints[index] = constraints[index].model_copy(
                        update={field: values[index]}
                    )
            update["params"] = cast(Any, envelope.params).model_copy(
                update={"constraints": constraints}
            )
    return envelope.model_copy(update=update) if update else envelope


def _format(value: float | None, field: Kind, unit: str) -> str:
    if value is None:
        return "no value"
    if field == LENGTH:
        return f"{value / UNITS[unit][0]:.6g} {unit} ({value:.6g} mm)"
    if field == ANGLE:
        return f"{value:.6g} deg"
    return f"{value:.6g}"


def _warning(
    found: BareLengths,
    text: str,
    unit: str,
    field: Kind,
    values: tuple[float | None, float | None],
    *,
    pointer: str | None = None,
    parameter_id: uuid.UUID | None = None,
) -> FormulaWarning:
    terms = ", ".join(f"`{literal}`" for literal in found.literals)
    value, fixed_value = values
    return FormulaWarning(
        code=EXPRESSION_BARE_MM,
        message=f"{terms} in `{text}` is read as mm, so it gives "
        f"{_format(value, field, unit)}. Read as {unit} (`{found.text}`), it "
        f"gives {_format(fixed_value, field, unit)}.",
        pointer=pointer,
        parameter_id=parameter_id,
        expression=text,
        literals=list(found.literals),
        fixed_expression=found.text,
        value=value,
        fixed_value=fixed_value,
    )


def _evaluated(
    text: str, field: Kind, parameters: Mapping[str, Quantity]
) -> float | None:
    try:
        q = parse(text).evaluate(parameters.__getitem__)
        return coerce(q, field)
    except (ExpressionError, KeyError):
        return None


def _dimension_value(
    constraints: list[Any], index: int, text: str, parameters: Mapping[str, Quantity]
) -> float | None:
    trial = list(constraints)
    trial[index] = trial[index].model_copy(update={"expression": text})
    try:
        return evaluate_driving_dimensions(trial, parameters).get(index)
    except (ExpressionError, KeyError):
        return None


def feature_warnings(
    envelope: AuthoredEnvelope, unit: str, parameters: Mapping[str, Quantity]
) -> list[FormulaWarning]:
    """An ``expression_bare_mm`` warning for every formula of this stored
    feature whose bare terms a part in *unit* reads as mm. Empty in mm."""
    if unit == "mm":
        return []
    kinds = _kinds(parameters)
    out: list[FormulaWarning] = []
    params = cast(Any, envelope.params).model_dump(mode="json")
    for pointer, text in (envelope.expressions or {}).items():
        field = _field_kind(params, pointer)
        found = _found(text, unit, field, kinds)
        if field is None or found is None:
            continue
        values = (
            _evaluated(text, field, parameters),
            _evaluated(found.text, field, parameters),
        )
        out.append(_warning(found, text, unit, field, values, pointer=pointer))
    dims = _dimensions(envelope)
    if dims:
        names, scope = _dimension_scope(envelope, kinds)
        constraints = list(cast(list[Any], getattr(envelope.params, "constraints")))  # noqa: B009
        for index, dim in dims:
            text = dim.expression
            if text is None or not dim.is_driving:
                continue
            field = ANGLE if dim.kind == "angle" else LENGTH
            found = _found(text, unit, field, scope, names=names, legacy_text=True)
            if found is None:
                continue
            values = (
                _dimension_value(constraints, index, text, parameters),
                _dimension_value(constraints, index, found.text, parameters),
            )
            pointer = f"/constraints/{index}/expression"
            out.append(_warning(found, text, unit, field, values, pointer=pointer))
    return out


def _found(
    text: str, unit: str, field: Kind | None, scope: Mapping[str, Kind], **kw: Any
) -> BareLengths | None:
    if field is None:
        return None
    try:
        return bare_lengths(text, unit, field, scope, **kw)
    except ExpressionLimitError:
        return None  # a fix that cannot be stored is not offered


def write_parameter_units(
    rows: Sequence[PartParameterInput],
    stored: Sequence[Mapping[str, Any]],
    unit: str,
) -> list[PartParameterInput]:
    """*rows* with the part's *unit* written into every expression this table
    PUT enters; a row whose id and expression are as stored keeps its text.
    Raises :class:`~loft_wire.parameters.ParameterTableError` past the cap."""
    if unit == "mm":
        return list(rows)
    before = {str(row["id"]): row["expression"] for row in stored}
    kinds: dict[str, Kind] = {row.name: row.unit for row in rows}
    out: list[PartParameterInput] = []
    for row in rows:
        text = row.expression
        if before.get(str(row.id)) != text:
            try:
                text = _fixed(text, unit, row.unit, kinds)
            except ExpressionLimitError as exc:
                raise ParameterTableError(
                    f"Parameter {row.name!r}: {exc}",
                    code=exc.code,
                    parameter=row.name,
                ) from exc
        out.append(
            row
            if text == row.expression
            else row.model_copy(update={"expression": text})
        )
    return out


def parameter_warnings(
    rows: Sequence[Mapping[str, Any]], unit: str
) -> list[FormulaWarning]:
    """An ``expression_bare_mm`` warning for every stored parameter row whose
    bare terms a part in *unit* reads as mm. Empty in mm."""
    if unit == "mm":
        return []
    kinds: dict[str, Kind] = {str(row["name"]): row["unit"] for row in rows}
    table = [
        NamedExpression(str(row["name"]), str(row["expression"]), row["unit"])
        for row in rows
    ]
    out: list[FormulaWarning] = []
    for index, row in enumerate(rows):
        text = str(row["expression"])
        field: Kind = row["unit"]
        found = _found(text, unit, field, kinds)
        if found is None:
            continue
        trial = list(table)
        trial[index] = NamedExpression(table[index].name, found.text, field)
        try:
            fixed_value: float | None = evaluate_parameters(trial)[
                table[index].name
            ].value
        except ExpressionError:
            fixed_value = None
        values = (float(row["value"]), fixed_value)
        parameter_id = uuid.UUID(str(row["id"]))
        out.append(
            _warning(found, text, unit, field, values, parameter_id=parameter_id)
        )
    return out


__all__ = [
    "feature_warnings",
    "parameter_warnings",
    "write_parameter_units",
    "write_units",
]
