"""How a shell's cavity turns a concave edge (SHELL-SHARP-DEFAULT).

``ShellParamsV1.shell_type`` (:mod:`loft_wire.features`). Behind a concave
edge of the body, a ``sharp`` shell extends the two inward walls until they
meet, so the cavity has a sharp corner and the wall across it is thicker than
the shell thickness: what SolidWorks, Onshape and Fusion do by default, and
what a new shell is authored with (OCCT's Intersection join). A ``rounded``
shell rounds that corner at the wall thickness from the edge (OCCT's Arc
join). Convex edges come out sharp either way.

Every shell stored before the field existed is rounded. Absent therefore reads
``rounded``, and ``rounded`` is not serialized, so those rows, the responses
that carry them and their rebuild-cache keys stay byte-identical.
"""

from typing import Any, Literal

from pydantic import Field

#: The shell kinds (module docstring).
ShellType = Literal["sharp", "rounded"]


def _is_rounded(value: object) -> bool:
    """``exclude_if`` predicate: the legacy ``rounded`` is not serialized."""
    return value == "rounded"


def _drop_schema_default(schema: dict[str, Any]) -> None:
    """Keep the field OPTIONAL in the generated ts-client, as
    ``loft_wire.features._drop_schema_default`` does for its fields (a schema
    ``default`` would make every existing web shell literal supply it)."""
    schema.pop("default", None)


#: ``ShellParamsV1.shell_type``.
SHELL_TYPE_FIELD: Any = Field(
    default="rounded",
    exclude_if=_is_rounded,
    json_schema_extra=_drop_schema_default,
    description="How the cavity turns a CONCAVE edge of the body. `sharp` "
    "(what a new shell is authored with, as SolidWorks, Onshape and Fusion do "
    "by default) extends the inward walls until they meet, so the cavity has a "
    "sharp corner and the wall there is thicker than `thickness_mm`; `rounded` "
    "rounds it at the wall thickness from the edge. Convex edges are sharp "
    "either way. Absent reads `rounded` (every shell stored before the field "
    "existed), and `rounded` is not serialized, so those rows stay "
    "byte-identical.",
)
