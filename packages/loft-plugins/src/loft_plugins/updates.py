"""Updating a stored custom feature to its newest release (OPENING-UPDATE,
PLUGIN-UPDATE-ALL, RESEARCH §23).

Onshape marks a custom feature whose Feature Studio has a newer version and
updates it on request, every input it can map carried across and every new
parameter at its default; Fusion badges out-of-date linked content. A stored
feature here keeps its pin until the user updates it, and an update is an
ordinary edit of the feature: the pin moves to the newest release and the
inputs are carried across by an EXPLICIT map, one per release pair. A
released manifest is frozen, so the map is what says how an old feature's
meaning reads in the new release; an input the old release did not have
takes the new release's default (the caller's ``canonical_inputs`` fills
it), so an update may add members, and it names what it adds
(:func:`update_effect`):

* ``loft.window`` / ``loft.door`` 1.0.0-1.4.0 -> 1.5.0. Each input the old
  release had keeps its value. What a later release added is set to what
  the old one built: Measured from the wall's start (1.2.0), a Custom size
  that reads the typed size and allowances, and no unit drawn (1.3.0, as
  through 1.2.0 nothing was). Header build becomes Fill the wall (1.4.0's
  default, three plies in a 2x6 wall). A 1.4.0 opening keeps its own Header
  build.
* ``loft.wall`` 1.2.0 and 1.3.0 -> 1.4.0, every input as it is: 1.4.0 is
  1.3.0 member for member (and a typed wall 1.2.0's), plus the backing of
  partitions that meet it and an inside gypsum left at None.
* ``loft.roof`` 1.2.0-1.5.0 -> 1.6.0, every input as it is, so Ceiling
  joists takes 1.6.0's default, Beside each common: a gable on an outline or
  on picked walls gains its ceiling joists (B7's 11), as a new roof frames
  them. A joist that cannot fit (it would pass the ridge board) is left out
  and the roof warns ``ceiling_joists_omitted``; the update never refuses.
  The update also notches the sheathing of the walls a pre-1.5.0 roof picks
  (ROOF-THROUGH-SHEATHING-UPDATE). This replaces CEILING-JOISTS' review call
  (0d22c34) that an update maps the joists to None (VISION, 2026-10-29).
* ``loft.floor`` 1.2.0 -> 1.3.0: Joist direction becomes the Joists bear on
  that frames the same joists. 1.2.0 ran the width along its typed
  direction, or along an outline's first line; 1.3.0 reads an outline's
  rectangle from its corners. The map reads both and picks Long walls when
  that frames them (B7: 1.2.0's default is 1.3.0's, byte for byte), else
  Front and back or Left and right.
* ``loft.deck`` 1.1.0 -> 1.2.0, every input as it is: each post gains its
  round pier footing and post base (1.2.0's defaults; B1's 3 piers).
* ``loft.foundation`` 1.0.0 -> 1.1.0, every input as it is: the stem lists
  the vents and the access door it cuts (B9's 5 and 1), priced Each.
* ``loft.cabinets``: every older release to the newest with every input as
  it is (:data:`SAME_INPUTS`). Only 1.0.0 is released, so it is offered
  nothing yet; CASEWORK-B10's 1.1.0 lands here with no code, its tests
  checking that the same inputs build the same boxes.

A release with no map here (``loft.wall`` 1.0.0 and ``loft.deck`` 1.0.0,
whose ordinal member ids 1.1.0 renamed; ``loft.floor`` 1.0.0 and 1.1.0 and
``loft.roof`` 1.0.0 and 1.1.0, typed releases saved before the outline) is
not offered an update: a guessed map could move a member silently.

The maps are pure, as ``expand`` is; documents applies them, checks the
result against the target manifest and re-expands it as any edit.
"""

import dataclasses
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from loft_wire.features import CustomInputValue, ExpandedMember
from loft_wire.plugins import semver_key

from loft_plugins.api import ExpandInputs, Plugin, PluginError
from loft_plugins.builtin import BUILTIN_PLUGINS
from loft_plugins.builtin.house import floor_values, floor_values_v1_3
from loft_plugins.registry import PluginRegistry

#: An update's input map: the stored canonical inputs in, with the stored
#: feature's context (the features before it, for a floor's outline), and the
#: target release's inputs out (checked against its manifest by the caller,
#: which fills every input the map leaves out with its default).
InputMap = Callable[
    [Mapping[str, CustomInputValue], ExpandInputs], dict[str, CustomInputValue]
]

#: The code of a refused update (422 on write).
PLUGIN_UPDATE_UNAVAILABLE = "plugin_update_unavailable"


@dataclass(frozen=True)
class PluginUpdate:
    """One release pair a stored feature may be updated across, and how."""

    plugin_id: str
    from_version: str
    to_version: str
    #: What the release changes, in the words the update action shows (the
    #: counts of what it adds are the feature's own: :func:`update_effect`).
    summary: str
    map_inputs: InputMap


def _same(
    inputs: Mapping[str, CustomInputValue], _context: ExpandInputs
) -> dict[str, CustomInputValue]:
    return dict(inputs)


