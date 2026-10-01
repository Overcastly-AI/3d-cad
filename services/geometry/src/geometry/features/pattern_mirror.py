"""Pattern (linear and circular) and mirror, in their ``body`` and ``features``
scopes.

Both replicate material already in the tree. The ``body`` scope works from the
active body plus the recorded cut tools, read under two different documented
rules (:func:`_pattern_cut_tools`, :func:`_mirror_cut_tools`); the ``features``
scope replays the per-feature tool records (docs/design/mirror-semantics.md,
docs/design/pattern-scope.md).
"""

import uuid
from collections.abc import Sequence

from build123d import Plane, Solid
from loft_wire.features import (
    CircularPatternParamsV1,
    EvaluatedFeatureInput,
    FeatureError,
    FeatureRef,
    LinearPatternParamsV1,
    MirrorFeature,
    MirrorFeaturesScope,
    PatternFeature,
    PatternFeaturesScope,
    PatternGeometry,
)

from geometry.features.datum_sketch import (
    resolve_sketch_plane,
)
from geometry.features.state import (
    EvaluationState,
    RecordedToolGroup,
)
from geometry.kernel import (
    MirrorError,
    MirrorUnreachableError,
    PatternAngleError,
    PatternAxisError,
    PatternCountError,
    PatternDirectionError,
    PatternDisjointError,
    PatternError,
    PatternSpacingError,
    PatternUnreachableError,
    check_pattern_count,
    circular_pattern,
    circular_pattern_cut,
    circular_pattern_placements,
    cut_placed_tools,
    cut_reflected_tools,
    fuse_placed_tools,
    fuse_reflected_tools,
    linear_pattern,
    linear_pattern_cut,
    linear_pattern_placements,
    mirror_cut,
    mirror_union,
    reflect_tools,
    removal_reaches_body,
)
from geometry.kernel.types import BodyShape


def _recorded_cut_tools(state: EvaluationState) -> list[Solid] | None:
    """:attr:`~EvaluationState.last_cut_tools`, but only while they still APPLY.

    The shared read both replication rules below start from: the recorded tools are
    offered only when the body they were cut from is still the active body (§MB-0),
    so a pocket in body A can never be reflected/arrayed into body B. ``None``
    otherwise — the caller replicates whole-body copies.
    """
    if state.last_cut_tools is None or state.last_cut_body_id != state.active_body_id:
        return None
    return state.last_cut_tools


def _pattern_cut_tools(state: EvaluationState) -> list[Solid] | None:
    """The tools a PATTERN should array, or ``None`` for whole-body copies.

    The pattern's source inference (BACKLOG #3, option a — reviewed and LOCKED):
    the source is the IMMEDIATELY-preceding body-affecting feature, so a pattern
    arrays a removal only when that feature is the cut which recorded the tools.
    Any other predecessor — an add (a boss), a fillet, an intervening modifier —
    means "array the body-so-far", which is a legitimate and useful reading and is
    guarded by ``test_add_pattern_after_a_cut_hole_still_unions_whole_body`` and
    ``test_pattern_after_an_intervening_fillet_unions_whole_body_not_recut``.

    Deliberately NOT the mirror's rule (:func:`_mirror_cut_tools`): the two verbs
    ask different questions of the same recorded tools. Shadowing costs a pattern
    only a less useful reading; it cost the mirror EXISTING GEOMETRY (CM-1).
    """
    if state.last_cut_feature_id != state.prev_body_feature_id:
        return None
    return _recorded_cut_tools(state)


def _mirror_cut_tools(state: EvaluationState) -> list[Solid] | None:
    """The tools a MIRROR should reflect, or ``None`` for reflect-and-union.

    The MOST RECENT cut of this body, however many non-cut features sit between it
    and the mirror (CM-1 fix, 2026-07-25). The mirror cannot use the pattern's
    immediate-predecessor rule, because the fallback is not merely less useful — it
    is DESTRUCTIVE: ``mirror_union`` reflects the whole body and fuses it, so the
    reflection's material FILLS the existing void, and a hole drilled before an
    unrelated chamfer/fillet/boss silently disappeared (the FINDINGS #2
    featureless-brick symptom, measured 31640.0 mm^3 vs 29629.3807 correct, with no
    cylindrical face left in the topology).

    Reflecting the most recent cut is the consistent generalisation of the LOCKED
    v1 semantic "a mirror reflects that removal" (``mirror_cut``): the cut path
    never unions material, so EVERY earlier void survives untouched — which is what
    keeps ``test_mirror_preserves_a_cut_that_precedes_the_mirrored_one`` (29600.0,
    pocket A preserved) green, and why the tempting "union then re-subtract both
    tool sets" alternative is still rejected (it welds pocket A shut at 30400.0).
    What v1 does NOT do is reflect an intervening ADD's material: a boss added
    after the cut is not duplicated (documented limit, GEOMETRY-QA 2026-07-25 —
    mirroring a SELECTED SET of features is the incumbent semantic and a v2 item).
    """
    return _recorded_cut_tools(state)


