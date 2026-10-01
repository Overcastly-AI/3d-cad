"""Sketch-based solids: extrude (add and cut), revolve, sweep and loft.

Each builds a tool solid from solved sketch geometry and applies it through the
shared body ops of :mod:`geometry.features.state`: the merge-aware add, or a cut
of the active body.
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

import uuid

from build123d import Face, Plane, Solid, Vertex, Wire
from loft_wire.features import (
    EvaluatedFeatureInput,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureError,
    FeatureRef,
    LoftFeature,
    RevolveFeature,
    SweepFeature,
    SweepParamsV1,
)
from loft_wire.sketch import Point2D

from geometry.features.datum_sketch import (
    _profile_build_error,
    _resolve_profile_face,
    _resolve_profile_faces,
    _resolve_solved_profile,
)
from geometry.features.naming_hooks import prism_names, swept_names
from geometry.features.state import (
    EvaluationState,
    _add_body,
    _cut_active,
)
from geometry.kernel import (
    AxisIntersectsProfileError,
    AxisNotInSketchPlaneError,
    BooleanError,
    CutRemovedNothingError,
    LoftError,
    NoAxisError,
    PathClosedError,
    PathEmptyError,
    PathNotConnectedError,
    ProfileNotClosedError,
    ProfileUnsupportedError,
    RevolveError,
    SweepError,
    TwistError,
    TwistPathError,
    build_loft_section,
    build_path_wire,
    build_revolve_profile_face,
    check_axis_clears_profile,
    combine_body,
    extrude_face,
    loft_sections,
    resolve_revolve_axis,
    revolve_face,
    sweep_profile,
    twisted_extrude_face,
    twisted_sweep_face,
)
from geometry.kernel.naming import NameHook, OpHistory


def _evaluate_extrude(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Extrude an earlier sketch's profile and boolean it against the body.

    The first **body-affecting** handler (§4.3): profile → closed-wire check
    → prism along the sketch plane normal (``direction: normal|reverse``) →
    ``add``/``cut`` against the prior body. Kernel failures surface as the
    design's error codes (``profile_not_closed``, ``boolean_failed``, …),
    pinned to this feature; the active body is only replaced on success.
    """
    feature = item.feature
    assert isinstance(feature, ExtrudeFeature), "registry dispatches on type='extrude'"
    params = feature.params
    reverse = params.direction == "reverse"

    if params.operation == "cut":
        return _evaluate_extrude_cut(item.id, params, state, reverse)

    # ADD: a single closed region (one loop, or one outer boundary + interior
    # holes). N disjoint loops would be N separate solids — multi-body, which
    # Loft does NOT support — so build_profile_face keeps rejecting them as
    # ``profile_unsupported``; the multi-region relaxation is CUT-only below.
    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, solved = resolved

    history = OpHistory()
    tool = _extrude_tool(face, plane, params, reverse, history)
    if isinstance(tool, FeatureError):
        return tool
    generated = prism_names(item.id, history, plane, solved.entities, region=False)
    return _add_body(item, state, tool, merge=params.merge, generated=generated)


def _extrude_tool(
    face: Face,
    plane: Plane,
    params: ExtrudeParamsV1,
    reverse: bool,
    history: OpHistory | None = None,
) -> Solid | FeatureError:
    """The solid one profile region sweeps to: a prism, or a twisted prism.

    THE single branch point between the straight and the twisted extrude, shared
    by the ADD and CUT paths so they can never disagree on it. No twist (the
    field absent, or ``0``) takes :func:`extrude_face` exactly as before, so an
    untwisted extrude is byte-identical to one built before the twist existed.
    A nonzero twist takes :func:`twisted_extrude_face`
    (docs/design/twisted-extrude.md); its refusal is ``twist_failed``. Only the
    straight prism fills *history* (the twisted one has no naming hook yet).
    """
    if not params.is_twisted:
        return extrude_face(face, plane, params.distance_mm, reverse, history=history)
    assert params.twist_angle_deg is not None  # is_twisted implies a value
    try:
        return twisted_extrude_face(
            face,
            plane,
            params.distance_mm,
            reverse,
            params.twist_angle_deg,
            params.twist_center or Point2D(x=0.0, y=0.0),
        )
    except TwistError as exc:
        return FeatureError(code="twist_failed", message=str(exc))


