"""Modify features: fillet, chamfer, shell and draft.

Each resolves picked edges or faces on the ACTIVE body and replaces that body
with the result. None starts a body or records a reflectable tool, which is why
a ``features``-scope mirror refuses them (mirror-semantics §4.3).
"""

from loft_wire.features import (
    ChamferFeature,
    DraftFeature,
    EvaluatedFeatureInput,
    FeatureError,
    FilletFeature,
    ShellFeature,
)

from geometry.features.naming_hooks import (
    edge_blend_names,
    edge_sources,
    face_sources,
    offset_names,
    tilted_face_names,
)
from geometry.features.state import (
    EvaluationState,
)
from geometry.kernel import (
    ChamferError,
    DraftError,
    FilletError,
    NoEdgesSelectedError,
    ShellError,
    ShellThicknessError,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    build_datum_plane,
    chamfer_body,
    draft_body,
    fillet_body,
    resolve_faces,
    select_edges,
    shell_body,
)
from geometry.kernel.naming import OpHistory
from geometry.kernel.shell import offset_history


def _evaluate_fillet(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Round selected edges of the current body chain (body-affecting, §4.3).

    Fillet operates on the implicit single body (design §7.6), so it needs a
    prior body-affecting feature (``no_target_body`` otherwise). Edges are
    resolved by the geometric selector (design §2.4 — NOT topological naming):
    an empty match is ``no_fillet_edges``; a kernel failure is
    ``fillet_failed``. the active body is only replaced on success (strict-prefix
    rule tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, FilletFeature), "registry dispatches on type='fillet'"
    params = feature.params

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Fillet requires an existing body, but no body-affecting "
                "feature precedes this one; add an extrude first."
            ),
        )

    names = state.face_names()
    try:
        edges = select_edges(
            active, params.edges, tally=state.subshape_tally, face_names=names
        )
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_fillet_edges", message=str(exc))
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    history, sources = OpHistory(), edge_sources(active, names, edges)
    try:
        filleted = fillet_body(active, edges, params.radius_mm, history=history)
    except FilletError as exc:
        return FeatureError(code="fillet_failed", message=str(exc))
    state.set_active_body(
        filleted,
        edge_blend_names(item.id, "fillet", history, sources),
        worked_on=history.worked_on,
    )
    return None


def _evaluate_chamfer(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Bevel selected edges of the current body chain (body-affecting, §4.3).

    The chamfer sibling of :func:`_evaluate_fillet` — same shape, same edge
    plumbing (:func:`select_edges`, design §2.4), same single-body requirement
    (``no_target_body`` otherwise, design §7.6). An empty match is
    ``no_chamfer_edges``; a kernel failure is ``chamfer_failed``. The active body
    is only replaced on success (strict-prefix rule tessellates the last-good
    body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, ChamferFeature), "registry dispatches on type='chamfer'"
    params = feature.params

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_target_body",
            message=(
                "Chamfer requires an existing body, but no body-affecting "
                "feature precedes this one; add an extrude first."
            ),
        )

    names = state.face_names()
    try:
        edges = select_edges(
            active, params.edges, tally=state.subshape_tally, face_names=names
        )
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_chamfer_edges", message=str(exc))
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    history, sources = OpHistory(), edge_sources(active, names, edges)
    try:
        chamfered = chamfer_body(active, edges, params.distance_mm, history=history)
    except ChamferError as exc:
        return FeatureError(code="chamfer_failed", message=str(exc))
    state.set_active_body(
        chamfered, edge_blend_names(item.id, "chamfer", history, sources)
    )
    return None


def _evaluate_shell(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Hollow the current body to a uniform wall, opening picked faces (§4.3).

    Shell modifies the implicit single body (design §7.6), so it needs a prior
    body-affecting feature (``no_prior_body`` otherwise). The faces to REMOVE
    (leave open) are resolved by the picked-FACE resolver
    (:func:`resolve_faces` — the SAME stage-1 planar-face signature the
    ``on_face`` datum uses, NOT a parallel taxonomy): a ref that no longer
    resolves is ``subshape_unresolved``, a congruent twin ``subshape_ambiguous``.
    An EMPTY faces list is a valid sealed (fully-enclosed) hollow — never an
    error. A thickness that collapses the cavity is ``shell_thickness_too_large``
    (OCCT's silent too-thick path, caught by the material-removed invariant); a
    kernel offset failure is ``shell_failed`` (belt-and-braces). The active body
    is only replaced on success (strict-prefix rule tessellates the last-good
    body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, ShellFeature), "registry dispatches on type='shell'"
    params = feature.params

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Shell requires an existing body, but no body-affecting feature "
                "precedes this one; add a feature that creates a body first."
            ),
        )

    try:
        faces = resolve_faces(
            active,
            [ref.selector.signature for ref in params.faces.refs],
            tally=state.subshape_tally,
            face_names=state.face_names(),
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    sources = face_sources(active, state.face_names())
    try:
        shelled = shell_body(active, faces, params.thickness_mm)
    except ShellThicknessError as exc:
        return FeatureError(code="shell_thickness_too_large", message=str(exc))
    except ShellError as exc:
        return FeatureError(code="shell_failed", message=str(exc))
    # Each inner wall is named from the face it offsets (DESIGN-INTENT-REFS
    # step 3): ``<shell id>:offset:<that face's name>``.
    history = OpHistory(
        generated=[*offset_history(active, shelled, params.thickness_mm)]
    )
    state.set_active_body(shelled, offset_names(item.id, history, sources))
    return None


def _evaluate_draft(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Taper picked faces of the current body by a constant angle (§4.3).

    Draft modifies the implicit single body (design §7.6), so it needs a prior
    body-affecting feature (``no_prior_body`` otherwise). The faces to TAPER are
    resolved by the picked-FACE resolver (:func:`resolve_faces` — the SAME
    stage-1 planar-face signature shell / the ``on_face`` datum use, NOT a
    parallel taxonomy): a ref that no longer resolves is ``subshape_unresolved``,
    a congruent twin ``subshape_ambiguous``. Unlike shell, an EMPTY selection has
    nothing to taper → ``no_draft_faces`` (draft is not a no-op). The neutral
    plane (the fixed plane, whose normal is the pull direction) is built from a
    principal datum through the SAME :func:`build_datum_plane` an offset datum
    uses (no picked geometry — independent of topological naming). A kernel draft
    failure (angle too large / undraftable face — OCCT RAISES, never a silent bad
    body) is ``draft_failed``. the active body is only replaced on success
    (strict-prefix rule tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, DraftFeature), "registry dispatches on type='draft'"
    params = feature.params

    active = state.active_body
    if active is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Draft requires an existing body, but no body-affecting feature "
                "precedes this one; add a feature that creates a body first."
            ),
        )

    try:
        faces = resolve_faces(
            active,
            [ref.selector.signature for ref in params.faces.refs],
            tally=state.subshape_tally,
            face_names=state.face_names(),
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    if not faces:
        return FeatureError(
            code="no_draft_faces",
            message=(
                "Draft must taper at least one face, but the picked-face "
                "selection is empty; pick the faces to taper."
            ),
        )

    neutral = build_datum_plane(
        params.neutral_plane.base,
        params.neutral_plane.offset_mm,
        params.neutral_plane.flip,
    )
    history = OpHistory()
    sources = face_sources(active, state.face_names())
    try:
        drafted = draft_body(active, faces, neutral, params.angle_deg, history=history)
    except DraftError as exc:
        return FeatureError(code="draft_failed", message=str(exc))
    state.set_active_body(drafted, tilted_face_names(history, sources))
    return None
