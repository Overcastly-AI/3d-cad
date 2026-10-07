"""Degenerate solved geometry: when a solve has annihilated a circle or an arc.

Moved out of :mod:`geometry.sketch.planegcs_solver` unchanged (FILE-SIZE
ratchet, SKETCH-POINT-DISTANCE); that module re-imports every name, and its
docstring carries the history (SOLVE-CRASH-1, ARC-DEGENERATE-1,
ARC-BRANCH-1). ``SATISFIED_TOL_MM`` is restated through
:mod:`geometry.sketch.readouts`, whose test pins it to the solver's.
"""

import math

from geometry.sketch.readouts import SATISFIED_TOL_MM
from geometry.sketch.schemas import Point2D, SketchArc

#: Smallest radius (mm) at which a solved CIRCLE is still a circle.
#:
#: Deliberately the same number and the same role as ``geometry.sketch.edit``'s
#: ``_TOL`` in ``_offset_circle``/``_offset_arc`` ("inward offset collapses the
#: circle (radius <= 0)" -> ``sketch_degenerate_result``): an offset that drives
#: a radius to nothing and a SOLVE that drives a radius to nothing are the same
#: degeneracy, and the one service may not classify them differently. That
#: module's own justification carries over unchanged — 1e-9 mm is far below any
#: meaningful sketch feature size yet safely above double-precision noise at
#: sketch magnitudes.
#:
#: **It is a magnitude test rather than a ``> 0`` test, and that is the whole
#: point** (SOLVE-CRASH-1). ``SketchCircle.radius`` is ``gt=0``, so deferring to
#: the DTO's own rule would draw the line at exactly zero — and the corpus that
#: found this defect straddles it. Of the nine annihilated circles among the
#: twelve crashes, seven reach exactly ``0.0`` and two stop at ``1.5e-15`` and
#: ``1.9e-15`` mm; two MORE (trials 644 and 926, at ``2.7e-15`` and ``8.9e-16``)
#: never crashed at all and shipped under ``status="underconstrained"`` with an
#: empty conflict list, purely because the last DogLeg iterate landed on the
#: positive side. One degeneracy, and which side of zero it lands on is float
#: noise; a rule that gave those two groups different outcomes would encode that
#: noise into a product decision.
#:
#: **This is the CIRCLE's floor and an arc needs a wider one** — see
#: :data:`DEGENERATE_ARC_RADIUS_MM`, which was measured rather than assumed.
DEGENERATE_RADIUS_MM = 1e-9

#: Smallest radius (mm) at which a SOLVED ARC is still an arc (ARC-DEGENERATE-1).
#:
#: Deliberately :data:`SATISFIED_TOL_MM`, and deliberately NOT
#: :data:`DEGENERATE_RADIUS_MM`, because the two quantities have different noise
#: floors and the difference is measured, not theorised. A circle's radius is the
#: solver's OWN PARAMETER: a constraint that annihilates it sets it to zero
#: directly, and on PBT-1's corpus every annihilated circle landed at ``0.0`` or
#: within ``2.7e-15`` mm of it. An arc's radius is a DERIVED DISTANCE between two
#: independently-solved points — ``read_back`` reads ``start_point``/``end_point``,
#: tied to ``center`` only by planegcs's internal arc rules — so it carries the
#: DogLeg residue of three parameter pairs rather than one value.
#:
#: The number that settles it is trial 458, and it is worth stating how it was
#: found because a narrower rule looked correct until then. Every one of the 27
#: annihilated arcs in the corpus sits at or below ``4.0e-14`` mm, so ``1e-9``
#: appeared to clear the whole population by five orders. It does not: once
#: :func:`_shippable_arc_points` is in place, ``_geometry_says_satisfied`` stops
#: agreeing with an annihilated arc, so the settle correctly refuses every hold on
#: such a sketch — and the settle had been the thing driving trial 458's arc from
#: the raw solve's ``4.5e-9`` mm down to exactly ``0.0``. The fix therefore MOVED
#: one case across its own threshold and shipped it, which is the sharpest
#: possible statement of the rule: **a floor set from a population the fix itself
#: perturbs must be re-measured AFTER the fix, not before.** ``4.5e-9`` mm is
#: planegcs's own convergence residue, four orders above double-precision noise at
#: sketch magnitudes and 22x below the tolerance at which this module already
#: declares a constraint satisfied — i.e. a radius the solver itself cannot tell
#: from zero, which is exactly what :data:`SATISFIED_TOL_MM` means.
#:
#: Headroom, so this is not a tolerance chosen to make a test pass: the smallest
#: NON-degenerate arc the corpus ships measures ``0.71`` mm, nearly seven orders
#: above this floor, and the kernel's own linear tolerance is ``1e-4`` mm — so
#: every radius this refuses is already three orders too small for OCCT to build
#: an edge from. Nothing legitimate lives in the band, at either candidate value;
#: what picks ``1e-7`` over ``1e-9`` is trial 458, not caution.
DEGENERATE_ARC_RADIUS_MM = SATISFIED_TOL_MM


