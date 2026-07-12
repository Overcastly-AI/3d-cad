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

Dispatch is a ``type → handler`` registry (:data:`FEATURE_HANDLERS`):
``sketch`` (produces input geometry, not body-affecting), ``extrude`` (the
first **body-affecting** feature, §4.3 — mutates the part's single solid body
chain via add/cut booleans), ``revolve`` (sweeps a profile about a sketch-line
axis, sharing extrude's profile + boolean plumbing), ``fillet`` (rounds
selected edges of that body chain) and ``chamfer`` (bevels selected edges; both
body-affecting and both resolving edges through the shared geometric selector).
A feature that
validates against
the shared ``Feature`` union but has no registered handler is a per-feature
``feature_type_unsupported`` error — never a transport failure (§4.3: the
py-kit error envelope is reserved for transport/validation failures of the
evaluation call itself, not for geometry outcomes).

When the evaluated prefix ends with a body, the last-good body is measured
(GProp) and tessellated, and the GLB is stored content-addressed behind the
interim §7.8 seam (:mod:`geometry.mesh_store` — in-process LRU today, object
storage when the compose/queue item lands); ``mesh_glb_id`` carries the
content address either way. With no body-affecting feature ``ok``, the
artifact fields stay honestly ``null`` — exactly the §6 failure-flavour
shape.

Determinism (RESEARCH §9): evaluation order is the request list order, the
registry is consulted by key only (no iteration order participates), the
solver backend is bitwise-deterministic, and kernel builds/booleans are pure
functions of their inputs — the same request yields an identical result,
including ``mesh_glb_id`` (a content hash of a deterministic GLB).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from build123d import Face, Solid
from py_kit.errors import ValidationApiError
from py_kit.schemas.features import (
    ChamferFeature,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExtrudeFeature,
    FeatureData,
    FeatureError,
    FeatureRef,
    FeatureResult,
    FilletFeature,
    LinearPatternParamsV1,
    PatternFeature,
    RevolveFeature,
    SketchFeature,
    SolvedSketchData,
)
from py_kit.schemas.geometry import MeshStats, ShapeProperties

