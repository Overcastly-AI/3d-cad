"""Loft geometry kernel layer — the ONLY code in the monorepo that may
import OCP/build123d (CLAUDE.md service boundaries).

Inputs are pydantic DTOs (:mod:`geometry.schemas`); outputs are GLB bytes
plus metadata DTOs. Kernel types (TopoDS/build123d shapes) never cross this
package boundary.
"""

from build123d import Solid

from geometry.kernel.properties import measure_shape
from geometry.kernel.shapes import build_box
from geometry.kernel.tessellate import glb_stats, tessellate_glb
from geometry.schemas import TessellateRequest, TessellationMetadata

__all__ = [
    "build_box",
    "build_shape",
    "evaluate_tessellation",
    "glb_stats",
    "measure_shape",
    "tessellate_glb",
]


def build_shape(request: TessellateRequest) -> Solid:
    """Dispatch a validated request to its shape builder.

    ``request.shape`` is a Literal, so pyright checks this match for
    exhaustiveness as new shape kinds land.
    """
    match request.shape:
        case "box":
            return build_box(request.params.x, request.params.y, request.params.z)


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
