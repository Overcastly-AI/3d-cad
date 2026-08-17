"""CAD file export — STEP (exact B-rep) and three faceted meshes (STL, 3MF, GLB).

Uses build123d's exporters (OCCT ``STEPControl_Writer`` / ``StlAPI_Writer`` /
``RWGltf_CafWriter``, and lib3mf via ``build123d.mesher.Mesher``, underneath).
Every output is **byte-deterministic** for identical requests (RESEARCH §9); the
geometry export gate asserts it:

* **STEP:** OCCT stamps the file's ``FILE_NAME`` record with the wall-clock
  creation time — the one nondeterministic byte range in the output. We pin
  it to :data:`STEP_EXPORT_TIMESTAMP` via ``export_step(timestamp=...)``
  (decision + evidence recorded in docs/GEOMETRY-QA.md, gap #4). Exporting
  through ``BytesIO`` also keeps filesystem paths out of the file — the
  ``FILE_NAME`` name field stays the fixed writer default, verified on
  build123d 0.11.1.
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

*Why no MAPPED_ITEM.* AP214 has two encodings for "this geometry, placed there":
``MAPPED_ITEM``/``REPRESENTATION_MAP`` (a representation re-used inside another
representation) and the assembly product structure above. OCCT's XCAF writer
emits the latter, which is the encoding every MCAD assembly exchange uses — the
audit's ``MAPPED_ITEM`` count was a proxy for "is anything instanced at all",
and the measurable that actually answers it is ``MANIFOLD_SOLID_BREP`` count ==
unique part count (asserted on the emitted bytes by ``test_assembly_export``).

Determinism (RESEARCH §9): the pinned timestamp above applies unchanged. The one
EXTRA nondeterministic byte range this path introduces is a **process-global**
occurrence counter OCCT stamps into each ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` id
(it increments across writer invocations within a worker, so a second export of
the same graph would differ); we canonicalise it to appearance order
(:func:`_canonicalise_occurrence_ids`) so identical requests stay byte-identical
(decision + evidence in docs/GEOMETRY-QA.md). The NAUO id is an arbitrary label
— STEP cross-references use ``#N`` entity ids, not this string — so renumbering
it is semantically inert.

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
    export_step,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
    export_stl,  # pyright: ignore[reportUnknownVariableType]
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
    part's name never appeared). ``None`` leaves the default, so callers that
    have no name to give are byte-identical to before. The label is restored
    afterwards: build123d's ``label`` is a plain attribute on the caller's shape,
    and an export must not rename the body it was handed.
    """
    previous_label = shape.label
    try:
        if name is not None:
            shape.label = name
        buffer = io.BytesIO()
        if not export_step(shape, buffer, timestamp=STEP_EXPORT_TIMESTAMP):
            raise RuntimeError("STEP export failed")
    finally:
        shape.label = previous_label
    data = buffer.getvalue()
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
    :func:`export_step_bytes` restores the label it borrows).
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
#: part-21 file — the one byte range OCCT's assembly writer fills from a
#: process-global counter. The name/reference fields that follow are untouched.
_NAUO_ID_RE = re.compile(rb"(NEXT_ASSEMBLY_USAGE_OCCURRENCE\(')([^']*)(')")


def _canonicalise_occurrence_ids(data: bytes) -> bytes:
    """Renumber ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` ids to appearance order (§9).

    OCCT stamps each usage occurrence's id string from a counter that persists
    ACROSS writer invocations in a worker process, so a second export of the
    same graph would differ only in those ids. The id is an arbitrary label
    (STEP cross-refs use ``#N`` entity ids, never this string), so rewriting it
    to a deterministic ``1..N`` in file order — itself deterministic — makes the
    whole file byte-identical for identical requests without touching geometry.
    """
    counter = 0

    def _renumber(match: re.Match[bytes]) -> bytes:
        nonlocal counter
        counter += 1
        return match.group(1) + str(counter).encode("ascii") + match.group(3)

    return _NAUO_ID_RE.sub(_renumber, data)


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
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    application = XCAFApp_Application.GetApplication_s()
    application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    application.InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1 / UNITS_PER_METER[Unit.MM])
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    # Our labels ARE the names; auto-naming would overwrite them (build123d's
    # export_step keeps it on for the same reason it is off here — it names
    # per-child, we name per-part).
    shape_tool.SetAutoNaming_s(False)

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for component in components:
        builder.Add(compound, _instanced_shape(component))

    root = shape_tool.AddShape(compound, True)
    TDataStd_Name.Set_s(root, TCollection_ExtendedString(assembly_name))

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
        TDataStd_Name.Set_s(occurrence, TCollection_ExtendedString(component.name))
        part = TDF_Label()
        if not XCAFDoc_ShapeTool.GetReferredShape_s(occurrence, part) or part.IsNull():
            continue
        if any(part.IsEqual(seen) for seen in named_parts):
            continue  # a later occurrence of an already-named part
        named_parts.append(part)
        TDataStd_Name.Set_s(
            part, TCollection_ExtendedString(_product_name(component.name))
        )
    shape_tool.UpdateAssemblies()
    return doc


def _write_step_document(doc: TDocStd_Document, header_name: str) -> bytes:
    """Transfer *doc* through ``STEPCAFControl_Writer`` to part-21 bytes.

    The writer half of build123d's ``export_step`` (same session, same name /
    colour / layer modes, same precision + p-curve statics, same pinned
    ``FILE_NAME`` timestamp), driven directly so the assembly path can name the
    SHARED part label itself (module docstring). Byte-equivalent to what
    build123d writes for the same XDE document.
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
    header.SetName(TCollection_HAsciiString(header_name))
    header.SetTimeStamp(TCollection_HAsciiString(STEP_EXPORT_TIMESTAMP.isoformat()))
    header.SetOriginatingSystem(TCollection_HAsciiString("build123d"))

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

    Deterministic (RESEARCH §9): the creation timestamp is pinned and the
    per-occurrence id counter is canonicalised, so identical requests are
    byte-identical in-process and across an interpreter restart.

    Raises:
        ValueError: if *components* is empty (nothing to place — the caller maps
            this to a clean 422, never a zero-solid file).
    """
    if not components:
        raise ValueError("assembly STEP export requires at least one placed body")
    doc = _assembly_xde_document(assembly_name, components)
    data = _canonicalise_occurrence_ids(_write_step_document(doc, assembly_name))
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