from geometry.kernel import (
    AxisIntersectsProfileError,
    BooleanError,
    ChamferError,
    FilletError,
    NoAxisError,
    NoEdgesSelectedError,
    PatternAngleError,
    PatternAxisError,
    PatternCountError,
    PatternDirectionError,
    PatternDisjointError,
    PatternError,
    PatternSpacingError,
    ProfileNotClosedError,
    ProfileUnsupportedError,
    RevolveError,
    build_profile_face,
    chamfer_body,
    check_axis_clears_profile,
    circular_pattern,
    combine_body,
    extrude_face,
    fillet_body,
    linear_pattern,
    measure_shape,
    resolve_axis_line,
    revolve_face,
    select_edges,
    tessellate_glb,
)
from geometry.mesh_store import store_mesh_glb
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

    ``solved_sketches``/``sketch_planes`` are keyed by feature id and
    insertion-ordered by evaluation order (deterministic); the extrude
    handler reads its profile from them. ``body`` is the part's single solid
    body chain (design §7.6) — a kernel type held strictly service-internal,
    mutated only by body-affecting handlers **on success** (so after a
    failure it is exactly the last-good body the strict-prefix rule
    tessellates, §4.3).
    """

    linear_deflection: float
    solved_sketches: dict[uuid.UUID, SolvedSketch] = field(
        default_factory=dict[uuid.UUID, SolvedSketch]
    )
    sketch_planes: dict[uuid.UUID, DatumPlaneRef] = field(
        default_factory=dict[uuid.UUID, DatumPlaneRef]
    )
    body: Solid | None = None


#: One feature handler: evaluate the item, record outputs on ``state``, and
#: return ``None`` on success or the per-feature error (§4.3). Geometry
#: outcomes are values, never exceptions. Handlers mutate ``state`` only on
#: the success path.
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
    state.sketch_planes[item.id] = plane
    return None


def _resolve_profile_face(
    profile: FeatureRef, state: EvaluationState
) -> tuple[Face, DatumPlaneRef, SolvedSketch] | FeatureError:
    """Resolve a profile FeatureRef to its ``(face, plane, solved sketch)``.

    The shared front half of every body-affecting feature that consumes a
    sketch profile (extrude, revolve — CLAUDE.md DRY rule): it re-checks the
    §2.2 reference rule (documents enforces it at write time; geometry must not
    trust its callers), then builds the single closed profile face through the
    shared :func:`build_profile_face` (construction geometry excluded there).
    Both failure flavours are returned as per-feature errors pinned to the
    upstream sketch, so the caller just propagates them.
    """
    profile_id = profile.feature_id
    solved = state.solved_sketches.get(profile_id)
    plane = state.sketch_planes.get(profile_id)
    if solved is None or plane is None:
        # Anything not an ok sketch of this prefix (unknown id, non-sketch
        # feature, or a sketch the strict-prefix rule never reached) resolves
        # to nothing.
        return FeatureError(
            code="reference_unresolved",
            message=(
                "Profile must reference an earlier successfully solved sketch "
                "feature of this tree."
            ),
            upstream_feature_id=profile_id,
        )
    try:
        face = build_profile_face(plane.plane, solved.entities)
    except ProfileNotClosedError as exc:
        return FeatureError(
            code="profile_not_closed", message=str(exc), upstream_feature_id=profile_id
        )
    except ProfileUnsupportedError as exc:
        return FeatureError(
            code="profile_unsupported",
            message=str(exc),
            upstream_feature_id=profile_id,
        )
    return face, plane, solved


def _evaluate_extrude(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Extrude an earlier sketch's profile and boolean it against the body.

    The first **body-affecting** handler (§4.3): profile → closed-wire check
    → prism along the sketch plane normal (``direction: normal|reverse``) →
    ``add``/``cut`` against the prior body. Kernel failures surface as the
    design's error codes (``profile_not_closed``, ``boolean_failed``, …),
    pinned to this feature; ``state.body`` is only replaced on success.
    """
    feature = item.feature
    assert isinstance(feature, ExtrudeFeature), "registry dispatches on type='extrude'"
    params = feature.params

    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, _ = resolved

    if params.operation == "cut" and state.body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive extrude first."
            ),
        )

    tool = extrude_face(
        face, plane.plane, params.distance_mm, params.direction == "reverse"
    )
    try:
        state.body = combine_body(state.body, tool, params.operation)
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    return None


def _evaluate_revolve(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Revolve an earlier sketch's profile about a sketch-line axis (§4.3).

    The revolve sibling of :func:`_evaluate_extrude`: it shares the profile
    resolution + closed-wire check (:func:`_resolve_profile_face`) and the
    ``add``/``cut`` boolean (:func:`combine_body`), swapping the linear prism
    for a swept revolution about a LINE entity of the SAME sketch. Kernel
    failures surface as design error codes pinned to this feature —
    ``profile_not_closed``/``profile_unsupported`` (upstream sketch),
    ``no_axis`` (bad axis reference), ``axis_intersects_profile`` (the axis
    crosses the profile → self-intersecting body), ``no_prior_body`` (cut with
    nothing to cut), ``revolve_failed``, ``boolean_failed``. ``state.body`` is
    only replaced on success (strict-prefix rule tessellates the last-good
    body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, RevolveFeature), "registry dispatches on type='revolve'"
    params = feature.params

    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, solved = resolved

    try:
        axis_line = resolve_axis_line(solved.entities, params.axis.entity)
        check_axis_clears_profile(axis_line, solved.entities)
    except NoAxisError as exc:
        return FeatureError(
            code="no_axis",
            message=str(exc),
            upstream_feature_id=params.profile.feature_id,
        )
    except AxisIntersectsProfileError as exc:
        return FeatureError(
            code="axis_intersects_profile",
            message=str(exc),
            upstream_feature_id=params.profile.feature_id,
        )

    if params.operation == "cut" and state.body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    try:
        tool = revolve_face(
            face,
            axis_line,
            plane.plane,
            params.angle_deg,
            params.direction == "reverse",
        )
    except RevolveError as exc:
        return FeatureError(code="revolve_failed", message=str(exc))

    try:
        state.body = combine_body(state.body, tool, params.operation)
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    return None


def _evaluate_fillet(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Round selected edges of the current body chain (body-affecting, §4.3).

    Fillet operates on the implicit single body (design §7.6), so it needs a
    prior body-affecting feature (``no_target_body`` otherwise). Edges are
    resolved by the geometric selector (design §2.4 — NOT topological naming):
    an empty match is ``no_fillet_edges``; a kernel failure is
    ``fillet_failed``. ``state.body`` is only replaced on success (strict-prefix
    rule tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, FilletFeature), "registry dispatches on type='fillet'"
    params = feature.params

    if state.body is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Fillet requires an existing body, but no body-affecting "
                "feature precedes this one; add an extrude first."
            ),
        )

    try:
        edges = select_edges(state.body, params.edges)
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_fillet_edges", message=str(exc))

    try:
        state.body = fillet_body(state.body, edges, params.radius_mm)
    except FilletError as exc:
        return FeatureError(code="fillet_failed", message=str(exc))
    return None


