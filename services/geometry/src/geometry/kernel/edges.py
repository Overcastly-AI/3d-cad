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
  named by a stage-1 :class:`~loft_wire.features.EdgeSignature` (curve kind +
  canonically-ordered endpoints + midpoint + length), matched
  nearest-within-tolerance, requiring EXACTLY ONE match — so an engineer rounds
  the specific edge they clicked.

RESILIENT RE-MATCH (NAME-2, audit S-24/S-24b; §14): a picked edge resolves through
a THREE-TIER matcher (:func:`resolve_edge_durable`), the edge twin of the
four-tier face matcher. Tier 1 is the strict signature above — exact on a clean
rebuild. Tier 2 (only when tier 1 finds NOTHING) re-matches on the
rebuild-invariant of the edge's curve kind: a STRAIGHT edge on its supporting line
+ span overlap (invariant under the edge growing or shrinking along itself), a
CIRCLE on its centre + radius + angular station (EDGE-REF-CONCENTRIC). Before
it existed, every dimension edit that moved a picked edge orphaned its fillet /
chamfer / edge flange / hem on the FIRST edit. Tier 3 (only when tier 2 finds
NOTHING) re-matches on the edge's ADJACENCY — the two planar faces it bounds,
re-resolved through the face matcher and intersected — which is what carries a
reference through an edit that RESIZES the part and so translates the edge off
every absolute coordinate tier 1 and tier 2 pin. See the block comments above
:data:`EdgeMatchTier` and above :func:`_adjacency_matches` for the two
measurements.

The signature functions here feed the PICK side
(:mod:`geometry.kernel.overlay`, the selection overlay, via
:func:`enumerate_edges_with_adjacency`) and the RESOLVE side
(:func:`select_edges`, via :func:`enumerate_edges`) through the SAME
``body.edges()`` enumeration and the SAME :func:`edge_signature_dto`, so a picked
edge resolves back to itself — the same-enumeration lesson from measurement/faces,
asserted by an order-equality gate (``test_edges.py``). The two enumerations
differ ONLY in the §14 adjacency annotation, which tier 1 does not compare.

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
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Edge, Face, GeomType, Vector
from loft_wire.features import (
    AllEdgesSelector,
    AxisParallelEdgesSelector,
    EdgeSelector,
    EdgeSignature,
    PickedEdgesSelector,
    PlanarFaceSignature,
    SubshapeResolutionTier,
)
from loft_wire.geometry import Vec3
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

from geometry.kernel.faces import (
    PlanarFaceRecord,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    face_signature_dto,
    match_face_records_tiered,
    planar_faces,
)
from geometry.kernel.naming import edge_names
from geometry.kernel.resolution import ResolutionTally

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
    #: The edge's history-based name (:mod:`geometry.kernel.naming`), when known.
    name: str | None = None


def _vec(vector: Vector) -> Vec3:
    """A build123d ``Vector`` (world mm) as a boundary :class:`Vec3`."""
    return Vec3(x=float(vector.X), y=float(vector.Y), z=float(vector.Z))


def canonical_endpoints(edge: Edge) -> tuple[Vector, Vector]:
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


