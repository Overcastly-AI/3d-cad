"""Sweep a closed profile along a CLOSED, tangent-continuous path (SWEEP-CLOSED-PATH).

A loop of tube, a ring frame, a rounded-rectangle bumper: Fusion 360, SolidWorks
and Onshape sweep a profile around a closed path in one feature and return one
closed solid with no cap faces, no seam gap and no overlap where the sweep
starts and ends. This module is that sweep; :mod:`geometry.kernel.sweep` keeps
the open-path sweep, which is unchanged (docs/RESEARCH.md §19).

Three kernel decisions, each the industry's:

* **Tangent continuity is required.** A closed path with a corner that is not
  G1 is refused with :class:`PathCornerError`, which names the joint (its two
  sketch entities and the sketch point), instead of sweeping it: OCCT's pipe
  shell around a sharp corner of a CLOSED spine returns a "valid" zero-volume
  solid (a 100 mm square loop sweeps to 3e-13 mm^3). SolidWorks and Onshape
  likewise need a tangent-continuous closed path, or a fillet at each corner.
* **A fixed binormal.** A sketch path is planar, so the section's frame keeps
  its binormal on the sketch normal (OCCT's ``BinormalMode``,
  ``BRepOffsetAPI_MakePipeShell::SetMode(gp_Dir)``): the frame is a pure
  function of the path tangent, so it cannot flip at an inflection the way a
  Frenet frame does, and it returns to itself after one loop, so the end
  section lands exactly on the start section (no twist creep, no seam gap).
* **The sweep starts at the profile.** A closed path has no natural start, so
  the section is seated at the point of the path nearest the profile's centre;
  the open sweep's "anchored at the profile" rule then holds for a closed path
  wherever its first sketch entity happens to begin. OCCT always starts the
  pipe at the wire's first vertex, so the profile is carried there by the one
  rigid motion that takes the binormal frame at the seat to the frame at the
  start. With a binormal frame every section is that frame times the profile,
  so the swept solid does not depend on where the loop starts.

Determinism (RESEARCH §9): joints are visited in entity order, the seat is the
first nearest edge in wire order, and every kernel call is a pure function of
its inputs.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Edge, Face, Plane, Solid, Vector, Vertex, Wire
from loft_wire.sketch import SketchEntity
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_SupportType
from OCP.BRepLProp import BRepLProp_CLProps
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.gp import gp_Dir, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_Orientation
from OCP.TopoDS import TopoDS, TopoDS_Edge

from geometry.kernel.extrude import PROFILE_WIRE_TOLERANCE, entity_edges
from geometry.kernel.healing import clean_shape
from geometry.kernel.sweep_check import check_not_self_intersecting

#: The largest turn (radians) a closed path may make at a joint and still count
#: as tangent-continuous: 1e-6 rad. A solved tangent constraint closes to
#: ~1e-12 rad and an arc-to-line fillet built in build123d to ~1e-15 rad, so
#: this admits every joint a sketch means to be smooth; a drawn corner of even
#: 0.001 deg (1.7e-5 rad) is refused rather than swept into a crease.
G1_ANGLE_TOLERANCE_RAD = 1e-6

#: A profile plane this close to containing the seat tangent (|n . t|) sweeps
#: a section edge-on along the path: no volume, so it is refused up front.
_EDGE_ON_TOLERANCE = 1e-6

#: Curvature samples per non-arc path edge (a spline) for the bend check.
_CURVATURE_SAMPLES = 64

#: Points sampled around the profile's outer loop to measure its reach.
_REACH_SAMPLES = 128


#: Two edge ends this close are one joint: the wire-assembly tolerance.
_JOINT_TOLERANCE = PROFILE_WIRE_TOLERANCE


class PathCornerError(ValueError):
    """A closed path turns at a joint that is not tangent-continuous (G1)."""


class ClosedSweepError(RuntimeError):
    """The closed sweep failed or produced an invalid or empty solid."""


class PathTooTightError(ClosedSweepError):
    """The path bends tighter than the profile reaches across it, so the swept
    section would pass through itself on the inside of the bend."""


@dataclass(frozen=True)
class _EdgeEnd:
    entity_id: str
    point: Vector
    #: Unit direction pointing from the joint INTO the edge.
    inward: Vector


def _ends(entity_id: str, edge: Edge) -> tuple[_EdgeEnd, _EdgeEnd]:
    start = _EdgeEnd(entity_id, edge.position_at(0), edge.tangent_at(0))
    end = _EdgeEnd(entity_id, edge.position_at(1), -edge.tangent_at(1))
    return start, end


def _turn_rad(a: Vector, b: Vector) -> float:
    """The turn between two inward directions meeting at one joint (0 = G1)."""
    cosine = max(-1.0, min(1.0, -a.dot(b)))
    return math.acos(cosine)


def check_closed_path_tangent(plane: Plane, entities: Sequence[SketchEntity]) -> None:
    """Refuse a closed path with any joint that is not G1, naming the joint.

    *entities* are the path sketch's solved entities (construction excluded
    here exactly as in :func:`geometry.kernel.sweep.build_path_wire`), which
    the caller has already proved form one closed wire. Each edge end is paired
    with the other end at the same point; the joint's turn is the angle between
    the two edges' directions there. The first offending joint in entity order
    is reported.

    Raises:
        PathCornerError: a joint turns by more than :data:`G1_ANGLE_TOLERANCE_RAD`.
    """
    ends: list[_EdgeEnd] = [
        end
        for entity in entities
        if not entity.construction
        for edge in entity_edges(plane, entity)
        for end in _ends(entity.id, edge)
    ]
    for index, here in enumerate(ends):
        partners = [
            other
            for j, other in enumerate(ends)
            if j != index and (other.point - here.point).length <= _JOINT_TOLERANCE
        ]
        if len(partners) != 1:
            # A closed wire meets each end exactly once; a branch is no loop.
            raise PathCornerError(
                f"The path branches at {_sketch_point(plane, here.point)} "
                f"({len(partners) + 1} ends meet there); a closed sweep path is "
                "one loop."
            )
        there = partners[0]
        turn = _turn_rad(here.inward, there.inward)
        if turn > G1_ANGLE_TOLERANCE_RAD:
            raise PathCornerError(
                f"The closed path has a sharp corner of {math.degrees(turn):.3g} "
                f"deg where {_joint_name(here, there)} meet at "
                f"{_sketch_point(plane, here.point)}. A closed sweep path must be "
                "tangent-continuous: add a tangent constraint or a fillet at that "
                "joint."
            )


def _joint_name(a: _EdgeEnd, b: _EdgeEnd) -> str:
    if a.entity_id == b.entity_id:
        return f"the two ends of '{a.entity_id}'"
    return f"'{a.entity_id}' and '{b.entity_id}'"


def _sketch_point(plane: Plane, point: Vector) -> str:
    local = plane.to_local_coords(point)
    assert isinstance(local, Vector)
    return f"({local.X:.4g}, {local.Y:.4g})"


def _oriented_tangent(edge: TopoDS_Edge, parameter: float) -> Vector:
    """The unit tangent of *edge* at *parameter*, in the WIRE's travel direction."""
    point = gp_Pnt()
    derivative = gp_Vec()
    BRepAdaptor_Curve(edge).D1(parameter, point, derivative)
    tangent = Vector(derivative.X(), derivative.Y(), derivative.Z()).normalized()
    if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        return -tangent
    return tangent


