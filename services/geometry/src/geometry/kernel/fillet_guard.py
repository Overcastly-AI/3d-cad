"""Checks a fillet result must pass before it may replace the body.

WHY. OCCT's blend can return a VALID but WRONG solid (a cylinder hub with two
blades, its seam on one blade's root: the R1 fillet of that blade drops the
hub's top cap, 24 746 mm^3 for 32 212, ``BRepCheck`` content), and a failed
attempt can leave a vertex tolerance of 74 mm behind, which every later
boolean then reads as real geometry. Neither is caught by validity alone.

WHAT. Three invariants of any constant-radius fillet, independent of how OCCT
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
* CLOSURE. Every edge of the result bounds two faces (or is a seam or
  degenerate): ``BRepCheck`` passes an open shell.
* TOLERANCE. No vertex or edge of the result may be looser than the input's
  loosest, r/100, or :data:`TOLERANCE_FLOOR_MM`, whichever is largest.
  Correct blends on lofted faces measure 3-5e-3 mm; the damage this exists to
  catch measured 74 mm.

A failed check is reported as what it found (:func:`fillet_problem`), never
as a guess about the radius.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from collections.abc import Sequence

from build123d import Edge, Solid
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

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
    return max(input_tolerance, radius_mm / 100.0, TOLERANCE_FLOOR_MM)


def fillet_problem(
    work: BodyShape,
    edges: Sequence[Edge],
    radius_mm: float,
    solids: Sequence[Solid],
    input_tolerance: float,
) -> str | None:
    """What is wrong with *solids*, a fillet of *edges* of *work* (the copy
    the fillet ran on), or ``None`` when it passes every check."""
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
    for solid in solids:
        for face in explore_faces(solid):
            kept.Add(face)
            on_surface.setdefault(_surface_of(face), []).append(face)
    reach = _REACH * radius_mm + KERNEL_LINEAR_TOL_MM
    near = [_box(edge.wrapped, reach) for edge in edges]
    picked = _compound([edge.wrapped for edge in edges])
    budget = _MAX_SAMPLES
    for face in explore_faces(work):
        if kept.Contains(face):
            continue  # the very same face: untouched
        close = any(not _box(face, 0.0).IsOut(other) for other in near)
        if not close:
            return (
                "a face farther than the fillet can reach is missing or "
                "changed in the result"
            )
        if budget <= 0:
            continue
        candidates = on_surface.get(_surface_of(face), [])
        for point in interior_points(
            TopoDS.Face_s(face), _SAMPLES_PER_FACE, spread=True
        ):
            if budget <= 0:
                break
            if _distance(point, picked) <= reach:
                continue  # within the fillet's reach: it may change here
            budget -= 1
            if not any(_holds(c, face, point) for c in candidates):
                return (
                    "the result lost part of a face beyond the fillet's reach "
                    "(material removed or added away from the rounded edges)"
                )
    return None


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
