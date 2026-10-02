"""A working copy of a body plus the picked faces on it, for a face op that
OCCT runs IN PLACE (draft, shell).

``BRepOffsetAPI_DraftAngle`` and ``BRepOffsetAPI_MakeThickSolid`` write to the
body they are given: measured 2026-10-02 (OCCT 7.9.3), every successful draft
and every sealed shell of the blade-hub bodies cleared the ``Checked`` flag of
one or two of the input's ``TShape`` objects. Geometry, tolerances, pcurves and
locations were unchanged, and a later cut on the input matched a cut on a fresh
build, so the change was cosmetic; but the input is the caller's body and the
rebuild cache's, and the fillet showed what an OCCT builder that writes to its
input can do (a 74 mm vertex tolerance). So these ops never get the input.

:func:`~geometry.kernel.fillet_isolation.working_copy` makes the copy (topology
copied, geometry shared, so the result is the same numbers). The picked faces
are carried over by index: a ``BRepBuilderAPI_Copy`` keeps the explorer order
face for face, the alignment :meth:`~geometry.kernel.naming.BodyNames.fork`
also relies on.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from collections.abc import Sequence

from build123d import Face
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedMapOfShape

from geometry.kernel.fillet_isolation import working_copy
from geometry.kernel.types import BodyShape


def working_copy_faces(
    body: BodyShape, faces: Sequence[Face]
) -> tuple[BodyShape, list[Face]]:
    """A topology copy of *body* and *faces* on it, in order (each keeps its
    orientation). A face that is not *body*'s is passed through as it is, so
    the op sees exactly what it would have seen on *body*."""
    copy, _edges = working_copy(body, [])
    seen, copied = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(body.wrapped, TopAbs_FACE, seen)
    TopExp.MapShapes_s(copy.wrapped, TopAbs_FACE, copied)
    if seen.Extent() != copied.Extent():  # pragma: no cover - OCCT invariant
        raise ValueError("the copy does not have the body's faces")
    out: list[Face] = []
    for face in faces:
        index = seen.FindIndex(face.wrapped)
        if index == 0:
            out.append(face)
            continue
        twin = TopoDS.Face_s(copied.FindKey(index))
        out.append(Face(TopoDS.Face_s(twin.Oriented(face.wrapped.Orientation()))))
    return copy, out