#: What each opening input added after 1.0.0 reads as for an opening that
#: predates it: the value that builds what the older release built.
_OPENING_ADDED: Mapping[str, CustomInputValue] = {
    "measure_from": "start",  # 1.2.0: 1.0.0-1.1.0 measured from the start
    "size": "custom",  # 1.3.0: the typed size and allowances
    "draw_unit": "none",  # 1.3.0: 1.0.0-1.2.0 drew no unit
}


def _opening_to_1_5(
    inputs: Mapping[str, CustomInputValue], _context: ExpandInputs
) -> dict[str, CustomInputValue]:
    """An opening 1.0.0-1.4.0's inputs at 1.5.0 (module docstring)."""
    out = dict(inputs)
    for name, value in _OPENING_ADDED.items():
        out.setdefault(name, value)
    out.setdefault("header_build", "fill")
    return out


#: Joists bear on, in the order the floor map tries them: the default first,
#: so a floor whose old direction is the default's keeps the default.
_BEAR_ON = ("long_walls", "front_back", "left_right")


def _joist_angle(values: ExpandInputs) -> float:
    """The plan angle (degrees, mod 180) the joists of a floor written as
    1.1.0's typed rectangle run at: along its direction for ``width``, across
    it for ``depth``."""
    turn = 0.0 if values.choice("joist_direction") == "width" else 90.0
    return (values.number("direction_deg") + turn) % 180.0


def _floor_to_1_3(
    inputs: Mapping[str, CustomInputValue], context: ExpandInputs
) -> dict[str, CustomInputValue]:
    """A floor 1.2.0's inputs at 1.3.0: Joist direction replaced by the
    first Joists bear on (Long walls, then Front and back, then Left and
    right) whose joists run the way 1.2.0's did, on the same rectangle.
    Raises :class:`PluginError` when the floor's outline cannot be read."""
    old = dataclasses.replace(context, values=dict(inputs))
    want = _joist_angle(floor_values(old))
    base = {k: v for k, v in inputs.items() if k != "joist_direction"}
    for bear_on in _BEAR_ON:
        candidate = {**base, "joists_bear_on": bear_on}
        new = floor_values_v1_3(dataclasses.replace(context, values=candidate))
        gap = abs(_joist_angle(new) - want) % 180.0
        if min(gap, 180.0 - gap) < 1e-6:
            return candidate
    raise PluginError(  # unreachable: two of the three run each way
        PLUGIN_UPDATE_UNAVAILABLE, "No Joists bear on frames this floor's joists."
    )


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
_ROOF = (
    "Notches the wall sheathing round the rafter tails, as framers do, and "
    "ties a gable with a ceiling joist beside each common (one that cannot "
    "fit under the ridge is left out, with a warning)."
)
_ROOF_1_5 = (
    "Ties a gable with a ceiling joist beside each common (one that cannot "
    "fit under the ridge is left out, with a warning); a hip or a typed "
    "bearing is unchanged."
)
_FLOOR = (
    "Joists bear on replaces Joist direction and frames the same joists; an "
    "outline's rectangle is read from its corners."
)
_DECK = (
    "Stands each post on a round pier footing with its post base, the "
    "concrete bought in 80 lb bags."
)
_FOUNDATION = (
    "Lists the foundation vents and the access door set in the stem wall, priced Each."
)
_SAME_SUMMARY = "Carries every input as it is; new inputs take their defaults."

#: Plugins whose every older release updates to the newest with every input
#: as it is (the hook CASEWORK-B10's ``loft.cabinets`` 1.1.0 lands in).
SAME_INPUTS: tuple[str, ...] = ("loft.cabinets",)


def _same_inputs_updates(plugins: Iterable[Plugin]) -> list[PluginUpdate]:
    out: list[PluginUpdate] = []
    for plugin_id in SAME_INPUTS:
        versions = sorted(
            (p.manifest.version for p in plugins if p.manifest.id == plugin_id),
            key=semver_key,
        )
        out += [
            PluginUpdate(plugin_id, v, versions[-1], _SAME_SUMMARY, _same)
            for v in versions[:-1]
        ]
    return out


def declared_updates(
    plugins: Iterable[Plugin] = BUILTIN_PLUGINS,
) -> tuple[PluginUpdate, ...]:
    """Every update of *plugins*' releases (the shipped ones by default)."""
    plugins = tuple(plugins)
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
        out.append(PluginUpdate("loft.roof", version, "1.6.0", _ROOF, _same))
    out.append(PluginUpdate("loft.roof", "1.5.0", "1.6.0", _ROOF_1_5, _same))
    out.append(PluginUpdate("loft.floor", "1.2.0", "1.3.0", _FLOOR, _floor_to_1_3))
    out.append(PluginUpdate("loft.deck", "1.1.0", "1.2.0", _DECK, _same))
    out.append(PluginUpdate("loft.foundation", "1.0.0", "1.1.0", _FOUNDATION, _same))
    out += _same_inputs_updates(plugins)
    return tuple(out)


