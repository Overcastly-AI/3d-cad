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

from geometry.drawings.evaluate import evaluate_drawing_views
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

__all__ = [
    "DimensionTypeError",
    "DimensionValue",
    "Point2D",
    "ProjectedEdge",
    "ViewDirection",
    "ViewProjection",
    "ViewProjectionError",
    "canonical_edges_repr",
    "evaluate_drawing_views",
    "measure_dimension",
    "measure_dimension_dto",
    "project_view",
    "view_normal",
]