def _apply_pattern(
    body: BodyShape, geometry: PatternGeometry, tools: list[Solid] | None
) -> BodyShape:
    """Dispatch one pattern to its kernel op (linear/circular x union/cut).

    ``tools is None`` selects the ADD (union whole-body copies) path — the
    original behavior, byte-identical; a tool list selects the CUT path
    (BACKLOG #3). Kept as one funnel so both geometry kinds share the one
    ``pattern_*`` error mapping in :func:`_evaluate_pattern`.
    """
    if isinstance(geometry, LinearPatternParamsV1):
        direction = (geometry.direction.x, geometry.direction.y, geometry.direction.z)
        if tools is not None:
            return linear_pattern_cut(
                body, tools, direction, geometry.spacing_mm, geometry.count
            )
        return linear_pattern(body, direction, geometry.spacing_mm, geometry.count)

    assert isinstance(geometry, CircularPatternParamsV1)  # closed union
    axis_point = (geometry.axis_point.x, geometry.axis_point.y, geometry.axis_point.z)
    axis_direction = (
        geometry.axis_direction.x,
        geometry.axis_direction.y,
        geometry.axis_direction.z,
    )
    if tools is not None:
        return circular_pattern_cut(
            body, tools, axis_point, axis_direction, geometry.angle_deg, geometry.count
        )
    return circular_pattern(
        body, axis_point, axis_direction, geometry.angle_deg, geometry.count
    )


def _pattern_placements(
    sources: list[BodyShape], geometry: PatternGeometry
) -> list[BodyShape]:
    """The ``k = 1..count-1`` placements of *sources* — the SAME kernel helpers
    :func:`_apply_pattern`'s ops use internally (CLAUDE.md DRY), so a recorded
    contribution can never drift from what the pattern applied."""
    if isinstance(geometry, LinearPatternParamsV1):
        direction = (geometry.direction.x, geometry.direction.y, geometry.direction.z)
        return linear_pattern_placements(
            sources, direction, geometry.spacing_mm, geometry.count
        )
    assert isinstance(geometry, CircularPatternParamsV1)  # closed union
    axis_point = (geometry.axis_point.x, geometry.axis_point.y, geometry.axis_point.z)
    axis_direction = (
        geometry.axis_direction.x,
        geometry.axis_direction.y,
        geometry.axis_direction.z,
    )
    return circular_pattern_placements(
        sources, axis_point, axis_direction, geometry.angle_deg, geometry.count
    )


def _pattern_contribution(
    body: BodyShape, geometry: PatternGeometry, tools: list[Solid] | None
) -> RecordedToolGroup:
    """What a SUCCEEDED pattern contributed, as one reflectable group (§4.5).

    A pattern's contribution is its ``count - 1`` PLACED rigid instances — placed
    tool copies (cut) or placed whole-body copies (add). Recording and reflecting
    those PLACEMENTS, rather than the pattern's parameters, is what makes a
    reflected CIRCULAR pattern correct: a reflection reverses handedness, so a
    re-derived ring with the same positive ``angle_deg`` about the reflected axis
    would wind backwards (mirror-semantics §4.5). ``count == 1`` yields an empty
    group — a no-op pattern contributed nothing to reflect.

    Mirrors :func:`_apply_pattern`'s branch structure including its vacuous-cut
    FALLBACK: when no placed tool copy can reach the body the kernel replicated the
    WHOLE body instead, so the contribution is those body copies under ``fuse``.
    Called only after the pattern succeeded, so the shared validation inside the
    placement helpers cannot raise here. Locked against drift by
    ``test_recorded_pattern_contribution_reproduces_the_pattern``.
    """
    if tools is not None:
        cut_copies = _pattern_placements(list(tools), geometry)
        if cut_copies and removal_reaches_body(body, cut_copies):
            return RecordedToolGroup("cut", cut_copies)
    return RecordedToolGroup("fuse", _pattern_placements([body], geometry))


