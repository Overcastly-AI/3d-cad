"""Datum planes and sketches: the features that produce INPUT geometry.

Neither is body-affecting (§4.3). This module also owns the resolvers their
consumers share: a sketch's plane (:func:`resolve_sketch_plane`), a picked planar
face as a plane (the ``on_face`` datum, midplane sides and the Hole's placement
face), and a solved sketch's closed profile as a kernel face (extrude, revolve,
sweep and the sheet-metal base flange).
"""

import uuid

from build123d import Face, Plane
from loft_wire.features import (
    DatumAlongPathParams,
    DatumAngleParams,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumOnFaceParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    FeatureError,
    FeatureRef,
    SketchFeature,
    SubshapeRef,
)
from loft_wire.resolution_tiers import SUBSHAPE_RESOLUTION_TIERS
from loft_wire.sketch import classify_overconstraint

from geometry.features.datum_angle import resolve_angle_plane
from geometry.features.pipe import resolve_along_path_plane
from geometry.features.sketch_projection import project_entities
from geometry.features.state import (
    EvaluationState,
)
from geometry.kernel import (
    DATUM_PLANES,
    ProfileNotClosedError,
    ProfileUnsupportedError,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    build_datum_plane,
    build_profile_face,
    build_profile_faces,
    face_match_tier,
    midplane_between,
    offset_plane,
    resolve_face_plane,
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


def resolve_sketch_plane(
    ref: DatumPlaneRef | FeatureRef, state: EvaluationState
) -> Plane | FeatureError:
    """Map a sketch's plane reference to one concrete :class:`~build123d.Plane`.

    The DRY funnel (docs/design/datum-planes.md §3a): a :class:`DatumPlaneRef`
    (one of the three origin datums) maps by name through :data:`DATUM_PLANES`;
    a :class:`FeatureRef` resolves to a ``datum`` feature's plane recorded
    earlier in this pass. Every downstream builder (profile/path/loft rail,
    revolve axis) takes the resolved plane, so the name→Plane lookup lives here
    once instead of per caller. A FeatureRef that does not resolve to a datum
    plane of this prefix (defined later, deleted, rolled back, or a non-datum
    feature) is a ``reference_unresolved`` error pinned to the referenced
    feature (§6) — documents rejects it at write time, but geometry re-checks
    because it must not trust its callers.
    """
    if isinstance(ref, DatumPlaneRef):
        return DATUM_PLANES[ref.plane]
    return _resolve_datum_feature_plane(ref, state, role="Sketch plane")


def _resolve_datum_feature_plane(
    ref: FeatureRef, state: EvaluationState, *, role: str
) -> Plane | FeatureError:
    """Resolve a FeatureRef to an EARLIER ``datum`` feature's resolved plane.

    The one datum-feature lookup every plane-consuming slot funnels through
    (sketch plane, chained-offset base, midplane side — CLAUDE.md DRY rule):
    ``state.datum_planes`` holds ONLY the datums already evaluated ``ok`` in
    this prefix, so a self reference, a forward reference, a rolled-back /
    deleted datum, or a non-datum target all MISS the same way — one honest
    ``reference_unresolved`` pinned to the referenced id, and structurally NO
    recursion (a dict lookup of an already-resolved plane; datum-planes §6/§7).
    Documents rejects these at write time (strict-backward + the slot's
    ``allowed_types``); geometry re-checks because it must not trust callers.
    *role* names the failing slot in the message.
    """
    plane = state.datum_planes.get(ref.feature_id)
    if plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                f"{role} must reference an earlier datum feature of this "
                "tree; the referenced feature is not a resolved datum plane."
            ),
            upstream_feature_id=ref.feature_id,
        )
    return plane


