"""Mass from material — the kernel half of docs/design/materials.md.

What is asserted here, in one sentence each:

* **Absence is the default.** No material in → ``mass_g is None`` out, never
  ``0.0`` and never a defaulted density. This is the whole point of the slice:
  a panel titled MASS PROPERTIES that reports no mass was an overstated
  surface, and "0 g" would have been a worse one.
* **Mass is derived, in one place.** ``mass = volume x density`` computed from
  the very volume ``measure_shape`` just measured, so the two cannot disagree.
* **The roll-ups are honest.** A part or assembly whose bodies mix materials
  reports a genuinely MASS-weighted centre of mass (which differs from the
  volume centroid), and reports NO mass at all if even one body lacks a
  material — a partial sum would understate while looking complete.

Analytic expectations only (geometry-gates skill): every number below is a
hand-derived density x an exactly-known volume, never a recorded output.
"""

import uuid

import pytest
from build123d import Box, Location, Pos
from geometry.assembly.evaluate import evaluate_assembly
from geometry.features import evaluate_tree
from geometry.kernel import combine_properties, measure_shape
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    Placement,
)
from py_kit.schemas.features import EvaluatedFeatureInput, EvaluateTreeRequest
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.materials import (
    MATERIALS,
    MATERIALS_BY_KEY,
    BodyMaterialAssignment,
    MaterialAssignment,
    density_kg_m3,
    mass_g,
    resolve_body_material,
)

#: 20 mm cube = 8000 mm^3. Aluminium 6061 (2700 kg/m^3) -> 21.6 g; steel 1018
#: (7870 kg/m^3) -> 62.96 g. Both exact products of the analytic volume.
CUBE_MM = 20.0
CUBE_VOLUME_MM3 = 8000.0
ALU_MASS_G = 21.6
STEEL_MASS_G = 62.96

#: Kernel-scale bound for these assertions. Mass = volume x density and every
#: library density is < 1 in g/mm^3, so the mass error is strictly smaller than
#: the volume error; 1e-9 is the same documented ceiling the goldens carry
#: (services/geometry/goldens/*/expected.json), never an ad-hoc epsilon.
TOL = 1e-9


def _cube(x: float = 0.0) -> Box:
    """A 20 mm cube centred at (x, 0, 0) — volume 8000 mm^3 exactly."""
    return Pos(x, 0.0, 0.0) * Box(CUBE_MM, CUBE_MM, CUBE_MM)


class TestNoMaterialMeansNoMass:
    """Absent, not zero — the honesty contract (design §1)."""

    def test_measure_without_density_reports_no_mass(self) -> None:
        props = measure_shape(_cube())

        assert props.mass_g is None, "no material must report absent mass, not 0 g"
        assert props.center_of_mass is None
        assert props.volume == pytest.approx(CUBE_VOLUME_MM3, abs=TOL)

    def test_zero_is_not_the_same_answer_as_unknown(self) -> None:
        """A reader must be able to tell "unknown" from a real zero.

        ``None`` is falsy in Python and 0.0 is falsy too, which is exactly why
        the distinction has to be asserted rather than assumed: this test fails
        the moment someone "helpfully" defaults the field.
        """
        unknown = measure_shape(_cube()).mass_g

        assert unknown is not None or unknown != 0.0
        assert unknown is None

    def test_a_body_with_material_reports_mass(self) -> None:
        props = measure_shape(_cube(), density_kg_m3=2700.0)

        assert props.mass_g == pytest.approx(ALU_MASS_G, abs=TOL)
        assert props.center_of_mass is not None


class TestMassIsDerivedFromTheMeasuredVolume:
    """One computation, beside the volume it uses (design §1 rule 1)."""

    @pytest.mark.parametrize(
        ("density", "expected_g"),
        [(2700.0, ALU_MASS_G), (7870.0, STEEL_MASS_G), (1240.0, 9.92)],
    )
    def test_mass_equals_volume_times_density(
        self, density: float, expected_g: float
    ) -> None:
        props = measure_shape(_cube(), density_kg_m3=density)

        assert props.mass_g is not None
        # Hand-derived: 8000 mm^3 x density x 1e-6 g/(mm^3 kg/m^3).
        assert props.mass_g == pytest.approx(expected_g, abs=TOL)
        # And it agrees with the volume in the SAME result, by construction.
        assert props.mass_g == pytest.approx(props.volume * density * 1e-6, abs=TOL)

    def test_single_material_body_balances_at_its_volume_centroid(self) -> None:
        """Homogeneous body: density factors out, so the two coincide exactly."""
        props = measure_shape(Pos(5.0, 0.0, 0.0) * _cube(), density_kg_m3=7870.0)

        assert props.center_of_mass is not None
        assert props.center_of_mass.x == props.centroid.x
        assert props.center_of_mass.y == props.centroid.y
        assert props.center_of_mass.z == props.centroid.z


