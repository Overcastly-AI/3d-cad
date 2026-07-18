"""Exact HLR projection of a body to canonically-ordered 2D edges (design §1).

Pipeline (docs/design/drawings.md §1.2/§1.3/§1.4):

1. Map a standard view (``front``/``top``/``right``/``iso``) to a projection
   frame ``gp_Ax2`` — the outward view normal ``N`` (model→eye) plus the pinned
   in-plane ``x_dir`` (§1.2's world-axis table). The projector's own y-axis is
   ``N x x_dir``, which equals the table's ``+y`` for every standard view (proven
   by the goldens), so the frame reproduces byte-for-byte with no free choice.
2. Run OCCT **exact** HLR (``HLRBRep_Algo``): ``Add`` the shape, set the
   ``Projector``, ``Update`` then ``Hide``. Classify the result through
   ``HLRBRep_HLRToShape`` into VISIBLE (``VCompound`` sharp + ``OutLineVCompound``
   silhouette) and HIDDEN (``HCompound`` + ``OutLineHCompound``) edge sets (§1.3).
   Tangent/smooth ``Rg1Line*`` edges are suppressed in v1 (§1.3).
3. The HLR output edges already lie in the projection plane with depth zeroed, so
   each is a genuine 2D edge. Classify every edge into a neutral primitive —
   **line**, **circle**, **arc**, or **polyline** (only genuinely free-form curves
   are sampled; real lines/circles stay exact) — with orientation-independent
   canonical endpoints (§1.3).
4. Impose the **canonical total order** (§1.4, the load-bearing determinism
   constraint): HLR edge enumeration order is a function of construction history,
   NOT geometry, so the output is de-duplicated (exact coincident edges collapse;
   a hidden edge coincident with a visible one is dropped — visible wins, §8 open
   Q2) and sorted by each edge's geometric signature. Same body + same view ⇒
   byte-identical edge list, in-process AND across an interpreter restart (§8.2,
   RESEARCH §9) — asserted by the golden restart probe, not merely claimed.

Honest failure (§1.5): ``HLRBRep_Algo`` is occasionally fragile (tangent edges,
self-intersections). Any kernel throw becomes a typed :class:`ViewProjectionError`
(the internal form of the per-view ``view_projection_failed`` the endpoint slice
will surface) — never an unhandled exception, and no improvised fallback engine
(poly-HLR is an explicitly deferred escape hatch, §1.1).

Determinism (RESEARCH §9): OCCT HLR is itself deterministic (no RNG; same body +
projector ⇒ same edges, in-process and across a restart); the ONE
nondeterministic-by-construction property — edge order — is pinned by the
canonical sort here, and coordinates are emitted through a fixed decimal formatter
(:func:`canonical_edges_repr`) with no locale or trailing-zero drift.
"""
# The OCP wheel ships no type stubs, so the raw OCCT projector/explorer calls
# below are opaque to pyright; these directives scope that relaxation to this file
# only (the same posture as geometry.kernel.imports / assembly.resolve), and the
# fully-typed Solid input + ProjectedEdge output keep the boundary honest.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Literal

from build123d import Solid
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from py_kit.schemas.features import EdgeSignature
from py_kit.schemas.geometry import Vec3

from geometry.kernel.edges import EdgeRecord, enumerate_edges

#: The standard orthographic + isometric directions v1 supports (design §1.2).
#: Section / detail / auxiliary / custom views are deferred (§1.5/§7).
ViewDirection = Literal["front", "top", "right", "iso"]

#: The neutral 2D primitive kinds an HLR edge classifies into (§1.3). Real lines
#: and circles stay EXACT (a diameter dimension reads a true radius, §1.1); only
#: genuinely free-form curves degrade to a sampled ``polyline``.
EdgePrimitive = Literal["line", "circle", "arc", "polyline"]

#: Number of vertices a free-form (BSpline/ellipse) edge is sampled to. A circle
#: seen edge-on can degenerate to a straight BSpline; sampling still renders it
#: faithfully. Real lines/circles never take this path, so the count only affects
#: genuinely curved output. Documented (not ad-hoc) — determinism needs it fixed.
_POLYLINE_SAMPLES = 33

