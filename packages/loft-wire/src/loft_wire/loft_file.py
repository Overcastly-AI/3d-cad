"""The ``.loft`` file: a part's tree as a data-only zip (docs/FILE-FORMAT.md).

What a ``.loft`` is, in one paragraph: a zip holding ``manifest.json`` (what the
file is and the sha256 of every other member), ``tree.json`` (the feature tree
— the only thing an import ever builds from), the part's named versions
(``versions/index.json`` plus one ``versions/<seq>.tree.json`` each, format 1.1),
``blobs/sha256-<hex>.step`` (an ``import`` feature's STEP text, moved out of the
tree so the tree stays a readable diff; shared by every tree that names it) and
an optional ``cache/body.step`` (the exported body, for tools that do not run
Loft). The cache is UNTRUSTED: an import never sends it to the
kernel; it rebuilds from ``tree.json`` and only compares the volume.

This module owns the whole format and nothing else: the models, the canonical
bytes (:func:`canonical_json`, :func:`pack_part`), the defensive reader
(:func:`read_loft`), the limits and the errors. It is pure standard library +
pydantic like the rest of ``loft_wire`` — the gateway packs and reads, documents
persists, and neither re-implements a byte of it.

**Canonical bytes.** The same part on the same build writes the same file:
JSON is ``sort_keys``, two-space indented, UTF-8, LF, with a trailing newline,
no NaN, and ``-0.0`` written as ``0.0``; zip members go in a fixed order, dated
1980-01-01, mode 0644, with no extra fields; JSON is STORED and STEP is DEFLATE
level 6. There is no export timestamp anywhere. A ``.loft`` in git therefore
diffs as its ``tree.json`` (the ``.gitattributes`` textconv recipe is in
docs/FILE-FORMAT.md).

**Reading untrusted bytes.** Everything is read in memory and nothing is ever
written to disk, so a hostile path cannot land anywhere; it is refused anyway.
Every member is matched against a whitelist, sizes are capped per member and in
total, a compression ratio over :data:`MAX_LOFT_COMPRESSION_RATIO` is a zip
bomb, and each member is read with ``read(cap + 1)`` so a header that lies about
its size cannot make the reader allocate more than the cap.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import re
import struct
import uuid
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from loft_wire.features import (
    MAX_INLINE_STEP_CHARS,
    MAX_TREE_FEATURES,
    FeatureName,
    JsonObject,
    document_slug,
)
from loft_wire.geometry import BoundingBox
from loft_wire.materials import MaterialAssignment
from loft_wire.parts import PartName, PartResponse
from loft_wire.units import LengthUnit
from loft_wire.versions import (
    MAX_PART_VERSIONS,
    VersionAuthor,
    VersionMessage,
    VersionName,
    VersionSeq,
)

# --- identity ---------------------------------------------------------------------

#: The ``format`` value every ``.loft`` manifest carries.
LOFT_FORMAT = "loft"

#: The format version this build WRITES, ``major.minor``. A reader refuses a
#: newer MAJOR (``loft_format_too_new``) and reads a newer MINOR, ignoring the
#: keys and members it does not know. 1.1 added ``versions/``; a 1.0 reader
#: skips it unread and imports the part without its versions.
LOFT_FORMAT_VERSION = "1.1"
LOFT_FORMAT_MAJOR = 1
LOFT_FORMAT_MINOR = 1

#: The file suffix and the media type the export route answers with.
LOFT_SUFFIX = ".loft"
LOFT_MEDIA_TYPE = "application/vnd.loft+zip"

#: Member paths. ``manifest.json`` is always first in the zip; the rest follow
#: in :func:`_member_order`.
MANIFEST_PATH = "manifest.json"
TREE_PATH = "tree.json"
BODY_STEP_PATH = "cache/body.step"
BLOB_DIR = "blobs/"
VERSIONS_INDEX_PATH = "versions/index.json"

#: How a tree names a blob in place of an import feature's inline STEP text.
BLOB_REF_PREFIX = "loft-blob:sha256:"

# --- limits (docs/FILE-FORMAT.md "Limits") ----------------------------------------

_MIB = 1024 * 1024

#: The whole upload, compressed. Read by the gateway WHILE the body streams.
MAX_LOFT_UPLOAD_BYTES = 64 * _MIB
#: Zip entries. Checked from the end-of-central-directory record BEFORE the
#: central directory is parsed, so a million-entry directory costs nothing.
MAX_LOFT_MEMBERS = 256
#: ``manifest.json``, uncompressed.
MAX_LOFT_MANIFEST_BYTES = 1 * _MIB
#: ``tree.json``, uncompressed.
MAX_LOFT_TREE_BYTES = 8 * _MIB
#: One ``blobs/*.step``: the same ceiling an inline import STEP has, because it
#: becomes exactly that.
MAX_LOFT_BLOB_BYTES = MAX_INLINE_STEP_CHARS
#: ``cache/body.step``, uncompressed.
MAX_LOFT_BODY_STEP_BYTES = 64 * _MIB
#: Named versions in one file: the same cap a part has in the database.
MAX_LOFT_VERSIONS = MAX_PART_VERSIONS
#: ``versions/index.json``, uncompressed. A full index of 100 entries with
#: 2000-character messages is about 250 KiB.
MAX_LOFT_VERSION_INDEX_BYTES = 1 * _MIB
#: One ``versions/<seq>.tree.json``: the same ceiling ``tree.json`` has.
MAX_LOFT_VERSION_TREE_BYTES = MAX_LOFT_TREE_BYTES
#: Every member together, uncompressed.
MAX_LOFT_TOTAL_BYTES = 256 * _MIB
#: Uncompressed : compressed above this is refused as a zip bomb. STEP text
#: deflates about 5-10:1; a bomb is in the thousands.
MAX_LOFT_COMPRESSION_RATIO = 100
#: The central directory, as its end record declares it. ``zipfile`` parses
#: exactly this many bytes, so capping it bounds the parse whatever the entry
#: count claims. 512 bytes an entry is four times the longest whitelisted
#: entry (46 + an 82-character blob path) and leaves room for extra fields.
MAX_LOFT_CENTRAL_DIRECTORY_BYTES = MAX_LOFT_MEMBERS * 512
#: Members smaller than this skip the ratio test: a few KiB of repetitive JSON
#: can legitimately exceed 100:1 and cannot hurt anyone.
LOFT_RATIO_FLOOR_BYTES = 1 * _MIB

#: The relative tolerance an import compares the rebuilt volume with the
#: manifest's at — the kernel's 1e-7 golden bound. Same build, same tree: the
#: two are bit-identical; a mismatch is a WARNING, never a refusal.
LOFT_VOLUME_REL_TOLERANCE = 1e-7

_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_ZIP_MODE = 0o100644 << 16
_DEFLATE_LEVEL = 6

_SHA256_RE = r"^[0-9a-f]{64}$"
_BLOB_PATH_RE = re.compile(r"^blobs/sha256-([0-9a-f]{64})\.step$")
_VERSION_TREE_RE = re.compile(r"^versions/([1-9][0-9]{0,8})\.tree\.json$")
_KNOWN_MEMBER_RE = re.compile(
    r"^(?:manifest\.json|tree\.json|cache/body\.step"
    r"|blobs/sha256-[0-9a-f]{64}\.step"
    r"|versions/index\.json|versions/[1-9][0-9]{0,8}\.tree\.json)$"
)
#: A member a NEWER minor version may add: a plain relative path. Skipped
#: unread, never refused, so a 1.1 file opens in a 1.0 Loft.
_FUTURE_MEMBER_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_BLOB_REF_RE = re.compile(r"^loft-blob:sha256:([0-9a-f]{64})$")

Sha256Hex = str

# --- errors -----------------------------------------------------------------------

LoftErrorCode = Literal[
    "loft_too_large",
    "loft_not_zip",
    "loft_zip_invalid",
    "loft_too_many_members",
    "loft_member_unsafe",
    "loft_member_duplicate",
    "loft_member_encrypted",
    "loft_member_compression",
    "loft_member_unknown",
    "loft_member_too_large",
    "loft_zip_bomb",
    "loft_member_missing",
    "loft_manifest_invalid",
    "loft_not_loft",
    "loft_format_too_new",
    "loft_kind_unsupported",
    "loft_tree_invalid",
    "loft_blob_corrupt",
    "loft_blob_missing",
    "loft_too_many_versions",
    "loft_versions_invalid",
]


class LoftFileError(ValueError):
    """A ``.loft`` this build refuses to read. The services render it as a 422.

    ``code`` is the machine-readable reason (:data:`LoftErrorCode`); ``details``
    names the member, the limit or the version involved.
    """

    def __init__(
        self,
        message: str,
        *,
        code: LoftErrorCode,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code: LoftErrorCode = code
        self.details: dict[str, Any] = details or {}


# --- models -----------------------------------------------------------------------


class LoftUnits(BaseModel):
    """The units every length in the file is stored in. Always millimetres."""

    storage: Literal["mm"] = "mm"


class LoftCacheProperties(BaseModel):
    """The exported body's mass properties, as the exporting build measured them."""

    volume_mm3: float = Field(allow_inf_nan=False)
    area_mm2: float = Field(allow_inf_nan=False)
    bbox: BoundingBox


