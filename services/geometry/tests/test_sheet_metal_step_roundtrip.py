"""STEP round-trip fidelity for AUTHORED sheet-metal bodies — geometry-QA gate 2
(docs/RESEARCH.md §9) applied to the sheet-metal pillar.

The kernel-level round-trip gate (``tests/test_step_roundtrip.py``) parametrizes
over the shared ``goldens/`` inventory only — none of which is a sheet-metal part
(the sheet-metal goldens live under ``goldens-sheet-metal/`` and drive the unfold /
flat-pattern gates, not the STEP path). So a folded sheet body — base flange + a
cylindrical bend + edge flange(s) — had **no** export→import→re-measure coverage.
This module closes that gap: it rebuilds each authored sheet-metal body from its
feature tree, exports it to STEP (build123d ``export_step``, OCCT STEPControl),
re-imports, and re-measures through the SAME GProp pipeline, asserting mass
properties within ``ROUNDTRIP_TOL`` and topology counts EXACTLY (the shared
``assert_roundtrip_preserved`` conftest fixture) — plus the lump/solid count, so a
bend that survives export as a disconnected shell would be caught.

Measured 2026-07-19 (build123d 0.11.1 / OCCT 7.9): the L-bracket (base + 1 edge
flange) and U-channel (base + 2 edge flanges) each round-trip with a volume
deviation ~8e-12, area ~3e-11, centroid ~1e-13, and IDENTICAL 10/24/1 and 14/36/1
topology — the analytic cylindrical bend geometry survives STEP without
degradation (evidence in docs/GEOMETRY-QA.md). A deviation here is a DEFECT to
root-cause to export / import / kernel, never tolerance noise (geometry-qa rules).
"""

from collections.abc import Callable
from pathlib import Path

import pytest

# Upstream export/import signatures carry Shape[Unknown]/PathLike[Unknown] type
# params (the same gap test_step_roundtrip.py documents) — scoped ignores only.
from build123d import (
    Compound,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features.evaluate import evaluate_tree
from geometry.kernel import measure_shape
from geometry.schemas import ShapeProperties
from py_kit.schemas.features import EvaluateTreeRequest

_GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-sheet-metal"

# Reuse the authored feature trees the flat-pattern-view goldens already ship — a
# base flange + N edge flanges (the depth-1 star), i.e. real folded sheet bodies.
_MODEL_FILES = sorted(_GOLDENS_DIR.glob("*-flat-pattern-view/model.json"))

each_model = pytest.mark.parametrize(
    "model_path", _MODEL_FILES, ids=[p.parent.name for p in _MODEL_FILES]
)


def test_sheet_metal_roundtrip_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert _MODEL_FILES, f"no authored sheet-metal trees under {_GOLDENS_DIR}"


@each_model
def test_sheet_metal_step_roundtrip_preserves_geometry(
    model_path: Path,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[
        [str, ShapeProperties, ShapeProperties], None
    ],
) -> None:
    """An authored folded sheet body survives STEP export→import with its mass
    properties (tol) and topology (exact) intact, as a single connected solid."""
    name = model_path.parent.name
    request = EvaluateTreeRequest.model_validate_json(
        model_path.read_text(encoding="utf-8")
    )
    evaluation = evaluate_tree(request)
    assert all(
        f.status == "ok" for f in evaluation.result.features
    ), [f.status for f in evaluation.result.features]
    assert evaluation.body is not None, f"{name}: no body evaluated"
    original_shape = evaluation.body
    original = measure_shape(original_shape)

    step_path = tmp_path / f"{name}.step"
    assert export_step(original_shape, step_path), f"{name}: STEP export failed"
    assert step_path.read_text(encoding="utf-8", errors="replace").startswith(
        "ISO-10303-21"
    ), f"{name}: not a STEP part 21 file"

    imported = import_step(step_path)
    solids = imported.solids()
    # A v1 sheet-metal part is ONE connected body (the flange fuses across the
    # bend); a bend that exported as a disconnected shell would split this.
    assert len(solids) == 1, f"{name}: expected 1 solid after import, got {len(solids)}"
    reimported_shape = solids[0] if len(solids) == 1 else Compound(list(solids))
    reimported = measure_shape(reimported_shape)

    assert_roundtrip_preserved(name, reimported, original)