#: Coordinate rounding (decimals, model mm) for the de-dup / coincidence-cull KEY
#: only — it never alters emitted coordinates, only decides which edges are "the
#: same" 2D edge. Sized to the kernel's ``edges.py`` endpoint tolerance
#: (``_EDGE_POINT_TOL_MM`` = 1e-6): two distinct edges of an authored part
#: separate by whole mm, a coincident pair matches to ulp scale.
_KEY_DECIMALS = 6

#: Coordinate rounding (decimals, model mm) for the canonical SERIALISATION
#: (:func:`canonical_edges_repr`, the §8.2 byte-determinism gate). One digit finer
#: than the cull key so distinct-but-near geometry never serialises identically;
#: still coarse enough to absorb sub-ulp kernel jitter into a stable string.
_SERIALIZE_DECIMALS = 7

#: A parametric span within this of 2*pi marks a CLOSED circle (vs. an arc). The
#: kernel builds full-turn circles to ulp; the bound only separates a true circle
#: from a near-complete arc, never two authored arcs.
_CLOSED_SPAN_TOL = 1e-6

#: Depth (along the outward view normal N) tie-break tolerance (mm) for the
#: provenance disambiguation of two model edges that project to the SAME 2D edge
#: (a box's coincident top/bottom face edges, §3.3). The nearer-the-eye edge (max
#: depth for a visible projected edge) is the true source; two model edges within
#: this depth are a GENUINE 3D coincidence (a boolean seam) → honest ambiguity, no
#: signature. Sized to the kernel edge endpoint tolerance (``_EDGE_POINT_TOL_MM``).
_DEPTH_TIE_TOL = 1e-6

#: How parallel a circular model edge's axis must be to the view normal for the
#: edge to project to a TRUE circle/arc (``|axis . N| >= 1 - tol``) — the condition
#: under which a diameter/radius dimension edge is provenance-mappable (design
#: §3.3). A foreshortened circle projects to an ellipse (an HLR outline/polyline,
#: never a sharp circle), so it carries no circle provenance — honest (§1.5). A
#: dimensionless (sin-scale) angular bound, the ``edges.py`` direction-tol twin.
_AXIS_PARALLEL_TOL = 1e-7

#: Canonical primitive sort rank (§1.4) — the first component of the total order.
_PRIMITIVE_RANK: dict[EdgePrimitive, int] = {
    "line": 0,
    "circle": 1,
    "arc": 2,
    "polyline": 3,
}


class ViewProjectionError(RuntimeError):
    """Exact HLR failed to project this view (design §1.5).

    The internal form of the per-view ``view_projection_failed`` outcome: a
    fragile body (tangent edges, self-intersections) makes ``HLRBRep_Algo`` throw,
    and the projection wraps that into this typed error rather than letting a raw
    OCCT exception escape. The endpoint slice maps it to the honest per-view error
    code; v1 improvises no fallback engine (poly-HLR is deferred, §1.1).
    """

    def __init__(self, view: str, message: str) -> None:
        super().__init__(f"HLR projection failed for the '{view}' view: {message}")
        self.view = view


@dataclass(frozen=True, order=True)
class Point2D:
    """A point in the view plane (model mm times the view scale). Ordered so it
    participates directly in the canonical edge sort key (§1.4)."""

    x: float
    y: float


