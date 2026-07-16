"""S3/MinIO mesh-store tests — the §7.8 object-storage swap.

Exercises the S3 code path against **moto**'s in-process S3 HTTP server
(``ThreadedMotoServer``, Apache-2.0) so the store's real boto3 put/get travels a
genuine HTTP round-trip against a MinIO-shaped endpoint (path-style addressing):
put/get round-trip, content-address correctness, miss→None, idempotent put, the
content-addressed (tenant-free) key scheme, and the config-driven backend
selection + single-worker-guard lift.

**The cross-process property (CI-verified).** moto runs in this one process, so
it cannot prove the *cross-process* property the swap exists for: an evaluate on
one worker/replica and a fetch on another see one shared store. That real-MinIO
evaluate→fetch smoke needs a live MinIO + docker daemon (unavailable in this
sandbox), so it is gated on ``LOFT_MINIO_SMOKE`` and runs in the dedicated
``geometry-minio-smoke`` CI job (``.github/workflows/ci.yml``), which boots MinIO
and provisions the mesh bucket. Under the default (no-MinIO) ``uv run pytest`` it
skips cleanly. See ``test_real_minio_cross_process_smoke_is_ci_gated`` below,
docs/design/feature-tree.md §7.8, and docs/GEOMETRY-QA.md.
"""

# boto3's client is dynamically generated and ships no stubs; suppress the
# untyped-member noise for this test module rather than casting every SDK call.
# reportPrivateUsage: this test deliberately pins the internal _object_key
# (the content-addressed, tenant-free S3 key scheme).
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingTypeStubs=false, reportPrivateUsage=false

import os
import subprocess
import sys
from collections.abc import Iterator

import boto3
import pytest
from botocore.exceptions import ClientError
from geometry.mesh_store import (
    MeshStore,
    configure_mesh_store,
    current_mesh_store,
    fetch_mesh_glb,
    mesh_glb_key,
    store_mesh_glb,
)
from geometry.s3_store import S3MeshStore, _object_key
from moto.server import ThreadedMotoServer

#: A syntactically valid endpoint for selection tests that never make a call
#: (constructing a boto3 client opens no connection).
_ENDPOINT = "http://s3.local:9000"
_BUCKET = "loft-test"
_ACCESS_KEY = "testing"
_SECRET_KEY = "testing"


def _store(endpoint_url: str = _ENDPOINT) -> S3MeshStore:
    return S3MeshStore(
        endpoint_url=endpoint_url,
        bucket=_BUCKET,
        access_key_id=_ACCESS_KEY,
        secret_access_key=_SECRET_KEY,
    )


@pytest.fixture(autouse=True)
def _restore_active_store() -> Iterator[None]:
    """Reset to the default in-process LRU after each test so no S3 backend leaks
    into other modules (the store is a cache, so a fresh LRU is equivalent)."""
    yield
    configure_mesh_store(None, _BUCKET)


@pytest.fixture(scope="module")
def s3() -> Iterator[str]:
    """An in-process S3 HTTP server (moto) with the mesh bucket provisioned.

    Yields the endpoint URL. A real HTTP S3 endpoint (path-style, MinIO-shaped)
    so the store's boto3 put/get is genuinely exercised end-to-end.
    """
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    host, port = server.get_host_and_port()
    endpoint = f"http://{host}:{port}"
    boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=_ACCESS_KEY,
        aws_secret_access_key=_SECRET_KEY,
    ).create_bucket(Bucket=_BUCKET)
    yield endpoint
    server.stop()


# --- round-trip + content addressing ---------------------------------------


def test_put_fetch_roundtrip_returns_identical_bytes(s3: str) -> None:
    store = _store(s3)
    glb = b"glTF-binary-payload-\x00\x01\x02"

    key = store.put(glb)

    assert key == mesh_glb_key(glb)
    assert key.startswith("sha256:")
    assert store.get(key) == glb  # byte-identical round-trip through S3


