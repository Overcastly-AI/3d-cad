"""Content-keyed cache of parsed STEP bodies (engineering audit F8).

An inline ``import`` feature stores its STEP part-21 TEXT in the feature tree
(up to ``MAX_INLINE_STEP_CHARS = 16 MiB``), and ``evaluate_tree`` re-runs the
whole prefix on every edit — so without a cache **every** edit of a part that
starts from an imported body re-spawns the killable OCCT parse worker
(~0.9 s cold-start + up to 16 MiB of part-21), a per-edit latency floor that
grows with nothing. This module memoises the PARSE RESULT keyed on the STEP
content so an unchanged import pays exactly one parse per distinct upload, not
one per edit.

**Cache, not state (RESEARCH §3).** The parse is a pure function of the STEP
bytes — like the mesh store, the key is the content address ONLY
(``sha256:<hex of step_text>``), never a tenant/part id — so the cache is a
per-worker performance optimisation, never a correctness dependency. A miss
(cold worker, eviction, or the very first upload) simply re-parses. With
multi-worker geometry now enabled (engineering audit F6, the S3 mesh-store
swap lifts the single-worker guard), this cache is **per-worker**: each worker
warms its own copy independently, and correctness never depends on a hit.

**Security + determinism preserved on a miss (design §6, BACKLOG P1).** A miss
runs the UNCHANGED :func:`geometry.kernel.import_step_solid`, whose untrusted
OCCT parse runs in the timeout-bounded, SIGKILL-able, subprocess-isolated
worker. The 16 MiB size cap is enforced at request validation (a 422) BEFORE a
feature is dispatched, so it is never bypassed either. Only a body that ALREADY
parsed cleanly once (one or more solids, within the wall-clock bound) is cached,
so a hit is reached only for input that has already cleared every bound (CPU-time
+ wall-clock parse bounds and the size cap) — a hit never short-circuits them.

**What is stored — BREP bytes, not a live shape.** The cache holds OCCT's native
lossless BREP serialization of the parsed solid, re-read into a FRESH shape on
every hit (:func:`geometry.kernel.solid_from_brep_bytes`). Caching a live OCCT
shape would be a determinism/thread-safety hazard: tessellation stores its
triangulation INTO the shape and the FastAPI threadpool could evaluate two
trees concurrently, racing on one shared body. A fresh per-hit shape has none
of that shared mutable state, and BREP re-read is in-process and cheap versus
re-spawning the parse worker.

**THE MISS PATH RETURNS THE ROUND-TRIPPED BODY TOO, AND THAT IS THE WHOLE
DETERMINISM ARGUMENT (F2, docs/GEOMETRY-QA.md 2026-09-15).** This module used
to return the worker's shape directly on a miss and the deserialized one on a
hit, justified by the claim that "BREP write→read is idempotent on an
already-BREP-read body". **That claim is false, and it is false in a way no
fixture here could see.** Measured on a 1 018-face imported gearbox: the
worker's body and its own BREP round-trip tessellate to DIFFERENT GLB bytes
(43 differing bytes of 10 412 360 — ULP noise in the vertex buffer, volume
bit-identical), and a second round-trip differs again, so the operation is not
idempotent at ANY iteration count. The user-visible consequence was that
``mesh_glb_id`` — a CONTENT address used for mesh dedup — took one value on a
cold worker and another on every cache hit, so a browser re-downloaded a 10 MB
mesh for no reason and any cross-restart determinism assertion was unsound.
Both import goldens are 6-face boxes, small enough that the round-trip happens
to be exact, which is why the suite agreed with the false claim for as long as
it existed.

The fix is structural rather than a tighter serialization: **every consumer of
an imported body receives the deserialization of ONE fixed byte string**, so
cold and warm cannot differ — not because the round-trip is faithful, but
because both paths take it exactly once. It costs one extra in-process BREP
read on a path that just spent seconds in a subprocess parse. Note the cache is
therefore mildly LOSSY with respect to the parse (the stored bytes are what
every downstream op sees), and that is now a stated property instead of an
accidental one.
"""

import hashlib
import threading
from collections import OrderedDict

