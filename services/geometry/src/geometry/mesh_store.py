"""Content-addressed GLB artifact store — the §7.8 mesh-delivery seam.

Implements the feature-tree design's ``mesh_glb_id`` semantics (§4.4:
content-addressed, never overwritten). Keys are pure content addresses
(``sha256:<hex digest of the GLB bytes>``), so the DTO contract *is* the
object-storage contract and every backend shares one key format.

**Two backends, selected by config (design §7.8, engineering audit F1/F6):**

- :class:`S3MeshStore` (``geometry.s3_store``) — the shipped object-storage
  swap. When ``S3_URL`` is configured the evaluate writer and the
  ``GET /api/v1/meshes/{id}`` reader share one MinIO/S3 store, so multi-worker
  and multi-replica geometry are correct. The single-worker guard is **lifted**
  for this backend (:func:`build_app` checks ``is_shared``).
- :class:`MeshStore` (this module) — a bounded in-process LRU, the fallback
  when ``S3_URL`` is unset (``just dev`` / tests without MinIO). It lives in one
  process, so it is only correct on a **single worker**:
  :func:`assert_single_worker_mesh_store` fails the service loud at startup on
  ``WEB_CONCURRENCY > 1`` rather than letting cross-worker fetches 404
  intermittently.

The store is a **cache, not state** (geometry stays stateless, RESEARCH §3):
evaluation results are pure functions of the request (§4.4), so a miss after
eviction or a worker restart is answered by re-evaluating the tree — the API
surfaces it as an honest 404, never a wrong mesh. Content addressing also
makes responses byte-deterministic: the same tree yields the same GLB and
therefore the same ``mesh_glb_id``.

Both backends are selected via :func:`configure_mesh_store` at startup and are
tenant-free: the key is the content address only (RESEARCH §5).
"""

import hashlib
import threading
from collections import OrderedDict
from typing import Protocol

#: Max cached artifacts. Bounds worst-case memory at capacity x largest GLB;
#: evaluate→fetch round-trips are near-adjacent in time, so a small window
#: is enough until object storage lands (§7.8 successor).
MESH_STORE_CAPACITY = 64


def mesh_glb_key(glb: bytes) -> str:
    """The content address of a GLB artifact (``sha256:<hex>``)."""
    return f"sha256:{hashlib.sha256(glb).hexdigest()}"


class MeshStoreBackend(Protocol):
    """The put/get contract every mesh-store backend implements.

    ``is_shared`` reports whether the backend is visible across processes: the
    S3/MinIO store is shared (multi-worker/replica safe), the in-process LRU is
    not. :func:`geometry.main.build_app` reads it to decide whether to enforce
    the single-worker guard.
    """

    is_shared: bool

    def put(self, glb: bytes) -> str: ...

    def get(self, mesh_glb_id: str) -> bytes | None: ...


class MeshStore:
    """Thread-safe bounded LRU of content-addressed GLB payloads.

    In-process only, so ``is_shared`` is ``False``: correct on a single worker,
    guarded against multi-worker fan-out (:func:`assert_single_worker_mesh_store`).
    """

    #: Not visible across processes → the single-worker guard applies.
    is_shared = False

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, bytes] = OrderedDict()

    def put(self, glb: bytes) -> str:
        """Store *glb* and return its content-addressed key (idempotent)."""
        key = mesh_glb_key(glb)
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
            else:
                self._entries[key] = glb
                while len(self._entries) > self._capacity:
                    self._entries.popitem(last=False)
        return key

    def get(self, mesh_glb_id: str) -> bytes | None:
        """The stored GLB for *mesh_glb_id*, or ``None`` (evicted/unknown)."""
        with self._lock:
            glb = self._entries.get(mesh_glb_id)
            if glb is not None:
                self._entries.move_to_end(mesh_glb_id)
            return glb


class MeshStoreMultiWorkerError(RuntimeError):
    """Startup guard: a multi-worker/replica deploy would break this store.

    Raised when the geometry service is configured with more than one worker
    (``WEB_CONCURRENCY > 1``) while the mesh store is still the in-process LRU.
    See :func:`assert_single_worker_mesh_store` and design §7.8.
    """


