"""Sheet-metal unfold (SPIKE 0) — the pillar-gating flat-pattern tractability proof.

The ONLY place OCP/build123d is imported for sheet metal (service-boundary rule,
CLAUDE.md). Public surface: :func:`unfold_l_bracket` (folded body →
:class:`FlatPattern`) + :func:`bend_allowance` (the §1 closed form). See
docs/design/sheet-metal.md §2/§5/§6/§9 and :mod:`geometry.sheet_metal.unfold`.
"""

from geometry.sheet_metal.base_flange import SheetMetalDefaults
from geometry.sheet_metal.flat_pattern import (
    BendLine,
    FlatEdge2D,
    FlatPattern,
)
from geometry.sheet_metal.resolve import (
    BendFlankingFacesError,
    NoBendFoundError,
    ResolvedBend,
    ResolvedFlange,
    SheetMetalUnfoldError,
    resolve_bends,
)
from geometry.sheet_metal.unfold import (
    UnfoldScopeError,
    bend_allowance,
    unfold_l_bracket,
)

__all__ = [
    "BendFlankingFacesError",
    "BendLine",
    "FlatEdge2D",
    "FlatPattern",
    "NoBendFoundError",
    "ResolvedBend",
    "ResolvedFlange",
    "SheetMetalDefaults",
    "SheetMetalUnfoldError",
    "UnfoldScopeError",
    "bend_allowance",
    "resolve_bends",
    "unfold_l_bracket",
]