from geometry.kernel import (
    import_step_solid,
    solid_from_brep_bytes,
    solid_to_brep_bytes,
)
from geometry.kernel.types import BodyShape

#: Max cached parsed bodies. Small on purpose — the cache is a per-worker perf
#: optimisation, not correctness, so a modest window covers a working session's
#: handful of distinct imported parts while bounding worst-case memory at
#: capacity x largest cached BREP.
STEP_CACHE_CAPACITY = 32


def step_content_key(step_text: str) -> str:
    """The content address of a STEP payload (``sha256:<hex>``).

    The same content-address idiom the mesh store uses: keyed on the bytes
    alone (tenant-free), so identical STEP content shares one cache entry.
    """
    return f"sha256:{hashlib.sha256(step_text.encode('utf-8')).hexdigest()}"


class StepParseCache:
    """Thread-safe bounded LRU of content-keyed parsed bodies (BREP bytes).

    In-process only (per-worker) — a hit is never a correctness guarantee, so
    there is no cross-process backend and no startup guard: a cold worker just
    re-parses. Values are BREP bytes (see the module docstring), keyed on the
    STEP content address.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, bytes] = OrderedDict()

    def get(self, key: str) -> bytes | None:
        """The cached BREP bytes for *key*, or ``None`` (evicted/cold)."""
        with self._lock:
            brep = self._entries.get(key)
            if brep is not None:
                self._entries.move_to_end(key)
            return brep

    def put(self, key: str, brep: bytes) -> None:
        """Cache *brep* under *key* (idempotent; evicts the LRU at capacity)."""
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
            else:
                self._entries[key] = brep
                while len(self._entries) > self._capacity:
                    self._entries.popitem(last=False)


#: Process-wide (per-worker) parse cache consulted by the import handler.
_cache = StepParseCache(STEP_CACHE_CAPACITY)


def reset_step_cache() -> None:
    """Install a fresh, empty per-worker cache.

    Test isolation seam: a test asserting MISS behaviour (e.g. that a tiny
    configured timeout actually trips the subprocess bound) must not be served
    a hit warmed by an earlier test in the same process. Production never calls
    this — the cache is append-only-with-eviction for the worker's lifetime.
    """
    global _cache
    _cache = StepParseCache(STEP_CACHE_CAPACITY)


def import_step_solid_cached(
    step_text: str, *, cpu_timeout_s: float, wall_timeout_s: float
) -> BodyShape:
    """Parse *step_text* into a :data:`BodyShape`, caching the result.

    Returns a bare :class:`~build123d.Solid` for a single-solid file or a
    lump-sorted :class:`~build123d.Compound` for a multi-solid one (§MB-4); the
    cached BREP bytes round-trip either body type (see
    :func:`~geometry.kernel.solid_from_brep_bytes`).

    The cached funnel the ``import`` evaluate handler calls instead of
    :func:`geometry.kernel.import_step_solid` directly. On a HIT, the parsed
    body is re-read from cached BREP bytes into a fresh shape and the killable
    subprocess parse is SKIPPED. On a MISS, the UNCHANGED bounded parse runs
    (preserving the timeout + subprocess isolation of design §6), and only its
    successful result is cached — a raise (timeout / parse failure / no solids)
    is never cached, so a rejected input re-enforces every bound on the next
    attempt.

    **A miss returns the body re-read from the bytes it just cached, NOT the
    worker's shape** — the one line that makes ``mesh_glb_id`` independent of
    cache state (F2; see the module docstring for the measurement that forced
    it). Both paths below end at ``solid_from_brep_bytes`` of the same ``brep``,
    which is what makes the two indistinguishable by construction rather than by
    an assumption about OCCT's serializer.

    Raises exactly what :func:`import_step_solid` raises on a miss; a hit cannot
    raise those (only cleanly-parsed bodies are ever cached).
    """
    key = step_content_key(step_text)
    cached = _cache.get(key)
    if cached is not None:
        return solid_from_brep_bytes(cached)
    body = import_step_solid(
        step_text, cpu_timeout_s=cpu_timeout_s, wall_timeout_s=wall_timeout_s
    )
    brep = solid_to_brep_bytes(body)
    _cache.put(key, brep)
    return solid_from_brep_bytes(brep)
