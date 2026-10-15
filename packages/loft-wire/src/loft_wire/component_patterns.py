"""Component patterns in an assembly (ASM-A3-PATTERN).

A component pattern repeats one or more instances of an assembly, the way
Fusion 360's Pattern Components, Onshape's linear / circular pattern and
Replicate, and SolidWorks' linear, circular and pattern-driven component
patterns do:

- ``linear``: ``count`` copies (the seed included) ``spacing_mm`` apart along a
  direction picked from geometry: a straight edge, a circular edge's axis, or
  one of the assembly's origin axes;
- ``circular``: ``count`` copies about an axis picked the same way, spread over
  ``angle_deg`` (360 = a full ring, equally spaced; anything less puts the last
  copy at that angle);
- ``hole``: pattern-driven (Onshape Replicate, SolidWorks pattern driven): one
  copy at every hole of the seed hole's size on the seed hole's face of the
  driving part, and on the same holes of any further instances of that part
  named in ``also_on``. The count follows the part: add a hole to the rail and
  one more screw appears.

A pattern is ONE entry of the assembly, stored with its definition, not as
copied instances: its copies are placed by geometry after the solve, each one
fixed relative to its seed (a copy is the seed's solved pose moved by the
pattern), so editing or re-jointing the seed moves every copy, as in Fusion.
Copies are not solver bodies, cannot carry joints, and are named by a
deterministic id (:func:`pattern_copy_id`).

Numbers may be written as expressions in the one expression language
(:mod:`loft_wire.expr`): ``count_expr`` / ``spacing_expr`` / ``angle_expr``
hold the text as typed, and documents evaluates each on write and stores the
number it gets in the numeric field, which is what geometry reads. Assemblies
have no parameter table of their own yet, so an expression is arithmetic with
units (``360 deg / 32``, ``2 * 12.5 mm``).

Pure pydantic: no kernel type crosses the boundary (CLAUDE.md).
"""

import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from loft_wire.expr import MAX_EXPRESSION_LENGTH
from loft_wire.signatures import EdgeSignature

#: Most copies one pattern may place, the seed included. The same number as the
#: per-request instance bound: a pattern can never on its own place more parts
#: than one evaluation may hold.
MAX_PATTERN_COUNT = 500

#: Most seed instances one pattern repeats.
MAX_PATTERN_SEEDS = 50

#: Most further driving instances a hole-driven pattern may name.
MAX_PATTERN_DRIVERS = 50

#: Most patterns one assembly may hold.
MAX_ASSEMBLY_PATTERNS = 200

#: Bound on a linear pattern's spacing (100 m), the joint length bound.
MAX_PATTERN_SPACING_MM = 100_000.0

#: The assembly origin axes a pattern may use as its direction or axis.
OriginAxis = Literal["x", "y", "z"]

#: An expression as typed into a pattern field.
PatternExpression = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_EXPRESSION_LENGTH
    ),
]


class OriginAxisRef(BaseModel):
    """One of the assembly's origin axes (X, Y or Z through the origin)."""

    kind: Literal["origin_axis"] = "origin_axis"
    axis: OriginAxis = Field(description="'x', 'y' or 'z'")


class EdgeAxisRef(BaseModel):
    """An axis picked on an instance's part: a straight edge (its line, pointing
    from its canonical start toward its end) or a circular edge (the axis
    through its centre, pointing out of the face it bounds).

    ``instance_id`` may be an instance of this assembly or a part inside one of
    its sub-assemblies (an occurrence id, as joints use). It may not be a copy
    placed by another pattern.
    """

    kind: Literal["edge"] = "edge"
    instance_id: uuid.UUID = Field(
        description="The instance (or nested occurrence) whose part carries the edge"
    )
    signature: EdgeSignature = Field(
        description="Stage-1 signature of the picked edge (curve 'line' or 'circle')"
    )

    @model_validator(mode="after")
    def _line_or_circle(self) -> Self:
        if self.signature.curve not in ("line", "circle"):
            raise ValueError("a pattern axis needs a straight or a circular edge")
        return self


#: A pattern direction or axis: an origin axis or a picked edge.
PatternAxisRef = Annotated[OriginAxisRef | EdgeAxisRef, Field(discriminator="kind")]