class LoftCache(BaseModel):
    """What ``cache/body.step`` is and which tree it was built from. Untrusted."""

    step_sha256: Sha256Hex = Field(pattern=_SHA256_RE)
    built_from_tree_sha256: Sha256Hex = Field(pattern=_SHA256_RE)
    properties: LoftCacheProperties | None = None


class LoftManifest(BaseModel):
    """``manifest.json``: what the file is, and the sha256 of every other member.

    No export time, on purpose: the same part must write the same bytes.
    Unknown keys are ignored, so a newer MINOR version still reads.
    """

    model_config = ConfigDict(extra="ignore")

    format: Literal["loft"]
    format_version: str = Field(pattern=r"^\d+\.\d+$")
    loft_version: str = Field(min_length=1, max_length=64)
    kind: Literal["part"]
    document_id: uuid.UUID
    units: LoftUnits
    tree_sha256: Sha256Hex = Field(pattern=_SHA256_RE)
    members: dict[str, Sha256Hex] = Field(max_length=MAX_LOFT_MEMBERS)
    cache: LoftCache | None = None
    references: list[str] = Field(
        default_factory=list[str],
        max_length=0,
        description="Documents this one references. Always empty for a part; "
        "assemblies arrive in a later format step.",
    )


class LoftTreeFeature(BaseModel):
    """One feature in ``tree.json``, in tree order.

    ``params`` stays raw JSON here on purpose: the reader cannot upcast (that is
    the registry's job, in documents), and a params blob from an OLDER
    ``param_version`` would not validate against today's model.
    """

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    name: FeatureName
    type: str = Field(min_length=1, max_length=64)
    param_version: int = Field(ge=1)
    suppressed: bool = False
    params: JsonObject


