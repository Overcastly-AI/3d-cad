"""S3/MinIO mesh-store tests — the §7.8 object-storage swap.

Exercises the S3 code path against **moto**'s in-process S3 HTTP server
(``ThreadedMotoServer``, Apache-2.0) so the store's real boto3 put/get travels a
genuine HTTP round-trip against a MinIO-shaped endpoint (path-style addressing):
put/get round-trip, content-address correctness, miss→None, idempotent put, the
content-addressed (tenant-free) key scheme, and the config-driven backend
selection + single-worker-guard lift.

**What is NOT proven here (CI-gated).** moto runs in this one process, so it
cannot prove the *cross-process* property the swap exists for: an evaluate on
one worker/replica and a fetch on another see one shared store. That real-MinIO
2-worker/2-replica evaluate→fetch smoke needs a live MinIO + docker daemon
(unavailable in this sandbox) and is gated in CI — see
``test_real_minio_cross_process_smoke_is_ci_gated`` below, docs/design/
feature-tree.md §7.8, and docs/GEOMETRY-QA.md.
"""

# boto3's client is dynamically generated and ships no stubs; suppress the
# untyped-member noise for this test module rather than casting every SDK call.
# reportPrivateUsage: this test deliberately pins the internal _object_key
# (the content-addressed, tenant-free S3 key scheme).
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingTypeStubs=false, reportPrivateUsage=false

from collections.abc import Iterator

import boto3
import pytest
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


# --- CI-gated acceptance (documented, not runnable here) --------------------


@pytest.mark.skip(
    reason=(
        "Real-MinIO cross-process 2-worker/2-replica evaluate->fetch smoke is "
        "CI-gated: it needs a live MinIO + docker daemon, unavailable in this "
        "sandbox. moto proves the S3 put/get + content-address code path "
        "in-process; the cross-process topology (the whole point of the swap) is "
        "verified in CI. See docs/design/feature-tree.md §7.8 and "
        "docs/GEOMETRY-QA.md."
    )
)
def test_real_minio_cross_process_smoke_is_ci_gated() -> None:  # pragma: no cover
    # Acceptance shape (run in CI against a real MinIO):
    #   1. Boot 2 geometry replicas behind one MinIO bucket (S3_URL set).
    #   2. POST /evaluate to replica A -> obtain mesh_glb_id.
    #   3. GET /meshes/{mesh_glb_id} from replica B -> 200 + identical bytes.
    # moto cannot reproduce (2)->(3) crossing a process boundary in-process.
    raise AssertionError("CI-only; see skip reason.")
