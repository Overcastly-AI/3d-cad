"""SETTLE-3 — what a settle sacrifices when the author's values compete.

A settle pins the author's input back onto an under-constrained solve (SOLVE-1).
When the constraints cannot admit all of it, something has to give, and until
this suite the answer was an accident of pass ORDER: circle radii were pinned in
a pass that ran AFTER the coordinate passes, so a circle whose centre those
passes had already nailed down lost its radius by arithmetic.

The case is the one ``apps/web/e2e/constraints.spec.ts`` calls *"line + circle
tangent: the line slides in to touch the circle"* — an r10 circle at the origin
and a vertical line 20 mm away, made tangent. Three answers, all of which solve
the constraint exactly:

======================  ==========  ===================  ====================
answer                  circle      line                 verdict
======================  ==========  ===================  ====================
radii pinned LAST       **r20**     never moves          shipped before this
radii pinned FIRST      r10         **pivots** about     the obvious fix; a
                                    its start corner     vertical line comes
                                                         back slanted
per-entity ladder       r10 at the  slides to x = 10,    what a modelling tool
                        origin      same length and      does
                                    direction
======================  ==========  ===================  ====================

The first two are not two bugs, they are the same bug twice: each sacrifices a
quantity the author DREW to keep one the solver exists to DERIVE, and which one
loses is decided by a pass number. The ladder decides it by policy instead —
per entity, take the coarsest hold the constraints still admit — and the 10 mm
comes out of the only quantity the user asked the solver to work out.

**Tolerance:** every assertion is bounded by
:data:`~geometry.sketch.planegcs_solver.SATISFIED_TOL_MM`, imported rather than
restated (RESEARCH §9 — derived, never ad hoc). The one exception is the
"visibly moved" assertions, which use whole millimetres because they are
statements about a 10 mm displacement, not about numerical error.
"""

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import pytest
from geometry.sketch import (
    PlanegcsSketchSolver,
    Point2D,
    SketchCircle,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    SolvedSketch,
    TangentConstraint,
)
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)

SOLVER: SketchSolver = PlanegcsSketchSolver()

#: The e2e fixture, in sketch millimetres: an r10 circle at the origin and a
#: vertical line at x = 20 running from y = -15 to y = +15 — a 10 mm gap.
CIRCLE_RADIUS_MM = 10.0
LINE_X_MM = 20.0
LINE_HALF_LENGTH_MM = 15.0


def tangent_fixture() -> SketchDefinition:
    return SketchDefinition(
        entities=[
            SketchCircle(
                id="e1",
                kind="circle",
                center=Point2D(x=0.0, y=0.0),
                radius=CIRCLE_RADIUS_MM,
            ),
            SketchLine(
                id="e2",
                kind="line",
                start=Point2D(x=LINE_X_MM, y=-LINE_HALF_LENGTH_MM),
                end=Point2D(x=LINE_X_MM, y=LINE_HALF_LENGTH_MM),
            ),
        ],
        constraints=[TangentConstraint(kind="tangent", a="e2", b="e1")],
    )


def _circle(solved: SolvedSketch) -> SketchCircle:
    entity = next(e for e in solved.entities if e.id == "e1")
    assert isinstance(entity, SketchCircle)
    return entity


def _line(solved: SolvedSketch) -> SketchLine:
    entity = next(e for e in solved.entities if e.id == "e2")
    assert isinstance(entity, SketchLine)
    return entity


def _centre_to_line_gap(circle: SketchCircle, line: SketchLine) -> float:
    dx, dy = line.end.x - line.start.x, line.end.y - line.start.y
    return abs(
        (circle.center.x - line.start.x) * dy - (circle.center.y - line.start.y) * dx
    ) / math.hypot(dx, dy)


