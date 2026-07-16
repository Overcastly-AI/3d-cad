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
from dataclasses import dataclass
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

    try:
        algo = HLRBRep_Algo()
        algo.Add(topo)
        frame = gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(*normal), gp_Dir(*x_dir))
        algo.Projector(HLRAlgo_Projector(frame))
        algo.Update()
        algo.Hide()
        to_shape = HLRBRep_HLRToShape(algo)
        # VISIBLE = sharp + silhouette; HIDDEN = the same classes occluded (§1.3).
        # Rg1Line* (tangent/smooth) is suppressed in v1 (§1.3).
        visible_compounds = (to_shape.VCompound(), to_shape.OutLineVCompound())
        hidden_compounds = (to_shape.HCompound(), to_shape.OutLineHCompound())
        # Classification (BRepAdaptor_Curve / GetType / Value on each projected
        # edge) can ALSO throw on a degenerate edge — keep it inside the guard so
        # §1.5 holds end to end (never a raw OCCT exception past this call).
        edges: list[ProjectedEdge] = []
        for compound in visible_compounds:
            for curve in _iter_edges(compound):
                edges.append(_classify(curve, visible=True, scale=scale))
        for compound in hidden_compounds:
            for curve in _iter_edges(compound):
                edges.append(_classify(curve, visible=False, scale=scale))
    except Exception as exc:  # any OCCT throw is an honest per-view error (§1.5)
        raise ViewProjectionError(view, f"{type(exc).__name__}: {exc}") from exc

    # _canonicalize is pure Python (sort/de-dup on dataclasses) — no OCCT, so it
    # stays outside the guard.
    return ViewProjection(view=view, scale=scale, edges=_canonicalize(edges))


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
