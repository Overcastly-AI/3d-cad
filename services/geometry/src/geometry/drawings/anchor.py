"""Durable dimension anchors — a drawing dimension survives the edit it measures.

Audit N1: a dimension on a bracket's 84 mm overall-length edge composed as
``84.000``; widening the plate 100 → 120 (the change request every engineer gets)
rebuilt the part cleanly and turned that dimension into ``subshape_unresolved``. The
rule was exactly inverted from the promise of an associative drawing: **the
dimensions destroyed were precisely the ones that measured what you changed**, and a
print revision became a re-dimensioning job.

Why FEATURE references survived the same edit and dimensions did not
(topological-naming.md §9/§10/§11): a picked FACE resolves through a TWO-TIER matcher
— the strict stage-1 signature (normal + centroid + area) and, only when that finds
nothing, a resilient re-match on the strongest INVARIANT alone (same-sense normal +
coincident supporting plane), which survives any in-plane boundary change
(``geometry.kernel.faces._match_face_records``, FINDINGS #3). Picked EDGES have only
the strict tier: :func:`geometry.kernel.edges.resolve_edge` requires both endpoints,
the midpoint AND the length to match within tolerance, so ANY change to the measured
edge itself is fatal — while a dimension is, by definition, attached to the geometry
the designer is about to change.

This module adds the missing edge tier, reusing the SAME naming (the shipped
:class:`~py_kit.schemas.features.EdgeSignature`, the SAME resolver, the SAME typed
:class:`~geometry.kernel.faces.SubshapeUnresolvedError` /
:class:`~geometry.kernel.faces.SubshapeAmbiguousError` taxonomy) rather than
inventing a second scheme:

1. **Tier 1 — exact.** :func:`geometry.kernel.edges.resolve_edge`, untouched. A
   clean rebuild and any edit that does not touch the measured edge resolve here,
   byte-identically to before.
2. **Tier 2 — durable.** Only when tier 1 finds NOTHING, re-match on the
   rebuild-invariant of the edge's curve kind, both computed from the stored
   signature alone (no new persisted state, no kernel change):

   * a **straight** edge: the same SUPPORTING LINE (collinear within the documented
     linear tolerance and parallel within the documented direction tolerance) whose
     span OVERLAPS the stored span. Invariant under the edge growing or shrinking
     along itself — the widened plate, the moved wall, the re-radiused corner fillet
     that shortens the edge between two rounds;
   * a **circular** edge: the same CENTRE and the same ANGULAR STATION (the unit
     directions from the centre to the stored ``end_a``/``end_b``/``midpoint`` are
     preserved), with the same closedness (a full circle never re-anchors onto an
     arc). Invariant under a radius change — the resized hole, the boss turned down;
   * anything else (spline / ellipse — ``curve == "other"``) has no invariant we can
     state honestly, so it stays an honest unresolved.

Still honest, never a guess (topological-naming §5/§7.3): zero tier-2 candidates is
``subshape_unresolved``, two or more is ``subshape_ambiguous`` (two collinear
segments overlapping the stored span, two coincident-centre circles at the same
station — refuse to pick one), and the caller learns WHICH tier fired through
:class:`~py_kit.schemas.drawings.DimensionAnchor`, so a re-anchored dimension is
visible on the wire rather than silently assumed. The §7.3 residual is unchanged and
NOT claimed away: an invariant-based match can still land on a different edge that
moved into the stored slot while the intended one vanished — it is the same
geometric (not index-based) retarget stage 1 already carries, which is why the tier
is reported and why the measured value is always re-measured off the current B-rep
rather than re-stamped from the authored number.

Determinism (RESEARCH §9): resolution is a pure function of (body, signature) —
candidates come from the SAME deterministic ``enumerate_edges`` order, every
predicate is a coordinate comparison at a documented tolerance, and ambiguity errors
instead of choosing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Edge
from py_kit.schemas.drawings import DimensionAnchorTier
from py_kit.schemas.features import EdgeSignature
from py_kit.schemas.geometry import Vec3

from geometry.kernel.edges import edge_signature_dto, enumerate_edges, resolve_edge
from geometry.kernel.faces import (
    CENTROID_TOL_MM,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
)
from geometry.kernel.types import BodyShape

#: Linear coincidence bound (mm) for the durable re-match: how far a stored point may
#: sit off a candidate's supporting line, and how far two circle centres may differ.
#: The SAME documented subshape linear tolerance the stage-1 signature matchers use
#: (:data:`geometry.kernel.faces.CENTROID_TOL_MM`, numerically the edge matcher's
#: endpoint/midpoint bound) — reused, never a new epsilon (CLAUDE.md).
ANCHOR_POINT_TOL_MM = CENTROID_TOL_MM

#: Direction-parallelism bound for the durable re-match, compared against the
#: cross-product magnitude of two unit vectors (``|sin theta|``) — a dimensionless
#: angular bound, not a linear one. Numerically the kernel's
#: ``edges._EDGE_DIRECTION_TOLERANCE`` / ``project._AXIS_PARALLEL_TOL`` sin-scale
#: bound: an exactly-parallel pair always matches and a meaningfully-tilted one never
#: does. Declared ONCE here and reused by the drawings foreshortening flag
#: (:mod:`geometry.drawings.measure`) so the package holds one such bound, not two.
ANCHOR_DIRECTION_SIN_TOL = 1e-7


@dataclass(frozen=True)
class ResolvedAnchor:
    """One dimension reference resolved against the CURRENT body.

    ``edge`` is the kernel edge to measure, ``signature`` its CURRENT stage-1
    signature (what the composer matches against the projected edges — the stored one
    may name geometry that no longer exists), and ``tier`` how it was found."""

    edge: Edge
    signature: EdgeSignature
    tier: DimensionAnchorTier


#: A plain 3-tuple world point/vector in mm — the local arithmetic type (the boundary
#: :class:`~py_kit.schemas.geometry.Vec3` stays the wire shape).
_V = tuple[float, float, float]


def _t(p: Vec3) -> _V:
    return (p.x, p.y, p.z)


def _sub(a: _V, b: _V) -> _V:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: _V, s: float) -> _V:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: _V, b: _V) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: _V, b: _V) -> _V:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: _V) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: _V) -> _V | None:
    """The unit vector of *a*, or None when *a* is (within tolerance) degenerate."""
    length = _length(a)
    if length <= ANCHOR_POINT_TOL_MM:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


def _parallel_same_sense(a: _V, b: _V) -> bool:
    """True when two UNIT vectors point the same way within the direction bound."""
    return _length(_cross(a, b)) <= ANCHOR_DIRECTION_SIN_TOL and _dot(a, b) > 0.0


def _collinear_overlapping(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """Durable match for a STRAIGHT edge: same supporting line, overlapping span.

    Invariant under the edge growing/shrinking along itself (the audit's 100 → 120
    widening, which moves an endpoint, the midpoint AND the length — every field the
    strict matcher compares). Requires:

    1. both spans non-degenerate and PARALLEL (unit directions, either sense);
    2. the stored ``end_a`` lies ON the candidate's supporting line (perpendicular
       distance within :data:`ANCHOR_POINT_TOL_MM`) — together with (1) this is
       "the same infinite line";
    3. the two spans OVERLAP by a positive length along that line — so a collinear
       edge END-TO-END with the stored one (a corner round splitting an edge in two)
       is NOT silently accepted as the same edge, while any growth or shrink of the
       stored edge is.
    """
    c_a, c_b = _t(candidate.end_a), _t(candidate.end_b)
    t_a, t_b = _t(target.end_a), _t(target.end_b)
    u_c = _unit(_sub(c_b, c_a))
    u_t = _unit(_sub(t_b, t_a))
    if u_c is None or u_t is None:
        return False
    if _length(_cross(u_c, u_t)) > ANCHOR_DIRECTION_SIN_TOL:
        return False
    offset = _sub(t_a, c_a)
    along = _dot(offset, u_c)
    perpendicular = _sub(offset, _scale(u_c, along))
    if _length(perpendicular) > ANCHOR_POINT_TOL_MM:
        return False
    # Parameters of both spans along the candidate's direction, from its own end_a.
    c0, c1 = 0.0, _dot(_sub(c_b, c_a), u_c)
    t0, t1 = along, _dot(_sub(t_b, c_a), u_c)
    lo = max(min(c0, c1), min(t0, t1))
    hi = min(max(c0, c1), max(t0, t1))
    return hi - lo > ANCHOR_POINT_TOL_MM


def _circle_centre(sig: EdgeSignature) -> _V | None:
    """The centre of a circular edge, derived from its stored signature alone.

    A FULL circle stores its seam twice (``end_a == end_b``) with ``midpoint`` at the
    diametrically opposite point, so the centre is their midpoint. An ARC stores three
    distinct points on the circle, so the centre is their CIRCUMCENTRE (the standard
    vector form, valid in 3D: with ``u = midpoint - end_a`` and ``v = end_b - end_a``,
    the centre is ``end_a + ((|u|^2 v - |v|^2 u) x (u x v)) / (2 |u x v|^2)``).
    Returns None when the three points are degenerate/collinear — a zero
    cross-product, i.e. no circle to centre — never a divide-by-zero."""
    a, b, m = _t(sig.end_a), _t(sig.end_b), _t(sig.midpoint)
    if _length(_sub(a, b)) <= ANCHOR_POINT_TOL_MM:
        return ((a[0] + m[0]) / 2, (a[1] + m[1]) / 2, (a[2] + m[2]) / 2)
    u = _sub(m, a)
    v = _sub(b, a)
    normal = _cross(u, v)
    denominator = 2.0 * _dot(normal, normal)
    if denominator <= 0.0:
        return None
    weighted = _sub(_scale(v, _dot(u, u)), _scale(u, _dot(v, v)))
    offset = _scale(_cross(weighted, normal), 1.0 / denominator)
    return (a[0] + offset[0], a[1] + offset[1], a[2] + offset[2])


def _concentric_same_station(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """Durable match for a CIRCULAR edge: same centre, same angular station.

    Invariant under a RADIUS change (the resized hole, whose rim edge changes
    endpoints, midpoint and length at once): scaling a circle about its centre moves
    every point radially, so the centre and the unit directions from the centre to the
    stored ``end_a``/``end_b``/``midpoint`` are all preserved — and those directions
    also pin the circle's PLANE and, for an arc, its sweep, so a coaxial circle in a
    different plane or a different arc of the same circle is not accepted. Closedness
    must match too (a full circle never re-anchors onto an arc)."""
    target_closed = _length(_sub(_t(target.end_a), _t(target.end_b)))
    candidate_closed = _length(_sub(_t(candidate.end_a), _t(candidate.end_b)))
    if (target_closed <= ANCHOR_POINT_TOL_MM) != (
        candidate_closed <= ANCHOR_POINT_TOL_MM
    ):
        return False
    t_centre = _circle_centre(target)
    c_centre = _circle_centre(candidate)
    if t_centre is None or c_centre is None:
        return False
    if math.dist(t_centre, c_centre) > ANCHOR_POINT_TOL_MM:
        return False
    for t_point, c_point in (
        (target.end_a, candidate.end_a),
        (target.end_b, candidate.end_b),
        (target.midpoint, candidate.midpoint),
    ):
        t_dir = _unit(_sub(_t(t_point), t_centre))
        c_dir = _unit(_sub(_t(c_point), c_centre))
        if t_dir is None or c_dir is None:
            return False
        if not _parallel_same_sense(t_dir, c_dir):
            return False
    return True


def _durable_match(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """The tier-2 predicate for *target*'s curve kind (see the module docstring)."""
    if candidate.curve != target.curve:
        return False
    if target.curve == "line":
        return _collinear_overlapping(candidate, target)
    if target.curve == "circle":
        return _concentric_same_station(candidate, target)
    return False


