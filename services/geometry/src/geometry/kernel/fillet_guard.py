"""Checks a fillet result must pass before it may replace the body.

WHY. OCCT's blend can return a VALID but WRONG solid (a cylinder hub with two
blades, its seam on one blade's root: the R1 fillet of that blade drops the
other blade, 24 746 mm^3 for 32 212, ``BRepCheck`` content), and a failed
attempt can leave a vertex tolerance of 74 mm behind, which every later
boolean then reads as real geometry. Neither is caught by validity alone.

WHAT. Two invariants of any constant-radius fillet, independent of how OCCT
built it:

* LOCALITY. A fillet of radius r only changes the body within a few r of the
  edges it rounds. Every sample point strictly inside a face of the input that
  lies farther than that from every rounded edge must still be boundary of the
  result, with the result's material on the same side: probes 1e-3 mm inside
  and outside it classify as they do in the input.
* CLOSURE. Every edge of the result bounds two faces (or is a seam or
  degenerate): ``BRepCheck`` passes an open shell.
* TOLERANCE. No vertex or edge of the result may be looser than the input's
  loosest or :data:`TOLERANCE_FLOOR_MM`, whichever is larger. A blend is fitted
  at ~1e-5 mm; 74 mm is damage.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

from collections.abc import Sequence

from build123d import Edge, Face, Solid, Vector
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_ON,
    TopAbs_OUT,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.naming import interior_points
from geometry.kernel.provenance import explore_faces
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

#: The loosest vertex/edge tolerance (mm) a fillet result may have when its
#: input was tighter: two orders above the ~3e-5 mm OCCT fits a B-spline blend
#: at, and five below the damage this exists to catch.
TOLERANCE_FLOOR_MM = 1e-3
#: Faces farther than this many radii from every filleted edge must be intact.
_REACH = 3.0


def max_tolerance(shape: BodyShape) -> float:
    """The loosest vertex or edge tolerance of *shape* (mm)."""
    analysis = ShapeAnalysis_ShapeTolerance()
    return max(
        analysis.Tolerance(shape.wrapped, 1, TopAbs_VERTEX),
        analysis.Tolerance(shape.wrapped, 1, TopAbs_EDGE),
    )


def fillet_result_ok(
    original: BodyShape,
    edges: Sequence[Edge],
    radius_mm: float,
    solids: Sequence[Solid],
    tolerance_limit: float,
) -> bool:
    """Whether *solids* (a fillet of *edges* of *original*) is valid, no
    looser than *tolerance_limit*, and leaves the far faces intact."""
    for solid in solids:
        if not BRepCheck_Analyzer(solid.wrapped).IsValid():
            return False
        if max_tolerance(solid) > tolerance_limit or _has_free_edge(solid):
            return False
    reach = _REACH * radius_mm + _PROBE_MM + KERNEL_LINEAR_TOL_MM
    near = [_box(edge.wrapped, reach) for edge in edges]
    after = [BRepClass3d_SolidClassifier(solid.wrapped) for solid in solids]
    before = BRepClass3d_SolidClassifier(original.wrapped)
    picked = _compound([edge.wrapped for edge in edges])
    for face in explore_faces(original):
        box = _box(face, 0.0)
        close = any(not box.IsOut(other) for other in near)
        as_face = Face(TopoDS.Face_s(face))
        for point in interior_points(as_face.wrapped, _SAMPLES_PER_FACE):
            if close and _distance(point, picked) <= reach:
                continue  # within the fillet's reach: it may change here
            # A probe just inside and one just outside the face: the result
            # must agree with the input at both (a solid that lost the material
            # behind a far face, or the face itself, fails one). The point ON
            # the face is not itself tested: on a B-spline face the classifier's
            # projection can call an exact surface point OUT.
            normal = as_face.normal_at(Vector(point.X(), point.Y(), point.Z()))
            for sign in (-1.0, 1.0):
                probe = Vector(point.X(), point.Y(), point.Z()) + normal * (
                    sign * _PROBE_MM
                )
                expected = _state([before], probe.to_pnt())
                if expected == TopAbs_ON:
                    continue  # too thin here to probe; the face point stands
                if _state(after, probe.to_pnt()) != expected:
                    return False
    return True


#: Sample points per face of the input (a parameter grid, interior only).
_SAMPLES_PER_FACE = 5


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


#: How far off a far face the inside/outside probes sit (mm).
_PROBE_MM = 1e-3


def _state(classifiers: Sequence[BRepClass3d_SolidClassifier], point: object) -> object:
    """``TopAbs_ON`` / ``IN`` if any solid says so (in that order), else OUT."""
    states = []
    for classifier in classifiers:
        classifier.Perform(point, KERNEL_LINEAR_TOL_MM)
        states.append(classifier.State())
    for wanted in (TopAbs_ON, TopAbs_IN):
        if wanted in states:
            return wanted
    return TopAbs_OUT


def _has_free_edge(solid: Solid) -> bool:
    """Whether *solid*'s boundary is OPEN: an edge only one face uses (not a
    seam, not degenerate). ``BRepCheck`` passes such a "solid" (measured: the
    two-blade hub whose R1 fillet dropped the whole top cap), and its volume
    and point classification are then meaningless."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    for index in range(1, ancestors.Extent() + 1):
        edge = TopoDS.Edge_s(ancestors.FindKey(index))
        faces = list(ancestors.FindFromIndex(index))
        if len(faces) >= 2 or BRep_Tool.Degenerated_s(edge):
            continue
        if not faces or not BRep_Tool.IsClosed_s(edge, TopoDS.Face_s(faces[0])):
            return True
    return False


def _box(shape: TopoDS_Shape, gap: float) -> Bnd_Box:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if gap > 0.0:
        box.Enlarge(gap)
    return box
