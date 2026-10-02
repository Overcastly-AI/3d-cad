"""Checks a fillet result must pass before it may replace the body.

WHY. OCCT's blend can return a VALID but WRONG solid (a cylinder hub with two
blades, its seam on one blade's root: the R1 fillet of that blade drops the
hub's top cap, 24 746 mm^3 for 32 212, ``BRepCheck`` content), and a failed
attempt can leave a vertex tolerance of 74 mm behind, which every later
boolean then reads as real geometry. Neither is caught by validity alone.

WHAT. Four invariants of any constant-radius fillet, independent of how OCCT
built it, each checked in time linear in the body (no ray casting: a guard
that classified points against the whole solid cost 127 s on a 906-face
plate, past the gateway's budget):

* LOCALITY. A fillet of radius r only changes the body within a few r of the
  edges it rounds. A face of the input that is still a face of the result (the
  same OCCT face, which is what ``BRepFilletAPI`` keeps for every face it did
  not touch) is intact. Any other face of the input is checked at sample
  points spread over it and farther than :data:`_REACH` r from every rounded
  edge: each must lie inside a face of the result on the SAME surface with
  the same orientation, so the face is still there and the material is still
  on its side. A face wholly that far away and not kept is a wrong body.
* COMPLETENESS. Every picked edge was rounded: its midpoint is off the
  result's boundary (OCCT can return a closed body that skipped a blade's
  root, 43 faces where 45 are right).
* CLOSURE. Every edge of the result bounds two faces (or is a seam or
  degenerate): ``BRepCheck`` passes an open shell.
* TOLERANCE. No vertex or edge of the result may be looser than the input's
  loosest, r/100 (at most 0.1 mm), or :data:`TOLERANCE_FLOOR_MM`, whichever
  is largest.
  Correct blends on lofted faces measure 3-5e-3 mm; the damage this exists to
  catch measured 74 mm.

A failed check is reported as what it found (:func:`fillet_problem`), never
as a guess about the radius.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

import math
import tempfile
from collections.abc import Sequence
from pathlib import Path

from build123d import Edge, Face, Solid, Vector
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

from geometry.kernel.export import export_step_bytes
from geometry.kernel.naming import interior_points
from geometry.kernel.provenance import explore_faces
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

#: The tolerance (mm) any fillet result may reach, whatever its input: above
#: the 3-5e-3 mm OCCT fits correct blends on lofted faces at, and four orders
#: below the 74 mm damage this exists to catch.
TOLERANCE_FLOOR_MM = 1e-2
#: Sample points farther than this many radii from every rounded edge must be
#: unchanged.
_REACH = 3.0
#: Sample points per changed face, spread over it.
_SAMPLES_PER_FACE = 5
#: At most this many sample points in all (each costs a distance query and a
#: face classification, so the check stays bounded on a big part).
_MAX_SAMPLES = 64


def max_tolerance(shape: BodyShape) -> float:
    """The loosest vertex or edge tolerance of *shape* (mm)."""
    analysis = ShapeAnalysis_ShapeTolerance()
    return max(
        analysis.Tolerance(shape.wrapped, 1, TopAbs_VERTEX),
        analysis.Tolerance(shape.wrapped, 1, TopAbs_EDGE),
    )


def tolerance_ceiling(input_tolerance: float, radius_mm: float) -> float:
    """The loosest tolerance a fillet of radius *radius_mm* may produce on a
    body whose loosest is *input_tolerance*."""
    return max(input_tolerance, min(radius_mm / 100.0, 0.1), TOLERANCE_FLOOR_MM)


def fillet_problem(
    work: BodyShape,
    edges: Sequence[Edge],
    radius_mm: float,
    solids: Sequence[Solid],
    input_tolerance: float,
    *,
    reseamed: bool = False,
) -> str | None:
    """What is wrong with *solids*, a fillet of *edges* of *work* (the copy
    the fillet ran on), or ``None`` when it passes every check.

    *reseamed* marks a result built on a re-seamed copy: each changed face on
    a closed surface must then also survive a STEP write and read as the same
    face. OCCT can blend a re-seamed cylinder into a face that is right in
    memory but that STEP reads back as two (the QA impeller with the seam at
    228 deg: 2332.94 mm^2 read as 2394.61 + 61.67), so the export would be
    wrong while every in-memory check passes."""
    ceiling = tolerance_ceiling(input_tolerance, radius_mm)
    for solid in solids:
        loosest = max_tolerance(solid)
        if loosest > ceiling:
            return (
                f"the result has a vertex or edge tolerance of {loosest:.3g} mm, "
                f"above the {ceiling:.3g} mm a fillet may leave"
            )
        if _has_free_edge(solid):
            return "the result's boundary is open (an edge bounds only one face)"
    kept = TopTools_IndexedMapOfShape()
    on_surface: dict[tuple[object, tuple[float, ...]], list[TopoDS_Shape]] = {}
    result_faces: list[tuple[TopoDS_Shape, Bnd_Box]] = []
    for solid in solids:
        for face in explore_faces(solid):
            kept.Add(face)
            on_surface.setdefault(_surface_of(face), []).append(face)
            result_faces.append((face, _box(face, 0.0)))
    unrounded = _unrounded(work, edges, result_faces)
    if unrounded:
        return (
            f"{unrounded} of the {len(edges)} picked edges are still sharp in "
            "the result (the fillet skipped them)"
        )
    if reseamed and not all(_step_keeps(face) for face in _new_closed(work, solids)):
        return "a re-seamed face would not survive a STEP export unchanged"
    reach = _REACH * radius_mm + KERNEL_LINEAR_TOL_MM
    near = [_box(edge.wrapped, reach) for edge in edges]
    picked = _compound([edge.wrapped for edge in edges])
    changed: list[TopoDS_Shape] = []
    for face in explore_faces(work):
        if kept.Contains(face):
            continue  # the very same face: untouched
        if all(_box(face, 0.0).IsOut(other) for other in near):
            return (
                "a face farther than the fillet can reach is missing or "
                "changed in the result"
            )
        changed.append(face)
    # The sample budget is shared out over every changed face, so a defect on
    # the last of them is looked at as surely as one on the first.
    each = max(1, min(_SAMPLES_PER_FACE, _MAX_SAMPLES // max(1, len(changed))))
    for face in changed:
        candidates = on_surface.get(_surface_of(face), [])
        for point in interior_points(TopoDS.Face_s(face), each, spread=True):
            if _distance(point, picked) <= reach:
                continue  # within the fillet's reach: it may change here
            if not any(_holds(c, face, point) for c in candidates):
                return (
                    "the result lost part of a face beyond the fillet's reach "
                    "(material removed or added away from the rounded edges)"
                )
    return None


#: How far (mm) a picked edge's midpoint must sit off the result's boundary to
#: count as rounded. A sharp edge the fillet skipped is ON the boundary (within
#: tolerance); a rounded one is r (1/sin(phi/2) - 1) away for a dihedral phi,
#: 0.41 r at 90 deg, so this refuses nothing short of a ~175 deg edge at R1.
_ROUNDED_MM = 1e-3


def _unrounded(
    work: BodyShape,
    edges: Sequence[Edge],
    result_faces: Sequence[tuple[TopoDS_Shape, Bnd_Box]],
) -> int:
    """How many of *edges* the result still has as a corner: a fillet that
    reports success must have rounded every edge it was given. A seam, or an
    edge between tangent faces, has no corner to round (OCCT passes over it,
    rightly) and is not counted.

    Skipped means BOTH faces of the edge still reach its midpoint: on the
    boundary is not enough, because a neighbouring blend can pass through
    it. A 2 mm shelled plate's 4 mm outer chamfer (x + y = 76) runs exactly
    through the inner corner (38, 38), so the inner edge, bevelled, has its
    midpoint on the outer bevel face, but on neither wall any more."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(work.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    count = 0
    for edge in edges:
        if _smooth(edge, ancestors):
            continue
        middle = edge @ 0.5
        midpoint = middle.to_pnt()
        probe = Bnd_Box()
        probe.Add(midpoint)
        probe.Enlarge(_ROUNDED_MM)
        touching = [
            Face(TopoDS.Face_s(face))
            for face, box in result_faces
            if not box.IsOut(probe) and _distance(midpoint, face) <= _ROUNDED_MM
        ]
        if not touching:
            continue
        users = (
            ancestors.FindFromKey(edge.wrapped)
            if ancestors.Contains(edge.wrapped)
            else None
        )
        if users is None or users.Size() != 2:
            count += 1  # no two sides to tell apart: on the boundary is a corner
            continue
        if all(
            any(_same_side(own, middle, face) for face in touching)
            for own in (Face(TopoDS.Face_s(side)) for side in users)
        ):
            count += 1
    return count


