"""CAD file export — STEP (exact B-rep) and three faceted meshes (STL, 3MF, GLB).

STEP is written through OCCT's ``STEPCAFControl_Writer`` directly (one writer for
parts and assemblies alike — :func:`_write_step_document`); the mesh formats use
build123d's exporters (``StlAPI_Writer``, ``RWGltf_CafWriter``, and lib3mf via
``build123d.mesher.Mesher``). Every output is **byte-deterministic** for
identical requests (RESEARCH §9); the geometry export gate asserts it:

* **STEP:** OCCT stamps the file's ``FILE_NAME`` record with the wall-clock
  creation time — the one nondeterministic byte range in a SINGLE-BODY output
  (the assembly writer adds two more; see the determinism note below). We pin
  it to :data:`STEP_EXPORT_TIMESTAMP` on the header we build
  (decision + evidence recorded in docs/GEOMETRY-QA.md, gap #4). Writing to a
  ``BytesIO`` also keeps filesystem paths out of the file, and the ``FILE_NAME``
  name field carries the document name or, unnamed, OCCT's fixed default.
* **STL:** binary format, fixed 80-byte OCCT header + mesher output, no
  timestamps. ``export_stl`` runs the SAME ``BRepMesh_IncrementalMesh`` call
  as the GLB tessellation path (``Shape.mesh``: relative linear deflection,
  parallel flag), so a given ``linear_deflection`` / ``angular_deflection``
  pair means the same facets in the viewport and in the exported file.
  Defaults come from :mod:`py_kit.schemas.geometry`
  (``DEFAULT_LINEAR_DEFLECTION`` = 0.1 mm, ``DEFAULT_ANGULAR_DEFLECTION`` =
  0.1 rad — the viewport-quality tessellation settings).
* **3MF:** an OPC (zip) container whose ``3D/3dmodel.model`` XML declares
  ``unit="millimeter"`` — the thing STL cannot say, and the reason every 2026
  slicer prefers it. lib3mf pins the zip member timestamps to 1980, so the only
  nondeterministic bytes are the five random production-extension UUIDs it
  stamps per write; :func:`_canonicalise_3mf_ids` pins those to
  :data:`THREE_MF_UUID_NAMESPACE`-derived values, exactly as
  :data:`STEP_EXPORT_TIMESTAMP` pins the STEP clock. It also drops the
  unreferenced components object build123d adds beside each mesh ("Not sure is
  this is required..." in ``build123d/mesher.py``) — nothing in the build item
  list points at it, and a resource no consumer reads is bytes we should not
  ship.
* **GLB:** *not a new exporter.* It is the payload
  :func:`~geometry.kernel.tessellate.tessellate_glb` already produces on every
  viewport tessellation, handed over unchanged — so the file a user downloads
  is byte-identical to the mesh their screen is drawing, and its determinism is
  the tessellation path's determinism, already gated. **It is in METRES and
  Y-up**, per the glTF 2.0 spec, unlike every other format here, which are
  millimetres and Z-up; ``py_kit.schemas.geometry.EXPORT_UNITS`` is the single
  place that says so and the export gate asserts the extents against it. That
  asymmetry is the format's, not ours: a GLB written in mm renders 1000x too
  large in every conformant viewer.

Kernel objects never leave ``geometry.kernel``: callers receive bytes.

**Assembly export (AP214 product structure, INSTANCED).**
:func:`export_step_assembly_bytes` composes N placed part bodies into ONE
multi-instance STEP. Twenty instances of one dowel pin write the pin's B-rep
**once** and place it twenty times, as AP214 product structure does it: one
``PRODUCT`` per unique part, one ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` +
``CONTEXT_DEPENDENT_SHAPE_REPRESENTATION`` + ``ITEM_DEFINED_TRANSFORMATION``
per occurrence (audit N8 — see below for why that triple, and not
``MAPPED_ITEM``, is the instancing OCCT emits). The receiving CAD/PLM therefore
sees ONE part used twenty times, so a change to the part is a change to all
twenty and a derived BOM reads qty 20 rather than 20 line items — and the file
stops scaling linearly with the fastener count.

*What made every instance a fresh B-rep:* ``Shape.located()`` is a **deep
geometric copy** (build123d runs ``BRepBuilderAPI_Copy`` inside its
``__deepcopy__``), so the twenty placed bodies shared no underlying
``TopoDS_TShape`` and there was no instancing for any writer to find. The STEP
composer therefore places its bodies with :func:`_instanced_shape`
(``TopoDS_Shape.Moved`` — a new shape over the SAME ``TShape``), which is what
lets OCCT's XCAF instance detection collapse them. :func:`place_body` keeps the
copying semantics for the interference + STL paths, where a boolean may
invalidate its argument in place (RESEARCH §9) and sharing would be unsafe.

*Naming.* Each occurrence label carries the INSTANCE name ("Dowel Pin 8x24 <17>"
→ the NAUO), and the shared part label carries the PART name — the first
occurrence's name with its ``<n>`` suffix stripped (:func:`_product_name`) →
the ``PRODUCT``. So instance-level traceability (FINDINGS #7) survives while the
file finally says the twenty are the same part. We drive
``STEPCAFControl_Writer`` directly rather than through build123d's
``export_step`` for exactly this: build123d names the referred (shared) label
from every child in turn, so the shared PRODUCT would end up named after
whichever instance happened to be written LAST ("Dowel Pin 8x24 <20>").

*Name FIDELITY* (STEPNAME-1). A STEP file is what a user hands to a machinist or
a supplier, so a name in it is read by a human in someone else's CAD — which
makes "almost right" and "wrong" the same outcome. Three things were measured
rather than assumed before this was called done:

* **Non-ASCII was corrupted.** ``TCollection_ExtendedString(str)`` binds to the
  ``isMultiByte=False`` overload, which reads the UTF-8 bytes one at a time as
  characters, so ``"Flänsch"`` became 17 characters instead of 13 and reached the
  file double-encoded. :func:`_xcaf_name` is the fix and the only place these
  labels are built; the name now decodes back byte-exactly for accents, a degree
  sign, an em dash and CJK.
* **Apostrophes needed nothing.** OCCT's part-21 writer already doubles them
  (``'Jim''s bracket'``), which is the standard's own escape. Asserted, not
  assumed — the naive instinct is to escape them a second time, which would
  corrupt the name in the other direction.
* **DUPLICATE part names are kept VERBATIM, and that is a decision.** Two
  instances of ONE part share a name and correctly produce one ``PRODUCT`` used
  twice — the case that actually occurs, and it already worked. Two DIFFERENT
  parts a user has both called "Bracket" produce two distinct ``PRODUCT``
  entities whose ``id`` AND ``name`` both read ``'Bracket'``. That id collision
  is real and is reproduced by ``test_step_names``. We do not disambiguate:
  the id would have to be mangled to do it, and a mangled part number in the
  file a supplier quotes from is worse than reproducing an ambiguity the user
  authored in their own data — which no CAD system resolves for them either.

*The SINGLE-BODY path now writes through the SAME writer* (STEPNAME-2), which is
what closes the naming split. It used to go through build123d's ``export_step``,
which hardcodes ``SetOriginatingSystem("build123d")`` with no parameter and
builds its label through the same defaulted ``ExtendedString`` overload — so the
export a user reaches by downloading ONE PART, the more common of the two, was
the one carrying both defects while the rarer assembly export was correct.

**Unifying cost nothing a consumer can see, and that is measured rather than
argued.** The worry that made this a decision was that owning the writer would
drag XCAF assembly structure into a file that has none. It does not:
:func:`_single_body_xde_document` rebuilds the document
``build123d.exporters3d._create_xde`` builds for a shape with no children —
``AddShape(..., makeAssembly=False)``, auto-naming ON — and the result is
BYTE-IDENTICAL to build123d's output for a named solid, an unnamed solid, and a
multi-body ``Compound`` both ways. ``test_step_names_part`` pins that by
comparing the part-21 DATA section — where entity ids, product structure and
geometry live — against build123d's own output, leaving only the header (whose
originating system we deliberately changed) out of the comparison. So no golden's
digest moves for a structural reason; measured over all four cases plus an
ASCII-named solid, the ONLY bytes that differ from yesterday are the
``FILE_NAME`` originating system and, for a non-ASCII name, the ``PRODUCT`` id
and name — which are the two defects. The single-body path remains free of both
process-global writer
counters — it interposes no extra level and emits no translator PRODUCT — so
:func:`_canonicalise_writer_counters` stays an assembly-only concern and the part
path's in-process determinism is asserted directly instead.

*Why no MAPPED_ITEM.* AP214 has two encodings for "this geometry, placed there":
``MAPPED_ITEM``/``REPRESENTATION_MAP`` (a representation re-used inside another
representation) and the assembly product structure above. OCCT's XCAF writer
emits the latter, which is the encoding every MCAD assembly exchange uses — the
audit's ``MAPPED_ITEM`` count was a proxy for "is anything instanced at all",
and the measurable that actually answers it is ``MANIFOLD_SOLID_BREP`` count ==
the unique parts' BODY count — one B-rep per body, placed once per instance, so
the file does not scale with the instance count (asserted on the emitted bytes by
``test_assembly_export``; per BODY rather than per PART since a multi-body part
legitimately writes several and instances all the same).

Determinism (RESEARCH §9): the pinned timestamp above applies unchanged. This
path introduces TWO extra nondeterministic byte ranges, both fed by the same
**process-global** counters OCCT increments across writer invocations within a
worker: the ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` id, and — when a component's body
is a ``Compound``, i.e. a MULTI-BODY part — the PRODUCT id/name of the extra
assembly level OCCT interposes, ``'Open CASCADE STEP translator 7.9 N.M.K'``.
:func:`_canonicalise_writer_counters` renumbers both to appearance order so
identical requests stay byte-identical (decision + evidence in
docs/GEOMETRY-QA.md). Both are arbitrary labels — STEP cross-references use
``#N`` entity ids, not these strings — so renumbering them is semantically
inert. The second range went unfixed for a month (STEPDET-1) because every
shipped assembly golden was made of single-``Solid`` parts, so the determinism
gates could not reach the code path; ``assembly-two-multibody-brackets`` is the
fixture that makes them able to fail.

The OCP wheel ships no type stubs, so the raw ``gp_Trsf`` / ``gp_Quaternion``
transform calls the assembly placement uses are opaque to pyright; the directives
scope that relaxation to this file only (same posture as
:mod:`geometry.kernel.properties` / :mod:`geometry.kernel.imports`), and the
fully-typed :data:`BodyShape` return keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import io
import re
import tempfile
import uuid
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from build123d import Compound, Location
from build123d.build_common import UNITS_PER_METER
from build123d.build_enums import PrecisionMode, Unit
from build123d.exporters3d import (
    export_stl,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
)
from build123d.mesher import Mesher
from lib3mf import Lib3MF
from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Quaternion, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Message import Message, Message_Gravity
from OCP.STEPCAFControl import STEPCAFControl_Controller, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_Controller, STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.XSControl import XSControl_WorkSession

from geometry.kernel.tessellate import tessellate_glb
from geometry.kernel.types import BodyShape

#: Pinned STEP creation timestamp (determinism decision, GEOMETRY-QA gap #4).
#: STEP consumers treat ``FILE_NAME``'s timestamp as provenance metadata, not
#: geometry; a fixed sentinel value makes identical requests byte-identical.
STEP_EXPORT_TIMESTAMP = datetime(2000, 1, 1, 0, 0, 0)

#: Marker every STEP part 21 file starts with (sanity-checked after export).
STEP_MAGIC = b"ISO-10303-21"

#: What EVERY STEP's ``FILE_NAME`` originating-system field says — the assembly
#: export since STEPNAME-1, the single-body export since STEPNAME-2, which is the
#: split that mattered because the part download is the common one.
#: It read ``'build123d'`` — the name of a library the recipient
#: has no reason to have heard of — so a file Loft AUTHORED did not say so
#: anywhere, and the one person who most needs to know where a suspect part came
#: from (the machinist holding it) had nothing to go on. AP214 defines this field
#: as the system that produced the file, which is this application, not the
#: binding it drove OCCT through.
#:
#: ASCII by construction: this string lands in a part-21 header via
#: ``TCollection_HAsciiString``, which is byte-transparent, so a non-ASCII value
#: here would put raw UTF-8 into a header the standard does not permit it in.
#: **It deliberately carries no version.** The timestamp beside it is already
#: pinned to a sentinel for determinism (:data:`STEP_EXPORT_TIMESTAMP`), and a
#: version string here would be the one byte range that changes on every release
#: — turning every committed digest and every byte-equality assertion into a
#: release-day failure for no provenance anyone acts on.
STEP_ORIGINATING_SYSTEM = "Loft"

#: Binary STL layout: 80-byte header + uint32 triangle count, then 50 bytes
#: per triangle (normal + 3 vertices as float32 triples + uint16 attribute).
STL_HEADER_BYTES = 84
STL_TRIANGLE_RECORD_BYTES = 50

#: The one part every 3MF (OPC) package must carry — the model XML that holds
#: the unit declaration, the meshes and the build items. Sanity-checked after
#: every write, and the thing a reader opens.
THREE_MF_MODEL_PART = "3D/3dmodel.model"

#: Namespace the pinned 3MF production-extension UUIDs are derived from
#: (determinism decision, module docstring — the 3MF twin of
#: :data:`STEP_EXPORT_TIMESTAMP`). lib3mf mints a fresh random UUID per object,
#: per component, per build item and for the build itself on every write, which
#: is five nondeterministic byte ranges in a file whose geometry is identical.
#: A 3MF package is self-contained — the production extension's UUIDs matter for
#: referencing BETWEEN packages, which we never emit — so pinning them costs
#: nothing a consumer can observe and buys the RESEARCH §9 gate.
THREE_MF_UUID_NAMESPACE = uuid.UUID("1cbe3d7c-1f0e-5f4a-9d3e-2b7a5c6f4e10")


def export_step_bytes(shape: BodyShape, *, name: str | None = None) -> bytes:
    """Export *shape* as a STEP AP214 part 21 file (exact B-rep, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    :class:`~build123d.Compound` of a multi-body part's solids (multi-body §MB-0);
    a STEP file holds multiple solids natively (valid AP214). Deterministic: the
    creation timestamp is pinned (module docstring).

    *name* becomes the file's ``PRODUCT`` name and its ``FILE_NAME`` name field:
    ``PRODUCT('Motor Mount Bracket')`` instead of the OCCT default
    ``PRODUCT('SOLID')`` (audit N4 — the exported file was the one place the
    part's name never appeared). ``None`` falls back to the shape's own
    ``label``, and an unlabelled shape keeps OCCT's defaults, so callers that
    have no name to give get the file they got before.

    Driven through :func:`_write_step_document` rather than build123d's
    ``export_step`` (STEPNAME-2), which is what fixes the two things a
    single-body STEP got wrong: it hardcodes ``'build123d'`` as the originating
    system with no parameter, and it builds the label through the defaulted
    ``ExtendedString`` overload, so every non-ASCII part name landed
    double-encoded (:func:`_xcaf_name`). Neither is reachable from a caller. The
    file's SHAPE is unchanged — :func:`_single_body_xde_document` rebuilds the
    same document build123d builds, byte-equivalence asserted — so no consumer
    sees a level, a product or an occurrence that was not there before.

    A welcome consequence: the caller's shape is no longer MUTATED. The old path
    had to borrow ``shape.label`` (build123d reads the name off it) and restore
    it in a ``finally``; the name now goes straight onto the XDE label instead.
    """
    # ``or None`` reproduces build123d's own ``if node.label:`` truthiness test,
    # so an EMPTY name is "no name" rather than ``PRODUCT('')`` — the fallback to
    # ``shape.label`` is what a caller that pre-labelled its body used to get
    # (``export_step`` read the name off the shape), kept so this path is inert
    # for every existing caller.
    header_name = (name if name is not None else shape.label) or None
    doc = _single_body_xde_document(shape, header_name)
    data = _write_step_document(doc, header_name)
    if not data.startswith(STEP_MAGIC):
        raise RuntimeError("STEP export produced a non-part-21 payload")
    return data


def export_stl_bytes(
    shape: BodyShape, linear_deflection: float, angular_deflection: float
) -> bytes:
    """Export *shape* as a binary STL (faceted, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    multi-body :class:`~build123d.Compound` (multi-body §MB-0); STL emits every
    triangle of every solid. Deflection semantics match the GLB tessellation path
    (module docstring).

    Raises:
        ValueError: if a deflection is not strictly positive (the API layer
            rejects these at validation time; this guards direct kernel use).
    """
    if linear_deflection <= 0 or angular_deflection <= 0:
        raise ValueError(
            "Deflections must be strictly positive, got "
            f"linear={linear_deflection}, angular={angular_deflection}"
        )
    # StlAPI_Writer only speaks paths — write to a tempfile like the GLB
    # exporter does. The path never leaks into binary STL output.
    with tempfile.TemporaryDirectory(prefix="loft-stl-") as tmp:
        target = Path(tmp) / "shape.stl"
        ok = export_stl(
            shape,
            target,
            tolerance=linear_deflection,
            angular_tolerance=angular_deflection,
            ascii_format=False,
        )
        if not ok:
            raise RuntimeError("STL export failed")
        data = target.read_bytes()
    if len(data) < STL_HEADER_BYTES:
        raise RuntimeError("STL export produced a truncated payload")
    return data


def _three_mf_model(mesher: Mesher) -> Lib3MF.Model:
    """``mesher.model``, narrowed from lib3mf's un-annotated ``Model | None``.

    ``Lib3MF.Wrapper.CreateModel`` carries no return annotation, so pyright
    infers Optional from its body and every call through ``mesher.model`` is an
    ``reportOptionalMemberAccess`` error. Narrowing HERE, once, keeps that
    diagnostic switched on for the rest of this module rather than blanket-
    disabling it in the file header — the same reasoning as the scoped OCP
    ignores above. The ``None`` branch is unreachable in practice (lib3mf raises
    ``ELib3MFException`` on a failed create), so it is stated as an assertion
    about the library, not as a handled path.
    """
    model = mesher.model
    if model is None:  # pragma: no cover - lib3mf raises before returning None
        raise RuntimeError("lib3mf produced no model to write")
    return model


class MeshExportNotManifoldError(Exception):
    """3MF refuses a body whose TRIANGULATION is not manifold and oriented.

    Found by the EXPORT-2 golden sweep, not predicted: the whole 51-model
    inventory writes clean 3MF except ``mirror-revolve-groove-tangent-wall``,
    whose mesh has exactly ONE non-manifold edge — the 8 mm segment on the
    revolve axis where the two mirrored groove lobes meet, with 4 triangles
    round it instead of 2 (measured: V 513, F 1024, E 1535, chi = 1).

    That is not a meshing bug to work around; it is the solid genuinely
    touching itself along a line, and the 3MF core specification requires a
    model-type object to be manifold. STL writes such a body happily *because
    STL has no topology at all* — which is precisely the failure class 3MF
    exists to eliminate, so quietly emitting a spec-violating package would
    throw away the reason to support the format. The body is fine: it is
    ``BRepCheck``-valid, STEP round-trips it to 1e-7, and STL still works.

    Same posture as :class:`~geometry.kernel.degenerate` (RESEARCH §9): DETECT
    the condition and degrade to a typed error naming the fix, never a 500 and
    never a file that lies.
    """

    def __init__(self, message: str, *, code: str = "export_mesh_not_manifold") -> None:
        super().__init__(message)
        self.code = code


#: What a user can actually do about :class:`MeshExportNotManifoldError`. Named
#: once because the part and assembly paths both raise it.
_NOT_MANIFOLD_MESSAGE = (
    "This body's surface touches itself along a line (a tangency or a knife "
    "edge where two lumps meet), so it cannot be written as the manifold mesh "
    "the 3MF specification requires - and a slicer would reject or silently "
    "repair it. Export STEP (exact B-rep) or STL instead, or give the contact "
    "some width with a small fillet or clearance."
)


def _add_shape_or_refuse(
    mesher: Mesher,
    shape: BodyShape,
    linear_deflection: float,
    angular_deflection: float,
) -> None:
    """``Mesher.add_shape``, with lib3mf's bare refusal turned into a diagnosis.

    build123d raises ``RuntimeError("3mf mesh is invalid")`` — a sentence with
    no cause in it — so this ASKS the model which mesh object is unhappy and
    why, rather than matching on that string (which would silently mis-attribute
    the day build123d rewords it, or the day a different failure wears the same
    exception). Only a mesh that lib3mf itself reports as non-manifold becomes
    the typed error; anything else propagates unchanged.
    """
    try:
        mesher.add_shape(
            shape,
            linear_deflection=linear_deflection,
            angular_deflection=angular_deflection,
        )
    except RuntimeError as exc:
        objects = _three_mf_model(mesher).GetMeshObjects()
        while objects.MoveNext():
            if not objects.GetCurrentMeshObject().IsManifoldAndOriented():
                raise MeshExportNotManifoldError(_NOT_MANIFOLD_MESSAGE) from exc
        raise


def _canonicalise_3mf_ids(mesher: Mesher) -> None:
    """Pin every production-extension UUID and drop the unread components objects.

    The determinism half (RESEARCH §9, module docstring): lib3mf mints a random
    UUID for each object, component, build item and the build itself, so two
    writes of the SAME mesh differ in five places — measured, and it also moves
    the compressed length, so a digest comparison catches it but a size check
    does not. Each id is replaced by a ``uuid5`` of its slot in
    :data:`THREE_MF_UUID_NAMESPACE`, which is a pure function of the package's
    shape.

    The tidying half: ``build123d.mesher.Mesher.add_shape`` adds a components
    object beside every mesh ("Not sure is this is required...") that no build
    item references. Removing it is what makes ``<object>`` count == body count,
    which is the property the 3MF gate asserts and the one a slicer shows.

    Ordering is the enumeration order lib3mf hands back, which follows resource
    creation order — itself request order — so the pinning is stable across runs
    rather than merely constant within one.
    """
    model = _three_mf_model(mesher)
    components = model.GetComponentsObjects()
    unreferenced = []
    while components.MoveNext():
        unreferenced.append(components.GetCurrentComponentsObject())
    for resource in unreferenced:
        model.RemoveResource(resource)

    objects = model.GetObjects()
    index = 0
    while objects.MoveNext():
        objects.GetCurrentObject().SetUUID(
            str(uuid.uuid5(THREE_MF_UUID_NAMESPACE, f"object-{index}"))
        )
        index += 1

    items = model.GetBuildItems()
    index = 0
    while items.MoveNext():
        items.GetCurrent().SetUUID(
            str(uuid.uuid5(THREE_MF_UUID_NAMESPACE, f"item-{index}"))
        )
        index += 1

    model.SetBuildUUID(str(uuid.uuid5(THREE_MF_UUID_NAMESPACE, "build")))


def _write_3mf(mesher: Mesher) -> bytes:
    """Canonicalise *mesher*'s ids and serialise it to 3MF package bytes."""
    _canonicalise_3mf_ids(mesher)
    buffer = io.BytesIO()
    mesher.write_stream(buffer, "3mf")
    data = buffer.getvalue()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise RuntimeError("3MF export produced a non-OPC payload")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if THREE_MF_MODEL_PART not in package.namelist():
            raise RuntimeError(
                f"3MF export produced a package without {THREE_MF_MODEL_PART}"
            )
    return data


def _name_new_meshes(mesher: Mesher, first: int, name: str | None) -> None:
    """Name the mesh objects *mesher* gained since index *first*.

    Named HERE rather than through ``Shape.label`` because
    ``Mesher.add_shape`` reads the label of each CHILD of a compound, so a
    multi-body part (``Compound`` of solids, §MB-0) would take its children's
    labels and ignore the document name entirely — and setting labels on the
    caller's solids is a mutation an export must not make (the same reason
    :func:`export_step_bytes` stopped borrowing ``shape.label`` when it took over
    its own writer).
    """
    if name is None:
        return
    for mesh in mesher.meshes[first:]:
        mesh.SetName(name)


def export_3mf_bytes(
    shape: BodyShape,
    linear_deflection: float,
    angular_deflection: float,
    *,
    name: str | None = None,
) -> bytes:
    """Export *shape* as a 3MF package (faceted, units DECLARED as millimetres).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    multi-body :class:`~build123d.Compound` (multi-body §MB-0), which becomes ONE
    3MF OBJECT PER SOLID rather than STL's undifferentiated triangle soup. That,
    plus the explicit unit in the model XML, is the whole reason this format
    exists next to STL: an STL is a bag of triangles at an unstated scale, and
    every slicer in 2026 would rather be told.

    Meshing is ``BRepMesh_IncrementalMesh`` with the same relative-linear /
    angular settings the STL and GLB paths use, so a given deflection pair means
    the same facets in all three files. *name* names the 3MF objects (the label a
    slicer shows in its object list); ``None`` leaves them unnamed.

    Raises:
        ValueError: if a deflection is not strictly positive (the API layer
            rejects these at validation time; this guards direct kernel use).
    """
    if linear_deflection <= 0 or angular_deflection <= 0:
        raise ValueError(
            "Deflections must be strictly positive, got "
            f"linear={linear_deflection}, angular={angular_deflection}"
        )
    mesher = Mesher(unit=Unit.MM)
    _add_shape_or_refuse(mesher, shape, linear_deflection, angular_deflection)
    _name_new_meshes(mesher, 0, name)
    return _write_3mf(mesher)


def export_glb_bytes(shape: BodyShape, linear_deflection: float) -> bytes:
    """Export *shape* as binary glTF — **metres, Y-up** (module docstring).

    Deliberately NOT a second meshing path: this is
    :func:`~geometry.kernel.tessellate.tessellate_glb`'s payload verbatim, the
    same bytes the viewport is served for the same body and deflection (the mesh
    store is keyed on their sha256, so an export and a tessellation of one body
    are one artifact). Its determinism is therefore the tessellation path's,
    already gated, and there is no way for the exported mesh to drift from the
    displayed one.

    The angular deflection is fixed service-wide on that path
    (``tessellate.ANGULAR_DEFLECTION``), which is why this signature takes only
    the linear one — an export that honoured a caller's angular setting would
    have to mesh again and would stop being the viewport's file.

    Raises:
        ValueError: if *linear_deflection* is not strictly positive (delegated).
    """
    glb, _stats = tessellate_glb(shape, linear_deflection)
    return glb


@dataclass(frozen=True)
class AssemblyComponent:
    """One instance to compose into an assembly export — body + world pose + name.

    ``body`` is a resolved part :data:`BodyShape` in its LOCAL frame;
    ``translation`` / ``quaternion`` (the latter ``(x, y, z, w)``, matching
    :class:`py_kit.schemas.assemblies.Quat`) are its SOLVED world placement; the
    exporter positions the body by ``world = R(q)·local + t``. ``name`` becomes
    the STEP PRODUCT / occurrence name (traceability back to the instance).
    """

    name: str
    body: BodyShape
    translation: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]


def placement_trsf(
    translation: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> gp_Trsf:
    """THE assembly rigid-placement transform: ``world = R(q)·local + t``.

    The single source of the quaternion→``gp_Trsf`` conversion (CLAUDE.md DRY
    rule) — the STEP composer (:func:`_instanced_shape`), the STL composer and
    the interference check (:mod:`geometry.kernel.interference`) all position a
    solved instance through here, so no path reinvents it (rotation order
    geometry-QA-verified to 1e-14). ``quaternion`` is ``(x, y, z, w)``, matching
    :class:`py_kit.schemas.assemblies.Quat`. Deterministic: a fixed sequence of
    OCCT ops on the numeric pose.
    """
    qx, qy, qz, qw = quaternion
    rotation = gp_Quaternion(qx, qy, qz, qw)
    rotation.Normalize()  # belt-and-braces; the solver already emits unit q
    trsf = gp_Trsf()
    trsf.SetRotation(rotation)
    tx, ty, tz = translation
    trsf.SetTranslationPart(gp_Vec(tx, ty, tz))
    return trsf


def place_body(
    body: BodyShape,
    translation: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> BodyShape:
    """COPY *body* to a world placement (:func:`placement_trsf`).

    Returns an independent copy: build123d's ``.located`` deep-copies the B-rep
    (``BRepBuilderAPI_Copy``), so the placed body shares no geometry with the
    part body or with a sibling instance. That is what the interference check
    and the STL composer need — a boolean can invalidate its ARGUMENT in place
    (RESEARCH §9), and one instance's clash test must not be able to corrupt
    every other instance of the same part.

    The STEP composer deliberately does NOT use this: instancing requires the
    occurrences to SHARE a ``TShape`` (module docstring, :func:`_instanced_shape`).
    """
    return body.located(Location(placement_trsf(translation, quaternion)))


def _placed_body(component: AssemblyComponent) -> BodyShape:
    """Copy *component*'s body to its world placement (see :func:`place_body`)."""
    return place_body(component.body, component.translation, component.quaternion)


def _instanced_shape(component: AssemblyComponent) -> TopoDS_Shape:
    """*component*'s body MOVED to its world placement, sharing its ``TShape``.

    The STEP composer's placement (module docstring): ``TopoDS_Shape.Moved``
    returns a new shape over the SAME underlying ``TopoDS_TShape``, so N
    occurrences of one part are recognisably one B-rep and OCCT's XCAF instance
    detection collapses them into one ``PRODUCT`` + N occurrences. The copying
    :func:`place_body` cannot do this — it is a deep geometric copy by
    construction, which is why the pre-instancing exporter wrote N identical
    solids. Safe here because nothing in the write path mutates a shape.
    """
    trsf = placement_trsf(component.translation, component.quaternion)
    return component.body.wrapped.Moved(TopLoc_Location(trsf))


#: Matches the id (first) field of every ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` in a
#: part-21 file — one of the two byte ranges OCCT's assembly writer fills from a
#: process-global counter. The name/reference fields that follow are untouched.
_NAUO_ID_RE = re.compile(rb"(NEXT_ASSEMBLY_USAGE_OCCURRENCE\(')([^']*)(')")

#: Matches the write counter inside the PRODUCT id/name OCCT gives an UNNAMED
#: shape — ``'Open CASCADE STEP translator 7.9 N.M.K'``, where the prefix is the
#: ``write.step.product.name`` static's value, ``N`` is the process-global write
#: counter (the nondeterministic part) and ``M.K`` index the component and its
#: sub-shape within THIS write (both deterministic). The version is matched as
#: ``[\d.]+`` so an OCCT point release does not silently stop matching; the
#: phrase itself is asserted against OCCT's own static by
#: ``test_assembly_export``, so an upstream rewording fails loudly rather than
#: quietly restoring the nondeterminism.
_TRANSLATOR_PRODUCT_RE = re.compile(
    rb"(Open CASCADE STEP translator [\d.]+ )(\d+)((?:\.\d+)*)"
)


def occt_default_product_name() -> str:
    """OCCT's OWN ``write.step.product.name`` — what :data:`_TRANSLATOR_PRODUCT_RE`
    hardcodes half of.

    The pattern above matches a literal OCCT phrase, so an upstream rewording
    would make it match nothing and silently restore the nondeterminism — the
    quiet failure, since a canonicaliser that canonicalises nothing raises no
    error. Exposed so the gate can compare the two readings rather than assert
    our own constant against itself, and here (not in the test) because this is
    the module that owns the OCP import and the ``reportMissingTypeStubs``
    relaxation the un-stubbed wheel needs.

    Initialises the controller first: the static is empty until it has run, and
    an empty prefix would make any pattern derived from it match everything.
    """
    STEPControl_Controller.Init_s()
    return str(Interface_Static.CVal_s("write.step.product.name"))


def _renumber_in_appearance_order(pattern: re.Pattern[bytes], data: bytes) -> bytes:
    """Rewrite *pattern*'s counter group (2) to its FIRST-APPEARANCE rank.

    Group 1 and group 3 are the surrounding text and are re-emitted verbatim.
    Equal counters map to equal ranks, so the transform preserves whatever
    identity structure OCCT authored while erasing the absolute values — which
    are the process-global part.
    """
    ranks: dict[bytes, bytes] = {}

    def _renumber(match: re.Match[bytes]) -> bytes:
        rank = ranks.setdefault(match.group(2), str(len(ranks) + 1).encode("ascii"))
        return match.group(1) + rank + match.group(3)

    return pattern.sub(_renumber, data)


def _canonicalise_writer_counters(data: bytes) -> bytes:
    """Pin every label OCCT fills from a PROCESS-GLOBAL counter (RESEARCH §9).

    There are two such byte ranges, and they are the same defect twice:

    * the ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` id, incremented per occurrence and
      persisting across writer invocations in a worker (measured: one assembly's
      four occurrences write ``3,1,2,4`` then ``7,5,6,8`` on the next export);
    * the PRODUCT id and name OCCT gives an UNNAMED shape — ``'Open CASCADE STEP
      translator 7.9 N.M.K'`` — whose leading ``N`` counts writes in the process
      (STEPDET-1: ``1.1.1`` on the first export, ``2.1.1`` on the second).

    The second only appears when a component's body is a ``Compound``, i.e. when
    a MULTI-BODY part (§MB-0) is instanced: OCCT then wraps the component in an
    extra assembly level whose per-body children we do not name, so they fall
    back to that defaulted label. Every shipped assembly golden was a single
    ``Solid`` part until ``assembly-two-multibody-brackets``, which is why the
    in-process AND interpreter-restart determinism gates passed for months while
    the property they assert was false — the fixture never reached the code path.

    Both are arbitrary LABELS: STEP cross-references use ``#N`` entity ids, never
    these strings, and the counter identifies nothing about the model. Rewriting
    each to its first-appearance rank is therefore semantically inert and makes
    identical requests byte-identical, in-process and across a worker restart.
    """
    return _renumber_in_appearance_order(
        _TRANSLATOR_PRODUCT_RE, _renumber_in_appearance_order(_NAUO_ID_RE, data)
    )


#: The occurrence suffix an instance name carries ("Dowel Pin 8x24 <17>"). The
#: shared PRODUCT names the PART, so the suffix is stripped off the first
#: occurrence's name to recover it (:func:`_product_name`).
_OCCURRENCE_SUFFIX_RE = re.compile(r"\s*<\d+>\s*$")


def _product_name(instance_name: str) -> str:
    """The shared PRODUCT name for a part, from one of its instance names.

    ``"Dowel Pin 8x24 <17>"`` → ``"Dowel Pin 8x24"``. Instances are named
    ``<part name> <n>`` by convention (``InstanceName``, assemblies §1.2), and a
    STEP PRODUCT under instancing names the PART — the occurrence number belongs
    on the NAUO, which carries the un-stripped instance name. A name that carries
    no suffix (a renamed instance) is used verbatim: the product is then named
    after the first occurrence in request order, which is deterministic and still
    traceable, and is strictly better than the ``PRODUCT('SOLID')`` a nameless
    export would write.
    """
    stripped = _OCCURRENCE_SUFFIX_RE.sub("", instance_name).strip()
    return stripped or instance_name


def _xcaf_name(text: str) -> TCollection_ExtendedString:
    """A user-facing name as an OCCT wide string, WITHOUT double-encoding it.

    ``TCollection_ExtendedString(str)`` binds to the overload whose second
    argument is ``isMultiByte=False``, which walks the Python string's UTF-8
    bytes ONE BYTE AT A TIME and stores each as a character. Every non-ASCII name
    therefore reached the file mojibaked, and the corruption was the recoverable-
    looking kind that survives every gate: ``"Flänsch"`` measured **17
    characters instead of 13** and landed in the STEP as the UTF-8 encoding of
    its own latin-1 misreading (STEPNAME-1). Passing ``isMultiByte=True`` is the
    documented "this is UTF-8" overload; measured, the same name then reads back
    as exactly 13 characters and the PRODUCT literal decodes UTF-8 to the string
    that was submitted, for accents, a degree sign, an em dash and CJK alike.

    This matters more than it looks. A STEP file is what a user hands to a
    machinist or a supplier, so the component names in it are read by a human in
    someone else's CAD — and a name is the one field where being *almost* right
    is indistinguishable from being wrong. It is also the trap
    :func:`_product_name` walks into: it strips an occurrence suffix by regex,
    and a mojibaked name is a DIFFERENT string, so the part/instance split was
    being computed on corrupted text as well.

    Apostrophes need nothing here and are asserted anyway: OCCT's part-21 writer
    already doubles them (``'Jim''s bracket'``), which is the standard's own
    escape, so the naive worry about quoting is measured rather than guarded
    against twice.
    """
    return TCollection_ExtendedString(text, True)


def _xde_document(auto_naming: bool) -> tuple[TDocStd_Document, XCAFDoc_ShapeTool]:
    """An empty XDE document in millimetres, plus its shape tool.

    The boilerplate both writer paths need, named once (CLAUDE.md DRY rule) and
    byte-faithful to ``build123d.exporters3d._create_xde``'s preamble — same
    storage format, same application, same ``SetLengthUnit_s``.

    *auto_naming* is the one thing the two paths disagree about, and it is a real
    difference rather than an oversight. The SINGLE-BODY path leaves it ON, so an
    unnamed export still writes ``PRODUCT('SOLID')`` exactly as it always has; the
    ASSEMBLY path turns it OFF, because there our labels ARE the names and OCCT's
    auto-naming would overwrite the shared part label we set deliberately.
    """
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    application = XCAFApp_Application.GetApplication_s()
    application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    application.InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1 / UNITS_PER_METER[Unit.MM])
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    shape_tool.SetAutoNaming_s(auto_naming)
    return doc, shape_tool


def _single_body_xde_document(shape: BodyShape, name: str | None) -> TDocStd_Document:
    """The XDE document a SINGLE-BODY export transfers — ONE shape, no assembly.

    ``AddShape(..., makeAssembly=False)``: a part is one shape at the document
    root, so nothing here interposes an assembly level, emits a
    ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` or adds a ``PRODUCT`` the file did not
    have. That is deliberate and it is the whole reason STEPNAME-2 could be fixed
    without changing what a consumer's CAD reads: this rebuilds the document
    build123d's ``_create_xde`` builds for a shape with no children, so the file's
    SHAPE is unchanged and only the two fields that were wrong move. Asserted, not
    asserted-by-hope — ``test_step_names_part`` pins byte-equivalence against a
    build123d-configured write for a named solid, an unnamed solid, and both for a
    multi-body ``Compound`` (which stays ONE product with two
    ``MANIFOLD_SOLID_BREP``, because a build123d ``Compound`` carries no anytree
    children for ``PreOrderIter`` to walk).

    *name* is set through :func:`_xcaf_name`, which is the fix: build123d names
    the label with the defaulted ``ExtendedString`` overload, so every non-ASCII
    part name reached the file double-encoded (STEPNAME-2). ``None`` sets no name
    at all, leaving OCCT's auto-naming to write ``PRODUCT('SOLID')`` as before.
    """
    doc, shape_tool = _xde_document(auto_naming=True)
    label = shape_tool.AddShape(shape.wrapped, False)
    if name is not None:
        TDataStd_Name.Set_s(label, _xcaf_name(name))
    shape_tool.UpdateAssemblies()
    return doc


def _assembly_xde_document(
    assembly_name: str, components: Sequence[AssemblyComponent]
) -> TDocStd_Document:
    """Build the XDE document the assembly writer transfers (module docstring).

    One compound of :func:`_instanced_shape`-placed occurrences goes in through
    ``AddShape(..., makeAssembly=True)``; OCCT's instance detection gives every
    UNIQUE part one label and every occurrence a reference to it. We then name
    the labels: occurrence label → instance name (the NAUO), shared part label →
    :func:`_product_name` of its FIRST occurrence (the PRODUCT). Deterministic:
    the compound is built in request order and the components come back in that
    order, so both the numbering and the chosen product name are fixed by the
    request.
    """
    # Our labels ARE the names; auto-naming would overwrite them (the single-body
    # path keeps it on for the same reason it is off here — it names per-child,
    # we name per-part).
    doc, shape_tool = _xde_document(auto_naming=False)

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for component in components:
        builder.Add(compound, _instanced_shape(component))

    root = shape_tool.AddShape(compound, True)
    TDataStd_Name.Set_s(root, _xcaf_name(assembly_name))

    occurrences = TDF_LabelSequence()
    XCAFDoc_ShapeTool.GetComponents_s(root, occurrences)
    if occurrences.Length() != len(components):
        raise RuntimeError(
            "assembly STEP export lost an occurrence: "
            f"{occurrences.Length()} placed for {len(components)} components"
        )
    named_parts: list[TDF_Label] = []
    for index, component in enumerate(components, start=1):
        occurrence = occurrences.Value(index)
        TDataStd_Name.Set_s(occurrence, _xcaf_name(component.name))
        part = TDF_Label()
        if not XCAFDoc_ShapeTool.GetReferredShape_s(occurrence, part) or part.IsNull():
            continue
        if any(part.IsEqual(seen) for seen in named_parts):
            continue  # a later occurrence of an already-named part
        named_parts.append(part)
        TDataStd_Name.Set_s(part, _xcaf_name(_product_name(component.name)))
    shape_tool.UpdateAssemblies()
    return doc


def _write_step_document(doc: TDocStd_Document, header_name: str | None) -> bytes:
    """Transfer *doc* through ``STEPCAFControl_Writer`` to part-21 bytes.

    THE writer for every STEP this service emits, part and assembly alike (there
    is no longer a second one — STEPNAME-2). Configured exactly as build123d's
    ``export_step`` configures it — same session, same name / colour / layer
    modes, same precision + p-curve statics, same pinned ``FILE_NAME`` timestamp
    — so it is byte-equivalent to build123d for the same XDE document, which is
    the property that let the part path move here without changing what a
    consumer reads. Only the originating system differs, deliberately
    (:data:`STEP_ORIGINATING_SYSTEM`).

    *header_name* is ``FILE_NAME``'s first field. ``None`` leaves it unset, which
    is how an unnamed export keeps OCCT's ``'Open CASCADE Shape Model'`` default
    — build123d skips the call for a shape with no label and so do we.
    """
    # Disable writing OCCT info to console (build123d does the same).
    messenger = Message.DefaultMessenger_s()
    for printer in messenger.Printers():
        printer.SetTraceLevel(Message_Gravity.Message_Fail)

    session = XSControl_WorkSession()
    writer = STEPCAFControl_Writer(session, False)
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)

    header = APIHeaderSection_MakeHeader(writer.Writer().Model())
    if not header.IsDone():  # as in OCCT 7.9.x
        header = APIHeaderSection_MakeHeader(0)
        header.Apply(writer.Writer().Model())
    if header_name is not None:
        header.SetName(TCollection_HAsciiString(header_name))
    header.SetTimeStamp(TCollection_HAsciiString(STEP_EXPORT_TIMESTAMP.isoformat()))
    # The file says who AUTHORED it, not which binding drove OCCT
    # (STEPNAME-1 — see :data:`STEP_ORIGINATING_SYSTEM`).
    header.SetOriginatingSystem(TCollection_HAsciiString(STEP_ORIGINATING_SYSTEM))

    STEPCAFControl_Controller.Init_s()
    STEPControl_Controller.Init_s()
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    Interface_Static.SetIVal_s("write.precision.mode", PrecisionMode.AVERAGE.value)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)

    buffer = io.BytesIO()
    if writer.WriteStream(buffer) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError("assembly STEP export failed")
    return buffer.getvalue()


def export_step_assembly_bytes(
    assembly_name: str, components: Sequence[AssemblyComponent]
) -> bytes:
    """Export *components* as ONE AP214 STEP with INSTANCED product structure.

    Every UNIQUE part is written once as a named ``PRODUCT``; every component
    becomes an occurrence of it at its solved world placement, named after its
    instance. Re-opening the file recovers every body at its placement, traceable
    to its instance name, and a downstream tool can tell that twenty occurrences
    of a dowel pin ARE one part (RESEARCH §10/§11; audit N8 — module docstring
    for the encoding and for why ``located()`` used to defeat this).

    Deterministic (RESEARCH §9): the creation timestamp is pinned and both
    process-global writer counters are canonicalised
    (:func:`_canonicalise_writer_counters`), so identical requests are
    byte-identical in-process and across an interpreter restart — including when
    a component is a MULTI-BODY part.

    Raises:
        ValueError: if *components* is empty (nothing to place — the caller maps
            this to a clean 422, never a zero-solid file).
    """
    if not components:
        raise ValueError("assembly STEP export requires at least one placed body")
    doc = _assembly_xde_document(assembly_name, components)
    data = _canonicalise_writer_counters(_write_step_document(doc, assembly_name))
    if not data.startswith(STEP_MAGIC):
        raise RuntimeError("assembly STEP export produced a non-part-21 payload")
    return data


def export_stl_assembly_bytes(
    components: Sequence[AssemblyComponent],
    linear_deflection: float,
    angular_deflection: float,
) -> bytes:
    """Export *components* as ONE binary STL with placements baked in (faceted).

    STL carries no product structure, so the solved world placements are baked
    into a single :class:`~build123d.Compound` of every instance's positioned
    body and emitted through the SAME mesher as the single-body path
    (:func:`export_stl_bytes`). Deflection semantics match tessellation.

    Raises:
        ValueError: if *components* is empty, or a deflection is not strictly
            positive (delegated to :func:`export_stl_bytes`).
    """
    if not components:
        raise ValueError("assembly STL export requires at least one placed body")
    compound = Compound([_placed_body(component) for component in components])
    return export_stl_bytes(compound, linear_deflection, angular_deflection)


def export_3mf_assembly_bytes(
    components: Sequence[AssemblyComponent],
    linear_deflection: float,
    angular_deflection: float,
) -> bytes:
    """Export *components* as ONE 3MF with one NAMED OBJECT per instance.

    The closest a mesh format gets to the STEP path's product structure, and the
    reason this is not just "STL with a unit": 3MF carries multiple objects in
    one package, so twenty dowel pins arrive as twenty named, individually
    selectable objects at their solved placements instead of one merged triangle
    soup. It does NOT instance them — every occurrence carries its own mesh, so
    unlike the STEP export this file still scales with the fastener count; the
    format's ``<components>`` encoding could fix that and is deferred (nothing
    in the product yet needs a 3MF small enough to care).

    Bodies are placed with the copying :func:`place_body`, per instance, and
    added one instance at a time so each instance's meshes can be named after it
    — a multi-body part contributes several 3MF objects and they should all
    carry the instance's name, which is exactly what a single bulk ``add_shape``
    could not express.

    Raises:
        ValueError: if *components* is empty, or a deflection is not strictly
            positive.
    """
    if not components:
        raise ValueError("assembly 3MF export requires at least one placed body")
    if linear_deflection <= 0 or angular_deflection <= 0:
        raise ValueError(
            "Deflections must be strictly positive, got "
            f"linear={linear_deflection}, angular={angular_deflection}"
        )
    mesher = Mesher(unit=Unit.MM)
    for component in components:
        first = len(mesher.meshes)
        _add_shape_or_refuse(
            mesher, _placed_body(component), linear_deflection, angular_deflection
        )
        _name_new_meshes(mesher, first, component.name)
    return _write_3mf(mesher)


def export_glb_assembly_bytes(
    components: Sequence[AssemblyComponent], linear_deflection: float
) -> bytes:
    """Export *components* as ONE binary glTF with placements baked in.

    The same compound the STL composer builds, through
    :func:`export_glb_bytes` — so an assembly download and the assembly the
    viewport draws are the same mesh, in **metres and Y-up** (module docstring).
    glTF has a node hierarchy that could carry the instance names, but reaching
    it means writing our own XDE document rather than reusing the tessellation
    payload, and the payload-reuse property is worth more than names in a format
    whose job is "show this to someone without CAD" (3MF is the mesh format that
    keeps the structure).

    Raises:
        ValueError: if *components* is empty, or the deflection is not positive.
    """
    if not components:
        raise ValueError("assembly GLB export requires at least one placed body")
    compound = Compound([_placed_body(component) for component in components])
    return export_glb_bytes(compound, linear_deflection)
