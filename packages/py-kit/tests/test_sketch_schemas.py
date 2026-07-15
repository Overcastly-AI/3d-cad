"""Sketch schema helpers — the typed over-constraint diagnosis (BACKLOG #6).

Covers :func:`py_kit.schemas.sketch.classify_overconstraint`: a pure function
that turns the solver's already-computed ``conflicting``/``redundant`` sets
(:class:`SolvedSketch`) into a typed :class:`SketchConstraintDiagnosis` — the
structured shape a caller reads BY FIELD instead of parsing a message string.
This is the backend classification building block; wiring it onto the
``sketch_conflicting`` ``FeatureError`` and the solved-sketch payload (plus the
sketcher UI reading the typed field) is the follow-up leg.
"""

from py_kit.schemas.sketch import (
    SketchConstraintDiagnosis,
    SolvedSketch,
    classify_overconstraint,
)


def _solved(
    status: str, *, conflicting: list[int], redundant: list[int]
) -> SolvedSketch:
    """A minimal SolvedSketch with the diagnosis fields set (entities empty)."""
    return SolvedSketch(
        status=status,  # pyright: ignore[reportArgumentType]
        entities=[],
        conflicting_constraints=conflicting,
        redundant_constraints=redundant,
    )


def test_conflicting_is_classified_unsolvable_with_named_ids() -> None:
    diag = classify_overconstraint(
        _solved("conflicting", conflicting=[2, 5], redundant=[])
    )
    assert isinstance(diag, SketchConstraintDiagnosis)
    assert diag.classification == "conflicting"
    assert diag.removable is False  # no solution until one is relaxed
    assert diag.conflicting_constraints == [2, 5]
    assert diag.suggested_fix is not None
    assert "2" in diag.suggested_fix  # names the first offending constraint


def test_overconstrained_is_classified_redundant_and_removable() -> None:
    diag = classify_overconstraint(
        _solved("overconstrained", conflicting=[], redundant=[3])
    )
    assert isinstance(diag, SketchConstraintDiagnosis)
    assert diag.classification == "redundant"
    assert diag.removable is True  # still solves once dropped
    assert diag.redundant_constraints == [3]
    assert diag.conflicting_constraints == []
    assert diag.suggested_fix == "Remove constraint 3"


def test_conflicting_carries_any_redundant_ids_planegcs_also_reported() -> None:
    diag = classify_overconstraint(
        _solved("conflicting", conflicting=[1], redundant=[4])
    )
    assert diag is not None
    assert diag.classification == "conflicting"
    assert diag.conflicting_constraints == [1]
    assert diag.redundant_constraints == [4]  # surfaced, but conflict dominates


def test_solved_statuses_have_no_overconstraint_diagnosis() -> None:
    """converged / underconstrained / diverged are not over-constraints → None."""
    for status in ("converged", "underconstrained", "diverged"):
        assert (
            classify_overconstraint(_solved(status, conflicting=[], redundant=[]))
            is None
        )
