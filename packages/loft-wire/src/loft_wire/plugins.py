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
  profile, feature reference, feature list (several picks, as a roof's
  walls), segments (lines of an outline sketch, as a roof's slope walls),
  material, and list (an ordered list of rows of number and choice fields,
  as a cabinet run's boxes). Every numeric input accepts a §20
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

import math
import re
import uuid
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    StrictFloat,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from loft_wire.casework import EdgeBanding, HardwareCount
from loft_wire.foundation import AnchorBolts, ConcretePour, RebarRun
from loft_wire.materials import MaterialKey
from loft_wire.opening_units import OpeningUnitPart
from loft_wire.refs import FeatureRef
from loft_wire.twist import is_none

#: Most base features ONE custom feature may expand to (RESEARCH §23). Over it
#: is the typed error ``plugin_expansion_too_large`` on that feature. The whole
#: expanded tree is also bounded by the evaluation request's
#: ``MAX_TREE_FEATURES``, which is the tighter bound today.
MAX_PLUGIN_EXPANSION: Final = 5000

#: CPU-time budget for ONE custom feature's expansion (seconds of the expanding
#: thread's CPU, RESEARCH §23). CPU, not wall-clock, so a loaded server never
#: fails an expansion that is cheap alone. Over it is the typed error
#: ``plugin_expansion_timeout`` on that feature.
PLUGIN_EXPAND_TIME_LIMIT_S: Final = 2.0
#: Wall-clock backstop for the same expansion: a plugin that sleeps or blocks
#: spends no CPU but still cannot hang a request. Also
#: ``plugin_expansion_timeout``.
PLUGIN_EXPAND_WALL_LIMIT_S: Final = 10.0

#: Most inputs one manifest declares, and most member roles.
MAX_PLUGIN_INPUTS: Final = 32
MAX_PLUGIN_ROLES: Final = 32
#: Most options one choice input offers.
MAX_CHOICE_OPTIONS: Final = 32
#: Longest string value a custom feature's input may hold.
MAX_PLUGIN_TEXT: Final = 200
#: Most features one feature-list input may name (a roof's picked walls).
MAX_FEATURE_LIST: Final = 32
#: Most outline segments one segments input may name (a roof's slope walls).
MAX_SEGMENTS: Final = 32
#: Most rows one list input may hold (a cabinet run's boxes), and most fields
#: one row declares.
MAX_LIST_ITEMS: Final = 32
MAX_LIST_FIELDS: Final = 16

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
#: A member's stable name within its role (WALL-MEMBER-RENUMBER, RESEARCH §23):
#: ``slot/8``, ``end``, ``opening/<door-id>/0``. Slash-separated lowercase
#: segments, the first starting with a letter, so a name never reads as an
#: index. A member with a name is identified by it instead of its index.
MemberName = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_]*(/[a-z0-9_.-]+)*$"
    ),
]
#: ``ExpandedMember.name`` (:mod:`loft_wire.features`): absent while ``None``.
MemberNameField = Annotated[
    MemberName | None,
    Field(
        exclude_if=is_none,
        description="The member's stable name within its role (`slot/8`, `end`), "
        "when the plugin names it by its place in a layout rather than by its "
        "ordinal (loft.wall and loft.deck 1.1.0); absent on members named by index.",
    ),
]
#: A sketch line's id as a segments input stores it (``e3``): the sketch-local
#: entity id of one line of an outline (BUILDING-OUTLINE).
SegmentId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"),
]
#: One field of one row of a list input: a number or an option key.
ListFieldValue = (
    StrictInt
    | StrictFloat
    | Annotated[str, StringConstraints(max_length=MAX_PLUGIN_TEXT)]
)
#: One row of a list input: field name -> value.
ListRow = Annotated[
    dict[
        Annotated[
            str,
            StringConstraints(
                min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_]*$"
            ),
        ],
        ListFieldValue,
    ],
    Field(max_length=MAX_LIST_FIELDS),
]
#: One input value: a number (mm, degrees or a count, by the input's kind), an
#: option or material key, one or more earlier features, one or more lines
#: of an outline (their sketch ids), or the rows of a list input. Strict: no
#: ``true``. Tried left to right, so a list of picks is never read as rows
#: (a ``FeatureRef`` is a dict too, and a dict is the rows' exact type).
CustomInputValue = Annotated[
    StrictInt
    | StrictFloat
    | Annotated[str, StringConstraints(max_length=MAX_PLUGIN_TEXT)]
    | FeatureRef
    | Annotated[list[FeatureRef], Field(min_length=1, max_length=MAX_FEATURE_LIST)]
    | Annotated[list[SegmentId], Field(min_length=1, max_length=MAX_SEGMENTS)]
    | Annotated[list[ListRow], Field(min_length=1, max_length=MAX_LIST_ITEMS)],
    Field(union_mode="left_to_right"),
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


def member_key(
    feature_id: uuid.UUID, role: str, index: int, name: str | None = None
) -> str:
    """The member's stable name, ``<feature-id>/<role>/<n>`` (RESEARCH §23),
    or ``<feature-id>/<role>/<name>`` for a member a plugin names by its place
    in a layout (``stud/slot/8``) rather than by its ordinal."""
    return f"{feature_id}/{role}/{index if name is None else name}"


def member_id(
    feature_id: uuid.UUID, role: str, index: int, name: str | None = None
) -> uuid.UUID:
    """The member's feature id: a UUIDv5 of :func:`member_key`.

    Feature ids are UUIDs on every wire (references, results, face names), so
    the stable name is carried as the UUID derived from it. Same custom
    feature, role and index (or name) -> the same id, on every server and
    every rebuild.
    """
    return uuid.uuid5(
        PLUGIN_MEMBER_NAMESPACE, member_key(feature_id, role, index, name)
    )


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
    superseded_by: InputName | None = Field(
        default=None,
        exclude_if=is_none,
        description="Another input of this manifest that makes this one unused: "
        "a feature pick, once set (a wall's start, direction and length when an "
        "outline is picked, BUILDING-OUTLINE), or a choice, on any option but "
        "`superseded_unless` (a window's typed size unless Size is Custom, "
        "OPENING-UNITS). The form hides this input while it is unused; its "
        "stored value is kept. Absent: always used.",
    )
    superseded_unless: InputName | None = Field(
        default=None,
        exclude_if=is_none,
        description="When `superseded_by` names a choice: the option of it that "
        "uses this input ('custom'); every other option hides it. Absent for a "
        "feature pick.",
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
    plugin_ids: list[PluginId] | None = Field(
        default=None,
        max_length=8,
        description="When the picked feature is a custom feature: the plugins "
        "it may be (a window's host is a `loft.wall`). Unset: any.",
    )
    host: bool = Field(
        default=False,
        description="True: the picked feature HOSTS this one, as a Revit window "
        "is hosted in its wall. The host's expansion receives this feature's "
        "inputs (it frames the opening), and a write to this feature "
        "re-expands its host. Requires `feature_types` `['custom']`, "
        "`plugin_ids` and a required pick; one per manifest.",
    )

    @model_validator(mode="after")
    def _host_names_a_plugin(self) -> Self:
        if self.host and (
            self.feature_types != ["custom"] or not self.plugin_ids or self.optional
        ):
            raise ValueError(
                f"host input {self.name!r} must be a required pick of a custom "
                "feature of named plugins"
            )
        if self.plugin_ids is not None and "custom" not in self.feature_types:
            raise ValueError(
                f"input {self.name!r}: plugin_ids needs feature type 'custom'"
            )
        return self


class FeatureListInput(_InputBase):
    """Several earlier features of one of ``feature_types``, in pick order:
    a roof's bearing walls, as Revit's Roof by Footprint picks walls. Stored
    as a list of ``FeatureRef`` (no repeats); an empty pick is stored as no
    value, allowed only when ``min_items`` is 0. Never a host."""

    kind: Literal["features"]
    feature_types: list[Annotated[str, StringConstraints(max_length=64)]] = Field(
        min_length=1,
        max_length=32,
        description="Feature types each picked feature may be "
        "(`datum`, `sketch`, `custom`, ...).",
    )
    plugin_ids: list[PluginId] | None = Field(
        default=None,
        max_length=8,
        description="When a picked feature is a custom feature: the plugins it "
        "may be (a roof's walls are `loft.wall`). Unset: any.",
    )
    min_items: int = Field(
        default=0,
        ge=0,
        le=MAX_FEATURE_LIST,
        description="Fewest features to pick; 0 makes the input optional.",
    )
    max_items: int = Field(
        default=MAX_FEATURE_LIST,
        ge=1,
        le=MAX_FEATURE_LIST,
        description="Most features to pick.",
    )

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if self.min_items > self.max_items:
            raise ValueError(f"input {self.name!r}: min_items is above max_items")
        if self.plugin_ids is not None and "custom" not in self.feature_types:
            raise ValueError(
                f"input {self.name!r}: plugin_ids needs feature type 'custom'"
            )
        return self


class SegmentsInput(_InputBase):
    """Lines of an OUTLINE, by their sketch ids, in pick order (BUILDING-OUTLINE):
    the wall of an outline a window sits in, the walls of an outline that
    define a roof's slope (Revit's "Defines Slope"). Stored as a list of line
    ids (``["e1", "e3"]``); an empty pick is stored as no value, allowed only
    when ``min_items`` is 0.

    The outline is the sketch that ``outline_input`` (another input of this
    manifest, a feature or feature-list pick) leads to: the picked sketch
    itself, or the ``outline`` input of the picked custom feature (a
    ``loft.wall`` in outline mode); for a feature list, its first pick. The
    form offers that sketch's non-construction lines, each named by the way
    the wall on it faces in the world, as the roof names its planes: the
    outward normal of the line (the side away from the loop's inside) is
    ``front`` when it points most nearly to -Y, ``back`` +Y, ``left`` -X and
    ``right`` +X (a tie goes to front/back); two lines facing one way are
    numbered along the loop clockwise from the sketch's first line
    (``front``, ``front 2``). The plugin checks every id against the
    outline."""

    kind: Literal["segments"]
    outline_input: InputName = Field(
        description="The input of this manifest whose pick carries the outline."
    )
    min_items: int = Field(
        default=0,
        ge=0,
        le=MAX_SEGMENTS,
        description="Fewest lines to pick; 0 makes the input optional.",
    )
    max_items: int = Field(
        default=MAX_SEGMENTS,
        ge=1,
        le=MAX_SEGMENTS,
        description="Most lines to pick.",
    )

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if self.min_items > self.max_items:
            raise ValueError(f"input {self.name!r}: min_items is above max_items")
        return self


class MaterialInput(_InputBase):
    """A library material for the generated members (their mass and cut list)."""

    kind: Literal["material"]
    default: MaterialKey | None = None


#: The kinds a list row's field may be: numbers and choices, never a pick.
ListFieldInput = Annotated[
    LengthInput | AngleInput | CountInput | ChoiceInput,
    Field(discriminator="kind"),
]


class ListInput(_InputBase):
    """An ordered list of ROWS, each the same few number and choice fields
    (``fields``): a cabinet run's boxes, as Mozaik lists a run's cabinets.
    Stored as a list of ``{field: value}`` objects in row order, a field left
    out of a row taking its default; an empty list is stored as no value,
    allowed only when ``min_items`` is 0. A formula drives one field of one
    row by pointer (``/inputs/<name>/<row>/<field>``). The form shows the
    rows as an add and remove list, a new row taking the last row's values."""

    kind: Literal["list"]
    item_label: Label = Field(description="What one row is called, e.g. 'Box'.")
    fields: list[ListFieldInput] = Field(
        min_length=1,
        max_length=MAX_LIST_FIELDS,
        description="The fields of every row, in form order.",
    )
    min_items: int = Field(
        default=0,
        ge=0,
        le=MAX_LIST_ITEMS,
        description="Fewest rows; 0 makes the input optional.",
    )
    max_items: int = Field(
        default=MAX_LIST_ITEMS, ge=1, le=MAX_LIST_ITEMS, description="Most rows."
    )
    default: list[ListRow] = Field(
        default_factory=list[ListRow],
        max_length=MAX_LIST_ITEMS,
        description="A new feature's rows (a field a row leaves out takes "
        "its default).",
    )

    @model_validator(mode="after")
    def _rows_fit_fields(self) -> Self:
        if self.min_items > self.max_items:
            raise ValueError(f"input {self.name!r}: min_items is above max_items")
        names = [item.name for item in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"list input {self.name!r} repeats a field name")
        for item in self.fields:
            if item.superseded_by is not None:
                raise ValueError(
                    f"list input {self.name!r}: a row's field is never superseded"
                )
        if not self.min_items <= len(self.default) <= self.max_items:
            raise ValueError(
                f"list input {self.name!r}: its default row count is out of bounds"
            )
        choices = {
            item.name: {o.value for o in item.options}
            for item in self.fields
            if isinstance(item, ChoiceInput)
        }
        for row in self.default:
            for key, value in row.items():
                if key not in names:
                    raise ValueError(f"list input {self.name!r}: no field {key!r}")
                if key in choices and value not in choices[key]:
                    raise ValueError(
                        f"list input {self.name!r}: {value!r} is not an "
                        f"option of {key!r}"
                    )
        return self


#: One typed input of a custom feature, discriminated on ``kind``.
PluginInput = Annotated[
    LengthInput
    | AngleInput
    | CountInput
    | ChoiceInput
    | ProfileInput
    | FeatureReferenceInput
    | FeatureListInput
    | SegmentsInput
    | MaterialInput
    | ListInput,
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
    unit: OpeningUnitPart | None = Field(
        default=None,
        exclude_if=is_none,
        description="Set on the bodies of a bought window or door unit "
        "(OPENING-UNITS): the cut list lists the unit once, Each, on its "
        "counted body. Absent on every other member.",
    )
    concrete: ConcretePour | None = Field(
        default=None,
        exclude_if=is_none,
        description="Set on a concrete body, one per pour (SLAB): the cut list "
        "lists its measured volume in cubic yards and orders it with the "
        "pour's waste allowance, rounded up to 1/4 yd³. Absent otherwise.",
    )
    rebar: list[RebarRun] | None = Field(
        default=None,
        exclude_if=is_none,
        max_length=64,
        description="The bars a pour carries, listed, not drawn (SLAB): each "
        "by its centreline length, bought in 20 ft sticks lapped 24 in. "
        "Absent on every other member.",
    )
    anchor_bolts: AnchorBolts | None = Field(
        default=None,
        exclude_if=is_none,
        description="Set on a plate that bears on concrete (SLAB): the cut "
        "list counts its anchor bolts from its measured length (IRC "
        "R403.1.6). Absent otherwise.",
    )
    grain: Annotated[list[float], Field(min_length=3, max_length=3)] | None = Field(
        default=None,
        exclude_if=is_none,
        description="A sheet-good panel with grain (CASEWORK: a plywood "
        "cabinet panel): the world direction its face grain runs, a unit "
        "vector [x, y, z]. The cut list lays the panel with that side along "
        "the sheet's length and never turns it. Absent: the panel may turn.",
    )
    banding: EdgeBanding | None = Field(
        default=None,
        exclude_if=is_none,
        description="The edge banding on this panel's exposed edges (CASEWORK), "
        "listed by the foot under Casework. Absent: none.",
    )
    hardware: list[HardwareCount] | None = Field(
        default=None,
        exclude_if=is_none,
        max_length=8,
        description="Hardware this member carries (CASEWORK: a door's hinges, "
        "a drawer box's pair of slides), listed Each under Casework. Absent: "
        "none.",
    )

    @field_validator("grain")
    @classmethod
    def _unit_grain(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not all(math.isfinite(v) for v in value):
            raise ValueError("a grain direction is finite")
        if abs(math.sqrt(sum(v * v for v in value)) - 1.0) > 1e-9:
            raise ValueError("a grain direction is a unit vector")
        return value

    @field_validator("profile", "nominal_size")
    @classmethod
    def _plain_text(cls, value: str | None) -> str | None:
        """A label, never a formula or control text: it reaches spreadsheets
        through the cut-list CSV, and a stored expansion in a shared ``.loft``
        is checked by the same model whether or not the plugin is installed."""
        if value is None:
            return value
        if value.startswith(("=", "+", "-", "@")):
            raise ValueError("a member label may not start with =, +, - or @")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("a member label may not contain control characters")
        return value


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
        hosts = [
            item
            for item in self.inputs
            if isinstance(item, FeatureReferenceInput) and item.host
        ]
        if len(hosts) > 1:
            raise ValueError(f"plugin {self.id!r} names more than one host input")
        picks = {
            item.name
            for item in self.inputs
            if isinstance(item, FeatureReferenceInput | FeatureListInput)
        }
        choices = {
            item.name: item for item in self.inputs if isinstance(item, ChoiceInput)
        }
        for item in self.inputs:
            if isinstance(item, SegmentsInput) and item.outline_input not in picks:
                raise ValueError(
                    f"segments input {item.name!r} must name a feature input as "
                    "its outline_input"
                )
            if item.superseded_by is None:
                if item.superseded_unless is not None:
                    raise ValueError(
                        f"input {item.name!r}: superseded_unless needs superseded_by"
                    )
                continue
            choice = choices.get(item.superseded_by)
            if choice is not None and item.superseded_by != item.name:
                if item.superseded_unless not in {o.value for o in choice.options}:
                    raise ValueError(
                        f"input {item.name!r}: superseded_unless must be an option "
                        f"of {item.superseded_by!r}"
                    )
            elif item.superseded_by not in picks or item.superseded_by == item.name:
                raise ValueError(
                    f"input {item.name!r} must be superseded by another feature "
                    "or choice input"
                )
            elif item.superseded_unless is not None:
                raise ValueError(
                    f"input {item.name!r}: superseded_unless is for a choice only"
                )
        return self

    def host_input(self) -> FeatureReferenceInput | None:
        """The input naming this feature's host (a window's wall), if any."""
        for item in self.inputs:
            if isinstance(item, FeatureReferenceInput) and item.host:
                return item
        return None


class PluginCatalog(BaseModel):
    """Every released version of every installed plugin (``GET /api/v1/plugins``),
    ordered by id, newest version first."""

    plugins: list[PluginManifest]
