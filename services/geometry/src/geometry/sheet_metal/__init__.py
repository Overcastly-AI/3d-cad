"""Sheet-metal unfold (SPIKE 0) — the pillar-gating flat-pattern tractability proof.

The ONLY place OCP/build123d is imported for sheet metal (service-boundary rule,
CLAUDE.md). Public surface: :func:`unfold_l_bracket` (folded body →
:class:`FlatPattern`) + :func:`bend_allowance` (the §1 closed form). See
docs/design/sheet-metal.md §2/§5/§6/§9 and :mod:`geometry.sheet_metal.unfold`.
"""

from geometry.sheet_metal.base_flange import SheetMetalDefaults
from geometry.sheet_metal.edge_flange import (
    EdgeFlangeEdgeError,
    EdgeFlangeError,
    EdgeFlangeResult,
    build_edge_flange,
)
from geometry.sheet_metal.flat_pattern import (
    BendLine,
    FlatEdge2D,
    FlatPattern,
)
from geometry.sheet_metal.resolve import (
    BendFlankingFacesError,
    FlangeFaceRecord,
    NoBendFoundError,
    ResolvedBend,
    ResolvedBendFaces,
    ResolvedFlange,
    SheetMetalUnfoldError,
    cylindrical_face_signature,
    resolve_bend_faces,
    resolve_bends,
    resolve_cylindrical_face,
)
from geometry.sheet_metal.unfold import (
    BendProvenance,
    UnfoldScopeError,
    UnfoldStarError,
    bend_allowance,
    unfold_l_bracket,
    unfold_sheet_metal,
)

__all__ = [
    "BendFlankingFacesError",
    "BendLine",
    "BendProvenance",
    "EdgeFlangeEdgeError",
    "EdgeFlangeError",
    "EdgeFlangeResult",
    "FlangeFaceRecord",
    "FlatEdge2D",
    "FlatPattern",
    "NoBendFoundError",
    "ResolvedBend",
    "ResolvedBendFaces",
    "ResolvedFlange",
    "SheetMetalDefaults",
    "SheetMetalUnfoldError",
    "UnfoldScopeError",
    "UnfoldStarError",
    "bend_allowance",
    "build_edge_flange",
    "cylindrical_face_signature",
    "resolve_bend_faces",
    "resolve_bends",
    "resolve_cylindrical_face",
    "unfold_l_bracket",
    "unfold_sheet_metal",
]