@dataclass(frozen=True)
class ProjectedEdge:
    """One classified 2D edge of a view (design §1.3) — a neutral primitive, never
    a kernel handle.

    ``visible`` distinguishes solid (drawn ``True``) from hidden/dashed (``False``,
    the occluded side). ``start``/``end`` are the canonical (orientation-
    independent) endpoints and ``midpoint`` a point ON the edge — together they
    sign the edge for the canonical order and for a future dimension→edge trace.
    ``center``/``radius`` are populated for ``circle``/``arc`` (a real projected
    circle a Ø-dimension reads off, §1.1); ``points`` holds the sampled vertices
    of a ``polyline`` (empty for the analytic kinds).
    """

    primitive: EdgePrimitive
    visible: bool
    start: Point2D
    end: Point2D
    midpoint: Point2D
    center: Point2D | None = None
    radius: float | None = None
    points: tuple[Point2D, ...] = ()
    #: Provenance (design §3.3), attached AFTER classification. ``compare=False``
    #: keeps it OUT of the dataclass eq/hash AND out of the canonical keys, so the
    #: provenance NEVER perturbs the §1.4 canonical order or the byte-stable
    #: serialisation (:func:`canonical_edges_repr`). ``source_edge`` is the shipped
    #: :class:`EdgeSignature` of the single model edge this projected edge came from
    #: (``None`` for a silhouette/free-form/ambiguous edge — §1.5); ``dimensionable``
    #: is ``True`` iff that source is unambiguous.
    source_edge: EdgeSignature | None = field(default=None, compare=False)
    dimensionable: bool = field(default=False, compare=False)
    #: Model→projected endpoint correspondence for a STRAIGHT dimensionable edge
    #: (design §3.3): ``True`` iff the emitted (lexicographically canonical)
    #: ``start`` projected point corresponds to the source model edge's canonical
    #: ``end_a`` (``False`` → it corresponds to ``end_b``). The one bit the
    #: canonicalisation of ``start``/``end`` would otherwise throw away — it lets a
    #: point-to-point linear dimension name the correct model endpoint from a picked
    #: projected end WITHOUT the caller re-deriving the view frame + projection.
    #: ``None`` for a non-straight edge (circle/arc/polyline) or any edge without a
    #: single clean model source (silhouette/free-form/ambiguous, §1.5) — the same
    #: optional-provenance discipline as ``source_edge``. ``compare=False`` keeps it
    #: OUT of the canonical keys, so it NEVER perturbs the §1.4 order or the
    #: byte-stable serialisation.
    start_is_end_a: bool | None = field(default=None, compare=False)

    def _points_key(self) -> tuple[tuple[float, float], ...]:
        """The rounded interior sample points — the identity of a ``polyline``
        whose analytic ``start``/``end``/``midpoint`` do NOT disambiguate it (two
        genuinely different free-form silhouettes can share those three points but
        differ in curvature). Empty for the analytic kinds (``points`` is ``()``),
        so folding it into the keys is a no-op there and closes the gap where two
        distinct polylines collide → silent de-dup / non-deterministic tie."""
        return tuple(_round_point(p) for p in self.points)

    def geometry_key(self) -> tuple[object, ...]:
        """The geometry-only signature (visibility excluded) — the coincidence key
        for de-dup / visible-wins culling (§8 open Q2)."""
        return (
            self.primitive,
            _round_point(self.start),
            _round_point(self.end),
            _round_point(self.midpoint),
            _round_point(self.center) if self.center is not None else None,
            round(self.radius, _KEY_DECIMALS) if self.radius is not None else None,
            self._points_key(),
        )

    def sort_key(self) -> tuple[object, ...]:
        """The canonical TOTAL order key (§1.4): primitive rank, then rounded
        start/end/mid, then radius, then the polyline sample points, then
        visibility. A pure function of geometry, so the order is independent of
        HLR's construction-history enumeration."""
        return (
            _PRIMITIVE_RANK[self.primitive],
            _round_point(self.start),
            _round_point(self.end),
            _round_point(self.midpoint),
            round(self.radius, _KEY_DECIMALS) if self.radius is not None else -1.0,
            self._points_key(),
            not self.visible,  # visible (False→0) sorts before hidden on a tie
        )


@dataclass(frozen=True)
class ViewProjection:
    """The full projected view — its canonically-ordered edges plus provenance.

    ``edges`` is the merged visible+hidden list in canonical order (§1.4); the two
    convenience accessors filter it without changing the order. ``scale`` and
    ``view`` echo the request so the result is self-describing.
    """

    view: ViewDirection
    scale: float
    edges: tuple[ProjectedEdge, ...]

    @property
    def visible_edges(self) -> tuple[ProjectedEdge, ...]:
        """The solid-drawn edges, in canonical order."""
        return tuple(e for e in self.edges if e.visible)

    @property
    def hidden_edges(self) -> tuple[ProjectedEdge, ...]:
        """The dashed-drawn (occluded) edges, in canonical order."""
        return tuple(e for e in self.edges if not e.visible)


