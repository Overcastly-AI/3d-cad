"""Updating a stored custom feature to its newest release (OPENING-UPDATE,
PLUGIN-UPDATE-ALL, RESEARCH §23).

Onshape marks a custom feature whose Feature Studio has a newer version and
updates it on request, every input it can map carried across and every new
parameter at its default; Fusion badges out-of-date linked content. A stored
feature here keeps its pin until the user updates it, and an update is an
ordinary edit of the feature: the pin moves to the newest release and the
inputs are carried across by an EXPLICIT map, one per release pair (the
table :data:`_TABLE`, one row per map). A released manifest is frozen, so
the map is what says how an old feature's meaning reads in the new release;
an input the old release did not have takes the new release's default (the
caller's ``canonical_inputs`` fills it), so an update may add members, and it
names what it adds (:func:`update_effect`).

An update never moves what the feature already built without saying so: a
member stored before the update that it changes or drops (a joist laid from
another corner) is RE-LAID, and :func:`update_effect` names those too. An
update that re-lays anything is offered on its own feature only, never
taken by Update all, which lists it as needing its own decision.

* ``loft.window`` / ``loft.door`` 1.0.0-1.4.0 -> 1.5.0. Each input the old
  release had keeps its value. What a later release added is set to what
  the old one built: Measured from the wall's start (1.2.0), a Custom size
  that reads the typed size and allowances, and no unit drawn (1.3.0, as
  through 1.2.0 nothing was). Header build becomes Fill the wall (1.4.0's
  default, three plies in a 2x6 wall). A 1.4.0 opening keeps its own Header
  build.
* ``loft.wall`` 1.2.0 and 1.3.0 -> 1.5.0, every input as it is: 1.4.0 is
  1.3.0 member for member (and a typed wall 1.2.0's), plus the backing of
  partitions that meet it and an inside gypsum left at None; 1.5.0 adds the
  Exterior finish below, at None.
* ``loft.wall`` 1.4.0 -> 1.5.0 (SIDING-TRIM), every input as it is, so
  Exterior finish takes 1.5.0's default, None: the update adds no member
  (1.4.0's member for member), so it wears no badge and rides in Update
  all. Siding is a material the user picks, as Chief's wall type is, so an
  update never adds siding nobody asked for (VISION, 2026-10-30).
* ``loft.roof`` 1.2.0-1.5.0 -> 1.6.0, every input as it is, so Ceiling
  joists takes 1.6.0's default, Beside each common: a gable on an outline or
  on picked walls gains its ceiling joists (B7's 11), as a new roof frames
  them. A joist that cannot fit (it would pass the ridge board) is left out
  and the roof warns ``ceiling_joists_omitted``; the update never refuses.
  This replaces CEILING-JOISTS' review call (0d22c34) that an update maps
  the joists to None (VISION, 2026-10-29). Since 1.7.0 (GABLE-END-STUDS)
  they go straight to 1.7.0, so Gable ends takes its default too.
* ``loft.roof`` 1.6.0 -> 1.7.0, every input as it is, so Gable ends takes
  1.7.0's default, Studs and sheathing: a gable on an outline gains its
  gable studs on each end wall's plate and the end walls' sheathing carried
  up to the roof (B7's 22 and 12). A ceiling joist that would lie on an end
  wall's plate is no longer framed (the end wall carries the ceiling there),
  which is a re-lay, so that update is offered on its own. Since 1.8.0
  (SIDING-TRIM) every roof 1.2.0-1.6.0 goes straight to 1.8.0.
* ``loft.roof`` 1.7.0 -> 1.8.0, every input as it is: a gable on outline
  walls with an Exterior finish (``loft.wall`` 1.5.0) carries the finish up
  each gable over the sheathing (2 gable siding layers on B7 sided); on
  walls with none, as every updated wall is, it is 1.7.0 member for member.
* ``loft.floor`` 1.2.0 -> 1.3.0: Joist direction becomes the Joists bear on
  (Long walls first, then Front and back, then Left and right) whose
  expansion frames 1.2.0's joists, rims and sills member for member. 1.2.0
  laid an outline's floor from its first line's corner and 1.3.0 lays it from
  the outline's lowest corner, so on a drawing where those differ and the
  spacing does not divide the floor, no choice reproduces them: the map
  keeps the span 1.2.0 framed and the update re-lays the framing (B7's own
  drawing is byte for byte).
  Since 1.4.0 (SECOND-FLOOR) a floor 1.2.0 goes straight to 1.4.0.
* ``loft.floor`` 1.3.0 -> 1.4.0, every input as it is, so On walls takes
  1.4.0's default, none, and Stairwell None: the update adds no member (1.3.0
  member for member), so it is quiet and rides in Update all. A floor on
  walls and a stairwell are what the user picks, never added by an update.
* ``loft.deck`` 1.1.0 -> 1.3.0, every input as it is: each post gains its
  round pier footing and post base (1.2.0's defaults; B1's 3 piers), and
  the guard opens at each stair that picks the deck (1.3.0).
* ``loft.deck`` 1.2.0 -> 1.3.0, every input as it is: a guarded deck opens
  its guard where a stair lands on its edge, the side's runs either side of
  the stair laid out again with a post at each side (DECK-GUARD-OPENING).
  That re-lays the side's guard posts, rails and balusters, so the update is
  offered on its own; a deck with no stair, or no guard, is 1.2.0 member for
  member and its update is quiet.
* ``loft.foundation`` 1.0.0 -> 1.1.0, every input as it is: the stem lists
  the vents and the access door it cuts (B9's 5 and 1), priced Each.
* ``loft.cabinets`` 1.0.0 -> 1.1.0: 1.1.0 stands a run on the wall's
  FINISHED face and measures its Distance from that face's end, so the map
  takes the face's board off the Back gap and the finished end's setback
  off the Distance, and the run keeps every panel. A stored run that
  already stood in the board (a Back gap or Distance under it) cannot keep
  its place at 1.1.0's minimum of 0; it is re-laid.

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

from loft_wire.features import CustomInputValue, ExpandedMember, feature_references
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import semver_key

from loft_plugins.api import ExpandInputs, PluginError
from loft_plugins.builtin import cabinets as cabinets_v1
from loft_plugins.builtin.building_outline import FLOOR_V1_2, FLOOR_V1_3
from loft_plugins.builtin.cabinets_v1_1 import finished_face
from loft_plugins.builtin.house import floor_values, floor_values_v1_3
from loft_plugins.registry import PluginRegistry, canonical_inputs, expand

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
    #: counts of what it adds and re-lays are the feature's own:
    #: :func:`update_effect`).
    summary: str
    map_inputs: InputMap
    #: Why it re-lays what it re-lays, when it does (" from the outline's
    #: lowest corner"), ending the effect's sentence.
    relay_reason: str = ""


def _same(
    inputs: Mapping[str, CustomInputValue], _context: ExpandInputs
) -> dict[str, CustomInputValue]:
    return dict(inputs)


# --- Openings -----------------------------------------------------------------------

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


# --- Floors -------------------------------------------------------------------------

#: Joists bear on, in the order the floor map tries them: the default first,
#: so a floor whose old framing is the default's keeps the default.
_BEAR_ON = ("long_walls", "front_back", "left_right")
#: The floor's framing the map must reproduce (its subfloor follows it).
_FRAMING = frozenset({"joist", "rim", "sill"})


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
    first Joists bear on whose expansion frames 1.2.0's joists, rims and
    sills member for member; when none does, the first whose joists run the
    way 1.2.0's did (the update then re-lays them, and says so). Raises
    :class:`PluginError` when the floor's outline cannot be read."""
    old_values = dataclasses.replace(context, values=dict(inputs))
    want = _joist_angle(floor_values(old_values))
    base = {k: v for k, v in inputs.items() if k != "joist_direction"}
    before = expand(
        FLOOR_V1_2,
        context.feature_id,
        inputs,
        context.earlier,
        parameters=context.parameters,
    )
    same_way: dict[str, CustomInputValue] | None = None
    for bear_on in _BEAR_ON:
        candidate = canonical_inputs(
            FLOOR_V1_3.manifest, {**base, "joists_bear_on": bear_on}
        )
        new = floor_values_v1_3(dataclasses.replace(context, values=candidate))
        gap = abs(_joist_angle(new) - want) % 180.0
        if min(gap, 180.0 - gap) >= 1e-6:
            continue
        after = expand(
            FLOOR_V1_3,
            context.feature_id,
            candidate,
            context.earlier,
            parameters=context.parameters,
        )
        if not any(m.role in _FRAMING for m in relaid(before, after)):
            return dict(candidate)
        if same_way is None:
            same_way = dict(candidate)
    if same_way is None:  # unreachable: two of the three run each way
        raise PluginError(
            PLUGIN_UPDATE_UNAVAILABLE, "No Joists bear on frames this floor's joists."
        )
    return same_way


