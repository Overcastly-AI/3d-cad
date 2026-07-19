"""Flat-pattern drawing view — a sheet-metal body's unfold AS a projected view.

docs/design/sheet-metal.md §6/§7 + drawings.md §7. A ``flat_pattern`` view SKIPS
HLR: a :class:`~geometry.sheet_metal.FlatPattern` is already 2D, so this module
feeds the unfold's ``edge_role``-tagged outline straight into the shipped neutral
:class:`~py_kit.schemas.drawings.ProjectedViewEdge` / :class:`DrawingViewResult`
shape every standard view already produces (never a new projection frame, never a
new crossing type), plus a per-bend :class:`~py_kit.schemas.drawings.BendTableRow`
table. It REUSES :func:`geometry.features.evaluate_tree`'s body + bend provenance
(via the :class:`TreeEvaluation`) and :func:`geometry.sheet_metal.unfold_sheet_metal`
— the only new work is the pure DTO translation below.

Honest per-view failure (sheet-metal.md §7, the standard drawings per-view
posture): a body with no sheet-metal defaults is a typed
``flat_pattern_not_sheet_metal`` (never a crash), an unresolvable/ambiguous bend a
``subshape_unresolved`` / ``subshape_ambiguous`` (never a wrong flat pattern, §5),
and any other unfold-scope failure (a non-parallel or depth >= 2 star, §4.3) a
``flat_pattern_failed`` — all inside a 200, the rest of the requested views
untouched.

Determinism (RESEARCH §9 / sheet-metal.md §9 #4): the outline + bend table are a
pure function of the deterministic unfold, so the same request yields byte-
identical edges + rows, in-process and across an interpreter restart.
"""

from __future__ import annotations

from py_kit.schemas.drawings import (
    BendTableRow,
    DrawingViewResult,
    ProjectedPoint,
    ProjectedViewEdge,
    ViewScale,
)
from py_kit.schemas.features import FeatureError

from geometry.features import TreeEvaluation
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.sheet_metal import (
    FlatPattern,
    SheetMetalUnfoldError,
    unfold_sheet_metal,
)

#: The one non-standard :data:`~py_kit.schemas.drawings.ViewProjection` this module
#: owns (the others go through exact HLR, :func:`geometry.drawings.project_view`).
FLAT_PATTERN_VIEW = "flat_pattern"


def _to_edges(pattern: FlatPattern, scale: float) -> list[ProjectedViewEdge]:
    """The flat pattern's outline as neutral :class:`ProjectedViewEdge`s (§6).

    Every flat-pattern outline entry is a straight segment, so each maps to a
    ``primitive="line"`` edge carrying its ``edge_role`` (``body`` cut edge or
    ``bend`` fold line). Coordinates are scaled by *scale* to match the view's echoed
    :class:`ViewScale` (the same view-mm convention the HLR views use); the order is
    the unfold's own deterministic outline order (body edges, then bend lines), so no
    re-sort is needed for byte-determinism. Endpoints are ``visible`` (a flat pattern
    has nothing to occlude — it is viewed along its own normal, §7).
    """
    edges: list[ProjectedViewEdge] = []
    for e in pattern.outline:
        x1, y1, x2, y2 = e.x1 * scale, e.y1 * scale, e.x2 * scale, e.y2 * scale
        edges.append(
            ProjectedViewEdge(
                primitive="line",
                visible=True,
                start=ProjectedPoint(x_mm=x1, y_mm=y1),
                end=ProjectedPoint(x_mm=x2, y_mm=y2),
                midpoint=ProjectedPoint(x_mm=(x1 + x2) / 2.0, y_mm=(y1 + y2) / 2.0),
                edge_role=e.role,
            )
        )
    return edges


def _to_bend_table(pattern: FlatPattern) -> list[BendTableRow]:
    """The flat pattern's per-bend rows as the shop's bend table (§6/§7).

    Values are MODEL-true (mm / degrees), never scaled — they are the real fold
    instructions. Order is the unfold's deterministic bend order (by fold position),
    and each row's ``bend_id`` matches its ``edge_role="bend"`` outline edge.
    """
    return [
        BendTableRow(
            bend_id=b.bend_id,
            angle_deg=b.angle_deg,
            radius_mm=b.radius_mm,
            direction=b.direction,
            bend_allowance_mm=b.allowance_mm,
        )
        for b in pattern.bends
    ]


def flat_pattern_view_result(
    evaluation: TreeEvaluation, scale: ViewScale
) -> DrawingViewResult:
    """Build the ``flat_pattern`` :class:`DrawingViewResult` for an evaluated part.

    Reuses the :class:`TreeEvaluation`'s body + bend provenance + sheet-metal
    defaults (produced once by :func:`evaluate_tree`) and
    :func:`unfold_sheet_metal`, then translates the :class:`FlatPattern` into the
    shipped neutral edge shape + bend table. Total — never raises for a modelling
    outcome: a non-sheet-metal body, an unresolvable bend, or an out-of-scope star
    each become that view's typed error (the rest of the request is unaffected).
    """
    scale_value = scale.numerator / scale.denominator
    defaults = evaluation.sheet_metal_defaults
    if evaluation.body is None or defaults is None:
        return DrawingViewResult(
            view=FLAT_PATTERN_VIEW,
            scale=scale,
            error=FeatureError(
                code="flat_pattern_not_sheet_metal",
                message=(
                    "A flat_pattern view requires a sheet-metal body (a base flange "
                    "+ edge flanges); this part has no sheet-metal feature. Add a "
                    "sheet-metal base flange, or request a standard projection."
                ),
            ),
        )
    try:
        pattern = unfold_sheet_metal(
            evaluation.body,
            evaluation.bend_provenance,
            defaults.thickness_mm,
            defaults.k_factor,
        )
    except (SubshapeUnresolvedError, SubshapeAmbiguousError) as exc:
        code = (
            "subshape_unresolved"
            if isinstance(exc, SubshapeUnresolvedError)
            else "subshape_ambiguous"
        )
        return DrawingViewResult(
            view=FLAT_PATTERN_VIEW,
            scale=scale,
            error=FeatureError(code=code, message=str(exc)),
        )
    except SheetMetalUnfoldError as exc:
        return DrawingViewResult(
            view=FLAT_PATTERN_VIEW,
            scale=scale,
            error=FeatureError(code="flat_pattern_failed", message=str(exc)),
        )
    return DrawingViewResult(
        view=FLAT_PATTERN_VIEW,
        scale=scale,
        edges=_to_edges(pattern, scale_value),
        bend_table=_to_bend_table(pattern),
        error=None,
    )
