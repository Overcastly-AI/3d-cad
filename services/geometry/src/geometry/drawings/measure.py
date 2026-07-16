"""Dimension measurement — resolve a dimension's model refs and MEASURE the true
value FROM THE MODEL (design §3.1/§3.2/§3.3).

A drawing dimension names MODEL geometry with the shipped
:class:`~py_kit.schemas.features.EdgeSignature` (the SAME fingerprint a
``concentric`` mate and a picked-edge fillet use — design §3.3). This module
resolves that ref against the view's evaluated body with the shipped
:func:`geometry.kernel.edges.resolve_edge` (exactly one or an honest error) and
measures the value off the EXACT 3D B-rep — never the foreshortened 2D
projection (design §3.1). ``linear``/``diameter``/``radius`` are millimetres,
``angular`` is degrees.

Foreshortening (design §3.2): the measured value is ALWAYS the model-true value,
but a feature not parallel to the view plane would *draw* shorter than reality — a
real footgun. The result carries a ``foreshortened`` flag (measured against the
SAME view normal :func:`geometry.drawings.project.view_normal` the projection
uses) so the UI can warn "dimension this in a true-size view". The flag is the
warning; the number stays honest.

Honest, typed failure (design §3.3/§5): a ref that no longer resolves is a
:class:`~geometry.kernel.faces.SubshapeUnresolvedError`, a congruent twin a
:class:`~geometry.kernel.faces.SubshapeAmbiguousError` — the SAME taxonomy a mate
and a fillet reuse (never a parallel one). A wrong-type ref (a diameter on a
non-circular edge, an angular on a non-straight edge) is a
:class:`DimensionTypeError`. :func:`measure_dimension_dto` maps all three onto the
neutral :class:`~py_kit.schemas.drawings.MeasuredDimension` error channel — never
a 500.

Determinism (RESEARCH §9): resolution + measurement are pure functions of the body
and the ref; the same body + dimension yields the same value, in-process and
across a restart.
"""
# The OCP wheel ships no type stubs; the raw circle-axis accessor below is opaque
# to pyright. Scope the relaxation to this file (the geometry.drawings.project
# posture); the fully-typed Solid input + MeasuredDimension output keep the
# boundary honest.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Edge, GeomType, Solid
from OCP.BRepAdaptor import BRepAdaptor_Curve
from py_kit.schemas.drawings import (
    AngularDimensionParams,
    DiameterDimensionParams,
    DimensionEndpointRef,
    DimensionParams,
    DimensionUnit,
    EdgeLengthMeasurement,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    RadiusDimensionParams,
    ViewProjection,
)
from py_kit.schemas.features import EdgeSignature, FeatureError
from py_kit.schemas.geometry import Vec3

from geometry.drawings.project import ViewDirection, view_normal
from geometry.kernel.edges import edge_signature_dto, resolve_edge
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError

#: How parallel to the view plane a feature must be to read TRUE-size (design
#: §3.2). A LINEAR feature is true-size when its direction is perpendicular to the
#: view normal N (``|d . N| <= tol``); a CIRCULAR feature is true-size when its
#: axis is parallel to N. A dimensionless (sin-scale) angular bound — the
#: ``project._AXIS_PARALLEL_TOL`` / ``edges._EDGE_DIRECTION_TOLERANCE`` twin. Sized
#: so an exactly-in-plane feature never flags and a meaningfully-tilted one always
#: does; documented (NOT ad-hoc — CLAUDE.md; see docs/GEOMETRY-QA.md).
_FORESHORTEN_SIN_TOL = 1e-7

#: Endpoint-coincidence tolerance (mm) for detecting the shared vertex of an
#: angular dimension's two edges — the kernel edge endpoint tolerance twin.
_VERTEX_TOL_MM = 1e-6


class DimensionTypeError(ValueError):
    """A dimension's ref resolved, but to the WRONG kind of edge (design §3.1).

    A ``diameter``/``radius`` whose edge is not circular, or an ``angular`` whose
    edge is not a straight line. The honest "you named the wrong geometry"
    outcome, distinct from an unresolved/ambiguous ref; the boundary maps it onto
    the ``dimension_wrong_type`` code (never a 500)."""


@dataclass(frozen=True)
class DimensionValue:
    """A measured dimension value (design §3) — model-true, with the §3.2 flag.

    ``value`` is millimetres for ``linear``/``diameter``/``radius`` and degrees for
    ``angular`` (``unit`` disambiguates). ``foreshortened`` is set when the measured
    feature is not parallel to the view plane — the value is STILL model-true."""

    value: float
    unit: DimensionUnit  # "mm" | "deg"
    foreshortened: bool


