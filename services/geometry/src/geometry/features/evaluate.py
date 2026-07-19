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
``datum`` (resolves an offset/parallel plane a later sketch sits on — not
body-affecting, total; docs/design/datum-planes.md), ``sketch`` (produces
input geometry, not body-affecting), ``extrude`` (the
first **body-affecting** feature, §4.3 — mutates the part's active body
via add/cut booleans; an additive ``merge=False`` starts a second body,
docs/design/multi-body.md §MB-0), ``revolve`` (sweeps a profile about a sketch-line
axis, sharing extrude's profile + boolean plumbing), ``sweep`` (the first
non-prismatic feature — sweeps a profile along a SECOND sketch's open path
wire), ``loft`` (blends a solid through two or more ordered section sketches),
``fillet`` (rounds
selected edges of that body chain), ``chamfer`` (bevels selected edges; both
body-affecting and both resolving edges through the shared geometric selector)
and ``shell`` (hollows the body to a uniform wall, opening picked faces resolved
through the SAME stage-1 planar-face signature the ``on_face`` datum uses) and
``draft`` (tapers picked faces by an angle about a principal-datum neutral plane
— the molding/casting release, reusing that SAME picked-face resolver) and
``import`` (brings an external STEP part in as the part's BASE body — the first
non-modeled body source, docs/design/step-import.md) and ``boolean`` (combines two
independently-built bodies named by their base features — the headline
multi-body feature; union/subtract/intersect all wired, docs/design/multi-body.md
§MB-1/§MB-2).
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

from build123d import Compound, Face, Plane, Solid, Vertex, Wire
from py_kit.errors import ValidationApiError
from py_kit.schemas.features import (
    BooleanFeature,
    ChamferFeature,
    CircularPatternParamsV1,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumOnFaceParams,
    DatumPlaneRef,
    DraftFeature,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureData,
    FeatureEnvelope,
    FeatureError,
    FeatureRef,
    FeatureResult,
    FilletFeature,
    ImportFeature,
    LinearPatternParamsV1,
    LoftFeature,
    PatternFeature,
    PatternGeometry,
    RevolveFeature,
    SheetMetalBaseFlangeFeature,
    SheetMetalEdgeFlangeFeature,
    ShellFeature,
    SketchFeature,
    SolvedSketchData,
    SubshapeRef,
    SweepFeature,
)
from py_kit.schemas.geometry import MeshStats, ShapeProperties
from py_kit.schemas.sketch import classify_overconstraint

from geometry.kernel import (
    DATUM_PLANES,
    AxisIntersectsProfileError,
    BooleanDisjointError,
    BooleanEmptyError,
    BooleanError,
    ChamferError,
    DraftError,
    FilletError,
    ImportNoSolidError,
    ImportParseError,
    ImportParseTimeoutError,
    LoftError,
    NoAxisError,
    NoEdgesSelectedError,
    PathClosedError,
    PathEmptyError,
    PathNotConnectedError,
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
    ShellError,
    ShellThicknessError,
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    SweepError,
    boolean_bodies,
    build_datum_plane,
    build_loft_section,
    build_path_wire,
    build_profile_face,
    build_profile_faces,
    chamfer_body,
    check_axis_clears_profile,
    circular_pattern,
    circular_pattern_cut,
    combine_body,
    combine_properties,
    draft_body,
    extrude_face,
    fillet_body,
    linear_pattern,
    linear_pattern_cut,
    loft_sections,
    measure_shape,
    midplane_between,
    offset_plane,
    resolve_axis_line,
    resolve_edge,
    resolve_face_plane,
    resolve_faces,
    revolve_face,
    select_edges,
    shell_body,
    sweep_profile,
    tessellate_glb,
)
from geometry.kernel.types import BodyShape
from geometry.mesh_store import store_mesh_glb
from geometry.sheet_metal import (
    BendProvenance,
    EdgeFlangeEdgeError,
    EdgeFlangeError,
    SheetMetalDefaults,
    build_edge_flange,
)
from geometry.sketch import (
    PlanegcsSketchSolver,
    SketchDefinitionError,
    SketchSolver,
    SolvedSketch,
)
from geometry.step_cache import import_step_solid_cached

