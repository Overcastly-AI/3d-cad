"""Content-addressed GLB artifact store — the interim §7.8 delivery seam.

Implements the feature-tree design's ``mesh_glb_id`` semantics (§4.4:
content-addressed, never overwritten) with an **in-process bounded LRU**
instead of object storage, per the documented interim decision in
docs/design/feature-tree.md §7.8: this container runs no MinIO, and the
evaluate flow is sync-HTTP like the tessellate proxy. Keys are pure content
addresses (``sha256:<hex digest of the GLB bytes>``) so the DTO contract is
already the object-storage contract — the compose/queue successor swaps this
module's put/get for MinIO writes and presigned/streamed reads without
touching ``EvaluateTreeResult`` or any caller.

The store is a **cache, not state** (geometry stays stateless, RESEARCH §3):
evaluation results are pure functions of the request (§4.4), so a miss after
eviction or a worker restart is answered by re-evaluating the tree — the API
surfaces it as an honest 404, never a wrong mesh. Content addressing also
makes responses byte-deterministic: the same tree yields the same GLB and
therefore the same ``mesh_glb_id``.

Because the store lives in one process, this interim is only correct on a
**single worker**. :func:`assert_single_worker_mesh_store` fails the service
loud at startup on a multi-worker config (``WEB_CONCURRENCY > 1``) rather than
letting cross-worker fetches 404 intermittently (engineering audit F1). That
guard retires when the MinIO swap lands.
"""

import hashlib
import threading
from collections import OrderedDict

#: Max cached artifacts. Bounds worst-case memory at capacity x largest GLB;
#: evaluate→fetch round-trips are near-adjacent in time, so a small window
#: is enough until object storage lands (§7.8 successor).
MESH_STORE_CAPACITY = 64


def mesh_glb_key(glb: bytes) -> str:
    """The content address of a GLB artifact (``sha256:<hex>``)."""
    return f"sha256:{hashlib.sha256(glb).hexdigest()}"


class MeshStore:
    """Thread-safe bounded LRU of content-addressed GLB payloads."""

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

    Until the MinIO-backed content-addressed swap lands (design §7.8, the
    forward goal), we turn that silent 404 into a **loud startup failure**:
    single-worker is the only safe geometry topology. Horizontal scale must wait
    for the shared object store, not fan out to in-process workers.

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


#: Process-wide store shared by the evaluate flow (writer) and the mesh
#: fetch endpoint (reader).
_STORE = MeshStore(MESH_STORE_CAPACITY)


def store_mesh_glb(glb: bytes) -> str:
    """Store a tessellated body; returns ``EvaluateTreeResult.mesh_glb_id``."""
    return _STORE.put(glb)


def fetch_mesh_glb(mesh_glb_id: str) -> bytes | None:
    """Resolve a ``mesh_glb_id`` to GLB bytes; ``None`` = evicted/unknown."""
    return _STORE.get(mesh_glb_id)
