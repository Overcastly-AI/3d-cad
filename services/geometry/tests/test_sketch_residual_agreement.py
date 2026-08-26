"""SETTLE-3 — the settle's safety net gets a second, independent opinion.

``_constraints_satisfied`` was the ONLY thing standing between a settle and
wrong geometry, and it asked one question of one witness: the solver's own
``constraint_error(tag)``, read off the parameter array the solver had just
produced. Two structural reasons that is not enough, both of them in the code
rather than in theory:

* a hold is accepted on ``SolveStatus.Converged``, and in FreeCAD's DogLeg that
  means the iteration STOPPED, not that it found a root — so the residual is the
  whole of the gate, asked of the thing under test;
* the check is scoped to the CALLER's tags, which is correct as far as it goes
  and leaves planegcs's internally-added arc rules (tag ``0``, error ``nan``)
  outside it entirely. Nothing asked whether the arc about to be shipped is
  still an arc.

:mod:`geometry.sketch.residual` is the second opinion, re-derived from the DTO
entities. This suite is its own guard — *a tool that guards commits needs its
own guard* (CLAUDE.md) — because a wrong second opinion is worse than none: both
opinions must hold for a settle to keep a hold, so an over-strict residual
silently reverts the product to its pre-SOLVE-1 behaviour with every gate green.

**Two bugs in the second opinion were found by this suite's method and would
not have been found by the obvious one.** Comparing the two after a converged
solve compares ``0.0`` against ``0.0``; comparing them at the INPUT
configuration, where every residual is large, immediately showed the parallel
residual reading **600** where planegcs read **0.394** (raw mm^2 versus
planegcs's unit-normalised sine) and the circle/circle tangent residual calling
two coincident equal circles a **17.22 mm** violation (planegcs's tangency
admits the INTERNAL branch; ``tangent_circle_circle`` exposes no flag saying so).
"""

import math

from geometry.sketch import (
    AngleConstraint,
    CoincidentConstraint,
    ConcentricConstraint,
    DiameterConstraint,
    DistanceConstraint,
    EntityPointRef,
    EqualConstraint,
    FixedConstraint,
    HorizontalConstraint,
    MidpointConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    PlanegcsSketchSolver,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolver,
    SymmetricConstraint,
    TangentConstraint,
    VerticalConstraint,
)
from geometry.sketch.angles import angle_frames
from geometry.sketch.expression import evaluate_driving_dimensions
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import (
    UNRESOLVABLE,
    constraint_residual,
    entity_residual,
)

SOLVER: SketchSolver = PlanegcsSketchSolver()

#: How much STRICTER the DTO opinion is allowed to be than planegcs's, as a
#: ratio, where both are non-zero. Two departures are deliberate and bounded:
#: a coincidence is the point distance where planegcs reports the RMS of its two
#: component constraints (exactly ``sqrt(2)``), and a curve/curve tangency is
#: linear in mm where planegcs's is quadratic. Anything beyond this is the
#: parallel bug's shape and must fail — a second opinion that rejects on its own
#: authority is a defect, not a safety margin.
MAX_STRICTER_RATIO = math.sqrt(2.0)


def _p(x: float, y: float) -> Point2D:
    return Point2D(x=x, y=y)


def _line(entity_id: str, a: tuple[float, float], b: tuple[float, float]) -> SketchLine:
    return SketchLine(id=entity_id, kind="line", start=_p(*a), end=_p(*b))


def _circle(entity_id: str, c: tuple[float, float], r: float) -> SketchCircle:
    return SketchCircle(id=entity_id, kind="circle", center=_p(*c), radius=r)


def _arc(
    entity_id: str,
    c: tuple[float, float],
    s: tuple[float, float],
    e: tuple[float, float],
) -> SketchArc:
    return SketchArc(id=entity_id, kind="arc", center=_p(*c), start=_p(*s), end=_p(*e))


def _ref(entity_id: str, point: str) -> EntityPointRef:
    return EntityPointRef(entity=entity_id, point=point)