def _evaluate_extrude_cut(
    feature_id: uuid.UUID,
    params: ExtrudeParamsV1,
    state: EvaluationState,
    reverse: bool,
) -> FeatureError | None:
    """Subtract one OR MORE disjoint profile regions from the body (§4.3).

    The CUT branch of :func:`_evaluate_extrude`: N disjoint closed loops resolve
    to N independent removal regions (showcase F2 — a ring of lightening holes
    cut in one feature), each prism-extruded and cut from the running body in a
    deterministic order (:func:`build_profile_faces` sorts the regions). A
    single-region sketch resolves to exactly one tool, byte-identical to the
    former single-cut path (plate-with-holes cut unchanged). Cutting A then B is
    the same removal as cutting their union, and each step reuses
    :func:`combine_body`'s single-solid body-chain guarantee (design §7.6);
    the active body is only replaced once every region cuts cleanly, preserving
    last-good semantics on a mid-cut failure.

    On success the region prisms are RECORDED as this feature's removal tools
    (:meth:`EvaluationState.record_cut_tools`) so a later mirror / pattern
    replicates the exact solids that were cut — the same posture the Hole has had
    since FINDINGS #1, and what makes an intervening feature unable to shadow the
    removal (CM-1).
    """
    resolved = _resolve_profile_faces(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    faces, plane = resolved
    solved = state.solved_sketches[params.profile.feature_id]

    body = state.active_body
    if body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive extrude first."
            ),
        )

    tools: list[Solid] = []
    generated: list[tuple[Face, str | None]] = []
    for face in faces:
        history = OpHistory()
        tool = _extrude_tool(face, plane, params, reverse, history)
        if isinstance(tool, FeatureError):
            return tool
        tools.append(tool)
        generated.extend(
            prism_names(
                feature_id, history, plane, solved.entities, region=len(faces) > 1
            )
        )
    try:
        for tool in tools:
            body = combine_body(body, tool, "cut")
    except CutRemovedNothingError as exc:
        return FeatureError(code="cut_removed_nothing", message=str(exc))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    state.set_active_body(body, generated)
    state.record_cut_tools(feature_id, tools)
    state.record_feature_tools(feature_id, "cut", list(tools), generated)
    return None


