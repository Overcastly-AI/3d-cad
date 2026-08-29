"""PBT-1 — the randomised sweep that found SETTLE-2 and SETTLE-3, committed.

Both of those fixes were found by a randomised sweep whose own commit messages
say so ("found by a randomised sweep", "400 generated sketches"), and the
generator was never committed. Three hand-transcribed counter-examples survived
in :mod:`test_sketch_residual_agreement`; the sweep did not. Two consequences,
and the second is the one this module exists for: the next solver change could
not be swept the same way, and the alarming number that sweep produced — **7 of
155 solvable sketches shipped a VIOLATED CONSTRAINT despite the solver reporting
success** (RESEARCH §2) — was unverifiable and unmonitored. There was no way to
show it is now 0, and no way to notice it regress.

**Re-measured on this corpus: 0 of 1326** (1327 at the commit that added this
module; 1328 after SOLVE-CRASH-1 turned three formerly-crashing sketches into
real solves; 1326 after ARC-DEGENERATE-1 reclassified two annihilated-arc
payloads out of ``underconstrained``). The 95% upper bound on the violation rate
is therefore 3/1326 = 0.23% (rule of three), against the 4.5% the original sweep
measured. That number is now a gate.

The sweep did not come back empty, though — it found three OTHER things, all
reported rather than folded into a green test: an unhandled
``pydantic.ValidationError`` escaping ``solve()`` on 12 of 2000 sketches, 2
payloads that say ``conflicting`` over geometry the solver moved, and an
``overconstrained`` status a client cannot read (see the last three tests).

**The first of those is CLOSED (SOLVE-CRASH-1), so its recorded live limit is
gone and two ordinary gates stand in its place**: nothing raises
(:func:`test_no_generated_sketch_makes_the_solver_raise`) and no solved payload
ships a circle that is not there
(:func:`test_no_solved_payload_ships_a_circle_that_is_not_there`). The second
gate is not a restatement of the first — it covers the SILENT half of the same
defect the crash was only the loud end of: trials 644 and 926 were shipping
circles of radius ``2.7e-15`` and ``8.9e-16`` mm under
``status="underconstrained"`` with an empty conflict list, purely because the
last DogLeg iterate landed on the positive side of zero, and no property here
could see them. The fix moved 9 of the 12 crashes and both of those to
``conflicting`` (276 -> 287) and turned the other 3 into real solves
(solvable 1327 -> 1328), each with a worst residual under ``1.8e-13`` mm.

**The SAME defect on an ARC had no loud half at all, and took a fourth gate to
see** (ARC-DEGENERATE-1,
:func:`test_no_solved_payload_ships_an_arc_that_is_not_there`). An arc DERIVES
its radius from three coordinates instead of carrying it in a ``gt=0`` field, so
there was never a crash to notice: **27 payloads here shipped an arc collapsed
onto its own centre**, 25 under ``overconstrained`` and 2 under
``underconstrained``, all at ``4e-14`` mm or less and all with a worst residual
under ``6e-11`` mm — because a constraint satisfied by putting a point on a point
is satisfied EXACTLY. Every property in this module agreed with all 27, and the
ticket was filed off an asymmetry (``_add_entity`` refuses that shape on INPUT)
rather than off any failure here. That is the lesson worth carrying: **a residual
oracle cannot see a degeneracy its own constraint is happy with**, so "no
violated constraint" and "no absent geometry" are two properties and each needs
its own assertion. Census after: ``conflicting`` 287 -> 314, ``overconstrained``
282 -> 257, ``underconstrained`` 1297 -> 1295, solvable 1328 -> 1326.

Seeded fixed corpus, NOT hypothesis
-----------------------------------
The ticket offered either shape. ``hypothesis`` is MPL-2.0 (checked: not
GPL/AGPL, so the licence guard does not decide this — RESEARCH §8), and its
shrinking is genuinely most of the debugging value of a property test. It was
still the wrong choice here, for reasons specific to this repo:

* **A CI failure must be reproducible from the commit alone.** Only the
  orchestrator can read CI here, the job log is the only channel, and a fixed
  tail of it is all anyone reliably gets. A corpus that is a pure function of
  ``SWEEP_SEED`` means "trial 341 fails" is a complete bug report; a
  ``@given`` failure is reproducible only from whatever the log happened to
  keep of the shrunk example.
* **Determinism is a product property here** (RESEARCH §9 — same definition in,
  bitwise-identical solution out), and a suite whose INPUTS move run to run
  cannot distinguish a new defect from a new input. Every trial in this corpus
  is in the commit, which is also the only "database of past failures" that
  survives a fresh CI runner: hypothesis's ``.hypothesis/`` directory does not.
* **The python job has already been killed once by a timeout.** A fixed trial
  count has a measured, flat cost (below); ``@given``'s does not.

Shrinking is not given up, it is just not paid for with a dependency:
:func:`_minimise` delta-debugs a failing sketch down to the constraints and
entities that still reproduce it, and runs ONLY on failure, so it costs nothing
on a green run. Measured on this module's own mutation evidence: a four-
constraint failing trial reduced to ``equal`` + ``tangent`` on two curves, and
another to a three-line ``parallel``/``perpendicular`` chain — small enough to
read, which is the entire point.

What this sweep is an oracle for, and what it is not
----------------------------------------------------
The residual oracle is :func:`geometry.sketch.residual.worst_residual` — the
same predicate the payload gate uses. That is deliberate and it is worth being
explicit about the limit it implies: **this module gates the CONTRACT (does the
shipped payload's status agree with the geometry beside it), not the residual
FORMULAS.** A blind residual would satisfy both. The formulas are guarded
independently by :mod:`test_sketch_residual_agreement`, which compares them
against planegcs's own ``constraint_error`` AWAY from a solution, where the two
can actually disagree. Neither suite subsumes the other and each is useless
alone — the division of labour is the point (CLAUDE.md: get a second opinion
from a different derivation, not a louder assertion of the first).

The one place this module does derive independently is the SETTLE-2 property:
``_turns_geometry_inside_out`` is the code under test, so
:func:`_reversed_entities` re-derives the dot product here rather than calling
it.

It cannot become a no-op
------------------------
Five gates in this repo have shipped with the shape ``all([])``. A sweep that
generates 2000 sketches of which 0 are solvable would pass forever and prove
nothing, so :func:`test_the_sweep_actually_exercised_the_solver` asserts a floor
on the solvable count, on the orientation-checked count, and demands that every
one of the 17 constraint kinds and every entity kind appears among the SOLVED
sketches — generated-but-never-solved is exercised nowhere that matters. The
counts are printed after the run (``sweep_census`` fixture ->
``pytest_unconfigure`` in ``conftest.py``) so a human reading CI sees what was
actually exercised rather than a green dot.

**That floor is not decoration; it was measured firing.** Emptying
:data:`SOLVED_STATUSES` so the corpus yields 0 solvable sketches leaves
:func:`test_no_solved_sketch_ships_a_violated_constraint` and
:func:`test_no_settle_ever_turns_the_geometry_inside_out` BOTH GREEN — they are
quantified over an empty set — while the floor fails with ``only 0 of 2000
generated sketches solved (floor 800)``. Without it this module would be a
green suite asserting nothing, which is the exact failure it is named after.

The first attempt at that negative control was itself INERT and passed, which
is the more useful half of the story: ``solvable`` was being derived by
EXCLUSION (not passthrough, not overconstrained) while
:data:`SOLVED_STATUSES` sat beside it documenting the rule and selecting
nothing, so emptying the constant mutated dead code and the "control" came back
green. A mutation that does not redden is a claim about which bytes ran until
you have checked. The population is now selected BY that constant.

Cost, measured on this container rather than estimated: the whole module is
**10.1-10.5 s** (four runs), of which the sweep itself is ~5 ms/trial and the
SETTLE-2 baseline solve is ~8% of that. The ``python`` CI job has been killed
by a timeout once, so the number matters: against a ~2958-test suite that runs
~19 minutes this is **0.9%**, and it buys the only gate on a defect class the
rest of the suite is blind to. If it ever needs to be cheaper, cut
:data:`SWEEP_TRIALS` — the cost is exactly linear in it and the confidence
bound moves with it, which is a legible trade rather than a hidden one.
"""