def test_content_address_is_a_pure_function_of_bytes(s3: str) -> None:
    store = _store(s3)
    key_a1 = store.put(b"body-a")
    key_a2 = store.put(b"body-a")  # identical bytes → identical key
    key_b = store.put(b"body-b")

    assert key_a1 == key_a2 == mesh_glb_key(b"body-a")
    assert key_b != key_a1
    assert store.get(key_a1) == b"body-a"
    assert store.get(key_b) == b"body-b"


def test_get_miss_returns_none_not_a_wrong_mesh(s3: str) -> None:
    store = _store(s3)
    # Well-formed but never-stored id → honest miss.
    assert store.get("sha256:" + "0" * 64) is None


def test_get_on_missing_bucket_propagates_not_masquerades_as_miss(s3: str) -> None:
    """A missing/misnamed bucket is a config fault or outage, NOT a mesh miss —
    it must PROPAGATE (surface the fault) rather than return None and masquerade
    as an honest 404 (audit F6 code review). Only ``NoSuchKey`` is a miss."""
    misconfigured = S3MeshStore(
        endpoint_url=s3,
        bucket="loft-bucket-never-created",  # never provisioned on the moto server
        access_key_id=_ACCESS_KEY,
        secret_access_key=_SECRET_KEY,
    )
    with pytest.raises(ClientError):
        misconfigured.get("sha256:" + "0" * 64)


@pytest.mark.parametrize("bad_id", ["", "not-a-hash", "sha256:xyz", "md5:" + "a" * 32])
def test_get_malformed_id_returns_none(s3: str, bad_id: str) -> None:
    # A malformed id can never address a real artifact → miss, never a bad key.
    assert _store(s3).get(bad_id) is None


def test_put_is_idempotent(s3: str) -> None:
    store = _store(s3)
    glb = b"idempotent-body"
    key_first = store.put(glb)
    key_second = store.put(glb)  # re-put: same content address, same bytes

    assert key_first == key_second
    assert store.get(key_first) == glb


# --- tenancy: content-addressed key, no tenant segment (RESEARCH §5) --------


def test_object_key_is_content_addressed_with_no_tenant_segment() -> None:
    hexd = "a" * 64
    assert _object_key(f"sha256:{hexd}") == f"meshes/sha256/{hexd}.glb"


@pytest.mark.parametrize("bad_id", ["", "sha256:short", "sha256:" + "A" * 64, "x:y"])
def test_object_key_rejects_malformed_ids(bad_id: str) -> None:
    # Uppercase hex is not the canonical lowercase digest → rejected as a miss.
    assert _object_key(bad_id) is None


# --- config-driven backend selection + guard lift ---------------------------


def test_configure_selects_lru_when_s3_unset() -> None:
    backend = configure_mesh_store(None, _BUCKET)

    assert isinstance(backend, MeshStore)
    assert backend.is_shared is False  # unshared → single-worker guard applies
    assert current_mesh_store() is backend


def test_configure_selects_s3_when_s3_configured() -> None:
    backend = configure_mesh_store(
        _ENDPOINT,
        _BUCKET,
        s3_access_key_id=_ACCESS_KEY,
        s3_secret_access_key=_SECRET_KEY,
    )

    assert isinstance(backend, S3MeshStore)
    assert backend.is_shared is True  # shared → build_app lifts the guard
    assert current_mesh_store() is backend


def test_module_functions_route_through_configured_s3_backend(s3: str) -> None:
    configure_mesh_store(
        s3,
        _BUCKET,
        s3_access_key_id=_ACCESS_KEY,
        s3_secret_access_key=_SECRET_KEY,
    )
    glb = b"module-level-glb-payload"

    key = store_mesh_glb(glb)  # evaluate-writer path
    assert fetch_mesh_glb(key) == glb  # fetch-reader path, same shared store


# --- CI-gated acceptance: real-MinIO cross-process smoke --------------------

