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

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from py_kit.schemas.assemblies import (
    AssemblyGraphResponse,
    AssemblyName,
    Placement,
)
from py_kit.schemas.features import MAX_INLINE_STEP_CHARS
from py_kit.schemas.geometry import DEFAULT_LINEAR_DEFLECTION, ShapeProperties
from py_kit.schemas.parts import PartResponse

#: Upper bound on how many products (== instances) a single assembly-STEP upload
#: may create. A DoS ceiling on the POST-transfer fan-out (documents-side part /
#: feature / instance creation, and the per-product body/mesh work the geometry
#: reader does): the byte-size upload cap alone is insufficient because a small
#: STEP can encode a pathological ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` count. The
#: gateway enforces this on the geometry read result BEFORE driving documents
#: (so no partial assembly is ever created), and documents re-checks it as
#: defense-in-depth. A few hundred instances comfortably covers real assemblies
#: while bounding the fan-out (slice-2a security review, 2026-07-23).
MAX_IMPORT_ASSEMBLY_PRODUCTS = 500

#: Absolute ceiling (bytes) on the TOTAL ``body_step`` payload the geometry read
#: may emit across all products — a response-amplification DoS bound (slice-2b
#: security review, 2026-07-23). The occurrence-count cap
#: (:data:`MAX_IMPORT_ASSEMBLY_PRODUCTS`) alone does NOT bound the response size:
#: because the result carries ``body_step`` once per occurrence, ONE large body
#: (near the 16 MiB single-body ingest cap) instanced up to the occurrence cap can
#: still amplify into a multi-GB response the gateway buffers whole. The geometry
#: service tracks the running total of emitted ``body_step`` bytes and rejects
#: (``import_response_too_large``, a typed 422) before materialising a product past
#: this ceiling, so the amplification is bounded ABSOLUTELY regardless of
#: occurrence count or body repetition. Sized at 2x
#: :data:`~py_kit.schemas.features.MAX_INLINE_STEP_CHARS` (== 32 MiB): a single
#: product body is bounded by that 16 MiB inline cap, and 2x leaves headroom for a
#: real assembly of several distinct large-ish part bodies while capping the
#: buffered response at a defensible ceiling. (The P2 follow-up that carries
#: ``body_step`` once per ``body_step_id`` — a cross-service DTO reshape — makes
#: the shape efficient; this byte cap makes the CURRENT shape safe without it.)
MAX_IMPORT_RESPONSE_BYTES = 2 * MAX_INLINE_STEP_CHARS


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


# --- documents-creation contract (gateway → documents, SLICE-2b) -----------------
#
# The inverse of the geometry read above, one hop further in: the gateway forwards
# the identity-free :class:`StepAssemblyImportResult` (plus the caller's chosen
# document name) to documents, which turns it into a REAL Loft graph — an assembly
# document with one part per unique ``body_step_id`` (deduped) and one named
# instance per product at its placement, or (``has_assembly_structure=False``) a
# single-body part (the MB-4b fallback). Pure pydantic — documents never imports
# the kernel; it consumes only these plain models (CLAUDE.md service boundaries).


class ImportAssemblyRequest(BaseModel):
    """documents-side request: materialise a geometry read into Loft documents.

    ``result`` is the geometry service's structured read (forwarded verbatim by
    the gateway); ``name`` is the caller-chosen name for the created document —
    the assembly name (``has_assembly_structure=True``) or the single part's name
    (the MB-4b fallback). Each product's editable ``body_step`` seeds a part's
    ``import`` feature (:class:`~py_kit.schemas.features.ImportParamsV1` — ZERO new
    ingest path), products sharing a ``body_step_id`` collapse to ONE part with N
    instances, and the whole graph is created atomically (all-or-nothing — a
    failure leaves no orphan docs).
    """

    name: AssemblyName = Field(
        description="Name for the created document — the assembly's name (product "
        "structure present) or the single part's name (single-body fallback)"
    )
    result: StepAssemblyImportResult = Field(
        description="The geometry service's structured read of the uploaded STEP"
    )


class AssemblyImportResult(BaseModel):
    """A STEP that carried product structure became a Loft assembly (SLICE-2b).

    ``assembly`` is the freshly-created assembly graph (its N named instances at
    their imported placements, ready to render — the same read model every other
    assembly route serves). ``part_ids`` are the DEDUPED part documents created:
    one per unique ``body_step_id``, so a part occurring twice is ONE id here but
    two instances in ``assembly.instances``.
    """

    kind: Literal["assembly"] = "assembly"
    assembly: AssemblyGraphResponse = Field(
        description="The created assembly with its instances at imported placements"
    )
    part_ids: list[uuid.UUID] = Field(
        description="Deduped part documents created (one per unique body_step_id)"
    )


class SingleBodyImportResult(BaseModel):
    """A flat STEP became a single-body part — the MB-4b fallback (SLICE-2b).

    Backward-compatible with the pre-assembly import: one part document seeded
    with the ``import`` base feature, no assembly. ``tree_version`` is the part's
    post-import concurrency token (1 — the single import feature).
    """

    kind: Literal["part"] = "part"
    part: PartResponse = Field(description="The created single-body part")
    tree_version: int = Field(
        description="The part's concurrency token after the import feature (== 1)"
    )


#: What a STEP upload created: an assembly (product structure) or a single part
#: (flat file). Discriminated on ``kind`` so the gateway/web can branch by field.
StepImportResponse = Annotated[
    AssemblyImportResult | SingleBodyImportResult,
    Field(discriminator="kind"),
]
