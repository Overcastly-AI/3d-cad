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

Surviving the edit it measures (audit N1, topological-naming §11): the ref resolves
through :func:`geometry.drawings.anchor.resolve_anchor_edge` — the shipped strict
resolver first, then, ONLY when that finds nothing, a re-match on the rebuild
invariant of the edge's curve kind (a straight edge's supporting line + overlapping
span, a circular edge's centre + angular station). So widening a plate 100 → 120
re-measures its overall-length dimension instead of destroying it. The result carries
the :class:`~py_kit.schemas.drawings.DimensionAnchor` — the CURRENT signature(s) the
dimension now names plus which tier matched — which is also what the composer matches
against the projected edges (a re-measured dimension whose ANNOTATION still looked up
the stale signature would still vanish from the sheet).

Honest, typed failure (design §3.3/§5): a ref that no longer resolves is a
:class:`~geometry.kernel.faces.SubshapeUnresolvedError`, a congruent twin a
:class:`~geometry.kernel.faces.SubshapeAmbiguousError` — the SAME taxonomy a mate
and a fillet reuse (never a parallel one). A wrong-type ref (a diameter on a
non-circular edge, an angular on a non-straight edge) is a
:class:`DimensionTypeError`. An ``edge_to_edge`` linear whose two edges are not
parallel — so no perpendicular distance EXISTS — is a
:class:`DimensionNotParallelError` (FB-10): a wrong number on a print a shop will
cut from is worse than no number, so this one refuses rather than measures.
:func:`measure_dimension_dto` maps all four onto the neutral
:class:`~py_kit.schemas.drawings.MeasuredDimension` error channel — never a 500.

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
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Edge, GeomType
from py_kit.schemas.drawings import (
    AngularDimensionParams,
    DiameterDimensionParams,
    DimensionAnchor,
    DimensionEndpointRef,
    DimensionParams,
    DimensionUnit,
    EdgeLengthMeasurement,
    EdgeToEdgeMeasurement,
    LinearDimensionParams,
    MeasuredDimension,
    PointToPointMeasurement,
    RadiusDimensionParams,
    ViewProjection,
)
from py_kit.schemas.features import EdgeSignature, FeatureError
from py_kit.schemas.geometry import Vec3

from geometry.drawings.anchor import (
    ANCHOR_DIRECTION_SIN_TOL,
    ResolvedAnchor,
    resolve_anchor_edge,
)
from geometry.drawings.project import ViewDirection, view_normal
from geometry.kernel.edges import circle_axis
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.kernel.types import BodyShape

#: How parallel to the view plane a feature must be to read TRUE-size (design
#: §3.2). A LINEAR feature is true-size when its direction is perpendicular to the
#: view normal N (``|d . N| <= tol``); a CIRCULAR feature is true-size when its
#: axis is parallel to N. A dimensionless (sin-scale) angular bound — THE SAME one the
#: durable anchor's parallelism test uses (:data:`geometry.drawings.anchor.
#: ANCHOR_DIRECTION_SIN_TOL`, itself the ``project._AXIS_PARALLEL_TOL`` /
#: ``edges._EDGE_DIRECTION_TOLERANCE`` twin), declared once and aliased here rather
#: than re-stated. Sized so an exactly-in-plane feature never flags and a
#: meaningfully-tilted one always does; documented (NOT ad-hoc — CLAUDE.md; see
#: docs/GEOMETRY-QA.md).
_FORESHORTEN_SIN_TOL = ANCHOR_DIRECTION_SIN_TOL

#: Endpoint-coincidence tolerance (mm) for detecting the shared vertex of an
#: angular dimension's two edges — the kernel edge endpoint tolerance twin.
_VERTEX_TOL_MM = 1e-6

#: How parallel two straight edges must be for an ``edge_to_edge`` perpendicular
#: distance to EXIST (FB-10): the sine of the angle between their directions —
#: ``|d_a x d_b|`` — must not exceed this. The SAME dimensionless sin-scale bound the
#: foreshortening flag and the durable anchor's parallelism test already use
#: (:data:`geometry.drawings.anchor.ANCHOR_DIRECTION_SIN_TOL`), aliased rather than
#: re-stated so "parallel" means one thing across this service. Documented, not
#: ad-hoc (CLAUDE.md; docs/GEOMETRY-QA.md).
_PARALLEL_SIN_TOL = ANCHOR_DIRECTION_SIN_TOL


class DimensionTypeError(ValueError):
    """A dimension's ref resolved, but to the WRONG kind of edge (design §3.1).

    A ``diameter``/``radius`` whose edge is not circular, or an ``angular`` whose
    edge is not a straight line. The honest "you named the wrong geometry"
    outcome, distinct from an unresolved/ambiguous ref; the boundary maps it onto
    the ``dimension_wrong_type`` code (never a 500)."""