import math
import random
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from geometry.sketch import (
    AngleConstraint,
    CoincidentConstraint,
    CollinearConstraint,
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
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolver,
    SketchSpline,
    SymmetricConstraint,
    SymmetricLinesConstraint,
    TangentConstraint,
    VerticalConstraint,
)
from geometry.sketch.angles import angle_frames
from geometry.sketch.expression import evaluate_driving_dimensions
from geometry.sketch.planegcs_solver import (
    DEGENERATE_ARC_RADIUS_MM,
    DEGENERATE_RADIUS_MM,
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
    _submitted_points,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import worst_residual
from planegcs import SolveStatus as GcsSolveStatus

SOLVER: SketchSolver = PlanegcsSketchSolver()

#: The seed the original SETTLE-2/SETTLE-3 sweep ran under, kept so this corpus
#: is the same KIND of thing that found those defects. Changing it is a
#: reviewed decision with a re-measurement, not a knob: the recorded live limits
#: below are counts over THIS corpus.
SWEEP_SEED = 20260822

#: Trials per run. 2000 rather than the original 400 because the question this
#: module answers is now "is the violation rate zero", and a zero over 1326
#: solvable sketches bounds the rate at 0.23% where 155 bounded it only at 1.9%.
#: Measured cost is ~6 ms/trial, so the whole module is ~12 s.
SWEEP_TRIALS = 2000

#: Vacuity floor. The measured solvable count is 1326 of 2000; this is ~60% of
#: it, low enough that ordinary solver churn does not trip it and high enough
#: that the sweep cannot quietly stop exercising anything. A run below this is
#: not a weaker sweep, it is a sweep whose generator has broken.
MIN_SOLVABLE = 800

#: Every constraint kind the DTO union carries. Asserted against what the corpus
#: actually SOLVES, not merely what it generates.
ALL_CONSTRAINT_KINDS = frozenset(
    {
        "angle",
        "coincident",
        "collinear",
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
        "symmetric_lines",
        "tangent",
        "vertical",
    }
)

ALL_ENTITY_KINDS = frozenset({"arc", "circle", "line", "point", "spline"})

#: Statuses whose payload UNAMBIGUOUSLY carries solved geometry
#: (:class:`~py_kit.schemas.sketch.SolvedSketch` — "positions are solved when
#: the numeric solve succeeded"). ``overconstrained`` is deliberately absent:
#: the same docstring says only *consistent* overconstrained cases carry solved
#: positions, so a client cannot tell from the status alone which it has, and
#: this corpus contains both (see
#: :func:`test_an_overconstrained_payload_is_either_solved_or_the_input`).
SOLVED_STATUSES = frozenset({"converged", "underconstrained"})

#: Statuses the DTO documents as returning "the input positions unchanged".
PASSTHROUGH_STATUSES = frozenset({"conflicting", "diverged"})


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------
#
# Every draw goes through ``randrange``/``random`` on a ``random.Random``
# seeded with an int, so the corpus is a pure function of SWEEP_SEED and of
# nothing else — not of dict ordering, not of the platform, not of the clock.
# ``random.sample``/``random.choice`` are deliberately not used: their internal
# strategy has changed between CPython releases, and a corpus that shifts under
# an interpreter upgrade would turn every recorded count below into a flake.


def _pick(rng: random.Random, items: list[str]) -> str:
    return items[rng.randrange(len(items))]


def _pick_distinct(rng: random.Random, items: list[str], count: int) -> list[str]:
    """``count`` distinct members, drawn without replacement, in draw order."""
    pool = list(items)
    drawn: list[str] = []
    for _ in range(count):
        drawn.append(pool.pop(rng.randrange(len(pool))))
    return drawn


def _point(rng: random.Random) -> Point2D:
    return Point2D(x=round(rng.uniform(-40, 40), 3), y=round(rng.uniform(-40, 40), 3))


def _entity(rng: random.Random, entity_id: str) -> SketchEntity:
    """One random entity. Lines are over-weighted: most constraint kinds need
    one, and several need two or three, so a line-poor corpus exercises fewer
    kinds rather than fewer entities."""
    kind = _pick(rng, ["line", "line", "line", "circle", "arc", "point", "spline"])
    if kind == "line":
        return SketchLine(id=entity_id, kind="line", start=_point(rng), end=_point(rng))
    if kind == "circle":
        return SketchCircle(
            id=entity_id,
            kind="circle",
            center=_point(rng),
            radius=round(rng.uniform(2, 20), 3),
        )
    if kind == "arc":
        # Built ON its own circle, so `entity_residual` reads 0.0 at the input:
        # an arc that arrives ill-formed would make every downstream finding
        # about the generator rather than about the solver.
        center = _point(rng)
        radius = round(rng.uniform(2, 20), 3)
        start_angle = rng.uniform(0.0, math.tau)
        end_angle = start_angle + rng.uniform(0.5, 5.0)
        return SketchArc(
            id=entity_id,
            kind="arc",
            center=center,
            start=Point2D(
                x=center.x + radius * math.cos(start_angle),
                y=center.y + radius * math.sin(start_angle),
            ),
            end=Point2D(
                x=center.x + radius * math.cos(end_angle),
                y=center.y + radius * math.sin(end_angle),
            ),
        )
    if kind == "spline":
        return SketchSpline(
            id=entity_id,
            kind="spline",
            points=[_point(rng) for _ in range(rng.randrange(2, 5))],
        )
    return SketchPoint(id=entity_id, kind="point", position=_point(rng))


def _point_refs(entities: list[SketchEntity]) -> list[EntityPointRef]:
    """Every addressable point of every entity, in entity order.

    A spline's points are its FIT points, addressed positionally — the one
    reference form whose valid set is data-dependent, and therefore the one a
    corpus of fixed named points would never exercise.
    """
    refs: list[EntityPointRef] = []
    for entity in entities:
        match entity:
            case SketchPoint():
                names = ["position"]
            case SketchLine():
                names = ["start", "end"]
            case SketchCircle():
                names = ["center"]
            case SketchArc():
                names = ["center", "start", "end"]
            case SketchSpline():
                names = [f"fit{index}" for index in range(len(entity.points))]
        refs.extend(EntityPointRef(entity=entity.id, point=name) for name in names)
    return refs


def _constraint(
    rng: random.Random, entities: list[SketchEntity]
) -> SketchConstraint | None:
    """One random constraint whose operands are TYPE-VALID for their kinds.

    Type-invalid pairings (``tangent`` between two lines, ``concentric`` on a
    line) are excluded on purpose: the solver rejects them with a typed
    ``SketchDefinitionError``, which is correct behaviour and already covered by
    the unit suites. Sweeping them would fill the corpus with sketches that
    never reach the solve this module is about.

    ``None`` where the draw cannot be satisfied by the entities present.
    """
    lines = [e.id for e in entities if isinstance(e, SketchLine)]
    curves = [e.id for e in entities if isinstance(e, SketchCircle | SketchArc)]
    refs = _point_refs(entities)
    kinds = ["coincident", "fixed"]
    if lines:
        kinds += ["horizontal", "vertical", "distance", "midpoint"]
    if len(lines) >= 2:
        kinds += ["parallel", "perpendicular", "collinear", "angle", "symmetric"]
    if len(lines) >= 3:
        kinds += ["symmetric_lines"]
    if curves:
        kinds += ["radius", "diameter"]
    if len(curves) >= 2:
        kinds += ["concentric"]
    if curves and (lines or len(curves) >= 2):
        kinds += ["tangent"]
    if len(lines) >= 2 or len(curves) >= 2:
        kinds += ["equal"]
    kind = _pick(rng, kinds)
    millimetres = round(rng.uniform(5, 60), 3)

    if kind == "coincident":
        if len(refs) < 2:
            return None
        first, second = rng.randrange(len(refs)), rng.randrange(len(refs) - 1)
        second += second >= first
        return CoincidentConstraint(kind="coincident", a=refs[first], b=refs[second])
    if kind == "fixed":
        return FixedConstraint(kind="fixed", point=refs[rng.randrange(len(refs))])
    if kind == "horizontal":
        return HorizontalConstraint(kind="horizontal", entity=_pick(rng, lines))
    if kind == "vertical":
        return VerticalConstraint(kind="vertical", entity=_pick(rng, lines))
    if kind == "distance":
        return DistanceConstraint(
            kind="distance", entity=_pick(rng, lines), value_mm=millimetres
        )
    if kind == "midpoint":
        line = _pick(rng, lines)
        elsewhere = [ref for ref in refs if ref.entity != line]
        if not elsewhere:
            return None
        return MidpointConstraint(
            kind="midpoint",
            point=elsewhere[rng.randrange(len(elsewhere))],
            line=line,
        )
    if kind in ("parallel", "perpendicular", "collinear", "angle"):
        a, b = _pick_distinct(rng, lines, 2)
        if kind == "parallel":
            return ParallelConstraint(kind="parallel", a=a, b=b)
        if kind == "perpendicular":
            return PerpendicularConstraint(kind="perpendicular", a=a, b=b)
        if kind == "collinear":
            return CollinearConstraint(kind="collinear", a=a, b=b)
        return AngleConstraint(
            kind="angle", a=a, b=b, value_deg=round(rng.uniform(10, 170), 3)
        )
    if kind == "symmetric":
        line = _pick(rng, lines)
        elsewhere = [ref for ref in refs if ref.entity != line]
        if len(elsewhere) < 2:
            return None
        first, second = rng.randrange(len(elsewhere)), rng.randrange(len(elsewhere) - 1)
        second += second >= first
        return SymmetricConstraint(
            kind="symmetric", a=elsewhere[first], b=elsewhere[second], line=line
        )
    if kind == "symmetric_lines":
        a, b, axis = _pick_distinct(rng, lines, 3)
        return SymmetricLinesConstraint(kind="symmetric_lines", a=a, b=b, line=axis)
    if kind == "radius":
        return RadiusConstraint(
            kind="radius", entity=_pick(rng, curves), value_mm=millimetres
        )
    if kind == "diameter":
        return DiameterConstraint(
            kind="diameter", entity=_pick(rng, curves), value_mm=millimetres
        )
    if kind == "concentric":
        a, b = _pick_distinct(rng, curves, 2)
        return ConcentricConstraint(kind="concentric", a=a, b=b)
    if kind == "tangent":
        if len(curves) >= 2 and (not lines or rng.random() < 0.5):
            a, b = _pick_distinct(rng, curves, 2)
        else:
            a, b = _pick(rng, lines), _pick(rng, curves)
        return TangentConstraint(kind="tangent", a=a, b=b)
    prefer_lines = len(lines) >= 2 and (len(curves) < 2 or rng.random() < 0.5)
    a, b = _pick_distinct(rng, lines if prefer_lines else curves, 2)
    return EqualConstraint(kind="equal", a=a, b=b)


def generate_sketch(rng: random.Random) -> SketchDefinition:
    """One random sketch: 2-4 entities, 1-4 type-valid constraints over them.

    Small on purpose. The defects this sweep is for are RELATIONAL — a pair of
    constraints nothing can satisfy at once, a settle that jumps branches — and
    they appear at two entities as readily as at twenty, while a small sketch
    keeps the corpus wide (2000 trials in seconds) and every counter-example
    legible without minimisation.
    """
    entities = [_entity(rng, f"e{index}") for index in range(rng.randrange(2, 5))]
    constraints: list[SketchConstraint] = []
    for _ in range(rng.randrange(1, 5)):
        constraint = _constraint(rng, entities)
        if constraint is not None:
            constraints.append(constraint)
    return SketchDefinition(entities=entities, constraints=constraints)


# ---------------------------------------------------------------------------
# The properties, each measured from the shipped payload
# ---------------------------------------------------------------------------


def shipped_residual(sketch: SketchDefinition, shipped: list[SketchEntity]) -> float:
    """The worst constraint/entity residual of a payload against its own sketch.

    ``fixed`` pins to the coordinate the AUTHOR submitted, so its reference is
    the input sketch — against the solved entities it would be trivially
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


def _arc_radius(entity: SketchArc) -> float:
    """An arc's radius as every consumer derives it, from its WORSE endpoint.

    Re-derived here rather than imported from
    :mod:`geometry.sketch.residual`, for the same reason
    :func:`_reversed_entities` re-derives SETTLE-2's dot product: the shipped
    payload is what is under test, and an oracle that borrows the production
    helper cannot see a mutation of it.

    ``max``, matching
    :func:`~geometry.sketch.planegcs_solver._shippable_arc_points`: an arc is
    ANNIHILATED only when both endpoints have reached the centre. One endpoint
    there and the other 10 mm away is a different defect — an arc that is not
    internally an arc — which ``entity_residual`` catches through
    :func:`shipped_residual` and which this must not claim as its own.
    """
    return max(
        math.hypot(entity.start.x - entity.center.x, entity.start.y - entity.center.y),
        math.hypot(entity.end.x - entity.center.x, entity.end.y - entity.center.y),
    )


def _senses(entities: list[SketchEntity]) -> dict[str, tuple[float, float]]:
    return {
        entity.id: (
            entity.end.x - entity.start.x,
            entity.end.y - entity.start.y,
        )
        for entity in entities
        if isinstance(entity, SketchLine | SketchArc)
    }


def _reversed_entities(
    shipped: list[SketchEntity], baseline: list[SketchEntity]
) -> list[str]:
    """Ids running BACKWARDS in ``shipped`` relative to the plain solve.

    SETTLE-2's property, re-derived here rather than imported: the production
    predicate ``_turns_geometry_inside_out`` is the code under test, and an
    oracle that calls it cannot see a mutation of it. Three lines is a cheap
    price for an independent witness.
    """
    before = _senses(baseline)
    return [
        entity_id
        for entity_id, (x, y) in _senses(shipped).items()
        if x * before[entity_id][0] + y * before[entity_id][1] < 0.0
    ]


def _plain_solve(sketch: SketchDefinition) -> list[SketchEntity] | None:
    """The UNSETTLED solution — the baseline a settle must refine, not replace.

    ``None`` when the plain solve does not converge, in which case there is no
    baseline to compare against and the SETTLE-2 property does not apply.
    """
    build = _GcsBuild(sketch, evaluate_driving_dimensions(sketch.constraints))
    if build.gcs.solve() not in (GcsSolveStatus.Success, GcsSolveStatus.Converged):
        return None
    return build.read_back()


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One trial that broke a property, with everything needed to reproduce it.

    ``kind`` selects the minimiser's arbiter (:func:`_reproduces`) and is a
    FIELD rather than a prefix sniffed off ``detail``: the shrink predicate must
    be the one that matches this finding's defect class, or the minimal case
    printed belongs to a different bug than the one being reported. It was a
    ``detail.startswith("solve() raised")`` test until a second class of finding
    arrived and would have fallen silently into the wrong arbiter.
    """

    trial: int
    sketch: SketchDefinition
    detail: str
    kind: str = "violates"

    def report(self) -> str:
        minimal = _minimise(self.sketch, _reproduces(self))
        return (
            f"trial {self.trial}: {self.detail}\n"
            f"  minimal counter-example ({len(minimal.entities)} entities, "
            f"{len(minimal.constraints)} constraints):\n"
            f"  {minimal.model_dump_json()}"
        )


@dataclass
class Census:
    """What one sweep run actually exercised, and what it found."""

    trials: int = 0
    solvable: int = 0
    orientation_checked: int = 0
    overconstrained_passthrough: int = 0
    #: Wall clock of the sweep itself, reported because NOTHING ELSE REPORTS IT:
    #: the work happens in a module-scoped fixture, and pytest attributes fixture
    #: setup to no test's ``call`` phase — ``--durations`` prints ``0.01s`` for a
    #: module that costs ten seconds. A future perf audit would read that number
    #: and conclude this file is free. Same discipline as the e2e seat helper
    #: that prints its own elapsed time: a cost nobody can see is a cost nobody
    #: can manage, and the ``python`` job has already been killed by a timeout.
    seconds: float = 0.0
    statuses: Counter[str] = field(default_factory=Counter[str])
    solved_constraint_kinds: Counter[str] = field(default_factory=Counter[str])
    solved_entity_kinds: Counter[str] = field(default_factory=Counter[str])
    violated: list[Finding] = field(default_factory=list["Finding"])
    inside_out: list[Finding] = field(default_factory=list["Finding"])
    crashed: list[Finding] = field(default_factory=list["Finding"])
    #: Payloads shipping a circle the solve drove below
    #: :data:`~geometry.sketch.planegcs_solver.DEGENERATE_RADIUS_MM` — the
    #: SILENT half of SOLVE-CRASH-1 (see the module docstring).
    annihilated: list[Finding] = field(default_factory=list["Finding"])
    #: Payloads shipping an ARC the solve drove onto its own centre
    #: (ARC-DEGENERATE-1). Counted separately from :attr:`annihilated` and
    #: against a different threshold
    #: (:data:`~geometry.sketch.planegcs_solver.DEGENERATE_ARC_RADIUS_MM`),
    #: because an arc's radius is a derived distance rather than a solver
    #: parameter — merging the two would hide which of the two floors moved.
    annihilated_arcs: list[Finding] = field(default_factory=list["Finding"])
    moved_passthrough: list[Finding] = field(default_factory=list["Finding"])
    dirty_overconstrained: list[Finding] = field(default_factory=list["Finding"])

    def lines(self) -> list[str]:
        return [
            f"generated {self.trials}  solvable {self.solvable}  "
            f"violated {len(self.violated)}  reversed {len(self.inside_out)}",
            f"  statuses: {dict(sorted(self.statuses.items()))}",
            f"  orientation-checked {self.orientation_checked}; "
            f"overconstrained returned as input {self.overconstrained_passthrough}",
            f"  raised {len(self.crashed)}; annihilated circles "
            f"{len(self.annihilated)}; annihilated arcs "
            f"{len(self.annihilated_arcs)}; recorded live limit: "
            f"{len(self.moved_passthrough)} moved-passthrough",
            f"  sweep wall clock {self.seconds:.1f}s "
            f"({1000 * self.seconds / max(self.trials, 1):.1f} ms/trial)",
        ]


def run_sweep(trials: int = SWEEP_TRIALS, seed: int = SWEEP_SEED) -> Census:
    """Generate, solve and interrogate ``trials`` sketches. Pure, given the seed."""
    started = time.perf_counter()
    rng = random.Random(seed)
    census = Census(trials=trials)
    for trial in range(trials):
        sketch = generate_sketch(rng)
        try:
            solved = SOLVER.solve(sketch)
        except Exception as exc:
            census.crashed.append(
                Finding(trial, sketch, f"solve() raised {type(exc).__name__}", "raised")
            )
            continue
        census.statuses[solved.status] += 1
        untouched = [e.model_dump() for e in solved.entities] == [
            e.model_dump() for e in sketch.entities
        ]
        if not untouched:
            # Only geometry the SOLVER produced is in scope: a passthrough
            # payload carries the author's own circles, and asserting about
            # those would be asserting about this file's generator.
            annihilated = [
                entity.id
                for entity in solved.entities
                if isinstance(entity, SketchCircle)
                and entity.radius < DEGENERATE_RADIUS_MM
            ]
            if annihilated:
                census.annihilated.append(
                    Finding(
                        trial,
                        sketch,
                        f"status={solved.status} ships circle(s) {annihilated} "
                        f"below {DEGENERATE_RADIUS_MM} mm",
                        "annihilated",
                    )
                )
            flat_arcs = [
                entity.id
                for entity in solved.entities
                if isinstance(entity, SketchArc)
                and _arc_radius(entity) < DEGENERATE_ARC_RADIUS_MM
            ]
            if flat_arcs:
                census.annihilated_arcs.append(
                    Finding(
                        trial,
                        sketch,
                        f"status={solved.status} ships arc(s) {flat_arcs} "
                        f"below {DEGENERATE_ARC_RADIUS_MM} mm",
                        "annihilated_arc",
                    )
                )
        if solved.status in PASSTHROUGH_STATUSES:
            if not untouched:
                census.moved_passthrough.append(
                    Finding(trial, sketch, f"{solved.status} but the entities MOVED")
                )
            continue
        residual = shipped_residual(sketch, solved.entities)
        if solved.status == "overconstrained":
            # The documented disjunction. An INCONSISTENT overconstrained system
            # returns the input untouched, which is allowed to violate — those
            # are the coordinates the author submitted, not a claim about them.
            # What is NOT allowed is the third thing: geometry the solver MOVED
            # under a status that says it solved.
            if untouched:
                census.overconstrained_passthrough += 1
            elif residual > SATISFIED_TOL_MM:
                census.dirty_overconstrained.append(
                    Finding(
                        trial, sketch, f"overconstrained, MOVED, residual {residual}"
                    )
                )
            continue
        if solved.status not in SOLVED_STATUSES:
            # Not reachable today — the two branches above cover every status
            # outside SOLVED_STATUSES — and asserted rather than assumed on
            # purpose. Deriving the solvable population by EXCLUSION left
            # :data:`SOLVED_STATUSES` documenting a rule the code did not read,
            # so emptying it changed nothing: the negative control for the
            # vacuity floor came back green having mutated a dead constant. A
            # constant that names the population must be the one that selects
            # it, or the next reader is calibrating against a comment.
            continue
        census.solvable += 1
        for constraint in sketch.constraints:
            census.solved_constraint_kinds[constraint.kind] += 1
        for entity in sketch.entities:
            census.solved_entity_kinds[entity.kind] += 1
        if residual > SATISFIED_TOL_MM:
            census.violated.append(
                Finding(
                    trial,
                    sketch,
                    f"status={solved.status} but worst residual is {residual} "
                    f"(> {SATISFIED_TOL_MM})",
                )
            )
        baseline = _plain_solve(sketch)
        if baseline is None:
            continue
        census.orientation_checked += 1
        backwards = _reversed_entities(solved.entities, baseline)
        if backwards:
            census.inside_out.append(
                Finding(
                    trial,
                    sketch,
                    f"the settle reversed {backwards} relative to the plain solve",
                )
            )
    census.seconds = time.perf_counter() - started
    return census


# ---------------------------------------------------------------------------
# Shrinking, without the dependency
# ---------------------------------------------------------------------------


def _referenced_ids(
    constraints: list[SketchConstraint], entities: list[SketchEntity]
) -> set[str]:
    """Entity ids any of ``constraints`` names, however it names them.

    Asked of the serialised constraints rather than by a per-kind match, so a
    constraint kind added later cannot silently drop out of it: the ids come
    from the ENTITIES, and a quoted id appearing anywhere in the JSON counts as
    a reference. Deliberately over-broad in the harmless direction — this runs
    only inside :func:`_minimise`, whose arbiter is the failing predicate
    itself, so a false reference costs a less-minimal example and nothing else.
    """
    blob = "".join(constraint.model_dump_json() for constraint in constraints)
    return {entity.id for entity in entities if f'"{entity.id}"' in blob}


def _minimise(
    sketch: SketchDefinition, fails: Callable[[SketchDefinition], bool]
) -> SketchDefinition:
    """Delta-debug ``sketch`` down while ``fails`` still holds.

    Drops constraints one at a time to a fixed point, then entities nothing
    references. This is the half of ``hypothesis`` worth having — turning a
    four-constraint failure into the one-constraint pair that causes it — and it
    runs only on the failure path, so a green run pays nothing for it.
    """
    constraints = list(sketch.constraints)
    entities = list(sketch.entities)
    shrinking = True
    while shrinking:
        shrinking = False
        for index in range(len(constraints)):
            candidate = _build(entities, constraints[:index] + constraints[index + 1 :])
            if candidate is not None and fails(candidate):
                constraints = list(candidate.constraints)
                shrinking = True
                break
    referenced = _referenced_ids(constraints, entities)
    for entity in list(entities):
        if entity.id in referenced:
            continue
        candidate = _build([e for e in entities if e.id != entity.id], constraints)
        if candidate is not None and fails(candidate):
            entities = list(candidate.entities)
    built = _build(entities, constraints)
    return built if built is not None else sketch


def _build(
    entities: list[SketchEntity], constraints: list[SketchConstraint]
) -> SketchDefinition | None:
    try:
        return SketchDefinition(entities=entities, constraints=constraints)
    except Exception:
        return None


def _reproduces(finding: Finding) -> Callable[[SketchDefinition], bool]:
    """A predicate that says whether a reduced sketch still shows this finding.

    Derived from the finding's own class, so the minimiser cannot shrink toward
    a DIFFERENT defect and present it as this one's minimal case.
    """
    if finding.kind == "raised":

        def crashes(candidate: SketchDefinition) -> bool:
            try:
                SOLVER.solve(candidate)
            except Exception:
                return True
            return False

        return crashes

    if finding.kind == "annihilated":

        def annihilates(candidate: SketchDefinition) -> bool:
            try:
                solved = SOLVER.solve(candidate)
            except Exception:
                return False
            if [e.model_dump() for e in solved.entities] == [
                e.model_dump() for e in candidate.entities
            ]:
                return False
            return any(
                isinstance(entity, SketchCircle)
                and entity.radius < DEGENERATE_RADIUS_MM
                for entity in solved.entities
            )

        return annihilates

    if finding.kind == "annihilated_arc":

        def flattens(candidate: SketchDefinition) -> bool:
            try:
                solved = SOLVER.solve(candidate)
            except Exception:
                return False
            if [e.model_dump() for e in solved.entities] == [
                e.model_dump() for e in candidate.entities
            ]:
                return False
            return any(
                isinstance(entity, SketchArc)
                and _arc_radius(entity) < DEGENERATE_ARC_RADIUS_MM
                for entity in solved.entities
            )

        return flattens

    def violates(candidate: SketchDefinition) -> bool:
        try:
            solved = SOLVER.solve(candidate)
        except Exception:
            return False
        if solved.status in PASSTHROUGH_STATUSES:
            untouched = [e.model_dump() for e in solved.entities] == [
                e.model_dump() for e in candidate.entities
            ]
            return not untouched
        if solved.status not in SOLVED_STATUSES:
            return False
        if shipped_residual(candidate, solved.entities) > SATISFIED_TOL_MM:
            return True
        baseline = _plain_solve(candidate)
        return baseline is not None and bool(
            _reversed_entities(solved.entities, baseline)
        )

    return violates


def _report(findings: list[Finding], limit: int = 3) -> str:
    head = "\n".join(finding.report() for finding in findings[:limit])
    tail = f"\n  ... and {len(findings) - limit} more" if len(findings) > limit else ""
    return head + tail


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def census() -> Census:
    """One sweep run, shared by every property below (it costs ~8 s)."""
    return run_sweep()


def test_the_sweep_actually_exercised_the_solver(
    census: Census, sweep_census: list[str]
) -> None:
    """The anti-vacuity gate: ``all([])`` is True and this repo has shipped five.

    A sweep that generates 2000 sketches and solves none of them passes every
    property below forever. So the floor is asserted first, and coverage with
    it: a constraint kind that is GENERATED but never appears in a sketch that
    SOLVES is exercised by nothing that follows.
    """
    sweep_census.extend(census.lines())
    assert census.trials == SWEEP_TRIALS
    assert census.solvable >= MIN_SOLVABLE, (
        f"only {census.solvable} of {census.trials} generated sketches solved "
        f"(floor {MIN_SOLVABLE}). Every property in this module is vacuous "
        f"below that floor. Statuses: {dict(sorted(census.statuses.items()))}"
    )
    assert census.orientation_checked >= MIN_SOLVABLE, (
        f"the SETTLE-2 arm compared only {census.orientation_checked} settles "
        "against a plain solve; it is silently doing nothing"
    )
    missing_constraints = ALL_CONSTRAINT_KINDS - set(census.solved_constraint_kinds)
    assert not missing_constraints, (
        f"{sorted(missing_constraints)} never appear in a sketch that SOLVES, "
        "so no property here is asserted about them"
    )
    missing_entities = ALL_ENTITY_KINDS - set(census.solved_entity_kinds)
    assert not missing_entities, f"{sorted(missing_entities)} never solve"


def test_no_solved_sketch_ships_a_violated_constraint(census: Census) -> None:
    """The headline number, re-measured and turned into a gate.

    RESEARCH §2: *7 of the 155 solvable sketches in that sweep shipped a
    violated constraint the same way* — ``status`` said the solve succeeded and
    the geometry beside it did not satisfy the constraints. On this corpus the
    count is **0**, and this is the assertion that keeps it there.

    Note what is being asserted: not that the solver converged, and not that it
    reported ``Success``. Those are the self-reports that lied. The evidence is
    the geometry, measured against the constraints the author submitted, to the
    documented ``SATISFIED_TOL_MM``.
    """
    assert not census.violated, (
        f"{len(census.violated)} of {census.solvable} solvable sketches ship "
        f"geometry their own constraints contradict:\n{_report(census.violated)}"
    )


def test_no_settle_ever_turns_the_geometry_inside_out(census: Census) -> None:
    """SETTLE-2's property, swept rather than sampled.

    A settle must REFINE the plain solve, never jump to a different branch of
    the solution manifold: same shape in space, opposite traversal, which flips
    every face normal downstream and resolves "the top edge" onto the bottom one
    (RESEARCH §2/§9). Constraint satisfaction cannot see it — every branch
    satisfies every constraint exactly — so this is a separate property with a
    separate witness, and the witness is re-derived here rather than borrowed
    from the code under test.
    """
    assert not census.inside_out, (
        f"{len(census.inside_out)} settles re-oriented the geometry instead of "
        f"refining it:\n{_report(census.inside_out)}"
    )


def test_a_conflicting_or_diverged_payload_returns_the_input_untouched(
    census: Census,
) -> None:
    """RECORDED LIVE LIMIT, found by this sweep: it does not always.

    ``SolvedSketch.entities`` promises "for conflicting/diverged sketches the
    input positions are returned unchanged", and ``solve()`` honours that for a
    diverged solve and for a payload the residual gate reclassifies — but NOT
    when planegcs itself diagnoses a conflict on a solve that converged: that
    path falls through to ``read_back()``, so the payload says ``conflicting``
    over geometry the solver moved. **2 of 2000 trials here.**

    Reported rather than fixed (PBT-1 is the sweep; which of the two the
    contract should follow is a separate decision). The bound is written BOTH
    WAYS on purpose: if this reaches 0 the defect has been fixed and this test
    must be deleted, which is a change nobody should be able to make silently.
    A recorded limit that can only fail in one direction stops being a record
    the moment the limit is lifted — the same reason a ``test.fail()`` case that
    starts PASSING is a real failure and needs saying by name.
    """
    assert 1 <= len(census.moved_passthrough) <= 20, (
        f"{len(census.moved_passthrough)} payloads breached the "
        "'input returned unchanged' contract; 2 were recorded when this limit "
        "was written. If this is 0, the gap is CLOSED — delete this test and "
        f"say so in the commit.\n{_report(census.moved_passthrough)}"
    )


def test_no_generated_sketch_makes_the_solver_raise(census: Census) -> None:
    """SOLVE-CRASH-1's gate, replacing the live limit that recorded it.

    The ``SketchSolver`` contract is that solve OUTCOMES are reported in
    ``status`` and exceptions are reserved for malformed INPUT. Every sketch
    this corpus generates is well-formed by construction (``_constraint`` draws
    only type-valid operands), so ANY exception out of ``solve()`` is a breach
    of that contract and reaches a user as an untyped 500 — a dead end with
    nothing attached that says what is wrong.

    It was 12 of 2000 (0.6%) when this sweep first ran: planegcs drove a
    circle's radius through zero and ``read_back()`` built a DTO the DTO
    refuses. Nine of those are now ``conflicting`` with the offending tangency
    NAMED, and three of them solve — see
    ``test_sketch_degenerate_radius.py`` for why those two answers are both
    right and why one rule for all twelve would have been wrong.
    """
    assert not census.crashed, (
        f"{len(census.crashed)} of {census.trials} sketches raised out of "
        f"solve(); a solve outcome may not be an exception:\n"
        f"{_report(census.crashed)}"
    )


def test_no_solved_payload_ships_a_circle_that_is_not_there(census: Census) -> None:
    """SOLVE-CRASH-1's SILENT half, which no property here could see.

    A crash is the loud end of this defect; the quiet end is the same collapse
    landing a bit-width on the other side of zero. This corpus was shipping
    circles of radius ``8.9e-16`` and ``2.7e-15`` mm under
    ``status="underconstrained"`` with an empty conflict list (trials 644 and
    926), and every property in this module agreed with it: the residual of a
    tangency to a point-sized circle whose centre sits on the line is *zero*, so
    the payload is self-consistent and geometrically absent.

    Measured, and this is why the fix is a magnitude test rather than the DTO's
    own ``gt=0``: with the minimal fix (substitute only when the DTO would
    refuse) the annihilated-circle fixture in ``test_sketch_degenerate_radius``
    ships ``radius=2.27e-16`` under ``underconstrained`` — the crash traded for
    a lie. This assertion is what refuses that trade.
    """
    assert not census.annihilated, (
        f"{len(census.annihilated)} payloads ship a circle the solve drove "
        f"below {DEGENERATE_RADIUS_MM} mm, i.e. geometry that is not there:\n"
        f"{_report(census.annihilated)}"
    )


def test_no_solved_payload_ships_an_arc_that_is_not_there(census: Census) -> None:
    """ARC-DEGENERATE-1 — the same defect with NO loud half at all.

    A circle annihilated by a solve at least crashed, because ``radius`` is
    ``gt=0``. An arc DERIVES its radius from ``center``/``start``/``end``, so
    annihilating one builds a DTO nothing refuses, and the residual is **zero** —
    a constraint satisfied by putting a point on a point is satisfied exactly. So
    this corpus was shipping **27 arcs of radius 4e-14 mm or less** (25 under
    ``overconstrained``, 2 under ``underconstrained``) and every property in this
    module agreed with all of them, which is why the ticket was filed off an
    ASYMMETRY — ``_add_entity`` refuses that exact shape on INPUT — rather than
    off any failure.

    Deliberately a separate assertion from
    :func:`test_no_solved_payload_ships_a_circle_that_is_not_there` even though
    both say "no geometry that is not there": the thresholds differ
    (``DEGENERATE_ARC_RADIUS_MM`` vs ``DEGENERATE_RADIUS_MM``, for the measured
    reason in the constant's own docstring), so one message must not be able to
    stand in for the other when a floor moves.
    """
    assert not census.annihilated_arcs, (
        f"{len(census.annihilated_arcs)} payloads ship an arc the solve drove "
        f"onto its own centre (below {DEGENERATE_ARC_RADIUS_MM} mm), i.e. "
        f"geometry that is not there:\n{_report(census.annihilated_arcs)}"
    )


def test_an_overconstrained_payload_is_either_solved_or_the_input(
    census: Census,
) -> None:
    """The documented disjunction, asserted as one.

    ``SolvedSketch.entities`` says positions are solved for "consistent
    overconstrained cases" — so an overconstrained payload carries either
    geometry that satisfies its constraints, or the input returned unchanged,
    and nothing else. BOTH occur in this corpus (282 overconstrained, of which
    17 are the input returned), which is why ``overconstrained`` is not in
    :data:`SOLVED_STATUSES`: a client cannot tell the two apart from the status
    alone, and the sweep must not count the author's own coordinates as the
    solver's claim about them.

    That ambiguity is worth closing and is reported with the other findings.
    Shipping the THIRD thing — geometry the solver MOVED, under a status saying
    it solved, that its constraints contradict — would be the 7-of-155 defect
    wearing a different status, and this is what refuses it.
    """
    assert not census.dirty_overconstrained, (
        "an overconstrained payload shipped MOVED geometry that violates its "
        f"constraints:\n{_report(census.dirty_overconstrained)}"
    )


def test_the_corpus_is_a_pure_function_of_its_seed(census: Census) -> None:
    """Determinism of the INPUTS, which is the whole case for a seeded sweep.

    A short second run, compared sketch-for-sketch against a third: if the
    generator ever picks up an unseeded source of entropy — a set iteration, a
    dict ordering, ``id()`` — "trial 341 fails" stops being a bug report and
    every recorded count above becomes a flake. Cheap to assert, and it is the
    property that justifies not taking the ``hypothesis`` dependency.
    """
    first = [
        generate_sketch(rng).model_dump_json()
        for rng in [random.Random(SWEEP_SEED)] * 1
        for _ in range(50)
    ]
    second_rng = random.Random(SWEEP_SEED)
    second = [generate_sketch(second_rng).model_dump_json() for _ in range(50)]
    assert first == second
    assert len(set(first)) == 50, "the generator is emitting duplicate sketches"
    assert census.trials == SWEEP_TRIALS
