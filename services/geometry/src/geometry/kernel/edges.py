"""Edge selection + stage-1 edge SIGNATURES — the shared edge-reference
plumbing for body-modifying features (fillet, chamfer).

Both fillet and chamfer must name edges of the CURRENT body chain. Two families,
both resolved here against ``body.edges()`` (OCCT's deterministic traversal):

* **Predicates** (design §2.4): ``all_edges`` selects every edge; ``axis_parallel``
  selects every straight edge parallel to a world axis (the vertical edges of an
  upright prism are ``axis: "Z"``). Re-selection by geometry each rebuild, so it
  survives without a name map — but it selects SETS: it structurally cannot round
  ONE edge and leave its neighbour sharp.
* **Picked edges** (topological naming, design §2.4/§10 — the SECOND
  ``SubshapeRef`` consumer, mirroring :mod:`geometry.kernel.faces`): each edge is
  named by a stage-1 :class:`~py_kit.schemas.features.EdgeSignature` (curve kind +
  canonically-ordered endpoints + midpoint + length), matched
  nearest-within-tolerance, requiring EXACTLY ONE match — so an engineer rounds
  the specific edge they clicked.

RESILIENT RE-MATCH (NAME-2, audit S-24/S-24b): a picked edge resolves through a
TWO-TIER matcher (:func:`resolve_edge_durable`), the edge twin of the four-tier
face matcher. Tier 1 is the strict signature above — exact on a clean rebuild.
Tier 2 (only when tier 1 finds NOTHING) re-matches on the rebuild-invariant of
the edge's curve kind: a STRAIGHT edge on its supporting line + span overlap
(invariant under the edge growing or shrinking along itself — the dimension edit
that widens the plate the edge bounds), a CIRCLE on its centre + angular station
(invariant under a radius change). Before it existed, every dimension edit that
moved a picked edge orphaned its fillet / chamfer / edge flange / hem on the
FIRST edit; see the block comment above :data:`EdgeMatchTier` for the measurement
and for why an invariant-based tier needs no re-stamping to survive edit N+1.

The signature functions here feed the PICK side
(:mod:`geometry.kernel.overlay`, the selection overlay) and the RESOLVE side
(:func:`select_edges`) through the SAME ``body.edges()`` enumeration and the SAME
:func:`edge_signature_dto`, so a picked edge resolves back to itself — the
same-enumeration lesson from measurement/faces, asserted by an order-equality
gate (``test_edges.py``).

HONEST STAGE-1 LIMIT (topological-naming.md §7.3, mirroring faces): signature
matching is BEST-EFFORT, not the structural non-retarget guarantee of stage 2.
It resolves the same edge across the common edits and FAILS HONESTLY
(:class:`SubshapeUnresolvedError` / :class:`SubshapeAmbiguousError`) for most
others, but a drastic model change can retarget to a coincidentally-congruent
edge without erroring. The exactly-one rule is load-bearing — it refuses to
guess rather than mis-resolve — but note WHAT it actually guards: the signature
encodes ABSOLUTE world coordinates (endpoints/midpoint), so the mirror-congruent
edges of a symmetric part have DISTINCT signatures and never tie (a picked edge
resolves only to the edge at that position, never its displaced twin). The
genuine ambiguity source is two edges that truly COINCIDE in space — a boolean
seam, a non-manifold duplicate, or a near-collision within tolerance; there the
resolver raises :class:`SubshapeAmbiguousError` instead of picking one.

Match tolerances (documented, NOT ad-hoc — CLAUDE.md; sized in docs/GEOMETRY-QA.md,
mirroring the face tolerances): the intended edge is the SAME edge on a clean
rebuild, so residuals are ulp-scale; the bounds below are tight enough that two
DISTINCT edges of an authored part never collide, loose enough to absorb kernel
jitter.

The kernel feature modules (:mod:`geometry.kernel.fillet`,
:mod:`geometry.kernel.chamfer`) own only the OCCT modeling call; the feature
layer maps :class:`NoEdgesSelectedError` onto ``no_fillet_edges`` /
``no_chamfer_edges`` and the subshape errors onto ``subshape_unresolved`` /
``subshape_ambiguous`` (design §4.3).

Determinism (RESEARCH §9): both families filter/match ``body.edges()`` by a pure
function, so the selected set and its order are a pure function of the body.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from dataclasses import dataclass
from typing import Literal

from build123d import Edge, GeomType, Vector
from OCP.BRepAdaptor import BRepAdaptor_Curve
from py_kit.schemas.features import (
    AllEdgesSelector,
    AxisParallelEdgesSelector,
    EdgeSelector,
    EdgeSignature,
    PickedEdgesSelector,
)
from py_kit.schemas.geometry import Vec3

from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError

# The two subshape-resolution errors are generic (defined alongside the face
# resolver); edge resolution reuses them rather than minting a parallel taxonomy.
from geometry.kernel.types import BodyShape

#: OCCT ``GeomType`` → :class:`EdgeSignature` curve family. Anything not a
#: straight line or a circle is ``other`` (ellipse, spline, …) — still fully
#: signed by endpoints + midpoint + length.
_EDGE_CURVE_KIND: dict[GeomType, str] = {
    GeomType.LINE: "line",
    GeomType.CIRCLE: "circle",
}

#: Endpoint / midpoint match tolerance (mm) — the face ``_CENTROID_TOL_MM`` twin.
#: Two distinct edges of an authored part separate by whole mm; the intended edge
#: is bit-identical on a clean rebuild (ulp residuals).
_EDGE_POINT_TOL_MM = 1e-6

#: Relative length match tolerance — the face ``_AREA_REL_TOL`` twin.
_EDGE_LENGTH_REL_TOL = 1e-6

#: World-axis direction vectors for the ``axis_parallel`` selector.
_AXIS_DIRECTIONS: dict[str, Vector] = {
    "X": Vector(1.0, 0.0, 0.0),
    "Y": Vector(0.0, 1.0, 0.0),
    "Z": Vector(0.0, 0.0, 1.0),
}

#: Parallelism tolerance for the ``axis_parallel`` predicate, compared against
#: the tangent-axis cross-product magnitude (``sin theta`` for unit vectors) —
#: an angular (dimensionless)
#: bound, not a linear one. A unit edge tangent counts as parallel to an axis
#: when the perpendicular component is below this bound. Prism edges are exactly
#: axis-aligned; the bound absorbs only ulp-scale construction noise (a tight
#: angular threshold, numerically the same 1e-7 the kernel uses for linear
#: tolerance but a distinct quantity).
_EDGE_DIRECTION_TOLERANCE = 1e-7


class NoEdgesSelectedError(ValueError):
    """The edge selector matched no edge of the body — nothing to modify.

    The honest "your selector picked no edges" outcome, distinct from a kernel
    modeling failure. The feature layer maps it onto the per-feature
    ``no_fillet_edges`` / ``no_chamfer_edges`` code (design §4.3)."""


@dataclass(frozen=True)
class EdgeRecord:
    """One edge of a body: its transient index, stage-1 signature, and the kernel
    :class:`Edge`. The single enumeration the pick side and the resolve side
    share (mirrors :class:`geometry.kernel.faces.PlanarFaceRecord`)."""

    index: int
    signature: EdgeSignature
    edge: Edge


def _vec(vector: Vector) -> Vec3:
    """A build123d ``Vector`` (world mm) as a boundary :class:`Vec3`."""
    return Vec3(x=float(vector.X), y=float(vector.Y), z=float(vector.Z))


def _canonical_endpoints(edge: Edge) -> tuple[Vector, Vector]:
    """The edge's two endpoints in a canonical, orientation-independent order.

    Sorted lexicographically by (x, y, z), so the signature does not depend on
    which way OCCT oriented the edge (topological orientation and geometric
    parametrisation can disagree — the same subtlety the overlay handles). For a
    closed edge (a full circle) both endpoints coincide, so order is moot.
    """
    a = edge @ 0.0
    b = edge @ 1.0
    if (a.X, a.Y, a.Z) <= (b.X, b.Y, b.Z):
        return a, b
    return b, a


def edge_signature_dto(edge: Edge) -> EdgeSignature:
    """The stage-1 :class:`EdgeSignature` of *edge* (curve + endpoints + mid + len).

    THE single signature construction (CLAUDE.md DRY rule) shared by the pick
    side (:mod:`geometry.kernel.overlay`) and the resolve side
    (:func:`enumerate_edges`), so an edge's overlay signature is byte-for-byte the
    one the resolver matches against — the same-enumeration guarantee. All metrics
    come from the exact B-rep (build123d ``@`` sampling + ``.length``), never a
    tessellation.
    """
    end_a, end_b = _canonical_endpoints(edge)
    return EdgeSignature(
        curve=_EDGE_CURVE_KIND.get(edge.geom_type, "other"),  # pyright: ignore[reportArgumentType]
        end_a=_vec(end_a),
        end_b=_vec(end_b),
        midpoint=_vec(edge @ 0.5),
        length_mm=float(edge.length),
    )


def circle_axis(edge: Edge) -> tuple[float, float, float]:
    """The unit axis of a CIRCULAR edge's plane, from the exact B-rep circle.

    The one quantity a circular edge carries that its stage-1
    :class:`~py_kit.schemas.features.EdgeSignature` cannot: a full circle stores only
    its seam and the antipodal midpoint (a diameter), which fixes the centre and the
    radius but NOT the plane. THE single accessor (CLAUDE.md DRY rule), shared by the
    drawings foreshortening flag (:mod:`geometry.drawings.measure` — a circle reads
    true-size only with its axis along the view normal) and the durable circle
    re-anchor (:mod:`geometry.drawings.anchor` — a bore's rim translates ALONG this
    axis when the face it sits on moves). Caller guarantees ``edge.geom_type`` is
    ``GeomType.CIRCLE``.
    """
    axis = BRepAdaptor_Curve(edge.wrapped).Circle().Axis().Direction()
    return (axis.X(), axis.Y(), axis.Z())


def enumerate_edges(body: BodyShape) -> list[EdgeRecord]:
    """Every edge of *body* in ``body.edges()`` order (deterministic).

    THE shared enumeration (CLAUDE.md DRY rule): the selection overlay builds its
    pickable edge list from the SAME edges + :func:`edge_signature_dto`, and
    :func:`_resolve_picked_edges` matches against these records, so a signature the
    overlay hands a client resolves back to the SAME edge (order-equality gate) —
    byte-for-byte the ``body.edges()`` order measurement resolves ``EdgeTarget``
    against.

    *body* is any :class:`~build123d.Shape` — a single :class:`~build123d.Solid`
    or a multi-body :class:`~build123d.Compound` (multi-body §MB-0), whose
    ``.edges()`` iterates every subshape solid's edges. Modifying features resolve
    against their ACTIVE body only (design §MB-0 Decision 1).
    """
    return [
        EdgeRecord(index=index, signature=edge_signature_dto(edge), edge=edge)
        for index, edge in enumerate(body.edges())
    ]


def _distance(a: Vec3, b: Vec3) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def edge_signatures_match(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """Nearest-within-tolerance match of two edge signatures (§7.2).

    Same curve family, both canonically-ordered endpoints within the linear
    tolerance, midpoint within the linear tolerance, and length within a relative
    tolerance. Compared field by field so a lone in-tolerance candidate is a
    unique match and two are an honest ambiguity (never a guess).

    THE single edge-signature comparison (CLAUDE.md DRY rule): the resolvers below
    and the drawings anchor (:mod:`geometry.drawings.anchor`, which asks whether a
    body edge is one of the edges a view DRAWS) share it rather than each declaring
    a point tolerance.
    """
    if candidate.curve != target.curve:
        return False
    if _distance(candidate.end_a, target.end_a) > _EDGE_POINT_TOL_MM:
        return False
    if _distance(candidate.end_b, target.end_b) > _EDGE_POINT_TOL_MM:
        return False
    if _distance(candidate.midpoint, target.midpoint) > _EDGE_POINT_TOL_MM:
        return False
    length_ref = max(abs(target.length_mm), 1.0)
    length_delta = abs(candidate.length_mm - target.length_mm)
    return length_delta / length_ref <= _EDGE_LENGTH_REL_TOL


def resolve_edge(body: BodyShape, target: EdgeSignature) -> Edge:
    """Resolve a stage-1 edge signature to its edge, STRICT TIER ONLY.

    Matches *target* against the edges of *body* (:func:`enumerate_edges`) and
    requires EXACTLY ONE match (§7.2 — refuse to guess).

    Deliberately NOT the resilient entry point. Two callers need the strict answer
    on its own: :func:`geometry.drawings.anchor.resolve_anchor_edge` runs this as
    its tier 1 and reports which tier fired (an exact match and a re-anchored one
    are different facts to a drawing), and the assembly mate resolver wants a mate
    to fail honestly rather than slide onto a moved edge. Every FEATURE-tree
    consumer wants :func:`resolve_edge_durable` instead.

    Raises:
        SubshapeUnresolvedError: zero matching edges (the referenced edge no
            longer exists after the rebuild).
        SubshapeAmbiguousError: two or more within tolerance (a congruent twin) —
            an honest error, never a coin flip (determinism, RESEARCH §9).
    """
    matches = [
        record
        for record in enumerate_edges(body)
        if edge_signatures_match(record.signature, target)
    ]
    if not matches:
        raise SubshapeUnresolvedError(_UNRESOLVED_MESSAGE)
    if len(matches) > 1:
        raise SubshapeAmbiguousError(
            f"{len(matches)} edges match the stored edge signature within "
            "tolerance; the reference is ambiguous (a congruent/symmetric edge). "
            "Refusing to guess — pick an edge without a congruent twin."
        )
    return matches[0].edge


# --------------------------------------------------------------------------- #
# TIER 2 — the DURABLE re-match (NAME-2 / audit S-24, S-24b)                   #
# --------------------------------------------------------------------------- #
#
# THE DEFECT, measured on the `l-bracket-edge-flange` golden before this tier
# existed: the strict matcher above pins BOTH endpoints, the midpoint AND the
# length, and a dimension edit moves at least one of them — so widening the base
# sketch of an L-bracket 50 -> 51 orphaned its edge flange (`subshape_unresolved`,
# every feature below it skipped) and so did 51 -> 52, 52 -> 53 and 53 -> 54. The
# audit read that ladder as "the first edit survives, the second breaks" and
# inferred a stale, re-stamped-too-late signature; the kernel measurement is
# blunter and worse — EVERY edit that moves a picked edge orphaned it, on the
# FIRST edit, because the feature tree had no tolerant tier at all to go stale.
# A face has had four tiers since M17/GEOM-3 (:mod:`geometry.kernel.faces`); an
# edge had one. That asymmetry IS the bug.
#
# The re-match itself is not invented here — the DRAWINGS module already solved
# exactly this for dimension anchors (audit N1/S-27: "widening the plate 100 ->
# 120 destroyed precisely the dimensions that measured what you changed"), and
# the two predicates below are that solution moved down to the layer every
# picked-edge consumer shares. NB `geometry.drawings.anchor` still carries its
# own copy (`_collinear_overlapping` / `_concentric_same_station`) and should
# collapse onto these — a mechanical ~15-line delete + import in that package's
# territory, deliberately NOT done in this commit.
#
# ORDER IS THE SAFETY PROPERTY, exactly as in faces.py: tier 2 runs ONLY on an
# EMPTY tier-1 result, so it can only turn an `unresolved` into a resolution or
# an honest ambiguity — it can never retarget a reference that already resolves.
#
# WHY THIS ALSO CLOSES THE "NOT RE-STAMPED" HALF. A drift-based matcher has to be
# re-stamped, because its budget is spent against the AUTHORED state and edit N+1
# starts from where edit N left off. These predicates are not drift-based: they
# compare INVARIANTS (a supporting line, a centre and an angular station) that
# the edit does not move at all, so the stored signature never goes stale no
# matter how many edits accumulate. The N-th consecutive edit resolves for the
# same reason the first one does. Re-stamping remains worth REPORTING — a client
# that persists :attr:`ResolvedEdge.signature` gets its reference back onto the
# strict tier — which is why the resolver returns the current signature and the
# tier that found it, mirroring `DimensionAnchor`; it is no longer required for
# correctness.

#: A plain 3-tuple world point/vector in mm — the local arithmetic type (the
#: boundary :class:`Vec3` stays the wire shape).
_V = tuple[float, float, float]

#: The single "this edge is gone" message, shared by every resolver in this module
#: so the four call sites cannot drift apart (CLAUDE.md DRY).
_UNRESOLVED_MESSAGE = (
    "No edge of the current body matches the stored edge signature (curve / "
    "endpoints / midpoint / length), and none shares its rebuild invariant (a "
    "straight edge's supporting line and span, a circle's centre and angular "
    "station) either; the referenced edge no longer exists after the rebuild. "
    "Re-pick the edge, or edit the upstream feature back to a state where it "
    "resolves."
)

#: Which tier of :func:`resolve_edge_durable` found the edge. Deliberately the
#: same two words as the drawings wire vocabulary
#: (:data:`~py_kit.schemas.drawings.DimensionAnchorTier`): what a consumer can DO
#: about a match is "it is where you left it" vs "it moved and I followed it".
EdgeMatchTier = Literal["exact", "durable"]


@dataclass(frozen=True)
class ResolvedEdge:
    """One picked-edge reference resolved against the CURRENT body.

    ``edge`` is the kernel edge to modify, ``signature`` its CURRENT stage-1
    signature — what a client persists to re-stamp the stored reference back onto
    the strict tier — and ``tier`` how it was found. Mirrors
    :class:`geometry.drawings.anchor.ResolvedAnchor` field for field, because it
    is the same fact about the same kind of reference.
    """

    edge: Edge
    signature: EdgeSignature
    tier: EdgeMatchTier


def _t(p: Vec3) -> _V:
    return (p.x, p.y, p.z)


def _sub(a: _V, b: _V) -> _V:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: _V, s: float) -> _V:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot3(a: _V, b: _V) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(a: _V, b: _V) -> _V:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: _V) -> float:
    return math.sqrt(_dot3(a, a))


def _unit(a: _V) -> _V | None:
    """The unit vector of *a*, or ``None`` when *a* is (within tolerance) degenerate."""
    length = _norm(a)
    if length <= _EDGE_POINT_TOL_MM:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


def _parallel_same_sense(a: _V, b: _V) -> bool:
    """True when two UNIT vectors point the same way within the direction bound."""
    return _norm(_cross3(a, b)) <= _EDGE_DIRECTION_TOLERANCE and _dot3(a, b) > 0.0


def collinear_overlapping_match(
    candidate: EdgeSignature, target: EdgeSignature
) -> bool:
    """Durable match for a STRAIGHT edge: same supporting line, overlapping span.

    Invariant under the edge growing or shrinking ALONG ITSELF — which is what a
    dimension edit does to the boundary edge it dimensions, and is precisely the
    audit's S-24 case ("the same y = +30 boundary edge of the same face, just
    30 mm longer"). The strict matcher compares an endpoint, the midpoint AND the
    length; growth moves all three, so it has no chance. Three conditions:

    1. both spans non-degenerate and PARALLEL (unit directions, either sense);
    2. the stored ``end_a`` lies ON the candidate's supporting line (perpendicular
       distance within :data:`_EDGE_POINT_TOL_MM`) — with (1) this is "the same
       infinite line";
    3. the two spans OVERLAP by a positive length along that line, so a collinear
       edge END-TO-END with the stored one (a corner round splitting one edge in
       two) is NOT silently accepted as the same edge, while any growth or shrink
       of the stored edge is.

    Uses the module's documented linear / direction tolerances, never a new
    epsilon (CLAUDE.md).
    """
    c_a, c_b = _t(candidate.end_a), _t(candidate.end_b)
    t_a, t_b = _t(target.end_a), _t(target.end_b)
    u_c = _unit(_sub(c_b, c_a))
    u_t = _unit(_sub(t_b, t_a))
    if u_c is None or u_t is None:
        return False
    if _norm(_cross3(u_c, u_t)) > _EDGE_DIRECTION_TOLERANCE:
        return False
    offset = _sub(t_a, c_a)
    along = _dot3(offset, u_c)
    perpendicular = _sub(offset, _scale(u_c, along))
    if _norm(perpendicular) > _EDGE_POINT_TOL_MM:
        return False
    # Parameters of both spans along the candidate's direction, from its own end_a.
    c0, c1 = 0.0, _dot3(_sub(c_b, c_a), u_c)
    t0, t1 = along, _dot3(_sub(t_b, c_a), u_c)
    lo = max(min(c0, c1), min(t0, t1))
    hi = min(max(c0, c1), max(t0, t1))
    return hi - lo > _EDGE_POINT_TOL_MM


def _circle_centre(sig: EdgeSignature) -> _V | None:
    """The centre of a circular edge, derived from its stored signature alone.

    A FULL circle stores its seam twice (``end_a == end_b``) with ``midpoint`` at
    the diametrically opposite point, so the centre is their midpoint. An ARC
    stores three distinct points on the circle, so the centre is their
    CIRCUMCENTRE (the standard vector form, valid in 3D: with ``u = midpoint -
    end_a`` and ``v = end_b - end_a``, the centre is
    ``end_a + ((|u|^2 v - |v|^2 u) x (u x v)) / (2 |u x v|^2)``). ``None`` when the
    three points are degenerate/collinear — a zero cross product, i.e. no circle to
    centre — never a divide-by-zero.
    """
    a, b, m = _t(sig.end_a), _t(sig.end_b), _t(sig.midpoint)
    if _norm(_sub(a, b)) <= _EDGE_POINT_TOL_MM:
        return ((a[0] + m[0]) / 2, (a[1] + m[1]) / 2, (a[2] + m[2]) / 2)
    u = _sub(m, a)
    v = _sub(b, a)
    normal = _cross3(u, v)
    denominator = 2.0 * _dot3(normal, normal)
    if denominator <= 0.0:
        return None
    weighted = _sub(_scale(v, _dot3(u, u)), _scale(u, _dot3(v, v)))
    offset = _scale(_cross3(weighted, normal), 1.0 / denominator)
    return (a[0] + offset[0], a[1] + offset[1], a[2] + offset[2])


def concentric_same_station_match(
    candidate: EdgeSignature, target: EdgeSignature
) -> bool:
    """Durable match for a CIRCULAR edge: same centre, same angular station.

    Invariant under a RADIUS change — the resized hole whose rim was chamfered,
    the boss turned down after its top edge was filleted. Scaling a circle about
    its centre moves every point radially, so the centre and the unit directions
    from the centre to the stored ``end_a`` / ``end_b`` / ``midpoint`` are all
    preserved; those directions also pin the circle's PLANE and, for an arc, its
    sweep, so a coaxial circle in a different plane or a different arc of the same
    circle is not accepted. Closedness must match too (a full circle never
    re-anchors onto an arc).
    """
    target_closed = _norm(_sub(_t(target.end_a), _t(target.end_b)))
    candidate_closed = _norm(_sub(_t(candidate.end_a), _t(candidate.end_b)))
    if (target_closed <= _EDGE_POINT_TOL_MM) != (
        candidate_closed <= _EDGE_POINT_TOL_MM
    ):
        return False
    t_centre = _circle_centre(target)
    c_centre = _circle_centre(candidate)
    if t_centre is None or c_centre is None:
        return False
    if math.dist(t_centre, c_centre) > _EDGE_POINT_TOL_MM:
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


def durable_edge_match(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """The tier-2 predicate for *target*'s curve kind.

    A ``line`` re-matches on its supporting line and span, a ``circle`` on its
    centre and angular station, and anything else (spline / ellipse —
    ``curve == "other"``) has no invariant we can state honestly, so it stays an
    honest ``subshape_unresolved`` rather than being guessed at.
    """
    if candidate.curve != target.curve:
        return False
    if target.curve == "line":
        return collinear_overlapping_match(candidate, target)
    if target.curve == "circle":
        return concentric_same_station_match(candidate, target)
    return False


def _match_edge_records(
    records: list[EdgeRecord], target: EdgeSignature
) -> tuple[list[EdgeRecord], bool]:
    """The two-tier picked-edge match shared by every feature-tree consumer.

    The edge twin of :func:`geometry.kernel.faces._match_face_records`: tier 1 is
    the strict signature (:func:`edge_signatures_match`), tier 2 the durable
    re-match (:func:`durable_edge_match`) and runs ONLY on an empty tier-1 result.

    Returns ``(matched records, durable)`` — the records (0, 1, or >1), which the
    caller maps onto its typed unresolved / ambiguous error, and whether tier 2
    produced them.
    """
    strict = [r for r in records if edge_signatures_match(r.signature, target)]
    if strict:
        return strict, False
    return [r for r in records if durable_edge_match(r.signature, target)], True


def _ambiguous(count: int, *, durable: bool) -> SubshapeAmbiguousError:
    """The typed >1-match refusal, worded for the tier that produced it."""
    if durable:
        return SubshapeAmbiguousError(
            f"{count} edges of the current body are equally valid re-anchors for "
            "the stored edge signature (collinear segments of one line overlapping "
            "its span, or coincident-centre circles at the same angular station). "
            "Refusing to guess which one the feature meant — re-pick the edge."
        )
    return SubshapeAmbiguousError(
        f"{count} edges match the stored edge signature within tolerance; the "
        "reference is ambiguous (a congruent/symmetric edge). Refusing to guess — "
        "pick an edge without a congruent twin."
    )


def resolve_edge_durable(body: BodyShape, target: EdgeSignature) -> ResolvedEdge:
    """Resolve a picked-edge reference against *body* — strict, then durable.

    THE feature-tree entry point (fillet / chamfer via
    :func:`_resolve_picked_edges`, sheet-metal edge flange + hem via the feature
    layer). Requires EXACTLY ONE match at whichever tier fires (§7.2 — refuse to
    guess) and returns the edge, its CURRENT signature, and the tier.

    Raises:
        SubshapeUnresolvedError: neither tier found the edge — it genuinely no
            longer exists (deleted, or moved off its own supporting line).
        SubshapeAmbiguousError: some tier found more than one candidate.
    """
    matches, durable = _match_edge_records(enumerate_edges(body), target)
    if not matches:
        raise SubshapeUnresolvedError(_UNRESOLVED_MESSAGE)
    if len(matches) > 1:
        raise _ambiguous(len(matches), durable=durable)
    record = matches[0]
    return ResolvedEdge(
        edge=record.edge,
        signature=record.signature,
        tier="durable" if durable else "exact",
    )


def _resolve_picked_edges(body: BodyShape, selector: PickedEdgesSelector) -> list[Edge]:
    """Resolve each picked edge ref to its edge; dedupe; return in body order.

    Every ref must resolve to exactly one edge through the SAME two-tier match
    :func:`resolve_edge_durable` uses (:func:`_match_edge_records`), against ONE
    shared enumeration. Two refs that resolve to the same edge collapse to one
    (idempotent). Returned in ``body.edges()`` order so the fillet/chamfer input is
    deterministic regardless of pick order (RESEARCH §9).

    The tier is not surfaced here: this resolver returns the kernel :class:`Edge`
    itself, not a derived POSITION, so a durable match needs no re-anchoring —
    exactly the reasoning :func:`geometry.kernel.faces.resolve_faces` records for
    its own ignored flag.
    """
    records = enumerate_edges(body)
    chosen: dict[int, Edge] = {}
    for ref in selector.refs:
        matches, durable = _match_edge_records(records, ref.selector.signature)
        if not matches:
            raise SubshapeUnresolvedError(_UNRESOLVED_MESSAGE)
        if len(matches) > 1:
            raise _ambiguous(len(matches), durable=durable)
        chosen[matches[0].index] = matches[0].edge
    return [chosen[index] for index in sorted(chosen)]


def _is_axis_parallel(edge: Edge, axis: Vector) -> bool:
    """True when *edge* is a straight line parallel to *axis*.

    Curved edges never match (an arc has no single direction). The tangent of a
    line is constant, so sampling it at the midpoint is exact.
    """
    if edge.geom_type != GeomType.LINE:
        return False
    tangent: Vector = edge.tangent_at(0.5)
    # |tangent x axis| == sin(angle); both are unit vectors, so the cross
    # magnitude is the perpendicular component. Parallel (either orientation)
    # ⇔ that component is ~0.
    return tangent.cross(axis).length <= _EDGE_DIRECTION_TOLERANCE


def select_edges(body: BodyShape, selector: EdgeSelector) -> list[Edge]:
    """Resolve an edge selector against *body* (design §2.4/§10).

    Deterministic: a PREDICATE selector filters ``body.edges()`` (OCCT's
    deterministic order) by a pure predicate; a PICKED selector matches each
    stage-1 signature against that same enumeration, exactly one or an honest
    error.

    Raises:
        NoEdgesSelectedError: a predicate matched no edge (nothing to modify).
        SubshapeUnresolvedError: a picked signature matches no current edge.
        SubshapeAmbiguousError: a picked signature matches a congruent twin.
    """
    match selector:
        case AllEdgesSelector():
            edges = list(body.edges())
        case AxisParallelEdgesSelector():
            axis = _AXIS_DIRECTIONS[selector.axis]
            edges = [e for e in body.edges() if _is_axis_parallel(e, axis)]
        case PickedEdgesSelector():
            # Picked-edge resolution raises the subshape errors directly (a
            # picked signature that no longer resolves is not the same outcome as
            # a predicate matching nothing); refs are >= 1, each resolving to one
            # edge, so the result is never empty.
            return _resolve_picked_edges(body, selector)

    if not edges:
        raise NoEdgesSelectedError(
            "The edge selector matched no edge of the body; nothing to modify "
            "(the predicate selectors re-select edges geometrically — design "
            "§2.4)."
        )
    return edges
