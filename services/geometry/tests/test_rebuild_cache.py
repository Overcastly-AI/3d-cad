"""The rebuild cache is not allowed to change a single byte (docs/PERF.md #1).

`geometry.rebuild_cache` makes `evaluate_tree` resume a tree whose feature
prefix hashes identically to one it already evaluated. That is the biggest
speedup in the service and also the most dangerous kind of change in a CAD
kernel: a cache that ever serves a body which does not correspond to its key is
the silent-wrong-geometry class this repo has closed four times. So the gates
here are correctness gates first and performance gates second, and the load-
bearing one is :func:`test_a_mutated_feature_is_never_served_from_a_stale_prefix`.

Everything is asserted against a COLD rebuild of the same request (the cache
emptied first), never against a hand-written expectation — the property is
TRANSPARENCY: warm and cold must be indistinguishable down to the GLB bytes and
the content-addressed ``mesh_glb_id``.
"""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# (the ladder's structural gates drive `_climb_rung` / `_Checkpoint` directly)
import copy
import ctypes
import dataclasses
import gc
import importlib
import importlib.util
import math
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import geometry.mesh_store as mesh_store
import pytest
from build123d import Solid
from build123d.topology.shape_core import Shape
from geometry.features import evaluate as evaluate_module
from geometry.features.evaluate import (
    EvaluationState,
    RecordedFeatureTools,
    RecordedToolGroup,
    evaluate_tree,
    rebuild_cache_stats,
    reset_rebuild_cache,
    warm_rebuild_cache,
)
from geometry.kernel import FaceProvenance
from geometry.kernel.fork import HEAP_BYTES_PER_FACE, fork_shapes
from geometry.rebuild_cache import (
    REBUILD_CACHE_CAPACITY,
    RUNG_DENSITY,
    RUNG_SPACING,
    PrefixCache,
    prefix_keys,
    rung_retained,
)
from loft_wire.features import EvaluateTreeRequest

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"


