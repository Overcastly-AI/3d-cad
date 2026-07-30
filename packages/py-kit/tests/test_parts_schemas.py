"""Part boundary DTOs — the ONE staleness rule and the provenance it compares.

What is under test is the claim a consumer is allowed to make: "what I am
showing you was built from the tree as it stands." That claim needs two
numbers on the wire — the version a result was BUILT FROM
(:attr:`EvaluateTreeResult.tree_version`) and the part's CURRENT version
(:attr:`PartResponse.tree_version`) — folded by ONE comparison
(:func:`is_stale_for_tree`), never re-implemented per consumer and never
guessed from timestamps (docs/design/feature-tree.md §4.4a, docs/UI-REVIEW.md
F2). The four-state fold and the two DTOs are pinned together here because
separating them is exactly how a status string drifts away from the value it
claims to describe.
"""

import uuid
from datetime import UTC, datetime

import pytest
from py_kit.schemas.features import EvaluateTreeResult
from py_kit.schemas.materials import EMPTY_MATERIAL_ASSIGNMENT
from py_kit.schemas.parts import (
    PartResponse,
    derive_part_eval_scope,
    derive_part_eval_state,
    is_stale_for_tree,
)
from pydantic import ValidationError

NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)


def _part(*, tree_version: int, eval_tree_version: int | None) -> PartResponse:
    """A part row at *tree_version* whose last evaluate saw *eval_tree_version*."""
    return PartResponse(
        id=uuid.uuid4(),
        name="Bracket",
        owner_id=uuid.uuid4(),
        length_unit="mm",
        materials=EMPTY_MATERIAL_ASSIGNMENT,
        tree_version=tree_version,
        eval_state=derive_part_eval_state(
            last_eval_status=None if eval_tree_version is None else "ok",
            last_eval_tree_version=eval_tree_version,
            tree_version=tree_version,
        ),
        last_eval_status=None if eval_tree_version is None else "ok",
        last_eval_at=None if eval_tree_version is None else NOW,
        last_eval_tree_version=eval_tree_version,
        created_at=NOW,
        updated_at=NOW,
    )


def _result(*, tree_version: int) -> EvaluateTreeResult:
    """An evaluate result whose body was built from *tree_version*."""
    return EvaluateTreeResult(
        part_id=uuid.uuid4(),
        tree_version=tree_version,
        features=[],
        mesh_glb_id="sha256:" + "a" * 64,
        properties=None,
        last_good_feature_id=None,
    )


# --- the rule -------------------------------------------------------------------


def test_a_result_from_the_current_version_is_not_stale() -> None:
    assert not is_stale_for_tree(built_from_tree_version=7, tree_version=7)


def test_a_result_from_an_older_version_is_stale() -> None:
    assert is_stale_for_tree(built_from_tree_version=6, tree_version=7)


def test_any_mismatch_is_stale_not_just_an_older_one() -> None:
    """Inequality, not ``<``: a result stamped with a version the part has never
    reached (a raced write, a restored snapshot) describes some other tree, so it
    is just as unusable as an old one — never quietly accepted as current."""
    assert is_stale_for_tree(built_from_tree_version=8, tree_version=7)


# --- the fold over a stored record ----------------------------------------------


def test_no_record_claims_nothing() -> None:
    assert (
        derive_part_eval_state(
            last_eval_status=None, last_eval_tree_version=None, tree_version=3
        )
        == "never"
    )
    # A half-written record is still "nothing known", never a bare status.
    assert (
        derive_part_eval_state(
            last_eval_status="ok", last_eval_tree_version=None, tree_version=3
        )
        == "never"
    )


@pytest.mark.parametrize("status", ["ok", "failed"])
def test_a_record_for_the_current_tree_reports_its_verdict(status: str) -> None:
    assert (
        derive_part_eval_state(
            last_eval_status="ok" if status == "ok" else "failed",
            last_eval_tree_version=4,
            tree_version=4,
        )
        == status
    )