def _round_point(point: Point2D) -> tuple[float, float]:
    """A point's coincidence-key coordinates (kills ``-0.0`` so it never splits a
    key from its ``+0.0`` twin)."""
    return (round(point.x, _KEY_DECIMALS) + 0.0, round(point.y, _KEY_DECIMALS) + 0.0)


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


# The standard isometric frame (§1.2, design table "(-1,-1,+1)-family"): outward
# view normal N pinned to the normalized (-1,-1,+1) eye direction; the in-plane
# x-axis pinned by rule to (worldUp x N) so the frame is reproducible byte-for-
# byte (never left to OCCT's default). worldUp = +Z is not parallel to this N, so
# the cross is well-defined. The projector's y-axis is then N x x_dir.
_ISO_N = _normalize((-1.0, -1.0, 1.0))
_ISO_X = _normalize(_cross((0.0, 0.0, 1.0), _ISO_N))

#: A projection frame: (outward view normal N (model→eye), in-plane +x direction).
_Frame = tuple[tuple[float, float, float], tuple[float, float, float]]

#: view → frame. N x x_dir yields the design table's +y for every entry (goldens
#: prove it). Front looks from -Y, Top from +Z, Right from +X — the world
#: convention datums/faces use.
_VIEW_FRAMES: dict[ViewDirection, _Frame] = {
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    "top": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "iso": (_ISO_N, _ISO_X),
}


def _iter_edges(shape: TopoDS_Shape | None) -> list[BRepAdaptor_Curve]:
    """Every edge of an HLR result compound as a curve adaptor (empty for a null
    compound — an absent classifier, e.g. no silhouette on a prism)."""
    curves: list[BRepAdaptor_Curve] = []
    if shape is None or shape.IsNull():
        return curves
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        curves.append(BRepAdaptor_Curve(TopoDS.Edge_s(explorer.Current())))
        explorer.Next()
    return curves


def _canonical_segment(start: Point2D, end: Point2D) -> tuple[Point2D, Point2D]:
    """Order two endpoints lexicographically — orientation independence (§1.3):
    the signature must not depend on which way OCCT walked the edge (the same
    subtlety ``kernel.edges._canonical_endpoints`` handles for 3D edges)."""
    return (start, end) if start <= end else (end, start)


