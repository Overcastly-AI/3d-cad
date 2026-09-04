"""SOLVE-CRASH-1 — what happens when a solve drives a circle's radius to zero.

The defect this closes: ``SketchCircle.radius`` is ``gt=0``, nothing constrains
planegcs to keep its radius parameter positive, and ``read_back()`` therefore
constructed a DTO the DTO refuses. ``evaluate_sketch`` catches only
``SketchDefinitionError``, so a ``pydantic.ValidationError`` escaped the feature
evaluator and reached the user as an untyped 500 — a dead end with nothing
attached that says what is wrong. PBT-1's sweep measured it at **12 of 2000**
generated sketches (0.6%), on shapes a user can author.

**The 12 were not one defect, and the two halves want opposite answers.** That
is what these tests pin, because getting it wrong in either direction is worse
than the crash:

* **Three** (trials 259, 536, 1697) had a NEGATIVE radius of real magnitude,
  which in planegcs is not a degenerate circle at all — its radius is a signed
  parameter whose sign selects the branch of a tangency
  (``tangent_circle_circle`` is ``d - (r1 + r2)``, so ``r2 < 0`` is the INTERNAL
  tangency of a circle of radius ``|r2|``). All three now come back as ordinary
  solves with a worst residual of **1.8e-13 mm**: a positive-radius solution
  existed and the solver had found it, so refusing these would have made legal
  models unbuildable — and the user would have no way to tell it was our fault.
* **Nine** were annihilated, nearly all one shape: a ``tangent`` between a line
  and a circle whose centre some OTHER constraint puts ON that line
  (``coincident`` with an endpoint, or ``midpoint``). The centre-to-line
  distance is zero, tangency needs it to equal the radius, so ``r = 0`` is the
  unique solution and there is no positive-radius answer to find.

And the crash was only the LOUD half, which is why
:data:`~geometry.sketch.planegcs_solver.DEGENERATE_RADIUS_MM` is a MAGNITUDE
test and not the DTO's own ``> 0``. The nine annihilated circles straddle zero
by float noise — seven reach exactly ``0.0``, two stop at ``1.5e-15`` and
``1.9e-15`` mm — and two MORE (trials 644, 926, at ``2.7e-15`` and ``8.9e-16``)
never crashed at all: they shipped under ``status="underconstrained"`` with an
empty conflict list, and every property in the PBT-1 sweep agreed with them.
"""