def _load_builders() -> ModuleType:
    """Load the tree builders by file path (importlib import-mode: test modules
    cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()

#: Small enough that a test does several rebuilds in a second or two, long
#: enough to carry the real mixed vocabulary (pockets, holes, fillets, a shell,
#: a datum, a revolve) — every point of ``housing_tree`` is a strict prefix of
#: every larger one, which is exactly the shape a resume test needs.
TREE_N = 12


def _payload(n: int = TREE_N) -> dict[str, Any]:
    return cast(dict[str, Any], _BUILDERS.housing_tree(n))


def _request(payload: dict[str, Any]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(payload)


@dataclass(frozen=True)
class Answer:
    """The observable result of an evaluation, for warm-vs-cold comparison."""

    statuses: tuple[str, ...]
    codes: tuple[str | None, ...]
    mesh_glb_id: str | None
    glb: bytes | None
    volume: float | None
    properties: object
    last_good: uuid.UUID | None
    #: The per-feature face fingerprints themselves (PERF-5b), not merely how
    #: many: a resume keeps the recorder — memo included — so warm-vs-cold
    #: equality here is what gates that attribution cannot depend on cache state.
    provenance: FaceProvenance


def _answer(request: EvaluateTreeRequest, *, record_history: bool = False) -> Answer:
    evaluation = evaluate_tree(request, record_history=record_history)
    result = evaluation.result
    return Answer(
        statuses=tuple(feature.status for feature in result.features),
        codes=tuple(
            feature.error.code if feature.error else None for feature in result.features
        ),
        mesh_glb_id=result.mesh_glb_id,
        glb=evaluation.glb,
        volume=None if result.properties is None else result.properties.volume,
        properties=result.properties,
        last_good=result.last_good_feature_id,
        provenance=evaluation.face_provenance,
    )


def _cold(request: EvaluateTreeRequest, *, record_history: bool = False) -> Answer:
    """The answer with the cache emptied — the reference every gate compares to."""
    reset_rebuild_cache()
    answer = _answer(request, record_history=record_history)
    reset_rebuild_cache()
    return answer


def _last_extrude_index(payload: dict[str, Any]) -> int:
    for index in range(len(payload["features"]) - 1, -1, -1):
        if payload["features"][index]["feature"]["type"] == "extrude":
            return index
    raise AssertionError("the housing tree always contains an extrude")


# --- The load-bearing gate ------------------------------------------------------


def test_a_mutated_feature_is_never_served_from_a_stale_prefix() -> None:
    """Change a feature DEEP in a warm tree; the answer must be the mutated one.

    THE test of this cache. The key is a rolling hash of the feature prefix, so a
    parameter change at feature *k* must invalidate every checkpoint at or past
    *k* — and the way that fails in practice is not a crash, it is a plausible
    body with the OLD dimension in it. So this asserts three things at once: the
    warm answer equals a COLD rebuild of the mutated tree byte-for-byte, it
    DIFFERS from the unmutated tree, and the difference is the mutation (a
    changed volume, not just changed bytes).
    """
    payload = _payload()
    request = _request(payload)
    unmutated = _cold(request)

    mutated_payload = copy.deepcopy(payload)
    index = _last_extrude_index(mutated_payload)
    params = mutated_payload["features"][index]["feature"]["params"]
    params["distance_mm"] = params["distance_mm"] + 1.5
    mutated = _request(mutated_payload)
    mutated_cold = _cold(mutated)

    # Warm the cache with the UNMUTATED tree, then ask for the mutated one.
    reset_rebuild_cache()
    _answer(request)
    warm = _answer(mutated)

    assert warm == mutated_cold, (
        "a warm rebuild of the mutated tree differs from a cold one — the cache "
        "served a prefix that does not correspond to its key"
    )
    assert warm.glb != unmutated.glb
    assert warm.volume != unmutated.volume, (
        "the mutation must actually move material, or this gate proves nothing"
    )


@pytest.mark.parametrize("mutation", ["suppress", "delete", "reorder", "deflection"])
def test_every_shape_of_prefix_change_invalidates(mutation: str) -> None:
    """A parameter is not the only way a prefix changes.

    Suppressing a feature, deleting one, reordering two, and changing the
    presentation deflection all produce a DIFFERENT body or a different mesh, and
    each has its own way of sneaking past a careless key: ``suppressed`` is a
    field on the feature (so it must be inside the hashed DTO), a deletion
    shortens the chain, a reorder keeps the same multiset of features, and
    ``linear_deflection`` is a request-level field the handlers read.
    """
    payload = _payload()
    reference = _cold(_request(payload))

    changed = copy.deepcopy(payload)
    if mutation == "suppress":
        changed["features"][_last_extrude_index(changed)]["feature"]["suppressed"] = (
            True
        )
    elif mutation == "delete":
        del changed["features"][_last_extrude_index(changed)]
    elif mutation == "reorder":
        index = _last_extrude_index(changed)
        features = changed["features"]
        features[index - 1], features[index] = features[index], features[index - 1]
    else:
        changed["linear_deflection"] = 0.05

    request = _request(changed)
    cold = _cold(request)
    reset_rebuild_cache()
    _answer(_request(payload))  # warm with the ORIGINAL tree
    assert _answer(request) == cold
    if mutation in ("suppress", "delete"):
        assert cold.glb != reference.glb, (
            "removing a feature must change the body, or the gate proves nothing"
        )


def test_a_scoped_mirror_added_later_invalidates_the_prefix() -> None:
    """The one input to a prefix that does NOT come from the prefix.

    A ``features``-scope mirror makes the features it names RETAIN their
    reflectable tools (mirror-semantics §9), so the state after k features
    genuinely depends on what follows. Found while building this cache: a prefix
    evaluated without the right capture set turns the later mirror into
    ``reference_unresolved``. The capture scope is therefore in the key, and this
    gate is what stops someone "optimising" it back out.
    """
    # housing_tree's motif cycle puts its first features-scope mirror at index
    # 25, so a 20-feature prefix is evaluated with an EMPTY capture scope and the
    # 30-feature tree needs the same prefix evaluated with a non-empty one.
    base = _request(_payload(20))
    longer = _request(_payload(30))
    assert any(item.feature.type == "mirror" for item in longer.features[20:]), (
        "this gate needs a mirror in the suffix"
    )

    cold = _cold(longer)
    reset_rebuild_cache()
    _answer(base)
    assert _answer(longer) == cold


# --- Transparency: a hit must be indistinguishable from a cold rebuild ----------


@pytest.mark.parametrize("appended", [1, 2, 5])
def test_appending_to_a_warm_tree_is_byte_identical_to_a_cold_rebuild(
    appended: int,
) -> None:
    """The headline case, and the one that would show drift if the cache copied.

    Every re-materialisation of an OCCT shape (``BRepBuilderAPI_Copy``, a BREP
    round-trip) preserves the geometry and still moves the tessellation by a ULP,
    which would make ``mesh_glb_id`` depend on cache state. The cache therefore
    hands over the ORIGINAL shapes; this asserts the consequence at three append
    lengths, including the GLB bytes and the content address derived from them.
    """
    base, target = TREE_N, TREE_N + appended
    cold = _cold(_request(_payload(target)))
    reset_rebuild_cache()
    _answer(_request(_payload(base)))
    warm = _answer(_request(_payload(target)))
    assert warm.glb == cold.glb
    assert warm.mesh_glb_id == cold.mesh_glb_id
    assert warm.properties == cold.properties
    assert rebuild_cache_stats().hits >= 1


def test_re_evaluating_the_same_tree_reuses_the_published_artifacts() -> None:
    """`/measure`, `/tessellate`, `/export` and drawings each used to pay a full
    rebuild of a tree ``/evaluate`` had just built. A repeat resumes with zero
    features left to run, so it also reuses the measurement and the mesh — and
    must still return exactly what a cold rebuild returns."""
    request = _request(_payload())
    cold = _cold(request)
    reset_rebuild_cache()
    _answer(request)
    before = rebuild_cache_stats().hits
    assert _answer(request) == cold
    assert rebuild_cache_stats().hits == before + 1


def test_a_material_change_alone_still_reports_the_new_mass() -> None:
    """Materials are deliberately NOT in the key (they are read only after the
    dispatch loop), so the memoised artifacts carry the resolved per-body
    material and are reused only when it matches. A tree re-evaluated with a
    different material must therefore re-measure, not replay a stale mass."""
    payload = _payload()
    plain = _request(payload)
    with_material = _request(
        {**payload, "materials": {"default_material": "steel_1018"}}
    )
    cold_plain, cold_material = _cold(plain), _cold(with_material)
    assert cold_plain.properties != cold_material.properties

    reset_rebuild_cache()
    _answer(plain)
    assert _answer(with_material) == cold_material
    assert _answer(plain) == cold_plain


def test_history_recording_never_resumes_a_prefix_that_has_no_history() -> None:
    """Per-face provenance walks a snapshot per body-affecting feature. A prefix
    evaluated WITHOUT history has none, so serving it to an overlay rebuild would
    silently mis-attribute every face the prefix built. The two callers get two
    lineages (``record_history`` is in the key), and this asserts the history a
    warm overlay sees is the COMPLETE one a cold overlay sees."""
    request = _request(_payload())
    cold = _cold(request, record_history=True)
    assert len(cold.provenance.snapshots) > 0

    reset_rebuild_cache()
    _answer(request)  # a plain evaluate first — the tempting stale prefix
    warm = _answer(request, record_history=True)
    assert warm.provenance == cold.provenance
    assert warm.glb == cold.glb


# --- What must NOT be cached ---------------------------------------------------


def test_a_failed_tree_is_not_a_resume_point() -> None:
    """A feature that fails may have left OCCT's boolean rewriting its ARGUMENT
    in place (CM-6b), so the last-good state of a failed tree is not something to
    build on. The failure must reproduce identically on the next call rather than
    being papered over (or, worse, cached) — asserted by comparing to cold."""
    payload = _payload()
    index = _last_extrude_index(payload)
    payload["features"][index]["feature"]["params"]["profile"] = {
        "kind": "feature",
        "feature_id": str(uuid.UUID(int=0xDEAD)),
    }
    request = _request(payload)
    cold = _cold(request)
    assert "error" in cold.statuses

    reset_rebuild_cache()
    assert _answer(request) == cold
    assert _answer(request) == cold


# --- Ownership, concurrency and bounds -----------------------------------------


def test_an_evaluation_still_in_use_is_never_lent_to_another_rebuild() -> None:
    """The safety property behind ownership transfer.

    A hit hands over the very shapes the previous caller was given, and OCCT
    booleans rewrite their arguments in place — so an entry may only be served
    once nothing else can touch it. The cache therefore stores a checkpoint on
    the RELEASE of the ``TreeEvaluation`` that owns those shapes: while a caller
    holds its evaluation (here, ``/export`` still writing a STEP file), a second
    rebuild of the same tree must MISS the frontier and build its own body.

    A LADDER rung may serve it (PERF-REAL-2) — a rung is a fork nobody else
    holds, and the caller gets a fork of THAT — so "missed the frontier" is
    asserted as "no frontier hit, and resumed short of the full tree".
    """
    request = _request(_payload())
    cold = _cold(request)
    reset_rebuild_cache()

    held = evaluate_tree(request)  # kept alive for the whole test
    before = rebuild_cache_stats()
    assert _answer(request) == cold, "a concurrent rebuild must still be correct"
    after = rebuild_cache_stats()
    assert after.hits - after.rung_hits == before.hits - before.rung_hits, (
        "the frontier entry was served while its owner was still using it"
    )
    assert after.resumed_features - before.resumed_features < len(request.features)
    assert held.body is not None


def test_a_caller_that_stashes_a_body_keeps_its_evaluation() -> None:
    """The ownership contract, enforced where it was actually broken.

    A ``TreeEvaluation`` is the handle on the shapes it produced: the checkpoint
    becomes re-servable when the evaluation dies, and a resume MUTATES those
    shapes in place. The claim cannot be pinned to the shapes themselves (the
    checkpoint holds them, so the token would never be collectable — measured:
    zero stores, a permanently cold cache), so the rule has to hold at the call
    site. ``assembly/evaluate.py`` is the one caller that stashed
    ``evaluation.body`` in a per-request dict and dropped the evaluation; this
    fails loudly if a future refactor "cleans up" the field that fixed it.
    """
    module = importlib.import_module("geometry.assembly.evaluate")
    part_result = cast(Any, module)._PartResult
    fields = {field.name for field in dataclasses.fields(part_result)}
    assert "evaluation" in fields, (
        "_PartResult must retain the TreeEvaluation that produced its body — "
        "dropping it lets a concurrent rebuild of the same part tree mutate a "
        "body this assembly is still placing (docs/PERF.md fix #1)"
    )
    source = Path(module.__file__ or "").read_text("utf-8")
    assert "evaluation=evaluation," in source


def test_concurrent_rebuilds_of_one_tree_all_get_the_same_answer() -> None:
    """Geometry handlers run in FastAPI's threadpool, so two requests for one
    part really do overlap. Whatever the interleaving of takes and stores, every
    thread must return the cold answer."""
    request = _request(_payload(10))
    cold = _cold(request)
    reset_rebuild_cache()

    answers: list[Answer] = []
    lock = threading.Lock()

    def run() -> None:
        answer = _answer(request)
        with lock:
            answers.append(answer)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert answers == [cold] * 3


@dataclass
class _FakePayload:
    """A checkpoint stand-in for the cache's own mechanics (no OCCT)."""

    name: str
    detached: list[str] = field(default_factory=list[str])
    nbytes: int = 0

    def detach(self) -> None:
        self.detached.append(self.name)

    def weigh(self) -> int:
        return self.nbytes

    def fork(self) -> _FakePayload:
        return _FakePayload(f"{self.name}'")


