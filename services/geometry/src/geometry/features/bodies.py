"""Body sources and combinations: STEP import (docs/design/step-import.md) and
the multi-body ``boolean`` (docs/design/multi-body.md §MB-1/§MB-2).
"""

from loft_wire.features import (
    BooleanFeature,
    EvaluatedFeatureInput,
    FeatureError,
    FeatureRef,
    ImportFeature,
)

from geometry.features.state import (
    EvaluationState,
)
from geometry.kernel import (
    BooleanDisjointError,
    BooleanEmptyError,
    BooleanError,
    ImportNoSolidError,
    ImportParseError,
    ImportParseTimeoutError,
    boolean_bodies_measured,
)
from geometry.kernel.types import BodyShape
from geometry.step_cache import import_step_solid_cached


def _step_import_bounds() -> tuple[float, float]:
    """The configured (CPU-time, wall-clock) bounds for the untrusted parse (§6).

    Resolved from ``GeometrySettings`` (the py-kit config knobs
    ``step_import_timeout_seconds`` — the CPU-time DoS ceiling — and
    ``step_import_wall_timeout_seconds`` — the wall-clock liveness backstop)
    rather than hardcoded in the kernel hot path. Imported lazily to avoid a cycle
    (``geometry.main`` imports this module through the API) — the worker-module
    precedent. Only consulted when an ``import`` feature is evaluated, so the
    per-call settings read is negligible.
    """
    from geometry.main import GeometrySettings

    settings = GeometrySettings()
    return (
        settings.step_import_timeout_seconds,
        settings.step_import_wall_timeout_seconds,
    )