class DimensionNotParallelError(ValueError):
    """An ``edge_to_edge`` dimension's two edges are not parallel (FB-10).

    Both refs resolved, and both are straight — but they converge or are skew, so
    there is no single perpendicular distance BETWEEN them: the separation depends
    on where along the pair you measure. The shortest distance between two skew
    lines is still a number, and stamping it would put a plausible, unusable value
    on a print that goes to a shop — the worst outcome this dimension has. So we
    refuse, in the same typed style as :class:`DimensionTypeError`; the boundary
    maps it onto the ``dimension_not_parallel`` code (never a 500, and never a
    number)."""


@dataclass(frozen=True)
class DimensionValue:
    """A measured dimension value (design §3) — model-true, with the §3.2 flag.

    ``value`` is millimetres for ``linear``/``diameter``/``radius`` and degrees for
    ``angular`` (``unit`` disambiguates). ``foreshortened`` is set when the measured
    feature is not parallel to the view plane — the value is STILL model-true.
    ``anchor`` says WHERE on the current body the reference(s) landed and whether the
    match was exact or a durable re-anchor (audit N1)."""

    value: float
    unit: DimensionUnit  # "mm" | "deg"
    foreshortened: bool
    anchor: DimensionAnchor


def _anchor_dto(
    primary: ResolvedAnchor, secondary: ResolvedAnchor | None = None
) -> DimensionAnchor:
    """The boundary :class:`DimensionAnchor` for one or two resolved refs (§11).

    The reported ``tier`` is the WEAKER of the two (``durable`` if either reference
    had to be re-anchored), so a consumer never reads "exact" for a dimension that
    half-moved."""
    durable = primary.tier == "durable" or (
        secondary is not None and secondary.tier == "durable"
    )
    return DimensionAnchor(
        tier="durable" if durable else "exact",
        primary=primary.signature,
        secondary=secondary.signature if secondary is not None else None,
    )


def _sub(a: Vec3, b: Vec3) -> tuple[float, float, float]:
    return (a.x - b.x, a.y - b.y, a.z - b.z)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _norm(a)
    if length == 0.0:
        # A degenerate (zero-length) edge has no direction. Return the zero
        # vector rather than divide by zero — callers read it as
        # not-foreshortened / 0°, never an uncaught ZeroDivisionError → 500.
        return (0.0, 0.0, 0.0)
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


def _circle_foreshortened(edge: Edge, normal: tuple[float, float, float]) -> bool:
    """A circular feature reads true-size only face-on — its axis parallel to the
    view normal; otherwise it foreshortens to an ellipse (design §3.2)."""
    return abs(_dot(circle_axis(edge), normal)) < 1.0 - _FORESHORTEN_SIN_TOL


def _require_circle(edge: Edge, kind: str) -> None:
    if edge.geom_type != GeomType.CIRCLE:
        raise DimensionTypeError(
            f"A {kind} dimension needs a circular edge, but the referenced edge is "
            f"{edge.geom_type}. Re-pick a circular/arc edge (design §3.1)."
        )


def _require_line(edge: Edge, which: str, kind: str = "An angular") -> None:
    if edge.geom_type != GeomType.LINE:
        raise DimensionTypeError(
            f"{kind} dimension needs two straight edges, but {which} is "
            f"{edge.geom_type}. Re-pick a straight edge (design §3.1)."
        )


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _endpoint(
    ref: DimensionEndpointRef, body: BodyShape
) -> tuple[Vec3, ResolvedAnchor]:
    """Resolve a point-to-point endpoint ref to a world point (design §3.3).

    Names a vertex THROUGH an edge (no unshipped bare-vertex signature): resolve
    the edge (two-tier, §11), then select its canonical ``end_a``/``end_b`` from the
    CURRENT signature, so the endpoint is the same canonical end of the same edge the
    signature was authored against even when that edge has since moved/grown."""
    anchor = resolve_anchor_edge(body, ref.signature)
    sig = anchor.signature
    return (sig.end_a if ref.endpoint == "end_a" else sig.end_b), anchor