def _classify(
    curve: BRepAdaptor_Curve, *, visible: bool, scale: float
) -> ProjectedEdge:
    """Classify one projected HLR edge into its neutral 2D primitive (§1.3).

    The HLR output already lies in the view plane with depth zeroed, so the
    adaptor's X/Y ARE the 2D coordinates; every emitted value is the exact
    coordinate times ``scale``. A ``GeomAbs_Line`` stays a line, a ``GeomAbs_Circle``
    a full circle or an arc (a real radius, §1.1), anything else is sampled to a
    polyline.
    """
    u0 = curve.FirstParameter()
    u1 = curve.LastParameter()

    def at(u: float) -> Point2D:
        p = curve.Value(u)
        return Point2D(p.X() * scale, p.Y() * scale)

    kind = curve.GetType()
    if kind == GeomAbs_Line:
        start, end = _canonical_segment(at(u0), at(u1))
        return ProjectedEdge(
            primitive="line",
            visible=visible,
            start=start,
            end=end,
            midpoint=at(0.5 * (u0 + u1)),
        )
    if kind == GeomAbs_Circle:
        circ = curve.Circle()
        loc = circ.Location()
        center = Point2D(loc.X() * scale, loc.Y() * scale)
        radius = float(circ.Radius()) * scale
        if abs((u1 - u0) - 2.0 * math.pi) <= _CLOSED_SPAN_TOL:
            # A full circle: pin start/end/mid to canonical points DERIVED from
            # center+radius (not the arbitrary seam parameter) so the signature is
            # a pure function of the geometry, not of where OCCT closed the loop.
            start = Point2D(center.x + radius, center.y)
            return ProjectedEdge(
                primitive="circle",
                visible=visible,
                start=start,
                end=start,
                midpoint=Point2D(center.x - radius, center.y),
                center=center,
                radius=radius,
            )
        start, end = _canonical_segment(at(u0), at(u1))
        return ProjectedEdge(
            primitive="arc",
            visible=visible,
            start=start,
            end=end,
            midpoint=at(0.5 * (u0 + u1)),  # a point ON the arc — orientation free
            center=center,
            radius=radius,
        )
    # Genuinely free-form (BSpline / ellipse, or a circle degenerate edge-on):
    # sample deterministically. Real lines/circles never reach here.
    points = tuple(
        at(u0 + (u1 - u0) * i / (_POLYLINE_SAMPLES - 1))
        for i in range(_POLYLINE_SAMPLES)
    )
    start, end = _canonical_segment(points[0], points[-1])
    return ProjectedEdge(
        primitive="polyline",
        visible=visible,
        start=start,
        end=end,
        midpoint=points[len(points) // 2],
        points=points,
    )


def _canonicalize(edges: list[ProjectedEdge]) -> tuple[ProjectedEdge, ...]:
    """De-dup, cull hidden-behind-visible, and impose the canonical order (§1.4).

    1. Collapse EXACT coincident duplicates within a visibility class (a box's two
       identical projected verticals from front and back faces, §8 open Q2).
    2. Drop any hidden edge coincident with a visible edge — VISIBLE WINS (§8 open
       Q2 tie-break): a solid line is never also drawn dashed.
    3. Sort by the pure-geometry :meth:`ProjectedEdge._sort_key` so the order is a
       function of geometry, not HLR's construction-history enumeration.
    """
    unique: dict[tuple[bool, tuple[object, ...]], ProjectedEdge] = {}
    for edge in edges:
        unique.setdefault((edge.visible, edge.geometry_key()), edge)
    visible_geoms = {edge.geometry_key() for edge in unique.values() if edge.visible}
    kept = [
        edge
        for edge in unique.values()
        if edge.visible or edge.geometry_key() not in visible_geoms
    ]
    kept.sort(key=lambda e: e.sort_key())
    return tuple(kept)


def view_normal(view: ViewDirection) -> tuple[float, float, float]:
    """The outward view normal N (model→eye) of a standard view (design §1.2).

    The SAME frame the projection uses (``_VIEW_FRAMES``), exposed so the
    measurement layer (:mod:`geometry.drawings.measure`) can flag foreshortening
    (design §3.2) against the identical convention — no parallel axis table.
    """
    return _VIEW_FRAMES[view][0]


@dataclass
class _ModelEdgeProjection:
    """One model edge's projected identity for provenance (design §3.3).

    ``signature`` is the shipped 3D :class:`EdgeSignature` a dimension names;
    ``depth`` is the edge midpoint's coordinate along the outward view normal N —
    the tie-break that picks the nearer-the-eye edge when two model edges project
    to the same 2D edge (a box's coincident top/bottom edges). Not frozen (it
    holds an unhashable pydantic signature and is only ever list-stored)."""

    signature: EdgeSignature
    depth: float
    #: For a STRAIGHT model edge: does the projected edge's canonical ``start``
    #: correspond to this edge's canonical ``end_a`` (design §3.3)? ``None`` for a
    #: circle/arc (no straight-endpoint correspondence). Captured here, BEFORE the
    #: projected ``start``/``end`` are canonicalised away, and carried to the
    #: attached projected edge.
    start_is_end_a: bool | None = None


def _project_model_edge(
    record: EdgeRecord,
    normal: tuple[float, float, float],
    x_dir: tuple[float, float, float],
    y_dir: tuple[float, float, float],
    scale: float,
) -> tuple[tuple[object, ...], _ModelEdgeProjection] | None:
    """Project one MODEL edge into the view plane, returning its ``geometry_key``
    and provenance record — or ``None`` when it has no clean single-edge projection.

    Mirrors :func:`_classify` EXACTLY (same canonical endpoints, same full-circle
    cardinal-point derivation, same rounding via ``geometry_key``) so a model
    edge's key is byte-for-byte the key of the HLR-projected edge it produced —
    the tie that lets a projected edge resolve back to its model ``EdgeSignature``.
    Returns ``None`` for a genuinely free-form edge (spline/ellipse) and for a
    foreshortened circle (axis not parallel to N → projects to an ellipse, an HLR
    outline/polyline, never a sharp circle): those are un-dimensionable (§1.5).
    """
    curve = BRepAdaptor_Curve(record.edge.wrapped)
    u0 = curve.FirstParameter()
    u1 = curve.LastParameter()

    def at(u: float) -> Point2D:
        p = curve.Value(u)
        px, py, pz = p.X(), p.Y(), p.Z()
        x = px * x_dir[0] + py * x_dir[1] + pz * x_dir[2]
        y = px * y_dir[0] + py * y_dir[1] + pz * y_dir[2]
        return Point2D(x * scale, y * scale)

    def depth_of(u: float) -> float:
        p = curve.Value(u)
        return p.X() * normal[0] + p.Y() * normal[1] + p.Z() * normal[2]

    def project_world(v: Vec3) -> Point2D:
        """Project a MODEL-space point (world mm) into the view plane — the same
        affine map ``at`` applies to a curve sample, fed a signature endpoint."""
        x = v.x * x_dir[0] + v.y * x_dir[1] + v.z * x_dir[2]
        y = v.x * y_dir[0] + v.y * y_dir[1] + v.z * y_dir[2]
        return Point2D(x * scale, y * scale)

    kind = curve.GetType()
    mid_u = 0.5 * (u0 + u1)
    depth = depth_of(mid_u)
    start_is_end_a: bool | None = None

    if kind == GeomAbs_Line:
        start, end = _canonical_segment(at(u0), at(u1))
        edge = ProjectedEdge(
            primitive="line", visible=False, start=start, end=end, midpoint=at(mid_u)
        )
        # Which of the model edge's canonical endpoints does the emitted (canonical)
        # `start` project from? `_canonical_segment` picks the lexicographically
        # smaller 2D point, so `start` == proj(end_a) iff proj(end_a) <= proj(end_b)
        # — the one bit the canonicalisation drops. Captured NOW, from the SAME
        # canonical `end_a`/`end_b` a picked EdgeSignature carries, so a picked
        # projected end maps to the right model endpoint with no re-projection.
        proj_a = project_world(record.signature.end_a)
        proj_b = project_world(record.signature.end_b)
        start_is_end_a = proj_a <= proj_b
    elif kind == GeomAbs_Circle:
        circ = curve.Circle()
        axis = circ.Axis().Direction()
        # |axis . N|: a true circle/arc only when the circle plane faces the view
        # (axis parallel to N). Otherwise it foreshortens to an ellipse (§1.5).
        axis_dot = abs(
            axis.X() * normal[0] + axis.Y() * normal[1] + axis.Z() * normal[2]
        )
        if axis_dot < 1.0 - _AXIS_PARALLEL_TOL:
            return None
        loc = circ.Location()
        center = Point2D(
            (loc.X() * x_dir[0] + loc.Y() * x_dir[1] + loc.Z() * x_dir[2]) * scale,
            (loc.X() * y_dir[0] + loc.Y() * y_dir[1] + loc.Z() * y_dir[2]) * scale,
        )
        radius = float(circ.Radius()) * scale
        if abs((u1 - u0) - 2.0 * math.pi) <= _CLOSED_SPAN_TOL:
            cardinal = Point2D(center.x + radius, center.y)
            edge = ProjectedEdge(
                primitive="circle",
                visible=False,
                start=cardinal,
                end=cardinal,
                midpoint=Point2D(center.x - radius, center.y),
                center=center,
                radius=radius,
            )
        else:
            start, end = _canonical_segment(at(u0), at(u1))
            edge = ProjectedEdge(
                primitive="arc",
                visible=False,
                start=start,
                end=end,
                midpoint=at(mid_u),
                center=center,
                radius=radius,
            )
    else:
        return None

    return edge.geometry_key(), _ModelEdgeProjection(
        signature=record.signature, depth=depth, start_is_end_a=start_is_end_a
    )


def _model_edge_index(
    shape: Solid,
    normal: tuple[float, float, float],
    x_dir: tuple[float, float, float],
    y_dir: tuple[float, float, float],
    scale: float,
) -> dict[tuple[object, ...], list[_ModelEdgeProjection]]:
    """Index every model edge by its projected ``geometry_key`` (design §3.3).

    Reuses the shipped :func:`geometry.kernel.edges.enumerate_edges` — the SAME
    ``body.edges()`` enumeration + :func:`edge_signature_dto` a picked-edge fillet
    and the ``/overlay`` pick surface use — so a projected edge's provenance IS the
    signature the rest of the app resolves (no parallel taxonomy). A key collides
    ONLY when two model edges project to the same 2D edge (coincident faces); the
    list preserves both for the depth tie-break.
    """
    index: dict[tuple[object, ...], list[_ModelEdgeProjection]] = {}
    for record in enumerate_edges(shape):
        projected = _project_model_edge(record, normal, x_dir, y_dir, scale)
        if projected is None:
            continue
        key, entry = projected
        index.setdefault(key, []).append(entry)
    return index


def _attach_provenance(
    edge: ProjectedEdge,
    index: dict[tuple[object, ...], list[_ModelEdgeProjection]],
) -> ProjectedEdge:
    """Tag one SHARP projected edge with the model ``EdgeSignature`` it came from.

    Look the edge's ``geometry_key`` up in the model-edge index (design §3.3):

    * exactly one model edge → attach its signature, ``dimensionable = True``;
    * several (a coincident projection) → the nearer-the-eye edge is the true
      source (max depth for a visible edge, min for hidden). A UNIQUE extreme
      wins; a genuine 3D coincidence (equal depth, e.g. a boolean seam) stays
      un-dimensionable — honest ambiguity, never a wrong signature (§1.5);
    * none (a silhouette/outline or free-form edge) → left un-dimensionable.
    """
    candidates = index.get(edge.geometry_key())
    if not candidates:
        return edge
    if len(candidates) == 1:
        return replace(
            edge,
            source_edge=candidates[0].signature,
            dimensionable=True,
            start_is_end_a=candidates[0].start_is_end_a,
        )
    depths = [c.depth for c in candidates]
    target = max(depths) if edge.visible else min(depths)
    front = [c for c in candidates if abs(c.depth - target) <= _DEPTH_TIE_TOL]
    if len(front) == 1:
        return replace(
            edge,
            source_edge=front[0].signature,
            dimensionable=True,
            start_is_end_a=front[0].start_is_end_a,
        )
    return edge


def project_view(
    shape: Solid,
    view: ViewDirection,
    scale: float = 1.0,
) -> ViewProjection:
    """Project *shape* to canonically-ordered visible/hidden 2D edges (design §1).

    *shape* is an exact body — the ``build123d`` ``Solid`` that
    :func:`geometry.features.evaluate_tree` yields — fed straight to exact HLR
    through its ``.wrapped`` ``TopoDS_Shape`` with no re-tessellation (§1.1). An
    assembly compound (a view of an assembly, §1.2) is a later slice. *view*
    selects a
    standard projection frame (§1.2); *scale* multiplies every emitted coordinate
    (model mm → sheet mm), and must be strictly positive so the canonical order is
    preserved (a positive scale is monotone on every coordinate).

    Returns a :class:`ViewProjection` whose ``edges`` are byte-deterministic across
    a fresh interpreter (§1.4 / RESEARCH §9). Raises :class:`ViewProjectionError`
    if HLR throws (§1.5) — never an unhandled OCCT exception.

    Raises:
        ValueError: ``scale`` is not strictly positive (the endpoint slice rejects
            this at request validation; this guards direct kernel use).
        ViewProjectionError: exact HLR failed on this body/view (§1.5).
    """
    if scale <= 0.0:
        raise ValueError(f"View scale must be strictly positive, got {scale!r}")
    topo: TopoDS_Shape = shape.wrapped
    normal, x_dir = _VIEW_FRAMES[view]
    y_dir = _cross(normal, x_dir)

    try:
        algo = HLRBRep_Algo()
        algo.Add(topo)
        frame = gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(*normal), gp_Dir(*x_dir))
        algo.Projector(HLRAlgo_Projector(frame))
        algo.Update()
        algo.Hide()
        to_shape = HLRBRep_HLRToShape(algo)
        # SHARP = real model edges (``V``/``HCompound``) — provenance-mappable to a
        # model ``EdgeSignature`` (§3.3). OUTLINE = silhouette/apparent-contour
        # edges (``OutLine*``) — NOT model edges, so never dimensionable (§1.5).
        # Rg1Line* (tangent/smooth) is suppressed in v1 (§1.3).
        # Classification (BRepAdaptor_Curve / GetType / Value on each projected
        # edge) can ALSO throw on a degenerate edge — keep it inside the guard so
        # §1.5 holds end to end (never a raw OCCT exception past this call).
        sharp: list[ProjectedEdge] = []
        outline: list[ProjectedEdge] = []
        for curve in _iter_edges(to_shape.VCompound()):
            sharp.append(_classify(curve, visible=True, scale=scale))
        for curve in _iter_edges(to_shape.HCompound()):
            sharp.append(_classify(curve, visible=False, scale=scale))
        for curve in _iter_edges(to_shape.OutLineVCompound()):
            outline.append(_classify(curve, visible=True, scale=scale))
        for curve in _iter_edges(to_shape.OutLineHCompound()):
            outline.append(_classify(curve, visible=False, scale=scale))
        # The model-edge provenance index also touches OCCT (BRepAdaptor on each
        # model edge), so it stays inside the guard (§1.5).
        model_index = _model_edge_index(shape, normal, x_dir, y_dir, scale)
    except Exception as exc:  # any OCCT throw is an honest per-view error (§1.5)
        raise ViewProjectionError(view, f"{type(exc).__name__}: {exc}") from exc

    # Provenance + _canonicalize are pure Python (dict lookups / sort / de-dup on
    # dataclasses) — no OCCT, so they stay outside the guard. Provenance does NOT
    # touch the canonical keys (§1.4), so the order + serialised bytes are
    # unchanged; sharp is listed before outline so a sharp edge wins any de-dup tie
    # over a coincident silhouette (visible provenance is never lost).
    tagged = [_attach_provenance(e, model_index) for e in sharp]
    return ViewProjection(view=view, scale=scale, edges=_canonicalize(tagged + outline))


