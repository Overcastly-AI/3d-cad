"""Sheet-metal features: base flange, edge flange, hem and corner relief.

docs/design/sheet-metal.md. The two fold features share
:func:`_fold_flange_off_edge`, which records each bend's provenance and keeps the
clean (un-notched) unfold body that the flat pattern and every corner relief
resolve their bends against (§4.4.4).
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

from collections.abc import Callable

from loft_wire.features import (
    HEM_CLOSED_RADIUS_RATIO,
    EdgeSubshapeRef,
    EvaluatedFeatureInput,
    FeatureError,
    FeatureRef,
    HemRadiusError,
    SheetMetalBaseFlangeFeature,
    SheetMetalCornerReliefFeature,
    SheetMetalEdgeFlangeFeature,
    SheetMetalHemFeature,
    resolve_hem_bend_radius_mm,
)

from geometry.features.datum_sketch import (
    _resolve_profile_face,
)
from geometry.features.naming_hooks import labelled_names, prism_names
from geometry.features.state import (
    EvaluationState,
    _add_body,
)
from geometry.kernel import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    extrude_face,
    resolve_edge_durable,
)
from geometry.kernel.naming import OpHistory
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.sheet_metal import (
    BendProvenance,
    CornerRelief,
    CornerReliefError,
    EdgeFlangeEdgeError,
    EdgeFlangeError,
    SheetMetalDefaults,
    build_edge_flange,
    corner_relief_tools,
    cut_relief_tools,
)


def _evaluate_sheet_metal_base_flange(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Thicken a sketch profile to gauge — the sheet-metal base flange (§4.1).

    A base flange is mechanically an ADDITIVE extrude by a FIXED gauge
    (docs/design/sheet-metal.md §4.1), so this reuses the EXACT extrude path — the
    shared :func:`_resolve_profile_face` (profile → single closed face) and
    :func:`extrude_face` (prism along the plane normal, ``direction:
    normal|reverse``) — with the gauge ``thickness_mm`` as the extrusion distance,
    then the SAME multi-body ADD (:func:`_add_body`). No new kernel geometry code.

    What a base flange adds over a plain extrude: on success it records the part's
    sheet-metal defaults (gauge/K/bend-radius) keyed by THIS feature id — the body
    identity (§MB-0 Decision 1) — so a later edge-flange / unfold slice reads the
    gauge + defaults off the body it attaches to (§5). Recorded only after the
    body is added (last-good semantics, §4.3): a boolean_failed leaves both the
    body set AND the defaults untouched. There is no ``operation`` — a base flange
    always creates material; kernel failures surface as the extrude error codes
    (``profile_not_closed``/``profile_unsupported``/``reference_unresolved``,
    ``boolean_failed``), pinned as extrude's are.
    """
    feature = item.feature
    assert isinstance(feature, SheetMetalBaseFlangeFeature), (
        "registry dispatches on type='sheet_metal_base_flange'"
    )
    params = feature.params
    reverse = params.direction == "reverse"

    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, solved = resolved

    # Named like an extrude's prism (DESIGN-INTENT-REFS step 3): each side from
    # the sketch entity it swept, the two skins ``start`` / ``end``.
    history = OpHistory()
    tool = extrude_face(face, plane, params.thickness_mm, reverse, history=history)
    generated = prism_names(item.id, history, plane, solved.entities, region=False)
    error = _add_body(item, state, tool, merge=params.merge, generated=generated)
    if error is not None:
        return error
    state.sheet_metal_defaults[item.id] = SheetMetalDefaults(
        thickness_mm=params.thickness_mm,
        k_factor=params.k_factor,
        bend_radius_mm=params.bend_radius_mm,
    )
    return None


