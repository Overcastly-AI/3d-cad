"""Plane-at-an-angle math (DATUM-PLANE-ANGLE) — a pure function of resolved inputs.

Fusion 360's *Plane at Angle*, SolidWorks' Plane "At angle" and Onshape's
Plane "Line angle" all build the same thing: the plane that contains a line and
makes a typed angle with a reference plane. Given a line already resolved to a
point and a direction (sketch line, model edge or origin axis — the feature
layer does that) and a resolved reference :class:`~build123d.Plane`, the plane
here is DETERMINISTIC (RESEARCH §9): same inputs, bitwise-identical plane.

Conventions (RESEARCH §18, mirrored by the web client's ``angleBasis``):

* The line must be PARALLEL to the reference (``|d . n| <=``
  :data:`DATUM_LINE_PARALLEL_TOLERANCE`); it may lie in the reference or off
  it. Turning a plane about a line that pierces the reference cannot reach the
  reference's orientation at angle 0, so "the angle from the reference" is
  undefined: :class:`DatumLineNotParallelError`, never a guessed plane.
* Normal = the reference normal turned ``angle_deg`` RIGHT-HANDED about the
  line direction (Rodrigues; with ``d . n = 0`` it is
  ``n cos(a) + (d x n) sin(a)``), re-orthogonalised against ``d`` so the frame
  is exactly orthonormal. ``angle_deg = 0`` gives the plane through the line
  parallel to the reference; ``flip`` negates the normal.
* Basis: ``x_dir`` = the line direction (sketch +u runs along the line, the
  natural frame for a tube sketched on it), origin = the point of the line
  nearest the world origin (the midplane's rule for a line), ``y_dir`` =
  ``z_dir x x_dir`` (build123d). ``flip`` keeps ``x_dir`` and flips +v, as for
  every datum kind.
"""

import math

from build123d import Plane, Vector

#: Documented parallelism bound: the line is parallel to the reference iff the
#: sine of the angle between them, ``|d . n|`` for unit vectors, is at most this.
#: The same sizing as ``MIDPLANE_PARALLEL_TOLERANCE`` (geometry.kernel.datum):
#: a line drawn in, or modelled along, the reference carries ulp-scale noise
#: (< 1e-12), while the smallest authorable tilt (1e-3 deg ~ 1.7e-5) is far
#: above it; nothing real lives near the bound.
DATUM_LINE_PARALLEL_TOLERANCE = 1e-9

#: A line shorter than this (mm) has no direction to turn about.
DATUM_LINE_MIN_LENGTH_MM = 1e-9


class DatumLineNotParallelError(ValueError):
    """The line crosses the reference plane at an angle, so it has no plane at
    a defined angle from it (RESEARCH §18)."""


def plane_at_angle(
    point: Vector,
    direction: Vector,
    reference: Plane,
    angle_deg: float,
    flip: bool,
) -> Plane:
    """The plane through the line ``point + t * direction`` at ``angle_deg``
    from *reference* (module docstring for the conventions).

    *direction* need not be unit length but must be longer than
    :data:`DATUM_LINE_MIN_LENGTH_MM` (the feature layer refuses a degenerate
    line before it gets here).

    Raises:
        DatumLineNotParallelError: the line is not parallel to *reference*.
    """
    d = direction.normalized()
    n = reference.z_dir.normalized()
    tilt = d.dot(n)
    if abs(tilt) > DATUM_LINE_PARALLEL_TOLERANCE:
        degrees = math.degrees(math.asin(min(1.0, abs(tilt))))
        raise DatumLineNotParallelError(
            f"The line crosses the reference plane at {degrees:.6g} deg, so no "
            "plane through it has a defined angle from that reference. Choose a "
            "line parallel to the reference (in it, or along it), or a "
            "reference the line is parallel to."
        )
    radians = math.radians(angle_deg)
    turned = n * math.cos(radians) + d.cross(n) * math.sin(radians)
    normal = (turned - d * turned.dot(d)).normalized()
    if flip:
        normal = -normal
    origin = point - d * point.dot(d)
    return Plane(origin=origin, x_dir=d, z_dir=normal)