def _evaluate_import(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Import an external STEP part as the part's BASE body (§4.3).

    DESIGN DECISION (docs/design/step-import.md §1, docs/design/multi-body.md
    §MB-0): an ``import`` is a body-affecting BASE feature — like the first
    extrude it does not modify a prior body, it STARTS a new active body from the
    imported solid. Under multi-body (§MB-0) an import with a body already
    present is no longer an error (the former ``import_with_prior_body``): it
    simply starts a SECOND body, exactly as an additive ``merge=False`` extrude
    would. A positioned insert / boolean against an existing body is a later
    boolean slice (MB-1+).

    The inline STEP text is read deterministically (units pinned to mm, RESEARCH
    §9) through :func:`~geometry.step_cache.import_step_solid_cached`, a
    content-keyed cache over :func:`import_step_solid` (engineering audit F8): an
    unchanged import re-uses its parsed body and SKIPS the subprocess parse, so
    editing a part that starts from an imported body pays one parse per distinct
    upload, not one per tree evaluation. A cache MISS runs the UNCHANGED bounded
    parse — the untrusted OCCT read still runs in a killable subprocess bounded
    by the configured CPU-time ceiling (``step_import_timeout_seconds``, the
    contention-invariant primary DoS bound) plus a wall-clock liveness backstop
    (``step_import_wall_timeout_seconds``) — design §6, BACKLOG P1 — and only a
    cleanly-parsed body is cached, so a hit never bypasses those bounds or the
    upstream 16 MiB size cap. Kernel failures surface as per-feature errors pinned
    to this feature — ``import_parse_timeout`` (the parse exceeded its CPU-time
    ceiling or the wall-clock backstop and was killed), ``import_parse_failed``
    (unparseable
    bytes) or ``import_no_solid`` (ZERO solids — surfaces/shells/wireframe only;
    the message carries the shape stats). A file with ONE solid becomes a bare
    Solid body and a file with TWO OR MORE becomes ONE lump-sorted Compound body
    (§MB-4) — a multi-solid file is now a SUCCESS, not an error. The active body
    is only started on success. Size/emptiness of ``data`` is a request-validation
    422 upstream (§6), so it never reaches here.
    """
    feature = item.feature
    assert isinstance(feature, ImportFeature), "registry dispatches on type='import'"
    params = feature.params

    try:
        cpu_timeout_s, wall_timeout_s = _step_import_bounds()
        body = import_step_solid_cached(
            params.data, cpu_timeout_s=cpu_timeout_s, wall_timeout_s=wall_timeout_s
        )
    except ImportParseTimeoutError as exc:
        return FeatureError(code="import_parse_timeout", message=str(exc))
    except ImportParseError as exc:
        return FeatureError(code="import_parse_failed", message=str(exc))
    except ImportNoSolidError as exc:
        return FeatureError(code="import_no_solid", message=str(exc))
    # An import is a BODY-CREATING BASE feature: it STARTS a new active body
    # (keyed by its own id — §MB-0 Decision 1), whether or not a prior body
    # exists. Multi-body (§MB-0) retires the former ``import_with_prior_body``
    # error — a part may now hold an imported body alongside a modelled one. The
    # imported body is a bare Solid (one solid) OR a lump-sorted Compound (a
    # multi-solid file → ONE multi-lump body, §MB-4), never N bodies.
    state.start_body(item.id, body)
    # The imported body IS this feature's rigid contribution, so it reflects and
    # re-fuses like any additive tool (mirror-semantics §4.1). Opt-in.
    state.record_feature_tools(item.id, "fuse", [body])
    return None


def _resolve_operand_body(
    ref: FeatureRef, state: EvaluationState, *, slot: str
) -> BodyShape | FeatureError:
    """Resolve a boolean operand FeatureRef to its CURRENT body solid (§MB-1).

    An operand names a body by its BASE feature id — the key of
    ``state.bodies`` (§MB-0 Decision 1) — so resolution is a single dict lookup
    of the operand's CURRENT geometry (every modifier already applied). A miss is
    an honest eval-time ``reference_unresolved`` pinned to the referenced feature:
    the base feature is later/rolled-back/non-body-creating, was MERGED into
    another body (``merge=True`` — it never keyed a standalone body), or was
    CONSUMED as the tool of an EARLIER boolean (removed from the set). Documents
    cannot catch that last case statically — a body's consumption is an eval-time
    fact — so geometry re-checks (design §Decisions-3, §MB-1 error taxonomy).
    """
    body = state.bodies.get(ref.feature_id)
    if body is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                f"Boolean {slot} must reference an earlier body-creating feature "
                "that still holds a distinct body of this part; the referenced "
                "feature is not a current body (it may have been merged into "
                "another body or consumed by an earlier boolean)."
            ),
            upstream_feature_id=ref.feature_id,
        )
    return body


def _evaluate_boolean(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Boolean two independently-built bodies (body-affecting, §Decisions-3).

    The headline multi-body feature (docs/design/multi-body.md §MB-1/§MB-2): it
    resolves ``target`` and ``tool`` to two CURRENT bodies of the part
    (:func:`_resolve_operand_body` — each keyed by its base feature id, §MB-0),
    booleans them (:func:`boolean_bodies` — ``union`` fuses, ``subtract`` cuts the
    tool out of the target, ``intersect`` keeps their common volume), and REPLACES
    both operands with the result — which takes over the target's identity slot
    and drops the tool body (:meth:`EvaluationState.combine_bodies`), becoming the
    active body.

    All three operations are wired (MB-1a union, MB-2 subtract/intersect). Errors
    pin the failing operand where relevant: ``reference_unresolved`` (an operand
    is not a current body — incl. one consumed by an earlier boolean),
    ``boolean_same_body`` (target and tool name the SAME body — a degenerate
    self-op), ``boolean_disjoint`` (the result is >1 solid: a union of
    non-touching bodies, or a subtract/intersect that leaves ≥2 pieces — the
    single-connected-solid-per-body invariant, §Decisions-3), ``boolean_empty``
    (a subtract that removes the whole target, or an intersect with no overlap),
    or ``boolean_failed`` (a kernel failure). The body set is mutated only on
    success (last-good semantics, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, BooleanFeature), "registry dispatches on type='boolean'"
    params = feature.params

    if params.target.feature_id == params.tool.feature_id:
        return FeatureError(
            code="boolean_same_body",
            message=(
                "A boolean's target and tool must name two DIFFERENT bodies, but "
                "both reference the same base feature; pick two distinct bodies. "
                "(A body unioned/subtracted/intersected with itself is degenerate.)"
            ),
            upstream_feature_id=params.tool.feature_id,
        )

    target = _resolve_operand_body(params.target, state, slot="target")
    if isinstance(target, FeatureError):
        return target
    tool = _resolve_operand_body(params.tool, state, slot="tool")
    if isinstance(tool, FeatureError):
        return tool

    try:
        combined = boolean_bodies_measured(
            target,
            tool,
            params.operation,
            allow_disjoint=params.allow_disjoint,
            target_volume=state.body_volume(params.target.feature_id),
            tool_volume=state.body_volume(params.tool.feature_id),
        )
    except BooleanDisjointError as exc:
        return FeatureError(code="boolean_disjoint", message=str(exc))
    except BooleanEmptyError as exc:
        return FeatureError(code="boolean_empty", message=str(exc))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))

    state.combine_bodies(
        params.target.feature_id,
        params.tool.feature_id,
        combined.shape,
        volume=combined.volume,
    )
    return None
