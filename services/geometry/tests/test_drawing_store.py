"""Content-addressed drawing-artifact store tests — DE-4 (drawing-export.md §8.3).

Three concerns, mirroring the mesh-store test split:

1. **The store seam** — the in-process LRU (``DrawingArtifactStore``) and the S3/MinIO
   backend (``S3DrawingArtifactStore``, exercised against moto's in-process S3),
   plus config-driven backend selection and the ``S3_URL``-unset in-memory fallback
   — the SAME conventions ``test_mesh_store.py`` / ``test_s3_store.py`` pin.
2. **The content address** — ``drawing_artifact_key`` incorporates everything that
   changes the composed bytes (the whole request incl. ``format``), so identical
   requests share a key and ANY edit (format, title-block, scale, …) misses.
3. **The endpoint** — ``POST /api/v1/drawing/compose`` composes on a cold cache
   (``X-Loft-Artifact-Cache: miss``) and serves a repeat export byte-identically
   from storage WITHOUT re-composing (``hit``); an edit misses and recomposes
   different bytes — never a stale artifact.
"""

# reportPrivateUsage: this module deliberately drives the config seam + a spy on
# the internal recompute path to prove a hit skips composition.
# pyright: reportPrivateUsage=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from geometry.api import ARTIFACT_CACHE_HEADER
from geometry.drawing_store import (
    DrawingArtifactStore,
    configure_drawing_artifact_store,
    current_drawing_artifact_store,
    drawing_artifact_key,
    fetch_drawing_artifact,
    store_drawing_artifact,
)
from geometry.main import app
from geometry.s3_store import S3DrawingArtifactStore
from moto.server import ThreadedMotoServer
from py_kit.schemas.drawings import ComposeDrawingRequest, ViewScale

_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_goldens"
_ENDPOINT = "http://s3.local:9000"
_BUCKET = "loft-test"
_ACCESS_KEY = "testing"
_SECRET_KEY = "testing"

client = TestClient(app)