def _pattern_count(geometry: PatternGeometry) -> int:
    """The pattern's TOTAL instance count, whichever geometry kind it is.

    Only the error messages of :func:`cut_placed_tools` / :func:`fuse_placed_tools`
    need it; both members carry ``count``, so this is the one place that says so.
    """
    return geometry.count


def _evaluate_pattern_features(
    scope: PatternFeaturesScope,
    state: EvaluationState,
    active: BodyShape,
    geometry: PatternGeometry,
) -> FeatureError | list[RecordedToolGroup]:
    """Repeat the RECORDED TOOLS of an explicit feature selection (v2, §3).

    The v2 mechanism, and deliberately the mirror's mechanism with ``place``
    substituted for ``reflect`` (docs/design/pattern-scope.md §3, the sibling of
    mirror-semantics §4): for each selected feature in TREE order (§6), take the
    rigid tool solid(s) it recorded at its OWN evaluation, place a copy of each at
    this pattern's ``k = 1 .. count-1`` placements, and re-apply THAT feature's own
    boolean — ``fuse`` for an additive contributor, ``cut`` for a subtractive one.
    Parameters are never re-derived, and the placements come from the SAME kernel
    helpers the ``body`` path calls, so what a selection repeats can never drift
    from what a pattern applies.

    This is where §1's coin flip dies. Neither inference of the v1 pattern runs on
    this path: the seed is not read off ``prev_body_feature_id`` (so an unrelated
    fillet between the hole and the pattern changes NOTHING — flip A), and there is
    no vacuous-cut fallback (so a removal that lands off the part is
    ``pattern_feature_unreachable``, not a silently doubled body — flip B).

    Typed per-feature refusals (§4), each pinned to the offending SELECTED feature
    via ``upstream_feature_id`` so the UI can name the true cause:

    * ``reference_unresolved`` — the id is not a feature of this evaluated prefix
      (documents 422s a forward/self/missing ref at write time; this is the backstop);
    * ``pattern_feature_unsupported`` — the named kind has no repeatable
      contribution: a MODIFIER, a ``sketch``/``datum``, a ``boolean``, or a
      ``body``-scope mirror/pattern (§3);
    * ``pattern_feature_other_body`` — the tools were recorded against a different
      body than the active one (§MB-0);
    * ``pattern_feature_unreachable`` — a placed cut removes nothing (§4);
    * ``pattern_feature_not_evaluated`` — nothing was recorded for any selected
      feature, so the pattern would be a silent no-op.

    ``count == 1`` is a documented no-op in BOTH scopes, so it returns an empty
    group list with the body untouched rather than the "not evaluated" refusal — it
    is a no-op pattern, not an empty selection.

    Returns the PLACED groups it applied (in application order) so the caller can
    record them for an outer ``features``-scope mirror or pattern to repeat in turn.
    The active body is replaced only after EVERY selected feature applied, so a
    mid-sequence failure leaves the last-good body untouched (§4.3).
    """
    for ref in scope.features:
        if ref.feature_id not in state.scoped_feature_types:
            return FeatureError(
                code="reference_unresolved",
                message=(
                    "Pattern scope must reference features of this evaluated tree "
                    "prefix; the named feature is missing, defined later, "
                    "rolled back, or did not evaluate."
                ),
                upstream_feature_id=ref.feature_id,
            )

    count = _pattern_count(geometry)
    check_pattern_count(count)
    applied: list[RecordedToolGroup] = []
    body = active
    for feature_id in _selection_in_tree_order(scope.features, state):
        record = state.feature_tools.get(feature_id)
        if record is None:
            kind = state.scoped_feature_types[feature_id]
            return FeatureError(
                code="pattern_feature_unsupported",
                message=(
                    f"A '{kind}' feature cannot be patterned: it has no rigid tool "
                    "to repeat, only a result. Modifiers (fillet, chamfer, shell, "
                    "draft, sheet-metal folds), booleans and whole-body "
                    "mirrors/patterns are not selectable — repeating an "
                    "approximation of one would produce a plausible but wrong body."
                ),
                upstream_feature_id=feature_id,
            )
        if record.body_id != state.active_body_id:
            return FeatureError(
                code="pattern_feature_other_body",
                message=(
                    "The selected feature contributed to a different body than the "
                    "one this pattern acts on, so repeating it would move material "
                    "between bodies. Pattern it while its own body is active."
                ),
                upstream_feature_id=feature_id,
            )
        for group in record.groups:
            if not group.tools:
                continue
            placed = _pattern_placements(list(group.tools), geometry)
            if not placed:
                continue  # count == 1 — the documented no-op, not a refusal
            try:
                if group.op == "cut":
                    body = cut_placed_tools(body, placed, count)
                else:
                    body = fuse_placed_tools(body, placed, count)
            except PatternUnreachableError as exc:
                return FeatureError(
                    code="pattern_feature_unreachable",
                    message=(
                        f"{exc} The selected feature's removal repeats clear of the "
                        "body — check the spacing/angle and the selection."
                    ),
                    upstream_feature_id=feature_id,
                )
            except PatternDisjointError as exc:
                return FeatureError(
                    code="pattern_disjoint",
                    message=str(exc),
                    upstream_feature_id=feature_id,
                )
            except PatternError as exc:
                return FeatureError(
                    code="pattern_failed",
                    message=str(exc),
                    upstream_feature_id=feature_id,
                )
            # The PLACED solids, not the sources: a nested pattern/mirror repeats
            # what THIS one placed, never the inner feature's own tool.
            applied.append(RecordedToolGroup(group.op, placed))

    if count > 1 and not applied:
        return FeatureError(
            code="pattern_feature_not_evaluated",
            message=(
                "None of the selected features recorded any geometry to repeat, so "
                "this pattern would do nothing. Check the selection (a count-1 "
                "inner pattern contributes no instances)."
            ),
        )

    if applied:
        state.set_active_body(body)
    return applied