# --- Cabinets -----------------------------------------------------------------------


def _cabinets_to_1_1(
    inputs: Mapping[str, CustomInputValue], context: ExpandInputs
) -> dict[str, CustomInputValue]:
    """A run 1.0.0's inputs at 1.1.0, placed where 1.0.0 placed it: the Back
    gap less the finished face's board, the Distance less the finished end's
    setback from the framing's end. A typed run is as it is. A value that
    would fall under 1.1.0's minimum of 0 is held at 0, and the update then
    re-lays the run (it stood in the board)."""
    out = dict(inputs)
    values = dataclasses.replace(context, values=dict(inputs))
    ref = values.optional_feature("wall")
    if ref is None:
        return out
    face = finished_face(values, ref)
    framing = cabinets_v1.framing_length(values, ref)
    setback = (
        framing - face.last if values.choice("measure_from") == "end" else face.first
    )
    gap = values.number("gap_mm") - face.finish * MM_PER_INCH
    offset = values.number("offset_mm") - setback * MM_PER_INCH
    out["gap_mm"] = max(0.0, round(gap, 9))
    out["offset_mm"] = max(0.0, round(offset, 9))
    return out


# --- Summaries ----------------------------------------------------------------------

_OPENING_FILL = (
    "Fills the header to the wall's thickness (three plies with two 1/2 in "
    "plywood spacers in a 2x6 wall) and lists and prices the spacers."
)
_OPENING_INFILL = (
    "Draws the header's 1/2 in plywood spacers (or an insulated header's "
    "foam), so the cut list and price book carry them."
)
_WALL = (
    "Frames the backing of partitions that meet it, can take an inside "
    "gypsum finish, and offers an Exterior finish (None until you pick "
    "siding); its framing is unchanged."
)
_WALL_1_4 = (
    "Offers an Exterior finish, None until you pick Lap, Vinyl or Cedar to "
    "side the walls with corner boards and casing; nothing is rebuilt."
)
_GABLE_ENDS = (
    "frames its end walls up to the roof with gable studs on their layout and "
    "carries their sheathing (and any siding) up the gables"
)
_ROOF_1_7 = "A gable on its walls carries their exterior finish up the gables."
_ROOF = (
    "Notches the wall sheathing round the rafter tails, as framers do, ties a "
    "gable with a ceiling joist beside each common (one that cannot fit under "
    f"the ridge is left out, with a warning) and {_GABLE_ENDS}."
)
_ROOF_1_5 = (
    "Ties a gable with a ceiling joist beside each common (one that cannot "
    f"fit under the ridge is left out, with a warning) and {_GABLE_ENDS}; a "
    "hip or a typed bearing is unchanged."
)
_ROOF_1_6 = (
    f"A gable on its walls {_GABLE_ENDS}; a hip or a typed bearing is unchanged."
)
_FLOOR = (
    "Joists bear on replaces Joist direction, set to the span this floor "
    "frames; 1.3.0 lays an outline's floor from its lowest corner."
)
_FLOOR_1_3 = (
    "Can stand on the walls of the storey below and frame a stairwell, "
    "both off until you pick them; nothing is rebuilt."
)
_GUARD_OPENS = (
    "opens the guard where a stair lands on the deck, with a post at each side"
)
_DECK = (
    "Stands each post on a round pier footing with its post base, the "
    f"concrete bought in 80 lb bags, and {_GUARD_OPENS}."
)
_DECK_1_2 = (
    f"{_GUARD_OPENS[0].upper()}{_GUARD_OPENS[1:]}; a deck with no stair is unchanged."
)
_FOUNDATION = (
    "Lists the foundation vents and the access door set in the stem wall, priced Each."
)
_CABINETS = (
    "Stands the run on the wall's finished face, its Back gap and Distance "
    "taken from the gypsum, so the run keeps its place."
)