def _measure_linear(
    params: LinearDimensionParams, body: BodyShape, normal: tuple[float, float, float]
) -> DimensionValue:
    source = params.measurement
    if isinstance(source, EdgeLengthMeasurement):
        resolved = resolve_anchor_edge(body, source.edge)
        edge = resolved.edge
        # Length is the EXACT B-rep arc length (an arc's length, a line's length) —
        # always model-true. Foreshortening only applies to a STRAIGHT edge (a
        # single direction); a curved edge's length is direction-free, never
        # flagged — so the direction is only needed inside the LINE guard (and a
        # degenerate edge never reaches `_line_direction`'s unit-vector divide).
        foreshortened = edge.geom_type == GeomType.LINE and _linear_foreshortened(
            _line_direction(resolved.signature), normal
        )
        return DimensionValue(
            value=float(edge.length),
            unit="mm",
            foreshortened=foreshortened,
            anchor=_anchor_dto(resolved),
        )
    if isinstance(source, EdgeToEdgeMeasurement):
        return _measure_edge_to_edge(source, body, normal)
    assert isinstance(source, PointToPointMeasurement)
    a, anchor_a = _endpoint(source.a, body)
    b, anchor_b = _endpoint(source.b, body)
    distance = _dist(a, b)
    direction = _sub(b, a)
    foreshortened = distance > 0.0 and _linear_foreshortened(direction, normal)
    return DimensionValue(
        value=distance,
        unit="mm",
        foreshortened=foreshortened,
        anchor=_anchor_dto(anchor_a, anchor_b),
    )


def _measure_edge_to_edge(
    source: EdgeToEdgeMeasurement,
    body: BodyShape,
    normal: tuple[float, float, float],
) -> DimensionValue:
    """The PERPENDICULAR distance between two parallel straight edges (FB-10).

    The wall-thickness measurement. Both refs resolve through the two-tier anchor
    like every other dimension, then:

    1. both edges must be STRAIGHT (a curve has no single direction) — otherwise
       :class:`DimensionTypeError`, the shipped ``dimension_wrong_type``;
    2. they must be PARALLEL — ``|d_a x d_b| <= _PARALLEL_SIN_TOL`` — otherwise
       :class:`DimensionNotParallelError`. A degenerate (zero-length) edge has no
       direction at all, so it refuses on the same channel rather than reading as
       trivially parallel and returning a meaningless number;
    3. the value is the length of the component of ``(p_b - p_a)`` PERPENDICULAR to
       the shared direction — i.e. the distance between the two supporting lines,
       independent of where along either edge it is taken. That independence is the
       whole point: it is what ``point_to_point`` cannot give, because two endpoints
       carry the along-wall offset as well.

    Foreshortening (design §3.2) is judged on the SEPARATION direction, exactly as
    ``point_to_point`` judges it on ``b - a``: the thickness reads true-size when the
    across-the-wall direction lies in the view plane.
    """
    resolved_a = resolve_anchor_edge(body, source.edge_a)
    resolved_b = resolve_anchor_edge(body, source.edge_b)
    _require_line(resolved_a.edge, "the first edge", "An edge-to-edge")
    _require_line(resolved_b.edge, "the second edge", "An edge-to-edge")
    sig_a = resolved_a.signature
    sig_b = resolved_b.signature

    da = _line_direction(sig_a)
    db = _line_direction(sig_b)
    if _norm(da) == 0.0 or _norm(db) == 0.0:
        raise DimensionNotParallelError(
            "An edge-to-edge dimension measures ACROSS two parallel edges, but one "
            "of the referenced edges is degenerate (zero length) and has no "
            "direction, so there is no perpendicular distance. Re-pick the edges."
        )
    sin_angle = _norm(_cross(da, db))
    if sin_angle > _PARALLEL_SIN_TOL:
        degrees = math.degrees(math.asin(min(1.0, sin_angle)))
        raise DimensionNotParallelError(
            "An edge-to-edge dimension measures the PERPENDICULAR distance between "
            f"two parallel edges, but these two meet at {degrees:.3f}deg. Their "
            "separation depends on where it is measured, so there is no single "
            "thickness to stamp. Re-pick two parallel edges, or use an angular "
            "dimension (design §3.1)."
        )

    # The perpendicular component of the offset between the two supporting lines.
    offset = _sub(sig_b.end_a, sig_a.end_a)
    along = _dot(offset, da)
    perpendicular = (
        offset[0] - along * da[0],
        offset[1] - along * da[1],
        offset[2] - along * da[2],
    )
    distance = _norm(perpendicular)
    foreshortened = distance > 0.0 and _linear_foreshortened(perpendicular, normal)
    return DimensionValue(
        value=distance,
        unit="mm",
        foreshortened=foreshortened,
        anchor=_anchor_dto(resolved_a, resolved_b),
    )


def _measure_diameter(
    params: DiameterDimensionParams,
    body: BodyShape,
    normal: tuple[float, float, float],
    drawn: Sequence[EdgeSignature],
) -> DimensionValue:
    resolved = resolve_anchor_edge(body, params.edge, drawn)
    edge = resolved.edge
    _require_circle(edge, "diameter")
    return DimensionValue(
        value=2.0 * float(edge.radius),
        unit="mm",
        foreshortened=_circle_foreshortened(edge, normal),
        anchor=_anchor_dto(resolved),
    )


