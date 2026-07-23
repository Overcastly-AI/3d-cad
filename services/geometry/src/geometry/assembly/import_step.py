"""Assembly STEP import — structured product-tree read to boundary DTO (§4).

The interop sibling of the assembly export (:mod:`geometry.assembly.export` /
``POST /api/v1/assembly/export``): where export composes a solved assembly into
one AP214 STEP, this reads such a STEP back into N structured products for the
documents service to turn into positioned, named Loft instances (BACKLOG
"Assembly STEP import with product structure").

Pipeline:

1. :func:`~geometry.kernel.step_assembly.read_step_assembly` walks the XDE
   product tree (``STEPCAFControl_Reader`` → ``XCAFDoc_ShapeTool``) into
   per-product ``{name, world placement, LOCAL-frame kernel body}`` plus the
   ``has_assembly_structure`` flag (the mirror of the export's XCAF composer).
2. Each UNIQUE product body is tessellated ONCE and stored content-addressed
   (:mod:`geometry.mesh_store`, reused), so two occurrences of one part share a
   single mesh (the §6.4 dedup contract, applied to import), and its mass
   properties are measured. The service builds the pure-pydantic
   :class:`StepAssemblyImportResult` — no kernel type crosses the boundary.

Never-500 (design §4.3, mirroring the single-body import taxonomy): a
malformed / bodyless file surfaces as a typed
:class:`~geometry.kernel.imports.ImportParseError` /
:class:`~geometry.kernel.imports.ImportNoSolidError`, which the API layer maps to
a clean 422 envelope. Deterministic (RESEARCH §9): the read pins units to mm and
the per-product meshes are content-addressed, so the same bytes yield an
identical result in-process and across an interpreter restart.
"""

from __future__ import annotations

from py_kit.schemas.assemblies import Placement, Quat
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.step_import import (
    ImportedProduct,
    StepAssemblyImportRequest,
    StepAssemblyImportResult,
)

from geometry.kernel import measure_shape, tessellate_glb
from geometry.kernel.step_assembly import ReadProduct, read_step_assembly
from geometry.mesh_store import store_mesh_glb


def _placement(product: ReadProduct) -> Placement:
    """The product's WORLD placement as a :class:`Placement` DTO."""
    tx, ty, tz = product.translation
    qx, qy, qz, qw = product.quaternion
    return Placement(
        position=Vec3(x=tx, y=ty, z=tz),
        orientation=Quat(x=qx, y=qy, z=qz, w=qw),
    )


def import_step_assembly(
    request: StepAssemblyImportRequest,
) -> StepAssemblyImportResult:
    """Read an assembly STEP into structured, positioned, named products (§4).

    Reuses :func:`~geometry.kernel.step_assembly.read_step_assembly` (the XDE
    product-tree walk) then tessellates + stores each UNIQUE product body once
    (content-addressed dedup) and measures its mass properties. Never raises for
    a geometry outcome beyond the typed import errors the reader emits (mapped to
    a clean 422 by the API layer). Deterministic (RESEARCH §9; module docstring).
    """
    read = read_step_assembly(request.data)

    # Repeated occurrences of one part have byte-identical local BREP → identical
    # GLB → the SAME content-addressed mesh id (the §6.4 dedup contract): the
    # content-addressed store makes the sharing automatic (an identical GLB `put`
    # returns the identical key), so no separate dedup bookkeeping is needed.
    products: list[ImportedProduct] = []
    for product in read.products:
        glb, _stats = tessellate_glb(product.body, request.linear_deflection)
        mesh_id = store_mesh_glb(glb)
        products.append(
            ImportedProduct(
                name=product.name,
                placement=_placement(product),
                mesh_glb_id=mesh_id,
                properties=measure_shape(product.body),
            )
        )

    return StepAssemblyImportResult(
        has_assembly_structure=read.has_assembly_structure, products=products
    )