#: Every declared update, by (plugin id, the stored release).
UPDATES: Mapping[tuple[str, str], PluginUpdate] = {
    (u.plugin_id, u.from_version): u for u in declared_updates()
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
    update: PluginUpdate,
    inputs: Mapping[str, CustomInputValue],
    context: ExpandInputs | None = None,
) -> dict[str, CustomInputValue]:
    """*inputs* carried to *update*'s target release by its explicit map.
    *context* is the stored feature's (its id and the features before it); a
    map that reads none needs none. Raises :class:`PluginError` when the map
    cannot read what it needs (a floor's outline missing)."""
    if context is None:
        context = ExpandInputs(uuid.UUID(int=0), dict(inputs))
    return update.map_inputs(inputs, context)


def check_update_table(registry: PluginRegistry) -> None:
    """Every declared update names two released versions of one plugin, the
    target its newest (a test runs this on the shipped registry)."""
    for update in UPDATES.values():
        registry.get(update.plugin_id, update.from_version)
        registry.get(update.plugin_id, update.to_version)
        if semver_key(update.to_version) <= semver_key(update.from_version):
            raise ValueError(f"{update.plugin_id} {update.from_version}: not newer")
        newest = registry.latest(update.plugin_id).manifest.version
        if update.to_version != newest:
            raise ValueError(
                f"{update.plugin_id} {update.from_version}: maps to "
                f"{update.to_version}, not the newest {newest}"
            )


# --- What an update adds ------------------------------------------------------------

#: A role's noun where its manifest title is not what a builder calls it.
_NOUNS: Mapping[tuple[str, str], str] = {
    ("loft.deck", "footing"): "pier footing",
    ("loft.wall", "header"): "header ply",
    ("loft.window", "spacer"): "header spacer",
    ("loft.door", "spacer"): "header spacer",
    ("loft.window", "foam"): "header foam insert",
    ("loft.door", "foam"): "header foam insert",
}

#: What a body's metadata lists that the update may add, by the noun.
_LISTED: Mapping[str, str] = {
    "post_base": "post base",
    "foundation_vent": "foundation vent",
    "crawl_access_door": "access door",
}


def _plural(noun: str, count: int) -> str:
    if count == 1:
        return f"1 {noun}"
    if noun.endswith("y") and noun[-2:-1] not in ("a", "e", "o", "u"):
        return f"{count} {noun[:-1]}ies"
    if noun.endswith(("s", "x", "ch", "sh")):
        return f"{count} {noun}es"
    return f"{count} {noun}s"


@dataclass(frozen=True)
class UpdateEffect:
    """What updating one stored feature does to the members it and its host
    build: what it adds, by count and noun, and whether anything changes."""

    #: "3 pier footings", "11 ceiling joists", in the order they are built.
    adds: tuple[str, ...]
    #: False when every member (the host's too) is as stored, byte for byte.
    changes: bool

    @property
    def sentence(self) -> str:
        """``Adds 3 pier footings and 3 post bases.``, or ``""``."""
        if not self.adds:
            return ""
        if len(self.adds) == 1:
            listed = self.adds[0]
        else:
            listed = ", ".join(self.adds[:-1]) + " and " + self.adds[-1]
        return f"Adds {listed}."


def _counted(
    plugin_id: str, members: Sequence[ExpandedMember], registry: PluginRegistry
) -> Counter[str]:
    """Each body of *members* by its noun, and what their metadata lists."""
    titles = {r.role: r.title for r in registry.latest(plugin_id).manifest.members}
    out: Counter[str] = Counter()
    for m in members:
        meta = m.metadata
        if meta is None:
            continue
        noun = _NOUNS.get((plugin_id, m.role)) or titles.get(m.role, m.role).lower()
        out[noun] += 1
        if meta.concrete is not None and meta.concrete.post_base is not None:
            out[_LISTED["post_base"]] += 1
        for listed in meta.foundation_openings or []:
            out[_LISTED.get(listed.item, listed.item)] += listed.quantity
    return out


def update_effect(
    changed: Iterable[tuple[str, Sequence[ExpandedMember], Sequence[ExpandedMember]]],
    registry: PluginRegistry,
) -> UpdateEffect:
    """What an update adds, from each feature it re-expands (the feature
    itself, and a hosted feature's host): ``(plugin id, the members stored,
    the members updated)``. A noun counts bodies of a role, or what their
    metadata lists (post bases, vents, access doors); it is named when the
    update builds more of it than were stored."""
    adds: list[str] = []
    changes = False
    for plugin_id, before, after in changed:
        if list(before) != list(after):
            changes = True
        old = _counted(plugin_id, before, registry)
        for noun, count in _counted(plugin_id, after, registry).items():
            if count > old[noun]:
                adds.append(_plural(noun, count - old[noun]))
    return UpdateEffect(tuple(adds), changes)


__all__ = [
    "PLUGIN_UPDATE_UNAVAILABLE",
    "SAME_INPUTS",
    "UPDATES",
    "InputMap",
    "PluginUpdate",
    "UpdateEffect",
    "check_update_table",
    "declared_updates",
    "update_effect",
    "update_for",
    "updated_inputs",
]
