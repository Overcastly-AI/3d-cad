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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import cast, get_args

from loft_wire.features import AuthoredEnvelope, FeatureEnvelope, FeatureRef
from loft_wire.materials import MaterialKey
from loft_wire.plugins import (
    PLUGIN_INPUT_INVALID,
    MemberMetadata,
    PluginManifest,
    member_id,
)

#: A canonical input value: float for a length or angle, int for a count, str
#: for a choice or material, a ``FeatureRef`` for a profile or feature, and
#: ``None`` for an optional feature or material left empty.
InputValue = float | int | str | FeatureRef | None


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
    the role declared in the manifest; the id is derived, never chosen."""

    role: str
    index: int
    feature: FeatureEnvelope
    metadata: MemberMetadata | None = None


@dataclass(frozen=True)
class ExpandInputs:
    """The validated inputs of one custom feature, and read-only access to
    the features before it (so a profile input can be read for its plane)."""

    feature_id: uuid.UUID
    values: Mapping[str, InputValue]
    earlier: Mapping[uuid.UUID, AuthoredEnvelope] = field(
        default_factory=dict[uuid.UUID, AuthoredEnvelope]
    )

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

    def feature(self, name: str) -> FeatureRef:
        """A profile or feature input, as the reference to put in a member."""
        value = self._get(name)
        if not isinstance(value, FeatureRef):
            raise PluginError(
                PLUGIN_INPUT_INVALID, f"{name!r} names no feature", input=name
            )
        return value

    def resolve(self, ref: FeatureRef) -> AuthoredEnvelope | None:
        """The earlier feature *ref* names, or ``None``."""
        return self.earlier.get(ref.feature_id)

    def ref(self, role: str, index: int = 0) -> FeatureRef:
        """A reference to this expansion's member ``(role, index)``."""
        return FeatureRef(
            kind="feature", feature_id=member_id(self.feature_id, role, index)
        )


#: ``expand``: inputs in, members out. May return a list or yield.
Expander = Callable[[ExpandInputs], Iterable[Member]]


@dataclass(frozen=True)
class Plugin:
    """One released version: its manifest and its expander, kept forever."""

    manifest: PluginManifest
    expand: Expander
