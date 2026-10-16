"""Plugin manifests: what a custom feature asks for (PLUGIN-REGISTRY, RESEARCH §23).

A plugin registers a CUSTOM FEATURE, as an Onshape custom feature does: typed,
bounded inputs from which the dialog is generated, and a pure ``expand`` that
turns those inputs into base features (sketch, datum, extrude, sweep, ...).
The expanders live in ``packages/loft-plugins``; this module holds only the
wire half, so documents, the gateway, the web (through the generated client)
and ``loft-script`` read one definition:

* :class:`PluginManifest` — id, semver version, title, toolbar group, typed
  inputs and the member roles it emits. Served at ``GET /api/v1/plugins`` and
  rendered into a form by the web, so no form is hand-written per plugin.
* the input kinds (:data:`PluginInput`): length, angle, count, choice,
  profile, feature reference and material. Every numeric input accepts a §20
  expression, through the envelope's ``expressions`` pointer
  (``/inputs/<name>``), so the input's NAME carries its unit exactly as a base
  feature's field name does: a length input ends ``_mm``, an angle ``_deg``,
  a count is a whole number (``loft_wire.feature_expressions.leaf_kind``).
* :class:`MemberMetadata` — role-independent facts about one generated member
  (profile, material, nominal size) for the cut list and mass.
* :func:`member_id` — the stable id of a generated member, derived from the
  custom feature's id, the member's role and its index
  (``<feature-id>/<role>/<n>``), so a pick on generated geometry keeps its
  name across an edit.

The custom-feature envelope that stores a pinned plugin, its inputs and its
last expansion is :class:`loft_wire.features.CustomFeature`.
"""

import re
import uuid
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from loft_wire.materials import MaterialKey

#: Most base features ONE custom feature may expand to (RESEARCH §23). Over it
#: is the typed error ``plugin_expansion_too_large`` on that feature. The whole
#: expanded tree is also bounded by the evaluation request's
#: ``MAX_TREE_FEATURES``, which is the tighter bound today.
MAX_PLUGIN_EXPANSION: Final = 5000

#: Wall-clock budget for ONE custom feature's expansion (seconds, RESEARCH §23).
#: Over it is the typed error ``plugin_expansion_timeout`` on that feature.
PLUGIN_EXPAND_TIME_LIMIT_S: Final = 2.0

#: Most inputs one manifest declares, and most member roles.
MAX_PLUGIN_INPUTS: Final = 32
MAX_PLUGIN_ROLES: Final = 32
#: Most options one choice input offers.
MAX_CHOICE_OPTIONS: Final = 32
#: Longest string value a custom feature's input may hold.
MAX_PLUGIN_TEXT: Final = 200

#: The namespace of every generated member id (:func:`member_id`). A fixed
#: constant: changing it would rename every member of every stored part.
PLUGIN_MEMBER_NAMESPACE: Final = uuid.UUID("6c0f7e52-3b1d-5f0e-9a4c-1d2e3f405162")

#: The typed errors a custom feature can fail with. A write refuses with them
#: (422); an evaluation reports them on the feature's members.
PLUGIN_NOT_FOUND: Final = "plugin_not_found"
PLUGIN_VERSION_NOT_FOUND: Final = "plugin_version_not_found"
PLUGIN_INPUT_INVALID: Final = "plugin_input_invalid"
PLUGIN_INPUT_UNSUPPORTED: Final = "plugin_input_unsupported"
PLUGIN_EXPANSION_TOO_LARGE: Final = "plugin_expansion_too_large"
PLUGIN_EXPANSION_TIMEOUT: Final = "plugin_expansion_timeout"
PLUGIN_EXPANSION_INVALID: Final = "plugin_expansion_invalid"
#: Editing a custom feature whose plugin (or pinned version) this server does
#: not have: the stored expansion still rebuilds, read-only.
PLUGIN_READ_ONLY: Final = "plugin_read_only"

