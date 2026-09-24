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

import io
import math
from collections.abc import Sequence
from typing import Any

from build123d.topology.shape_core import Shape, downcast
from OCP.BinTools import BinTools
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
from OCP.TopTools import TopTools_IndexedMapOfShape

#: Heap bytes per byte of OCCT's binary BRep serialisation, and per face, of a
#: forked shape held in memory — the two terms of :func:`estimate_heap_bytes`.
#:
#: MEASURED 2026-09-24 (heap in use via ``mallinfo2``, six forks held, of the
#: final evaluator state), because no single term fits both kinds of part:
#:
#: ==================================  ======  ===========  ===========  =========
#: part                                 faces  heap / fork  BinTools     heap/bin
#: ==================================  ======  ===========  ===========  =========
#: housing tray N=250 (analytic)          560     1.76 MiB     0.45 MiB       3.90
#: lofted NURBS lobes, 8 motifs            22     0.80 MiB     0.51 MiB       1.55
#: lofted NURBS lobes, 24 motifs           68     3.81 MiB     2.49 MiB       1.53
#: ==================================  ======  ===========  ===========  =========
#:
#: The serialised size carries the GEOMETRY (poles, knots, pcurves, and any
#: triangulation), which is what a freeform part is made of; a fixed per-face
#: term carries the topology's object overhead, which is what an analytic part
#: is made of. Fitting both to the three points gives ~1.48 x bin + ~2.0 KiB per
#: face; the constants below are that fit rounded UP, so the estimate reads
#: +8 % to +11 % over every measured fork. A face-only price was the defect
#: (GQA-LADDER-1): the tray's 3.2 KiB/face is 15.7x too low for the NURBS part.
HEAP_BYTES_PER_BIN_BYTE = 1.6
HEAP_BYTES_PER_FACE = 2304


class _CountingSink(io.BytesIO):
    """A write-only stream that keeps the COUNT, not the bytes, so weighing a
    100 MiB shape does not allocate another 100 MiB to do it."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def write(self, data: Any, /) -> int:
        size = len(data)
        self.count += size
        return size


def estimate_heap_bytes(shape: Any, faces: int) -> int:
    """Estimated heap a held copy of *shape* (a ``TopoDS_Shape``) occupies.

    ``HEAP_BYTES_PER_BIN_BYTE`` x its binary BRep size (``BinTools``, geometry
    and triangulation included) + ``HEAP_BYTES_PER_FACE`` x *faces*. Costs one
    serialisation into a counting sink: ~7 ms for the 560-face tray, ~12 ms for
    the 24-lobe NURBS part, i.e. about what one fork costs.
    """
    sink = _CountingSink()
    BinTools.Write_s(shape, sink)
    return math.ceil(HEAP_BYTES_PER_BIN_BYTE * sink.count) + HEAP_BYTES_PER_FACE * faces


class ForkedShapes[ShapeT: Shape[Any]]:
    """The forked shapes, in input order, plus what they weigh.

    ``faces`` is counted on the copy, once per distinct face, so a face shared
    between two of the shapes is not charged twice. ``nbytes`` is the estimated
    heap the copy occupies (:func:`estimate_heap_bytes`) — the ladder's memory
    WEIGHT — and is ``0`` unless the fork was asked to ``weigh`` itself.
    """

    __slots__ = ("faces", "nbytes", "shapes")

    def __init__(self, shapes: list[ShapeT], faces: int, nbytes: int = 0) -> None:
        self.shapes = shapes
        self.faces = faces
        self.nbytes = nbytes


def fork_shapes[ShapeT: Shape[Any]](
    shapes: Sequence[ShapeT], *, weigh: bool = False
) -> ForkedShapes[ShapeT]:
    """Deep-copy *shapes* together, preserving every subshape they share.

    Returns new wrappers of the same build123d classes, in the same order, with
    ``label`` and ``color`` carried over (the STEP writer reads ``label``). The
    geometry is copied too (``copyGeom=True``) so that no ``Geom_*`` handle is
    shared either, and the triangulation is not (``copyMesh=False``): a fork
    carries no mesh, exactly like a freshly built shape.

    *weigh* also estimates the copy's heap bytes — only worth paying for a fork
    that will be HELD (a ladder rung), not one an evaluation carries on with.
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
    nbytes = estimate_heap_bytes(copied, faces.Extent()) if weigh else 0
    return ForkedShapes(forked, faces.Extent(), nbytes)