#: One fixture per constraint kind, every one deliberately drawn OFF its
#: solution so both opinions report a large residual and can actually disagree.
OFF_SOLUTION: dict[str, SketchDefinition] = {
    "coincident": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0)), _line("l2", (42, 3), (42, 25))],
        constraints=[
            CoincidentConstraint(
                kind="coincident", a=_ref("l1", "end"), b=_ref("l2", "start")
            )
        ],
    ),
    "horizontal-vertical": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 6)), _line("l2", (0, 0), (5, 25))],
        constraints=[
            HorizontalConstraint(kind="horizontal", entity="l1"),
            VerticalConstraint(kind="vertical", entity="l2"),
        ],
    ),
    "distance-radius": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0)), _circle("c1", (0, 0), 10.0)],
        constraints=[
            DistanceConstraint(kind="distance", entity="l1", value_mm=25.0),
            RadiusConstraint(kind="radius", entity="c1", value_mm=13.0),
        ],
    ),
    # The diameter fixture is deliberately the SAME circle and the SAME miss as
    # the radius one above, doubled: r=10 asked d=26 is r=10 asked r=13. planegcs
    # reports 3.0 for both — its diameter error is on the RADIUS scale — so a
    # residual written in diameter units would read 6.0 here and be exactly 2x
    # stricter than the witness it is checking. That is the parallel bug's shape,
    # and `test_the_second_opinion_is_never_the_stricter_witness` is what catches
    # it: MAX_STRICTER_RATIO is sqrt(2), so a factor of 2 cannot slip through.
    "diameter": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _arc("a1", (30, 0), (37, 0), (30, 7))],
        constraints=[
            DiameterConstraint(kind="diameter", entity="c1", value_mm=26.0),
            DiameterConstraint(kind="diameter", entity="a1", value_mm=30.0),
        ],
    ),
    "fixed": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0))],
        constraints=[FixedConstraint(kind="fixed", point=_ref("l1", "end"))],
    ),
    "parallel-perpendicular": SketchDefinition(
        entities=[
            _line("l1", (0, 0), (40, 0)),
            _line("l2", (0, 12), (35, -3)),
            _line("l3", (10, 5), (35, 25)),
        ],
        constraints=[
            ParallelConstraint(kind="parallel", a="l1", b="l2"),
            PerpendicularConstraint(kind="perpendicular", a="l1", b="l3"),
        ],
    ),
    "tangent-line-circle": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _line("l1", (20, -15), (20, 15))],
        constraints=[TangentConstraint(kind="tangent", a="l1", b="c1")],
    ),
    "tangent-line-arc": SketchDefinition(
        entities=[
            _arc("a1", (0, 0), (10, 0), (0, 10)),
            _line("l1", (20, -15), (20, 15)),
        ],
        constraints=[TangentConstraint(kind="tangent", a="l1", b="a1")],
    ),
    "tangent-circle-circle": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _circle("c2", (35, 0), 12.0)],
        constraints=[TangentConstraint(kind="tangent", a="c1", b="c2")],
    ),
    "tangent-arc-arc": SketchDefinition(
        entities=[
            _arc("a1", (0, 0), (10, 0), (0, 10)),
            _arc("a2", (35, 0), (47, 0), (35, 12)),
        ],
        constraints=[TangentConstraint(kind="tangent", a="a1", b="a2")],
    ),
    "tangent-circle-arc": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _arc("a2", (35, 0), (47, 0), (35, 12))],
        constraints=[TangentConstraint(kind="tangent", a="c1", b="a2")],
    ),
    "equal-lines": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0)), _line("l2", (0, 10), (25, 10))],
        constraints=[EqualConstraint(kind="equal", a="l1", b="l2")],
    ),
    "equal-curves": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _arc("a2", (30, 0), (37, 0), (30, 7))],
        constraints=[EqualConstraint(kind="equal", a="c1", b="a2")],
    ),
    "concentric": SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _arc("a2", (3, 2), (10, 2), (3, 9))],
        constraints=[ConcentricConstraint(kind="concentric", a="c1", b="a2")],
    ),
    # Two angle fixtures, because the convention has two branches. The first
    # pair shares no corner, so the frame is the authored directions; the second
    # meets at a corner, so both legs are re-oriented away from it and the
    # comparison covers the reversal arithmetic that maps the DTO's unsigned
    # number onto planegcs's signed one.
    "angle-free": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0)), _line("l2", (0, 12), (35, -3))],
        constraints=[AngleConstraint(kind="angle", a="l1", b="l2", value_deg=55.0)],
    ),
    "angle-corner": SketchDefinition(
        entities=[_line("l1", (0, 0), (40, 0)), _line("l2", (43, 2), (10, 20))],
        constraints=[
            CoincidentConstraint(
                kind="coincident", a=_ref("l1", "end"), b=_ref("l2", "start")
            ),
            AngleConstraint(kind="angle", a="l1", b="l2", value_deg=110.0),
        ],
    ),
    # Off-solution in BOTH of the midpoint constraint's parts at once: the point
    # is 30 mm clear of the line AND 10 mm past its middle, so neither witness
    # reads zero and the two can actually disagree.
    "midpoint": SketchDefinition(
        entities=[
            _line("l1", (0, 0), (40, 0)),
            SketchPoint(id="p1", kind="point", position=_p(30, 30)),
        ],
        constraints=[
            MidpointConstraint(kind="midpoint", point=_ref("p1", "position"), line="l1")
        ],
    ),
    "symmetric": SketchDefinition(
        entities=[
            _line("axis", (0, 0), (50, 0)),
            SketchPoint(id="p1", kind="point", position=_p(10, 8)),
            SketchPoint(id="p2", kind="point", position=_p(14, -3)),
        ],
        constraints=[
            SymmetricConstraint(
                kind="symmetric",
                a=_ref("p1", "position"),
                b=_ref("p2", "position"),
                line="axis",
            )
        ],
    ),
}


