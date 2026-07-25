"""Content-addressed composed-drawing-artifact store — DE-4 (drawing-export.md §8.3).

``POST /api/v1/drawing/compose`` re-renders the SVG/PDF/DXF sheet on every request
today. This store memoises the COMPOSED BYTES keyed on a content address of the
compose inputs, so a repeat export of an unchanged drawing is a fetch, not a
recompute (drawing-export.md §8.3). It rides the SAME object-storage seam the mesh
store uses (:mod:`geometry.mesh_store` / :mod:`geometry.s3_store`): the same
``sha256:<hex>`` content-address key format, the same two backends selected by
config, and the same ``S3_URL``-unset in-memory fallback convention.

**The content address is over the INPUTS, not the output.** The mesh store hashes
its output GLB because tessellation always runs and the key exists only to fetch
the result. Here the whole point is to SKIP composing on a repeat, so the key must
be derivable BEFORE composing: it is the SHA-256 of the canonical JSON of the whole
:class:`~py_kit.schemas.drawings.ComposeDrawingRequest`
(:func:`drawing_artifact_key`). That request carries EVERYTHING that changes the
composed bytes — the part feature prefix, the views + scale, the dimensions, the
sheet layout (size/orientation/title-block/placed views) AND the ``format`` — each
as a field, so any edit yields different JSON, a different key, a cache miss, and a
recompose (never a stale artifact). Compose is a pure, byte-deterministic function
of that request (RESEARCH §9), so the same request always addresses the same bytes.

**Cache, not state (RESEARCH §3).** Like the mesh store and the STEP parse cache,
this is a per-worker (or shared-S3) performance optimisation, never a correctness
dependency: a miss (cold worker, eviction, S3 unset) simply recomposes the SAME
bytes. So — unlike the mesh store — the in-process LRU needs **no single-worker
guard**: the compose route both computes and caches within ONE request, and a
cross-worker miss just recomposes rather than 404-ing. Both backends are selected
via :func:`configure_drawing_artifact_store` at startup and are tenant-free (the
key is the content address only, RESEARCH §5).

**Two backends (mirroring the mesh store, drawing-export.md §8.3):**

- :class:`~geometry.s3_store.S3DrawingArtifactStore` — the shared object-storage
  backend, installed when ``S3_URL`` is set: multi-worker/replica share one cache.
- :class:`DrawingArtifactStore` (this module) — a bounded in-process LRU, the
  fallback when ``S3_URL`` is unset (``just dev`` / tests without MinIO).
"""

import hashlib
import threading
from collections import OrderedDict
from typing import Protocol

from py_kit.schemas.drawings import ComposeDrawingRequest

#: Max cached artifacts. Bounds worst-case memory at capacity x largest sheet;
#: a working session touches a handful of drawings, and a miss just recomposes.
DRAWING_ARTIFACT_STORE_CAPACITY = 64


def drawing_artifact_key(request: ComposeDrawingRequest) -> str:
    """The content address of a composed drawing artifact (``sha256:<hex>``).

    Hashes the canonical JSON of the WHOLE :class:`ComposeDrawingRequest`, so the
    key incorporates every input that changes the composed bytes — the feature
    prefix, views, scale, dimensions, the sheet layout (size/orientation/
    title-block/placed views) and the ``format`` — each a request field. A change
    to any of them yields different JSON and a different key (a miss → recompose),
    so a stale artifact is never served after an edit. ``model_dump_json`` is
    deterministic (fixed field order, stable float/UUID rendering), so the address
    is byte-stable in-process and across an interpreter restart — the same posture
    that makes compose itself byte-deterministic (RESEARCH §9).
    """
    payload = request.model_dump_json().encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class DrawingArtifactBackend(Protocol):
    """The put/get contract every drawing-artifact-store backend implements.

    Keyed by the INPUT content address (:func:`drawing_artifact_key`), unlike the
    mesh store whose ``put`` derives the key from output bytes: the whole point is
    to skip composing on a hit, so the caller holds the key before any bytes exist.
    ``is_shared`` reports cross-process visibility (S3 shared, in-process LRU not);
    it is informational here — no single-worker guard, since a miss just recomposes.
    """

    is_shared: bool

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes | None: ...


class DrawingArtifactStore:
    """Thread-safe bounded LRU of content-addressed composed-artifact bytes.

    In-process only (``is_shared`` is ``False``), the ``S3_URL``-unset fallback. A
    hit is never a correctness guarantee, so there is no cross-process backend and
    no startup guard — a cold/evicted key recomposes the SAME bytes.
    """

    #: Not visible across processes; a miss just recomposes, so no guard applies.
    is_shared = False

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, bytes] = OrderedDict()

    def put(self, key: str, data: bytes) -> None:
        """Cache *data* under content-address *key* (idempotent; evicts LRU at cap)."""
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
            else:
                self._entries[key] = data
                while len(self._entries) > self._capacity:
                    self._entries.popitem(last=False)

    def get(self, key: str) -> bytes | None:
        """The cached artifact bytes for *key*, or ``None`` (evicted/unknown)."""
        with self._lock:
            data = self._entries.get(key)
            if data is not None:
                self._entries.move_to_end(key)
            return data


#: Process-wide store shared by the compose route (writer + reader). Defaults to
#: the in-process LRU; :func:`configure_drawing_artifact_store` swaps in the
#: S3/MinIO backend at startup when ``S3_URL`` is set. The default keeps imports,
#: tests, and ``just dev`` (no MinIO) working with no config.
_active_store: DrawingArtifactBackend = DrawingArtifactStore(
    DRAWING_ARTIFACT_STORE_CAPACITY
)


def configure_drawing_artifact_store(
    s3_url: str | None,
    s3_bucket: str,
    *,
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
    s3_region: str = "us-east-1",
) -> DrawingArtifactBackend:
    """Select and install the process-wide drawing-artifact backend from config.

    When *s3_url* is set, use the shared S3/MinIO store (multi-worker/replica share
    one cache); when ``None`` (dev without MinIO / tests), fall back to the
    in-process LRU. Mirrors :func:`geometry.mesh_store.configure_mesh_store`.
    Returns the installed backend for introspection. boto3 is imported lazily so
    the LRU-only path never pays for it.
    """
    global _active_store
    if s3_url:
        from geometry.s3_store import S3DrawingArtifactStore

        _active_store = S3DrawingArtifactStore(
            endpoint_url=s3_url,
            bucket=s3_bucket,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
            region=s3_region,
        )
    else:
        _active_store = DrawingArtifactStore(DRAWING_ARTIFACT_STORE_CAPACITY)
    return _active_store


def current_drawing_artifact_store() -> DrawingArtifactBackend:
    """The process-wide backend currently installed (introspection/tests)."""
    return _active_store


def store_drawing_artifact(key: str, data: bytes) -> None:
    """Cache composed artifact *data* under content-address *key* (compose writer)."""
    _active_store.put(key, data)


def fetch_drawing_artifact(key: str) -> bytes | None:
    """Resolve a content-address *key* to bytes; ``None`` = miss (recompose)."""
    return _active_store.get(key)