def assert_single_worker_mesh_store(web_concurrency: int) -> None:
    """Refuse to start on a multi-worker config the mesh store can't serve.

    The mesh store (this module) is a **process-global** LRU: evaluate (writer)
    and ``GET /api/v1/meshes/{id}`` (reader) share memory only within one
    process. Under ``WEB_CONCURRENCY > 1`` those two calls land on independent
    worker processes with independent stores, so a fetch misses the writer's
    store ~(N-1)/N of the time and 404s a mesh that genuinely exists — a silent,
    intermittent correctness cliff on the "cloud-native/self-hostable" claim
    (engineering audit F1).

    This guard applies **only when the LRU is the active backend** — i.e.
    ``S3_URL`` is unset (dev without MinIO / tests). It turns that silent 404
    into a **loud startup failure**: with the in-process store, single-worker is
    the only safe geometry topology. When ``S3_URL`` is configured the shared
    :class:`~geometry.s3_store.S3MeshStore` backend is installed instead
    (:func:`configure_mesh_store`) and ``build_app`` **lifts** this guard — a
    shared object store is exactly what makes multi-worker/replica geometry
    correct (design §7.8, the object-storage swap; engineering audit F1/F6).

    ``WEB_CONCURRENCY`` is the canonical knob because uvicorn already reads it to
    default its worker count; it is therefore the single source of truth for how
    many geometry workers a process manager spawns. Replica-level fan-out
    (compose ``scale``/k8s ``replicas`` > 1) is the same hazard and is gated by
    the readiness note in the compose file until the swap lands.
    """
    if web_concurrency > 1:
        raise MeshStoreMultiWorkerError(
            f"WEB_CONCURRENCY={web_concurrency}: the geometry mesh store is an "
            "in-process LRU (geometry.mesh_store), so evaluate and fetch on "
            "different workers 404 the mesh ~(N-1)/N of the time. Run a single "
            "worker (WEB_CONCURRENCY=1, the default) until the MinIO-backed "
            "content-addressed swap lands. Scaling geometry needs replicas "
            "behind a shared object store, not in-process workers. "
            "See docs/design/feature-tree.md §7.8."
        )


#: Process-wide store shared by the evaluate flow (writer) and the mesh fetch
#: endpoint (reader). Defaults to the in-process LRU; :func:`configure_mesh_store`
#: swaps in the S3/MinIO backend at startup when ``S3_URL`` is set. The default
#: keeps imports, tests, and ``just dev`` (no MinIO) working with no config.
_active_store: MeshStoreBackend = MeshStore(MESH_STORE_CAPACITY)


def configure_mesh_store(
    s3_url: str | None,
    s3_bucket: str,
    *,
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
    s3_region: str = "us-east-1",
) -> MeshStoreBackend:
    """Select and install the process-wide mesh-store backend from config.

    When *s3_url* is set, use the shared S3/MinIO store (design §7.8 swap):
    multi-worker/replica geometry is correct because the store is shared, so the
    caller (``build_app``) lifts the single-worker guard for it. When *s3_url* is
    ``None`` (dev without MinIO / tests), fall back to the in-process LRU and
    keep the guard. Returns the installed backend so the caller can read
    ``is_shared`` for the guard decision.

    boto3 is imported lazily here so the LRU-only path never pays for it.
    """
    global _active_store
    if s3_url:
        from geometry.s3_store import S3MeshStore

        _active_store = S3MeshStore(
            endpoint_url=s3_url,
            bucket=s3_bucket,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
            region=s3_region,
        )
    else:
        _active_store = MeshStore(MESH_STORE_CAPACITY)
    return _active_store


def current_mesh_store() -> MeshStoreBackend:
    """The process-wide backend currently installed (introspection/tests)."""
    return _active_store


def store_mesh_glb(glb: bytes) -> str:
    """Store a tessellated body; returns ``EvaluateTreeResult.mesh_glb_id``."""
    return _active_store.put(glb)


def fetch_mesh_glb(mesh_glb_id: str) -> bytes | None:
    """Resolve a ``mesh_glb_id`` to GLB bytes; ``None`` = evicted/unknown."""
    return _active_store.get(mesh_glb_id)
