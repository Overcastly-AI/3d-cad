"""Workspace DTOs — the copy-naming rule and the typed dependency payload."""

import uuid

import pytest
from py_kit.schemas.workspace import (
    DependencyConflictEnvelope,
    DocumentDependent,
    DocumentDependents,
    copy_name,
)

MAX = 200


def test_first_copy_takes_the_plain_suffix() -> None:
    assert copy_name("Bracket", set(), max_length=MAX) == "Bracket copy"


def test_subsequent_copies_count_up_from_two() -> None:
    taken = {"Bracket", "Bracket copy"}
    second = copy_name("Bracket", taken, max_length=MAX)
    assert second == "Bracket copy 2"
    assert copy_name("Bracket", taken | {second}, max_length=MAX) == "Bracket copy 3"


def test_a_gap_in_the_sequence_is_filled_not_skipped() -> None:
    """The rule is 'first free', so deleting "copy 2" reuses that name."""
    assert (
        copy_name("Bracket", {"Bracket copy", "Bracket copy 3"}, max_length=MAX)
        == "Bracket copy 2"
    )


def test_duplicating_a_copy_is_ugly_and_honest() -> None:
    assert copy_name("Bracket copy", set(), max_length=MAX) == "Bracket copy copy"


def test_a_name_at_the_limit_still_produces_a_legal_name() -> None:
    """Truncation lands on the BASE — never on the suffix, which would make the
    copy indistinguishable from the original name."""
    long_name = "B" * MAX
    first = copy_name(long_name, set(), max_length=MAX)
    assert len(first) == MAX
    assert first.endswith(" copy")

    second = copy_name(long_name, {first}, max_length=MAX)
    assert len(second) <= MAX
    assert second.endswith(" copy 2")
    assert second != first


def test_truncation_does_not_leave_a_trailing_space_before_the_suffix() -> None:
    name = "A" * (MAX - 6) + " tail"
    assert "  copy" not in copy_name(name, set(), max_length=MAX)


def test_dependents_round_trip_through_the_documented_409_envelope() -> None:
    """The 409 the delete routes document is the payload documents actually
    builds — one model, so the browser's typed read cannot drift from it."""
    payload = DocumentDependents(
        dependents=[
            DocumentDependent(id=uuid.uuid4(), name="gearbox", kind="assembly"),
            DocumentDependent(id=uuid.uuid4(), name="bracket-detail", kind="drawing"),
        ]
    )
    envelope = DependencyConflictEnvelope.model_validate(
        {
            "error": {
                "code": "part_has_dependents",
                "message": "Document is referenced by 2 document(s).",
                "details": payload.model_dump(mode="json"),
                "request_id": "abc",
            }
        }
    )
    assert [d.kind for d in envelope.error.details.dependents] == [
        "assembly",
        "drawing",
    ]
    assert envelope.error.details.dependents[0].name == "gearbox"


def test_a_part_can_never_be_named_as_a_dependent() -> None:
    """`DependentKind` has no "part" member: a part references nothing outside
    itself, so offering the option would name a class the server cannot report."""
    with pytest.raises(ValueError):
        DocumentDependent(id=uuid.uuid4(), name="plate", kind="part")  # type: ignore[arg-type]