def face_owner_body_id(
    face: SubshapeRef, state: EvaluationState
) -> uuid.UUID | FeatureError | None:
    """The id of the body that OWNS the picked *face* (HOLE-ACTIVE-BODY).

    A stored face reference carries a signature, not a body: its ``feature_id``
    is the tip body feature at pick time (``anchorBodyFeatureId``), whichever
    body the face was on. Fusion 360 and SolidWorks cut the body the picked face
    belongs to, so the owner is found by matching the signature against EVERY
    body (tree order) at the resolver's own tiers (:func:`face_match_tier`):

    * the body matching at the most certain tier owns the face — an exact match
      on an earlier member beats a resilient (``durable``) one on the active
      member, which is precisely the congruent-stud wrong cut this closes;
    * a tie at that tier keeps the ACTIVE body when it is among the tied (the
      pre-fix answer, so no reference that resolved on the active body moves),
      and is otherwise an honest ``subshape_ambiguous`` across bodies;
    * no body matching at all falls back to the active body, so the face then
      fails exactly as it always did (``subshape_unresolved``).

    A single-body part never scans: its one body is the active body, which
    keeps every single-body rebuild byte-identical. ``None`` with no body.
    """
    active_id = state.active_body_id
    if active_id is None or len(state.bodies) == 1:
        return active_id
    target = face.selector.signature
    ranked: dict[uuid.UUID, int] = {}
    for body_id, body in state.bodies.items():
        tier = face_match_tier(body, target, state.body_face_names(body_id))
        if tier is not None:
            ranked[body_id] = SUBSHAPE_RESOLUTION_TIERS.index(tier)
    if not ranked:
        return active_id
    best = min(ranked.values())
    tied = [body_id for body_id, rank in ranked.items() if rank == best]
    if active_id in tied:
        return active_id
    if len(tied) == 1:
        return tied[0]
    return FeatureError(
        code="subshape_ambiguous",
        message=(
            f"The picked face matches a face on {len(tied)} different bodies "
            "equally well, so the body it belongs to is ambiguous. Refusing to "
            "guess; re-pick the face."
        ),
        upstream_feature_id=face.feature_id,
    )