def _fmt(value: float) -> str:
    """One coordinate as a fixed-decimal string — no locale, no trailing-zero
    drift, ``-0.0`` normalised to ``0.0`` (the §1.4 fixed formatter)."""
    return f"{round(value, _SERIALIZE_DECIMALS) + 0.0:.{_SERIALIZE_DECIMALS}f}"


def _fmt_point(point: Point2D | None) -> str:
    if point is None:
        return "-"
    return f"({_fmt(point.x)},{_fmt(point.y)})"


def canonical_edges_repr(projection: ViewProjection) -> str:
    """A byte-deterministic string form of a view's edges (the §8.2 gate).

    One line per edge, in the canonical order (§1.4), each field through the fixed
    decimal formatter. Same body + same view ⇒ identical bytes, in-process and
    across an interpreter restart — the drawings analogue of the pinned STEP byte
    range (``geometry.kernel.export``). The golden restart probe diffs exactly
    this string.
    """
    lines: list[str] = [f"view={projection.view} scale={_fmt(projection.scale)}"]
    for edge in projection.edges:
        radius = "-" if edge.radius is None else _fmt(edge.radius)
        points = "|".join(_fmt_point(p) for p in edge.points)
        lines.append(
            f"{edge.primitive}\t{'V' if edge.visible else 'H'}\t"
            f"{_fmt_point(edge.start)}\t{_fmt_point(edge.end)}\t"
            f"{_fmt_point(edge.midpoint)}\t{_fmt_point(edge.center)}\t"
            f"{radius}\t[{points}]"
        )
    return "\n".join(lines)