#: The sweep's own counter-example, coordinates verbatim (seed 20260822, trial
#: 89 of 400). ``parallel`` AND ``perpendicular`` between the same two lines,
#: which nothing can satisfy — planegcs solves it to lines 67 degrees apart and
#: reports ``Success`` with no conflict.
#:
#: The exact numbers matter and are not decoration. A tidier hand-written pair
#: (``(0,0)-(40,0)`` against ``(0,12)-(35,-3)``) makes planegcs COLLAPSE the
#: second line to zero length instead, at which point both constraints really
#: are satisfied — by geometry that should not ship either, but that is a
#: separate defect (a degenerate entity) and it would make this test pass for
#: the wrong reason.
IMPOSSIBLE = SketchDefinition(
    entities=[
        _line("e0", (29.28, 15.004), (10.825, -12.636)),
        _line("e1", (38.773, 13.728), (38.483, -23.815)),
    ],
    constraints=[
        ParallelConstraint(kind="parallel", a="e1", b="e0"),
        PerpendicularConstraint(kind="perpendicular", a="e0", b="e1"),
    ],
)


def _both_opinions(
    sketch: SketchDefinition,
) -> list[tuple[str, int, float, float]]:
    """``(kind, index, planegcs residual, DTO residual)`` at the INPUT geometry.

    No solve is run: the constraint system is built and both witnesses are asked
    about the configuration the author submitted, which is the only place the
    two can meaningfully be compared (after a converged solve both read zero).

    The build is given the sketch's DRIVING dimension values rather than an empty
    map, so dimensions are in the system and get compared like every relational
    kind. With an empty map every dimension reads as DRIVEN, is never added, has
    no tag, and silently drops out of the comparison — so ``distance``/``radius``
    had fixtures here that proved nothing, and an ``angle`` would have joined
    them.
    """
    driving = evaluate_driving_dimensions(sketch.constraints)
    build = _GcsBuild(sketch, driving)
    entities = build.read_back()
    by_id = {entity.id: entity for entity in entities}
    inputs = build._input_points()  # pyright: ignore[reportPrivateUsage]
    frames = angle_frames(sketch.constraints, inputs)
    by_index: dict[int, list[int]] = {}
    for tag, index in build.tag_to_index.items():
        by_index.setdefault(index, []).append(tag)
    rows: list[tuple[str, int, float, float]] = []
    for index, tags in sorted(by_index.items()):
        constraint = sketch.constraints[index]
        planegcs = max(abs(build.gcs.solver.constraint_error(tag)) for tag in tags)
        mine = constraint_residual(
            constraint, by_id, inputs, driving.get(index), frames.get(index)
        )
        assert mine is not None, f"{constraint.kind} is in the system but reports None"
        rows.append((constraint.kind, index, planegcs, mine))
    return rows


def test_every_constraint_kind_is_covered_by_a_fixture() -> None:
    """A residual nobody exercises is a residual nobody has checked."""
    covered = {
        kind
        for sketch in OFF_SOLUTION.values()
        for kind in (c.kind for c in sketch.constraints)
    }
    assert covered == {
        "angle",
        "coincident",
        "concentric",
        "diameter",
        "distance",
        "equal",
        "fixed",
        "horizontal",
        "midpoint",
        "parallel",
        "perpendicular",
        "radius",
        "symmetric",
        "tangent",
        "vertical",
    }


#: ``fixed`` cannot be exercised off-solution AT THE INPUT, and not by
#: oversight: ``fix_point`` pins a point to its own PRE-SOLVE coordinate, so the
#: input configuration IS its solution by construction. It is compared after a
#: solve instead, by
#: :func:`test_the_fixed_residual_matches_planegcs_once_the_point_is_dragged`.
NO_INPUT_RESIDUAL = {"fixed"}


