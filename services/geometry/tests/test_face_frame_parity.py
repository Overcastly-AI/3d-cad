"""HOLE-FRAME-PARITY: the kernel's on-face frame against the shared frozen vector.

``loft_wire.hole_placement`` turns a hole's face X/Y into a world position with
its own copy of :func:`geometry.kernel.faces.deterministic_x_dir`; the web has a
third. All three read ``packages/loft-wire/tests/fixtures/face_frames.json``.
Y is checked on the plane the kernel really builds for a face
(``Plane(x_dir=deterministic_x_dir(n), z_dir=n)``, as ``_face_plane`` does), so
the sketch-on-face basis is covered too, not only the x pick.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from build123d import Plane, Vector
from geometry.kernel.faces import deterministic_x_dir

VECTOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "loft-wire"
    / "tests"
    / "fixtures"
    / "face_frames.json"
)
_VECTOR: dict[str, Any] = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
_TOL: float = _VECTOR["tolerance"]
_CASES: list[dict[str, Any]] = _VECTOR["cases"]


def _close(got: Vector, want: list[float]) -> bool:
    return all(abs(g - w) <= _TOL for g, w in zip(tuple(got), want, strict=True))


def test_the_shared_vector_is_there_and_full() -> None:
    assert _TOL == 1e-12
    assert len(_CASES) >= 40


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["label"])
def test_kernel_face_frame_matches_the_frozen_vector(case: dict[str, Any]) -> None:
    normal = Vector(*case["normal"])
    x_dir = deterministic_x_dir(normal)
    assert _close(x_dir, case["x_dir"]), (tuple(x_dir), case["x_dir"])
    plane = Plane(origin=(0, 0, 0), x_dir=x_dir, z_dir=normal)
    assert _close(plane.x_dir, case["x_dir"]), (tuple(plane.x_dir), case["x_dir"])
    assert _close(plane.y_dir, case["y_dir"]), (tuple(plane.y_dir), case["y_dir"])
