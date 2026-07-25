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

#: Object-key prefix for content-addressed composed drawing artifacts (DE-4,
#: drawing-export.md §8.3). Same no-tenant content-address scheme as the mesh
#: prefix — the key is the SHA-256 of the compose inputs (the
#: ``ComposeDrawingRequest`` including its ``format``), so identical drawings dedup
#: and any edit misses. The drawing twin of the mesh store, sharing this seam.
_DRAWING_KEY_PREFIX = "drawings/sha256/"

#: Composed drawing artifacts are stored opaque (svg/pdf/dxf bytes): the FORMAT is
#: already folded into the content-address key, and the compose route re-labels the
#: response media type per format on serve, so the object's stored type is generic
#: metadata only (never read back to label the response).
_ARTIFACT_CONTENT_TYPE = "application/octet-stream"

#: A well-formed content id is exactly ``sha256:`` + 64 lowercase hex. Shared by
#: the mesh and drawing-artifact stores — both are content-addressed identically.
_SHA256_ID_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


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


def _content_object_key(content_id: str, *, prefix: str, ext: str) -> str | None:
    """Map a ``sha256:<hex>`` content id to its S3 object key, or ``None`` if malformed.

    The one content-address→key mapping both stores share: a malformed id can
    never address a real artifact, so it resolves to a miss rather than a garbage
    key. The ``prefix`` and ``ext`` name the artifact class (``meshes/…``.glb vs
    ``drawings/…``.bin); the hex digest is the tenant-free address (RESEARCH §5).
    """
    match = _SHA256_ID_RE.match(content_id)
    if match is None:
        return None
    return f"{prefix}{match.group(1)}.{ext}"


def _object_key(mesh_glb_id: str) -> str | None:
    """Map a ``mesh_glb_id`` to its S3 object key, or ``None`` if malformed.

    A malformed id (client-supplied on the fetch path) can never address a real
    artifact, so it resolves to a miss (honest 404) rather than a garbage key.
    """
    return _content_object_key(mesh_glb_id, prefix=_KEY_PREFIX, ext="glb")


def _build_s3_client(
    *,
    endpoint_url: str,
    access_key_id: str | None,
    secret_access_key: str | None,
    region: str,
) -> _S3Client:
    """Construct the path-style boto3 S3 client both content-addressed stores share.

    Path-style addressing: MinIO (and many S3-compatibles) don't do virtual-host
    buckets by default. Deterministic, no DNS surprises.
    """
    return cast(
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


def _get_object_or_none(
    client: _S3Client, bucket: str, object_key: str
) -> bytes | None:
    """GET an object's bytes, or ``None`` on a genuine ``NoSuchKey`` miss.

    A miss is the honest absence — never wrong bytes. Any other S3 error (a
    missing bucket, auth/transport) is a fault, NOT an absence, and propagates
    rather than masquerading as a miss (:func:`_is_not_found`, audit F6).
    """
    try:
        response = client.get_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        if _is_not_found(exc):
            return None
        raise
    return response["Body"].read()


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
        self._client = _build_s3_client(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
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
        return _get_object_or_none(self._client, self._bucket, object_key)


class S3DrawingArtifactStore:
    """Content-addressed composed-drawing-artifact store backed by S3/MinIO (DE-4).

    The drawing twin of :class:`S3MeshStore` on the SAME object-storage seam
    (drawing-export.md §8.3): a SHARED backend, so a compose on one worker/replica
    and a repeat export on another see one cache. ``is_shared`` is ``True``.

    The one seam difference: ``put`` takes the content-address KEY explicitly (the
    SHA-256 of the compose inputs, :func:`geometry.drawing_store.drawing_artifact_key`,
    computed BEFORE composing so a hit skips the recompose) rather than deriving it
    from the output bytes as the mesh store does. The artifact bytes are stored
    opaque — the ``format`` is already folded into the key and the compose route
    re-labels the response media type on serve.
    """

    #: Process-shared, so multi-worker/replica shares one cache — a miss anywhere
    #: simply recomposes (a cache, never correctness; RESEARCH §3).
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
        self._client = _build_s3_client(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
        )

    def put(self, key: str, data: bytes) -> None:
        """Store composed artifact *data* under content-address *key* (idempotent).

        *key* is a pure content address (``drawing_artifact_key``), so re-putting an
        unchanged drawing writes the same object — never an overwrite with different
        bytes.
        """
        object_key = _content_object_key(key, prefix=_DRAWING_KEY_PREFIX, ext="bin")
        # ``key`` comes from drawing_artifact_key, so it is always well-formed.
        assert object_key is not None
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=_ARTIFACT_CONTENT_TYPE,
        )

    def get(self, key: str) -> bytes | None:
        """The stored artifact for *key*, or ``None`` (unknown/malformed → miss)."""
        object_key = _content_object_key(key, prefix=_DRAWING_KEY_PREFIX, ext="bin")
        if object_key is None:
            return None
        return _get_object_or_none(self._client, self._bucket, object_key)


def _is_not_found(exc: ClientError) -> bool:
    """True when a boto3 ``ClientError`` means the OBJECT simply isn't there.

    Match ONLY ``NoSuchKey`` — a genuinely absent mesh, the honest 404. A
    missing/misnamed BUCKET (``NoSuchBucket``) or any auth/transport error is a
    misconfiguration or outage, NOT a mesh miss, and must propagate rather than
    masquerade as a 404 that hides the fault (code review, audit F6). The write
    path never catches ``NoSuchBucket``, so a fully-absent bucket already fails
    loud at the writer before any id is handed out.
    """
    error = cast("dict[str, object]", getattr(exc, "response", {})).get("Error", {})
    code = cast("dict[str, object]", error).get("Code")
    return code == "NoSuchKey"
