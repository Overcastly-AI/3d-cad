"""The DIAMETER dimension: asserted on the solved circle, never on the status.

SKETCH-VOCAB-1 / docs/AUDIT-PRODUCT.md T-5 — holes are specified by diameter on
every drawing and every fastener table, and a sketcher that offers only a radius
makes the number on screen permanently disagree with the number on the drawing.

The whole risk in this constraint is a factor of two, in either direction, and
neither mistake is visible in a solver status: a diameter driven as a radius
gives a hole twice the size the user asked for, and its residual half the size
it should be. So every test here MEASURES the solved radius against the typed
diameter, and one of them pins the residual scale against planegcs's own.

Tolerance: ``RADIUS_TOLERANCE_MM = 1e-9`` mm — the same documented bound the
rest of the sketch suite uses for a well-conditioned solve, five orders under
the kernel linear tolerance (1e-7 m = 1e-4 mm). Measured deviations are at the
1e-13 mm level.
"""

import math

import pytest
from geometry.sketch import (
    DiameterConstraint,
    EntityPointRef,
    FixedConstraint,
    PlanegcsSketchSolver,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchExpressionError,
    SketchLine,
    SketchSolver,
    SolvedSketch,
)
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import constraint_residual

RADIUS_TOLERANCE_MM = 1e-9

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _circle(eid: str, center: tuple[float, float], radius: float) -> SketchCircle:
    return SketchCircle(
        id=eid,
        kind="circle",
        center=Point2D(x=center[0], y=center[1]),
        radius=radius,
    )


def _solved_circle(result: SolvedSketch, eid: str) -> SketchCircle:
    entity = next(e for e in result.entities if e.id == eid)
    assert isinstance(entity, SketchCircle)
    return entity


def test_diameter_drives_half_of_itself_into_the_radius() -> None:
    """Ask for 16, get a radius of 8 — the factor of two, asserted on geometry.

    A diameter wired straight onto the radius parameter would give a 32 mm hole
    for a 16 mm callout, which is a scrapped part and not a status the solver
    would ever complain about.
    """
    circle = _circle("c1", (20.0, 12.5), 5.0)
    sketch = SketchDefinition(
        entities=[circle],
        constraints=[
            FixedConstraint(
                kind="fixed",
                point=EntityPointRef(entity="c1", point="center"),
            ),
            DiameterConstraint(kind="diameter", entity="c1", value_mm=16.0),
        ],
    )

    result = SOLVER.solve(sketch)

    assert result.status in ("converged", "underconstrained")
    assert _solved_circle(result, "c1").radius == pytest.approx(
        8.0, abs=RADIUS_TOLERANCE_MM
    )


def test_diameter_and_radius_reach_the_same_geometry() -> None:
    """The acceptance criterion: it drives the same radius internally.

    Two sketches identical but for the dimension KIND — Ø16 against R8 — must
    produce the same circle. Asserted bitwise, not within a tolerance: they are
    the same constraint on the same parameter, so any difference at all would
    mean the diameter path takes a different route through the solver.
    """
    circle = _circle("c1", (20.0, 12.5), 5.0)
    anchor: list[SketchConstraint] = [
        FixedConstraint(kind="fixed", point=EntityPointRef(entity="c1", point="center"))
    ]
    by_diameter = SOLVER.solve(
        SketchDefinition(
            entities=[circle],
            constraints=[
                *anchor,
                DiameterConstraint(kind="diameter", entity="c1", value_mm=16.0),
            ],
        )
    )
    by_radius = SOLVER.solve(
        SketchDefinition(
            entities=[circle],
            constraints=[
                *anchor,
                RadiusConstraint(kind="radius", entity="c1", value_mm=8.0),
            ],
        )
    )

    assert [e.model_dump() for e in by_diameter.entities] == [
        e.model_dump() for e in by_radius.entities
    ]
    assert by_diameter.status == by_radius.status
    assert by_diameter.dof == by_radius.dof


def test_diameter_on_an_arc_drives_its_radius_too() -> None:
    """An arc is a circle with ends; a diameter callout works on it the same."""
    arc = SketchArc(
        id="a1",
        kind="arc",
        center=Point2D(x=0.0, y=0.0),
        start=Point2D(x=5.0, y=0.0),
        end=Point2D(x=0.0, y=5.0),
    )
    entities: list[SketchEntity] = [arc]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            FixedConstraint(
                kind="fixed", point=EntityPointRef(entity="a1", point="center")
            ),
            DiameterConstraint(kind="diameter", entity="a1", value_mm=24.0),
        ],
    )

    result = SOLVER.solve(sketch)
    solved = next(e for e in result.entities if e.id == "a1")
    assert isinstance(solved, SketchArc)

    start_radius = math.hypot(
        solved.start.x - solved.center.x, solved.start.y - solved.center.y
    )
    end_radius = math.hypot(
        solved.end.x - solved.center.x, solved.end.y - solved.center.y
    )
    assert start_radius == pytest.approx(12.0, abs=RADIUS_TOLERANCE_MM)
    # Both ends, because an arc whose endpoints disagree about their own centre
    # distance is not a curve any kernel can build (residual.entity_residual).
    assert end_radius == pytest.approx(12.0, abs=RADIUS_TOLERANCE_MM)


