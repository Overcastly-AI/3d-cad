# pyright: reportMissingTypeStubs=false
"""S3/MinIO-backed content-addressed GLB store — the §7.8 object-storage swap.

This is the **shared** mesh-store backend that retires the in-process LRU's
single-worker limitation (engineering audit F1/F6): put/get land in object
storage keyed by the SAME ``sha256:<hex>`` content address, so the evaluate
writer and the ``GET /api/v1/meshes/{id}`` reader see one store regardless of
which worker or replica serves each request. The DTO contract
(``EvaluateTreeResult.mesh_glb_id``) and the key format are unchanged — only
put/get move off-process (design §7.8).

**Tenancy (RESEARCH §5).** The derived mesh is a *pure function of the feature
tree* and is content-addressed + auth-gated but **not** tenant-scoped: the
object key is the content address only (``meshes/sha256/<hex>.glb``), with no
owner/tenant component. Knowing the key requires having produced byte-identical
geometry, which is the dedup contract. Do NOT reuse this scheme for authored
source bytes, whose existence/bytes are tenant-sensitive.

**Idempotent put / lifecycle.** Content addresses are never overwritten with
different bytes (same content → same key → same bytes), so ``put`` is idempotent
by construction. A retention/GC policy for orphaned artifacts is out of scope
here (design §7.8/§9-open-questions): v1 accepts unbounded growth.

boto3/botocore are Apache-2.0 (license-clean, no GPL); this module is the only
place they are imported, and only when ``S3_URL`` is configured.
"""

import re
from typing import Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from geometry.mesh_store import mesh_glb_key

#: MIME type of the stored artifacts (glTF binary), set on every object so a
#: presigned/streamed read carries the right content type.
_GLB_CONTENT_TYPE = "model/gltf-binary"

#: Object-key prefix for content-addressed meshes. No tenant/owner segment: the
#: key is the content address, per RESEARCH §5.
_KEY_PREFIX = "meshes/sha256/"

#: A well-formed ``mesh_glb_id`` is exactly ``sha256:`` + 64 lowercase hex.
_MESH_ID_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class _S3Body(Protocol):
    def read(self) -> bytes: ...


class _GetObjectOutput(Protocol):
    def __getitem__(self, key: str) -> _S3Body: ...


class _S3Client(Protocol):
    """The minimal, typed slice of the boto3 S3 client this store uses.

    Casting the (untyped) boto3 client to this Protocol keeps the store
    strict-pyright-clean without pulling boto3-stubs into the runtime deps.
    """

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> object: ...

    def get_object(self, *, Bucket: str, Key: str) -> _GetObjectOutput: ...


def _object_key(mesh_glb_id: str) -> str | None:
    """Map a ``mesh_glb_id`` to its S3 object key, or ``None`` if malformed.

    A malformed id (client-supplied on the fetch path) can never address a real
    artifact, so it resolves to a miss (honest 404) rather than a garbage key.
    """
    match = _MESH_ID_RE.match(mesh_glb_id)
    if match is None:
        return None
    return f"{_KEY_PREFIX}{match.group(1)}.glb"


class S3MeshStore:
    """Content-addressed GLB store backed by S3/MinIO (shared across processes).

    ``is_shared`` is ``True`` so :func:`geometry.main.build_app` lifts the
    single-worker guard for this backend — a shared store is exactly what makes
    multi-worker/replica geometry correct.
    """

    #: This backend is process-shared, so multi-worker/replica is safe (the
    #: build_app guard checks this attribute before enforcing single-worker).
    is_shared = True

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        # Path-style addressing: MinIO (and many S3-compatibles) don't do
        # virtual-host buckets by default. Deterministic, no DNS surprises.
        self._client = cast(
            _S3Client,
            boto3.client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                config=Config(s3={"addressing_style": "path"}),
            ),
        )

    def put(self, glb: bytes) -> str:
        """Store *glb* and return its content-addressed key (idempotent).

        The key is a pure content address, so re-putting identical bytes writes
        the same object — never an overwrite with different content.
        """
        key = mesh_glb_key(glb)
        object_key = _object_key(key)
        # ``key`` comes from mesh_glb_key, so it is always well-formed; assert to
        # satisfy the type-narrowing (object_key is str | None).
        assert object_key is not None
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=glb,
            ContentType=_GLB_CONTENT_TYPE,
        )
        return key

    def get(self, mesh_glb_id: str) -> bytes | None:
        """Resolve *mesh_glb_id* to GLB bytes, or ``None`` (unknown/malformed).

        A miss is the honest 404 — never a wrong mesh. A genuinely absent key
        (``NoSuchKey``/404) returns ``None``; any other S3 error propagates.
        """
        object_key = _object_key(mesh_glb_id)
        if object_key is None:
            return None
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise
        return response["Body"].read()


def _is_not_found(exc: ClientError) -> bool:
    """True when a boto3 ``ClientError`` means the object simply isn't there."""
    error = cast("dict[str, object]", getattr(exc, "response", {})).get("Error", {})
    code = cast("dict[str, object]", error).get("Code")
    return code in ("NoSuchKey", "NoSuchBucket", "404")