class HoleRef(BaseModel):
    """The hole a hole-driven pattern's seed sits at: a circular edge (a hole
    rim) of a part instance in this assembly, or of a part inside one of its
    sub-assemblies."""

    instance_id: uuid.UUID = Field(
        description="The driving part's instance (or nested occurrence)"
    )
    signature: EdgeSignature = Field(
        description="Stage-1 signature of the seed hole's rim (curve 'circle')"
    )

    @model_validator(mode="after")
    def _circle(self) -> Self:
        if self.signature.curve != "circle":
            raise ValueError("a hole-driven pattern needs a circular edge (a hole rim)")
        return self


_Seeds = Annotated[
    list[uuid.UUID],
    Field(
        min_length=1,
        max_length=MAX_PATTERN_SEEDS,
        description="The instances to repeat (instances of this assembly: parts "
        "or rigid sub-assemblies), in order",
    ),
]

_Count = Annotated[
    int,
    Field(
        ge=2,
        le=MAX_PATTERN_COUNT,
        description="How many in the pattern, the seed included",
    ),
]


def _unique_seeds(seeds: list[uuid.UUID]) -> None:
    if len(set(seeds)) != len(seeds):
        raise ValueError("a seed instance is named twice")


class LinearComponentPattern(BaseModel):
    """``count`` copies, ``spacing_mm`` apart along ``direction``."""

    type: Literal["linear"] = "linear"
    seed_instance_ids: _Seeds
    direction: PatternAxisRef = Field(description="The direction the copies run in")
    flip: bool = Field(default=False, description="Run the other way")
    count: _Count
    spacing_mm: float = Field(
        gt=0.0,
        le=MAX_PATTERN_SPACING_MM,
        allow_inf_nan=False,
        description="Distance between neighbouring copies (mm)",
    )
    count_expr: PatternExpression | None = Field(
        default=None, description="`count` as typed (an expression), if typed"
    )
    spacing_expr: PatternExpression | None = Field(
        default=None, description="`spacing_mm` as typed (an expression), if typed"
    )

    @model_validator(mode="after")
    def _seeds(self) -> Self:
        _unique_seeds(self.seed_instance_ids)
        return self


class CircularComponentPattern(BaseModel):
    """``count`` copies about ``axis``, over ``angle_deg``.

    360 degrees is a full ring: the copies are 360/count apart. A smaller
    angle is the angle from the seed to the last copy: they are
    angle/(count - 1) apart (Fusion's Full / Angle, SolidWorks' equal spacing).
    """

    type: Literal["circular"] = "circular"
    seed_instance_ids: _Seeds
    axis: PatternAxisRef = Field(description="The axis the copies turn about")
    flip: bool = Field(default=False, description="Turn the other way")
    count: _Count
    angle_deg: float = Field(
        default=360.0,
        gt=0.0,
        le=360.0,
        allow_inf_nan=False,
        description="Total angle (degrees); 360 = a full, equally spaced ring",
    )
    count_expr: PatternExpression | None = Field(
        default=None, description="`count` as typed (an expression), if typed"
    )
    angle_expr: PatternExpression | None = Field(
        default=None, description="`angle_deg` as typed (an expression), if typed"
    )

    @model_validator(mode="after")
    def _seeds(self) -> Self:
        _unique_seeds(self.seed_instance_ids)
        return self


class HoleComponentPattern(BaseModel):
    """Pattern-driven: one copy at every hole like ``seed_hole`` (Replicate).

    The holes are every circular edge of the driving part with the seed hole's
    radius whose centre lies on the seed hole's plane, with a parallel axis:
    the rims of one hole feature on one face. The seed sits at ``seed_hole``;
    a copy goes to each of the other holes, and to every such hole on each
    instance in ``also_on`` (further instances of the SAME part, such as the
    second rail). The count is whatever the part has when it is evaluated.
    """

    type: Literal["hole"] = "hole"
    seed_instance_ids: _Seeds
    seed_hole: HoleRef = Field(description="The hole the seed sits at")
    also_on: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        max_length=MAX_PATTERN_DRIVERS,
        description="Further instances (or nested occurrences) of the driving "
        "part whose matching holes also get a copy",
    )

    @model_validator(mode="after")
    def _seeds(self) -> Self:
        _unique_seeds(self.seed_instance_ids)
        drivers = [self.seed_hole.instance_id, *self.also_on]
        if len(set(drivers)) != len(drivers):
            raise ValueError("a driving instance is named twice")
        if set(drivers) & set(self.seed_instance_ids):
            raise ValueError("a seed cannot also drive its own pattern")
        return self