class LoftTree(BaseModel):
    """``tree.json``: the part's whole parametric definition.

    Everything an import builds from, and nothing derivable: no
    ``order_index`` (the list order is the order), no dependency edges (an
    import re-derives them), no timestamps, no undo history.
    """

    model_config = ConfigDict(extra="ignore")

    name: PartName
    length_unit: LengthUnit = "mm"
    materials: MaterialAssignment | None = None
    rollback_feature_id: uuid.UUID | None = None
    features: list[LoftTreeFeature] = Field(max_length=MAX_TREE_FEATURES)


def _utc(value: datetime) -> datetime:
    """One spelling of a moment, so a re-pack writes the same bytes."""
    return value.astimezone(UTC)


#: A timezone-aware moment, held in UTC.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]


class LoftVersionEntry(BaseModel):
    """One line of ``versions/index.json``: a named version, without its tree.

    ``tree_sha256`` is the sha256 of ``versions/<seq>.tree.json`` as written.
    The author is a display name only, never an account id or an email.
    """

    model_config = ConfigDict(extra="ignore")

    seq: VersionSeq
    name: VersionName
    message: VersionMessage = ""
    author: VersionAuthor | None = None
    created_at: UtcDatetime
    tree_sha256: Sha256Hex = Field(pattern=_SHA256_RE)


class LoftVersionIndex(BaseModel):
    """``versions/index.json``: every named version, in ascending ``seq``."""

    model_config = ConfigDict(extra="ignore")

    versions: list[LoftVersionEntry] = Field(max_length=MAX_LOFT_VERSIONS)


class LoftVersion(BaseModel):
    """A named version with its tree: what documents stores and serves for an
    export, what an import hands documents, and what :func:`read_loft` returns.

    ``tree`` carries import STEP text inline, like every other in-memory tree.
    """

    seq: VersionSeq
    name: VersionName
    message: VersionMessage = ""
    author: VersionAuthor | None = None
    created_at: UtcDatetime
    tree: LoftTree


class LoftVersionList(BaseModel):
    """Documents -> gateway: a part's versions with their trees, ascending ``seq``."""

    versions: list[LoftVersion] = Field(max_length=MAX_LOFT_VERSIONS)


LoftWarningCode = Literal[
    "loft_tree_edited",
    "loft_cache_corrupt",
    "loft_volume_mismatch",
    "loft_rebuild_errors",
    "loft_verify_unavailable",
    "loft_version_edited",
]


class LoftWarning(BaseModel):
    """Something an import noticed and did NOT refuse over."""

    code: LoftWarningCode
    message: str


class LoftImportRequest(BaseModel):
    """Gateway -> documents: a read, blob-inlined tree to create a part from."""

    document_id: uuid.UUID = Field(
        description="The part id the file carries; kept unless it, or any "
        "feature id, already exists in this install"
    )
    tree: LoftTree
    versions: list[LoftVersion] = Field(
        default_factory=list[LoftVersion],
        max_length=MAX_LOFT_VERSIONS,
        description="The file's named versions, ascending seq; kept with their seq",
    )


class LoftImportResponse(BaseModel):
    """``POST /api/v1/parts/import``: the created part and what was noticed."""

    part: PartResponse
    warnings: list[LoftWarning] = Field(default_factory=list[LoftWarning])


@dataclass(frozen=True)
class LoftArchive:
    """A ``.loft`` that passed :func:`read_loft`.

    ``tree`` has every blob inlined again, ready for :class:`LoftImportRequest`.
    ``cache`` is ``None`` when the file has none or when it cannot be trusted
    (a hand-edited tree, a corrupt body); ``warnings`` say which.
    """

    manifest: LoftManifest
    tree: LoftTree
    cache: LoftCache | None
    warnings: tuple[LoftWarning, ...]
    versions: tuple[LoftVersion, ...] = ()


# --- canonical bytes ----------------------------------------------------------------