def _resolve_face_datum_plane(
    face: SubshapeRef,
    offset_mm: float,
    state: EvaluationState,
    *,
    body_id: uuid.UUID | None = None,
) -> Plane | FeatureError:
    """Resolve a stage-1 face reference to the face's (offset) sketch plane.

    The shared face half of the datum resolvers (``on_face`` datum + midplane
    face sides — one taxonomy, datum-planes §7): no prior body, or a signature
    that no longer matches, is ``subshape_unresolved``; a congruent twin is
    ``subshape_ambiguous`` (refuse to guess — determinism, topo-naming §7.2).
    Errors pin the named body feature as the upstream cause. The face is
    resolved on the active body, or on body *body_id* when given (the owner
    :func:`face_owner_body_id` found).
    """
    if body_id is None:
        body_id = state.active_body_id
    active = None if body_id is None else state.bodies[body_id]
    if active is None or body_id is None:
        return FeatureError(
            code="subshape_unresolved",
            message=(
                "This datum references a face of the current body, but no "
                "body-affecting feature precedes it; add a feature that creates "
                "a body before referencing a face."
            ),
            upstream_feature_id=face.feature_id,
        )
    try:
        return resolve_face_plane(
            active,
            face.selector.signature,
            offset_mm,
            tally=state.subshape_tally,
            face_names=state.body_face_names(body_id),
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(
            code="subshape_unresolved",
            message=str(exc),
            upstream_feature_id=face.feature_id,
        )
    except SubshapeAmbiguousError as exc:
        return FeatureError(
            code="subshape_ambiguous",
            message=str(exc),
            upstream_feature_id=face.feature_id,
        )


def _resolve_plane_side(
    ref: DatumPlaneRef | FeatureRef | SubshapeRef, state: EvaluationState, *, role: str
) -> Plane | FeatureError:
    """Resolve one midplane side (or an angle datum's reference) to a plane.

    Datum-planes §7a; the ``angle`` datum's reference takes the same three
    forms, so it resolves here too (*role* names the slot in the message).

    Reuses the existing funnels — an origin datum name maps through
    :data:`DATUM_PLANES`, a ``datum`` FeatureRef through
    :func:`_resolve_datum_feature_plane`, a picked planar face through
    :func:`_resolve_face_datum_plane` (offset 0: the side IS the face's plane)
    — so a midplane introduces no new reference semantics, only a new consumer.
    """
    if isinstance(ref, DatumPlaneRef):
        return DATUM_PLANES[ref.plane]
    if isinstance(ref, FeatureRef):
        return _resolve_datum_feature_plane(ref, state, role=role)
    assert isinstance(ref, SubshapeRef)  # closed union
    return _resolve_face_datum_plane(ref, 0.0, state)


def _evaluate_datum(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Resolve one datum plane — offset, on-face, chained, midplane, angle or
    along a path.

    Not body-affecting: whatever the kind, the resolved plane is recorded under
    the feature id for a later consumer (a sketch's plane FeatureRef, another
    datum's base, a midplane side) to resolve against. Per kind
    (docs/design/datum-planes.md §3/§7/§7a):

    * ``offset`` — an origin datum slid ``offset_mm`` along its normal with an
      optional ``flip``; TOTAL, never errors (a non-finite offset is a
      parse-time 422).
    * ``offset_from`` — an EARLIER datum feature's resolved plane slid along
      ITS normal (chaining). The only failure is the base reference: a self /
      forward / missing / non-datum base is ``reference_unresolved`` (a dict
      miss — never a recursion). Given a resolved base it is as total as
      ``offset``.
    * ``on_face`` — adopts the plane of a PLANAR face of the CURRENT body,
      named by a stage-1 :class:`SubshapeRef` signature, plus an optional
      offset; fails ``subshape_unresolved`` / ``subshape_ambiguous``
      (:func:`_resolve_face_datum_plane`).
    * ``midplane`` — bisects two resolved side planes
      (:func:`midplane_between`, the documented parallel/angular/identical
      conventions). TOTAL over resolved sides; each side fails with its own
      funnel's taxonomy (:func:`_resolve_plane_side`).
    * ``angle`` — a plane through a line, turned from a reference plane
      (:func:`~geometry.features.datum_angle.resolve_angle_plane`); the
      reference resolves like a midplane side, the line through its own
      typed funnel.
    * ``along_path`` — a plane normal to a picked curve at a point along it
      (:func:`~geometry.features.pipe.resolve_along_path_plane`).
    """
    feature = item.feature
    assert isinstance(feature, DatumFeature), "registry dispatches on type='datum'"
    params = feature.params
    if isinstance(params, DatumOffsetParams):
        state.datum_planes[item.id] = build_datum_plane(
            params.base, params.offset_mm, params.flip
        )
        return None

    if isinstance(params, DatumOffsetFromParams):
        parent = _resolve_datum_feature_plane(
            params.base, state, role="Offset-plane base"
        )
        if isinstance(parent, FeatureError):
            return parent
        state.datum_planes[item.id] = offset_plane(
            parent, params.offset_mm, params.flip
        )
        return None

    if isinstance(params, DatumMidplaneParams):
        side_a = _resolve_plane_side(params.a, state, role="Midplane side 'a'")
        if isinstance(side_a, FeatureError):
            return side_a
        side_b = _resolve_plane_side(params.b, state, role="Midplane side 'b'")
        if isinstance(side_b, FeatureError):
            return side_b
        state.datum_planes[item.id] = midplane_between(side_a, side_b, params.flip)
        return None

    if isinstance(params, DatumAngleParams):
        reference = _resolve_plane_side(
            params.reference, state, role="Plane-at-angle reference"
        )
        if isinstance(reference, FeatureError):
            return reference
        angled = resolve_angle_plane(params, reference, state)
        if isinstance(angled, FeatureError):
            return angled
        state.datum_planes[item.id] = angled
        return None

    if isinstance(params, DatumAlongPathParams):
        along = resolve_along_path_plane(params, state)
        if isinstance(along, FeatureError):
            return along
        state.datum_planes[item.id] = along
        return None

    assert isinstance(params, DatumOnFaceParams)  # closed union
    plane = _resolve_face_datum_plane(params.face, params.offset_mm, state)
    if isinstance(plane, FeatureError):
        return plane
    state.datum_planes[item.id] = plane
    return None


def _evaluate_sketch(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Solve one sketch feature (not body-affecting, §4.3).

    Solver *outcomes* follow the ``SketchSolver`` contract: statuses that
    carry a solved model (converged / underconstrained / consistent
    overconstrained) are ``ok`` — the diagnosis rides in the solved payload
    for the sketcher UI (§7.10) — while statuses with no usable solution
    (conflicting / diverged) map to per-feature errors, never exceptions.

    The sketch's plane reference (an origin datum or a ``datum`` feature) is
    resolved to a concrete plane through :func:`resolve_sketch_plane` FIRST — a
    bad plane reference is a ``reference_unresolved`` error before the solve.
    Then every projected entity is re-projected from the body at this tree
    position (:func:`~geometry.features.sketch_projection.project_entities`);
    a sick one keeps its stored coordinates and is reported in the payload's
    ``projections``, never as an error (Fusion 360's sick projection).
    """
    feature = item.feature
    assert isinstance(feature, SketchFeature), "registry dispatches on type='sketch'"

    plane = resolve_sketch_plane(feature.params.plane, state)
    if isinstance(plane, FeatureError):
        return plane

    # Projected entities follow their body edges BEFORE the solve, so what
    # hangs off them follows too; one that cannot is sick, never an error.
    params, projections = project_entities(feature.params, plane, state)

    try:
        # SketchParamsV1 extends SketchDefinition (py-kit): the validated
        # params ARE the solver input — statically-malformed sketches never
        # reach this point, they are 422 request-validation failures (§4.3:
        # the envelope owns transport/validation failures of the call).
        solved = _SOLVER.solve(params)
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
            sketch_diagnosis=classify_overconstraint(solved),
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
    if projections:
        state.sketch_projections[item.id] = projections
    return None


def _resolve_solved_profile(
    profile: FeatureRef, state: EvaluationState
) -> tuple[Plane, SolvedSketch] | FeatureError:
    """Resolve a profile FeatureRef to its ``(plane, solved sketch)``.

    The reference-resolution front half shared by :func:`_resolve_profile_face`
    (single region — add/revolve/loft/sweep) and :func:`_resolve_profile_faces`
    (N disjoint cut regions — CLAUDE.md DRY rule): it re-checks the §2.2
    reference rule (documents enforces it at write time; geometry must not trust
    its callers). Anything not an ok sketch of this prefix (unknown id,
    non-sketch feature, or a sketch the strict-prefix rule never reached)
    resolves to a ``reference_unresolved`` error pinned to the upstream id.
    """
    profile_id = profile.feature_id
    solved = state.solved_sketches.get(profile_id)
    plane = state.sketch_planes.get(profile_id)
    if solved is None or plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                "Profile must reference an earlier successfully solved sketch "
                "feature of this tree."
            ),
            upstream_feature_id=profile_id,
        )
    return plane, solved


def _profile_build_error(exc: Exception, profile_id: uuid.UUID) -> FeatureError:
    """Map a profile-builder exception onto its per-feature error code.

    Single mapping point (CLAUDE.md DRY rule) for both profile resolvers:
    ``ProfileNotClosedError``/``ProfileUnsupportedError`` from the shared
    profile builders become per-feature errors pinned to the upstream sketch.
    """
    if isinstance(exc, ProfileNotClosedError):
        return FeatureError(
            code="profile_not_closed", message=str(exc), upstream_feature_id=profile_id
        )
    assert isinstance(exc, ProfileUnsupportedError)
    return FeatureError(
        code="profile_unsupported", message=str(exc), upstream_feature_id=profile_id
    )


def _resolve_profile_face(
    profile: FeatureRef, state: EvaluationState
) -> tuple[Face, Plane, SolvedSketch] | FeatureError:
    """Resolve a profile FeatureRef to its ``(face, plane, solved sketch)``.

    The shared front half of every SINGLE-region body-affecting feature that
    consumes a sketch profile (extrude-add, revolve, loft, sweep — CLAUDE.md DRY
    rule): reference-resolves through :func:`_resolve_solved_profile`, then
    builds the single closed profile face through the shared
    :func:`build_profile_face` (construction geometry excluded there). Disjoint
    loops are a multi-body sketch and stay a ``profile_unsupported`` error here
    — the multi-region relaxation is CUT-only (:func:`_resolve_profile_faces`).
    """
    resolved = _resolve_solved_profile(profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    plane, solved = resolved
    try:
        face = build_profile_face(plane, solved.entities)
    except (ProfileNotClosedError, ProfileUnsupportedError) as exc:
        return _profile_build_error(exc, profile.feature_id)
    return face, plane, solved


def _resolve_profile_faces(
    profile: FeatureRef, state: EvaluationState
) -> tuple[list[Face], Plane] | FeatureError:
    """Resolve a profile FeatureRef to its ``(region faces, plane)`` for a CUT.

    The multi-region sibling of :func:`_resolve_profile_face`, used ONLY by the
    subtractive extrude path (§4.3): N disjoint closed loops resolve to N
    independent removal regions through :func:`build_profile_faces` — no shared
    outer boundary required. A single-region sketch (one loop, or one outer
    boundary + interior holes) resolves to a one-element list byte-identical to
    the single-face path, so the plate-with-holes cut is unchanged.
    """
    resolved = _resolve_solved_profile(profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    plane, solved = resolved
    try:
        faces = build_profile_faces(plane, solved.entities)
    except (ProfileNotClosedError, ProfileUnsupportedError) as exc:
        return _profile_build_error(exc, profile.feature_id)
    return faces, plane
