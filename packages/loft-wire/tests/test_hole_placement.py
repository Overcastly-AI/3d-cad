"""A hole's face-frame X/Y and the world position derived from them
(HOLE-POSITION-FORMULA, :mod:`loft_wire.hole_placement`)."""

import math
from typing import Any

import pytest
from loft_wire.expr import Quantity
from loft_wire.feature_resolve import resolve_feature
from loft_wire.features import FEATURE_REGISTRY, HoleParamsV1
from loft_wire.geometry import Vec3
from loft_wire.hole_placement import deterministic_x_dir, face_frame
from pydantic import ValidationError


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(p * q for p, q in zip(a, b, strict=True))


def _hole(envelope: Any) -> HoleParamsV1:
    params = envelope.params
    assert isinstance(params, HoleParamsV1)
    return params


def _params(normal: Vec3, centroid: Vec3, **extra: Any) -> dict[str, Any]:
    return {
        "face": {
            "kind": "subshape",
            "feature_id": "00000000-0000-0000-0000-0000000f0002",
            "subshape_type": "face",
            "selector": {
                "selector_version": 1,
                "signature": {
                    "subshape_type": "face",
                    "surface": "plane",
                    "normal": normal.model_dump(),
                    "centroid": centroid.model_dump(),
                    "area_mm2": 1000.0,
                },
            },
        },
        "position": {"x": 20.0, "y": 12.5, "z": 10.0},
        "diameter_mm": 5.0,
        "depth": {"kind": "through_all"},
        **extra,
    }


TOP = Vec3(x=0.0, y=0.0, z=1.0)
TOP_CENTROID = Vec3(x=20.0, y=12.5, z=10.0)


def test_a_hole_without_face_coordinates_keeps_its_position_and_bytes() -> None:
    raw = _params(TOP, TOP_CENTROID, position={"x": 3.25, "y": -1.0, "z": 10.0001})
    hole = HoleParamsV1.model_validate(raw)
    assert hole.position == Vec3(x=3.25, y=-1.0, z=10.0001)
    dumped = hole.model_dump(mode="json")
    assert "face_x_mm" not in dumped and "face_y_mm" not in dumped


def test_face_coordinates_derive_the_world_position_on_the_face_plane() -> None:
    hole = HoleParamsV1.model_validate(
        _params(TOP, TOP_CENTROID, face_x_mm=30.0, face_y_mm=-4.0)
    )
    # The top face's frame: origin (0, 0, 10), X along +X, Y along +Y.
    assert hole.position == Vec3(x=30.0, y=-4.0, z=10.0)
    # Idempotent: validating the dump again derives the same bytes.
    again = HoleParamsV1.model_validate(hole.model_dump(mode="json"))
    assert again.model_dump_json() == hole.model_dump_json()


def test_the_two_coordinates_come_together() -> None:
    with pytest.raises(ValidationError, match="set together"):
        HoleParamsV1.model_validate(_params(TOP, TOP_CENTROID, face_x_mm=1.0))
    with pytest.raises(ValidationError):
        HoleParamsV1.model_validate(
            _params(TOP, TOP_CENTROID, face_x_mm=math.inf, face_y_mm=0.0)
        )


def test_the_frame_is_the_kernels_and_the_webs() -> None:
    # Least-aligned world axis, ties to the earlier one (the kernel's rule).
    assert deterministic_x_dir((0.0, 0.0, 1.0)) == (1.0, 0.0, 0.0)
    assert deterministic_x_dir((1.0, 0.0, 0.0)) == (0.0, 1.0, 0.0)
    assert deterministic_x_dir((0.0, -1.0, 0.0)) == (1.0, 0.0, 0.0)
    # A 45-degree face: u, v, n orthonormal and right-handed; the origin is
    # the part origin projected onto the plane.
    s = math.sqrt(0.5)
    normal = Vec3(x=0.0, y=s, z=s)
    origin, u, v = face_frame(normal, Vec3(x=5.0, y=10.0, z=10.0))
    n = (0.0, s, s)
    assert _dot(u, n) == pytest.approx(0, abs=1e-15)
    assert _dot(v, n) == pytest.approx(0, abs=1e-15)
    assert _dot(u, v) == pytest.approx(0, abs=1e-15)
    assert u == (1.0, 0.0, 0.0)
    assert origin == pytest.approx((0.0, 10.0, 10.0))


def test_a_formula_on_x_moves_the_hole_when_its_parameter_changes() -> None:
    envelope = FEATURE_REGISTRY.load(
        "hole",
        1,
        _params(TOP, TOP_CENTROID, face_x_mm=0.0, face_y_mm=12.5),
        expressions={"/face_x_mm": "W - 20"},
    )
    at_100 = resolve_feature(envelope, {"W": Quantity(100.0, "length")})
    assert _hole(at_100).position == Vec3(x=80.0, y=12.5, z=10.0)
    at_80 = resolve_feature(at_100, {"W": Quantity(80.0, "length")})
    assert _hole(at_80).position == Vec3(x=60.0, y=12.5, z=10.0)
    assert at_80.expressions == {"/face_x_mm": "W - 20"}


def test_a_pointer_to_an_absent_coordinate_is_refused() -> None:
    with pytest.raises(ValidationError, match="face_x_mm"):
        FEATURE_REGISTRY.load(
            "hole", 1, _params(TOP, TOP_CENTROID), expressions={"/face_x_mm": "W"}
        )
