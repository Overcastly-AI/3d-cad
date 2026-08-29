"""ARC-DEGENERATE-1 — what happens when a solve drives an arc onto its own centre.

The defect this closes is SOLVE-CRASH-1's shape with the loud half removed, and
that is the whole reason it needed its own ticket. A circle carries its radius as
a field constrained ``gt=0``, so annihilating one built a DTO the DTO refused and
a ``ValidationError`` escaped as a 500 — noisy, findable, fixed. An arc carries
``center``/``start``/``end`` and DERIVES its radius from them, so annihilating one
builds a perfectly valid DTO: no exception, and — this is the part that made it
invisible — a residual of **zero**, because a constraint satisfied by putting a
point on a point is satisfied *exactly*. Every property in PBT-1's sweep agreed
with every one of them.

What pointed at it was an ASYMMETRY rather than a failure:
``_GcsBuild._add_entity`` raises ``SketchDefinitionError`` on an arc whose start
coincides with its centre, so **the solver refused to accept a shape it would
happily emit**. Measured on the same corpus that found the circle defect: **27 of
2000 sketches shipped an annihilated arc**, 25 under ``overconstrained`` and 2
under ``underconstrained``, against 12 crashes for the circle.

Forced, or a bad branch?
------------------------
SOLVE-CRASH-1's prior question, asked again because its answer there was *both*
and one rule for all twelve would have been wrong. Two independent probes per
case — pin the radius to a value any non-degenerate solution could reach, and
re-solve from 8 configurations with the arc pushed 7 mm off the degenerate one —
put it at **26 forced, 1 branch**. Sixteen of the 26 minimise to a SINGLE
constraint, ``coincident`` between an arc's own centre and its own endpoint,
which is exactly the shape ``_add_entity`` refuses on input, authored as a
constraint instead of as coordinates.

The one exception is recorded rather than fixed
(:func:`test_the_branch_case_is_a_recorded_live_limit_not_a_forced_collapse`):
trial 1906's tangency admits ``r2 = 0`` and ``r2 = 2 * r1``, and the solver takes
the first. That sketch is SOLVABLE, so calling it ``conflicting`` is also wrong —
just less wrong than shipping a void, and a fix for it is a change to branch
selection, not to a payload gate.

Two thresholds, and why they differ
-----------------------------------
The arc floor is :data:`~geometry.sketch.planegcs_solver.DEGENERATE_ARC_RADIUS_MM`
(``= SATISFIED_TOL_MM``), NOT the circle's ``DEGENERATE_RADIUS_MM``. A circle's
radius is the solver's own parameter and lands at ``0.0``; an arc's is a distance
between two independently-solved points and carries the DogLeg residue of three
parameter pairs. Trial 458 is the measurement that settled it and the reason the
constant is not decorative — see
:func:`test_the_circle_floor_is_too_narrow_for_a_derived_arc_radius`.
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
    MidpointConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchArc,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    TangentConstraint,
)
from geometry.sketch.planegcs_solver import (
    DEGENERATE_ARC_RADIUS_MM,
    DEGENERATE_RADIUS_MM,
    SATISFIED_TOL_MM,
    _shippable_arc_points,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.solver import SketchDefinitionError

SOLVER: SketchSolver = PlanegcsSketchSolver()


def arc_radius(entity: SketchArc) -> float:
    """The arc's radius as every consumer derives it — the WORST endpoint.

    ``max``, matching :func:`_shippable_arc_points`: an arc is annihilated only
    when BOTH endpoints have reached the centre. One endpoint there and the other
    10 mm away is a different defect (an arc that is not internally an arc) and
    ``residual.entity_residual`` is what catches that one.
    """
    return max(
        math.hypot(entity.start.x - entity.center.x, entity.start.y - entity.center.y),
        math.hypot(entity.end.x - entity.center.x, entity.end.y - entity.center.y),
    )


def smallest_arc(entities: list[SketchEntity]) -> float:
    return min(
        (arc_radius(e) for e in entities if isinstance(e, SketchArc)),
        default=math.inf,
    )


def _arc_pinned_to_its_own_centre() -> SketchDefinition:
    """PBT-1 trial 394, minimised to ONE entity and ONE constraint.

    The most direct statement of the ticket there is: a single ``coincident``
    between an arc's ``end`` and its own ``center``. It is authorable in one
    gesture — drag an endpoint onto the centre mark and accept the snap — and it
    is precisely the configuration ``_add_entity`` rejects when it arrives as
    coordinates instead of as a constraint. ``r = 0`` is the only solution; there
    is nothing else for the solver to find.

    Before this fix: ``status="overconstrained"``, ``conflicting_constraints=[]``,
    and an arc of radius ``4e-15`` mm in the payload.
    """
    return SketchDefinition(
        entities=[
            SketchArc(
                id="e0",
                kind="arc",
                center=Point2D(x=18.255, y=-26.667),
                start=Point2D(x=15.661275727566887, y=-28.443887840746097),
                end=Point2D(x=20.228738912443127, y=-29.11426187922499),
            )
        ],
        constraints=[
            CoincidentConstraint(
                kind="coincident",
                a=EntityPointRef(entity="e0", point="end"),
                b=EntityPointRef(entity="e0", point="center"),
            )
        ],
    )


def _arc_tangent_to_a_line_through_its_centre() -> SketchDefinition:
    """PBT-1 trial 981, minimised: the circle defect's own shape, on an arc.

    ``midpoint`` puts the arc's centre ON the line and ``tangent`` requires the
    centre-to-line distance to equal the radius, so the distance is zero and the
    radius must be too. This is the identical construction that annihilated nine
    circles in SOLVE-CRASH-1 — which is the point of keeping it: the same
    geometry got a typed ``conflicting`` for a circle and a silent void for an
    arc, purely because one DTO has a radius field and the other does not.

    Before this fix: ``status="underconstrained"``, ``conflicting_constraints=[]``,
    and an arc of radius ``0.0`` in the payload.
    """
    return SketchDefinition(
        entities=[
            SketchArc(
                id="e0",
                kind="arc",
                center=Point2D(x=18.518, y=-3.727),
                start=Point2D(x=26.318110564032978, y=5.141934332199172),
                end=Point2D(x=6.707350048563738, y=-3.8179325279458083),
            ),
            SketchLine(
                id="e1",
                kind="line",
                start=Point2D(x=1.601, y=13.17),
                end=Point2D(x=9.984, y=-18.858),
            ),
        ],
        constraints=[
            MidpointConstraint(
                kind="midpoint",
                point=EntityPointRef(entity="e0", point="center"),
                line="e1",
            ),
            TangentConstraint(kind="tangent", a="e1", b="e0"),
        ],
    )


def _tangent_arcs_with_a_non_degenerate_branch() -> SketchDefinition:
    """PBT-1 trial 1906, minimised: the one case that is NOT forced.

    ``e2``'s centre sits on ``e1`` (coincident with its endpoint), so the
    centre-to-centre distance is ``r1``; tangency then admits ``r2 = 0`` and
    ``r2 = 2 * r1``. Both are real solutions and the solver takes the degenerate
    one from the author's own starting configuration.

    Before this fix: ``status="underconstrained"`` with ``e2`` at ``4e-14`` mm.
    """
    return SketchDefinition(
        entities=[
            SketchArc(
                id="e1",
                kind="arc",
                center=Point2D(x=-7.113, y=9.035),
                start=Point2D(x=-21.54076492181796, y=6.684356819770545),
                end=Point2D(x=1.3201461362484457, y=-2.9051830071686062),
            ),
            SketchArc(
                id="e2",
                kind="arc",
                center=Point2D(x=-25.201, y=0.176),
                start=Point2D(x=-14.970805091332478, y=17.009131501021226),
                end=Point2D(x=-8.431121379790337, y=-10.157555780244998),
            ),
        ],
        constraints=[
            CoincidentConstraint(
                kind="coincident",
                a=EntityPointRef(entity="e2", point="center"),
                b=EntityPointRef(entity="e1", point="end"),
            ),
            TangentConstraint(kind="tangent", a="e1", b="e2"),
        ],
    )


def test_a_solve_that_annihilates_an_arc_reports_the_conflict_it_is() -> None:
    """No void in the payload, and the constraint the user must change is NAMED.

    The ``SketchSolver`` contract puts solve OUTCOMES in ``status`` and reserves
    exceptions for malformed INPUT; this sketch is not malformed, it simply has
    no non-degenerate solution, which is what ``conflicting`` means. Nothing new
    decides that — ``_shippable_arc_points`` hands ``read_back`` an arc carrying
    the author's own radius, which then fails the very constraint that annihilated
    it, and ``_violated_constraints`` (already the payload gate) does the rest.
    """
    sketch = _arc_pinned_to_its_own_centre()
    solved = SOLVER.solve(sketch)

    assert solved.status == "conflicting"
    # The documented conflicting/diverged contract: the input, untouched.
    assert [e.model_dump() for e in solved.entities] == [
        e.model_dump() for e in sketch.entities
    ]
    # Index 0 is the coincident, i.e. the one constraint in the sketch.
    assert solved.conflicting_constraints == [0]


def test_the_same_shape_on_an_arc_and_on_a_circle_get_the_same_answer() -> None:
    """The asymmetry the ticket is named for, asserted as an equality.

    ``tangent`` to a line the centre is pinned to annihilated nine CIRCLES in
    SOLVE-CRASH-1 and got a typed ``conflicting`` with the tangency named. The
    identical construction on an ARC shipped a void under a status saying it
    solved. One service may not classify one degeneracy two ways depending on
    which DTO happens to carry a radius field.
    """
    sketch = _arc_tangent_to_a_line_through_its_centre()
    solved = SOLVER.solve(sketch)

    assert solved.status == "conflicting"
    assert [e.model_dump() for e in solved.entities] == [
        e.model_dump() for e in sketch.entities
    ]
    # Index 1 is the tangency — the constraint with nowhere to go, exactly as
    # the circle case reports it.
    assert solved.conflicting_constraints == [1]


def test_no_payload_ships_an_arc_that_is_not_there() -> None:
    """The property, over both forced fixtures: a shipped arc is a real arc.

    Stated separately from the status assertions because it is the thing that
    actually matters downstream — ``kernel/extrude.py`` turns these three points
    into an OCCT edge, and an edge of radius 4e-14 mm is not geometry at any
    tolerance this project uses (the kernel's linear tolerance is 1e-4 mm).
    """
    for sketch in (
        _arc_pinned_to_its_own_centre(),
        _arc_tangent_to_a_line_through_its_centre(),
        _tangent_arcs_with_a_non_degenerate_branch(),
    ):
        solved = SOLVER.solve(sketch)
        assert smallest_arc(solved.entities) >= DEGENERATE_ARC_RADIUS_MM


def test_the_branch_case_is_a_recorded_live_limit_not_a_forced_collapse() -> None:
    """RECORDED LIVE LIMIT: this sketch is SOLVABLE and we answer ``conflicting``.

    Said out loud because the alternative is letting a known-wrong answer pass as
    a fix. 26 of the 27 annihilated arcs in the corpus have no non-degenerate
    solution at all, so ``conflicting`` is simply true of them. This one does
    have one — the tangency admits ``r2 = 2 * r1`` as well as ``r2 = 0`` — and the
    solver takes the degenerate branch from the author's own start. This change
    turns a silent void into a wrong-but-legible refusal, which is an improvement
    and is not the fix; choosing the branch is ARC-BRANCH-1.

    The proof that a real solution exists is re-derived here rather than
    asserted: the same constraint set, solved from a configuration with ``e2``
    pushed 7 mm away, reaches ``r2 = 2 * r1`` at a residual of ``0.0``. **If this
    test starts failing because the plain solve now finds that branch, the gap is
    CLOSED — delete this test and say so in the commit.** A recorded limit that
    can only fail in one direction stops being a record the moment it is lifted.
    """
    sketch = _tangent_arcs_with_a_non_degenerate_branch()
    solved = SOLVER.solve(sketch)
    assert solved.status == "conflicting"

    # The non-degenerate branch, reached from a pushed start. Four of the eight
    # directions find it; one is enough to prove the constraint set admits it.
    # Only the START POSE moves — the constraints are identical, so what this
    # shows is a different branch of the SAME problem, not a different problem.
    entities: list[SketchEntity] = []
    for entity in sketch.entities:
        moved = entity.model_copy(deep=True)
        if moved.id == "e2" and isinstance(moved, SketchArc):
            moved.center = Point2D(x=moved.center.x + 7.0, y=moved.center.y)
        entities.append(moved)
    pushed = SketchDefinition(entities=entities, constraints=list(sketch.constraints))
    from_branch = SOLVER.solve(pushed)
    assert from_branch.status in ("converged", "underconstrained")
    radii = {
        e.id: arc_radius(e) for e in from_branch.entities if isinstance(e, SketchArc)
    }
    assert radii["e2"] == pytest.approx(2.0 * radii["e1"], abs=SATISFIED_TOL_MM)
    assert radii["e2"] > 1.0, "the branch this sketch also admits is not degenerate"


def test_an_arc_that_arrives_degenerate_is_still_refused_as_malformed_input() -> None:
    """The INPUT side of the boundary keeps its exception — deliberately.

    The ticket's framing invites making the two sides symmetric, and they now are
    in the quantity they test (both ask ``< DEGENERATE_ARC_RADIUS_MM``) but NOT in
    the mechanism, because the ``SketchSolver`` contract distinguishes them: an
    arc that ARRIVES with its start on its centre is malformed input — there is no
    ``atan2`` angle to build a gcs arc from — while an arc a SOLVE drives there is
    a well-formed sketch with an unsatisfiable constraint set. Different things,
    different reports, same threshold.
    """
    degenerate = SketchDefinition(
        entities=[
            SketchArc(
                id="e0",
                kind="arc",
                center=Point2D(x=4.0, y=4.0),
                start=Point2D(x=4.0, y=4.0),
                end=Point2D(x=4.0, y=4.0),
            )
        ],
        constraints=[],
    )
    with pytest.raises(SketchDefinitionError, match="degenerate"):
        SOLVER.solve(degenerate)


def test_the_input_refusal_is_a_magnitude_test_not_an_equality() -> None:
    """``radius == 0.0`` admitted an arc of radius 1e-14 mm, and did until now.

    The same float-noise seam SOLVE-CRASH-1 documented, on the other side of the
    boundary: an arc whose start is a femtometre off its centre has ``atan2``
    angles that are pure noise, and it reaches the kernel as an edge ten orders
    under the 1e-4 mm linear tolerance. The old test was ``== 0.0``, so this arc
    sailed through; the negative control is that it now does not.
    """
    barely = SketchDefinition(
        entities=[
            SketchArc(
                id="e0",
                kind="arc",
                center=Point2D(x=4.0, y=4.0),
                start=Point2D(x=4.0 + 1e-14, y=4.0),
                end=Point2D(x=4.0, y=4.0 + 1e-14),
            )
        ],
        constraints=[],
    )
    assert math.hypot(1e-14, 0.0) > 0.0, "the old ``== 0.0`` rule admits this radius"
    with pytest.raises(SketchDefinitionError, match="degenerate"):
        SOLVER.solve(barely)


def test_the_circle_floor_is_too_narrow_for_a_derived_arc_radius() -> None:
    """Why there are two constants, pinned so nobody collapses them into one.

    This is the measurement the fix itself produced and the earlier draft missed.
    Every annihilated arc in the corpus sits at or below ``4.0e-14`` mm, so the
    circle's ``1e-9`` floor appeared to clear the whole population by five orders.
    It does not: with ``_shippable_arc_points`` in place the settle correctly
    stops holding anything on such a sketch, and the settle had been what drove
    PBT-1 trial 458's arc from the raw solve's ``4.5e-9`` mm down to ``0.0``. Set
    at ``1e-9``, this fix therefore MOVED one case across its own threshold and
    shipped it under ``overconstrained``.

    The general rule, which is why this is a test and not a comment: **a floor
    measured from a population the fix itself perturbs must be re-measured after
    the fix.** ``4.5e-9`` mm is planegcs's convergence residue, not float noise,
    which is why the arc floor is the tolerance at which this module already
    declares a constraint satisfied.
    """
    assert DEGENERATE_ARC_RADIUS_MM == SATISFIED_TOL_MM
    assert DEGENERATE_ARC_RADIUS_MM > DEGENERATE_RADIUS_MM

    residue = 4.514675268215401e-09  # trial 458, measured
    assert residue > DEGENERATE_RADIUS_MM, "the circle floor admits this arc"
    assert residue < DEGENERATE_ARC_RADIUS_MM, "the arc floor refuses it"

    submitted = SketchArc(
        id="e0",
        kind="arc",
        center=Point2D(x=0.0, y=0.0),
        start=Point2D(x=3.0, y=0.0),
        end=Point2D(x=0.0, y=3.0),
    )
    start, end = _shippable_arc_points(
        (-32.008, -34.477),
        (-32.008 + residue, -34.477),
        (-32.008, -34.477 + residue),
        submitted,
    )
    assert (start.x, start.y) == (-32.008 + 3.0, -34.477)
    assert (end.x, end.y) == (-32.008, -34.477 + 3.0)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # An ordinary arc passes through untouched, bit for bit.
        ((10.0, 0.0), (0.0, 10.0), ((10.0, 0.0), (0.0, 10.0))),
        # Annihilated: the author's arc, TRANSLATED to the solved centre. The
        # submitted arc below is centred at (0, 0), so its offsets are its own
        # coordinates and the expected points are the solved centre plus them.
        ((0.0, 0.0), (0.0, 0.0), ((3.0, 0.0), (0.0, 3.0))),
        # Both sides of the threshold, from the corpus's own magnitudes.
        ((4e-14, 0.0), (0.0, 4e-14), ((3.0, 0.0), (0.0, 3.0))),
        ((4.5e-9, 0.0), (0.0, 4.5e-9), ((3.0, 0.0), (0.0, 3.0))),
        (
            (DEGENERATE_ARC_RADIUS_MM, 0.0),
            (0.0, DEGENERATE_ARC_RADIUS_MM),
            ((DEGENERATE_ARC_RADIUS_MM, 0.0), (0.0, DEGENERATE_ARC_RADIUS_MM)),
        ),
        # ONE endpoint collapsed is NOT this defect: an arc whose endpoints
        # disagree about their own centre is caught by entity_residual, and
        # substituting here would replace it with a consistent arc and hide the
        # inconsistency that names it. ``max`` is what keeps it out.
        ((0.0, 0.0), (0.0, 10.0), ((0.0, 0.0), (0.0, 10.0))),
        # Not a number is not on a circle either; the comparison it fails is the
        # one that sends it down the degenerate path.
        ((math.nan, 0.0), (0.0, 0.0), ((3.0, 0.0), (0.0, 3.0))),
    ],
)
def test_the_shippable_arc_rule_at_its_boundaries(
    start: tuple[float, float],
    end: tuple[float, float],
    expected: tuple[tuple[float, float], tuple[float, float]],
) -> None:
    submitted = SketchArc(
        id="e0",
        kind="arc",
        center=Point2D(x=0.0, y=0.0),
        start=Point2D(x=3.0, y=0.0),
        end=Point2D(x=0.0, y=3.0),
    )
    got_start, got_end = _shippable_arc_points((0.0, 0.0), start, end, submitted)
    assert ((got_start.x, got_start.y), (got_end.x, got_end.y)) == expected


def test_the_solved_geometry_is_still_bitwise_deterministic() -> None:
    """RESEARCH §9, over every fixture here — the substitution must add no noise."""
    for sketch in (
        _arc_pinned_to_its_own_centre(),
        _arc_tangent_to_a_line_through_its_centre(),
        _tangent_arcs_with_a_non_degenerate_branch(),
    ):
        first = SOLVER.solve(sketch)
        second = SOLVER.solve(sketch)
        assert first.model_dump_json() == second.model_dump_json()


def test_the_user_gets_a_typed_conflict_and_not_a_silent_void() -> None:
    """The outcome asserted where the user actually is, through the real route.

    No new error code and no contract change, exactly as SOLVE-CRASH-1 needed
    none: a sketch whose constraints admit only a degenerate solution IS a
    conflicting sketch. HTTP 200, feature status ``error``, code
    ``sketch_conflicting``, the constraint index in the message, and the typed
    ``sketch_diagnosis`` beside it — so the sketch stays editable instead of
    handing the next feature an arc that is not there.
    """
    sketch = _arc_pinned_to_its_own_centre()
    payload: dict[str, Any] = {
        "part_id": str(uuid.UUID("00000000-0000-0000-0000-0000000000a0")),
        "tree_version": 1,
        "features": [
            {
                "id": str(uuid.UUID("00000000-0000-0000-0000-0000000000a1")),
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
    assert "[0]" in feature["error"]["message"]
    assert feature["error"]["sketch_diagnosis"] is not None
