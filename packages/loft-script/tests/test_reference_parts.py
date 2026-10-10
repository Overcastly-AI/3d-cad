"""The parametric reference parts, end to end (PART-PARAMETERS step 9).

``docs/reference-parts`` builds three parts through loft-script with a
parameter table: the helical gear, ladder 2c (the hydraulic manifold) and
ladder 3d (the two-body knob). Each is re-driven by ONE ``set_parameter``
call, the ladder's named edit, and its volume must match the script's own
hand-derived value (pure Python, no kernel) to 1e-4 relative, the ladder's
bound. Running them here keeps the scripts building against the API as it
moves; their STEP re-reads are QA-only and not run.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import loft
import pytest

from .conftest import Stack

PARTS = Path(__file__).resolve().parents[3] / "docs" / "reference-parts"
PASSWORD = "reference-parts-passphrase"
_emails = (f"reference-{n}@example.com" for n in itertools.count())

#: The ladder's independent-check bound (docs/reference-parts/ladder.md).
REL = 1e-4


@pytest.fixture(scope="module")
def scripts() -> Iterator[dict[str, ModuleType]]:
    """The three scripts, imported as modules (they share ``formula_sketch``)."""
    sys.path.insert(0, str(PARTS))
    loaded: dict[str, ModuleType] = {}
    try:
        for stem in ("helical-gear", "manifold", "knob"):
            name = f"reference_{stem.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(name, PARTS / f"{stem}.py")
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            # Registered first: dataclasses resolve the module by name.
            sys.modules[name] = module
            spec.loader.exec_module(module)
            loaded[stem] = module
        yield loaded
    finally:
        sys.path.remove(str(PARTS))
        for stem in loaded:
            sys.modules.pop(f"reference_{stem.replace('-', '_')}", None)


def test_the_helical_gear_follows_one_helix_edit(
    stack: Stack, scripts: dict[str, ModuleType]
) -> None:
    gear = scripts["helical-gear"]
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Helical gear (parametric)")
        g = gear.Gear()
        gear.build_parametric(part, g, 12, gear.Timer())
        exact, _ = gear.expected_volume(g, 2)
        assert part.mass_properties().volume == pytest.approx(exact, rel=REL)

        part.set_parameter("beta", "20 deg")
        exact20, _ = gear.expected_volume(gear.Gear(beta_deg=20.0), 2)
        assert abs(exact20 - exact) > 10 * REL * exact  # the edit is visible
        assert part.mass_properties().volume == pytest.approx(exact20, rel=REL)


def test_the_manifold_follows_one_height_edit(
    stack: Stack, scripts: dict[str, ModuleType]
) -> None:
    manifold = scripts["manifold"]
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Hydraulic manifold (ladder 2c)")
        m = manifold.Manifold()
        manifold.build(part, m, manifold.Timer())
        want = manifold.expected(m)["part"]
        assert part.mass_properties().volume == pytest.approx(want, rel=REL)

        part.set_parameter("H", "60")
        want60 = manifold.expected(replace(m, H=60.0))["part"]
        assert part.mass_properties().volume == pytest.approx(want60, rel=REL)


def test_the_knob_follows_one_flute_count_edit(
    stack: Stack, scripts: dict[str, ModuleType]
) -> None:
    knob = scripts["knob"]
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        part = session.new_part("Two-body knob (ladder 3d)")
        k = knob.Knob()
        knob.build(part, k, knob.Timer())
        want = knob.expected(k)["part"]
        assert part.mass_properties().volume == pytest.approx(want, rel=REL)

        part.set_parameter("flutes", "24")
        want24 = knob.expected(replace(k, flutes=24))["part"]
        assert abs(want24 - want) > 10 * REL * want  # the edit is visible
        assert part.mass_properties().volume == pytest.approx(want24, rel=REL)
