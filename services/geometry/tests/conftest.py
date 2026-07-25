"""Shared fixtures for the geometry test suite.

The workspace runs pytest with ``--import-mode=importlib`` (root
pyproject.toml), so test modules cannot import from each other —
cross-suite constants and assertion helpers live here as fixtures instead
(single source of truth, CLAUDE.md DRY rule).
"""

from collections.abc import Callable
from typing import Any

import pytest
from geometry.schemas import ShapeProperties

#: Round-trip tolerance for mass properties: the CLAUDE.md kernel linear
#: tolerance (1e-7), NOT a fitted epsilon — the measured round-trip deviation
#: for the planar box is exactly 0.0 (docs/GEOMETRY-QA.md), so the bound is a
#: ceiling, not a fit. Shared by the kernel-level (test_step_roundtrip) and
#: endpoint-level (test_export) STEP round-trip gates. Loosening it is a
#: reviewed decision recorded in docs/GEOMETRY-QA.md, never a quick fix.
ROUNDTRIP_TOL = 1e-7


@pytest.fixture(scope="session")
def roundtrip_tol() -> float:
    """``ROUNDTRIP_TOL`` as a fixture (importlib mode blocks cross-module imports).

    For gates that compare mass properties themselves rather than through
    :func:`assert_roundtrip_preserved` — e.g. the assembly-export round-trip,
    which matches re-imported solids to solved placements — so the one documented
    kernel bound stays the single source of truth (DRY), never re-hardcoded.
    """
    return ROUNDTRIP_TOL


@pytest.fixture(scope="session")
def assert_roundtrip_preserved() -> Callable[
    [str, ShapeProperties, ShapeProperties], None
]:
    """Assert re-imported geometry matches the original B-rep.

    Mass properties (volume, area, centroid, exact AABB) within
    ``ROUNDTRIP_TOL``; topology counts exactly. A deviation is a DEFECT to
    root-cause to export, import, or kernel — never tolerance noise to
    absorb (geometry-gates skill rules).
    """

    def check(
        name: str, reimported: ShapeProperties, original: ShapeProperties
    ) -> None:
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
            f"{name}: topology changed across round-trip — "
            f"exported {original.topology.model_dump()}, "
            f"re-imported {reimported.topology.model_dump()}"
        )

    return check


@pytest.fixture(scope="session")
def assert_validation_envelope() -> Callable[[dict[str, Any]], None]:
    """Assert a body is the py-kit error envelope with the validation code."""

    def check(body: dict[str, Any]) -> None:
        assert set(body) == {"error"}
        error: dict[str, Any] = body["error"]
        assert set(error) == {"code", "message", "details", "request_id"}
        assert error["code"] == "validation_error"
        assert error["details"]  # pydantic locates the offending field(s)

    return check
