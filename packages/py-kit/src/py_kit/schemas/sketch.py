"""Sketch DTOs — 2D entities, constraints, and the solved-sketch result.

Single source of truth (CLAUDE.md DRY rule) for the sketch shapes that cross
service boundaries, moved here from ``geometry.sketch.schemas`` by the
"Sketch model + solver API" item exactly as that module's docstring promised:
the documents service persists these shapes inside sketch feature params
(:mod:`py_kit.schemas.features`), the geometry service solves them, and
``just gen`` exports them to ``packages/contracts`` / ``packages/ts-client``.
Pure pydantic models: no kernel (OCP/build123d) and no solver (planegcs)
types appear here.

Shapes follow the feature-tree design (docs/design/feature-tree.md §2.4/§6):
entities carry **sketch-local string ids** (``"e1"``, ``"e2"``, …) that
topological-naming selectors will address later, and the solved result is
the payload the ``FeatureResult.data`` extension (feature-tree §7.10)
returns per sketch feature.

Units: millimetres, matching the persisted feature params
(``py_kit.schemas.geometry`` convention — units are fixed per field, never
tagged per value). Coordinates are 2D in the sketch plane; mapping the plane
into 3D is the sketch *feature's* job, not the solver's.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

#: Sketch-local entity id — unique within one sketch, stable across edits.
EntityId = Annotated[
    str, Field(min_length=1, description="Sketch-local entity id, e.g. 'e1'")
]


class Point2D(BaseModel):
    """A point in sketch-plane coordinates (mm)."""

    x: float
    y: float


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class SketchEntityBase(BaseModel):
    """Fields shared by every sketch entity: identity and the construction flag.

    ``construction`` marks **reference-only** geometry — centerlines, symmetry
    axes, diagonals. A construction entity participates fully in the constraint
    solve (it can be constrained to/from, and other geometry can reference it),
    but it is **excluded** from the closed-wire profile that body-affecting
    features (extrude, revolve, …) consume to build a solid. Marking a *real*
    profile edge construction therefore opens the loop — the profile check
    fails ``profile_not_closed``, which is the correct CAD semantics.

    Additive optional field (docs/design/feature-tree.md §1.3 — additive
    optional fields do **not** bump ``param_version``): sketches persisted
    before this field lack the key and read as ``construction=False`` via the
    pydantic default, so the upcast is the identity and totality holds (no
    stored sketch becomes unreadable).
    """

    id: EntityId
    construction: bool = Field(
        default=False,
        description=(
            "Reference-only geometry (centerlines, symmetry/mirror axes, "
            "diagonals): solves and can be constrained/referenced, but is "
            "excluded from the profile that gates extrude/revolve. Absent in "
            "pre-construction-field sketches, which read as False."
        ),
    )


class SketchPoint(SketchEntityBase):
    """A free point (construction geometry, arc centers to snap to, …)."""

    kind: Literal["point"]
    position: Point2D


class SketchLine(SketchEntityBase):
    """A line segment between two endpoints."""

    kind: Literal["line"]
    start: Point2D
    end: Point2D


class SketchCircle(SketchEntityBase):
    """A full circle."""

    kind: Literal["circle"]
    center: Point2D
    radius: float = Field(gt=0, description="Radius (mm)")


class SketchArc(SketchEntityBase):
    """A circular arc traversed **counterclockwise** from start to end.

    The radius is implied by ``|start - center|``; the solver keeps start and
    end on the circle (they may move to satisfy constraints).
    """

    kind: Literal["arc"]
    center: Point2D
    start: Point2D
    end: Point2D


class SketchSpline(SketchEntityBase):
    """A smooth **fit-point** curve — a C2 B-spline interpolating ``points``.

    The free-form/organic profile entity (the last hard Sketching capability
    gap): the curve passes **through** every fit point in order (an *interpolating*
    B-spline, OCCT ``GeomAPI_Interpolate`` via ``Edge.make_spline``), so a closed
    profile wire containing a spline edge can extrude/revolve. ``points`` are the
    ordered fit points (mm, sketch-plane); **at least two** are required (two fit
    points degenerate to a straight interpolant — still valid). Consecutive fit
    points must be distinct; a coincident pair is a degenerate spline the profile
    builder rejects (``profile_not_closed``, like the degenerate-arc precedent).

    Additive optional-free field-set (docs/design/feature-tree.md §1.3): this is
    a NEW entity **kind**, not a changed field. Persisted sketches are unaffected
    — the discriminated ``SketchEntity`` union keys on ``kind``, and no existing
    sketch carries ``kind: "spline"``, so every stored sketch still parses to the
    exact same entity it did before (totality holds; ``param_version`` unchanged).

    **Solver interaction — constrainable FIT POINTS (v1.1).** planegcs still has
    no spline *primitive*, so the CURVE itself carries no tangent/curvature
    constraints. What v1.1 adds is that each fit point is addressable as a solver
    point: a constraint may name it ``{"entity": <spline id>, "point": "fitN"}``
    (:data:`SplineFitPointName`), and the solver adds THAT fit point to the
    constraint system so it takes the point-level constraints any other point can
    (coincident, fixed, symmetric — and, via a coincident-linked line, distance /
    horizontal / vertical). After the solve the spline is rebuilt through the
    solved fit-point positions, so it reshapes to satisfy its constraints.

    A fit point contributes DOF **only when constrained**: a fit point no
    constraint references is left out of the constraint system entirely, so an
    UNCONSTRAINED spline still solves as fixed geometry (zero added DOF, fit
    points preserved bitwise) exactly as before. A reference to an out-of-range
    fit index (``"fit9"`` on a 3-point spline) is a malformed definition
    (``SketchDefinitionError``), like any unknown-point reference.

    **Spline tangency stays DEFERRED (honest limit):** a common tangent between a
    spline and its neighbouring edge (curvature-continuity at a fit point) needs a
    native spline primitive in the solver and is not offered here — only fit-point
    *position* constraints are. It remains behind the ``SketchSolver`` protocol
    for a future solver (or a planegcs spline extension).
    """

    kind: Literal["spline"]
    points: list[Point2D] = Field(
        min_length=2,
        description=(
            "Ordered fit points (mm) the curve interpolates through; at least "
            "two. Consecutive points must be distinct (a coincident pair is a "
            "degenerate spline, rejected at profile build)."
        ),
    )


SketchEntity = Annotated[
    SketchPoint | SketchLine | SketchCircle | SketchArc | SketchSpline,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

#: Named point of an entity. ``position`` addresses a point entity; ``start``/
#: ``end`` address line and arc endpoints; ``center`` addresses circle and arc
#: centers. These are the FIXED, named points every non-spline entity kind owns.
NamedPointName = Literal["start", "end", "center", "position"]

#: A spline's Nth **fit point**, addressed positionally: ``"fit0"`` is the first
#: fit point, ``"fit1"`` the second, … Zero-based, no leading zeros (``"fit00"``
#: / ``"fit01"`` are rejected). A spline has as many fit points as it has
#: ``points`` (:class:`SketchSpline`), so — unlike the fixed named points above —
#: the valid set is data-dependent and cannot be a closed ``Literal``. The index
#: is therefore bounds-checked against the target spline's fit-point count at
#: SOLVE time (an out-of-range ``"fit9"`` on a 3-point spline resolves to no
#: solver point → ``SketchDefinitionError``, the same clean malformed-reference
#: path as an unknown entity id), not by this per-field pattern, which cannot see
#: the referenced entity.
SplineFitPointName = Annotated[
    str,
    Field(
        pattern=r"^fit(?:0|[1-9][0-9]*)$",
        description="A spline fit point by zero-based index, e.g. 'fit0'.",
    ),
]

#: One point of one entity: either a fixed named point (:data:`NamedPointName`)
#: or a spline fit point (:data:`SplineFitPointName`). The fit-point form is
#: ADDITIVE (docs/design/feature-tree.md §1.3 — NO ``param_version`` bump): no
#: constraint persisted before splines became constrainable carries a ``"fit*"``
#: reference, so every existing line/circle/arc/point ref parses to the exact
#: same shape it did before (totality holds).
PointName = NamedPointName | SplineFitPointName

_FIT_POINT_RE = re.compile(r"^fit(0|[1-9][0-9]*)$")


def spline_fit_index(point: str) -> int | None:
    """Zero-based fit-point index a :data:`PointName` addresses, or ``None``.

    ``None`` for a fixed named point (``"start"``/``"end"``/``"center"``/
    ``"position"``); an ``int`` for a spline fit reference (``"fit0"`` → ``0``).
    The bounds check against a spline's actual fit-point count is the solver's
    job (this only decodes the index from the name).
    """
    match = _FIT_POINT_RE.match(point)
    return int(match.group(1)) if match else None


class EntityPointRef(BaseModel):
    """Names one point of one entity, e.g. ``{"entity": "e1", "point": "end"}``.

    ``point`` is a fixed named point (``start``/``end``/``center``/``position``)
    for a line/arc/circle/point entity, or a spline fit point (``"fit0"``,
    ``"fit1"``, …) for a :class:`SketchSpline` — a constraint addresses a
    spline's Nth fit point exactly as it addresses a line's endpoint.
    """

    entity: EntityId
    point: PointName


class CoincidentConstraint(BaseModel):
    """Two named points share a location."""

    kind: Literal["coincident"]
    a: EntityPointRef
    b: EntityPointRef


class HorizontalConstraint(BaseModel):
    """A line is parallel to the sketch X axis."""

    kind: Literal["horizontal"]
    entity: EntityId


class VerticalConstraint(BaseModel):
    """A line is parallel to the sketch Y axis."""

    kind: Literal["vertical"]
    entity: EntityId


#: A dimension's optional reference NAME — a stable handle another dimension's
#: expression can reference (name ``"width"`` → ``height`` carries
#: ``expression="width/2"``). Identifier-like (a letter or underscore, then
#: letters/digits/underscores); uniqueness within a sketch is enforced on
#: :class:`SketchDefinition` (a per-field pattern cannot see its siblings).
DimensionName = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Dimension reference name: identifier-like, unique per sketch.",
    ),
]


class DimensionConstraint(BaseModel):
    """Shared fields of a **dimension** (distance, radius, …): value, optional
    expression, optional reference name, and the driving/driven flag.

    A dimension's value is EITHER a literal ``value_mm`` OR a math
    ``expression`` over other dimensions' names; when ``expression`` is present
    it SUPERSEDES ``value_mm`` (which then holds the last resolved value, kept
    for display before the next solve). ``name`` gives the dimension a stable
    handle other expressions can reference. ``driving`` distinguishes a DRIVING
    dimension (its value is fed to the solver) from a DRIVEN one (excluded from
    the constraint system; its value is measured back from the solved geometry
    for read-only display — the solver never sees it, so it cannot
    over-constrain).

    Additive optional fields (docs/design/feature-tree.md §1.3 — NO
    ``param_version`` bump): a dimension persisted before these fields lacks the
    keys and reads as ``expression=None``, ``name=None``, ``driving=True`` — a
    plain literal driving dimension, exactly its former meaning. Totality holds:
    every stored sketch still parses and, since a literal driving dimension
    feeds the solver its ``value_mm`` unchanged, solves byte-identically.
    """

    value_mm: float = Field(
        gt=0,
        description="Resolved dimension value (mm). The literal value when "
        "`expression` is None; otherwise the last solved/resolved value (the "
        "expression supersedes it on the next solve, but a positive placeholder "
        "is still required so a pre-solve read has a value).",
    )
    expression: str | None = Field(
        default=None,
        max_length=256,
        description="Optional math expression over other dimension NAMES "
        '(`+ - * / ( )`, unary minus, decimals), e.g. `"width/2"`. When '
        "present it SUPERSEDES `value_mm` and the geometry service re-evaluates "
        "it each solve. A bare literal dimension leaves this None. Only "
        "*driving* dimensions may be referenced; a bad expression / unknown or "
        "driven reference / cycle / division-by-zero is a clean `sketch_invalid` "
        "error, never a crash. Capped at 256 chars: an expression is a short "
        "formula over dimension names (`(width+gap)/2`), never prose, and the "
        "cap bounds parser paren-depth (<=128) and evaluator AST-depth (<=128) "
        "well under Python's recursion limit, so a hostile deeply-nested / "
        "very-long string 422s at request validation BEFORE the recursive-"
        "descent parser runs — it can never reach the kernel as an uncaught "
        "RecursionError. The parser also carries its own depth guard (defense "
        "in depth) should this cap ever be raised.",
    )
    name: DimensionName | None = Field(
        default=None,
        description="Optional stable name so another dimension's `expression` "
        "can reference this one. Unique within a sketch (enforced on "
        "SketchDefinition). None = unnamed: still solves, just not referenceable.",
    )
    driving: bool | None = Field(
        default=None,
        description="Driving/driven flag. None (absent, the default) or True = "
        "DRIVING: the value is fed to the solver. False = DRIVEN: excluded from "
        "the constraint system; the value is measured back from the solved "
        "geometry for display (read-only, never fed as a constraint, so a driven "
        "dimension cannot over-constrain). Nullable+None-default (rather than a "
        "bare `bool`) keeps it an ADDITIVE optional field: a sketch persisted "
        "before it reads as None = driving, and the generated TS client leaves "
        "it optional. Read it through `is_driving`, never the raw tri-state.",
    )

    @property
    def is_driving(self) -> bool:
        """True unless the dimension is explicitly marked driven.

        Collapses the additive tri-state (`None`/`True`/`False`) to the boolean
        the solver wiring wants: absent/None (backward-compat default) and True
        both mean DRIVING; only an explicit `False` means DRIVEN.
        """
        return self.driving is not False


class DistanceConstraint(DimensionConstraint):
    """Dimension: the length of a line (mm). Driving by default; see
    :class:`DimensionConstraint` for the expression/name/driving fields."""

    kind: Literal["distance"]
    entity: EntityId


class RadiusConstraint(DimensionConstraint):
    """Dimension: the radius of a circle or arc (mm). Driving by default; see
    :class:`DimensionConstraint` for the expression/name/driving fields."""

    kind: Literal["radius"]
    entity: EntityId


class FixedConstraint(BaseModel):
    """Anchor a named point at its current (input) coordinates.

    Every fully-constrained sketch needs an anchor — without one, a rigid
    solution still floats with two translational degrees of freedom.
    """

    kind: Literal["fixed"]
    point: EntityPointRef


class ParallelConstraint(BaseModel):
    """Two lines have equal direction.

    Relates two **whole** line entities (by id, not by endpoint) — contrast
    with :class:`CoincidentConstraint`, whose ``a``/``b`` name single points.
    Removes one rotational degree of freedom. Both entities must be lines.
    """

    kind: Literal["parallel"]
    a: EntityId
    b: EntityId


class PerpendicularConstraint(BaseModel):
    """Two lines are orthogonal (their directions differ by 90°).

    Relates two whole line entities by id; removes one rotational degree of
    freedom. Both entities must be lines.
    """

    kind: Literal["perpendicular"]
    a: EntityId
    b: EntityId


class TangentConstraint(BaseModel):
    """Two curves touch with a common tangent at the contact point.

    Relates a line and an arc/circle, or two arcs/circles, by whole-entity id.
    A line-and-line pair is not tangency-capable and is rejected at solve time.
    Order is immaterial (tangency is symmetric); the solver dispatches to the
    matching planegcs variant from the resolved entity kinds.
    """

    kind: Literal["tangent"]
    a: EntityId
    b: EntityId


class EqualConstraint(BaseModel):
    """Two entities of the same class have equal size.

    Two lines get equal length; two circles, two arcs, or a circle-and-arc
    pair get equal radius. Relates two **whole** entities by id (order is
    immaterial — equality is symmetric); the solver dispatches to the matching
    planegcs variant from the resolved entity kinds. A mismatched pair
    (e.g. a line and a circle) has no equal-size relation and is rejected at
    solve time. Removes one degree of freedom.
    """

    kind: Literal["equal"]
    a: EntityId
    b: EntityId


class SymmetricConstraint(BaseModel):
    """Two points are mirror images about a line.

    ``a`` and ``b`` name single points (like :class:`CoincidentConstraint`);
    ``line`` is the whole line entity they are symmetric about — cleanest with
    a construction centerline, but any line works. Removes two degrees of
    freedom (the pair collapses to one point's worth of freedom plus a
    reflection). ``line`` must be a line entity.
    """

    kind: Literal["symmetric"]
    a: EntityPointRef
    b: EntityPointRef
    line: EntityId


class ConcentricConstraint(BaseModel):
    """Two circles/arcs share a center point.

    Relates two whole circle/arc entities by id (order immaterial); the solver
    ties their centers together (there is no separate radius relation — use
    :class:`EqualConstraint` for that). Removes two degrees of freedom. Both
    entities must be a circle or an arc; a line has no center and is rejected.
    """

    kind: Literal["concentric"]
    a: EntityId
    b: EntityId


SketchConstraint = Annotated[
    CoincidentConstraint
    | HorizontalConstraint
    | VerticalConstraint
    | DistanceConstraint
    | RadiusConstraint
    | FixedConstraint
    | ParallelConstraint
    | PerpendicularConstraint
    | TangentConstraint
    | EqualConstraint
    | SymmetricConstraint
    | ConcentricConstraint,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Solver input / output
# ---------------------------------------------------------------------------


class SketchDefinition(BaseModel):
    """Solver input: entities (with starting positions) plus constraints.

    Entity positions double as the solver's starting guess — the solved
    result stays near where the user drew. Both lists are **ordered**;
    solvers must process them in list order (determinism, RESEARCH §9).
    ``SketchParamsV1`` (:mod:`py_kit.schemas.features`) extends this model
    with the sketch plane, so persisted sketch params ARE valid solver input.
    """

    entities: list[SketchEntity]
    constraints: list[SketchConstraint]

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchDefinition":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self

    @model_validator(mode="after")
    def _unique_dimension_names(self) -> "SketchDefinition":
        # A dimension NAME must be unique within a sketch so an expression's
        # reference resolves unambiguously (``height="width/2"``). Enforced here
        # rather than per-field because a field validator cannot see sibling
        # constraints. Unnamed dimensions (name=None) are unconstrained.
        seen: set[str] = set()
        for constraint in self.constraints:
            name = getattr(constraint, "name", None)
            if name is None:
                continue
            if name in seen:
                raise ValueError(f"Duplicate sketch dimension name: {name!r}")
            seen.add(name)
        return self


#: Outcome of a solve, in precedence order (a conflicting sketch is reported
#: ``conflicting`` even if it is also over- or underconstrained):
#:
#: - ``conflicting``      — constraints are mutually unsatisfiable.
#: - ``overconstrained``  — a constraint is redundant (consistent but
#:                          superfluous); a solution may still be returned.
#: - ``diverged``         — the numeric solve failed with no diagnosed
#:                          conflict (bad starting guess, degenerate input).
#: - ``underconstrained`` — solved, but degrees of freedom remain.
#: - ``converged``        — solved and fully constrained.
SketchSolveStatus = Literal[
    "converged",
    "underconstrained",
    "overconstrained",
    "conflicting",
    "diverged",
]


class SolvedDimension(BaseModel):
    """The computed value of one dimension constraint in a solved sketch.

    Reported per dimension so the sketcher can show the number next to each
    dimension WITHOUT re-parsing expressions itself:

    * **driving** — ``value_mm`` is the evaluated literal/expression value that
      was fed to the solver (e.g. ``height="width/2"`` with ``width=20`` reports
      ``value_mm=10``).
    * **driven** — ``value_mm`` is the value MEASURED back from the solved
      geometry (a line's length / a circle-or-arc's radius): the read-only
      readout that updates as the geometry it dimensions moves.

    ``constraint_index`` points into the sketch's input constraint list, so the
    UI can line each readout up with the constraint the user authored.
    """

    constraint_index: int = Field(
        ge=0, description="Index into the sketch's input constraint list."
    )
    name: str | None = Field(
        default=None, description="The dimension's reference name, if it has one."
    )
    driving: bool = Field(
        description="True = driving (value fed to the solver); False = driven "
        "(value measured back from the solved geometry)."
    )
    value_mm: float = Field(
        description="Computed value (mm): the evaluated expression/literal for a "
        "driving dimension, or the measured geometry value for a driven one."
    )
    expression: str | None = Field(
        default=None,
        description="The dimension's source expression, echoed for the UI "
        "(None for a bare literal dimension).",
    )


class SolvedSketch(BaseModel):
    """Solver output: solved geometry plus diagnosis.

    This is the payload the per-feature solved-sketch ``FeatureResult.data``
    extension (feature-tree §7.10) carries for sketch features, via
    :class:`py_kit.schemas.features.SolvedSketchData`.
    """

    status: SketchSolveStatus
    entities: list[SketchEntity] = Field(
        description=(
            "Same entities (ids, kinds, order) as the input. Positions are "
            "solved when the numeric solve succeeded (converged, "
            "underconstrained, and consistent overconstrained cases); for "
            "conflicting/diverged sketches the input positions are returned "
            "unchanged."
        )
    )
    dof: int | None = Field(
        default=None,
        description=(
            "Remaining degrees of freedom (0 = fully constrained); None when "
            "the diagnosis cannot determine it (e.g. conflicting systems)."
        ),
    )
    conflicting_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices into the input constraint list that conflict.",
    )
    redundant_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices into the input constraint list that are redundant.",
    )
    dimensions: list[SolvedDimension] = Field(
        default_factory=list["SolvedDimension"],
        description="Per-dimension computed values (driving = evaluated "
        "expression/literal; driven = measured from the solved geometry). One "
        "entry per dimension constraint, in input order. Empty for a sketch with "
        "no dimensions; additive (pre-expression callers ignore it).",
    )


#: Over-constraint severity (BACKLOG #6). The solver already computes both the
#: conflicting and redundant constraint sets (:class:`SolvedSketch`); this names
#: which KIND of over-constraint a sketch has:
#:
#: - ``redundant``   — the named constraints are superfluous but CONSISTENT: the
#:                     sketch still solves once they are removed (removable).
#: - ``conflicting`` — the named constraints are mutually CONTRADICTORY: no
#:                     solution exists until one is removed or relaxed.
SketchOverconstraintClass = Literal["redundant", "conflicting"]


class SketchConstraintDiagnosis(BaseModel):
    """Typed classification of an over-constrained sketch (BACKLOG #6).

    Exposes the solver's already-computed redundant/conflicting constraint sets
    (:class:`SolvedSketch`) as a STRUCTURED diagnosis a caller reads by field —
    never a message string the frontend has to parse. It distinguishes the two
    over-constraint kinds a working engineer must tell apart (VISION.md
    Sketching row): a REDUNDANT constraint is removable and the sketch still
    solves, whereas a CONFLICTING constraint makes the sketch unsolvable until
    one is relaxed. Built by :func:`classify_overconstraint`; carried on the
    :class:`py_kit.schemas.features.FeatureError` (the ``sketch_conflicting``
    error path) and on the solved-sketch feature payload (the redundant-but-
    solvable path), so BOTH cases surface the same typed shape.
    """

    classification: SketchOverconstraintClass = Field(
        description="Over-constraint kind: 'redundant' (removable, still solves) "
        "or 'conflicting' (contradictory, unsolvable until relaxed)."
    )
    removable: bool = Field(
        description="True when the sketch still solves after removing the named "
        "constraints (the redundant case); False when a genuine conflict remains "
        "(the sketch is unsolvable). Mirrors `classification` for callers that "
        "prefer a boolean over the enum."
    )
    conflicting_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices (into the sketch's input constraint list) of the "
        "CONTRADICTORY constraints — empty for a purely redundant over-constraint.",
    )
    redundant_constraints: list[int] = Field(
        default_factory=list[int],
        description="Indices (into the sketch's input constraint list) of the "
        "REDUNDANT (consistent-but-superfluous, removable) constraints.",
    )
    message: str = Field(
        description="Human-readable diagnosis (kernel/solver detail sanitized)."
    )
    suggested_fix: str | None = Field(
        default=None,
        description="Actionable hint naming a constraint to remove/relax, e.g. "
        "'Remove constraint 3'. None when no single-constraint fix is offered.",
    )


def classify_overconstraint(solved: SolvedSketch) -> SketchConstraintDiagnosis | None:
    """Classify an over-constrained solve into a typed diagnosis.

    Produces a :class:`SketchConstraintDiagnosis` (or ``None``).

    Pure function of the solver's already-computed output (BACKLOG #6 EXPOSES
    the existing ``conflicting``/``redundant`` sets — it derives no new math).
    Returns ``None`` for a solve with no over-constraint (converged /
    underconstrained / diverged). Otherwise the solver ``status`` decides the
    kind (its documented precedence — ``conflicting`` dominates ``redundant``):

    * ``conflicting`` — some constraints are mutually unsatisfiable, so the
      sketch is UNSOLVABLE (``removable=False``). Both the conflicting ids and
      any redundant ids planegcs also reported are named; the fix relaxes a
      conflicting one.
    * ``overconstrained`` — the extra constraints are CONSISTENT, so the sketch
      still solves after dropping them (``removable=True``); the fix removes a
      redundant one.
    """
    if solved.status == "conflicting":
        conflicting = list(solved.conflicting_constraints)
        redundant = list(solved.redundant_constraints)
        named = conflicting or redundant
        fix = f"Remove or relax constraint {named[0]}" if named else None
        detail = (
            f"constraint(s) {conflicting} conflict"
            if conflicting
            else "constraints conflict"
        )
        return SketchConstraintDiagnosis(
            classification="conflicting",
            removable=False,
            conflicting_constraints=conflicting,
            redundant_constraints=redundant,
            message=(
                f"Sketch constraints are mutually unsatisfiable: {detail}. No "
                "solution exists until one is removed or relaxed."
            ),
            suggested_fix=fix,
        )
    if solved.status == "overconstrained":
        redundant = list(solved.redundant_constraints)
        fix = f"Remove constraint {redundant[0]}" if redundant else None
        return SketchConstraintDiagnosis(
            classification="redundant",
            removable=True,
            conflicting_constraints=[],
            redundant_constraints=redundant,
            message=(
                f"Sketch is over-constrained but consistent: constraint(s) "
                f"{redundant} are redundant and can be removed; the sketch still "
                "solves."
            ),
            suggested_fix=fix,
        )
    return None


# ---------------------------------------------------------------------------
# Sketch editing — trim / extend (BACKLOG #2, backend)
# ---------------------------------------------------------------------------
#
# Trim and extend are **server-side geometry operations** (RESEARCH §3 +
# CLAUDE.md service boundaries): 2D curve intersection/trimming is kernel-owned
# geometry logic and must NOT be reimplemented in the frontend (that would be
# WET and a boundary breach). The geometry service serves them at
# ``POST /api/v1/sketch/trim`` and ``POST /api/v1/sketch/extend``; the gateway
# proxies them auth-gated at ``/api/v1/geometry/sketch/{trim,extend}``. Both
# share one request/response pair — DRY (CLAUDE.md): the contract is "the whole
# entity set + a target + a pick point in, the modified entity set out". The
# operations are **stateless** (nothing persisted) and **deterministic**
# (RESEARCH §9): identical input yields byte/coordinate-identical output.
#
# Constraints are deliberately NOT part of this contract. The geometry service
# is stateless and does not own the constraint graph; trim/extend operate on
# geometry alone and return the new entity list. Re-mapping any constraints
# that referenced a split/removed entity id is the caller's job (the sketch-UI
# / documents layer, item #2b). Splitting an entity keeps the target's id on
# the piece that survives from the target's start; any additional piece gets a
# fresh deterministic id ``f"{target}.{n}"`` (see :class:`SketchEditResult`).


class SketchEditRequest(BaseModel):
    """Input for a sketch trim or extend edit (stateless, one-shot).

    ``entities`` is the whole sketch's entity list (same shapes the solver
    consumes — a construction entity is trimmed/extended like any other).
    ``target`` names the entity being edited; it MUST be present in
    ``entities`` (else a 422 ``sketch_target_not_found``). ``pick`` is the
    2D sketch-plane point the user clicked:

    * **trim** — ``pick`` selects WHICH segment of ``target`` to delete: the
      target curve is cut at its nearest intersection(s) with the other
      entities on each side of the pick, and the segment containing the pick
      is removed (standard Onshape/Fusion "cut at intersection" gesture). With
      no intersection bounding a side, that side runs to the curve's end; with
      no intersection at all, the whole target is deleted. The pick must
      project onto the target's drawn extent (else 422
      ``sketch_pick_not_on_target``).
    * **extend** — ``pick`` selects WHICH END of ``target`` to lengthen (the
      nearer endpoint): the curve grows along its own supporting line/circle
      from that end to the nearest neighboring entity it meets in that
      direction (else 422 ``sketch_extend_no_target``).

    Units are millimetres (:mod:`py_kit.schemas.sketch` convention).
    """

    entities: list[SketchEntity] = Field(
        description="The whole sketch's entities (the edit rewrites this set)."
    )
    target: EntityId = Field(
        description="Id of the entity to trim/extend; must be in `entities`."
    )
    pick: Point2D = Field(
        description="Sketch-plane pick point (mm): the segment to delete (trim) "
        "or the end to lengthen (extend, nearest endpoint wins)."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchEditRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchEditResult(BaseModel):
    """Output of a trim/extend edit: the rewritten entity list.

    Order is preserved: unedited entities keep their position and id; the
    target is replaced **in place** by its resulting piece(s). Trim may leave
    the target shortened (one piece, id unchanged), split it into two (the
    piece from the target's start keeps the id; the second piece gets a fresh
    deterministic id ``f"{target}.{n}"``, the lowest ``n`` >= 2 not already in
    use), convert a trimmed circle into a single arc (id unchanged), or delete
    it entirely (target absent from the result). Extend returns the target
    lengthened (id unchanged). Deterministic: identical input yields identical
    output entities, coordinates included (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The sketch entities after the edit (see class docstring "
        "for how the target is rewritten and how split ids are assigned)."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchEditResult":
        # Defense in depth: a split-piece id must never collide with an
        # existing entity id. The edit op seeds its id generator from the whole
        # sketch to guarantee this; enforcing it on the result too means a
        # regression fails loudly at the boundary instead of silently
        # corrupting the sketch (the frontend diffs these ids to reconcile
        # constraints, so a duplicate would make that diff ambiguous).
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


# ---------------------------------------------------------------------------
# Sketch editing — offset (BACKLOG #3, backend)
# ---------------------------------------------------------------------------
#
# Offset is the standard rib/web/wall-profile tool: a **parallel copy** of a
# curve at a signed distance. Like trim/extend it is a **server-side geometry
# operation** (RESEARCH §3 + CLAUDE.md service boundaries) — the frontend must
# not reimplement offset math — served at ``POST /api/v1/sketch/offset`` and
# gateway-proxied auth-gated at ``/api/v1/geometry/sketch/offset``. It is
# stateless and deterministic (RESEARCH §9): identical input yields
# coordinate-identical output, computed by **exact closed-form analytic**
# geometry (no solver iteration), matching the trim/extend choice.
#
# Unlike trim (which *rewrites* the target), offset **ADDS** geometry: the
# source entity is returned unchanged in the caller's set and the result
# carries only the NEW offset entity, with a fresh deterministic id
# ``f"{target}.{n}"`` (lowest ``n`` >= 2 not already in use) and the source's
# construction flag inherited. Re-mapping/constraining the new entity is the
# caller's job (the geometry op is constraint-free by design, same as
# trim/extend).
#
# **Sign convention (documented, uniform across kinds).** The copy is displaced
# along the target curve's **left-hand normal** — the curve's forward direction
# rotated +90° (counter-clockwise). ``+distance`` = left of the directed curve,
# ``-distance`` = right. For a line directed start→end this is the familiar
# perpendicular offset, e.g. ``(0,0)→(10,0)`` offset ``+2`` → ``(0,2)→(10,2)``.
# Because a circle/arc is traversed **counter-clockwise**, its left-hand normal
# points **inward** (toward the center), so ``+distance`` shrinks the radius
# (``radius - distance``, same center/angular span) and ``-distance`` grows it;
# an inward offset that would drive the radius to ≤ 0 is a degenerate error.
#
# **v1 scope (honest).** Single-entity offset (line / arc / circle) is shipped.
# Chain offset — a connected run of curves offset together with miter/arc join
# handling — is DEFERRED (it is more than a clean increment: it needs join
# construction and self-intersection trimming). Callers offset one entity at a
# time in v1.


class SketchOffsetRequest(BaseModel):
    """Input for a sketch offset (stateless, one-shot).

    ``entities`` is the whole sketch's entity list — passed so the new offset
    entity gets a fresh id that cannot collide with an existing one (and to
    mirror the trim/extend contract). ``target`` names the entity to offset; it
    MUST be present in ``entities`` (else a 422 ``sketch_target_not_found``).
    ``distance`` is the **signed** offset distance in millimetres (see the
    module comment above for the left-hand-normal sign convention); it must be
    a nonzero, finite value (else 422 ``sketch_offset_zero_distance``).
    """

    entities: list[SketchEntity] = Field(
        description="The whole sketch's entities (offset ADDS to this set; the "
        "source stays unchanged)."
    )
    target: EntityId = Field(
        description="Id of the entity to offset; must be in `entities`."
    )
    distance: float = Field(
        description="Signed offset distance (mm): +distance = left of the "
        "directed curve (a CCW arc/circle's left normal points inward, so "
        "+distance shrinks its radius). Must be nonzero and finite."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchOffsetRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchOffsetResult(BaseModel):
    """Output of an offset: the NEW offset entity/entities (source unchanged).

    Offset **adds** geometry, so — unlike :class:`SketchEditResult` (which
    returns the whole rewritten set) — this carries ONLY the newly created
    offset entities. In v1 that is exactly one entity, with a fresh
    deterministic id ``f"{target}.{n}"`` and the source's construction flag
    inherited. The caller appends these to its own entity list. Deterministic:
    identical input yields identical output entities, coordinates included
    (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The newly created offset entities (source entities are "
        "unchanged and NOT echoed here). One entity in v1 (single-entity "
        'offset); fresh id `f"{target}.{n}"`, construction flag inherited.'
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchOffsetResult":
        # Internal-uniqueness guard for the returned batch (trivial at one
        # entity in v1; future-proofs chain offset, which returns several).
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


# ---------------------------------------------------------------------------
# Sketch editing — mirror (BACKLOG #4, backend)
# ---------------------------------------------------------------------------
#
# Mirror is the standard symmetric-profile tool: reflect selected entities
# about an axis line, appending the reflected COPIES. Like trim/extend/offset
# it is a **server-side geometry operation** (RESEARCH §3 + CLAUDE.md service
# boundaries) — the frontend must not reimplement reflection math — served at
# ``POST /api/v1/sketch/mirror`` and gateway-proxied auth-gated at
# ``/api/v1/geometry/sketch/mirror``. It is stateless and deterministic
# (RESEARCH §9): identical input yields coordinate-identical output, computed
# by **exact closed-form analytic** reflection (a rational foot-of-perpendicular
# — no sqrt, no trig, no solver iteration), matching the trim/extend/offset
# choice.
#
# **Mirror the OP is not the ``symmetric`` CONSTRAINT.** They are deliberately
# distinct concepts and must not be conflated:
#
# * :class:`SymmetricConstraint` is a *constraint* the solver enforces on two
#   points that ALREADY exist — it keeps them mirror images as the sketch is
#   dragged/dimensioned. It creates no geometry.
# * The mirror *operation* here CREATES new reflected copies of whole entities
#   in one shot. A named ❌ Sketching-scorecard blocker (docs/COMPETITIVE.md):
#   symmetric profiles with more than a couple of point-pairs need this op, not
#   one ``symmetric`` constraint per pair.
#
# **v1 scope (honest).** Mirror is **geometry-only**: it appends the reflected
# copies and does NOT auto-add ``symmetric`` constraints between each source and
# its copy. Pairing source↔copy with symmetric constraints (a live-linked
# mirror) is deferred; callers who want that add the constraints themselves. The
# op mints a fresh deterministic id ``f"{source}.{n}"`` per copy (seeded from the
# WHOLE sketch's id set so a copy id can never collide with an existing entity or
# another copy) and inherits each source's construction flag.
#
# **Axis representation (documented decision).** The axis is a tagged union so
# both real-world gestures are first-class and DRY (one op, one reflection):
#
# * :class:`MirrorAxisEntity` — mirror about an existing **line** entity, named
#   by id. The common "mirror about this construction centerline" case; the
#   entity must be a line (a circle/arc/point axis is ``sketch_mirror_axis_not_line``).
# * :class:`MirrorAxisPoints` — mirror about the infinite line through two given
#   points ``a``/``b``. More general (no axis entity need exist in the sketch).
#
# Either way a zero-length axis (coincident points / degenerate line) is
# ``sketch_mirror_degenerate_axis``. An entity lying ON the axis reflects to
# itself — a coincident copy with a fresh id (identity reflection is
# well-defined; we do NOT special-case or reject it, avoiding a fragile
# on-axis epsilon test).


class MirrorAxisEntity(BaseModel):
    """Mirror axis named by an existing **line** entity id.

    The cleanest "mirror about this construction centerline" case: ``entity``
    must resolve to a :class:`SketchLine` in the request's ``entities`` (else
    ``sketch_target_not_found``; a non-line axis entity is
    ``sketch_mirror_axis_not_line``). The line's start/end define the axis.
    """

    kind: Literal["entity"]
    entity: EntityId = Field(
        description="Id of the line entity to mirror about; must be in `entities`."
    )


class MirrorAxisPoints(BaseModel):
    """Mirror axis given directly as the infinite line through two points.

    More general than :class:`MirrorAxisEntity` — no axis entity need exist in
    the sketch. ``a`` and ``b`` must be distinct (a zero-length axis is
    ``sketch_mirror_degenerate_axis``).
    """

    kind: Literal["points"]
    a: Point2D = Field(description="First point on the mirror axis line (mm).")
    b: Point2D = Field(description="Second point on the mirror axis line (mm).")


#: The mirror axis: an existing line entity (by id) or two points defining the
#: infinite axis line. Discriminated on ``kind`` (``"entity"`` / ``"points"``).
MirrorAxis = Annotated[
    MirrorAxisEntity | MirrorAxisPoints,
    Field(discriminator="kind"),
]


class SketchMirrorRequest(BaseModel):
    """Input for a sketch mirror (stateless, one-shot).

    ``entities`` is the whole sketch's entity list — passed so each new copy
    gets a fresh id that cannot collide with an existing one (and to resolve a
    :class:`MirrorAxisEntity` axis). ``targets`` names the entities to reflect;
    each MUST be present in ``entities`` (else ``sketch_target_not_found``) and
    at least one is required. ``axis`` is the mirror line (see :data:`MirrorAxis`).

    Mirror **adds** geometry: the sources are untouched and the response carries
    only the NEW reflected copies (see :class:`SketchMirrorResult`). Every entity
    kind is reflectable (point, line, circle, arc). Units are millimetres
    (:mod:`py_kit.schemas.sketch` convention).
    """

    entities: list[SketchEntity] = Field(
        description="The whole sketch's entities (mirror ADDS to this set; the "
        "sources stay unchanged)."
    )
    targets: list[EntityId] = Field(
        min_length=1,
        description="Ids of the entities to reflect; each must be in `entities`.",
    )
    axis: MirrorAxis = Field(
        description="The mirror axis: a line entity id or two points (see MirrorAxis)."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchMirrorRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchMirrorResult(BaseModel):
    """Output of a mirror: the NEW reflected copies (sources unchanged).

    Like :class:`SketchOffsetResult` (and unlike :class:`SketchEditResult`),
    mirror **adds** geometry, so this carries ONLY the newly created copies —
    one per ``target``, in ``targets`` order — each with a fresh deterministic
    id ``f"{source}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded from the
    whole sketch AND the copies already minted) and the source's construction
    flag inherited. The caller appends these to its own entity list.

    Reflection reverses orientation, so a mirrored **arc** has its start/end
    **swapped** (``start`` = reflected source ``end``, ``end`` = reflected source
    ``start``) to preserve the CCW-from-start invariant :class:`SketchArc`
    documents. Deterministic: identical input yields identical output entities,
    coordinates included (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The newly created mirrored copies (sources are unchanged and "
        'NOT echoed here). One per target; fresh id `f"{source}.{n}"`, '
        "construction flag inherited, arcs start/end-swapped for CCW."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchMirrorResult":
        # Defense in depth (same posture as SketchEditResult/SketchOffsetResult):
        # a minted copy id must never collide with another copy's. The op seeds
        # its id generator from the whole sketch plus the copies already minted;
        # enforcing uniqueness here fails a regression loudly at the boundary.
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


# ---------------------------------------------------------------------------
# Sketch editing — corner fillet / chamfer (BACKLOG #5, backend)
# ---------------------------------------------------------------------------
#
# The one-click corner-round an engineer expects instead of hand-placing a
# tangent arc and constraining it twice (a named ❌ Sketching-scorecard blocker,
# docs/COMPETITIVE.md). Two entities that meet at (or extend/trim to) a shared
# corner are replaced at that corner by:
#
# * **fillet** — a tangent **arc** of radius ``radius``; both curves are trimmed
#   back to their tangent points and the arc bridges them.
# * **chamfer** — a straight **line** across the corner between two equal-setback
#   points at distance ``distance`` along each curve; both curves are trimmed
#   back to those points and the line bridges them.
#
# Like trim/extend/offset/mirror these are **server-side geometry operations**
# (RESEARCH §3 + CLAUDE.md service boundaries) — the frontend must not
# reimplement the tangent-point/bisector math — served at
# ``POST /api/v1/sketch/{fillet,chamfer}`` and gateway-proxied auth-gated at
# ``/api/v1/geometry/sketch/{fillet,chamfer}``. They are stateless and
# deterministic (RESEARCH §9): identical input yields coordinate-identical
# output, computed by **exact closed-form analytic** geometry (no solver
# iteration), matching the trim/extend/offset/mirror choice. Fillet and chamfer
# share one request shape per op and one result type (:class:`SketchCornerResult`)
# — DRY: the corner-resolution, setback, and trim math is one code path, the only
# difference is the bridging entity (arc vs. line) and the size parameter's role.
#
# Unlike offset/mirror (which only ADD), a corner op both **rewrites** the two
# source curves (shortened to the tangent/setback points, **ids preserved**) AND
# **adds** the bridging entity (fresh deterministic id ``f"{a}.{n}"`` seeded from
# the WHOLE entity set, construction flag inherited from the first curve). The
# result therefore returns the whole rewritten entity set (like
# :class:`SketchEditResult`), with the two sources replaced in place and the
# bridge appended at the end.
#
# **v1 scope (honest).** **Line-line** corners only — the tangent-point/bisector
# geometry is fully closed-form. The corner is the intersection of the two lines'
# infinite supports; for each line the endpoint **farther** from that corner is
# kept and the nearer endpoint is moved to the tangent/setback point (so an
# under-length leg is extended and an over-length leg is trimmed — "extend/trim
# to the corner"). A line-arc or arc-arc corner needs a tangent-circle
# construction and is **DEFERRED**: such a target pair is rejected
# ``sketch_unsupported_entity`` (message names the deferred kinds), never
# mis-filleted. Ambiguous X-crossings are not pick-disambiguated in v1 (the
# farther-endpoint rule selects the longer legs).


class SketchFilletRequest(BaseModel):
    """Input for a sketch **fillet** (round a corner with a tangent arc).

    ``entities`` is the whole sketch's entity list (so the new arc gets a fresh
    id that cannot collide, and to mirror the trim/offset contract). ``a`` and
    ``b`` name the two curves forming the corner; each MUST be present in
    ``entities`` (else ``sketch_target_not_found``), be **distinct**, and — in
    v1 — be **lines** (a non-line, or a line-arc/arc-arc pair, is
    ``sketch_unsupported_entity``). ``radius`` is the tangent-arc radius (mm),
    strictly positive and finite.

    Both lines are trimmed to their tangent points (``radius`` from the corner
    along each leg, scaled by the corner half-angle) and a tangent arc is added.
    Errors are 422s, never 500s: ``sketch_corner_not_found`` (the supports are
    parallel/collinear, or ``a``/``b`` name the same entity — no isolated
    corner), ``sketch_corner_too_large`` (the tangent point falls past a leg's
    far end — radius too large for the available length),
    ``sketch_degenerate_result`` (a zero-length result), plus the target/kind
    codes above.
    """

    entities: list[SketchEntity] = Field(
        description="The whole sketch's entities (fillet rewrites the two "
        "corner curves and ADDS the arc)."
    )
    a: EntityId = Field(
        description="Id of the first corner line; must be in `entities`."
    )
    b: EntityId = Field(
        description="Id of the second corner line; must be in `entities`, "
        "distinct from `a`."
    )
    radius: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Fillet (tangent-arc) radius (mm); strictly positive and finite.",
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchFilletRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchChamferRequest(BaseModel):
    """Input for a sketch **chamfer** (bevel a corner with a straight line).

    Same corner contract as :class:`SketchFilletRequest` (``a``/``b`` two
    distinct line curves present in ``entities``). ``distance`` is the equal
    setback (mm) measured along each leg from the corner; strictly positive and
    finite. Both lines are trimmed to their setback points and a straight
    chamfer line is added between them. Errors are the same 422 codes as fillet
    (``sketch_corner_not_found``, ``sketch_corner_too_large`` when ``distance``
    exceeds a leg's available length, ``sketch_degenerate_result``,
    ``sketch_target_not_found``, ``sketch_unsupported_entity``).
    """

    entities: list[SketchEntity] = Field(
        description="The whole sketch's entities (chamfer rewrites the two "
        "corner curves and ADDS the bevel line)."
    )
    a: EntityId = Field(
        description="Id of the first corner line; must be in `entities`."
    )
    b: EntityId = Field(
        description="Id of the second corner line; must be in `entities`, "
        "distinct from `a`."
    )
    distance: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Equal setback distance (mm) along each leg from the corner; "
        "strictly positive and finite.",
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchChamferRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchCornerResult(BaseModel):
    """Output of a fillet/chamfer: the whole rewritten entity list.

    Like :class:`SketchEditResult` (and unlike the additive offset/mirror
    results), a corner op returns the FULL entity set: order is preserved, the
    two corner curves are replaced **in place** by their trimmed selves (ids and
    construction flags unchanged, only the corner-side endpoint moved to the
    tangent/setback point), and the bridging entity — a tangent arc (fillet) or
    straight line (chamfer) — is **appended at the end** with a fresh
    deterministic id ``f"{a}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded
    from the whole input set) inheriting the first curve's construction flag. A
    fillet arc is emitted CCW-from-start (the minor corner arc), honouring the
    :class:`SketchArc` invariant. Deterministic: identical input yields identical
    output entities, coordinates included (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The sketch entities after the corner op: the two source "
        "curves trimmed in place (ids preserved) plus the appended bridge "
        '(fresh id `f"{a}.{n}"`).'
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchCornerResult":
        # Defense in depth (same posture as SketchEditResult): the appended
        # bridge id must never collide with an existing entity. The op seeds its
        # id generator from the whole input set; enforcing uniqueness here fails
        # a regression loudly at the boundary instead of corrupting the sketch.
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self
