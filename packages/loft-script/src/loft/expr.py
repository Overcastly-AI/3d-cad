"""Loft's one expression language, for offline checks (RESEARCH §20).

The shared library itself (:mod:`loft_wire.expr`), re-exported: documents,
geometry and this package evaluate the same string to the same float, so a
script can check a formula without a server::

    from loft.expr import Quantity, evaluate

    evaluate("20*tan(15)")                                # Quantity(5.35..., unitless)
    evaluate("W/2 + 3", {"W": Quantity(40, "length")})    # Quantity(23.0, length)
    evaluate("D", part.parameter_values())                # against a part's table

Lengths are mm and angles degrees; a bare number is unitless. Every failure is
an :class:`ExpressionError` subclass with a stable ``code``, the same codes the
server puts on a refusal (:class:`loft.InvalidExpression`).
"""

from __future__ import annotations

from loft_wire.expr import (
    ANGLE,
    FUNCTIONS,
    LENGTH,
    MAX_EXPRESSION_LENGTH,
    MAX_PARAMETERS,
    UNITLESS,
    UNITS,
    Expression,
    ExpressionCycleError,
    ExpressionDomainError,
    ExpressionError,
    ExpressionLimitError,
    ExpressionNameError,
    ExpressionReferenceError,
    ExpressionSyntaxError,
    ExpressionUnitError,
    Kind,
    Quantity,
    coerce,
    evaluate,
    parse,
    validate_name,
)

__all__ = [
    "ANGLE",
    "FUNCTIONS",
    "LENGTH",
    "MAX_EXPRESSION_LENGTH",
    "MAX_PARAMETERS",
    "UNITLESS",
    "UNITS",
    "Expression",
    "ExpressionCycleError",
    "ExpressionDomainError",
    "ExpressionError",
    "ExpressionLimitError",
    "ExpressionNameError",
    "ExpressionReferenceError",
    "ExpressionSyntaxError",
    "ExpressionUnitError",
    "Kind",
    "Quantity",
    "coerce",
    "evaluate",
    "parse",
    "validate_name",
]