def _golden_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _golden_payload() -> dict[str, Any]:
    return json.loads((_GOLDEN_DIR / "request.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh_store() -> Iterator[None]:
    """Start every test with a cold in-process LRU so hit/miss is deterministic and
    no S3 backend leaks between tests (the store is a cache — a fresh LRU is
    equivalent). Mirrors ``test_s3_store``'s ``_restore_active_store``."""
    configure_drawing_artifact_store(None, _BUCKET)
    yield
    configure_drawing_artifact_store(None, _BUCKET)


# --- the in-process LRU backend (the S3_URL-unset fallback) ----------------------


def test_put_get_roundtrip_is_keyed_by_content_address() -> None:
    store = DrawingArtifactStore(capacity=4)
    key = drawing_artifact_key(_golden_request())
    store.put(key, b"<svg>artifact</svg>")
    assert store.get(key) == b"<svg>artifact</svg>"


def test_put_is_idempotent() -> None:
    store = DrawingArtifactStore(capacity=4)
    store.put("sha256:" + "a" * 64, b"bytes-1")
    store.put("sha256:" + "a" * 64, b"bytes-1")  # re-put same content
    assert store.get("sha256:" + "a" * 64) == b"bytes-1"


def test_get_miss_returns_none() -> None:
    assert DrawingArtifactStore(capacity=4).get("sha256:" + "0" * 64) is None


def test_eviction_is_least_recently_used() -> None:
    store = DrawingArtifactStore(capacity=2)
    store.put("k-a", b"a")
    store.put("k-b", b"b")
    assert store.get("k-a") == b"a"  # touch a → b becomes LRU
    store.put("k-c", b"c")
    assert store.get("k-a") == b"a"
    assert store.get("k-b") is None  # evicted
    assert store.get("k-c") == b"c"


def test_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DrawingArtifactStore(capacity=0)


# --- the content address: what invalidates the cache ----------------------------


def test_key_is_a_deterministic_function_of_the_request() -> None:
    # Two independent parses of the SAME request JSON address the same artifact.
    assert drawing_artifact_key(_golden_request()) == drawing_artifact_key(
        _golden_request()
    )


def test_format_change_changes_the_key() -> None:
    svg = _golden_request().model_copy(update={"format": "svg"})
    pdf = _golden_request().model_copy(update={"format": "pdf"})
    assert drawing_artifact_key(svg) != drawing_artifact_key(pdf)


def test_title_block_change_changes_the_key() -> None:
    base = _golden_request()
    edited = base.model_copy(
        update={"layout": base.layout.model_copy(update={"title": "Edited Title"})}
    )
    assert drawing_artifact_key(base) != drawing_artifact_key(edited)


def test_scale_change_changes_the_key() -> None:
    # A non-layout, non-format input (an inherited evaluate field) still invalidates.
    base = _golden_request()
    rescaled = base.model_copy(update={"scale": ViewScale(numerator=1, denominator=2)})
    assert drawing_artifact_key(base) != drawing_artifact_key(rescaled)


# --- config-driven backend selection + fallback ---------------------------------


def test_configure_selects_lru_when_s3_unset() -> None:
    backend = configure_drawing_artifact_store(None, _BUCKET)
    assert isinstance(backend, DrawingArtifactStore)
    assert backend.is_shared is False
    assert current_drawing_artifact_store() is backend


def test_configure_selects_s3_when_s3_configured() -> None:
    backend = configure_drawing_artifact_store(
        _ENDPOINT,
        _BUCKET,
        s3_access_key_id=_ACCESS_KEY,
        s3_secret_access_key=_SECRET_KEY,
    )
    assert isinstance(backend, S3DrawingArtifactStore)
    assert backend.is_shared is True
    assert current_drawing_artifact_store() is backend


def test_module_functions_use_the_in_memory_fallback_when_s3_unset() -> None:
    # The S3_URL-unset dev path: store/fetch route through the LRU with no MinIO.
    configure_drawing_artifact_store(None, _BUCKET)
    key = drawing_artifact_key(_golden_request())
    store_drawing_artifact(key, b"fallback-bytes")
    assert fetch_drawing_artifact(key) == b"fallback-bytes"


# --- the S3/MinIO backend (moto) ------------------------------------------------


@pytest.fixture(scope="module")
def s3() -> Iterator[str]:
    """An in-process S3 HTTP server (moto) with the artifact bucket provisioned."""
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


def _s3_store(endpoint_url: str) -> S3DrawingArtifactStore:
    return S3DrawingArtifactStore(
        endpoint_url=endpoint_url,
        bucket=_BUCKET,
        access_key_id=_ACCESS_KEY,
        secret_access_key=_SECRET_KEY,
    )


def test_s3_put_fetch_roundtrip_returns_identical_bytes(s3: str) -> None:
    store = _s3_store(s3)
    key = drawing_artifact_key(_golden_request())
    payload = b"%PDF-artifact-\x00\x01\x02"
    store.put(key, payload)
    assert store.get(key) == payload  # byte-identical round-trip through S3


def test_s3_get_miss_returns_none(s3: str) -> None:
    # Well-formed but never-stored key → honest miss (recompose), never wrong bytes.
    assert _s3_store(s3).get("sha256:" + "0" * 64) is None


@pytest.mark.parametrize("bad_key", ["", "not-a-hash", "sha256:xyz", "md5:" + "a" * 32])
def test_s3_get_malformed_key_returns_none(s3: str, bad_key: str) -> None:
    assert _s3_store(s3).get(bad_key) is None


def test_s3_module_functions_route_through_configured_backend(s3: str) -> None:
    configure_drawing_artifact_store(
        s3, _BUCKET, s3_access_key_id=_ACCESS_KEY, s3_secret_access_key=_SECRET_KEY
    )
    key = drawing_artifact_key(_golden_request())
    store_drawing_artifact(key, b"shared-s3-artifact")  # compose writer
    assert fetch_drawing_artifact(key) == b"shared-s3-artifact"  # repeat reader


# --- the endpoint: hit / miss / no stale artifact -------------------------------


def test_repeat_export_is_a_cache_hit_serving_identical_bytes() -> None:
    payload = _golden_payload()
    first = client.post("/api/v1/drawing/compose", json=payload)
    assert first.status_code == 200
    assert first.headers[ARTIFACT_CACHE_HEADER] == "miss"

    second = client.post("/api/v1/drawing/compose", json=payload)
    assert second.status_code == 200
    assert second.headers[ARTIFACT_CACHE_HEADER] == "hit"  # served from storage
    assert second.content == first.content  # byte-identical, not a recompute


def test_cache_hit_does_not_recompose(monkeypatch: pytest.MonkeyPatch) -> None:
    """The airtight signal: the second export never calls the compose path.

    The spy sits on ``geometry.api.compose_drawing_evaluation`` — the evaluation
    seam ``_compose_sheet`` calls for BOTH the part and assembly branches (D4
    slice a), so a hit skipping it proves no re-projection of either kind."""
    from geometry.drawings import compose_drawing_evaluation as real

    calls = {"n": 0}

    def _spy(request: ComposeDrawingRequest) -> Any:
        calls["n"] += 1
        return real(request)

    monkeypatch.setattr("geometry.api.compose_drawing_evaluation", _spy)
    payload = _golden_payload()
    client.post("/api/v1/drawing/compose", json=payload)  # miss → composes
    client.post("/api/v1/drawing/compose", json=payload)  # hit → skips compose
    assert calls["n"] == 1


def test_title_edit_misses_cache_and_recomposes_different_bytes() -> None:
    payload = _golden_payload()
    first = client.post("/api/v1/drawing/compose", json=payload)
    assert first.headers[ARTIFACT_CACHE_HEADER] == "miss"

    edited = _golden_payload()
    edited["layout"]["title"] = "Edited Title — Not The Golden"
    resp = client.post("/api/v1/drawing/compose", json=edited)
    assert resp.headers[ARTIFACT_CACHE_HEADER] == "miss"  # NOT a stale hit
    assert resp.content != first.content  # recomposed, different bytes


def test_format_change_misses_cache_and_recomposes() -> None:
    svg = client.post(
        "/api/v1/drawing/compose", json={**_golden_payload(), "format": "svg"}
    )
    assert svg.headers[ARTIFACT_CACHE_HEADER] == "miss"
    pdf = client.post(
        "/api/v1/drawing/compose", json={**_golden_payload(), "format": "pdf"}
    )
    assert pdf.headers[ARTIFACT_CACHE_HEADER] == "miss"  # format is in the key
    assert pdf.content != svg.content
    assert pdf.content.startswith(b"%PDF-")
