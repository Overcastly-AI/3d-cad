"""Content-addressed library-thumbnail cache (LIBRARY-THUMBNAILS).

The same seam as the composed-drawing store (:mod:`geometry.drawing_store`), and
for the same reason: the key is the SHA-256 of the render INPUTS, so a hit skips
the evaluate + rasterise entirely. The inputs are the document kind, the
:data:`~geometry.thumbnail.RENDERER_VERSION` and the canonical JSON of the
evaluation request documents composed from the current tree — which is what
"render once per tree version" means here, made stronger: a part edited and
then undone hashes back to the picture it already has, and an assembly whose
child part changed hashes differently even though the assembly's own version
did not move.

Cache, not state (RESEARCH §3): the S3/MinIO backend is shared across workers
when ``S3_URL`` is set; otherwise a bounded in-process LRU. A miss re-renders the
same bytes. Failures are never cached — a failed part has no picture.
"""

import hashlib

from pydantic import BaseModel

from geometry.drawing_store import DrawingArtifactBackend, DrawingArtifactStore
from geometry.thumbnail import RENDERER_VERSION

#: Max cached thumbnails in the in-process fallback. A PNG is ~5-30 KB, so even
#: a full cache is a few megabytes.
THUMBNAIL_STORE_CAPACITY = 512


def thumbnail_key(kind: str, request: BaseModel) -> str:
    """The content address (``sha256:<hex>``) of one document's thumbnail inputs."""
    digest = hashlib.sha256()
    digest.update(f"loft-thumbnail/{RENDERER_VERSION}/{kind}\n".encode())
    digest.update(request.model_dump_json().encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


_active_store: DrawingArtifactBackend = DrawingArtifactStore(THUMBNAIL_STORE_CAPACITY)


def configure_thumbnail_store(
    s3_url: str | None,
    s3_bucket: str,
    *,
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
    s3_region: str = "us-east-1",
) -> DrawingArtifactBackend:
    """Install the shared S3 backend when *s3_url* is set, else the in-process LRU."""
    global _active_store
    if s3_url:
        from geometry.s3_store import THUMBNAIL_KEY_PREFIX, S3DrawingArtifactStore

        _active_store = S3DrawingArtifactStore(
            endpoint_url=s3_url,
            bucket=s3_bucket,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
            region=s3_region,
            prefix=THUMBNAIL_KEY_PREFIX,
        )
    else:
        _active_store = DrawingArtifactStore(THUMBNAIL_STORE_CAPACITY)
    return _active_store


def store_thumbnail(key: str, png: bytes) -> None:
    """Cache a rendered thumbnail under its input content address."""
    _active_store.put(key, png)


def fetch_thumbnail(key: str) -> bytes | None:
    """The cached thumbnail for *key*, or ``None`` (render it)."""
    return _active_store.get(key)