#: The solver backend, typed as the protocol (RESEARCH §2 guardrail: callers
#: never import a solver package). ``PlanegcsSketchSolver`` is stateless —
#: every solve builds a fresh system — so one shared instance is safe.
_SOLVER: SketchSolver = PlanegcsSketchSolver()


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


@dataclass
class EvaluationState:
    """Mutable state threaded through one ordered dispatch pass.

    ``solved_sketches``/``sketch_planes`` are keyed by feature id and
    insertion-ordered by evaluation order (deterministic); the extrude
    handler reads its profile from them. ``sketch_planes`` holds the RESOLVED
    :class:`~build123d.Plane` each ok sketch sits on (origin datum or offset
    ``datum`` feature — docs/design/datum-planes.md §3a), so every downstream
    builder takes a concrete plane. ``datum_planes`` holds the resolved
    :class:`~build123d.Plane` of each ok ``datum`` feature, keyed by its id, so
    a later sketch's plane FeatureRef resolves against it. All hold kernel
    types strictly service-internal (never serialized), exactly like ``bodies``.

    ``bodies`` is the part's set of solid bodies (docs/design/multi-body.md
    §MB-0): keyed by the BASE feature id that created each body and insertion-
    ordered by the tree order those base features were evaluated (deterministic,
    RESEARCH §9). A part is *implicitly one body* until an additive feature with
    ``merge=False`` (or an ``import`` after a body already exists) starts a
    second. ``active_body_id`` names the body every MODIFYING feature (fillet/
    chamfer/shell/draft/pattern, add-merge/cut) targets AND that topological
    naming resolves against — NEVER a union of all bodies (the MB-0 correctness
    rule, Decision 1): a congruent face on two coexisting bodies must not tie a
    false ``subshape_ambiguous``. ``bodies`` is mutated only by body-affecting
    handlers **on success**, so after a failure it is exactly the last-good body
    set the strict-prefix rule tessellates (§4.3).
    """

    linear_deflection: float
    solved_sketches: dict[uuid.UUID, SolvedSketch] = field(
        default_factory=dict[uuid.UUID, SolvedSketch]
    )
    sketch_planes: dict[uuid.UUID, Plane] = field(
        default_factory=dict[uuid.UUID, Plane]
    )
    datum_planes: dict[uuid.UUID, Plane] = field(default_factory=dict[uuid.UUID, Plane])
    bodies: dict[uuid.UUID, BodyShape] = field(
        default_factory=dict[uuid.UUID, BodyShape]
    )
    #: The part's sheet-metal defaults (gauge/K/bend-radius) keyed by the
    #: base-flange feature id that created the sheet body (docs/design/
    #: sheet-metal.md §4.1/§5). Recorded only on an ok base flange; the
    #: edge-flange / unfold slices read it to compute a bend allowance. Held as a
    #: service-internal record (never serialized), exactly like ``bodies``.
    sheet_metal_defaults: dict[uuid.UUID, SheetMetalDefaults] = field(
        default_factory=dict[uuid.UUID, SheetMetalDefaults]
    )
    #: The bend provenance (§5: cylindrical-face + base-face signatures + K-factor)
    #: recorded by each ok edge-flange feature, keyed by that feature id and
    #: insertion-ordered by evaluation order (deterministic). The unfold reads it to
    #: find each bend by provenance, never blind detection. Service-internal.
    bend_provenance: dict[uuid.UUID, BendProvenance] = field(
        default_factory=dict[uuid.UUID, BendProvenance]
    )
    active_body_id: uuid.UUID | None = None
    #: The immediately-preceding BODY-AFFECTING feature (tree order), updated
    #: after each ok body-affecting feature by :func:`evaluate_tree`. A pattern
    #: reads it to infer whether it should array a CUT (source = a preceding
    #: extrude-cut, BACKLOG #3) or union whole-body copies (the default). Holds a
    #: validated feature envelope — never serialized, exactly like ``bodies``.
    prev_body_feature: FeatureEnvelope | None = None

    @property
    def active_body(self) -> BodyShape | None:
        """The current shape of the ACTIVE body, or ``None`` if no body yet.

        The single read every modifying handler and the topo-naming resolvers
        use in place of the former single ``body`` slot (§MB-0). A body is a
        single :class:`~build123d.Solid` OR a multi-lump
        :class:`~build123d.Compound` (§MB-4).
        """
        if self.active_body_id is None:
            return None
        return self.bodies[self.active_body_id]

    def set_active_body(self, shape: BodyShape) -> None:
        """Replace the ACTIVE body's current shape (a modifying feature result).

        Keeps the body's identity slot (its base feature id) so downstream refs
        keep resolving; asserts an active body exists (callers gate on it). The
        shape may be a single solid or a lump-count-preserving multi-lump
        Compound (§MB-4).
        """
        assert self.active_body_id is not None, "no active body to modify"
        self.bodies[self.active_body_id] = shape

    def start_body(self, base_id: uuid.UUID, shape: BodyShape) -> None:
        """Insert a NEW body keyed by its base feature id and make it active.

        The second-body path (``merge=False`` / ``import`` / the first body): a
        body's identity IS its base feature id (§MB-0 Decision 1), so the key is
        the creating feature's id and it becomes the resolution target.
        """
        self.bodies[base_id] = shape
        self.active_body_id = base_id

    def combine_bodies(
        self, target_id: uuid.UUID, tool_id: uuid.UUID, shape: BodyShape
    ) -> None:
        """Replace two operand bodies with a boolean result (multi-body §MB-1).

        The operand-replacement mechanism of the ``boolean`` feature: the result
        TAKES OVER the target's identity slot — reusing ``bodies[target_id]``
        keeps target's base-feature id AND its tree-ordered insertion position, so
        every downstream ref to the surviving body keeps resolving — and the TOOL
        body is REMOVED from the set (consumed). The combined body becomes active.
        Callers verify both ids name distinct current bodies first. *shape* may be
        a single solid or a multi-lump Compound (a disjoint boolean, §MB-4).
        """
        self.bodies[target_id] = shape
        del self.bodies[tool_id]
        self.active_body_id = target_id


