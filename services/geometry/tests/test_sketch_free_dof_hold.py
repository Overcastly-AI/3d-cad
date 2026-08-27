"""SOLVE-1 — an under-constrained solve HOLDS the input geometry.

Regression suite for the product audit's R-5 / R-5b / R-5c (P0, wrong
geometry), reproduced here as a *kernel* test on the exact profile the auditor
drew: the flanged shaft coupling of ``docs/AUDIT-PRODUCT.md`` pass 2026-08-21,
six lines, six inferred coincident corners, six typed driving dimensions
(27 / 8 / 21 / 22 / 6 / 30) and — as the web sketcher actually authors a
line-by-line profile — **no horizontal/vertical constraints**, which is why the
auditor's status line read ``DOF 6``.

**The defect was not a conflict.** A hexagon with those six side lengths closes
perfectly well once the corners are free to change angle, so the audit's
``8 -> 12`` edit has a solution and the solver is right to accept it. What was
wrong is WHICH solution: planegcs's DogLeg walks a trajectory from the input
positions, so slack the edit merely *created* was spent moving geometry the
edit never named. Measured on the original bytes, with the product's own
feedback loop (``PartPage`` adopts the solved positions back into the store, so
the next solve starts from the previous solve's output):

===========================  ================  ==========================
reading                      before SOLVE-1    after SOLVE-1
===========================  ================  ==========================
bbox after ``8 -> 12``       y[-3.0795, 30]    y[0, 30]
revolved solid               70 x 70 x 33.079  70 x 70 x 30
entities moved by the edit   all six           e2 + e3 (their shared corner)
bbox after retyping ``8``    69.8106 x 32.162  70 x 30
deviation from the original  **2.162284 mm**   **6.39e-14 mm**
===========================  ================  ==========================

Those "before" figures are the audit's own to three decimals ("70 x 70 x 33.08,
Min z -3.08"; "69.81 x 69.81 x 32.16"), reproduced from the DTOs with no
browser in the loop.

**Tolerance (RESEARCH §9 — derived, never ad hoc).** Every assertion below is
bounded by :data:`~geometry.sketch.planegcs_solver.SATISFIED_TOL_MM`, imported
rather than restated. That constant is the residual at which the solver itself
calls a constraint satisfied, and it is the RIGHT bound here rather than a
coincidence of scale: a coordinate hold is added as a ``coordinate_x`` /
``coordinate_y`` equality against a fixed parameter, so the constraint's
residual IS the coordinate's error in millimetres, one for one, and a hold that
``settle`` accepted therefore cannot have left a coordinate further than
``SATISFIED_TOL_MM`` from the author's value. The observed margin is seven
orders wider than needed (6.4e-14 mm against 1e-7 mm), and 1e-7 mm still sits
three orders under the kernel linear tolerance (1e-7 m = 1e-4 mm), so nothing
this suite passes can carry a kernel-relevant error.
"""

import pytest
from geometry.sketch import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    VerticalConstraint,
)
from geometry.sketch.planegcs_solver import SATISFIED_TOL_MM
from py_kit.schemas.sketch import classify_overconstraint

SOLVER: SketchSolver = PlanegcsSketchSolver()

#: The audit's profile, in sketch coordinates: revolve axis at x = 0, bore
#: radius 8 (Ø16), flange OD radius 35 (Ø70), hub OD radius 14 (Ø28), flange
#: 8 thick, overall 30 tall. Consistent by construction — 21 + 6 = 27 across
#: and 8 + 22 = 30 up — which is what makes the ``8 -> 12`` edit interesting.
CORNERS: list[tuple[float, float]] = [
    (8.0, 0.0),
    (35.0, 0.0),
    (35.0, 8.0),
    (14.0, 8.0),
    (14.0, 30.0),
    (8.0, 30.0),
]

#: Driving dimension per edge, ``e1``..``e6``, in the auditor's order.
DIMENSIONS: list[float] = [27.0, 8.0, 21.0, 22.0, 6.0, 30.0]

#: The edited edge (the flange thickness the auditor thickened) and its new
#: value. ``e2`` runs from the flange OD corner up; ``12 + 22 = 34`` against the
#: ``30`` that spans them, which is the arithmetic the audit called a conflict.
EDITED_EDGE = 1
EDITED_VALUE_MM = 12.0

