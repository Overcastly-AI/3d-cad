"""``with_member_materials``: a plugin member's own material (DECK).

The user's per-body override wins, then the member's material, then the part
default; the stored assignment is never changed.
"""

import uuid

from loft_wire.materials import (
    BodyMaterialAssignment,
    MaterialAssignment,
    resolve_body_material,
    with_member_materials,
)

JOIST, POST, PLAIN = (uuid.uuid4() for _ in range(3))


def test_members_take_their_own_material_over_the_default() -> None:
    stored = MaterialAssignment(default_material="spf_lumber")
    merged = with_member_materials(
        stored, {JOIST: "southern_pine_pt", POST: "concrete"}
    )
    assert merged is not None
    assert resolve_body_material(merged, JOIST) == "southern_pine_pt"
    assert resolve_body_material(merged, POST) == "concrete"
    assert resolve_body_material(merged, PLAIN) == "spf_lumber"
    assert stored.bodies == []  # the stored assignment is untouched


def test_the_users_override_wins() -> None:
    stored = MaterialAssignment(
        bodies=[BodyMaterialAssignment(base_feature_id=JOIST, material="lvl")]
    )
    merged = with_member_materials(stored, {JOIST: "southern_pine_pt"})
    assert resolve_body_material(merged, JOIST) == "lvl"


def test_no_material_and_no_members_change_nothing() -> None:
    assert with_member_materials(None, {}) is None
    assert with_member_materials(None, {JOIST: None}) is None
    merged = with_member_materials(None, {JOIST: "southern_pine_pt"})
    assert merged is not None and merged.default_material is None
    assert resolve_body_material(merged, PLAIN) is None