def _sub(a: Vec3, b: Vec3) -> tuple[float, float, float]:
    return (a.x - b.x, a.y - b.y, a.z - b.z)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _norm(a)
    return (a[0] / length, a[1] / length, a[2] / length)


def _dist(a: Vec3, b: Vec3) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def _line_direction(sig: EdgeSignature) -> tuple[float, float, float]:
    """A straight edge's unit direction from its canonical endpoints."""
    return _unit(_sub(sig.end_b, sig.end_a))


def _linear_foreshortened(
    direction: tuple[float, float, float], normal: tuple[float, float, float]
) -> bool:
    """A linear feature is foreshortened unless it lies in the view plane —
    i.e. its direction is perpendicular to the view normal (design §3.2)."""
    return abs(_dot(_unit(direction), normal)) > _FORESHORTEN_SIN_TOL


def _circle_axis(edge: Edge) -> tuple[float, float, float]:
    """The unit axis of a circular edge's plane (from the exact B-rep circle)."""
    axis = BRepAdaptor_Curve(edge.wrapped).Circle().Axis().Direction()
    return (axis.X(), axis.Y(), axis.Z())


def _circle_foreshortened(edge: Edge, normal: tuple[float, float, float]) -> bool:
    """A circular feature reads true-size only face-on — its axis parallel to the
    view normal; otherwise it foreshortens to an ellipse (design §3.2)."""
    return abs(_dot(_circle_axis(edge), normal)) < 1.0 - _FORESHORTEN_SIN_TOL


def _require_circle(edge: Edge, kind: str) -> None:
    if edge.geom_type != GeomType.CIRCLE:
        raise DimensionTypeError(
            f"A {kind} dimension needs a circular edge, but the referenced edge is "
            f"{edge.geom_type}. Re-pick a circular/arc edge (design §3.1)."
        )


def _require_line(edge: Edge, which: str) -> None:
    if edge.geom_type != GeomType.LINE:
        raise DimensionTypeError(
            f"An angular dimension needs two straight edges, but {which} is "
            f"{edge.geom_type}. Re-pick a straight edge (design §3.1)."
        )


def _endpoint(ref: DimensionEndpointRef, body: Solid) -> Vec3:
    """Resolve a point-to-point endpoint ref to a world point (design §3.3).

    Names a vertex THROUGH an edge (no unshipped bare-vertex signature): resolve
    the edge, then select its canonical ``end_a``/``end_b`` — recomputed via the
    shipped :func:`edge_signature_dto` so the endpoint is the SAME canonical point
    the signature was authored against."""
    edge = resolve_edge(body, ref.signature)
    sig = edge_signature_dto(edge)
    return sig.end_a if ref.endpoint == "end_a" else sig.end_b


def _measure_linear(
    params: LinearDimensionParams, body: Solid, normal: tuple[float, float, float]
) -> DimensionValue:
    source = params.measurement
    if isinstance(source, EdgeLengthMeasurement):
        edge = resolve_edge(body, source.edge)
        direction = _line_direction(edge_signature_dto(edge))
        # Length is the EXACT B-rep arc length (an arc's length, a line's length) —
        # always model-true. Foreshortening only applies to a STRAIGHT edge (a
        # single direction); a curved edge's length is direction-free, never flagged.
        foreshortened = edge.geom_type == GeomType.LINE and _linear_foreshortened(
            direction, normal
        )
        return DimensionValue(
            value=float(edge.length), unit="mm", foreshortened=foreshortened
        )
    assert isinstance(source, PointToPointMeasurement)
    a = _endpoint(source.a, body)
    b = _endpoint(source.b, body)
    distance = _dist(a, b)
    direction = _sub(b, a)
    foreshortened = distance > 0.0 and _linear_foreshortened(direction, normal)
    return DimensionValue(value=distance, unit="mm", foreshortened=foreshortened)


def _measure_diameter(
    params: DiameterDimensionParams, body: Solid, normal: tuple[float, float, float]
) -> DimensionValue:
    edge = resolve_edge(body, params.edge)
    _require_circle(edge, "diameter")
    return DimensionValue(
        value=2.0 * float(edge.radius),
        unit="mm",
        foreshortened=_circle_foreshortened(edge, normal),
    )


def _measure_radius(
    params: RadiusDimensionParams, body: Solid, normal: tuple[float, float, float]
) -> DimensionValue:
    edge = resolve_edge(body, params.edge)
    _require_circle(edge, "radius")
    return DimensionValue(
        value=float(edge.radius),
        unit="mm",
        foreshortened=_circle_foreshortened(edge, normal),
    )


