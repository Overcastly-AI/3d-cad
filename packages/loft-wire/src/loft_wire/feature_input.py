"""The ``input_error`` field of an evaluation-request entry (PART-PARAMETERS).

Kept out of :mod:`loft_wire.features` (FILE-SIZE-RATCHET); that module owns
the field itself, ``EvaluatedFeatureInput.input_error``, and takes its
definition and code check from here.

Documents resolves every parameter expression before it composes an evaluation
request (docs/RESEARCH.md §19), so geometry receives numbers only. When a
feature's resolved value fails its field's validation, or a name it uses cannot
be resolved, documents cannot hand geometry a valid feature built from it.
It sends the feature with its last good values and this error instead.
Geometry then builds NOTHING for that feature: it reports it failed with this
error, and the features after it build against the body before it.
"""

from typing import Any, Final, Literal, get_args

from pydantic import AfterValidator, Field

from loft_wire.twist import is_none

#: A resolved parameter value the feature's field refuses (a negative extrude
#: distance, a non-integer pattern count, a length where an angle belongs).
PARAMETER_VALUE_INVALID: Final = "parameter_value_invalid"
#: A name the feature's expression uses that resolves to no value (an
#: unresolved import, a parameter the table no longer has).
PARAMETER_UNRESOLVED: Final = "parameter_unresolved"

#: The only codes an ``input_error`` may carry. Any other failure is the
#: kernel's to report, so a request carrying one is refused at validation.
FeatureInputErrorCode = Literal["parameter_value_invalid", "parameter_unresolved"]
FEATURE_INPUT_ERROR_CODES: Final = frozenset(get_args(FeatureInputErrorCode))


def _check_input_error_code(value: Any) -> Any:
    """Refuse an ``input_error`` whose code is not a feature-input code."""
    if value is not None and value.code not in FEATURE_INPUT_ERROR_CODES:
        allowed = ", ".join(sorted(FEATURE_INPUT_ERROR_CODES))
        raise ValueError(f"input_error.code must be one of: {allowed}")
    return value


#: The ``Annotated`` metadata that applies :func:`_check_input_error_code`.
INPUT_ERROR_CHECK: Final = AfterValidator(_check_input_error_code)

#: Optional, and omitted from a dump while null, so every request without an
#: input error dumps (and keys the rebuild cache) exactly as before the field.
INPUT_ERROR_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    description="Set by documents when this feature's inputs could not be "
    "resolved (`parameter_value_invalid`, `parameter_unresolved`). Geometry "
    "does not build the feature: its result is this error, and later features "
    "build against the body before it. Null (omitted) for a buildable feature.",
)