#: One feature handler: evaluate the item, record outputs on ``state``, and
#: return ``None`` on success or the per-feature error (§4.3). Geometry
#: outcomes are values, never exceptions. Handlers mutate ``state`` only on
#: the success path.
FeatureHandler = Callable[[EvaluatedFeatureInput, EvaluationState], FeatureError | None]


def _add_body(
    item: EvaluatedFeatureInput,
    state: EvaluationState,
    tool: Solid,
    *,
    merge: bool,
) -> FeatureError | None:
    """Apply an ADDITIVE body op under the multi-body merge rule (§MB-0 Dec. 2).

    ``merge=True`` with an active body fuses *tool* into it (today's single-body
    behaviour); ``merge=False``, or no active body yet, STARTS a new active body
    keyed by this feature's id (``item.id`` — the base-feature-keyed identity of
    §MB-0 Decision 1). ``state.bodies`` is mutated only on success (last-good
    semantics, §4.3). Shared by extrude/revolve/sweep/loft ADD (CLAUDE.md DRY).
    """
    if merge and state.active_body_id is not None:
        active = state.active_body
        assert active is not None
        try:
            fused = combine_body(active, tool, "add")
        except BooleanError as exc:
            return FeatureError(code="boolean_failed", message=str(exc))
        state.set_active_body(fused)
        return None
    state.start_body(item.id, tool)
    return None


