"""Material vocabulary — the contract half of docs/design/materials.md.

The kernel suite proves mass comes out right; this proves the SHAPE of the
contract that makes a wrong answer unrepresentable: no material is ``None``
(never 0), a density lookup has one home, an override may not be duplicated,
and a part response never hands a consumer two spellings of "nothing".
"""

import uuid

import pytest
from py_kit.schemas.geometry import (
    BoundingBox,
    ShapeProperties,
    TopologyCounts,
    Vec3,
)
from py_kit.schemas.materials import (
    EMPTY_MATERIAL_ASSIGNMENT,
    MATERIALS,
    MATERIALS_BY_KEY,
    BodyMaterialAssignment,
    MaterialAssignment,
    density_kg_m3,
    mass_g,
    resolve_body_material,
)
from pydantic import ValidationError


def test_mass_of_no_density_is_absent_not_zero() -> None:
    """The one-line statement of the whole slice."""
    assert mass_g(1000.0, None) is None
    assert mass_g(1000.0, 7870.0) == pytest.approx(7.87, abs=1e-12)


def test_mass_is_volume_times_density_in_canonical_units() -> None:
    """mm^3 x kg/m^3 -> grams: 1 cm^3 (1000 mm^3) of water-density is 1 g."""
    assert mass_g(1000.0, 1000.0) == pytest.approx(1.0, abs=1e-12)


def test_the_library_is_closed_and_ordered() -> None:
    assert [m.key for m in MATERIALS] == [
        "steel_1018",
        "stainless_304",
        "aluminium_6061",
        "brass_c360",
        "abs",
        "pla",
        "nylon_6",
    ]
    assert set(MATERIALS_BY_KEY) == {m.key for m in MATERIALS}
    assert all(m.density_kg_m3 > 0 for m in MATERIALS)


def test_an_unknown_material_cannot_be_expressed() -> None:
    """A closed literal makes "no mass because we did not recognise it" impossible."""
    with pytest.raises(ValidationError):
        MaterialAssignment.model_validate({"default_material": "unobtainium"})


def test_duplicate_overrides_are_rejected_rather_than_last_wins() -> None:
    """Array order must not decide a body's material (RESEARCH §9 determinism)."""
    body = uuid.uuid4()

    with pytest.raises(ValidationError, match="duplicate material override"):
        MaterialAssignment(
            bodies=[
                BodyMaterialAssignment(base_feature_id=body, material="steel_1018"),
                BodyMaterialAssignment(base_feature_id=body, material="abs"),
            ]
        )


def test_resolution_is_override_then_default_then_nothing() -> None:
    overridden, plain = uuid.uuid4(), uuid.uuid4()
    assignment = MaterialAssignment(
        default_material="abs",
        bodies=[BodyMaterialAssignment(base_feature_id=overridden, material="nylon_6")],
    )

    assert resolve_body_material(assignment, overridden) == "nylon_6"
    assert resolve_body_material(assignment, plain) == "abs"
    assert resolve_body_material(EMPTY_MATERIAL_ASSIGNMENT, plain) is None
    assert resolve_body_material(None, plain) is None


def test_density_lookup_has_exactly_one_home() -> None:
    for material in MATERIALS:
        assert density_kg_m3(material.key) == material.density_kg_m3
    assert density_kg_m3(None) is None


def test_shape_properties_default_to_no_mass() -> None:
    """Every pre-materials construction site keeps meaning what it meant.

    A ``ShapeProperties`` built without mass fields describes a body nobody has
    said the material of — which is exactly what those call sites (STEP import,
    interference probes) know.
    """
    props = ShapeProperties(
        volume=1.0,
        surface_area=6.0,
        centroid=Vec3(x=0.0, y=0.0, z=0.0),
        bounding_box=BoundingBox(
            min=Vec3(x=0.0, y=0.0, z=0.0), max=Vec3(x=1.0, y=1.0, z=1.0)
        ),
        topology=TopologyCounts(faces=6, edges=12, shells=1),
    )

    assert props.mass_g is None
    assert props.center_of_mass is None


def test_the_empty_assignment_is_the_honest_nothing() -> None:
    assert EMPTY_MATERIAL_ASSIGNMENT.default_material is None
    assert EMPTY_MATERIAL_ASSIGNMENT.bodies == []