def _measure_radius(
    params: RadiusDimensionParams,
    body: BodyShape,
    normal: tuple[float, float, float],
    drawn: Sequence[EdgeSignature],
) -> DimensionValue:
    resolved = resolve_anchor_edge(body, params.edge, drawn)
    edge = resolved.edge
    _require_circle(edge, "radius")
    return DimensionValue(
        value=float(edge.radius),
        unit="mm",
        foreshortened=_circle_foreshortened(edge, normal),
        anchor=_anchor_dto(resolved),
    )


def _measure_angular(
    params: AngularDimensionParams, body: BodyShape, normal: tuple[float, float, float]
) -> DimensionValue:
    resolved_a = resolve_anchor_edge(body, params.edge_a)
    resolved_b = resolve_anchor_edge(body, params.edge_b)
    edge_a = resolved_a.edge
    edge_b = resolved_b.edge
    _require_line(edge_a, "the first edge")
    _require_line(edge_b, "the second edge")
    sig_a = resolved_a.signature
    sig_b = resolved_b.signature

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
    return DimensionValue(
        value=degrees,
        unit="deg",
        foreshortened=foreshortened,
        anchor=_anchor_dto(resolved_a, resolved_b),
    )


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
    body: BodyShape,
    dimension: DimensionParams,
    view: ViewProjection,
    drawn: Sequence[EdgeSignature] = (),
) -> DimensionValue:
    """Measure *dimension* against *body* in *view* — model-true (design §3.1).

    Resolves the dimension's model-edge signature(s) against *body* and measures
    the value off the EXACT 3D B-rep (never the projected 2D). *view* supplies the
    projection normal for the §3.2 foreshortening flag ONLY — it never changes the
    value.

    *drawn* is the set of model-edge signatures THIS VIEW projects (the ``source_edge``
    of its projected edges). It is used by one thing only: the tier-3 re-anchor for a
    circle whose face TRANSLATED (a thickness edit moves a bore's rim along its own
    axis, QA-3), where the invariant alone cannot separate the two congruent rims of a
    through hole and the set the user could have PICKED from breaks the tie honestly
    (:func:`geometry.drawings.anchor.resolve_anchor_edge`). Omitting it (a unit test,
    an older caller) keeps the pre-QA-3 behaviour exactly. It never affects a measured
    VALUE — the value is always taken off the 3-D edge that resolved.

    Raises:

        SubshapeUnresolvedError: a ref no longer matches any edge (design §3.3).
        SubshapeAmbiguousError: a ref matches a congruent twin (refuse to guess).
        DimensionTypeError: a ref resolved to the wrong edge kind (design §3.1).
        DimensionNotParallelError: an ``edge_to_edge`` pair is not parallel, so no
            perpendicular distance exists (FB-10) — refuse rather than stamp a
            plausible, unusable number.
    """
    normal = view_normal(_as_direction(view))
    if isinstance(dimension, LinearDimensionParams):
        return _measure_linear(dimension, body, normal)
    if isinstance(dimension, DiameterDimensionParams):
        return _measure_diameter(dimension, body, normal, drawn)
    if isinstance(dimension, RadiusDimensionParams):
        return _measure_radius(dimension, body, normal, drawn)
    assert isinstance(dimension, AngularDimensionParams)
    return _measure_angular(dimension, body, normal)


def _as_direction(view: ViewProjection) -> ViewDirection:
    """The boundary ``ViewProjection`` literal is value-identical to the kernel
    ``ViewDirection`` for the four standard directions; this narrows the type
    without a map. ``flat_pattern`` (sheet-metal.md §7) has NO HLR projection
    direction — measuring a dimension against a flat-pattern view is out of v1 scope
    (dimensions attach to standard views); it falls back to the ``top`` normal purely
    as the §3.2 foreshortening reference, and the measured value stays model-true
    regardless (design §3.1)."""
    if view in ("flat_pattern", "section"):
        return "top"
    return view


def measure_dimension_dto(
    body: BodyShape,
    dimension: DimensionParams,
    view: ViewProjection,
    drawn: Sequence[EdgeSignature] = (),
) -> MeasuredDimension:
    """:func:`measure_dimension` with the typed errors folded onto the neutral
    :class:`MeasuredDimension` error channel (design §3.3/§5) — never a raise for a
    resolution outcome, so a bad ref is an honest per-dimension error, not a 500.

    *drawn* (the signatures of the model edges this view projects) is threaded through
    to the tier-3 circle re-anchor — see :func:`measure_dimension`."""
    try:
        measured = measure_dimension(body, dimension, view, drawn)
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
    except DimensionNotParallelError as exc:
        return MeasuredDimension(
            error=FeatureError(code="dimension_not_parallel", message=str(exc))
        )
    return MeasuredDimension(
        value=measured.value,
        unit=measured.unit,
        foreshortened=measured.foreshortened,
        anchor=measured.anchor,
    )
