"""Resolve a feature's formulas against its part's parameters (RESEARCH §20).

PART-PARAMETERS step 4. Two kinds of formula reach a part's parameters:

* the envelope's ``expressions`` (:mod:`loft_wire.feature_expressions`), a JSON
  pointer into ``params`` -> a formula over the parameters;
* a sketch's driving-dimension ``expression``, which reads the sketch's own
  dimensions first and then the parameters
  (:func:`loft_wire.expr.evaluate_driving_dimensions`).

Documents resolves both on every write (the numbers are stored in ``params``)
and once per evaluation request, where :func:`for_geometry` then strips every
formula that names a parameter, so geometry receives numbers only and its
rebuild-cache keys follow the resolved values. Standard library and pydantic
only: documents, the geometry golden harness and ``loft-script`` share it.

A feature that names no parameter and carries no ``expressions`` is returned
untouched (the same object), so every existing tree keeps its bytes.
"""

import copy
from collections.abc import Iterable, Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, ValidationError

from loft_wire.expr import (
    DimensionLike,
    ExpressionError,
    ExpressionNameError,
    ExpressionReferenceError,
    Quantity,
    coerce,
    coerce_int,
    evaluate_driving_dimensions,
    parse,
    rename_references,
)
from loft_wire.feature_expressions import leaf_kind, locate, parse_pointer
from loft_wire.feature_input import PARAMETER_UNRESOLVED, PARAMETER_VALUE_INVALID
from loft_wire.features import FeatureEnvelope, FeatureError

#: The code a resolved value that its field refuses is reported with at write.
VALUE_INVALID: Final = PARAMETER_VALUE_INVALID