def _evaluate_revolve(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Revolve an earlier sketch's profile about a sketch-plane axis (§4.3).

    The revolve sibling of :func:`_evaluate_extrude`: it shares the profile
    resolution + closed-wire check (:func:`_resolve_profile_face`) and the
    ``add``/``cut`` boolean (:func:`combine_body`), swapping the linear prism
    for a swept revolution. The axis is a LINE entity of the SAME sketch or a
    world ORIGIN axis (REVOLVE-1); :func:`resolve_revolve_axis` reduces either
    to one sketch-plane line, so everything after it is axis-kind-agnostic.
    Kernel failures surface as design error codes pinned to this feature —
    ``profile_not_closed``/``profile_unsupported`` (upstream sketch),
    ``no_axis`` (bad axis reference), ``axis_not_in_sketch_plane`` (a world axis
    that is not in the profile's plane, so the revolution would not sweep the
    profile's own cross-section), ``axis_intersects_profile`` (the axis crosses
    the profile → self-intersecting body), ``no_prior_body`` (cut with nothing
    to cut), ``revolve_failed``, ``boolean_failed``. the active body is
    only replaced on success (strict-prefix rule tessellates the last-good
    body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, RevolveFeature), "registry dispatches on type='revolve'"
    params = feature.params

    # Resolve the solved sketch, then the axis, THEN build the profile face:
    # the axis is resolved first so a construction centerline can close a
    # half-profile open only along the axis (build_revolve_profile_face), the
    # natural SolidWorks/Fusion idiom. A profile already closed by real edges
    # (offset washer, real on-axis edge) builds byte-identically.
    resolved = _resolve_solved_profile(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    plane, solved = resolved

    try:
        axis = resolve_revolve_axis(params.axis, plane, solved.entities)
    except NoAxisError as exc:
        return FeatureError(
            code="no_axis",
            message=str(exc),
            upstream_feature_id=params.profile.feature_id,
        )
    except AxisNotInSketchPlaneError as exc:
        return FeatureError(
            code="axis_not_in_sketch_plane",
            message=str(exc),
            upstream_feature_id=params.profile.feature_id,
        )

    try:
        face = build_revolve_profile_face(plane, solved.entities, axis)
    except (ProfileNotClosedError, ProfileUnsupportedError) as exc:
        return _profile_build_error(exc, params.profile.feature_id)

    try:
        check_axis_clears_profile(axis, solved.entities)
    except AxisIntersectsProfileError as exc:
        return FeatureError(
            code="axis_intersects_profile",
            message=str(exc),
            upstream_feature_id=params.profile.feature_id,
        )

    if params.operation == "cut" and state.active_body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    history = OpHistory()
    try:
        tool = revolve_face(
            face,
            axis,
            plane,
            params.angle_deg,
            params.direction == "reverse",
            history=history,
        )
    except RevolveError as exc:
        return FeatureError(code="revolve_failed", message=str(exc))
    generated = swept_names(item.id, history, plane, solved.entities)

    if params.operation == "cut":
        return _cut_active(state, tool, feature_id=item.id, generated=generated)
    return _add_body(item, state, tool, merge=params.merge, generated=generated)


def _resolve_path_wire(path: FeatureRef, state: EvaluationState) -> Wire | FeatureError:
    """Resolve a sweep-path FeatureRef to its single OPEN path wire.

    The path sibling of :func:`_resolve_profile_face`: it re-checks the §2.2
    reference rule (documents enforces it at write time; geometry must not trust
    its callers), then assembles the open path wire through
    :func:`geometry.kernel.build_path_wire` (construction geometry excluded
    there, the shared per-entity edge builder). Every failure flavour is a
    per-feature error pinned to the upstream path sketch.
    """
    path_id = path.feature_id
    solved = state.solved_sketches.get(path_id)
    plane = state.sketch_planes.get(path_id)
    if solved is None or plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                "Path must reference an earlier successfully solved sketch "
                "feature of this tree."
            ),
            upstream_feature_id=path_id,
        )
    try:
        return build_path_wire(plane, solved.entities)
    except PathEmptyError as exc:
        return FeatureError(
            code="sweep_path_empty", message=str(exc), upstream_feature_id=path_id
        )
    except PathNotConnectedError as exc:
        return FeatureError(
            code="sweep_path_not_connected",
            message=str(exc),
            upstream_feature_id=path_id,
        )
    except PathClosedError as exc:
        return FeatureError(
            code="sweep_path_closed", message=str(exc), upstream_feature_id=path_id
        )