#: Why a deck update re-lays its guard.
_AT_THE_STAIR = " to open the guard at the stair"

# --- The table ----------------------------------------------------------------------

#: (plugin, the stored releases, the target, summary, map, re-lay reason):
#: one row per map, so a release adds its own row.
_TABLE: tuple[tuple[str, tuple[str, ...], str, str, InputMap, str], ...] = (
    (
        "loft.window",
        ("1.0.0", "1.1.0", "1.2.0", "1.3.0"),
        "1.5.0",
        _OPENING_FILL,
        _opening_to_1_5,
        "",
    ),
    ("loft.window", ("1.4.0",), "1.5.0", _OPENING_INFILL, _opening_to_1_5, ""),
    (
        "loft.door",
        ("1.0.0", "1.1.0", "1.2.0", "1.3.0"),
        "1.5.0",
        _OPENING_FILL,
        _opening_to_1_5,
        "",
    ),
    ("loft.door", ("1.4.0",), "1.5.0", _OPENING_INFILL, _opening_to_1_5, ""),
    ("loft.wall", ("1.2.0", "1.3.0"), "1.5.0", _WALL, _same, ""),
    ("loft.wall", ("1.4.0",), "1.5.0", _WALL_1_4, _same, ""),
    ("loft.roof", ("1.2.0", "1.3.0", "1.4.0"), "1.8.0", _ROOF, _same, ""),
    ("loft.roof", ("1.5.0",), "1.8.0", _ROOF_1_5, _same, ""),
    ("loft.roof", ("1.6.0",), "1.8.0", _ROOF_1_6, _same, ""),
    ("loft.roof", ("1.7.0",), "1.8.0", _ROOF_1_7, _same, ""),
    (
        "loft.floor",
        ("1.2.0",),
        "1.4.0",
        _FLOOR,
        _floor_to_1_3,
        " from the outline's lowest corner",
    ),
    ("loft.floor", ("1.3.0",), "1.4.0", _FLOOR_1_3, _same, ""),
    ("loft.deck", ("1.1.0",), "1.3.0", _DECK, _same, _AT_THE_STAIR),
    ("loft.deck", ("1.2.0",), "1.3.0", _DECK_1_2, _same, _AT_THE_STAIR),
    ("loft.foundation", ("1.0.0",), "1.1.0", _FOUNDATION, _same, ""),
    (
        "loft.cabinets",
        ("1.0.0",),
        "1.1.0",
        _CABINETS,
        _cabinets_to_1_1,
        " out of the wall's gypsum",
    ),
)


