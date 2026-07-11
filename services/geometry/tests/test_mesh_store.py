"""Mesh store unit tests — the interim §7.8 content-addressed LRU.

The API-level behavior (fetchable id, 404 on miss, content addressing) is
covered in ``test_extrude.py``; this file pins the store's own contract:
idempotent puts, LRU eviction at capacity, and recency updates.
"""

from geometry.mesh_store import MeshStore, mesh_glb_key


def test_put_is_idempotent_and_content_addressed() -> None:
    store = MeshStore(capacity=4)
    key_a = store.put(b"glTF-payload-a")
    key_b = store.put(b"glTF-payload-a")

    assert key_a == key_b == mesh_glb_key(b"glTF-payload-a")
    assert key_a.startswith("sha256:")
    assert store.get(key_a) == b"glTF-payload-a"


def test_get_miss_returns_none() -> None:
    store = MeshStore(capacity=4)
    assert store.get("sha256:" + "0" * 64) is None


def test_eviction_is_least_recently_used() -> None:
    store = MeshStore(capacity=2)
    key_a = store.put(b"a")
    key_b = store.put(b"b")
    assert store.get(key_a) is not None  # touch a → b becomes LRU
    key_c = store.put(b"c")

    assert store.get(key_a) == b"a"
    assert store.get(key_b) is None  # evicted
    assert store.get(key_c) == b"c"