#: How closely (radians) a result face's normal must match an input face's at
#: a picked edge's midpoint to be that face still reaching it.
_SAME_NORMAL_RAD = 1e-3


def _same_side(own: Face, point: Vector, face: Face) -> bool:
    """Whether *face* (touching *point*) faces the way *own* does there. A
    normal that cannot be had counts as the same side: the edge is then
    taken as skipped and the fillet refused, never shipped unverified."""
    try:
        angle = own.normal_at(point).get_angle(face.normal_at(point))
    except Exception:  # OCCT projection failures are not a stable taxonomy
        return True
    return angle < math.degrees(_SAME_NORMAL_RAD)


def _new_closed(work: BodyShape, solids: Sequence[Solid]) -> list[TopoDS_Shape]:
    """The result's faces that are not *work*'s and lie on a closed surface
    (they carry a seam edge)."""
    before = TopTools_IndexedMapOfShape()
    for face in explore_faces(work):
        before.Add(face)
    out: list[TopoDS_Shape] = []
    for solid in solids:
        for face in explore_faces(solid):
            if before.Contains(face):
                continue
            explorer = TopExp_Explorer(face, TopAbs_EDGE)
            while explorer.More():
                if BRep_Tool.IsClosed_s(
                    TopoDS.Edge_s(explorer.Current()), TopoDS.Face_s(face)
                ):
                    out.append(face)
                    break
                explorer.Next()
    return out