def declared_updates() -> tuple[PluginUpdate, ...]:
    """Every update :data:`_TABLE` declares, one per stored release."""
    return tuple(
        PluginUpdate(plugin_id, version, target, summary, mapping, reason)
        for plugin_id, versions, target, summary, mapping, reason in _TABLE
        for version in versions
    )


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


# --- What an update adds and re-lays ------------------------------------------------


def relaid(
    before: Sequence[ExpandedMember], after: Sequence[ExpandedMember]
) -> list[ExpandedMember]:
    """The members of *before* an update moves: gone from *after*, built
    differently there, or built on a member it moves (a joist on a moved
    level). A member's running index is not its place, so it is not
    compared; nor is its metadata, which only lists (vents, post bases)."""
    now = {m.id: m for m in after}
    moved: set[uuid.UUID] = set()
    out: list[ExpandedMember] = []
    for m in before:
        new = now.get(m.id)
        refs = {r.ref.feature_id for r in feature_references(m.feature)}
        if new is None or new.feature != m.feature or refs & moved:
            moved.add(m.id)
            out.append(m)
    return out


#: A role's noun where its manifest title is not what a builder calls it.
_NOUNS: Mapping[tuple[str, str], str] = {
    ("loft.deck", "footing"): "pier footing",
    ("loft.wall", "header"): "header ply",
    ("loft.window", "spacer"): "header spacer",
    ("loft.door", "spacer"): "header spacer",
    ("loft.window", "foam"): "header foam insert",
    ("loft.door", "foam"): "header foam insert",
    ("loft.floor", "subfloor"): "subfloor panel",
    ("loft.cabinets", "drawer_end"): "drawer end",
    ("loft.roof", "gable_sheathing"): "gable sheathing panel",
    ("loft.wall", "siding"): "siding layer",
    ("loft.wall", "casing"): "casing piece",
    ("loft.roof", "gable_siding"): "gable siding layer",
}

#: What a long list of re-laid nouns is summed as, by plugin ("75 panels").
_COLLECTIVE: Mapping[str, str] = {"loft.cabinets": "panel"}
#: Most nouns a re-lay names before it is summed.
_MAX_RELAID_NOUNS = 4

