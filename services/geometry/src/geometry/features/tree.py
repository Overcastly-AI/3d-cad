"""Tree evaluation: the ordered dispatch pass, publishing, and the rebuild cache.

:func:`evaluate_tree` is the one funnel every rebuild passes through: it walks
the request's features under the strict-prefix rule (§4.3), then measures and
tessellates the last-good body. :func:`warm_rebuild_cache` is the prefetch seam.
The rebuild-cache checkpoints and ladder (:class:`_Checkpoint`,
:func:`_climb_rung`; docs/PERF.md fix #1, PERF-REAL-2) live here because they are
threaded through the dispatch loop itself.
"""

# Underscore names are private to the geometry.features package rather than to
# one module, so importing them from a sibling module is intended.
# pyright: reportPrivateUsage=false

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

from build123d import Compound, Plane
from loft_wire.features import (
    BodyLumpInfo,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExtrudeFeature,
    FeatureEnvelope,
    FeatureError,
    FeatureResult,
    MirrorFeature,
    MirrorFeaturesScope,
    PatternFeature,
    PatternFeaturesScope,
    SweepFeature,
    iter_feature_refs,
)
from loft_wire.geometry import MeshStats, ShapeProperties
from loft_wire.materials import (
    MaterialKey,
    density_kg_m3,
    resolve_body_material,
)
from py_kit.errors import ValidationApiError

from geometry.features.dispatch import (
    BODY_AFFECTING_TYPES,
    _dispatch,
    _feature_data,
)
from geometry.features.state import (
    EvaluationState,
)
from geometry.kernel import (
    attribute_faces,
    combine_properties,
    measure_shape,
    tessellate_glb,
)
from geometry.kernel.fork import weigh_shapes
from geometry.kernel.healing import body_is_valid
from geometry.kernel.lumps import lump_count
from geometry.kernel.naming import BodyNames
from geometry.kernel.provenance import FaceProvenance, FaceProvenanceRecorder
from geometry.kernel.resolution import ResolutionTally
from geometry.kernel.types import BodyShape
from geometry.mesh_store import store_mesh_glb
from geometry.rebuild_cache import (
    REBUILD_CACHE_CAPACITY,
    WARM_YIELD_SLICE_S,
    CacheStats,
    PrefixCache,
    WorkGate,
    drop_triangulation,
    live_work,
    prefix_keys,
)
from geometry.sheet_metal import (
    BendProvenance,
    CornerRelief,
    SheetMetalDefaults,
)
from geometry.sketch import (
    SolvedSketch,
)


def _snapshot_shape(bodies: dict[uuid.UUID, BodyShape]) -> BodyShape:
    """The current body set as ONE shape — a bare :class:`~build123d.Solid` (a
    single body) or a FLATTENED :class:`~build123d.Compound` of every body's lumps
    (multi-body §MB-4).

    The single construction (CLAUDE.md DRY) shared by the final tessellated shape
    and the per-feature provenance snapshots (:attr:`EvaluationState.provenance`),
    so a face has byte-identical geometry between a mid-tree snapshot and the final
    body — the invariant :func:`geometry.kernel.attribute_faces` matches on.
    Callers guard a non-empty ``bodies`` (a body-less tree tessellates nothing).
    """
    body_list = list(bodies.values())
    if len(body_list) == 1:
        return body_list[0]
    return Compound([solid for body in body_list for solid in body.solids()])


