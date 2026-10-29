"""Tree-export endpoint sweeps (``POST /api/v1/export/tree``), half B of the
tree goldens.

Five cases per golden (headers and in-process determinism for STEP and STL,
plus the STEP round-trip) made test_export.py alone more than a pytest shard,
so the sweeps are halved across two modules (a shard packs whole files). The
checks and the halving live in conftest.py (``TreeExportSweep``);
test_export.py keeps the route-level tree checks that need only one model.

The sweeps stay on STEP/STL on purpose: each case re-evaluates the tree, and
3MF/GLB get whole-inventory coverage in test_export_mesh_formats.py, which
builds each golden once.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from geometry.schemas import ExportFormat

each_tree_format = pytest.mark.parametrize("fmt", ["step", "stl"])


@each_tree_format
def test_tree_export_response_headers(
    export_tree_model: Path,
    fmt: ExportFormat,
    assert_tree_export_headers: Callable[[Path, ExportFormat], None],
) -> None:
    """Correct media type + attachment filename for each format and tree."""
    assert_tree_export_headers(export_tree_model, fmt)


def test_tree_step_export_endpoint_roundtrip(
    export_tree_model: Path,
    tmp_path: Path,
    assert_tree_step_export_roundtrip: Callable[[Path, Path], None],
) -> None:
    """Gap #8: HTTP tree STEP export → re-import → geometry preserved.

    The evaluated body is exported over HTTP, re-imported, and re-measured
    against the SAME body rebuilt through the evaluate-tree path
    (``build_model_solid``): mass properties within ``ROUNDTRIP_TOL``,
    topology exact — the shape-golden round-trip gate, now over trees.
    """
    assert_tree_step_export_roundtrip(export_tree_model, tmp_path)


@each_tree_format
def test_tree_export_is_byte_deterministic_in_process(
    export_tree_model: Path,
    fmt: ExportFormat,
    assert_tree_export_deterministic_in_process: Callable[[Path, ExportFormat], None],
) -> None:
    """Same tree-export request twice → byte-identical file (RESEARCH §9).

    The STEP timestamp is pinned on the tree path exactly as on the shape path
    (both go through ``export_solid`` → ``export_step_bytes``); a flake is P0.
    """
    assert_tree_export_deterministic_in_process(export_tree_model, fmt)