def test_driven_diameter_reads_back_twice_the_radius() -> None:
    """A reference diameter reports what the geometry HAS, in diameter units."""
    circle = _circle("c1", (0.0, 0.0), 7.5)
    sketch = SketchDefinition(
        entities=[circle],
        constraints=[
            FixedConstraint(
                kind="fixed", point=EntityPointRef(entity="c1", point="center")
            ),
            RadiusConstraint(kind="radius", entity="c1", value_mm=7.5),
            DiameterConstraint(
                kind="diameter", entity="c1", value_mm=1.0, driving=False
            ),
        ],
    )

    result = SOLVER.solve(sketch)

    readout = next(d for d in result.dimensions if d.constraint_index == 2)
    assert readout.driving is False
    assert readout.value_mm == pytest.approx(15.0, abs=RADIUS_TOLERANCE_MM)


def test_diameter_residual_is_on_the_radius_scale_planegcs_uses() -> None:
    """The second opinion may not be stricter than the solver — measured.

    planegcs's ``circle_diameter`` error is ``r - d/2``, the RADIUS-scale miss:
    probed at r=10 asking d=26 it reports 3.0, exactly what ``set_circle_radius
    (13)`` reports, where the diameter difference would be 6.0. A residual
    written in diameter units would therefore be exactly 2x stricter than the
    witness it is checking — the parallel bug's shape, which silently refuses
    settles the solver accepts (``residual`` module docstring).
    """
    sketch = SketchDefinition(
        entities=[_circle("c1", (0.0, 0.0), 10.0)],
        constraints=[DiameterConstraint(kind="diameter", entity="c1", value_mm=26.0)],
    )
    build = _GcsBuild(sketch, {0: 26.0})
    (tag,) = [t for t, index in build.tag_to_index.items() if index == 0]

    planegcs = abs(build.gcs.solver.constraint_error(tag))
    mine = constraint_residual(
        sketch.constraints[0],
        {e.id: e for e in build.read_back()},
        {},
        26.0,
    )

    assert planegcs == pytest.approx(3.0, abs=SATISFIED_TOL_MM)
    assert mine is not None
    assert mine == pytest.approx(planegcs, abs=SATISFIED_TOL_MM)


def test_diameter_on_a_line_rejected() -> None:
    """A line has no diameter; a callout on one is malformed input."""
    sketch = SketchDefinition(
        entities=[
            SketchLine(
                id="e1",
                kind="line",
                start=Point2D(x=0.0, y=0.0),
                end=Point2D(x=10.0, y=0.0),
            )
        ],
        constraints=[DiameterConstraint(kind="diameter", entity="e1", value_mm=16.0)],
    )

    with pytest.raises(SketchDefinitionError, match="diameter"):
        SOLVER.solve(sketch)


def test_diameter_expression_over_another_dimension() -> None:
    """``bore = "shaft + clearance"`` — the reason a dimension has a name."""
    sketch = SketchDefinition(
        entities=[_circle("c1", (0.0, 0.0), 3.0), _circle("c2", (40.0, 0.0), 3.0)],
        constraints=[
            FixedConstraint(
                kind="fixed", point=EntityPointRef(entity="c1", point="center")
            ),
            FixedConstraint(
                kind="fixed", point=EntityPointRef(entity="c2", point="center")
            ),
            DiameterConstraint(
                kind="diameter", entity="c1", value_mm=10.0, name="shaft"
            ),
            DiameterConstraint(
                kind="diameter", entity="c2", value_mm=1.0, expression="shaft+0.4"
            ),
        ],
    )

    result = SOLVER.solve(sketch)

    assert _solved_circle(result, "c1").radius == pytest.approx(
        5.0, abs=RADIUS_TOLERANCE_MM
    )
    assert _solved_circle(result, "c2").radius == pytest.approx(
        5.2, abs=RADIUS_TOLERANCE_MM
    )
    fit = next(d for d in result.dimensions if d.constraint_index == 3)
    assert fit.value_mm == pytest.approx(10.4, abs=RADIUS_TOLERANCE_MM)


def test_diameter_expression_that_goes_non_positive_is_a_clean_error() -> None:
    """A hole cannot have a diameter of zero — refused, never handed to OCCT."""
    sketch = SketchDefinition(
        entities=[_circle("c1", (0.0, 0.0), 3.0), _circle("c2", (40.0, 0.0), 3.0)],
        constraints=[
            DiameterConstraint(
                kind="diameter", entity="c1", value_mm=10.0, name="shaft"
            ),
            DiameterConstraint(
                kind="diameter", entity="c2", value_mm=1.0, expression="shaft-10"
            ),
        ],
    )

    with pytest.raises(SketchExpressionError, match="must be > 0"):
        SOLVER.solve(sketch)


def test_diameter_solve_is_deterministic_bitwise() -> None:
    """Same definition in, bitwise identical geometry out (RESEARCH §9)."""
    sketch = SketchDefinition(
        entities=[_circle("c1", (20.0, 12.5), 5.0)],
        constraints=[
            FixedConstraint(
                kind="fixed", point=EntityPointRef(entity="c1", point="center")
            ),
            DiameterConstraint(kind="diameter", entity="c1", value_mm=16.0),
        ],
    )

    runs = [SOLVER.solve(sketch).model_dump() for _ in range(5)]

    for other in runs[1:]:
        assert other == runs[0]
