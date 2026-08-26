"""SYMMETRIC accepting two LINES and an axis — the selection made first.

SKETCH-VOCAB-1 / docs/AUDIT-PRODUCT.md T-5: ``symmetric`` took only *two points
and a line*, and refused two parallel edges plus a centreline with "Select two
points and a line" — which is what an engineer selects first and what SolidWorks
and Onshape both accept.

The acceptance criterion is a comparison, not an absolute: the line form must
produce **the same result as the existing two-points-and-a-line path on an
equivalent fixture**, and that is asserted BITWISE here — the line form is wired
from the same planegcs primitive, so anything else would mean it takes a
different route through the solver.

Tolerance: ``SYMMETRY_TOLERANCE_MM = 1e-9`` mm, the sketch suite's documented
bound for a well-conditioned solve. The equivalence assertions take none at all.
"""

import pytest
from geometry.sketch import (
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchLine,
    SketchSolver,
    SolvedSketch,
    SymmetricConstraint,
    SymmetricLinesConstraint,
    VerticalConstraint,
)
from geometry.sketch.residual import symmetric_lines_crossed

SYMMETRY_TOLERANCE_MM = 1e-9

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> SketchLine:
    return SketchLine(
        id=eid,
        kind="line",
        start=Point2D(x=start[0], y=start[1]),
        end=Point2D(x=end[0], y=end[1]),
    )


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def _solved(result: SolvedSketch, eid: str) -> SketchLine:
    entity = next(e for e in result.entities if e.id == eid)
    assert isinstance(entity, SketchLine)
    return entity


def _axis_and_pins(eid: str = "ax") -> tuple[SketchLine, list[SketchConstraint]]:
    """A vertical centreline at x = 20, pinned rigid: the mirror to work about."""
    axis = _line(eid, (20.0, -5.0), (20.0, 30.0))
    return axis, [
        FixedConstraint(kind="fixed", point=_ref(eid, "start")),
        FixedConstraint(kind="fixed", point=_ref(eid, "end")),
    ]


def _pinned_right_leg() -> tuple[SketchLine, list[SketchConstraint]]:
    """The reference edge, pinned rigid at both ends: (40,0) up-left to (30,25)."""
    leg = _line("e2", (40.0, 0.0), (30.0, 25.0))
    return leg, [
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
        FixedConstraint(kind="fixed", point=_ref("e2", "end")),
    ]


def test_two_lines_and_an_axis_are_accepted_and_mirror() -> None:
    """The selection the audit found refused, now solved and MEASURED.

    ``e4`` is drawn wrong — 6 mm off where a mirror of ``e2`` would put it — and
    the constraint alone moves it onto the reflected coordinates.
    """
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    free = _line("e4", (6.0, 25.0), (0.0, 0.0))
    sketch = SketchDefinition(
        entities=[axis, leg, free],
        constraints=[
            *axis_pins,
            *leg_pins,
            SymmetricLinesConstraint(kind="symmetric_lines", a="e2", b="e4", line="ax"),
        ],
    )

    result = SOLVER.solve(sketch)

    assert result.status in ("converged", "underconstrained")
    solved = _solved(result, "e4")
    # Mirror of (40,0)-(30,25) in x = 20 is (0,0)-(10,25); e4 runs the other way
    # round the profile, so its START is the reflected END.
    assert (solved.start.x, solved.start.y) == pytest.approx(
        (10.0, 25.0), abs=SYMMETRY_TOLERANCE_MM
    )
    assert (solved.end.x, solved.end.y) == pytest.approx(
        (0.0, 0.0), abs=SYMMETRY_TOLERANCE_MM
    )


def test_the_line_form_reaches_the_point_form_bitwise() -> None:
    """THE acceptance criterion, asserted with no tolerance at all.

    Same entities, same axis, same starting geometry — once with one
    ``symmetric_lines``, once with the two ``symmetric`` point constraints it is
    equivalent to. Both are built from planegcs's ``symmetric_line`` primitive,
    so the two systems are the same system and must solve to the same bits. A
    tolerance here would hide a genuinely different route through the solver.
    """
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    free = _line("e4", (6.0, 25.0), (0.0, 0.0))
    shared: list[SketchConstraint] = [*axis_pins, *leg_pins]

    by_lines = SOLVER.solve(
        SketchDefinition(
            entities=[axis, leg, free],
            constraints=[
                *shared,
                SymmetricLinesConstraint(
                    kind="symmetric_lines", a="e2", b="e4", line="ax"
                ),
            ],
        )
    )
    by_points = SOLVER.solve(
        SketchDefinition(
            entities=[axis, leg, free],
            constraints=[
                *shared,
                SymmetricConstraint(
                    kind="symmetric",
                    a=_ref("e2", "start"),
                    b=_ref("e4", "end"),
                    line="ax",
                ),
                SymmetricConstraint(
                    kind="symmetric",
                    a=_ref("e2", "end"),
                    b=_ref("e4", "start"),
                    line="ax",
                ),
            ],
        )
    )

    assert [e.model_dump() for e in by_lines.entities] == [
        e.model_dump() for e in by_points.entities
    ]
    assert by_lines.status == by_points.status