def test_the_cache_is_bounded_and_evicts_the_least_recently_used() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(2)
    for name in ("a", "b", "c"):
        cache.store(f"key-{name}", _FakePayload(name))
    assert cache.take(["root", "key-a"]) is None, "the oldest entry must be evicted"
    assert cache.take(["root", "key-c"]) is not None
    assert cache.stats.evictions == 1


def test_a_warm_can_never_evict_a_live_checkpoint() -> None:
    """THE load-bearing rule of CONC-4, as a unit.

    The docstring of ``rebuild_cache.py`` always said a warm must not evict a
    checkpoint a live request is about to use, and the load run measured it doing
    exactly that on a full LRU (evictions 24 -> 35, hit rate 0.40 -> 0.31). A
    guess losing its slot to real work is correct; real work losing its slot to a
    guess is a self-inflicted regression, so the speculative store is REFUSED
    instead — the warm achieved nothing, which is the acceptable failure.
    """
    cache: PrefixCache[_FakePayload] = PrefixCache(2)
    cache.store("live-a", _FakePayload("live-a"))
    cache.store("live-b", _FakePayload("live-b"))

    assert cache.store("guess", _FakePayload("guess"), speculative=True) is False
    assert cache.stats.speculative_refused == 1
    assert cache.stats.evictions == 0, "no live checkpoint may be dropped for a guess"

    assert cache.take(["root", "guess"]) is None
    assert cache.take(["root", "live-a"]) is not None, "the LRU live entry survived"
    assert cache.take(["root", "live-b"]) is not None


def test_a_live_checkpoint_evicts_speculation_before_older_live_work() -> None:
    """The other half of the rule: speculation is always the first victim, even
    when it is the NEWEST entry and the live checkpoint beside it is the LRU."""
    cache: PrefixCache[_FakePayload] = PrefixCache(2)
    cache.store("live-old", _FakePayload("live-old"))
    cache.store("guess", _FakePayload("guess"), speculative=True)

    cache.store("live-new", _FakePayload("live-new"))

    assert cache.stats.evictions == 1
    assert cache.take(["root", "guess"]) is None, "the guess gave up its slot"
    assert cache.take(["root", "live-old"]) is not None, "live work outlives a guess"


def test_speculation_may_replace_speculation() -> None:
    """A weaker claim than live work is not the same as no claim: a new warm can
    still take a stale warm's slot, which is what keeps the prefetch useful on a
    worker whose cache is not full of other people's checkpoints."""
    cache: PrefixCache[_FakePayload] = PrefixCache(2)
    cache.store("live", _FakePayload("live"))
    cache.store("guess-old", _FakePayload("guess-old"), speculative=True)

    assert cache.store("guess-new", _FakePayload("guess-new"), speculative=True) is True

    assert cache.stats.speculative_refused == 0
    assert cache.take(["root", "guess-old"]) is None
    assert cache.take(["root", "guess-new"]) is not None
    assert cache.take(["root", "live"]) is not None


def test_a_resumed_entry_reports_the_claim_it_was_stored_with() -> None:
    """``take`` carries the flag out because the warm's re-store path has to put
    it back unchanged: laundering a guess into live work (or demoting a live
    checkpoint to evictable) would defeat both halves of the rule above."""
    cache: PrefixCache[_FakePayload] = PrefixCache(4)
    cache.store("live", _FakePayload("live"))
    cache.store("guess", _FakePayload("guess"), speculative=True)

    live = cache.take(["root", "live"])
    guess = cache.take(["root", "guess"])
    assert live is not None and live.speculative is False
    assert guess is not None and guess.speculative is True


def test_the_capacity_is_sized_for_more_than_four_modelers() -> None:
    """CONC-4: a working modeler holds TWO lineages (the plain one an edit
    rebuilds, and the ``record_history`` one a face pick uses), so the old
    capacity of 8 was exactly four users and the fifth cost everyone 79x on
    ``/measure``. docs/OPERATIONS.md §6 sizes a host for up to 8 concurrent
    modelers, and without affinity all of them can land on one worker.
    """
    assert REBUILD_CACHE_CAPACITY >= 8 * 2, (
        "8 modelers x 2 lineages is the working set one worker must hold"
    )


def test_taking_an_entry_removes_it() -> None:
    """Ownership transfer, stated as a unit: the same checkpoint is never handed
    to two rebuilds, and ``detach`` runs exactly once, on the cache's side."""
    cache: PrefixCache[_FakePayload] = PrefixCache(4)
    payload = _FakePayload("only")
    cache.store("key", payload)
    assert payload.detached == ["only"]
    taken = cache.take(["root", "key"])
    assert taken is not None and taken[1] is payload
    assert cache.take(["root", "key"]) is None


def test_the_longest_matching_prefix_wins() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(4)
    cache.store("k2", _FakePayload("short"))
    cache.store("k5", _FakePayload("long"))
    taken = cache.take(["k0", "k1", "k2", "k3", "k4", "k5"])
    assert taken is not None
    assert taken[0] == 5 and taken[1].name == "long"


def test_prefix_keys_roll_forward_and_break_at_the_change() -> None:
    """The key chain's two properties, without any geometry: appending leaves
    every earlier key untouched (so an append hits), and editing feature *k*
    changes exactly the keys from *k+1* on (so nothing before it is invalidated
    and nothing after it survives)."""
    payload = _payload(10)
    base = prefix_keys(_request(payload), capture_scope=(), record_history=False)
    longer_payload = _payload(12)
    longer = prefix_keys(
        _request(longer_payload), capture_scope=(), record_history=False
    )
    assert longer[: len(base)] == base

    edited_payload = copy.deepcopy(payload)
    index = _last_extrude_index(edited_payload)
    params = edited_payload["features"][index]["feature"]["params"]
    params["distance_mm"] = params["distance_mm"] + 1.0
    edited = prefix_keys(
        _request(edited_payload), capture_scope=(), record_history=False
    )
    assert edited[: index + 1] == base[: index + 1]
    assert all(
        a != b for a, b in zip(edited[index + 1 :], base[index + 1 :], strict=True)
    )


def test_the_capture_scope_and_history_flag_are_part_of_the_key() -> None:
    request = _request(_payload(10))
    plain = prefix_keys(request, capture_scope=(), record_history=False)
    scoped = prefix_keys(
        request, capture_scope=(uuid.UUID(int=7),), record_history=False
    )
    history = prefix_keys(request, capture_scope=(), record_history=True)
    assert plain[0] != scoped[0] != history[0] != plain[0]
    assert len({plain[-1], scoped[-1], history[-1]}) == 3


