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

The one exception was recorded rather than fixed: trial 1906's tangency admits
``r2 = 0`` and ``r2 = 2 * r1``, and the solver took the first. That sketch is
SOLVABLE, so calling it ``conflicting`` was also wrong — just less wrong than
shipping a void, and the fix for it is a change to branch selection, not to a
payload gate.

**ARC-BRANCH-1 (2026-09-04) closed that, and this file carries it too**, because
the two tickets are one story: the collapse is the defect and the branch is what
the collapse was hiding. The recorded-limit test is deleted, as its own docstring
required, and replaced by
:func:`test_the_branch_case_solves_to_its_non_degenerate_branch`. When the plain
solve annihilates an entity it has produced geometry no payload can carry — never
an answer the author is being offered — so the solver asks ONCE more from the
author's own pose with only the collapsed entity relocated to where the solve put
it, and prefers that answer only if it is shippable where the first was not
(:func:`~geometry.sketch.planegcs_solver._restarted_without_the_collapse`). Over
PBT-1's corpus that is taken on **2 of the 38** solves that annihilate something
and refused on the other 36; census: solvable 1326 -> **1328**, conflicting
314 -> **312**, violated still 0, annihilated still 0. The second of the two is a
CIRCLE (:func:`_tangent_circle_and_arc_with_a_non_degenerate_branch`) minimising
to the same two constraints — this file's asymmetry, one layer up.

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
    SketchCircle,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    TangentConstraint,
)
from geometry.sketch.angles import angle_frames
from geometry.sketch.expression import evaluate_driving_dimensions
from geometry.sketch.planegcs_solver import (
    DEGENERATE_ARC_RADIUS_MM,
    DEGENERATE_RADIUS_MM,
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
    _restarted_without_the_collapse,  # pyright: ignore[reportPrivateUsage]
    _shippable_arc_points,  # pyright: ignore[reportPrivateUsage]
    _submitted_points,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import worst_residual
from geometry.sketch.solver import SketchDefinitionError
from planegcs import SolveStatus as GcsSolveStatus

SOLVER: SketchSolver = PlanegcsSketchSolver()


def worst_residual_of(sketch: SketchDefinition, shipped: list[SketchEntity]) -> float:
    """The worst constraint/entity residual of a payload against its own sketch.

    ``fixed`` pins to the coordinate the AUTHOR submitted, so its reference is
    the input sketch — measured against the solved entities it would be trivially
    satisfied, which is the mistake that makes a residual check self-verifying.
    """
    submitted = _submitted_points(sketch.entities)
    return worst_residual(
        sketch.constraints,
        shipped,
        submitted,
        evaluate_driving_dimensions(sketch.constraints),
        angle_frames(sketch.constraints, submitted),
    )


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
    """PBT-1 trial 1906, minimised: the one annihilated ARC that is NOT forced.

    ``e2``'s centre sits on ``e1`` (coincident with its endpoint), so the
    centre-to-centre distance is ``r1``; tangency then admits ``r2 = 0`` and
    ``r2 = 2 * r1``. Both are real solutions and the solver took the degenerate
    one from the author's own starting configuration.

    Before ARC-DEGENERATE-1: ``status="underconstrained"`` with ``e2`` at
    ``4e-14`` mm. After it and before ARC-BRANCH-1: ``conflicting``, which is
    also wrong — the sketch solves. Now: ``underconstrained`` with
    ``r2 = 29.236`` mm.
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


def _tangent_circle_and_arc_with_a_non_degenerate_branch() -> SketchDefinition:
    """PBT-1 trial 1593, minimised: the same branch shape wearing the other DTO.

    Found by ARC-BRANCH-1 rather than authored — asking "does a restart rescue
    this?" of every annihilated entity in the corpus turned up two cases, and this
    is the one nobody had separated out. It minimises to the SAME two constraints
    as trial 1906 (``coincident`` from one curve's centre to the other's endpoint,
    plus ``tangent``), which is why it is here rather than in a file of its own:
    it is ARC-DEGENERATE-1's own asymmetry — one construction classified two ways
    by which DTO carries a radius field — reappearing at the branch layer.

    ``e1``'s centre sits on ``e3``'s endpoint, so tangency admits ``r1 = 0`` and
    ``r1 = 2 * r3``. Before ARC-BRANCH-1 this shipped ``conflicting``; SOLVE-CRASH-1
    had counted it among the annihilated circles it called forced.
    """
    return SketchDefinition(
        entities=[
            SketchCircle(
                id="e1",
                kind="circle",
                center=Point2D(x=16.067, y=-22.168),
                radius=17.285,
            ),
            SketchArc(
                id="e3",
                kind="arc",
                center=Point2D(x=-30.228, y=-16.427),
                start=Point2D(x=-25.1943139308245, y=-18.707061524825264),
                end=Point2D(x=-35.56922936292508, y=-17.844019722031756),
            ),
        ],
        constraints=[
            CoincidentConstraint(
                kind="coincident",
                a=EntityPointRef(entity="e1", point="center"),
                b=EntityPointRef(entity="e3", point="end"),
            ),
            TangentConstraint(kind="tangent", a="e3", b="e1"),
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
        _tangent_circle_and_arc_with_a_non_degenerate_branch(),
    ):
        solved = SOLVER.solve(sketch)
        assert smallest_arc(solved.entities) >= DEGENERATE_ARC_RADIUS_MM


def test_the_branch_case_solves_to_its_non_degenerate_branch() -> None:
    """ARC-BRANCH-1 — the recorded live limit, LIFTED, and asserted where it was.

    This test replaces ARC-DEGENERATE-1's
    ``test_the_branch_case_is_a_recorded_live_limit_not_a_forced_collapse``, whose
    own docstring said to delete it the moment the plain solve found this branch:
    *"a recorded limit that can only fail in one direction stops being a record the
    moment it is lifted."* It is lifted. The sketch shipped a void under
    ``underconstrained`` before ARC-DEGENERATE-1 and a wrong ``conflicting`` after
    it; both were wrong, because ``r2 = 2 * r1`` exists at a residual of ``0.0``,
    and that is now the answer.

    Note the number is not merely non-degenerate, it is the one the old limit
    NAMED: ``r2 = 29.236`` mm, twice the author's own ``e1``.
    """
    sketch = _tangent_arcs_with_a_non_degenerate_branch()
    solved = SOLVER.solve(sketch)

    assert solved.status == "underconstrained"
    radii = {e.id: arc_radius(e) for e in solved.entities if isinstance(e, SketchArc)}
    assert radii["e2"] == pytest.approx(2.0 * radii["e1"], abs=SATISFIED_TOL_MM)
    assert radii["e2"] == pytest.approx(29.236, abs=SATISFIED_TOL_MM)
    assert radii["e2"] >= DEGENERATE_ARC_RADIUS_MM
    assert worst_residual_of(sketch, solved.entities) <= SATISFIED_TOL_MM


def test_the_branch_answer_still_hands_the_author_back_their_free_geometry() -> None:
    """SOLVE-1's property over ARC-BRANCH-1's answer, and it is what picks the pose.

    ``e1`` has no constraint on its size or position — every one of this sketch's
    7 free degrees of freedom is the author's — so a restart that finds the branch
    at the cost of resizing ``e1`` has traded one defect for a quieter one.

    This is the assertion that discriminates the two restart poses that were
    built, so it is the reason the design is what it is rather than a restatement
    of the one above. Restarting from the WHOLE solved answer with the collapse
    undone reaches the branch too — and carries over the first solve's unforced
    drag on ``e1`` (r 14.618 -> 8.242, chord reversed), after which the settle's
    correct recovery of ``e1`` is discarded by SETTLE-2's orientation guard
    because the baseline it is judged against is itself reversed relative to the
    author. Measured: that pose ships ``r1 = 10.029``, this one ships the author's
    own arc. Restarting from the AUTHOR's pose with only the collapsed entity
    relocated keeps SETTLE-2's premise — *the plain solve is a walk from the
    author's own values* — true, which is what makes the guard measure what it was
    designed to measure.

    The status assertion is not decoration and was added after a mutation run
    showed why: a ``conflicting`` payload returns the author's entities UNTOUCHED,
    so without it this test passes vacuously against a solver with the restart
    ripped out — the very failure mode it exists to observe. It has to say which
    payload it is reading before it says what is in it.
    """
    sketch = _tangent_arcs_with_a_non_degenerate_branch()
    solved = SOLVER.solve(sketch)
    assert solved.status == "underconstrained"

    submitted = next(e for e in sketch.entities if e.id == "e1")
    shipped = next(e for e in solved.entities if e.id == "e1")
    assert isinstance(submitted, SketchArc) and isinstance(shipped, SketchArc)
    for before, after in (
        (submitted.center, shipped.center),
        (submitted.start, shipped.start),
        (submitted.end, shipped.end),
    ):
        assert after.x == pytest.approx(before.x, abs=SATISFIED_TOL_MM)
        assert after.y == pytest.approx(before.y, abs=SATISFIED_TOL_MM)


def test_the_branch_is_found_by_the_RESTART_and_not_by_the_plain_solve() -> None:
    """The negative control, stated without reaching for a monkeypatch.

    The two tests above are only evidence for ARC-BRANCH-1 if the FIRST DogLeg
    pass still walks into the collapse — otherwise they would be green against a
    solver that never needed the restart, and reverting it would leave them green
    too. So this asserts the defect is still there underneath: one solve from the
    author's own configuration annihilates ``e2``, exactly as ARC-DEGENERATE-1
    measured it, and everything above is therefore produced by the restart.
    """
    sketch = _tangent_arcs_with_a_non_degenerate_branch()
    build = _GcsBuild(sketch, evaluate_driving_dimensions(sketch.constraints))

    assert build.gcs.solve() in (GcsSolveStatus.Success, GcsSolveStatus.Converged)
    assert build.annihilated_entity_ids() == ["e2"]


def test_the_same_branch_shape_on_a_circle_is_found_too() -> None:
    """PBT-1 trial 1593, minimised — and the reason the restart is not arc-only.

    ARC-DEGENERATE-1's headline is an ASYMMETRY: one construction got a typed
    ``conflicting`` for a circle and a silent void for an arc, purely because one
    DTO carries a radius field. This is the same asymmetry one layer up. The
    minimal form here is the SAME two constraints as trial 1906 — a ``coincident``
    putting one curve's centre on the other's endpoint, plus a ``tangent`` — with
    a circle where 1906 has an arc, and it had been shipping ``conflicting`` for
    the same reason: ``r = 0`` and ``r = 2 * r_arc`` both satisfy it, and DogLeg
    took the first from the author's own start.

    It was found by asking the restart's own question over PBT-1's corpus rather
    than by looking for it: of the 38 solves there that annihilate an entity, 36
    are FORCED and 2 have a real branch — one arc (1906) and this circle. Had the
    mechanism been narrowed to arcs, to match the ticket, this one would still be
    refusing a sketch that solves.
    """
    sketch = _tangent_circle_and_arc_with_a_non_degenerate_branch()
    solved = SOLVER.solve(sketch)

    assert solved.status == "underconstrained"
    circle = next(e for e in solved.entities if isinstance(e, SketchCircle))
    arc = next(e for e in solved.entities if isinstance(e, SketchArc))
    assert circle.radius == pytest.approx(2.0 * arc_radius(arc), abs=SATISFIED_TOL_MM)
    assert circle.radius >= DEGENERATE_RADIUS_MM
    assert worst_residual_of(sketch, solved.entities) <= SATISFIED_TOL_MM


def test_a_forced_collapse_is_not_rescued_by_the_restart() -> None:
    """The other side of the boundary: 36 of 38 have no branch, and stay refused.

    Asserted on the restart itself rather than only on the status, because the
    two fixtures' ``conflicting`` is what ARC-DEGENERATE-1 already shipped and
    would stay green if the restart silently stopped running at all. What is new
    and worth pinning is that the restart RUNS on them and REFUSES: there is no
    non-degenerate solution to find, so the second solve returns to the same
    collapse and the author keeps the honest refusal with the constraint named.
    """
    for sketch in (
        _arc_pinned_to_its_own_centre(),
        _arc_tangent_to_a_line_through_its_centre(),
    ):
        driving_values = evaluate_driving_dimensions(sketch.constraints)
        build = _GcsBuild(sketch, driving_values)
        assert build.gcs.solve() in (GcsSolveStatus.Success, GcsSolveStatus.Converged)
        assert build.annihilated_entity_ids(), "the fixture no longer collapses"
        assert _restarted_without_the_collapse(build, driving_values) is None


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
    """RESEARCH §9, over every fixture here — the substitution must add no noise.

    Load-bearing for ARC-BRANCH-1 as well as for the substitution: the restart is
    a SECOND solve whose start pose is computed from the FIRST one's answer, so it
    is exactly the shape of change that could make an answer depend on solve
    history. It cannot here — the pose is a pure function of the sketch, there is
    no seed, no clock and no search — and this is the assertion that says so. The
    same property is swept over 2000 sketches by ``test_sketch_solver_sweep``.
    """
    for sketch in (
        _arc_pinned_to_its_own_centre(),
        _arc_tangent_to_a_line_through_its_centre(),
        _tangent_arcs_with_a_non_degenerate_branch(),
        _tangent_circle_and_arc_with_a_non_degenerate_branch(),
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