def _durable_resolve(body: BodyShape, target: EdgeSignature) -> ResolvedAnchor:
    """Tier 2: re-anchor *target* on its curve-kind invariant, or fail honestly."""
    if target.curve not in ("line", "circle"):
        raise SubshapeUnresolvedError(
            "No edge of the current body matches the stored edge signature, and a "
            f"'{target.curve}' curve (spline / ellipse) has no rebuild-invariant to "
            "re-anchor on. Re-pick the edge, or edit the upstream feature back to a "
            "state where it resolves."
        )
    matches = [
        record
        for record in enumerate_edges(body)
        if _durable_match(record.signature, target)
    ]
    if not matches:
        raise SubshapeUnresolvedError(
            "No edge of the current body matches the stored edge signature, and none "
            + (
                "lies on its supporting line overlapping its span"
                if target.curve == "line"
                else "shares its centre and angular station"
            )
            + " either; the referenced edge no longer exists after the rebuild. "
            "Re-pick the edge, or edit the upstream feature back to a state where it "
            "resolves."
        )
    if len(matches) > 1:
        raise SubshapeAmbiguousError(
            f"{len(matches)} edges of the current body are equally valid re-anchors "
            "for the stored edge signature (collinear segments of one line, or "
            "coincident-centre circles at the same station). Refusing to guess which "
            "one the dimension meant — re-pick the edge."
        )
    record = matches[0]
    return ResolvedAnchor(edge=record.edge, signature=record.signature, tier="durable")


def resolve_anchor_edge(body: BodyShape, target: EdgeSignature) -> ResolvedAnchor:
    """Resolve a dimension's stored edge signature against *body* — two tiers.

    Tier 1 is :func:`geometry.kernel.edges.resolve_edge` verbatim (exact signature
    match). Only a tier-1 *unresolved* falls through to the durable re-match; a tier-1
    AMBIGUITY is already honest and propagates unchanged (the invariant tier cannot
    disambiguate congruent twins).

    Returns the edge, its CURRENT signature, and which tier matched.

    Raises:
        SubshapeUnresolvedError: neither tier found the edge.
        SubshapeAmbiguousError: either tier found more than one candidate.
    """
    try:
        edge = resolve_edge(body, target)
    except SubshapeUnresolvedError:
        return _durable_resolve(body, target)
    return ResolvedAnchor(edge=edge, signature=edge_signature_dto(edge), tier="exact")
