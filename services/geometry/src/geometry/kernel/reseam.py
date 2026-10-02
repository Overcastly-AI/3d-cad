"""Move a closed face's seam away from the edges a fillet must round.

WHY. A face on a closed surface (a cylinder, cone, sphere, torus) carries a
SEAM edge where its parameter wraps. Where the seam ends on, or runs beside, an
edge being filleted, OCCT's rolling-ball fillet fails: the blend has to cross
a vertex where a third edge meets. That is a parameterisation artefact, not
geometry. The QA impeller shows it (hard-parts re-run 2026-10-01): after the
hub 40 -> 44 edit one blade's root curve crosses the hub cylinder's seam, the
same R1 root fillet that builds with the seam anywhere else fails, and so
does a fresh re-pick. Parasolid (Fusion, SolidWorks, Onshape) has no such
seam, so the engineer never sees it.

WHAT. :func:`reseam_near` rebuilds each closed face that the fillet's edges
touch on the SAME surface turned about its own axis, so that its seam sits in
the middle of the widest angular gap between those edges, then re-adds the
face's own boundary (every edge but the old seam) and lets ``ShapeFix_Face``
add the new seam. The surface is the same point set, the boundary edges are the
same edges, so the solid is the same solid. That is checked rather than
assumed: the result must be valid (``BRepCheck``), keep its face count, and
keep its volume to 1e-9 relative, or it is discarded.

It is only a RETRY (:func:`geometry.kernel.fillet.fillet_body` calls it after
the plain fillet failed), so a body that fillets today is untouched.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

import math
from collections.abc import Sequence

from build123d import Edge, Solid, Vertex
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.Geom import Geom_ElementarySurface
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.gp import gp_Ax1
from OCP.GProp import GProp_GProps
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds, ShapeAnalysis_Surface
from OCP.ShapeBuild import ShapeBuild_ReShape
from OCP.ShapeFix import ShapeFix_Face
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import (
    TopTools_HSequenceOfShape,
    TopTools_IndexedDataMapOfShapeListOfShape,
)

from geometry.kernel.fillet_guard import TOLERANCE_FLOOR_MM, max_tolerance
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM

#: The re-seamed solid must keep its volume to this relative bound (it is the
#: same point set; anything more means the rebuild went wrong).
_VOLUME_REL_TOL = 1e-9
#: Samples per filleted edge when locating it in the face's angle.
_SAMPLES = 9


#: How many seam placements the fillet retry tries, widest gap first.
CANDIDATES = 3


def reseam_near(
    body: Solid, edges: Sequence[Edge], choice: int = 0
) -> tuple[Solid, list[Edge]] | None:
    """*body* with the seams of the closed faces next to *edges* moved away
    from them, plus *edges* on the new body; ``None`` when there is nothing to
    move or the rebuild does not check out (the caller then reports the
    original failure). *choice* picks the gap: 0 the widest between the
    face's edges, 1 the next, and so on (``None`` past the last)."""
    copier = BRepBuilderAPI_Copy(body.wrapped, True, False)
    copy = copier.Shape()
    picked = [copier.ModifiedShape(edge.wrapped) for edge in edges]
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(copy, TopAbs_EDGE, TopAbs_FACE, ancestors)

    reshape = ShapeBuild_ReShape()
    seen: list[TopoDS_Shape] = []
    for edge in picked:
        if not ancestors.Contains(edge):
            return None
        for face_shape in ancestors.FindFromKey(edge):
            if any(face_shape.IsSame(done) for done in seen):
                continue
            seen.append(face_shape)
            face = TopoDS.Face_s(face_shape)
            rebuilt = _reseamed(
                face, [e for e in picked if _on_face(e, face)], reshape, choice
            )
            if rebuilt is _NO_CHOICE:
                return None
            if rebuilt is not None:
                reshape.Replace(face, rebuilt)
    if not seen:
        return None
    result = reshape.Apply(copy)
    if result.IsSame(copy) or not BRepCheck_Analyzer(result).IsValid():
        return None
    if _face_count(result) != _face_count(copy):
        return None
    before, after = _volume(copy), _volume(result)
    if abs(after - before) > _VOLUME_REL_TOL * abs(before):
        return None
    if result.ShapeType() != TopAbs_SOLID:
        return None
    if max_tolerance(Solid(result)) > max(max_tolerance(body), TOLERANCE_FLOOR_MM):
        return None
    solid = Solid(TopoDS.Solid_s(result))
    moved = [Edge(reshape.Value(edge)) for edge in picked]
    return solid, moved


