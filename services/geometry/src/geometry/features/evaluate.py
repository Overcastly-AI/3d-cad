"""Feature-tree evaluation — ordered dispatch + strict-prefix rule (design §4).

Implements the stateless documents→geometry evaluation contract of
docs/design/feature-tree.md §4 over the shared DTOs in
:mod:`py_kit.schemas.features`. The evaluator walks the request's ordered
feature list exactly as given (§4.2 — documents applies the rollback bar
BEFORE sending, so a rolled-back tree arrives simply as a shorter list;
geometry never knows rollback exists) and applies the strict-prefix
partial-result rule (§4.3): the FIRST failure is marked ``error``, every
subsequent feature ``skipped``, and the artifact fields reflect the
last-good state.

Dispatch is a ``type → handler`` registry (:data:`FEATURE_HANDLERS`). Only
``sketch`` is registered in this slice; ``extrude`` plugs into the same
registry with BACKLOG #6. A feature that validates against the shared
``Feature`` union but has no registered handler is a per-feature
``feature_type_unsupported`` error — never a transport failure (§4.3: the
py-kit error envelope is reserved for transport/validation failures of the
evaluation call itself, not for geometry outcomes).

A **sketch is not body-affecting** (§4.3): it only produces input geometry
for later features. With sketch-only dispatch no body ever exists, so an
evaluation honestly returns ``mesh_glb_id: null`` / ``properties: null``
while ``last_good_feature_id`` still names the last ``ok`` feature — exactly
the §6 failure-flavour shape. The content-addressed object-storage write
(§4.4) stays behind the :func:`store_mesh_glb` seam until a body-affecting
feature type registers.

Determinism (RESEARCH §9): evaluation order is the request list order, the
registry is consulted by key only (no iteration order participates), and the
solver backend is bitwise-deterministic — the same request yields an
identical result, including solved positions.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureData,
    FeatureError,
    FeatureRef,
    FeatureResult,
    SketchFeature,
    SolvedSketchData,
)

from geometry.sketch import (
    PlanegcsSketchSolver,
    SketchDefinitionError,
    SketchSolver,
    SolvedSketch,
)

#: The solver backend, typed as the protocol (RESEARCH §2 guardrail: callers
#: never import a solver package). ``PlanegcsSketchSolver`` is stateless —
#: every solve builds a fresh system — so one shared instance is safe.
_SOLVER: SketchSolver = PlanegcsSketchSolver()


@dataclass
class EvaluationState:
    """Mutable state threaded through one ordered dispatch pass.

    ``solved_sketches`` is keyed by feature id and insertion-ordered by
    evaluation order (deterministic). The extrude handler (BACKLOG #6) reads
    its profile from here and adds body tracking (current solid, last-good
    body) when it registers — no body-affecting feature type exists yet, so
    no body fields are defined now.
    """

    linear_deflection: float
    solved_sketches: dict[uuid.UUID, SolvedSketch] = field(
        default_factory=dict[uuid.UUID, SolvedSketch]
    )


#: One feature handler: evaluate the item, record outputs on ``state``, and
#: return ``None`` on success or the per-feature error (§4.3). Geometry
#: outcomes are values, never exceptions.
FeatureHandler = Callable[[EvaluatedFeatureInput, EvaluationState], FeatureError | None]


def _evaluate_sketch(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Solve one sketch feature (not body-affecting, §4.3).

    Solver *outcomes* follow the ``SketchSolver`` contract: statuses that
    carry a solved model (converged / underconstrained / consistent
    overconstrained) are ``ok`` — the diagnosis rides in the solved payload
    for the sketcher UI (§7.10) — while statuses with no usable solution
    (conflicting / diverged) map to per-feature errors, never exceptions.
    """
    feature = item.feature
    assert isinstance(feature, SketchFeature), "registry dispatches on type='sketch'"

    plane = feature.params.plane
    if isinstance(plane, FeatureRef):
        # v1 sketches sit on datum planes only (§2.1); no feature type
        # produces a sketchable plane yet. Documents rejects this at write
        # time — geometry re-checks because it must not trust its callers
        # for correctness.
        return FeatureError(
            code="reference_unresolved",
            message=(
                "Sketch planes must be datum planes (XY/XZ/YZ) in v1; the "
                "referenced feature does not provide a sketch plane."
            ),
            upstream_feature_id=plane.feature_id,
        )

    try:
        # SketchParamsV1 extends SketchDefinition (py-kit): the validated
        # params ARE the solver input — statically-malformed sketches never
        # reach this point, they are 422 request-validation failures (§4.3:
        # the envelope owns transport/validation failures of the call).
        solved = _SOLVER.solve(feature.params)
    except SketchDefinitionError as exc:
        # Malformed definition (bad reference, wrong point name, degenerate
        # geometry) — same failure class as a validation error.
        return FeatureError(code="sketch_invalid", message=str(exc))

    if solved.status == "conflicting":
        return FeatureError(
            code="sketch_conflicting",
            message=(
                "Sketch constraints are mutually unsatisfiable (conflicting "
                f"constraint indices: {solved.conflicting_constraints})."
            ),
        )
    if solved.status == "diverged":
        return FeatureError(
            code="sketch_diverged",
            message=(
                "Sketch solve did not converge and no conflict was diagnosed; "
                "check for degenerate geometry or a bad starting position."
            ),
        )

    state.solved_sketches[item.id] = solved
    return None


#: The dispatcher registry (§4): feature ``type`` discriminator → handler.
#: ``extrude`` registers here with BACKLOG #6 — same framework, no new
#: plumbing. Consulted by key only; no iteration order participates
#: (RESEARCH §9 determinism).
FEATURE_HANDLERS: dict[str, FeatureHandler] = {
    "sketch": _evaluate_sketch,
}


def store_mesh_glb(glb: bytes) -> str:
    """SEAM — content-addressed object-storage write (design §4.4, §7.9).

    Returns the storage key for ``EvaluateTreeResult.mesh_glb_id``.
    Unreachable in this slice: no registered feature type is body-affecting
    (§4.3), so no evaluation ever produces a body to tessellate and store.
    Implemented together with the first body-affecting feature (extrude,
    BACKLOG #6) once the client mesh-delivery decision (§7.8) fixes the
    storage posture.
    """
    raise NotImplementedError(
        "object-storage mesh write lands with the first body-affecting "
        "feature (extrude, BACKLOG #6; design feature-tree.md §4.4/§7.8)"
    )


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
    return SolvedSketchData.model_validate(solved.model_dump())


@dataclass
class TreeEvaluation:
    """A full evaluation: the boundary DTO plus service-internal payloads.

    ``result`` is everything that crosses the service boundary — including
    the per-feature solved-sketch payloads on ``FeatureResult.data`` (§7.10,
    lifted by BACKLOG #3). ``solved_sketches`` (``ok`` sketch features only,
    evaluation order) stays exposed service-internally as typed solver
    output: the extrude handler (BACKLOG #6) reads its profile from here.
    """

    result: EvaluateTreeResult
    solved_sketches: dict[uuid.UUID, SolvedSketch]


def evaluate_tree(request: EvaluateTreeRequest) -> TreeEvaluation:
    """Evaluate an ordered feature prefix under the strict-prefix rule (§4.3).

    Deterministic: same request → identical statuses, identical solved
    positions (RESEARCH §9). Never raises for geometry outcomes.
    """
    state = EvaluationState(linear_deflection=request.linear_deflection)
    results: list[FeatureResult] = []
    last_good_feature_id: uuid.UUID | None = None
    failed = False

    for item in request.features:
        if failed:
            results.append(FeatureResult(feature_id=item.id, status="skipped"))
            continue
        error = _dispatch(item, state)
        if error is None:
            results.append(
                FeatureResult(
                    feature_id=item.id,
                    status="ok",
                    data=_feature_data(item.id, state),
                )
            )
            last_good_feature_id = item.id
        else:
            results.append(
                FeatureResult(feature_id=item.id, status="error", error=error)
            )
            failed = True

    # §4.4 artifact fields: when a body-affecting feature type registers
    # (extrude, BACKLOG #6), the last-good body is tessellated here and
    # written through store_mesh_glb(). With sketch-only dispatch no body
    # ever exists, so null is the honest, spec-consistent value — the §6
    # failure flavour shows exactly this shape (mesh_glb_id: null,
    # properties: null, last_good_feature_id still set).
    return TreeEvaluation(
        result=EvaluateTreeResult(
            part_id=request.part_id,
            tree_version=request.tree_version,
            features=results,
            mesh_glb_id=None,
            properties=None,
            last_good_feature_id=last_good_feature_id,
        ),
        solved_sketches=state.solved_sketches,
    )