def edge_signature_dto(
    edge: Edge,
    adjacent_faces: list[PlanarFaceSignature] | None = None,
    topo_name: str | None = None,
) -> EdgeSignature:
    """The stage-1 :class:`EdgeSignature` of *edge* (curve + endpoints + mid + len).

    THE single signature construction (CLAUDE.md DRY rule) shared by the pick
    side (:mod:`geometry.kernel.overlay`) and the resolve side
    (:func:`enumerate_edges`), so an edge's overlay signature is byte-for-byte the
    one the resolver matches against — the same-enumeration guarantee. All metrics
    come from the exact B-rep (build123d ``@`` sampling + ``.length``), never a
    tessellation.

    *adjacent_faces* is the §14 adjacency annotation — the edge's two planar
    neighbours, already canonically ordered by :func:`adjacent_face_signatures`.
    It defaults to ``None`` because an edge alone cannot know its neighbours: only
    a caller holding the BODY can compute them, and only the PICK side needs to
    (tier 3 resolves the TARGET's stored faces against the body, never a
    candidate's — see :func:`_adjacency_matches`). So the resolve-side
    :func:`enumerate_edges` deliberately stays cheap and passes nothing.
    """
    end_a, end_b = canonical_endpoints(edge)
    return EdgeSignature(
        curve=_EDGE_CURVE_KIND.get(edge.geom_type, "other"),  # pyright: ignore[reportArgumentType]
        end_a=_vec(end_a),
        end_b=_vec(end_b),
        midpoint=_vec(edge @ 0.5),
        length_mm=float(edge.length),
        adjacent_faces=adjacent_faces,
        topo_name=topo_name,
    )


#: Canonical sort key for an adjacent-face signature (normal, then centroid). Two
#: distinct faces meeting at one edge cannot share both, so the order is total —
#: and being a pure function of the geometry it is DETERMINISTIC (RESEARCH §9):
#: the same edge of the same body always stores the same pair in the same order,
#: which matters because the signature is persisted and hashed.
def _adjacency_sort_key(sig: PlanarFaceSignature) -> tuple[float, ...]:
    return (
        sig.normal.x,
        sig.normal.y,
        sig.normal.z,
        sig.centroid.x,
        sig.centroid.y,
        sig.centroid.z,
    )


def edge_adjacency(
    body: BodyShape,
    face_signatures: list[PlanarFaceSignature | None] | None = None,
) -> dict[int, list[PlanarFaceSignature]]:
    """The §14 adjacency annotation for every edge of *body*, by ``body.edges()`` index.

    THE single adjacency construction (CLAUDE.md DRY rule) — the PICK side stamps
    its result into each :class:`EdgeSignature` it hands a client, and tier 3
    later re-resolves those stored faces against a rebuilt body.

    An edge is ABSENT from the result — never given a partial answer — whenever it
    does not have exactly two DISTINCT PLANAR neighbours:

    * a **seam** edge of a cylinder or cone, whose ancestor list names the SAME
      face twice (there is no pair to intersect, so tier 3 has nothing to say);
    * an edge bounded by any **curved** face (a hole rim, a fillet boundary) —
      :class:`~loft_wire.features.PlanarFaceSignature` describes planes only, and
      minting a curved sibling here would be a second signature schema, not a fix.
      This is the stated honest limit of §14, not an oversight;
    * a **non-manifold** or free edge (2 is the manifold-solid count).

    *face_signatures*, when supplied, is index-aligned with ``body.faces()`` and
    lets a caller that has ALREADY computed them (the selection overlay does,
    for its own ``faces`` payload) share the work. It is not an optimisation
    detail: a planar face signature builds an outer-wire region, so recomputing
    one per incident edge is quadratic on a real part.
    """
    faces = list(body.faces())
    face_index = TopTools_IndexedMapOfShape()
    for face in faces:
        face_index.Add(face.wrapped)
    signatures = (
        [face_signature_dto(face) for face in faces]
        if face_signatures is None
        else face_signatures
    )

    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)

    adjacency: dict[int, list[PlanarFaceSignature]] = {}
    for index, edge in enumerate(body.edges()):
        if not ancestors.Contains(edge.wrapped):
            continue
        incident = list(ancestors.FindFromKey(edge.wrapped))
        if len(incident) != 2 or incident[0].IsSame(incident[1]):
            continue
        pair: list[PlanarFaceSignature] = []
        for shape in incident:
            position = face_index.FindIndex(shape)
            signature = signatures[position - 1] if position > 0 else None
            if signature is None:
                break
            pair.append(signature)
        if len(pair) == 2:
            adjacency[index] = sorted(pair, key=_adjacency_sort_key)
    return adjacency