def _canonical_value(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a .loft cannot store NaN or infinity")
        return 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        entries = cast(dict[Any, Any], value)
        return {str(key): _canonical_value(item) for key, item in entries.items()}
    if isinstance(value, list | tuple):
        items = cast(list[Any], value)
        return [_canonical_value(item) for item in items]
    return value


def canonical_json(value: Any) -> bytes:
    """THE JSON encoding of every ``.loft`` member: same value, same bytes.

    ``sort_keys``, ``indent=2``, ``ensure_ascii=False``, UTF-8 with LF and a
    trailing newline, ``allow_nan=False``; floats are Python's shortest
    round-tripping repr and ``-0.0`` is written ``0.0``.
    """
    text = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Lower-case hex sha256 — the digest every manifest entry uses."""
    return hashlib.sha256(data).hexdigest()


def blob_path(digest: str) -> str:
    """The member path of a blob with this sha256."""
    return f"{BLOB_DIR}sha256-{digest}.step"


def _extract_blobs(tree: LoftTree) -> tuple[LoftTree, dict[str, bytes]]:
    """Move every import feature's inline STEP text out into a blob."""
    blobs: dict[str, bytes] = {}
    features: list[LoftTreeFeature] = []
    for feature in tree.features:
        data = feature.params.get("data")
        if (
            feature.type == "import"
            and isinstance(data, str)
            and not data.startswith(BLOB_REF_PREFIX)
        ):
            raw = data.encode("utf-8")
            digest = sha256_hex(raw)
            blobs[digest] = raw
            params = {**feature.params, "data": f"{BLOB_REF_PREFIX}{digest}"}
            feature = feature.model_copy(update={"params": params})
        features.append(feature)
    return tree.model_copy(update={"features": features}), blobs


def _canonical_tree(tree: LoftTree) -> LoftTree:
    """Sort what has no meaningful order (per-body materials) by its key."""
    if tree.materials is None:
        return tree
    bodies = sorted(tree.materials.bodies, key=lambda body: str(body.base_feature_id))
    return tree.model_copy(
        update={"materials": tree.materials.model_copy(update={"bodies": bodies})}
    )


def _zip_member(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
    info.create_system = 3  # unix, so the mode below means the same everywhere
    info.external_attr = _ZIP_MODE
    if name.endswith(".json"):
        info.compress_type = zipfile.ZIP_STORED
    else:
        info.compress_type = zipfile.ZIP_DEFLATED
    return info


def version_tree_path(seq: int) -> str:
    """The member path of version *seq*'s tree."""
    return f"versions/{seq}.tree.json"


def encode_tree(tree: LoftTree) -> tuple[bytes, dict[str, bytes]]:
    """A tree's canonical ``tree.json`` bytes, and the blobs moved out of it.

    THE encoding of every tree in a ``.loft`` (the current one and each
    version's), and the bytes a version's ``tree_sha256`` is taken over.
    """
    extracted, blobs = _extract_blobs(_canonical_tree(tree))
    return canonical_json(extracted.model_dump(mode="json")), blobs


def _inlined_bytes(tree: LoftTree) -> int:
    """The STEP bytes a reader inlines back into *tree*: every reference
    counted, as :func:`_inline_blobs` counts them (one blob may be named by
    several import features; the file stores it once)."""
    total = 0
    for feature in tree.features:
        data = feature.params.get("data")
        if feature.type == "import" and isinstance(data, str):
            total += len(data.encode("utf-8"))
    return total


def _check_packable(
    members: list[tuple[str, bytes]], *, inlined: int, versions: int
) -> None:
    """Refuse to write a file :func:`read_loft` would refuse to read.

    Same caps, measured the same way: member count, each member's cap, and the
    total including the STEP text each tree inlines again on read.
    """
    if versions > MAX_LOFT_VERSIONS:
        raise LoftFileError(
            f"A .loft holds at most {MAX_LOFT_VERSIONS} versions.",
            code="loft_too_many_versions",
            details={"max_versions": MAX_LOFT_VERSIONS, "versions": versions},
        )
    if len(members) > MAX_LOFT_MEMBERS:
        raise LoftFileError(
            f"The part needs more than {MAX_LOFT_MEMBERS} .loft members.",
            code="loft_too_many_members",
            details={"max_members": MAX_LOFT_MEMBERS, "members": len(members)},
        )
    total = inlined
    for name, data in members:
        cap = _member_cap(name)
        if len(data) > cap:
            raise LoftFileError(
                f"The .loft member {name} would be over its {cap}-byte limit.",
                code="loft_member_too_large",
                details={"member": name, "size": len(data), "max_bytes": cap},
            )
        total += len(data)
    if total > MAX_LOFT_TOTAL_BYTES:
        raise LoftFileError(
            f"The part would unpack to more than {MAX_LOFT_TOTAL_BYTES} bytes.",
            code="loft_member_too_large",
            details={"max_bytes": MAX_LOFT_TOTAL_BYTES, "size": total},
        )


def pack_part(
    *,
    document_id: uuid.UUID,
    tree: LoftTree,
    loft_version: str,
    body_step: bytes | None = None,
    properties: LoftCacheProperties | None = None,
    versions: Sequence[LoftVersion] = (),
) -> bytes:
    """Write a part ``.loft``. Deterministic: same inputs, same bytes.

    *tree* carries import STEP text inline (as documents serves it); it is moved
    into ``blobs/`` here. *body_step* is the geometry export of the same tree
    and *properties* its mass properties; both are optional (a tree with no
    body has no cache). *versions* are the part's named versions; each tree is
    written with the same rules as ``tree.json`` and shares ``blobs/``. Raises
    :class:`LoftFileError` rather than write a file over the reader's caps.
    """
    if len(versions) > MAX_LOFT_VERSIONS:
        _check_packable([], inlined=0, versions=len(versions))
    tree_bytes, blobs = encode_tree(tree)
    tree_digest = sha256_hex(tree_bytes)
    inlined = _inlined_bytes(tree)

    ordered = sorted(versions, key=lambda version: version.seq)
    if len({version.seq for version in ordered}) != len(ordered):
        raise ValueError("two versions share a seq")
    version_members: list[tuple[str, bytes]] = []
    entries: list[LoftVersionEntry] = []
    for version in ordered:
        version_bytes, version_blobs = encode_tree(version.tree)
        blobs.update(version_blobs)
        inlined += _inlined_bytes(version.tree)
        version_members.append((version_tree_path(version.seq), version_bytes))
        entries.append(
            LoftVersionEntry(
                seq=version.seq,
                name=version.name,
                message=version.message,
                author=version.author,
                created_at=version.created_at,
                tree_sha256=sha256_hex(version_bytes),
            )
        )

    members: list[tuple[str, bytes]] = [(TREE_PATH, tree_bytes)]
    if entries:
        index = LoftVersionIndex(versions=entries)
        members.append(
            (VERSIONS_INDEX_PATH, canonical_json(index.model_dump(mode="json")))
        )
        members += version_members
    members += [(blob_path(digest), blobs[digest]) for digest in sorted(blobs)]
    cache: LoftCache | None = None
    if body_step is not None:
        members.append((BODY_STEP_PATH, body_step))
        cache = LoftCache(
            step_sha256=sha256_hex(body_step),
            built_from_tree_sha256=tree_digest,
            properties=properties,
        )

    manifest = LoftManifest(
        format="loft",
        format_version=LOFT_FORMAT_VERSION,
        loft_version=loft_version,
        kind="part",
        document_id=document_id,
        units=LoftUnits(),
        tree_sha256=tree_digest,
        members={name: sha256_hex(data) for name, data in members},
        cache=cache,
    )
    manifest_bytes = canonical_json(manifest.model_dump(mode="json"))
    all_members = [(MANIFEST_PATH, manifest_bytes), *members]
    _check_packable(all_members, inlined=inlined, versions=len(ordered))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in all_members:
            archive.writestr(_zip_member(name), data, compresslevel=_DEFLATE_LEVEL)
    return buffer.getvalue()


# --- reading ------------------------------------------------------------------------


def _parse_format_version(raw: object) -> tuple[int, int]:
    if not isinstance(raw, str) or re.fullmatch(r"\d+\.\d+", raw) is None:
        raise LoftFileError(
            "The .loft manifest has no readable format_version.",
            code="loft_manifest_invalid",
        )
    major, minor = raw.split(".")
    return int(major), int(minor)


def _declared_entry_count(data: bytes) -> int:
    """Total entries, from the end-of-central-directory record, before parsing it."""
    tail_start = max(0, len(data) - (22 + 0xFFFF))
    eocd = data.rfind(b"PK\x05\x06", tail_start)
    if eocd < 0 or eocd + 22 > len(data):
        raise LoftFileError(
            "This file is not a .loft (not a zip).", code="loft_not_zip"
        )
    # ZIP64: zipfile reads the locator 20 bytes before the classic end record
    # and, if present, trusts the ZIP64 record's entry count and directory size
    # over the classic one's, so a classic record claiming 1 entry / 100 bytes
    # would sail past the cap below while zipfile parses 700k entries. A legal
    # .loft never needs ZIP64 (the caps keep it far below 4 GiB / 65k entries),
    # so the ZIP64 end structures are refused outright. Both signatures are
    # looked for in the bytes just before the end record — where zipfile looks —
    # rather than anywhere, because deflated STEP can contain any 4 bytes.
    zip64_window = data[max(0, eocd - 20 - 56 - 1024) : eocd]
    if b"PK\x06\x07" in zip64_window or b"PK\x06\x06" in zip64_window:
        raise LoftFileError(
            "The .loft uses ZIP64, which a .loft never needs.",
            code="loft_zip_invalid",
        )
    (entries, directory_bytes) = struct.unpack_from("<HI", data, eocd + 10)
    if directory_bytes > MAX_LOFT_CENTRAL_DIRECTORY_BYTES:
        # The entry count is the attacker's to write; the directory SIZE is what
        # zipfile actually parses, so it is what must be bounded.
        raise LoftFileError(
            f"The .loft holds more than {MAX_LOFT_MEMBERS} members.",
            code="loft_too_many_members",
            details={
                "max_members": MAX_LOFT_MEMBERS,
                "central_directory_bytes": directory_bytes,
            },
        )
    return int(entries)


def _check_member_name(name: str) -> None:
    unsafe = (
        "\\" in name
        or name.startswith("/")
        or name.endswith("/")
        or re.match(r"^[A-Za-z]:", name) is not None
        or any(part in ("", ".", "..") for part in name.split("/"))
        or "\x00" in name
    )
    if unsafe:
        raise LoftFileError(
            "The .loft holds a member with an unsafe path.",
            code="loft_member_unsafe",
            details={"member": name},
        )


def _member_cap(name: str) -> int:
    if name == MANIFEST_PATH:
        return MAX_LOFT_MANIFEST_BYTES
    if name == TREE_PATH:
        return MAX_LOFT_TREE_BYTES
    if name == VERSIONS_INDEX_PATH:
        return MAX_LOFT_VERSION_INDEX_BYTES
    if _VERSION_TREE_RE.match(name) is not None:
        return MAX_LOFT_VERSION_TREE_BYTES
    if name == BODY_STEP_PATH:
        return MAX_LOFT_BODY_STEP_BYTES
    return MAX_LOFT_BLOB_BYTES


def _screen_members(
    archive: zipfile.ZipFile, *, allow_unknown: bool
) -> dict[str, zipfile.ZipInfo]:
    """Every member that will be read, after the safety checks."""
    accepted: dict[str, zipfile.ZipInfo] = {}
    seen: set[str] = set()
    total = 0
    for info in archive.infolist():
        name = info.filename
        _check_member_name(name)
        if name in seen:
            raise LoftFileError(
                "The .loft lists a member twice.",
                code="loft_member_duplicate",
                details={"member": name},
            )
        seen.add(name)
        if info.flag_bits & 0x1:
            raise LoftFileError(
                "The .loft holds an encrypted member.",
                code="loft_member_encrypted",
                details={"member": name},
            )
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise LoftFileError(
                "The .loft uses a compression other than STORED or DEFLATE.",
                code="loft_member_compression",
                details={"member": name, "compress_type": info.compress_type},
            )
        if _KNOWN_MEMBER_RE.match(name) is None:
            if allow_unknown and _FUTURE_MEMBER_RE.match(name) is not None:
                continue  # a newer minor's member: skipped, never read
            raise LoftFileError(
                "The .loft holds a member this format does not define.",
                code="loft_member_unknown",
                details={"member": name},
            )
        cap = _member_cap(name)
        if info.file_size > cap:
            raise LoftFileError(
                f"The .loft member {name} is over its {cap}-byte limit.",
                code="loft_member_too_large",
                details={"member": name, "size": info.file_size, "max_bytes": cap},
            )
        total += info.file_size
        if total > MAX_LOFT_TOTAL_BYTES:
            raise LoftFileError(
                f"The .loft unpacks to more than {MAX_LOFT_TOTAL_BYTES} bytes.",
                code="loft_member_too_large",
                details={"max_bytes": MAX_LOFT_TOTAL_BYTES},
            )
        if info.file_size >= LOFT_RATIO_FLOOR_BYTES and (
            info.compress_size == 0
            or info.file_size / info.compress_size > MAX_LOFT_COMPRESSION_RATIO
        ):
            raise LoftFileError(
                "The .loft member compresses too well to be real (zip bomb).",
                code="loft_zip_bomb",
                details={
                    "member": name,
                    "max_ratio": MAX_LOFT_COMPRESSION_RATIO,
                },
            )
        accepted[name] = info
    return accepted


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    cap = _member_cap(info.filename)
    try:
        with archive.open(info) as handle:
            data = handle.read(cap + 1)
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError) as exc:
        raise LoftFileError(
            f"The .loft member {info.filename} is damaged.",
            code="loft_not_zip",
            details={"member": info.filename},
        ) from exc
    if len(data) > cap:
        raise LoftFileError(
            f"The .loft member {info.filename} is over its {cap}-byte limit.",
            code="loft_member_too_large",
            details={"member": info.filename, "max_bytes": cap},
        )
    return data


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed in a .loft")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # 1e999 parses as inf
        raise ValueError(f"{text} is not a finite number")
    return value


def _parse_json(data: bytes, *, member: str, code: LoftErrorCode) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise LoftFileError(
            f"The .loft member {member} is not valid JSON.",
            code=code,
            details={"member": member},
        ) from exc


def _validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": [str(part) for part in error["loc"]], "msg": error["msg"]}
        for error in exc.errors()[:20]
    ]