def _start_frame(path: Wire) -> tuple[Vector, Vector]:
    """Where OCCT's pipe shell starts on *path*, and the travel tangent there.

    ``BRepFill_PipeShell`` walks the spine with ``BRepTools_WireExplorer``, so
    its first section sits at the first explored edge's first vertex.
    """
    explorer = BRepTools_WireExplorer(path.wrapped)
    edge = explorer.Current()
    curve = BRepAdaptor_Curve(edge)
    forward = edge.Orientation() != TopAbs_Orientation.TopAbs_REVERSED
    parameter = curve.FirstParameter() if forward else curve.LastParameter()
    point = curve.Value(parameter)
    return Vector(point.X(), point.Y(), point.Z()), _oriented_tangent(edge, parameter)


def _seat_frame(path: Wire, target: Vector) -> tuple[Vector, Vector]:
    """The point of *path* nearest *target*, and the travel tangent there.

    Edges are visited in wire order and only a strictly nearer edge replaces the
    best so far, so a tie (a profile centred on a circular path's axis) resolves
    to the earliest edge, deterministically.
    """
    best: tuple[float, Vector, Vector] | None = None
    probe = Vertex(target.X, target.Y, target.Z).wrapped
    explorer = BRepTools_WireExplorer(path.wrapped)
    while explorer.More():
        edge = explorer.Current()
        extrema = BRepExtrema_DistShapeShape(probe, edge)
        extrema.Perform()
        if extrema.IsDone() and extrema.NbSolution() > 0:
            distance = extrema.Value()
            if best is None or distance < best[0] - 1e-9:
                hit = extrema.PointOnShape2(1)
                best = (
                    distance,
                    Vector(hit.X(), hit.Y(), hit.Z()),
                    _oriented_tangent(edge, _parameter_of_hit(extrema, edge)),
                )
        explorer.Next()
    if best is None:
        raise ClosedSweepError("The closed path has no edge to seat the profile on.")
    return best[1], best[2]


