"""Assembly STEP import boundary DTOs — the structured product-structure read.

The inverse contract of the assembly export (:mod:`py_kit.schemas.assemblies`
``ExportAssemblyRequest``): where export composes a solved assembly into ONE
AP214 STEP with named PRODUCTs at solved placements, this reads such a STEP back
into N structured products — each a PRODUCT **name**, a world **placement**, and
a content-addressed **body reference** (mesh + mass properties) — plus a
``has_assembly_structure`` flag. Pure pydantic only: no kernel (OCP/build123d)
type appears here (CLAUDE.md service boundaries); the geometry service resolves
the XDE product tree internally and surfaces only these plain models, and
``just gen`` exports them to ``packages/contracts`` / ``packages/ts-client``.

The body is surfaced exactly as the single-body import surfaces an imported body
(docs/design/step-import.md; multi-body §MB-4b): a content-addressed
``mesh_glb_id`` (shared across repeated occurrences of one part — the dedup
contract) plus the body's own :class:`~py_kit.schemas.geometry.ShapeProperties`.
No B-rep crosses the wire.

This slice (geometry-side reader) returns the structured result; the SLICE-2
follow-up (documents assembly-document creation + a gateway upload endpoint)
turns each product into a positioned, named Loft assembly instance and wires the
``has_assembly_structure=False`` case to the existing single-body MB-4b import.
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
    """One product recovered from an assembly STEP — name + placement + body ref.

    ``name`` is the STEP PRODUCT name (``None`` when the file names no product —
    the caller supplies a fallback instance name). ``placement`` is the
    product's WORLD pose (reusing :class:`~py_kit.schemas.assemblies.Placement` —
    identity for a flat single-body STEP), matched to the exported placement
    within the kernel round-trip tolerance. The body is surfaced by reference
    (no B-rep crosses the wire): ``mesh_glb_id`` is a content-addressed
    presentation mesh, SHARED across repeated occurrences of one part (the dedup
    contract), and ``properties`` are the body's OWN (local-frame) mass
    properties for BOM / inspection.
    """

    name: str | None = Field(
        description="STEP PRODUCT name, or null when the file names no product"
    )
    placement: Placement = Field(
        description="World placement of this product (identity for a flat STEP)"
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
