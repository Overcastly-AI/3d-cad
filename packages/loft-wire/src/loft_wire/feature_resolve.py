"""Resolve a feature's formulas against its part's parameters (RESEARCH §20).

PART-PARAMETERS step 4. A formula reaches a part's parameters from the
envelope's ``expressions`` (:mod:`loft_wire.feature_expressions`): a JSON
pointer into ``params`` -> a formula. A sketch dimension's formula that names
a parameter is stored there too, at the dimension's value pointer
(:func:`normalize`), and reads its sketch's own dimensions first, then the
parameters (:func:`loft_wire.expr.evaluate_driving_dimensions`). A dimension
formula over its sketch only stays in the dimension's own ``expression``.

So stored ``params`` hold numbers wherever a parameter is involved, and every
path that hands stored params to geometry (the evaluation request, the web's
measure and pick requests, the reference backfill) sends something geometry
can build; ``EvaluatedFeatureInput`` drops ``expressions`` on the way in, so
the rebuild-cache key follows the numbers alone. Documents resolves on every
write, on a parameter PUT and once per evaluation request. Standard library
and pydantic only: documents, the geometry golden harness and ``loft-script``
share it.

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


def _value_field(dim: DimensionLike) -> str:
    return "value_deg" if dim.kind == "angle" else "value_mm"


def _value_pointer(index: int, dim: DimensionLike) -> str:
    """The pointer to a sketch dimension's number."""
    return f"/constraints/{index}/{_value_field(dim)}"


def _dimension_formulas(envelope: FeatureEnvelope) -> dict[int, tuple[str, str | None]]:
    """Driving dimension index -> (formula, pointer). The pointer is set when
    the formula is stored in ``expressions`` (how documents stores one that
    names a parameter, :func:`normalize`); None for the dimension's own
    ``expression``."""
    expressions = envelope.expressions or {}
    out: dict[int, tuple[str, str | None]] = {}
    for index, dim in _dimensions(envelope):
        if not dim.is_driving:
            continue
        pointer = _value_pointer(index, dim)
        if pointer in expressions:
            out[index] = (expressions[pointer], pointer)
        elif dim.expression is not None:
            out[index] = (dim.expression, None)
    return out


def _dimension_pointers(envelope: FeatureEnvelope) -> frozenset[str]:
    return frozenset(
        pointer for _, pointer in _dimension_formulas(envelope).values() if pointer
    )


def _outside_names(envelope: FeatureEnvelope) -> dict[int, frozenset[str]]:
    """Driving dimension index -> the names its formula reads that are NOT
    this sketch's dimensions. Text that does not parse is left to geometry,
    which reports it as it always has (``sketch_invalid``)."""
    names = dimension_names(envelope)
    out: dict[int, frozenset[str]] = {}
    for index, (text, _) in _dimension_formulas(envelope).items():
        try:
            refs = parse(text, names=names, legacy_text=True).references()
        except ExpressionError:
            continue
        if refs - names:
            out[index] = refs - names
    return out


def _legacy_outside(envelope: FeatureEnvelope) -> list[int]:
    """Dimensions whose OWN ``expression`` names something outside the
    sketch: the form :func:`normalize` moves into ``expressions``."""
    outside = _outside_names(envelope)
    return [
        index
        for index, (_, pointer) in _dimension_formulas(envelope).items()
        if pointer is None and index in outside
    ]


def _rebuild[E: BaseModel](envelope: E, params: dict[str, Any], **extra: Any) -> E:
    data = envelope.model_dump(mode="json")
    data.update(params=params, **extra)
    return type(envelope).model_validate(data)


def _params(envelope: FeatureEnvelope) -> dict[str, Any]:
    params: dict[str, Any] = cast(BaseModel, envelope.params).model_dump(mode="json")
    return params


def normalize(envelope: FeatureEnvelope) -> FeatureEnvelope:
    """The stored form: ``params`` hold numbers wherever a parameter is read.

    A sketch dimension whose own ``expression`` names something outside its
    sketch has that formula moved into ``expressions`` at its value pointer
    (its number stays in ``params``), so every path that hands stored params to
    geometry sends a sketch geometry can solve. A formula over the sketch's
    own dimensions stays put. No parameter table is needed.
    """
    moving = _legacy_outside(envelope)
    if not moving:
        return envelope
    params = _params(envelope)
    expressions = dict(envelope.expressions or {})
    dims = dict(_dimensions(envelope))
    for index in moving:
        expressions[_value_pointer(index, dims[index])] = params["constraints"][index][
            "expression"
        ]
        params["constraints"][index]["expression"] = None
    return _rebuild(envelope, params, expressions=expressions)