class TestCombineIsMassWeighted:
    """The multi-body roll-up (design §3) — where volume and mass diverge."""

    def test_mixed_densities_move_the_centre_of_mass(self) -> None:
        """Equal volumes, unequal densities: the balance point is NOT the middle.

        Aluminium cube at x=0 (21.6 g), steel cube at x=40 (62.96 g). Volume
        centroid = (0 + 40)/2 = 20 mm. Centre of mass = (21.6*0 + 62.96*40) /
        84.56 = 2518.4/84.56 = 787*40/1057 = 31480/1057 = 29.7823... mm.
        """
        alu = measure_shape(_cube(0.0), density_kg_m3=2700.0)
        steel = measure_shape(_cube(40.0), density_kg_m3=7870.0)

        combined = combine_properties([alu, steel])

        assert combined.mass_g == pytest.approx(ALU_MASS_G + STEEL_MASS_G, abs=TOL)
        assert combined.centroid.x == pytest.approx(20.0, abs=TOL)
        assert combined.center_of_mass is not None
        assert combined.center_of_mass.x == pytest.approx(31480 / 1057, abs=TOL)
        assert combined.center_of_mass.x != pytest.approx(
            combined.centroid.x, abs=1e-3
        ), "a mass-weighted centre must not silently equal the volume centroid"

    def test_one_missing_material_makes_the_whole_mass_unknown(self) -> None:
        """A partial sum would understate the part while looking complete."""
        known = measure_shape(_cube(0.0), density_kg_m3=2700.0)
        unknown = measure_shape(_cube(40.0))

        combined = combine_properties([known, unknown])

        assert combined.mass_g is None
        assert combined.center_of_mass is None
        # Volume is still fully known — geometry does not depend on material.
        assert combined.volume == pytest.approx(2 * CUBE_VOLUME_MM3, abs=TOL)

    def test_missing_material_first_also_wins(self) -> None:
        """Order must not decide the answer (a later known body cannot revive it)."""
        unknown = measure_shape(_cube(0.0))
        known = measure_shape(_cube(40.0), density_kg_m3=2700.0)

        assert combine_properties([unknown, known]).mass_g is None


class TestResolution:
    """Override beats default beats nothing (design §2)."""

    def test_override_wins_over_the_document_default(self) -> None:
        body_a, body_b = uuid.uuid4(), uuid.uuid4()
        assignment = MaterialAssignment(
            default_material="aluminium_6061",
            bodies=[
                BodyMaterialAssignment(base_feature_id=body_b, material="steel_1018")
            ],
        )

        assert resolve_body_material(assignment, body_a) == "aluminium_6061"
        assert resolve_body_material(assignment, body_b) == "steel_1018"

    def test_no_assignment_and_no_default_resolve_to_nothing(self) -> None:
        assert resolve_body_material(None, uuid.uuid4()) is None
        assert resolve_body_material(MaterialAssignment(), uuid.uuid4()) is None

    def test_density_of_nothing_is_nothing(self) -> None:
        assert density_kg_m3(None) is None
        assert mass_g(1000.0, None) is None

    def test_library_densities_are_the_documented_handbook_values(self) -> None:
        """The table is load-bearing: a wrong density is a wrong mass forever."""
        assert MATERIALS_BY_KEY["steel_1018"].density_kg_m3 == 7870.0
        assert MATERIALS_BY_KEY["stainless_304"].density_kg_m3 == 8000.0
        assert MATERIALS_BY_KEY["aluminium_6061"].density_kg_m3 == 2700.0
        assert MATERIALS_BY_KEY["brass_c360"].density_kg_m3 == 8500.0
        assert MATERIALS_BY_KEY["abs"].density_kg_m3 == 1040.0
        assert MATERIALS_BY_KEY["pla"].density_kg_m3 == 1240.0
        assert MATERIALS_BY_KEY["nylon_6"].density_kg_m3 == 1140.0
        assert len(MATERIALS) == len(MATERIALS_BY_KEY) == 7

    def test_every_library_density_is_under_one_gram_per_cubic_mm(self) -> None:
        """The premise of the goldens' shared tolerance argument (§6).

        Mass rides the model's length/volume tolerance because density < 1 in
        g/mm^3 makes the propagated mass error smaller than the volume error.
        If a denser material is ever added, that argument needs re-deriving —
        this test is where it fails loudly instead of silently.
        """
        for material in MATERIALS:
            assert material.density_kg_m3 * 1e-6 < 1.0