def _read_manifest(raw: Any) -> LoftManifest:
    if not isinstance(raw, dict):
        raise LoftFileError(
            "The .loft manifest is not a JSON object.", code="loft_manifest_invalid"
        )
    manifest_raw = cast(dict[str, Any], raw)
    if manifest_raw.get("format") != LOFT_FORMAT:
        raise LoftFileError(
            "This zip is not a .loft file (its manifest does not say format 'loft').",
            code="loft_not_loft",
        )
    major, _minor = _parse_format_version(manifest_raw.get("format_version"))
    if major > LOFT_FORMAT_MAJOR:
        raise LoftFileError(
            f"This .loft was written by a newer Loft (format "
            f"{manifest_raw['format_version']}); this Loft reads format "
            f"{LOFT_FORMAT_MAJOR}.x. Upgrade Loft to open it.",
            code="loft_format_too_new",
            details={
                "format_version": manifest_raw["format_version"],
                "supported_major": LOFT_FORMAT_MAJOR,
            },
        )
    if manifest_raw.get("kind") != "part":
        raise LoftFileError(
            "This .loft holds a document kind this Loft cannot import yet.",
            code="loft_kind_unsupported",
            details={"kind": manifest_raw.get("kind")},
        )
    try:
        return LoftManifest.model_validate(manifest_raw)
    except ValidationError as exc:
        raise LoftFileError(
            "The .loft manifest is invalid.",
            code="loft_manifest_invalid",
            details={"errors": _validation_details(exc)},
        ) from exc