#: ``loft.twisted_prism``: dotted lowercase segments, at least two.
PluginId = Annotated[
    str,
    StringConstraints(
        min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
    ),
]
#: A RELEASED semantic version, ``MAJOR.MINOR.PATCH`` (no pre-release tag: a
#: stored feature pins a release, and a release never changes).
SemVer = Annotated[
    str,
    StringConstraints(
        max_length=32, pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
    ),
]
#: An input's name: the key in ``params.inputs`` and the pointer segment an
#: expression drives (``/inputs/<name>``).
InputName = Annotated[
    str, StringConstraints(min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_]*$")
]
#: A member role (``joist``, ``path``): the middle segment of a member's id.
RoleName = Annotated[
    str, StringConstraints(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
]
Label = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(max_length=500)]


def semver_key(version: str) -> tuple[int, int, int]:
    """``"1.10.0"`` -> ``(1, 10, 0)``: versions order numerically, not as text."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"{version!r} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(part) for part in match.groups())
    return (major, minor, patch)


def member_key(feature_id: uuid.UUID, role: str, index: int) -> str:
    """The member's stable name, ``<feature-id>/<role>/<n>`` (RESEARCH §23)."""
    return f"{feature_id}/{role}/{index}"


def member_id(feature_id: uuid.UUID, role: str, index: int) -> uuid.UUID:
    """The member's feature id: a UUIDv5 of :func:`member_key`.

    Feature ids are UUIDs on every wire (references, results, face names), so
    the stable name is carried as the UUID derived from it. Same custom
    feature, role and index -> the same id, on every server and every rebuild.
    """
    return uuid.uuid5(PLUGIN_MEMBER_NAMESPACE, member_key(feature_id, role, index))


# --- Inputs ----------------------------------------------------------------------


class _InputBase(BaseModel):
    name: InputName = Field(
        description="Key in the custom feature's `params.inputs`, and the pointer "
        "an expression drives (`/inputs/<name>`). A length's name ends `_mm` and "
        "an angle's `_deg`, as a base feature's fields do."
    )
    label: Label = Field(description="Form label, e.g. 'Twist angle'.")
    description: Description | None = Field(
        default=None, description="Help text under the field."
    )


def _check_bounds(
    name: str, default: float, low: float | None, high: float | None, open_low: bool
) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError(f"input {name!r}: minimum is above maximum")
    if low is not None and (default < low or (open_low and default == low)):
        raise ValueError(f"input {name!r}: the default is below the minimum")
    if high is not None and default > high:
        raise ValueError(f"input {name!r}: the default is above the maximum")


class _NumberInput(_InputBase):
    default: float = Field(allow_inf_nan=False, description="Value a new feature gets.")
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    exclusive_minimum: bool = Field(
        default=False, description="True: the value must be strictly above `minimum`."
    )


class LengthInput(_NumberInput):
    """A length in mm (a distance, a spacing). Accepts a §20 expression."""

    kind: Literal["length"]
    unit: Literal["mm"] = "mm"

    @model_validator(mode="after")
    def _named_and_bounded(self) -> Self:
        if not self.name.endswith("_mm"):
            raise ValueError(f"length input {self.name!r} must end with '_mm'")
        _check_bounds(
            self.name, self.default, self.minimum, self.maximum, self.exclusive_minimum
        )
        return self


class AngleInput(_NumberInput):
    """An angle in degrees. Accepts a §20 expression."""

    kind: Literal["angle"]
    unit: Literal["deg"] = "deg"

    @model_validator(mode="after")
    def _named_and_bounded(self) -> Self:
        if not self.name.endswith("_deg"):
            raise ValueError(f"angle input {self.name!r} must end with '_deg'")
        _check_bounds(
            self.name, self.default, self.minimum, self.maximum, self.exclusive_minimum
        )
        return self


class CountInput(_InputBase):
    """A whole number of things (studs, rungs). Accepts a §20 expression that
    evaluates to a whole plain number."""

    kind: Literal["count"]
    default: int
    minimum: int = Field(default=0, ge=0)
    maximum: int = Field(le=MAX_PLUGIN_EXPANSION)

    @model_validator(mode="after")
    def _named_and_bounded(self) -> Self:
        if self.name.endswith(("_mm", "_deg")):
            raise ValueError(f"count input {self.name!r} is not a length or angle")
        _check_bounds(self.name, self.default, self.minimum, self.maximum, False)
        return self


class ChoiceOption(BaseModel):
    """One option of a choice input."""

    value: InputName
    label: Label


