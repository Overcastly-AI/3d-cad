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
parsed cleanly once (single solid, within the wall-clock bound) is ever cached,
so a hit is reached only for input that has already cleared every bound — a hit
never short-circuits the timeout or the size cap.

**What is stored — BREP bytes, not a live shape.** The cache holds OCCT's native
lossless BREP serialization of the parsed solid, re-read into a FRESH shape on
every hit (:func:`geometry.kernel.solid_from_brep_bytes`). Caching a live OCCT
shape would be a determinism/thread-safety hazard: tessellation stores its
triangulation INTO the shape and the FastAPI threadpool could evaluate two
trees concurrently, racing on one shared body. A fresh per-hit shape has none
of that shared mutable state, and BREP re-read is in-process and cheap versus
re-spawning the parse worker. Because BREP write→read is idempotent on the
already-BREP-read body the worker returns, a hit tessellates byte-identically
to the direct parse (the ``import-step-box-10x20x30`` golden stays byte-exact).
"""

import hashlib
import threading
from collections import OrderedDict

from build123d import Solid

from geometry.kernel import (
    import_step_solid,
    solid_from_brep_bytes,
    solid_to_brep_bytes,
)

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


def import_step_solid_cached(step_text: str, *, timeout_s: float) -> Solid:
    """Parse *step_text* into a single :class:`Solid`, caching the result.

    The cached funnel the ``import`` evaluate handler calls instead of
    :func:`geometry.kernel.import_step_solid` directly. On a HIT, the parsed
    body is re-read from cached BREP bytes into a fresh shape and the killable
    subprocess parse is SKIPPED. On a MISS, the UNCHANGED bounded parse runs
    (preserving the timeout + subprocess isolation of design §6), and only its
    successful result is cached — a raise (timeout / parse failure / not a
    single solid) is never cached, so a rejected input re-enforces every bound
    on the next attempt.

    Raises exactly what :func:`import_step_solid` raises on a miss; a hit cannot
    raise those (only cleanly-parsed bodies are ever cached).
    """
    key = step_content_key(step_text)
    cached = _cache.get(key)
    if cached is not None:
        return solid_from_brep_bytes(cached)
    solid = import_step_solid(step_text, timeout_s=timeout_s)
    _cache.put(key, solid_to_brep_bytes(solid))
    return solid
