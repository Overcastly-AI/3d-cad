"""BODY-NAMES wire: the member name rule, the per-solid list a STEP export
names its solids by, and the bounds a rename is held to."""

import uuid

import pytest
from loft_wire.body_names import (
    BODY_NAME_MAX_LENGTH,
    MAX_BODY_NAMES,
    BodyName,
    PartBodyNames,
    member_body_name,
    solid_names,
)
from loft_wire.features import MAX_TREE_FEATURES, ExportTreeRequest
from loft_wire.loft_file import LoftTree
from loft_wire.parts import PartUpdate
from pydantic import ValidationError

A = uuid.UUID(int=1)
B = uuid.UUID(int=2)
C = uuid.UUID(int=3)


def test_a_member_is_named_as_the_tree_labels_it() -> None:
    assert member_body_name("Front wall", "Stud", 2, 10) == "Front wall · Stud 3"
    assert member_body_name("Roof", "Ridge", 0, 1) == "Roof · Ridge"
    long = member_body_name("W" * 200, "T" * 200, 9, 12)
    assert len(long) == BODY_NAME_MAX_LENGTH


def test_each_lump_of_a_body_takes_its_name() -> None:
    names = [
        BodyName(base_feature_id=A, name="Stud 1"),
        BodyName(base_feature_id=C, name="Sill"),
    ]
    assert solid_names([(A, 1), (B, 2), (C, 1)], names) == [
        "Stud 1",
        None,
        None,
        "Sill",
    ]
    assert solid_names([(B, 1)], names) is None
    assert solid_names([], names) is None


def test_a_rename_list_is_bounded_and_one_per_body() -> None:
    assert MAX_BODY_NAMES == MAX_TREE_FEATURES
    entry = {"base_feature_id": str(A), "name": "x"}
    with pytest.raises(ValidationError, match="duplicate name"):
        PartUpdate.model_validate(
            {"expected_tree_version": 0, "body_names": [entry, entry]}
        )
    with pytest.raises(ValidationError):
        PartBodyNames.model_validate(
            {
                "bodies": [
                    {"base_feature_id": str(uuid.UUID(int=n)), "name": "x"}
                    for n in range(MAX_BODY_NAMES + 1)
                ]
            }
        )
    with pytest.raises(ValidationError):
        BodyName(base_feature_id=A, name="   ")
    assert BodyName(base_feature_id=A, name="  King stud ").name == "King stud"


def test_no_names_leaves_the_wire_and_the_file_as_they_were() -> None:
    export = ExportTreeRequest.model_validate(
        {"part_id": str(A), "tree_version": 1, "features": [], "format": "step"}
    )
    assert "body_names" not in export.model_dump(mode="json")
    tree = LoftTree.model_validate({"name": "Plate", "features": []})
    assert "body_names" not in tree.model_dump(mode="json")
