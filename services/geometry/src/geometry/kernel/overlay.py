"""Pickable selection geometry of an evaluated body (BACKLOG #6b).

The kernel half of the stateless overlay endpoint: given a recomputed body it
enumerates the EXACT vertices and edges the measurement UI picks against. The
edge enumeration is ``body.edges()`` — the SAME deterministic OCCT exploration
order :mod:`geometry.kernel.measure` resolves an edge ``index`` against — so
``edges[i]`` here is exactly the edge ``EdgeTarget(index=i)`` measures. Vertices
come from ``body.vertices()`` in its own deterministic order and carry EXACT
world-mm coordinates (a picked vertex is measured as a ``PointTarget``, so it
must be exact, never a mesh snap).

Curved edges are sampled to a polyline with OCCT's ``GCPnts_QuasiUniformDeflection``
at the caller's ``linear_deflection`` — the SAME tolerance the mesh tessellation
uses (:mod:`geometry.kernel.tessellate`), so the overlay never introduces a new
epsilon. A straight edge is exactly ``[start, end]``.

Determinism (RESEARCH §9): ``.vertices()`` / ``.edges()`` explore a fixed shape
in a deterministic order and the deflection sampler is a pure function of the
curve + deflection, so the same body yields an identical overlay.

The OCP wheel ships no type stubs, so the raw OCCT calls below are opaque to
pyright; the directives scope that relaxation to this file only, and the
fully-typed :class:`OverlayResult` DTO keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from build123d import Edge, GeomType, Solid, Vector, Vertex
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.overlay import OverlayEdge, OverlayEdgeKind, OverlayResult

#: OCCT ``GeomType`` → overlay edge kind (a rendering hint only). Anything not a
#: straight line or a circle is ``other`` (ellipse, spline, …) — still sampled
#: to a polyline, still exactly measurable via the B-rep.
_EDGE_KIND: dict[GeomType, OverlayEdgeKind] = {
    GeomType.LINE: "line",
    GeomType.CIRCLE: "circle",
}


def _vertex_point(vertex: Vertex) -> Vec3:
    """Exact world-mm coordinates of a B-rep vertex (no mesh snap)."""
    x, y, z = tuple(vertex)
    return Vec3(x=float(x), y=float(y), z=float(z))


def _vec(vector: Vector) -> Vec3:
    """A build123d ``Vector`` (world mm) as a boundary ``Vec3``."""
    return Vec3(x=float(vector.X), y=float(vector.Y), z=float(vector.Z))


def _edge_polyline(edge: Edge, linear_deflection: float) -> list[Vec3]:
    """Sample *edge* to a polyline at *linear_deflection* (world mm).

    Uses the same deflection the mesh tessellation uses (no new epsilon). A
    straight line comes back as its two endpoints; a curve is sampled so its
    chord deviation never exceeds ``linear_deflection``.
    """
    adaptor = BRepAdaptor_Curve(edge.wrapped)
    sampler = GCPnts_QuasiUniformDeflection(adaptor, linear_deflection)
    if not sampler.IsDone() or sampler.NbPoints() < 2:
        # Degenerate/failed discretisation: fall back to the endpoints so the
        # client always has a drawable 2-point polyline (belt-and-braces —
        # the service maps any raw raise to a 422 regardless).
        return [_vec(edge @ 0.0), _vec(edge @ 1.0)]
    points: list[Vec3] = []
    for index in range(1, sampler.NbPoints() + 1):
        point = sampler.Value(index)
        points.append(Vec3(x=float(point.X()), y=float(point.Y()), z=float(point.Z())))
    return points


def selection_overlay(body: Solid, linear_deflection: float) -> OverlayResult:
    """Pickable vertices + edges of *body* (transient indices, world mm).

    ``edges`` is in ``body.edges()`` order — byte-for-byte the enumeration
    :func:`geometry.kernel.measure.measure_targets` resolves ``EdgeTarget.index``
    against — so ``edges[i]`` is the edge ``EdgeTarget(index=i)`` measures.
    ``vertices`` is in ``body.vertices()`` order with EXACT coordinates.
    Deterministic (RESEARCH §9).
    """
    vertices = [_vertex_point(vertex) for vertex in body.vertices()]

    edges: list[OverlayEdge] = []
    for edge in body.edges():
        polyline = _edge_polyline(edge, linear_deflection)
        # start/end are the polyline ends so the three are always
        # self-consistent (start == polyline[0], end == polyline[-1]); the
        # geometric curve parametrisation and the topological edge orientation
        # can disagree, so deriving them here avoids a mismatched pair.
        edges.append(
            OverlayEdge(
                kind=_EDGE_KIND.get(edge.geom_type, "other"),
                start=polyline[0],
                end=polyline[-1],
                polyline=polyline,
            )
        )

    return OverlayResult(vertices=vertices, edges=edges)