#: R-5c's second edit: the flange's bottom edge, ``27 -> 25``.
SHORTENED_EDGE = 0
SHORTENED_VALUE_MM = 25.0


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def coupling_profile(
    dimensions: list[float],
    *,
    axis_aligned: bool = False,
    entities: list[SketchEntity] | None = None,
) -> SketchDefinition:
    """The audit's coupling profile.

    ``entities`` replays the product's feedback loop: ``PartPage`` adopts the
    solved positions back into the sketch store, so a dimension edit is solved
    from the PREVIOUS solve's output, not from the coordinates the author first
    drew. That loop is what makes the result a function of solve history, and
    passing the geometry forward is the only way to reproduce it here.

    ``axis_aligned`` adds the horizontal/vertical constraints the web sketcher
    does NOT infer for a line-by-line profile (only rectangles and snapped
    corners author constraints today — ``apps/web/src/sketch/store.ts``). With
    them the same edit is a genuine contradiction; without them it is not.
    """
    if entities is None:
        drawn: list[SketchEntity] = [
            SketchLine(
                id=f"e{index + 1}",
                kind="line",
                start=Point2D(x=CORNERS[index][0], y=CORNERS[index][1]),
                end=Point2D(
                    x=CORNERS[(index + 1) % 6][0], y=CORNERS[(index + 1) % 6][1]
                ),
            )
            for index in range(6)
        ]
    else:
        drawn = [entity.model_copy(deep=True) for entity in entities]

    constraints: list[SketchConstraint] = [
        CoincidentConstraint(
            kind="coincident",
            a=_ref(f"e{index + 1}", "end"),
            b=_ref(f"e{((index + 1) % 6) + 1}", "start"),
        )
        for index in range(6)
    ]
    if axis_aligned:
        constraints += [
            HorizontalConstraint(kind="horizontal", entity=f"e{index + 1}")
            if index % 2 == 0
            else VerticalConstraint(kind="vertical", entity=f"e{index + 1}")
            for index in range(6)
        ]
    constraints += [
        DistanceConstraint(kind="distance", entity=f"e{index + 1}", value_mm=value)
        for index, value in enumerate(dimensions)
    ]
    return SketchDefinition(entities=drawn, constraints=constraints)


def _lines(entities: list[SketchEntity]) -> dict[str, SketchLine]:
    lines: dict[str, SketchLine] = {}
    for entity in entities:
        assert isinstance(entity, SketchLine), "this profile is all lines"
        lines[entity.id] = entity
    return lines


def _coordinates(entities: list[SketchEntity]) -> list[float]:
    """Every coordinate, flattened in input order — for bitwise comparison."""
    flat: list[float] = []
    for line in _lines(entities).values():
        flat += [line.start.x, line.start.y, line.end.x, line.end.y]
    return flat


def _max_deviation(a: list[SketchEntity], b: list[SketchEntity]) -> float:
    return max(
        abs(x - y) for x, y in zip(_coordinates(a), _coordinates(b), strict=True)
    )


def _entity_movement(a: list[SketchEntity], b: list[SketchEntity]) -> dict[str, float]:
    """Per-entity largest coordinate move between two solves."""
    before, after = _lines(a), _lines(b)
    return {
        eid: max(
            abs(before[eid].start.x - after[eid].start.x),
            abs(before[eid].start.y - after[eid].start.y),
            abs(before[eid].end.x - after[eid].end.x),
            abs(before[eid].end.y - after[eid].end.y),
        )
        for eid in before
    }


def _bounds(entities: list[SketchEntity]) -> tuple[float, float, float, float]:
    """``(min x, max x, min y, max y)`` — the revolved solid's radius and height."""
    xs = [c for line in _lines(entities).values() for c in (line.start.x, line.end.x)]
    ys = [c for line in _lines(entities).values() for c in (line.start.y, line.end.y)]
    return min(xs), max(xs), min(ys), max(ys)


def _length(line: SketchLine) -> float:
    return ((line.end.x - line.start.x) ** 2 + (line.end.y - line.start.y) ** 2) ** 0.5


def test_the_drawn_profile_solves_to_the_authored_coupling() -> None:
    """Baseline: the profile as drawn is under-constrained and unmoved.

    DOF 6 is the auditor's own reading of the status line, so this also pins
    the fixture to the sketch that produced the finding rather than to some
    other six-sided profile.
    """
    solved = SOLVER.solve(coupling_profile(DIMENSIONS))

    assert solved.status == "underconstrained"
    assert solved.dof == 6
    assert solved.conflicting_constraints == []
    min_x, max_x, min_y, max_y = _bounds(solved.entities)
    assert min_x == pytest.approx(8.0, abs=SATISFIED_TOL_MM)  # bore Ø16
    assert max_x == pytest.approx(35.0, abs=SATISFIED_TOL_MM)  # flange Ø70
    assert min_y == pytest.approx(0.0, abs=SATISFIED_TOL_MM)
    assert max_y == pytest.approx(30.0, abs=SATISFIED_TOL_MM)


