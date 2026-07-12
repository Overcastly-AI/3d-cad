"""Fit-point spline sketch entity — DTO, solver pass-through, kernel edge.

Covers BACKLOG #6 (splines, backend) beyond the ``sketch-spline-extrude``
golden (which locks mass properties / topology / determinism / STEP
round-trip through the harness): the DTO validation floor (min 2 fit points),
the NON-CONSTRAINED v1 solver contract (a spline is skipped when building the
constraint system yet preserved bitwise in the solved result, and its presence
never perturbs the DOF/diagnosis of the other entities), the kernel edge
construction (:func:`entity_edges` emits exactly one interpolating spline
edge), and the degenerate error path (coincident consecutive fit points ->
legible profile error, never an opaque kernel 500).

Determinism assertions are bitwise (``==``) — determinism takes no tolerance
(RESEARCH §9).
"""

import math

import pytest
from build123d import Plane
from geometry.kernel.extrude import (
    ProfileNotClosedError,
    build_profile_face,
    entity_edges,
)
from geometry.sketch import (
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    SketchSpline,
)
from geometry.sketch.solver import SketchDefinitionError
from pydantic import ValidationError

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _spline(eid: str, points: list[tuple[float, float]]) -> SketchSpline:
    return SketchSpline(
        id=eid, kind="spline", points=[Point2D(x=x, y=y) for x, y in points]
    )


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


# --- DTO validation --------------------------------------------------------


def test_spline_requires_at_least_two_fit_points() -> None:
    """min_length=2: a single fit point is a malformed DTO (422 upstream)."""
    with pytest.raises(ValidationError):
        SketchSpline(id="e1", kind="spline", points=[Point2D(x=0.0, y=0.0)])


def test_spline_two_fit_points_is_valid() -> None:
    """Two fit points is the documented floor (degenerates to a straight
    interpolant, still a valid spline entity)."""
    entity = _spline("e1", [(0.0, 0.0), (10.0, 0.0)])
    assert len(entity.points) == 2


def test_spline_is_a_discriminated_member_of_the_entity_union() -> None:
    """A ``kind: "spline"`` object parses to :class:`SketchSpline` through the
    discriminated union (persisted sketches route by ``kind``)."""
    sketch = SketchDefinition.model_validate(
        {
            "entities": [
                {
                    "id": "e1",
                    "kind": "spline",
                    "points": [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 5.0}],
                }
            ],
            "constraints": [],
        }
    )
    assert isinstance(sketch.entities[0], SketchSpline)


# --- solver: skip-but-preserve (NON-CONSTRAINED v1) ------------------------


def test_solver_preserves_spline_fit_points_bitwise() -> None:
    """A spline passes through the solve untouched — fit points identical."""
    entities: list[SketchEntity] = [
        _spline("e1", [(0.0, 0.0), (3.0, 8.0), (11.0, 4.0)])
    ]
    result = SOLVER.solve(SketchDefinition(entities=entities, constraints=[]))
    (solved,) = result.entities
    assert isinstance(solved, SketchSpline)
    assert [(p.x, p.y) for p in solved.points] == [(0.0, 0.0), (3.0, 8.0), (11.0, 4.0)]
    assert solved.id == "e1"


