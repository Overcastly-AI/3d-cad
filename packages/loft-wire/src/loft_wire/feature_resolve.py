"""Resolve a feature's formulas against its part's parameters (RESEARCH §20).

PART-PARAMETERS step 4. Two kinds of formula reach a part's parameters:

* the envelope's ``expressions`` (:mod:`loft_wire.feature_expressions`), a JSON
  pointer into ``params`` -> a formula over the parameters (never into a
  sketch's entities or constraints);
* a sketch's driving-dimension ``expression``, which reads the sketch's own
  dimensions first and then the parameters
  (:func:`loft_wire.expr.evaluate_driving_dimensions`). It stays in the
  dimension, so a client that saves the sketch's params carries it untouched.

Documents resolves both on every write, on a parameter PUT and once per
evaluation request, and stores every number in ``params`` (a dimension's
``value_mm``/``value_deg`` beside its formula). Geometry is sent numbers only:
:func:`~loft_wire.feature_expressions.strip_for_geometry`, applied to every
``EvaluatedFeatureInput``, drops ``expressions`` and each dimension formula
that names a parameter, so the resolved value stands and a request the web
builds from ``GET /features`` keys the rebuild cache like documents' own.
Standard library and pydantic only: documents, the geometry golden harness and
``loft-script`` share it.

A feature that names no parameter and carries no ``expressions`` is returned
untouched (the same object), so every existing tree keeps its bytes.
"""

from collections.abc import Iterable, Mapping
from typing import Any, Final, cast

from pydantic import BaseModel, ValidationError

from loft_wire.expr import (
    MAX_EXPRESSION_LENGTH,
    DimensionLike,
    ExpressionError,
    ExpressionLimitError,
    ExpressionNameError,
    ExpressionReferenceError,
    Quantity,
    coerce,
    coerce_int,
    evaluate_driving_dimensions,
    parse,
    rename_references,
)
from loft_wire.feature_expressions import (
    leaf_kind,
    locate,
    outside_dimension_names,
    parse_pointer,
    strip_for_geometry,
)
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


def parameter_references(envelope: FeatureEnvelope) -> frozenset[str]:
    """Every name this feature reads from the part's parameter table."""
    found: set[str] = set()
    for text in (envelope.expressions or {}).values():
        try:
            found |= parse(text).references()
        except ExpressionError:
            continue
    for refs in outside_dimension_names(envelope).values():
        found |= refs
    return frozenset(found)


def uses_parameters(envelope: FeatureEnvelope) -> bool:
    """Does this feature carry a formula resolution has to look at?"""
    return envelope.expressions is not None or bool(outside_dimension_names(envelope))


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


def _params(envelope: FeatureEnvelope) -> dict[str, Any]:
    params: dict[str, Any] = cast(BaseModel, envelope.params).model_dump(mode="json")
    return params


def _refused(exc: ValidationError) -> FeatureExpressionError:
    detail = exc.errors()[0]
    where = "/".join(str(part) for part in detail["loc"])
    return FeatureExpressionError(
        f"A resolved value is refused by its field ({where}): {detail['msg']}",
        code=VALUE_INVALID,
    )


def resolve_feature(
    envelope: FeatureEnvelope, parameters: Mapping[str, Quantity]
) -> FeatureEnvelope:
    """The feature as stored: every formula evaluated, its number written at
    its pointer (and into each sketch dimension's value), formulas kept.

    Raises :class:`FeatureExpressionError`.
    """
    if not uses_parameters(envelope):
        return envelope
    params = _params(envelope)

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
    if outside_dimension_names(envelope):
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
        raise _refused(exc) from exc


def for_geometry(envelope: FeatureEnvelope) -> FeatureEnvelope:
    """What geometry receives (:func:`~loft_wire.feature_expressions.
    strip_for_geometry`, the rule every ``EvaluatedFeatureInput`` applies)."""
    return cast(FeatureEnvelope, strip_for_geometry(envelope))


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


def _checked(text: str, pointer: str) -> str:
    """A renamed formula, or the refusal to store one past the length cap."""
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise FeatureExpressionError(
            f"The rename makes the formula at {pointer} {len(text)} characters "
            f"long; the limit is {MAX_EXPRESSION_LENGTH}. Choose a shorter name.",
            code=ExpressionLimitError.code,
            pointer=pointer,
        )
    return text


def rename_parameters(
    envelope: FeatureEnvelope, renames: Mapping[str, str]
) -> FeatureEnvelope:
    """The feature with every reference to a renamed parameter rewritten,
    token by token, in ``expressions`` and in sketch dimension formulas (a
    sketch's own dimension names are never touched).

    Every rewritten formula is checked as a written one is: one pushed past the
    256-character cap, or an envelope that no longer validates, raises
    :class:`FeatureExpressionError` rather than storing what cannot load.
    """
    if not renames:
        return envelope
    expressions = envelope.expressions
    if expressions is not None:
        expressions = {
            pointer: _checked(rename_references(text, renames), pointer)
            for pointer, text in expressions.items()
        }
    own = dimension_names(envelope)
    applicable = {old: new for old, new in renames.items() if old not in own}
    params = _params(envelope)
    dims_changed = False
    for index in outside_dimension_names(envelope):
        item = params["constraints"][index]
        renamed = rename_references(item["expression"], applicable, legacy_text=True)
        if renamed != item["expression"]:
            item["expression"] = _checked(renamed, f"/constraints/{index}/expression")
            dims_changed = True
    if not dims_changed and expressions == envelope.expressions:
        return envelope
    try:
        return _rebuild(envelope, params, expressions=expressions)
    except ValidationError as exc:
        raise _refused(exc) from exc


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