def _solve_1_fixtures() -> ModuleType:
    """The SOLVE-1 suite's coupling profile, imported by PATH.

    ``pyproject.toml`` sets ``--import-mode=importlib``, so sibling test modules
    are not importable by name; the orientation suite loads it the same way, and
    re-declaring the audit's profile here is exactly the duplicate that drifts.
    """
    name = "test_sketch_free_dof_hold"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(f"{name}.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def solved() -> SolvedSketch:
    return SOLVER.solve(tangent_fixture())


def test_the_constraint_is_actually_satisfied(solved: SolvedSketch) -> None:
    """Whatever a settle sacrifices, the tangency itself is non-negotiable."""
    assert solved.status == "underconstrained"
    circle, line = _circle(solved), _line(solved)
    assert abs(_centre_to_line_gap(circle, line) - circle.radius) <= SATISFIED_TOL_MM


def test_the_circle_keeps_the_size_the_author_drew(solved: SolvedSketch) -> None:
    """r10 stays r10. On the bytes before SETTLE-3 it came back **r20**.

    The radius pass ran last, so by the time it was reached the line's four
    coordinates were already pinned and the only parameter left free to absorb
    the 10 mm gap was the circle's size.
    """
    assert abs(_circle(solved).radius - CIRCLE_RADIUS_MM) <= SATISFIED_TOL_MM


def test_the_circle_keeps_the_place_the_author_drew_it(solved: SolvedSketch) -> None:
    circle = _circle(solved)
    assert abs(circle.center.x) <= SATISFIED_TOL_MM
    assert abs(circle.center.y) <= SATISFIED_TOL_MM


def test_the_line_slides_in_to_touch_the_circle(solved: SolvedSketch) -> None:
    """The line is what moves — and it moves, which is the e2e spec's assertion.

    ``constraints.spec.ts`` checks ``|line.start.x - 20| > 1``. Before SETTLE-3
    that read exactly ``20`` (the line never moved and the circle grew); with
    radii pinned FIRST instead it also reads exactly ``20``, because the line
    pivots about its start corner. Both spellings of the bug are excluded here
    by asserting the arrival, not merely the departure.
    """
    line = _line(solved)
    assert abs(line.start.x - CIRCLE_RADIUS_MM) <= SATISFIED_TOL_MM
    assert abs(line.end.x - CIRCLE_RADIUS_MM) <= SATISFIED_TOL_MM


def test_the_line_keeps_its_length_and_its_direction(solved: SolvedSketch) -> None:
    """A vertical line the author drew comes back vertical, and 30 mm long.

    This is the assertion that rejects the radii-pinned-FIRST answer, which is
    otherwise respectable: r10 kept, tangency exact, the line's start corner
    held at the author's ``(20, -15)``. It rotates the line by 29.6 degrees to
    get there, and nothing the author did asked for that.
    """
    line = _line(solved)
    assert abs(line.end.x - line.start.x) <= SATISFIED_TOL_MM  # still vertical
    assert (
        abs(math.hypot(line.end.x - line.start.x, line.end.y - line.start.y) - 30.0)
        <= SATISFIED_TOL_MM
    )
    assert abs(line.start.y + LINE_HALF_LENGTH_MM) <= SATISFIED_TOL_MM
    assert abs(line.end.y - LINE_HALF_LENGTH_MM) <= SATISFIED_TOL_MM


def test_settling_the_tangent_is_bitwise_deterministic_over_a_SEQUENCE() -> None:
    """RESEARCH §9, at sequence level: feed each solve's output back in.

    A per-solve assertion would miss drift that only accumulates across an edit
    history, and the settle's per-entity ladder is exactly the kind of pass that
    could introduce it — the rungs are tried in input entity order for this
    reason.
    """

    def walk() -> list[list[SketchEntity]]:
        sketch = tangent_fixture()
        trail: list[list[SketchEntity]] = []
        for _ in range(4):
            result = PlanegcsSketchSolver().solve(sketch)
            trail.append(result.entities)
            sketch = SketchDefinition(
                entities=result.entities, constraints=sketch.constraints
            )
        return trail

    first, second = walk(), walk()
    assert [e.model_dump() for step in first for e in step] == [
        e.model_dump() for step in second for e in step
    ]


def test_the_answer_is_stable_under_the_products_feedback_loop() -> None:
    """``PartPage`` adopts solved positions back into the sketch — re-solving
    them must be a no-op, or every rebuild walks the geometry somewhere new."""
    once = SOLVER.solve(tangent_fixture())
    twice = SOLVER.solve(
        SketchDefinition(
            entities=once.entities, constraints=tangent_fixture().constraints
        )
    )
    assert [e.model_dump() for e in twice.entities] == [
        e.model_dump() for e in once.entities
    ]


def test_the_shape_rung_refuses_to_move_an_entity_it_does_not_name() -> None:
    """The condition on rung 2, with the regression it prevents, measured.

    A shape pin constrains a RELATIONSHIP, so unlike a coordinate pin the system
    can satisfy it by shoving whatever is attached to the entity somewhere else
    — and "does it still solve" cannot see the difference. On the R-5b coupling
    that is not hypothetical: pinning ``e3``'s direction inside a closed
    six-edge chain whose free DOF ARE the corner angles makes three edges the
    edit never named move **10.285 mm**.

    The negative control is the point of the test: with
    ``_drift_of_everything_else`` stubbed to ``0.0`` the guard cannot fire, and
    the regression reappears at full size. Asserting only the good case would
    pass just as happily with the guard deleted.
    """
    fixtures = _solve_1_fixtures()

    def furthest_unnamed_edge_moves() -> float:
        baseline = SOLVER.solve(fixtures.coupling_profile(fixtures.DIMENSIONS))
        edited = list(fixtures.DIMENSIONS)
        edited[fixtures.EDITED_EDGE] = fixtures.EDITED_VALUE_MM
        solved = SOLVER.solve(
            fixtures.coupling_profile(edited, entities=baseline.entities)
        )
        before = {e.id: e for e in baseline.entities}
        worst = 0.0
        for entity in solved.entities:
            if entity.id in ("e2", "e3"):  # the edited edge and its shared corner
                continue
            was = before[entity.id]
            assert isinstance(entity, SketchLine) and isinstance(was, SketchLine)
            worst = max(
                worst,
                abs(entity.start.x - was.start.x),
                abs(entity.start.y - was.start.y),
                abs(entity.end.x - was.end.x),
                abs(entity.end.y - was.end.y),
            )
        return worst

    assert furthest_unnamed_edge_moves() <= SATISFIED_TOL_MM

    guard = _GcsBuild._drift_of_everything_else  # pyright: ignore[reportPrivateUsage]
    _GcsBuild._drift_of_everything_else = lambda self, entity_id, targets: 0.0  # type: ignore[assignment,method-assign]
    try:
        unguarded = furthest_unnamed_edge_moves()
    finally:
        _GcsBuild._drift_of_everything_else = guard  # type: ignore[method-assign]
    assert unguarded > 10.0, (
        "the negative control did not reproduce: with the guard disabled the "
        f"coupling's unnamed edges moved {unguarded} mm, expected ~10.285"
    )


def test_the_shape_rung_still_fires_where_it_costs_nobody_anything() -> None:
    """The other half of the control: the guard must not disable the rung.

    On the tangent fixture the circle is held complete first, so pinning the
    line's end-to-end vector moves nobody — and that is the rung that produces
    the slide. Break it and the line pivots.
    """
    sketch = tangent_fixture()
    build = _GcsBuild(sketch, {})
    build.gcs.solve()
    targets = build._input_points()  # pyright: ignore[reportPrivateUsage]
    assert build._try_hold_placement([sketch.entities[0]]) is True  # pyright: ignore[reportPrivateUsage]
    assert build._try_hold_placement([sketch.entities[1]]) is False  # pyright: ignore[reportPrivateUsage]
    assert build._try_hold_shape(sketch.entities[1], targets) is True  # pyright: ignore[reportPrivateUsage]
