"""Feature-tree evaluation (feature-tree design §4) — geometry-side semantics.

The evaluation contract's DTOs live in :mod:`py_kit.schemas.features`
(shared single source, CLAUDE.md DRY rule); this package owns the ordered
dispatch, the strict-prefix partial-result rule, and the handler registry
that new feature types (extrude, BACKLOG #6) plug into.
"""

from geometry.features.evaluate import (
    FEATURE_HANDLERS,
    EvaluationState,
    FeatureHandler,
    TreeEvaluation,
    evaluate_tree,
    store_mesh_glb,
)

__all__ = [
    "FEATURE_HANDLERS",
    "EvaluationState",
    "FeatureHandler",
    "TreeEvaluation",
    "evaluate_tree",
    "store_mesh_glb",
]
