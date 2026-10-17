"""Lumber profiles and building materials (LUMBER-MATERIALS).

Every number here is pinned by hand from its source, never read back from the
table under test: actual sizes from DOC PS 20-20, wood densities re-derived
from the AWC NDS specific gravity with the Wood Handbook ch. 4 relations, and
the rest from the published unit weight in lb/ft^3.
"""

from typing import get_args

import pytest
from loft_wire.lumber import (
    LUMBER_PROFILES,
    LUMBER_PROFILES_BY_KEY,
    MM_PER_INCH,
    LumberProfileKey,
    lumber_profile,
)
from loft_wire.materials import (
    MATERIALS,
    MATERIALS_BY_KEY,
    MaterialAssignment,
    density_kg_m3,
    mass_g,
)
from loft_wire.plugins import ChoiceOption

#: key -> (nominal name, actual thickness in, actual width in), PS 20-20:
#: boards 1 -> 3/4, decking 5/4 -> 1, dimension 2 -> 1-1/2, 3 -> 2-1/2,
#: 4 -> 3-1/2, 6 -> 5-1/2, 8 -> 7-1/4, 10 -> 9-1/4, 12 -> 11-1/4 (dry);
#: timbers 6 -> 5-1/2 (green).
EXPECTED_PROFILES: dict[str, tuple[str, float, float]] = {
    "us_1x4": ("1x4", 0.75, 3.5),
    "us_1x6": ("1x6", 0.75, 5.5),
    "us_5_4x6": ("5/4x6", 1.0, 5.5),
    "us_2x2": ("2x2", 1.5, 1.5),
    "us_2x3": ("2x3", 1.5, 2.5),
    "us_2x4": ("2x4", 1.5, 3.5),
    "us_2x6": ("2x6", 1.5, 5.5),
    "us_2x8": ("2x8", 1.5, 7.25),
    "us_2x10": ("2x10", 1.5, 9.25),
    "us_2x12": ("2x12", 1.5, 11.25),
    "us_4x4": ("4x4", 3.5, 3.5),
    "us_4x6": ("4x6", 3.5, 5.5),
    "us_6x6": ("6x6", 5.5, 5.5),
}

#: Every library density (kg/m^3), pinned. The first seven predate lumber and
#: must never move: a stored part's mass would change under it.
EXPECTED_DENSITIES: dict[str, float] = {
    "steel_1018": 7870.0,
    "stainless_304": 8000.0,
    "aluminium_6061": 2700.0,
    "brass_c360": 8500.0,
    "abs": 1040.0,
    "pla": 1240.0,
    "nylon_6": 1140.0,
    "spf_lumber": 450.0,
    "dfl_lumber": 532.0,
    "southern_pine_pt": 582.0,
    "lvl": 673.0,
    "glulam_dfl": 561.0,
    "steel_a992": 7850.0,
    "concrete": 2400.0,
}

KG_M3_PER_PCF = 16.018463373960138  # 0.45359237 kg / 0.3048^3 m^3


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b)


def test_every_profile_actual_size_is_pinned() -> None:
    assert [p.key for p in LUMBER_PROFILES] == list(EXPECTED_PROFILES)
    assert set(get_args(LumberProfileKey)) == set(EXPECTED_PROFILES)
    for key, (name, thickness_in, width_in) in EXPECTED_PROFILES.items():
        profile = LUMBER_PROFILES_BY_KEY[key]  # type: ignore[index]
        assert profile.name == name
        assert profile.thickness_in == thickness_in
        assert profile.width_in == width_in
        assert profile.thickness_mm == pytest.approx(thickness_in * 25.4, rel=1e-12)
        assert profile.width_mm == pytest.approx(width_in * 25.4, rel=1e-12)
        assert profile.source.startswith("DOC PS 20-20")


def test_buildings_md_sizes() -> None:
    """The sizes docs/reference-parts/buildings.md builds B1 and B2 from."""
    assert lumber_profile("us_2x10").thickness_mm == pytest.approx(38.1)
    assert lumber_profile("us_2x10").width_mm == pytest.approx(234.95)
    assert lumber_profile("us_6x6").width_in == 5.5
    assert lumber_profile("us_5_4x6").thickness_in == 1.0


def test_profile_keys_are_plugin_choice_values() -> None:
    """A plugin offers profiles as a choice input; the key must be a valid
    option value (``InputName``)."""
    for profile in LUMBER_PROFILES:
        ChoiceOption(value=profile.key, label=profile.name)


def test_every_density_is_pinned_and_sourced() -> None:
    assert {m.key: m.density_kg_m3 for m in MATERIALS} == EXPECTED_DENSITIES
    assert [m.key for m in MATERIALS] == list(EXPECTED_DENSITIES)
    assert all(m.source for m in MATERIALS)


@pytest.mark.parametrize(
    ("key", "g_oven_dry"),
    [("spf_lumber", 0.42), ("dfl_lumber", 0.50), ("southern_pine_pt", 0.55)],
)
def test_wood_density_follows_from_nds_specific_gravity(
    key: str, g_oven_dry: float
) -> None:
    """NDS 2018 Table 12.3.3A G (oven-dry) -> density at 12 % MC, Wood Handbook ch. 4:
    G_b = G_0/(1 + 0.265 G_0); G_12 = G_b/(1 - 0.265 a G_b), a = (30-12)/30;
    rho = 1000 G_12 (1.12). Rounded to 3 significant figures like the rest."""
    g_basic = g_oven_dry / (1 + 0.265 * g_oven_dry)
    a = (30 - 12) / 30
    g_12 = g_basic / (1 - 0.265 * a * g_basic)
    rho = 1000 * g_12 * 1.12
    assert MATERIALS_BY_KEY[key].density_kg_m3 == float(f"{rho:.3g}")  # type: ignore[index]


@pytest.mark.parametrize(
    ("key", "pcf"),
    [("lvl", 42), ("glulam_dfl", 35), ("steel_a992", 490), ("concrete", 150)],
)
def test_unit_weight_densities(key: str, pcf: float) -> None:
    rho = pcf * KG_M3_PER_PCF
    assert MATERIALS_BY_KEY[key].density_kg_m3 == float(f"{rho:.3g}")  # type: ignore[index]


def test_2x10_x_12ft_spf_mass_matches_the_hand_calculation() -> None:
    """Hand calculation, 2x10 x 12 ft SPF:

    section  1.5 in x 9.25 in = 13.875 in^2
    length   12 ft = 144 in
    volume   13.875 x 144 = 1998 in^3
             1998 x 25.4^3 (16 387.064 mm^3/in^3) = 32 741 353.872 mm^3
    density  SPF 450 kg/m^3 = 450e-9 kg/mm^3 = 450e-6 g/mm^3
    mass     32 741 353.872 x 450e-6 = 14 733.609 g  (14.73 kg, 32.48 lb)
    """
    hand_mass_g = 14_733.609
    profile = lumber_profile("us_2x10")
    length_mm = 144 * MM_PER_INCH
    volume_mm3 = profile.thickness_mm * profile.width_mm * length_mm
    assert volume_mm3 == pytest.approx(32_741_353.872, rel=1e-12)

    mass = mass_g(volume_mm3, density_kg_m3("spf_lumber"))

    assert mass is not None
    assert _rel(mass, hand_mass_g) < 1e-4


def test_lumber_materials_are_assignable() -> None:
    assignment = MaterialAssignment.model_validate(
        {"default_material": "southern_pine_pt"}
    )
    assert assignment.default_material == "southern_pine_pt"
