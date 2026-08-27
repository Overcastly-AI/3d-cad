"""The ANGLE dimension: every assertion here measures the solved GEOMETRY.

SKETCH-VOCAB-1 / docs/AUDIT-PRODUCT.md T-5 — until this landed, a gusset at 30
degrees could be drawn but never driven, so it drifted on every edit.

**Not one test here asserts on the solver's status alone, and that is the
point.** planegcs returns ``Success`` with ``conflicting=[]`` on sketches whose
constraints are flatly unsatisfiable — a 400-sketch sweep found lines 67 degrees
apart under a ``parallel`` + ``perpendicular`` pair reported clean
(``_violated_constraints``' docstring). So an angle constraint is tested by
MEASURING the angle between the solved lines, which is the only evidence that
means anything.

Tolerance: ``ANGLE_TOLERANCE_DEG = 1e-7`` degrees. Derived, not picked: the
solver's own satisfaction bound is ``SATISFIED_TOL_MM = 1e-7`` read on the
constraint's own scale (radians for the angular kinds), and 1e-7 degrees is
``1.7e-9`` radians — ~57x TIGHTER than the bound the solver is held to, so this
suite cannot pass on a solve the residual gate would reject. Measured deviations
are at the 1e-14 degree level (below), five orders inside it.
"""

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import pytest
from geometry.sketch import (
    AngleConstraint,
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    PlanegcsSketchSolver,
    Point2D,
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
from geometry.sketch.angles import AngleFrame, angle_frames

#: Documented angular bound (degrees) — see module docstring for the derivation.
ANGLE_TOLERANCE_DEG = 1e-7

_Vec = tuple[float, float]

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _load_outline_builder() -> ModuleType:
    """Import the realistic-outline builder by path.

    The workspace runs pytest with ``--import-mode=importlib``, so test modules
    cannot import each other by name (same idiom as ``test_benchmarks.py``).
    """
    path = Path(__file__).resolve().parent / "_sketch_outline_builder.py"
    spec = importlib.util.spec_from_file_location("_sketch_outline_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OUTLINES = _load_outline_builder()


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


def _dir(line: SketchLine) -> tuple[float, float]:
    return (line.end.x - line.start.x, line.end.y - line.start.y)


def _angle_between_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Unsigned angle between two vectors, in degrees — measured independently.

    Deliberately NOT ``geometry.sketch.angles``: a test that measured with the
    module under test would verify a wrong claim happily against itself
    (CLAUDE.md). Plain ``acos`` of the normalised dot product, which knows
    nothing about corners, orientation or sign.
    """
    dot = a[0] * b[0] + a[1] * b[1]
    scale = math.hypot(*a) * math.hypot(*b)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / scale))))


def _fixed_base_line(
    eid: str = "e1", length: float = 40.0
) -> tuple[SketchLine, list[SketchConstraint]]:
    """A line from the origin along +X, pinned rigid: the angle's reference leg."""
    line = _line(eid, (0.0, 0.0), (length, 0.0))
    return line, [
        FixedConstraint(kind="fixed", point=_ref(eid, "start")),
        HorizontalConstraint(kind="horizontal", entity=eid),
        DistanceConstraint(kind="distance", entity=eid, value_mm=length),
    ]


def test_angle_dimension_drives_the_measured_angle() -> None:
    """A free line dimensioned 30 degrees off a rigid one MEASURES 30 degrees.

    The base case, asserted on geometry: the solved directions' own angle, from
    an ``acos`` that has never heard of the solver.
    """
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 2.0))
    constraints: list[SketchConstraint] = [
        *fixings,
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
    ]
    sketch = SketchDefinition(entities=[base, free], constraints=constraints)
    dimensioned = SketchDefinition(
        entities=[base, free],
        constraints=[
            *constraints,
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=30.0),
        ],
    )

    loose = SOLVER.solve(sketch)
    result = SOLVER.solve(dimensioned)

    assert result.status in ("converged", "underconstrained")
    measured = _angle_between_deg(
        _dir(_solved(result, "e1")), _dir(_solved(result, "e2"))
    )
    assert measured == pytest.approx(30.0, abs=ANGLE_TOLERANCE_DEG)
    assert loose.dof is not None
    assert result.dof == loose.dof - 1  # exactly one rotational DOF removed


