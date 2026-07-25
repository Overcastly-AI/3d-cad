"""Assembly STEP import — structured product-tree read to boundary DTO (§4).

The interop sibling of the assembly export (:mod:`geometry.assembly.export` /
``POST /api/v1/assembly/export``): where export composes a solved assembly into
one AP214 STEP, this reads such a STEP back into N structured products for the
documents service to turn into positioned, named Loft instances (BACKLOG
"Assembly STEP import with product structure").

Pipeline:

1. :func:`~geometry.kernel.step_assembly.read_step_assembly` runs the untrusted
   XCAF read + product-tree walk in a **killable subprocess** (the CPU-time +
   wall-clock DoS bound — design §6) into per-product
   ``{name, world placement, LOCAL-frame kernel body}`` plus the
   ``has_assembly_structure`` flag (the mirror of the export's XCAF composer).
2. Each UNIQUE product body is turned ONCE into (a) a LOCAL-frame STEP AP214
   fragment — ``body_step``, the exact input the single-body ``import`` feature
   ingests (:class:`py_kit.schemas.features.ImportParamsV1`), so slice 2b seeds N
   editable parts with ZERO new ingest path — plus its content address
   ``body_step_id``; (b) a content-addressed presentation mesh
   (:mod:`geometry.mesh_store`, reused); and (c) its mass properties. Repeated
   occurrences of one part have a byte-identical LOCAL body → identical fragment,
   id, and mesh (the §6.4 dedup contract, applied to import), so the caller
   collapses them into ONE stored B-rep with N instances; the per-body work runs
   once, keyed by the body's BREP content address.

Never-500 (design §5, mirroring the single-body import taxonomy): a
malformed / bodyless / adversarial file surfaces as a typed
:class:`~geometry.kernel.imports.ImportParseError` /
:class:`~geometry.kernel.imports.ImportParseTimeoutError` /
:class:`~geometry.kernel.imports.ImportNoSolidError`, which the API layer maps to
a clean 422 envelope — including a transferable-but-degenerate solid that fails
the post-transfer tessellate/measure/export here. Deterministic (RESEARCH §9):
the read pins units to mm and the per-product artifacts are content-addressed, so
the same bytes yield an identical result in-process and across an interpreter
restart.
"""

from __future__ import annotations

import hashlib

from py_kit.schemas.assemblies import Placement, Quat
from py_kit.schemas.geometry import ShapeProperties, Vec3
from py_kit.schemas.step_import import (
    MAX_IMPORT_RESPONSE_BYTES,
    ImportedProduct,
    StepAssemblyImportRequest,
    StepAssemblyImportResult,
)

from geometry.kernel import (
    export_step_bytes,
    measure_shape,
    solid_to_brep_bytes,
    tessellate_glb,
)
from geometry.kernel.imports import (
    ImportNoSolidError,
    ImportParseError,
    ImportResponseTooLargeError,
)
from geometry.kernel.step_assembly import ReadProduct, read_step_assembly
from geometry.mesh_store import mesh_glb_key, store_mesh_glb


def _placement(product: ReadProduct) -> Placement:
    """The product's WORLD placement as a :class:`Placement` DTO."""
    tx, ty, tz = product.translation
    qx, qy, qz, qw = product.quaternion
    return Placement(
        position=Vec3(x=tx, y=ty, z=tz),
        orientation=Quat(x=qx, y=qy, z=qz, w=qw),
    )


def _step_import_bounds() -> tuple[float, float]:
    """The configured (CPU-time, wall-clock) bounds for the untrusted parse (§6).

    Resolved from ``GeometrySettings`` (the SAME knobs the single-body import
    reads — ``step_import_timeout_seconds`` / ``step_import_wall_timeout_seconds``)
    rather than hardcoded, so the assembly reader's DoS ceiling is tuned by one
    config surface. Imported lazily to avoid a cycle (``geometry.main`` imports
    the API which imports this module).
    """
    from geometry.main import GeometrySettings

    settings = GeometrySettings()
    return (
        settings.step_import_timeout_seconds,
        settings.step_import_wall_timeout_seconds,
    )


