"""How far an extrude reaches on each side of its sketch plane (EXTRUDE-SYMMETRIC).

``ExtrudeParamsV1.extent`` (:mod:`loft_wire.features`). ``one_side`` is the
extrude every stored row describes: the profile sweeps ``distance_mm`` from
the sketch plane, along the normal or against it (``direction``).
``symmetric`` sweeps from ``-distance_mm / 2`` to ``+distance_mm / 2`` about
the sketch plane, so the typed distance is the WHOLE length, split evenly:
SolidWorks' End Condition "Mid Plane", Onshape's "Symmetric" and Fusion 360's
Direction "Symmetric" with Measurement "Whole length". ``direction`` is
ignored while symmetric (both senses build the same solid) and is kept, so
toggling back to ``one_side`` restores the side the user had.

Every extrude stored before the field existed is one-sided. Absent therefore
reads ``one_side``, and ``one_side`` is not serialized, so those rows, the
responses that carry them and their rebuild-cache keys stay byte-identical.
A future ``two_sides`` (Fusion's third Direction) joins this Literal.
"""

from typing import Any, Literal

from pydantic import Field

#: The extrude extents (module docstring).
ExtrudeExtent = Literal["one_side", "symmetric"]


def _is_one_side(value: object) -> bool:
    """``exclude_if`` predicate: the legacy ``one_side`` is not serialized."""
    return value == "one_side"


def _drop_schema_default(schema: dict[str, Any]) -> None:
    """Keep the field OPTIONAL in the generated ts-client, as
    :mod:`loft_wire.shell` does (a schema ``default`` would make every
    existing web extrude literal supply it)."""
    schema.pop("default", None)


#: ``ExtrudeParamsV1.extent``.
EXTRUDE_EXTENT_FIELD: Any = Field(
    default="one_side",
    exclude_if=_is_one_side,
    json_schema_extra=_drop_schema_default,
    description="How far the extrude reaches on each side of the sketch plane. "
    "`one_side` (absent; every extrude stored before the field existed) sweeps "
    "`distance_mm` along `direction`. `symmetric` sweeps `distance_mm / 2` each "
    "way, so the distance is the WHOLE length (SolidWorks Mid Plane, Onshape "
    "and Fusion Symmetric); `direction` is ignored while symmetric. Applies to "
    "add and cut. Not combinable with the legacy twist (422). `one_side` is not "
    "serialized, so stored rows stay byte-identical.",
)
