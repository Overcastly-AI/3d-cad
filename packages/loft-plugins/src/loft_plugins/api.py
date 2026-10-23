"""What a plugin author writes against: inputs in, members out (RESEARCH §23).

A plugin is a :class:`PluginManifest` (``loft_wire.plugins``) and an ``expand``
function. ``expand`` is PURE: it reads :class:`ExpandInputs` and returns (or
yields) :class:`Member` s, each a base feature with a role and an index. It
does no I/O and runs no kernel code, so it cannot make geometry the base
tools could not; the same inputs give the same members on every server.

Members are referenced by :meth:`ExpandInputs.ref`, which names the stable id
the registry will give the member (``<feature-id>/<role>/<n>``), so a sweep can
name the path sketch emitted before it.
"""

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast, get_args

from loft_wire.expr import Quantity
from loft_wire.features import AuthoredEnvelope, FeatureEnvelope, FeatureRef
from loft_wire.lumber import (
    LUMBER_PROFILES,
    LUMBER_PROFILES_BY_KEY,
    LumberProfile,
    LumberProfileKey,
)
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    ChoiceOption,
    MemberMetadata,
    PluginManifest,
    member_id,
)

#: One row of a list input: field name -> float, int or str, as a top-level
#: number or choice is stored.
ListRowValue = dict[str, int | float | str]

#: A canonical input value: float for a length or angle, int for a count, str
#: for a choice or material, a ``FeatureRef`` for a profile or feature, a list
#: of them for a feature list, line ids for a segments input, rows for a list
#: input, and ``None`` for an optional feature, feature list, segments, list
#: or material left empty.
InputValue = (
    float
    | int
    | str
    | FeatureRef
    | list[FeatureRef]
    | list[str]
    | list[ListRowValue]
    | None
)


class PluginError(Exception):
    """A typed refusal (``loft_wire.plugins`` codes): a 422 on write, the
    feature's error on evaluation. ``input`` names the input at fault."""

    def __init__(self, code: str, message: str, *, input: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.input = input


@dataclass(frozen=True)
class Member:
    """One base feature of an expansion. ``(role, index)`` must be unique and
    the role declared in the manifest; the id is derived, never chosen. A
    member with a ``name`` (``slot/8``) is identified by ``(role, name)``
    instead, which must be unique too: a plugin names a member by its place
    in a layout so that an edit elsewhere never renumbers it."""

    role: str
    index: int
    feature: FeatureEnvelope
    metadata: MemberMetadata | None = None
    name: str | None = None


@dataclass(frozen=True)
class Hosted:
    """A later custom feature that names this one as its host (a window in a
    wall, RESEARCH §23): its pin, its name for messages, and its canonical,
    formula-resolved inputs. Never its expansion, so hosting cannot cycle."""

    feature_id: uuid.UUID
    plugin_id: str
    plugin_version: str
    name: str
    inputs: "ExpandInputs"


@dataclass(frozen=True)
class ExpandInputs:
    """The validated inputs of one custom feature, read-only access to the
    features before it (so a profile input can be read for its plane), and
    the later features it hosts, in tree order."""

    feature_id: uuid.UUID
    values: Mapping[str, InputValue]
    earlier: Mapping[uuid.UUID, AuthoredEnvelope] = field(
        default_factory=dict[uuid.UUID, AuthoredEnvelope]
    )
    hosted: Sequence[Hosted] = ()
    #: Prepended (``<prefix>/``) to every member name :meth:`ref` derives, so
    #: one wall of an outline names its members under its sketch line
    #: (``e3/slot/2``, BUILDING-OUTLINE). ``None``: names as given.
    name_prefix: str | None = None
    #: The part's parameter table, by name: what a sketch dimension's formula
    #: reads when a plugin resolves a picked sketch (BUILDING-OUTLINE).
    parameters: Mapping[str, Quantity] = field(default_factory=dict[str, Quantity])

    def _get(self, name: str) -> InputValue:
        if name not in self.values:
            raise PluginError(PLUGIN_INPUT_INVALID, f"no input {name!r}", input=name)
        return self.values[name]

    def number(self, name: str) -> float:
        """A length (mm) or angle (degrees) input."""
        value = self._get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise PluginError(PLUGIN_INPUT_INVALID, f"{name!r} is not a number")
        return float(value)

    def count(self, name: str) -> int:
        value = self._get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise PluginError(PLUGIN_INPUT_INVALID, f"{name!r} is not a count")
        return value

    def choice(self, name: str) -> str:
        value = self._get(name)
        if not isinstance(value, str):
            raise PluginError(PLUGIN_INPUT_INVALID, f"{name!r} is not a choice")
        return value

    def material(self, name: str) -> MaterialKey | None:
        value = self._get(name)
        if value is None:
            return None
        if not isinstance(value, str) or value not in get_args(MaterialKey):
            raise PluginError(PLUGIN_INPUT_INVALID, f"{name!r} is not a material")
        return cast(MaterialKey, value)

    def lumber(self, name: str) -> LumberProfile:
        """A choice input whose options are lumber profiles
        (:func:`lumber_options`), as the profile with its actual size."""
        value = self._get(name)
        if not isinstance(value, str) or value not in LUMBER_PROFILES_BY_KEY:
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} is not a lumber profile", input=name
            )
        return LUMBER_PROFILES_BY_KEY[cast(LumberProfileKey, value)]

    def feature(self, name: str) -> FeatureRef:
        """A profile or feature input, as the reference to put in a member."""
        value = self._get(name)
        if not isinstance(value, FeatureRef):
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} names no feature", input=name
            )
        return value

    def features(self, name: str) -> list[FeatureRef]:
        """A feature-list input's picks, in order (empty when left empty)."""
        value = self._get(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(v, FeatureRef) for v in value
        ):
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} names no features", input=name
            )
        return [v for v in value if isinstance(v, FeatureRef)]

    def segments(self, name: str) -> list[str]:
        """A segments input's line ids, in order (empty when left empty)."""
        value = self._get(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} names no lines", input=name
            )
        return [v for v in value if isinstance(v, str)]

    def rows(self, name: str) -> list["ExpandInputs"]:
        """A list input's rows, in order (empty when left empty), each read
        with :meth:`number`, :meth:`count` and :meth:`choice` by field name."""
        value = self._get(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} holds no rows", input=name
            )
        return [
            ExpandInputs(self.feature_id, cast(Mapping[str, InputValue], row))
            for row in value
            if isinstance(row, dict)
        ]

    def optional_feature(self, name: str) -> FeatureRef | None:
        """An optional feature input's pick, or ``None`` when left empty."""
        value = self._get(name)
        if value is None:
            return None
        return self.feature(name)

    def resolve(self, ref: FeatureRef) -> AuthoredEnvelope | None:
        """The earlier feature *ref* names, or ``None``."""
        return self.earlier.get(ref.feature_id)

    def ref(self, role: str, index: int = 0, name: str | None = None) -> FeatureRef:
        """A reference to this expansion's member ``(role, index)``, or
        ``(role, name)`` for a named member (under :attr:`name_prefix`)."""
        if name is not None and self.name_prefix is not None:
            name = f"{self.name_prefix}/{name}"
        return FeatureRef(
            kind="feature", feature_id=member_id(self.feature_id, role, index, name)
        )