# --- The prefetch seam ---------------------------------------------------------


def test_a_warm_caches_a_prefix_and_cannot_publish_a_body() -> None:
    """``warm_rebuild_cache`` returns an integer — by construction it cannot hand
    back a speculative body, mesh id or mass properties. What it leaves behind is
    servable only through the ordinary key, so the evaluation that follows must
    still be byte-identical to a cold one."""
    request = _request(_payload())
    cold = _cold(request)
    reset_rebuild_cache()

    cached = warm_rebuild_cache(request)
    assert cached == len(request.features)
    hits = rebuild_cache_stats().hits
    assert _answer(request) == cold
    assert rebuild_cache_stats().hits == hits + 1


def test_a_warm_is_bounded_and_cancellable() -> None:
    """Speculation on a four-core box must be interruptible; the honest
    granularity is one feature (a single uninterruptible OCCT call)."""
    request = _request(_payload())
    reset_rebuild_cache()
    assert warm_rebuild_cache(request, budget_s=0.0) == 0

    reset_rebuild_cache()
    calls = {"n": 0}

    def cancel_after_three() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    cached = warm_rebuild_cache(request, cancelled=cancel_after_three)
    assert 0 < cached < len(request.features), "a cancelled warm keeps what it built"
    # And what it kept is a legitimate resume point, not a half-feature.
    cold = _cold(request)
    reset_rebuild_cache()
    warm_rebuild_cache(request, cancelled=cancel_after_three)
    calls["n"] = 0
    assert _answer(request) == cold


# --- The checkpoint ladder (PERF-REAL-2) ----------------------------------------

#: Two full rungs (at RUNG_SPACING and 2 * RUNG_SPACING) with at least two
#: features past the second, so every rung has a feature on BOTH sides of it and
#: the feature after the last rung has a consumer.
LADDER_N = 2 * RUNG_SPACING + 3

#: The numeric params the edit gate nudges, in the order it looks for them.
_NUDGEABLE = (
    "distance_mm",
    "depth_mm",
    "diameter_mm",
    "radius_mm",
    "thickness_mm",
    "offset_mm",
    "angle_deg",
)


def _edit_at(payload: dict[str, Any], index: int) -> dict[str, Any]:
    """*payload* with feature *index* changed in a way that changes the answer.

    A numeric parameter is shrunk 3 % where the feature has one (a revolve's 360
    degrees must go DOWN to stay valid); a feature with no dimension (a sketch,
    a pattern, a mirror) is suppressed instead, which also moves its consumers.
    Either way the key of every prefix past *index* changes.
    """
    edited = copy.deepcopy(payload)
    feature = edited["features"][index]["feature"]
    params = feature.get("params", {})
    for name in _NUDGEABLE:
        value = params.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
            params[name] = value * 0.97
            return edited
    feature["suppressed"] = True
    return edited