#: What a body's metadata lists that the update may add, by the noun.
_LISTED: Mapping[str, str] = {
    "post_base": "post base",
    "foundation_vent": "foundation vent",
    "crawl_access_door": "access door",
}


def _plural(noun: str, count: int) -> str:
    if count == 1:
        return f"1 {noun}"
    if noun.endswith("lf"):
        return f"{count} {noun[:-1]}ves"
    if noun.endswith("y") and noun[-2:-1] not in ("a", "e", "o", "u"):
        return f"{count} {noun[:-1]}ies"
    if noun.endswith(("s", "x", "ch", "sh")):
        return f"{count} {noun}es"
    return f"{count} {noun}s"


def _listed(items: Sequence[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


@dataclass(frozen=True)
class UpdateEffect:
    """What updating one stored feature does to the members it and its host
    build: what it adds and what it re-lays, by count and noun, and whether
    anything changes."""

    #: "3 pier footings", "11 ceiling joists", in the order they are built.
    adds: tuple[str, ...]
    #: False when every member (the host's too) is as stored, byte for byte.
    changes: bool
    #: "12 joists", "21 subfloor panels": stored bodies the update moves.
    relays: tuple[str, ...] = ()
    #: Why it re-lays them (the update's ``relay_reason``).
    relay_reason: str = ""

    @property
    def sentence(self) -> str:
        """``Adds 3 pier footings and 3 post bases.``, ``Re-lays 12 joists
        and 21 subfloor panels from the outline's lowest corner.``, both, or
        ``""``."""
        out: list[str] = []
        if self.relays:
            out.append(f"Re-lays {_listed(self.relays)}{self.relay_reason}.")
        if self.adds:
            out.append(f"Adds {_listed(self.adds)}.")
        return " ".join(out)


def _bodies(
    plugin_id: str, members: Sequence[ExpandedMember], registry: PluginRegistry
) -> Counter[str]:
    """Each body of *members* by its noun."""
    titles = {r.role: r.title for r in registry.latest(plugin_id).manifest.members}
    return Counter(
        _NOUNS.get((plugin_id, m.role)) or titles.get(m.role, m.role).lower()
        for m in members
        if m.metadata is not None
    )


def _counted(
    plugin_id: str, members: Sequence[ExpandedMember], registry: PluginRegistry
) -> Counter[str]:
    """Each body of *members* by its noun, and what their metadata lists."""
    out = _bodies(plugin_id, members, registry)
    for m in members:
        meta = m.metadata
        if meta is None:
            continue
        if meta.concrete is not None and meta.concrete.post_base is not None:
            out[_LISTED["post_base"]] += 1
        for listed in meta.foundation_openings or []:
            out[_LISTED.get(listed.item, listed.item)] += listed.quantity
    return out


def update_effect(
    changed: Iterable[tuple[str, Sequence[ExpandedMember], Sequence[ExpandedMember]]],
    registry: PluginRegistry,
    relay_reason: str = "",
) -> UpdateEffect:
    """What an update adds and re-lays, from each feature it re-expands (the
    feature itself, and a hosted feature's host): ``(plugin id, the members
    stored, the members updated)``. A noun counts bodies of a role, or what
    their metadata lists (post bases, vents, access doors); it is added when
    the update builds more of it than were stored, and re-laid when a stored
    body of it moves (:func:`relaid`)."""
    adds: list[str] = []
    relays: list[str] = []
    changes = False
    for plugin_id, before, after in changed:
        if list(before) != list(after):
            changes = True
        old = _counted(plugin_id, before, registry)
        for noun, count in _counted(plugin_id, after, registry).items():
            if count > old[noun]:
                adds.append(_plural(noun, count - old[noun]))
        moved = _bodies(plugin_id, relaid(before, after), registry)
        if len(moved) > _MAX_RELAID_NOUNS:
            noun = _COLLECTIVE.get(plugin_id, "member")
            relays.append(_plural(noun, sum(moved.values())))
        else:
            relays += [_plural(noun, count) for noun, count in moved.items()]
    return UpdateEffect(
        tuple(adds), changes, tuple(relays), relay_reason if relays else ""
    )


__all__ = [
    "PLUGIN_UPDATE_UNAVAILABLE",
    "UPDATES",
    "InputMap",
    "PluginUpdate",
    "UpdateEffect",
    "check_update_table",
    "declared_updates",
    "relaid",
    "update_effect",
    "update_for",
    "updated_inputs",
]