def lumber_options(
    keys: Iterable[LumberProfileKey] | None = None,
) -> list[ChoiceOption]:
    """Choice options for a lumber-profile input, labelled by nominal size
    ("2x10"): every library profile in display order, or just *keys*. Read
    the chosen one back with :meth:`ExpandInputs.lumber`."""
    wanted = None if keys is None else set(keys)
    return [
        ChoiceOption(value=profile.key, label=profile.name)
        for profile in LUMBER_PROFILES
        if wanted is None or profile.key in wanted
    ]


#: ``expand``: inputs in, members out. May return a list or yield.
Expander = Callable[[ExpandInputs], Iterable[Member]]

#: ``settle``: a write's canonical inputs in, the inputs to STORE out, with
#: every write-time choice made (a window's "nearer the origin" stored as the
#: wall end it picks, OPENING-FROM-END). Pure, as ``expand`` is.
Settler = Callable[[ExpandInputs], Mapping[str, InputValue]]


@dataclass(frozen=True)
class Plugin:
    """One released version: its manifest and its expander, kept forever.

    ``renumbered_roles`` are the roles whose INDEX is an ordinal a re-layout
    can hand to another physical member (``loft.wall`` 1.0.0's ``stud/6``
    after a door moves). Documents refuses an edit that moves a referenced
    member of one of these roles (WALL-MEMBER-RENUMBER), since the reference
    cannot tell a member that followed the edit from one that was renumbered.
    A release that names its members by their place (``name``) has none.

    ``settle`` (optional) turns a write-time choice into the value stored, so
    a stored feature's meaning never depends on where its context later
    moves (:func:`loft_plugins.registry.settle_inputs`)."""

    manifest: PluginManifest
    expand: Expander
    renumbered_roles: frozenset[str] = frozenset()
    settle: Settler | None = None