#: Returned by :func:`_reseamed` when *choice* is past the face's gaps.
_NO_CHOICE = TopoDS_Face()


def _reseamed(
    face: TopoDS_Face,
    picked: Sequence[TopoDS_Shape],
    reshape: ShapeBuild_ReShape,
    choice: int = 0,
) -> TopoDS_Face | None:
    """*face* on its surface turned so the seam is clear of *picked*, or
    ``None`` when the face has no seam or is not on a closed elementary
    surface. A closed boundary edge the old seam started on (a cylinder's end
    circle) is re-started at the new seam, recorded in *reshape* so the faces
    that share it (the end caps) take the same edge."""
    seams = _seam_edges(face)
    if not seams:
        return None
    location = TopLoc_Location()
    surface = BRep_Tool.Surface_s(face, location)
    if not isinstance(surface, Geom_ElementarySurface) or not surface.IsUPeriodic():
        return None
    # Clear of EVERY edge on the face, not only the picked ones: a seam turned
    # into another blade's root moves the defect there instead of removing it.
    angles = _picked_angles(surface, [*picked, *_open_edges(face, seams)], location)
    if not angles:
        return None
    middles = _gap_middles(angles, surface.UPeriod())
    if choice >= len(middles):
        return _NO_CHOICE
    turn = middles[choice]
    turned = surface.Copy()
    position = turned.Position()
    turned.Rotate(gp_Ax1(position.Location(), position.Direction()), turn)

    seam_vertices = [v for seam in seams for v in Edge(seam).vertices()]
    loose = TopTools_HSequenceOfShape()
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    done: list[TopoDS_Shape] = []
    while explorer.More():
        edge = explorer.Current()
        explorer.Next()
        if any(edge.IsSame(seam) for seam in seams) or any(
            edge.IsSame(d) for d in done
        ):
            continue
        done.append(edge)
        restarted = _restart(edge, seam_vertices, surface, location, turn)
        if restarted is False:
            return None
        if restarted is not None:
            reshape.Replace(edge.Oriented(TopAbs_FORWARD), restarted)
            edge = restarted
        loose.Append(edge)
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(
        loose, KERNEL_LINEAR_TOL_MM, True, wires
    )

    builder = BRep_Builder()
    new_face = TopoDS_Face()
    builder.MakeFace(new_face, turned, location, BRep_Tool.Tolerance_s(face))
    for index in range(1, wires.Length() + 1):
        builder.Add(new_face, wires.Value(index))
    fixer = ShapeFix_Face(new_face)
    fixer.SetContext(reshape)
    fixer.FixMissingSeamMode = 1
    fixer.FixOrientationMode = 1
    fixer.Perform()
    fixed = fixer.Face()
    fixed.Orientation(face.Orientation())
    if not _seam_edges(fixed):
        return None
    return fixed


def _restart(
    edge: TopoDS_Shape,
    seam_vertices: Sequence[Vertex],
    surface: Geom_ElementarySurface,
    location: TopLoc_Location,
    turn: float,
) -> TopoDS_Shape | None | bool:
    """*edge* re-started where the new seam crosses it, if it is a CLOSED
    edge starting on the old seam (an end circle); ``None`` if it needs
    nothing, ``False`` if it needs it and cannot have it."""
    as_edge = TopoDS.Edge_s(edge)
    first, last = TopExp.FirstVertex_s(as_edge), TopExp.LastVertex_s(as_edge)
    if not first.IsSame(last):
        # An open edge ending on the old seam keeps that vertex as an ordinary
        # one (the pieces of a root curve the seam cut).
        return None
    if not any(v.wrapped.IsSame(first) for v in seam_vertices):
        return None
    curve = BRep_Tool.Curve_s(as_edge, 0.0, 0.0)
    start = BRep_Tool.Parameter_s(first, as_edge)
    if curve is None or not curve.IsPeriodic():
        return False
    place = location.Transformation()
    vertex_point = BRep_Tool.Pnt_s(first).Transformed(place.Inverted())
    v = ShapeAnalysis_Surface(surface).ValueOfUV(vertex_point, KERNEL_LINEAR_TOL_MM).Y()
    target = surface.Value(turn, v).Transformed(place)
    projector = GeomAPI_ProjectPointOnCurve(target, curve)
    if projector.NbPoints() < 1 or projector.LowerDistance() > KERNEL_LINEAR_TOL_MM:
        return False
    t = projector.LowerDistanceParameter()
    period = curve.Period()
    t = start + math.fmod(t - start + 2 * period, period)
    maker = BRepBuilderAPI_MakeEdge(curve, t, t + period)
    if not maker.IsDone():
        return False
    return maker.Edge()


