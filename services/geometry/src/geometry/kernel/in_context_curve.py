"""In-context curves: a resolved edge as data, and back (ASM-A3-IN-CONTEXT).

An in-context link stores the edge it last resolved to as a 3D line, circle or
arc in the edited part's frame (:data:`loft_wire.in_context.InContextCurve`).
:func:`describe_edge` reads one off a kernel edge (exactly, from the B-rep's
own line or circle), and :func:`curve_edge` builds the kernel edge back, so the
sketch rebuild projects it with the projector a same-part projection uses
(:func:`geometry.kernel.project.project_edge`).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import math
from typing import Literal

from build123d import Edge, GeomType, Plane, Vector
from loft_wire.geometry import Vec3
from loft_wire.in_context import (
    InContextArc,
    InContextCircle,
    InContextCurve,
    InContextLine,
)
from OCP.BRepAdaptor import BRepAdaptor_Curve

from geometry.kernel.edges import canonical_endpoints

#: A circle edge spanning a full turn to within this is a whole circle.
_CLOSED_TOL_RAD = 1e-9


def _vec3(x: float, y: float, z: float) -> Vec3:
    return Vec3(x=float(x), y=float(y), z=float(z))


def _of(point: Vector) -> Vec3:
    return _vec3(point.X, point.Y, point.Z)


def _at(v: Vec3) -> Vector:
    return Vector(v.x, v.y, v.z)


def _dist(a: Vec3, b: Vec3) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def describe_edge(
    edge: Edge, previous: InContextCurve | None = None
) -> InContextCurve | Literal["unsupported_curve"]:
    """*edge* as an in-context curve, in *edge*'s own frame.

    A line keeps the end order of *previous* (the end nearer its ``start``
    comes first), so an entity's ``start`` keeps following the same end; with
    none it starts at the signature's canonical ``end_a``. Only lines and
    circles are curves a sketch holds exactly.
    """
    match edge.geom_type:
        case GeomType.LINE:
            end_a, end_b = canonical_endpoints(edge)
            a, b = _of(end_a), _of(end_b)
            if isinstance(previous, InContextLine) and _dist(b, previous.start) < _dist(
                a, previous.start
            ):
                a, b = b, a
            return InContextLine(kind="line", start=a, end=b)
        case GeomType.CIRCLE:
            adaptor = BRepAdaptor_Curve(edge.wrapped)
            circle = adaptor.Circle()
            first, last = adaptor.FirstParameter(), adaptor.LastParameter()
            if last - first >= 2.0 * math.pi - _CLOSED_TOL_RAD:
                centre = circle.Location()
                axis = circle.Axis().Direction()
                return InContextCircle(
                    kind="circle",
                    center=_vec3(centre.X(), centre.Y(), centre.Z()),
                    normal=_vec3(axis.X(), axis.Y(), axis.Z()),
                    radius=float(circle.Radius()),
                )
            points = [adaptor.Value(t) for t in (first, (first + last) / 2.0, last)]
            start, mid, end = (_vec3(p.X(), p.Y(), p.Z()) for p in points)
            return InContextArc(kind="arc", start=start, mid=mid, end=end)
        case _:
            return "unsupported_curve"


def curve_edge(curve: InContextCurve) -> Edge:
    """The kernel edge *curve* describes."""
    match curve:
        case InContextLine():
            return Edge.make_line(_at(curve.start), _at(curve.end))
        case InContextCircle():
            plane = Plane(origin=_at(curve.center), z_dir=_at(curve.normal))
            return Edge.make_circle(curve.radius, plane)
        case InContextArc():
            return Edge.make_three_point_arc(
                _at(curve.start), _at(curve.mid), _at(curve.end)
            )


def curve_distance(a: InContextCurve, b: InContextCurve) -> float:
    """How far apart two curves of the same kind are (mm; infinite across
    kinds): the largest gap between corresponding defining points. A circle's
    normal counts by its tip at unit length."""
    match a, b:
        case InContextLine(), InContextLine():
            return max(_dist(a.start, b.start), _dist(a.end, b.end))
        case InContextCircle(), InContextCircle():
            return max(
                _dist(a.center, b.center),
                _dist(a.normal, b.normal),
                abs(a.radius - b.radius),
            )
        case InContextArc(), InContextArc():
            return max(
                _dist(a.start, b.start), _dist(a.mid, b.mid), _dist(a.end, b.end)
            )
        case _:
            return math.inf