#: Fixed body identities so a per-body override can name one (MB-0 identity =
#: the id of the feature that created the body — here the two extrudes).
SKETCH_A = uuid.UUID("00000000-0000-0000-0000-0000000a0001")
EXTRUDE_A = uuid.UUID("00000000-0000-0000-0000-0000000a0002")
SKETCH_B = uuid.UUID("00000000-0000-0000-0000-0000000a0003")
EXTRUDE_B = uuid.UUID("00000000-0000-0000-0000-0000000a0004")


def _square(y: float) -> dict[str, object]:
    """A closed 20 x 20 square starting at ``y``, as sketch params."""
    corners = [(0.0, y), (20.0, y), (20.0, y + 20.0), (0.0, y + 20.0)]
    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": f"l{i + 1}",
                "kind": "line",
                "start": {"x": corners[i][0], "y": corners[i][1]},
                "end": {"x": corners[(i + 1) % 4][0], "y": corners[(i + 1) % 4][1]},
            }
            for i in range(4)
        ],
        "constraints": [],
    }


def _extrude_params(sketch_id: uuid.UUID, *, merge: bool) -> dict[str, object]:
    return {
        "profile": {"kind": "feature", "feature_id": str(sketch_id)},
        "distance_mm": 20.0,
        "operation": "add",
        "direction": "normal",
        "merge": merge,
    }


def _two_body_features() -> list[EvaluatedFeatureInput]:
    """Two disjoint 20 mm cubes: bodies keyed by EXTRUDE_A / EXTRUDE_B."""
    return [
        EvaluatedFeatureInput.model_validate(
            {
                "id": SKETCH_A,
                "feature": {"type": "sketch", "version": 1, "params": _square(0.0)},
            }
        ),
        EvaluatedFeatureInput.model_validate(
            {
                "id": EXTRUDE_A,
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": _extrude_params(SKETCH_A, merge=True),
                },
            }
        ),
        EvaluatedFeatureInput.model_validate(
            {
                "id": SKETCH_B,
                "feature": {"type": "sketch", "version": 1, "params": _square(40.0)},
            }
        ),
        EvaluatedFeatureInput.model_validate(
            {
                "id": EXTRUDE_B,
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": _extrude_params(SKETCH_B, merge=False),
                },
            }
        ),
    ]


def _tree(materials: MaterialAssignment | None) -> EvaluateTreeRequest:
    """The two-body tree above, evaluated with *materials*."""
    return EvaluateTreeRequest(
        part_id=uuid.uuid4(),
        tree_version=1,
        features=_two_body_features(),
        materials=materials,
    )


class TestEvaluateTreeThreadsMaterials:
    """End-to-end through the feature-tree evaluator (design §2/§4)."""

    def test_no_materials_yields_no_mass_anywhere(self) -> None:
        result = evaluate_tree(_tree(None)).result

        assert result.properties is not None
        assert result.properties.mass_g is None
        assert [body.mass_g for body in result.bodies] == [None, None]
        assert [body.material for body in result.bodies] == [None, None]

    def test_document_default_applies_to_every_body(self) -> None:
        result = evaluate_tree(
            _tree(MaterialAssignment(default_material="aluminium_6061"))
        ).result

        assert result.properties is not None
        assert result.properties.mass_g == pytest.approx(2 * ALU_MASS_G, abs=TOL)
        for body in result.bodies:
            assert body.material == "aluminium_6061"
            assert body.mass_g == pytest.approx(ALU_MASS_G, abs=TOL)

    def test_per_body_override_mixes_materials_in_one_part(self) -> None:
        """The multi-body case the design exists for (a steel insert in alu)."""
        request = _tree(
            MaterialAssignment(
                default_material="aluminium_6061",
                bodies=[
                    BodyMaterialAssignment(
                        base_feature_id=EXTRUDE_B, material="steel_1018"
                    )
                ],
            )
        )
        result = evaluate_tree(request).result

        assert result.properties is not None
        assert result.properties.mass_g == pytest.approx(
            ALU_MASS_G + STEEL_MASS_G, abs=TOL
        )
        assert [body.material for body in result.bodies] == [
            "aluminium_6061",
            "steel_1018",
        ]
        # y is where the two bodies differ (0..20 and 40..60): volume centroid
        # is 30, the mass-weighted centre is pulled toward the steel body at 50.
        assert result.properties.centroid.y == pytest.approx(30.0, abs=TOL)
        assert result.properties.center_of_mass is not None
        assert result.properties.center_of_mass.y == pytest.approx(
            (ALU_MASS_G * 10.0 + STEEL_MASS_G * 50.0) / (ALU_MASS_G + STEEL_MASS_G),
            abs=TOL,
        )

    def test_an_unassigned_body_makes_the_part_mass_unknown(self) -> None:
        """Per-body masses still report; the WHOLE-part claim goes silent."""
        # Only body A (created by EXTRUDE_A) is assigned; body B has nothing.
        result = evaluate_tree(
            _tree(
                MaterialAssignment(
                    bodies=[
                        BodyMaterialAssignment(
                            base_feature_id=EXTRUDE_A, material="steel_1018"
                        )
                    ]
                )
            )
        ).result

        assert result.properties is not None
        assert result.properties.mass_g is None
        assert result.bodies[0].mass_g == pytest.approx(STEEL_MASS_G, abs=TOL)
        assert result.bodies[1].mass_g is None


