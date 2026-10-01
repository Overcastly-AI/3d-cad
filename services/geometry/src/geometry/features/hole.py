"""The Hole feature: a simple, counterbored or countersunk hole, optionally
tapped (a cosmetic thread callout), placed on a picked planar face and cut from
the active body.
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

from build123d import Solid
from loft_wire.features import (
    EvaluatedFeatureInput,
    FeatureError,
    HoleBlindDepth,
    HoleCounterbore,
    HoleCountersink,
    HoleFeature,
    HoleParamsV1,
)

from geometry.features.datum_sketch import (
    _resolve_face_datum_plane,
)
from geometry.features.state import (
    EvaluationState,
)
from geometry.kernel import (
    BooleanError,
    HoleInvalidDiameterError,
    HoleOffBodyError,
    HoleRecessInvalidError,
    HoleTooDeepError,
    ThreadBoreMismatchError,
    ThreadUnsupportedError,
    bore_hole,
    bore_tool,
    check_tap_drill_bore,
    counterbore_tool,
    countersink_tool,
    cut_counterbore,
    cut_countersink,
    resolve_iso_metric_thread,
)


def _check_hole_thread(params: HoleParamsV1) -> FeatureError | None:
    """Validate a hole's optional COSMETIC thread callout — typed, never silent.

    ``None`` when the hole is untapped or the callout is honourable; otherwise the
    per-feature error, mapped 1:1 from the kernel thread taxonomy
    (``geometry.kernel.threads``):

    * ``hole_thread_unsupported`` — the (nominal, pitch) pair is not an ISO 261
      combination the kernel knows;
    * ``hole_thread_mismatch`` — the authored bore is not a hole that thread can
      be tapped in (outside ``[minor diameter, nominal diameter)``).

    Pure param arithmetic, so it runs BEFORE the face resolves and before any
    boolean: a hole whose callout cannot be honoured must produce NO body at all,
    rather than a plain bore wearing a thread designation on the drawing (the
    silent-wrong class this slice exists to close).
    """
    thread = params.thread
    if thread is None:
        return None
    try:
        resolved = resolve_iso_metric_thread(
            thread.nominal_diameter_mm, thread.pitch_mm
        )
        check_tap_drill_bore(resolved, params.diameter_mm)
    except ThreadUnsupportedError as exc:
        return FeatureError(code="hole_thread_unsupported", message=str(exc))
    except ThreadBoreMismatchError as exc:
        return FeatureError(code="hole_thread_mismatch", message=str(exc))
    return None


def _evaluate_hole(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Drill a cylindrical hole into the current body at a point on a face (§4.3).

    The dedicated Hole feature (BACKLOG P2, slice 1 — the simple bore; slice 2 —
    the optional coaxial counterbore / countersink recess, and the optional
    COSMETIC thread callout that makes the hole TAPPED). Like fillet/shell/draft
    it modifies the implicit single body chain (design §7.6), so it needs a prior
    body-affecting feature (``no_prior_body`` otherwise). The placement FACE is
    resolved by the SAME stage-1 planar-face signature the ``on_face`` datum /
    shell openings use (:func:`resolve_face_plane`, via
    :func:`_resolve_face_datum_plane` — offset 0): a ref that no longer resolves
    is ``subshape_unresolved``, a congruent twin ``subshape_ambiguous``, a
    non-planar / missing face likewise (planar faces only carry a signature). The
    drill cuts INTO the material (opposite the face's outward normal — the correct
    direction, automatically) through the shared cut boolean; a counterbore /
    countersink then sinks a larger coaxial recess at the face. Failures degrade to
    typed per-feature errors, never a 500 or a silently wrong body:
    ``hole_off_body`` (the point is off the face / the direction is wrong — no
    material removed), ``hole_too_deep`` (a blind depth OR a recess depth exceeds
    the available material / overhangs the face edge), ``hole_cbore_invalid`` /
    ``hole_csink_invalid`` (a recess no wider than the bore),
    ``hole_thread_unsupported`` / ``hole_thread_mismatch`` (a thread callout the
    kernel cannot honour), or ``boolean_failed`` (a kernel cut failure /
    lump-count change). The active body is only replaced on success (strict-prefix
    rule tessellates the last-good body, §4.3).

    A ``thread`` callout is COSMETIC (``geometry.kernel.threads``): it adds no
    geometry — the drilled solid is byte-identical to the same hole untapped — so
    a tapped hole mirrors/patterns/shells exactly as its bore does. It is
    validated FIRST, before any geometry runs, because it is pure param
    arithmetic: an unhonourable designation therefore never produces a body, and
    never silently degrades to a plain hole carrying a thread callout nobody can
    cut.
    """
    feature = item.feature
    assert isinstance(feature, HoleFeature), "registry dispatches on type='hole'"
    params = feature.params

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Hole requires an existing body, but no body-affecting feature "
                "precedes this one; add a feature that creates a body first."
            ),
        )

    thread_error = _check_hole_thread(params)
    if thread_error is not None:
        return thread_error

    plane = _resolve_face_datum_plane(params.face, 0.0, state)
    if isinstance(plane, FeatureError):
        return plane

    blind = isinstance(params.depth, HoleBlindDepth)
    depth_mm = (
        params.depth.depth_mm if isinstance(params.depth, HoleBlindDepth) else None
    )
    point = (params.position.x, params.position.y, params.position.z)
    try:
        drilled = bore_hole(
            active,
            plane,
            point,
            params.diameter_mm,
            through_all=not blind,
            depth_mm=depth_mm,
        )
        # Slice 2: sink the optional coaxial recess (counterbore / countersink) at
        # the face, cut ALONGSIDE the bore (design: HoleType additive member).
        hole_type = params.type
        if isinstance(hole_type, HoleCounterbore):
            drilled = cut_counterbore(
                drilled,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                cbore_diameter_mm=hole_type.cbore_diameter_mm,
                cbore_depth_mm=hole_type.cbore_depth_mm,
            )
        elif isinstance(hole_type, HoleCountersink):
            drilled = cut_countersink(
                drilled,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                csink_diameter_mm=hole_type.csink_diameter_mm,
                csink_angle_deg=hole_type.csink_angle_deg,
            )
    except HoleInvalidDiameterError as exc:
        # Unreachable from the API (HoleParamsV1.diameter_mm is Field(gt=0)); the
        # typed guard keeps a script/pattern path from surfacing a raw OCCT raise
        # as a 500 (FINDINGS #23).
        return FeatureError(code="hole_invalid_diameter", message=str(exc))
    except HoleRecessInvalidError as exc:
        code = (
            "hole_cbore_invalid"
            if isinstance(params.type, HoleCounterbore)
            else "hole_csink_invalid"
        )
        return FeatureError(code=code, message=str(exc))
    except HoleOffBodyError as exc:
        return FeatureError(code="hole_off_body", message=str(exc))
    except HoleTooDeepError as exc:
        return FeatureError(code="hole_too_deep", message=str(exc))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    state.set_active_body(drilled)
    # Capture the removal tool(s) for a following pattern / mirror of this hole
    # (FINDINGS #1). Rebuilt from the SAME pre-cut ``active`` body the cuts used, so
    # every tool is byte-identical to what was removed; the recess builders reuse the
    # already-validated params (a bore diagonal is invariant to the seed bore, so the
    # recess span matches). Pure geometry — the cut already succeeded above.
    tools: list[Solid] = [
        bore_tool(
            active,
            plane,
            point,
            params.diameter_mm,
            through_all=not blind,
            depth_mm=depth_mm,
        )
    ]
    if isinstance(hole_type, HoleCounterbore):
        tools.append(
            counterbore_tool(
                active,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                cbore_diameter_mm=hole_type.cbore_diameter_mm,
                cbore_depth_mm=hole_type.cbore_depth_mm,
            )
        )
    elif isinstance(hole_type, HoleCountersink):
        tools.append(
            countersink_tool(
                active,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                csink_diameter_mm=hole_type.csink_diameter_mm,
                csink_angle_deg=hole_type.csink_angle_deg,
            )
        )
    state.record_cut_tools(item.id, tools)
    state.record_feature_tools(item.id, "cut", list(tools))
    return None