def _evaluate_chamfer(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Bevel selected edges of the current body chain (body-affecting, §4.3).

    The chamfer sibling of :func:`_evaluate_fillet` — same shape, same edge
    plumbing (:func:`select_edges`, design §2.4), same single-body requirement
    (``no_target_body`` otherwise, design §7.6). An empty match is
    ``no_chamfer_edges``; a kernel failure is ``chamfer_failed``. ``state.body``
    is only replaced on success (strict-prefix rule tessellates the last-good
    body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, ChamferFeature), "registry dispatches on type='chamfer'"
    params = feature.params

    if state.body is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Chamfer requires an existing body, but no body-affecting "
                "feature precedes this one; add an extrude first."
            ),
        )

    try:
        edges = select_edges(state.body, params.edges)
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_chamfer_edges", message=str(exc))

    try:
        state.body = chamfer_body(state.body, edges, params.distance_mm)
    except ChamferError as exc:
        return FeatureError(code="chamfer_failed", message=str(exc))
    return None


def _evaluate_pattern(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Replicate the current body into a linear row / circular ring (§4.3).

    v1 DESIGN DECISION (option B, docs/GEOMETRY-QA.md): a pattern arrays the
    CURRENT single body — everything modelled so far — and unions the copies
    into the body chain (design §7.6). It operates on the implicit body about
    world-space direction/axis vectors (no picked sub-geometry — independent of
    topological naming, #1), so like fillet/chamfer it needs a prior
    body-affecting feature (``no_target_body`` otherwise). Every pattern value
    is validated in :mod:`geometry.kernel.pattern` and mapped 1:1 to a
    per-feature ``pattern_*`` code — bad count/spacing/direction/axis/angle,
    ``pattern_disjoint`` (instances do not merge into one solid), or the kernel
    ``pattern_failed``. ``state.body`` is only replaced on success (strict-prefix
    rule tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, PatternFeature), "registry dispatches on type='pattern'"

    if state.body is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Pattern requires an existing body, but no body-affecting "
                "feature precedes this one; add a feature that creates a body "
                "first."
            ),
        )

    geometry = feature.params.pattern
    try:
        if isinstance(geometry, LinearPatternParamsV1):
            state.body = linear_pattern(
                state.body,
                (geometry.direction.x, geometry.direction.y, geometry.direction.z),
                geometry.spacing_mm,
                geometry.count,
            )
        else:
            state.body = circular_pattern(
                state.body,
                (geometry.axis_point.x, geometry.axis_point.y, geometry.axis_point.z),
                (
                    geometry.axis_direction.x,
                    geometry.axis_direction.y,
                    geometry.axis_direction.z,
                ),
                geometry.angle_deg,
                geometry.count,
            )
    except PatternCountError as exc:
        return FeatureError(code="pattern_bad_count", message=str(exc))
    except PatternSpacingError as exc:
        return FeatureError(code="pattern_bad_spacing", message=str(exc))
    except PatternDirectionError as exc:
        return FeatureError(code="pattern_bad_direction", message=str(exc))
    except PatternAxisError as exc:
        return FeatureError(code="pattern_bad_axis", message=str(exc))
    except PatternAngleError as exc:
        return FeatureError(code="pattern_bad_angle", message=str(exc))
    except PatternDisjointError as exc:
        return FeatureError(code="pattern_disjoint", message=str(exc))
    except PatternError as exc:
        return FeatureError(code="pattern_failed", message=str(exc))
    return None