def _evaluate_pattern(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Array a source solid into a linear row / circular ring — union OR cut (§4.3).

    v1 DESIGN DECISION (docs/GEOMETRY-QA.md 2026-07-12/2026-07-13): a pattern
    places rigid copies of a source solid about world-space direction/axis
    vectors (no picked sub-geometry — independent of topological naming, #1), so
    like fillet/chamfer it needs a prior body-affecting feature
    (``no_target_body`` otherwise). Two combine modes, inferred (option a) from
    the IMMEDIATELY-preceding body-affecting feature (:func:`_pattern_cut_tools` —
    the pattern's rule, deliberately narrower than the mirror's):

    * when it is an extrude-CUT or a Hole (a bolt-circle hole, a lightening hole —
      BACKLOG #3 / FINDINGS #1 / showcase F1), the copies of that cut's tool are
      REMOVED at each placement, so one hole-cut + pattern makes N holes, not N
      bodies;
    * otherwise the copies of the WHOLE current body are UNIONED into the chain
      (the original add-pattern, unchanged — BACKLOG #7).

    v2 (docs/design/pattern-scope.md): ``params.scope`` states WHAT is repeated, so
    neither inference above is consulted when the tree says. ``scope.kind ==
    "features"`` dispatches to :func:`_evaluate_pattern_features`; ``scope.kind ==
    "body"`` — which is also what a persisted pre-v2 pattern with no ``scope`` key
    normalises to — runs the v1 body below VERBATIM. That is why the four shipped
    pattern goldens' byte identity is STRUCTURAL rather than measured (§2.1): the
    ``body`` branch dispatches to code this work did not touch.

    Every pattern value is validated in :mod:`geometry.kernel.pattern` and mapped
    1:1 to a per-feature ``pattern_*`` code — bad count/spacing/direction/axis/
    angle, ``pattern_disjoint`` (instances do not merge into / the cut severs one
    solid), or the kernel ``pattern_failed`` (incl. a cut that removes the whole
    body). Both scopes are validated by the SAME guards, which is the reason the
    ``features`` branch sits inside this ``try`` rather than owning a second copy.
    The active body is only replaced on success (strict-prefix rule tessellates the
    last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, PatternFeature), "registry dispatches on type='pattern'"

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Pattern requires an existing body, but no body-affecting "
                "feature precedes this one; add a feature that creates a body "
                "first."
            ),
        )

    scope = feature.params.scope
    tools = (
        None if isinstance(scope, PatternFeaturesScope) else _pattern_cut_tools(state)
    )
    try:
        if isinstance(scope, PatternFeaturesScope):
            applied = _evaluate_pattern_features(
                scope, state, active, feature.params.pattern
            )
            if isinstance(applied, FeatureError):
                return applied
            # Record what this pattern applied so an OUTER `features`-scope pattern
            # or mirror can repeat/reflect it. Opt-in (no-op unless selected).
            state.record_feature_tool_groups(item.id, applied)
            return None
        patterned = _apply_pattern(active, feature.params.pattern, tools)
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
    # Record BEFORE the body is replaced: the contribution is derived from the
    # PRE-pattern body (the source the placements were made from), exactly as a cut
    # records its tools from the pre-cut body (FINDINGS #1/#3). Opt-in, so an
    # unreferenced pattern pays neither the placement rebuild nor the retention.
    if item.id in state.tool_scope_ids:
        contribution = _pattern_contribution(active, feature.params.pattern, tools)
        state.set_active_body(patterned)
        state.record_feature_tool_groups(item.id, [contribution])
        return None
    state.set_active_body(patterned)
    return None


#: Feature kinds a ``features``-scope mirror can reflect
#: (docs/design/mirror-semantics.md §4.7): those whose contribution is a RIGID TOOL
#: plus one boolean. Everything else is refused with a typed
#: ``mirror_feature_unsupported`` — every MODIFIER (fillet/chamfer/shell/draft and
#: the sheet-metal fold/flange/relief family) has a RESULT and no tool, and §4.3
#: refuses those in writing rather than approximating them with a
#: ``before.cut(after)`` delta sliver: that sliver is only the right removal where
#: the reflected side is CONGRUENT to the original, and elsewhere it cuts a groove
#: that is a fillet of nothing — a valid, closed, plausible, WRONG body (the
#: silent-retarget failure class, and strictly worse than an error because a user's
#: own part has no golden). A ``boolean`` is refused because its contribution is a
#: two-body operation, not a tool. Membership here is necessary, not sufficient: a
#: reflectable kind must ALSO have recorded tools (a ``body``-scope mirror is a
#: ``mirror`` that records nothing, §4.6).
_MIRROR_REFLECTABLE_TYPES: frozenset[str] = frozenset(
    {"extrude", "revolve", "sweep", "loft", "hole", "pattern", "mirror", "import"}
)


def _selection_in_tree_order(
    refs: Sequence[FeatureRef], state: EvaluationState
) -> list[uuid.UUID]:
    """The selected ids in EVALUATION order, ignoring the array order (§8.1).

    Array order is UI-incidental (it depends on the order the user ctrl-clicked), so
    honouring it would make identical models tessellate to different bytes; tree
    order replays the selected sub-chain in the same relative order the original side
    was built in, which is what makes composition sound (chain A's hole-then-boss
    reflects as cut-then-fuse, matching the original). ``scoped_feature_types`` is
    insertion-ordered by evaluation, so filtering it IS tree order — a total order
    derived from the tree, hence a pure function of it (RESEARCH §9).

    Takes the refs rather than a scope object so the mirror and the pattern share
    ONE definition of "tree order" (pattern-scope §6) — the determinism rule is the
    same rule, and two copies of it could drift.
    """
    selected = {ref.feature_id for ref in refs}
    return [fid for fid in state.scoped_feature_types if fid in selected]


def _evaluate_mirror_features(
    scope: MirrorFeaturesScope,
    state: EvaluationState,
    active: BodyShape,
    plane: Plane,
) -> FeatureError | list[RecordedToolGroup]:
    """Reflect the RECORDED TOOLS of an explicit feature selection (v2, §4).

    The v2 mechanism, uniform across kinds: for each selected feature in TREE order
    (§8.1), reflect the rigid tool solid(s) it recorded at its OWN evaluation and
    re-apply THAT feature's own boolean — ``fuse`` for an additive contributor,
    ``cut`` for a subtractive one. Parameters are never re-derived, which is what
    keeps a reflected circular pattern correct (§4.5) and what makes this shippable
    without any topological-naming machinery: no reference is resolved on the
    reflected side (§7.1), so there is no new ``subshape_unresolved`` /
    ``subshape_ambiguous`` surface and stage-1's residual silent-retarget hole is not
    widened.

    Typed per-feature refusals (§8.2), each pinned to the offending SELECTED feature
    via ``upstream_feature_id`` so the UI can name the true cause:

    * ``reference_unresolved`` — the id is not a feature of this evaluated prefix
      (documents 422s a forward/self/missing ref at write time; this is the backstop);
    * ``mirror_feature_unsupported`` — the named kind has no reflectable
      contribution: a MODIFIER (§4.3), a non-body-affecting ``sketch``/``datum``
      (§4.4), a ``boolean``, or a ``body``-scope MIRROR (§4.6 — its contribution is a
      whole-body reflection whose delta is not a tool; converting the inner mirror to
      a ``features`` scope makes the 4-fold quadrant nesting work);
    * ``mirror_feature_other_body`` — the tools were recorded against a different
      body than the active one (§MB-0: material from body A never crosses into B);
    * ``mirror_feature_unreachable`` — a reflected cut removes nothing. v1 had to
      fall back to ``mirror_union`` there because it was guessing between two
      workflows; an explicit selection has nothing to guess, so this is an honest
      error (§4.2);
    * ``mirror_feature_not_evaluated`` — nothing was recorded for any selected
      feature, so the mirror would be a silent no-op (the no-silent-no-op rule that
      also motivates ``min_length=1``).

    Returns the REFLECTED groups it applied (in application order) so the caller can
    record them for an OUTER mirror to reflect in turn — a composition of two
    reflections is an exact isometry, so ``features: [base, hole, mirror1]`` populates
    all four quadrants exactly (§4.6). The active body is replaced only after EVERY
    selected feature applied, so a mid-sequence failure leaves the last-good body
    untouched (§4.3).
    """
    for ref in scope.features:
        if ref.feature_id not in state.scoped_feature_types:
            return FeatureError(
                code="reference_unresolved",
                message=(
                    "Mirror scope must reference features of this evaluated tree "
                    "prefix; the named feature is missing, defined later, "
                    "rolled back, or did not evaluate."
                ),
                upstream_feature_id=ref.feature_id,
            )

    applied: list[RecordedToolGroup] = []
    body = active
    for feature_id in _selection_in_tree_order(scope.features, state):
        record = state.feature_tools.get(feature_id)
        if record is None:
            kind = state.scoped_feature_types[feature_id]
            return FeatureError(
                code="mirror_feature_unsupported",
                message=(
                    f"A '{kind}' feature cannot be mirrored: it has no rigid tool "
                    "to reflect, only a result. Modifiers (fillet, chamfer, shell, "
                    "draft, sheet-metal folds), booleans and whole-body mirrors are "
                    "not selectable — reflecting an approximation of one would "
                    "produce a plausible but wrong body."
                ),
                upstream_feature_id=feature_id,
            )
        if record.body_id != state.active_body_id:
            return FeatureError(
                code="mirror_feature_other_body",
                message=(
                    "The selected feature contributed to a different body than the "
                    "one this mirror acts on, so reflecting it would move material "
                    "between bodies. Mirror it while its own body is active."
                ),
                upstream_feature_id=feature_id,
            )
        for group in record.groups:
            if not group.tools:
                continue
            try:
                reflected = reflect_tools(group.tools, plane)
                if group.op == "cut":
                    body = cut_reflected_tools(body, reflected)
                else:
                    body = fuse_reflected_tools(body, reflected)
            except MirrorUnreachableError as exc:
                return FeatureError(
                    code="mirror_feature_unreachable",
                    message=(
                        f"{exc} The selected feature's removal reflects clear of the "
                        "body — check the mirror plane and the selection."
                    ),
                    upstream_feature_id=feature_id,
                )
            except MirrorError as exc:
                return FeatureError(
                    code="mirror_failed",
                    message=str(exc),
                    upstream_feature_id=feature_id,
                )
            # The REFLECTED solids, not the sources: a nested mirror reflects what
            # this one placed (§4.6). Retained only when some outer mirror named this
            # feature — the caller checks the opt-in set before using them.
            applied.append(RecordedToolGroup(group.op, reflected))

    if not applied:
        return FeatureError(
            code="mirror_feature_not_evaluated",
            message=(
                "None of the selected features recorded any geometry to reflect, so "
                "this mirror would do nothing. Check the selection (a count-1 "
                "pattern contributes no instances)."
            ),
        )

    state.set_active_body(body)
    return applied


def _evaluate_mirror(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Reflect the current body about a plane — cut-aware or reflect-and-union (§4.3).

    v1 DESIGN DECISION (docs/GEOMETRY-QA.md): a mirror reflects the CURRENT
    evaluated body about ``plane``. Like fillet/chamfer/pattern it needs a prior
    body-affecting feature (``no_target_body`` otherwise). The mirror plane is
    resolved through the SAME :func:`resolve_sketch_plane` funnel a sketch uses (an
    origin datum name or an earlier ``datum`` feature — no new plane taxonomy), so
    a plane that names a missing / later / non-datum feature is a
    ``reference_unresolved`` pinned to the referenced feature (documents rejects it
    at write time; geometry re-checks because it must not trust its callers).

    v2 (docs/design/mirror-semantics.md): ``params.scope`` states WHAT is reflected.
    ``scope.kind == "features"`` dispatches to :func:`_evaluate_mirror_features`;
    ``scope.kind == "body"`` — which is also what a persisted pre-v2 mirror with no
    ``scope`` key normalises to — runs the v1 body below VERBATIM. That is why the
    shipped mirror goldens' byte identity is STRUCTURAL rather than measured (§3.2 /
    §6.1): the elegant unification ("mirror the body" == "mirror every preceding
    body-affecting feature") is available and REFUSED, because the goldens assert
    byte-identical GLB, which is sensitive to B-rep face ORDER, and the two paths
    hand OCCT different boolean sequences. Keeping both branches costs one ``if``
    and buys the guarantee.

    Two combine modes, chosen from the MOST RECENT cut of this body
    (:func:`_mirror_cut_tools`) — the same cut-awareness the pattern has, but
    tracked past intervening features, because for a mirror the fallback DESTROYS
    geometry rather than merely reading the request differently (FINDINGS #1 and
    CM-1: both verbs reasoned about the body chain without cut-awareness, and the
    mirror's shadowed case erased the hole):

    * when this body has a cut on record, the mirror reflects THAT CUT's tool(s)
      about ``plane`` and removes them (:func:`mirror_cut`), so a plate with a hole
      on one side mirrors to a plate with a hole on BOTH sides — the #1 mirror use
      case — and it keeps doing so when an unrelated chamfer / fillet / boss sits
      between the cut and the mirror (CM-1). Reflecting the whole filled body and
      unioning would instead FILL the original hole (the featureless-brick bug);
    * otherwise the mirror reflects the WHOLE current body and BOOLEAN-UNIONS the
      reflection into the body chain (:func:`mirror_union` — option B, the
      reflective sibling of the ADD pattern, unchanged). UNLIKE a pattern this union
      may be a DISJOINT two-lump body (the reflection of a body that clears the
      plane — a valid ``2V`` multi-body, §MB-0), an OVERLAPPING merge, or the
      unchanged body (a symmetric source).

    A degenerate reflection / failed union or cut is a per-feature ``mirror_failed``
    error; the active body is only replaced on success (strict-prefix rule
    tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, MirrorFeature), "registry dispatches on type='mirror'"

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Mirror requires an existing body, but no body-affecting feature "
                "precedes this one; add a feature that creates a body first."
            ),
        )

    plane = resolve_sketch_plane(feature.params.plane, state)
    if isinstance(plane, FeatureError):
        return plane

    scope = feature.params.scope
    if isinstance(scope, MirrorFeaturesScope):
        applied = _evaluate_mirror_features(scope, state, active, plane)
        if isinstance(applied, FeatureError):
            return applied
        # Record what this mirror applied so an OUTER `features`-scope mirror can
        # reflect it (the 4-fold quadrant workflow, §4.6). Opt-in.
        state.record_feature_tool_groups(item.id, applied)
        return None

    tools = _mirror_cut_tools(state)
    try:
        if tools is not None:
            state.set_active_body(mirror_cut(active, tools, plane))
        else:
            state.set_active_body(mirror_union(active, plane))
    except MirrorError as exc:
        return FeatureError(code="mirror_failed", message=str(exc))
    return None