def test_dimension_edit_moves_only_the_geometry_it_names() -> None:
    """R-5: thickening the flange 8 -> 12 moves ONE corner, not the profile.

    The corner shared by ``e2.end`` and ``e3.start`` is the only thing the edit
    names, so it is the only thing allowed to move; the other four edges — and
    in particular the flange OD and the bore, which nothing in this edit
    mentions — must come back where the author put them.

    On the original bytes every edge moved (up to 3.079 mm) and the profile
    slid to ``y[-3.0795, 30]``: the audit's "70 x 70 x 33.08 mm, Min z -3.08".
    """
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS))
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM

    solved = SOLVER.solve(coupling_profile(edited, entities=baseline.entities))
    assert solved.status == "underconstrained"

    movement = _entity_movement(baseline.entities, solved.entities)
    # The named edge and the edge sharing its far corner move; nothing else.
    for eid in ("e1", "e4", "e5", "e6"):
        assert movement[eid] <= SATISFIED_TOL_MM, (
            f"{eid} moved {movement[eid]} mm for an edit that never named it"
        )
    # …and the edit is not a no-op: the corner really does travel ~4 mm.
    assert movement["e2"] > 1.0
    assert movement["e2"] == pytest.approx(movement["e3"], abs=SATISFIED_TOL_MM)

    lines = _lines(solved.entities)
    assert _length(lines["e2"]) == pytest.approx(EDITED_VALUE_MM, abs=SATISFIED_TOL_MM)
    # e2's own start (the flange OD corner at the bottom) is not "its" corner
    # to spend either — only the end the dimension grew towards.
    assert lines["e2"].start.x == pytest.approx(35.0, abs=SATISFIED_TOL_MM)
    assert lines["e2"].start.y == pytest.approx(0.0, abs=SATISFIED_TOL_MM)


def test_dimension_edit_does_not_slide_the_profile_below_its_origin() -> None:
    """R-5: the revolved solid stayed 70 x 70 x 30 and sat on z = 0.

    Split from the movement assertion above deliberately: this is the reading a
    user takes off the part (a bounding box), and it is the one the audit
    published. On the original bytes it was ``70 x 70 x 33.0795`` with the
    bottom 3.0795 mm below the plane the profile was drawn on.
    """
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS))
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM

    solved = SOLVER.solve(coupling_profile(edited, entities=baseline.entities))

    min_x, max_x, min_y, max_y = _bounds(solved.entities)
    assert min_y == pytest.approx(0.0, abs=SATISFIED_TOL_MM)
    assert max_y == pytest.approx(30.0, abs=SATISFIED_TOL_MM)
    assert max_x == pytest.approx(35.0, abs=SATISFIED_TOL_MM)  # Ø70 flange OD
    assert min_x == pytest.approx(8.0, abs=SATISFIED_TOL_MM)  # Ø16 bore


def test_retyping_the_original_dimension_restores_the_original_geometry() -> None:
    """R-5b: 8 -> 12 -> 8 returns the profile, coordinate for coordinate.

    This is the property that made R-5 a P0 rather than an annoyance: an
    engineer who mistypes a dimension and corrects it must get their part back.
    On the original bytes the round trip landed **2.162284 mm** away — a flange
    at Ø69.81 under dimensions that say Ø70, sitting 2.16 mm below its own
    origin plane. Measured here at 6.4e-14 mm.
    """
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS))
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM

    after_edit = SOLVER.solve(coupling_profile(edited, entities=baseline.entities))
    restored = SOLVER.solve(coupling_profile(DIMENSIONS, entities=after_edit.entities))

    assert restored.status == "underconstrained"
    assert _max_deviation(baseline.entities, restored.entities) <= SATISFIED_TOL_MM


def test_edit_does_not_change_a_dimension_it_never_named() -> None:
    """R-5c: shortening the flange bottom edge leaves the BORE alone.

    The audit's second instance, and the sharper one: editing ``27 -> 25``
    changed the shaft bore by 2.24 mm (Ø16 -> Ø18.24) — the one dimension on a
    coupling that must not move — while the geometry the edit named did not
    change at all. Both halves are asserted: the bore and the OD hold, and the
    named edge actually reaches 25 mm.
    """
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS))
    shortened = list(DIMENSIONS)
    shortened[SHORTENED_EDGE] = SHORTENED_VALUE_MM

    solved = SOLVER.solve(coupling_profile(shortened, entities=baseline.entities))

    lines = _lines(solved.entities)
    assert _length(lines["e1"]) == pytest.approx(
        SHORTENED_VALUE_MM, abs=SATISFIED_TOL_MM
    )
    # e6 IS the bore wall; e3/e4/e5 carry the hub and the flange OD corner.
    movement = _entity_movement(baseline.entities, solved.entities)
    for eid in ("e3", "e4", "e5", "e6"):
        assert movement[eid] <= SATISFIED_TOL_MM, (
            f"{eid} moved {movement[eid]} mm for an edit that never named it"
        )
    min_x, max_x, _, _ = _bounds(solved.entities)
    assert min_x == pytest.approx(8.0, abs=SATISFIED_TOL_MM)  # bore still Ø16
    assert max_x == pytest.approx(35.0, abs=SATISFIED_TOL_MM)  # OD still Ø70


