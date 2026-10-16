"""Plane Along Path math (PIPE-ALONG-PATH): a plane normal to a curve.

Fusion 360's *Plane Along Path* and SolidWorks' Plane "normal to curve": the
plane through a point of a curve, at a fraction of its length or a distance
along it from its start, whose normal is the curve's tangent there in the
direction of travel. The feature layer resolves the curve to a world edge
running from its start (a sketch curve as drawn, a model edge as picked);
this is a pure function of that edge (RESEARCH §9).

Basis: ``z_dir`` the tangent (negated by ``flip``); ``x_dir`` the owning
sketch's normal when the curve is a sketch curve (it is perpendicular to the
tangent everywhere along a planar curve, and it moves continuously when the
skeleton is edited, so a sketch on the plane never jumps a quarter turn), and
otherwise :func:`~geometry.kernel.faces.deterministic_x_dir` of the normal
(the on-face rule). ``flip`` keeps ``x_dir``, as for every datum kind.
"""

from typing import Literal

from build123d import Edge, Plane, PositionMode, Vector

from geometry.kernel.faces import deterministic_x_dir

#: A distance this far (mm) past the curve's end still lands on its end:
#: a typed length that equals the curve's length up to float noise.
PATH_END_TOLERANCE_MM = 1e-6


class DatumPathRangeError(ValueError):
    """The distance along the curve is past its end."""


def plane_along_edge(
    edge: Edge,
    measure: Literal["ratio", "distance"],
    ratio: float,
    distance_mm: float,
    flip: bool,
    sketch_normal: Vector | None,
) -> Plane:
    """The plane normal to *edge* at the requested point (module docstring).

    Raises:
        DatumPathRangeError: ``distance_mm`` is past the end of the curve.
    """
    length = float(edge.length)
    if measure == "ratio":
        along = ratio * length
    else:
        if distance_mm > length + PATH_END_TOLERANCE_MM:
            raise DatumPathRangeError(
                f"The plane is {distance_mm:.6g} mm along a curve only "
                f"{length:.6g} mm long. Use a distance up to the curve's length, "
                "or a ratio."
            )
        along = min(distance_mm, length)
    point = edge.position_at(along, PositionMode.LENGTH)
    normal = edge.tangent_at(along, PositionMode.LENGTH).normalized()
    if sketch_normal is not None:
        x_dir = (sketch_normal - normal * sketch_normal.dot(normal)).normalized()
    else:
        x_dir = deterministic_x_dir(normal)
    if flip:
        normal = -normal
    return Plane(origin=point, x_dir=x_dir, z_dir=normal)