def _parameter_of_hit(extrema: BRepExtrema_DistShapeShape, edge: TopoDS_Edge) -> float:
    """The curve parameter on *edge* of the extremum's first solution."""
    if extrema.SupportTypeShape2(1) == BRepExtrema_SupportType.BRepExtrema_IsOnEdge:
        # OCP returns the by-reference parameter as a 1-tuple.
        return float(extrema.ParOnEdgeS2(1)[0])
    vertex = TopoDS.Vertex_s(extrema.SupportOnShape2(1))
    return BRep_Tool.Parameter_s(vertex, edge)


def _tightest_bends(path: Wire, normal: Vector) -> tuple[float, float]:
    """The tightest bend radius turning LEFT and turning RIGHT along *path*.

    Left is ``normal x travel`` (the binormal frame's lateral). A bend only
    folds the section on its INSIDE, so a left turn is limited by how far the
    section reaches to the left, and a right turn by its reach to the right.
    Every curved edge (arc or spline) is sampled at :data:`_CURVATURE_SAMPLES`
    points, ends included; a circle's curvature is exact at every sample.
    """
    left = right = math.inf
    explorer = BRepTools_WireExplorer(path.wrapped)
    while explorer.More():
        edge = explorer.Current()
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() != GeomAbs_CurveType.GeomAbs_Line:
            first, last = curve.FirstParameter(), curve.LastParameter()
            for i in range(_CURVATURE_SAMPLES + 1):
                parameter = first + (last - first) * i / _CURVATURE_SAMPLES
                props = BRepLProp_CLProps(curve, parameter, 2, 1e-9)
                curvature = props.Curvature()
                if curvature <= 1e-12:
                    continue
                towards = gp_Dir()
                props.Normal(towards)
                centre = Vector(towards.X(), towards.Y(), towards.Z())
                lateral = normal.cross(_oriented_tangent(edge, parameter))
                if centre.dot(lateral) > 0:
                    left = min(left, 1.0 / curvature)
                else:
                    right = min(right, 1.0 / curvature)
        explorer.Next()
    return left, right


def _lateral_reach(face: Face, seat: Vector, lateral: Vector) -> tuple[float, float]:
    """How far the profile reaches from the path to its left and to its right."""
    outer = face.outer_wire()
    offsets = [
        (outer.position_at(i / _REACH_SAMPLES) - seat).dot(lateral)
        for i in range(_REACH_SAMPLES)
    ]
    return max(0.0, *offsets), max(0.0, *(-o for o in offsets))


