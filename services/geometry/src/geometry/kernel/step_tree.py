"""Read a STEP file's PRODUCT TREE back through OCCT XCAF (BIKE2-STEP-FLAT gate).

The assembly export writes product structure the way SolidWorks, Fusion and
Onshape do: a root product named after the assembly, each sub-assembly a nested
product, each part one product placed by as many occurrences as it has
instances. :func:`read_step_tree` is the reading a receiving CAD performs, kept
whole rather than flattened: every occurrence with its own name, the product it
refers to (and that product's label, so shared products are visible as shared),
its children, and for a part its WORLD-space bounding box after composing every
location on the way down.

It runs in-process and is for files this service wrote (the goldens' STEP
round-trip gate). An untrusted upload goes through
:func:`geometry.kernel.step_assembly.read_step_assembly`, which bounds the read
in a killable subprocess.

:func:`placed_bounding_box` is the other side of the same comparison: a part
body at a solved world placement, measured the same way.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from geometry.kernel.export import placement_trsf
from geometry.kernel.types import BodyShape

#: An axis-aligned box as ``((xmin, ymin, zmin), (xmax, ymax, zmax))``.
Box3 = tuple[tuple[float, float, float], tuple[float, float, float]]


@dataclass(frozen=True)
class StepTreeNode:
    """One occurrence of a STEP product tree (the root is the root product).

    ``name`` is the occurrence's own name (the NAUO), ``product`` the name of
    the product it refers to and ``product_label`` that product's XCAF entry,
    equal for every occurrence of one shared product. ``bounding_box`` is the
    world-space box of a part occurrence and ``None`` for an assembly.
    """

    name: str | None
    product: str | None
    product_label: str
    children: tuple[StepTreeNode, ...]
    bounding_box: Box3 | None


def _name(label: TDF_Label) -> str | None:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return str(attr.Get().ToExtString())
    return None


def _entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return str(entry.ToCString())


def _box(shape: TopoDS_Shape) -> Box3:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (
        (float(xmin), float(ymin), float(zmin)),
        (float(xmax), float(ymax), float(zmax)),
    )


def _node(
    name: str | None, product: TDF_Label, location: TopLoc_Location
) -> StepTreeNode:
    if not XCAFDoc_ShapeTool.IsAssembly_s(product):
        shape = XCAFDoc_ShapeTool.GetShape_s(product).Moved(location)
        return StepTreeNode(name, _name(product), _entry(product), (), _box(shape))
    components = TDF_LabelSequence()
    XCAFDoc_ShapeTool.GetComponents_s(product, components)
    children: list[StepTreeNode] = []
    for index in range(1, components.Length() + 1):
        component = components.Value(index)
        referred = TDF_Label()
        if not XCAFDoc_ShapeTool.GetReferredShape_s(component, referred):
            continue
        child_location = location.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(component))
        children.append(_node(_name(component), referred, child_location))
    return StepTreeNode(name, _name(product), _entry(product), tuple(children), None)


def read_step_tree(data: bytes) -> StepTreeNode:
    """The product tree of the STEP *data* (exactly one root product).

    Raises:
        ValueError: OCCT could not read the file, or it has no single root.
    """
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    XCAFApp_Application.GetApplication_s().InitDocument(document)
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    with tempfile.TemporaryDirectory(prefix="loft-step-tree-") as tmp:
        path = Path(tmp) / "tree.step"
        path.write_bytes(data)
        if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise ValueError("STEP read failed")
    if not reader.Transfer(document):
        raise ValueError("STEP transfer failed")
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise ValueError(f"expected one root product, found {roots.Length()}")
    root = roots.Value(1)
    return _node(_name(root), root, XCAFDoc_ShapeTool.GetLocation_s(root))


def placed_bounding_box(
    body: BodyShape,
    translation: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> Box3:
    """*body*'s world box at a placement, measured as :func:`read_step_tree` does."""
    trsf = placement_trsf(translation, quaternion)
    return _box(body.wrapped.Moved(TopLoc_Location(trsf)))
