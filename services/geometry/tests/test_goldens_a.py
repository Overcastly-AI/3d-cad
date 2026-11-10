"""Golden-model gates 1 and 3 (docs/RESEARCH.md §9), half A of the goldens.

Mass properties within the documented tolerance, exact topology and mesh
counts, and the in-process determinism gate, per golden. Over every golden in
one module (test_goldens.py) they had outgrown a pytest shard, which packs
whole files, so they are halved by golden as the restart gates are. The checks
live in _golden_cases.py, the halving in conftest.py; test_goldens.py keeps the
inventory checks.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _golden_cases import (
    check_mass_properties_within_documented_tolerance,
    check_rebuild_is_deterministic_in_process,
    check_topology_and_mesh_counts_exact,
    load_golden_case,
)


def test_mass_properties_within_documented_tolerance(golden_case_model: Path) -> None:
    check_mass_properties_within_documented_tolerance(
        load_golden_case(golden_case_model)
    )


def test_topology_and_mesh_counts_exact(golden_case_model: Path) -> None:
    check_topology_and_mesh_counts_exact(load_golden_case(golden_case_model))


def test_rebuild_is_deterministic_in_process(golden_case_model: Path) -> None:
    check_rebuild_is_deterministic_in_process(load_golden_case(golden_case_model))
