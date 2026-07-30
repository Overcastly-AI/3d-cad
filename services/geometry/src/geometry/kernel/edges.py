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
    """Resolve a stage-1 edge signature to its edge (exactly one or an error).

    Matches *target* against the edges of *body* (:func:`enumerate_edges`) and
    requires EXACTLY ONE match (§7.2 — refuse to guess).

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
        raise SubshapeUnresolvedError(
            "No edge of the current body matches the stored edge signature "
            "(curve / endpoints / midpoint / length); the referenced edge no "
            "longer exists after the rebuild. Re-pick the edge, or edit the "
            "upstream feature back to a state where it resolves."
        )
    if len(matches) > 1:
        raise SubshapeAmbiguousError(
            f"{len(matches)} edges match the stored edge signature within "
            "tolerance; the reference is ambiguous (a congruent/symmetric edge). "
            "Refusing to guess — pick an edge without a congruent twin."
        )
    return matches[0].edge


def _resolve_picked_edges(body: BodyShape, selector: PickedEdgesSelector) -> list[Edge]:
    """Resolve each picked edge ref to its edge; dedupe; return in body order.

    Every ref must resolve to exactly one edge (:func:`resolve_edge`). Two refs
    that resolve to the same edge collapse to one (idempotent). Returned in
    ``body.edges()`` order so the fillet/chamfer input is deterministic
    regardless of pick order (RESEARCH §9).
    """
    records = enumerate_edges(body)
    chosen: dict[int, Edge] = {}
    for ref in selector.refs:
        target = ref.selector.signature
        matches = [r for r in records if edge_signatures_match(r.signature, target)]
        if not matches:
            raise SubshapeUnresolvedError(
                "No edge of the current body matches a picked edge signature "
                "(curve / endpoints / midpoint / length); the referenced edge no "
                "longer exists after the rebuild. Re-pick it, or edit the upstream "
                "feature back to a state where it resolves."
            )
        if len(matches) > 1:
            raise SubshapeAmbiguousError(
                f"{len(matches)} edges match a picked edge signature within "
                "tolerance; the reference is ambiguous (a congruent/symmetric "
                "edge). Refusing to guess — pick an edge without a congruent twin."
            )
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
