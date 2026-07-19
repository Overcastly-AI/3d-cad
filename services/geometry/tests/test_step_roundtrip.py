"""STEP round-trip fidelity gate — gate 2 of the geometry QA strategy
(docs/RESEARCH.md §9), kernel-level.

Every golden's solid is rebuilt (:func:`geometry.harness.build_model_solid`
— shape goldens via the parametric builders, feature-tree goldens via the
full evaluate-tree path), exported to STEP via build123d (``export_step``,
OCCT STEPControl underneath), re-imported (``import_step``), re-measured
through the same GProp pipeline, and compared against the in-memory
original: mass properties within ``ROUNDTRIP_TOL``, topology counts exactly.

Measured 2026-07-10 (build123d 0.11.1): the 10x20x30 box round-trips with a
deviation of exactly 0.0 on every mass property, bbox extent, and centroid
component, and identical 6/12/1 topology — planar B-rep geometry survives
STEP without degradation (evidence in docs/GEOMETRY-QA.md). A deviation
here is a DEFECT to root-cause to export, import, or kernel — never
tolerance noise to absorb (geometry-qa agent rules).

Scope: this exercises the kernel + build123d I/O layer directly (build123d's
default wall-clock STEP timestamp is irrelevant here — geometry, not bytes,
is compared). The endpoint-level round-trip gate — HTTP export → re-import —
plus export byte-determinism live in ``test_export.py``.

Parametrized over the golden inventory, so every future golden gets
round-trip coverage with zero changes here. The comparison itself (mass
properties within the shared ``ROUNDTRIP_TOL``, topology exact) is the
``assert_roundtrip_preserved`` conftest fixture, shared with the
endpoint-level gate.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

# Upstream signatures carry Shape[Unknown]/PathLike[Unknown] type params
# (same gap tessellate.py documents for export_gltf) — scoped ignores only.
from build123d import (
    Compound,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.harness import build_model_solid, load_model_request
from geometry.kernel import measure_shape
from geometry.schemas import ShapeProperties

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"
MODEL_FILES = sorted(GOLDENS_DIR.glob("*/model.json"))

each_model = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)


def test_roundtrip_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert MODEL_FILES, f"no golden models discovered under {GOLDENS_DIR}"


@each_model
def test_step_roundtrip_preserves_geometry(
    model_path: Path,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    name = model_path.parent.name
    request = load_model_request(model_path.read_text(encoding="utf-8"))
    original_shape = build_model_solid(request)
    original = measure_shape(original_shape)

    # Export: build123d/OCCT writes a STEP AP214 part 21 file.
    step_path = tmp_path / f"{name}.step"
    assert export_step(original_shape, step_path), f"{name}: STEP export failed"
    assert step_path.read_text(encoding="utf-8", errors="replace").startswith(
        "ISO-10303-21"
    ), f"{name}: not a STEP part 21 file"

    # Re-import and re-measure with the identical GProp pipeline. A multi-body
    # golden (§MB-0) exports as a multi-solid STEP, so the re-imported body set
    # is a single Solid OR a Compound of the imported solids — measure the whole
    # set (measure_shape rolls up either), covering multi-body round-trips too.
    imported = import_step(step_path)
    solids = imported.solids()
    assert solids, f"{name}: expected at least 1 solid after import, got 0"
    reimported_shape = solids[0] if len(solids) == 1 else Compound(list(solids))
    reimported = measure_shape(reimported_shape)

    assert_roundtrip_preserved(name, reimported, original)