def parameter_references(envelope: FeatureEnvelope) -> frozenset[str]:
    """Every name this feature reads from the part's parameter table."""
    found: set[str] = set()
    dimension_pointers = _dimension_pointers(envelope)
    for pointer, text in (envelope.expressions or {}).items():
        if pointer in dimension_pointers:
            continue  # counted below, without the sketch's own names
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


def _refused(exc: ValidationError) -> FeatureExpressionError:
    detail = exc.errors()[0]
    where = "/".join(str(part) for part in detail["loc"])
    return FeatureExpressionError(
        f"A resolved value is refused by its field ({where}): {detail['msg']}",
        code=VALUE_INVALID,
    )


def _resolve_dimensions(
    envelope: FeatureEnvelope,
    params: dict[str, Any],
    parameters: Mapping[str, Quantity],
) -> None:
    """Write every driving dimension formula's number into *params*: the
    sketch's own names first, then the parameters (typed)."""
    formulas = _dimension_formulas(envelope)
    constraints = list(cast(list[BaseModel], getattr(envelope.params, "constraints")))  # noqa: B009
    for index, (text, pointer) in formulas.items():
        if pointer is not None:
            constraints[index] = constraints[index].model_copy(
                update={"expression": text}
            )
    try:
        values = evaluate_driving_dimensions(constraints, parameters)
    except ExpressionError as exc:
        raise FeatureExpressionError(str(exc), code=exc.code) from exc
    dims = dict(_dimensions(envelope))
    for index in formulas:
        if index in values:
            params["constraints"][index][_value_field(dims[index])] = values[index]


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
    dimension_pointers = _dimension_pointers(envelope)

    def lookup(name: str) -> Quantity:
        if name not in parameters:
            raise ExpressionReferenceError(f"unknown parameter {name!r}")
        return parameters[name]

    for pointer, text in (envelope.expressions or {}).items():
        if pointer in dimension_pointers:
            continue  # a sketch dimension: resolved with its sketch below
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
    if dimension_pointers or _outside_names(envelope):
        _resolve_dimensions(envelope, params, parameters)
    try:
        return _rebuild(envelope, params)
    except ValidationError as exc:
        raise _refused(exc) from exc


def for_geometry(envelope: FeatureEnvelope) -> FeatureEnvelope:
    """What geometry receives: ``expressions`` cleared (every number is
    already in ``params``), and a dimension whose own formula names a parameter
    (a tree stored before :func:`normalize`) reduced to its number. A formula
    over the sketch's own dimensions stays. Untouched when there is nothing to
    strip."""
    legacy = _legacy_outside(envelope)
    if envelope.expressions is None and not legacy:
        return envelope
    if not legacy:
        return envelope.model_copy(update={"expressions": None})
    params = _params(envelope)
    for index in legacy:
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
    own = dimension_names(envelope)
    applicable = {old: new for old, new in renames.items() if old not in own}
    dimension_pointers = _dimension_pointers(envelope)
    expressions = envelope.expressions
    if expressions is not None:
        expressions = {
            pointer: _checked(
                rename_references(text, applicable, legacy_text=True)
                if pointer in dimension_pointers
                else rename_references(text, renames),
                pointer,
            )
            for pointer, text in expressions.items()
        }
    params = _params(envelope)
    legacy = False
    for index, (text, pointer) in _dimension_formulas(envelope).items():
        if pointer is None:
            renamed = rename_references(text, applicable, legacy_text=True)
            if renamed != text:
                where = f"/constraints/{index}/expression"
                params["constraints"][index]["expression"] = _checked(renamed, where)
                legacy = True
    if not legacy and expressions == envelope.expressions:
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
    "normalize",
    "parameter_references",
    "parameter_values",
    "rename_parameters",
    "resolve_feature",
    "uses_parameters",
]
