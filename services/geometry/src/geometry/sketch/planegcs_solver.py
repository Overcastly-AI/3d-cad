"""``SketchSolver`` backed by planegcs (FreeCAD's PlaneGCS solver).

planegcs (PyPI, LGPL-2.1-or-later — allowed as a dynamically-loaded dep,
RESEARCH §8) wraps the planar geometric constraint solver extracted from
FreeCAD's Sketcher. Spike verdict + license evidence: RESEARCH §2.

planegcs types stay strictly inside this module — the interface speaks only
the pydantic DTOs of :mod:`geometry.sketch.schemas`.

Determinism: entities and constraints are translated in input list order,
the solve uses planegcs's default DogLeg algorithm from the input positions
as the starting guess, and PlaneGCS itself is deterministic (no random
restarts). Same definition in → bitwise-identical solution out (asserted by
the unit suite; RESEARCH §9 "solver determinism" gate).

**An under-constrained solve HOLDS the input geometry** (SOLVE-1, RESEARCH §2).
DogLeg starting from the current positions is not the same thing as leaving the
free degrees of freedom alone: it walks a trajectory, so a value edit that only
adds slack drags geometry the edit never named, the result is a function of
solve HISTORY rather than of the constraint set, and re-typing the original
number does not restore the original shape. Measured on the product audit's own
six-dimension coupling profile (docs/AUDIT-PRODUCT.md R-5/R-5b), whose free
hexagon has DOF 6: editing one dimension 8 → 12 slid the whole profile to
``y[-3.079, 30]`` — the audit's "-3.08 below its own origin plane" — and typing
``8`` back landed **2.162 mm** from where it started. :meth:`_GcsBuild.settle`
closes that: after the solve converges, every input coordinate the constraints
still admit is pinned back to the value the author gave it, so the same edit now
moves exactly ONE corner and the retype returns to within 6.4e-14 mm.

**A settle REFINES that solve; it never re-orients it** (SETTLE-2, RESEARCH §2).
Free DOF generally leave several disconnected branches of solution, all of them
satisfying every constraint exactly, so "the residuals are still fine" does not
mean settling stayed on the branch the plain solve found — it reflected a
rectangle on the SKETCH-2 datum walk, with a SMALLER residual than the answer it
replaced. :func:`_turns_geometry_inside_out` is the guard, and
:meth:`_GcsBuild.settle`'s docstring carries the two cheaper-looking fixes that
were measured and rejected.

**A settle sacrifices the COARSEST hold the constraints will still admit, entity
by entity** (SETTLE-3, RESEARCH §2). When the author's values cannot all be kept,
something must give, and "whichever pass happened to run last" is not a policy:
a separate radius pass, running after the point passes, made a circle's SIZE the
sacrifice by arithmetic, so a line 20 mm from an r10 circle was made tangent by
doubling the circle. :meth:`_GcsBuild.settle` now walks a per-entity ladder —
the whole entity, then its SHAPE alone (:meth:`_GcsBuild._shape_pins`: a
circle's radius, a line's end-to-end vector, an arc's centre-to-endpoint
vectors), then single points, then single coordinates — which is SETTLE-2's own
finding, *holding a subset of a rigid body's points distorts the body*, applied
to the single entity. The shape rung fires only where it costs no OTHER entity
anything, which is SOLVE-1's principle turned on the settle itself; unconditional
it regresses R-5b by 10.285 mm. Its docstring carries both measurements.

**And the settle's only safety net gets a second, independently-derived opinion**
(SETTLE-3). ``constraint_error(tag)`` is the solver's report on its own parameter
array, and a hold is accepted on ``SolveStatus.Converged``, which is DogLeg
saying it STOPPED rather than that it succeeded — so that report is the whole of
the net, asked of the thing under test. It is also scoped to the CALLER's tags,
which excludes planegcs's internal arc rules (tag ``0``, ``nan``): nothing asked
whether the arc ``read_back`` is about to ship is still an arc.
:mod:`geometry.sketch.residual` re-derives every residual from the DTO entities
instead, and both must hold. The same predicate then gates the PAYLOAD, because
the sweep that went looking for a lying residual found a lying STATUS instead:
planegcs returns ``Success`` with ``conflicting=[]`` on a sketch carrying
``parallel`` and ``perpendicular`` between the same two lines
(:func:`_violated_constraints`).
"""

import math
from collections.abc import Callable
from typing import assert_never

from planegcs import ArcId, CircleId, LineId, PointId
from planegcs import ConstraintTag as GcsConstraintTag
from planegcs import Sketch as GcsSystem
from planegcs import SolveStatus as GcsSolveStatus
from py_kit.schemas.sketch import spline_fit_index

from geometry.sketch.expression import (
    evaluate_driving_dimensions,
    measure_dimension,
)
from geometry.sketch.residual import geometric_residuals, worst_residual
from geometry.sketch.schemas import (
    CoincidentConstraint,
    ConcentricConstraint,
    DimensionConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolveStatus,
    SketchSpline,
    SolvedDimension,
    SolvedSketch,
    SymmetricConstraint,
    TangentConstraint,
    VerticalConstraint,
)
from geometry.sketch.solver import SketchDefinitionError

# --- tuned, documented tolerances (never ad-hoc; RESEARCH §9) -------------------

#: Largest per-constraint residual at which a constraint counts as SATISFIED.
#: planegcs reports it through ``constraint_error(tag)`` (the RMS error of the
#: constraints carrying that tag) in the constraint's own units — mm for a
#: distance/radius, dimensionless-or-radian for the angular kinds — and 1e-7 is
#: below both scales' meaningful resolution while sitting three orders of
#: magnitude under the kernel linear tolerance (1e-7 m = 1e-4 mm), so a solve
#: this suite calls satisfied can never carry a kernel-relevant error.
#:
#: Deliberately the same number and the same role as the ASSEMBLY solver's
#: ``SATISFIED_TOL`` (``geometry/assembly/solver.py``): a converged numeric
#: solve is not evidence that the constraints hold, so both solvers ask the
#: residual before believing their own optimiser. This module had no residual
#: concept at all until SOLVE-1 (docs/AUDIT-ENGINEERING.md Pass 8 N1).
SATISFIED_TOL_MM = 1e-7


