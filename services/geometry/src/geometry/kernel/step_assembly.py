"""Assembly STEP import — read AP214 product structure back into placed bodies.

The inverse of :func:`geometry.kernel.export.export_step_assembly_bytes`
(docs/design/step-import.md; BACKLOG "Assembly STEP import with product
structure"). Where the export composes N named part bodies at solved world
placements into ONE multi-instance STEP via OCCT XDE
(``STEPCAFControl_Writer`` + ``TDocStd_Document`` + ``XCAFDoc_ShapeTool``),
this reader walks the SAME XDE machinery the other direction:
``STEPCAFControl_Reader`` → ``TDocStd_Document`` → the ``XCAFDoc_ShapeTool``
label tree, recovering each product's PRODUCT **name**, its world
**placement** (``TopLoc_Location`` → translation + unit quaternion), and its
LOCAL-frame **B-rep body** (the referred prototype shape). Two occurrences of
one part therefore share an identical local body — the dedup contract the
assembly evaluator relies on — with distinct placements.

**Structure detection (``has_assembly_structure``).** True when the file
carries ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` product structure — surfaced here as
``XCAFDoc_ShapeTool.IsAssembly_s`` on a free (root) label, which is exactly the
XDE view of a NAUO occurrence graph. A flat / single-body STEP has no assembly
root, so the flag is False and the reader returns the whole shape as ONE product
at identity — the backward-compatible signal the caller uses to fall back to the
single-body MB-4b import path (:func:`geometry.kernel.imports.import_step_solid`)
unchanged.

**Body taxonomy (MB-4b, reused).** Each product's prototype is normalised
through :func:`~geometry.kernel.lumps.assemble_lumps` exactly like the
single-body import: one solid → a bare :class:`~build123d.Solid`; two or more
disjoint solids → one lump-sorted :class:`~build123d.Compound`. Non-solid
reference geometry in a product is dropped; an import that recovers NO solid
product at all is an honest :class:`~geometry.kernel.imports.ImportNoSolidError`.

**Determinism (RESEARCH §9).** The read is a pure function of the file bytes
plus the process-global ``Interface_Static`` unit setting, which is pinned to
millimetres on every call (mirroring the single-body worker) so the result is
independent of process history. The product order follows the deterministic
XDE component order of the fixed bytes; each placement's quaternion is read
straight off the ``gp_Trsf`` (measured to match the exported placement to 1e-12).

**Never-500 posture (design §5).** Every OCCT failure mode is wrapped into a
typed :class:`~geometry.kernel.imports.ImportParseError` /
:class:`~geometry.kernel.imports.ImportNoSolidError` — the same taxonomy the
single-body reader raises — so the caller maps a bad file to a clean per-request
error, never an unhandled 500. The killable-subprocess CPU/wall DoS bound the
single-body reader applies to the untrusted parse (:mod:`geometry.kernel.imports`
§6) is NOT yet wired here: this slice's route is geometry-internal, and extending
that bound to the XCAF reader lands with the untrusted gateway upload endpoint
(slice 2).

Kernel objects never leave ``geometry.kernel``: :class:`ReadProduct` is
service-internal (its ``body`` is a kernel shape), and the service layer
(:func:`geometry.assembly.import_step.import_step_assembly`) converts it to the
pure-pydantic boundary DTO.

The OCP wheel ships no type stubs, so the raw XDE / OCCT calls below are opaque
to pyright; the directives scope that relaxation to this file only (same posture
as :mod:`geometry.kernel.imports` / :mod:`geometry.kernel.export`), and the
fully-typed :class:`ReadProduct` / :class:`StepAssemblyRead` results keep the
boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from build123d import Solid
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from geometry.kernel.imports import ImportNoSolidError, ImportParseError
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape

#: The OCCT target unit, pinned to millimetres on every read so the transferred
#: coordinates are independent of ambient ``Interface_Static`` state (RESEARCH
#: §9) — the same pin the single-body parse worker applies in its fresh process.
_CASCADE_UNIT_KEY = "xstep.cascade.unit"


@dataclass(frozen=True)
class ReadProduct:
    """One product recovered from an assembly STEP — name + world pose + body.

    Service-internal: ``body`` is a kernel :data:`BodyShape` in the product's
    LOCAL frame (never serialised), normalised through
    :func:`~geometry.kernel.lumps.assemble_lumps` (one solid → a bare
    :class:`~build123d.Solid`, several → a lump-sorted
    :class:`~build123d.Compound`) exactly like the single-body import. ``name``
    is the STEP PRODUCT name (``None`` when the file names no product);
    ``translation`` + ``quaternion`` (the latter ``(x, y, z, w)``, matching
    :class:`py_kit.schemas.assemblies.Quat`) are the occurrence's WORLD placement,
    so ``world = R(quaternion)·local + translation`` reproduces the exported pose.
    """

    name: str | None
    body: BodyShape
    translation: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]


@dataclass(frozen=True)
class StepAssemblyRead:
    """The structured result of reading a STEP through the XDE product tree.

    ``has_assembly_structure`` is True when the file carried NAUO product
    structure (an XDE assembly root); False for a flat / single-body STEP, whose
    single product sits at identity and signals the caller to fall back to the
    single-body MB-4b path. ``products`` are in the deterministic XDE order of
    the fixed bytes.
    """

    has_assembly_structure: bool
    products: list[ReadProduct]


def _label_name(label: TDF_Label) -> str | None:
    """The ``TDataStd_Name`` of *label* as a Python string, or ``None``."""
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return str(attr.Get().ToExtString())
    return None


def _placement_of(
    location: TopLoc_Location,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """A ``TopLoc_Location`` as ``(translation, (x, y, z, w) quaternion)``.

    Reads the rigid pose straight off the accumulated ``gp_Trsf`` — the exact
    inverse of the ``place_body`` quaternion → ``gp_Trsf`` the export applies, so
    a round-trip recovers the authored placement (measured to 1e-12).
    """
    trsf = location.Transformation()
    quat = trsf.GetRotation()
    xyz = trsf.TranslationPart()
    return (
        (float(xyz.X()), float(xyz.Y()), float(xyz.Z())),
        (float(quat.X()), float(quat.Y()), float(quat.Z()), float(quat.W())),
    )


def _body_from_shape(shape: TopoDS_Shape) -> BodyShape | None:
    """Normalise a prototype shape into one lump-sorted body, or ``None``.

    Extracts every ``TopAbs_SOLID`` and runs them through
    :func:`~geometry.kernel.lumps.assemble_lumps` (the SAME deterministic
    centroid/volume sort the single-body import uses, §MB-4b): one solid returns
    bare, several return a lump-sorted compound. A shape with no solids
    (non-solid reference geometry) returns ``None`` — the caller drops it.
    """
    if shape.IsNull():
        return None
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solids: list[Solid] = []
    while explorer.More():
        solids.append(Solid(TopoDS.Solid_s(explorer.Current())))
        explorer.Next()
    if not solids:
        return None
    return assemble_lumps(solids)


def _transfer_document(step_text: str) -> TDocStd_Document:
    """Parse *step_text* through XCAF into a rooted, kept-alive XDE document.

    Units are pinned to mm BEFORE the read (determinism, RESEARCH §9). The
    document is created through ``XCAFApp_Application`` and returned by the
    caller VERBATIM so it stays referenced: the ``XCAFDoc_ShapeTool`` labels are
    views into the document's data framework, so a collected document would
    invalidate every label mid-walk. Any OCCT failure is wrapped into a typed
    :class:`ImportParseError` — never an unhandled raise.
    """
    Interface_Static.SetCVal_s(_CASCADE_UNIT_KEY, "MM")
    application = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    application.InitDocument(document)

    with tempfile.TemporaryDirectory(prefix="loft-step-assembly-") as tmp:
        path = os.path.join(tmp, "assembly.step")
        with open(path, "wb") as handle:
            handle.write(step_text.encode("utf-8"))
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        try:
            status = reader.ReadFile(path)
        except Exception as exc:  # OCCT can raise on malformed part-21
            raise ImportParseError(
                "The assembly STEP payload could not be read; it may be "
                "malformed, truncated, or not a STEP file."
            ) from exc
        if status != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise ImportParseError(
                "The assembly STEP payload could not be read (STEP reader "
                f"status {status}); it may be malformed or not a STEP file."
            )
        try:
            transferred = reader.Transfer(document)
        except Exception as exc:
            raise ImportParseError(
                "The assembly STEP payload could not be transferred into the "
                "product structure; it may be malformed or degenerate."
            ) from exc
        if not transferred:
            raise ImportParseError(
                "The assembly STEP payload transferred no geometry; it may be "
                "empty, surfaces-only, or not a STEP file."
            )
    return document


def _collect_leaf(
    shape_tool: object,
    ref_label: TDF_Label,
    world_location: TopLoc_Location,
    name: str | None,
    into: list[ReadProduct],
) -> None:
    """Emit one product for a leaf occurrence, recursing into a sub-assembly.

    A component references a prototype (``ref_label``); when that prototype is
    itself an assembly (a rigid sub-assembly) the walk recurses, composing the
    child location under *world_location* so every leaf carries its full WORLD
    placement. A leaf prototype's LOCAL shape is normalised into one body; a
    non-solid prototype is dropped.
    """
    if shape_tool.IsAssembly_s(ref_label):  # type: ignore[attr-defined]
        _collect_components(shape_tool, ref_label, world_location, into)
        return
    body = _body_from_shape(shape_tool.GetShape_s(ref_label))  # type: ignore[attr-defined]
    if body is None:
        return
    translation, quaternion = _placement_of(world_location)
    into.append(
        ReadProduct(
            name=name, body=body, translation=translation, quaternion=quaternion
        )
    )


def _collect_components(
    shape_tool: object,
    assembly_label: TDF_Label,
    parent_location: TopLoc_Location,
    into: list[ReadProduct],
) -> None:
    """Walk every component (NAUO occurrence) of an assembly label.

    For each occurrence: compose its location under *parent_location* (so nested
    sub-assemblies accumulate to a world placement), resolve its referred
    prototype, and take the occurrence NAME from the PRODUCT (referred) label,
    falling back to the component (NAUO) label.
    """
    components = TDF_LabelSequence()
    shape_tool.GetComponents_s(assembly_label, components)  # type: ignore[attr-defined]
    for index in range(1, components.Length() + 1):
        component = components.Value(index)
        component_location = shape_tool.GetLocation_s(component)  # type: ignore[attr-defined]
        world_location = parent_location.Multiplied(component_location)
        referred = TDF_Label()
        if not shape_tool.GetReferredShape_s(component, referred):  # type: ignore[attr-defined]
            continue
        name = _label_name(referred) or _label_name(component)
        _collect_leaf(shape_tool, referred, world_location, name, into)


def read_step_assembly(step_text: str) -> StepAssemblyRead:
    """Parse *step_text* into a structured, positioned, named product list.

    Walks the XDE product tree (module docstring): an assembly root expands into
    one product per occurrence — its PRODUCT name, WORLD placement, and
    LOCAL-frame body — while a flat / single-body STEP returns ONE product at
    identity with ``has_assembly_structure=False`` (the backward-compatible
    fallback signal). Deterministic (units pinned to mm; RESEARCH §9).

    Raises:
        ImportParseError: OCCT could not read/transfer the payload (bad/empty/
            truncated STEP) — the same code the single-body reader raises.
        ImportNoSolidError: the file parsed but yielded NO solid product
            (surfaces-only / wireframe / open shells) — carries the honest
            "no solids" phrasing the single-body reader uses.
    """
    document = _transfer_document(step_text)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)

    has_assembly_structure = False
    products: list[ReadProduct] = []
    for index in range(1, free.Length() + 1):
        root = free.Value(index)
        root_location = shape_tool.GetLocation_s(root)
        if shape_tool.IsAssembly_s(root):
            has_assembly_structure = True
            _collect_components(shape_tool, root, root_location, products)
        else:
            # Flat / single-body free shape: surface the whole located shape as
            # one product at identity — the single-body MB-4b fallback signal.
            body = _body_from_shape(shape_tool.GetShape_s(root))
            if body is None:
                continue
            translation, quaternion = _placement_of(root_location)
            products.append(
                ReadProduct(
                    name=_label_name(root),
                    body=body,
                    translation=translation,
                    quaternion=quaternion,
                )
            )

    if not products:
        raise ImportNoSolidError(
            "The assembly STEP file transferred no solids; it may contain only "
            "surfaces, wireframe, or annotations, or no importable product."
        )
    return StepAssemblyRead(
        has_assembly_structure=has_assembly_structure, products=products
    )