def _check_bends(
    face: Face, path: Wire, normal: Vector, seat: Vector, lateral: Vector
) -> None:
    """Refuse a bend tighter than the section reaches towards its inside."""
    reach_left, reach_right = _lateral_reach(face, seat, lateral)
    bend_left, bend_right = _tightest_bends(path, normal)
    for reach, bend in ((reach_left, bend_left), (reach_right, bend_right)):
        if reach < bend:
            continue
        away = (face.center() - seat).length
        where = (
            f" (its centre sits {away:.4g} mm off the path; draw it on the path)"
            if away > 1e-6
            else ""
        )
        raise PathTooTightError(
            f"The path bends at radius {bend:.4g} mm, but the profile reaches "
            f"{reach:.4g} mm towards the inside of that bend{where}, so the "
            "sweep would pass through itself. Enlarge the bend or shrink the "
            "profile."
        )


def _in_plane(direction: Vector, normal: Vector) -> Vector:
    return (direction - normal * direction.dot(normal)).normalized()


def _seat_profile(face: Face, path: Wire, normal: Vector) -> Face:
    """Carry *face* from its seat on *path* to where the pipe shell starts.

    The rigid motion takes the binormal frame (tangent, normal x tangent, normal)
    at the seat onto the same frame at the start. When the profile already sits
    at the start it is returned untouched (bit-identical, no float noise).
    """
    start, start_tangent = _start_frame(path)
    seat, seat_tangent = _seat_frame(path, face.center())
    if abs(face.normal_at().dot(seat_tangent)) < _EDGE_ON_TOLERANCE:
        raise ClosedSweepError(
            "The profile lies along the path where it meets it; draw the profile "
            "on a plane that crosses the path."
        )
    lateral = normal.cross(_in_plane(seat_tangent, normal))
    _check_bends(face, path, normal, seat, lateral)
    if (seat - start).length <= PROFILE_WIRE_TOLERANCE and (
        seat_tangent - start_tangent
    ).length <= G1_ANGLE_TOLERANCE_RAD:
        return face
    seat_plane = Plane(origin=seat, x_dir=_in_plane(seat_tangent, normal), z_dir=normal)
    start_plane = Plane(
        origin=start, x_dir=_in_plane(start_tangent, normal), z_dir=normal
    )
    return face.moved(start_plane.location * seat_plane.location.inverse())


def _pipe(section: Wire, path: Wire, normal: Vector) -> Solid:
    builder = BRepOffsetAPI_MakePipeShell(path.wrapped)
    builder.SetMode(gp_Dir(normal.X, normal.Y, normal.Z))
    builder.Add(section.wrapped, False, False)
    builder.Build()
    if not builder.IsDone() or not builder.MakeSolid():
        raise ClosedSweepError("The closed sweep could not close into a solid.")
    return Solid(builder.Shape())


def sweep_closed_profile(face: Face, path: Wire, normal: Vector) -> Solid:
    """Sweep the closed profile *face* once around the closed planar *path*.

    *normal* is the path sketch's plane normal, the fixed binormal. Each loop
    of the profile is piped separately and the holes cut from the outer pipe,
    as build123d's ``Solid.sweep`` does for a face with holes.

    Raises:
        ClosedSweepError: the profile lies along the path, the pipe shell fails,
            or the result is not one valid solid with positive volume.
        SweepSelfIntersectingError: the swept solid passes through itself.
    """
    unit = normal.normalized()
    try:
        seated = _seat_profile(face, path, unit)
        body = _pipe(seated.outer_wire(), path, unit)
        for hole in seated.inner_wires():
            body = body.cut(_pipe(hole, path, unit))
        solids = body.solids()
    except ClosedSweepError:
        raise
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ClosedSweepError(
            f"Closed sweep failed in the kernel ({type(exc).__name__}); the path "
            "may self-intersect or turn tighter than the profile can follow."
        ) from exc
    if len(solids) != 1:
        raise ClosedSweepError(
            f"Closed sweep produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    solid = solids[0]
    if not BRepCheck_Analyzer(solid.wrapped).IsValid() or solid.volume <= 0:
        raise ClosedSweepError(
            "Closed sweep produced an invalid solid; the path may turn tighter "
            "than the profile can follow, or cross itself."
        )
    check_not_self_intersecting(solid)
    return clean_shape(solid)