def _open_edges(face: TopoDS_Face, seams: Sequence[TopoDS_Shape]) -> list[TopoDS_Shape]:
    """The face's boundary edges that are neither its seam nor a closed loop
    (an end circle covers every angle and constrains nothing)."""
    out: list[TopoDS_Shape] = []
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        explorer.Next()
        if any(edge.IsSame(s) for s in [*seams, *out]):
            continue
        if TopExp.FirstVertex_s(edge).IsSame(TopExp.LastVertex_s(edge)):
            continue
        out.append(edge)
    return out


def _seam_edges(face: TopoDS_Face) -> list[TopoDS_Shape]:
    out: list[TopoDS_Shape] = []
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        if BRep_Tool.IsClosed_s(edge, face) and not any(edge.IsSame(e) for e in out):
            out.append(edge)
        explorer.Next()
    return out


def _on_face(edge: TopoDS_Shape, face: TopoDS_Face) -> bool:
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    while explorer.More():
        if explorer.Current().IsSame(edge):
            return True
        explorer.Next()
    return False


def _picked_angles(
    surface: Geom_ElementarySurface,
    picked: Sequence[TopoDS_Shape],
    location: TopLoc_Location,
) -> list[float]:
    """The U parameter (an angle) of samples along every picked edge."""
    analysis = ShapeAnalysis_Surface(surface)
    inverse = location.Transformation().Inverted()
    period = surface.UPeriod()
    out: list[float] = []
    for shape in picked:
        edge = Edge(TopoDS.Edge_s(shape))
        for i in range(_SAMPLES):
            point = (edge @ (i / (_SAMPLES - 1))).to_pnt().Transformed(inverse)
            u = analysis.ValueOfUV(point, KERNEL_LINEAR_TOL_MM).X()
            out.append(u % period)
    return out


def _gap_middles(angles: list[float], period: float) -> list[float]:
    """The middles of the gaps between *angles*, widest first (ties by
    angle, so the order is a pure function of the geometry)."""
    ordered = sorted(set(angles))
    if len(ordered) == 1:
        return [math.fmod(ordered[0] + period / 2.0, period)]
    gaps = [
        ((ordered[(i + 1) % len(ordered)] - a) % period, a)
        for i, a in enumerate(ordered)
    ]
    gaps.sort(key=lambda gap: (-round(gap[0], 9), gap[1]))
    return [math.fmod(a + width / 2.0, period) for width, a in gaps]


def _widest_gap_middle(angles: list[float], period: float) -> float:
    """The middle of the widest gap between *angles* around the period.

    Repeated angles (two edges sharing an end) are one angle: counted twice
    they made a zero gap, which read as a whole period and put the seam
    half a turn round, on another blade's root."""
    ordered = sorted(set(angles))
    if len(ordered) == 1:
        return math.fmod(ordered[0] + period / 2.0, period)
    best, middle = -1.0, 0.0
    for index, angle in enumerate(ordered):
        following = ordered[(index + 1) % len(ordered)]
        gap = (following - angle) % period
        if gap > best:
            best, middle = gap, angle + gap / 2.0
    return math.fmod(middle, period)


def _face_count(shape: TopoDS_Shape) -> int:
    count, explorer = 0, TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()