class TestAssemblyRollUp:
    """The assembly composes mass the same analytic way (design §3)."""

    @staticmethod
    def _instance(
        name: str, x_mm: float, materials: MaterialAssignment | None
    ) -> EvaluatedInstance:
        return EvaluatedInstance(
            instance_id=uuid.uuid4(),
            part_key=f"{name}@tip",
            # One 20 mm cube per instance (the first sketch + extrude only).
            features=_two_body_features()[:2],
            materials=materials,
            # Identity orientation (Placement's default) — only the
            # translation matters for a mass-weighted centre.
            placement=Placement(position=Vec3(x=x_mm, y=0.0, z=0.0)),
            grounded=True,
        )

    def test_mixed_material_assembly_is_mass_weighted(self) -> None:
        """Two identical cubes, different materials, 40 mm apart in x.

        Volume centroid x = (10 + 50)/2 = 30 mm (each cube spans 0..20 locally,
        so its own centroid sits at +10). Centre of mass = (21.6*10 +
        62.96*50)/84.56 mm, pulled toward the steel instance.
        """
        result = evaluate_assembly(
            EvaluateAssemblyRequest(
                assembly_id=uuid.uuid4(),
                version=1,
                instances=[
                    self._instance(
                        "alu",
                        0.0,
                        MaterialAssignment(default_material="aluminium_6061"),
                    ),
                    self._instance(
                        "steel", 40.0, MaterialAssignment(default_material="steel_1018")
                    ),
                ],
            )
        )

        assert result.properties is not None
        assert result.properties.mass_g == pytest.approx(
            ALU_MASS_G + STEEL_MASS_G, abs=TOL
        )
        assert result.properties.centroid.x == pytest.approx(30.0, abs=TOL)
        assert result.properties.center_of_mass is not None
        assert result.properties.center_of_mass.x == pytest.approx(
            (ALU_MASS_G * 10.0 + STEEL_MASS_G * 50.0) / (ALU_MASS_G + STEEL_MASS_G),
            abs=TOL,
        )

    def test_one_material_free_instance_makes_the_assembly_mass_unknown(self) -> None:
        result = evaluate_assembly(
            EvaluateAssemblyRequest(
                assembly_id=uuid.uuid4(),
                version=1,
                instances=[
                    self._instance(
                        "alu",
                        0.0,
                        MaterialAssignment(default_material="aluminium_6061"),
                    ),
                    self._instance("bare", 40.0, None),
                ],
            )
        )

        assert result.properties is not None
        assert result.properties.mass_g is None
        assert result.properties.center_of_mass is None
        assert result.properties.volume == pytest.approx(2 * CUBE_VOLUME_MM3, abs=TOL)


def test_placement_moves_mass_with_the_body() -> None:
    """A translated body's centre of mass translates with it (assembly §4)."""
    moved = measure_shape(Location((7.0, 0.0, 0.0)) * _cube(), density_kg_m3=2700.0)

    assert moved.center_of_mass is not None
    assert moved.center_of_mass.x == pytest.approx(7.0, abs=TOL)
    assert moved.mass_g == pytest.approx(ALU_MASS_G, abs=TOL)
