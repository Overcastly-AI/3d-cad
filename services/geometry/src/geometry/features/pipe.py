"""Pipe and Plane Along Path: resolve picked curves, then build (PIPE-ALONG-PATH).

Both take curves the user picked (:data:`loft_wire.pipe.PathSegment`): a
curve of an earlier SOLVED sketch, mapped to world through that sketch's
resolved plane (so editing the skeleton moves every tube and plane on it), or
an edge of the active body, resolved through the strict / named / durable
tiers every picked edge uses. Each resolves to a world edge running from the
curve's own start: a sketch curve as drawn, a model edge from ``end_a`` of
its signature as picked (the angle datum's sense rule).

:func:`_evaluate_pipe` chains the edges and sweeps the tube
(:mod:`geometry.kernel.pipe`) into the body under the usual add / new body /
cut rules; :func:`resolve_along_path_plane` is the ``along_path`` branch of the
datum evaluator. Every failure is a typed :class:`FeatureError`.
"""

# pyright: reportPrivateUsage=false

from dataclasses import dataclass

from build123d import Edge, Plane, Vector
from loft_wire.features import (
    DatumAlongPathParams,
    EdgeSubshapeRef,
    EvaluatedFeatureInput,
    FeatureError,
    PathSegment,
    PathSketchCurve,
    PipeFeature,
)
from loft_wire.sketch import SketchPoint

from geometry.features.cut_scope import cut_one_tool
from geometry.features.naming_hooks import labelled_names
from geometry.features.owner import edge_owner_body_id
from geometry.features.state import EvaluationState, _add_body
from geometry.kernel.datum_path import DatumPathRangeError, plane_along_edge
from geometry.kernel.edges import resolve_edge_durable
from geometry.kernel.extrude import ProfileNotClosedError, entity_edges
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.kernel.naming import OpHistory
from geometry.kernel.path_chain import (
    PathNotConnectedError,
    chain_edges,
    reversed_edge,
)
from geometry.kernel.pipe import PipeBendError, PipeError, build_pipe
from geometry.kernel.sweep_check import SweepSelfIntersectingError


@dataclass(frozen=True)
class _Curve:
    """A picked curve in world space, running from its own start."""

    edge: Edge
    #: The face-label key of the curve (stable across edits of its geometry).
    key: str
    #: The owning sketch's plane normal, for a sketch curve.
    sketch_normal: Vector | None


def _sketch_curve(
    ref: PathSketchCurve, state: EvaluationState, role: str
) -> _Curve | FeatureError:
    sketch_id = ref.sketch.feature_id
    solved = state.solved_sketches.get(sketch_id)
    plane = state.sketch_planes.get(sketch_id)
    if solved is None or plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                f"The {role} must be in an earlier, successfully solved sketch of "
                "this tree; that sketch is missing, later, suppressed or failed."
            ),
            upstream_feature_id=sketch_id,
        )
    entity = next((e for e in solved.entities if e.id == ref.entity), None)
    if entity is None or isinstance(entity, SketchPoint):
        what = "is no longer in its sketch" if entity is None else "is a point"
        return FeatureError(
            code="reference_unresolved",
            message=f"The {role} curve '{ref.entity}' {what}. Pick the curve again.",
            upstream_feature_id=sketch_id,
        )
    try:
        edges = entity_edges(plane, entity)
    except ProfileNotClosedError as exc:
        return FeatureError(code="sweep_failed", message=str(exc))
    if len(edges) != 1:
        return FeatureError(
            code="sweep_failed",
            message=f"The {role} curve '{ref.entity}' is not one curve.",
        )
    return _Curve(edges[0], f"{sketch_id}:{ref.entity}", plane.z_dir)


def _model_edge(
    ref: EdgeSubshapeRef, state: EvaluationState, index: int, role: str
) -> _Curve | FeatureError:
    owner = edge_owner_body_id(ref, state)
    if isinstance(owner, FeatureError):
        return owner
    if owner is None:
        return FeatureError(
            code="subshape_unresolved",
            message=(
                f"The {role} is a model edge, but no body precedes this feature; "
                "add a feature that creates a body first."
            ),
            upstream_feature_id=ref.feature_id,
        )
    try:
        resolved = resolve_edge_durable(
            state.bodies[owner],
            ref.selector.signature,
            tally=state.subshape_tally,
            face_names=state.body_face_names(owner),
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(
            code="subshape_unresolved",
            message=str(exc),
            upstream_feature_id=ref.feature_id,
        )
    except SubshapeAmbiguousError as exc:
        return FeatureError(
            code="subshape_ambiguous",
            message=str(exc),
            upstream_feature_id=ref.feature_id,
        )
    edge = resolved.edge
    # The SENSE is the pick's (end_a first), never the edge's current kernel
    # orientation, which an upstream rebuild may flip.
    a = ref.selector.signature.end_a
    picked_start = Vector(a.x, a.y, a.z)
    if (edge.position_at(1) - picked_start).length < (
        edge.position_at(0) - picked_start
    ).length:
        edge = reversed_edge(edge)
    return _Curve(edge, f"edge{index}", None)


def _resolve_curve(
    segment: PathSegment, state: EvaluationState, index: int, role: str
) -> _Curve | FeatureError:
    if isinstance(segment, PathSketchCurve):
        return _sketch_curve(segment, state, role)
    return _model_edge(segment, state, index, role)


def _evaluate_pipe(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Sweep a circle or ring along the picked chain and apply it to the body.

    ``add`` with ``merge`` joins the tube to the active body (or starts the
    first one), ``add`` without it starts a new body, ``cut`` removes it from
    the active body (``no_prior_body`` without one). The active body is only
    replaced on success.
    """
    feature = item.feature
    assert isinstance(feature, PipeFeature), "registry dispatches on type='pipe'"
    params = feature.params
    curves: list[_Curve] = []
    for index, segment in enumerate(params.path):
        curve = _resolve_curve(segment, state, index, "pipe path")
        if isinstance(curve, FeatureError):
            return curve
        curves.append(curve)
    try:
        chained = chain_edges([curve.edge for curve in curves])
    except PathNotConnectedError as exc:
        return FeatureError(code="sweep_path_not_connected", message=str(exc))

    if params.operation == "cut" and state.active_body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    history = OpHistory()
    try:
        tool = build_pipe(
            chained,
            [curve.key for curve in curves],
            params.outer_diameter_mm,
            params.wall_thickness_mm,
            history,
        )
    except (PipeBendError, PipeError) as exc:
        return FeatureError(code="sweep_failed", message=str(exc))
    except SweepSelfIntersectingError as exc:
        return FeatureError(code="sweep_self_intersecting", message=str(exc))
    generated = labelled_names(item.id, history)
    if params.operation == "cut":
        return cut_one_tool(
            state,
            tool,
            feature_id=item.id,
            scope=params.cut_bodies,
            generated=generated,
        )
    return _add_body(item, state, tool, merge=params.merge, generated=generated)


def resolve_along_path_plane(
    params: DatumAlongPathParams, state: EvaluationState
) -> Plane | FeatureError:
    """The ``along_path`` datum's plane, or the typed error that makes it sick."""
    curve = _resolve_curve(params.path, state, 0, "plane's path")
    if isinstance(curve, FeatureError):
        return curve
    try:
        return plane_along_edge(
            curve.edge,
            params.measure,
            params.ratio,
            params.distance_mm,
            params.flip,
            curve.sketch_normal,
        )
    except DatumPathRangeError as exc:
        return FeatureError(code="datum_path_out_of_range", message=str(exc))
