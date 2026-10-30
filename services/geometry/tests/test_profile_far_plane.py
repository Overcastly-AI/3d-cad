"""A profile with holes on a plane far from the origin (SIDING-TRIM).

B7 at 28 ft puts its right wall's window unit on the plane X = 336 in, and
its frame (a rectangle round the glass) was refused as "loops not enclosed":
build123d's ``Face.is_inside`` classifies with OCCT's 3D solid classifier,
which calls every point outside once the face's plane is more than about
300 in from the origin along its normal. The containment test now uses the
2D face classifier, which holds at any distance.
"""

import pytest
from build123d import Vector, Wire
from geometry.kernel.extrude import (
    ProfileUnsupportedError,
    _build_face_with_holes,  # pyright: ignore[reportPrivateUsage]
)

IN = 25.4


def _loop(x: float, a0: float, a1: float, z0: float, z1: float) -> Wire:
    points = [(a0, z0), (a1, z0), (a1, z1), (a0, z1)]
    return Wire.make_polygon([Vector(x, a * IN, z * IN) for a, z in points], close=True)


@pytest.mark.parametrize("x_in", [0.0, 288.0, 336.0, 400.0, 4000.0])
def test_a_framed_window_on_a_far_plane_builds(x_in: float) -> None:
    """The 2030 unit's frame: 24 x 36 round its 20 x 32 glass, area
    864 - 640 = 224 in^2, wherever the wall stands."""
    x = x_in * IN
    face = _build_face_with_holes(
        [_loop(x, 84, 108, 57.71875, 93.71875), _loop(x, 86, 106, 59.71875, 91.71875)]
    )
    assert face.area / IN**2 == pytest.approx(224.0, abs=1e-9)


@pytest.mark.parametrize("x_in", [0.0, 336.0, 4000.0])
def test_a_loop_outside_is_still_refused(x_in: float) -> None:
    x = x_in * IN
    with pytest.raises(ProfileUnsupportedError, match="not all enclosed"):
        _build_face_with_holes([_loop(x, 84, 108, 57, 93), _loop(x, 186, 206, 59, 91)])
