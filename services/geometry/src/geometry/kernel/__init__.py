"""Loft geometry kernel layer — the ONLY code in the monorepo that may
import OCP/build123d (CLAUDE.md service boundaries).

Inputs are pydantic DTOs (:mod:`geometry.schemas`); outputs are GLB bytes
plus metadata DTOs. Kernel types (TopoDS/build123d shapes) never cross this
package boundary.
"""

from build123d import Solid

from geometry.kernel.export import export_step_bytes, export_stl_bytes
from geometry.kernel.properties import measure_shape
from geometry.kernel.shapes import build_box, build_cylinder
from geometry.kernel.tessellate import glb_stats, tessellate_glb
from geometry.schemas import (
    BoxParams,
    CylinderParams,
    ExportRequest,
    ShapeRequest,
    TessellateRequest,
    TessellationMetadata,
)

__all__ = [
    "build_box",
    "build_cylinder",
    "build_shape",
    "evaluate_export",
    "evaluate_tessellation",
    "export_step_bytes",
    "export_stl_bytes",
    "glb_stats",
    "measure_shape",
    "tessellate_glb",
]


def build_shape(request: ShapeRequest) -> Solid:
    """Dispatch a validated request to its shape builder.

    Accepts the shared ``ShapeRequest`` base, so tessellation and export
    requests build through the identical path. Dispatch is on the params
    model — ``ShapeRequest`` validation guarantees it matches ``shape`` —
    and ``params`` is a closed union, so pyright checks this match for
    exhaustiveness as new shape kinds land.
    """
    match request.params:
        case BoxParams():
            return build_box(request.params.x, request.params.y, request.params.z)
        case CylinderParams():
            return build_cylinder(request.params.radius, request.params.height)


def evaluate_tessellation(
    request: TessellateRequest,
) -> tuple[bytes, TessellationMetadata]:
    """Core evaluation shared by the REST route and the arq worker task.

    Builds the shape, measures exact B-rep properties, tessellates to GLB.
    Deterministic end to end: identical requests yield identical metadata and
    byte-identical GLB (RESEARCH §9).
    """
    shape = build_shape(request)
    properties = measure_shape(shape)
    glb, mesh = tessellate_glb(shape, request.linear_deflection)
    return glb, TessellationMetadata(properties=properties, mesh=mesh)


def evaluate_export(request: ExportRequest) -> bytes:
    """Build the requested shape and export it in the requested format.

    Deterministic end to end: identical requests yield byte-identical files
    (RESEARCH §9; see :mod:`geometry.kernel.export` for the STEP timestamp
    pinning that makes this true).
    """
    shape = build_shape(request)
    match request.format:
        case "step":
            return export_step_bytes(shape)
        case "stl":
            return export_stl_bytes(
                shape, request.linear_deflection, request.angular_deflection
            )
