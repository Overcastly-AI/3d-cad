"""The Hole feature: a simple, counterbored or countersunk hole, optionally
tapped (a cosmetic thread callout), placed on a picked planar face and cut from
the body that owns that face (plus any bodies in its Feature Scope).
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

import uuid

from build123d import Compound, Plane, Solid
from loft_wire.features import (
    EvaluatedFeatureInput,
    FeatureError,
    HoleBlindDepth,
    HoleCounterbore,
    HoleCountersink,
    HoleFeature,
    HoleParamsV1,
)

from geometry.features.bodies import _resolve_operand_body
from geometry.features.datum_sketch import (
    _resolve_face_datum_plane,
)
from geometry.features.naming_hooks import hole_names
from geometry.features.owner import face_owner_body_id
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
    bore_tool,
    check_tap_drill_bore,
    counterbore_tool,
    countersink_tool,
    label_hole_tool,
    resolve_iso_metric_thread,
)
from geometry.kernel.boolean_guard import MeasuredBody
from geometry.kernel.hole import (
    bore_hole_measured,
    cut_counterbore_measured,
    cut_countersink_measured,
    cut_scoped_bore_measured,
)
from geometry.kernel.naming import NameHook, OpHistory
from geometry.kernel.types import BodyShape


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
    """Drill a cylindrical hole into the body owning a face, at a point on it (§4.3).

    The dedicated Hole feature (BACKLOG P2, slice 1 — the simple bore; slice 2 —
    the optional coaxial counterbore / countersink recess, and the optional
    COSMETIC thread callout that makes the hole TAPPED). It needs a prior
    body-affecting feature (``no_prior_body`` otherwise). It drills the body that
    OWNS the picked face (:func:`face_owner_body_id`, HOLE-ACTIVE-BODY — the
    Fusion 360 / SolidWorks rule), which then becomes the active body; a
    through-all hole's ``scope_bodies`` (SolidWorks' Feature Scope) are bored
    too (:func:`_cut_scope`). The placement FACE is
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

    if state.active_body is None or state.active_body_id is None:
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

    # HOLE-ACTIVE-BODY: drill the body that OWNS the picked face, not the
    # most recently built one (they differ in any multi-body part).
    owner_id = face_owner_body_id(params.face, state)
    if isinstance(owner_id, FeatureError):
        return owner_id
    assert owner_id is not None, "a part with an active body has an owner"
    active = state.bodies[owner_id]
    active_id = owner_id
    plane = _resolve_face_datum_plane(params.face, 0.0, state, body_id=owner_id)
    if isinstance(plane, FeatureError):
        return plane
    blind = isinstance(params.depth, HoleBlindDepth)
    # A blind hole KEEPS its Feature Scope (a switch back to through-all
    # restores it) but cuts only its owner: its depth is measured there.
    scoped: list[tuple[uuid.UUID, BodyShape]] = []
    for index, ref in enumerate([] if blind else params.scope_bodies or []):
        if ref.feature_id == owner_id:
            continue
        body = _resolve_operand_body(ref, state, slot=f"Hole scope_bodies[{index}]")
        if isinstance(body, FeatureError):
            return body
        scoped.append((ref.feature_id, body))

    depth_mm = (
        params.depth.depth_mm if isinstance(params.depth, HoleBlindDepth) else None
    )
    point = (params.position.x, params.position.y, params.position.z)
    # The faces the cuts make, by role (``hole:0:wall``...): a resize keeps
    # every name, so a chamfered rim follows it (DESIGN-INTENT-REFS).
    history = OpHistory()
    try:
        drilled = bore_hole_measured(
            active,
            plane,
            point,
            params.diameter_mm,
            through_all=not blind,
            depth_mm=depth_mm,
            body_volume=state.body_volume(active_id),
            history=history,
        )
        # Slice 2: sink the optional coaxial recess (counterbore / countersink) at
        # the face, cut ALONGSIDE the bore (design: HoleType additive member).
        hole_type = params.type
        if isinstance(hole_type, HoleCounterbore):
            drilled = cut_counterbore_measured(
                drilled.shape,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                cbore_diameter_mm=hole_type.cbore_diameter_mm,
                cbore_depth_mm=hole_type.cbore_depth_mm,
                history=history,
                body_volume=drilled.volume,
            )
        elif isinstance(hole_type, HoleCountersink):
            drilled = cut_countersink_measured(
                drilled.shape,
                plane,
                point,
                bore_diameter_mm=params.diameter_mm,
                csink_diameter_mm=hole_type.csink_diameter_mm,
                csink_angle_deg=hole_type.csink_angle_deg,
                history=history,
                body_volume=drilled.volume,
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
    scoped_cuts = _cut_scope(item, state, active, plane, point, scoped)
    if isinstance(scoped_cuts, FeatureError):
        return scoped_cuts
    state.set_body(
        owner_id, drilled.shape, hole_names(item.id, history), volume=drilled.volume
    )
    for body_id, (cut, names) in scoped_cuts.items():
        state.set_body(body_id, cut.shape, names, volume=cut.volume)
    # The drilled body becomes the active one — the body the last feature
    # touched, as a boolean's result or a new body does — so a following
    # pattern / mirror of this hole repeats it in the body it was drilled in.
    state.active_body_id = owner_id
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
    # The recorded tools are labelled the same way, so a features-scope pattern
    # or mirror of this hole names each copy's faces after these.
    labelled = OpHistory()
    label_hole_tool(labelled, tools[0], plane, "wall", "floor" if blind else None)
    if isinstance(hole_type, HoleCounterbore):
        label_hole_tool(labelled, tools[1], plane, "cbore_wall", "cbore_floor")
    elif isinstance(hole_type, HoleCountersink):
        label_hole_tool(labelled, tools[1], plane, "csink_cone", None)
    state.record_feature_tools(
        item.id, "cut", list(tools), hole_names(item.id, labelled)
    )
    return None


def _cut_scope(
    item: EvaluatedFeatureInput,
    state: EvaluationState,
    owner: BodyShape,
    plane: Plane,
    point: tuple[float, float, float],
    scoped: list[tuple[uuid.UUID, BodyShape]],
) -> dict[uuid.UUID, tuple[MeasuredBody, NameHook]] | FeatureError:
    """Cut the through-all bore from each FURTHER body of the hole's Feature
    Scope (SolidWorks' Feature Scope; HOLE-ACTIVE-BODY).

    ONE coaxial tool serves every scoped body: :func:`bore_tool` over the union
    of the owner and the scoped bodies, so its span clears all of them. Only
    the bore is cut here — a counterbore / countersink seats in the owner,
    where its depth was validated. Pure: the state is written by the caller on
    success, so a body the bore misses (``hole_off_body``, pinned to that
    body's base feature) leaves every body untouched.
    """
    feature = item.feature
    assert isinstance(feature, HoleFeature)
    if not scoped:
        return {}
    reach = Compound(children=[owner, *(body for _, body in scoped)])
    tool = bore_tool(
        reach,
        plane,
        point,
        feature.params.diameter_mm,
        through_all=True,
        depth_mm=None,
    )
    labelled = OpHistory()
    label_hole_tool(labelled, tool, plane, "wall", None)
    names = hole_names(item.id, labelled)
    cuts: dict[uuid.UUID, tuple[MeasuredBody, NameHook]] = {}
    for body_id, body in scoped:
        try:
            cut = cut_scoped_bore_measured(
                body, tool, body_volume=state.body_volume(body_id)
            )
        except HoleOffBodyError as exc:
            return FeatureError(
                code="hole_off_body", message=str(exc), upstream_feature_id=body_id
            )
        except BooleanError as exc:
            return FeatureError(code="boolean_failed", message=str(exc))
        cuts[body_id] = (cut, names)
    return cuts
