"""Split the PINCHED faces OCCT's Arc hollow leaves when a cavity touches
itself at a point (SHELL-HEAL-NONDETERMINISM, 2026-10-01).

THE CASE. A rod r10 x 40 with a through cross-bore r6, sealed at t = 2. The
rod's offset (r8) and the bore's (r8) are equal cylinders meeting at right
angles, so the cavity (the r8 rod minus the r8 bore) is two pieces, above and
below the bore, that touch at the two points (0, +-8, 0). The right shell has
three shells: the outside and one per cavity piece. Hand-checked:
10411.407994 - (pi 64 x 36 - 16/3 x 8^3) = 5903.845187 mm^3.

WHERE THE ADDRESS DEPENDENCE ENTERS. ``BRepOffset_MakeOffset::BuildOffsetByArc``
(OCCT 7.9.3) intersects the offset faces in the iteration order of ``MapSF``, a
hash map keyed by the input's TShape addresses (kernel/shell.py, module
docstring). On this body that order decides how the two tangent ellipses are
split where they cross. Measured over 40 fresh copies of the body in one
process: 19 built the cavity as 6 faces that ShapeFix splits into two shells
(valid, 11 faces), 21 built it as 4 faces in which the bore's offset is ONE face
spanning both lobes, its single wire running through each pinch point twice,
and the rod's offset is one face spanning both pieces. That body is
``BRepCheck``-invalid (``UnorientableShape``), ``ShapeFix_Shape`` cannot repair
it, and the shell was refused: 31 of 60 rebuilds over 3 processes. Both
variants hold the right material (5903.8451865 mm^3 to 1e-12). Which one a
process gets depends on where malloc put the faces, so the outcome was fixed
within a process and differed between processes.

The order cannot be fixed from outside (the hash is of the pointer), so the
heal is made robust to the variant instead: :func:`split_pinched_faces`
rebuilds each face of an invalid result from its own edges with
``BOPAlgo_BuilderFace``, the face splitter OCCT's booleans use. A face whose
edges bound more than one region is replaced by those regions. On the bad
variant that gives exactly the good variant's faces (the bore's 512 mm^2 face
becomes 128 + 128 + 256, the rod's 1297.557 becomes 2 x 648.779), and
:func:`~geometry.kernel.healing.conform_solid` then sorts them into three
valid shells. A face is one connected region by definition, so splitting one
that is not cannot change the material, and ``conform_solid`` still refuses a
heal that moves the volume by more than 1e-9 mm^3. The shell definition check
runs on the result as on every other.

What still moves with the layout: OCCT orients each crossing ellipse either
way. On one layout one ellipse's arc is split at the curve's own parameter
origin, (-8, 0, 8), so that result has 21 edges and 13 vertices where the healed
one has 20 and 12. Measured over 60 fresh copies: every one builds, with 3
shells, 11 faces and 5903.8451865 mm^3 (``volume_properties``) to 1e-9.
``ShapeUpgrade_UnifySameDomain`` does not merge the two arcs.

A valid solid is returned unchanged (identity), so every body that was valid
before, every golden included, takes the byte-identical path.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from build123d import Solid
from OCP.BOPAlgo import BOPAlgo_BuilderFace
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepTools import BRepTools_ReShape
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Face
from OCP.TopTools import TopTools_ListOfShape


def split_pinched_faces(solid: Solid) -> Solid:
    """*solid* with every face that bounds more than one region replaced by
    those regions (module docstring). A valid *solid*, or one with no such
    face, is returned as is."""
    if BRepCheck_Analyzer(solid.wrapped).IsValid():
        return solid
    reshape = BRepTools_ReShape()
    split = False
    faces = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
    while faces.More():
        face = TopoDS.Face_s(faces.Current())
        regions = _regions(face)
        if len(regions) > 1:
            builder = BRep_Builder()
            pieces = TopoDS_Compound()
            builder.MakeCompound(pieces)
            for region in regions:
                builder.Add(pieces, region.Oriented(face.Orientation()))
            reshape.Replace(face, pieces)
            split = True
        faces.Next()
    if not split:
        return solid
    rebuilt = reshape.Apply(solid.wrapped)
    if rebuilt.IsNull() or rebuilt.ShapeType() != TopAbs_SOLID:
        return solid
    return Solid(TopoDS.Solid_s(rebuilt))


def _regions(face: TopoDS_Face) -> list[TopoDS_Face]:
    """The faces ``BOPAlgo_BuilderFace`` builds on *face*'s surface from its
    own edges, in its (deterministic) order; ``[]`` if it fails."""
    forward = TopoDS.Face_s(face.Oriented(TopAbs_FORWARD))
    edges = TopTools_ListOfShape()
    explorer = TopExp_Explorer(forward, TopAbs_EDGE)
    while explorer.More():
        edges.Append(explorer.Current())
        explorer.Next()
    builder = BOPAlgo_BuilderFace()
    builder.SetFace(forward)
    builder.SetShapes(edges)
    builder.Perform()
    if builder.HasErrors():
        return []
    return [TopoDS.Face_s(area) for area in builder.Areas()]