#: A component pattern, discriminated on ``type``.
ComponentPattern = Annotated[
    LinearComponentPattern | CircularComponentPattern | HoleComponentPattern,
    Field(discriminator="type"),
]

#: Plain union alias for annotations of validated values.
ComponentPatternParams = (
    LinearComponentPattern | CircularComponentPattern | HoleComponentPattern
)


def pattern_reference_ids(pattern: ComponentPatternParams) -> tuple[uuid.UUID, ...]:
    """The instance (or occurrence) ids a pattern READS geometry from: its
    direction or axis edge, or its driving holes. Seeds are not included."""
    if isinstance(pattern, HoleComponentPattern):
        return (pattern.seed_hole.instance_id, *pattern.also_on)
    axis = (
        pattern.direction
        if isinstance(pattern, LinearComponentPattern)
        else pattern.axis
    )
    if isinstance(axis, EdgeAxisRef):
        return (axis.instance_id,)
    return ()


def explicit_copies(pattern: ComponentPatternParams) -> int | None:
    """Copies per seed a linear or circular pattern adds (``count - 1``), or
    None for a hole-driven pattern, whose count only geometry knows."""
    if isinstance(pattern, HoleComponentPattern):
        return None
    return pattern.count - 1


def pattern_copy_id(
    pattern_id: uuid.UUID, seed_instance_id: uuid.UUID, index: int
) -> uuid.UUID:
    """The id of copy *index* (1 = the first copy after the seed) of
    *seed_instance_id* in pattern *pattern_id*.

    ``uuid5`` keyed on the pattern, so documents, geometry and the web derive
    the same id. A copy of a sub-assembly seed stands in for that instance:
    its parts are :func:`~loft_wire.assemblies.nested_occurrence_id` of it.
    """
    return uuid.uuid5(pattern_id, f"{seed_instance_id}/{index}")


# --- CRUD DTOs ---------------------------------------------------------------------


class PatternCreate(BaseModel):
    """Add a component pattern to an assembly."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    pattern: ComponentPattern = Field(description="The pattern (on `type`)")


class PatternUpdate(BaseModel):
    """Replace a pattern's definition (its id and position stay)."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    pattern: ComponentPattern = Field(description="The new definition")


class PatternResponse(BaseModel):
    """A pattern as stored."""

    id: uuid.UUID
    assembly_id: uuid.UUID
    order_index: int = Field(description="Stable order in the assembly's tree")
    pattern: ComponentPattern


class PatternMutationResponse(BaseModel):
    """Result of a pattern write: the pattern + the new version."""

    pattern: PatternResponse
    doc_version: int


class EvaluatedPattern(BaseModel):
    """One pattern as the evaluator sees it: its stored id names its copies."""

    pattern_id: uuid.UUID
    order_index: int = Field(ge=0, description="Expansion order (determinism)")
    pattern: ComponentPattern


class PatternCopyRef(BaseModel):
    """Marks a result row as a pattern copy: which pattern, which seed."""

    pattern_id: uuid.UUID
    seed_instance_id: uuid.UUID
    index: int = Field(ge=1, description="1 = the first copy after the seed")


class PatternCount(BaseModel):
    """How many a pattern places when evaluated, the seed included, or why it
    places none. ``count`` is per seed."""

    pattern_id: uuid.UUID
    count: int | None = Field(
        description="Copies per seed, the seed included; null when the pattern "
        "could not be resolved (see `error`)"
    )
    error_code: str | None = Field(
        default=None, description="Why the pattern did not resolve, if it did not"
    )
    error_message: str | None = Field(default=None, description="The same, in words")


class PatternCountsResult(BaseModel):
    """Every pattern of an evaluation request, at every level, with its count."""

    counts: list[PatternCount]
