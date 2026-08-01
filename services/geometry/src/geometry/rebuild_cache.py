"""Content-addressed cache of an evaluated feature-tree PREFIX (docs/PERF.md #1).

`evaluate_tree` used to re-run the entire tree from feature 0 on every call, and
the tree's cost is **N^1.85** in feature count — so on the 200-feature tray
docs/PERF.md measures, editing feature #199 cost the same 27 s as editing #1,
one face pick cost 29 s, and `/measure`, `/tessellate`, `/export` and drawings
compose each paid their own full rebuild. That turns an O(N^2) rebuild into an
O(N^2) *per interaction*, which is the single biggest multiplier in the product.

This module is the mechanism that stops it: a bounded, thread-safe, in-process
LRU keyed on the **rolling content hash of the feature prefix**, holding the
evaluator's own state as of that prefix. A request whose first *k* features hash
identically resumes at *k* and pays only for features *k+1..N*.

**Cache, not state (RESEARCH §3.)** Like :mod:`geometry.mesh_store` and
:mod:`geometry.step_cache`, this is a per-worker performance optimisation and
never a correctness dependency: a miss (cold worker, eviction, a borrowed entry,
a changed prefix) simply re-evaluates the tree, and geometry stays stateless —
nothing here is durable, tenant-scoped, or consulted for an answer the evaluator
could not recompute.

WHY OWNERSHIP TRANSFER, AND NOT A COPY — the measurement that shaped this
design (2026-07-31). The obvious implementation stores a *copy* of the state and
hands out copies on a hit. It is wrong here, and only measurement says so:

* **Every re-materialisation of an OCCT shape perturbs its tessellation.** A
  `BRepBuilderAPI_Copy` of the tray's body (build123d's `deepcopy`) preserves
  the geometry exactly — identical vertices, identical face locations, volume
  bit-identical, STEP byte-identical — and yet re-meshes to a GLB that differs:
  one accessor bound moves by 1 ULP (`0.02` vs `0.020000000000000004`), 16 bytes
  of 155 800. It is not the copy flags (`copyGeom` and `copyMesh` were tried in
  all four combinations, all four differ, and the four agree with each other),
  and it is not allocation nondeterminism (two fresh rebuilds separated by heavy
  OCCT churn stay byte-identical). A BREP round-trip — the idiom
  :mod:`geometry.step_cache` uses — is no better: volume comes back bit-exact
  and the GLB still moves, by 68 bytes. Resuming from a copy would therefore
  make `mesh_glb_id` depend on CACHE STATE, i.e. it would trade a documented
  determinism guarantee (evaluate.py: "byte-identical GLB and therefore
  identical ``mesh_glb_id``") for speed. Correctness beats the speedup.
* So a hit hands the *original* shapes to the resuming evaluation and the cache
  keeps nothing: :meth:`PrefixCache.take` REMOVES the entry. Byte-exactness is
  then structural — the resumed evaluation runs the identical OCCT calls on the
  identical objects a cold rebuild would have built — and it is asserted, at
  several prefix lengths, in ``tests/test_rebuild_cache.py``.
* The price is honest and worth stating: the cache holds **one live checkpoint
  per lineage** (the frontier), so it serves APPEND ("the tree I just evaluated,
  plus one") and REPEAT ("the same tree again, from `/measure`, `/tessellate`,
  `/export`, drawings"), and it does NOT serve an edit in the middle of a long
  tree — that would need a ladder of intermediate checkpoints, which cannot be
  built without copies. See docs/PERF.md for the follow-up.

WHY A `weakref` HAND-BACK. Ownership transfer only works if the cache's copy of
a state is referenced by nobody else — otherwise a resuming evaluation would
mutate shapes another request is still exporting (OCCT booleans rewrite their
arguments' subshapes in place; CM-6b), and the geometry handlers run in
FastAPI's THREADPOOL, so that is real concurrency and not a thought experiment.
So a checkpoint is not stored when the evaluation ends — it is stored when the
`TreeEvaluation` that owns those shapes is **released** (:meth:`store_on_release`
registers a `weakref.finalize`). Under CPython refcounting that is the moment
the request handler returns, so the append case still hits; if a caller holds
its evaluation forever, the entry is simply never cached. Correct degradation in
both directions, no lease protocol, and nothing for a caller to remember.

WHAT A PREFETCH MAY DO, AND WHAT IT MUST NOT (written before it existed, and
still the contract now that :class:`WarmScheduler` below implements it).
Speculative rebuilding is meaningless without this cache — it would do the 27 s
twice with nowhere to put the result — and nearly free with it:

* A prefetch **warms**, it never **answers**. The only entry point that
  populates the cache without producing an artifact is
  :func:`geometry.features.evaluate.warm_rebuild_cache`, which returns an
  integer and cannot return a body, a mesh id or mass properties. A speculative
  rebuild that could be published would eventually be published for a tree it
  does not exactly correspond to — the silent-wrong-geometry class this repo has
  closed four times. Keep the two paths separate.
* A warm result is servable **only through the ordinary key**, so it can only
  ever be used by a request whose prefix hashes identically. There is no "close
  enough" resume and there must never be one.
* A warm must be **bounded and cancellable**: four cores, several users, and an
  uncancellable speculation is a self-inflicted DoS. ``warm_rebuild_cache``
  takes a ``budget_s`` deadline and a ``cancelled`` predicate, both checked
  BETWEEN features — the honest granularity, since a single feature is one
  uninterruptible OCCT call (up to ~200 ms on a 442-face body). A cancelled warm
  keeps what it evaluated: the checkpoint it stores is simply a shorter prefix,
  which is a legitimate resume point.
* A warm must never evict a checkpoint a live request is about to use, which is
  why speculation stays well inside :data:`REBUILD_CACHE_CAPACITY` and is never
  issued in bulk — :class:`WarmScheduler` runs at most ONE warm per worker and
  each warm stores at most one entry per lineage.

WHY `detach()` BEFORE STORING. A checkpoint's shapes may have been TESSELLATED
by the request that produced them (tessellate/STL/export all write a
`Poly_Triangulation` into the face's TShape), and a body that carries a
triangulation meshes DIFFERENTLY after a further boolean than one that does not:
measured on the tray, appending one feature to an already-tessellated body moved
the final GLB, and `BRepTools::Clean` on the stored bodies made it byte-exact
again at every prefix length tried. That is what :meth:`Detachable.detach` is
for, and it is why the cache — not the caller — performs it: it must happen
after the producing request is done and before any resume.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false

import hashlib
import json
import threading
import time
import uuid
import weakref
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from OCP.BRepTools import BRepTools
from py_kit.metrics import (
    note_rebuild,
    record_rebuild_cache_eviction,
    record_rebuild_cache_hit,
    record_rebuild_cache_miss,
    record_rebuild_cache_store,
)
from py_kit.schemas.features import EvaluateTreeRequest

from geometry.kernel.types import BodyShape

#: Bumped whenever the MEANING of a key changes (what goes into the header, how
#: a feature is serialised, or what a checkpoint stores). The cache is
#: in-process, so a version skew cannot outlive a worker — this exists so a
#: future change is a deliberate, greppable bust rather than a silent stale hit.
CACHE_KEY_VERSION = 1

#: Max live checkpoints (LRU). Small on purpose: with ownership transfer each
#: entry is ONE lineage's frontier, so the useful working set is "parts being
#: edited in this worker right now", and each entry retains a whole evaluator
#: state — bodies, sketch profiles and any captured mirror tools. MEASURED on
#: the docs/PERF.md tray at N=100 (219 faces), eight distinct lineages held at
#: once: **+2 MiB of RSS per retained checkpoint** past the first, ~4 MiB
#: extrapolated at the N=200 body's 442 faces — so a full cache is tens of MiB
#: against OCCT's ~500 MiB baseline. (Releasing them does not return RSS to the
#: OS — glibc keeps the arena — which is why the figure is measured as a
#: marginal cost, not a delta after a clear.) An assembly evaluates one tree per
#: unique part, so 8 also covers a small assembly without thrashing.
REBUILD_CACHE_CAPACITY = 8


def drop_triangulation(shape: BodyShape) -> None:
    """Discard any mesh stored on *shape* (``BRepTools::Clean``).

    The one OCCT call this module makes, and it is load-bearing rather than
    hygienic: see the module docstring — a body still carrying the
    ``Poly_Triangulation`` its previous consumer's tessellate/STL/STEP call left
    on it meshes DIFFERENTLY once another boolean has been applied, so a
    checkpoint that skipped this would resume to a GLB that a cold rebuild does
    not produce. It lives here because this cache is what requires it; a shape
    with no mesh is exactly what a freshly-built one looks like.
    """
    if shape.wrapped is not None:
        BRepTools.Clean_s(shape.wrapped)


class Detachable(Protocol):
    """What the cache requires of a checkpoint payload it takes ownership of."""

    def detach(self) -> None:
        """Drop state derived from a PREVIOUS consumer of these shapes.

        Called exactly once, by the cache, at the moment it takes exclusive
        ownership — never by the caller. See the module docstring: a retained
        triangulation changes how a later boolean's result meshes, so a
        checkpoint that is not detached would resume to a subtly different GLB.
        """


@dataclass(frozen=True)
class CacheStats:
    """In-process counters, read by the tests. The operator-facing versions of
    the same events are Prometheus counters moved at the SAME lines that move
    these (:mod:`py_kit.metrics`), so the two cannot drift apart: there is one
    increment site per event, not two."""

    hits: int
    misses: int
    stores: int
    evictions: int
    resumed_features: int


def prefix_keys(
    request: EvaluateTreeRequest,
    *,
    capture_scope: Iterable[uuid.UUID],
    record_history: bool,
) -> list[str]:
    """Rolling content address of every prefix of *request*'s feature list.

    Returns ``N + 1`` keys: ``keys[k]`` addresses the first *k* features, so
    ``keys[0]`` is the empty prefix and ``keys[N]`` the whole request. Rolling by
    construction — ``h(k+1) = sha256(h(k) || feature_k)`` — so a prefix that is
    unchanged keeps its address no matter what follows it, which is the property
    that makes an APPEND a hit.

    WHAT IS IN THE KEY, and why each thing is there:

    * **every feature of the prefix, verbatim** (id, type, params, ``suppressed``
      — the whole validated DTO's JSON, in pydantic field order, which is
      deterministic), and their ORDER, since the key is a chain;
    * **``linear_deflection``**, because it is threaded onto
      :class:`~geometry.features.evaluate.EvaluationState` and read by handlers,
      not only by the final tessellation;
    * **the mirror capture scope** — the one input to prefix evaluation that
      does NOT come from the prefix. A ``features``-scope mirror anywhere in the
      tree makes the features it names retain their reflectable tools
      (mirror-semantics §9), so the state after k features genuinely depends on
      the suffix. Measured the hard way while building this: resuming a prefix
      evaluated without the right capture set turned a later mirror into
      ``reference_unresolved``. Adding a scoped mirror is therefore a miss, which
      is correct.
    * **``record_history``**, because a history-recording evaluation retains an
      intermediate body per body-affecting feature and a plain one retains none —
      so a prefix evaluated without history cannot serve per-face provenance
      (the missing snapshots would silently mis-attribute every face the prefix
      built). Two keys means two independent lineages that BOTH stay cached, so
      an edit → pick → edit → pick session hits on the picks instead of
      ping-ponging one entry between the two callers.
    * **:data:`CACHE_KEY_VERSION`**, the deliberate-bust seam.

    WHAT IS DELIBERATELY *NOT* IN THE KEY, with the rule that makes it safe: a
    checkpoint stores only the EVALUATOR STATE, and every artifact is re-derived
    on every call, so anything consulted solely AFTER the dispatch loop cannot
    change what a hit means. That is exactly ``part_id`` and ``tree_version``
    (copied onto the result, and re-copied from the live request on a hit) and
    ``materials`` (densities, read only by the post-loop measurement — and the
    memoised artifacts are additionally guarded on the resolved per-body material,
    see ``evaluate.py``). Keying on ``tree_version`` in particular would be worse
    than useless: it changes on every edit, so it would defeat the cache entirely
    while protecting nothing.
    """
    header = json.dumps(
        {
            "version": CACHE_KEY_VERSION,
            "linear_deflection": request.linear_deflection,
            "capture_scope": sorted(str(feature_id) for feature_id in capture_scope),
            "record_history": record_history,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(header.encode("utf-8")).digest()
    keys = [f"sha256:{digest.hex()}"]
    for item in request.features:
        digest = hashlib.sha256(
            digest + b"\x00" + item.model_dump_json().encode("utf-8")
        ).digest()
        keys.append(f"sha256:{digest.hex()}")
    return keys


class PrefixCache[CheckpointT: Detachable]:
    """Thread-safe bounded LRU of prefix-keyed checkpoints, with OWNERSHIP.

    Generic over its payload so this module stays free of kernel and evaluator
    imports (the checkpoint type lives with the evaluator that produces it).
    Three operations, and the ownership rule is the whole design:

    * :meth:`take` — pop the LONGEST cached prefix of a request's key chain. The
      entry is REMOVED: the caller now owns those shapes exclusively.
    * :meth:`store_on_release` — offer a checkpoint that will enter the cache
      only once *owner* is unreachable, i.e. once nothing else can touch it.
    * :meth:`clear` — test isolation seam (a test asserting a MISS must not be
      served a hit warmed by an earlier test in the same process).
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, CheckpointT] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._evictions = 0
        self._resumed_features = 0

    def take(self, keys: Sequence[str]) -> tuple[int, CheckpointT] | None:
        """The longest cached prefix of *keys*, removed, or ``None``.

        Searches longest-first, so a repeat of the same tree resumes at the full
        length (zero further features) and an append resumes one short of it.
        ``keys[0]`` (the empty prefix) is never a useful checkpoint and is not
        probed. Returns ``(prefix_length, checkpoint)``; the caller owns the
        checkpoint and MUST NOT assume the cache still holds it.

        THIS IS ALSO THE REBUILD OBSERVABILITY SEAM (:mod:`py_kit.metrics`).
        ``evaluate_tree`` consults the cache unconditionally — it is the second
        statement of the function, before any kernel work — so every rebuild in
        the product passes through here exactly once, whatever route asked for
        it. Instrumenting the nine ``evaluate_tree`` call sites instead would
        leave the tenth uncounted and the graph silently wrong. Nothing about the
        cache's behaviour depends on the recording.
        """
        with self._lock:
            for length in range(len(keys) - 1, 0, -1):
                entry = self._entries.pop(keys[length], None)
                if entry is not None:
                    self._hits += 1
                    self._resumed_features += length
                    record_rebuild_cache_hit()
                    note_rebuild(features=len(keys) - 1, resumed=length)
                    return length, entry
            self._misses += 1
            record_rebuild_cache_miss()
            note_rebuild(features=len(keys) - 1, resumed=0)
            return None

    def store_on_release(
        self, owner: object, key: str, checkpoint: CheckpointT
    ) -> None:
        """Cache *checkpoint* under *key* once *owner* becomes unreachable.

        *owner* is the ``TreeEvaluation`` handed back to the caller, and it has
        to be — **the claim cannot be pinned to the shapes themselves.** That was
        tried: a strong reference from each handed-out shape to a lifetime token
        would be the airtight version, except the checkpoint HOLDS those shapes,
        so the token is reachable from the finalizer's own arguments and the
        finalizer can never fire (measured: zero stores, a permanently cold
        cache). Any liveness signal must live on an object the checkpoint does
        not reference, and the evaluation is the only one.

        The consequence is a real contract, so it is written down in
        :class:`~geometry.features.evaluate.TreeEvaluation`: **a caller that
        keeps a kernel shape must keep its evaluation.** One caller genuinely
        did not (``assembly/evaluate.py`` stashed ``evaluation.body`` in a
        per-request dict and dropped the evaluation), and it was fixed rather
        than documented around.

        The finalizer does not run at interpreter exit: storing into a per-worker
        cache during shutdown would be pure work with no reader.
        """
        finalizer = weakref.finalize(owner, self.store, key, checkpoint)
        # Storing into a per-worker cache during interpreter shutdown is pure
        # work with no reader — and it would run after the modules the payload
        # needs have started tearing down.
        finalizer.atexit = False

    def store(self, key: str, checkpoint: CheckpointT) -> None:
        """Take ownership of *checkpoint* and cache it under *key*.

        The caller MUST own the checkpoint exclusively — nothing else may hold
        its shapes — which is why the ordinary path is
        :meth:`store_on_release` and the direct call is reserved for a warm,
        whose state was never published. :meth:`Detachable.detach` runs here, on
        the cache's side of the transfer.
        """
        checkpoint.detach()
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = checkpoint
            self._stores += 1
            record_rebuild_cache_store()
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
                self._evictions += 1
                record_rebuild_cache_eviction()

    def clear(self) -> None:
        """Drop every entry (test isolation; production never calls this)."""
        with self._lock:
            self._entries.clear()

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                stores=self._stores,
                evictions=self._evictions,
                resumed_features=self._resumed_features,
            )