@pytest.mark.parametrize("status", ["ok", "failed"])
def test_a_moved_tree_turns_any_verdict_into_unknown(status: str) -> None:
    """The point of the fourth state: after the tree moves, neither ``ok`` nor
    ``failed`` is a statement anyone may act on."""
    assert (
        derive_part_eval_state(
            last_eval_status="ok" if status == "ok" else "failed",
            last_eval_tree_version=4,
            tree_version=5,
        )
        == "stale"
    )


# --- the second axis: what the verdict is a verdict OF (audit J3) ----------------


@pytest.mark.parametrize("state", ["ok", "failed"])
@pytest.mark.parametrize("scope", ["whole", "rolled_back"])
def test_a_live_verdict_carries_the_scope_it_was_recorded_with(
    state: str, scope: str
) -> None:
    """All four combinations are legal and none collapses into another: a
    rolled-back tree can fail, and a whole-tree evaluate can too."""
    assert (
        derive_part_eval_scope(
            eval_state="ok" if state == "ok" else "failed",
            last_eval_scope="whole" if scope == "whole" else "rolled_back",
        )
        == scope
    )


@pytest.mark.parametrize("state", ["never", "stale"])
def test_a_dead_verdict_is_not_qualified_at_all(state: str) -> None:
    """There is nothing to scope when the state is not a claim. Reporting
    ``rolled_back`` next to ``stale`` would invite reading the pair as "we know
    it built a prefix", which is exactly what ``stale`` denies."""
    assert (
        derive_part_eval_scope(
            eval_state="never" if state == "never" else "stale",
            last_eval_scope="rolled_back",
        )
        is None
    )


def test_an_unscoped_record_stays_unscoped_rather_than_defaulting_to_whole() -> None:
    """A row written before the column existed does not know its scope. Filling
    that in as ``whole`` would re-create the over-claim J3 filed."""
    assert derive_part_eval_scope(eval_state="ok", last_eval_scope=None) is None


def test_scope_is_optional_on_the_wire_so_it_broke_no_existing_caller() -> None:
    """Added as an OPTIONAL field on purpose (the ``ViewCreate.auto_place``
    lesson): a payload written before it existed still validates, and reads back
    as the honest "unqualified", never as ``whole``."""
    payload = _part(tree_version=2, eval_tree_version=2).model_dump(mode="json")
    del payload["eval_scope"]
    assert PartResponse.model_validate(payload).eval_scope is None


# --- the wire: provenance is comparable without re-deriving anything -------------


def test_the_body_a_client_holds_is_checkable_against_the_part_row() -> None:
    """The F2 capability, end to end on the DTOs: an evaluate result carries the
    version its body was built from, the part row carries the current version, and
    the shared rule answers "is what I am showing still the current tree?" — with
    no request state, no timestamps, and no second implementation."""
    part = _part(tree_version=5, eval_tree_version=5)
    displayed = _result(tree_version=5)
    assert not is_stale_for_tree(
        built_from_tree_version=displayed.tree_version,
        tree_version=part.tree_version,
    )

    # A concurrent edit lands: the part moves, the body in hand does not. Nothing
    # about the held result changed — and that is precisely why the comparison,
    # not the result alone, is what a readout must be built on.
    moved = _part(tree_version=6, eval_tree_version=5)
    assert is_stale_for_tree(
        built_from_tree_version=displayed.tree_version,
        tree_version=moved.tree_version,
    )
    assert moved.eval_state == "stale"


def test_the_current_version_is_required_and_never_negative() -> None:
    """``tree_version`` is a REQUIRED part-response field: a row that omitted it
    would leave a consumer with no denominator, i.e. back to guessing."""
    payload = _part(tree_version=2, eval_tree_version=None).model_dump(mode="json")
    del payload["tree_version"]
    with pytest.raises(ValidationError):
        PartResponse.model_validate(payload)

    with pytest.raises(ValidationError):
        PartResponse.model_validate({**payload, "tree_version": -1})
