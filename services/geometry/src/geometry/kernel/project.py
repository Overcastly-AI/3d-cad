"""Project a body edge onto a sketch plane (SKETCH-PROJECT-EDGES).

Fusion 360's Project and SolidWorks' Convert Entities: the edge seen along the
plane normal, in the plane's local (x, y) coordinates. Only the curves a
sketch has an entity for project exactly:

* a **line** projects to a line through its two projected endpoints, unless it
  runs along the normal, where both endpoints land on one point
  (``degenerate``);
* a **circle or arc** whose axis is parallel to the normal projects to a
  circle or arc of the same radius about the projected centre. Its parameter
  runs counter-clockwise about its own axis, so with the axis ANTIPARALLEL to
  the normal it runs clockwise in the sketch, and the ends are swapped to keep
  the sketch's counter-clockwise arc convention. Any other circle projects to
  an ellipse (``unsupported_curve``);
* an ellipse, a B-spline or any other curve is ``unsupported_curve``. v1 has
  no entity that holds a projected B-spline exactly (BACKLOG
  SKETCH-PROJECT-SPLINE), and a fit-point approximation would be wrong
  geometry wearing a link.

The entity kind is the caller's: an edge that now projects to a different kind
than the entity holds (a line that became an arc, an arc that closed into a
circle) is ``kind_changed``. Every failure is a reason, never an exception: a
projection that cannot follow its edge is sick, and the sketch keeps its last
good coordinates (Fusion's behaviour).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import math
from dataclasses import dataclass
from typing import Literal

from build123d import Edge, GeomType, Plane, Vector
from OCP.BRepAdaptor import BRepAdaptor_Curve

from geometry.kernel.edges import canonical_endpoints

#: The entity kinds a body edge can project to.
ProjectedKind = Literal["line", "arc", "circle"]

#: Why an edge cannot be projected (the kernel half of the wire's
#: ``SketchProjectionReason``; ``unresolved``/``ambiguous``/``no_body`` are the
#: resolver's and the evaluator's).
ProjectionFailure = Literal["unsupported_curve", "degenerate", "kind_changed"]

#: Two projected points closer than this are one point: the subshape linear
#: tolerance (the edge signature's endpoint tolerance, docs/GEOMETRY-QA.md).
_POINT_TOL_MM = 1e-6

#: A circle's axis counts as parallel to the plane normal when the sine of the
#: angle between them is at most this: the kernel's edge direction tolerance
#: (``geometry.kernel.edges._EDGE_DIRECTION_TOLERANCE``). A tilt any larger
#: makes the projection an ellipse the sketch cannot hold exactly.
_AXIS_TOL = 1e-7

#: A circle edge whose parameter span is a full turn to within this is a whole
#: circle: OCCT stores a full circle as exactly [0, 2 pi].
_CLOSED_TOL_RAD = 1e-9

_P2 = tuple[float, float]


@dataclass(frozen=True)
class ProjectedLine:
    """A line's projection. ``a``/``b`` are the edge's CANONICAL ends
    (``end_a``/``end_b`` of its signature), so the caller can keep each end in
    its entity slot; ``a_3d``/``b_3d`` are the same ends in world space."""

    a: _P2
    b: _P2
    a_3d: tuple[float, float, float]
    b_3d: tuple[float, float, float]


@dataclass(frozen=True)
class ProjectedArc:
    """An arc's projection, counter-clockwise from ``start`` to ``end``."""

    center: _P2
    start: _P2
    end: _P2


@dataclass(frozen=True)
class ProjectedCircle:
    center: _P2
    radius: float


Projected = ProjectedLine | ProjectedArc | ProjectedCircle


def _local(plane: Plane, point: Vector) -> _P2:
    local = plane.to_local_coords(point)
    return (float(local.X), float(local.Y))


def plane_point(plane: Plane, point: tuple[float, float, float]) -> _P2:
    """A world point seen along *plane*'s normal, in its local (x, y)."""
    return _local(plane, Vector(*point))


def _xyz(point: Vector) -> tuple[float, float, float]:
    return (float(point.X), float(point.Y), float(point.Z))


def _project_line(edge: Edge, plane: Plane) -> ProjectedLine | ProjectionFailure:
    end_a, end_b = canonical_endpoints(edge)
    a, b = _local(plane, end_a), _local(plane, end_b)
    if math.dist(a, b) <= _POINT_TOL_MM:
        return "degenerate"
    return ProjectedLine(a=a, b=b, a_3d=_xyz(end_a), b_3d=_xyz(end_b))


def _project_circle(
    edge: Edge, plane: Plane
) -> ProjectedArc | ProjectedCircle | ProjectionFailure:
    adaptor = BRepAdaptor_Curve(edge.wrapped)
    circle = adaptor.Circle()
    axis = circle.Axis().Direction()
    normal = plane.z_dir
    dot = axis.X() * normal.X + axis.Y() * normal.Y + axis.Z() * normal.Z
    if math.sqrt(max(0.0, 1.0 - dot * dot)) > _AXIS_TOL:
        return "unsupported_curve"
    location = circle.Location()
    center = _local(plane, Vector(location.X(), location.Y(), location.Z()))
    first, last = adaptor.FirstParameter(), adaptor.LastParameter()
    if last - first >= 2.0 * math.pi - _CLOSED_TOL_RAD:
        return ProjectedCircle(center=center, radius=float(circle.Radius()))
    p_first, p_last = adaptor.Value(first), adaptor.Value(last)
    start = _local(plane, Vector(p_first.X(), p_first.Y(), p_first.Z()))
    end = _local(plane, Vector(p_last.X(), p_last.Y(), p_last.Z()))
    if dot < 0.0:
        start, end = end, start
    return ProjectedArc(center=center, start=start, end=end)


def _kind_of(projected: Projected) -> ProjectedKind:
    if isinstance(projected, ProjectedLine):
        return "line"
    if isinstance(projected, ProjectedArc):
        return "arc"
    return "circle"


def project_edge(
    edge: Edge, plane: Plane, kind: ProjectedKind
) -> Projected | ProjectionFailure:
    """*edge* projected along *plane*'s normal into its local coordinates, as
    an entity of *kind*, or the reason it cannot be.

    The curve is read from the exact B-rep (the adaptor's own circle and
    parameter range), never a tessellation. Deterministic: a pure function of
    the edge and the plane.
    """
    match edge.geom_type:
        case GeomType.LINE:
            projected = _project_line(edge, plane)
        case GeomType.CIRCLE:
            projected = _project_circle(edge, plane)
        case _:
            return "unsupported_curve"
    if isinstance(projected, str):
        return projected
    if _kind_of(projected) != kind:
        return "kind_changed"
    return projected
