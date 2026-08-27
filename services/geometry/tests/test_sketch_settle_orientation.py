"""SETTLE-2 — settling REFINES the plain solve; it never re-orients geometry.

Companion to ``test_sketch_free_dof_hold.py`` (SOLVE-1), which established that
an under-constrained solve must hold the coordinates the author submitted. This
file is the other side of that contract: holding an input coordinate must not be
allowed to buy itself a DIFFERENT BRANCH of the solution manifold.

## The defect

``sketch-datum-flow.spec.ts`` drives the SKETCH-2 walk — a rigid rectangle,
floating at y in [8, 24], made ``symmetric`` about the plane's X axis. The
constraint has to move it, and there are two ways to satisfy it:

===============  ====================================  ==================
solve            e4 (the left edge) start.y -> end.y   what happened
===============  ====================================  ==================
plain            +8 -> -8                              TRANSLATED down 16
settled          -8 -> +8                              REFLECTED
===============  ====================================  ==================

Both put the rectangle in the same place — x in [10, 34], y in [-8, 8] — and
both satisfy every constraint, the reflection with the SMALLER residual, which
is why nothing in the solver objected. What differs is the CORRESPONDENCE:
settling held the two bottom corners at the y the author gave them and sent the
two top corners past them, so the profile's wire runs the other way round. For a
kernel that is not cosmetic. A closed wire's traversal sets the face normal
every downstream feature is built on, and a stored topological reference to "the
top edge" resolves to the bottom one after a rebuild (RESEARCH §9).

Settling produced it by accident of greed: each hold is judged alone, and
holding four corners at their submitted y scores better by settle's own rule
than holding none — the rule never asked what the other four corners had to do
to allow it.

## Why the guard is a direction test, and why it is all-or-nothing

Two plausible fixes were built and measured, and both are wrong:

* **Refuse a settle that ends FARTHER from the author's input.** No displacement
  statistic separates the two fixtures — all four rank them the same way, so no
  threshold on any of them exists.
  ``test_a_distance_guard_could_not_have_told_these_apart`` keeps that negative
  result executable. It is structural: a least-squares solve is already near the
  minimum-norm correction so it always wins on total displacement, while what
  SOLVE-1 wants is the SPARSE correction — and a reflection is sparse too.
* **Refuse the individual holds that reverse an entity, keep the rest.** The
  tempting one, and measurably worse: the surviving holds pin the two TOP
  corners at ``y = 24`` and symmetry drives the bottom pair to ``-24``, a
  rectangle stretched from 16 mm to 48 mm, right way up. Holding a SUBSET of a
  rigid body's points distorts the body. ``_keep_or_roll_back``'s docstring
  records this; the choice is all of them or none.

So the guard is one dot product per entity over the FINISHED settle, and on
this sketch it declines the settle entirely — leaving the plain solve, which is
exactly what shipped before SOLVE-1 and is correct here.

## Tolerance (RESEARCH §9 — derived, never ad hoc)

The orientation assertion needs NO tolerance: it is the sign of a coordinate,
and the reflection is a 16 mm error. ``CENTRING_TOL_MM`` below is derived from a
measurement and carries its working.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from geometry.sketch import (
    CoincidentConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchSolver,
    SymmetricConstraint,
    VerticalConstraint,
)
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _turns_geometry_inside_out,  # pyright: ignore[reportPrivateUsage]
)

SOLVER: SketchSolver = PlanegcsSketchSolver()

#: Half-length of the materialised datum axis. ``apps/web/src/sketch/datum.ts``
#: sizes it to the drawn frame (1.25x the frame half-height), which at the
#: parked camera is of this order.
AXIS_HALF_MM = 100.0

#: The rectangle ``sketch-datum-flow.spec.ts`` seeds as ``RIGID_RECT``:
#: 24 x 16 at (10, 8), rigid in SHAPE and floating in POSITION.
CORNERS: list[tuple[float, float]] = [
    (10.0, 8.0),
    (34.0, 8.0),
    (34.0, 24.0),
    (10.0, 24.0),
]

#: Where the symmetric constraint must leave the left edge: the rectangle
#: centres on the axis, top corner still on top.
EXPECTED_LEFT_EDGE_Y = (8.0, -8.0)

#: Per-model tolerance for the centring assertions.
#:
#: The rectangle's SIZE is a free degree of freedom here (DOF 3 after the
#: symmetric: x, width, height), so the plain solve is entitled to smear a
#: little of the correction into it — and it does, by an amount that is pure
#: conditioning of the datum axis. Measured on this fixture as the axis grows:
#:
#:     axis half-length L   25       40       80       100      200
#:     |e4.start.y - 8|     3.0e-2   5.3e-3   3.6e-4   1.5e-4   9.3e-6
#:
#: At the realistic ``AXIS_HALF_MM`` the residual is 1.5e-4 mm, so 1e-3 mm
#: carries a ~7x margin over the plain solve's own smear while sitting FOUR
#: ORDERS below the 16 mm the reflection moves each corner: the assertion can
#: neither pass by accident nor fail on conditioning noise. It is deliberately
#: not ``SATISFIED_TOL_MM`` — that constant bounds a CONSTRAINT RESIDUAL, and
#: the symmetric constraint is satisfied here to the bit (see
#: ``test_the_profile_really_does_centre_on_the_axis``, which asserts the
#: centre at ``SATISFIED_TOL_MM``). What this bounds is a free DOF the solve was
#: never obliged to hold at all.
CENTRING_TOL_MM = 1e-3


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def _line(
    entity_id: str,
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    construction: bool = False,
) -> SketchLine:
    return SketchLine.model_validate(
        {
            "id": entity_id,
            "kind": "line",
            "construction": construction,
            "start": {"x": a[0], "y": a[1]},
            "end": {"x": b[0], "y": b[1]},
        }
    )


def symmetric_plate(*, entities: list[SketchEntity] | None = None) -> SketchDefinition:
    """SKETCH-2's rigid rectangle, made symmetric about the datum X axis.

    Four coincident corners plus both axis-aligned pairs, so the profile can
    only translate and resize. The X axis is ordinary CONSTRUCTION geometry with
    both endpoints pinned — exactly how the web sketcher materialises a datum
    the moment a constraint references it (``groundDatums``). The pins are
    load-bearing: without them a symmetric to the axis is satisfiable by moving
    the AXIS, which would take the sketch's zero with it.

    ``entities`` replays the product's feedback loop (``PartPage`` adopts solved
    positions back into the store), the same seam the SOLVE-1 suite uses.
    """
    if entities is None:
        drawn: list[SketchEntity] = [
            _line(f"e{i + 1}", CORNERS[i], CORNERS[(i + 1) % 4]) for i in range(4)
        ]
        drawn.append(
            _line(
                "x-axis",
                (-AXIS_HALF_MM, 0.0),
                (AXIS_HALF_MM, 0.0),
                construction=True,
            )
        )
    else:
        drawn = [entity.model_copy(deep=True) for entity in entities]

    constraints: list[SketchConstraint] = [
        CoincidentConstraint(
            kind="coincident",
            a=_ref(f"e{i + 1}", "end"),
            b=_ref(f"e{((i + 1) % 4) + 1}", "start"),
        )
        for i in range(4)
    ]
    constraints += [
        HorizontalConstraint(kind="horizontal", entity="e1"),
        HorizontalConstraint(kind="horizontal", entity="e3"),
        VerticalConstraint(kind="vertical", entity="e2"),
        VerticalConstraint(kind="vertical", entity="e4"),
        SymmetricConstraint(
            kind="symmetric", a=_ref("e4", "end"), b=_ref("e4", "start"), line="x-axis"
        ),
        FixedConstraint(kind="fixed", point=_ref("x-axis", "start")),
        FixedConstraint(kind="fixed", point=_ref("x-axis", "end")),
    ]
    return SketchDefinition(entities=drawn, constraints=constraints)


def _lines(entities: list[SketchEntity]) -> dict[str, SketchLine]:
    return {e.id: e for e in entities if isinstance(e, SketchLine)}


def _profile_ys(entities: list[SketchEntity]) -> list[float]:
    lines = _lines(entities)
    return [
        v for e in ("e1", "e2", "e3", "e4") for v in (lines[e].start.y, lines[e].end.y)
    ]


def _coordinates(entities: list[SketchEntity]) -> list[float]:
    out: list[float] = []
    for entity in entities:
        if isinstance(entity, SketchLine):
            out += [entity.start.x, entity.start.y, entity.end.x, entity.end.y]
    return out


# -- the defect ----------------------------------------------------------------


def test_symmetric_about_a_datum_axis_does_not_reflect_the_profile() -> None:
    """THE REGRESSION, asserted without a tolerance: the top corner stays on top.

    ``e4`` is authored from (10, 24) down to (10, 8), so its start is the TOP
    corner. After the solve its start must still be the upper of the two. A
    bounding-box assertion cannot see this defect — both answers occupy exactly
    the same rectangle — so this reads the edge's own endpoints, and it reads
    their SIGN, which no conditioning can blur.
    """
    left = _lines(SOLVER.solve(symmetric_plate()).entities)["e4"]
    assert left.start.y > 0.0 > left.end.y, (
        f"e4 runs {left.start.y} -> {left.end.y}: the profile was reflected, "
        "not translated"
    )


def test_the_profile_really_does_centre_on_the_axis() -> None:
    """The positive control: refusing the reflection must not refuse the MOVE.

    A guard that simply handed back the input would satisfy the sign test above
    (the author's own corners are at +8 and +24, both positive), so this pins
    what the symmetric constraint is FOR. The centre lands on the axis to the
    bit — that part IS a constraint residual — and the corners at +/-8.
    """
    solved = SOLVER.solve(symmetric_plate())
    ys = _profile_ys(solved.entities)
    assert (max(ys) + min(ys)) / 2 == pytest.approx(0.0, abs=SATISFIED_TOL_MM)
    assert max(ys) == pytest.approx(8.0, abs=CENTRING_TOL_MM)
    assert min(ys) == pytest.approx(-8.0, abs=CENTRING_TOL_MM)
    left = _lines(solved.entities)["e4"]
    assert (left.start.y, left.end.y) == pytest.approx(
        EXPECTED_LEFT_EDGE_Y, abs=CENTRING_TOL_MM
    )


def test_the_answer_is_stable_under_the_products_feedback_loop() -> None:
    """Re-solving from the previous answer must not start the reflection over.

    ``PartPage`` adopts solved positions back into the sketch, so every solve
    after the first is fed its own output. A guard that only held on the first
    pass would let the profile flip on the second — the shape of defect the
    SOLVE-1 suite had to replay this same loop to catch.
    """
    solved = SOLVER.solve(symmetric_plate())
    for _ in range(3):
        solved = SOLVER.solve(symmetric_plate(entities=solved.entities))
        left = _lines(solved.entities)["e4"]
        assert left.start.y > 0.0 > left.end.y
        assert (left.start.y, left.end.y) == pytest.approx(
            EXPECTED_LEFT_EDGE_Y, abs=CENTRING_TOL_MM
        )


def test_settling_this_sketch_is_bitwise_deterministic() -> None:
    """RESEARCH §9, at sequence level: identical definition in, identical out.

    Bitwise (``==``), no tolerance — determinism takes none — and over the whole
    feedback sequence rather than one solve, because the guard is evaluated per
    solve and a per-solve decision is exactly the kind that can drift across a
    sequence. A fresh backend for the second run, so no solver state carries.
    """

    def sequence(solver: SketchSolver) -> list[list[float]]:
        out: list[list[float]] = []
        solved = solver.solve(symmetric_plate())
        out.append(_coordinates(solved.entities))
        for _ in range(3):
            solved = solver.solve(symmetric_plate(entities=solved.entities))
            out.append(_coordinates(solved.entities))
        return out

    assert sequence(SOLVER) == sequence(PlanegcsSketchSolver())


# -- the guard itself ----------------------------------------------------------


def test_the_guard_fires_on_a_reversed_entity_and_only_on_one() -> None:
    """Unit-level positive and negative controls for the predicate.

    Written against the predicate directly: the integration tests above observe
    it only through a solve, so a change that quietly disabled it would still
    pass whenever the solver happened not to flip anything.
    """
    baseline: list[SketchEntity] = [_line("e1", (0.0, 0.0), (10.0, 0.0))]
    nudged: list[SketchEntity] = [_line("e1", (0.0, 0.1), (10.0, -0.1))]
    square: list[SketchEntity] = [_line("e1", (0.0, 0.0), (0.0, 10.0))]
    reversed_: list[SketchEntity] = [_line("e1", (10.0, 0.0), (0.0, 0.0))]

    assert not _turns_geometry_inside_out(nudged, baseline)
    # A right angle is not a reversal — the guard must not fire short of one.
    assert not _turns_geometry_inside_out(square, baseline)
    assert _turns_geometry_inside_out(reversed_, baseline)


def test_a_degenerate_entity_needs_no_epsilon_to_survive_the_guard() -> None:
    """A zero-length line has no direction, so it can never read as reversed.

    This is why the predicate carries no tolerance (CLAUDE.md — no ad-hoc
    epsilons): its dot product is ``0.0``, which fails a strict ``< 0``.
    """
    baseline: list[SketchEntity] = [_line("e1", (0.0, 0.0), (10.0, 0.0))]
    collapsed: list[SketchEntity] = [_line("e1", (5.0, 5.0), (5.0, 5.0))]
    assert not _turns_geometry_inside_out(collapsed, baseline)
    assert not _turns_geometry_inside_out(baseline, collapsed)


def _solve_1_fixtures() -> ModuleType:
    """The SOLVE-1 suite's coupling fixture, imported by PATH.

    ``pyproject.toml`` sets ``--import-mode=importlib``, so sibling test modules
    are NOT importable by name; loading it by location is the supported way to
    share a fixture between two test files without duplicating it (DRY —
    CLAUDE.md), and re-declaring the audit's profile here is precisely the
    duplicate that would drift.
    """
    name = "test_sketch_free_dof_hold"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(f"{name}.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_a_distance_guard_could_not_have_told_these_apart() -> None:
    """The negative result behind the design choice, kept executable.

    Every displacement statistic ranks the settled answer the SAME way on both
    fixtures — worse on the R-5b edit that must be KEPT and worse on the
    SKETCH-2 reflection that must be REFUSED — so no threshold on any of them
    separates the two. Should that ever stop being true, this fails and the
    choice of a direction guard deserves re-deriving rather than inheriting.
    """
    import geometry.sketch.planegcs_solver as module

    fixtures = _solve_1_fixtures()

    def displacements(
        sketch: SketchDefinition, entities: list[SketchEntity]
    ) -> list[float]:
        source = _lines(list(sketch.entities))
        out: list[float] = []
        for entity in entities:
            if not isinstance(entity, SketchLine):
                continue
            was = source[entity.id]
            for name in ("start", "end"):
                a, b = getattr(entity, name), getattr(was, name)
                out.append(((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5)
        return out

    def plain_and_settled(
        sketch: SketchDefinition,
    ) -> tuple[list[float], list[float]]:
        """The two candidates ``settle`` chooses between, for one sketch."""
        captured: dict[str, list[SketchEntity]] = {}
        build = module._GcsBuild  # pyright: ignore[reportPrivateUsage]
        original = build.settle

        def spy(self: "module._GcsBuild") -> list[SketchEntity]:  # pyright: ignore[reportPrivateUsage]
            captured["plain"] = self.read_back()
            original(self)
            captured["settled"] = self.read_back()
            return captured["settled"]

        build.settle = spy  # type: ignore[method-assign]
        try:
            PlanegcsSketchSolver().solve(sketch)
        finally:
            build.settle = original  # type: ignore[method-assign]
        return (
            displacements(sketch, captured["plain"]),
            displacements(sketch, captured["settled"]),
        )

    edited = list(fixtures.DIMENSIONS)
    edited[fixtures.EDITED_EDGE] = fixtures.EDITED_VALUE_MM
    first = PlanegcsSketchSolver().solve(fixtures.coupling_profile(fixtures.DIMENSIONS))
    keep_plain, keep_settled = plain_and_settled(
        fixtures.coupling_profile(edited, entities=first.entities)
    )
    drop_plain, drop_settled = plain_and_settled(symmetric_plate())

    metrics: dict[str, Callable[[list[float]], float]] = {
        "sum of squares": lambda d: sum(v * v for v in d),
        "worst point": max,
        "points moved": lambda d: float(sum(1 for v in d if v > SATISFIED_TOL_MM)),
        "sum of displacements": sum,
    }
    for name, metric in metrics.items():
        keeps = metric(keep_settled) < metric(keep_plain)
        drops = metric(drop_settled) < metric(drop_plain)
        assert keeps == drops, (
            f"{name!r} now separates the two fixtures (R-5b prefers the settle: "
            f"{keeps}; SKETCH-2 prefers the settle: {drops}) — a distance guard "
            "may have become viable; re-derive settle()'s choice."
        )