def test_angle_holds_the_side_the_author_drew() -> None:
    """Typing a number resizes the drawn angle; it never reflects the profile.

    ``e2`` is drawn sloping DOWN from its anchor. A signed constraint that
    ignored which side the author drew would solve it 30 degrees ABOVE the base
    line — same magnitude, mirrored geometry, and every downstream feature moved.
    """
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 2.0))  # drawn sloping DOWN
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=30.0),
        ],
    )

    solved = _solved(SOLVER.solve(sketch), "e2")

    assert solved.end.y < solved.start.y  # still below its anchor, as drawn
    assert _angle_between_deg(_dir(solved), (1.0, 0.0)) == pytest.approx(
        30.0, abs=ANGLE_TOLERANCE_DEG
    )


def test_angle_is_the_interior_angle_at_the_shared_corner() -> None:
    """Two edges meeting at a corner are dimensioned by the angle you SEE.

    Traverse a profile in loop order and consecutive edge DIRECTIONS differ by
    the exterior angle, so planegcs's raw line-to-line angle would put 120 on the
    screen where the user means 60 — and typing 60 would open the corner to 120.
    The convention is therefore the angle between the two legs taken AWAY from
    the corner they share (``geometry.sketch.angles``), and this test pins the
    difference: the interior angle is the constrained 60, and the raw direction
    difference is its supplement.
    """
    base, fixings = _fixed_base_line()
    leg = _line("e2", (40.0, 0.0), (10.0, 20.0))  # up and to the left, ~34 deg
    sketch = SketchDefinition(
        entities=[base, leg],
        constraints=[
            *fixings,
            CoincidentConstraint(
                kind="coincident", a=_ref("e1", "end"), b=_ref("e2", "start")
            ),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=60.0),
        ],
    )

    result = SOLVER.solve(sketch)
    e1, e2 = _solved(result, "e1"), _solved(result, "e2")
    corner = (e2.start.x, e2.start.y)

    interior = _angle_between_deg(
        (e1.start.x - corner[0], e1.start.y - corner[1]),  # corner -> far end
        (e2.end.x - corner[0], e2.end.y - corner[1]),
    )
    assert interior == pytest.approx(60.0, abs=ANGLE_TOLERANCE_DEG)
    # ... and the raw directions differ by the SUPPLEMENT, which is exactly the
    # number a naive wiring would have driven to 60.
    assert _angle_between_deg(_dir(e1), _dir(e2)) == pytest.approx(
        120.0, abs=ANGLE_TOLERANCE_DEG
    )
    assert e2.end.y > 0.0  # opened upward, the side it was drawn on


def test_angle_readout_is_degrees_on_its_own_list() -> None:
    """The readout carries the angle in ``angles``, never under an ``_mm`` name."""
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 2.0))
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=30.0, name="rake"),
        ],
    )

    result = SOLVER.solve(sketch)

    assert [d.constraint_index for d in result.dimensions] == [2]  # the distance
    assert len(result.angles) == 1
    (angle,) = result.angles
    assert angle.constraint_index == 4
    assert angle.name == "rake"
    assert angle.driving is True
    assert angle.value_deg == pytest.approx(30.0, abs=ANGLE_TOLERANCE_DEG)