def shippable_radius(solved: float, submitted: float) -> float:
    """The DTO radius for planegcs's SIGNED radius parameter (SOLVE-CRASH-1).

    Two different things happen here, and separating them is the whole content
    of the fix — a sweep of 2000 generated sketches crashed on twelve, and the
    twelve split into two groups that want OPPOSITE answers.

    **A negative radius is not a degenerate circle; it is the same circle under
    a sign convention the DTO does not have.** planegcs carries a circle's
    radius as a signed parameter and reads the sign as a choice of BRANCH: its
    ``tangent_circle_circle`` error is ``d - (r1 + r2)``, so ``r2 < 0``
    describes the internal tangency of a circle of radius ``|r2|``. The point
    set ``{p : |p - c| = r}`` is identical either way, so ``abs`` is the
    de-parameterisation from a solver parameter to a geometric magnitude, not a
    correction applied to a wrong answer. Measured: THREE of the twelve are this
    case, and with ``abs`` applied all three come back as ordinary solves whose
    worst residual over every constraint is **1.8e-13 mm**, six orders under
    :data:`SATISFIED_TOL_MM` — the constraint sets DO have positive-radius
    solutions and the solver had already found them. Refusing those sketches
    would have made three legal models unbuildable, which is a worse defect than
    the crash: the user has no way to tell it is our fault.

    **A radius the solve has driven to nothing is not a circle at all.** No
    ``SketchCircle`` can carry it (``radius`` is ``gt=0``), so this returns the
    author's submitted value — read_back must produce a DTO — and the geometry
    it produces then fails its own tangency residual by the whole radius, which
    is what reclassifies the payload as the conflict it is
    (:func:`_violated_constraints`). Nothing new decides that: the existing
    payload gate already refuses to ship geometry a payload's own constraints
    contradict, and a circle the constraints have annihilated is the sharpest
    case of it. The other NINE of the twelve are this case, and nearly all are
    one shape — ``tangent`` between a line and a circle whose centre some OTHER
    constraint puts ON that line (``coincident`` with an endpoint, or
    ``midpoint``), so the centre-to-line distance is zero and ``r = 0`` is the
    unique solution. There is no positive-radius answer to find, and saying so
    is honest.

    The threshold is :data:`DEGENERATE_RADIUS_MM`, on the MAGNITUDE — see there
    for why deferring to the DTO's own ``> 0`` would split one degeneracy in
    half along a float-noise seam.
    """
    return submitted if radius_is_annihilated(solved) else abs(solved)


def radius_is_annihilated(solved: float) -> bool:
    """Has the solve driven this planegcs radius parameter to nothing?

    The magnitude test :func:`shippable_radius` documents, named so the RESTART
    (:func:`_restarted_without_the_collapse`) asks it with the same threshold and
    the same NaN handling rather than re-deriving them. Two call sites that
    disagree about where the floor is would restart on a circle the payload
    ships, or ship one the payload was about to substitute.

    ``not (x >= t)`` rather than ``x < t`` so that NaN answers TRUE: a radius
    that is not a number is not a circle either, and the degenerate path is the
    safe direction (:func:`shippable_radius`).
    """
    return not abs(solved) >= DEGENERATE_RADIUS_MM


