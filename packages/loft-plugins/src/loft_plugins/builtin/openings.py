"""Window and Door: rough openings hosted in a wall (WINDOW-DOOR, RESEARCH §23).

As Revit and Chief Architect host them: a window or door names its host wall
(a ``loft.wall`` feature input) and sits at an offset along it, and the WALL
frames it. ``loft.wall`` receives every opening that names it
(``ExpandInputs.hosted``) and lays out kings, jacks, a doubled header, top
cripples and, for a window, a flat sill with bottom cripples, cutting the
bottom plate for a door (``loft_plugins.builtin.wall``). A write to an opening
re-expands its wall.

An opening frames its ROUGH OPENING only: it expands to no member of its own
(the unit body, frame and sash or slab, is WINDOW-DOOR-UNIT). Its expansion
checks that it fits its wall, so a write that does not fit is refused on the
opening's own field, before the wall is re-expanded.

**Inputs.** Unit width and height, the rough-opening allowance added to each
(a 36 x 80 prehung door takes 2 x 2.5, a 24 x 36 window 0.5 x 0.5: B2's
38 x 82.5 and 24.5 x 36.5), the offset of the unit's centre along the wall
from the wall's start, and for a window the head height: the top of the rough
opening (the header's underside) above the wall's base, 82.5 in by default so
window and door heads align, as framers set them. A door's rough opening
stands on the wall's base. The header is two plies of ``header_profile`` on
edge.
"""

from collections.abc import Iterator
from typing import Literal

from loft_wire.features import CustomFeature
from loft_wire.lumber import MM_PER_INCH, LumberProfileKey
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    ChoiceInput,
    FeatureReferenceInput,
    LengthInput,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
)

from loft_plugins.api import (
    Expander,
    ExpandInputs,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)
from loft_plugins.builtin.wall import Opening, WallSpec, frame_opening

_HEADERS: list[LumberProfileKey] = ["us_2x6", "us_2x8", "us_2x10", "us_2x12"]


def _length(
    name: str, label: str, default_in: float, low_in: float, high_in: float, help: str
) -> LengthInput:
    return LengthInput(
        kind="length",
        name=name,
        label=label,
        description=help,
        default=default_in * MM_PER_INCH,
        minimum=low_in * MM_PER_INCH,
        maximum=high_in * MM_PER_INCH,
    )


def _inputs(
    kind: Literal["door", "window"],
    unit: tuple[float, float],
    allowance: tuple[float, float],
) -> list[PluginInput]:
    what = "door" if kind == "door" else "window"
    inputs: list[PluginInput] = [
        FeatureReferenceInput(
            kind="feature",
            name="host_wall",
            label="Host wall",
            description=f"The wall this {what} sits in; the wall frames it.",
            feature_types=["custom"],
            plugin_ids=["loft.wall"],
            host=True,
        ),
        _length(
            "offset_mm",
            "Offset",
            72.0,
            0.0,
            960.0,
            f"From the wall's start to the {what}'s centre, along the wall.",
        ),
        _length("width_mm", "Unit width", unit[0], 12.0, 144.0, "The unit's width."),
        _length("height_mm", "Unit height", unit[1], 12.0, 144.0, "The unit's height."),
        _length(
            "ro_width_allowance_mm",
            "RO width allowance",
            allowance[0],
            0.0,
            6.0,
            "Added to the unit width for the rough opening (shims, plumbing).",
        ),
        _length(
            "ro_height_allowance_mm",
            "RO height allowance",
            allowance[1],
            0.0,
            6.0,
            "Added to the unit height for the rough opening.",
        ),
    ]
    if kind == "window":
        inputs.append(
            _length(
                "head_height_mm",
                "Head height",
                82.5,
                24.0,
                234.0,
                "Top of the rough opening (the header's underside) above the "
                "wall's base; 82.5 aligns with a 6'8\" door's.",
            )
        )
    inputs.append(
        ChoiceInput(
            kind="choice",
            name="header_profile",
            label="Header",
            description="Two plies on edge over the jacks.",
            options=lumber_options(_HEADERS),
            default="us_2x6",
        )
    )
    return inputs


def _members(what: str) -> list[PluginMemberRole]:
    return [
        PluginMemberRole(
            role="unit",
            title="Unit",
            description=f"The {what} unit's body (not yet drawn: the wall frames "
            "the rough opening).",
        )
    ]


WINDOW_MANIFEST_V1 = PluginManifest(
    id="loft.window",
    version="1.0.0",
    title="Window",
    description="A window hosted in a wall: its wall frames the rough opening "
    "with kings, jacks, a header, a sill and cripples (Revit, Chief Architect).",
    inputs=_inputs("window", (24.0, 36.0), (0.5, 0.5)),
    members=_members("window"),
)

DOOR_MANIFEST_V1 = PluginManifest(
    id="loft.door",
    version="1.0.0",
    title="Door",
    description="A door hosted in a wall: its wall frames the rough opening "
    "with kings, jacks, a header and cripples, and cuts the bottom plate.",
    inputs=_inputs("door", (36.0, 80.0), (2.0, 2.5)),
    members=_members("door"),
)


def _host(inputs: ExpandInputs) -> WallSpec:
    """The host wall's spec, from its stored inputs (the registry has checked
    it is an earlier ``loft.wall``)."""
    ref = inputs.feature("host_wall")
    host = inputs.resolve(ref)
    if not isinstance(host, CustomFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Host wall: pick an earlier Wall.", input="host_wall"
        )
    return WallSpec.from_inputs(ExpandInputs(ref.feature_id, host.params.inputs))


def _expander(kind: Literal["door", "window"], title: str) -> Expander:
    def expand(inputs: ExpandInputs) -> Iterator[Member]:
        frame_opening(_host(inputs), Opening.from_inputs(kind, f"This {title}", inputs))
        return iter(())

    return expand


WINDOW_V1 = Plugin(WINDOW_MANIFEST_V1, _expander("window", "window"))
DOOR_V1 = Plugin(DOOR_MANIFEST_V1, _expander("door", "door"))