class PlanegcsSketchSolver:
    """Solve :class:`SketchDefinition` sketches with planegcs.

    Stateless: every :meth:`solve` builds a fresh planegcs system, so calls
    are independent and safe to repeat (the geometry service is stateless by
    contract).
    """

    def solve(self, sketch: SketchDefinition) -> SolvedSketch:
        # Resolve dimension expressions FIRST (input prep): driving dimensions
        # get a concrete value (literal or evaluated expression); a bad
        # expression / unknown-or-driven ref / cycle / div-zero raises
        # SketchExpressionError (a SketchDefinitionError → sketch_invalid).
        # Driven dimensions are absent from this map and never fed to the solver.
        driving_values = evaluate_driving_dimensions(sketch.constraints)
        system = _GcsBuild(sketch, driving_values)
        raw_status = system.gcs.solve()  # default DogLeg — deterministic
        diagnosis = system.gcs.diagnose()
        solved = raw_status in (GcsSolveStatus.Success, GcsSolveStatus.Converged)

        status = _map_status(
            solved=solved,
            conflicting=bool(diagnosis.conflicting),
            redundant=bool(diagnosis.redundant),
            dof=diagnosis.dof,
        )
        # Internal tags (e.g. arc rules auto-added by planegcs) are not in
        # the map; report only indices of caller-supplied constraints.
        conflicting = sorted(
            {
                system.tag_to_index[tag]
                for tag in diagnosis.conflicting
                if tag in system.tag_to_index
            }
        )
        redundant = sorted(
            {
                system.tag_to_index[tag]
                for tag in diagnosis.redundant
                if tag in system.tag_to_index
            }
        )
        if solved and not diagnosis.conflicting and diagnosis.dof > 0:
            # SOLVE-1: the free DOF are the author's to keep, not the
            # optimiser's to spend. Skipped entirely at DOF 0 (nothing is free)
            # and when the system conflicts (the geometry below is the input).
            entities = system.settle()
        elif solved:
            entities = system.read_back()
        else:
            entities = [entity.model_copy(deep=True) for entity in sketch.entities]

        # A converged optimiser is not evidence that the constraints hold (the
        # assembly solver's SATISFIED_TOL posture, applied here). A payload may
        # not ship geometry its own constraints contradict, so a solve whose
        # geometry violates one is reclassified as the conflict it is, and —
        # like every other conflicting solve — returns the input geometry
        # untouched rather than a silent least-squares compromise.
        violated = (
            _violated_constraints(sketch, entities, driving_values) if solved else []
        )
        if violated:
            status = "conflicting"
            entities = [entity.model_copy(deep=True) for entity in sketch.entities]
            conflicting = sorted(set(conflicting) | set(violated))

        dimensions = _dimension_readouts(sketch.constraints, entities, driving_values)
        return SolvedSketch(
            status=status,
            entities=entities,
            dof=diagnosis.dof if diagnosis.dof >= 0 else None,
            conflicting_constraints=conflicting,
            redundant_constraints=redundant,
            dimensions=dimensions,
        )


def _submitted_points(
    entities: list[SketchEntity],
) -> dict[tuple[str, str], tuple[float, float]]:
    """``(entity id, point name)`` -> coordinate, over a list of entities."""
    return {
        (entity.id, name): (point.x, point.y)
        for entity in entities
        for name, point in _entity_point_names(entity)
    }


def _violated_constraints(
    sketch: SketchDefinition,
    entities: list[SketchEntity],
    driving_values: dict[int, float],
) -> list[int]:
    """Indices of the constraints the solved geometry does not satisfy.

    Measured from the ENTITIES, by :func:`geometry.sketch.residual`, so the one
    predicate answers this for the payload and for every settle hold. It began
    (SOLVE-1) as a check on DRIVING DIMENSIONS only — the reasoning being that a
    payload may not report a number the geometry beside it contradicts — and the
    narrowness was the defect, not the reasoning: a payload may not ship geometry
    ANY of its constraints contradicts, and a relational constraint is no less
    load-bearing than a dimension for having no readout.

    **planegcs's own verdict is not sufficient to close this, which is why the
    check exists at the payload level and not only inside the settle.** Found
    2026-08-22 by a randomised sweep over 400 generated sketches: on a sketch
    carrying both ``parallel`` and ``perpendicular`` between the same two lines
    — flatly unsatisfiable — ``diagnose()`` returns ``conflicting=[]`` and
    ``solve()`` returns ``SolveStatus.Success``, and the service shipped
    ``status="underconstrained"`` with the two lines at 67 degrees to each
    other. Seven of the 155 solvable sketches in that sweep shipped a violated
    constraint the same way. The solver's STATUS is a self-report exactly as its
    residual is; the geometry is the evidence.
    """
    return [
        index
        for index, residual in geometric_residuals(
            sketch.constraints,
            entities,
            # A ``fixed`` constraint pins a point to the coordinate the AUTHOR
            # submitted, so its reference is the input sketch, never the solved
            # entities — against those it would be trivially satisfied.
            _submitted_points(sketch.entities),
            driving_values,
        )
        if residual > SATISFIED_TOL_MM
    ]


def _dimension_readouts(
    constraints: list[SketchConstraint],
    entities: list[SketchEntity],
    driving_values: dict[int, float],
) -> list[SolvedDimension]:
    """Per-dimension computed values for the solved payload.

    A driving dimension reports the value fed to the solver (evaluated
    expression / literal); a driven dimension reports the value MEASURED back
    from the solved geometry (the read-only readout that tracks the geometry it
    dimensions). One entry per dimension constraint, in input order.

    **Invariant (SOLVE-1): no readout disagrees with the ``entities`` beside it
    in the same payload by more than :data:`SATISFIED_TOL_MM`.** A driving
    dimension's requested value is therefore VERIFIED against the geometry
    before it is reported, and where it does not describe that geometry — a
    conflicting or diverged solve returns the input entities untouched, so the
    requested number is exactly the one they do not have — the MEASURED value is
    reported instead. Reporting the request unchecked is how the service came to
    claim a 12 mm dimension on an 8 mm line (docs/AUDIT-ENGINEERING.md Pass 8
    N1); nothing in the payload contradicted it.
    """
    entities_by_id = {entity.id: entity for entity in entities}
    readouts: list[SolvedDimension] = []
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, DimensionConstraint):
            continue
        measured = measure_dimension(constraint, entities_by_id)
        requested = driving_values.get(index)
        value = (
            requested
            if requested is not None and abs(measured - requested) <= SATISFIED_TOL_MM
            else measured
        )
        readouts.append(
            SolvedDimension(
                constraint_index=index,
                name=constraint.name,
                driving=constraint.is_driving,
                value_mm=value,
                expression=constraint.expression,
            )
        )
    return readouts


def _map_status(
    *, solved: bool, conflicting: bool, redundant: bool, dof: int
) -> SketchSolveStatus:
    """Precedence documented on :data:`~geometry.sketch.schemas.SketchSolveStatus`."""
    if conflicting:
        return "conflicting"
    if redundant:
        return "overconstrained"
    if not solved:
        return "diverged"
    if dof > 0:
        return "underconstrained"
    return "converged"