def _measure_angular(
    params: AngularDimensionParams, body: Solid, normal: tuple[float, float, float]
) -> DimensionValue:
    edge_a = resolve_edge(body, params.edge_a)
    edge_b = resolve_edge(body, params.edge_b)
    _require_line(edge_a, "the first edge")
    _require_line(edge_b, "the second edge")
    sig_a = edge_signature_dto(edge_a)
    sig_b = edge_signature_dto(edge_b)

    # If the two edges share a vertex, orient each AWAY from it so the measured
    # angle is the unambiguous vee angle (0,180). Otherwise fall back to the
    # undirected angle between the two lines in [0,90] (design §3.1).
    shared, da, db = _oriented_directions(sig_a, sig_b)
    cos_theta = _dot(da, db)
    if not shared:
        cos_theta = abs(cos_theta)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    degrees = math.degrees(math.acos(cos_theta))

    # Angular reads true only when BOTH edges lie in the view plane (design §3.2).
    foreshortened = _linear_foreshortened(da, normal) or _linear_foreshortened(
        db, normal
    )
    return DimensionValue(value=degrees, unit="deg", foreshortened=foreshortened)


def _oriented_directions(
    sig_a: EdgeSignature, sig_b: EdgeSignature
) -> tuple[bool, tuple[float, float, float], tuple[float, float, float]]:
    """Directions for the two angular edges, oriented away from a shared vertex.

    Returns ``(shared, dir_a, dir_b)``. When the edges share an endpoint (within
    ``_VERTEX_TOL_MM``) both directions point away from it → the true vee angle;
    otherwise ``shared`` is ``False`` and directions are the canonical
    ``end_a→end_b`` (the caller takes the undirected acute angle)."""
    ends_a = (sig_a.end_a, sig_a.end_b)
    ends_b = (sig_b.end_a, sig_b.end_b)
    for i, va in enumerate(ends_a):
        for j, vb in enumerate(ends_b):
            if _dist(va, vb) <= _VERTEX_TOL_MM:
                other_a = ends_a[1 - i]
                other_b = ends_b[1 - j]
                return True, _unit(_sub(other_a, va)), _unit(_sub(other_b, vb))
    return False, _line_direction(sig_a), _line_direction(sig_b)


def measure_dimension(
    body: Solid, dimension: DimensionParams, view: ViewProjection
) -> DimensionValue:
    """Measure *dimension* against *body* in *view* — model-true (design §3.1).

    Resolves the dimension's model-edge signature(s) against *body* and measures
    the value off the EXACT 3D B-rep (never the projected 2D). *view* supplies the
    projection normal for the §3.2 foreshortening flag ONLY — it never changes the
    value. Raises:

        SubshapeUnresolvedError: a ref no longer matches any edge (design §3.3).
        SubshapeAmbiguousError: a ref matches a congruent twin (refuse to guess).
        DimensionTypeError: a ref resolved to the wrong edge kind (design §3.1).
    """
    normal = view_normal(_as_direction(view))
    if isinstance(dimension, LinearDimensionParams):
        return _measure_linear(dimension, body, normal)
    if isinstance(dimension, DiameterDimensionParams):
        return _measure_diameter(dimension, body, normal)
    if isinstance(dimension, RadiusDimensionParams):
        return _measure_radius(dimension, body, normal)
    assert isinstance(dimension, AngularDimensionParams)
    return _measure_angular(dimension, body, normal)


def _as_direction(view: ViewProjection) -> ViewDirection:
    """The boundary ``ViewProjection`` literal is value-identical to the kernel
    ``ViewDirection`` (front/top/right/iso); this narrows the type without a map."""
    return view


def measure_dimension_dto(
    body: Solid, dimension: DimensionParams, view: ViewProjection
) -> MeasuredDimension:
    """:func:`measure_dimension` with the typed errors folded onto the neutral
    :class:`MeasuredDimension` error channel (design §3.3/§5) — never a raise for a
    resolution outcome, so a bad ref is an honest per-dimension error, not a 500."""
    try:
        measured = measure_dimension(body, dimension, view)
    except SubshapeUnresolvedError as exc:
        return MeasuredDimension(
            error=FeatureError(code="subshape_unresolved", message=str(exc))
        )
    except SubshapeAmbiguousError as exc:
        return MeasuredDimension(
            error=FeatureError(code="subshape_ambiguous", message=str(exc))
        )
    except DimensionTypeError as exc:
        return MeasuredDimension(
            error=FeatureError(code="dimension_wrong_type", message=str(exc))
        )
    return MeasuredDimension(
        value=measured.value, unit=measured.unit, foreshortened=measured.foreshortened
    )