def _tool_scope_ids(request: EvaluateTreeRequest) -> frozenset[uuid.UUID]:
    """Every feature id named by a ``features``-scope mirror OR PATTERN in *request*.

    The OPT-IN pre-pass of docs/design/mirror-semantics.md §9: only a tree that
    names features funds retaining their tools. v1 retained exactly ONE tool list
    (the most recent cut); v2 must retain a tool list for every feature some mirror
    might name, which without a gate would grow with tree length x tool complexity
    for the whole evaluation. The selection is known BEFORE evaluation starts, so
    only these ids retain their tools — a tree with no ``features``-scope verb
    pays ZERO additional memory, which is also why the widening cannot regress an
    existing document's rebuild cost.

    The pattern joined the mirror here unchanged (pattern-scope §5): both verbs read
    the SAME per-feature store, so one pre-pass funds both and a tree that uses
    neither still pays nothing. Suppressed features are included deliberately:
    unsuppressing one must not need a different capture set (a rebuild is a pure
    function of the tree, and this keeps the captured set independent of evaluation
    outcomes).
    """
    ids: set[uuid.UUID] = set()
    for item in request.features:
        feature = item.feature
        if (
            isinstance(feature, MirrorFeature)
            and isinstance(feature.params.scope, MirrorFeaturesScope)
        ) or (
            isinstance(feature, PatternFeature)
            and isinstance(feature.params.scope, PatternFeaturesScope)
        ):
            ids.update(ref.feature_id for ref in feature.params.scope.features)
    return frozenset(ids)


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

    **OWNERSHIP — this object is the handle on its kernel shapes, so a caller
    that keeps a shape must keep the evaluation** (docs/PERF.md fix #1). The
    rebuild cache offers this evaluation's prefix as a resume point only once
    THIS object is unreachable, because a resuming rebuild mutates those shapes
    in place (OCCT booleans rewrite their arguments' subshapes — CM-6b). So
    ``body = evaluate_tree(request).body`` is a bug: it drops the handle while
    keeping the thing it protects, and a concurrent rebuild of the same tree may
    then modify that body underneath you. Keep the evaluation for as long as you
    use anything it gave you (``assembly/evaluate.py`` retains it for exactly
    this reason). The claim cannot be moved onto the shapes themselves — the
    checkpoint holds them, so a token pinned there is never collectable; see
    :meth:`geometry.rebuild_cache.PrefixCache.store_on_release`.
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
    #: Explicit corner reliefs (§4.4) authored in the tree, evaluation order — passed
    #: to :func:`unfold_sheet_metal` so the flat pattern develops the relieved blank.
    #: Empty for a part with no corner-relief feature.
    corner_reliefs: list[CornerRelief] = field(default_factory=list[CornerRelief])
    #: The CLEAN sheet body the flat-pattern unfold resolves its bends against
    #: (§4.4.4) — every bend applied, NO relief notches, maintained by the folds
    #: regardless of feature order (so a flange authored AFTER a relief still unfolds).
    #: ``None`` for a non-sheet-metal part; for an unrelieved sheet part it equals
    #: ``body`` (same bends, no notches), so the unfold uses ``unfold_body or body``.
    unfold_body: BodyShape | None = None
    #: The resolved plane of every ``ok`` datum feature in this prefix, by feature id
    #: (service-internal like ``body``). A drawing SECTION view whose cutting plane is
    #: a ``FeatureRef`` (an axis-aligned offset/midplane datum, drawings-section.md §1)
    #: resolves it here — the SAME plane the sketch/extrude path resolved during this
    #: evaluation, never a re-resolution. Empty for a part with no datum feature.
    datum_planes: dict[uuid.UUID, Plane] = field(default_factory=dict[uuid.UUID, Plane])
    #: The evaluation's per-face provenance RECORDER (FINDINGS #9), the same object
    #: the evaluator state — and so the rebuild-cache checkpoint — holds. Read it
    #: through :attr:`face_provenance` / :meth:`face_owners`: the fingerprints are
    #: computed on first read and kept on the recorder (PERF-REAL-3 follow-up), so
    #: an evaluation nobody picks from never pays for them, and a checkpoint that
    #: served one pick serves the next with nothing to compute. ``None`` for a
    #: hand-built evaluation (tests), which reads as an empty history.
    provenance_recorder: FaceProvenanceRecorder | None = None
    #: The history-based face names of every body (DESIGN-INTENT-REFS), the same
    #: objects the evaluator state holds. Read through :meth:`face_names`.
    topo_names: list[BodyNames] = field(default_factory=list[BodyNames])

    def face_names(self) -> list[str | None]:
        """The name of each face of :attr:`body`, in ``body.faces()`` order
        (``None`` where a face has none). ``[]`` without a body."""
        if self.body is None:
            return []
        out: list[str | None] = []
        for face in self.body.faces():
            names = (n.name_of(face) for n in self.topo_names)
            out.append(next((name for name in names if name is not None), None))
        return out

    @property
    def face_provenance(self) -> FaceProvenance:
        """Face FINGERPRINTS of the body set after each ok body-affecting feature
        (evaluation order), fingerprinted on first read and memoised. EMPTY for a
        body-less tree and for one past
        :data:`~loft_wire.overlay.MAX_PROVENANCE_FACES`. Carries no kernel shape."""
        recorder = self.provenance_recorder
        return FaceProvenance() if recorder is None else recorder.freeze()

    def face_owners(self) -> list[uuid.UUID | None]:
        """The feature owning each face of :attr:`body`, in ``body.faces()``
        order — :func:`geometry.kernel.attribute_faces` over this evaluation's
        history, with the final faces' fingerprints read from the recorder (the
        final body is its last snapshot) rather than recomputed. ``[]`` without a
        body."""
        if self.body is None:
            return []
        recorder = self.provenance_recorder
        return attribute_faces(
            self.body,
            self.face_provenance,
            None if recorder is None else recorder.fingerprint_of,
        )


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


def _suppressed_reference_error(
    feature: FeatureEnvelope, suppressed_ids: set[uuid.UUID]
) -> FeatureError | None:
    """A ``references_suppressed`` error if *feature* names a suppressed feature.

    Feature suppress (§4.3a): a suppressed feature is skipped, so a later
    NON-suppressed feature that DIRECTLY references its output — a profile /
    plane / operand :class:`FeatureRef`, or a picked face/edge
    :class:`SubshapeRef`/:class:`EdgeSubshapeRef` anchored on it — can no longer
    rebuild off a body that omits that feature's contribution. That is a
    distinct, honest failure from a plain ``reference_unresolved`` (the target
    exists; it is deliberately suppressed), so it gets its own typed code pinned
    to the suppressed upstream feature and, like any per-feature error, is a 200
    with the strict-prefix rule downstream (never a raise). Walks EVERY ref kind
    the schema carries (:func:`iter_feature_refs`), so a new ref-bearing field is
    covered without touching this check; the first suppressed ref in deterministic
    model-field order wins (RESEARCH §9).
    """
    for ref in iter_feature_refs(feature):
        if ref.feature_id in suppressed_ids:
            return FeatureError(
                code="references_suppressed",
                message=(
                    "This feature references a suppressed feature, so it cannot "
                    "rebuild off the current body; un-suppress that feature or "
                    "repoint the reference."
                ),
                upstream_feature_id=ref.feature_id,
            )
    return None


def _blame_invalidated_body(
    results: list[FeatureResult], last_good_feature_id: uuid.UUID | None
) -> list[FeatureResult]:
    """Turn the last-good feature's ``ok`` into the typed ``invalid_body`` error.

    Only used by the CM-6b publish-time re-check, and only when NO feature failed
    on its own: the body every feature reported ``ok`` for is invalid by the time
    it would be measured, so exactly one result is a lie and it is the one whose
    artifact the part is showing. Re-stating it as an error is what makes the tree
    honest end to end — the alternative (all-``ok`` statuses beside a part with no
    body) reads as a bug in the viewport rather than a defect in the model.
    """
    return [
        FeatureResult(
            feature_id=result.feature_id,
            status="error",
            error=FeatureError(
                code="invalid_body",
                message=(
                    "The body this feature produced was valid when it was built "
                    "and is not valid now: a later operation modified it in place "
                    "and OCCT rejects the result. Its volume, mesh and STEP export "
                    "would be wrong, so none are published."
                ),
            ),
        )
        if result.feature_id == last_good_feature_id and result.status == "ok"
        else result
        for result in results
    ]


@dataclass
class _PublishedArtifacts:
    """Everything :func:`evaluate_tree` derives AFTER the dispatch loop.

    Memoised on a checkpoint so a repeat of the SAME tree — the ``/measure``,
    ``/tessellate``, ``/export`` and drawings-compose calls that follow an
    ``/evaluate``, each of which used to pay its own full rebuild (docs/PERF.md)
    — skips the re-measure and the re-tessellation too, not just the rebuild.
    Reused ONLY when the resume consumed zero further features AND the resolved
    per-body material is unchanged, because that is exactly the input the
    measurement (and therefore ``mass_g``) depends on; everything else these
    values derive from is already pinned by the prefix key.
    """

    body_materials: dict[uuid.UUID, MaterialKey | None]
    body_measures: dict[uuid.UUID, ShapeProperties]
    properties: ShapeProperties
    shape: BodyShape
    glb: bytes
    mesh: MeshStats


@dataclass
class _Checkpoint:
    """One cached prefix: the evaluator state, plus what it had produced.

    The cache owns this EXCLUSIVELY (see :mod:`geometry.rebuild_cache`). As a
    FRONTIER entry nothing is copied on the way in or out, which is what makes a
    resumed rebuild byte-identical to a cold one. As a LADDER rung it is the
    first of the two forks :func:`_climb_rung` takes, and it is handed out only
    as :meth:`fork` — which is what every evaluation continues with at that rung,
    so the resume is byte-identical for the same reason.
    """

    state: EvaluationState
    results: list[FeatureResult]
    last_good_feature_id: uuid.UUID | None
    suppressed_ids: frozenset[uuid.UUID]
    artifacts: _PublishedArtifacts | None
    #: The :meth:`weigh` memo of the SHAPES and GLB — ``None`` until the cache
    #: first weighs it (the provenance term is added live on every weigh).
    nbytes: int | None = None

    def detach(self) -> None:
        """Drop the triangulation the producing request left on these shapes.

        Required for byte-exactness, not hygiene: a body that still carries a
        ``Poly_Triangulation`` from a previous tessellate/STL/STEP call meshes
        DIFFERENTLY once a further boolean has been applied to it (measured on
        the docs/PERF.md tray: appending one feature to an already-tessellated
        body moved the final GLB; ``BRepTools::Clean`` on the stored bodies made
        it byte-exact again at every prefix length tried). Everything the state
        can hand to a mesher is cleaned: the list is
        :meth:`EvaluationState.shape_slots`, the same one a fork copies.
        """
        for shape, _ in self.state.shape_slots():
            drop_triangulation(shape)

    def weigh(self) -> int:
        """Estimated heap this checkpoint pins in the FRONTIER cache.

        Every shape of the state (:meth:`EvaluationState.shape_slots`), the faces
        the provenance memo keeps alive, and the published shape, serialised
        together so shared subshapes count once
        (:func:`~geometry.kernel.fork.weigh_shapes`), plus the memoised GLB's exact
        length. That part is memoised on the checkpoint, and carried across a
        REPEAT (which re-stores the same state and artifacts) by
        :func:`_evaluate_tree`, so the ``/measure`` / ``/tessellate`` /
        ``/export`` calls that follow an ``/evaluate`` do not pay to re-weigh an
        unchanged checkpoint. The provenance history's own heap
        (:meth:`~geometry.kernel.FaceProvenanceRecorder.nbytes`) is added on
        EVERY weigh, because a face pick grows it without changing anything else.
        """
        if self.nbytes is None:
            shapes: list[object] = [s.wrapped for s, _ in self.state.shape_slots()]
            shapes.extend(self.state.provenance.retained_faces())
            glb = 0
            if self.artifacts is not None:
                shapes.append(cast(object, self.artifacts.shape.wrapped))
                glb = len(self.artifacts.glb)
            self.nbytes = weigh_shapes(shapes) + glb
        # NOT memoised: a face pick materialises fingerprints on the recorder
        # while it owns the checkpoint, so the history weighs more at its next
        # store than at the last one (PERF-REAL-3 follow-up).
        return self.nbytes + self.state.provenance.nbytes()

    def fork(self) -> "_Checkpoint":
        """An independent copy for the caller of a LADDER rung (PERF-REAL-2).

        The rung itself stays on the ladder; the resuming evaluation continues
        with this fork, which is exactly what a cold evaluation continues with at
        the same rung (:func:`_climb_rung`). No artifacts: a rung is never the
        end of the tree that published them.
        """
        state, _ = self.state.fork()
        return _Checkpoint(
            state=state,
            results=list(self.results),
            last_good_feature_id=self.last_good_feature_id,
            suppressed_ids=self.suppressed_ids,
            artifacts=None,
        )


#: The per-worker rebuild cache (docs/PERF.md fix #1). Process-global like the
#: mesh and STEP-parse caches, and like them a pure performance optimisation:
#: every miss is answered by evaluating the tree.
_REBUILD_CACHE: PrefixCache[_Checkpoint] = PrefixCache(REBUILD_CACHE_CAPACITY)


def reset_rebuild_cache() -> None:
    """Empty the rebuild cache (test isolation seam; production never calls it).

    A test that asserts a COLD rebuild — a timing, a determinism gate, or a miss
    path — must not be served a checkpoint warmed by an earlier test in the same
    process.
    """
    _REBUILD_CACHE.clear()


def rebuild_cache_stats() -> CacheStats:
    """Hit/miss counters of the per-worker rebuild cache (tests + diagnostics)."""
    return _REBUILD_CACHE.stats


def _published_artifacts(
    body_materials: dict[uuid.UUID, MaterialKey | None],
    body_measures: dict[uuid.UUID, ShapeProperties],
    properties: ShapeProperties | None,
    shape: BodyShape | None,
    glb: bytes | None,
    mesh: MeshStats | None,
) -> _PublishedArtifacts | None:
    """The memoisable artifact set, or ``None`` for a tree that published none.

    A body-less prefix (sketches only, or a first extrude that failed) has
    nothing to memoise and nothing to save — the publish step for it is already
    free.
    """
    if shape is None or properties is None or glb is None or mesh is None:
        return None
    return _PublishedArtifacts(
        body_materials=body_materials,
        body_measures=body_measures,
        properties=properties,
        shape=shape,
        glb=glb,
        mesh=mesh,
    )


@dataclass(frozen=True)
class _Ladder:
    """Where one dispatch pass offers its rungs: the request's key chain, and
    whether the pass is speculation (a warm) or live work."""

    keys: Sequence[str]
    speculative: bool


def _climb_rung(
    position: int,
    state: EvaluationState,
    results: list[FeatureResult],
    suppressed_ids: set[uuid.UUID],
    last_good_feature_id: uuid.UUID | None,
    ladder: _Ladder,
) -> None:
    """Fork the state at rung *position* and continue on the fork (PERF-REAL-2).

    Runs at EVERY multiple of the cache's ``rung_spacing`` (default
    :data:`~geometry.rebuild_cache.RUNG_SPACING`) on EVERY evaluation, whether or
    not anything is cached or will be kept — that is the invariant that makes a
    ladder resume byte-identical to a cold rebuild.
    Two forks, and both are needed:

    * ``stored = fork(state)`` goes on the ladder and is never touched again, so
      the features evaluated after this point cannot rewrite it in place;
    * ``live = fork(stored)`` is what THIS evaluation continues with.

    A resume from the rung later continues with ``fork(stored)`` too — the same
    OCCT copy of the same untouched input, so it is the same state, down to the
    ULP a copy can move a mesh by. Forking once and continuing on the original
    would make the cold path carry the un-copied shapes forward and the resumed
    one a copy, and a single copy DOES re-mesh differently on 13 of 89 trees
    (geometry QA, 2026-09-23; :mod:`geometry.rebuild_cache`), so ``mesh_glb_id``
    would depend on cache state. Both single-fork variants are gated: by bytes
    in ``tests/test_rebuild_ladder_qa.py`` (a resume is byte-identical to cold
    in mesh AND STEP on the shared-face tree, which that mutant reddens) and
    structurally, by ``IsSame``, in ``tests/test_rebuild_cache.py``
    (``test_a_rung_climb_forks_twice_*``) and
    ``test_every_rung_climb_carries_on_with_a_copy_of_the_rung``. The second
    fork costs ~9 ms at 560 faces.
    """
    stored, nbytes = state.fork(weigh=True)
    live, _ = stored.fork()
    state.adopt(live)
    _REBUILD_CACHE.store_rung(
        ladder.keys,
        position,
        _Checkpoint(
            state=stored,
            results=list(results),
            last_good_feature_id=last_good_feature_id,
            suppressed_ids=frozenset(suppressed_ids),
            artifacts=None,
        ),
        nbytes=nbytes + stored.provenance.nbytes(),
        speculative=ladder.speculative,
    )


#: A READ-ONLY look at each feature and the state it is about to be dispatched
#: on, i.e. the body its picks resolve against (DESIGN-INTENT-BACKFILL,
#: :mod:`geometry.features.ref_backfill`).
RefObserver = Callable[[EvaluatedFeatureInput, EvaluationState], None]


def _dispatch_prefix(
    features: Sequence[EvaluatedFeatureInput],
    state: EvaluationState,
    results: list[FeatureResult],
    suppressed_ids: set[uuid.UUID],
    last_good_feature_id: uuid.UUID | None,
    *,
    offset: int,
    ladder: _Ladder | None,
    stop: Callable[[], bool] | None = None,
    observer: RefObserver | None = None,
) -> tuple[uuid.UUID | None, bool, int]:
    """The ordered dispatch pass (§4.2/§4.3), shared by evaluate and warm.

    Mutates *state*, *results* and *suppressed_ids* in place and returns
    ``(last_good_feature_id, failed, consumed)``. *stop* is polled BEFORE each
    feature: a warm that is cancelled or out of budget stops cleanly on a feature
    boundary, having produced a genuine (shorter) prefix — there is no way to
    interrupt one OCCT call, and pretending otherwise would be a lie about the
    bound. ONE implementation on purpose: a speculative warm that dispatched
    features differently from a real evaluation would eventually cache a state a
    real evaluation would not have produced.

    *offset* is the absolute index of ``features[0]`` in the request, because the
    ladder rungs sit at ABSOLUTE positions (:func:`_climb_rung`): a pass that
    resumed at 37 must fork after feature 40 exactly as a cold pass does.
    A ``None`` *ladder* climbs no rung: the pass neither reads nor writes the
    rebuild cache (:func:`dispatch_cold`), and only such a pass passes an
    *observer* (:func:`_dispatch_one`).
    """
    failed = False
    consumed = 0
    for item in features:
        if not failed and stop is not None and stop():
            break
        consumed += 1
        if failed:
            results.append(FeatureResult(feature_id=item.id, status="skipped"))
            continue
        _dispatch_one(item, state, results, suppressed_ids, observer)
        # A feature sent with an input error built nothing and touched no state,
        # so it is no strict-prefix failure: the features after it build on.
        if results[-1].status == "error" and item.input_error is None:
            failed = True
            continue
        if results[-1].status == "ok":
            last_good_feature_id = item.id
        position = offset + consumed
        if ladder is not None and position % _REBUILD_CACHE.rung_spacing == 0:
            _climb_rung(
                position, state, results, suppressed_ids, last_good_feature_id, ladder
            )
    return last_good_feature_id, failed, consumed


def _dispatch_one(
    item: EvaluatedFeatureInput,
    state: EvaluationState,
    results: list[FeatureResult],
    suppressed_ids: set[uuid.UUID],
    observer: RefObserver | None = None,
) -> None:
    """Evaluate ONE feature into *state*, appending exactly one result.

    The body of :func:`_dispatch_prefix`'s loop, split out so the loop can own
    the rung bookkeeping. The appended status says what happened: ``suppressed``,
    ``ok`` or ``error``.
    """
    if item.feature.suppressed:
        # Skip a suppressed feature entirely: no dispatch, no body mutation,
        # no last-good/prev-body advance — the running body state carries
        # forward as the last non-suppressed body (§4.3a).
        suppressed_ids.add(item.id)
        results.append(FeatureResult(feature_id=item.id, status="suppressed"))
        return
    if item.input_error is not None:
        # Documents could not resolve this feature's inputs (RESEARCH §19): build
        # nothing and report its error. As with suppress, the body carries on.
        results.append(
            FeatureResult(feature_id=item.id, status="error", error=item.input_error)
        )
        return
    ref_error = _suppressed_reference_error(item.feature, suppressed_ids)
    if ref_error is not None:
        results.append(
            FeatureResult(feature_id=item.id, status="error", error=ref_error)
        )
        return
    # A FRESH tally per feature (EDGE-RESOLVE-WARN-1): whatever the handler's
    # resolvers note lands on THIS feature's result and nowhere else. Read only on
    # success — a feature that failed has no body built on its references, and its
    # error already says so.
    state.subshape_tally = ResolutionTally()
    if observer is not None:
        # The backfill's observer (DESIGN-INTENT-BACKFILL): it sees exactly the
        # body and names this feature's resolvers are about to see, and writes
        # nothing to the state.
        observer(item, state)
    error = _dispatch(item, state)
    if error is None:
        results.append(
            FeatureResult(
                feature_id=item.id,
                status="ok",
                data=_feature_data(item.id, state),
                subshape_resolution=state.subshape_tally.summary(),
            )
        )
        # Remember the TYPE of every captured feature, in evaluation order: a
        # `features`-scope mirror reads it to tell "not in this prefix"
        # (reference_unresolved) from "in the prefix but not reflectable"
        # (mirror_feature_unsupported), and the insertion order IS the tree order
        # its reflected tools are applied in (mirror-semantics §8.1).
        if item.id in state.tool_scope_ids:
            state.scoped_feature_types[item.id] = item.feature.type
        # Advance the last ok body-affecting feature id so the NEXT feature (a
        # pattern) can tell whether the recorded cut tools came from its
        # IMMEDIATE predecessor (BACKLOG #3, `_pattern_cut_tools`). Set AFTER
        # dispatch, so a pattern reads the feature BEFORE it, then this
        # advances to the pattern itself.
        if item.feature.type in BODY_AFFECTING_TYPES:
            state.prev_body_feature_id = item.id
            # RECORD the body set for per-face feature provenance
            # (FINDINGS #9): each final face is attributed to the earliest
            # feature after which it exists in its final form. Taken HERE, not
            # from a retained snapshot at attribution time (PERF-5b) — see
            # :class:`FaceProvenanceRecorder`. UNCONDITIONAL since PERF-REAL-3
            # (see :func:`evaluate_tree`, "ONE LINEAGE"): a state that has not
            # recorded cannot serve a face pick, so recording only for the pick
            # made every pick after an open or an edit a full rebuild. The
            # intermediate body still dies as before; the recorder keeps its
            # faces and fingerprints them only when somebody reads provenance.
            if state.bodies:
                state.provenance.record(item.id, _snapshot_shape(state.bodies))
    else:
        results.append(FeatureResult(feature_id=item.id, status="error", error=error))


def warm_rebuild_cache(
    request: EvaluateTreeRequest,
    *,
    prefix_length: int | None = None,
    budget_s: float | None = None,
    cancelled: Callable[[], bool] | None = None,
    yield_to: WorkGate | None = None,
) -> int:
    """Evaluate *request*'s prefix into the cache WITHOUT publishing anything.

    The prefetch seam (docs/PERF.md / :mod:`geometry.rebuild_cache`): it returns
    the number of features now cached and **cannot** return a body, a mesh id or
    mass properties, so a speculative rebuild can never be served as an answer —
    a later request gets it only by hashing to the identical prefix, through the
    ordinary key.

    *prefix_length* is how much of *request* to evaluate; ``None`` means all of
    it. The distinction is the whole point of the seam, because the two triggers
    ask different questions:

    * **an open feature editor** declares features ``0..k-1`` settled while
      feature ``k`` is being retyped — so *request* is the tree as it stands and
      ``prefix_length=k``. The key is taken from the FULL request's chain
      (:func:`~geometry.rebuild_cache.prefix_keys`), which is exactly the chain
      the edited tree will probe, because an edit at ``k`` cannot change the hash
      of anything before it;
    * **a travel stop** is a shorter tree in its own right — the caller sends
      that tree and leaves *prefix_length* alone.

    A truncated *request* would answer neither question the same way: the
    mirror capture scope in the key header is computed over the whole feature
    list (a ``features``-scope mirror at index 150 changes what the state after
    feature 10 must retain), so warming "the first k features" and warming "a
    k-feature tree" are genuinely different keys. Both are correct; the caller
    says which it means.

    Bounded and cancellable: *budget_s* (wall clock from entry) and *cancelled*
    are polled BETWEEN features, so a warm stops within one feature's work of
    being asked to — up to ~200 ms on a 442-face body, which is the honest
    granularity of an uninterruptible OCCT call. A stopped warm still caches what
    it evaluated; a warm whose tree FAILS caches nothing (see
    :func:`evaluate_tree` for why a failed prefix is not a resume point).

    ONE COST WORTH KNOWING ABOUT, since it is the reverse of the intended one: a
    warm that RESUMES from a cached checkpoint holds it for the duration (``take``
    removes the entry — ownership transfer is what makes a resume byte-exact), so
    a real request arriving for that same checkpoint mid-warm MISSES and rebuilds
    from scratch. The exposure is bounded by the budget and by cancellation, and
    it is why speculation is single-slot and retired the moment its reason goes
    away. It cannot happen for the open-editor trigger — a prefix warm can only
    take checkpoints at or before ``prefix_length``, and the tree's frontier is
    past it — only for a travel stop the user had already visited.

    *yield_to* is the live-work gate (:class:`~geometry.rebuild_cache.WorkGate`),
    and it is what stops a prefetch being a pessimisation. One geometry worker has
    ONE effective core (OCP holds the GIL), so a warm that keeps working through a
    real rebuild does not use spare capacity — it takes half of the only capacity
    there is, and CONC-6 measured that at **2 589 -> 4 742 ms** on a commit issued
    right after the editor opened. So between features this function checks the
    gate, and when real work is in flight it:

    1. **banks the prefix it has built** as a speculative checkpoint and gives up
       ownership of it — because work still held by the warm is invisible, and a
       request that arrives mid-warm can only resume from something that is in the
       CACHE. (Measured the same day: a face pick landing while the warm sat
       mid-provenance paid the full 9.2 s with nothing to show for the warm's 15
       seconds of work.) A real request may then take it, which is the win;
    2. **waits** for the worker to go idle, in short slices so a cancel is still
       observed promptly;
    3. **takes its own checkpoint back** and carries on. If it is gone — somebody
       used it, or a store was refused for want of a slot — the warm stops: its
       reason for existing has either been served or cannot be served here.

    The whole loop is still bounded by *budget_s* and *cancelled*, so a warm on a
    worker that never goes idle spends its budget waiting and achieves nothing,
    which is the correct outcome on a machine with no spare cycles. Pass
    ``yield_to=None`` (the default) for a warm that should simply run — the direct
    callers in the tests, not the prefetch route.

    Returns 0 when nothing was cached (a failed tree, cancelled before the first
    feature, or a cache with no room for speculation).
    """
    target = len(request.features) if prefix_length is None else prefix_length
    target = max(0, min(target, len(request.features)))
    if target == 0:
        return 0
    deadline = None if budget_s is None else time.monotonic() + budget_s

    def stop() -> bool:
        if deadline is not None and time.monotonic() >= deadline:
            return True
        return cancelled is not None and cancelled()

    keys = prefix_keys(
        request,
        capture_scope=_tool_scope_ids(request),
    )
    resume = _REBUILD_CACHE.take(keys[: target + 1])
    start = 0 if resume is None else resume.prefix_length
    checkpoint = None if resume is None else resume.checkpoint
    if checkpoint is None:
        state = EvaluationState(
            linear_deflection=request.linear_deflection,
            tool_scope_ids=_tool_scope_ids(request),
        )
        results: list[FeatureResult] = []
        last_good: uuid.UUID | None = None
        suppressed: set[uuid.UUID] = set()
    else:
        state = checkpoint.state
        results = list(checkpoint.results)
        last_good = checkpoint.last_good_feature_id
        suppressed = set(checkpoint.suppressed_ids)

    if resume is not None and resume.rung and start == target:
        # A LADDER rung already sits at exactly the requested prefix, and it
        # stays there: the request this warm is for will fork it. The fork we were
        # handed is surplus — storing it too would only spend a second slot on the
        # same state.
        return target
    if start == target:
        # Already cached at exactly the requested prefix — put it straight back
        # (`take` REMOVED it) and do no kernel work. A re-declared editor open
        # must not cost a rebuild, and must not leave the cache colder than it
        # found it. The entry goes back with the claim it ARRIVED with: a real
        # checkpoint a warm happened to land on stays real (downgrading it would
        # let the next guess evict work somebody is using), and a speculative one
        # stays speculative (promoting it would launder a guess into live work).
        _REBUILD_CACHE.store(
            keys[target],
            _Checkpoint(
                state=state,
                results=results,
                last_good_feature_id=last_good,
                suppressed_ids=frozenset(suppressed),
                artifacts=checkpoint.artifacts if checkpoint is not None else None,
            ),
            speculative=resume is not None and resume.speculative,
        )
        return target

    def dispatching() -> bool:
        """The dispatch loop's stop signal: give up, OR give the core back."""
        return stop() or (yield_to is not None and yield_to.busy())

    built = start
    while True:
        last_good, failed, consumed = _dispatch_prefix(
            request.features[built:target],
            state,
            results,
            suppressed,
            last_good,
            offset=built,
            ladder=_Ladder(keys, speculative=True),
            stop=dispatching,
        )
        built += consumed
        if failed:
            return 0
        if built > 0:
            # The warm owns this state exclusively — nothing was published — so
            # it can be stored directly rather than on the release of a caller's
            # evaluation. It is marked SPECULATIVE, which is what stops it
            # evicting a live modeler's checkpoint on a full cache (CONC-4); when
            # every slot is live work the store is refused and this warm simply
            # achieved nothing, which is the honest return value.
            stored = _REBUILD_CACHE.store(
                keys[built],
                _Checkpoint(
                    state=state,
                    results=results,
                    last_good_feature_id=last_good,
                    suppressed_ids=frozenset(suppressed),
                    artifacts=None,
                ),
                speculative=True,
            )
            if not stored:
                return 0
        if built >= target or stop() or yield_to is None:
            return built
        # PAUSED, not stopped: real work wants the core. The prefix above is
        # banked (and may be taken by that very request, which is the point), so
        # wait for the worker to go idle and then reclaim it.
        #
        # WAIT IN A LOOP HERE, and do not fall through to the store/take above
        # each slice. Measured 2026-08-01 on the N=200 tray: re-banking every
        # 50 ms ran ``BRepTools::Clean`` over a 442-face body twenty times a
        # second for the whole pause, and the commit it had stepped aside for
        # came out 12 % SLOWER than with no prefetch at all — the exact defect
        # the yield exists to prevent, reintroduced by the yield's own bookkeeping.
        while yield_to.busy() and not stop():
            yield_to.wait_until_idle(WARM_YIELD_SLICE_S)
        if stop():
            return built
        if built == 0:
            continue  # nothing was stored, so there is nothing to reclaim
        reclaimed = _REBUILD_CACHE.take(keys[: built + 1])
        if reclaimed is not None and reclaimed.rung:
            # ANY rung means our banked prefix is GONE — including a rung at
            # exactly ``built``, which is where a warm paused on a multiple of
            # RUNG_SPACING always has one. Continuing from that fork would re-run
            # every feature the live request that took our prefix has just
            # computed, on the one core it is using, and then overwrite its
            # frontier with a speculative copy that has no artifacts (PERF-REAL-2
            # review; CONC-4/CONC-6). The rung itself stays on the ladder, so
            # there is nothing to put back.
            return built
        if reclaimed is None or reclaimed.prefix_length != built:
            # Somebody used it (the speculation paid off) or it lost its slot.
            # Either way this ticket's reason to keep spending is gone; starting
            # the prefix again from zero would be pure waste.
            if reclaimed is not None:
                _REBUILD_CACHE.store(
                    keys[reclaimed.prefix_length],
                    reclaimed.checkpoint,
                    speculative=reclaimed.speculative,
                )
            return built
        state = reclaimed.checkpoint.state
        results = list(reclaimed.checkpoint.results)
        last_good = reclaimed.checkpoint.last_good_feature_id
        suppressed = set(reclaimed.checkpoint.suppressed_ids)


def features_have_twist(features: Sequence[EvaluatedFeatureInput]) -> bool:
    """Whether any extrude or sweep in *features* is twisted (design
    twisted-extrude.md §6.1). It gates the bounded helicoid mesher, so every part
    WITHOUT a twist tessellates and exports byte-for-byte as before, by
    construction. The part path asks it of the tree (:func:`tree_has_twist`);
    the assembly export asks it of each instance's part."""
    return any(
        isinstance(item.feature, ExtrudeFeature | SweepFeature)
        and item.feature.params.is_twisted
        for item in features
    )


def tree_has_twist(request: EvaluateTreeRequest) -> bool:
    """Whether any extrude or sweep in *request* is twisted
    (:func:`features_have_twist`)."""
    return features_have_twist(request.features)


def evaluate_tree(request: EvaluateTreeRequest) -> TreeEvaluation:
    """Evaluate a feature tree — the ONE funnel every rebuild in the product
    passes through, and therefore where real work announces itself.

    The body is :func:`_evaluate_tree`; this wrapper exists only to mark the
    evaluation live for its duration (:class:`~geometry.rebuild_cache.
    LiveWorkGate`), which is what makes a speculative warm step aside instead of
    halving the core this request is using (CONC-6: a prefetch racing the commit
    it was meant to help measured 1.8x SLOWER than not prefetching at all). It is
    a counter, never a lock: concurrent real rebuilds do not serialise on it.
    """
    with live_work().tracked():
        return _evaluate_tree(request)


def dispatch_cold(
    request: EvaluateTreeRequest, observer: RefObserver
) -> list[FeatureResult]:
    """Dispatch *request* from feature 0 with *observer* looking at each
    feature, and return the per-feature results (DESIGN-INTENT-BACKFILL).

    COLD AND CACHE-FREE on purpose: the rebuild cache hands a resumed rebuild
    the state AFTER the cached prefix, so the body each earlier feature
    resolved its picks against is gone; and a pass with an observer must
    not seed the cache a real evaluate resumes from. The same dispatch
    (:func:`_dispatch_prefix`, :func:`_dispatch_one`) as every evaluation,
    so the strict-prefix and suppress rules are the evaluator's own. Nothing
    is tessellated or published.
    """
    with live_work().tracked():
        state = EvaluationState(
            linear_deflection=request.linear_deflection,
            tool_scope_ids=_tool_scope_ids(request),
        )
        results: list[FeatureResult] = []
        _dispatch_prefix(
            request.features,
            state,
            results,
            set(),
            None,
            offset=0,
            ladder=None,
            observer=observer,
        )
        return results


def _evaluate_tree(request: EvaluateTreeRequest) -> TreeEvaluation:
    """Evaluate an ordered feature prefix under the strict-prefix rule (§4.3).

    Suppressed features (§4.3a) are SKIPPED: the body is built from the
    non-suppressed prefix and each subsequent non-suppressed feature evaluates
    off the last non-suppressed body. A non-suppressed feature that references a
    suppressed one is a typed ``references_suppressed`` error
    (:func:`_suppressed_reference_error`), never a raise.

    Every evaluation RECORDS the body set's faces after each body-affecting
    feature (:class:`~geometry.kernel.FaceProvenanceRecorder`), which is what
    per-face provenance (:attr:`TreeEvaluation.face_provenance`) is attributed
    from. It reads geometry and never writes it, so it changes NOTHING about what
    is built; the fingerprints themselves are computed on first read.

    ONE LINEAGE (PERF-REAL-3, 2026-09-24). Recording used to be opt-in (audit H4:
    only ``/overlay`` reads it, so the other callers should not pay for it), and
    because a prefix evaluated without it cannot serve a face pick, the flag was
    part of the cache key. The consequence nobody had priced: **a face pick after
    an open or an edit was ALWAYS a miss**, on a lineage of its own, and re-ran the
    whole tree. That is the product's core loop — edit, then click a face — and on
    the gauntlet's imported ``gearbox-11752`` (1 018 faces) the pick re-spent
    7.9 s of an 8.5 s cold evaluate in process (15.3 s through the browser). So
    every evaluation records, and one key serves every route. Recording eagerly
    cost ~6-8 % of a cold rebuild (1 477 ms of 25.0 s on the N=200 tray); the
    recorder now defers the GProps to the first reader and re-anchors its memo
    across ladder forks, which leaves ~1.6 % (390 ms at N=200, 4 ms on the
    gearbox) — measured in docs/PERF.md, "PERF-REAL-3". Recording is still bounded
    by :data:`~loft_wire.overlay.MAX_PROVENANCE_FACES` (a 20 000-face import costs
    one face count, then stops), and one lineage per modeler instead of two halves
    what the cache must hold per user.

    Deterministic: same request → identical statuses, identical solved
    positions, byte-identical GLB and therefore identical ``mesh_glb_id``
    (RESEARCH §9). Never raises for geometry outcomes.

    REBUILD CACHE (docs/PERF.md fix #1). A request whose leading features hash
    identically to a cached prefix RESUMES there and evaluates only what is new,
    so appending to a 200-feature tree costs one feature instead of 27 s, and the
    ``/measure`` / ``/tessellate`` / ``/export`` / drawings calls that follow an
    ``/evaluate`` of the same tree reuse both the state and the artifacts. An
    EDIT at feature *k* resumes from the ladder rung at or below *k*
    (PERF-REAL-2), so editing #249 of 250 re-runs a handful of features rather
    than all of them. The cache is transparent by construction — a frontier hit
    hands over the very shapes a cold rebuild would have built, and a rung hit
    hands over the same fork a cold rebuild continues with at that rung (see
    :mod:`geometry.rebuild_cache`) — and a miss is only slower. NOT cached as a
    frontier: a tree that failed (its last-good state is not a resume point, and
    a failed op may have rewritten its argument in place — CM-6b), and a tree
    whose publish-time re-check found the body invalidated. The rungs such a tree
    passed BEFORE its failure stay: each is a fork taken while every feature so
    far had succeeded, so a later in-place rewrite cannot reach it.
    """
    keys = prefix_keys(
        request,
        capture_scope=_tool_scope_ids(request),
    )
    resume = _REBUILD_CACHE.take(keys)
    start = 0 if resume is None else resume.prefix_length
    checkpoint = None if resume is None else resume.checkpoint
    if checkpoint is None:
        state = EvaluationState(
            linear_deflection=request.linear_deflection,
            # OPT-IN tool capture (mirror-semantics §9): only features some
            # `features`-scope mirror names retain their reflectable tools, so a
            # tree without one pays zero extra memory and zero extra work.
            tool_scope_ids=_tool_scope_ids(request),
        )
        results: list[FeatureResult] = []
        last_good_feature_id: uuid.UUID | None = None
        suppressed_ids: set[uuid.UUID] = set()
    else:
        state = checkpoint.state
        results = list(checkpoint.results)
        last_good_feature_id = checkpoint.last_good_feature_id
        suppressed_ids = set(checkpoint.suppressed_ids)

    last_good_feature_id, failed, _consumed = _dispatch_prefix(
        request.features[start:],
        state,
        results,
        suppressed_ids,
        last_good_feature_id,
        offset=start,
        ladder=_Ladder(keys, speculative=False),
    )
    # A resume that consumed NOTHING is the same tree again, so the artifacts the
    # earlier call derived are still the right answer — provided nothing outside
    # the prefix key feeds them (materials; checked below).
    unchanged = (
        checkpoint.artifacts
        if checkpoint is not None and start == len(request.features)
        else None
    )

    # PUBLISH-TIME RE-CHECK (CM-6b, docs/GEOMETRY-QA.md 2026-07-30). Every body
    # was valid when :meth:`EvaluationState._admit` let it in, so an invalid one
    # HERE can only have been invalidated in place afterwards — which OCCT really
    # does: on a degenerate (tangent-pinch) body, ``BRepAlgoAPI`` rewrites its
    # ARGUMENT's subshapes, so the failed feature's boolean welded the void shut in
    # the last-good body it was handed (measured: the mirrored plate went from
    # 30793.6284 to 31865.9587 mm^3 without anyone assigning to it). Publishing
    # that body would put the exact wrong solid QA-1 reported back on the wire
    # under an error message, so the artifacts are WITHHELD instead — the same
    # honestly-null flavour a sketch-only tree produces (§6).
    body_invalidated = bool(state.bodies) and not all(
        body_is_valid(body) for body in state.bodies.values()
    )
    if body_invalidated:
        if not failed:
            # Nothing else failed, so the blame has nowhere else to go: the last
            # body-affecting feature's own artifact is what turned out unusable.
            results = _blame_invalidated_body(results, last_good_feature_id)
        last_good_feature_id = None

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
    # Material per body (docs/design/materials.md §2): the per-body override if
    # the request carries one, else the document default, else None = "nobody has
    # said what this is made of", which is reported as no mass at all.
    body_materials: dict[uuid.UUID, MaterialKey | None] = {
        base_id: resolve_body_material(request.materials, base_id)
        for base_id in state.bodies
    }
    body_measures: dict[uuid.UUID, ShapeProperties] = {}
    reused_nbytes: int | None = None
    if (
        state.bodies
        and not body_invalidated
        and unchanged is not None
        and unchanged.body_materials == body_materials
    ):
        # The same tree, again, made of the same stuff: this IS the previous
        # call's answer, reused byte-for-byte rather than re-derived (a re-measure
        # + re-tessellation is ~1 s of the 27 s an N=200 `/measure` used to cost).
        # The mesh id is re-PUT because the mesh store is a bounded cache that may
        # have evicted the payload; the put is content-addressed and idempotent,
        # so the id is the same one.
        shape, glb, mesh = unchanged.shape, unchanged.glb, unchanged.mesh
        properties, body_measures = unchanged.properties, unchanged.body_measures
        # Same state, same shape, same GLB: the checkpoint weighs what it weighed.
        reused_nbytes = None if checkpoint is None else checkpoint.nbytes
        mesh_glb_id = store_mesh_glb(glb)
    elif state.bodies and not body_invalidated:
        # Tree/insertion-ordered body set (§MB-0): a part with ONE body measures
        # and tessellates that bare solid — byte-identical to the pre-multi-body
        # path. A part with >1 body rolls up its mass properties ANALYTICALLY
        # (Σ over the body set, no re-mesh/boolean — the assembly pattern) and
        # tessellates a COMPOUND of all bodies in the fixed base-order, which
        # ``glb_stats`` sums over. Both are deterministic (RESEARCH §9).
        # The tessellated shape — a bare solid (one body) or a FLATTENED Compound
        # of every body's lumps (§MB-4). Same construction the provenance
        # snapshots use (:func:`_snapshot_shape`), so the final faces match the
        # last snapshot exactly (CLAUDE.md DRY).
        shape = _snapshot_shape(state.bodies)
        # Each body is measured with ITS OWN material's density (override, else
        # the document default, else none — docs/design/materials.md §2), so a
        # part that mixes materials rolls up a genuinely mass-weighted centre of
        # mass. A body with no material measures to mass_g=None and the whole
        # part's mass is then None: absent, never zero.
        for base_id, body in state.bodies.items():
            body_measures[base_id] = measure_shape(
                body, density_kg_m3=density_kg_m3(body_materials[base_id])
            )
        measured = list(body_measures.values())
        # ONE body — which may itself be a multi-lump Compound (a disjoint
        # boolean / multi-solid import, §MB-4) — reports its own measurement
        # verbatim (GProp + .shells() across its lumps). >1 body rolls up mass
        # properties ANALYTICALLY per body (no re-mesh, no boolean — the
        # assembly pattern); the flattened Compound tessellated above avoids a
        # nested Compound, which would give ``glb_stats`` a nondeterministic
        # traversal.
        properties = measured[0] if len(measured) == 1 else combine_properties(measured)
        glb, mesh = tessellate_glb(
            shape, request.linear_deflection, twisted=tree_has_twist(request)
        )
        mesh_glb_id = store_mesh_glb(glb)

    # Per-body lump count (§MB-4): tree/insertion-ordered over the last-good body
    # set, each entry keyed by the feature that created that body (§MB-0 identity).
    # The whole-part ``properties.topology.shells`` aggregate cannot distinguish a
    # disjoint-union / multi-solid-import body (one body, several lumps) from a
    # single-lump one, so this carries the honest per-body count for the consumer.
    # ``material`` / ``mass_g`` ride along per body (docs/design/materials.md §4):
    # the whole-part ``properties.mass_g`` goes null as soon as ONE body lacks a
    # material, and without this a consumer could not say WHICH body is missing
    # one. ``mass_g`` here is the very value measured above, never recomputed.
    bodies = [
        BodyLumpInfo(
            base_feature_id=base_id,
            lumps=lump_count(body),
            material=body_materials[base_id],
            mass_g=body_measures[base_id].mass_g,
        )
        for base_id, body in state.bodies.items()
        if not body_invalidated
    ]

    evaluation = TreeEvaluation(
        result=EvaluateTreeResult(
            part_id=request.part_id,
            tree_version=request.tree_version,
            features=results,
            bodies=bodies,
            mesh_glb_id=mesh_glb_id,
            properties=properties,
            last_good_feature_id=last_good_feature_id,
        ),
        solved_sketches=dict(state.solved_sketches),
        body=shape,
        glb=glb,
        mesh=mesh,
        bend_provenance=list(state.bend_provenance.values()),
        sheet_metal_defaults=next(iter(state.sheet_metal_defaults.values()), None),
        corner_reliefs=list(state.corner_reliefs.values()),
        unfold_body=state.sheet_metal_unfold_body,
        datum_planes=dict(state.datum_planes),
        provenance_recorder=state.provenance,
        topo_names=list(state.topo_names.values()),
    )

    # Offer this prefix as a resume point — but only once *evaluation* is dead,
    # because it is the object that hands these very shapes to the caller
    # (`body`, `unfold_body`, the sketch dict) and a resuming rebuild MUTATES
    # them. See :mod:`geometry.rebuild_cache`: ownership transfer is what makes a
    # hit byte-identical, and the `weakref` hand-back is what makes it safe under
    # the FastAPI threadpool. NOT offered when anything failed (a failed op may
    # have rewritten its argument in place — CM-6b) or when the publish-time
    # re-check found the body invalidated: neither is a state to build on.
    if not failed and not body_invalidated:
        _REBUILD_CACHE.store_on_release(
            evaluation,
            keys[len(request.features)],
            _Checkpoint(
                state=state,
                results=results,
                last_good_feature_id=last_good_feature_id,
                suppressed_ids=frozenset(suppressed_ids),
                artifacts=_published_artifacts(
                    body_materials, body_measures, properties, shape, glb, mesh
                ),
                nbytes=reused_nbytes,
            ),
        )
    return evaluation
