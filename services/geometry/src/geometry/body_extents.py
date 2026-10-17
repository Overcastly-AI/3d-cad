"""Measure every body of a tree for the cut list (CUT-LIST).

Geometry measures; the gateway groups (:mod:`loft_wire.cut_list`). The tree
is evaluated through the same :func:`geometry.features.evaluate_tree` as
``/evaluate``, so a cut list read right after a rebuild is served from the
rebuild cache, and each last-good body is measured on its exact B-rep
(:func:`geometry.kernel.extents.body_extents`). A tree with no body measures
to an empty list: an empty cut list, not an error.
"""

from loft_wire.cut_list import BodyExtent, BodyExtentsResult
from loft_wire.features import EvaluateTreeRequest

from geometry.faults import unexpected_query_failure
from geometry.features import evaluate_tree
from geometry.kernel.extents import body_extents, body_volume


def evaluate_body_extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    """Each last-good body's extents along its own axes, in tree order."""
    # Keep the evaluation alive while its shapes are measured (TreeEvaluation:
    # the rebuild cache reclaims them once it is unreachable).
    evaluation = evaluate_tree(request)
    try:
        bodies = [
            BodyExtent(
                base_feature_id=base_id,
                extents_mm=body_extents(body),
                volume_mm3=body_volume(body),
            )
            for base_id, body in evaluation.bodies.items()
        ]
    except Exception as exc:
        raise unexpected_query_failure(
            exc, code="body_extents_failed", action="body measurement"
        ) from exc
    return BodyExtentsResult(
        part_id=request.part_id, tree_version=request.tree_version, bodies=bodies
    )