def enumerate_edges_with_adjacency(body: BodyShape) -> list[EdgeRecord]:
    """:func:`enumerate_edges`, with each signature carrying its §14 adjacency.

    The PICK-side enumeration. Deliberately SEPARATE from :func:`enumerate_edges`
    rather than replacing it, because the two sides need different things and the
    costs are not symmetric: the resolve side matches a stored target against
    candidate signatures and never reads a CANDIDATE's adjacency (tier 3 resolves
    the target's stored faces against the body — :func:`_adjacency_matches`), so
    making the hot resolve path build a face signature per face would buy nothing
    and cost an outer-wire region per face on every rebuild.
    """
    adjacency = edge_adjacency(body)
    return [
        EdgeRecord(
            index=index,
            signature=edge_signature_dto(edge, adjacency.get(index)),
            edge=edge,
        )
        for index, edge in enumerate(body.edges())
    ]


def circle_axis(edge: Edge) -> tuple[float, float, float]:
    """The unit axis of a CIRCULAR edge's plane, from the exact B-rep circle.

    The one quantity a circular edge carries that its stage-1
    :class:`~loft_wire.features.EdgeSignature` cannot: a full circle stores only
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


def enumerate_edges(
    body: BodyShape, face_names: Sequence[str | None] | None = None
) -> list[EdgeRecord]:
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

    *face_names*, aligned with ``body.faces()``, names each record from the pair
    of faces it bounds (:func:`~geometry.kernel.naming.edge_names`).
    """
    names: list[str | None] | None = None
    if face_names is not None and len(face_names) == len(body.faces()):
        names = edge_names(body, face_names)
    return [
        EdgeRecord(
            index=index,
            signature=edge_signature_dto(edge),
            edge=edge,
            name=None if names is None else names[index],
        )
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

    Deliberately NOT the resilient entry point.
    :func:`geometry.drawings.anchor.resolve_anchor_edge` needs the strict answer
    on its own: it runs this as its tier 1 and reports which tier fired (an exact
    match and a re-anchored one are different facts to a drawing). Every
    FEATURE-tree consumer, and every assembly mate or joint origin (a joint moves
    with its hole, as in Fusion 360, RESEARCH §21), wants
    :func:`resolve_edge_durable` instead.

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
    "endpoints / midpoint / length), none shares its rebuild invariant (a "
    "straight edge's supporting line and span, a circle's centre, radius and "
    "angular station), and the two faces the edge bounded do not meet at a single edge "
    "on the rebuilt body; the referenced edge no longer exists after the "
    "rebuild. Re-pick the edge, or edit the upstream feature back to a state "
    "where it resolves."
)

#: Which tier of :func:`resolve_edge_durable` found the edge. The first two words
#: are deliberately the drawings wire vocabulary
#: (:data:`~loft_wire.drawings.DimensionAnchorTier`): what a consumer can DO
#: about a match is "it is where you left it" vs "it moved and I followed it".
#: ``adjacent`` is the §14 third tier — "the edge itself moved off every
#: coordinate I stored, and I found it again as the intersection of the two faces
#: it bounds". Since EDGE-RESOLVE-WARN-1 a DTO reports it, so this IS the wire
#: alias (:data:`~loft_wire.features.SubshapeResolutionTier`) — one vocabulary,
#: re-exported under its kernel name.
EdgeMatchTier = SubshapeResolutionTier


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


