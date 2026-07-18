"""Exact nearest-distance measurement between two targets (OCCT BRepExtrema).

The kernel half of the stateless measure endpoint (BACKLOG #6a). Distances come
from the exact B-rep via OCCT's ``BRepExtrema_DistShapeShape`` — the same
optimal-geometry posture as :mod:`geometry.kernel.properties`: mesh quality
never perturbs a measurement (curved edges included). A POINT target becomes a
``TopoDS_Vertex``; an EDGE target is the ``TopoDS_Edge`` at a transient index
into the recomputed body's deterministic edge list (build123d ``.edges()`` /
OCCT exploration order). The witness points the solver returns give the exact
delta components, and — for two straight-line edges — the acute angle between
their directions.

Determinism (RESEARCH §9): ``.edges()`` explores a fixed shape in a
deterministic order, and ``BRepExtrema_DistShapeShape`` is a pure function of
its two shapes, so the same request yields an identical result.

The OCP wheel ships no type stubs, so the raw OCCT calls below are opaque to
pyright; the directives scope that relaxation to this file only, and the
fully-typed :class:`MeasureResult` DTO keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from typing import Literal

from build123d import GeomType, Vector
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt
from OCP.TopoDS import TopoDS_Shape
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.measure import (
    EdgeTarget,
    MeasureResult,
    MeasureTarget,
    PointTarget,
)

from geometry.kernel.types import BodyShape


class MeasureError(ValueError):
    """A measurement could not be evaluated (surfaces as a 422, never a 500)."""


class EdgeIndexError(MeasureError):
    """An edge target's index is out of range for the recomputed body."""


def _resolve_target(
    target: MeasureTarget, body: BodyShape | None
) -> tuple[TopoDS_Shape, Vector | None]:
    """Resolve a target to its ``(TopoDS shape, line direction | None)``.

    The direction is the unit tangent of a STRAIGHT-line edge (used for the
    edge-edge angle) and ``None`` for a point or a curved edge — neither has a
    single direction.
    """
    if isinstance(target, PointTarget):
        position = target.position
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(position.x, position.y, position.z)
        ).Vertex()
        return vertex, None

    if body is None:
        # Guarded by MeasureRequest validation (an edge target requires a
        # tree) — belt-and-braces so the kernel never trusts its caller.
        raise MeasureError("edge target requires a recomputed body")

    edges = body.edges()
    if target.index >= len(edges):
        raise EdgeIndexError(
            f"edge index {target.index} out of range: the recomputed body has "
            f"{len(edges)} edges (valid indices 0..{len(edges) - 1})"
        )
    edge = edges[target.index]
    direction = edge.tangent_at(0.0) if edge.geom_type == GeomType.LINE else None
    return edge.wrapped, direction


def _line_angle_deg(a: Vector, b: Vector) -> float:
    """Acute angle (degrees, [0, 90]) between two line directions."""
    norm_a = math.sqrt(a.X * a.X + a.Y * a.Y + a.Z * a.Z)
    norm_b = math.sqrt(b.X * b.X + b.Y * b.Y + b.Z * b.Z)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0  # unreachable for a valid line edge; keeps the math total
    dot = a.X * b.X + a.Y * b.Y + a.Z * b.Z
    cosine = min(1.0, max(-1.0, abs(dot) / (norm_a * norm_b)))
    return math.degrees(math.acos(cosine))


def _measure_kind(
    a: MeasureTarget, b: MeasureTarget
) -> Literal["point_point", "point_edge", "edge_edge"]:
    """Classify the measured pair for the result tag."""
    a_edge = isinstance(a, EdgeTarget)
    b_edge = isinstance(b, EdgeTarget)
    if a_edge and b_edge:
        return "edge_edge"
    if a_edge or b_edge:
        return "point_edge"
    return "point_point"


def measure_targets(
    target_a: MeasureTarget, target_b: MeasureTarget, body: BodyShape | None
) -> MeasureResult:
    """Exact nearest distance (+ delta, witnesses, line-line angle) A→B.

    ``body`` is the recomputed solid an edge target resolves against; it may be
    ``None`` when both targets are points. Raises :class:`EdgeIndexError` for an
    out-of-range edge index and :class:`MeasureError` if the solver fails —
    both map to a clean 422 at the service boundary, never a 500.
    """
    shape_a, direction_a = _resolve_target(target_a, body)
    shape_b, direction_b = _resolve_target(target_b, body)

    solver = BRepExtrema_DistShapeShape(shape_a, shape_b)
    if not solver.IsDone():
        raise MeasureError("nearest-distance computation did not converge")

    on_a = solver.PointOnShape1(1)
    on_b = solver.PointOnShape2(1)
    point_on_a = Vec3(x=float(on_a.X()), y=float(on_a.Y()), z=float(on_a.Z()))
    point_on_b = Vec3(x=float(on_b.X()), y=float(on_b.Y()), z=float(on_b.Z()))
    delta = Vec3(
        x=point_on_b.x - point_on_a.x,
        y=point_on_b.y - point_on_a.y,
        z=point_on_b.z - point_on_a.z,
    )

    angle: float | None = None
    if direction_a is not None and direction_b is not None:
        angle = _line_angle_deg(direction_a, direction_b)

    return MeasureResult(
        kind=_measure_kind(target_a, target_b),
        distance=float(solver.Value()),
        delta=delta,
        point_on_a=point_on_a,
        point_on_b=point_on_b,
        angle_deg=angle,
    )