def _blob_reference(feature: LoftTreeFeature) -> str | None:
    """The sha256 an ``import`` feature's ``params.data`` names, or None."""
    if feature.type != "import":
        return None
    data = feature.params.get("data")
    match = _BLOB_REF_RE.match(data) if isinstance(data, str) else None
    return match.group(1) if match is not None else None


def _inline_blobs(
    tree: LoftTree, blobs: dict[str, bytes], *, budget: int
) -> tuple[LoftTree, int]:
    """Put each referenced blob's STEP text back where the tree names it.

    Only into an ``import`` feature's ``params.data``. A blob may be named by
    any number of features (two imports of the same STEP file share one), but
    EVERY reference's bytes count against *budget* (what is left of
    :data:`MAX_LOFT_TOTAL_BYTES`), and that is checked BEFORE any text is
    decoded: a 16 MiB blob named by a thousand features is refused here rather
    than decoded a thousand times. Each blob is decoded once and the one
    string is shared. Returns the tree and the bytes it inlined, which the
    caller takes off the budget of the next tree.
    """
    inlined = 0
    for feature in tree.features:
        digest = _blob_reference(feature)
        if digest is None:
            continue
        if digest not in blobs:
            raise LoftFileError(
                f"Feature {feature.name!r} names a blob the .loft does not hold.",
                code="loft_blob_missing",
                details={"feature_id": str(feature.id), "sha256": digest},
            )
        inlined += len(blobs[digest])
        if inlined > budget:
            raise LoftFileError(
                f"The .loft unpacks to more than {MAX_LOFT_TOTAL_BYTES} bytes.",
                code="loft_member_too_large",
                details={"max_bytes": MAX_LOFT_TOTAL_BYTES},
            )
    features: list[LoftTreeFeature] = []
    decoded: dict[str, str] = {}
    for feature in tree.features:
        digest = _blob_reference(feature)
        if digest is not None:
            text = decoded.get(digest)
            if text is None:
                try:
                    text = decoded[digest] = blobs[digest].decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise LoftFileError(
                        "A .loft blob is not STEP text.",
                        code="loft_blob_corrupt",
                        details={"sha256": digest},
                    ) from exc
            feature = feature.model_copy(
                update={"params": {**feature.params, "data": text}}
            )
        features.append(feature)
    return tree.model_copy(update={"features": features}), inlined