class ChoiceInput(_InputBase):
    """One of a fixed list of options (a direction, add or cut)."""

    kind: Literal["choice"]
    options: list[ChoiceOption] = Field(min_length=1, max_length=MAX_CHOICE_OPTIONS)
    default: InputName

    @model_validator(mode="after")
    def _default_is_an_option(self) -> Self:
        values = [option.value for option in self.options]
        if len(set(values)) != len(values):
            raise ValueError(f"choice input {self.name!r} repeats an option")
        if self.default not in values:
            raise ValueError(f"choice input {self.name!r}: default is not an option")
        return self


class ProfileInput(_InputBase):
    """An earlier SKETCH whose closed wire is the profile (picked in the
    viewport or the tree). Stored as a ``FeatureRef``."""

    kind: Literal["profile"]


class FeatureReferenceInput(_InputBase):
    """An earlier feature of one of ``feature_types`` (a host wall, a datum).
    Stored as a ``FeatureRef``. Hosting is by inputs, never by geometry."""

    kind: Literal["feature"]
    feature_types: list[Annotated[str, StringConstraints(max_length=64)]] = Field(
        min_length=1,
        max_length=32,
        description="Feature types the picked feature may be "
        "(`datum`, `sketch`, `custom`, ...).",
    )
    optional: bool = Field(default=False, description="True: may be left empty.")


class MaterialInput(_InputBase):
    """A library material for the generated members (their mass and cut list)."""

    kind: Literal["material"]
    default: MaterialKey | None = None


#: One typed input of a custom feature, discriminated on ``kind``.
PluginInput = Annotated[
    LengthInput
    | AngleInput
    | CountInput
    | ChoiceInput
    | ProfileInput
    | FeatureReferenceInput
    | MaterialInput,
    Field(discriminator="kind"),
]


# --- Members ---------------------------------------------------------------------


class PluginMemberRole(BaseModel):
    """A role the plugin's members take (``joist``, ``path``): the middle
    segment of each member's id, and the group a member unfolds under in the
    tree."""

    role: RoleName
    title: Label
    description: Description | None = None


class MemberMetadata(BaseModel):
    """What the cut list and mass need about one generated member (RESEARCH §23).

    All optional: a helper member (a path sketch) carries none.
    """

    profile: Annotated[str, StringConstraints(max_length=80)] | None = Field(
        default=None, description="Section the member is cut from, e.g. '2x8'."
    )
    material: MaterialKey | None = Field(
        default=None, description="Library material of the member."
    )
    nominal_size: Annotated[str, StringConstraints(max_length=80)] | None = Field(
        default=None, description="Nominal size as sold, e.g. '2x8x12'."
    )


# --- The manifest ----------------------------------------------------------------


class PluginManifest(BaseModel):
    """One released version of a plugin: what the toolbar and form are built
    from (``GET /api/v1/plugins``). Immutable once released: a change to what
    the plugin builds from existing inputs is a new version."""

    id: PluginId = Field(description="Stable plugin id, e.g. 'loft.twisted_prism'.")
    version: SemVer = Field(description="Released version, MAJOR.MINOR.PATCH.")
    title: Label = Field(description="Toolbar and tree title, e.g. 'Twisted prism'.")
    description: Description = Field(description="One-line help for the tool.")
    group: Literal["build"] = Field(
        default="build", description="Toolbar group the tool sits in."
    )
    inputs: list[PluginInput] = Field(min_length=1, max_length=MAX_PLUGIN_INPUTS)
    members: list[PluginMemberRole] = Field(
        min_length=1,
        max_length=MAX_PLUGIN_ROLES,
        description="Roles the expansion's members take, in tree order.",
    )
    latest: bool = Field(
        default=False,
        description="True on the newest released version of this plugin: the "
        "one a new feature is inserted with. Older versions are listed so a "
        "feature pinned to one still gets its form.",
    )

    @model_validator(mode="after")
    def _unique_names(self) -> Self:
        names = [item.name for item in self.inputs]
        if len(set(names)) != len(names):
            raise ValueError(f"plugin {self.id!r} repeats an input name")
        roles = [item.role for item in self.members]
        if len(set(roles)) != len(roles):
            raise ValueError(f"plugin {self.id!r} repeats a member role")
        return self


class PluginCatalog(BaseModel):
    """Every released version of every installed plugin (``GET /api/v1/plugins``),
    ordered by id, newest version first."""

    plugins: list[PluginManifest]