def _fold_flange_off_edge(
    item: EvaluatedFeatureInput,
    state: EvaluationState,
    edge_ref: EdgeSubshapeRef,
    *,
    flange_length_mm: float,
    bend_angle_deg: float,
    override_radius_mm: float | None,
    override_k_factor: float | None,
    subject: str,
    width_mm: float | None = None,
    offset_mm: float = 0.0,
    radius_rule: Callable[[SheetMetalDefaults], float | FeatureError] | None = None,
) -> FeatureError | None:
    """Shared bend machinery for the edge-flange (§4.2) and hem (parity §2) folds.

    Both features fold a flange off a resolved base-flange edge via the SAME
    :func:`build_edge_flange` (a hem is an edge flange at a fixed 180 deg fold —
    parity §2 / DRY): resolve the picked edge (stage-1 :class:`EdgeSignature`,
    :func:`resolve_edge_durable` — strict, then the durable re-match that carries
    the fold through a base-sketch dimension edit, NAME-2 / audit S-24), settle the
    bend radius and K, build + fuse the bend, and record the bend
    provenance (§5) keyed by this feature id.

    THE RADIUS IS NOT SHARED, and conflating it shipped HEM-1. By default the fold
    inherits the part's general base-flange ``bend_radius_mm`` when the feature's
    own is omitted — right for an edge flange, which IS the free-standing die bend
    that radius describes. A caller whose radius means something else passes
    *radius_rule*, which is handed the part's :class:`SheetMetalDefaults` and
    returns either the radius or a TYPED :class:`FeatureError` to degrade to; the
    hem uses it because its radius is the air gap between the folded layers. K is
    still inherited in both cases (it is a material property).

    Every failure is a TYPED per-feature
    error (never a raw kernel exception or an invalid solid — parity §3): no prior
    body (``no_prior_body``), no recorded sheet-metal defaults (``no_base_flange``),
    an unresolvable / ambiguous edge (``subshape_unresolved`` /
    ``subshape_ambiguous``), an unsuitable edge (``edge_flange_bad_edge``), whatever
    *radius_rule* returns (the hem's ``hem_type_radius_conflict`` /
    ``hem_gap_degenerate``), or a
    degenerate/self-intersecting fold the kernel rejects (``edge_flange_failed`` —
    :func:`build_edge_flange` validates the fused solid count). ``subject`` names
    the feature in the no-body messages. The active body is only replaced on
    success (strict-prefix tessellates the last-good body, §4.3); ``set_active_body``
    keeps the body's identity (its base-flange id) so the defaults stay reachable
    for a later fold (a depth-1 star, §4.3).
    """
    active = state.active_body
    if active is None or state.active_body_id is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                f"{subject} requires an existing sheet body, but no "
                "body-affecting feature precedes it; add a base flange first."
            ),
        )
    defaults = state.sheet_metal_defaults.get(state.active_body_id)
    if defaults is None:
        return FeatureError(
            code="no_base_flange",
            message=(
                f"{subject} needs the part's sheet-metal gauge/K (from a base "
                "flange) to compute its bend allowance, but the active body is not "
                "a sheet-metal base flange."
            ),
        )

    try:
        edge = resolve_edge_durable(
            active,
            edge_ref.selector.signature,
            tally=state.subshape_tally,
            face_names=state.face_names(),
        ).edge
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    # The RADIUS RULE differs by verb, and conflating them shipped HEM-1. An edge
    # flange inherits the part's general base-flange radius when its own is omitted
    # — that radius describes exactly what an edge flange is, a free-standing die
    # bend. A HEM does not: its radius IS the air gap between the folded layers
    # (gap = 2r), so it is derived from the hem TYPE and the gauge instead
    # (`radius_rule`, py_kit.resolve_hem_bend_radius_mm). Inheriting it there put
    # 6 mm of air inside a "closed" hem on 2 mm sheet.
    if radius_rule is not None:
        resolved = radius_rule(defaults)
        if isinstance(resolved, FeatureError):
            return resolved
        radius = resolved
    else:
        radius = override_radius_mm or defaults.bend_radius_mm
    k_factor = override_k_factor if override_k_factor is not None else defaults.k_factor

    history = OpHistory()
    try:
        result = build_edge_flange(
            active,
            edge,
            flange_length_mm=flange_length_mm,
            bend_angle_deg=bend_angle_deg,
            bend_radius_mm=radius,
            thickness_mm=defaults.thickness_mm,
            width_mm=width_mm,
            offset_mm=offset_mm,
            history=history,
        )
    except EdgeFlangeEdgeError as exc:
        return FeatureError(code="edge_flange_bad_edge", message=str(exc))
    except EdgeFlangeError as exc:
        return FeatureError(code="edge_flange_failed", message=str(exc))

    # Each face of the fold is named by its role (DESIGN-INTENT-REFS step 3):
    # ``<feature id>:outer`` is this flange's outer flat whatever the base size.
    state.set_active_body(result.body, labelled_names(item.id, history), history.merged)

    # Maintain the CLEAN (un-notched) sheet body — every bend applied, NO relief
    # notches (§4.4.4). Both the flat-pattern unfold AND each corner relief resolve
    # their bend signatures against THIS body, never the live (possibly notched) one:
    # a relief notch shortens a bend cylinder and shifts its centroid past the
    # signature match tolerance, so resolving against the live body would miss a
    # shared/earlier bend. Until the first relief the clean body tracks the live body
    # verbatim (same object). AFTER a relief has notched the live body the two have
    # diverged, so re-fold THIS same flange off the clean body (identical edge + fold
    # params → an identical bend, so the provenance recorded below still resolves
    # against it). The provenance is taken from whichever build the clean body carries.
    clean_result = result
    prior_clean = state.sheet_metal_unfold_body
    if prior_clean is None or prior_clean is active:
        state.sheet_metal_unfold_body = result.body
    else:
        try:
            # NOT tallied: this is the SAME picked reference the live resolve
            # above already reported, re-found on the un-notched twin of the body
            # purely to keep the unfold's bend provenance. The user picked once.
            clean_edge = resolve_edge_durable(
                prior_clean, edge_ref.selector.signature
            ).edge
            clean_result = build_edge_flange(
                prior_clean,
                clean_edge,
                flange_length_mm=flange_length_mm,
                bend_angle_deg=bend_angle_deg,
                bend_radius_mm=radius,
                thickness_mm=defaults.thickness_mm,
                width_mm=width_mm,
                offset_mm=offset_mm,
            )
            state.sheet_metal_unfold_body = clean_result.body
        except (
            SubshapeUnresolvedError,
            SubshapeAmbiguousError,
            EdgeFlangeError,
        ):
            # The live fold succeeded, so this re-fold on a strictly-simpler
            # (un-notched) body is essentially unreachable; if it ever fails we leave
            # the clean reference WITHOUT this bend (provenance from the live build)
            # rather than crash — the unfold then reports an honest
            # ``subshape_unresolved`` for this bend, never a 500 (§5 degradation).
            clean_result = result
    state.bend_provenance[item.id] = BendProvenance(
        cyl_signature=clean_result.cyl_signature,
        base_face_signature=clean_result.base_face_signature,
        k_factor=k_factor,
    )
    return None