def _constraint_point_refs(constraint: SketchConstraint) -> tuple[EntityPointRef, ...]:
    """The ``EntityPointRef``s a constraint carries (empty for entity-only ones).

    Only these three constraint kinds address individual points; the rest relate
    whole entities by id. Used to discover which spline fit points a sketch
    actually constrains (so only *those* enter the solver — an unconstrained
    fit point contributes no DOF, matching the pre-v1.1 pass-through).

    The entity-only kinds are enumerated EXPLICITLY (not a ``case _`` wildcard)
    with an ``assert_never`` tail: if a future constraint kind grows an
    ``EntityPointRef``, pyright fails here until it is classified, rather than a
    wildcard silently dropping its point refs (whose fit points would then never
    register and the valid constraint would surface a misleading error).
    """
    match constraint:
        case CoincidentConstraint() | SymmetricConstraint():
            return (constraint.a, constraint.b)
        case FixedConstraint():
            return (constraint.point,)
        case (
            HorizontalConstraint()
            | VerticalConstraint()
            | DistanceConstraint()
            | RadiusConstraint()
            | ParallelConstraint()
            | PerpendicularConstraint()
            | TangentConstraint()
            | EqualConstraint()
            | ConcentricConstraint()
        ):
            return ()
        case _:
            assert_never(constraint)


def _referenced_fit_points(constraints: list[SketchConstraint]) -> set[tuple[str, str]]:
    """``(entity_id, "fitN")`` pairs some constraint references, in the sketch.

    A fit reference to a NON-spline entity (or an out-of-range index) is still
    collected here; it simply never matches a registered spline fit point and so
    surfaces later as a clean malformed-reference error at constraint time.
    """
    referenced: set[tuple[str, str]] = set()
    for constraint in constraints:
        for ref in _constraint_point_refs(constraint):
            if spline_fit_index(ref.point) is not None:
                referenced.add((ref.entity, ref.point))
    return referenced


def _directions(entities: list[SketchEntity]) -> dict[str, tuple[float, float]]:
    """Entity id → the vector whose SENSE says which way the entity runs.

    A line's start->end; an arc's start->end chord. Points, circles and splines
    have no such sense and are absent. Used only to compare two solutions of the
    SAME sketch, so the ids line up by construction.
    """
    senses: dict[str, tuple[float, float]] = {}
    for entity in entities:  # input order — deterministic (RESEARCH §9)
        match entity:
            case SketchLine() | SketchArc():
                senses[entity.id] = (
                    entity.end.x - entity.start.x,
                    entity.end.y - entity.start.y,
                )
            case _:
                pass
    return senses


def _entity_point_names(entity: SketchEntity) -> list[tuple[str, Point2D]]:
    """``(point name, submitted coordinate)`` for every point an entity owns.

    The one enumeration of "which points does this kind of entity have", in the
    order the solver registers them, shared by the placement targets
    (:meth:`_GcsBuild._input_points`) and the shape pins
    (:meth:`_GcsBuild._shape_pins`) — the two must agree about the point set or
    a settle would hold one view of the entity against another.

    A circle contributes only its centre: its radius is a shape parameter, not
    a point, and is pinned separately.
    """
    match entity:
        case SketchPoint():
            return [("position", entity.position)]
        case SketchLine():
            return [("start", entity.start), ("end", entity.end)]
        case SketchCircle():
            return [("center", entity.center)]
        case SketchArc():
            return [
                ("center", entity.center),
                ("start", entity.start),
                ("end", entity.end),
            ]
        case SketchSpline():
            return [(f"fit{index}", point) for index, point in enumerate(entity.points)]
        case _:  # pragma: no cover — the entity union is closed
            assert_never(entity)


def _turns_geometry_inside_out(
    settled: list[SketchEntity], baseline: list[SketchEntity]
) -> bool:
    """Does ``settled`` run any entity BACKWARDS relative to ``baseline``?

    The invariant separating a settle that REFINES the plain solve from one that
    has jumped to a different branch of the solution manifold. Settling only
    ever pulls coordinates back toward the values the author submitted, and the
    plain solve is itself a walk from those same values, so the two must agree
    about which way every edge runs. A negative dot product means they disagree
    by more than a right angle, which no refinement does.

    Cheap, scale-free, and needs no tolerance: a degenerate entity has a zero
    vector, whose dot product is ``0.0`` and so never trips the strict ``< 0``
    (CLAUDE.md — no ad-hoc epsilons).
    """
    before = _directions(baseline)
    for entity_id, (x, y) in _directions(settled).items():
        before_x, before_y = before[entity_id]
        if x * before_x + y * before_y < 0.0:
            return True
    return False


