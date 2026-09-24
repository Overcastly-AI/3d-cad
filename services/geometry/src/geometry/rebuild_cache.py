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
* The price: the frontier is **one live checkpoint per lineage**, so on its
  own it serves APPEND ("the tree I just evaluated, plus one") and REPEAT ("the
  same tree again, from `/measure`, `/tessellate`, `/export`, drawings") and
  nothing else. An EDIT is served by the ladder below.

THE LADDER (PERF-REAL-2, 2026-09-23). The frontier alone made every edit a full
rebuild: the gauntlet measured edit #249 of a 250-feature tray at 36.5 s against
a 36.1 s cold rebuild. The fix is a ladder of intermediate checkpoints, and the
paragraph above is why it cannot simply keep references to the intermediate
states — they are the objects the rest of the evaluation mutates. So a rung
needs a COPY, and a copy does not always re-mesh like its original (the
2026-07-31 measurement above; re-measured by geometry QA on 2026-09-23 on
PRE-ladder bodies: ONE ``BRepBuilderAPI_Copy`` moves the GLB of **13 of 89**
trees — housing N=27/40/60/100, five sheet-metal goldens, a bolt-circle pattern,
two heat sinks — by a ULP in an accessor bound, with STEP bytes and mass
properties identical. An earlier note here said the N=40/100 tray forks were
byte-identical; that was measured on bodies that had ALREADY been forked by the
ladder, i.e. a copy of a copy, and it was wrong about the original.) The way out
is to make the copy part of the evaluation rather than a side effect of caching:

* **Every evaluation forks its state at every multiple of** :data:`RUNG_SPACING`
  (``evaluate._climb_rung``), cached or not. It forks twice: the first fork goes
  on the ladder and is never touched again; the evaluation continues on a fork
  OF THAT FORK. A resume from the rung continues on another fork of the same
  untouched rung, so the cold path and the resumed path run identical OCCT calls
  on identical inputs — the same structural byte-exactness the frontier has,
  re-established one copy later. It is asserted, including ``mesh_glb_id`` and
  face provenance, in ``tests/test_rebuild_cache.py``.
* **A rung is never handed out**: :meth:`PrefixCache.take` hands out
  ``rung.fork()`` and leaves the rung where it is, so dragging one parameter
  back and forth resumes from the same rung every time. At equal length the
  frontier wins (no fork needed).
* **Invalidation is the key and nothing else.** A rung is stored under
  ``keys[r]`` — the rolling hash of exactly the *r* features it has evaluated —
  so an edit at feature index *k* can reach rungs at ``r <= k`` only. The
  off-by-one in either direction is gated by editing the features on BOTH sides
  of every rung and comparing to a cold rebuild.
* **Bounded three ways.** Per chain, :func:`rung_retained` thins older rungs
  geometrically (dense near the frontier, sparse towards feature 0), so a
  250-feature tree keeps 15 rungs, not 31. Across the worker, at most
  :data:`RUNG_CAPACITY` rungs and :data:`RUNG_BYTE_BUDGET` estimated heap bytes,
  LRU-first with speculation evicted before live work, as for the frontier; a
  single rung over :data:`RUNG_MAX_BYTES` is never stored.

What it buys, measured by ``just gauntlet``'s deep leg at N=250, before and
after back to back on the same machine: **edit #249 went from 36 527 ms to
1 763 ms (20.7x)**; ``repeat`` (163 -> 173 ms) and ``append`` (1 868 -> 1 718
ms) did not move beyond noise, and cold rebuild paid the fork tax (36.1 -> 37.1
s, of which ~0.6 s is forking). Further in, same tree, ladder on vs off in a
quiet window (load ~1): edit #230 34.5 -> 7.8 s, #186 34.7 -> 18.7 s, #125
35.7 -> 30.8 s — the saving follows the ~N^2.15 cost curve, as it must.

What it CANNOT buy is an edit near the start of a linear tree: an edit at
feature *k* must re-run every feature after *k* (each one's input is the body
the previous one left), so editing #3 — the shell every later feature is cut
into — still re-runs 247 of 250 features (35.3 -> 36.1 s, i.e. unchanged). That
floor belongs to the evaluator, not the cache; only a dependency-aware
evaluator could go under it.

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
* A warm must never evict a checkpoint a live request is about to use, and — the
  2026-08-01 correction — *saying so was not enough*. The load run measured four
  modelers on one worker with the prefetch on: evictions 24 -> 35 and the hit
  rate 0.40 -> 0.31, because on a full LRU every warm displaced somebody's live
  checkpoint (CONC-4/CONC-6). "Speculation stays well inside the capacity" is not
  a property a bounded LRU has; it is a hope about the working set. So the claim
  is now STRUCTURAL and enforced by :meth:`PrefixCache.store`: a speculative
  entry is marked as such, is always the first victim, and a speculative store
  that would have to evict live work is REFUSED outright (counted, never
  silent). A warm losing its slot to a real request is correct; the reverse is a
  self-inflicted regression.
* A warm must never take the CORE from a live request either, which is the same
  mistake one layer down and cost 1.8x. Measured (CONC-6): committing
  immediately after opening an editor went 2 589 -> 4 742 ms, because OCP holds
  the GIL (CONC-5) so speculation and the real rebuild simply split one core. A
  warm therefore BANKS the prefix it has built and PAUSES between features for as
  long as any real evaluation is in flight in this process
  (:class:`LiveWorkGate`, consulted by
  :func:`geometry.features.evaluate.warm_rebuild_cache`, which is the only code
  that can act on it — it holds the half-built state). The worst case is then
  "the warm achieved nothing", never "the user waited longer".

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
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NamedTuple, Protocol, Self

from loft_wire.features import EvaluateTreeRequest
from OCP.BRepTools import BRepTools
from py_kit.metrics import (
    note_rebuild,
    record_rebuild_cache_eviction,
    record_rebuild_cache_hit,
    record_rebuild_cache_miss,
    record_rebuild_cache_store,
)

from geometry.kernel.types import BodyShape

#: Bumped whenever the MEANING of a key changes (what goes into the header, how
#: a feature is serialised, or what a checkpoint stores). The cache is
#: in-process, so a version skew cannot outlive a worker — this exists so a
#: future change is a deliberate, greppable bust rather than a silent stale hit.
CACHE_KEY_VERSION = 3

#: Max live checkpoints (LRU). **32, derived from concurrency and priced in RAM
#: — not a leftover.** With ownership transfer each entry is ONE lineage's
#: frontier, so the working set is "lineages being worked on in this worker right
#: now", and the arithmetic that sizes it is:
#:
#: * a working modeler holds **one** lineage per part they are working on. It
#:   was sized at two — a plain one for edits and a ``record_history`` one for
#:   face picks (docs/PERF.md 2026-08-01 §2) — until PERF-REAL-3 made every
#:   evaluation record, so an edit and the pick after it share one checkpoint;
#:   the arithmetic below keeps the old factor of 2 as headroom (a modeler
#:   flipping between two parts);
#: * docs/OPERATIONS.md §6 sizes a host for up to **8 concurrent modelers**, and
#:   without session affinity every one of them can land on any worker — so one
#:   worker must be able to hold 8 users x 2 = **16** live checkpoints;
#: * speculation now has a strictly weaker claim (see :meth:`PrefixCache.store`),
#:   but it still needs room to be worth having: one warm ticket is one entry
#:   (two before PERF-REAL-3), plus the stale ones superseded tickets leave behind;
#: * an assembly evaluates one tree per unique part inside a single request, so a
#:   ~10-part assembly wants ~10 transient entries of its own.
#:
#: 16 + headroom, rounded to a power of two, is 32. The OLD value was 8 — exactly
#: four modelers — and the fifth user knocked over everybody's cache: hit rate
#: 0.40 -> 0.28 -> 0.15 and ``/measure`` 244 ms -> 19 189 ms, a 79x regression on
#: the cheapest operation in the product (CONC-4).
#:
#: THE PRICE, measured rather than assumed. On the docs/PERF.md tray at N=100
#: (219 faces), eight distinct lineages held at once cost **+2 MiB of RSS per
#: retained checkpoint** past the first, ~4 MiB at the N=200 body's 442 faces.
#: So a *completely full* cache of big parts is ~128 MiB (32 x 4 MiB), and of
#: mid-sized ones ~64 MiB, against the ~1 GiB per-worker budget in
#: docs/OPERATIONS.md §6 whose floor is OCCT's ~500 MiB plus the resident part.
#: That is the tradeoff, stated: **up to ~13 % of a worker's budget spent to stop
#: the fifth user costing everyone 79x.** It is a ceiling, not a reservation —
#: one modeler occupies one or two entries, and RSS only grows if 32 distinct large
#: lineages are genuinely live. (Releasing them does not return RSS to the OS —
#: glibc keeps the arena — which is why the per-entry figure is measured as a
#: marginal cost, not as a delta after a clear.)
#:
#: SINCE 2026-09-24 THIS IS THE SECONDARY BOUND. "~128 MiB" above was true of
#: analytic parts only: a count prices every entry the same, and a freeform
#: checkpoint weighs more. The memory bound is now
#: :data:`REBUILD_CACHE_BYTE_BUDGET`, which keeps 128 MiB as the ceiling.
REBUILD_CACHE_CAPACITY = 32

#: Max total estimated HEAP BYTES held by frontier checkpoints in this worker —
#: **the frontier cache's memory bound**, with :data:`REBUILD_CACHE_CAPACITY` now
#: the secondary (count) bound. **128 MiB: the ceiling the capacity comment above
#: already documents** ("a completely full cache of big parts is ~128 MiB"), which
#: was only TRUE for analytic parts. A count prices every entry the same, and on
#: geometry QA's lofted-NURBS plate (GQA-LADDER-1's part; 24 lobes, 76 features)
#: one entry measured ~5.5 MiB of heap, so 32 of them would have been ~176 MiB.
#: Each entry is weighed when it is stored (:meth:`Detachable.weigh`: the state's
#: shapes and the provenance memo's faces by
#: :func:`geometry.kernel.fork.estimate_heap_bytes`, plus the memoised GLB's
#: exact length), and evicted LRU-first with speculation first, as before.
#: ``tests/test_rebuild_cache.py`` fills the cache with that freeform part and
#: measures the heap it actually frees against the budget.
#:
#: THE ONE-ENTRY EXEMPTION, for a checkpoint heavier than the whole budget — a
#: part whose state plus mesh exceeds 128 MiB, e.g. the 211-solid gauntlet
#: assembly, whose GLB alone is 142 MB. Refusing it would make every repeat of
#: that part (``/measure``, ``/tessellate``, ``/export``) a full rebuild — a
#: budget making the part in front of the user SLOWER than no budget at all, on
#: exactly the large real parts PERF-REAL-1 is about. So a LIVE oversize
#: checkpoint is held ALONE: every other entry is evicted first
#: (:attr:`CacheStats.oversize_held`). It is bounded: at most one such entry
#: exists (the next store of any size puts the cache over budget, and the LRU
#: eviction takes it first), and a SPECULATIVE oversize checkpoint is still
#: refused (:attr:`CacheStats.oversize_refused`).
#:
#: WORST CASE, stated: at rest the frontier holds either <= this budget, or
#: exactly ONE live oversize checkpoint and nothing else. For the instant of an
#: oversize store — between the new entry being handed over and the others
#: being dropped — it is this budget plus that one checkpoint. The oversize
#: part's own cost (~2 GiB peak RSS for the 211-solid assembly) dwarfs either.
REBUILD_CACHE_BYTE_BUDGET = 128 * 1024 * 1024

#: Every ``RUNG_SPACING``-th feature boundary is a LADDER rung (PERF-REAL-2): the
#: evaluator forks its state there on EVERY evaluation and offers the fork to the
#: ladder. **8, from what a fork costs against what a feature costs.** A fork of
#: the N=250 tray's final state (560 faces) measured **18-20 ms**; the evaluator
#: does two per rung, and summed over a cold N=250 rebuild that is **~630 ms of
#: ~38 s (1.6 %)** — while one late feature of that tray costs ~0.4-1 s. So
#: halving the spacing would double a small tax to save about one feature per
#: edit, and doubling it would save ~0.3 s per cold rebuild and cost up to four
#: more features (~2-4 s) on every late edit.
RUNG_SPACING = 8

#: How densely the ladder keeps rungs as they recede from the chain's frontier
#: (:func:`rung_retained`). **2, from the tray's measured cost curve.** Rebuild
#: cost grows as ~N^2.15 (docs/GEOMETRY-QA.md 2026-09-15), so waste near feature 0
#: is cheap and waste near the end is not. Modelling an edit at a uniformly random
#: feature of the 250-feature tray, the re-run cost the ladder adds over the
#: unavoidable floor is: density 1 -> 9 rungs, mean 5.3 % / worst 18 % of a cold
#: rebuild; **density 2 -> 15 rungs, 2.9 % / 10.5 %**; density 3 -> 23 rungs,
#: 1.7 % / 5.8 %. Density 2 buys most of the gain for ~1.6x the rungs of density 1.
RUNG_DENSITY = 2

#: Max rungs held across every chain in this worker — the secondary bound, for a
#: workload of many tiny parts, where per-rung Python overhead outweighs the bytes.
RUNG_CAPACITY = 64

#: Max total estimated HEAP BYTES held by rungs in this worker — **the memory
#: bound.** 64 MiB: ~6 % of docs/OPERATIONS.md §6's ~1 GiB per worker, and half
#: :data:`REBUILD_CACHE_BYTE_BUDGET`, the frontier cache's own byte ceiling —
#: so the whole rebuild cache is bounded at ~192 MiB estimated heap. Each rung
#: is weighed when it is stored (:func:`geometry.kernel.fork.estimate_heap_bytes`:
#: its binary BRep size, which carries the geometry, plus a per-face term for the
#: topology), because a face's weight varies 15.7x between part kinds.
#:
#: WHY BYTES AND NOT FACES (GQA-LADDER-1, 2026-09-24). The first ladder was
#: bounded at 20 000 faces, priced at the housing tray's 3.2 KiB/face. On a part
#: of overlapping lofted NURBS lobes geometry QA measured **50.4 KiB/face**: 2 344
#: faces were already 115 MiB, and the face budget projected to ~985 MiB per
#: worker. ``tests/test_rebuild_cache.py`` holds that part's ladder under this
#: bound and fails with a face-priced weight put back. The estimate is calibrated
#: to read +8-11 % HIGH on every part measured, so the bound errs towards holding
#: less.
RUNG_BYTE_BUDGET = 64 * 1024 * 1024

#: No single rung may weigh more than this; a heavier one is refused, not stored.
#: A quarter of the budget, so one enormous part cannot evict every other chain
#: in one store, and still ~8x the heaviest state measured (the 560-face tray at
#: ~2 MiB, the 24-lobe NURBS part at ~4 MiB). A part past it gets no ladder:
#: its edits cost what they cost before PERF-REAL-2, and its memory is bounded.
RUNG_MAX_BYTES = RUNG_BYTE_BUDGET // 4


def rung_retained(
    unit: int, frontier_unit: int, *, density: int = RUNG_DENSITY
) -> bool:
    """Whether rung *unit* stays on a chain whose newest rung is *frontier_unit*.

    Units count rungs (``prefix_length // RUNG_SPACING``). The rule keeps every
    rung near the frontier and progressively fewer further back: at distance
    ``d = frontier_unit - unit + 1`` a rung survives iff ``unit`` is a multiple of
    ``2 ** max(0, floor(log2 d) - density)``. So the gap below an edit is under
    ``2 ** (1 - density)`` times its distance from the frontier (checked for every
    frontier up to 400 units: worst 0.66x at density 1, **0.28x at density 2**) —
    an edit ``D`` features from the end re-runs under ~``1.3 D`` features plus one
    spacing — and a chain holds at most ``2**density * units.bit_length()``
    rungs, not one per unit.

    MONOTONE, which is what makes it safe to apply incrementally: as the frontier
    advances the required power of two only grows, so a rung dropped once would be
    dropped again — a later evaluation never needs a rung an earlier one threw
    away. (Asserted in ``tests/test_rebuild_cache.py``.)
    """
    if unit <= 0 or unit > frontier_unit:
        return unit > frontier_unit
    level = (frontier_unit - unit + 1).bit_length() - 1
    return unit % (1 << max(0, level - density)) == 0


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

    def weigh(self) -> int:
        """Estimated heap bytes this checkpoint pins while it is cached.

        Called by the cache, after :meth:`detach` and outside its lock, when a
        FRONTIER checkpoint is stored — the weight the byte budget
        (:data:`REBUILD_CACHE_BYTE_BUDGET`) is charged. A count alone could not
        bound memory: one freeform checkpoint weighs ~5.5 MiB where the tray's
        weighs ~2-4 MiB (see that constant).
        """
        ...

    def fork(self) -> Self:
        """An independent copy the caller will own (a LADDER rung's hand-out).

        A rung is never handed out itself — it stays on the ladder for the next
        edit — so :meth:`PrefixCache.take` hands out ``rung.fork()``. That is
        byte-transparent ONLY because the evaluator forks at every rung position
        on every evaluation, cached or not (see "THE LADDER" in the module
        docstring); a payload whose fork is not what the evaluator itself
        continues with would make the resume differ from a cold rebuild.
        """
        ...


@dataclass(frozen=True)
class CacheStats:
    """In-process counters, read by the tests. The operator-facing versions of
    the same events are Prometheus counters moved at the SAME lines that move
    these (:mod:`py_kit.metrics`), so the two cannot drift apart: there is one
    increment site per event, not two.

    ``speculative_refused`` is the exception, and deliberately so: it counts warm
    checkpoints DROPPED because the cache held only live work, which is the
    mechanism CONC-4 asked for behaving correctly rather than an operator-facing
    fault. It has no Prometheus twin yet because the counter would have to be
    declared in :mod:`py_kit.metrics`, which this change does not own.
    """

    hits: int
    misses: int
    stores: int
    evictions: int
    resumed_features: int
    speculative_refused: int = 0
    #: FRONTIER bytes held right now (estimated); SPECULATIVE checkpoints
    #: refused because one alone outweighed the whole byte budget; and LIVE ones
    #: that did, and were held alone under the one-entry exemption.
    entry_bytes: int = 0
    oversize_refused: int = 0
    oversize_held: int = 0
    #: The LADDER's counters (PERF-REAL-2). ``rung_hits`` is the subset of
    #: ``hits`` served by a rung rather than by a frontier checkpoint;
    #: ``rung_evictions`` counts rungs dropped for the global bound (count or
    #: bytes), ``rung_thinned`` those dropped by :func:`rung_retained`;
    #: ``rung_bytes`` is the estimated heap the ladder holds right now.
    rung_hits: int = 0
    rung_stores: int = 0
    rung_evictions: int = 0
    rung_thinned: int = 0
    rungs: int = 0
    rung_bytes: int = 0


class Resume[CheckpointT: Detachable](NamedTuple):
    """What :meth:`PrefixCache.take` hands back: a checkpoint, and its claim.

    ``speculative`` travels with the entry because a re-store must not LAUNDER
    it: :func:`geometry.features.evaluate.warm_rebuild_cache` puts back an entry
    it took when the requested prefix is already cached, and if that put-back
    guessed the flag it would either downgrade a live checkpoint to speculative
    (making it evictable by somebody else's guess) or promote a guess to live.
    """

    prefix_length: int
    checkpoint: CheckpointT
    speculative: bool
    #: ``True`` when this is a FORK of a ladder rung, which is still on the
    #: ladder: there is nothing to put back, and nothing to re-store.
    rung: bool = False


@dataclass(frozen=True)
class _Entry[CheckpointT: Detachable]:
    """One cached checkpoint plus the strength of its claim on a slot."""

    checkpoint: CheckpointT
    speculative: bool
    nbytes: int = 0


@dataclass(frozen=True)
class _Rung[CheckpointT: Detachable]:
    """One ladder rung: a checkpoint nobody else references, and its weight."""

    checkpoint: CheckpointT
    speculative: bool
    nbytes: int


def prefix_keys(
    request: EvaluateTreeRequest,
    *,
    capture_scope: Iterable[uuid.UUID],
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

    Nor is WHO is asking. Until PERF-REAL-3 a ``record_history`` flag was in the
    header, because only a face pick recorded per-face provenance and a prefix
    evaluated without it cannot serve one; that split every modeler into two
    lineages and made the pick after every open or edit a full-tree miss (7.9 s
    on the 1 018-face gearbox). Every evaluation now records, so the state after
    *k* features is the same object whichever route asked, and one key serves them
    all — ``/evaluate``, ``/overlay``, ``/measure``, ``/tessellate``, export and
    drawings. A future evaluation mode that changes what the state HOLDS must go
    back in the header; one that only changes what is published afterwards must
    not.
    """
    header = json.dumps(
        {
            "version": CACHE_KEY_VERSION,
            "linear_deflection": request.linear_deflection,
            "capture_scope": sorted(str(feature_id) for feature_id in capture_scope),
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

    SPECULATION HAS A WEAKER CLAIM THAN LIVE WORK, and it is this class that
    makes that true rather than the callers' good manners — see :meth:`store`.
    """

    def __init__(
        self,
        capacity: int,
        *,
        byte_budget: int = REBUILD_CACHE_BYTE_BUDGET,
        rung_capacity: int = RUNG_CAPACITY,
        rung_byte_budget: int = RUNG_BYTE_BUDGET,
        rung_max_bytes: int = RUNG_MAX_BYTES,
        rung_spacing: int = RUNG_SPACING,
    ) -> None:
        if capacity <= 0 or byte_budget <= 0:
            raise ValueError(
                f"capacity and byte budget must be > 0, got {capacity}, {byte_budget}"
            )
        if (
            min(rung_capacity, rung_byte_budget, rung_max_bytes) < 0
            or rung_spacing <= 0
        ):
            raise ValueError("rung bounds must be >= 0 and the spacing > 0")
        self._capacity = capacity
        self._byte_budget = byte_budget
        self._entry_bytes = 0
        self._oversize_refused = 0
        self._oversize_held = 0
        self._rung_capacity = rung_capacity
        self._rung_byte_budget = rung_byte_budget
        self._rung_max_bytes = min(rung_max_bytes, rung_byte_budget)
        self._rung_spacing = rung_spacing
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, _Entry[CheckpointT]] = OrderedDict()
        self._rungs: OrderedDict[str, _Rung[CheckpointT]] = OrderedDict()
        self._rung_bytes = 0
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._evictions = 0
        self._resumed_features = 0
        self._speculative_refused = 0
        self._rung_hits = 0
        self._rung_stores = 0
        self._rung_evictions = 0
        self._rung_thinned = 0

    def take(self, keys: Sequence[str]) -> Resume[CheckpointT] | None:
        """The longest cached prefix of *keys*, owned by the caller, or ``None``.

        Searches longest-first, so a repeat of the same tree resumes at the full
        length (zero further features) and an append resumes one short of it.
        ``keys[0]`` (the empty prefix) is never a useful checkpoint and is not
        probed. Returns ``(prefix_length, checkpoint)``; the caller owns the
        checkpoint and MUST NOT assume the cache still holds it.

        Two sources, one rule -- the LONGEST prefix wins, whichever holds it:

        * a FRONTIER checkpoint is REMOVED and handed over (ownership transfer);
        * a LADDER rung stays where it is and the caller gets ``rung.fork()``,
          taken outside the lock since it is OCCT work. A rung is never mutated
          after it is stored, so forking it while another thread evicts it is
          harmless: eviction only drops the cache's reference.

        At equal length the frontier wins: it needs no fork.

        INVALIDATION IS THE KEY, AND ONLY THE KEY. ``keys[k]`` addresses the first
        *k* features, so an edit at feature index *k* changes ``keys[k + 1:]`` and
        nothing before -- the longest match is then at most *k*, and no state that
        has seen the pre-edit feature can be reached. Both sources are looked up
        under exactly that key; there is no second index to drift.

        THIS IS ALSO THE REBUILD OBSERVABILITY SEAM (:mod:`py_kit.metrics`).
        ``evaluate_tree`` consults the cache unconditionally — it is the second
        statement of the function, before any kernel work — so every rebuild in
        the product passes through here exactly once, whatever route asked for
        it. Instrumenting the nine ``evaluate_tree`` call sites instead would
        leave the tenth uncounted and the graph silently wrong. Nothing about the
        cache's behaviour depends on the recording.
        """
        rung: _Rung[CheckpointT] | None = None
        rung_length = 0
        with self._lock:
            for length in range(len(keys) - 1, 0, -1):
                entry = self._entries.pop(keys[length], None)
                if entry is not None:
                    self._entry_bytes -= entry.nbytes
                    self._touch_rungs(keys, length)
                    self._hits += 1
                    self._resumed_features += length
                    record_rebuild_cache_hit()
                    note_rebuild(features=len(keys) - 1, resumed=length)
                    return Resume(length, entry.checkpoint, entry.speculative)
                rung = self._rungs.get(keys[length])
                if rung is not None:
                    self._touch_rungs(keys, length)
                    rung_length = length
                    self._hits += 1
                    self._rung_hits += 1
                    self._resumed_features += length
                    record_rebuild_cache_hit()
                    note_rebuild(features=len(keys) - 1, resumed=length)
                    break
            else:
                self._misses += 1
                record_rebuild_cache_miss()
                note_rebuild(features=len(keys) - 1, resumed=0)
                return None
        assert rung is not None
        return Resume(rung_length, rung.checkpoint.fork(), speculative=False, rung=True)

    def store_rung(
        self,
        chain: Sequence[str],
        prefix_length: int,
        checkpoint: CheckpointT,
        *,
        nbytes: int,
        speculative: bool = False,
    ) -> bool:
        """Put *checkpoint* on the ladder as the state after *prefix_length*
        features of *chain*, then thin the chain's older rungs. Returns whether it
        was kept.

        *checkpoint* must be exclusively owned and never touched again by the
        caller -- the evaluator hands over the FIRST of its two forks at a rung and
        carries on with the second (module docstring, "THE LADDER"). *nbytes* is
        its estimated heap weight against the byte budget.

        It goes in under ``chain[prefix_length]`` -- the key of exactly the
        features it has evaluated, which is the whole invalidation argument (see
        :meth:`take`). Then every older rung ON THE SAME CHAIN that
        :func:`rung_retained` no longer keeps is dropped, and finally the global
        bounds are enforced LRU-first with speculation evicted before live work,
        the order :meth:`store` uses. A speculative rung that could only be kept
        by evicting live rungs is refused; so is any rung heavier than
        :data:`RUNG_MAX_BYTES`. A key already on the ladder keeps its checkpoint (every
        evaluation forks at the same positions, so it is the same state); a live
        pass over a speculative rung only upgrades its claim.
        """
        if prefix_length <= 0 or prefix_length % self._rung_spacing:
            raise ValueError(
                f"a rung sits on a multiple of {self._rung_spacing}, "
                f"got prefix length {prefix_length}"
            )
        key = chain[prefix_length]
        with self._lock:
            existing = self._rungs.get(key)
            if existing is not None:
                self._rungs.move_to_end(key)
                if existing.speculative and not speculative:
                    # Live work has now passed this rung too: it is no longer a
                    # guess, so it stops being the first victim.
                    self._rungs[key] = _Rung(
                        existing.checkpoint, False, existing.nbytes
                    )
                return True
            if nbytes > self._rung_max_bytes or self._rung_capacity == 0:
                self._speculative_refused += int(speculative)
                return False
            frontier = prefix_length // self._rung_spacing
            for unit in range(1, frontier):
                older = chain[unit * self._rung_spacing]
                if older in self._rungs and not rung_retained(unit, frontier):
                    self._drop_rung(older)
                    self._rung_thinned += 1
            if speculative and not self._rung_room_without_live(nbytes):
                self._speculative_refused += 1
                return False
            self._rungs[key] = _Rung(checkpoint, speculative, nbytes)
            self._rung_bytes += nbytes
            self._rung_stores += 1
            while (
                len(self._rungs) > self._rung_capacity
                or self._rung_bytes > self._rung_byte_budget
            ):
                victim = next(
                    (k for k, r in self._rungs.items() if r.speculative),
                    next(iter(self._rungs)),
                )
                self._drop_rung(victim)
                self._rung_evictions += 1
            return key in self._rungs

    def _touch_rungs(self, keys: Sequence[str], length: int) -> None:
        """Mark every rung of ``keys[:length + 1]`` recently used, shallowest
        first (caller holds the lock).

        A hit at *length* proves the whole chain below it is live, not only the
        rung that served it. Touching just that one let a drag on a late
        feature age the chain's deep rungs out behind the dead branches the drag
        itself kept creating (review probe: 40 drags on #241 of 250 left the live
        chain with ONE rung, and 34 dead ones at 248), so the next edit further
        in paid a full rebuild. Ascending order keeps the deepest rung the most
        recent of them, which is the one the NEXT drag step resumes from.
        """
        for position in range(self._rung_spacing, length + 1, self._rung_spacing):
            if keys[position] in self._rungs:
                self._rungs.move_to_end(keys[position])

    @property
    def rung_spacing(self) -> int:
        """Rungs sit at every multiple of this prefix length. The evaluator reads
        it HERE, so the positions it forks at and the positions this cache accepts
        cannot disagree."""
        return self._rung_spacing

    def _rung_room_without_live(self, nbytes: int) -> bool:
        """Could a new rung of *nbytes* fit by evicting speculative rungs only?
        (caller holds the lock)"""
        live = [r for r in self._rungs.values() if not r.speculative]
        return (
            len(live) + 1 <= self._rung_capacity
            and sum(r.nbytes for r in live) + nbytes <= self._rung_byte_budget
        )

    def _drop_rung(self, key: str) -> None:
        """Remove one rung and its weight (caller holds the lock)."""
        rung = self._rungs.pop(key)
        self._rung_bytes -= rung.nbytes

    def rung_lengths(self, keys: Sequence[str]) -> list[int]:
        """The prefix lengths of *keys* holding a rung (TEST SEAM + diagnostics)."""
        with self._lock:
            return [
                length for length in range(1, len(keys)) if keys[length] in self._rungs
            ]

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

    def store(
        self, key: str, checkpoint: CheckpointT, *, speculative: bool = False
    ) -> bool:
        """Take ownership of *checkpoint* and cache it under *key*.

        The caller MUST own the checkpoint exclusively — nothing else may hold
        its shapes — which is why the ordinary path is
        :meth:`store_on_release` and the direct call is reserved for a warm,
        whose state was never published. :meth:`Detachable.detach` runs here, on
        the cache's side of the transfer.

        *speculative* marks a checkpoint a PREFETCH built (nobody asked for it
        yet), and it buys the entry a strictly weaker claim on a slot. Returns
        whether the entry was cached — ``False`` only for a refused speculative
        store (including one that alone outweighs
        :data:`REBUILD_CACHE_BYTE_BUDGET`; a LIVE one that does is held alone —
        see the one-entry exemption there).
        The cache is bounded by COUNT and by estimated HEAP BYTES
        (:meth:`Detachable.weigh`, taken here after ``detach``, outside the lock);
        "full" below means either bound. The rule, in the order the code applies
        it:

        * **evict speculation first.** The victim is the least-recently-used
          SPECULATIVE entry if there is one, and only otherwise the LRU overall.
          So a real checkpoint outlives a guess even when the guess is newer,
          which is the direction CONC-6 says is correct.
        * **refuse a speculative store that would REPLACE live work** under the
          same key — a live entry may carry artifacts a guess never has.
        * **refuse a speculative store that would evict live work.** When the
          cache is full of real checkpoints, the warm's own result is dropped —
          the speculation simply achieved nothing, which is a far better outcome
          than a live modeler's checkpoint becoming a 19-second `/measure`
          (CONC-4). Counted in :attr:`CacheStats.speculative_refused`.

        Together these make "a warm never evicts a live user's checkpoint" a
        property of this method rather than an assumption about the working set —
        the assumption that measurably failed at four users on one worker.

        ``detach`` and ``weigh`` run before the decision, so a refused
        checkpoint is detached, weighed and then dropped. That is deliberate:
        doing it inside the lock would hold the lock across an OCCT call, and
        the only cost is a ``BRepTools::Clean`` and a serialisation of shapes
        about to be garbage anyway.
        """
        checkpoint.detach()
        nbytes = checkpoint.weigh()
        with self._lock:
            existing = self._entries.get(key)
            if speculative and existing is not None and not existing.speculative:
                # A guess never REPLACES live work under the same key either —
                # the collision form of the eviction rule below. The live entry
                # may carry artifacts a guess never has.
                self._speculative_refused += 1
                return False
            if nbytes > self._byte_budget and speculative:
                # A GUESS heavier than the whole budget is never worth a slot.
                self._oversize_refused += 1
                return False
            if existing is not None:
                del self._entries[key]
                self._entry_bytes -= existing.nbytes
            if nbytes > self._byte_budget:
                # THE ONE-ENTRY EXEMPTION: the part in front of the user is never
                # made slower by the budget than by no budget at all. A LIVE
                # checkpoint heavier than the whole budget is stored anyway, and
                # the eviction loop below drops every OTHER entry (it is the
                # newest, so it is never the victim while another remains) and
                # then stops with it held ALONE, so its repeats stay hits. At
                # most one such entry exists: the next store of any size puts the
                # cache over budget with two entries, and the loop takes this
                # one (then the LRU) first.
                self._oversize_held += 1
            if speculative and not self._room_without_live(nbytes):
                # Only live work could make room. Speculation yields — silently
                # to the user, and loudly to the counters.
                self._speculative_refused += 1
                return False
            self._entries[key] = _Entry(checkpoint, speculative, nbytes)
            self._entry_bytes += nbytes
            self._stores += 1
            record_rebuild_cache_store()
            # Over budget with ONE entry left means that entry is the exempt
            # oversize checkpoint just stored: it stays (see the exemption above).
            while len(self._entries) > self._capacity or (
                self._entry_bytes > self._byte_budget and len(self._entries) > 1
            ):
                speculative_victim = self._victim_key()
                victim = (
                    next(iter(self._entries))
                    if speculative_victim is None
                    else speculative_victim
                )
                self._entry_bytes -= self._entries.pop(victim).nbytes
                self._evictions += 1
                record_rebuild_cache_eviction()
        return True

    def _room_without_live(self, nbytes: int) -> bool:
        """Could an entry of *nbytes* fit by evicting speculative entries only?
        (caller holds the lock)"""
        live = [entry for entry in self._entries.values() if not entry.speculative]
        return (
            len(live) + 1 <= self._capacity
            and sum(entry.nbytes for entry in live) + nbytes <= self._byte_budget
        )

    def _victim_key(self) -> str | None:
        """The least-recently-used SPECULATIVE entry, or ``None`` if every entry
        is live work (caller holds the lock)."""
        for candidate, entry in self._entries.items():
            if entry.speculative:
                return candidate
        return None

    def clear(self) -> None:
        """Drop every entry (test isolation; production never calls this)."""
        with self._lock:
            self._entries.clear()
            self._entry_bytes = 0
            self._rungs.clear()
            self._rung_bytes = 0

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                stores=self._stores,
                evictions=self._evictions,
                resumed_features=self._resumed_features,
                speculative_refused=self._speculative_refused,
                entry_bytes=self._entry_bytes,
                oversize_refused=self._oversize_refused,
                oversize_held=self._oversize_held,
                rung_hits=self._rung_hits,
                rung_stores=self._rung_stores,
                rung_evictions=self._rung_evictions,
                rung_thinned=self._rung_thinned,
                rungs=len(self._rungs),
                rung_bytes=self._rung_bytes,
            )


