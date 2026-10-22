"""The warning a stored formula with a bare number carries (FORMULA-BARE-UNIT).

In a part whose unit is not mm, a bare number added to a length reads as mm
under the unchanged grammar (RESEARCH §20), where Fusion reads it in the
document unit. Documents writes the unit into every formula entered from now
on (:mod:`loft_wire.bare_units`); a formula stored before that keeps its
meaning and is flagged with this warning, which carries the one-click fix as
the text to write. Writing it is an ordinary edit, so undo restores the old
formula: nothing is rewritten silently.
"""

import uuid
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from loft_wire.twist import is_none

#: The code of the warning, as the client branches on it.
EXPRESSION_BARE_MM: Final = "expression_bare_mm"


class FormulaWarning(BaseModel):
    """One stored formula whose bare numbers read as mm in a non-mm part."""

    code: Literal["expression_bare_mm"] = Field(
        description="'expression_bare_mm': a bare number added to a length "
        "reads as mm, not in the part's unit"
    )
    message: str = Field(description="Names the bare terms and both readings")
    pointer: str | None = Field(
        description="The feature field the formula drives (`/distance_mm`), or "
        "`/constraints/<i>/expression` for a sketch dimension; null for a "
        "parameter row"
    )
    parameter_id: uuid.UUID | None = Field(
        description="The parameter row the formula is in; null for a feature"
    )
    expression: str = Field(description="The formula as stored")
    literals: list[str] = Field(
        description="Each bare term as written, e.g. `1/2` in `wall + 1/2`"
    )
    fixed_expression: str = Field(
        description="The formula with the part's unit written in "
        "(`wall + 1 in/2`): what the 'Read as' action saves"
    )
    value: float | None = Field(
        description="What the stored formula gives now, in the field's unit "
        "(mm, degrees or a plain number); null when it does not resolve"
    )
    fixed_value: float | None = Field(
        description="What `fixed_expression` would give, in the same unit; "
        "null when it does not resolve"
    )


#: A response's warnings: null (omitted) when there are none, so every
#: response without one keeps its bytes.
FormulaWarnings = list[FormulaWarning] | None

FORMULA_WARNINGS_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    description="Stored formulas whose bare numbers read as mm in this non-mm "
    "part (`expression_bare_mm`), each with its fix. Omitted when there are none.",
)


__all__ = [
    "EXPRESSION_BARE_MM",
    "FORMULA_WARNINGS_FIELD",
    "FormulaWarning",
    "FormulaWarnings",
]
