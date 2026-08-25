"""SETTLE-PERF-1 — the settle is bounded, and the bound is not a clock.

SOLVE-1/SETTLE-2/SETTLE-3 bought correctness this project needed; what they did
not buy was a cost model. The per-entity ladder puts a yes/no question to the
solver per entity, per point and per coordinate, on a system whose every solve
is itself quadratic in entity count — ``O(E**3)`` — and the engineering audit
measured what that costs on an ordinary part (``docs/AUDIT-ENGINEERING.md``
N11): a 48-line rectilinear outline took **13 seconds** to answer one dimension
edit, and a 96-line one **196 seconds**, against a gateway that abandons the
request at 90 s and deliberately does not cancel the upstream.

This suite locks the two properties of the fix that a benchmark cannot state:

* **The budget is a function of the SKETCH, never of the clock.** A wall-clock
  deadline was the audit's own suggestion and is the wrong shape here, because
  the settle CHOOSES GEOMETRY: a deadline makes the shipped shape depend on how
  busy the machine was, which is precisely what RESEARCH §9's determinism gate
  forbids. The tests below assert the bound is derived from the entity count and
  that a budgeted settle is bitwise reproducible.
* **Bounded is not broken.** Every guarantee the settle already carried — every
  caller constraint satisfied, never re-oriented, never worse than the plain
  solve — still holds when the budget bites, because it runs out of QUESTIONS,
  not out of checks.

The correctness contract itself lives where it always did
(``test_sketch_free_dof_hold.py``, ``test_sketch_settle_orientation.py``,
``test_sketch_settle_sacrifice.py``); nothing here replaces it.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import ModuleType

from geometry.sketch import PlanegcsSketchSolver, evaluate_driving_dimensions
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    SETTLE_WORK_UNITS,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import worst_residual
from geometry.sketch.schemas import SketchEntity, SketchLine

_OUTLINE_PATH = Path(__file__).resolve().parent / "_sketch_outline_builder.py"


def _load_outline_builder() -> ModuleType:
    """Import by path — the workspace runs pytest with ``--import-mode=importlib``,
    so test modules cannot import one another (conftest.py's note)."""
    spec = importlib.util.spec_from_file_location(
        "_sketch_outline_builder", _OUTLINE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OUTLINES = _load_outline_builder()
SOLVER = PlanegcsSketchSolver()

#: Big enough that the ladder's budget genuinely bites (96 lines needs far more
#: trial solves than SETTLE_WORK_UNITS allows it), and the size at which the
#: unfixed settle burned 196 s.
BUDGET_BITING_LINES = 96


def _coordinates(entities: list[SketchEntity]) -> list[float]:
    """Every coordinate of every entity, in input order — the whole answer."""
    values: list[float] = []
    for entity in entities:
        assert isinstance(entity, SketchLine)
        values += [entity.start.x, entity.start.y, entity.end.x, entity.end.y]
    return values


def test_the_ladder_budget_is_a_function_of_the_sketch_alone() -> None:
    """No clock, no load, no machine — just the entity count.

    The distinction is the whole reason this is a work budget and not the
    wall-clock deadline the audit proposed: two solves of the same sketch must
    reach the same geometry however busy the box was (RESEARCH §9).
    """
    for line_count in (4, 12, 48, 96):
        sketch = _OUTLINES.outline(line_count, width_mm=14.0)
        first = _GcsBuild(sketch, {})._ladder_budget()  # pyright: ignore[reportPrivateUsage]
        second = _GcsBuild(sketch, {})._ladder_budget()  # pyright: ignore[reportPrivateUsage]
        assert first == second == SETTLE_WORK_UNITS // line_count**2, (
            f"the {line_count}-line budget is not the documented "
            f"SETTLE_WORK_UNITS // entities**2"
        )


def test_a_budgeted_settle_is_bitwise_reproducible() -> None:
    """RESEARCH §9's determinism gate, at a size where the budget runs out.

    A settle that stops early still has to stop in the same PLACE every time.
    Bitwise equality, no tolerance — a budget that leaked any wall-clock
    dependence would show up here as a flake rather than as a failure, so the
    repeat count is deliberately more than two.
    """
    sketch = _OUTLINES.outline(BUDGET_BITING_LINES, width_mm=14.0)
    answers = [PlanegcsSketchSolver().solve(sketch) for _ in range(4)]
    reference = _coordinates(answers[0].entities)
    for index, answer in enumerate(answers[1:], start=2):
        assert _coordinates(answer.entities) == reference, (
            f"solve {index} of the same {BUDGET_BITING_LINES}-line outline "
            "returned different geometry"
        )
        assert (answer.status, answer.dof) == (answers[0].status, answers[0].dof)


def test_running_out_of_budget_never_ships_a_violated_constraint() -> None:
    """The budget removes QUESTIONS, not CHECKS.

    Both of the settle's guarantees are asserted over the answer it actually
    ships: every caller constraint satisfied (SETTLE-3's second witness,
    re-derived from the DTOs rather than asked of the solver), and the reported
    status unchanged from the plain solve's diagnosis.
    """
    sketch = _OUTLINES.outline(BUDGET_BITING_LINES, width_mm=14.0)
    solved = SOLVER.solve(sketch)
    assert solved.status == "underconstrained"
    assert solved.dof == BUDGET_BITING_LINES - 1
    assert not solved.conflicting_constraints
    submitted = {
        (entity.id, name): (point.x, point.y)
        for entity in sketch.entities
        if isinstance(entity, SketchLine)
        for name, point in (("start", entity.start), ("end", entity.end))
    }
    assert (
        worst_residual(sketch.constraints, solved.entities, submitted, {})
        <= SATISFIED_TOL_MM
    )


def test_the_budget_does_not_buy_speed_by_giving_up_the_drawn_shape() -> None:
    """A cheap settle that distorted the profile would be no settle at all.

    The outline is rectilinear with one driving width, so the 4 mm has to come
    out of exactly ONE other horizontal edge — every other edge is geometry the
    edit never named (SOLVE-1's principle), and the settle's job is to keep it
    at the length the author drew. ``e2`` is the horizontal the ladder reaches
    first after the dimensioned ``e0``, and which edge gives way is a policy
    outcome, so it is named rather than counted.

    The negative control is in the same test on purpose: the UNSETTLED solve of
    this very sketch — the answer that ships when the settle declines — distorts
    strictly more, so a "budget" that quietly degraded to no settle at all would
    fail here rather than pass by counting to one.
    """
    sketch = _OUTLINES.outline(BUDGET_BITING_LINES, width_mm=14.0)
    drawn = {entity.id: entity for entity in sketch.entities}

    def distorted_edges(entities: list[SketchEntity]) -> list[str]:
        changed: list[str] = []
        for entity in entities:
            if entity.id == "e0":  # the dimensioned edge; it is meant to change
                continue
            was = drawn[entity.id]
            assert isinstance(entity, SketchLine) and isinstance(was, SketchLine)
            if not math.isclose(
                math.hypot(
                    entity.end.x - entity.start.x, entity.end.y - entity.start.y
                ),
                math.hypot(was.end.x - was.start.x, was.end.y - was.start.y),
                abs_tol=SATISFIED_TOL_MM,
            ):
                changed.append(entity.id)
        return changed

    settled = distorted_edges(SOLVER.solve(sketch).entities)
    assert settled == ["e2"], (
        "a budgeted settle must still keep every edge the edit did not name at "
        f"the length the author drew; these changed: {settled}"
    )
    build = _GcsBuild(sketch, evaluate_driving_dimensions(sketch.constraints))
    build.gcs.solve()
    unsettled = distorted_edges(build.read_back())
    assert len(unsettled) > len(settled), (
        "the negative control did not reproduce: the unsettled solve was "
        f"expected to distort more than the budgeted settle, but it changed "
        f"{unsettled}"
    )


def test_an_already_solved_outline_never_reaches_the_ladder() -> None:
    """The commonest solve in the product costs no trial solve at all.

    ``PartPage`` adopts solved positions back into the store, so a tree rebuild
    re-solves every sketch from a configuration that is already an exact
    solution. Holding all of it is then satisfied where the system already
    stands, so it is accepted with no solver call — and the ladder, with its
    budget, is never entered. That is why the fast path stayed fast while the
    edited path was cubic, and it is the row a "speed up the edit" change must
    not redden.
    """
    sketch = _OUTLINES.outline(BUDGET_BITING_LINES, width_mm=None)
    build = _GcsBuild(sketch, {})
    build.gcs.solve()
    build._baseline_holds = build._constraints_satisfied([])  # pyright: ignore[reportPrivateUsage]
    before = build._trial_solves_left  # pyright: ignore[reportPrivateUsage]
    assert build._try_hold_everything() is True  # pyright: ignore[reportPrivateUsage]
    assert build._trial_solves_left == before, (  # pyright: ignore[reportPrivateUsage]
        "the already-solved fast path spent a trial solve; it should be "
        "satisfied where the system already stands"
    )