class _GcsBuild:
    """Translation of one ``SketchDefinition`` into a planegcs system.

    Holds the DTO-id → planegcs-handle maps needed to apply constraints, map
    diagnosis tags back to constraint indices, and read solved geometry out.
    """

    def __init__(
        self, sketch: SketchDefinition, driving_values: dict[int, float]
    ) -> None:
        self.sketch = sketch
        #: constraint index -> evaluated value, for DRIVING dimensions only. A
        #: dimension constraint whose index is absent is DRIVEN — excluded from
        #: the constraint system (its value is measured back post-solve).
        self.driving_values = driving_values
        self.gcs = GcsSystem()
        self._points: dict[tuple[str, str], PointId] = {}
        self._lines: dict[str, LineId] = {}
        self._circles: dict[str, CircleId] = {}
        self._arcs: dict[str, ArcId] = {}
        #: ``(spline id, "fitN")`` pairs some constraint references. Only these
        #: spline fit points are added to the constraint system; unreferenced fit
        #: points stay out of it (zero DOF, preserved bitwise).
        self._referenced_fit_points = _referenced_fit_points(sketch.constraints)
        #: planegcs constraint tag → index into ``sketch.constraints``.
        self.tag_to_index: dict[int, int] = {}
        for entity in sketch.entities:  # input order — deterministic
            self._add_entity(entity)
        for index, constraint in enumerate(sketch.constraints):
            self._add_constraint(index, constraint)

    # -- entities -----------------------------------------------------------

    def _add_point(self, entity_id: str, name: str, point: Point2D) -> PointId:
        pid = self.gcs.add_point(point.x, point.y)
        self._points[(entity_id, name)] = pid
        return pid

    def _add_entity(self, entity: SketchEntity) -> None:
        match entity:
            case SketchPoint():
                self._add_point(entity.id, "position", entity.position)
            case SketchLine():
                p1 = self._add_point(entity.id, "start", entity.start)
                p2 = self._add_point(entity.id, "end", entity.end)
                self._lines[entity.id] = self.gcs.add_line(p1, p2)
            case SketchCircle():
                center = self._add_point(entity.id, "center", entity.center)
                radius = self.gcs.add_param(entity.radius, fixed=False)
                self._circles[entity.id] = self.gcs.add_circle(center, radius)
            case SketchArc():
                radius = math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
                if radius == 0.0:
                    raise SketchDefinitionError(
                        f"Arc {entity.id!r} is degenerate: start coincides with center"
                    )
                start_angle = math.atan2(
                    entity.start.y - entity.center.y,
                    entity.start.x - entity.center.x,
                )
                end_angle = math.atan2(
                    entity.end.y - entity.center.y,
                    entity.end.x - entity.center.x,
                )
                if end_angle <= start_angle:  # CCW convention (schemas)
                    end_angle += math.tau
                center = self._add_point(entity.id, "center", entity.center)
                start = self._add_point(entity.id, "start", entity.start)
                end = self._add_point(entity.id, "end", entity.end)
                # add_arc_cse -> add_arc auto-adds the arc-rules constraints
                # tying start/end to center/radius/angles; do NOT add them
                # again (that would be a redundant constraint).
                self._arcs[entity.id] = self.gcs.add_arc_cse(
                    center, start, end, radius, start_angle, end_angle
                )
            case SketchSpline():
                # Constrainable FIT POINTS (v1.1, SketchSpline docstring):
                # planegcs still has no spline primitive, so the CURVE is not in
                # the solver — but each fit point a constraint references is added
                # as a gcs point named ``"fitN"``, so it takes point-level
                # constraints like any other point. A fit point NO constraint
                # references is left out entirely (zero added DOF), so an
                # unconstrained spline solves as fixed geometry exactly as before.
                # An out-of-range ``"fitN"`` was collected but is never registered
                # here (no such index), so it resolves to no point -> a clean
                # SketchDefinitionError at constraint time. read_back() rebuilds
                # the spline through the solved fit-point positions.
                for index, point in enumerate(entity.points):
                    name = f"fit{index}"
                    if (entity.id, name) in self._referenced_fit_points:
                        self._add_point(entity.id, name, point)

    # -- constraints ---------------------------------------------------------

    def _resolve_point(self, ref: EntityPointRef) -> PointId:
        try:
            return self._points[(ref.entity, ref.point)]
        except KeyError:
            raise SketchDefinitionError(
                f"No point {ref.point!r} on entity {ref.entity!r} (unknown "
                "entity id, or a point name the entity kind does not have)"
            ) from None

    def _resolve_line(self, entity_id: str, constraint_kind: str) -> LineId:
        try:
            return self._lines[entity_id]
        except KeyError:
            raise SketchDefinitionError(
                f"Constraint {constraint_kind!r} requires a line entity; "
                f"{entity_id!r} is not a known line"
            ) from None

    def _add_constraint(self, index: int, constraint: object) -> None:
        gcs = self.gcs
        match constraint:
            case CoincidentConstraint():
                tag = gcs.coincident(
                    self._resolve_point(constraint.a),
                    self._resolve_point(constraint.b),
                )
            case HorizontalConstraint():
                line = self._resolve_line(constraint.entity, "horizontal")
                tag = gcs.horizontal(line)
            case VerticalConstraint():
                tag = gcs.vertical(self._resolve_line(constraint.entity, "vertical"))
            case DistanceConstraint():
                if index not in self.driving_values:
                    return  # DRIVEN — not fed to the solver (measured post-solve)
                line_id = constraint.entity
                self._resolve_line(line_id, "distance")  # kind check
                tag = gcs.set_p2p_distance(
                    self._points[(line_id, "start")],
                    self._points[(line_id, "end")],
                    self.driving_values[index],
                )
            case RadiusConstraint():
                if index not in self.driving_values:
                    return  # DRIVEN — not fed to the solver (measured post-solve)
                value = self.driving_values[index]
                if constraint.entity in self._circles:
                    tag = gcs.set_circle_radius(self._circles[constraint.entity], value)
                elif constraint.entity in self._arcs:
                    tag = gcs.set_arc_radius(self._arcs[constraint.entity], value)
                else:
                    raise SketchDefinitionError(
                        "Constraint 'radius' requires a circle or arc entity; "
                        f"{constraint.entity!r} is neither"
                    )
            case FixedConstraint():
                point_id = self._resolve_point(constraint.point)
                x, y = gcs.get_point(point_id)  # pre-solve = input position
                fix_x, fix_y = gcs.fix_point(point_id, x, y)
                self.tag_to_index[fix_x] = index
                self.tag_to_index[fix_y] = index
                return
            case ParallelConstraint():
                tag = gcs.parallel(
                    self._resolve_line(constraint.a, "parallel"),
                    self._resolve_line(constraint.b, "parallel"),
                )
            case PerpendicularConstraint():
                tag = gcs.perpendicular(
                    self._resolve_line(constraint.a, "perpendicular"),
                    self._resolve_line(constraint.b, "perpendicular"),
                )
            case TangentConstraint():
                tag = self._add_tangent(constraint)
            case EqualConstraint():
                tag = self._add_equal(constraint)
            case SymmetricConstraint():
                tag = gcs.symmetric_line(
                    self._resolve_point(constraint.a),
                    self._resolve_point(constraint.b),
                    self._resolve_line(constraint.line, "symmetric"),
                )
            case ConcentricConstraint():
                tag = self._add_concentric(constraint)
            case _:  # pragma: no cover — unreachable via the DTO union
                raise SketchDefinitionError(f"Unsupported constraint: {constraint!r}")
        self.tag_to_index[tag] = index

    def _classify_curve(self, entity_id: str, constraint_kind: str = "tangent") -> str:
        """Return ``"line"``/``"circle"``/``"arc"`` for an entity ref, or raise."""
        if entity_id in self._lines:
            return "line"
        if entity_id in self._circles:
            return "circle"
        if entity_id in self._arcs:
            return "arc"
        raise SketchDefinitionError(
            f"Constraint {constraint_kind!r} references {entity_id!r}, which is "
            "not a known line, circle, or arc entity"
        )

    def _add_tangent(self, constraint: TangentConstraint) -> int:
        """Dispatch to the planegcs tangency variant for the resolved kinds.

        planegcs exposes a distinct native constraint per curve-pair shape
        (``tangent_line_arc``/``tangent_line_circle``/``tangent_arc_arc``/
        ``tangent_circle_circle``/``tangent_circle_arc``); tangency is
        symmetric, so ``a``/``b`` are reordered to each variant's argument
        order. Two lines cannot be tangent and are rejected. The (kind, kind)
        match is fixed by input, so dispatch is deterministic.
        """
        gcs = self.gcs
        a_id, b_id = constraint.a, constraint.b
        pair = (self._classify_curve(a_id), self._classify_curve(b_id))
        match pair:
            case ("line", "arc"):
                return gcs.tangent_line_arc(self._lines[a_id], self._arcs[b_id])
            case ("arc", "line"):
                return gcs.tangent_line_arc(self._lines[b_id], self._arcs[a_id])
            case ("line", "circle"):
                return gcs.tangent_line_circle(self._lines[a_id], self._circles[b_id])
            case ("circle", "line"):
                return gcs.tangent_line_circle(self._lines[b_id], self._circles[a_id])
            case ("arc", "arc"):
                return gcs.tangent_arc_arc(self._arcs[a_id], self._arcs[b_id])
            case ("circle", "circle"):
                return gcs.tangent_circle_circle(
                    self._circles[a_id], self._circles[b_id]
                )
            case ("circle", "arc"):
                return gcs.tangent_circle_arc(self._circles[a_id], self._arcs[b_id])
            case ("arc", "circle"):
                return gcs.tangent_circle_arc(self._circles[b_id], self._arcs[a_id])
            case _:  # ("line", "line") — no common-tangent relation
                raise SketchDefinitionError(
                    "Constraint 'tangent' relates a line and a curve, or two "
                    f"curves; {pair} is not a tangency-capable pair"
                )

    def _add_equal(self, constraint: EqualConstraint) -> int:
        """Dispatch to the planegcs equal-size variant for the resolved kinds.

        planegcs has no single "equal" constraint: two lines get
        ``equal_length``; equal *radius* has one native variant per curve-pair
        shape (``equal_radius_cc``/``equal_radius_aa``/``equal_radius_ca``).
        Equality is symmetric, so the circle-and-arc pair is reordered to
        ``equal_radius_ca``'s (circle, arc) argument order. A mismatched pair
        (a line paired with a circle/arc) has no equal-size relation and is
        rejected. The (kind, kind) match is fixed by input, so dispatch is
        deterministic.
        """
        gcs = self.gcs
        a_id, b_id = constraint.a, constraint.b
        pair = (
            self._classify_curve(a_id, "equal"),
            self._classify_curve(b_id, "equal"),
        )
        match pair:
            case ("line", "line"):
                return gcs.equal_length(self._lines[a_id], self._lines[b_id])
            case ("circle", "circle"):
                return gcs.equal_radius_cc(self._circles[a_id], self._circles[b_id])
            case ("arc", "arc"):
                return gcs.equal_radius_aa(self._arcs[a_id], self._arcs[b_id])
            case ("circle", "arc"):
                return gcs.equal_radius_ca(self._circles[a_id], self._arcs[b_id])
            case ("arc", "circle"):
                return gcs.equal_radius_ca(self._circles[b_id], self._arcs[a_id])
            case _:  # (line, circle/arc) and its mirror — no equal-size relation
                raise SketchDefinitionError(
                    "Constraint 'equal' relates two lines (equal length) or two "
                    f"circles/arcs (equal radius); {pair} is not an equal-capable "
                    "pair"
                )

    def _add_concentric(self, constraint: ConcentricConstraint) -> int:
        """Tie two circle/arc centers together (planegcs has no ``concentric``).

        FreeCAD's concentric constraint is coincident centers; planegcs offers
        no dedicated method, so ``coincident`` on the two center points is the
        exact equivalent. Both entities must be a circle or arc (each owns a
        ``center`` point); a line is rejected.
        """
        a_kind = self._classify_curve(constraint.a, "concentric")
        b_kind = self._classify_curve(constraint.b, "concentric")
        for entity_id, kind in ((constraint.a, a_kind), (constraint.b, b_kind)):
            if kind == "line":
                raise SketchDefinitionError(
                    "Constraint 'concentric' relates two circles/arcs; "
                    f"{entity_id!r} is a line and has no center"
                )
        return self.gcs.coincident(
            self._points[(constraint.a, "center")],
            self._points[(constraint.b, "center")],
        )

    # -- holding the free DOF (SOLVE-1) --------------------------------------

    def _input_points(self) -> dict[tuple[str, str], tuple[float, float]]:
        """``(entity id, point name)`` → the coordinate the AUTHOR submitted.

        Read from ``self.sketch`` rather than from the solver, so it is the
        input position even after :meth:`settle` has moved the system around.
        """
        return _submitted_points(self.sketch.entities)

    def _solver_says_satisfied(self, extra: list[GcsConstraintTag]) -> bool:
        """Is every CALLER constraint (plus ``extra``) within tolerance?

        ``constraint_error`` is only meaningful for tags the Sketch API
        registered: planegcs's internally-added rules (the arc rules behind
        ``add_arc_cse``) all share tag 0, whose error reads ``nan`` — asking for
        it would reject every trial, so the caller's own tags are the honest
        scope. ``nan`` from any tag fails the comparison, which is the safe
        direction (a hold is rejected, never wrongly accepted).

        **This is the solver's opinion of its own parameter array, and it is not
        sufficient on its own** — see :meth:`_geometry_says_satisfied`, which is
        asked alongside it by :meth:`_constraints_satisfied`.
        """
        solver = self.gcs.solver
        return all(
            abs(solver.constraint_error(tag)) <= SATISFIED_TOL_MM
            for tag in [*self.tag_to_index, *extra]
        )

    def _geometry_says_satisfied(self) -> bool:
        """Do the ENTITIES this solve would ship satisfy the caller's constraints?

        The second, independently-derived opinion (SETTLE-3, module docstring).
        :meth:`_solver_says_satisfied` asks the solver about its own parameters;
        this re-derives every residual from the DTOs :meth:`read_back` produces,
        through :mod:`geometry.sketch.residual`, and covers two things the first
        opinion structurally cannot: an arc whose endpoints have stopped
        agreeing about their own centre (planegcs's tag-0 arc rules, outside the
        caller-tag scope), and any state where the parameter array and the
        entities read out of it have come apart.

        The two share the ``SATISFIED_TOL_MM`` scale deliberately — the formulas
        are planegcs's own, re-implemented over different data — so a
        disagreement means the geometry and the solver disagree, not that two
        conventions were compared. Measured agreement across the solver suite's
        fixtures: worst gap ``3.3e-12`` mm, five orders under the tolerance.
        """
        return (
            worst_residual(
                self.sketch.constraints,
                self.read_back(),
                self._input_points(),
                self.driving_values,
            )
            <= SATISFIED_TOL_MM
        )

    def _constraints_satisfied(self, extra: list[GcsConstraintTag]) -> bool:
        """Both opinions, because one of them is the thing under test.

        CLAUDE.md's standing answer to a self-verifying check: *a wrong claim
        verifies happily against itself* — get a second opinion from a different
        derivation, not a louder assertion of the first.
        """
        return self._solver_says_satisfied(extra) and self._geometry_says_satisfied()

    def _keep_or_roll_back(
        self,
        added: list[GcsConstraintTag],
        also: Callable[[], bool] | None = None,
    ) -> bool:
        """Re-solve with ``added`` in place; keep them only if everything holds.

        A hold is accepted only when the re-solve converges AND leaves every
        caller constraint — including the new pins — satisfied, so settling can
        only ever return geometry at least as correct as the unsettled solve.
        Note ``Converged`` is accepted as convergence and, in FreeCAD's DogLeg,
        means the iteration STOPPED rather than that it found a root: the
        residual check is not a formality here, it is the whole of the gate.

        **Orientation is deliberately NOT judged here, per hold — it is judged
        once, over the finished settle, in :meth:`settle`.** The per-hold
        placement is the tempting one (drop only the guilty hold, keep the
        innocent ones) and it is measurably worse, because on a shape whose SIZE
        is a free degree of freedom the holds are not independent. On the
        SKETCH-2 datum fixture — a rigid rectangle made symmetric about the X
        axis — refusing only the reflecting holds leaves the ones that pin the
        two TOP corners at their submitted ``y = 24``, and symmetry then drives
        the bottom corners to ``-24``: a rectangle stretched from 16 mm tall to
        48 mm, right way up. Correct by every per-hold rule and further from what
        the author drew than doing nothing at all. Holding a SUBSET of a rigid
        body's points distorts the body; the choice is all of them or none, and
        that is the choice ``settle`` makes.

        ``also`` is an extra acceptance predicate evaluated on the re-solved
        system, used by :meth:`_try_hold_shape` for the one question a residual
        cannot answer: *what did this hold cost everybody else?*
        """
        status = self.gcs.solve()
        if (
            status in (GcsSolveStatus.Success, GcsSolveStatus.Converged)
            and self._constraints_satisfied(added)
            and (also is None or also())
        ):
            return True
        for tag in added:
            self.gcs.solver.clear_by_tag(tag)
        self.gcs.solve()  # back to a solution of the un-held system
        return False

    def _try_hold_point(
        self, point_id: PointId, axes: tuple[int, ...], target: tuple[float, float]
    ) -> bool:
        """Pin ``axes`` of ``point_id`` at their input values, if it still solves."""
        added: list[GcsConstraintTag] = []
        for axis in axes:
            anchor = self.gcs.add_param(target[axis], fixed=True)
            added.append(
                self.gcs.coordinate_x(point_id, anchor)
                if axis == 0
                else self.gcs.coordinate_y(point_id, anchor)
            )
        return self._keep_or_roll_back(added)

    def _placement_pins(self, entities: list[SketchEntity]) -> list[GcsConstraintTag]:
        """Pin ``entities`` completely: every coordinate AND every radius.

        Everything the author gave the entity — what it is and where it sits.
        Passed the whole sketch this is the settle's fast path; passed one
        entity it is the top rung of the per-entity ladder in :meth:`settle`.
        """
        pins: list[GcsConstraintTag] = []
        for entity in entities:  # input order — deterministic (RESEARCH §9)
            for name, point in _entity_point_names(entity):
                point_id = self._points.get((entity.id, name))
                if point_id is None:  # an unreferenced spline fit point
                    continue
                pins.append(
                    self.gcs.coordinate_x(
                        point_id, self.gcs.add_param(point.x, fixed=True)
                    )
                )
                pins.append(
                    self.gcs.coordinate_y(
                        point_id, self.gcs.add_param(point.y, fixed=True)
                    )
                )
            if isinstance(entity, SketchCircle):
                pins.append(
                    self.gcs.set_circle_radius(self._circles[entity.id], entity.radius)
                )
        return pins

    def _try_hold_placement(self, entities: list[SketchEntity]) -> bool:
        """Hold ``entities`` completely, if the system still solves."""
        pins = self._placement_pins(entities)
        return self._keep_or_roll_back(pins) if pins else True

    def _try_hold_everything(self) -> bool:
        """Pin EVERY free parameter at once — the whole settle in one solve.

        A performance fast path with no semantic content, and it is safe for a
        reason worth stating: when this succeeds, every input coordinate and
        radius is retained AND every caller constraint holds, which is the
        maximum the per-entity passes below can ever achieve. So a success here
        and a full run of those passes return the same geometry; this just
        reaches it in ONE solve instead of one per entity and point.

        It matters because of the product's own feedback loop. ``PartPage``
        adopts solved positions back into the sketch, and a tree rebuild
        re-solves every sketch from its STORED positions — which are the
        previous solve's output, i.e. already an exact solution. Holding all of
        it therefore succeeds outright for every solve that is not reacting to
        an edit, which is most of them. Measured on a 96-line closed polygon
        (192 points, DOF 96) whose stored positions already solve: **45 ms**
        unsettled, **11 050 ms** through the per-point passes, **147 ms** (n=4,
        146-153 ms) through this one — settling a sketch nothing has disturbed
        costs 3.3x rather than 245x. The growth is what forces the path: the
        per-point passes run a solve per point, so they scale about n^3 (5 /
        17 / 95 / 936 / 11 050 ms at n = 6 / 12 / 24 / 48 / 96 lines), and a
        live sketcher re-solves on every keystroke of a dimension edit.

        On failure ``_keep_or_roll_back`` clears the pins and re-solves, and
        the per-entity passes run exactly as before, one wasted solve later.
        """
        return self._try_hold_placement(self.sketch.entities)

    def _shape_pins(self, entities: list[SketchEntity]) -> list[GcsConstraintTag]:
        """Pin every entity's INTRINSIC geometry, leaving where it sits free.

        An entity's shape is what the author drew; its placement is what the
        constraints are for. The two are expressed differently in the solver and
        that is the whole point:

        * a **circle**'s shape is its radius — one scalar, ``set_circle_radius``;
        * every other entity's shape is its points measured RELATIVE to its
          first point, pinned with ``difference`` on the x and y parameters. Two
          such pins on a line hold its length *and* its direction while leaving
          it free to translate; on an arc, the centre-to-start and centre-to-end
          vectors hold radius and both endpoint angles, i.e. the whole arc.
        * a **point** has no intrinsic shape, and a **spline**'s is the shape of
          its fit polygon (only the fit points a constraint references are in
          the system at all — an unreferenced one is not the solver's to move).

        Absolute coordinates cannot express this. Pinning both endpoints of a
        line holds its shape *and* nails it down, so a constraint that needs the
        line to move can only be satisfied by refusing the hold outright — and
        then the single-axis fallback pins ONE coordinate of ONE endpoint, which
        is SETTLE-2's own finding (holding a subset of a rigid body's points
        distorts the body) applied, unintentionally, to a single entity. With
        the shape held first, that fallback can only slide the entity.
        """
        gcs = self.gcs
        pins: list[GcsConstraintTag] = []
        for entity in entities:  # input order — deterministic (RESEARCH §9)
            if isinstance(entity, SketchCircle):
                pins.append(
                    gcs.set_circle_radius(self._circles[entity.id], entity.radius)
                )
                continue
            named = [
                (name, point)
                for name, point in _entity_point_names(entity)
                if (entity.id, name) in self._points
            ]
            if len(named) < 2:
                continue
            anchor_name, anchor = named[0]
            anchor_x, anchor_y = gcs.get_point_param_ids(
                self._points[(entity.id, anchor_name)]
            )
            for name, point in named[1:]:
                point_x, point_y = gcs.get_point_param_ids(
                    self._points[(entity.id, name)]
                )
                pins.append(
                    gcs.difference(
                        anchor_x, point_x, gcs.add_param(point.x - anchor.x, fixed=True)
                    )
                )
                pins.append(
                    gcs.difference(
                        anchor_y, point_y, gcs.add_param(point.y - anchor.y, fixed=True)
                    )
                )
        return pins

    def _drift_of_everything_else(
        self, entity_id: str, targets: dict[tuple[str, str], tuple[float, float]]
    ) -> float:
        """How far the REST of the sketch currently sits from the author's input (mm).

        Every registered point and every circle radius that does not belong to
        ``entity_id``, worst case. Deliberately absolute rather than relative to
        the plain solve: the question :meth:`_try_hold_shape` asks with it is
        whether a hold made anybody else worse, which is a comparison of this
        number against itself before and after.
        """
        worst = 0.0
        for (owner, name), point_id in self._points.items():  # input order
            if owner == entity_id:
                continue
            target = targets.get((owner, name))
            if target is None:  # pragma: no cover - every registered point has one
                continue
            x, y = self.gcs.get_point(point_id)
            worst = max(worst, abs(x - target[0]), abs(y - target[1]))
        for entity in self.sketch.entities:
            if entity.id == entity_id or not isinstance(entity, SketchCircle):
                continue
            solved = self.gcs.get_circle(self._circles[entity.id])
            worst = max(worst, abs(solved.radius - entity.radius))
        return worst

    def _try_hold_shape(
        self, entity: SketchEntity, targets: dict[tuple[str, str], tuple[float, float]]
    ) -> bool:
        """Hold ``entity``'s shape — but only if it costs no OTHER entity anything.

        The extra condition is not caution, it is what makes this rung a policy
        instead of a bias, and it is SOLVE-1's own principle turned on the settle
        itself: *an edit may not move geometry it never named*, so neither may a
        hold. A shape pin constrains a RELATIONSHIP rather than a value, so —
        unlike a coordinate pin, which the system can only satisfy by putting
        that coordinate where it was asked — it can be satisfied by shoving
        everything attached to the entity somewhere else, and the plain
        "does it still solve" test cannot see the difference.

        Measured, and this is the whole reason the rung is conditional. On the
        tangent fixture the circle is already held complete, so pinning the
        line's end-to-end vector moves nobody: drift elsewhere stays ``0`` and
        the line slides. On the R-5b coupling the same rung pins ``e3``'s
        direction inside a closed six-edge chain whose free DOF ARE the corner
        angles, and the chain answers by shifting: ``e4``, ``e5`` and ``e6`` —
        edges the edit never named — move **10.285 mm**, and the settle returns
        geometry worse than doing nothing. Unconditional, this rung is a
        regression; conditional, it fires exactly where a rigid body has room to
        be one.
        """
        pins = self._shape_pins([entity])
        if not pins:
            return False
        before = self._drift_of_everything_else(entity.id, targets)
        return self._keep_or_roll_back(
            pins,
            also=lambda: (
                self._drift_of_everything_else(entity.id, targets)
                <= before + SATISFIED_TOL_MM
            ),
        )

    def settle(self) -> list[SketchEntity]:
        """Re-solve holding every input value the constraints still allow.

        Runs only on an under-constrained, non-conflicting solve. The passes run
        in input entity order (so the result is deterministic, RESEARCH §9), and
        their order is the POLICY, not an implementation detail (SETTLE-3):

        0. :meth:`_try_hold_everything` — every parameter at once. Pure
           performance; when it succeeds it returns what the passes below would
           have returned, in one solve rather than one per entity and point.
        1. **each entity COMPLETELY** — every coordinate *and* its radius. What
           the author drew and where they put it, together.
        2. failing that, **that entity's SHAPE** (:meth:`_shape_pins`) — a
           circle's radius, a line's end-to-end vector, an arc's centre-to-
           endpoint vectors — so it keeps what it IS and moves as a rigid body.
        3. failing that, its **whole points**, both coordinates at once.
           Atomicity matters and is not a micro-optimisation: pinning x and then
           y walks the system through a TANGENTIAL configuration (with ``|e|``
           and ``x`` fixed, ``y`` sits at an extremum of the length constraint),
           where the Jacobian is singular and the coordinate error is the *square
           root* of the residual tolerance. Measured on the R-5b fixture,
           coordinate-at-a-time settling returns to 2.09e-5 mm and
           point-at-a-time to **6.4e-14 mm**.
        4. and last, single coordinates — a corner that must move in x can still
           be held in y.

        **What a settle sacrifices when values compete: the COARSEST hold that
        the constraints will still admit, entity by entity — never "whichever
        pass happened to run last".** There used to be a separate radius pass,
        after the point passes, so a circle whose centre those passes had already
        nailed down lost its radius by arithmetic: the tangent case in
        ``constraints.spec.ts``, where a line 20 mm from an r10 circle was made
        tangent by growing the circle to **r20** and not moving the line at all.
        Running radii FIRST only moves the arbitrariness — measured on the same
        fixture, the line's start point then holds and its far end swings, so a
        line the author drew vertical comes back slanted. Both answers sacrifice
        a quantity the author DREW to keep one the solver exists to DERIVE, and
        neither is a policy; each is a consequence of a pass number.

        The ladder is a policy, and it is SETTLE-2's own finding — *holding a
        SUBSET of a rigid body's points distorts the body; the choice is all of
        them or none* — applied one level down, to the single entity. Rung 2 is
        the rung that was missing: without it, an entity that cannot stay where
        it is has no way to move except by having some of its coordinates pinned
        and the rest dragged, which deforms it. On the tangent fixture rung 1
        holds the circle outright (r10 at the origin), rung 1 refuses the line,
        rung 2 holds its length and direction, and the 10 mm the constraint needs
        comes out of the one quantity the user asked the solver to work out:
        where the line sits. It slides to x = 10.

        **Both orders above were measured, and so was the tempting generalisation
        that rung 2 should come FIRST for every entity ("shape before
        placement").** That one is falsified by R-5b, which is why the ladder is
        per-entity rather than a global precedence: on the coupling profile the
        six free DOF ARE the corner angles, so pinning six line directions and
        six lengths against a closure the edit has changed is infeasible, the
        refusals cascade, and ``e4`` — an edge the edit never named — moves
        **10.285 mm**. The author's placement is achievable there and their
        directions are not; on the tangent fixture it is the other way round. No
        fixed precedence between shape and placement can be right for both, and
        the coarsest-hold-that-fits rule needs no such precedence.

        The pins are internal: the reported DOF is the user's sketch's, taken
        from the pre-settle diagnosis, because their sketch really does still
        have those degrees of freedom.

        Falls back to the unsettled solution on EITHER of two checks, so this
        can never return worse geometry than the plain solve — the guarantee is
        checked, not assumed:

        * every caller constraint is still satisfied, judged by BOTH witnesses
          (:meth:`_constraints_satisfied`), and
        * no entity has been turned round (:func:`_turns_geometry_inside_out`).

        **"No worse than the plain solve" is a relative guarantee and SOLVE-1
        read it as an absolute one.** The plain solve can itself be wrong:
        planegcs returns ``Success`` with an empty conflict list on sketches
        nothing can satisfy, so the baseline this falls back to is not a floor
        (:func:`_violated_constraints`, which is why the payload is checked
        separately from the settle).

        **The second check is not belt-and-braces; constraint satisfaction
        cannot see the failure it catches, and neither can any measure of
        distance from the input.** A sketch with free DOF generally has several
        disconnected branches of solution, every one of them satisfying every
        constraint exactly, so a settle that lands on a DIFFERENT branch from the
        plain solve passes the first check with a clean conscience. Measured on
        the SKETCH-2 datum fixture — a rigid rectangle at y in [8, 24] made
        symmetric about the X axis — the plain solve translates it to y in
        [-8, 8] and settling instead reflected it, holding the two bottom corners
        at their submitted y and sending the two top corners past them. Same
        rectangle in space, opposite traversal: the profile's wire now runs the
        other way, which flips the face normals every downstream feature is
        built on, and a stored topological reference to "the top edge" resolves
        to the bottom one (RESEARCH §9).

        Reaching for a displacement metric here is the obvious move and it does
        not work — measured, both fixtures, four metrics, all four ranking the
        two cases the SAME way, so no threshold on any of them can separate the
        correction from the reflection:

        ==========================  ==============  ==============
        settled vs. plain solve     R-5b (want      SKETCH-2 (want
                                    the settle)     the plain solve)
        ==========================  ==============  ==============
        sum of squared displacement 32.20 vs 20.72  4096 vs 2048
        worst single point          4.01 vs 3.08    32.00 vs 16.01
        points moved at all         2 vs 10         4 vs 8
        sum of displacements        8.024 vs 8.048  128.000 vs 128.002
        REVERSED ENTITIES           **none**        **e2, e4**
        ==========================  ==============  ==============

        The reason is structural rather than bad luck: a least-squares solve is
        already close to the minimum-norm correction, so it always WINS on total
        displacement, while what SOLVE-1 wants is the sparse correction that
        moves the fewest points — and the reflection is sparse too. Only the
        last row tells them apart, and it is the one that names the actual
        defect instead of a symptom of it.
        """
        baseline = self.read_back()
        targets = self._input_points()
        if self._try_hold_everything():
            return self._refinement_or(self.read_back(), baseline)
        deferred: list[tuple[PointId, tuple[float, float]]] = []
        for entity in self.sketch.entities:  # input order — deterministic
            if self._try_hold_placement([entity]):
                continue
            self._try_hold_shape(entity, targets)
            for name, _ in _entity_point_names(entity):
                point_id = self._points.get((entity.id, name))
                target = targets.get((entity.id, name))
                if point_id is None or target is None:
                    continue  # an unreferenced spline fit point
                if not self._try_hold_point(point_id, (0, 1), target):
                    deferred.append((point_id, target))
        for point_id, target in deferred:
            for axis in (0, 1):
                self._try_hold_point(point_id, (axis,), target)
        if not self._constraints_satisfied([]):
            return baseline
        return self._refinement_or(self.read_back(), baseline)

    @staticmethod
    def _refinement_or(
        settled: list[SketchEntity], baseline: list[SketchEntity]
    ) -> list[SketchEntity]:
        """``settled`` unless it re-oriented the geometry rather than refining it.

        Applied to the ``_try_hold_everything`` fast path as well as the
        per-point one — an exempt branch is a branch nobody checks, and here it
        costs a dot product per entity beside a solve.
        """
        if _turns_geometry_inside_out(settled, baseline):
            return baseline
        return settled

    # -- results -------------------------------------------------------------

    def read_back(self) -> list[SketchEntity]:
        """Solved entities, same ids/kinds/order/construction-flag as input.

        The ``construction`` flag is a property of the entity, not a solve
        result, so it is carried through unchanged: construction geometry
        solves like any other entity and stays flagged for the profile builder
        and the UI (dashed/muted rendering).
        """
        solved: list[SketchEntity] = []
        for entity in self.sketch.entities:
            match entity:
                case SketchPoint():
                    x, y = self.gcs.get_point(self._points[(entity.id, "position")])
                    solved.append(
                        SketchPoint(
                            id=entity.id,
                            kind="point",
                            construction=entity.construction,
                            position=Point2D(x=x, y=y),
                        )
                    )
                case SketchLine():
                    info = self.gcs.get_line(self._lines[entity.id])
                    solved.append(
                        SketchLine(
                            id=entity.id,
                            kind="line",
                            construction=entity.construction,
                            start=Point2D(x=info.p1[0], y=info.p1[1]),
                            end=Point2D(x=info.p2[0], y=info.p2[1]),
                        )
                    )
                case SketchCircle():
                    circle = self.gcs.get_circle(self._circles[entity.id])
                    solved.append(
                        SketchCircle(
                            id=entity.id,
                            kind="circle",
                            construction=entity.construction,
                            center=Point2D(x=circle.center[0], y=circle.center[1]),
                            radius=circle.radius,
                        )
                    )
                case SketchArc():
                    arc = self.gcs.get_arc(self._arcs[entity.id])
                    solved.append(
                        SketchArc(
                            id=entity.id,
                            kind="arc",
                            construction=entity.construction,
                            center=Point2D(x=arc.center[0], y=arc.center[1]),
                            start=Point2D(x=arc.start_point[0], y=arc.start_point[1]),
                            end=Point2D(x=arc.end_point[0], y=arc.end_point[1]),
                        )
                    )
                case SketchSpline():
                    # Rebuild the spline THROUGH the solved fit-point positions:
                    # a referenced fit point reads its solved (x, y) back from the
                    # gcs; an unreferenced one keeps its input coordinate. When NO
                    # fit point was referenced the spline never entered the solver,
                    # so it is preserved bitwise (deep copy) — identical to the
                    # pre-v1.1 pass-through (backward compat). The interpolating
                    # curve itself is re-fitted downstream by the kernel
                    # (Edge.make_spline) from these updated fit points.
                    if not any(
                        (entity.id, f"fit{i}") in self._points
                        for i in range(len(entity.points))
                    ):
                        solved.append(entity.model_copy(deep=True))
                        continue
                    fit_points: list[Point2D] = []
                    for index, point in enumerate(entity.points):
                        pid = self._points.get((entity.id, f"fit{index}"))
                        if pid is None:
                            fit_points.append(point.model_copy(deep=True))
                        else:
                            x, y = self.gcs.get_point(pid)
                            fit_points.append(Point2D(x=x, y=y))
                    solved.append(
                        SketchSpline(
                            id=entity.id,
                            kind="spline",
                            construction=entity.construction,
                            points=fit_points,
                        )
                    )
        return solved
