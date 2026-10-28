"""Updating a stored custom feature to a newer release (OPENING-UPDATE, RESEARCH §23).

Onshape marks a custom feature whose Feature Studio has a newer version and
updates it on request; Fusion badges out-of-date linked content. A stored
feature here keeps its pin until the user updates it, and an update is an
ordinary edit of the feature: the pin moves to the newer release and the
inputs are carried across by an EXPLICIT map, one per release pair, never by
"same names, defaults for the rest". A released manifest is frozen, so the
map is what says how an old feature's meaning reads in the new release:

* ``loft.window`` / ``loft.door`` 1.0.0-1.4.0 -> 1.5.0. Each input the old
  release had keeps its value. What a later release added is set to what
  the old one built: Measured from the wall's start (1.2.0), a Custom size
  that reads the typed size and allowances, and no unit drawn (1.3.0, as
  through 1.2.0 nothing was). Header build becomes Fill the wall (1.4.0's
  default, three plies in a 2x6 wall): framing the header the wall's
  thickness is the reason to update, and a 2x4 wall frames the same either
  way. A 1.4.0 opening keeps its own Header build.
* ``loft.wall`` 1.2.0 and 1.3.0 -> 1.4.0, every input as it is: 1.4.0 is
  1.3.0 member for member (and a typed wall 1.2.0's), plus the backing of
  partitions that meet it and an inside gypsum left at None.
* ``loft.roof`` 1.2.0-1.4.0 -> 1.5.0, every input as it is: 1.5.0 notches
  the sheathing of the walls it picks (ROOF-THROUGH-SHEATHING-UPDATE), and a
  gable on an outline is 1.4.0's byte for byte.

A release with no map here (``loft.floor`` 1.2.0, whose Joist direction 1.3.0
replaced, or ``loft.wall`` 1.0.0, whose ordinal ids 1.1.0 renamed) is not
offered an update: a guessed map could move a member silently.

The maps are pure, as ``expand`` is; documents applies them, checks the
result against the target manifest and re-expands it as any edit.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from loft_wire.features import CustomInputValue
from loft_wire.plugins import semver_key

from loft_plugins.api import PluginError
from loft_plugins.registry import PluginRegistry

#: An update's input map: the stored canonical inputs in, the target
#: release's inputs out (checked against its manifest by the caller).
InputMap = Callable[[Mapping[str, CustomInputValue]], dict[str, CustomInputValue]]

#: The code of a refused update (422 on write).
PLUGIN_UPDATE_UNAVAILABLE = "plugin_update_unavailable"


@dataclass(frozen=True)
class PluginUpdate:
    """One release pair a stored feature may be updated across, and how."""

    plugin_id: str
    from_version: str
    to_version: str
    #: What the update changes, in the words the update action shows.
    summary: str
    map_inputs: InputMap


def _same(inputs: Mapping[str, CustomInputValue]) -> dict[str, CustomInputValue]:
    return dict(inputs)


#: What each opening input added after 1.0.0 reads as for an opening that
#: predates it: the value that builds what the older release built.
_OPENING_ADDED: Mapping[str, CustomInputValue] = {
    "measure_from": "start",  # 1.2.0: 1.0.0-1.1.0 measured from the start
    "size": "custom",  # 1.3.0: the typed size and allowances
    "draw_unit": "none",  # 1.3.0: 1.0.0-1.2.0 drew no unit
}


def _opening_to_1_5(
    inputs: Mapping[str, CustomInputValue],
) -> dict[str, CustomInputValue]:
    """An opening 1.0.0-1.4.0's inputs at 1.5.0 (module docstring)."""
    out = dict(inputs)
    for name, value in _OPENING_ADDED.items():
        out.setdefault(name, value)
    out.setdefault("header_build", "fill")
    return out


_OPENING_FILL = (
    "Fills the header to the wall's thickness (three plies with two 1/2 in "
    "plywood spacers in a 2x6 wall) and lists and prices the spacers."
)
_OPENING_INFILL = (
    "Draws the header's 1/2 in plywood spacers (or an insulated header's "
    "foam), so the cut list and price book carry them."
)
_WALL = (
    "Frames the backing of partitions that meet it and can take an inside "
    "gypsum finish; its framing is unchanged."
)
_ROOF = "Notches the wall sheathing round the rafter tails, as framers do."


def _updates() -> tuple[PluginUpdate, ...]:
    out: list[PluginUpdate] = []
    for plugin_id in ("loft.window", "loft.door"):
        for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
            out.append(
                PluginUpdate(
                    plugin_id, version, "1.5.0", _OPENING_FILL, _opening_to_1_5
                )
            )
        out.append(
            PluginUpdate(plugin_id, "1.4.0", "1.5.0", _OPENING_INFILL, _opening_to_1_5)
        )
    for version in ("1.2.0", "1.3.0"):
        out.append(PluginUpdate("loft.wall", version, "1.4.0", _WALL, _same))
    for version in ("1.2.0", "1.3.0", "1.4.0"):
        out.append(PluginUpdate("loft.roof", version, "1.5.0", _ROOF, _same))
    return tuple(out)


#: Every declared update, by (plugin id, the stored release).
UPDATES: Mapping[tuple[str, str], PluginUpdate] = {
    (u.plugin_id, u.from_version): u for u in _updates()
}


def update_for(
    plugin_id: str, version: str, registry: PluginRegistry | None = None
) -> PluginUpdate | None:
    """The update a feature pinned to *plugin_id* *version* is offered, or
    ``None``. With *registry*, only one whose target that registry runs."""
    found = UPDATES.get((plugin_id, version))
    if found is None:
        return None
    if registry is not None:
        try:
            registry.get(plugin_id, found.to_version)
        except PluginError:
            return None
    return found


def updated_inputs(
    update: PluginUpdate, inputs: Mapping[str, CustomInputValue]
) -> dict[str, CustomInputValue]:
    """*inputs* carried to *update*'s target release by its explicit map."""
    return update.map_inputs(inputs)


def check_update_table(registry: PluginRegistry) -> None:
    """Every declared update names two released versions of one plugin, the
    target newer than the source (a test runs this on the shipped registry)."""
    for update in UPDATES.values():
        registry.get(update.plugin_id, update.from_version)
        registry.get(update.plugin_id, update.to_version)
        if semver_key(update.to_version) <= semver_key(update.from_version):
            raise ValueError(f"{update.plugin_id} {update.from_version}: not newer")


__all__ = [
    "PLUGIN_UPDATE_UNAVAILABLE",
    "UPDATES",
    "InputMap",
    "PluginUpdate",
    "check_update_table",
    "update_for",
    "updated_inputs",
]
