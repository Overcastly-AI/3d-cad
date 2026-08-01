"""2D drawing projection — exact hidden-line removal (HLR) from a 3D B-rep.

The Drawings-pillar kernel layer (docs/design/drawings.md §1, THE CRUX). Given an
exact body (a ``build123d`` ``Solid`` as :func:`geometry.features.evaluate_tree`
already produces) and a standard orthographic direction, it computes the
**visible** (solid) and **hidden** (dashed) 2D edges of the view via OCCT's exact
HLR (``HLRBRep_Algo``) — a hole projects to a real circle a diameter dimension can
read off, a straight edge to a real line (§1.1). Output is a canonically-ordered,
byte-deterministic list of neutral 2D primitives (§1.4) — never a kernel handle.

Only this package (inside ``services/geometry``) touches ``OCP.HLRBRep`` — the
projection is kernel-only (CLAUDE.md boundaries); callers upstack receive the
neutral :class:`ProjectedEdge` dataclasses, and the API-facing DTO + evaluate
endpoint are a later slice.
"""

from geometry.drawings.anchor import (
    ResolvedAnchor,
    resolve_anchor_edge,
)
from geometry.drawings.assembly_project import (
    compose_assembly_body,
    compose_drawing_evaluation,
    evaluate_assembly_drawing_views,
)
from geometry.drawings.compose import (
    MIN_VIEW_CLEARANCE_MM,
    VIEW_GUTTER_MM,
    measure_layout_issues,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from geometry.drawings.evaluate import (
    SECTION_VIEW,
    evaluate_drawing_views,
    section_view_result,
)
from geometry.drawings.flat_pattern import (
    FLAT_PATTERN_VIEW,
    flat_pattern_view_result,
)
from geometry.drawings.measure import (
    DimensionTypeError,
    DimensionValue,
    measure_dimension,
    measure_dimension_dto,
)
from geometry.drawings.project import (
    Point2D,
    ProjectedEdge,
    ViewDirection,
    ViewProjection,
    ViewProjectionError,
    canonical_edges_repr,
    project_view,
    view_normal,
)
from geometry.drawings.section import (
    SectionCut,
    SectionEmptyError,
    SectionError,
    SectionMissesBodyError,
    SectionPlaneNotPrincipalError,
    section_cut,
)
from geometry.drawings.thread_schedule import thread_schedule_rows

__all__ = [
    "FLAT_PATTERN_VIEW",
    "MIN_VIEW_CLEARANCE_MM",
    "SECTION_VIEW",
    "VIEW_GUTTER_MM",
    "DimensionTypeError",
    "DimensionValue",
    "Point2D",
    "ProjectedEdge",
    "ResolvedAnchor",
    "SectionCut",
    "SectionEmptyError",
    "SectionError",
    "SectionMissesBodyError",
    "SectionPlaneNotPrincipalError",
    "ViewDirection",
    "ViewProjection",
    "ViewProjectionError",
    "canonical_edges_repr",
    "compose_assembly_body",
    "compose_drawing_evaluation",
    "evaluate_assembly_drawing_views",
    "evaluate_drawing_views",
    "flat_pattern_view_result",
    "measure_dimension",
    "measure_dimension_dto",
    "measure_layout_issues",
    "place_sheet",
    "project_view",
    "resolve_anchor_edge",
    "section_cut",
    "section_view_result",
    "serialize_dxf",
    "serialize_pdf",
    "serialize_svg",
    "thread_schedule_rows",
    "view_normal",
]
