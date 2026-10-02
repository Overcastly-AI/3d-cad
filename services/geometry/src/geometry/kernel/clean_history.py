"""Booleans and ``clean`` that also report which faces were MERGED
(DESIGN-INTENT-REFS step 3, docs/RESEARCH.md §14).

``ShapeUpgrade_UnifySameDomain`` merges coplanar neighbours into one face: a
flange's end cap and the base flange's side face it lies flush with become one
face. A merged face is BOTH faces, so it carries both names
(:func:`geometry.kernel.naming.carry_names`). Which faces merged is read from
the upgrader's own history, never inferred from geometry.

build123d runs that upgrader inside every boolean (``_bool_op``) and again in
``Shape.clean()``, and exposes the history of neither. So this module repeats
the two, VERBATIM (the same ``BRepAlgoAPI`` set-up, the same upgrader flags,
``AllowInternalEdges(False)``, the same compound unwrap and cast, the same
fall-back when OCCT raises), and only keeps the history: the shape is the one
build123d returns, byte for byte. It is used only where a caller asks for the
history, and never through build123d's process-global ``SkipClean`` switch,
which would leak into booleans running on other threads.

Each merge is reported as the merged face of the result plus the faces it was
made from, taken from a ``BRepBuilderAPI_Copy`` made before the upgrader runs:
``UnifySameDomain`` rewrites its input's shapes in place, so only the copy
still shows the faces as they were.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false, reportMissingTypeArgument=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import warnings
from typing import Literal, cast

from build123d import Compound, Face, ShapeList, Solid
from build123d.topology.shape_core import (
    Shape,
    downcast,
    get_top_level_topods_shapes,
    unwrap_topods_compound,
)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape

from geometry.kernel.types import BodyShape

#: One merge: the merged face of the cleaned body, and the faces (as they were
#: before the clean) it was made from.
MergedFaces = tuple[Face, list[Face]]


def _faces(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, found)
    return [found.FindKey(i) for i in range(1, found.Extent() + 1)]


def _unify(
    shape: TopoDS_Shape, pristine: TopoDS_Shape, merges: list[MergedFaces]
) -> TopoDS_Shape | None:
    """``UnifySameDomain`` on *shape* exactly as build123d runs it; the result,
    or ``None`` when OCCT raised (build123d then keeps the input). Appends
    each merge to *merges*, its members taken from *pristine* (a copy of
    *shape* made before the call: both are walked in the same order)."""
    before = _faces(shape)
    upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    upgrader.AllowInternalEdges(False)
    try:
        upgrader.Build()
        result = downcast(upgrader.Shape())
    except Exception:
        return None
    copies = _faces(pristine)
    if len(before) != len(copies):
        return result
    history = upgrader.History()
    groups: list[tuple[TopoDS_Shape, list[Face]]] = []
    for face, copy in zip(before, copies, strict=True):
        produced = list(history.Modified(face))
        if len(produced) != 1:
            continue
        (merged,) = produced
        member = Face(TopoDS.Face_s(copy))
        group = next((g for g in groups if g[0].IsSame(merged)), None)
        if group is None:
            groups.append((merged, [member]))
        else:
            group[1].append(member)
    merges.extend(
        (Face(TopoDS.Face_s(merged)), members)
        for merged, members in groups
        if len(members) > 1
    )
    return result


def clean_recording[ShapeT: BodyShape](
    shape: ShapeT, spare: ShapeT, merges: list[MergedFaces]
) -> ShapeT:
    """``shape.clean()``, appending each face merge to *merges*.

    *spare* is a ``BRepBuilderAPI_Copy`` of *shape* taken before this call
    (:func:`~geometry.kernel.healing.clean_shape` makes it anyway).
    """
    assert shape.wrapped is not None and spare.wrapped is not None
    result = _unify(shape.wrapped, spare.wrapped, merges)
    if result is None:  # the very fall-back of Shape.clean()
        warnings.warn(f"Unable to clean {shape}", stacklevel=2)
        return shape
    shape.wrapped = result
    return shape


def boolean_recording(
    base: BodyShape,
    tool: Solid,
    operation: Literal["fuse", "cut"],
    merges: list[MergedFaces],
) -> BodyShape:
    """``base.fuse(tool)`` / ``base - tool``, appending each face merge of the
    boolean's built-in clean to *merges*. Both shapes are non-empty solids
    (or a multi-lump compound for *base*), so the result is one of the two."""
    assert base.wrapped is not None and tool.wrapped is not None
    op = BRepAlgoAPI_Fuse() if operation == "fuse" else BRepAlgoAPI_Cut()
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(base.wrapped)
    tools.Append(tool.wrapped)
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    raw = downcast(op.Shape())
    pristine = BRepBuilderAPI_Copy(raw).Shape()
    unified = _unify(raw, pristine, merges)
    if unified is None:
        warnings.warn("Boolean operation unable to clean", stacklevel=2)
        unified = raw
    if isinstance(unified, TopoDS_Compound):
        unified = unwrap_topods_compound(unified, True)
    kinds: list[type[Shape]] = [type(base), type(tool)]  # pyright: ignore[reportUnknownVariableType]
    highest = max(kinds, key=lambda kind: kind.order)
    if isinstance(unified, TopoDS_Compound) and highest.order != 4:
        results = ShapeList(
            highest.cast(s) for s in get_top_level_topods_shapes(unified)
        )
        for result in results:
            base.copy_attributes_to(result, ["wrapped", "_NodeMixin__children"])
        composite = Shape.make_composite(results, highest.order)
        base.copy_attributes_to(composite, ["wrapped", "_NodeMixin__children"])
        return cast(Compound, composite)
    result = highest.cast(unified)
    base.copy_attributes_to(result, ["wrapped", "_NodeMixin__children"])
    return cast(BodyShape, result)
