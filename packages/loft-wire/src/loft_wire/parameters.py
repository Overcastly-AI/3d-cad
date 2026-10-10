"""Part parameters (PART-PARAMETERS, RESEARCH §20): a part's table of named
values, as Fusion 360's Change Parameters and Onshape's Variables.

Each row has a stable ``id`` (a rename keeps it), a ``name`` other formulas
use, an ``expression`` in the one expression language (:mod:`loft_wire.expr`),
a ``unit`` that says what the value measures, a free ``comment``, and the
resolved ``value`` the server computes on every write: mm for a length,
degrees for an angle, a plain number otherwise. A client never sends
``value``; it is always the server's evaluation of ``expression``.

``PUT /api/v1/parts/{id}/parameters`` replaces the whole table under the
part's optimistic ``expected_tree_version``, as one undoable tree edit. The
table is refused (422) when a name is invalid, reserved or repeated, a formula
does not parse, names something that is not a parameter, forms a cycle, mixes
units, or has no finite value.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from loft_wire.expr import (
    MAX_EXPRESSION_LENGTH,
    MAX_PARAMETERS,
    ExpressionCycleError,
    ExpressionError,
    ExpressionLimitError,
    ExpressionNameError,
    ExpressionReferenceError,
    Kind,
    NamedExpression,
    evaluate_parameters,
    parse,
    validate_name,
)

#: Longest parameter name (the identifier rule in :data:`loft_wire.expr.NAME_PATTERN`).
PARAMETER_NAME_MAX_LENGTH = 64

#: Longest comment on one parameter.
PARAMETER_COMMENT_MAX_LENGTH = 500

ParameterName = Annotated[
    str, StringConstraints(min_length=1, max_length=PARAMETER_NAME_MAX_LENGTH)
]
ParameterExpression = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
]
ParameterComment = Annotated[
    str, StringConstraints(max_length=PARAMETER_COMMENT_MAX_LENGTH)
]

#: What a parameter measures: ``length`` (value in mm), ``angle`` (value in
#: degrees) or ``unitless``. A bare number in a length row is mm.
ParameterUnit = Kind


class PartParameterInput(BaseModel):
    """One row as a client writes it: everything but the resolved value."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(
        description="Stable identity of the row; a rename keeps it. A new row "
        "carries a fresh UUID minted by the client."
    )
    name: ParameterName = Field(
        description="What formulas call it: a letter or _, then up to 63 "
        "letters, digits or _; not a function, unit or constant word"
    )
    expression: ParameterExpression = Field(
        description="A number or formula, e.g. '40', '0.5 in', 'width/2 + 3'"
    )
    unit: ParameterUnit = Field(
        description="What the value measures: length (mm), angle (degrees) or unitless"
    )
    comment: ParameterComment = Field(default="", description="Free note")


class PartParameter(PartParameterInput):
    """One stored row with its resolved value. Unknown keys are ignored, as
    everywhere in a ``.loft`` tree, so an older reader takes a newer file."""

    model_config = ConfigDict(extra="ignore")

    value: float = Field(
        description="The evaluated expression: mm for a length, degrees for an "
        "angle, a plain number for unitless. Computed by the server."
    )


class PartParametersUpdate(BaseModel):
    """``PUT /api/v1/parts/{id}/parameters``: replace the whole table."""

    model_config = ConfigDict(extra="forbid")

    expected_tree_version: int = Field(ge=0)
    parameters: list[PartParameterInput] = Field(max_length=MAX_PARAMETERS)


class PartParametersResponse(BaseModel):
    """A part's parameter table, in its stored order, with the tree version."""

    tree_version: int = Field(ge=0)
    parameters: list[PartParameter]


class ParameterTableError(ValueError):
    """Why a parameter table was refused. ``code`` is the stable id of the
    underlying :class:`~loft_wire.expr.ExpressionError` (or
    ``parameter_id_duplicate``); ``parameter`` names the row at fault when one
    row is; ``chain`` is the loop for a cycle."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        parameter: str | None = None,
        chain: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.parameter = parameter
        self.chain = chain


def _row_error(row: PartParameterInput, exc: ExpressionError) -> ParameterTableError:
    return ParameterTableError(
        f"Parameter {row.name!r}: {exc}", code=exc.code, parameter=row.name
    )


def resolve_parameters(rows: Sequence[PartParameterInput]) -> list[PartParameter]:
    """Evaluate a whole table; return it, in order, with each ``value``.

    Raises :class:`ParameterTableError`. Per-row faults (a bad, reserved or
    repeated name, a formula that does not parse, an unknown name) are found
    first so the error can name the row; cycles, unit clashes and non-finite
    results come from :func:`~loft_wire.expr.evaluate_parameters`.
    """
    if len(rows) > MAX_PARAMETERS:
        raise ParameterTableError(
            f"{len(rows)} parameters; a part may define at most {MAX_PARAMETERS}",
            code=ExpressionLimitError.code,
        )
    ids: set[uuid.UUID] = set()
    names: set[str] = set()
    for row in rows:
        if row.id in ids:
            raise ParameterTableError(
                f"Parameter id {row.id} appears twice.",
                code="parameter_id_duplicate",
                parameter=row.name,
            )
        ids.add(row.id)
        try:
            validate_name(row.name)
        except ExpressionError as exc:
            raise _row_error(row, exc) from exc
        if row.name in names:
            raise ParameterTableError(
                f"Parameter {row.name!r} is defined twice.",
                code=ExpressionNameError.code,
                parameter=row.name,
            )
        names.add(row.name)
    for row in rows:
        try:
            unknown = sorted(parse(row.expression).references() - names)
        except ExpressionError as exc:
            raise _row_error(row, exc) from exc
        if unknown:
            raise ParameterTableError(
                f"Parameter {row.name!r}: unknown name {unknown[0]!r} in expression",
                code=ExpressionReferenceError.code,
                parameter=row.name,
            )
    try:
        values = evaluate_parameters(
            [NamedExpression(row.name, row.expression, row.unit) for row in rows]
        )
    except ExpressionCycleError as exc:
        raise ParameterTableError(
            str(exc), code=exc.code, parameter=exc.chain[0], chain=exc.chain
        ) from exc
    except ExpressionError as exc:
        raise ParameterTableError(str(exc), code=exc.code) from exc
    # A stored row may come back in (a version restore, an import): its old
    # ``value`` is never trusted, only re-derived.
    fields = set(PartParameterInput.model_fields)
    return [
        PartParameter(**row.model_dump(include=fields), value=values[row.name].value)
        for row in rows
    ]


__all__ = [
    "PARAMETER_COMMENT_MAX_LENGTH",
    "PARAMETER_NAME_MAX_LENGTH",
    "ParameterComment",
    "ParameterExpression",
    "ParameterName",
    "ParameterTableError",
    "ParameterUnit",
    "PartParameter",
    "PartParameterInput",
    "PartParametersResponse",
    "PartParametersUpdate",
    "resolve_parameters",
]