class FeatureExpressionError(ValueError):
    """Why a feature's formulas do not resolve. ``code`` is the expression
    error's stable id, or ``parameter_value_invalid`` when the number is fine
    but its field refuses it; ``pointer`` names the field when one does."""

    def __init__(self, message: str, *, code: str, pointer: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.pointer = pointer

    def input_error(self) -> FeatureError:
        """The evaluation-request ``input_error`` this failure becomes: a name
        with no value is ``parameter_unresolved``, anything else is
        ``parameter_value_invalid``."""
        unresolved = self.code == ExpressionReferenceError.code
        return FeatureError(
            code=PARAMETER_UNRESOLVED if unresolved else PARAMETER_VALUE_INVALID,
            message=self.message,
        )


def parameter_values(rows: Iterable[Mapping[str, Any]]) -> dict[str, Quantity]:
    """name -> typed value, from stored ``PartParameter`` rows."""
    return {
        str(row["name"]): Quantity(float(row["value"]), row["unit"]) for row in rows
    }


def _dimensions(envelope: FeatureEnvelope) -> list[tuple[int, DimensionLike]]:
    if envelope.type != "sketch":
        return []
    constraints = cast(list[object], getattr(envelope.params, "constraints", []))
    return [(i, c) for i, c in enumerate(constraints) if isinstance(c, DimensionLike)]


def dimension_names(envelope: FeatureEnvelope) -> frozenset[str]:
    """The names of a sketch's dimensions (empty for any other feature)."""
    return frozenset(c.name for _, c in _dimensions(envelope) if c.name is not None)


def _outside_names(envelope: FeatureEnvelope) -> dict[int, frozenset[str]]:
    """Constraint index -> the names its expression reads that are NOT this
    sketch's dimensions. Text that does not parse is left to geometry, which
    reports it as it always has (``sketch_invalid``)."""
    names = dimension_names(envelope)
    out: dict[int, frozenset[str]] = {}
    for index, dim in _dimensions(envelope):
        if dim.expression is None or not dim.is_driving:
            continue
        try:
            refs = parse(dim.expression, names=names, legacy_text=True).references()
        except ExpressionError:
            continue
        if refs - names:
            out[index] = refs - names
    return out


def parameter_references(envelope: FeatureEnvelope) -> frozenset[str]:
    """Every name this feature reads from the part's parameter table."""
    found: set[str] = set()
    for text in (envelope.expressions or {}).values():
        try:
            found |= parse(text).references()
        except ExpressionError:
            continue
    for refs in _outside_names(envelope).values():
        found |= refs
    return frozenset(found)


def uses_parameters(envelope: FeatureEnvelope) -> bool:
    """Does this feature carry a formula resolution has to look at?"""
    return envelope.expressions is not None or bool(_outside_names(envelope))


def check_dimension_names(envelope: FeatureEnvelope, parameters: Iterable[str]) -> None:
    """A sketch dimension may not take a parameter's name."""
    clash = sorted(dimension_names(envelope) & set(parameters))
    if clash:
        raise FeatureExpressionError(
            f"Sketch dimension {clash[0]!r} has a parameter's name; rename one.",
            code=ExpressionNameError.code,
        )


def _rebuild[E: BaseModel](envelope: E, params: dict[str, Any], **extra: Any) -> E:
    data = envelope.model_dump(mode="json")
    data.update(params=params, **extra)
    return type(envelope).model_validate(data)


def resolve_feature(
    envelope: FeatureEnvelope, parameters: Mapping[str, Quantity]
) -> FeatureEnvelope:
    """The feature as stored: every formula evaluated, its number written at
    its pointer (and into each sketch dimension's value), formulas kept.

    Raises :class:`FeatureExpressionError`.
    """
    if not uses_parameters(envelope):
        return envelope
    params = cast(BaseModel, envelope.params).model_dump(mode="json")

    def lookup(name: str) -> Quantity:
        if name not in parameters:
            raise ExpressionReferenceError(f"unknown parameter {name!r}")
        return parameters[name]

    for pointer, text in (envelope.expressions or {}).items():
        try:
            tokens = parse_pointer(pointer)
            parent, key, leaf = locate(params, tokens)
            kind = leaf_kind(tokens, leaf)
            q = parse(text).evaluate(lookup)
            who = f"expression for {pointer}"
            parent[key] = coerce_int(q, who) if kind == "int" else coerce(q, kind, who)
        except ExpressionError as exc:
            raise FeatureExpressionError(
                f"{pointer} = {text!r}: {exc}", code=exc.code, pointer=pointer
            ) from exc
        except ValueError as exc:  # a pointer the validator let through, re-checked
            raise FeatureExpressionError(
                f"{pointer}: {exc}", code=VALUE_INVALID, pointer=pointer
            ) from exc
    if _outside_names(envelope):
        constraints = cast(list[object], getattr(envelope.params, "constraints"))  # noqa: B009
        try:
            values = evaluate_driving_dimensions(constraints, parameters)
        except ExpressionError as exc:
            raise FeatureExpressionError(str(exc), code=exc.code) from exc
        for index, dim in _dimensions(envelope):
            if index in values and dim.expression is not None:
                field = "value_deg" if dim.kind == "angle" else "value_mm"
                params["constraints"][index][field] = values[index]
    try:
        return _rebuild(envelope, params)
    except ValidationError as exc:
        detail = exc.errors()[0]
        where = "/".join(str(part) for part in detail["loc"])
        raise FeatureExpressionError(
            f"A resolved value is refused by its field ({where}): {detail['msg']}",
            code=VALUE_INVALID,
        ) from exc


def for_geometry(envelope: FeatureEnvelope) -> FeatureEnvelope:
    """What geometry receives: ``expressions`` cleared, and every sketch
    dimension that reads a parameter reduced to its (resolved) number. A
    dimension that reads only other dimensions keeps its formula, which then
    reads their numbers. Untouched when there is nothing to strip."""
    outside = _outside_names(envelope)
    if envelope.expressions is None and not outside:
        return envelope
    if not outside:
        return envelope.model_copy(update={"expressions": None})
    params = cast(BaseModel, envelope.params).model_dump(mode="json")
    for index in outside:
        params["constraints"][index]["expression"] = None
    return _rebuild(envelope, params, expressions=None)


def evaluation_input(
    envelope: FeatureEnvelope, parameters: Mapping[str, Quantity]
) -> tuple[FeatureEnvelope, FeatureError | None]:
    """The feature for an evaluation request, and its ``input_error``.

    Resolved and stripped on success. On failure the stored (last good)
    numbers go to geometry, stripped, with the error; geometry then builds
    nothing for the feature.
    """
    if not uses_parameters(envelope):
        return envelope, None
    try:
        return for_geometry(resolve_feature(envelope, parameters)), None
    except FeatureExpressionError as exc:
        return for_geometry(envelope), exc.input_error()


def rename_parameters(
    envelope: FeatureEnvelope, renames: Mapping[str, str]
) -> FeatureEnvelope:
    """The feature with every reference to a renamed parameter rewritten,
    token by token, in ``expressions`` and in sketch dimension formulas (a
    sketch's own dimension names are never touched)."""
    if not renames:
        return envelope
    expressions = envelope.expressions
    if expressions is not None:
        expressions = {
            pointer: rename_references(text, renames)
            for pointer, text in expressions.items()
        }
    outside = _outside_names(envelope)
    changed = [
        index for index, refs in outside.items() if any(r in renames for r in refs)
    ]
    if not changed:
        if expressions == envelope.expressions:
            return envelope
        return envelope.model_copy(update={"expressions": expressions})
    own = dimension_names(envelope)
    applicable = {old: new for old, new in renames.items() if old not in own}
    params = copy.deepcopy(cast(BaseModel, envelope.params).model_dump(mode="json"))
    for index in changed:
        item = params["constraints"][index]
        item["expression"] = rename_references(
            item["expression"], applicable, legacy_text=True
        )
    return _rebuild(envelope, params, expressions=expressions)


__all__ = [
    "FeatureExpressionError",
    "check_dimension_names",
    "dimension_names",
    "evaluation_input",
    "for_geometry",
    "parameter_references",
    "parameter_values",
    "rename_parameters",
    "resolve_feature",
    "uses_parameters",
]