def _cut_active(state: EvaluationState, tool: Solid) -> FeatureError | None:
    """Subtract *tool* from the ACTIVE body (a modifying op — §MB-0).

    The caller has already verified an active body exists (``no_prior_body``
    otherwise). ``state.bodies`` is mutated only on success (§4.3).
    """
    active = state.active_body
    assert active is not None, "cut without an active body is handled by the caller"
    try:
        state.set_active_body(combine_body(active, tool, "cut"))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    return None


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


def _resolve_face_datum_plane(
    face: SubshapeRef, offset_mm: float, state: EvaluationState
) -> Plane | FeatureError:
    """Resolve a stage-1 face reference to the face's (offset) sketch plane.

    The shared face half of the datum resolvers (``on_face`` datum + midplane
    face sides — one taxonomy, datum-planes §7): no prior body, or a signature
    that no longer matches, is ``subshape_unresolved``; a congruent twin is
    ``subshape_ambiguous`` (refuse to guess — determinism, topo-naming §7.2).
    Errors pin the named body feature as the upstream cause.
    """
    active = state.active_body
    if active is None:
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
        return resolve_face_plane(active, face.selector.signature, offset_mm)
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


def _resolve_midplane_side(
    ref: DatumPlaneRef | FeatureRef | SubshapeRef, state: EvaluationState, *, slot: str
) -> Plane | FeatureError:
    """Resolve one midplane side to a concrete plane (datum-planes §7a).

    Reuses the existing funnels — an origin datum name maps through
    :data:`DATUM_PLANES`, a ``datum`` FeatureRef through
    :func:`_resolve_datum_feature_plane`, a picked planar face through
    :func:`_resolve_face_datum_plane` (offset 0: the side IS the face's plane)
    — so a midplane introduces no new reference semantics, only a new consumer.
    """
    if isinstance(ref, DatumPlaneRef):
        return DATUM_PLANES[ref.plane]
    if isinstance(ref, FeatureRef):
        return _resolve_datum_feature_plane(ref, state, role=f"Midplane side '{slot}'")
    assert isinstance(ref, SubshapeRef)  # closed union
    return _resolve_face_datum_plane(ref, 0.0, state)


def _evaluate_datum(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Resolve one datum plane — offset, on-a-face, chained offset, or midplane.

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
      funnel's taxonomy (:func:`_resolve_midplane_side`).
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
        side_a = _resolve_midplane_side(params.a, state, slot="a")
        if isinstance(side_a, FeatureError):
            return side_a
        side_b = _resolve_midplane_side(params.b, state, slot="b")
        if isinstance(side_b, FeatureError):
            return side_b
        state.datum_planes[item.id] = midplane_between(side_a, side_b, params.flip)
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
    """
    feature = item.feature
    assert isinstance(feature, SketchFeature), "registry dispatches on type='sketch'"

    plane = resolve_sketch_plane(feature.params.plane, state)
    if isinstance(plane, FeatureError):
        return plane

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
        return _evaluate_extrude_cut(params, state, reverse)

    # ADD: a single closed region (one loop, or one outer boundary + interior
    # holes). N disjoint loops would be N separate solids — multi-body, which
    # Loft does NOT support — so build_profile_face keeps rejecting them as
    # ``profile_unsupported``; the multi-region relaxation is CUT-only below.
    resolved = _resolve_profile_face(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    face, plane, _ = resolved

    tool = extrude_face(face, plane, params.distance_mm, reverse)
    return _add_body(item, state, tool, merge=params.merge)


def _evaluate_extrude_cut(
    params: ExtrudeParamsV1, state: EvaluationState, reverse: bool
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
    """
    resolved = _resolve_profile_faces(params.profile, state)
    if isinstance(resolved, FeatureError):
        return resolved
    faces, plane = resolved

    body = state.active_body
    if body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive extrude first."
            ),
        )

    try:
        for face in faces:
            tool = extrude_face(face, plane, params.distance_mm, reverse)
            body = combine_body(body, tool, "cut")
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))
    state.set_active_body(body)
    return None


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
    face, plane, _ = resolved

    tool = extrude_face(face, plane, params.thickness_mm, reverse)
    error = _add_body(item, state, tool, merge=params.merge)
    if error is not None:
        return error
    state.sheet_metal_defaults[item.id] = SheetMetalDefaults(
        thickness_mm=params.thickness_mm,
        k_factor=params.k_factor,
        bend_radius_mm=params.bend_radius_mm,
    )
    return None


