"""The ``expressions`` field of a feature envelope (PART-PARAMETERS step 4).

Kept out of :mod:`loft_wire.features` (FILE-SIZE-RATCHET); that module owns the
field, ``FeatureEnvelopeBase.expressions``, and takes its definition and its
check from here. Resolution against a part's parameter table lives in
:mod:`loft_wire.feature_resolve` (RESEARCH §20).

``expressions`` maps a JSON pointer (RFC 6901) into the feature's ``params``
to the formula that drives that number: ``{"/distance_mm": "D"}``. Documents
evaluates every formula on each write and stores the resolved number at the
pointer, so ``params`` always holds numbers and geometry never sees a formula.

A pointer must land on an int or float leaf whose unit the field name says:
``*_deg`` is an angle (degrees), ``*_mm`` and point/vector coordinates are
lengths (mm), ``k_factor`` and ``relief_ratio`` are plain numbers, and an int
field takes a whole plain number. Anything else (a string, an enum, a picked
reference's measured signature, an area) is refused at validation, a 422.
"""

from typing import Annotated, Any, Final, Literal, cast

from pydantic import AfterValidator, Field, StringConstraints

from loft_wire.expr import MAX_EXPRESSION_LENGTH
from loft_wire.twist import is_none

#: Most expressions one feature may carry, and the longest pointer.
MAX_FEATURE_EXPRESSIONS: Final = 64
MAX_POINTER_LENGTH: Final = 256

#: What a driven leaf holds: mm, degrees, a plain float, or a whole number.
FieldKind = Literal["length", "angle", "unitless", "int"]

_LENGTH_KEYS: Final = frozenset({"x", "y", "z", "radius"})
_UNITLESS_KEYS: Final = frozenset({"k_factor", "relief_ratio"})


class PointerError(ValueError):
    """A pointer that does not name a drivable number of these params."""


def parse_pointer(pointer: str) -> list[str]:
    """RFC 6901 reference tokens of ``pointer`` (``~1`` is ``/``, ``~0`` is ``~``)."""
    if not pointer.startswith("/"):
        raise PointerError(f"pointer {pointer!r} must start with '/'")
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]


def locate(params: Any, tokens: list[str]) -> tuple[Any, str | int, Any]:
    """``(container, key, leaf)`` for ``tokens`` in a params JSON tree."""
    parent: Any = None
    key: str | int = ""
    node: Any = params
    for token in tokens:
        parent = node
        if isinstance(node, dict):
            fields = cast(dict[str, Any], node)
            if token not in fields:
                raise PointerError(f"no field {token!r}")
            key, node = token, fields[token]
        elif isinstance(node, list):
            items = cast(list[Any], node)
            if not token.isdigit() or (token != "0" and token.startswith("0")):
                raise PointerError(f"{token!r} is not a list index")
            if int(token) >= len(items):
                raise PointerError(f"index {token} is past the end of the list")
            key, node = int(token), items[int(token)]
        else:
            raise PointerError(f"{token!r} goes below a number")
    if parent is None:
        raise PointerError("the pointer names the whole params object")
    return parent, key, node


def leaf_kind(tokens: list[str], leaf: Any) -> FieldKind:
    """What the number at ``tokens`` measures, from the field's name."""
    if isinstance(leaf, bool) or not isinstance(leaf, int | float):
        raise PointerError("an expression can only drive a number")
    if any("signature" in token for token in tokens):
        raise PointerError("a picked reference's signature is measured, not driven")
    if isinstance(leaf, int):
        return "int"
    name = tokens[-1]
    if name.endswith("_deg"):
        return "angle"
    if name.endswith("_mm") or name in _LENGTH_KEYS:
        return "length"
    if name in _UNITLESS_KEYS:
        return "unitless"
    raise PointerError(f"field {name!r} cannot be driven by an expression")


def check_expressions(params: Any, expressions: dict[str, str] | None) -> None:
    """Refuse (``ValueError``) a pointer that misses an int or float leaf."""
    for pointer in expressions or {}:
        tokens = parse_pointer(pointer)
        try:
            _, _, leaf = locate(params, tokens)
            leaf_kind(tokens, leaf)
        except PointerError as exc:
            raise ValueError(f"expressions[{pointer!r}]: {exc}") from exc


def _none_if_empty(value: dict[str, str] | None) -> dict[str, str] | None:
    """``{}`` is stored and dumped as no expressions at all."""
    return value or None


Pointer = Annotated[str, StringConstraints(min_length=1, max_length=MAX_POINTER_LENGTH)]
ExpressionText = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
]

#: The field's type: pointer -> formula, at most 64 of them; ``{}`` reads None.
FeatureExpressions = Annotated[
    Annotated[dict[Pointer, ExpressionText], Field(max_length=MAX_FEATURE_EXPRESSIONS)]
    | None,
    AfterValidator(_none_if_empty),
]

#: Optional, and omitted from a dump while null, so every envelope without
#: expressions dumps (and keys the rebuild cache) exactly as before the field.
EXPRESSIONS_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    description="Formulas driving numbers in `params`: a JSON pointer into "
    "`params` (e.g. `/distance_mm`) to an expression over the part's parameters "
    "(e.g. `D/2 + 1`). The pointer must name an int or float field. Documents "
    "stores the resolved number at each pointer on every write, and clears this "
    "before evaluation, so geometry receives numbers only. Null (omitted) when "
    "every field is a plain number.",
)