#: Truthy only in the ``geometry-minio-smoke`` CI job, which boots a real MinIO
#: and points S3_URL/S3_BUCKET/creds at it. Unset everywhere else (the default
#: ``uv run pytest``), so this smoke skips cleanly without a live object store.
_MINIO_SMOKE = os.environ.get("LOFT_MINIO_SMOKE")

#: The **reader** half (process B), run as a genuinely separate OS process. It
#: builds its OWN store instance (fresh boto3 client, no shared in-memory state
#: with the writer) via the real fetch-reader seam and streams the fetched GLB
#: bytes to stdout — or exits non-zero on a miss. Kept as a source string so the
#: child interpreter runs it with ``python -c`` in the same venv (geometry is
#: importable via ``sys.executable``).
_READER_SCRIPT = """
import os
import sys

from geometry.mesh_store import configure_mesh_store, fetch_mesh_glb

configure_mesh_store(
    os.environ["S3_URL"],
    os.environ["S3_BUCKET"],
    s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
    s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
    s3_region=os.environ.get("S3_REGION", "us-east-1"),
)
glb = fetch_mesh_glb(sys.argv[1])
if glb is None:
    sys.stderr.write("cross-process MISS: %s\\n" % sys.argv[1])
    raise SystemExit(3)
sys.stdout.buffer.write(glb)
"""


@pytest.mark.skipif(
    not _MINIO_SMOKE,
    reason=(
        "Real-MinIO cross-process evaluate->fetch smoke: set LOFT_MINIO_SMOKE=1 "
        "with a live MinIO (S3_URL/S3_BUCKET/creds). Runs in the geometry-minio-"
        "smoke CI job (.github/workflows/ci.yml); skipped in the default no-MinIO "
        "suite. moto proves the S3 code path in-process; this job proves the "
        "cross-process topology the swap exists for. See "
        "docs/design/feature-tree.md §7.8 and docs/GEOMETRY-QA.md."
    ),
)
def test_real_minio_cross_process_smoke_is_ci_gated() -> None:
    """Evaluate-writer stores on one process; a SEPARATE process fetches and gets
    byte-identical bytes from the same MinIO — the multi-worker/replica property
    the in-process LRU could never provide (design §7.8, engineering audit F6).

    Process A (this pytest process): its own S3-backed store, via the real
    evaluate-writer seam (``store_mesh_glb``). Process B (a fresh ``subprocess``
    interpreter with its OWN boto3 client + store instance, no shared memory
    with A): fetches the returned id via the real fetch-reader seam. A 404/miss
    across that boundary would fail here — proving the store is genuinely shared.
    """
    endpoint = os.environ["S3_URL"]
    bucket = os.environ["S3_BUCKET"]

    # Process A: install the shared S3 backend and store via the writer path.
    # Unique bytes (random nonce) so the fetched object is provably written by
    # THIS run — not a content-addressed leftover from a prior CI run.
    configure_mesh_store(
        endpoint,
        bucket,
        s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
        s3_region=os.environ.get("S3_REGION", "us-east-1"),
    )
    glb = b"loft-minio-cross-process-smoke-" + os.urandom(32)
    mesh_id = store_mesh_glb(glb)
    assert mesh_id == mesh_glb_key(glb)

    # Process B: a real second OS process — fresh interpreter, fresh boto3
    # client/store, no shared in-memory state with A. This is what the
    # in-process LRU could never satisfy.
    reader = subprocess.run(
        [sys.executable, "-c", _READER_SCRIPT, mesh_id],
        capture_output=True,
        env=os.environ.copy(),
        timeout=60,
    )

    assert reader.returncode == 0, (
        f"cross-process reader failed (rc={reader.returncode}): "
        f"{reader.stderr.decode(errors='replace')}"
    )
    # Byte-identical fetch across the process boundary — no 404, no wrong mesh.
    assert reader.stdout == glb
