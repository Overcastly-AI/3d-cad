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
   A ``flat_pattern`` view (sheet-metal.md §7) instead SKIPS HLR and unfolds the
   sheet-metal body (:func:`geometry.drawings.flat_pattern_view_result`) into the
   SAME :class:`DrawingViewResult` shape (edge_role-tagged outline + bend table);
   a non-sheet-metal body is that view's typed ``flat_pattern_not_sheet_metal``.
3. Map the internal :class:`~geometry.drawings.ProjectedEdge` dataclasses → the
   neutral py-kit DTOs at this boundary. NO OCCT/kernel type crosses (CLAUDE.md).

The internal projection module owns determinism (the canonical edge order); this
module only orchestrates ``evaluate_tree`` + ``project_view`` and translates the
result to pure-pydantic DTOs. Mirrors :func:`geometry.assembly.evaluate_assembly`
in shape and error posture (a single part rather than an instance graph).
"""

from __future__ import annotations

from build123d import Plane
from py_kit.schemas.drawings import (
    DrawingViewResult,
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    MeasuredDimensionResult,
    ProjectedPoint,
    ProjectedViewEdge,
    SectionFaceLoop,
    SectionViewParams,
    ViewProjection,
    ViewScale,
)
from py_kit.schemas.features import (
    DatumPlaneRef,
    EdgeSignature,
    EvaluateTreeRequest,
    FeatureError,
    GeomRef,
)

from geometry.drawings.flat_pattern import FLAT_PATTERN_VIEW, flat_pattern_view_result
from geometry.drawings.measure import measure_dimension_dto
from geometry.drawings.project import (
    Point2D,
    ProjectedEdge,
    ViewProjectionError,
    project_view,
)
from geometry.drawings.section import (
    SectionCut,
    SectionEmptyError,
    SectionLoop2D,
    SectionMissesBodyError,
    SectionPlaneNotPrincipalError,
    section_cut,
)
from geometry.features import TreeEvaluation, evaluate_tree
from geometry.kernel.datum import DATUM_PLANES
from geometry.kernel.types import BodyShape

#: The section view projection kind (drawings-section.md v1) — like ``flat_pattern``
#: it is NOT one of the third-angle quartet: it has its OWN evaluate + compose branch.
SECTION_VIEW = "section"


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


def projected_edge_dto(edge: ProjectedEdge) -> ProjectedViewEdge:
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
        # The model→projected endpoint correspondence (design §3.3) captured before
        # `start`/`end` were canonicalised — lets a picked projected end name the
        # correct model `end_a`/`end_b` without the caller re-projecting.
        start_is_end_a=edge.start_is_end_a,
    )


def _drawn_edges_by_view(
    views: list[DrawingViewResult],
) -> dict[ViewProjection, list[EdgeSignature]]:
    """The MODEL edges each projected view actually draws, keyed by projection.

    Provenance the projector already computed (``ProjectedViewEdge.source_edge``,
    design §3.3), collected once per request. It is the set a user could have PICKED
    in that view, which is what makes the tier-3 circle re-anchor honest rather than a
    coin flip (QA-3, :func:`geometry.drawings.anchor.resolve_anchor_edge`): a
    thickness edit slides a bore's rim along its own axis, and the two rims of a
    through hole are congruent — but the projector emits the drawn curve once, from
    the edge the viewer sees. Silhouette / un-tied edges carry no signature and simply
    do not appear here.
    """
    drawn: dict[ViewProjection, list[EdgeSignature]] = {}
    for result in views:
        if result.error is not None:
            continue
        drawn[result.view] = [
            edge.source_edge for edge in result.edges if edge.source_edge is not None
        ]
    return drawn


def _measure_dimensions(
    body: BodyShape,
    request: EvaluateDrawingViewsRequest,
    drawn_by_view: dict[ViewProjection, list[EdgeSignature]],
) -> list[MeasuredDimensionResult]:
    """Measure every requested dimension off the SAME exact body (design §3/§5).

    Each dimension is measured in request order against ``body`` in its tagged
    ``view`` (which supplies ONLY the §3.2 foreshortening frame — the value is
    model-true regardless, design §3.1). A per-dimension resolution failure is
    folded onto that dimension's typed error channel by ``measure_dimension_dto``
    (``subshape_unresolved`` / ``subshape_ambiguous`` / ``dimension_wrong_type``) —
    never a raise, never failing the other dimensions or the projected views. The
    ``id`` correlation token is echoed straight back for client mapping.

    ``drawn_by_view`` hands each dimension the model edges ITS OWN view draws
    (:func:`_drawn_edges_by_view`) — used only by the tier-3 circle re-anchor, and
    never by a measured value.
    """
    return [
        MeasuredDimensionResult(
            id=item.id,
            view=item.view,
            measured=measure_dimension_dto(
                body, item.dimension, item.view, drawn_by_view.get(item.view, ())
            ),
        )
        for item in request.dimensions
    ]


def _to_section_loop(loop: SectionLoop2D) -> SectionFaceLoop:
    """Internal 2D section loop → the neutral boundary DTO (no kernel type)."""
    return SectionFaceLoop(
        outer=[_to_point(p) for p in loop.outer],
        holes=[[_to_point(p) for p in hole] for hole in loop.holes],
    )


def _resolve_section_plane(
    ref: GeomRef, evaluation: TreeEvaluation
) -> Plane | FeatureError:
    """Resolve a section view's cutting-plane reference to a concrete plane (§1).

    Reuses the SAME datum machinery a sketch's plane reference resolves through
    (drawings-section.md §1, DRY): a :class:`DatumPlaneRef` maps by name through the
    shipped ``DATUM_PLANES``; a :class:`FeatureRef` looks the datum feature's already-
    resolved plane up in ``evaluation.datum_planes`` (populated by ``evaluate_tree`` —
    never a re-resolution). A ref that does not resolve to a datum plane of this prefix
    (deleted / retargeted / a non-datum feature) is a typed ``subshape_unresolved`` (§7
    — the topological-naming honesty contract), never a wrong plane.
    """
    if isinstance(ref, DatumPlaneRef):
        return DATUM_PLANES[ref.plane]
    plane = evaluation.datum_planes.get(ref.feature_id)
    if plane is None:
        return FeatureError(
            code="subshape_unresolved",
            message=(
                "The section cutting plane must reference an origin datum (XY/XZ/YZ) "
                "or an earlier axis-aligned datum feature of this part; the referenced "
                "feature is not a resolved datum plane."
            ),
            upstream_feature_id=ref.feature_id,
        )
    return plane


def section_view_result(
    evaluation: TreeEvaluation,
    params: SectionViewParams | None,
    scale: ViewScale,
    scale_value: float,
) -> DrawingViewResult:
    """Build the ``section`` :class:`DrawingViewResult` for an evaluated part (§2).

    Resolves the cutting plane (§1), cuts the eye-side half through the shipped
    disjoint-tolerant boolean (:func:`geometry.drawings.section.section_cut`), projects
    the remaining behind-geometry through the shipped HLR seam with the derived STANDARD
    view direction (§3) — filtered to VISIBLE edges (a section omits hidden lines, §3) —
    and carries the canonical cross-section loops for the compose layer to hatch (§5).
    Total — never raises for a modelling outcome: a missing plane param, a non-principal
    normal, a plane that misses / swallows the body, an unresolved datum ref, or an HLR
    failure each become this view's typed error (drawings-section.md §7).
    """
    if params is None:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=FeatureError(
                code="section_params_missing",
                message=(
                    "A section view requires `section_params` (the cutting plane + "
                    "flip); none were provided."
                ),
            ),
        )
    if evaluation.body is None:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=_part_no_body_error(evaluation),
        )
    resolved = _resolve_section_plane(params.plane, evaluation)
    if isinstance(resolved, FeatureError):
        return DrawingViewResult(view=SECTION_VIEW, scale=scale, error=resolved)

    try:
        cut: SectionCut = section_cut(
            evaluation.body, resolved, flip=params.flip, scale=scale_value
        )
    except SectionPlaneNotPrincipalError as exc:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=FeatureError(code="section_plane_not_principal", message=str(exc)),
        )
    except SectionMissesBodyError as exc:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=FeatureError(code="section_plane_misses_body", message=str(exc)),
        )
    except SectionEmptyError as exc:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=FeatureError(code="section_empty", message=str(exc)),
        )

    try:
        projection = project_view(cut.remaining, cut.view, scale=scale_value)
    except ViewProjectionError as exc:
        return DrawingViewResult(
            view=SECTION_VIEW,
            scale=scale,
            error=FeatureError(code="view_projection_failed", message=str(exc)),
        )
    # A section view conventionally OMITS hidden lines (design §3) — the interior is
    # now exposed, so dashed occluded edges only add noise. Keep visible edges only.
    return DrawingViewResult(
        view=SECTION_VIEW,
        scale=scale,
        edges=[projected_edge_dto(e) for e in projection.visible_edges],
        section_faces=[_to_section_loop(lp) for lp in cut.loops],
        error=None,
    )


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
    for index, view in enumerate(request.views):
        if view == FLAT_PATTERN_VIEW:
            # A flat_pattern view SKIPS HLR (sheet-metal.md §7): it unfolds the
            # sheet-metal body and feeds the edge_role-tagged outline + bend table
            # straight into the SAME DrawingViewResult shape. Non-sheet-metal /
            # unresolvable-bend cases are that view's typed error (handled inside).
            views.append(flat_pattern_view_result(evaluation, request.scale))
            continue
        if view == SECTION_VIEW:
            # A section view (drawings-section.md §2) resolves its cutting plane, cuts
            # the eye-side half, then projects the behind-geometry through the SAME HLR
            # seam with the derived standard direction (no frame refactor, §3) — its
            # own evaluate arm, mirroring flat_pattern. Handled entirely inside. Each
            # section view reads ITS OWN params from the per-view `section_params` map
            # (keyed by this view's index into `views`, §1) — the level-correct wire
            # that binds params to a specific view; a section view with no entry is a
            # typed `section_params_missing` inside `section_view_result`.
            views.append(
                section_view_result(
                    evaluation,
                    request.section_params.get(index),
                    request.scale,
                    scale_value,
                )
            )
            continue
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
                edges=[projected_edge_dto(e) for e in projection.edges],
                error=None,
            )
        )
    return EvaluateDrawingViewsResult(
        part_id=request.part_id,
        tree_version=request.tree_version,
        views=views,
        dimensions=_measure_dimensions(body, request, _drawn_edges_by_view(views)),
        part_error=None,
    )