def import_step_assembly(
    request: StepAssemblyImportRequest,
) -> StepAssemblyImportResult:
    """Read an assembly STEP into structured, positioned, named products (§4).

    Reuses :func:`~geometry.kernel.step_assembly.read_step_assembly` (the killable
    XCAF read + product-tree walk) then, per UNIQUE product body, exports a
    LOCAL-frame STEP fragment + tessellates + measures ONCE (keyed by the body's
    BREP content address, so a part instanced twice does the work once and its two
    instances share one stored B-rep, mesh, and mass properties — distinct
    placements). Never raises for a geometry outcome beyond the typed import errors
    (mapped to a clean 422 by the API layer): the reader's parse/timeout/no-solid
    errors propagate, and a transferable-but-degenerate solid that fails the
    per-product export/tessellate/measure here is wrapped into an
    :class:`~geometry.kernel.imports.ImportParseError` (design §5). Deterministic
    (RESEARCH §9; module docstring).

    Two response-amplification bounds keep an untrusted parse's OUTPUT bounded
    (slice-2b security review), both surfacing as typed 422s at the API layer:
    the reader rejects a file whose leaf-occurrence count exceeds
    :data:`~py_kit.schemas.step_import.MAX_IMPORT_ASSEMBLY_PRODUCTS`
    (:class:`~geometry.kernel.imports.ImportTooManyProductsError`, inside the
    CPU-bounded child), and this service rejects once the running total of emitted
    ``body_step`` bytes would exceed
    :data:`~py_kit.schemas.step_import.MAX_IMPORT_RESPONSE_BYTES`
    (:class:`~geometry.kernel.imports.ImportResponseTooLargeError`), the absolute
    bound that also catches one large body instanced many times.
    """
    cpu_timeout_s, wall_timeout_s = _step_import_bounds()
    read = read_step_assembly(
        request.data, cpu_timeout_s=cpu_timeout_s, wall_timeout_s=wall_timeout_s
    )

    # Cache the per-body artifacts keyed by the LOCAL body's BREP content address:
    # two occurrences of one part have byte-identical BREP → one export, one
    # tessellation, one measure, one stored B-rep (the §6.4 dedup contract). The
    # content-addressed mesh store makes the mesh sharing automatic; the STEP
    # fragment + its id are shared explicitly so the caller (slice 2b) groups
    # repeated products into ONE part + N instances by body_step_id.
    # The running total of emitted body_step bytes, checked against
    # MAX_IMPORT_RESPONSE_BYTES BEFORE materialising each product. This is the
    # ABSOLUTE amplification bound the occurrence-count cap cannot catch: the
    # result carries body_step once PER occurrence, so one large body instanced
    # many times (under both the occurrence cap and the 16 MiB upload cap) would
    # still amplify — this rejects it as a typed 422 (slice-2b security review).
    # The cached tuple carries the body_step byte length so a repeated occurrence
    # (cache hit) still adds its emitted bytes to the total without a re-encode.
    cache: dict[str, tuple[str, str, str, ShapeProperties, int]] = {}
    products: list[ImportedProduct] = []
    emitted_bytes = 0
    for product in read.products:
        try:
            body_key = mesh_glb_key(solid_to_brep_bytes(product.body))
            cached = cache.get(body_key)
            if cached is None:
                step_bytes = export_step_bytes(product.body)
                body_step = step_bytes.decode("utf-8")
                body_step_id = f"sha256:{hashlib.sha256(step_bytes).hexdigest()}"
                glb, _stats = tessellate_glb(product.body, request.linear_deflection)
                mesh_id = store_mesh_glb(glb)
                properties = measure_shape(product.body)
                cached = (body_step, body_step_id, mesh_id, properties, len(step_bytes))
                cache[body_key] = cached
        except (ImportParseError, ImportNoSolidError):
            raise
        except Exception as exc:  # degenerate solid → typed 422, never a raw 500
            raise ImportParseError(
                "The assembly STEP transferred but a product could not be "
                "meshed, measured, or re-exported; it may be geometrically "
                "degenerate."
            ) from exc
        body_step, body_step_id, mesh_id, properties, body_step_len = cached
        emitted_bytes += body_step_len
        if emitted_bytes > MAX_IMPORT_RESPONSE_BYTES:
            # Reject BEFORE appending this product, so the response is never
            # materialised past the ceiling regardless of occurrence count.
            raise ImportResponseTooLargeError(
                "The assembly STEP would produce more editable-body data than the "
                "import limit allows. Split it into smaller sub-assemblies and try "
                "again."
            )
        products.append(
            ImportedProduct(
                name=product.name,
                placement=_placement(product),
                mesh_glb_id=mesh_id,
                body_step=body_step,
                body_step_id=body_step_id,
                properties=properties,
            )
        )

    return StepAssemblyImportResult(
        has_assembly_structure=read.has_assembly_structure, products=products
    )
