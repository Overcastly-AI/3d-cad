"""Stateless selection-overlay service (BACKLOG #6b) — recompute + pick geometry.

Ties the boundary contract (:mod:`py_kit.schemas.overlay`) to the kernel: it
recomputes the body from the supplied feature tree — reusing
:func:`geometry.features.evaluate_tree` (DRY: the SAME ordered dispatch +
strict-prefix rule as ``POST /api/v1/evaluate`` and ``/measure``, no duplicated
evaluation logic) — and returns the last-good body's pickable vertices + edges.
The edge list is in ``body.edges()`` order, the SAME enumeration
``/measure`` resolves ``EdgeTarget.index`` against, so a client can measure an
edge by its overlay index. Never persists anything (CLAUDE.md: the geometry
service is stateless); the response is a plain value DTO, no artifact and no
kernel type crosses the boundary.
"""

from py_kit.schemas.overlay import OverlayRequest, OverlayResult

from geometry.faults import unexpected_query_failure
from geometry.features import evaluate_tree, tree_no_body_error
from geometry.kernel import attribute_faces, selection_overlay


def evaluate_overlay(request: OverlayRequest) -> OverlayResult:
    """Recompute ``request.tree`` and return its body's pickable geometry.

    A tree that produces no body is a clean 422 ``tree_overlay_failed`` envelope
    (never a 500, never an empty overlay masquerading as success); a raw kernel
    raise while enumerating the overlay is a 422 ``overlay_failed``. Both share
    the measure endpoint's "surfaces as a 422, never a 500" posture.
    Deterministic end to end (RESEARCH §9): the tree evaluation and the overlay
    enumeration are pure functions of the request.
    """
    evaluation = evaluate_tree(request.tree)
    if evaluation.body is None:
        raise tree_no_body_error(
            evaluation.result, code="tree_overlay_failed", action="overlay"
        )

    try:
        # Per-face feature provenance (FINDINGS #9): attribute each face of the
        # last-good body to the feature that created / last modified it, threaded
        # onto OverlayFace.feature_id so the frontend highlights ONLY the selected
        # feature's faces (never a whole-body clay swap). Additive — the vertices/
        # edges/signatures path is unchanged.
        face_features = attribute_faces(evaluation.body, evaluation.body_history)
        return selection_overlay(
            evaluation.body, request.tree.linear_deflection, face_features
        )
    except Exception as exc:
        raise unexpected_query_failure(
            exc, code="overlay_failed", action="overlay"
        ) from exc
