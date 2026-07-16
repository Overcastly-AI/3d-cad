"""Drawing-view evaluation — part → projected standard views (design §1.2/§4).

The Drawings v1 slice #3 pipeline: turn a part feature tree into its requested
standard drawing views over the wire. A stateless pure function of the request
(RESEARCH §9): same request in, byte-identical projected edges out, in-process AND
across an interpreter restart.

Pipeline (design §1.2):

1. Evaluate the part body ONCE via :func:`geometry.features.evaluate_tree` (reused
   VERBATIM — drawings add NO new part-evaluation path). A part that produces no
   body surfaces as a whole-request ``part_error`` (there is nothing to project).
2. Run exact HLR (:func:`geometry.drawings.project_view`) per requested view. An
   HLR failure on one view (a fragile body, §1.5) becomes THAT view's typed
   ``view_projection_failed`` error — never a 500, never failing the other views.
3. Map the internal :class:`~geometry.drawings.ProjectedEdge` dataclasses → the
   neutral py-kit DTOs at this boundary. NO OCCT/kernel type crosses (CLAUDE.md).

The internal projection module owns determinism (the canonical edge order); this
module only orchestrates ``evaluate_tree`` + ``project_view`` and translates the
result to pure-pydantic DTOs. Mirrors :func:`geometry.assembly.evaluate_assembly`
in shape and error posture (a single part rather than an instance graph).
"""

from __future__ import annotations

from build123d import Solid
from py_kit.schemas.drawings import (
    DrawingViewResult,
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    MeasuredDimensionResult,
    ProjectedPoint,
    ProjectedViewEdge,
)
from py_kit.schemas.features import EvaluateTreeRequest, FeatureError

from geometry.drawings.measure import measure_dimension_dto
from geometry.drawings.project import (
    Point2D,
    ProjectedEdge,
    ViewProjectionError,
    project_view,
)
from geometry.features import TreeEvaluation, evaluate_tree


def _part_no_body_error(evaluation: TreeEvaluation) -> FeatureError:
    """The whole-request error for a part that evaluated to no body (design §4).

    Surfaces the strict-prefix failing feature's own error when present (e.g.
    ``profile_not_closed``), else the honest ``no_body`` — a sketch-only / empty
    tree. Mirrors ``geometry.assembly.evaluate._part_no_body_error`` for the
    single part a drawing view references.
    """
    failed = next(
        (
            f
            for f in evaluation.result.features
            if f.status == "error" and f.error is not None
        ),
        None,
    )
    if failed is not None and failed.error is not None:
        return failed.error
    return FeatureError(
        code="no_body",
        message=(
            "The part evaluated to no body (no body-affecting feature); there is "
            "nothing to project."
        ),
    )


def _to_point(point: Point2D) -> ProjectedPoint:
    """Internal 2D point → the neutral boundary point DTO (no kernel type)."""
    return ProjectedPoint(x_mm=point.x, y_mm=point.y)


def _to_edge(edge: ProjectedEdge) -> ProjectedViewEdge:
    """Map one internal projected-edge dataclass → the neutral boundary DTO."""
    return ProjectedViewEdge(
        primitive=edge.primitive,
        visible=edge.visible,
        start=_to_point(edge.start),
        end=_to_point(edge.end),
        midpoint=_to_point(edge.midpoint),
        center=_to_point(edge.center) if edge.center is not None else None,
        radius=edge.radius,
        points=[_to_point(p) for p in edge.points],
        # Provenance (design §3.3): the shipped EdgeSignature crosses the boundary
        # verbatim (it is already a py-kit type), so a pick on a dimensionable edge
        # yields a ref that resolves + measures directly. `source_edge` is None for
        # silhouette/free-form/ambiguous edges (un-dimensionable, §1.5).
        source_edge=edge.source_edge,
        dimensionable=edge.dimensionable,
    )


def _measure_dimensions(
    body: Solid, request: EvaluateDrawingViewsRequest
) -> list[MeasuredDimensionResult]:
    """Measure every requested dimension off the SAME exact body (design §3/§5).

    Each dimension is measured in request order against ``body`` in its tagged
    ``view`` (which supplies ONLY the §3.2 foreshortening frame — the value is
    model-true regardless, design §3.1). A per-dimension resolution failure is
    folded onto that dimension's typed error channel by ``measure_dimension_dto``
    (``subshape_unresolved`` / ``subshape_ambiguous`` / ``dimension_wrong_type``) —
    never a raise, never failing the other dimensions or the projected views. The
    ``id`` correlation token is echoed straight back for client mapping.
    """
    return [
        MeasuredDimensionResult(
            id=item.id,
            view=item.view,
            measured=measure_dimension_dto(body, item.dimension, item.view),
        )
        for item in request.dimensions
    ]


def evaluate_drawing_views(
    request: EvaluateDrawingViewsRequest,
) -> EvaluateDrawingViewsResult:
    """Project a part into its requested standard drawing views + measure its
    dimensions (design §1.2/§3).

    Evaluates the part body ONCE (``evaluate_tree``) then runs exact HLR per
    requested view AND measures each requested dimension off that SAME exact body
    (model-true, design §3.1). Total — never raises for an evaluation outcome: a
    body-less part is a whole-request ``part_error`` (empty ``views`` +
    ``dimensions``), a per-view HLR failure is that view's typed
    ``view_projection_failed`` (the rest still project), and a per-dimension
    resolution failure is that dimension's typed error (the rest still measure).
    Deterministic (RESEARCH §9): byte-identical projected edges + measured values
    for the same request, in-process and across an interpreter restart.
    """
    # An exact rational scale (ViewScale numerator/denominator, both >= 1) → the
    # strictly-positive float project_view multiplies every coordinate by.
    scale_value = request.scale.numerator / request.scale.denominator
    evaluation = evaluate_tree(
        EvaluateTreeRequest(
            part_id=request.part_id,
            tree_version=request.tree_version,
            features=request.features,
        )
    )
    if evaluation.body is None:
        return EvaluateDrawingViewsResult(
            part_id=request.part_id,
            tree_version=request.tree_version,
            views=[],
            part_error=_part_no_body_error(evaluation),
        )

    body = evaluation.body
    views: list[DrawingViewResult] = []
    for view in request.views:
        try:
            projection = project_view(body, view, scale=scale_value)
        except ViewProjectionError as exc:
            views.append(
                DrawingViewResult(
                    view=view,
                    scale=request.scale,
                    edges=[],
                    error=FeatureError(code="view_projection_failed", message=str(exc)),
                )
            )
            continue
        views.append(
            DrawingViewResult(
                view=view,
                scale=request.scale,
                edges=[_to_edge(e) for e in projection.edges],
                error=None,
            )
        )
    return EvaluateDrawingViewsResult(
        part_id=request.part_id,
        tree_version=request.tree_version,
        views=views,
        dimensions=_measure_dimensions(body, request),
        part_error=None,
    )