def test_driven_angle_measures_back_from_the_geometry() -> None:
    """A DRIVEN angle constrains nothing and reads the angle that is there.

    The reference-dimension half of the vocabulary: ``driving=False`` keeps the
    number out of the constraint system (no DOF removed) and reports what the
    geometry actually does — here the 45 degrees the drawn line already has, not
    the 30 the constraint carries as a placeholder.
    """
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 0.0), (10.0, 10.0))  # exactly 45 degrees, as drawn
    constraints: list[SketchConstraint] = [
        *fixings,
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
        FixedConstraint(kind="fixed", point=_ref("e2", "end")),
    ]
    reference = SketchDefinition(
        entities=[base, free],
        constraints=[
            *constraints,
            AngleConstraint(
                kind="angle", a="e1", b="e2", value_deg=30.0, driving=False
            ),
        ],
    )

    baseline = SOLVER.solve(
        SketchDefinition(entities=[base, free], constraints=constraints)
    )
    result = SOLVER.solve(reference)

    assert result.dof == baseline.dof  # driven: nothing removed
    (angle,) = result.angles
    assert angle.driving is False
    assert angle.value_deg == pytest.approx(45.0, abs=ANGLE_TOLERANCE_DEG)
    assert _angle_between_deg(
        _dir(_solved(result, "e1")), _dir(_solved(result, "e2"))
    ) == pytest.approx(45.0, abs=ANGLE_TOLERANCE_DEG)


def test_angle_driven_by_an_expression_over_another_dimension() -> None:
    """``angle = "half*2"`` resolves, and the GEOMETRY lands on the result."""
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 7.0))
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            DistanceConstraint(
                kind="distance", entity="e2", value_mm=20.0, name="half"
            ),
            AngleConstraint(
                kind="angle", a="e1", b="e2", value_deg=1.0, expression="half*2"
            ),
        ],
    )

    result = SOLVER.solve(sketch)

    assert _angle_between_deg(
        _dir(_solved(result, "e1")), _dir(_solved(result, "e2"))
    ) == pytest.approx(40.0, abs=ANGLE_TOLERANCE_DEG)
    (angle,) = result.angles
    assert angle.value_deg == pytest.approx(40.0, abs=ANGLE_TOLERANCE_DEG)
    assert angle.expression == "half*2"


def test_angle_expression_out_of_range_is_a_clean_error() -> None:
    """An expression can reach 180 where the field bounds cannot see it.

    ``value_deg`` is bounded (0, 180) at the schema, but an EXPRESSION is a
    string: ``"half*20"`` validates fine and evaluates to 400. Unchecked it would
    reach planegcs and come back as a silently wrapped angle — a wrong answer
    rather than a refusal.
    """
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 7.0))
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            DistanceConstraint(
                kind="distance", entity="e2", value_mm=20.0, name="half"
            ),
            AngleConstraint(
                kind="angle", a="e1", b="e2", value_deg=1.0, expression="half*20"
            ),
        ],
    )

    with pytest.raises(SketchExpressionError, match="must be < 180"):
        SOLVER.solve(sketch)


def test_angle_value_out_of_range_rejected_at_validation() -> None:
    """0 and 180 are the parallel degeneracies, not angles — refused by the DTO."""
    for degrees in (0.0, 180.0, 360.0, -30.0):
        with pytest.raises(ValueError):
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=degrees)


def test_angle_on_a_circle_rejected() -> None:
    """An angle dimension relates two LINES; anything else is malformed input."""
    base, fixings = _fixed_base_line()
    circle = SketchCircle(
        id="c1", kind="circle", center=Point2D(x=5.0, y=5.0), radius=3.0
    )
    entities: list[SketchEntity] = [base, circle]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *fixings,
            AngleConstraint(kind="angle", a="e1", b="c1", value_deg=30.0),
        ],
    )

    with pytest.raises(SketchDefinitionError, match="angle"):
        SOLVER.solve(sketch)


def test_angle_contradicting_perpendicular_never_ships_the_wrong_geometry() -> None:
    """30 degrees AND perpendicular on the same pair cannot both hold.

    The SOLVE-1 lesson in its own vocabulary: planegcs is capable of reporting
    ``Success`` on exactly this shape (see ``_violated_constraints``), so what is
    asserted is not the status but that the payload never contains lines whose
    measured angle is neither 30 nor 90 — the least-squares compromise that
    would otherwise ship.
    """
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 7.0))
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=30.0),
            PerpendicularConstraint(kind="perpendicular", a="e1", b="e2"),
        ],
    )

    result = SOLVER.solve(sketch)

    # Either refusal is honest ("conflicting" when the diagnosis names the pair,
    # "diverged" when DogLeg simply cannot land); what may never happen is a
    # SOLVED status over geometry that satisfies neither number.
    assert result.status in ("conflicting", "diverged")
    # A refused sketch ships the INPUT geometry untouched, never a compromise.
    solved = _solved(result, "e2")
    assert (solved.start.x, solved.start.y) == (0.0, 5.0)
    assert (solved.end.x, solved.end.y) == (8.0, 7.0)