def test_the_two_opinions_agree_about_what_counts_as_satisfied() -> None:
    """Same zero set, off-solution — the property that lets them share a tolerance."""
    for name, sketch in OFF_SOLUTION.items():
        for kind, index, planegcs, mine in _both_opinions(sketch):
            assert (planegcs <= SATISFIED_TOL_MM) == (mine <= SATISFIED_TOL_MM), (
                f"{name}[{index}] {kind}: planegcs={planegcs} dto={mine} — the two "
                "witnesses disagree about whether this constraint is satisfied"
            )
            assert kind in NO_INPUT_RESIDUAL or planegcs > SATISFIED_TOL_MM, (
                f"{name}[{index}] {kind} is already satisfied at the input, so this "
                "fixture compares 0.0 against 0.0 and proves nothing — move it off "
                "its solution"
            )


def test_a_fixed_point_cannot_be_dragged_at_all_so_its_residual_is_structural() -> None:
    """Why ``fixed`` is exempt above, established rather than assumed.

    ``fix_point`` pins to genuinely FIXED solver parameters, not to a constraint
    the optimiser can trade away, so no solve can move the point and no fixture
    can put this residual off its solution. Measured on two points pinned 10 mm
    apart and then made coincident: planegcs returns ``Failed``, leaves both
    points exactly where they were, and puts the whole 10 mm on the COINCIDENT
    constraint instead — reported as ``7.0711``, which is ``10 / sqrt(2)`` and
    is the direct evidence for the ``sqrt(2)`` in :data:`MAX_STRICTER_RATIO`
    (planegcs reports the RMS over its two component constraints; this module
    reports the point distance).

    So the ``fixed`` residual is exercised as a formula, on a displaced entity
    built by hand — the only way it can be non-zero.
    """
    sketch = SketchDefinition(
        entities=[
            SketchPoint(id="p1", kind="point", position=_p(0, 0)),
            SketchPoint(id="p2", kind="point", position=_p(10, 0)),
        ],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("p1", "position")),
            FixedConstraint(kind="fixed", point=_ref("p2", "position")),
            CoincidentConstraint(
                kind="coincident", a=_ref("p1", "position"), b=_ref("p2", "position")
            ),
        ],
    )
    build = _GcsBuild(sketch, {})
    assert build.gcs.solve().name == "Failed"
    solved = build.read_back()
    assert [entity.model_dump() for entity in solved] == [
        entity.model_dump() for entity in sketch.entities
    ]
    coincident_tag = next(
        tag for tag, index in build.tag_to_index.items() if index == 2
    )
    reported = abs(build.gcs.solver.constraint_error(coincident_tag))
    mine = constraint_residual(
        sketch.constraints[2], {e.id: e for e in solved}, {}, None
    )
    assert mine is not None
    assert abs(reported - 10.0 / math.sqrt(2.0)) <= SATISFIED_TOL_MM
    assert abs(mine - 10.0) <= SATISFIED_TOL_MM
    assert mine <= reported * MAX_STRICTER_RATIO + SATISFIED_TOL_MM

    displaced: dict[str, SketchEntity] = {
        "p1": SketchPoint(id="p1", kind="point", position=_p(0.25, -0.75))
    }
    assert (
        constraint_residual(
            sketch.constraints[0], displaced, {("p1", "position"): (0.0, 0.0)}, None
        )
        == 0.75
    )


def test_the_second_opinion_is_never_the_stricter_witness() -> None:
    """The direction that matters: it may be blind, it may not be a rejecter.

    This is the assertion the parallel bug tripped — a raw mm^2 cross product
    against planegcs's unit-normalised sine, 1500x too large, with an identical
    zero set so the test above sailed past it.
    """
    for name, sketch in OFF_SOLUTION.items():
        for kind, index, planegcs, mine in _both_opinions(sketch):
            assert mine <= planegcs * MAX_STRICTER_RATIO, (
                f"{name}[{index}] {kind}: dto={mine} is {mine / planegcs:.1f}x "
                f"planegcs={planegcs}. A second opinion that refuses holds the "
                "solver accepts silently disables the settle."
            )