class WorkGate(Protocol):
    """What a warm needs of the world to decide whether it may use the core.

    A Protocol so :func:`geometry.features.evaluate.warm_rebuild_cache` — which
    is where the yield has to be implemented, because that is where the
    half-built state lives — does not import a concrete gate, and so a test can
    hand it a deterministic one instead of racing real threads.
    """

    def busy(self) -> bool:
        """Whether real (non-speculative) work is in flight right now."""
        ...

    def wait_until_idle(self, timeout_s: float) -> bool:
        """Block up to *timeout_s* for it to stop being. Returns idle-ness."""
        ...


class LiveWorkGate:
    """How many REAL evaluations are in flight in this process, and a way to wait.

    The counterpart to the cache's eviction rule, one layer down: speculation
    must have a weaker claim on the CORE as well as on a slot. It exists because
    the alternative was measured and it was bad — CONC-6, on the 50-feature tray:
    a warm issued immediately before the commit took the commit from **2 589 ms
    to 4 742 ms**, 1.8x WORSE than never speculating at all. Nothing was wrong
    with the warm; OCP does not release the GIL (CONC-5), so one worker has one
    effective core and the guess and the real request simply halved each other.

    Two things follow, and both are policy the :class:`WarmScheduler` applies
    rather than anything this class decides:

    * a warm does not START while real work is in flight, so the pessimal case is
      "the speculation achieved nothing", never "the user waited longer";
    * a warm PAUSES at its next feature boundary when real work arrives, STORES
      the prefix it has built so far, and resumes from it when the worker is idle
      again. Storing is not tidiness — it is what makes a partial dwell worth
      anything at all. Measured 2026-08-01 on the N=100 tray: work a warm is
      still holding is invisible, so a face pick that arrived while the warm sat
      mid-provenance paid the full 9.2 s; with the prefix banked at the pause it
      resumes instead. Nothing in flight can be resumed from; only something in
      the cache can.

    NOT A LOCK, and it must never become one: :meth:`tracked` is a counter, so
    two real requests never serialise on it (``test_concurrent_modelers.py``
    depends on genuinely concurrent rebuilds). The only thread that ever waits is
    the single speculative one.

    Scope note: it counts :func:`geometry.features.evaluate.evaluate_tree`, which
    is where every rebuild in the product funnels (the same argument that makes
    ``take`` the metrics seam), and so covers tessellation, mass properties and
    export as well as the dispatch loop. A STEP import is a bounded SUBPROCESS
    and deliberately not counted.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._count = 0
        self._waits = 0

    @contextmanager
    def tracked(self) -> Generator[None]:
        """Mark real work in flight for the duration of the block."""
        with self._lock:
            self._count += 1
        try:
            yield
        finally:
            with self._lock:
                self._count -= 1
                if self._count == 0:
                    self._idle.notify_all()

    def busy(self) -> bool:
        with self._lock:
            return self._count > 0

    def wait_until_idle(self, timeout_s: float) -> bool:
        """Block up to *timeout_s* for the last real evaluation to finish.

        Returns whether the worker is idle. Callers poll this in short slices
        rather than waiting once for a long time, because the waiter also has to
        notice being superseded or cancelled, and that signal lives elsewhere.
        """
        with self._lock:
            if self._count == 0:
                return True
            self._waits += 1
            return self._idle.wait_for(lambda: self._count == 0, timeout_s)

    @property
    def waits(self) -> int:
        """How many times speculation has stood aside for real work.

        Nonzero is the design working, not a fault: it counts the CPU a
        committing user did NOT have to share with a guess.
        """
        with self._lock:
            return self._waits


#: The process's live-work counter. Process-global for the same reason the caches
#: are: it describes THIS worker's one effective core.
_LIVE_WORK = LiveWorkGate()


def live_work() -> LiveWorkGate:
    """The process's live-work gate (the evaluator marks it; a warm waits on it)."""
    return _LIVE_WORK


#: How long one speculative pause lasts before the warm re-examines its world.
#: Short enough that a cancelled or superseded ticket is not held up by it, long
#: enough that a warm waiting out a 27-second rebuild is not spinning.
WARM_YIELD_SLICE_S = 0.05

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
    Neither of those is the PRIORITY rule. One warm per worker bounds the CPU
    speculation can consume; it does not stop that one core being the core
    somebody's commit needed, and CONC-6 measured the difference at 1.8x. That
    rule is :class:`LiveWorkGate`, applied inside
    :func:`geometry.features.evaluate.warm_rebuild_cache` — a bound and a
    priority are different jobs and this class only does the first.

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
        spent* OR *somebody has superseded/cancelled me*.

        Deliberately NOT the live-work yield. "Give the core back" and "give up"
        are different instructions — a yielding warm banks its prefix and carries
        on later, a stopped one is finished — and only the code holding the
        half-built state can act on the first. So the yield lives in
        :func:`geometry.features.evaluate.warm_rebuild_cache` (which owns that
        state) and this predicate keeps meaning exactly one thing.
        """
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