def _evaluate_sweep(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Sweep an earlier sketch's profile along an earlier sketch's path (§4.3).

    The first NON-PRISMATIC body-affecting handler: it shares extrude/revolve's
    profile resolution + closed-wire check (:func:`_resolve_profile_face`) and
    ``add``/``cut`` boolean (:func:`combine_body`), swapping the linear prism /
    revolution for a sweep along a SECOND sketch's open path wire
    (:func:`_resolve_path_wire`). Kernel failures surface as design error codes
    pinned to the failing feature — ``profile_not_closed``/``profile_unsupported``
    and ``reference_unresolved`` (upstream profile), ``sweep_path_empty``/
    ``sweep_path_not_connected``/``sweep_path_closed``/``reference_unresolved``
    (upstream path), ``no_prior_body`` (cut with nothing to cut),
    ``sweep_failed``, ``boolean_failed``. the active body is only replaced on
    success (strict-prefix rule tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, SweepFeature), "registry dispatches on type='sweep'"
    params = feature.params

    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, _ = resolved

    path = _resolve_path_wire(params.path, state)
    if isinstance(path, FeatureError):
        return path

    if params.operation == "cut" and state.active_body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    tool = _sweep_tool(face, plane, path, params)
    if isinstance(tool, FeatureError):
        return tool

    if params.operation == "cut":
        return _cut_active(state, tool, feature_id=item.id)
    return _add_body(item, state, tool, merge=params.merge)


def _sweep_tool(
    face: Face, plane: Plane, path: Wire, params: SweepParamsV1
) -> Solid | FeatureError:
    """The solid a sweep builds: a plain sweep, or one TWISTED along its path.

    THE single branch point for the sweep twist (TWIST-TO-SWEEP), shared by ADD
    and CUT. No twist (absent, or normalised away) takes :func:`sweep_profile`
    exactly as before, so every untwisted sweep is byte-identical to one built
    before the twist existed. A twist takes :func:`twisted_sweep_face`, which
    builds through the twisted extrude's own kernel call; a path it cannot twist
    exactly is ``twist_path_unsupported`` and a sweep it refuses is
    ``twist_failed`` (the extrude's code, the same kernel refusal).
    """
    if not params.is_twisted:
        try:
            return sweep_profile(face, path)
        except SweepError as exc:
            return FeatureError(code="sweep_failed", message=str(exc))
    assert params.twist_angle_deg is not None  # is_twisted implies a value
    try:
        return twisted_sweep_face(face, plane, path, params.twist_angle_deg)
    except TwistPathError as exc:
        return FeatureError(code="twist_path_unsupported", message=str(exc))
    except TwistError as exc:
        return FeatureError(code="twist_failed", message=str(exc))


def _resolve_loft_section(
    ref: FeatureRef, state: EvaluationState
) -> Wire | Vertex | FeatureError:
    """Resolve one loft-section FeatureRef to its closed wire or apex vertex.

    A per-section sibling of :func:`_resolve_profile_face`: it re-checks the
    §2.2 reference rule (documents enforces it at write time; geometry must not
    trust its callers), then builds the section through the shared
    :func:`geometry.kernel.build_loft_section` (construction geometry excluded,
    single-closed-loop check, or a single apex point). Every failure flavour is
    a per-feature error pinned to the upstream section sketch.
    """
    section_id = ref.feature_id
    solved = state.solved_sketches.get(section_id)
    plane = state.sketch_planes.get(section_id)
    if solved is None or plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                "Loft section must reference an earlier successfully solved "
                "sketch feature of this tree."
            ),
            upstream_feature_id=section_id,
        )
    try:
        return build_loft_section(plane, solved.entities)
    except ProfileNotClosedError as exc:
        return FeatureError(
            code="profile_not_closed", message=str(exc), upstream_feature_id=section_id
        )
    except ProfileUnsupportedError as exc:
        return FeatureError(
            code="profile_unsupported",
            message=str(exc),
            upstream_feature_id=section_id,
        )


def _evaluate_loft(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Blend a solid through two or more ordered section sketches (§4.3).

    The loft sibling of :func:`_evaluate_sweep` and the second non-prismatic
    handler: it resolves each ordered section (:func:`_resolve_loft_section` —
    a closed wire or an apex point, sharing extrude/sweep's closed-wire check)
    and ruled-lofts them (:func:`loft_sections`), then applies the SAME
    ``add``/``cut`` boolean (:func:`combine_body`). Kernel failures surface as
    design error codes pinned to the failing feature — ``profile_not_closed``/
    ``profile_unsupported``/``reference_unresolved`` (upstream section),
    ``no_prior_body`` (cut with nothing to cut), ``loft_failed`` (incompatible
    sections / not one solid), ``boolean_failed``. the active body is only
    replaced on success (strict-prefix rule tessellates the last-good body,
    §4.3). Fewer than 2 sections cannot reach here — ``LoftParamsV1`` enforces
    ``min_length=2`` at request validation (a clean 422, never a 500).
    """
    feature = item.feature
    assert isinstance(feature, LoftFeature), "registry dispatches on type='loft'"
    params = feature.params

    sections: list[Wire | Vertex] = []
    first_wire: uuid.UUID | None = None
    for ref in params.profiles:
        resolved = _resolve_loft_section(ref, state)
        if isinstance(resolved, FeatureError):
            return resolved
        sections.append(resolved)
        if first_wire is None and isinstance(resolved, Wire):
            first_wire = ref.feature_id

    if params.operation == "cut" and state.active_body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    history = OpHistory()
    try:
        tool = loft_sections(sections, history)
    except LoftError as exc:
        return FeatureError(code="loft_failed", message=str(exc))
    generated: NameHook = ()
    if first_wire is not None:
        generated = swept_names(
            item.id,
            history,
            state.sketch_planes[first_wire],
            state.solved_sketches[first_wire].entities,
            spans=len(sections) - 1,
        )

    if params.operation == "cut":
        return _cut_active(state, tool, feature_id=item.id, generated=generated)
    return _add_body(item, state, tool, merge=params.merge, generated=generated)