def test_angle_agreeing_with_parallel_is_still_a_conflict() -> None:
    """An angle of 90 beside ``parallel`` is unsatisfiable and reported as such."""
    base, fixings = _fixed_base_line()
    free = _line("e2", (0.0, 5.0), (8.0, 7.0))
    sketch = SketchDefinition(
        entities=[base, free],
        constraints=[
            *fixings,
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=90.0),
            ParallelConstraint(kind="parallel", a="e1", b="e2"),
        ],
    )

    result = SOLVER.solve(sketch)

    assert result.status in ("conflicting", "diverged")
    solved = _solved(result, "e2")
    assert (solved.end.x, solved.end.y) == (8.0, 7.0)  # input, not a compromise


def test_angle_solve_is_deterministic_bitwise() -> None:
    """Same definition in, bitwise identical geometry out (RESEARCH §9)."""
    base, fixings = _fixed_base_line()
    leg = _line("e2", (40.0, 0.0), (10.0, 20.0))
    sketch = SketchDefinition(
        entities=[base, leg],
        constraints=[
            *fixings,
            CoincidentConstraint(
                kind="coincident", a=_ref("e1", "end"), b=_ref("e2", "start")
            ),
            AngleConstraint(kind="angle", a="e1", b="e2", value_deg=60.0),
        ],
    )

    runs = [SOLVER.solve(sketch) for _ in range(5)]

    first = runs[0].model_dump()
    for other in runs[1:]:
        assert other.model_dump() == first


def test_the_angle_convention_is_never_re_derived_on_the_settle_hot_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frame is built ONCE per solve, not once per trial solve.

    The residual sweep runs on every rung of the settle ladder, and deriving an
    angle frame walks the constraint list and builds a union-find over every
    coincident pair. Re-deriving it there would put a per-constraint cost on the
    one path whose cost must not grow with sketch size — the exact shape of
    SETTLE-PERF-1, where a per-entity question in the settle turned an 8 ms
    dimension edit into 13 seconds. So the build caches the map and hands it
    down, and this asserts the property rather than the timing (a wall-clock
    assertion under a parallel batch is a coin flip; a call count is not).

    Measured alongside, on the realistic staircase outline rather than on a
    12-entity toy — swapping one ``vertical`` for an equivalent 90-degree angle
    dimension, so the system is the same size and the angle is load-bearing:
    rebuild 0.92x at 48 lines, dimension edit 0.61x at 48 lines, i.e. inside the
    run-to-run noise at every size measured (16/32/48).
    """
    calls = 0

    def counting(
        constraints: list[SketchConstraint], points: dict[tuple[str, str], _Vec]
    ) -> dict[int, AngleFrame]:
        nonlocal calls
        calls += 1
        return angle_frames(constraints, points)

    # The name the residual module resolves at call time, patched by path: it is
    # bound there by `from ... import`, so patching the source module would not
    # be seen.
    monkeypatch.setattr("geometry.sketch.residual.angle_frames", counting)

    sketch = _OUTLINES.outline(
        16, width_mm=14.0
    )  # the settle-heavy "type a new number"
    constraints = [
        AngleConstraint(kind="angle", a="e0", b="e1", value_deg=90.0)
        if c.kind == "vertical" and c.entity == "e1"
        else c
        for c in sketch.constraints
    ]
    result = SOLVER.solve(
        SketchDefinition(entities=sketch.entities, constraints=constraints)
    )

    assert result.status in ("converged", "underconstrained")
    assert calls == 0, (
        f"the residual sweep derived the angle frames {calls} time(s) — it must "
        "receive the build's cached map, or every settle trial pays for it"
    )