def _evaluate_sheet_metal_edge_flange(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Fold a flange off a base-flange edge and fuse it across a bend (§4.2).

    Body-modifying (design §7.6): it needs a prior sheet body with recorded
    sheet-metal defaults. Delegates the resolve/build/record steps to
    :func:`_fold_flange_off_edge` (shared with the hem), passing the picked edge +
    the per-feature ``flange_length_mm`` / ``bend_angle_deg`` and the inherited
    radius/K overrides. See that helper for the typed error contract.
    """
    feature = item.feature
    assert isinstance(feature, SheetMetalEdgeFlangeFeature), (
        "registry dispatches on type='sheet_metal_edge_flange'"
    )
    params = feature.params
    return _fold_flange_off_edge(
        item,
        state,
        params.edge,
        flange_length_mm=params.flange_length_mm,
        bend_angle_deg=params.bend_angle_deg,
        override_radius_mm=params.bend_radius_mm,
        override_k_factor=params.k_factor,
        subject="An edge flange",
        width_mm=params.width_mm,
        offset_mm=params.offset_mm if params.offset_mm is not None else 0.0,
    )


def _evaluate_sheet_metal_hem(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Fold a ~180 deg hem — closed or open — off a base-flange edge (parity §2).

    A hem is an edge flange at a FIXED 180 deg fold (parity §2 / §1): the picked
    edge folds back onto the sheet, forming a doubled, safe edge. Delegates to
    :func:`_fold_flange_off_edge` with ``bend_angle_deg = 180`` and the hem's
    ``length_mm`` as the developed return length — no new kernel geometry code. The
    bend is tagged with a :class:`CylindricalFaceSignature` (§5) so the unfold
    develops it as any bend (BA = pi * (radius + K * thickness)); its bend-table row
    reads angle 180 deg.

    **The radius comes from the hem TYPE and the part's GAUGE, never from the base
    flange's general bend radius** (HEM-1 — see ``resolve_hem_bend_radius_mm``). The
    fold's cross-section makes the air gap between the two layers exactly
    ``2 * radius``, so inheriting the part's 3 mm die-bend radius on 2 mm sheet
    built a 6 mm gap labelled "closed". Two typed refusals guard the label:

    * ``hem_type_radius_conflict`` — an explicit ``bend_radius_mm`` that describes
      the OTHER hem type. Refused, not ignored and not clamped: an ignored field is
      the ``extra="ignore"`` defect class, and a clamped one is the same lie in the
      other direction.
    * ``hem_gap_degenerate`` — a radius so small the resulting gap is at or below
      the kernel's linear tolerance, i.e. the two layers are the SAME PLACE to this
      kernel and the body carries a zero-width slit (measured: at ``r = 1e-6`` the
      fold builds a BRepCheck-valid solid that
      :func:`geometry.kernel.degenerate.find_zero_width_slits` reports as degenerate;
      the slit disappears at a gap of ``KERNEL_LINEAR_TOL_MM``). Same posture as
      ``find_zero_width_slits``/``removal_reaches_body`` (RESEARCH §9): detect,
      degrade to a typed error naming the fix, never ship the cracked body. The
      check is arithmetic on the resolved radius, so it fires BEFORE the kernel
      spends a fuse on a body that must be thrown away.
    """
    feature = item.feature
    assert isinstance(feature, SheetMetalHemFeature), (
        "registry dispatches on type='sheet_metal_hem'"
    )
    params = feature.params

    def _hem_radius(defaults: SheetMetalDefaults) -> float | FeatureError:
        try:
            radius = resolve_hem_bend_radius_mm(
                params.hem_type, defaults.thickness_mm, params.bend_radius_mm
            )
        except HemRadiusError as exc:
            return FeatureError(code="hem_type_radius_conflict", message=str(exc))
        if 2.0 * radius <= KERNEL_LINEAR_TOL_MM:
            return FeatureError(
                code="hem_gap_degenerate",
                message=(
                    f"A {radius:g} mm hem radius folds the return to within "
                    f"{2 * radius:g} mm of the parent face, which is at or below "
                    f"this kernel's {KERNEL_LINEAR_TOL_MM:g} mm linear tolerance — "
                    f"the two layers would be one degenerate, zero-width slit "
                    f"rather than a hem. Use a larger bend radius (a closed hem on "
                    f"{defaults.thickness_mm:g} mm sheet folds at "
                    f"{HEM_CLOSED_RADIUS_RATIO * defaults.thickness_mm:g} mm)."
                ),
            )
        return radius

    return _fold_flange_off_edge(
        item,
        state,
        params.edge,
        flange_length_mm=params.length_mm,
        bend_angle_deg=180.0,
        override_radius_mm=None,
        override_k_factor=params.k_factor,
        subject="A hem",
        radius_rule=_hem_radius,
    )


def _resolve_relief_bend(
    ref: FeatureRef, state: EvaluationState, *, slot: str
) -> BendProvenance | FeatureError:
    """Resolve a corner-relief bend FeatureRef to its recorded bend provenance (§5).

    A corner relief names each bend by the earlier edge-flange feature that CREATED
    it (documents enforces the ``sheet_metal_edge_flange`` slot rule at write time;
    geometry re-checks because it must not trust callers). The provenance dict holds
    only edge flanges evaluated ``ok`` in this prefix, so a self / forward / rolled-
    back / non-edge-flange ref all MISS the same way — one honest
    ``reference_unresolved`` pinned to the referenced id (§4.3). *slot* names the
    failing bend in the message.
    """
    prov = state.bend_provenance.get(ref.feature_id)
    if prov is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                f"Corner-relief {slot} must reference an earlier edge-flange feature "
                "of this tree whose bend was built successfully; the referenced "
                "feature is not a resolved sheet-metal bend."
            ),
            upstream_feature_id=ref.feature_id,
        )
    return prov