@pytest.mark.parametrize(
    "side", [-1, 0, 1], ids=["last-inside", "first-outside", "next"]
)
@pytest.mark.parametrize("rung", [RUNG_SPACING, 2 * RUNG_SPACING])
def test_an_edit_beside_a_rung_resumes_from_the_rung_below_it_and_no_further(
    rung: int, side: int
) -> None:
    """THE ladder gate: invalidation around every rung, in both directions.

    A rung at prefix length *r* holds the state after features ``0..r-1``, under
    ``keys[r]``. So:

    * an edit to feature ``r - 1`` (the LAST one inside the rung) must not be
      served that rung — it has seen the old feature. It must resume from the
      rung below (``r - RUNG_SPACING``), or rebuild;
    * an edit to feature ``r`` or ``r + 1`` must be served exactly rung *r*.

    Filed against PERF-REAL-2's "an edit at feature k must never serve a cached
    state computed from a pre-edit feature <= k", and written so it fails when
    the rung's key is off by one EITHER way. Storing the state under ``keys[r-1]``
    serves an edit at ``r - 1`` a state that already contains the old feature;
    storing it under ``keys[r+1]`` serves an edit at ``r + 1`` a state MISSING
    feature ``r``. Both are caught twice: by the resume length, and by the answer
    differing from a cold rebuild of the edited tree (GLB bytes, mesh id, mass
    properties, statuses).
    """
    payload = _payload(LADDER_N)
    index = rung + side
    edited = _request(_edit_at(payload, index))
    original_cold = _cold(_request(payload))
    edited_cold = _cold(edited)
    assert edited_cold != original_cold, "the edit must change the answer"

    reset_rebuild_cache()
    _answer(_request(payload))  # builds the ladder under the ORIGINAL keys
    before = rebuild_cache_stats()
    warm = _answer(edited)
    after = rebuild_cache_stats()

    # The property first (the answer), then the mechanism (where it resumed).
    assert warm == edited_cold, (
        "a ladder resume differs from a cold rebuild of the edited tree"
    )
    expected = (index // RUNG_SPACING) * RUNG_SPACING
    assert after.resumed_features - before.resumed_features == expected, (
        f"an edit at feature {index} must resume from the rung at {expected}"
    )
    assert expected <= index
    if expected:
        assert after.rung_hits == before.rung_hits + 1, "a rung must have served it"


def test_a_ladder_resume_keeps_face_provenance_exact() -> None:
    """The ``record_history`` lineage forks its provenance recorder at every rung
    (the memo is dropped: a fork has none of the original ``TShape``s). The
    fingerprints a face pick attributes with must still equal a cold rebuild's,
    so an overlay after an edit highlights the same faces a fresh worker would."""
    payload = _payload(LADDER_N)
    edited = _request(_edit_at(payload, 2 * RUNG_SPACING))
    cold = _cold(edited, record_history=True)

    reset_rebuild_cache()
    _answer(_request(payload), record_history=True)
    before = rebuild_cache_stats()
    warm = _answer(edited, record_history=True)
    assert rebuild_cache_stats().rung_hits == before.rung_hits + 1
    assert warm == cold
    assert warm.provenance.snapshots, "the gate must compare a real history"


def test_a_rung_serves_every_edit_of_a_dragged_parameter() -> None:
    """A rung is never handed out, only forked — so a parameter dragged through
    three values resumes from the SAME rung three times, and each answer is its
    own cold rebuild's."""
    payload = _payload(LADDER_N)
    index = 2 * RUNG_SPACING
    assert payload["features"][index]["feature"]["type"] == "revolve"
    drags: list[EvaluateTreeRequest] = []
    for angle in (300.0, 280.0, 260.0):
        dragged = copy.deepcopy(payload)
        dragged["features"][index]["feature"]["params"]["angle_deg"] = angle
        drags.append(_request(dragged))
    references = [_cold(request) for request in drags]

    reset_rebuild_cache()
    _answer(_request(payload))  # ONE ladder, built once, for all three drags
    for request, reference in zip(drags, references, strict=True):
        before = rebuild_cache_stats()
        warm = _answer(request)
        after = rebuild_cache_stats()
        assert after.rung_hits == before.rung_hits + 1
        assert after.resumed_features - before.resumed_features == index
        assert warm == reference
    assert len({reference.volume for reference in references}) == 3


def test_rung_retention_is_monotone_logarithmic_and_leaves_bounded_gaps() -> None:
    """The thinning rule, checked exhaustively rather than by example.

    * MONOTONE: a rung dropped when the frontier was at U is never wanted again at
      U + 1 — which is what makes it safe to thin as the evaluation goes;
    * the newest rung is always kept;
    * at most ``2**density * U.bit_length()`` rungs survive, not U;
    * the gap below any unit is under ``2**(1 - density)`` times its distance from
      the frontier — the edit-cost bound the docstring promises.
    """
    for frontier in range(1, 300):
        kept = [u for u in range(1, frontier + 1) if rung_retained(u, frontier)]
        later = {u for u in range(1, frontier + 1) if rung_retained(u, frontier + 1)}
        assert later <= set(kept), f"a dropped rung came back at frontier {frontier}"
        assert kept[-1] == frontier
        assert len(kept) <= (1 << RUNG_DENSITY) * frontier.bit_length()
        for unit in range(1, frontier + 1):
            below = max((u for u in kept if u <= unit), default=0)
            distance = frontier - unit + 1
            assert unit - below < distance / 2 ** (RUNG_DENSITY - 1), (frontier, unit)


def _chain(name: str, length: int) -> list[str]:
    return [f"{name}{i}" for i in range(length + 1)]


def test_a_rung_is_handed_out_as_a_fork_and_stays_on_the_ladder() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(4, rung_spacing=2)
    chain = _chain("a", 6)
    rung = _FakePayload("rung")
    assert cache.store_rung(chain, 4, rung, nbytes=10)
    first = cache.take(chain)
    second = cache.take(chain)
    assert first is not None and second is not None
    assert first.rung and first.prefix_length == 4
    assert first.checkpoint is not rung and first.checkpoint.name == "rung'"
    assert second.checkpoint is not first.checkpoint
    assert rung.detached == [], "a rung is a fresh fork; nothing to detach"
    assert cache.stats.rung_hits == 2


def test_the_longest_prefix_wins_across_frontier_and_ladder() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(4, rung_spacing=2)
    chain = _chain("a", 8)
    cache.store_rung(chain, 6, _FakePayload("rung6"), nbytes=1)
    cache.store(chain[5], _FakePayload("frontier5"))
    taken = cache.take(chain)
    assert taken is not None and taken.prefix_length == 6 and taken.rung

    cache.store(chain[6], _FakePayload("frontier6"))
    taken = cache.take(chain)
    assert taken is not None and taken.prefix_length == 6 and not taken.rung, (
        "at equal length the frontier wins: it needs no fork"
    )
    assert taken.checkpoint.name == "frontier6"


def test_a_rung_off_the_grid_is_refused() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(4, rung_spacing=4)
    with pytest.raises(ValueError):
        cache.store_rung(_chain("a", 8), 3, _FakePayload("x"), nbytes=1)


def test_the_ladder_is_bounded_by_count_and_by_bytes() -> None:
    """The memory bound, as a unit: LRU-first eviction on the rung COUNT and on
    the total estimated BYTES, and a rung over the per-rung cap is never kept."""
    cache: PrefixCache[_FakePayload] = PrefixCache(
        4, rung_capacity=3, rung_byte_budget=100, rung_spacing=1
    )
    for name in "abcd":
        cache.store_rung(_chain(name, 1), 1, _FakePayload(name), nbytes=10)
    assert cache.stats.rungs == 3 and cache.stats.rung_evictions == 1
    assert cache.take(_chain("a", 1)) is None, "the LRU rung went first"

    cache.store_rung(_chain("e", 1), 1, _FakePayload("e"), nbytes=85)
    assert cache.stats.rung_bytes <= 100
    assert cache.take(_chain("e", 1)) is not None

    assert not cache.store_rung(_chain("f", 1), 1, _FakePayload("f"), nbytes=101)
    assert cache.stats.rung_bytes <= 100

    capped: PrefixCache[_FakePayload] = PrefixCache(
        4, rung_byte_budget=100, rung_max_bytes=40, rung_spacing=1
    )
    assert capped.store_rung(_chain("g", 1), 1, _FakePayload("g"), nbytes=40)
    assert not capped.store_rung(_chain("h", 1), 1, _FakePayload("h"), nbytes=41), (
        "a rung over the per-rung cap is refused, whatever room is left"
    )
    assert capped.stats.rungs == 1


def test_a_speculative_rung_never_evicts_a_live_one() -> None:
    """The frontier's CONC-4 rule, applied to rungs: a warm's rung is the first
    victim, and a warm's rung that could only be kept by evicting live rungs is
    refused rather than stored."""
    cache: PrefixCache[_FakePayload] = PrefixCache(
        4, rung_capacity=2, rung_byte_budget=1000, rung_spacing=1
    )
    cache.store_rung(_chain("live", 1), 1, _FakePayload("live"), nbytes=1)
    assert cache.store_rung(
        _chain("guess", 1), 1, _FakePayload("guess"), nbytes=1, speculative=True
    )
    cache.store_rung(_chain("newer", 1), 1, _FakePayload("newer"), nbytes=1)
    assert cache.take(_chain("guess", 1)) is None, "speculation is evicted first"
    assert cache.take(_chain("live", 1)) is not None, "older live work survives"
    assert cache.take(_chain("newer", 1)) is not None

    assert not cache.store_rung(
        _chain("late", 1), 1, _FakePayload("late"), nbytes=1, speculative=True
    ), "every slot is live work, so the guess yields"
    assert cache.stats.rungs == 2

    # A guess that live work then passes over is promoted, not duplicated.
    promoted: PrefixCache[_FakePayload] = PrefixCache(
        4, rung_capacity=2, rung_byte_budget=1000, rung_spacing=1
    )
    promoted.store_rung(_chain("q", 1), 1, _FakePayload("q"), nbytes=1)
    promoted.store_rung(
        _chain("p", 1), 1, _FakePayload("p"), nbytes=1, speculative=True
    )
    promoted.store_rung(_chain("p", 1), 1, _FakePayload("again"), nbytes=1)
    promoted.store_rung(_chain("r", 1), 1, _FakePayload("r"), nbytes=1)
    kept = promoted.take(_chain("p", 1))
    assert kept is not None, "promoted to live, it outlives the older live rung"
    assert kept.checkpoint.name == "p'", "the original checkpoint, not the re-offer"
    assert promoted.take(_chain("q", 1)) is None


def test_thinning_only_touches_its_own_chain() -> None:
    """Retention is per chain: a long evaluation of part A must not thin part B's
    rungs, which sit at the same positions under different keys."""
    cache: PrefixCache[_FakePayload] = PrefixCache(4, rung_spacing=1)
    other = _chain("b", 40)
    for length in range(1, 5):
        cache.store_rung(other, length, _FakePayload(f"b{length}"), nbytes=1)
    mine = _chain("a", 40)
    for length in range(1, 41):
        cache.store_rung(mine, length, _FakePayload(f"a{length}"), nbytes=1)
    assert cache.rung_lengths(other) == [1, 2, 3, 4]
    kept = cache.rung_lengths(mine)
    assert kept == [u for u in range(1, 41) if rung_retained(u, 40)]
    assert len(kept) < 40


#: Every EvaluationState field, by how ``EvaluationState.fork`` must treat it.
#: A new field fails ``test_every_state_field_is_classified_for_the_fork`` until
#: somebody decides which set it belongs in — and if it holds a kernel shape,
#: adds it to ``EvaluationState.shape_slots`` (which both the fork and the
#: detach walk), or a ladder rung would share it with the evaluation that carries
#: on past the rung. The name census forces the decision; the BEHAVIOUR is gated
#: by ``test_every_shape_the_state_holds_is_forked_and_detached``.
_FORKED_FIELDS = frozenset(
    {
        "bodies",
        "sheet_metal_unfold_body",
        "last_cut_tools",
        "feature_tools",
        "provenance",
        "solved_sketches",
        "sketch_planes",
        "datum_planes",
        "sheet_metal_defaults",
        "bend_provenance",
        "corner_reliefs",
        "scoped_feature_types",
    }
)
_SHARED_IMMUTABLE_FIELDS = frozenset(
    {
        "linear_deflection",
        "active_body_id",
        "prev_body_feature_id",
        "last_cut_feature_id",
        "last_cut_body_id",
        "tool_scope_ids",
    }
)


def test_every_state_field_is_classified_for_the_fork() -> None:
    names = {item.name for item in dataclasses.fields(EvaluationState)}
    assert names == _FORKED_FIELDS | _SHARED_IMMUTABLE_FIELDS, (
        "EvaluationState gained or lost a field: classify it for "
        "EvaluationState.fork (and EvaluationState.shape_slots if it holds a shape)"
    )


def _same(a: Shape[Any], b: Shape[Any]) -> bool:
    """OCCT's own identity test: same ``TShape`` (and location)."""
    return bool(a.wrapped.IsSame(b.wrapped))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def test_a_fork_shares_no_shape_with_its_original_and_keeps_its_own_sharing() -> None:
    """The two properties the ladder rests on, on a hand-built state.

    * NOTHING shared with the original: every forked shape is a different
      ``TShape`` (``IsSame`` false), so features evaluated after a rung cannot
      rewrite the rung in place;
    * EVERYTHING shared inside the state stays shared: the body, the tool that
      shaped it and the unfold body are one shape here, and must still be one
      shape in the fork — copying them separately would turn one B-rep into
      three unrelated ones as far as a later boolean is concerned.
    """
    body = Solid.make_box(10, 20, 30)
    cutter = Solid.make_box(2, 2, 40)
    body_id, tool_feature = uuid.UUID(int=1), uuid.UUID(int=2)
    state = EvaluationState(
        linear_deflection=0.1,
        bodies={body_id: body},
        last_cut_tools=[cutter],
        feature_tools={
            tool_feature: RecordedFeatureTools(
                body_id=body_id, groups=[RecordedToolGroup("fuse", [body, cutter])]
            )
        },
        sheet_metal_unfold_body=body,
        active_body_id=body_id,
        tool_scope_ids=frozenset({tool_feature}),
    )
    twin, nbytes = state.fork(weigh=True)

    forked_body = twin.bodies[body_id]
    assert twin.sheet_metal_unfold_body is not None
    assert twin.last_cut_tools is not None
    group = twin.feature_tools[tool_feature].groups[0]
    originals = [body, cutter]
    for shape in (forked_body, twin.sheet_metal_unfold_body, *twin.last_cut_tools):
        assert not any(_same(shape, original) for original in originals)
    assert _same(forked_body, twin.sheet_metal_unfold_body)
    assert _same(forked_body, group.tools[0])
    assert _same(twin.last_cut_tools[0], group.tools[1])
    assert fork_shapes([body, cutter, body]).faces == 12, (
        "two boxes' faces, the shared one counted once"
    )
    assert nbytes >= 12 * HEAP_BYTES_PER_FACE, "a weighed fork carries its weight"
    assert state.fork()[1] == 0, "an unweighed fork pays nothing to weigh"
    assert forked_body.volume == pytest.approx(body.volume, rel=0, abs=0)
    assert twin.bodies is not state.bodies
    assert twin.feature_tools is not state.feature_tools
    assert twin.provenance is not state.provenance

    target = EvaluationState(linear_deflection=0.5)
    target.adopt(twin)
    assert target.bodies is twin.bodies and target.linear_deflection == 0.1


@pytest.mark.parametrize(
    ("dragged_at", "steps", "probe_at", "expected"),
    [(241, 40, 200, 200), (200, 6, 100, 96)],
    ids=["drag-241-then-edit-200", "drag-200-then-edit-100"],
)
def test_a_drag_session_does_not_age_out_the_live_chains_deep_rungs(
    dragged_at: int, steps: int, probe_at: int, expected: int
) -> None:
    """A hit proves the whole chain below it is live (PERF-REAL-2 review,
    GQA-LADDER-2).

    Each drag step resumes from the rung below the dragged feature and lays
    dead-branch rungs above it. If only the rung that served the hit were
    touched, those dead rungs would outlive the live chain's deep rungs in the
    LRU — measured: 40 drags on #241 left the chain with ONE rung, and 6 values
    dragged on #200 evicted every rung from 32 to 192 — and the next edit
    further in would rebuild from zero. Rungs are weighed at the tray's
    measured ~2 MiB each, so the production byte budget is what binds.
    """
    n, spacing, weight = 250, RUNG_SPACING, 2 * 1024 * 1024
    cache: PrefixCache[_FakePayload] = PrefixCache(4)  # production rung bounds
    base = _chain("k", n)
    for length in range(spacing, n + 1, spacing):
        cache.store_rung(base, length, _FakePayload(str(length)), nbytes=weight)
    assert expected in cache.rung_lengths(base)
    resume_at = (dragged_at // spacing) * spacing

    for step in range(steps):
        dragged = base[: dragged_at + 1] + [
            f"d{step}_{i}" for i in range(dragged_at + 1, n + 1)
        ]
        taken = cache.take(dragged)
        assert taken is not None and taken.prefix_length == resume_at
        for length in range(resume_at + spacing, n + 1, spacing):
            cache.store_rung(dragged, length, _FakePayload("dead"), nbytes=weight)
    assert cache.stats.rung_evictions > 0, "the session must have pressed the bound"

    edited = base[: probe_at + 1] + [f"e{i}" for i in range(probe_at + 1, n + 1)]
    taken = cache.take(edited)
    assert taken is not None and taken.prefix_length == expected, (
        f"an edit at #{probe_at} after a drag session on #{dragged_at} must still "
        f"resume from rung {expected}"
    )


def _walk_shapes(value: object) -> list[Shape[Any]]:
    """Every build123d shape reachable from *value* — derived GENERICALLY.

    Deliberately independent of ``EvaluationState.shape_slots``: it walks dicts,
    lists, tuples and dataclasses without knowing any field name, so a shape the
    enumerator forgets is still found here and the comparison below fails.
    """
    if isinstance(value, Shape):
        return [cast(Shape[Any], value)]
    items: list[object]
    if isinstance(value, dict):
        items = list(cast(dict[object, object], value).values())
    elif isinstance(value, (list, tuple)):
        items = list(cast(list[object], value))
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        items = [getattr(value, item.name) for item in dataclasses.fields(value)]
    else:
        return []
    return [shape for item in items for shape in _walk_shapes(item)]


def _populated_state() -> EvaluationState:
    """A state with a shape in EVERY shape-bearing slot, and some sharing."""
    body, other = Solid.make_box(10, 20, 30), Solid.make_box(5, 5, 5)
    cutter = Solid.make_box(2, 2, 40)
    body_id, other_id, tool_feature = (uuid.UUID(int=i) for i in (1, 2, 3))
    return EvaluationState(
        linear_deflection=0.1,
        bodies={body_id: body, other_id: other},
        last_cut_tools=[cutter],
        feature_tools={
            tool_feature: RecordedFeatureTools(
                body_id=body_id,
                groups=[
                    RecordedToolGroup("cut", [cutter]),
                    RecordedToolGroup("fuse", [Solid.make_box(1, 1, 1)]),
                ],
            )
        },
        sheet_metal_unfold_body=Solid.make_box(3, 3, 3),
        active_body_id=body_id,
        tool_scope_ids=frozenset({tool_feature}),
    )


def test_every_shape_the_state_holds_is_forked_and_detached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DRY enumerator, checked by BEHAVIOUR against a generic walk.

    ``EvaluationState.shape_slots`` is the one list both the fork and the
    checkpoint's detach use. Whatever shape a generic walk of the state finds
    must be detached, and must come back from a fork as a DIFFERENT ``TShape``
    in a container the fork owns — a slot the enumerator forgot would be shared
    between a ladder rung and the evaluation that carries on past it.
    """
    state = _populated_state()
    expected = _walk_shapes(state)
    assert len(expected) == 6, "the fixture must put a shape in every slot"

    detached: list[int] = []

    def record(shape: object) -> None:
        detached.append(id(shape))

    monkeypatch.setattr(evaluate_module, "drop_triangulation", record)
    evaluate_module._Checkpoint(
        state=state,
        results=[],
        last_good_feature_id=None,
        suppressed_ids=frozenset(),
        artifacts=None,
    ).detach()
    assert {id(shape) for shape in expected} <= set(detached), (
        "a shape the state holds is not detached"
    )

    twin, _nbytes = state.fork()
    forked = _walk_shapes(twin)
    assert len(forked) == len(expected)
    for shape in forked:
        assert not any(_same(shape, original) for original in expected), (
            "a fork shares a shape with its original"
        )
    for item in dataclasses.fields(EvaluationState):
        mine, theirs = getattr(state, item.name), getattr(twin, item.name)
        if isinstance(mine, (dict, list)) and mine:
            assert theirs is not mine, f"{item.name}: the fork shares a container"


def test_a_rung_climb_forks_twice_and_continues_on_neither_original_nor_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural, so it does not depend on whether a copy moves a mesh by an ULP.

    ``_climb_rung`` must (1) store a fork, and (2) continue on a fork OF THAT
    fork. Either single-fork variant — carrying on with the original shapes, or
    carrying on with the stored rung itself — leaves the continuing state
    ``IsSame`` to something it must not share, and this catches both.
    """
    state = _populated_state()
    originals = _walk_shapes(state)
    stored: list[Any] = []

    def capture(chain: object, length: int, checkpoint: object, **_: object) -> bool:
        stored.append(checkpoint)
        return True

    monkeypatch.setattr(evaluate_module._REBUILD_CACHE, "store_rung", capture)
    keys = [f"k{i}" for i in range(RUNG_SPACING + 1)]
    evaluate_module._climb_rung(
        RUNG_SPACING,
        state,
        [],
        set(),
        None,
        evaluate_module._Ladder(keys, speculative=False),
    )

    assert len(stored) == 1
    rung = _walk_shapes(stored[0].state)
    live = _walk_shapes(state)
    assert len(rung) == len(live) == len(originals)
    for shape in live:
        assert not any(_same(shape, other) for other in originals), (
            "the evaluation continued on the un-forked original"
        )
        assert not any(_same(shape, other) for other in rung), (
            "the evaluation continued on the stored rung itself"
        )
    for shape in rung:
        assert not any(_same(shape, other) for other in originals)


# --- The ladder's memory bound on a FREEFORM part (GQA-LADDER-1) ---------------


def _spline_loop(
    cx: float, cy: float, radius: float, wobble: float, phase: float
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for i in range(18):
        a = 2 * math.pi * i / 18
        r = radius * (
            1 + wobble * math.sin(3 * a + phase) + 0.5 * wobble * math.cos(5 * a)
        )
        points.append(
            {"x": round(cx + r * math.cos(a), 4), "y": round(cy + r * math.sin(a), 4)}
        )
    points.append(dict(points[0]))
    return points


def _lobed_plate_tree(motifs: int, plate_mm: float) -> dict[str, Any]:
    """A plate under a field of lofted spline lobes that overlap the plate AND
    each other — geometry QA's freeform fixture (docs/GEOMETRY-QA.md 2026-09-23,
    GQA-LADDER-1), where a face weighs ~50 KiB against the tray's 3.2 KiB:
    merged BSpline faces trimmed by approximated BSpline-BSpline intersection
    edges. *plate_mm* is feature 1, so changing it lays a whole new chain."""
    features: list[dict[str, Any]] = []

    def add(feature: dict[str, Any]) -> str:
        feature_id = str(uuid.UUID(int=0xF0F0_0000 + len(features) + 1))
        features.append({"id": feature_id, "feature": feature})
        return feature_id

    def sketch(plane: dict[str, Any], entities: list[dict[str, Any]]) -> str:
        return add(
            {
                "type": "sketch",
                "version": 1,
                "params": {"plane": plane, "entities": entities, "constraints": []},
            }
        )

    cols, pitch = 8, 16.0
    rows = max(1, (motifs + cols - 1) // cols)
    corners = [
        {"x": -14.0, "y": -14.0},
        {"x": cols * pitch, "y": -14.0},
        {"x": cols * pitch, "y": rows * pitch},
        {"x": -14.0, "y": rows * pitch},
    ]
    plate = sketch(
        {"kind": "datum_plane", "plane": "XY"},
        [
            {
                "id": f"p{i}",
                "kind": "line",
                "start": corners[i],
                "end": corners[(i + 1) % 4],
            }
            for i in range(4)
        ],
    )
    add(
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": plate},
                "distance_mm": plate_mm,
                "operation": "add",
                "direction": "normal",
            },
        }
    )
    low, high = (
        add(
            {
                "type": "datum",
                "version": 1,
                "params": {"kind": "offset", "base": "XY", "offset_mm": offset},
            }
        )
        for offset in (2.0, 14.0)
    )
    for m in range(motifs):
        cx, cy = (m % cols) * pitch, (m // cols) * pitch
        bottom = sketch(
            {"kind": "feature", "feature_id": low},
            [
                {
                    "id": "s",
                    "kind": "spline",
                    "points": _spline_loop(cx, cy, 10.0, 0.12, m * 0.7),
                }
            ],
        )
        top = sketch(
            {"kind": "feature", "feature_id": high},
            [
                {
                    "id": "s",
                    "kind": "spline",
                    "points": _spline_loop(cx + 1.5, cy - 1.0, 6.5, 0.2, m * 1.3),
                }
            ],
        )
        add(
            {
                "type": "loft",
                "version": 1,
                "params": {
                    "profiles": [
                        {"kind": "feature", "feature_id": bottom},
                        {"kind": "feature", "feature_id": top},
                    ],
                    "operation": "add",
                },
            }
        )
    return {
        "part_id": str(uuid.UUID(int=0xF0F0)),
        "tree_version": 1,
        "features": features,
    }


class _MallInfo2(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_size_t)
        for name in (
            "arena",
            "ordblks",
            "smblks",
            "hblks",
            "hblkhd",
            "usmblks",
            "fsmblks",
            "uordblks",
            "fordblks",
            "keepcost",
        )
    ]


def _heap_in_use() -> int:
    """glibc's bytes in use (``mallinfo2``: small chunks + mmapped chunks) —
    where OCCT's allocations land. The same reading geometry QA and the ladder's
    calibration used, so the gate measures what the bound claims to bound."""
    libc = ctypes.CDLL("libc.so.6")
    libc.mallinfo2.restype = _MallInfo2
    gc.collect()
    info = libc.mallinfo2()
    return int(info.uordblks + info.hblkhd)


#: Small enough that four chains of the 8-lobe part overflow it several times.
_FREEFORM_BUDGET = 3 * 1024 * 1024


def test_a_freeform_ladder_holds_no_more_heap_than_its_byte_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GQA-LADDER-1: the ladder's memory bound, measured in HEAP, not estimated.

    The first ladder priced every face at the tray's 3.2 KiB, and on this part a
    face weighs ~50 KiB, so a budget that read "64 MiB" held 115 MiB at its count
    cap and projected to ~1 GiB. Here a ladder with a 3 MiB budget is filled by
    four chains of the lofted-lobe part (feature 1 changed each time, so every
    evaluation lays a new chain), the cap is shown to BIND, and then the ladder
    alone is dropped and the heap that frees is compared with the budget. With
    the rung weighed at 3.2 KiB/face instead, the same fill holds several times
    the budget and this fails.
    """
    cache: PrefixCache[Any] = PrefixCache(
        REBUILD_CACHE_CAPACITY,
        rung_byte_budget=_FREEFORM_BUDGET,
        rung_max_bytes=_FREEFORM_BUDGET,
    )
    monkeypatch.setattr(evaluate_module, "_REBUILD_CACHE", cache)
    for chain in range(4):
        payload = _lobed_plate_tree(8, 4.0 - 0.25 * chain)
        result = evaluate_tree(_request(payload)).result
        assert all(feature.status == "ok" for feature in result.features)
    stats = cache.stats
    before = _heap_in_use()
    cache._rungs.clear()  # the ladder alone; the frontier entries stay
    freed = before - _heap_in_use()
    assert freed <= _FREEFORM_BUDGET, (
        f"the ladder held {freed / 2**20:.1f} MiB of heap against a "
        f"{_FREEFORM_BUDGET / 2**20:.0f} MiB budget ({stats.rungs} rungs)"
    )
    # Only then, the guards that keep the comparison above from being vacuous:
    # the probe saw the ladder, the fill pressed the bound, a ladder remained.
    assert freed > 0, "dropping the ladder freed nothing: the probe is blind"
    assert stats.rung_evictions > 0, "the budget must have BOUND"
    assert stats.rungs >= 2, "and still hold a ladder"
    assert stats.rung_bytes <= _FREEFORM_BUDGET


# --- The FRONTIER cache's memory bound (GQA-LADDER-1's twin) -------------------


def test_the_frontier_is_bounded_by_bytes_as_well_as_count() -> None:
    """A count prices every checkpoint the same; the byte budget does not. LRU
    eviction on either bound, and a checkpoint heavier than the whole budget is
    refused rather than allowed to break it."""
    cache: PrefixCache[_FakePayload] = PrefixCache(8, byte_budget=100)
    for name in "abc":
        assert cache.store(f"key-{name}", _FakePayload(name, nbytes=40))
    assert cache.stats.entry_bytes == 80 and cache.stats.evictions == 1
    assert cache.take(["root", "key-a"]) is None, "the LRU entry went first"
    assert cache.take(["root", "key-c"]) is not None
    assert cache.stats.entry_bytes == 40, "a take hands its bytes back"

    assert not cache.store("huge", _FakePayload("huge", nbytes=101))
    assert cache.stats.oversize_refused == 1
    assert cache.take(["root", "key-b"]) is not None, "and evicted nothing"


def test_speculation_yields_bytes_as_well_as_slots() -> None:
    """CONC-4 on the byte bound: a warm's checkpoint is the first victim when a
    live one needs the bytes, and is refused when only live work could make
    room for it."""
    cache: PrefixCache[_FakePayload] = PrefixCache(8, byte_budget=100)
    cache.store("live", _FakePayload("live", nbytes=40))
    assert cache.store("guess", _FakePayload("guess", nbytes=40), speculative=True)
    cache.store("newer", _FakePayload("newer", nbytes=40))
    assert cache.take(["root", "guess"]) is None, "speculation is evicted first"
    assert cache.take(["root", "live"]) is not None, "older live work survives"

    cache.store("big-live", _FakePayload("big-live", nbytes=50))
    assert not cache.store(
        "late-guess", _FakePayload("late-guess", nbytes=60), speculative=True
    ), "only live work could make room, so the guess yields"
    assert cache.stats.entry_bytes == 90


def test_a_repeat_does_not_pay_to_reweigh_its_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Weighing is a serialisation of the whole state, so it must not be paid on
    the cheap path: the ``/measure``, ``/tessellate``, ``/export`` calls that
    REPEAT a tree re-store the same state and artifacts, and carry its weight."""
    calls: list[int] = []
    real = evaluate_module.weigh_shapes  # pyright: ignore[reportPrivateImportUsage]

    def counting(shapes: Any) -> int:
        calls.append(1)
        return real(shapes)

    monkeypatch.setattr(evaluate_module, "weigh_shapes", counting)
    request = _request(_payload())
    reset_rebuild_cache()
    _answer(request)
    assert len(calls) == 1, "the first release weighs the checkpoint once"
    for _ in range(3):
        _answer(request)
    assert len(calls) == 1, "a repeat re-weighed an unchanged checkpoint"
    assert rebuild_cache_stats().entry_bytes > 0


#: Small enough that five frontier checkpoints of the 8-lobe part overflow it.
_FRONTIER_BUDGET = 4 * 1024 * 1024


def test_a_freeform_frontier_holds_no_more_heap_than_its_byte_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontier cache's memory bound, measured in HEAP, not estimated.

    Before it had a byte budget the frontier was bounded by COUNT (32 entries),
    documented as "~128 MiB ... of big parts" — true for the tray, and ~176 MiB
    on the lofted-lobe part, whose checkpoints weigh ~5.5 MiB each. Here five
    evaluations of the 8-lobe part (feature 1 changed each time, so each stores
    a new frontier checkpoint) fill a frontier with a 4 MiB byte budget; then the
    frontier alone is dropped and the heap that frees is compared with the
    budget. The ladder is off and the mesh store keeps one GLB, so what is freed
    is the frontier's own. With the count-only bound put back, this fails.
    """
    cache: PrefixCache[Any] = PrefixCache(
        REBUILD_CACHE_CAPACITY, byte_budget=_FRONTIER_BUDGET, rung_capacity=0
    )
    monkeypatch.setattr(evaluate_module, "_REBUILD_CACHE", cache)
    monkeypatch.setattr(mesh_store, "_active_store", mesh_store.MeshStore(1))
    for chain in range(5):
        payload = _lobed_plate_tree(8, 4.0 - 0.25 * chain)
        result = evaluate_tree(_request(payload)).result
        assert all(feature.status == "ok" for feature in result.features)

    stats = cache.stats
    before = _heap_in_use()
    cache._entries.clear()  # the frontier alone
    freed = before - _heap_in_use()
    assert freed <= _FRONTIER_BUDGET, (
        f"the frontier held {freed / 2**20:.1f} MiB of heap against a "
        f"{_FRONTIER_BUDGET / 2**20:.0f} MiB budget ({stats.stores} stores, "
        f"{stats.evictions} evictions)"
    )
    # Only then, the guards that keep the comparison above from being vacuous.
    assert freed > 0, "dropping the frontier freed nothing: the probe is blind"
    assert stats.evictions > 0, "the byte budget must have BOUND"
    assert stats.stores == 5 and stats.entry_bytes <= _FRONTIER_BUDGET