#: Wall-clock ceiling for ONE warm ticket, across every lineage it warms
#: (docs/PERF.md PERF-1b). **30 s, and the number was measured rather than
#: chosen.** What it is NOT is the DoS bound: speculation is capped at one core
#: by the single :class:`WarmScheduler` thread, whatever this says, and a client
#: that resubmits can hold that one core at any budget. So this answers a
#: narrower question — how much work is ONE declaration of intent worth?
#:
#: 1. **It is the cost of the thing it is speculating on.** Warming the prefix an
#:    open editor settles on the docs/PERF.md tray measures **7.7 CPU s at
#:    N=100** and **28.9 CPU s for feature 192 of 200** — so a 10 s budget (the
#:    first value here) delivered the full win on a 100-feature part and
#:    truncated the 200-feature one to a fraction, which is exactly the part the
#:    fix exists for. 30 s covers a full-prefix warm at the top of the range the
#:    tool is usable in, and still bounds the pathological tree
#:    (``MAX_TREE_FEATURES`` is 1000, whose prefix would be minutes).
#: 2. **The pessimal case is bounded by the USER, not by this.** A warm that
#:    finishes stops; a warm whose reason goes away is cancelled within one
#:    feature (~200 ms) of the editor closing or the stop moving. So "opened a
#:    dialog and did nothing" costs the seconds they sat in it, not 30 — and if
#:    they DO commit, none of it was waste: it is the same work the commit would
#:    have done, moved earlier.
#: 3. It is 1.5x ``DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S``, which this service
#:    already accepts for one unattended, NON-preemptible parse. This one yields.
#:
#: The budget is shared across a ticket's lineages in priority order, so a warm
#: that runs out has always finished the more valuable half (see
#: :mod:`geometry.warm`).
DEFAULT_WARM_BUDGET_S = 30.0


