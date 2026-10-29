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

``loft.foundation`` (CRAWL-SPACE) carries ``crawl_height_low`` when its
crawl height is under IRC R317.1's 18 in: code advice on an input, with no
release to update to, and the foundation builds.

``loft.roof`` 1.6.0 (CEILING-JOISTS) carries ``ceiling_joists_omitted`` when
it asked for ceiling joists its gable cannot take (the chosen joist would
pass the ridge board's underside): the roof builds without them, as Chief
warns rather than blocks, and the message says what to pick.
"""

from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from loft_wire.twist import is_none

#: The codes of the warnings, as the client branches on them.
ROOF_THROUGH_SHEATHING: Final = "roof_through_sheathing"
#: CRAWL-SPACE: a ``loft.foundation`` whose crawl height (grade to the
#: joists' underside) is under IRC R317.1's 18 in, below which the joists
#: must be pressure-treated or naturally durable. Advice, never a refusal.
CRAWL_HEIGHT_LOW: Final = "crawl_height_low"
#: CEILING-JOISTS: a ``loft.roof`` 1.6.0 gable set to frame ceiling joists
#: whose chosen joist would pass the ridge board: built without them.
CEILING_JOISTS_OMITTED: Final = "ceiling_joists_omitted"


class PluginWarning(BaseModel):
    """One stored custom feature's geometry warning, with its fix if any."""

    code: Literal[
        "roof_through_sheathing", "crawl_height_low", "ceiling_joists_omitted"
    ] = Field(
        description="'roof_through_sheathing': the roof's tails pass through "
        "wall sheathing, so the two share volume; 'crawl_height_low': a "
        "foundation's crawl height is under the 18 in of IRC R317.1; "
        "'ceiling_joists_omitted': a gable's chosen ceiling joist would pass "
        "its ridge board, so the roof is built without them"
    )
    message: str = Field(description="Names the problem and what fixes it")
    overlap_in3: float = Field(
        ge=0,
        description="The volume the roof shares with the sheathing (in^3); 0 "
        "for a warning that is not an overlap",
    )
    pairs: int = Field(
        ge=0,
        description="How many (roof member, sheathing panel) pairs share it; "
        "0 for a warning that is not an overlap",
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
    "(`roof_through_sheathing`), each with the release that fixes it, or a "
    "warning on its inputs (`crawl_height_low`, `ceiling_joists_omitted`). "
    "Omitted when there are none.",
)


__all__ = [
    "CEILING_JOISTS_OMITTED",
    "CRAWL_HEIGHT_LOW",
    "PLUGIN_WARNINGS_FIELD",
    "ROOF_THROUGH_SHEATHING",
    "PluginWarning",
    "PluginWarnings",
]