def _evaluate_sheet_metal_edge_flange(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Fold a flange off a base-flange edge and fuse it across a bend (§4.2).

    Body-modifying (design §7.6): it needs a prior sheet body with recorded
    sheet-metal defaults (``no_base_flange`` otherwise — a bend allowance needs the
    part gauge/K). The base-flange edge is resolved by the picked
    :class:`EdgeSignature` (:func:`resolve_edge` — the SAME stage-1 machinery a
    fillet uses); a ref that no longer resolves is ``subshape_unresolved`` / a
    congruent twin ``subshape_ambiguous``. ``bend_radius_mm`` / ``k_factor`` inherit
    the part defaults when omitted (§4.2). The bend geometry is built + fused
    (:func:`build_edge_flange`); on success the active body becomes the fused sheet
    and the bend's provenance (§5) is recorded for the unfold. The active body is
    only replaced on success (strict-prefix tessellates the last-good body, §4.3).
    """
    feature = item.feature
    assert isinstance(feature, SheetMetalEdgeFlangeFeature), (
        "registry dispatches on type='sheet_metal_edge_flange'"
    )
    params = feature.params

    active = state.active_body
    if active is None or state.active_body_id is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "An edge flange requires an existing sheet body, but no "
                "body-affecting feature precedes it; add a base flange first."
            ),
        )
    defaults = state.sheet_metal_defaults.get(state.active_body_id)
    if defaults is None:
        return FeatureError(
            code="no_base_flange",
            message=(
                "An edge flange needs the part's sheet-metal gauge/K (from a base "
                "flange) to compute its bend allowance, but the active body is not "
                "a sheet-metal base flange."
            ),
        )

    try:
        edge = resolve_edge(active, params.edge.selector.signature)
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    radius = params.bend_radius_mm or defaults.bend_radius_mm
    k_factor = params.k_factor if params.k_factor is not None else defaults.k_factor

    try:
        result = build_edge_flange(
            active,
            edge,
            flange_length_mm=params.flange_length_mm,
            bend_angle_deg=params.bend_angle_deg,
            bend_radius_mm=radius,
            thickness_mm=defaults.thickness_mm,
        )
    except EdgeFlangeEdgeError as exc:
        return FeatureError(code="edge_flange_bad_edge", message=str(exc))
    except EdgeFlangeError as exc:
        return FeatureError(code="edge_flange_failed", message=str(exc))

    # set_active_body keeps the body's identity (its base-flange id), so the
    # sheet-metal defaults stay reachable for a SECOND edge flange (a depth-1
    # star, §4.3 — the U-channel case) without re-keying.
    state.set_active_body(result.body)
    state.bend_provenance[item.id] = BendProvenance(
        cyl_signature=result.cyl_signature,
        base_face_signature=result.base_face_signature,
        k_factor=k_factor,
    )
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
    nothing to cut), ``revolve_failed``, ``boolean_failed``. the active body is
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

    if params.operation == "cut" and state.active_body is None:
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
            plane,
            params.angle_deg,
            params.direction == "reverse",
        )
    except RevolveError as exc:
        return FeatureError(code="revolve_failed", message=str(exc))

    if params.operation == "cut":
        return _cut_active(state, tool)
    return _add_body(item, state, tool, merge=params.merge)


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
    face, _plane, _ = resolved

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

    try:
        tool = sweep_profile(face, path)
    except SweepError as exc:
        return FeatureError(code="sweep_failed", message=str(exc))

    if params.operation == "cut":
        return _cut_active(state, tool)
    return _add_body(item, state, tool, merge=params.merge)


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
    for ref in params.profiles:
        resolved = _resolve_loft_section(ref, state)
        if isinstance(resolved, FeatureError):
            return resolved
        sections.append(resolved)

    if params.operation == "cut" and state.active_body is None:
        return FeatureError(
            code="no_prior_body",
            message=(
                "Cut requires an existing body, but no body-affecting "
                "feature precedes this one; use an additive feature first."
            ),
        )

    try:
        tool = loft_sections(sections)
    except LoftError as exc:
        return FeatureError(code="loft_failed", message=str(exc))

    if params.operation == "cut":
        return _cut_active(state, tool)
    return _add_body(item, state, tool, merge=params.merge)


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

    try:
        edges = select_edges(active, params.edges)
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_fillet_edges", message=str(exc))
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    try:
        state.set_active_body(fillet_body(active, edges, params.radius_mm))
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

    try:
        edges = select_edges(active, params.edges)
    except NoEdgesSelectedError as exc:
        return FeatureError(code="no_chamfer_edges", message=str(exc))
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    try:
        state.set_active_body(chamfer_body(active, edges, params.distance_mm))
    except ChamferError as exc:
        return FeatureError(code="chamfer_failed", message=str(exc))
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
            active, [ref.selector.signature for ref in params.faces.refs]
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(code="subshape_unresolved", message=str(exc))
    except SubshapeAmbiguousError as exc:
        return FeatureError(code="subshape_ambiguous", message=str(exc))

    try:
        state.set_active_body(shell_body(active, faces, params.thickness_mm))
    except ShellThicknessError as exc:
        return FeatureError(code="shell_thickness_too_large", message=str(exc))
    except ShellError as exc:
        return FeatureError(code="shell_failed", message=str(exc))
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
            active, [ref.selector.signature for ref in params.faces.refs]
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
    try:
        state.set_active_body(draft_body(active, faces, neutral, params.angle_deg))
    except DraftError as exc:
        return FeatureError(code="draft_failed", message=str(exc))
    return None


def _pattern_cut_tools(state: EvaluationState) -> list[Solid] | None:
    """The removal tools to array-cut, or ``None`` to array-union (BACKLOG #3).

    Option (a): a pattern infers its combine mode from the IMMEDIATELY-preceding
    body-affecting feature (``state.prev_body_feature``, tree order — no new
    schema field, no picked reference, so independent of topological naming #1).
    When that source is an extrude-CUT, its removal tool(s) are RECONSTRUCTED
    from the source's already-solved profile — a pure, deterministic function of
    the same solved sketch + params the cut itself used (:func:`_resolve_profile_faces`
    + :func:`extrude_face`), so the seed hole (placement 0) and the patterned
    copies (placements 1..count-1) are the identical tool. Any other source (an
    add, a fillet, an intervening feature) returns ``None`` — the pattern unions
    whole-body copies exactly as before (the add-pattern path is unchanged).

    The source cut already succeeded in this prefix (strict-prefix rule), so
    reconstruction cannot fail; a defensive ``FeatureError`` from the resolver
    (which must not happen) falls back to ``None`` rather than crash.
    """
    source = state.prev_body_feature
    if not isinstance(source, ExtrudeFeature) or source.params.operation != "cut":
        return None
    resolved = _resolve_profile_faces(source.params.profile, state)
    if isinstance(resolved, FeatureError):
        return None
    faces, plane = resolved
    reverse = source.params.direction == "reverse"
    return [
        extrude_face(face, plane, source.params.distance_mm, reverse) for face in faces
    ]


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


def _evaluate_pattern(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Array a source solid into a linear row / circular ring — union OR cut (§4.3).

    v1 DESIGN DECISION (docs/GEOMETRY-QA.md 2026-07-12/2026-07-13): a pattern
    places rigid copies of a source solid about world-space direction/axis
    vectors (no picked sub-geometry — independent of topological naming, #1), so
    like fillet/chamfer it needs a prior body-affecting feature
    (``no_target_body`` otherwise). Two combine modes, inferred (option a) from
    the IMMEDIATELY-preceding body-affecting feature (:func:`_pattern_cut_tools`):

    * when it is an extrude-CUT (a bolt-circle hole, a lightening hole —
      BACKLOG #3 / showcase F1), the copies of that cut's tool are REMOVED at
      each placement, so one hole-cut + pattern makes N holes, not N bodies;
    * otherwise the copies of the WHOLE current body are UNIONED into the chain
      (the original add-pattern, unchanged — BACKLOG #7).

    Every pattern value is validated in :mod:`geometry.kernel.pattern` and mapped
    1:1 to a per-feature ``pattern_*`` code — bad count/spacing/direction/axis/
    angle, ``pattern_disjoint`` (instances do not merge into / the cut severs one
    solid), or the kernel ``pattern_failed`` (incl. a cut that removes the whole
    body). the active body is only replaced on success (strict-prefix rule
    tessellates the last-good body, §4.3).
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

    tools = _pattern_cut_tools(state)
    try:
        state.set_active_body(_apply_pattern(active, feature.params.pattern, tools))
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
        combined = boolean_bodies(
            target, tool, params.operation, allow_disjoint=params.allow_disjoint
        )
    except BooleanDisjointError as exc:
        return FeatureError(code="boolean_disjoint", message=str(exc))
    except BooleanEmptyError as exc:
        return FeatureError(code="boolean_empty", message=str(exc))
    except BooleanError as exc:
        return FeatureError(code="boolean_failed", message=str(exc))

    state.combine_bodies(params.target.feature_id, params.tool.feature_id, combined)
    return None


#: Feature types whose ok evaluation mutates the body set (§MB-0). The
#: main loop records the last such feature as ``state.prev_body_feature`` so a
#: pattern can infer its combine mode from the immediately-preceding
#: body-affecting feature (BACKLOG #3). Sketch/datum are absent — they produce
#: input geometry / a plane, never a body.
_BODY_AFFECTING_TYPES: frozenset[str] = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "draft",
        "pattern",
        "import",
        "sheet_metal_base_flange",
        "sheet_metal_edge_flange",
        "boolean",
    }
)


#: The dispatcher registry (§4): feature ``type`` discriminator → handler.
#: Consulted by key only; no iteration order participates (RESEARCH §9
#: determinism). New feature types plug in here.
FEATURE_HANDLERS: dict[str, FeatureHandler] = {
    "datum": _evaluate_datum,
    "sketch": _evaluate_sketch,
    "extrude": _evaluate_extrude,
    "revolve": _evaluate_revolve,
    "sweep": _evaluate_sweep,
    "loft": _evaluate_loft,
    "fillet": _evaluate_fillet,
    "chamfer": _evaluate_chamfer,
    "shell": _evaluate_shell,
    "draft": _evaluate_draft,
    "pattern": _evaluate_pattern,
    "import": _evaluate_import,
    "sheet_metal_base_flange": _evaluate_sheet_metal_base_flange,
    "sheet_metal_edge_flange": _evaluate_sheet_metal_edge_flange,
    "boolean": _evaluate_boolean,
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
    # An over-constrained-but-solvable sketch carries the typed redundant
    # diagnosis on its payload (BACKLOG #6); a cleanly-solved sketch → None.
    diagnosis = classify_overconstraint(solved)
    return SolvedSketchData.model_validate(
        {
            **solved.model_dump(),
            "diagnosis": diagnosis.model_dump() if diagnosis else None,
        }
    )


@dataclass
class TreeEvaluation:
    """A full evaluation: the boundary DTO plus service-internal payloads.

    ``result`` is everything that crosses the service boundary — including
    the per-feature solved-sketch payloads on ``FeatureResult.data`` (§7.10)
    and the content-addressed ``mesh_glb_id``. The remaining fields are
    strictly service-internal (used by the golden harness and future
    callers inside this service): ``solved_sketches`` (``ok`` sketch
    features only, evaluation order), ``body`` (the last-good kernel shape —
    a single :class:`~build123d.Solid`, or a :class:`~build123d.Compound` of a
    multi-body part's disjoint solids (§MB-0); never serialized), and the
    tessellation artifact ``glb``/``mesh`` that ``mesh_glb_id`` addresses.
    """

    result: EvaluateTreeResult
    solved_sketches: dict[uuid.UUID, SolvedSketch]
    body: BodyShape | None = None
    glb: bytes | None = None
    mesh: MeshStats | None = None
    #: Sheet-metal unfold inputs (§5/§6), service-internal like ``body``: the bend
    #: provenance recorded by each ok edge flange (evaluation order) + the part's
    #: sheet-metal defaults (gauge/K/radius) from its base flange, so a flat-pattern
    #: query (:func:`geometry.sheet_metal.unfold_sheet_metal`) resolves each bend by
    #: provenance against ``body``. Empty / ``None`` for a non-sheet-metal part.
    bend_provenance: list[BendProvenance] = field(default_factory=list[BendProvenance])
    sheet_metal_defaults: SheetMetalDefaults | None = None


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
            # Record the last ok body-affecting feature so the NEXT feature (a
            # pattern) can infer its source (BACKLOG #3). Set AFTER dispatch, so
            # a pattern reads the feature BEFORE it, then this advances to the
            # pattern itself.
            if item.feature.type in _BODY_AFFECTING_TYPES:
                state.prev_body_feature = item.feature
        else:
            results.append(
                FeatureResult(feature_id=item.id, status="error", error=error)
            )
            failed = True

    # §4.3/§4.4 artifact fields: the LAST-GOOD body — handlers mutate
    # state.bodies only on success, so even after a mid-tree failure this is
    # the state after the last ok body-affecting feature ("the viewport
    # always has something honest to show"). No body (sketch-only tree, or
    # the first extrude failed) → honestly null, the §6 failure flavour.
    properties: ShapeProperties | None = None
    mesh_glb_id: str | None = None
    glb: bytes | None = None
    mesh: MeshStats | None = None
    shape: BodyShape | None = None
    if state.bodies:
        # Tree/insertion-ordered body set (§MB-0): a part with ONE body measures
        # and tessellates that bare solid — byte-identical to the pre-multi-body
        # path. A part with >1 body rolls up its mass properties ANALYTICALLY
        # (Σ over the body set, no re-mesh/boolean — the assembly pattern) and
        # tessellates a COMPOUND of all bodies in the fixed base-order, which
        # ``glb_stats`` sums over. Both are deterministic (RESEARCH §9).
        body_list = list(state.bodies.values())
        if len(body_list) == 1:
            # ONE body — which may itself be a multi-lump Compound (a disjoint
            # boolean / multi-solid import, §MB-4): measure it directly (GProp +
            # .shells() count across its lumps), byte-identical to the single-solid
            # path when it is a bare Solid.
            shape = body_list[0]
            properties = measure_shape(body_list[0])
        else:
            # >1 body: roll up mass properties ANALYTICALLY per body, and tessellate
            # a FLATTENED Compound of every body's lumps (§MB-4) — flattening avoids
            # a nested Compound (a body that is itself a Compound), which would give
            # ``glb_stats`` a nondeterministic traversal. Each body's lumps are
            # already in explicit lump order; bodies stay tree-ordered.
            shape = Compound([s for b in body_list for s in b.solids()])
            properties = combine_properties([measure_shape(b) for b in body_list])
        glb, mesh = tessellate_glb(shape, request.linear_deflection)
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
        body=shape,
        glb=glb,
        mesh=mesh,
        bend_provenance=list(state.bend_provenance.values()),
        sheet_metal_defaults=next(iter(state.sheet_metal_defaults.values()), None),
    )
