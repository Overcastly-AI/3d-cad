"""Loft geometry kernel layer — the ONLY code in the monorepo that may
import OCP/build123d (CLAUDE.md service boundaries).

Inputs are pydantic DTOs (:mod:`geometry.schemas`); outputs are GLB bytes
plus metadata DTOs. Kernel shapes (TopoDS/build123d) may be threaded through
service-internal evaluation state (the feature evaluator holds the current
body between features), but they never serialize into a DTO or cross the
service boundary.
"""

from build123d import Solid

from geometry.kernel.chamfer import ChamferError, chamfer_body
from geometry.kernel.edges import NoEdgesSelectedError, select_edges
from geometry.kernel.export import export_step_bytes, export_stl_bytes
from geometry.kernel.extrude import (
    BooleanError,
    ProfileNotClosedError,
    ProfileUnsupportedError,
    build_profile_face,
    combine_body,
    extrude_face,
)
from geometry.kernel.fillet import FilletError, fillet_body
from geometry.kernel.measure import EdgeIndexError, MeasureError, measure_targets
from geometry.kernel.properties import measure_shape
from geometry.kernel.revolve import (
    AxisIntersectsProfileError,
    NoAxisError,
    RevolveError,
    check_axis_clears_profile,
    resolve_axis_line,
    revolve_face,
)
from geometry.kernel.shapes import build_box, build_cylinder
from geometry.kernel.tessellate import glb_stats, tessellate_glb
from geometry.schemas import (
    BoxParams,
    CylinderParams,
    ExportFormat,
    ExportRequest,
    ShapeRequest,
    TessellateRequest,
    TessellationMetadata,
)

__all__ = [
    "AxisIntersectsProfileError",
    "BooleanError",
    "ChamferError",
    "EdgeIndexError",
    "FilletError",
    "MeasureError",
    "NoAxisError",
    "NoEdgesSelectedError",
    "ProfileNotClosedError",
    "ProfileUnsupportedError",
    "RevolveError",
    "build_box",
    "build_cylinder",
    "build_profile_face",
    "build_shape",
    "chamfer_body",
    "check_axis_clears_profile",
    "combine_body",
    "evaluate_export",
    "evaluate_tessellation",
    "export_solid",
    "export_step_bytes",
    "export_stl_bytes",
    "extrude_face",
    "fillet_body",
    "glb_stats",
    "measure_shape",
    "measure_targets",
    "resolve_axis_line",
    "revolve_face",
    "select_edges",
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


def export_solid(
    shape: Solid,
    fmt: ExportFormat,
    linear_deflection: float,
    angular_deflection: float,
) -> bytes:
    """Export an already-built solid in *fmt* — the shared format dispatch.

    Single source of the format→bytes mapping (CLAUDE.md DRY rule): the
    parametric-shape export path (:func:`evaluate_export`) and the
    evaluated-feature-tree export path (``geometry.api.export_tree``) both go
    through here, so a filleted part and a primitive box export identically.
    STEP ignores the deflection arguments (exact B-rep); STL uses both.
    Deterministic (RESEARCH §9; :mod:`geometry.kernel.export` pins the STEP
    timestamp).
    """
    match fmt:
        case "step":
            return export_step_bytes(shape)
        case "stl":
            return export_stl_bytes(shape, linear_deflection, angular_deflection)


def evaluate_export(request: ExportRequest) -> bytes:
    """Build the requested shape and export it in the requested format.

    Deterministic end to end: identical requests yield byte-identical files
    (RESEARCH §9; see :mod:`geometry.kernel.export` for the STEP timestamp
    pinning that makes this true).
    """
    shape = build_shape(request)
    return export_solid(
        shape, request.format, request.linear_deflection, request.angular_deflection
    )
