"""The feature registry (feature-tree design §4).

:data:`FEATURE_HANDLERS` maps a feature ``type`` to its handler and is where a
new feature type plugs in; :func:`_dispatch` routes one feature through it and
turns a handler's raise into a per-feature error. :data:`BODY_AFFECTING_TYPES`
names the types whose ok evaluation mutates the body set.
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

import uuid

from loft_wire.features import (
    EvaluatedFeatureInput,
    FeatureData,
    FeatureError,
    SolvedSketchData,
)
from loft_wire.sketch import classify_overconstraint

from geometry.features.bodies import (
    _evaluate_boolean,
    _evaluate_import,
)
from geometry.features.datum_sketch import (
    _evaluate_datum,
    _evaluate_sketch,
)
from geometry.features.hole import (
    _evaluate_hole,
)
from geometry.features.modify import (
    _evaluate_chamfer,
    _evaluate_draft,
    _evaluate_fillet,
    _evaluate_shell,
)
from geometry.features.pattern_mirror import (
    _evaluate_mirror,
    _evaluate_pattern,
)
from geometry.features.sheet_metal_features import (
    _evaluate_sheet_metal_base_flange,
    _evaluate_sheet_metal_corner_relief,
    _evaluate_sheet_metal_edge_flange,
    _evaluate_sheet_metal_hem,
)
from geometry.features.sketch_solids import (
    _evaluate_extrude,
    _evaluate_loft,
    _evaluate_revolve,
    _evaluate_sweep,
)
from geometry.features.state import (
    EvaluationState,
    FeatureHandler,
    InvalidBodyError,
)

#: Feature types whose ok evaluation mutates the body set (§MB-0). The
#: main loop records the last such feature's id as ``state.prev_body_feature_id``
#: so a pattern can infer its combine mode from the immediately-preceding
#: body-affecting feature (BACKLOG #3, :func:`_pattern_cut_tools`). Sketch/datum
#: are absent — they produce input geometry / a plane, never a body.
BODY_AFFECTING_TYPES: frozenset[str] = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "draft",
        "hole",
        "pattern",
        "mirror",
        "import",
        "sheet_metal_base_flange",
        "sheet_metal_edge_flange",
        "sheet_metal_hem",
        "sheet_metal_corner_relief",
        "boolean",
    }
)


#: The dispatcher registry (§4): feature ``type`` discriminator → handler.
#: Consulted by key only; no iteration order participates (RESEARCH §9
#: determinism). New feature types plug in here.
FEATURE_HANDLERS: dict[str, FeatureHandler] = {
    "datum": _evaluate_datum,
    "sketch": _evaluate_sketch,
    "extrude": _evaluate_extrude,
    "revolve": _evaluate_revolve,
    "sweep": _evaluate_sweep,
    "loft": _evaluate_loft,
    "fillet": _evaluate_fillet,
    "chamfer": _evaluate_chamfer,
    "shell": _evaluate_shell,
    "draft": _evaluate_draft,
    "hole": _evaluate_hole,
    "pattern": _evaluate_pattern,
    "mirror": _evaluate_mirror,
    "import": _evaluate_import,
    "sheet_metal_base_flange": _evaluate_sheet_metal_base_flange,
    "sheet_metal_edge_flange": _evaluate_sheet_metal_edge_flange,
    "sheet_metal_hem": _evaluate_sheet_metal_hem,
    "sheet_metal_corner_relief": _evaluate_sheet_metal_corner_relief,
    "boolean": _evaluate_boolean,
}


def _dispatch(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Route one feature through the registry; outcomes are values, not raises."""
    handler = FEATURE_HANDLERS.get(item.feature.type)
    if handler is None:
        return FeatureError(
            code="feature_type_unsupported",
            message=(
                f"Feature type '{item.feature.type}' has no registered "
                "evaluator in this build."
            ),
        )
    try:
        return handler(item, state)
    except InvalidBodyError as exc:
        # The CM-6 gate: the handler built a body OCCT calls invalid, and
        # EvaluationState refused to install it. A typed code, not the generic
        # `evaluation_failed`, because the user can act on it (the previous
        # feature's body is intact and the geometry that broke is this one's) and
        # because a silent wrong solid is precisely what this replaces.
        return FeatureError(code="invalid_body", message=str(exc))
    except Exception as exc:
        # Belt and braces (§4.3): a handler bug must surface as a per-feature
        # error pinned to the failing feature, not a 500 for the whole tree.
        # Kernel/solver detail is sanitized down to the exception class name.
        return FeatureError(
            code="evaluation_failed",
            message=(
                f"Unexpected {type(exc).__name__} while evaluating feature "
                f"type '{item.feature.type}'."
            ),
        )


def _feature_data(feature_id: uuid.UUID, state: EvaluationState) -> FeatureData | None:
    """The §7.10 payload of an ``ok`` feature: solved sketch geometry, when
    the feature produced one (body-affecting features produce none today)."""
    solved = state.solved_sketches.get(feature_id)
    if solved is None:
        return None
    # An over-constrained-but-solvable sketch carries the typed redundant
    # diagnosis on its payload (BACKLOG #6); a cleanly-solved sketch → None.
    diagnosis = classify_overconstraint(solved)
    return SolvedSketchData.model_validate(
        {
            **solved.model_dump(),
            "diagnosis": diagnosis.model_dump() if diagnosis else None,
            "projections": [
                status.model_dump()
                for status in state.sketch_projections.get(feature_id, [])
            ],
        }
    )
