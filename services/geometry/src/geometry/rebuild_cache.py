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

WHAT A FUTURE PREFETCH MAY DO, AND WHAT IT MUST NOT (written down now, on
purpose). Speculative rebuilding is meaningless without this cache — it would do
the 27 s twice with nowhere to put the result — and nearly free with it, so it
is worth stating the rules before someone needs them:

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
  why speculation should stay well inside :data:`REBUILD_CACHE_CAPACITY` and
  never be issued in bulk.

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
import uuid
import weakref
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from OCP.BRepTools import BRepTools
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
    """Observability counters (tests assert on these; nothing else reads them)."""

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
        """
        with self._lock:
            for length in range(len(keys) - 1, 0, -1):
                entry = self._entries.pop(keys[length], None)
                if entry is not None:
                    self._hits += 1
                    self._resumed_features += length
                    return length, entry
            self._misses += 1
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
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
                self._evictions += 1

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
