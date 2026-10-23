"""The warning a stored custom feature carries when its pinned release builds
wrong geometry that a newer release fixes (ROOF-THROUGH-SHEATHING-UPDATE).

``loft.roof`` 1.0.0-1.4.0 run their rafter and hip tails through the
sheathing of the walls they bear on (1.4.0 notches a gable's on an outline
only), so the overlap is counted twice in volume, mass and STEP. A stored
feature keeps its pin: nothing is rebuilt differently behind the user's back
(Fusion marks out-of-date content for the user to update; Revit reloads a
family only on request). The roof's response carries this warning, which
names the overlap, and, where a newer release would notch it (the roof
picks its walls), the version to update to. The update is an ordinary edit
of the pin with the same inputs, so undo restores the old roof.
"""

from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from loft_wire.twist import is_none

#: The code of the warning, as the client branches on it.
ROOF_THROUGH_SHEATHING: Final = "roof_through_sheathing"


class PluginWarning(BaseModel):
    """One stored custom feature's geometry warning, with its fix if any."""

    code: Literal["roof_through_sheathing"] = Field(
        description="'roof_through_sheathing': the roof's tails pass through "
        "wall sheathing, so the two share volume"
    )
    message: str = Field(description="Names the overlap and what fixes it")
    overlap_in3: float = Field(
        ge=0, description="The volume the roof shares with the sheathing (in^3)"
    )
    pairs: int = Field(
        ge=0, description="How many (roof member, sheathing panel) pairs share it"
    )
    update_to: str | None = Field(
        description="The release whose expansion notches it (the 'Update to' "
        "action re-pins the feature to it with the same inputs); null when no "
        "release can (a typed roof picks no walls)"
    )


#: A response's warnings: null (omitted) when there are none, so every
#: response without one keeps its bytes.
PluginWarnings = list[PluginWarning] | None

PLUGIN_WARNINGS_FIELD: Any = Field(
    default=None,
    exclude_if=is_none,
    description="Wrong geometry the feature's pinned plugin release builds "
    "(`roof_through_sheathing`), each with the release that fixes it. Omitted "
    "when there are none.",
)


__all__ = [
    "PLUGIN_WARNINGS_FIELD",
    "ROOF_THROUGH_SHEATHING",
    "PluginWarning",
    "PluginWarnings",
]
