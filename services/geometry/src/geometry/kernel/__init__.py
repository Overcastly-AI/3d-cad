"""Loft geometry kernel layer — the ONLY code in the monorepo that may
import OCP/build123d (CLAUDE.md service boundaries).

Inputs are pydantic DTOs (:mod:`geometry.schemas`); outputs are GLB bytes
plus metadata DTOs. Kernel shapes (TopoDS/build123d) may be threaded through
service-internal evaluation state (the feature evaluator holds the current
body between features), but they never serialize into a DTO or cross the
service boundary.
"""

from build123d import Solid

from geometry.kernel.boolean import (
    BooleanDisjointError,
    BooleanEmptyError,
    boolean_bodies,
)
from geometry.kernel.chamfer import ChamferError, chamfer_body
from geometry.kernel.datum import (
    DATUM_PLANES,
    build_datum_plane,
    midplane_between,
    offset_plane,
)
from geometry.kernel.draft import DraftError, draft_body
from geometry.kernel.edges import (
    EdgeRecord,
    NoEdgesSelectedError,
    edge_signature_dto,
    enumerate_edges,
    resolve_edge,
    select_edges,
)
from geometry.kernel.export import (
    AssemblyComponent,
    export_step_assembly_bytes,
    export_step_bytes,
    export_stl_assembly_bytes,
    export_stl_bytes,
    place_body,
)
from geometry.kernel.extrude import (
    BooleanError,
    ProfileNotClosedError,
    ProfileUnsupportedError,
    build_profile_face,
    build_profile_faces,
    combine_body,
    extrude_face,
)
from geometry.kernel.faces import (
    FaceResolutionError,
    PlanarFaceRecord,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    planar_faces,
    resolve_face_plane,
    resolve_faces,
)
from geometry.kernel.fillet import FilletError, fillet_body
from geometry.kernel.imports import (
    ImportNoSolidError,
    ImportParseError,
    ImportParseTimeoutError,
    import_step_solid,
    solid_from_brep_bytes,
    solid_to_brep_bytes,
)
from geometry.kernel.interference import (
    CLASH_VOLUME_FLOOR_MM3,
    intersection_volume,
)
from geometry.kernel.loft import LoftError, build_loft_section, loft_sections
from geometry.kernel.measure import EdgeIndexError, MeasureError, measure_targets
from geometry.kernel.overlay import selection_overlay
from geometry.kernel.pattern import (
    PatternAngleError,
    PatternAxisError,
    PatternCountError,
    PatternDirectionError,
    PatternDisjointError,
    PatternError,
    PatternSpacingError,
    circular_pattern,
    circular_pattern_cut,
    linear_pattern,
    linear_pattern_cut,
)
from geometry.kernel.properties import combine_properties, measure_shape
from geometry.kernel.revolve import (
    AxisIntersectsProfileError,
    NoAxisError,
    RevolveError,
    check_axis_clears_profile,
    resolve_axis_line,
    revolve_face,
)
from geometry.kernel.shapes import build_box, build_cylinder
from geometry.kernel.shell import ShellError, ShellThicknessError, shell_body
from geometry.kernel.step_assembly import (
    ReadProduct,
    StepAssemblyRead,
    read_step_assembly,
)
from geometry.kernel.sweep import (
    PathClosedError,
    PathEmptyError,
    PathNotConnectedError,
    SweepError,
    build_path_wire,
    sweep_profile,
)
from geometry.kernel.tessellate import glb_stats, tessellate_glb
from geometry.kernel.types import BodyShape
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
    "CLASH_VOLUME_FLOOR_MM3",
    "DATUM_PLANES",
    "AssemblyComponent",
    "AxisIntersectsProfileError",
    "BooleanDisjointError",
    "BooleanEmptyError",
    "BooleanError",
    "ChamferError",
    "DraftError",
    "EdgeIndexError",
    "EdgeRecord",
    "FaceResolutionError",
    "FilletError",
    "ImportNoSolidError",
    "ImportParseError",
    "ImportParseTimeoutError",
    "LoftError",
    "MeasureError",
    "NoAxisError",
    "NoEdgesSelectedError",
    "PathClosedError",
    "PathEmptyError",
    "PathNotConnectedError",
    "PatternAngleError",
    "PatternAxisError",
    "PatternCountError",
    "PatternDirectionError",
    "PatternDisjointError",
    "PatternError",
    "PatternSpacingError",
    "PlanarFaceRecord",
    "ProfileNotClosedError",
    "ProfileUnsupportedError",
    "ReadProduct",
    "RevolveError",
    "ShellError",
    "ShellThicknessError",
    "StepAssemblyRead",
    "SubshapeAmbiguousError",
    "SubshapeUnresolvedError",
    "SweepError",
    "boolean_bodies",
    "build_box",
    "build_cylinder",
    "build_datum_plane",
    "build_loft_section",
    "build_path_wire",
    "build_profile_face",
    "build_profile_faces",
    "build_shape",
    "chamfer_body",
    "check_axis_clears_profile",
    "circular_pattern",
    "circular_pattern_cut",
    "combine_body",
    "combine_properties",
    "draft_body",
    "edge_signature_dto",
    "enumerate_edges",
    "evaluate_export",
    "evaluate_tessellation",
    "export_solid",
    "export_step_assembly_bytes",
    "export_step_bytes",
    "export_stl_assembly_bytes",
    "export_stl_bytes",
    "extrude_face",
    "fillet_body",
    "glb_stats",
    "import_step_solid",
    "intersection_volume",
    "linear_pattern",
    "linear_pattern_cut",
    "loft_sections",
    "measure_shape",
    "measure_targets",
    "midplane_between",
    "offset_plane",
    "place_body",
    "planar_faces",
    "read_step_assembly",
    "resolve_axis_line",
    "resolve_edge",
    "resolve_face_plane",
    "resolve_faces",
    "revolve_face",
    "select_edges",
    "selection_overlay",
    "shell_body",
    "solid_from_brep_bytes",
    "solid_to_brep_bytes",
    "sweep_profile",
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
    shape: BodyShape,
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