def _evaluate_sheet_metal_corner_relief(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Cut a rectangular corner relief at two adjacent flanges' corner (§4.4).

    Body-modifying (design §7.6): it needs a prior sheet body with recorded
    sheet-metal defaults (gauge, for the ratio sizing) and the two named bends'
    provenance. Resolves each bend FeatureRef to its recorded
    :class:`CylindricalFaceSignature` (:func:`_resolve_relief_bend`), sizes the notch
    (``size_mm`` override, else ``relief_ratio * thickness`` — §4.4.3), builds the
    geometry-side :class:`CornerRelief`, and cuts the 3D notch.

    **Resolution vs. cut are decoupled (§4.4.4) — this is what lets ALL FOUR corners
    of a pan relieve.** Every bend signature is resolved against the CLEAN,
    un-notched reference body (:attr:`EvaluationState.sheet_metal_unfold_body`,
    maintained by the folds — all bends, no notches) via
    :func:`corner_relief_tools`, then the notch tool is cut from the LIVE active body
    via :func:`cut_relief_tools`. A relief that SHARES a flange with an earlier relief
    therefore still resolves: an earlier notch shortens the shared flange's bend
    cylinder and shifts its centroid past the signature match tolerance, so resolving
    against the live (already-notched) body would miss that shared bend — resolving
    against the un-notched reference sidesteps it, and the cuts stack on the live
    body (disjoint corner bites at opposite ends of the shared flange). The SAME relief
    spec is recorded on ``state`` so the flat-pattern unfold — which also resolves
    against that clean reference — develops the matching relieved blank; the fold-back
    guarantee (§4.4.4) holds through the real pipeline, not just the unit test. The
    clean reference is NOT mutated here (the relief cuts only the live body), so it
    keeps serving every later relief and the unfold regardless of feature ordering.

    Every failure is a TYPED per-feature error (never a raw kernel exception or a
    wrong body — §4.4/§5): no prior body (``no_prior_body``), no sheet-metal defaults
    (``no_base_flange``), a bend ref that no longer resolves
    (``reference_unresolved``), a bend signature that no longer matches the reference
    (``subshape_unresolved`` / ``subshape_ambiguous``), or a relief that cannot apply
    — parallel/non-perpendicular bends, an axis-unaligned corner, or a cut that
    severs the sheet (``corner_relief_failed``). The active body + the recorded
    relief set are mutated only on success (last-good semantics, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, SheetMetalCornerReliefFeature), (
        "registry dispatches on type='sheet_metal_corner_relief'"
    )
    params = feature.params

    active = state.active_body
    if active is None or state.active_body_id is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "A corner relief requires an existing sheet body, but no "
                "body-affecting feature precedes it; add a base flange and edge "
                "flanges first."
            ),
        )
    defaults = state.sheet_metal_defaults.get(state.active_body_id)
    if defaults is None:
        return FeatureError(
            code="no_base_flange",
            message=(
                "A corner relief needs the part's sheet-metal gauge (from a base "
                "flange) to size its notch, but the active body is not a sheet-metal "
                "base flange."
            ),
        )

    prov_a = _resolve_relief_bend(params.bend_a, state, slot="bend_a")
    if isinstance(prov_a, FeatureError):
        return prov_a
    prov_b = _resolve_relief_bend(params.bend_b, state, slot="bend_b")
    if isinstance(prov_b, FeatureError):
        return prov_b

    size = (
        params.size_mm
        if params.size_mm is not None
        else params.relief_ratio * defaults.thickness_mm
    )
    relief = CornerRelief(
        bend_a=prov_a.cyl_signature,
        bend_b=prov_b.cyl_signature,
        size_mm=size,
        relief_type=params.relief_type,
    )

    # Resolve the notch tools against the CLEAN un-notched reference (all bends, no
    # notches — maintained by the folds), then cut them from the LIVE body. A resolved
    # bend implies a fold ran, which set the clean reference, so it is non-None here;
    # guard it as a typed error rather than assume (never a crash).
    reference = state.sheet_metal_unfold_body
    if reference is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "A corner relief needs the sheet body's bends (from edge flanges) to "
                "resolve its named corner, but no bend has been folded yet; add edge "
                "flanges first."
            ),
        )
    try:
        tools = corner_relief_tools(reference, relief)
        relieved = cut_relief_tools(active, [tools])
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))
    except CornerReliefError as exc:
        return FeatureError(code="corner_relief_failed", message=str(exc))

    # The clean reference is NOT mutated — the relief cuts only the LIVE body, so the
    # reference keeps ALL bends and NO notches for every later relief + the unfold.
    state.set_active_body(relieved)
    state.corner_reliefs[item.id] = relief
    return None