def read_loft(data: bytes) -> LoftArchive:
    """Read and verify a ``.loft`` held in memory, or raise :class:`LoftFileError`.

    Never touches the filesystem. Refuses: an oversize upload, too many members,
    unsafe/duplicate/directory/encrypted members, any compression but STORED or
    DEFLATE, an unknown member (unless the file is a newer minor version), a
    member over its cap, a zip bomb, a newer major format version, a blob whose
    sha256 does not match. Warns, without refusing, when ``tree.json`` was
    edited after export (the cache is then ignored) or the cached body's sha256
    does not match (ditto).
    """
    if len(data) > MAX_LOFT_UPLOAD_BYTES:
        raise LoftFileError(
            f"The .loft is over the {MAX_LOFT_UPLOAD_BYTES}-byte upload limit.",
            code="loft_too_large",
            details={"max_bytes": MAX_LOFT_UPLOAD_BYTES},
        )
    if _declared_entry_count(data) > MAX_LOFT_MEMBERS:
        raise LoftFileError(
            f"The .loft holds more than {MAX_LOFT_MEMBERS} members.",
            code="loft_too_many_members",
            details={"max_members": MAX_LOFT_MEMBERS},
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as exc:
        raise LoftFileError(
            "This file is not a .loft (not a zip).", code="loft_not_zip"
        ) from exc
    with archive:
        if len(archive.infolist()) > MAX_LOFT_MEMBERS:
            raise LoftFileError(
                f"The .loft holds more than {MAX_LOFT_MEMBERS} members.",
                code="loft_too_many_members",
                details={"max_members": MAX_LOFT_MEMBERS},
            )
        # The manifest decides whether unknown members are a newer minor's (skip)
        # or junk (refuse), so it is screened and read first, on its own.
        manifest_info = next(
            (info for info in archive.infolist() if info.filename == MANIFEST_PATH),
            None,
        )
        if manifest_info is None:
            raise LoftFileError(
                "The .loft has no manifest.json.",
                code="loft_member_missing",
                details={"member": MANIFEST_PATH},
            )
        screened = _screen_members(archive, allow_unknown=True)
        manifest_raw = _parse_json(
            _read_member(archive, screened[MANIFEST_PATH]),
            member=MANIFEST_PATH,
            code="loft_manifest_invalid",
        )
        manifest = _read_manifest(manifest_raw)
        newer_minor = _parse_format_version(manifest.format_version)[1] > (
            LOFT_FORMAT_MINOR
        )
        if not newer_minor:
            screened = _screen_members(archive, allow_unknown=False)
        contents = {
            name: _read_member(archive, info)
            for name, info in screened.items()
            if name != MANIFEST_PATH
        }
    return _verify(manifest, contents)


def _verify(manifest: LoftManifest, contents: dict[str, bytes]) -> LoftArchive:
    warnings: list[LoftWarning] = []
    tree_bytes = contents.get(TREE_PATH)
    if tree_bytes is None:
        raise LoftFileError(
            "The .loft has no tree.json.",
            code="loft_member_missing",
            details={"member": TREE_PATH},
        )

    blobs: dict[str, bytes] = {}
    for name, data in contents.items():
        match = _BLOB_PATH_RE.match(name)
        if match is None:
            continue
        digest = sha256_hex(data)
        if digest != match.group(1) or manifest.members.get(name) not in (
            None,
            digest,
        ):
            raise LoftFileError(
                "A .loft blob does not match its sha256: the file is damaged.",
                code="loft_blob_corrupt",
                details={"member": name},
            )
        blobs[match.group(1)] = data

    tree_trusted = sha256_hex(tree_bytes) == manifest.tree_sha256
    if not tree_trusted:
        warnings.append(
            LoftWarning(
                code="loft_tree_edited",
                message="tree.json was changed after this file was exported; "
                "the part was rebuilt from the edited tree and the cached body "
                "was ignored.",
            )
        )
    cache = manifest.cache if tree_trusted else None
    if cache is not None:
        body = contents.get(BODY_STEP_PATH)
        if (
            body is None
            or sha256_hex(body) != cache.step_sha256
            or cache.built_from_tree_sha256 != manifest.tree_sha256
        ):
            warnings.append(
                LoftWarning(
                    code="loft_cache_corrupt",
                    message="The cached body in this file does not match its "
                    "manifest; it was ignored.",
                )
            )
            cache = None

    tree = _parse_tree(tree_bytes, member=TREE_PATH)
    budget = MAX_LOFT_TOTAL_BYTES - sum(len(data) for data in contents.values())
    tree, used = _inline_blobs(tree, blobs, budget=budget)
    budget -= used

    versions: list[LoftVersion] = []
    edited: list[int] = []
    for entry, version_bytes in _version_members(contents):
        if sha256_hex(version_bytes) != entry.tree_sha256:
            edited.append(entry.seq)
        version_tree, used = _inline_blobs(
            _parse_tree(version_bytes, member=version_tree_path(entry.seq)),
            blobs,
            budget=budget,
        )
        budget -= used
        versions.append(
            LoftVersion(
                seq=entry.seq,
                name=entry.name,
                message=entry.message,
                author=entry.author,
                created_at=entry.created_at,
                tree=version_tree,
            )
        )
    if edited:
        warnings.append(
            LoftWarning(
                code="loft_version_edited",
                message="The tree of version(s) "
                + ", ".join(str(seq) for seq in edited)
                + " was changed after this file was exported; it was imported "
                "as it now reads.",
            )
        )
    return LoftArchive(
        manifest=manifest,
        tree=tree,
        cache=cache,
        warnings=tuple(warnings),
        versions=tuple(versions),
    )


def _parse_tree(data: bytes, *, member: str) -> LoftTree:
    try:
        return LoftTree.model_validate(
            _parse_json(data, member=member, code="loft_tree_invalid")
        )
    except ValidationError as exc:
        raise LoftFileError(
            f"The .loft {member} is invalid.",
            code="loft_tree_invalid",
            details={"member": member, "errors": _validation_details(exc)},
        ) from exc


def _version_members(
    contents: dict[str, bytes],
) -> list[tuple[LoftVersionEntry, bytes]]:
    """``versions/index.json`` and the tree member of each entry, checked.

    The index and the ``versions/<seq>.tree.json`` members must agree exactly:
    a tree the index does not list, or an entry without its tree, is refused,
    as is an index that is not in strictly ascending ``seq``.
    """
    trees = {
        int(match.group(1)): data
        for name, data in contents.items()
        if (match := _VERSION_TREE_RE.match(name)) is not None
    }
    index_bytes = contents.get(VERSIONS_INDEX_PATH)
    if index_bytes is None:
        if trees:
            raise LoftFileError(
                "The .loft holds version trees but no versions/index.json.",
                code="loft_versions_invalid",
                details={"member": VERSIONS_INDEX_PATH},
            )
        return []
    raw = _parse_json(
        index_bytes, member=VERSIONS_INDEX_PATH, code="loft_versions_invalid"
    )
    listed = (
        cast(dict[str, Any], raw).get("versions") if isinstance(raw, dict) else None
    )
    if isinstance(listed, list) and len(cast(list[Any], listed)) > MAX_LOFT_VERSIONS:
        raise LoftFileError(
            f"The .loft holds more than {MAX_LOFT_VERSIONS} versions.",
            code="loft_too_many_versions",
            details={"max_versions": MAX_LOFT_VERSIONS},
        )
    try:
        index = LoftVersionIndex.model_validate(raw)
    except ValidationError as exc:
        raise LoftFileError(
            "The .loft versions/index.json is invalid.",
            code="loft_versions_invalid",
            details={"errors": _validation_details(exc)},
        ) from exc
    seqs = [entry.seq for entry in index.versions]
    if any(later <= earlier for earlier, later in itertools.pairwise(seqs)):
        raise LoftFileError(
            "The .loft versions/index.json is not in ascending seq order.",
            code="loft_versions_invalid",
        )
    unlisted = sorted(set(trees) - set(seqs))
    if unlisted:
        raise LoftFileError(
            "The .loft holds a version tree its index does not list.",
            code="loft_versions_invalid",
            details={"member": version_tree_path(unlisted[0])},
        )
    missing = [seq for seq in seqs if seq not in trees]
    if missing:
        raise LoftFileError(
            "The .loft lists a version whose tree it does not hold.",
            code="loft_member_missing",
            details={"member": version_tree_path(missing[0])},
        )
    return [(entry, trees[entry.seq]) for entry in index.versions]


def loft_filename(name: str, document_id: uuid.UUID) -> str:
    """The download name of a part's ``.loft``: ``<slug>.loft``."""
    slug = document_slug(name)
    return f"{slug or f'part-{document_id}'}{LOFT_SUFFIX}"


__all__ = [
    "BLOB_REF_PREFIX",
    "LOFT_FORMAT_VERSION",
    "LOFT_MEDIA_TYPE",
    "LOFT_VOLUME_REL_TOLERANCE",
    "MAX_LOFT_BLOB_BYTES",
    "MAX_LOFT_BODY_STEP_BYTES",
    "MAX_LOFT_COMPRESSION_RATIO",
    "MAX_LOFT_MEMBERS",
    "MAX_LOFT_TOTAL_BYTES",
    "MAX_LOFT_TREE_BYTES",
    "MAX_LOFT_UPLOAD_BYTES",
    "MAX_LOFT_VERSIONS",
    "VERSIONS_INDEX_PATH",
    "LoftArchive",
    "LoftCache",
    "LoftCacheProperties",
    "LoftFileError",
    "LoftImportRequest",
    "LoftImportResponse",
    "LoftManifest",
    "LoftTree",
    "LoftTreeFeature",
    "LoftVersion",
    "LoftVersionEntry",
    "LoftVersionIndex",
    "LoftVersionList",
    "LoftWarning",
    "canonical_json",
    "encode_tree",
    "loft_filename",
    "pack_part",
    "read_loft",
    "version_tree_path",
]
