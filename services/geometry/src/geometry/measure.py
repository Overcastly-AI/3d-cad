"""Stateless measurement service (BACKLOG #6a) — recompute + exact distance.

Ties the boundary contract (:mod:`py_kit.schemas.measure`) to the kernel: point
targets need no geometry, edge targets recompute the body from the supplied
feature tree — reusing :func:`geometry.features.evaluate_tree` (DRY: the SAME
ordered dispatch + strict-prefix rule as ``POST /api/v1/evaluate``, no
duplicated evaluation logic) — and measure the EXACT B-rep edge. Never persists
anything (CLAUDE.md: the geometry service is stateless); the response is a plain
value DTO, no artifact and no kernel type crosses the boundary.
"""

from build123d import Solid
from py_kit.errors import ValidationApiError
from py_kit.schemas.measure import EdgeTarget, MeasureRequest, MeasureResult

from geometry.faults import unexpected_query_failure
from geometry.features import evaluate_tree, tree_no_body_error
from geometry.kernel import EdgeIndexError, MeasureError, measure_targets


def _needs_body(request: MeasureRequest) -> bool:
    """True when either target is an edge (so the tree must be recomputed)."""
    return isinstance(request.a, EdgeTarget) or isinstance(request.b, EdgeTarget)


def evaluate_measure(request: MeasureRequest) -> MeasureResult:
    """Resolve both targets and return their exact nearest distance.

    Edge targets recompute ``request.tree`` and measure its last-good body; a
    tree that produces no body is a clean 422 ``tree_measure_failed`` envelope
    (never a 500, never a wrong number). A bad edge index or a solver failure
    is likewise a 422, not a crash. Deterministic end to end (RESEARCH §9): the
    tree evaluation and the nearest-distance solve are both pure functions of
    the request.
    """
    body: Solid | None = None
    if _needs_body(request):
        # Guaranteed present by MeasureRequest validation, but re-asserted so a
        # future caller can never smuggle an edge target past without a tree.
        assert request.tree is not None
        evaluation = evaluate_tree(request.tree)
        if evaluation.body is None:
            raise tree_no_body_error(
                evaluation.result, code="tree_measure_failed", action="measure"
            )
        body = evaluation.body

    try:
        return measure_targets(request.a, request.b, body)
    except EdgeIndexError as exc:
        raise ValidationApiError(str(exc), code="edge_index_out_of_range") from exc
    except MeasureError as exc:
        raise ValidationApiError(str(exc), code="measure_failed") from exc
    except Exception as exc:
        # Belt and braces: a RAW OCCT/std raise (e.g. the
        # BRepExtrema_DistShapeShape constructor, or PointOnShape1(1) with
        # NbSolution()==0, on a degenerate recomputed edge) must surface as
        # the promised 422, never a 500. Sanitized to the exception class
        # name (geometry.faults) — no kernel internals leak to the client.
        raise unexpected_query_failure(
            exc, code="measure_failed", action="measurement"
        ) from exc
