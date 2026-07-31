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

import copy
import dataclasses
import importlib
import importlib.util
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from geometry.features.evaluate import (
    evaluate_tree,
    rebuild_cache_stats,
    reset_rebuild_cache,
    warm_rebuild_cache,
)
from geometry.rebuild_cache import PrefixCache, prefix_keys
from py_kit.schemas.features import EvaluateTreeRequest

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
    history: int


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
        history=len(evaluation.body_history),
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
    assert cold.history > 0

    reset_rebuild_cache()
    _answer(request)  # a plain evaluate first — the tempting stale prefix
    warm = _answer(request, record_history=True)
    assert warm.history == cold.history
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
    rebuild of the same tree must MISS and build its own body.
    """
    request = _request(_payload())
    cold = _cold(request)
    reset_rebuild_cache()

    held = evaluate_tree(request)  # kept alive for the whole test
    misses = rebuild_cache_stats().misses
    assert _answer(request) == cold, "a concurrent rebuild must still be correct"
    assert rebuild_cache_stats().misses == misses + 1, (
        "the entry was served while its owner was still using it"
    )
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

    def detach(self) -> None:
        self.detached.append(self.name)


def test_the_cache_is_bounded_and_evicts_the_least_recently_used() -> None:
    cache: PrefixCache[_FakePayload] = PrefixCache(2)
    for name in ("a", "b", "c"):
        cache.store(f"key-{name}", _FakePayload(name))
    assert cache.take(["root", "key-a"]) is None, "the oldest entry must be evicted"
    assert cache.take(["root", "key-c"]) is not None
    assert cache.stats.evictions == 1


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
