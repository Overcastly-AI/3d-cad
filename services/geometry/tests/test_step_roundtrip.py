"""STEP round-trip fidelity gate — gate 2 of the geometry QA strategy
(docs/RESEARCH.md §9), kernel-level.

Every golden's shape is rebuilt, exported to STEP via build123d
(``export_step``, OCCT STEPControl underneath), re-imported
(``import_step``), re-measured through the same GProp pipeline, and compared
against the in-memory original: mass properties within ``ROUNDTRIP_TOL``,
topology counts exactly.

Measured 2026-07-10 (build123d 0.11.1): the 10x20x30 box round-trips with a
deviation of exactly 0.0 on every mass property, bbox extent, and centroid
component, and identical 6/12/1 topology — planar B-rep geometry survives
STEP without degradation (evidence in docs/GEOMETRY-QA.md). A deviation
here is a DEFECT to root-cause to export, import, or kernel — never
tolerance noise to absorb (geometry-qa agent rules).

Scope: this exercises the kernel + build123d I/O layer directly. There is no
STEP export *endpoint* yet (Phase 1 roadmap); endpoint-level round-trip
coverage lands with it — tracked as a gap in docs/GEOMETRY-QA.md.

Parametrized over the golden inventory, so every future golden gets
round-trip coverage with zero changes here.
"""

from pathlib import Path

import pytest

# Upstream signatures carry Shape[Unknown]/PathLike[Unknown] type params
# (same gap tessellate.py documents for export_gltf) — scoped ignores only.
from build123d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.kernel import build_shape, measure_shape
from geometry.schemas import TessellateRequest

#: Round-trip tolerance for mass properties: the CLAUDE.md kernel linear
#: tolerance (1e-7), NOT a fitted epsilon — measured round-trip deviation
#: for the planar box is exactly 0.0 (module docstring). Loosening this is a
#: reviewed decision recorded in docs/GEOMETRY-QA.md, never a quick fix.
ROUNDTRIP_TOL = 1e-7

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"
MODEL_FILES = sorted(GOLDENS_DIR.glob("*/model.json"))

each_model = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)


def test_roundtrip_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert MODEL_FILES, f"no golden models discovered under {GOLDENS_DIR}"


@each_model
def test_step_roundtrip_preserves_geometry(model_path: Path, tmp_path: Path) -> None:
    name = model_path.parent.name
    request = TessellateRequest.model_validate_json(
        model_path.read_text(encoding="utf-8")
    )
    original_shape = build_shape(request)
    original = measure_shape(original_shape)

    # Export: build123d/OCCT writes a STEP AP214 part 21 file.
    step_path = tmp_path / f"{name}.step"
    assert export_step(original_shape, step_path), f"{name}: STEP export failed"
    assert step_path.read_text(encoding="utf-8", errors="replace").startswith(
        "ISO-10303-21"
    ), f"{name}: not a STEP part 21 file"

    # Re-import and re-measure with the identical GProp pipeline.
    imported = import_step(step_path)
    solids = imported.solids()
    assert len(solids) == 1, f"{name}: expected 1 solid after import, got {len(solids)}"
    reimported = measure_shape(solids[0])

    checks: list[tuple[str, float, float]] = [
        ("volume", reimported.volume, original.volume),
        ("surface_area", reimported.surface_area, original.surface_area),
        ("centroid.x", reimported.centroid.x, original.centroid.x),
        ("centroid.y", reimported.centroid.y, original.centroid.y),
        ("centroid.z", reimported.centroid.z, original.centroid.z),
        ("bbox.min.x", reimported.bounding_box.min.x, original.bounding_box.min.x),
        ("bbox.min.y", reimported.bounding_box.min.y, original.bounding_box.min.y),
        ("bbox.min.z", reimported.bounding_box.min.z, original.bounding_box.min.z),
        ("bbox.max.x", reimported.bounding_box.max.x, original.bounding_box.max.x),
        ("bbox.max.y", reimported.bounding_box.max.y, original.bounding_box.max.y),
        ("bbox.max.z", reimported.bounding_box.max.z, original.bounding_box.max.z),
    ]
    for label, got, want in checks:
        assert got == pytest.approx(want, abs=ROUNDTRIP_TOL), (
            f"{name}: round-trip {label} drifted — exported {want!r}, "
            f"re-imported {got!r} (tol {ROUNDTRIP_TOL!r}). This is a defect "
            f"to root-cause (export/import/kernel), not noise."
        )

    assert reimported.topology == original.topology, (
        f"{name}: topology changed across STEP round-trip — "
        f"exported {original.topology.model_dump()}, "
        f"re-imported {reimported.topology.model_dump()}"
    )
