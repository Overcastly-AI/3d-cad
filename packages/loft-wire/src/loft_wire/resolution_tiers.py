"""Subshape resolution tiers and projected-entity status (rebuild payloads).

Split out of :mod:`loft_wire.features` (check-file-size) and re-exported
there, so every import path and every generated schema name is unchanged.
"""

from typing import Literal

from pydantic import BaseModel, Field

from loft_wire.sketch import EntityId

#: Which tier of the stage-1 matcher re-found a picked subshape reference on a
#: rebuild (docs/design/topological-naming.md §13/§14), best to worst:
#: ``exact`` - the stored signature matched verbatim, the subshape is where the
#: user left it; ``durable`` - it moved or changed shape and was re-found on a
#: rebuild invariant (an edge's supporting line or circle station; a face's
#: plane, area/in-plane centroid or outer boundary); ``adjacent`` - an EDGE that
#: left every coordinate it was stored at, re-found as the one edge its two
#: stored neighbouring faces still share; ``named`` - re-found by its stored
#: history-based ``topo_name`` (DESIGN-INTENT-REFS), ranked just below exact
#: because it is a fact of the feature history, not a geometric guess. The words
#: exact and durable are the drawings vocabulary
#: (:data:`~loft_wire.drawings.DimensionAnchorTier`).
SubshapeResolutionTier = Literal["exact", "named", "durable", "adjacent"]

#: :data:`SubshapeResolutionTier` ordered BEST to WORST - the one ordering a
#: "worst tier" is taken over, kept beside the alias it ranks.
SUBSHAPE_RESOLUTION_TIERS: tuple[SubshapeResolutionTier, ...] = (
    "exact",
    "named",
    "durable",
    "adjacent",
)


#: Why a projected sketch entity is sick (SKETCH-PROJECT-EDGES): its edge
#: did not resolve, or resolved to more than one edge, there is no body at the
#: sketch, the edge projects to a curve the sketch has no entity for (an
#: ellipse, a B-spline), it projects to nothing (seen end-on), or it projects
#: to another kind than the entity holds.
SketchProjectionReason = Literal[
    "unresolved",
    "ambiguous",
    "no_body",
    "unsupported_curve",
    "degenerate",
    "kind_changed",
]


class SketchProjectionStatus(BaseModel):
    """How one projected entity re-projected on this rebuild.

    ``sick`` is Fusion 360's sick projection: the sketch keeps the entity's
    stored coordinates (the last good projection) and stays ``ok``; this says
    why it could not follow its edge.
    """

    entity: EntityId
    state: Literal["ok", "sick"]
    tier: SubshapeResolutionTier | None = Field(
        default=None, description="The tier that re-found the edge; None if sick."
    )
    reason: SketchProjectionReason | None = Field(
        default=None, description="Why the entity is sick; None when ok."
    )