#: The dispatcher registry (§4): feature ``type`` discriminator → handler.
#: Consulted by key only; no iteration order participates (RESEARCH §9
#: determinism). New feature types plug in here.
FEATURE_HANDLERS: dict[str, FeatureHandler] = {
    "sketch": _evaluate_sketch,
    "extrude": _evaluate_extrude,
    "revolve": _evaluate_revolve,
    "fillet": _evaluate_fillet,
    "chamfer": _evaluate_chamfer,
    "pattern": _evaluate_pattern,
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
    the per-feature solved-sketch payloads on ``FeatureResult.data`` (§7.10)
    and the content-addressed ``mesh_glb_id``. The remaining fields are
    strictly service-internal (used by the golden harness and future
    callers inside this service): ``solved_sketches`` (``ok`` sketch
    features only, evaluation order), ``body`` (the last-good kernel solid —
    never serialized), and the tessellation artifact ``glb``/``mesh`` that
    ``mesh_glb_id`` addresses.
    """

    result: EvaluateTreeResult
    solved_sketches: dict[uuid.UUID, SolvedSketch]
    body: Solid | None = None
    glb: bytes | None = None
    mesh: MeshStats | None = None


def tree_no_body_error(
    result: EvaluateTreeResult, *, code: str, action: str
) -> ValidationApiError:
    """A clean 422 for a tree that produced no body (never a 500).

    Shared (CLAUDE.md DRY rule) by every endpoint that needs the last-good
    body of an evaluated tree — export and measure today. Reuses the
    strict-prefix ``FeatureError`` semantics (§4.3): if a feature failed, its
    code/message/upstream id ride in the envelope ``details`` so the caller
    learns exactly why (e.g. ``profile_not_closed``); a tree with no
    body-affecting feature at all is the honest ``no_body`` case. *action* is
    the verb the message uses ("export", "measure").
    """
    failed = next(
        (feature for feature in result.features if feature.status == "error"), None
    )
    if failed is not None and failed.error is not None:
        return ValidationApiError(
            "The feature tree could not be evaluated to a body, so there is "
            f"nothing to {action}.",
            code=code,
            details={
                "feature_id": str(failed.feature_id),
                "feature_error": failed.error.model_dump(mode="json"),
            },
        )
    return ValidationApiError(
        "The feature tree evaluated with no body-affecting feature, so there "
        f"is nothing to {action}; add an extrude first.",
        code=code,
        details={"reason": "no_body"},
    )


def evaluate_tree(request: EvaluateTreeRequest) -> TreeEvaluation:
    """Evaluate an ordered feature prefix under the strict-prefix rule (§4.3).

    Deterministic: same request → identical statuses, identical solved
    positions, byte-identical GLB and therefore identical ``mesh_glb_id``
    (RESEARCH §9). Never raises for geometry outcomes.
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

    # §4.3/§4.4 artifact fields: the LAST-GOOD body — handlers mutate
    # state.body only on success, so even after a mid-tree failure this is
    # the state after the last ok body-affecting feature ("the viewport
    # always has something honest to show"). No body (sketch-only tree, or
    # the first extrude failed) → honestly null, the §6 failure flavour.
    properties: ShapeProperties | None = None
    mesh_glb_id: str | None = None
    glb: bytes | None = None
    mesh: MeshStats | None = None
    if state.body is not None:
        properties = measure_shape(state.body)
        glb, mesh = tessellate_glb(state.body, request.linear_deflection)
        mesh_glb_id = store_mesh_glb(glb)

    return TreeEvaluation(
        result=EvaluateTreeResult(
            part_id=request.part_id,
            tree_version=request.tree_version,
            features=results,
            mesh_glb_id=mesh_glb_id,
            properties=properties,
            last_good_feature_id=last_good_feature_id,
        ),
        solved_sketches=state.solved_sketches,
        body=state.body,
        glb=glb,
        mesh=mesh,
    )
