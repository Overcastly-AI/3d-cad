"""Which body a picked face or edge belongs to (HOLE-ACTIVE-BODY, RESEARCH §28).

A stored face or edge reference holds a signature, not a body: its
``feature_id`` is the tip body feature at pick time (``anchorBodyFeatureId``),
whichever body the subshape was on. Fusion 360 and SolidWorks modify the body
the picked face or edge belongs to, so every feature that resolves a picked
subshape asks here which body that is, instead of assuming the ACTIVE (most
recently built) one.
"""

import uuid
from collections.abc import Callable, Sequence

from loft_wire.features import (
    EdgeSubshapeRef,
    FeatureError,
    SubshapeRef,
    SubshapeResolutionTier,
)
from loft_wire.geometry import Vec3
from loft_wire.resolution_tiers import SUBSHAPE_RESOLUTION_TIERS

from geometry.features.state import EvaluationState
from geometry.kernel import edge_match_tier, face_match_tier
from geometry.kernel.removal import Bounds
from geometry.kernel.types import BodyShape

#: How certainly a body matches one reference: the tier, or ``None`` (no match).
TierOf = Callable[[BodyShape, list[str | None]], SubshapeResolutionTier | None]


def _owner(
    state: EvaluationState, tier_of: TierOf, upstream: uuid.UUID, point: Vec3
) -> uuid.UUID | FeatureError | None:
    """The body ONE picked reference belongs to.

    The reference is matched against EVERY body (tree order) at the resolver's
    own tiers:

    * the body matching at the most certain tier owns it, so an exact match on
      an earlier member beats a resilient (``durable``) one on the active
      member, the congruent-stud wrong cut HOLE-ACTIVE-BODY closed;
    * a tie at that tier keeps the ACTIVE body when it is tied (the pre-fix
      answer, so no reference that resolved on the active body moves), and is
      otherwise an honest ``subshape_ambiguous`` across bodies;
    * no body matching at all falls back to the active body, so the reference
      then fails exactly as it always did (``subshape_unresolved``).

    A single-body part never scans: its one body is the active body, which
    keeps every single-body rebuild byte-identical. ``None`` with no body.
    """
    active_id = state.active_body_id
    if active_id is None or len(state.bodies) == 1:
        return active_id
    # An exact match on the active body is already the answer (the best tier,
    # and a tie keeps the active body), so the common case scans one body.
    if tier_of(state.bodies[active_id], state.body_face_names(active_id)) == "exact":
        return active_id
    # The EXACT screen (CUT-OBJECTS-TO-CUT): an exact match puts the stored
    # point within 1e-6 mm of a point of the body, so only a body whose box
    # holds it can match exactly. Exact is the best tier, so when such bodies
    # match exactly the answer is theirs, the ranking below would give the
    # same, and no other body is enumerated (0.16 s -> ~2 ms at 200 bodies).
    exact = [
        body_id
        for body_id, body in state.bodies.items()
        if body_id != active_id
        and _holds(state.body_bounds(body_id), point)
        and tier_of(body, state.body_face_names(body_id)) == "exact"
    ]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return _ambiguous(len(exact), upstream)
    ranked: dict[uuid.UUID, int] = {}
    for body_id, body in state.bodies.items():
        tier = tier_of(body, state.body_face_names(body_id))
        if tier is not None:
            ranked[body_id] = SUBSHAPE_RESOLUTION_TIERS.index(tier)
    if not ranked:
        return active_id
    best = min(ranked.values())
    tied = [body_id for body_id, rank in ranked.items() if rank == best]
    if active_id in tied:
        return active_id
    if len(tied) == 1:
        return tied[0]
    return _ambiguous(len(tied), upstream)


#: How far past a body's box the exact screen still looks (mm). Any margin
#: above the 1e-6 mm match tolerance is exact; a wider one only admits more
#: bodies to the full match, never fewer.
_SCREEN_MARGIN_MM = 1e-3


def _holds(bounds: Bounds, point: Vec3) -> bool:
    """Whether *point* lies in *bounds* grown by the screen margin."""
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
    m = _SCREEN_MARGIN_MM
    return (
        xmin - m <= point.x <= xmax + m
        and ymin - m <= point.y <= ymax + m
        and zmin - m <= point.z <= zmax + m
    )


def _ambiguous(bodies: int, upstream: uuid.UUID) -> FeatureError:
    return FeatureError(
        code="subshape_ambiguous",
        message=(
            f"The picked face or edge matches one on {bodies} different "
            "bodies equally well, so the body it belongs to is ambiguous. "
            "Refusing to guess; re-pick it."
        ),
        upstream_feature_id=upstream,
    )


def face_owner_body_id(
    face: SubshapeRef, state: EvaluationState
) -> uuid.UUID | FeatureError | None:
    """The id of the body that OWNS the picked planar *face* (:func:`_owner`)."""
    signature = face.selector.signature
    return _owner(
        state,
        lambda body, names: face_match_tier(body, signature, names),
        face.feature_id,
        signature.centroid,
    )


def _common_owner(
    owners: Sequence[uuid.UUID | FeatureError | None], noun: str
) -> uuid.UUID | FeatureError | None:
    """The one body every reference of a feature belongs to.

    A fillet, chamfer, shell or draft modifies ONE body, so references on two
    bodies are refused (``subshapes_on_several_bodies``) rather than applied to
    one body and silently dropped on the other."""
    distinct: list[uuid.UUID] = []
    for owner in owners:
        if isinstance(owner, FeatureError):
            return owner
        if owner is not None and owner not in distinct:
            distinct.append(owner)
    if len(distinct) > 1:
        return FeatureError(
            code="subshapes_on_several_bodies",
            message=(
                f"The picked {noun} lie on {len(distinct)} different bodies, but "
                "this feature modifies one body. Split it into one feature per "
                "body."
            ),
        )
    return distinct[0] if distinct else None


def faces_owner_body_id(
    faces: Sequence[SubshapeRef], state: EvaluationState
) -> uuid.UUID | FeatureError | None:
    """The body every picked face belongs to; the active body for none."""
    if not faces:
        return state.active_body_id
    return _common_owner([face_owner_body_id(f, state) for f in faces], "faces")


def edge_owner_body_id(
    edge: EdgeSubshapeRef, state: EvaluationState
) -> uuid.UUID | FeatureError | None:
    """The id of the body that OWNS the picked *edge* (:func:`_owner`)."""
    signature = edge.selector.signature
    return _owner(
        state,
        lambda body, names: edge_match_tier(body, signature, names),
        edge.feature_id,
        signature.midpoint,
    )


def edges_owner_body_id(
    edges: Sequence[EdgeSubshapeRef], state: EvaluationState
) -> uuid.UUID | FeatureError | None:
    """The body every picked edge belongs to (:func:`_owner` per edge)."""
    return _common_owner([edge_owner_body_id(ref, state) for ref in edges], "edges")
