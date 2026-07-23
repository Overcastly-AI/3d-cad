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

**Hard parse bound — the SAME killable-subprocess DoS ceiling the single-body
reader applies (design §6, BACKLOG P1).** An assembly STEP is untrusted external
input and OCCT's XCAF transfer is not guaranteed linear in input size, so a
degenerate/adversarial part-21 can be super-linear and pin its worker. The read
therefore runs the untrusted ``ReadFile`` → ``Transfer`` **and** the product-tree
walk in a **separate, killable process**
(:mod:`geometry.kernel._step_assembly_parse_worker`) under a **CPU-time**
``RLIMIT_CPU`` ceiling (the contention-invariant primary bound) plus a generous
**wall-clock** liveness backstop, reusing
:func:`geometry.kernel.imports.run_bounded_parse_worker` — the ONE bound both
readers share. A killed parse is reaped and surfaces as
:class:`~geometry.kernel.imports.ImportParseTimeoutError` → ``import_parse_timeout``.

The walk runs in the child (not the parent) because the XDE document does not
survive a SaveAs/Open round-trip in this OCP build, so the child serialises each
leaf occurrence as ``(name, world placement, LOCAL-frame BREP file)`` and the
parent reads that back, applying only the build123d normalisation
(:func:`~geometry.kernel.lumps.assemble_lumps`) here where it is tested. So no
kernel-object taxonomy is duplicated, only relocated off the parent's unbounded
in-process path.

**Body taxonomy (MB-4b, reused).** Each product's prototype is normalised
through :func:`~geometry.kernel.lumps.assemble_lumps` exactly like the
single-body import: one solid → a bare :class:`~build123d.Solid`; two or more
disjoint solids → one lump-sorted :class:`~build123d.Compound`. Non-solid
reference geometry in a product is dropped; an import that recovers NO solid
product at all is an honest :class:`~geometry.kernel.imports.ImportNoSolidError`.

**Determinism (RESEARCH §9).** The read is a pure function of the file bytes
plus the process-global ``Interface_Static`` unit setting, which is pinned to
millimetres in the worker's fresh process on every call so the result is
independent of process history. The product order follows the deterministic
XDE component order of the fixed bytes; each placement's quaternion is read
straight off the ``gp_Trsf`` (measured to match the exported placement to 1e-12).

**Never-500 posture (design §5).** Every failure mode is wrapped into a typed
:class:`~geometry.kernel.imports.ImportParseError` /
:class:`~geometry.kernel.imports.ImportParseTimeoutError` /
:class:`~geometry.kernel.imports.ImportNoSolidError` — the same taxonomy the
single-body reader raises — so the caller maps a bad file to a clean per-request
error, never an unhandled 500. Both the worker's read/transfer/walk phase (a
non-zero exit) AND the parent's post-transfer body normalisation (a raise on a
transferable-but-degenerate solid) resolve to one of those typed errors.

Kernel objects never leave ``geometry.kernel``: :class:`ReadProduct` is
service-internal (its ``body`` is a kernel shape), and the service layer
(:func:`geometry.assembly.import_step.import_step_assembly`) converts it to the
pure-pydantic boundary DTO.

The OCP wheel ships no type stubs, so the raw BREP calls below are opaque to
pyright; the directives scope that relaxation to this file only (same posture as
:mod:`geometry.kernel.imports`), and the fully-typed :class:`ReadProduct` /
:class:`StepAssemblyRead` results keep the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass

from build123d import Solid
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from py_kit.schemas.step_import import MAX_IMPORT_ASSEMBLY_PRODUCTS

from geometry.kernel.imports import (
    DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S,
    DEFAULT_STEP_IMPORT_WALL_TIMEOUT_S,
    ImportNoSolidError,
    ImportParseError,
    read_brep_shape,
    run_bounded_parse_worker,
)
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape

#: Absolute path of the OCP-only assembly parse worker (a sibling module), invoked
#: BY PATH (not ``-m``) so the spawn does not drag in ``geometry.kernel.__init__``
#: (build123d + every kernel module, ~3 s of cold-start); by path it is ~0.9 s of
#: OCP alone. Referenced as a file, not imported, so there is no partial-package-
#: init coupling with ``geometry.kernel``.
_ASSEMBLY_WORKER_PATH = os.path.join(
    os.path.dirname(__file__), "_step_assembly_parse_worker.py"
)


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


