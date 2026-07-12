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


SketchEntity = Annotated[
    SketchPoint | SketchLine | SketchCircle | SketchArc,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

#: Named point of an entity. ``position`` addresses a point entity; ``start``/
#: ``end`` address line and arc endpoints; ``center`` addresses circle and
#: arc centers.
PointName = Literal["start", "end", "center", "position"]


class EntityPointRef(BaseModel):
    """Names one point of one entity, e.g. ``{"entity": "e1", "point": "end"}``."""

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


class DistanceConstraint(BaseModel):
    """Driving dimension: the length of a line (mm)."""

    kind: Literal["distance"]
    entity: EntityId
    value_mm: float = Field(gt=0, description="Line length (mm)")


class RadiusConstraint(BaseModel):
    """Driving dimension: the radius of a circle or arc (mm)."""

    kind: Literal["radius"]
    entity: EntityId
    value_mm: float = Field(gt=0, description="Radius (mm)")


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