@dataclass(frozen=True)
class WarmStats:
    """Scheduler counters (tests + diagnostics), all per-worker and in-process.

    ``superseded`` and ``cancelled`` are the interesting ones: they count the
    speculation this worker was told to abandon, i.e. exactly the CPU the bounded
    design gives back. ``completed`` counts runs that RETURNED, which includes a
    run that returned early because it was superseded — the two are orthogonal,
    and calling an abandoned run "not completed" would need the work to report
    back, which is precisely the coupling this scheduler does not have.
    """

    submitted: int
    started: int
    completed: int
    superseded: int
    cancelled: int
    failed: int


class WarmScheduler:
    """At most ONE speculative rebuild in flight per worker, always cancellable.

    The prefetch triggers (an open feature editor, a dragged travel stop) are
    genuine declarations of intent, but they are *guesses*, and a guess must not
    be able to hurt the requests that are not guesses. Two properties do that,
    and they are separate on purpose:

    * **A hard concurrency bound.** One daemon thread, one slot. Speculation can
      therefore consume at most one core of the box no matter how many prefetch
      calls arrive — a hundred users mashing feature editors produce one warm
      thread, not a hundred. Doing this in FastAPI's threadpool instead (a
      request that simply is not awaited) would have made the DoS exactly as bad
      as the number of concurrent clients, which is the wrong direction.
    * **Supersede + explicit cancel.** A newer submission REPLACES an older one
      (the newest intent is the only one worth spending on), and
      :meth:`cancel` retires a ticket outright — what the UI calls when the
      editor closes or the drag ends. Both are observed BETWEEN features by the
      ``should_stop`` predicate handed to the work, so a warm stops within one
      OCCT call of being asked to. There is no way to interrupt a single
      ``BRepAlgoAPI`` call and this module does not pretend otherwise.

    A *ticket* is an opaque caller-chosen string identifying the intent (the
    gateway namespaces it per user). Submitting the SAME ticket that is already
    running is deliberately a no-op: a React re-render that re-declares the same
    open editor must not restart the warm it is waiting for.

    Nothing here knows what a warm *is* — the work is a callable taking the stop
    predicate — so this module stays free of evaluator and kernel imports.
    """

    def __init__(self, budget_s: float = DEFAULT_WARM_BUDGET_S) -> None:
        if budget_s <= 0:
            raise ValueError(f"budget_s must be > 0, got {budget_s}")
        self._budget_s = budget_s
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._idle = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        #: Bumped by every submit and every matching cancel. A running warm
        #: compares the generation it started with; anything else means "you have
        #: been superseded or cancelled, stop at the next feature".
        self._generation = 0
        self._pending: tuple[str, Callable[[Callable[[], bool]], None]] | None = None
        self._running: str | None = None
        self._submitted = 0
        self._started = 0
        self._completed = 0
        self._superseded = 0
        self._cancelled = 0
        self._failed = 0

    def submit(self, ticket: str, work: Callable[[Callable[[], bool]], None]) -> bool:
        """Queue *work* under *ticket*, retiring whatever the worker was doing.

        Returns ``False`` when *ticket* is already the running or pending one —
        the idempotent re-declaration case — and ``True`` when it was accepted.
        """
        with self._lock:
            if ticket == self._running or (
                self._pending is not None and self._pending[0] == ticket
            ):
                return False
            if self._pending is not None:
                self._superseded += 1
            if self._running is not None:
                self._superseded += 1
            self._pending = (ticket, work)
            self._submitted += 1
            # Retire the incumbent: it observes the new generation on its next
            # feature boundary and stops, keeping the shorter prefix it built.
            self._generation += 1
            self._ensure_thread()
            self._wake.notify_all()
        return True

    def cancel(self, ticket: str) -> bool:
        """Retire *ticket* if it is running or pending. Returns whether it was.

        The editor closing, the drag ending, the part being navigated away from:
        the intent is gone, so the speculation funded by it must stop rather than
        finish out of politeness.
        """
        with self._lock:
            hit = False
            if self._pending is not None and self._pending[0] == ticket:
                self._pending = None
                hit = True
            if self._running == ticket:
                # Only a RUNNING ticket's cancellation moves the generation:
                # that is the signal one in-flight warm reads, and bumping it for
                # a merely-pending cancel would also retire whatever else is
                # running — which nobody asked for.
                self._generation += 1
                hit = True
            if hit:
                self._cancelled += 1
                self._idle.notify_all()
            return hit

    def wait_idle(self, timeout_s: float) -> bool:
        """Block until nothing is running or pending (TEST SEAM).

        Production never calls this: the whole point of the scheduler is that
        nobody waits on speculation. A test that asserts what a warm left in the
        cache does need to, and polling a private attribute would be worse.
        """
        deadline = time.monotonic() + timeout_s
        with self._lock:
            while self._running is not None or self._pending is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(remaining)
            return True

    @property
    def stats(self) -> WarmStats:
        with self._lock:
            return WarmStats(
                submitted=self._submitted,
                started=self._started,
                completed=self._completed,
                superseded=self._superseded,
                cancelled=self._cancelled,
                failed=self._failed,
            )

    def _ensure_thread(self) -> None:
        """Start the worker on first use (caller holds the lock).

        Daemon, so a warm can never hold up worker shutdown, and started lazily
        so a process that never prefetches never spawns it.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="rebuild-warm", daemon=True
        )
        self._thread.start()

    def _stopper(self, generation: int) -> Callable[[], bool]:
        """The predicate one warm run polls between features: *my budget is
        spent* OR *somebody has superseded/cancelled me*."""
        deadline = time.monotonic() + self._budget_s

        def should_stop() -> bool:
            if time.monotonic() >= deadline:
                return True
            with self._lock:
                return self._generation != generation

        return should_stop

    def _run(self) -> None:
        while True:
            with self._lock:
                while self._pending is None:
                    self._wake.wait()
                ticket, work = self._pending
                self._pending = None
                self._running = ticket
                generation = self._generation
                self._started += 1
            try:
                work(self._stopper(generation))
            except Exception:  # speculation must never kill the worker thread
                # A warm produces no answer, so there is nobody to report to: the
                # request that would have used it simply misses and rebuilds. The
                # counter is the honest record.
                with self._lock:
                    self._failed += 1
            else:
                with self._lock:
                    self._completed += 1
            with self._lock:
                self._running = None
                self._idle.notify_all()