def _step_keeps(face: TopoDS_Shape) -> bool:
    """Whether *face*, exported alone through the product's own STEP writer
    and read back, is one face of the same area. A clean blend face reads back
    within ~2e-9 relative; the defect reads back as two faces, 5 % larger."""
    before = _area(face)
    data = export_step_bytes(Face(TopoDS.Face_s(face)))  # pyright: ignore[reportArgumentType]
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "face.step"
        path.write_bytes(data)
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            return False
        reader.TransferRoots()
        back = reader.OneShape()
    faces: list[TopoDS_Shape] = []
    explorer = TopExp_Explorer(back, TopAbs_FACE)
    while not back.IsNull() and explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    return len(faces) == 1 and abs(_area(faces[0]) - before) <= _STEP_AREA_REL * before


#: How far (relative) a face's area may move across a STEP write and read.
_STEP_AREA_REL = 1e-6


def _area(face: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


#: Faces meeting at less than this angle (radians) across an edge are tangent.
_SMOOTH_RAD = 1e-3


def _smooth(edge: Edge, ancestors: TopTools_IndexedDataMapOfShapeListOfShape) -> bool:
    """Whether *edge* is a seam or joins two tangent faces (no corner)."""
    if not ancestors.Contains(edge.wrapped):
        return False
    users = ancestors.FindFromKey(edge.wrapped)
    if users.Size() != 2:
        return users.Size() < 2
    first, second = (Face(TopoDS.Face_s(face)) for face in users)
    if first.wrapped.IsSame(second.wrapped):
        return True  # a seam: the same face on both sides
    point = edge @ 0.5
    return first.normal_at(point).get_angle(second.normal_at(point)) < math.degrees(
        _SMOOTH_RAD
    )


def _surface_of(face: TopoDS_Shape) -> tuple[object, tuple[float, ...]]:
    """The face's supporting surface object and location: a fillet re-bounds a
    face it touches but keeps its surface."""
    location = TopLoc_Location()
    surface = BRep_Tool.Surface_s(TopoDS.Face_s(face), location)
    matrix = location.Transformation()
    return (
        surface,  # compared as an OCCT handle: the same object, not equal values
        tuple(matrix.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4)),
    )


def _holds(candidate: TopoDS_Shape, original: TopoDS_Shape, point: object) -> bool:
    """Whether *candidate* (same surface as *original*) contains *point* and
    keeps the material on the same side (the same orientation)."""
    if candidate.Orientation() != original.Orientation():
        return False
    state = BRepClass_FaceClassifier(
        TopoDS.Face_s(candidate), point, KERNEL_LINEAR_TOL_MM
    ).State()
    return state in (TopAbs_IN, TopAbs_ON)


def _has_free_edge(solid: Solid) -> bool:
    """Whether *solid*'s boundary is OPEN: an edge only one face uses (not a
    seam, not degenerate). ``BRepCheck`` passes such a "solid"."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    for index in range(1, ancestors.Extent() + 1):
        users = ancestors.FindFromIndex(index)
        if users.Size() >= 2:
            continue  # the common case, decided without leaving C++
        edge = TopoDS.Edge_s(ancestors.FindKey(index))
        if BRep_Tool.Degenerated_s(edge):
            continue
        if users.Size() == 0 or not BRep_Tool.IsClosed_s(
            edge, TopoDS.Face_s(users.First())
        ):
            return True
    return False


def _compound(shapes: Sequence[TopoDS_Shape]) -> TopoDS_Compound:
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _distance(point: object, shape: TopoDS_Shape) -> float:
    vertex = BRepBuilderAPI_MakeVertex(point).Vertex()
    extrema = BRepExtrema_DistShapeShape(vertex, shape)
    return extrema.Value() if extrema.IsDone() else 0.0


def _box(shape: TopoDS_Shape, gap: float) -> Bnd_Box:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if gap > 0.0:
        box.Enlarge(gap)
    return box