def test_two_coincident_equal_circles_are_tangent_not_a_17mm_violation() -> None:
    """planegcs's curve/curve tangency admits the INTERNAL branch. Measured.

    Nothing in ``tangent_circle_circle``'s name or signature says so, and an
    external-only residual (``|d - (r1 + r2)|``) therefore calls this settled
    answer — one circle, at the origin — a 17.22 mm violation, refuses every
    hold, and reverts the settle. Found by a randomised sweep that reported five
    "holes" in the solver's check, all five of them this bug.
    """
    sketch = SketchDefinition(
        entities=[_circle("c1", (0, 0), 10.0), _circle("c2", (30, 0), 4.0)],
        constraints=[
            TangentConstraint(kind="tangent", a="c1", b="c2"),
            CoincidentConstraint(
                kind="coincident", a=_ref("c1", "center"), b=_ref("c2", "center")
            ),
        ],
    )
    solved = SOLVER.solve(sketch)
    by_id: dict[str, SketchEntity] = {entity.id: entity for entity in solved.entities}
    residual = constraint_residual(sketch.constraints[0], by_id, {}, None)
    assert residual is not None
    assert residual <= SATISFIED_TOL_MM
    assert solved.status == "underconstrained"


def test_the_solver_check_never_asks_whether_an_arc_is_still_an_arc() -> None:
    """The scope gap, stated as an executable fact about the code.

    An arc's ``start``/``end`` points are solver parameters distinct from its
    ``center``/``radius``/angles, tied to them ONLY by the rules ``add_arc_cse``
    adds under tag ``0`` — and ``_solver_says_satisfied`` iterates
    ``tag_to_index``, which contains no entry for tag ``0``, whose error is
    ``nan`` anyway. So the question "do this arc's two endpoints still agree
    about their own centre" has no witness on the solver side at all;
    :func:`entity_residual` is the only thing that asks it, and an arc that
    fails it is a curve no kernel can build.
    """
    sketch = SketchDefinition(
        entities=[_arc("a1", (0, 0), (10, 0), (0, 10))],
        constraints=[RadiusConstraint(kind="radius", entity="a1", value_mm=12.0)],
    )
    build = _GcsBuild(sketch, {0: 12.0})
    assert 0 not in build.tag_to_index, "tag 0 is planegcs's, never a caller's"
    assert math.isnan(build.gcs.solver.constraint_error(0))

    well_formed = _arc("a1", (0, 0), (10, 0), (0, 10))
    assert entity_residual(well_formed) == 0.0
    ill_formed = _arc("a1", (0, 0), (10, 0), (0, 14))
    assert entity_residual(ill_formed) == 4.0


def test_an_unresolvable_reference_is_refused_not_excused() -> None:
    """Every reference resolved when the system was built, so one that does not
    resolve now means the two views disagree about the sketch."""
    constraint = HorizontalConstraint(kind="horizontal", entity="gone")
    assert constraint_residual(constraint, {}, {}, None) == UNRESOLVABLE
    assert UNRESOLVABLE > SATISFIED_TOL_MM


def test_planegcs_calls_an_impossible_sketch_SOLVED() -> None:
    """The evidence for the payload gate, kept executable.

    ``parallel`` and ``perpendicular`` between the same two lines cannot both
    hold, and planegcs reports ``Success`` with an EMPTY conflict list. This
    test asserts that trap still exists; if planegcs ever learns to diagnose it,
    this fails and the gate below can be reconsidered rather than carried
    forever on a stale premise.
    """
    build = _GcsBuild(IMPOSSIBLE, {})
    assert build.gcs.solve().name == "Success"
    assert build.gcs.diagnose().conflicting == []
    assert build.gcs.diagnose().dof == 6  # and it calls the sketch merely loose


def test_a_solve_never_ships_geometry_its_own_constraints_contradict() -> None:
    """The payload gate: relational constraints are verified, not assumed.

    SOLVE-1 verified DRIVING DIMENSIONS against the solved geometry before
    reporting them, on the principle that a payload may not report a number the
    geometry beside it contradicts. The narrowness was the defect: a relational
    constraint is no less load-bearing for having no readout. On the pushed
    bytes this sketch came back ``underconstrained`` with its two lines 67
    degrees apart and nothing in the payload saying so — 7 of the 155 solvable
    sketches in a 400-sketch randomised sweep shipped a violated constraint the
    same way.
    """
    solved = SOLVER.solve(IMPOSSIBLE)
    assert solved.status == "conflicting"
    assert solved.conflicting_constraints == [0, 1]
    # A conflicting solve returns the input untouched — never a compromise.
    assert [entity.model_dump() for entity in solved.entities] == [
        entity.model_dump() for entity in IMPOSSIBLE.entities
    ]