def test_the_pairing_follows_the_drawn_geometry_not_the_endpoint_names() -> None:
    """A mirror reverses orientation, so start-to-start is often the wrong pair.

    Two sketches identical but for the DIRECTION the second edge was drawn in.
    The pairing must follow the drawing, or one of them is asked to flip its
    line end-for-end — a jump to a different branch of the solution manifold,
    not a refinement of the author's geometry.
    """
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    constraint = SymmetricLinesConstraint(
        kind="symmetric_lines", a="e2", b="e4", line="ax"
    )

    for (start, end), crossed in (
        # traced round the loop (down-left): e2's end pairs with e4's start
        (((6.0, 25.0), (0.0, 0.0)), True),
        # drawn the same way as e2 (up-left): the straight pairing
        (((0.0, 0.0), (6.0, 25.0)), False),
    ):
        free = _line("e4", start, end)
        sketch = SketchDefinition(
            entities=[axis, leg, free],
            constraints=[*axis_pins, *leg_pins, constraint],
        )
        points = {
            (entity.id, name): value
            for entity in sketch.entities
            if isinstance(entity, SketchLine)
            for name, value in (
                ("start", (entity.start.x, entity.start.y)),
                ("end", (entity.end.x, entity.end.y)),
            )
        }
        assert symmetric_lines_crossed(constraint, points) is crossed

        solved = _solved(SOLVER.solve(sketch), "e4")
        # Whichever way it was drawn, the SEGMENT is the mirror of e2 and the
        # line still runs the way its author drew it.
        ends = {
            (round(solved.start.x, 9), round(solved.start.y, 9)),
            (round(solved.end.x, 9), round(solved.end.y, 9)),
        }
        assert ends == {(10.0, 25.0), (0.0, 0.0)}
        drawn_upward = end[1] > start[1]
        assert (solved.end.y > solved.start.y) is drawn_upward


def test_symmetric_lines_removes_four_degrees_of_freedom() -> None:
    """``b`` is completely determined by ``a`` and the axis: 4 DOF, not 2."""
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    free = _line("e4", (6.0, 25.0), (0.0, 0.0))
    entities: list[SketchEntity] = [axis, leg, free]
    shared: list[SketchConstraint] = [*axis_pins, *leg_pins]

    loose = SOLVER.solve(SketchDefinition(entities=entities, constraints=shared))
    result = SOLVER.solve(
        SketchDefinition(
            entities=entities,
            constraints=[
                *shared,
                SymmetricLinesConstraint(
                    kind="symmetric_lines", a="e2", b="e4", line="ax"
                ),
            ],
        )
    )

    assert loose.dof is not None
    assert result.dof == loose.dof - 4


def test_a_symmetric_profile_solves_about_its_centreline() -> None:
    """The real shape: a trapezoid whose two legs are symmetric about x = 20.

    Drawn with the left leg 6 mm out of place; the constraint alone squares the
    profile up, and what is asserted is the SYMMETRY (both legs' x-coordinates
    equidistant from the axis) rather than a pair of literal coordinates.
    """
    entities: list[SketchEntity] = [
        _line("e1", (0.0, 0.0), (40.0, 0.0)),
        _line("e2", (40.0, 0.0), (30.0, 25.0)),
        _line("e3", (30.0, 25.0), (10.0, 25.0)),
        _line("e4", (6.0, 25.0), (0.0, 0.0)),
        _line("ax", (20.0, -5.0), (20.0, 30.0)),
    ]
    constraints: list[SketchConstraint] = [
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
        HorizontalConstraint(kind="horizontal", entity="e1"),
        DistanceConstraint(kind="distance", entity="e1", value_mm=40.0),
        FixedConstraint(kind="fixed", point=_ref("ax", "start")),
        FixedConstraint(kind="fixed", point=_ref("ax", "end")),
        VerticalConstraint(kind="vertical", entity="ax"),
        FixedConstraint(kind="fixed", point=_ref("e2", "end")),
        SymmetricLinesConstraint(kind="symmetric_lines", a="e2", b="e4", line="ax"),
    ]

    result = SOLVER.solve(SketchDefinition(entities=entities, constraints=constraints))
    e2, e4 = _solved(result, "e2"), _solved(result, "e4")

    for right, left in ((e2.start, e4.end), (e2.end, e4.start)):
        assert right.x - 20.0 == pytest.approx(20.0 - left.x, abs=SYMMETRY_TOLERANCE_MM)
        assert right.y == pytest.approx(left.y, abs=SYMMETRY_TOLERANCE_MM)


def test_symmetric_lines_on_a_circle_rejected() -> None:
    """It relates two LINES about a LINE; anything else is malformed input."""
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    circle = SketchCircle(
        id="c1", kind="circle", center=Point2D(x=5.0, y=5.0), radius=3.0
    )
    entities: list[SketchEntity] = [axis, leg, circle]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *axis_pins,
            *leg_pins,
            SymmetricLinesConstraint(kind="symmetric_lines", a="e2", b="c1", line="ax"),
        ],
    )

    with pytest.raises(SketchDefinitionError, match="symmetric_lines"):
        SOLVER.solve(sketch)


def test_symmetric_lines_solve_is_deterministic_bitwise() -> None:
    """Same definition in, bitwise identical geometry out (RESEARCH §9)."""
    axis, axis_pins = _axis_and_pins()
    leg, leg_pins = _pinned_right_leg()
    free = _line("e4", (6.0, 25.0), (0.0, 0.0))
    sketch = SketchDefinition(
        entities=[axis, leg, free],
        constraints=[
            *axis_pins,
            *leg_pins,
            SymmetricLinesConstraint(kind="symmetric_lines", a="e2", b="e4", line="ax"),
        ],
    )

    runs = [SOLVER.solve(sketch).model_dump() for _ in range(5)]

    for other in runs[1:]:
        assert other == runs[0]