def test_spline_contributes_no_dof_and_does_not_disturb_other_entities() -> None:
    """A fully-constrained line stays converged (DOF 0) when a spline is added
    to the same sketch: the spline adds no parameters and no equations."""
    line = SketchLine(
        id="ln",
        kind="line",
        start=Point2D(x=0.0, y=0.0),
        end=Point2D(x=10.0, y=0.0),
    )
    constraints: list[SketchConstraint] = [
        HorizontalConstraint(kind="horizontal", entity="ln"),
        DistanceConstraint(kind="distance", entity="ln", value_mm=10.0),
        FixedConstraint(kind="fixed", point=_ref("ln", "start")),
    ]
    without = SOLVER.solve(SketchDefinition(entities=[line], constraints=constraints))
    with_spline = SOLVER.solve(
        SketchDefinition(
            entities=[line, _spline("sp", [(0.0, 5.0), (5.0, 9.0), (10.0, 5.0)])],
            constraints=constraints,
        )
    )
    assert without.status == "converged" and without.dof == 0
    # Same diagnosis for the line-bearing system with the spline present.
    assert with_spline.status == "converged" and with_spline.dof == 0
    # The spline survives, last in order, untouched.
    sp = with_spline.entities[1]
    assert isinstance(sp, SketchSpline)
    assert [(p.x, p.y) for p in sp.points] == [(0.0, 5.0), (5.0, 9.0), (10.0, 5.0)]


def test_solver_is_deterministic_with_a_spline() -> None:
    """Same definition -> bitwise-identical solved result (RESEARCH §9)."""
    sketch = SketchDefinition(
        entities=[_spline("e1", [(0.0, 0.0), (4.0, 7.0), (9.0, 2.0)])],
        constraints=[],
    )
    assert SOLVER.solve(sketch) == SOLVER.solve(sketch)


def test_constraint_on_a_spline_point_is_a_malformed_definition() -> None:
    """v1 splines expose no solver-addressable point; a constraint that names
    one is a caller bug (SketchDefinitionError), not a solve outcome."""
    sketch = SketchDefinition(
        entities=[_spline("e1", [(0.0, 0.0), (5.0, 5.0)])],
        constraints=[FixedConstraint(kind="fixed", point=_ref("e1", "start"))],
    )
    with pytest.raises(SketchDefinitionError):
        SOLVER.solve(sketch)


# --- kernel edge construction ----------------------------------------------


def test_entity_edges_emits_one_spline_edge() -> None:
    spline = _spline("e1", [(0.0, 0.0), (10.0, 8.0), (20.0, 0.0)])
    edges = entity_edges(Plane.XY, spline)
    assert len(edges) == 1
    edge = edges[0]
    # The interpolating curve passes through its endpoints (fit points).
    start = edge.position_at(0.0)
    end = edge.position_at(1.0)
    assert math.isclose(start.X, 0.0, abs_tol=1e-9)
    assert math.isclose(start.Y, 0.0, abs_tol=1e-9)
    assert math.isclose(end.X, 20.0, abs_tol=1e-9)
    assert math.isclose(end.Y, 0.0, abs_tol=1e-9)


def test_coincident_consecutive_fit_points_raise_profile_error() -> None:
    """A degenerate spline surfaces as a legible profile error (maps to the
    per-feature ``profile_not_closed`` code), never an opaque kernel failure."""
    degenerate = _spline("e1", [(0.0, 0.0), (5.0, 5.0), (5.0, 5.0), (10.0, 0.0)])
    with pytest.raises(ProfileNotClosedError, match="coincident"):
        entity_edges(Plane.XY, degenerate)


def test_closed_profile_with_a_spline_edge_builds_a_face() -> None:
    """Three lines + one spline closing the loop assemble into a single face —
    the golden's profile, checked here at the kernel-unit grain."""
    entities: list[SketchEntity] = [
        SketchLine(
            id="e1",
            kind="line",
            start=Point2D(x=0.0, y=0.0),
            end=Point2D(x=40.0, y=0.0),
        ),
        SketchLine(
            id="e2",
            kind="line",
            start=Point2D(x=40.0, y=0.0),
            end=Point2D(x=40.0, y=20.0),
        ),
        SketchLine(
            id="e3",
            kind="line",
            start=Point2D(x=40.0, y=20.0),
            end=Point2D(x=30.0, y=25.0),
        ),
        _spline("e4", [(30.0, 25.0), (15.0, 30.0), (5.0, 20.0), (0.0, 0.0)]),
    ]
    face = build_profile_face("XY", entities)
    assert face.area > 0.0
