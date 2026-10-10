"""Where a ``.loft`` 1.2 tree keeps a sketch dimension's parameter formula.

PART-PARAMETERS step 5 (RESEARCH §20, docs/FILE-FORMAT.md). In storage a
sketch dimension's formula stays in the dimension's own ``expression``, with
the resolved number beside it in ``value_mm``/``value_deg``. A formula that
names anything OUTSIDE its sketch (a part parameter) cannot be written there in
a file: a Loft from before parameters reads ``expression`` as a formula over
the sketch's own dimensions, and ``= W`` would rebuild as ``sketch_invalid:
unknown dimension name 'W'`` instead of the number.

So :func:`move_out` writes each such formula beside the feature, in
``dimension_expressions`` (a JSON pointer to the dimension's ``expression`` ->
the formula), and leaves ``expression`` null in ``params``, where the resolved
number stands. The rule is the geometry boundary's
(:func:`loft_wire.feature_expressions.outside_dimension_names`), decided from
the sketch alone; a formula over the sketch's own dimensions stays where it is,
since every Loft evaluates it. :func:`move_in` puts each formula back on read.
An older reader ignores the unknown key and imports the numbers.

The pointers address constraints by position. That is safe here and nowhere
else: a file is one snapshot, written and read whole, never edited between.
"""

import re
from types import SimpleNamespace
from typing import Any, Final, cast

from pydantic import TypeAdapter, ValidationError

from loft_wire.expr import MAX_EXPRESSION_LENGTH
from loft_wire.feature_expressions import outside_dimension_names
from loft_wire.sketch import MAX_SKETCH_CONSTRAINTS, SketchConstraint

#: The per-feature key in ``tree.json`` (format 1.2).
DIMENSION_EXPRESSIONS_KEY: Final = "dimension_expressions"

_POINTER_RE: Final = re.compile(r"^/constraints/(0|[1-9][0-9]{0,8})/expression$")
_DIMENSION_VALUE_KEYS: Final = ("value_mm", "value_deg")
_CONSTRAINTS: Final = TypeAdapter(list[SketchConstraint])
#: The most of a file's pointer an error repeats back.
_ECHO: Final = 64


class DimensionFormulaError(ValueError):
    """A ``dimension_expressions`` entry that does not fit its sketch."""

    def __init__(self, message: str, *, pointer: str | None = None) -> None:
        super().__init__(message)
        self.pointer = pointer


def _constraints_of(params: object) -> object:
    """A params object's ``constraints``, or None."""
    if not isinstance(params, dict):
        return None
    return cast(dict[str, Any], params).get("constraints")


def _pointer(index: int) -> str:
    return f"/constraints/{index}/expression"


def move_out(feature: dict[str, Any]) -> dict[str, Any]:
    """The encoded feature with every sketch formula that names a parameter
    moved into ``dimension_expressions``. Returns *feature* itself when there
    is nothing to move (any non-sketch, or a sketch whose constraints do not
    validate, which no stored part holds)."""
    if feature.get("type") != "sketch":
        return feature
    params = feature.get("params")
    constraints = _constraints_of(params)
    if not isinstance(constraints, list):
        return feature
    try:
        typed = _CONSTRAINTS.validate_python(constraints)
    except ValidationError:
        return feature
    outside = outside_dimension_names(
        SimpleNamespace(type="sketch", params=SimpleNamespace(constraints=typed))
    )
    if not outside:
        return feature
    raw = cast(list[Any], constraints)
    moved: dict[str, str] = {}
    kept: list[Any] = []
    for index, constraint in enumerate(raw):
        if index in outside:
            entry = cast(dict[str, Any], constraint)
            moved[_pointer(index)] = cast(str, entry["expression"])
            constraint = {**entry, "expression": None}
        kept.append(constraint)
    return {
        **feature,
        "params": {**cast(dict[str, Any], params), "constraints": kept},
        DIMENSION_EXPRESSIONS_KEY: moved,
    }


def move_in(feature: dict[str, Any]) -> None:
    """Put each ``dimension_expressions`` formula back on its dimension, in
    place, and drop the key. Raises :class:`DimensionFormulaError` for an
    entry that is not a formula for a formula-less dimension of this sketch."""
    if DIMENSION_EXPRESSIONS_KEY not in feature:
        return
    moved = feature.pop(DIMENSION_EXPRESSIONS_KEY)
    if moved is None:
        return
    if not isinstance(moved, dict):
        raise DimensionFormulaError("dimension_expressions is not an object")
    entries = cast(dict[str, Any], moved)
    if len(entries) > MAX_SKETCH_CONSTRAINTS:
        raise DimensionFormulaError("dimension_expressions has too many entries")
    params = feature.get("params")
    constraints = _constraints_of(params)
    if feature.get("type") != "sketch" or not isinstance(constraints, list):
        raise DimensionFormulaError("dimension_expressions on a feature with no sketch")
    raw = cast(list[Any], constraints)
    for key, text in entries.items():
        match = _POINTER_RE.match(key)
        pointer = key if len(key) <= _ECHO else f"{key[: _ECHO - 3]}..."
        index = int(match.group(1)) if match is not None else len(raw)
        target = raw[index] if index < len(raw) else None
        if not isinstance(target, dict):
            raise DimensionFormulaError(
                f"{pointer} is not a sketch dimension's expression", pointer=pointer
            )
        dimension = cast(dict[str, Any], target)
        if not any(key in dimension for key in _DIMENSION_VALUE_KEYS):
            raise DimensionFormulaError(
                f"{pointer} is not a dimension", pointer=pointer
            )
        if dimension.get("expression") is not None:
            raise DimensionFormulaError(
                f"{pointer} already holds a formula", pointer=pointer
            )
        if not isinstance(text, str) or not 0 < len(text) <= MAX_EXPRESSION_LENGTH:
            raise DimensionFormulaError(
                f"{pointer}: a formula is 1 to {MAX_EXPRESSION_LENGTH} characters",
                pointer=pointer,
            )
        dimension["expression"] = text


__all__ = [
    "DIMENSION_EXPRESSIONS_KEY",
    "DimensionFormulaError",
    "move_in",
    "move_out",
]
