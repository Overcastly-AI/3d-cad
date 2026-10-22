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
    PLUGIN_INPUT_UNSUPPORTED,
    ChoiceInput,
    FeatureReferenceInput,
    LengthInput,
    PluginInput,
    PluginManifest,
    PluginMemberRole,
    SegmentsInput,
)

from loft_plugins.api import (
    Expander,
    ExpandInputs,
    Member,
    Plugin,
    PluginError,
    lumber_options,
)
from loft_plugins.builtin.house import is_outline_wall, wall_specs_of
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


def _host(inputs: ExpandInputs, segments: bool) -> tuple[WallSpec, bool]:
    """The host wall's spec, from its stored inputs (the registry has checked
    it is an earlier ``loft.wall``), and whether it frames as 1.1.0 does.
    *segments* (1.1.0) reads ``wall_segment``: which wall of an outline wall
    (BUILDING-OUTLINE) the opening sits in."""
    ref = inputs.feature("host_wall")
    host = inputs.resolve(ref)
    if not isinstance(host, CustomFeature):
        raise PluginError(
            PLUGIN_INPUT_INVALID, "Host wall: pick an earlier Wall.", input="host_wall"
        )
    named = host.params.plugin_version != "1.0.0"
    if not segments:
        if is_outline_wall(host):
            # Outline walls are new: no stored 1.0.0 opening names one.
            raise PluginError(
                PLUGIN_INPUT_UNSUPPORTED,
                "Host wall: this release cannot pick one wall of an outline; "
                "update the opening to pick its wall.",
                input="host_wall",
            )
        spec = WallSpec.from_inputs(ExpandInputs(ref.feature_id, host.params.inputs))
        return spec, named
    specs = dict(wall_specs_of(ref.feature_id, host, inputs.earlier, inputs.parameters))
    picked = inputs.segments("wall_segment")
    if None in specs:
        if picked:
            raise PluginError(
                PLUGIN_INPUT_INVALID,
                "Wall: the host is one wall, not an outline; leave Wall empty.",
                input="wall_segment",
            )
        return specs[None], named
    if len(picked) != 1 or picked[0] not in specs:
        raise PluginError(
            PLUGIN_INPUT_INVALID,
            "Wall: pick the wall of the outline this opening sits in.",
            input="wall_segment",
        )
    return specs[picked[0]], named


def _expander(
    kind: Literal["door", "window"], title: str, segments: bool = False
) -> Expander:
    def expand(inputs: ExpandInputs) -> Iterator[Member]:
        wall, named = _host(inputs, segments)
        frame_opening(wall, Opening.from_inputs(kind, f"This {title}", inputs), named)
        return iter(())

    return expand


WINDOW_V1 = Plugin(WINDOW_MANIFEST_V1, _expander("window", "window"))
DOOR_V1 = Plugin(DOOR_MANIFEST_V1, _expander("door", "door"))


# --- 1.1.0: a wall of an outline (BUILDING-OUTLINE) -------------------------------


def _with_segment(manifest: PluginManifest) -> PluginManifest:
    """*manifest* at 1.1.0: a Wall pick after the host, for an outline wall."""
    inputs = list(manifest.inputs)
    inputs.insert(
        1,
        SegmentsInput(
            kind="segments",
            name="wall_segment",
            label="Wall",
            description="When the host is an outline wall: which of its walls "
            "(a line of the outline) this sits in. Empty for a single wall.",
            outline_input="host_wall",
            min_items=0,
            max_items=1,
        ),
    )
    return manifest.model_copy(
        update={
            "version": "1.1.0",
            "inputs": inputs,
            "description": manifest.description
            + " It may sit in one wall of an outline wall.",
        }
    )


WINDOW_MANIFEST_V1_1 = _with_segment(WINDOW_MANIFEST_V1)
DOOR_MANIFEST_V1_1 = _with_segment(DOOR_MANIFEST_V1)

WINDOW_V1_1 = Plugin(WINDOW_MANIFEST_V1_1, _expander("window", "window", True))
DOOR_V1_1 = Plugin(DOOR_MANIFEST_V1_1, _expander("door", "door", True))
