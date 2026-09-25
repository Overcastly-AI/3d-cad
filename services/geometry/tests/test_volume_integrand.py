"""Which faces the adaptive volume integral sees as NURBS twins (geometry QA F1).

:func:`geometry.kernel.properties.volume_integrand` converts a face to its
exact NURBS twin only when it sweeps a SPLINE: the adaptive integrator does not
converge on an extrusion or revolution of a B-spline, but it does on one of an
analytic conic, where the twin reads worse (review S3 of ``a0a70ec``). The
spline-slot golden pins the converted case's accuracy; this module pins the
routing on both sides.
"""
# The routing IS the private helper, so this module reads it directly.
# pyright: reportPrivateUsage=false

import math
from collections.abc import Callable

import geometry.kernel.properties as properties_module
import pytest
from build123d import Axis, Edge, Face, Plane, Solid, Wire, extrude, revolve
from geometry.kernel.properties import measure_shape, volume_integrand

#: Absolute volume bound (mm^3) for the analytic conic bodies below, MEASURED
#: FIRST, THEN SET (2026-09-25, VOLUME_EPS 1e-10): the unconverted readings are
#: 1.05e-5 (ellipse prism, 1885 mm^3) and 1.05e-5 (elliptic torus, 3158 mm^3);
#: as NURBS twins they read 1.93e-5 and 4.85e-5. 1.5e-5 sits between the two.
CONIC_VOLUME_TOL = 1.5e-5


def _ellipse_prism() -> Solid:
    return extrude(Face(Wire([Edge.make_ellipse(12.0, 5.0)])), 10.0).solid()


def _elliptic_torus() -> Solid:
    section = Edge.make_ellipse(4.0, 2.0, Plane.XZ.shift_origin((20, 0, 0)))
    return revolve(Face(Wire([section])), Axis.Z, 360).solid()


def _spline_prism() -> Solid:
    spline = Edge.make_spline([(0, 0, 0), (5, 3, 0), (10, -2, 0), (15, 0, 0)])
    closing = Edge.make_line((15, 0, 0), (0, 0, 0))
    return extrude(Face(Wire([spline, closing])), 10.0).solid()


@pytest.mark.parametrize(
    ("body", "truth"),
    [
        (_ellipse_prism, math.pi * 12.0 * 5.0 * 10.0),
        (_elliptic_torus, 2 * math.pi * 20.0 * math.pi * 4.0 * 2.0),
    ],
    ids=["ellipse-prism", "elliptic-torus"],
)
def test_a_swept_conic_is_integrated_as_itself(
    body: Callable[[], Solid], truth: float
) -> None:
    solid = body()
    assert measure_shape(solid).volume == pytest.approx(truth, abs=CONIC_VOLUME_TOL)
    assert volume_integrand(solid) is solid.wrapped


def test_a_swept_spline_is_integrated_as_its_nurbs_twin() -> None:
    solid = _spline_prism()
    assert volume_integrand(solid) is not solid.wrapped


def test_each_face_is_classified_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review N4: the routing builds a surface adaptor per check, so each face
    is classified exactly once, even when the body is converted."""
    solid = _spline_prism()
    seen: list[object] = []
    classify = properties_module._sweeps_a_spline

    def counting(face: Face) -> bool:
        seen.append(face)
        return classify(face)

    monkeypatch.setattr(properties_module, "_sweeps_a_spline", counting)
    assert volume_integrand(solid) is not solid.wrapped
    assert len(seen) == len(solid.faces())
