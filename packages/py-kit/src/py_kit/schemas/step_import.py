"""Assembly STEP import boundary DTOs — the structured product-structure read.

The inverse contract of the assembly export (:mod:`py_kit.schemas.assemblies`
``ExportAssemblyRequest``): where export composes a solved assembly into ONE
AP214 STEP with named PRODUCTs at solved placements, this reads such a STEP back
into N structured products — each a PRODUCT **name**, a world **placement**, an
editable **LOCAL-frame B-rep** (a STEP fragment), and content-addressed
presentation/analysis surfaces (mesh + mass properties) — plus a
``has_assembly_structure`` flag. Pure pydantic only: no kernel (OCP/build123d)
type appears here (CLAUDE.md service boundaries); the geometry service resolves
the XDE product tree internally and surfaces only these plain models (the B-rep
as plain STEP text, never a kernel object), and ``just gen`` exports them to
``packages/contracts`` / ``packages/ts-client``.

Each product carries the editable body as ``body_step`` — a LOCAL-frame STEP
AP214 fragment (placement stripped), exactly what the single-body ``import``
feature ingests — content-addressed by ``body_step_id`` and shared across
repeated occurrences of one part (the dedup contract, as meshes share
``mesh_glb_id``). ``mesh_glb_id`` is the shared presentation mesh; ``properties``
the body's own mass properties.

This slice (2a: geometry-side reader, hardened — the DoS bound is now wired and
the walk/tessellate phase is guarded) returns the structured result; SLICE-2b
(documents assembly-document creation + a gateway upload endpoint) turns each
product into a positioned, named Loft instance — seeding each part's ``import``
feature with ``ImportParamsV1(data=body_step)`` (zero new ingest path) and
grouping by ``body_step_id`` — and wires the ``has_assembly_structure=False`` case
to the existing single-body MB-4b import.
"""

from pydantic import BaseModel, Field

from py_kit.schemas.assemblies import Placement
from py_kit.schemas.features import MAX_INLINE_STEP_CHARS
from py_kit.schemas.geometry import DEFAULT_LINEAR_DEFLECTION, ShapeProperties


class StepAssemblyImportRequest(BaseModel):
    """Read an assembly STEP into its structured product list (geometry-side).

    ``data`` is the STEP AP214 part-21 TEXT inline, bounded/non-empty by
    :data:`~py_kit.schemas.features.MAX_INLINE_STEP_CHARS` (the SAME cap the
    single-body :class:`~py_kit.schemas.features.ImportParamsV1` uses) — an
    oversize or empty payload is a request-validation 422 at the boundary, never
    a per-request geometry error. ``linear_deflection`` is the presentation
    tessellation parameter for each product's shared mesh (never persisted).
    Deterministic (RESEARCH §9): the geometry service pins the read unit to mm,
    so the same bytes yield an identical structured result and byte-identical
    per-product meshes across rebuilds and interpreter restarts.
    """

    data: str = Field(
        min_length=1,
        max_length=MAX_INLINE_STEP_CHARS,
        description="Assembly STEP AP214 part-21 file text (inline). Bounded / "
        "non-empty at parse time (422); parsed into positioned, named products "
        "by the geometry service (product structure when present, else one "
        "single-body product with has_assembly_structure=false).",
    )
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description="Presentation tessellation parameter (mm) for each product's "
        "shared mesh; never persisted",
    )


class ImportedProduct(BaseModel):
    """One product recovered from an assembly STEP — name + placement + body.

    ``name`` is the STEP PRODUCT name (``None`` when the file names no product —
    the caller supplies a fallback instance name). ``placement`` is the
    product's WORLD pose (reusing :class:`~py_kit.schemas.assemblies.Placement` —
    identity for a flat single-body STEP), matched to the exported placement
    within the kernel round-trip tolerance.

    Two body surfaces, both content-addressed and SHARED across repeated
    occurrences of one part (the dedup contract, as slice 1 does for meshes):

    * ``body_step`` — the product's editable **LOCAL-frame B-rep**, as a STEP
      AP214 part-21 fragment with the instance placement STRIPPED (that is
      ``placement``, kept separate). It is exactly what the single-body
      ``import`` feature ingests (:class:`~py_kit.schemas.features.ImportParamsV1`
      ``data``), so the documents service seeds each part with ``ImportParamsV1(
      data=body_step)`` — ZERO new ingest path. A mesh is not editable geometry;
      this is the field that lets 2b build a REAL part per instance.
    * ``mesh_glb_id`` — a content-addressed presentation mesh for the viewport.

    ``body_step_id`` is the content address (``sha256:<hex>``) of ``body_step``;
    it is EQUAL for two occurrences of one part, so the caller groups products by
    it to create ONE stored B-rep (one part) with N instances. ``properties`` are
    the body's OWN (local-frame) mass properties for BOM / inspection.
    """

    name: str | None = Field(
        description="STEP PRODUCT name, or null when the file names no product"
    )
    placement: Placement = Field(
        description="World placement of this product (identity for a flat STEP)"
    )
    body_step: str | None = Field(
        default=None,
        description="The product's LOCAL-frame B-rep as a STEP AP214 part-21 "
        "fragment (placement stripped — see `placement`); consumed verbatim as "
        "ImportParamsV1.data to seed an editable part (the single-body import "
        "path). Null when the product produced no solid.",
    )
    body_step_id: str | None = Field(
        default=None,
        description="Content address (sha256:<hex>) of `body_step`; EQUAL across "
        "repeated occurrences of one part, so the caller creates ONE part and N "
        "instances (the dedup key, as meshes share mesh_glb_id). Null when no solid.",
    )
    mesh_glb_id: str | None = Field(
        description="Content-addressed shared presentation mesh (sha256:<hex>), "
        "or null when the product produced no mesh"
    )
    properties: ShapeProperties | None = Field(
        default=None,
        description="The product body's own (local-frame) mass properties",
    )


class StepAssemblyImportResult(BaseModel):
    """Structured read of an assembly STEP — the product list + structure flag.

    ``has_assembly_structure`` is True when the file carried
    ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` product structure (multiple positioned,
    named products); False for a flat / single-body STEP, whose single product
    signals the caller to fall back to the single-body MB-4b import (backward
    compatible). ``products`` are in the deterministic order the geometry service
    walks the product tree (RESEARCH §9).
    """

    has_assembly_structure: bool = Field(
        description="True when the file carried NAUO product structure; False for "
        "a flat / single-body STEP (fall back to single-body import)"
    )
    products: list[ImportedProduct] = Field(
        description="Recovered products, in deterministic product-tree order"
    )
