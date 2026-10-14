"""HOLE-FRAME-PARITY: loft-wire's face frame against the shared frozen vector.

A planar face's in-plane frame is computed three times (here, the kernel's
``geometry.kernel.faces.deterministic_x_dir`` and the web's ``faceFrame``).
All three read ``tests/fixtures/face_frames.json`` and must match it to its
tolerance; a hole driven by face X/Y lands in the wrong place if they drift.
The vector was generated from this implementation once and is FROZEN: a
failure here means this code changed, not that the file needs regenerating.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from loft_wire.geometry import Vec3
from loft_wire.hole_placement import deterministic_x_dir, face_frame

VECTOR_PATH = Path(__file__).parent / "fixtures" / "face_frames.json"
_VECTOR: dict[str, Any] = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
_TOL: float = _VECTOR["tolerance"]
_CASES: list[dict[str, Any]] = _VECTOR["cases"]


def _close(got: tuple[float, ...], want: list[float]) -> bool:
    return all(abs(g - w) <= _TOL for g, w in zip(got, want, strict=True))


def test_the_vector_covers_what_it_claims() -> None:
    # Non-vacuity: an emptied or truncated file would pass every case below.
    assert _TOL == 1e-12
    assert len(_CASES) >= 40
    labels = [case["label"] for case in _CASES]
    assert len(set(labels)) == len(labels)
    assert sum(label.startswith("axis ") for label in labels) == 6
    assert sum(label.startswith("near tie") for label in labels) >= 6


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["label"])
def test_loft_wire_face_frame_matches_the_frozen_vector(case: dict[str, Any]) -> None:
    n = case["normal"]
    _, u, v = face_frame(Vec3(x=n[0], y=n[1], z=n[2]), Vec3(x=0.0, y=0.0, z=0.0))
    assert _close(u, case["x_dir"]), (u, case["x_dir"])
    assert _close(v, case["y_dir"]), (v, case["y_dir"])
    assert _close(deterministic_x_dir((n[0], n[1], n[2])), case["x_dir"])


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["label"])
def test_frozen_frames_are_right_handed_orthonormal(case: dict[str, Any]) -> None:
    # Independent of every implementation: (x, y, n) is an orthonormal,
    # right-handed basis, so a hand-edited vector cannot smuggle in nonsense.
    n: list[float] = case["normal"]
    x: list[float] = case["x_dir"]
    y: list[float] = case["y_dir"]

    def dot(a: list[float], b: list[float]) -> float:
        return sum(p * q for p, q in zip(a, b, strict=True))

    for w in (n, x, y):
        assert math.isclose(dot(w, w), 1.0, abs_tol=1e-12)
    assert abs(dot(n, x)) <= 1e-12
    assert abs(dot(n, y)) <= 1e-12
    assert abs(dot(x, y)) <= 1e-12
    cross = (
        n[1] * x[2] - n[2] * x[1],
        n[2] * x[0] - n[0] * x[2],
        n[0] * x[1] - n[1] * x[0],
    )
    assert _close(cross, y)


@pytest.mark.parametrize(
    ("label", "x_dir"),
    [
        # Hand-derived, not from any implementation under test.
        (
            "tie all three (1,1,1)",
            (2 / math.sqrt(6), -1 / math.sqrt(6), -1 / math.sqrt(6)),
        ),
        (
            "angled (1,2,3)",
            (13 / math.sqrt(182), -2 / math.sqrt(182), -3 / math.sqrt(182)),
        ),
        ("angled (0.6,0,0.8)", (0.0, 1.0, 0.0)),
        (
            "near tie |y|<|x| by 1e-10 (1+e,1,sqrt2)",
            (-1 / (2 * math.sqrt(3)), math.sqrt(3) / 2, -1 / math.sqrt(6)),
        ),
    ],
)
def test_frozen_vector_agrees_with_hand_calculation(
    label: str, x_dir: tuple[float, float, float]
) -> None:
    case = next(case for case in _CASES if case["label"] == label)
    # The near-tie normal is 1e-10 off the hand value, hence 1e-9 there.
    assert all(abs(g - w) <= 1e-9 for g, w in zip(case["x_dir"], x_dir, strict=True))
