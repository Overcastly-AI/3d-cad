"""Feature-tree evaluation (feature-tree design §4) — geometry-side semantics.

The evaluation contract's DTOs live in :mod:`py_kit.schemas.features`
(shared single source, CLAUDE.md DRY rule); this package owns the ordered
dispatch, the strict-prefix partial-result rule, and the handler registry
(``sketch`` + ``extrude`` today) that new feature types plug into. Artifact
delivery (the content-addressed GLB behind ``mesh_glb_id``) lives in
:mod:`geometry.mesh_store` — the interim §7.8 seam.
"""

from geometry.features.evaluate import (
    FEATURE_HANDLERS,
    EvaluationState,
    FeatureHandler,
    TreeEvaluation,
    evaluate_tree,
)

__all__ = [
    "FEATURE_HANDLERS",
    "EvaluationState",
    "FeatureHandler",
    "TreeEvaluation",
    "evaluate_tree",
]