def test_holding_the_free_dof_is_bitwise_deterministic() -> None:
    """RESEARCH §9: settling adds solver passes, and adds no nondeterminism.

    Bitwise (``==``), no tolerance — determinism takes none. Exercised over the
    whole edit sequence, not just one solve, because the passes run in input
    entity order precisely so that a sequence of them stays reproducible; a
    fresh backend instance is used for the second run so no solver state can
    carry between them.
    """
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM

    def sequence(solver: SketchSolver) -> list[list[float]]:
        baseline = solver.solve(coupling_profile(DIMENSIONS))
        after = solver.solve(coupling_profile(edited, entities=baseline.entities))
        restored = solver.solve(coupling_profile(DIMENSIONS, entities=after.entities))
        return [_coordinates(s.entities) for s in (baseline, after, restored)]

    assert sequence(SOLVER) == sequence(PlanegcsSketchSolver())


def test_a_genuine_conflict_is_still_diagnosed_on_a_value_edit() -> None:
    """The same edit on an axis-aligned profile is REFUSED, through the one
    existing diagnosis (BACKLOG #6) — holding the free DOF did not soften it.

    Add the horizontal/vertical constraints and ``12 + 22 = 34`` really cannot
    coexist with the ``30`` spanning them: there is no solution, so the solver
    reports ``conflicting`` with the offending constraint indices, returns the
    input geometry untouched, and ``classify_overconstraint`` — the SAME typed
    diagnosis a newly-ADDED constraint produces, not a second one written for
    value edits — carries it to the caller as ``sketch_conflicting``.
    """
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS, axis_aligned=True))
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM

    solved = SOLVER.solve(
        coupling_profile(edited, axis_aligned=True, entities=baseline.entities)
    )

    assert solved.status == "conflicting"
    assert solved.conflicting_constraints != []
    # Refused, not absorbed: the geometry is exactly what went in.
    assert _coordinates(solved.entities) == _coordinates(baseline.entities)

    diagnosis = classify_overconstraint(solved)
    assert diagnosis is not None
    assert diagnosis.classification == "conflicting"
    assert diagnosis.removable is False
    assert diagnosis.conflicting_constraints == solved.conflicting_constraints
    assert diagnosis.suggested_fix is not None


def test_no_dimension_readout_contradicts_the_geometry_beside_it() -> None:
    """A payload may not report a number the entities in it do not have.

    The invariant :func:`~geometry.sketch.planegcs_solver._dimension_readouts`
    documents, asserted end to end over every solve in this file's scenario:
    each readout is re-measured from the entities shipped with it. The refused
    edit is the case that matters — there the request is 12 and the geometry is
    the untouched 8, and the readout must say 8.
    """
    edited = list(DIMENSIONS)
    edited[EDITED_EDGE] = EDITED_VALUE_MM
    baseline = SOLVER.solve(coupling_profile(DIMENSIONS))
    cases = [
        SOLVER.solve(coupling_profile(edited, entities=baseline.entities)),
        SOLVER.solve(coupling_profile(DIMENSIONS, axis_aligned=True)),
        SOLVER.solve(
            coupling_profile(
                edited,
                axis_aligned=True,
                entities=SOLVER.solve(
                    coupling_profile(DIMENSIONS, axis_aligned=True)
                ).entities,
            )
        ),
    ]
    for solved in cases:
        lines = _lines(solved.entities)
        # The dimension constraints are the tail of the constraint list, one
        # per edge in ``e1``..``e6`` order, so readout N describes edge N+1.
        assert len(solved.dimensions) == len(lines)
        for index, readout in enumerate(solved.dimensions):
            measured = _length(lines[f"e{index + 1}"])
            assert readout.value_mm == pytest.approx(measured, abs=SATISFIED_TOL_MM), (
                f"readout {readout.constraint_index} says {readout.value_mm} mm "
                f"beside geometry measuring {measured} mm"
            )