import math
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from geometry.sketch import (
    CoincidentConstraint,
    EntityPointRef,
    PlanegcsSketchSolver,
    Point2D,
    RadiusConstraint,
    SketchCircle,
    SketchDefinition,
    SketchLine,
    SketchSolver,
    TangentConstraint,
)
from geometry.sketch.planegcs_solver import (
    DEGENERATE_RADIUS_MM,
    SATISFIED_TOL_MM,
    _shippable_radius,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import worst_residual

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _annihilated_circle() -> SketchDefinition:
    """PBT-1 trial 1809, minimised: a tangency with nowhere to be.

    The circle's centre is pinned to the line's start point, so the
    centre-to-line distance is zero and the only radius satisfying ``tangent``
    is zero. Before this fix, the solve raised ``ValidationError``.
    """
    return SketchDefinition(
        entities=[
            SketchLine(
                id="e1",
                kind="line",
                start=Point2D(x=-34.989, y=-13.107),
                end=Point2D(x=-0.386, y=34.234),
            ),
            SketchCircle(
                id="e2",
                kind="circle",
                center=Point2D(x=-1.803, y=21.685),
                radius=7.741,
            ),
        ],
        constraints=[
            TangentConstraint(kind="tangent", a="e1", b="e2"),
            CoincidentConstraint(
                kind="coincident",
                a=EntityPointRef(entity="e1", point="start"),
                b=EntityPointRef(entity="e2", point="center"),
            ),
        ],
    )


def _internally_tangent_circles() -> SketchDefinition:
    """PBT-1 trial 259, minimised: the solve lands on the NEGATIVE branch.

    Two circles made tangent with the larger one dimensioned to 43.595 mm.
    planegcs answers with the second circle's radius parameter at
    ``-14.198539866496207`` — i.e. the internal tangency of an r14.198 circle,
    which is a real, positive-radius solution written in the solver's sign
    convention. Before this fix, the solve raised ``ValidationError`` here too,
    so a perfectly solvable sketch was a 500.
    """
    return SketchDefinition(
        entities=[
            SketchCircle(
                id="e2",
                kind="circle",
                center=Point2D(x=-15.968, y=10.728),
                radius=12.88,
            ),
            SketchCircle(
                id="e3",
                kind="circle",
                center=Point2D(x=17.882, y=9.974),
                radius=5.946,
            ),
        ],
        constraints=[
            TangentConstraint(kind="tangent", a="e2", b="e3"),
            RadiusConstraint(kind="radius", entity="e2", value_mm=43.595),
        ],
    )


def test_a_solve_that_annihilates_a_circle_reports_the_conflict_it_is() -> None:
    """No exception, and the payload names the constraint the user must change.

    The contract in ``geometry.sketch.solver`` is explicit that solve OUTCOMES
    belong in ``status`` and exceptions are reserved for malformed INPUT. This
    sketch is not malformed — every reference resolves and every constraint is
    type-valid — it simply has no non-degenerate solution, which is exactly what
    ``conflicting`` means and what ``conflicting_constraints`` is for.
    """
    sketch = _annihilated_circle()
    solved = SOLVER.solve(sketch)

    assert solved.status == "conflicting"
    # The documented conflicting/diverged contract: the input, untouched.
    assert [e.model_dump() for e in solved.entities] == [
        e.model_dump() for e in sketch.entities
    ]
    # Index 0 is the tangency, which is the constraint with nowhere to go.
    assert solved.conflicting_constraints == [0]


def test_a_negative_solved_radius_is_the_same_circle_and_still_solves() -> None:
    """The half that must NOT be refused: a sign, not a degeneracy.

    Refusing this would reject a solvable sketch, which is a worse defect than
    the crash it replaces — the model becomes unbuildable and nothing tells the
    user why. The evidence is the residual, measured from the shipped entities
    by the same predicate the payload gate uses.

    Note WHERE the negative radius appears, because it is why this reads as an
    ordinary sketch: the plain solve reaches ``-14.198539866496207`` and the
    settle's first read-back is what used to raise there, mid-trial. With the
    read-back able to answer, the settle goes on to do its job and hands the
    author their OWN 5.946 mm radius back, moving the centre instead (SOLVE-1) —
    external tangency at ``d = 43.595 + 5.946``. So the assertion here is the
    property, not the intermediate value: this sketch has a positive-radius
    answer and the service must ship one.
    """
    sketch = _internally_tangent_circles()
    solved = SOLVER.solve(sketch)

    assert solved.status in ("converged", "underconstrained")
    radii = {e.id: e.radius for e in solved.entities if isinstance(e, SketchCircle)}
    assert radii["e2"] == pytest.approx(43.595, abs=SATISFIED_TOL_MM)
    assert radii["e3"] == pytest.approx(5.946, abs=SATISFIED_TOL_MM)
    assert all(radius >= DEGENERATE_RADIUS_MM for radius in radii.values())

    submitted = {
        (entity.id, "center"): (entity.center.x, entity.center.y)
        for entity in sketch.entities
        if isinstance(entity, SketchCircle)
    }
    assert (
        worst_residual(sketch.constraints, solved.entities, submitted, {1: 43.595}, {})
        <= SATISFIED_TOL_MM
    )


def test_the_solved_geometry_is_still_bitwise_deterministic() -> None:
    """RESEARCH §9, asserted over both halves — ``abs`` must not add noise."""
    for sketch in (_annihilated_circle(), _internally_tangent_circles()):
        first = SOLVER.solve(sketch)
        second = SOLVER.solve(sketch)
        assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.parametrize(
    ("solved", "expected"),
    [
        # A sign is a branch selection, not a degeneracy: same circle back.
        (-14.198539866496207, 14.198539866496207),
        (14.198539866496207, 14.198539866496207),
        # Annihilated, both sides of zero and zero itself. The two femtometre
        # cases are the point of the whole constant: the corpus shipped
        # +8.9e-16 under a status saying it solved (trial 926) and raised a 500
        # on -1.5e-15 (trial 1593). One defect, two sides of a float-noise seam.
        (0.0, 7.741),
        (-0.0, 7.741),
        (8.881784197001252e-16, 7.741),
        (-1.5192166791387265e-15, 7.741),
        # The threshold itself, from both sides.
        (DEGENERATE_RADIUS_MM, DEGENERATE_RADIUS_MM),
        (DEGENERATE_RADIUS_MM / 2, 7.741),
        # Not a number is not a circle either, and the comparison it fails is
        # the one that sends it down the degenerate path.
        (math.nan, 7.741),
    ],
)
def test_the_shippable_radius_rule_at_its_boundaries(
    solved: float, expected: float
) -> None:
    assert _shippable_radius(solved, 7.741) == expected


def test_the_user_gets_a_typed_feature_error_and_not_a_500() -> None:
    """The whole point of the ticket, asserted where the user actually is.

    ``_evaluate_sketch`` catches only ``SketchDefinitionError``, so the escaping
    ``ValidationError`` was an untyped 500 — a dead end with no explanation
    attached, which is worse for trust than a wrong answer that is at least
    labelled. It is now the SAME typed outcome any unsatisfiable sketch gets:
    HTTP 200, feature status ``error``, code ``sketch_conflicting``, a message
    naming the constraint index, and the typed ``sketch_diagnosis`` the sketcher
    reads by field. No new error code and no contract change — a sketch whose
    constraints admit only a degenerate solution IS a conflicting sketch.
    """
    sketch = _annihilated_circle()
    payload: dict[str, Any] = {
        "part_id": str(uuid.UUID("00000000-0000-0000-0000-0000000000c0")),
        "tree_version": 1,
        "features": [
            {
                "id": str(uuid.UUID("00000000-0000-0000-0000-0000000000c1")),
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": "XY"},
                        "entities": [e.model_dump() for e in sketch.entities],
                        "constraints": [c.model_dump() for c in sketch.constraints],
                    },
                },
            }
        ],
    }
    response = TestClient(app).post("/api/v1/evaluate", json=payload)

    assert response.status_code == 200, response.text
    feature = response.json()["features"][0]
    assert feature["status"] == "error"
    assert feature["error"]["code"] == "sketch_conflicting"
    # The tangency, NAMED — not merely "something is wrong with your sketch".
    assert "[0]" in feature["error"]["message"]
    assert feature["error"]["sketch_diagnosis"] is not None


def test_reverting_the_magnitude_rule_to_the_dto_rule_reopens_the_silent_half() -> None:
    """The mutation this test file exists to refuse, stated as a property.

    Deferring to ``SketchCircle``'s own ``gt=0`` — the obvious minimal fix —
    stops the crash and leaves the silent half wide open: ``8.9e-16 > 0`` is
    True, so a circle that is not there ships under a status saying it solved.
    Asserting the two agree at the DTO boundary and DISAGREE below it is what
    makes ``DEGENERATE_RADIUS_MM`` load-bearing rather than decorative.
    """
    annihilated = 8.881784197001252e-16
    assert annihilated > 0.0, "the DTO's own rule admits this radius"
    assert _shippable_radius(annihilated, 7.741) != annihilated
    real = 3.311
    assert _shippable_radius(real, 7.741) == real
