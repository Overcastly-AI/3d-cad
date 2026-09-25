"""Tighten the loose edges a shell leaves around its offset spline walls.

GEOMETRY-QA 2026-09-25 F1. ``BRepOffsetAPI_MakeThickSolid`` (the shell) offsets
a spline wall into a ``Geom_OffsetSurface``. It meets its neighbouring planes
along edges whose 3D curves it FITS, loosely:
- 1.0e-5 mm on the golden ``shell-spline-prism-30x10-t1``;
- 2.2e-4 mm on QA's case 2;
- 2.2e-3 mm on the shelled spline-slot disc.
The latter two are above the kernel's 1e-4 mm linear tolerance. On the open
rim (the plane the removed face leaves behind), the rim face's boundary follows
that loose fit. On case 2 the rim encloses 7.3e-3 mm^2 too little, the volume
reads 0.023 mm^3 low, and a STEP re-import (whose reader re-derives the rim's
boundary) moves it by as much.

The exact edge is known. Where the wall's face is bounded by isolines (every
shell of an extrude), each such edge IS an isoline of the offset surface, and
the rectangle's corners are the exact corners (measured: within 1e-14 of the
intersection with the side planes). :func:`tighten_offset_edges` rebuilds each
selected edge on its isoline:
- its pcurve on the wall becomes the exact isoline, a ``Geom2d_Line`` over the
  rectangle's side;
- its 3D curve is fitted to that isoline to 1e-9 mm (``Approx_CurveOnSurface``);
- its pcurves on the neighbouring planes are that curve's projection;
- its vertices are moved to the curve's ends.

Which edges: every loose edge of the wall that lies on the plane of an OPENED
face (the rim), and any other loose edge above the kernel tolerance.
Re-fitting the golden's and case 2's CAVITY-FLOOR edges (9.2e-6 and 3.6e-6,
inside the kernel tolerance) made case 2's floor enclose 3.4e-6 mm^2 more than
before. Its reading moved from -7.9e-8 to +3.4e-6 against the truth, so those
edges are left as the shell made them. Measured, rim edges only:

| Body | Volume vs truth | STEP round trip |
|---|---|---|
| the golden | -1.4e-8 (was +1.85e-7) | -1.3e-8 (was -3.2e-7) |
| case 2 | +2.1e-7 (was -2.4e-2) | +8.1e-7 (was +2.3e-2) |
| shelled disc | no truth | -1.6e-10 (was 2.8e-2) |

Rim areas are within 6e-11 of the truth.

An edge is only rebuilt when every step succeeds: the wall is an isoline
rectangle, the edge's pcurve is one of its sides, every other face on the edge
is a plane, and the fit meets 10x its target. Otherwise the edge is left alone,
so this can only tighten a shell, never break one. The caller validates the
result as before.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from collections.abc import Sequence

from build123d import Face, Solid
from OCP.Approx import Approx_CurveOnSurface
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepLib import BRepLib
from OCP.Geom2d import Geom2d_Line
from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Shape, GeomAbs_SurfaceType
from OCP.GeomAdaptor import GeomAdaptor_Surface
from OCP.GeomProjLib import GeomProjLib
from OCP.gp import gp_Dir2d, gp_Pln, gp_Pnt2d
from OCP.ShapeFix import ShapeFix_ShapeTolerance
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Face
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.properties import isoline_rectangle

#: An edge looser than this (mm) is a candidate: the shell's exact edges carry
#: 1e-7.
LOOSE_EDGE_TOL_MM = 1e-6

#: The kernel's linear tolerance (1e-7 m, in mm). A loose edge off the rim is
#: rebuilt only above it.
KERNEL_TOL_MM = 1e-4

#: Fit tolerance (mm) for the rebuilt 3D curve, and the tolerance it is given.
#: Measured: 4.9e-10 max error on every edge of the three bodies above.
FIT_TOL_MM = 1e-9

#: A fit worse than this multiple of FIT_TOL_MM is refused (the edge is kept).
_FIT_SLACK = 10.0
_FIT_SEGMENTS = 400
_FIT_DEGREE = 8
_ISOLINE_SAMPLES = 32
_ISOLINE_TOL = 1e-9
_PLANE_TOL_MM = 1e-7
_PARALLEL_TOL = 1e-12


def _same_plane(plane: gp_Pln, other: gp_Pln) -> bool:
    n, m = plane.Axis().Direction(), other.Axis().Direction()
    if abs(abs(n.Dot(m)) - 1.0) > _PARALLEL_TOL:
        return False
    return plane.Distance(other.Location()) <= _PLANE_TOL_MM


def _on_opened_plane(face: TopoDS_Face, opened: Sequence[gp_Pln]) -> bool:
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return False
    plane = adaptor.Plane()
    return any(_same_plane(plane, o) for o in opened)


def _rebuild_on_isoline(
    builder: BRep_Builder,
    edge: object,
    wall: Face,
    rectangle: tuple[float, float, float, float],
    others: list[TopoDS_Face],
) -> bool:
    """Rebuild *edge* (a side of *wall*'s isoline rectangle) exactly; False and
    untouched when it is not such a side or the fit misses its target."""
    u0, u1, v0, v1 = rectangle
    pcurve = BRepAdaptor_Curve2d(edge, wall.wrapped)
    first, last = pcurve.FirstParameter(), pcurve.LastParameter()
    points = [
        pcurve.Value(first + (last - first) * k / _ISOLINE_SAMPLES)
        for k in range(_ISOLINE_SAMPLES + 1)
    ]
    us, vs = [p.X() for p in points], [p.Y() for p in points]
    if max(vs) - min(vs) <= _ISOLINE_TOL * max(1.0, abs(vs[0])):
        forward = us[-1] > us[0]
        start = gp_Pnt2d(u0 if forward else u1, vs[0])
        direction = gp_Dir2d(1.0 if forward else -1.0, 0.0)
        length = u1 - u0
    elif max(us) - min(us) <= _ISOLINE_TOL * max(1.0, abs(us[0])):
        forward = vs[-1] > vs[0]
        start = gp_Pnt2d(us[0], v0 if forward else v1)
        direction = gp_Dir2d(0.0, 1.0 if forward else -1.0)
        length = v1 - v0
    else:
        return False
    isoline = Geom2d_Line(start, direction)
    surface = BRep_Tool.Surface_s(wall.wrapped)
    fit = Approx_CurveOnSurface(
        Geom2dAdaptor_Curve(isoline, 0.0, length),
        GeomAdaptor_Surface(surface),
        0.0,
        length,
        FIT_TOL_MM,
    )
    fit.Perform(_FIT_SEGMENTS, _FIT_DEGREE, GeomAbs_Shape.GeomAbs_C2, True, False)
    if (
        not fit.IsDone()
        or not fit.HasResult()
        or fit.MaxError3d() > _FIT_SLACK * FIT_TOL_MM
    ):
        return False
    curve = fit.Curve3d()
    start_vertex, end_vertex = TopExp.FirstVertex_s(edge), TopExp.LastVertex_s(edge)
    builder.UpdateEdge(edge, curve, FIT_TOL_MM)
    builder.UpdateEdge(edge, isoline, wall.wrapped, FIT_TOL_MM)
    for other in others:
        location = TopLoc_Location()
        plane = BRep_Tool.Surface_s(other, location)
        local = (
            curve
            if location.IsIdentity()
            else curve.Transformed(location.Transformation().Inverted())
        )
        builder.UpdateEdge(
            edge, GeomProjLib.Curve2d_s(local, 0.0, length, plane), other, FIT_TOL_MM
        )
    builder.Range(edge, 0.0, length)
    tolerance = ShapeFix_ShapeTolerance()
    for vertex, parameter in ((start_vertex, 0.0), (end_vertex, length)):
        builder.UpdateVertex(vertex, curve.Value(parameter), FIT_TOL_MM)
        builder.UpdateVertex(vertex, parameter, edge, FIT_TOL_MM)
        tolerance.SetTolerance(vertex, FIT_TOL_MM)
    tolerance.SetTolerance(edge, FIT_TOL_MM)
    builder.SameRange(edge, True)
    BRepLib.SameParameter_s(edge, FIT_TOL_MM, True)
    return True


def tighten_offset_edges(solid: Solid, opened_faces: Sequence[Face]) -> Solid:
    """*solid* with its offset walls' loose edges rebuilt (module docstring).

    *opened_faces* are the faces the shell removed; the rim lies on their
    planes. Returns *solid* itself when nothing needs rebuilding (every body
    without a loose offset-wall edge, which is every shell of planes and
    quadrics), else a rebuilt copy.
    """
    candidates = [
        face
        for face in solid.faces()
        if BRepAdaptor_Surface(face.wrapped).GetType()
        == GeomAbs_SurfaceType.GeomAbs_OffsetSurface
        and any(
            BRep_Tool.Tolerance_s(e.wrapped) > LOOSE_EDGE_TOL_MM for e in face.edges()
        )
    ]
    if not candidates:
        return solid
    opened = [
        BRepAdaptor_Surface(f.wrapped).Plane()
        for f in opened_faces
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_SurfaceType.GeomAbs_Plane
    ]
    copy = Solid(BRepBuilderAPI_Copy(solid.wrapped).Shape())
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(copy.wrapped, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    builder = BRep_Builder()
    rebuilt = 0
    for wall in copy.faces():
        if (
            BRepAdaptor_Surface(wall.wrapped).GetType()
            != GeomAbs_SurfaceType.GeomAbs_OffsetSurface
        ):
            continue
        rectangle = isoline_rectangle(wall)
        if rectangle is None:
            continue
        for edge in wall.edges():
            tolerance = BRep_Tool.Tolerance_s(edge.wrapped)
            if tolerance <= LOOSE_EDGE_TOL_MM:
                continue
            others = [
                TopoDS.Face_s(f)
                for f in edge_faces.FindFromKey(edge.wrapped)
                if not f.IsSame(wall.wrapped)
            ]
            if not others or any(
                BRepAdaptor_Surface(o).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane
                for o in others
            ):
                continue
            on_rim = all(_on_opened_plane(o, opened) for o in others)
            if not on_rim and tolerance <= KERNEL_TOL_MM:
                continue
            if _rebuild_on_isoline(builder, edge.wrapped, wall, rectangle, others):
                rebuilt += 1
    if not rebuilt:
        return solid
    BRepLib.UpdateTolerances_s(copy.wrapped, False)
    return copy