def shippable_arc_points(
    center: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    submitted: SketchArc,
) -> tuple[Point2D, Point2D]:
    """The DTO endpoints for a solved arc, refusing to ship one that collapsed.

    :func:`shippable_radius`'s job for an arc (ARC-DEGENERATE-1), and the ticket
    that produced it began from an ASYMMETRY rather than a crash:
    :meth:`_GcsBuild._add_entity` raises ``SketchDefinitionError`` on an arc whose
    start coincides with its centre, so the solver refused to ACCEPT the shape it
    would then happily EMIT. Nothing downstream asked, and nothing could: a
    ``SketchArc`` carries ``center``/``start``/``end`` and DERIVES its radius, so
    an arc the solve has annihilated is a well-formed DTO whose
    :func:`~geometry.sketch.residual.entity_residual` is ``0.0`` (both endpoints
    are equidistant from the centre — at zero) and whose constraint residuals are
    ``0.0`` too, because the constraint that annihilated it is satisfied EXACTLY
    by a point. Measured on PBT-1's corpus: **27 of 2000 sketches shipped one**,
    25 under ``overconstrained`` and 2 under ``underconstrained``, all with a
    worst residual under ``6e-11`` mm. Every property in that sweep agreed with
    every one of them.

    **Is the collapse forced, or a bad branch?** The prior question SOLVE-CRASH-1
    turned on, asked again here because its answer there was *both* and no single
    rule was right. For arcs it is measured at **26 forced, 1 branch**, by two
    independent probes per case: adding a 10 mm ``radius`` dimension the arc
    could reach if any non-degenerate solution existed (25 come back
    ``conflicting`` and 1 ``diverged``; the SMALLEST of their residuals is
    **6.3 mm**, seven orders over :data:`SATISFIED_TOL_MM`, so none is a
    near-miss), and re-solving from 8 configurations with the arc pushed 7 mm
    off the degenerate one (all 26 return to r = 0). Sixteen of the 26
    minimise to a SINGLE constraint — ``coincident`` between an arc's own centre
    and its own start or end — which is precisely the shape ``_add_entity``
    refuses on input, authored as a constraint instead of as coordinates; the
    rest are chains that force the same thing (``concentric`` + a ``coincident``
    onto the other curve's centre, two ``midpoint``s onto the same line,
    ``tangent`` to a line the centre is pinned to). There is no non-degenerate
    answer to find in any of them.

    The ONE exception is trial 1906 (``coincident`` from one arc's centre to the
    other's endpoint, plus ``tangent`` between them), and it is a real one: the
    tangency admits ``r2 = 0`` AND ``r2 = 2 * r1``, the solver takes the first
    from the author's own start, and 4 of 8 perturbed starts reach
    ``r2 = 29.236`` mm at a residual of exactly ``0.0``. That is a
    BRANCH-SELECTION defect, not this one, and ARC-DEGENERATE-1 was blunt that it
    did not fix it: before, the sketch shipped an arc that was not there; after,
    it said ``conflicting``; and BOTH were wrong, because the sketch is solvable.
    **ARC-BRANCH-1 closed it** — :func:`_restarted_without_the_collapse` runs
    BEFORE this function is reached on such a sketch, so the substitution below is
    now what happens to the 36 collapses that really are forced. Note the split is
    no longer 26/1: asking the restart's question of every annihilated entity in
    the corpus, rather than of arcs only, put it at **36 forced, 2 branch** —
    the second being a circle in the same construction (trial 1593).

    So this returns the author's own arc, TRANSLATED to the solved centre — the
    same move as :func:`shippable_radius` returning the author's radius beside
    the solved centre, and for the same reason: ``read_back`` must produce a DTO,
    and geometry carrying the author's radius where the solve found none fails
    the very constraint that annihilated it, which is what reclassifies the
    payload through :func:`_violated_constraints`. Nothing new decides the
    outcome. A translation is used rather than a re-derivation of angles because
    it preserves the author's radius, both endpoint angles and the CCW-from-start
    invariant :class:`~loft_wire.sketch.SketchArc` documents, exactly.

    The test is on ``max`` of the two endpoint distances — "the arc has collapsed
    ENTIRELY" — not on ``min``. An arc with ONE endpoint on its centre and the
    other 10 mm away is a different defect, an arc that is not internally an arc,
    and :func:`~geometry.sketch.residual.entity_residual` is the thing that
    already catches it; routing it here would replace it with a consistent arc
    and hide the very inconsistency that names it. Both endpoint distances are
    below the threshold in all 27 measured cases.

    The threshold is :data:`DEGENERATE_ARC_RADIUS_MM`, which is NOT the circle's
    — see there for the measurement that separated them, and for why it had to be
    taken after this function existed rather than before.
    """
    if not arc_is_annihilated(center, start, end):
        return (
            Point2D(x=start[0], y=start[1]),
            Point2D(x=end[0], y=end[1]),
        )
    return (
        Point2D(
            x=center[0] + (submitted.start.x - submitted.center.x),
            y=center[1] + (submitted.start.y - submitted.center.y),
        ),
        Point2D(
            x=center[0] + (submitted.end.x - submitted.center.x),
            y=center[1] + (submitted.end.y - submitted.center.y),
        ),
    )


def arc_is_annihilated(
    center: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    """Has the solve driven BOTH of this arc's endpoints onto its own centre?

    :func:`radius_is_annihilated`'s job for an arc, and named for the same
    reason: :func:`shippable_arc_points` and the restart
    (:func:`_restarted_without_the_collapse`) must ask exactly one question, at
    exactly one threshold. See :func:`shippable_arc_points` for why the test is
    on ``max`` rather than ``min`` of the two endpoint distances, and
    :data:`DEGENERATE_ARC_RADIUS_MM` for why an arc's floor is not the circle's.

    ``not (x >= t)``, so NaN answers TRUE — the safe direction, as for a circle.
    """
    return (
        not max(
            math.hypot(start[0] - center[0], start[1] - center[1]),
            math.hypot(end[0] - center[0], end[1] - center[1]),
        )
        >= DEGENERATE_ARC_RADIUS_MM
    )
