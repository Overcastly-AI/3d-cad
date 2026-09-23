"""Fork a set of shapes into an independent copy that keeps their sharing.

The one kernel primitive the rebuild cache's checkpoint LADDER needs (PERF-REAL-2,
:mod:`geometry.rebuild_cache`). A ladder rung is an evaluator state held while the
evaluation that produced it carries on past it, so the two must not share a
single ``TShape``: OCCT booleans rewrite their arguments' subshapes in place
(tolerance growth, added pcurves; CM-6b), and a boolean result shares every face
it did not touch with its argument — so a rung that merely kept references would
be edited, silently, by the features evaluated after it.

WHY ONE COPY OVER A COMPOUND, AND NOT ONE COPY PER SHAPE. The evaluator state
holds several shapes that can share subshapes with each other — a body and the
cut tool that made it (the result keeps the tool's untouched faces), or the
sheet-metal unfold body that IS the live body on an unrelieved part. Copying each
separately would turn one shared face into two unrelated ones, which is a
different B-rep as far as a later boolean is concerned. Copying them together, as
children of one throwaway compound, maps every shared ``TShape`` to one shared
copy, so the fork is the same topology as the original, relation for relation.

WHAT A FORK IS NOT: bit-for-bit the original. ``BRepBuilderAPI_Copy`` preserves
geometry exactly (volume and STEP bytes identical) but re-meshes to a GLB that can
differ by an ULP (measured 2026-07-31, see :mod:`geometry.rebuild_cache`). That is
why the ladder does not fork *on the side*: every evaluation forks at the same
fixed rung positions whether or not anything is cached, so a resumed rebuild and a
cold one perform the identical OCCT calls on identical inputs.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from collections.abc import Sequence
from typing import Any

from build123d.topology.shape_core import Shape, downcast
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
from OCP.TopTools import TopTools_IndexedMapOfShape


class ForkedShapes[ShapeT: Shape[Any]]:
    """The forked shapes, in input order, plus how many distinct faces they hold.

    ``faces`` is the cache's memory WEIGHT for the fork — counted on the copy,
    which is the object the cache will keep, and counted once per distinct face so
    a face shared between two of the shapes is not charged twice.
    """

    __slots__ = ("faces", "shapes")

    def __init__(self, shapes: list[ShapeT], faces: int) -> None:
        self.shapes = shapes
        self.faces = faces


def fork_shapes[ShapeT: Shape[Any]](shapes: Sequence[ShapeT]) -> ForkedShapes[ShapeT]:
    """Deep-copy *shapes* together, preserving every subshape they share.

    Returns new wrappers of the same build123d classes, in the same order, with
    ``label`` and ``color`` carried over (the STEP writer reads ``label``). The
    geometry is copied too (``copyGeom=True``) so that no ``Geom_*`` handle is
    shared either, and the triangulation is not (``copyMesh=False``): a fork
    carries no mesh, exactly like a freshly built shape.
    """
    if not shapes:
        return ForkedShapes([], 0)
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape.wrapped)
    copied = BRepBuilderAPI_Copy(compound, True, False).Shape()

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(copied, TopAbs_FACE, faces)

    forked: list[ShapeT] = []
    children = TopoDS_Iterator(copied)
    for shape in shapes:
        if not children.More():  # pragma: no cover - OCCT contract
            raise RuntimeError("fork_shapes: the copied compound lost a child")
        twin = type(shape)(downcast(children.Value()))
        twin.label = shape.label
        twin.color = shape.color
        forked.append(twin)
        children.Next()
    return ForkedShapes(forked, faces.Extent())
