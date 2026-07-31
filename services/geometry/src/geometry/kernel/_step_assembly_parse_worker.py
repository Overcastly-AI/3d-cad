"""Out-of-process assembly-STEP parse — the XCAF read + walk KILL boundary (§6).

Run as ``python <this file> <in.step> <out_dir> <cpu_seconds>``. The sibling of
:mod:`geometry.kernel._step_parse_worker` for the *assembly* reader: where the
single-body worker bounds ``ReadFile`` → ``TransferRoots`` and returns ONE shape,
this bounds the ``STEPCAFControl_Reader`` XDE ``ReadFile`` → ``Transfer`` **and**
the product-tree walk, emitting a per-product structured result. Both untrusted
OCCT phases run HERE, in a process the parent
(:func:`geometry.kernel.step_assembly.read_step_assembly`) spawns under a
**CPU-time** ``RLIMIT_CPU`` ceiling (applied in-child, before any OCCT work) plus
a generous **wall-clock** backstop (``subprocess.run(..., timeout=…)`` in the
parent), so a degenerate/adversarial assembly part-21 is killed and reaped, never
pinning a FastAPI threadpool worker (BACKLOG P1, docs/design/step-import.md §6).

**Why the walk runs here too.** The single-body worker keeps the topology
taxonomy in the parent because the XDE document does not survive a
SaveAs/Open round-trip in this OCP build, so the parent cannot re-walk a
serialised document. Instead the walk — pure OCCT (``XCAFDoc_ShapeTool`` label
traversal, ``TopLoc_Location`` composition, ``TDataStd_Name``), needing NO
build123d — runs in the child, which serialises each leaf occurrence as
``(name, world placement, LOCAL-frame shape)``: the shape as a native BREP file
(OCCT's lossless serialization, the SAME format the single-body worker uses) and
the name/placement in a JSON manifest. The parent reads that back and applies the
build123d normalisation (:func:`~geometry.kernel.lumps.assemble_lumps`) it can
test — so no kernel-object taxonomy is duplicated, only relocated out of the
parent's in-process (unbounded) path. Running the walk under the CPU bound is a
bonus: a transfer that succeeds but whose walk is degenerate is bounded too.

This module imports **only OCP** — never build123d — on purpose: build123d's
import graph adds ~2.5 s of cold-start to every spawn (the single-body worker's
rationale). Units are pinned to millimetres HERE, in the fresh process, so the
read is independent of ambient ``Interface_Static`` state — deterministic given
fixed bytes (RESEARCH §9).

Exit codes are the protocol: ``0`` = the manifest + per-product BREPs were
written; :data:`EXIT_PARSE_FAILED` = OCCT could not read/transfer/walk the bytes.
A SIGKILL/SIGXCPU (timeout) or any other non-zero exit is mapped by the parent to
a parse failure / timeout — a crash in untrusted parsing is never a 500.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import os
import sys

# Run as a script, this file's directory (``geometry/kernel/``) is on
# ``sys.path[0]`` — where its ``types.py`` would SHADOW the stdlib ``types``
# module and break any stdlib import that pulls it (``json`` → ``re`` → ``enum``
# → ``types``), dragging build123d in via a half-initialised package. Strip that
# entry BEFORE importing anything but ``os``/``sys`` (both cached at startup), so
# stdlib resolves cleanly; the CPU-limit helper is then loaded by ABSOLUTE FILE
# PATH (below), never via that directory being on the path.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]

import importlib.util  # noqa: E402
import json  # noqa: E402

# Reuse the ONE CPU-limit helper (DRY) by loading the sibling worker from its
# absolute path — it imports only ``math``/``sys`` at module load (no OCP, no
# build123d, no ``geometry.kernel.__init__``), so this stays a ~0 s, side-effect-
# free import that shares the production ``_apply_cpu_limit``/``EXIT_PARSE_FAILED``.
_spec = importlib.util.spec_from_file_location(
    "_loft_step_parse_worker", os.path.join(_HERE, "_step_parse_worker.py")
)
assert _spec is not None and _spec.loader is not None
_helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helper)
EXIT_PARSE_FAILED: int = _helper.EXIT_PARSE_FAILED
EXIT_TOO_MANY_PRODUCTS: int = _helper.EXIT_TOO_MANY_PRODUCTS
_apply_cpu_limit = _helper._apply_cpu_limit


class _TooManyProducts(Exception):
    """Internal signal: the leaf-occurrence count exceeded the import ceiling.

    Raised the moment the walk emits one product past ``max_products`` so the
    child ABORTS before writing a per-occurrence BREP for every occurrence — the
    response-amplification count cap enforced inside the CPU-bounded child
    (slice-2b DoS hardening). :func:`_walk` maps it to
    :data:`EXIT_TOO_MANY_PRODUCTS`, which the parent turns into a typed 422."""


def _label_name(label: object) -> str | None:
    """The ``TDataStd_Name`` of *label* as a Python string, or ``None``.

    An EMPTY name reads as absent: STEP writers routinely emit ``''`` for a name
    field they have nothing to say about, and "" is not a name a caller could
    show. Returning None lets the occurrence/product fallback below pick the
    other one instead of propagating a blank.
    """
    from OCP.TDataStd import TDataStd_Name

    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):  # type: ignore[attr-defined]
        return str(attr.Get().ToExtString()).strip() or None
    return None


def _placement_of(
    location: object,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """A ``TopLoc_Location`` as ``(translation, (x, y, z, w) quaternion)``.

    Reads the rigid pose straight off the accumulated ``gp_Trsf`` — the exact
    inverse of the ``place_body`` quaternion → ``gp_Trsf`` the export applies.
    """
    trsf = location.Transformation()  # type: ignore[attr-defined]
    quat = trsf.GetRotation()
    xyz = trsf.TranslationPart()
    return (
        (float(xyz.X()), float(xyz.Y()), float(xyz.Z())),
        (float(quat.X()), float(quat.Y()), float(quat.Z()), float(quat.W())),
    )


def _emit(
    shape: object,
    name: str | None,
    location: object,
    out_dir: str,
    products: list[dict[str, object]],
    max_products: int,
) -> None:
    """Serialise one leaf occurrence's LOCAL shape as BREP + append its manifest row.

    Enforces the occurrence-count cap in-child: once appending would push the
    leaf-occurrence count past *max_products*, raise :class:`_TooManyProducts`
    (before writing the offending BREP) so the walk aborts rather than expanding a
    pathological occurrence count into a giant response (slice-2b DoS bound).
    """
    from OCP.BRepTools import BRepTools

    if shape.IsNull():  # type: ignore[attr-defined]
        return
    if len(products) >= max_products:
        raise _TooManyProducts
    translation, quaternion = _placement_of(location)
    brep = f"p{len(products)}.brep"
    BRepTools.Write_s(shape, os.path.join(out_dir, brep))
    products.append(
        {
            "name": name,
            "translation": list(translation),
            "quaternion": list(quaternion),
            "brep": brep,
        }
    )


def _collect_leaf(
    shape_tool: object,
    ref_label: object,
    world_location: object,
    name: str | None,
    out_dir: str,
    products: list[dict[str, object]],
    max_products: int,
) -> None:
    """Emit one product for a leaf occurrence, recursing into a sub-assembly.

    A component references a prototype (*ref_label*); when that prototype is
    itself an assembly (a rigid sub-assembly) the walk recurses, composing the
    child location under *world_location* so every leaf carries its full WORLD
    placement. A leaf prototype's LOCAL shape is emitted; a null prototype is
    dropped (the parent drops non-solid products after normalisation).
    """
    if shape_tool.IsAssembly_s(ref_label):  # type: ignore[attr-defined]
        _collect_components(
            shape_tool, ref_label, world_location, out_dir, products, max_products
        )
        return
    _emit(
        shape_tool.GetShape_s(ref_label),  # type: ignore[attr-defined]
        name,
        world_location,
        out_dir,
        products,
        max_products,
    )


def _collect_components(
    shape_tool: object,
    assembly_label: object,
    parent_location: object,
    out_dir: str,
    products: list[dict[str, object]],
    max_products: int,
) -> None:
    """Walk every component (NAUO occurrence) of an assembly label.

    For each occurrence: compose its location under *parent_location* (so nested
    sub-assemblies accumulate to a world placement), resolve its referred
    prototype, and take the occurrence NAME from the COMPONENT (NAUO) label,
    falling back to the referred PRODUCT label.

    That priority is the instanced-export contract read back (audit N8): under
    AP214 product structure a part is ONE product used N times, so the PRODUCT
    name identifies the PART ("Dowel Pin 8x24") and is necessarily shared by
    every occurrence, while the NAUO name identifies the INSTANCE ("Dowel Pin
    8x24 <17>"). Preferring the product name — as this walk used to — collapsed
    twenty distinct instances to twenty copies of one name. The fallback keeps
    files whose writer names only the product (an occurrence-name-less flat
    export) reading exactly as before.
    """
    from OCP.TDF import TDF_Label, TDF_LabelSequence

    components = TDF_LabelSequence()
    shape_tool.GetComponents_s(assembly_label, components)  # type: ignore[attr-defined]
    for index in range(1, components.Length() + 1):
        component = components.Value(index)
        component_location = shape_tool.GetLocation_s(component)  # type: ignore[attr-defined]
        world_location = parent_location.Multiplied(component_location)  # type: ignore[attr-defined]
        referred = TDF_Label()
        if not shape_tool.GetReferredShape_s(component, referred):  # type: ignore[attr-defined]
            continue
        name = _label_name(component) or _label_name(referred)
        _collect_leaf(
            shape_tool,
            referred,
            world_location,
            name,
            out_dir,
            products,
            max_products,
        )


def _walk(in_path: str, out_dir: str, max_products: int) -> int:
    """Read the assembly STEP, walk the XDE tree, write manifest + BREPs.

    Aborts with :data:`EXIT_TOO_MANY_PRODUCTS` if the leaf-occurrence count
    exceeds *max_products* — the response-amplification count cap, enforced inside
    this CPU-bounded child so the accumulation itself is bounded (slice-2b).
    """
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    # Pin the target unit in THIS process (fresh every spawn → no ambient state).
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    application = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    application.InitDocument(document)

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(in_path) != IFSelect_ReturnStatus.IFSelect_RetDone:
        return EXIT_PARSE_FAILED
    if not reader.Transfer(document):
        return EXIT_PARSE_FAILED

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)

    has_assembly_structure = False
    products: list[dict[str, object]] = []
    try:
        for index in range(1, free.Length() + 1):
            root = free.Value(index)
            root_location = shape_tool.GetLocation_s(root)
            if shape_tool.IsAssembly_s(root):
                has_assembly_structure = True
                _collect_components(
                    shape_tool, root, root_location, out_dir, products, max_products
                )
            else:
                # Flat / single-body free shape: surface the whole located shape as
                # one product at identity — the single-body MB-4b fallback signal.
                _emit(
                    shape_tool.GetShape_s(root),
                    _label_name(root),
                    root_location,
                    out_dir,
                    products,
                    max_products,
                )
    except _TooManyProducts:
        return EXIT_TOO_MANY_PRODUCTS

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {"has_assembly_structure": has_assembly_structure, "products": products},
            handle,
        )
    return 0


def main(argv: list[str]) -> int:
    # argv: <prog> <in_path> <out_dir> <cpu_seconds> <max_products>. The CPU
    # ceiling is applied BEFORE OCCT is imported/run so the ~0.9 s OCP cold-import
    # also counts toward (and is bounded by) the budget. <max_products> is the
    # occurrence-count cap enforced during the walk (slice-2b DoS bound).
    if len(argv) != 5:
        return EXIT_PARSE_FAILED
    try:
        cpu_seconds = float(argv[3])
        max_products = int(argv[4])
    except ValueError:
        return EXIT_PARSE_FAILED
    _apply_cpu_limit(cpu_seconds)
    try:
        return _walk(argv[1], argv[2], max_products)
    except Exception:  # any OCCT read/transfer/walk raise → a parse failure
        return EXIT_PARSE_FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