def read_step_assembly(
    step_text: str,
    *,
    cpu_timeout_s: float = DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S,
    wall_timeout_s: float = DEFAULT_STEP_IMPORT_WALL_TIMEOUT_S,
    max_products: int = MAX_IMPORT_ASSEMBLY_PRODUCTS,
) -> StepAssemblyRead:
    """Parse *step_text* into a structured, positioned, named product list.

    Walks the XDE product tree (module docstring): an assembly root expands into
    one product per occurrence — its PRODUCT name, WORLD placement, and
    LOCAL-frame body — while a flat / single-body STEP returns ONE product at
    identity with ``has_assembly_structure=False`` (the backward-compatible
    fallback signal). The untrusted OCCT read + walk runs in a killable
    subprocess bounded by a CPU-time ceiling (*cpu_timeout_s*, the primary DoS
    bound, invariant to machine load) and a wall-clock liveness backstop
    (*wall_timeout_s*) — design §6, the SAME bound the single-body reader applies.
    The walk also aborts inside that CPU-bounded child once the leaf-occurrence
    count exceeds *max_products* — the response-amplification count cap (slice-2b),
    so a file with thousands of tiny ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` lines is
    rejected before the parent builds a product for each. Deterministic (units
    pinned to mm in the worker; RESEARCH §9).

    Raises:
        ImportTooManyProductsError: the file's leaf-occurrence count exceeded
            *max_products* (``import_too_many_products``) — a response-amplification
            DoS bound, rejected inside the CPU-bounded child.
        ImportParseTimeoutError: the read exceeded its CPU-time ceiling or the
            wall-clock backstop and the worker was killed (``import_parse_timeout``).
        ImportParseError: OCCT could not read/transfer/walk the payload (bad/empty/
            truncated STEP, worker non-zero exit), OR a transferred-but-degenerate
            product failed the parent's body normalisation — the same code the
            single-body reader raises (``import_parse_failed``).
        ImportNoSolidError: the file parsed but yielded NO solid product
            (surfaces-only / wireframe / open shells) — ``import_no_solid``.
    """
    with tempfile.TemporaryDirectory(prefix="loft-step-assembly-") as tmp:
        in_path = os.path.join(tmp, "assembly.step")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir)
        with open(in_path, "wb") as handle:
            handle.write(step_text.encode("utf-8"))
        run_bounded_parse_worker(
            [
                sys.executable,
                _ASSEMBLY_WORKER_PATH,
                in_path,
                out_dir,
                repr(cpu_timeout_s),
                str(max_products),
            ],
            cpu_timeout_s=cpu_timeout_s,
            wall_timeout_s=wall_timeout_s,
        )
        # Post-transfer: read the worker's manifest + per-product BREPs and apply
        # the build123d body normalisation HERE. A transferable-but-degenerate
        # solid can raise in assemble_lumps/Solid extraction — wrap it so any
        # post-transfer failure is a typed ImportParseError, never a raw 500
        # (design §5, consistent with the single-body taxonomy).
        try:
            with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as fh:
                manifest = json.load(fh)
            products: list[ReadProduct] = []
            for entry in manifest["products"]:
                body = _body_from_shape(
                    read_brep_shape(os.path.join(out_dir, entry["brep"]))
                )
                if body is None:
                    continue
                products.append(
                    ReadProduct(
                        name=entry["name"],
                        body=body,
                        translation=tuple(entry["translation"]),
                        quaternion=tuple(entry["quaternion"]),
                    )
                )
            has_assembly_structure = bool(manifest["has_assembly_structure"])
        except (ImportParseError, ImportNoSolidError):
            raise
        except Exception as exc:  # degenerate solid / corrupt manifest → typed 422
            raise ImportParseError(
                "The assembly STEP transferred but a product could not be "
                "normalised into a body; it may be geometrically degenerate."
            ) from exc

    if not products:
        raise ImportNoSolidError(
            "The assembly STEP file transferred no solids; it may contain only "
            "surfaces, wireframe, or annotations, or no importable product."
        )
    return StepAssemblyRead(
        has_assembly_structure=has_assembly_structure, products=products
    )