def _same_radius(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """True when two CIRCULAR signatures have the same radius (to the edge
    point tolerance); False when either has no centre."""
    t_centre = _circle_centre(target)
    c_centre = _circle_centre(candidate)
    if t_centre is None or c_centre is None:
        return False
    t_radius = math.dist(t_centre, _t(target.midpoint))
    c_radius = math.dist(c_centre, _t(candidate.midpoint))
    return abs(t_radius - c_radius) <= _EDGE_POINT_TOL_MM


def concentric_same_station_match(
    candidate: EdgeSignature, target: EdgeSignature
) -> bool:
    """Durable match for a CIRCULAR edge: same circle, same angular station.

    Same centre, same RADIUS, and the unit directions from the centre to the
    stored ``end_a`` / ``end_b`` / ``midpoint`` preserved; those directions also
    pin the circle's PLANE and, for an arc, its sweep, so a coaxial circle in a
    different plane or a different arc of the same circle is not accepted.
    Closedness must match too (a full circle never re-anchors onto an arc).

    NOT invariant under a radius change (EDGE-REF-CONCENTRIC, RESEARCH §14). It
    once was, so a resized bore's chamfered rim would follow; but then a picked
    edge whose own edge vanished re-anchored onto any CONCENTRIC edge of another
    radius left standing (the inner R3 rim arc of a deleted shell onto the outer
    R5 arc, a counterbore's R5 floor edge onto a pocket's R9 one) with status
    ok. A concentric circle of another radius is another edge, as in Fusion 360,
    where a fillet whose edge is gone is an error, never a different edge. A
    NAMED reference still follows its resized edge, through the named tier.
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
    if not _same_radius(candidate, target):
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
    centre, radius and angular station, and anything else (spline / ellipse —
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


# --------------------------------------------------------------------------- #
# TIER 3 — the ADJACENCY re-anchor (product audit 2026-09-16, §14)             #
# --------------------------------------------------------------------------- #
#
# THE DEFECT, measured before this tier existed, on the most ordinary edit there
# is. A gearbox housing (130 x 80 x 40, 3 mm wall, R8 corners, 4 x D8 holes — six
# features) with the sketch's width retyped 120 -> 150: `Fillet1 ERR
# SUBSHAPE_UNRESOLVED`, `Shell1` / `Hole1` / `Pattern1` SKIP, the part collapsed
# to a bare block of 480 000 mm^3 and 6 faces. Four of six features destroyed by
# one dimension edit. The auditor's verdict: "Yes for a first build, no for the
# second edit — that is the thing that sends an engineer back to Fusion."
#
# WHY TIER 2 CANNOT REACH IT, by construction rather than by tolerance. Every
# field of an EdgeSignature is an ABSOLUTE WORLD COORDINATE, and tier 2's
# straight-edge predicate re-matches on the edge's own SUPPORTING LINE. Widening
# the part TRANSLATES the vertical edges from x = 120 onto a parallel line 30 mm
# away: not collinear, so `collinear_overlapping_match` returns False for every
# candidate and no tolerance would change that. Tier 2 is durable against an edge
# being LENGTHENED OR SHORTENED IN PLACE; it is not durable against the part
# CHANGING SIZE. A dimension edit is the second thing.
#
# THE ASYMMETRY IS THE CLUE, and it is an existence proof rather than an analogy.
# Every FACE reference in that same tree re-resolved through 120 -> 150 -> 130,
# including Shell1's. §13 recorded why it looked as though edges could not follow:
# "freeing the perpendicular offset makes every parallel edge of the same length
# an equally good candidate ... a face's area and in-plane centroid carry an
# identity that an edge's direction and length do not." That is true of an edge's
# OWN geometry and it is the whole reason this tier does not work on the edge's
# geometry at all. An edge of a manifold solid IS the intersection of exactly two
# faces; a face's identity survives, through four tiers, precisely because it has
# an area and an in-plane centroid. So the identity an edge lacks in itself it
# borrows from its neighbours: resolve the two stored faces through the face
# matcher that already works, and take the edge they share.
#
# NOT GREEDY — STRICTLY MORE CONSTRAINED THAN THE RULE-BASED WORKAROUND. The
# audit's repair was to retarget the fillet BY RULE ("edges parallel to Z"), which
# rebuilds but selects a SET: all four vertical edges, which is not what the user
# picked. Tier 3 names ONE edge, and names it by a pair of faces, so the other
# three vertical edges of the widened box are not candidates at all — they bound
# different pairs.
#
# ORDER IS THE SAFETY PROPERTY, as in tier 2 and in faces.py: tier 3 runs ONLY on
# an EMPTY tier-2 result, so it can only turn an `unresolved` into a resolution or
# an honest ambiguity. It can never retarget a reference that already resolves,
# and `edge_signatures_match` deliberately does NOT compare adjacency, so adding
# the field changes no tier-1 outcome either.
#
# REFUSE TO GUESS (§7.2) — the tier has three ways to decline and takes all of
# them. A stored face that resolves to NOTHING, or to MORE THAN ONE face, makes
# the pair unusable and the edge stays `subshape_unresolved` (the face resolver's
# own honesty, inherited rather than re-litigated). Two faces that resolve
# uniquely but share MORE THAN ONE edge — two coplanar runs of one intersection
# line, e.g. a relief notch bitten out of the middle of a bottom-front edge — are
# genuinely two equally valid re-anchors, and that is `subshape_ambiguous`.


def _adjacency_matches(
    face_records: list[PlanarFaceRecord],
    records: list[EdgeRecord],
    target: EdgeSignature,
) -> list[EdgeRecord]:
    """Tier 3: the edges shared by *target*'s two re-resolved adjacent faces.

    Returns 0, 1 or >1 records, which :func:`_match_edge_records`'s caller maps
    onto its typed error exactly as for the tiers above. An empty result covers
    both "this signature carries no adjacency" (every selector authored before
    §14, and every edge without two distinct planar neighbours) and "a stored face
    no longer resolves uniquely" — in both cases the edge is honestly not found.

    The face side is NOT re-implemented here: each stored signature goes through
    :func:`geometry.kernel.faces.match_face_records`, the same four-tier matcher
    every picked-FACE consumer uses, so this tier is exactly as durable and
    exactly as honest as face resolution already is (CLAUDE.md DRY — one matcher,
    two consumers).
    """
    stored = target.adjacent_faces
    if stored is None or len(stored) != 2:
        return []

    resolved: list[Face] = []
    for signature in stored:
        matches, _tier = match_face_records_tiered(face_records, signature)
        if len(matches) != 1:
            # Zero -> that neighbour is gone; more than one -> the face resolver
            # itself refuses to guess, and a pair we cannot pin cannot pin an edge.
            return []
        resolved.append(matches[0].face)

    # OCCT shape identity (IsSame, orientation-blind), not a geometric re-compare:
    # the faces came from THIS body, so their edges ARE the records' edges.
    edge_index = TopTools_IndexedMapOfShape()
    for record in records:
        edge_index.Add(record.edge.wrapped)
    on_face = [
        {
            position
            for position in (edge_index.FindIndex(e.wrapped) for e in face.edges())
            if position > 0
        }
        for face in resolved
    ]
    shared = on_face[0] & on_face[1]
    return [
        record
        for record in records
        if edge_index.FindIndex(record.edge.wrapped) in shared
        and _same_curve(record.signature, target)
    ]


def _same_curve(candidate: EdgeSignature, target: EdgeSignature) -> bool:
    """Tier 3 keeps the curve: a circle re-anchors only onto a circle of the
    same radius (EDGE-REF-CONCENTRIC); a line moves freely with its faces."""
    if target.curve != "circle":
        return True
    return candidate.curve == "circle" and _same_radius(candidate, target)


def _match_edge_records(
    body: BodyShape,
    records: list[EdgeRecord],
    target: EdgeSignature,
    face_names: Sequence[str | None] | None = None,
) -> tuple[list[EdgeRecord], EdgeMatchTier]:
    """The three-tier picked-edge match shared by every feature-tree consumer.

    The edge twin of :func:`geometry.kernel.faces.match_face_records`, each tier
    reached ONLY when the one above it finds NOTHING:

    * **Tier 1 — strict** (:func:`edge_signatures_match`): curve kind, both
      canonical endpoints, midpoint and length. Exact on a clean rebuild.
    * **Tier 2 — durable** (:func:`durable_edge_match`): the rebuild invariant of
      the edge's curve kind — a straight edge's supporting line + span overlap, a
      circle's centre + radius + angular station. Models the edge growing or shrinking
      ALONG ITSELF.
    * **Tier 3 — adjacency** (:func:`_adjacency_matches`): the two PLANAR FACES
      the edge bounds, re-resolved through the four-tier face matcher. Models the
      edge being CARRIED somewhere else by a dimension edit that resizes the part
      — the case tiers 1 and 2 cannot reach because both pin an absolute position.

    Returns ``(matched records, tier)`` — the records (0, 1, or >1), which the
    caller maps onto its typed unresolved / ambiguous error, and which tier
    produced them.

    THE NAMED TIER (DESIGN-INTENT-REFS) follows the strict one under exactly
    the rule :func:`geometry.kernel.faces.match_face_records_tiered` states: a
    stored ``topo_name`` held by exactly one current edge (*records* carry the
    names) wins when tiers 2-3 find nothing or find several including it, and
    yields to them when they find edges without it. Without names, nothing
    here changes.

    THE NAME GUARD (EDGE-REF-CONCENTRIC): a tier-2/3 match of a NAMED reference
    whose edge the body names DIFFERENTLY is dropped before that rule runs. It
    is another edge standing where the referenced one was, not the referenced
    edge moved; Fusion 360 fails such a reference rather than move it. One
    guard for every edge-ref consumer (fillet, chamfer, edge flange, hem, a
    sketch projection). An unnamed reference, or an edge the body cannot name,
    is matched as before.
    """
    strict = [r for r in records if edge_signatures_match(r.signature, target)]
    if strict:
        return strict, "exact"
    geometric, tier = _geometric_edge_matches(body, records, target, face_names)
    name = target.topo_name
    if name is None:
        return geometric, tier
    names = _record_names(body, records, face_names)
    by_index = {r.index: n for r, n in zip(records, names, strict=True)}
    geometric = [r for r in geometric if by_index[r.index] in (None, name)]
    named = [r for r, n in zip(records, names, strict=True) if n == name]
    held = {r.index for r in named}
    if named and (not geometric or any(r.index in held for r in geometric)):
        return named, "named"
    return geometric, tier


def _record_names(
    body: BodyShape,
    records: list[EdgeRecord],
    face_names: Sequence[str | None] | None,
) -> list[str | None]:
    """Each record's name, aligned with *records*: ONE edge, or the pieces of
    one RUN, may share a name.

    The records' own ``name`` when they carry one; otherwise the body's edge
    names are worked out here, only once the strict tier has missed, so an
    unedited rebuild never pays for naming every edge. A name is only ever
    STORED from an edge that alone bounds its two faces; here it also reaches
    the pieces of that boundary when an edit cut it at a vertex (a cylinder's
    seam now crossing a blade's root curve), because the pieces are still the
    whole of the boundary between the same two faces (:func:`edge_names`
    ``runs``). All ``None`` when the body cannot be named."""
    names = [r.name for r in records]
    if all(n is None for n in names) and face_names is not None:
        computed = edge_names(body, face_names, runs=True)
        if len(computed) == len(records):
            return computed
    return names


def _geometric_edge_matches(
    body: BodyShape,
    records: list[EdgeRecord],
    target: EdgeSignature,
    face_names: Sequence[str | None] | None,
) -> tuple[list[EdgeRecord], EdgeMatchTier]:
    """Tiers 2-3 of :func:`_match_edge_records`."""
    durable = [r for r in records if durable_edge_match(r.signature, target)]
    if durable:
        return durable, "durable"
    if target.adjacent_faces is None:
        return [], "adjacent"
    face_records = planar_faces(body, face_names)
    return _adjacency_matches(face_records, records, target), "adjacent"


def _ambiguous(count: int, *, tier: EdgeMatchTier) -> SubshapeAmbiguousError:
    """The typed >1-match refusal, worded for the tier that produced it."""
    if tier == "adjacent":
        return SubshapeAmbiguousError(
            f"{count} edges of the current body are shared by BOTH faces the "
            "stored edge reference names, so they are equally valid re-anchors "
            "(the two faces meet along more than one run). Refusing to guess "
            "which one the feature meant — re-pick the edge."
        )
    if tier == "durable":
        return SubshapeAmbiguousError(
            f"{count} edges of the current body are equally valid re-anchors for "
            "the stored edge signature (collinear segments of one line overlapping "
            "its span, or coincident circles at the same angular station). "
            "Refusing to guess which one the feature meant — re-pick the edge."
        )
    return SubshapeAmbiguousError(
        f"{count} edges match the stored edge signature within tolerance; the "
        "reference is ambiguous (a congruent/symmetric edge). Refusing to guess — "
        "pick an edge without a congruent twin."
    )


def resolve_edge_durable(
    body: BodyShape,
    target: EdgeSignature,
    *,
    tally: ResolutionTally | None = None,
    face_names: Sequence[str | None] | None = None,
) -> ResolvedEdge:
    """Resolve a picked-edge reference against *body* — strict, then durable.

    THE feature-tree entry point (fillet / chamfer via
    :func:`_resolve_picked_edges`, sheet-metal edge flange + hem via the feature
    layer). Requires EXACTLY ONE match at whichever tier fires (§7.2 — refuse to
    guess) and returns the edge, its CURRENT signature, and the tier. *tally*,
    when given, is told that tier too (:mod:`geometry.kernel.resolution`).
    *face_names* (aligned with ``body.faces()``) enables the ``named`` tier,
    which here must also land on ONE edge: a fold needs a single straight edge,
    so the pieces of a run are ambiguous.

    Raises:
        SubshapeUnresolvedError: neither tier found the edge — it genuinely no
            longer exists (deleted, or moved off its own supporting line).
        SubshapeAmbiguousError: some tier found more than one candidate.
    """
    matches, tier = _match_edge_records(body, enumerate_edges(body), target, face_names)
    if not matches:
        raise SubshapeUnresolvedError(_UNRESOLVED_MESSAGE)
    if len(matches) > 1:
        raise _ambiguous(len(matches), tier=tier)
    if tally is not None:
        tally.note(tier)
    record = matches[0]
    return ResolvedEdge(edge=record.edge, signature=record.signature, tier=tier)


def resolve_edges_each(
    body: BodyShape,
    targets: Sequence[EdgeSignature],
    *,
    tally: ResolutionTally | None = None,
    face_names: Sequence[str | None] | None = None,
) -> list[ResolvedEdge | SubshapeUnresolvedError | SubshapeAmbiguousError]:
    """:func:`resolve_edge_durable` for many references at once, NON-RAISING.

    One answer per target, in target order: the resolved edge, or the typed
    error :func:`resolve_edge_durable` would have raised for it. The consumer is
    a sketch's projected entities (SKETCH-PROJECT-EDGES), where an edge that no
    longer resolves makes ONE entity sick and must not fail the others or the
    sketch, so a raise is the wrong shape. Each target needs exactly one edge,
    as there: the pieces of a named run are ambiguous.

    The body is enumerated ONCE for every target, and its edge names are worked
    out at most once, only when some target misses the strict tier (the
    records then carry them, which is exactly what :func:`_record_names` would
    compute per target). Only a resolved target is reported to *tally*, as a
    raising resolver reports nothing for the reference it raised on.

    A geometric re-find that the body names differently from the stored name
    is refused by :func:`_match_edge_records`'s name guard, as for every
    consumer (a projection would otherwise move sketch geometry with no error;
    Fusion 360 marks it sick instead).
    """
    records = enumerate_edges(body)
    named: list[EdgeRecord] | None = None
    out: list[ResolvedEdge | SubshapeUnresolvedError | SubshapeAmbiguousError] = []
    for target in targets:
        pool = records
        if face_names is not None and not any(
            edge_signatures_match(r.signature, target) for r in records
        ):
            if named is None:
                names = edge_names(body, face_names, runs=True)
                named = (
                    records
                    if len(names) != len(records)
                    else [
                        EdgeRecord(r.index, r.signature, r.edge, name)
                        for r, name in zip(records, names, strict=True)
                    ]
                )
            pool = named
        matches, tier = _match_edge_records(body, pool, target, face_names)
        if not matches:
            out.append(SubshapeUnresolvedError(_UNRESOLVED_MESSAGE))
            continue
        if len(matches) > 1:
            out.append(_ambiguous(len(matches), tier=tier))
            continue
        record = matches[0]
        if tally is not None:
            tally.note(tier)
        out.append(
            ResolvedEdge(edge=record.edge, signature=record.signature, tier=tier)
        )
    return out


def _resolve_picked_edges(
    body: BodyShape,
    selector: PickedEdgesSelector,
    tally: ResolutionTally | None,
    face_names: Sequence[str | None] | None = None,
) -> list[Edge]:
    """Resolve each picked edge ref to its edge; dedupe; return in body order.

    Every ref must resolve to exactly one edge through the SAME two-tier match
    :func:`resolve_edge_durable` uses (:func:`_match_edge_records`), against ONE
    shared enumeration. Two refs that resolve to the same edge collapse to one
    (idempotent). Returned in ``body.edges()`` order so the fillet/chamfer input is
    deterministic regardless of pick order (RESEARCH §9).

    This resolver returns the kernel :class:`Edge` itself, not a derived
    POSITION, so a durable match needs no re-anchoring — exactly the reasoning
    :func:`geometry.kernel.faces.resolve_faces` records for its own flag. The
    tier is still REPORTED to *tally*, once per ref (EDGE-RESOLVE-WARN-1).
    """
    records = enumerate_edges(body)
    chosen: dict[int, Edge] = {}
    for ref in selector.refs:
        matches, tier = _match_edge_records(
            body, records, ref.selector.signature, face_names
        )
        if not matches:
            raise SubshapeUnresolvedError(_UNRESOLVED_MESSAGE)
        if len(matches) > 1 and tier != "named":
            raise _ambiguous(len(matches), tier=tier)
        if tally is not None:
            tally.note(tier)
        # A named match of several records is ONE picked edge an edit cut into
        # pieces (a run, see _record_names): a fillet rounds all of it.
        for match in matches:
            chosen[match.index] = match.edge
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


def select_edges(
    body: BodyShape,
    selector: EdgeSelector,
    *,
    tally: ResolutionTally | None = None,
    face_names: Sequence[str | None] | None = None,
) -> list[Edge]:
    """Resolve an edge selector against *body* (design §2.4/§10).

    Deterministic: a PREDICATE selector filters ``body.edges()`` (OCCT's
    deterministic order) by a pure predicate; a PICKED selector matches each
    stage-1 signature against that same enumeration, exactly one or an honest
    error. Only a PICKED ref is a reference, so only those are reported to
    *tally* — a predicate re-selects by rule and has no tier to report.
    *face_names* (aligned with ``body.faces()``) enables the ``named`` tier.

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
            return _resolve_picked_edges(body, selector, tally, face_names)

    if not edges:
        raise NoEdgesSelectedError(
            "The edge selector matched no edge of the body; nothing to modify "
            "(the predicate selectors re-select edges geometrically — design "
            "§2.4)."
        )
    return edges
