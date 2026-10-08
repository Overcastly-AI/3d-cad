"""The ``.loft`` container: canonical bytes, and a reader that refuses hostile zips.

Three claims, each pinned here:

1. **Same part, same bytes.** The golden fixture (``golden-v1.1.loft``, with
   named versions) is checked byte-for-byte, and a file that is read and packed
   again comes back identical (the repack test). Regenerate the golden ONLY for
   a deliberate format change:
   ``LOFT_REGEN_GOLDEN=1 uv run pytest packages/loft-wire/tests/test_loft_file.py``.
   ``golden-v1.loft`` is the frozen format 1.0 file: never regenerated, it
   proves an older file still reads, and the hostile-zip tests start from it.
2. **The reader never trusts the zip.** Zip-slip paths, duplicates, directory
   entries, encryption, foreign compression, unknown members, every size cap and
   a zip bomb are each refused with their own code.
3. **Versions.** A newer MAJOR format is refused ("Upgrade Loft"); a newer
   MINOR is read, ignoring the keys and members it adds.
"""

from __future__ import annotations

import io
import json
import os
import random
import time
import tracemalloc
import uuid
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from loft_wire import loft_file
from loft_wire.geometry import BoundingBox
from loft_wire.loft_file import (
    BODY_STEP_PATH,
    MANIFEST_PATH,
    TREE_PATH,
    VERSIONS_INDEX_PATH,
    LoftCacheProperties,
    LoftFileError,
    LoftTree,
    LoftVersion,
    canonical_json,
    encode_tree,
    pack_part,
    read_loft,
    sha256_hex,
)

FIXTURE = Path(__file__).parent / "fixtures" / "golden-v1.loft"
GOLDEN = Path(__file__).parent / "fixtures" / "golden-v1.1.loft"

PART_ID = uuid.UUID("0b6f3d0e-6f0a-4a39-9a4c-5d1d0f7c2a10")
SKETCH_ID = uuid.UUID("1c7a4e1f-7a1b-4b4a-8b5d-6e2e1a8d3b21")
EXTRUDE_ID = uuid.UUID("2d8b5f20-8b2c-4c5b-9c6e-7f3f2b9e4c32")
IMPORT_ID = uuid.UUID("3e9c6031-9c3d-4d6c-8d7f-80403caf5d43")

STEP_TEXT = "ISO-10303-21;\nHEADER;\n/* a tiny stand-in body, Größe 1 */\nENDSEC;\n"
BODY_STEP = b"ISO-10303-21;\nHEADER;\nFILE_NAME('bracket','1970-01-01T00:00:00');\n"


def _golden_tree() -> LoftTree:
    """Hand-written params: the golden pins the CONTAINER, not today's params dump."""
    return LoftTree.model_validate(
        {
            "name": "Bracket — Größe 1",
            "length_unit": "in",
            "materials": {
                "default_material": "aluminium_6061",
                "bodies": [
                    {"base_feature_id": str(IMPORT_ID), "material": "steel_1018"},
                    {"base_feature_id": str(EXTRUDE_ID), "material": "abs"},
                ],
            },
            "rollback_feature_id": None,
            "features": [
                {
                    "id": str(IMPORT_ID),
                    "name": "Imported STEP",
                    "type": "import",
                    "param_version": 1,
                    "suppressed": False,
                    "params": {"kind": "inline", "format": "step", "data": STEP_TEXT},
                },
                {
                    "id": str(SKETCH_ID),
                    "name": "Sketch1",
                    "type": "sketch",
                    "param_version": 1,
                    "suppressed": False,
                    "params": {"plane": "XY", "offset": -0.0, "scale": 0.1},
                },
                {
                    "id": str(EXTRUDE_ID),
                    "name": "Extrude1",
                    "type": "extrude",
                    "param_version": 1,
                    "suppressed": True,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                        "distance_mm": 12.5,
                        "taper": 1e-07,
                    },
                },
            ],
        }
    )


GOLDEN_PROPERTIES = LoftCacheProperties(
    volume_mm3=12345.678901234,
    area_mm2=-0.0,
    bbox=BoundingBox.model_validate(
        {
            "min": {"x": 0.0, "y": -0.0, "z": 0.0},
            "max": {"x": 40.0, "y": 25.0, "z": 10.0},
        }
    ),
)


def _golden_versions() -> list[LoftVersion]:
    """Rev A (import + sketch) and Rev B (the whole golden tree)."""
    whole = _golden_tree()
    rev_a = whole.model_copy(update={"features": whole.features[:2], "materials": None})
    return [
        LoftVersion(
            seq=2,
            name="Rev B — Größe",
            author=None,
            created_at=datetime(2026, 10, 8, 12, 30, 0, 250000, tzinfo=UTC),
            tree=whole,
        ),
        LoftVersion(
            seq=1,
            name="Rev A",
            message="First article,\nsent to the shop",
            author="Ada Lovelace",
            created_at=datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC),
            tree=rev_a,
        ),
    ]


def _golden_bytes() -> bytes:
    return pack_part(
        document_id=PART_ID,
        tree=_golden_tree(),
        loft_version="golden",
        body_step=BODY_STEP,
        properties=GOLDEN_PROPERTIES,
        versions=_golden_versions(),
    )


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


# --- 1. canonical bytes -------------------------------------------------------------


def test_golden_fixture_byte_for_byte() -> None:
    """Pinned bytes. A diff here is a FORMAT change: bump the version or revert."""
    produced = _golden_bytes()
    if os.environ.get("LOFT_REGEN_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_bytes(produced)
    expected = GOLDEN.read_bytes()
    if produced != expected:
        # Say WHICH layer moved before failing: a member's content, or only the
        # deflate stream (a different zlib build), are different conversations.
        same_members = _members(produced) == _members(expected)
        pytest.fail(
            "golden-v1.1.loft changed: "
            + (
                "member contents are identical, only the zip bytes differ "
                f"(zlib {__import__('zlib').ZLIB_RUNTIME_VERSION})"
                if same_members
                else "member contents differ"
            )
        )


def test_pack_is_deterministic_and_member_order_is_fixed() -> None:
    first, second = _golden_bytes(), _golden_bytes()
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        infos = archive.infolist()
    digest = sha256_hex(STEP_TEXT.encode())
    assert [info.filename for info in infos] == [
        MANIFEST_PATH,
        TREE_PATH,
        VERSIONS_INDEX_PATH,
        "versions/1.tree.json",
        "versions/2.tree.json",
        f"blobs/sha256-{digest}.step",
        BODY_STEP_PATH,
    ]
    for info in infos:
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.external_attr >> 16 == 0o100644
        assert info.extra == b""
        expected = zipfile.ZIP_STORED if info.filename.endswith(".json") else 8
        assert info.compress_type == expected


def test_canonical_json_rules() -> None:
    encoded = canonical_json({"b": -0.0, "a": [0.1, 1e-07], "ü": "é"})
    assert (
        encoded
        == (
            '{\n  "a": [\n    0.1,\n    1e-07\n  ],\n  "b": 0.0,\n  "ü": "é"\n}\n'
        ).encode()
    )
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_tree_json_holds_a_blob_reference_not_the_step_text() -> None:
    tree = json.loads(_members(_golden_bytes())[TREE_PATH])
    data = tree["features"][0]["params"]["data"]
    assert data == f"loft-blob:sha256:{sha256_hex(STEP_TEXT.encode())}"
    assert "order_index" not in tree["features"][0]
    # Per-body materials are written sorted by base feature id.
    bodies = [body["base_feature_id"] for body in tree["materials"]["bodies"]]
    assert bodies == sorted(bodies)


def test_manifest_has_no_timestamp_and_hashes_every_member() -> None:
    members = _members(_golden_bytes())
    manifest = json.loads(members[MANIFEST_PATH])
    assert set(manifest) == {
        "cache",
        "document_id",
        "format",
        "format_version",
        "kind",
        "loft_version",
        "members",
        "references",
        "tree_sha256",
        "units",
    }
    assert manifest["format_version"] == "1.1"
    assert manifest["units"] == {"storage": "mm"}
    for name, digest in manifest["members"].items():
        assert sha256_hex(members[name]) == digest
    assert manifest["cache"]["built_from_tree_sha256"] == manifest["tree_sha256"]


def test_repack_is_byte_identical() -> None:
    """read -> pack gives the same bytes: nothing is lost or reordered on the
    way, the versions included (seq, name, message, author, time and tree)."""
    original = GOLDEN.read_bytes()
    archive = read_loft(original)
    assert archive.warnings == ()
    assert archive.tree.features[0].params["data"] == STEP_TEXT
    assert [v.seq for v in archive.versions] == [1, 2]
    assert archive.versions[0].author == "Ada Lovelace"
    assert archive.versions[1].author is None
    assert archive.versions[0].tree.features[0].params["data"] == STEP_TEXT
    members = _members(original)
    repacked = pack_part(
        document_id=archive.manifest.document_id,
        tree=archive.tree,
        loft_version=archive.manifest.loft_version,
        body_step=members[BODY_STEP_PATH],
        properties=archive.cache.properties if archive.cache else None,
        versions=archive.versions,
    )
    assert repacked == original


def test_a_format_1_0_file_without_versions_still_reads() -> None:
    """The frozen 1.0 golden: read as before, no versions, nothing to warn."""
    archive = read_loft(FIXTURE.read_bytes())
    assert archive.manifest.format_version == "1.0"
    assert archive.warnings == ()
    assert archive.versions == ()
    assert archive.tree == _golden_tree().model_copy(
        update={"materials": archive.tree.materials}
    )


def test_version_index_and_trees_use_the_canonical_rules() -> None:
    members = _members(_golden_bytes())
    index = json.loads(members[VERSIONS_INDEX_PATH])
    assert members[VERSIONS_INDEX_PATH] == canonical_json(index)
    assert [entry["seq"] for entry in index["versions"]] == [1, 2]
    assert index["versions"][0] == {
        "author": "Ada Lovelace",
        "created_at": "2026-10-01T09:00:00Z",
        "message": "First article,\nsent to the shop",
        "name": "Rev A",
        "seq": 1,
        "tree_sha256": sha256_hex(members["versions/1.tree.json"]),
    }
    # Rev B IS the current tree: same canonical bytes, one shared blob.
    assert members["versions/2.tree.json"] == members[TREE_PATH]
    assert members["versions/2.tree.json"] == encode_tree(_golden_tree())[0]
    assert len([name for name in members if name.startswith("blobs/")]) == 1


def test_a_part_without_versions_writes_no_versions_members() -> None:
    data = pack_part(document_id=PART_ID, tree=_golden_tree(), loft_version="t")
    assert not [name for name in _members(data) if name.startswith("versions/")]
    assert read_loft(data).versions == ()


def test_an_older_reader_skips_the_versions_it_does_not_know(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 1.0 reader (no ``versions/`` in its whitelist, minor 0) opens a 1.1
    file: the new members are skipped unread and the part imports."""
    import re

    monkeypatch.setattr(loft_file, "LOFT_FORMAT_MINOR", 0)
    monkeypatch.setattr(
        loft_file,
        "_KNOWN_MEMBER_RE",
        re.compile(
            r"^(?:manifest\.json|tree\.json|cache/body\.step"
            r"|blobs/sha256-[0-9a-f]{64}\.step)$"
        ),
    )
    archive = read_loft(GOLDEN.read_bytes())
    assert archive.tree.name == _golden_tree().name
    assert archive.warnings == ()


def test_part_without_a_body_has_no_cache() -> None:
    data = pack_part(document_id=PART_ID, tree=_golden_tree(), loft_version="t")
    assert BODY_STEP_PATH not in _members(data)
    assert read_loft(data).cache is None


# --- 2. hostile zips ------------------------------------------------------------------


def _zip(
    entries: Sequence[tuple[str | zipfile.ZipInfo, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def _golden_entries() -> list[tuple[str, bytes]]:
    return list(_members(FIXTURE.read_bytes()).items())


def _with_manifest(
    edit: Callable[[dict[str, Any]], None],
) -> list[tuple[str, bytes]]:
    entries = _golden_entries()
    manifest = json.loads(entries[0][1])
    edit(manifest)
    return [(MANIFEST_PATH, canonical_json(manifest)), *entries[1:]]


def _refused(data: bytes) -> str:
    with pytest.raises(LoftFileError) as caught:
        read_loft(data)
    return caught.value.code


@pytest.mark.parametrize(
    "name",
    [
        "../evil.json",
        "blobs/../../etc/passwd",
        "/abs/tree.json",
        "blobs\\sha256-x.step",
        "C:/tree.json",
        "blobs//x.step",
        "blobs/",
    ],
)
def test_zip_slip_and_odd_paths_are_refused(name: str) -> None:
    assert _refused(_zip([*_golden_entries(), (name, b"x")])) == "loft_member_unsafe"


def test_duplicate_member_is_refused() -> None:
    entries = _golden_entries()
    with pytest.warns(UserWarning):  # zipfile itself warns about the duplicate
        data = _zip([*entries, (TREE_PATH, entries[1][1])])
    assert _refused(data) == "loft_member_duplicate"


def test_encrypted_member_is_refused() -> None:
    # zipfile cannot WRITE an encrypted member, so set the flag in the central
    # directory record by hand (general-purpose bit 0, offset 8).
    data = bytearray(_zip(_golden_entries()))
    record = data.find(b"PK\x01\x02")
    while bytes(data[record + 46 : record + 46 + len(TREE_PATH)]) != b"tree.json":
        record = data.find(b"PK\x01\x02", record + 4)
    data[record + 8] |= 0x1
    assert _refused(bytes(data)) == "loft_member_encrypted"


def test_foreign_compression_is_refused() -> None:
    entries = _golden_entries()
    info = zipfile.ZipInfo("tree.json")
    info.compress_type = zipfile.ZIP_BZIP2
    data = _zip([entries[0], (info, entries[1][1]), *entries[2:]])
    assert _refused(data) == "loft_member_compression"


def test_unknown_member_is_refused_in_a_same_version_file() -> None:
    data = _zip([*_golden_entries(), ("thumb.png", b"\x89PNG")])
    assert _refused(data) == "loft_member_unknown"


def test_too_many_members_is_refused_before_parsing() -> None:
    entries = [(f"x{index}", b"") for index in range(loft_file.MAX_LOFT_MEMBERS + 1)]
    assert _refused(_zip(entries)) == "loft_too_many_members"


def test_upload_cap() -> None:
    data = b"\0" * (loft_file.MAX_LOFT_UPLOAD_BYTES + 1)
    assert _refused(data) == "loft_too_large"


def test_not_a_zip() -> None:
    assert _refused(b"ISO-10303-21;\n") == "loft_not_zip"


def test_not_a_loft() -> None:
    data = _zip(_with_manifest(lambda m: m.update(format="other")))
    assert _refused(data) == "loft_not_loft"


@pytest.mark.parametrize(
    ("member", "cap"),
    [
        (MANIFEST_PATH, "MAX_LOFT_MANIFEST_BYTES"),
        (TREE_PATH, "MAX_LOFT_TREE_BYTES"),
        (BODY_STEP_PATH, "MAX_LOFT_BODY_STEP_BYTES"),
        ("blobs/sha256-" + "0" * 64 + ".step", "MAX_LOFT_BLOB_BYTES"),
    ],
)
def test_every_member_cap(
    member: str, cap: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each cap refuses one byte over it (caps shrunk so the test stays small)."""
    monkeypatch.setattr(loft_file, cap, 64)
    entries = [(n, d) for n, d in _golden_entries() if n != member]
    if member == MANIFEST_PATH:
        entries.insert(0, (member, b" " * 65))
    else:
        entries.append((member, b"x" * 65))
    assert _refused(_zip(entries)) == "loft_member_too_large"


def test_total_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loft_file, "MAX_LOFT_TOTAL_BYTES", 1024)
    assert _refused(FIXTURE.read_bytes()) == "loft_member_too_large"


def test_lying_size_header_cannot_read_past_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A member whose header understates its size is still cut at cap + 1."""
    entries = _golden_entries()
    data = bytearray(_zip(entries))
    archive = zipfile.ZipFile(io.BytesIO(bytes(data)))
    info = archive.getinfo(BODY_STEP_PATH)
    monkeypatch.setattr(loft_file, "MAX_LOFT_BODY_STEP_BYTES", info.file_size - 1)
    assert _refused(bytes(data)) == "loft_member_too_large"


def test_zip_bomb_ratio_is_refused() -> None:
    bomb = b"\0" * (8 * 1024 * 1024)  # deflates ~1000:1
    entries = [
        *_golden_entries()[:2],
        ("blobs/sha256-" + sha256_hex(bomb) + ".step", bomb),
    ]
    data = _zip(entries, compression=zipfile.ZIP_DEFLATED)
    assert len(data) < 64 * 1024
    assert _refused(data) == "loft_zip_bomb"


def test_missing_tree_is_refused() -> None:
    entries = [e for e in _golden_entries() if e[0] != TREE_PATH]
    assert _refused(_zip(entries)) == "loft_member_missing"


def test_blob_sha_mismatch_is_refused() -> None:
    entries = [
        (name, b"tampered" if name.startswith("blobs/") else data)
        for name, data in _golden_entries()
    ]
    assert _refused(_zip(entries)) == "loft_blob_corrupt"


def test_hand_edited_tree_warns_and_drops_the_cache() -> None:
    entries = _golden_entries()
    tree = json.loads(entries[1][1])
    tree["name"] = "Edited by hand"
    edited = [entries[0], (TREE_PATH, canonical_json(tree)), *entries[2:]]
    archive = read_loft(_zip(edited))
    assert archive.tree.name == "Edited by hand"
    assert archive.cache is None
    assert [w.code for w in archive.warnings] == ["loft_tree_edited"]


def test_corrupt_cached_body_warns_and_drops_the_cache() -> None:
    entries = [
        (name, b"other" if name == BODY_STEP_PATH else data)
        for name, data in _golden_entries()
    ]
    archive = read_loft(_zip(entries))
    assert archive.cache is None
    assert [w.code for w in archive.warnings] == ["loft_cache_corrupt"]


def test_invalid_tree_is_refused() -> None:
    entries = _golden_entries()
    entries[1] = (TREE_PATH, b'{"name": "x", "features": [{"id": "nope"}]}')
    assert _refused(_zip(entries)) == "loft_tree_invalid"


# --- 3. versions --------------------------------------------------------------------


def test_newer_major_format_is_refused() -> None:
    data = _zip(_with_manifest(lambda m: m.update(format_version="2.0")))
    with pytest.raises(LoftFileError) as caught:
        read_loft(data)
    assert caught.value.code == "loft_format_too_new"
    assert "Upgrade Loft" in caught.value.message


def test_newer_minor_format_is_read_ignoring_what_it_adds() -> None:
    def newer(manifest: dict[str, Any]) -> None:
        manifest.update(format_version="1.7", thumbnail="thumb.png")

    data = _zip([*_with_manifest(newer), ("thumb.png", b"\x89PNG")])
    archive = read_loft(data)
    assert archive.manifest.format_version == "1.7"
    assert archive.tree.name == _golden_tree().name


def test_newer_minor_still_refuses_an_unsafe_member() -> None:
    def newer(manifest: dict[str, Any]) -> None:
        manifest.update(format_version="1.7")

    data = _zip([*_with_manifest(newer), ("../thumb.png", b"x")])
    assert _refused(data) == "loft_member_unsafe"


# --- review 191eed8: amplification and parser limits ----------------------------


def _blob_bomb(references: int) -> bytes:
    """One 16 MiB blob (ratio-legal: random hex text) named by N import features."""
    rng = random.Random(7)
    chunk = "".join(rng.choice("0123456789abcdef") for _ in range(2 * 1024 * 1024))
    data = (chunk * 8)[: loft_file.MAX_LOFT_BLOB_BYTES].encode()
    digest = sha256_hex(data)
    tree = _golden_tree().model_dump(mode="json")
    template = tree["features"][0]
    tree["features"] = [
        {
            **template,
            "id": str(uuid.UUID(int=index + 1)),
            "params": {**template["params"], "data": f"loft-blob:sha256:{digest}"},
        }
        for index in range(references)
    ]
    entries = [e for e in _golden_entries() if not e[0].startswith("blobs/")]
    entries[1] = (TREE_PATH, canonical_json(tree))
    entries.append((f"blobs/sha256-{digest}.step", data))
    return _zip(entries, compression=zipfile.ZIP_DEFLATED)


def test_a_blob_named_by_many_features_is_refused_before_it_is_copied() -> None:
    data = _blob_bomb(1000)
    tracemalloc.start()
    try:
        assert _refused(data) == "loft_blob_reused"
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # One raw blob plus the reader's working set, not a thousand decoded
    # copies (~16 GiB before the fix).
    assert peak < 64 * 1024 * 1024, peak


def test_a_blob_ref_outside_an_import_feature_is_not_inlined() -> None:
    entries = _golden_entries()
    tree = json.loads(entries[1][1])
    ref = tree["features"][0]["params"]["data"]
    tree["features"][1]["params"]["data"] = ref
    entries[1] = (TREE_PATH, canonical_json(tree))
    archive = read_loft(_zip(entries))
    assert archive.tree.features[0].params["data"] == STEP_TEXT
    assert archive.tree.features[1].params["data"] == ref


def test_a_lying_entry_count_cannot_make_the_directory_parse_expensive() -> None:
    """20k members declared as 1: refused from the directory SIZE, unparsed."""
    data = bytearray(_zip([(f"x{index}", b"") for index in range(20_000)]))
    eocd = data.rfind(b"PK\x05\x06")
    data[eocd + 8 : eocd + 12] = (1).to_bytes(2, "little") * 2
    started = time.perf_counter()
    assert _refused(bytes(data)) == "loft_too_many_members"
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize(
    "tree",
    [b'{"name": "x", "features": [], "w": 1e999}', b"[" * 100_000 + b"]" * 100_000],
    ids=["non-finite", "deep-nesting"],
)
def test_non_finite_numbers_and_deep_nesting_are_typed_refusals(tree: bytes) -> None:
    entries = _golden_entries()
    entries[1] = (TREE_PATH, tree)
    assert _refused(_zip(entries)) == "loft_tree_invalid"


def _zip64_probe(members: int) -> bytes:
    """The reviewer's probe: a real ZIP64 directory of *members* entries, whose
    classic end record claims 1 entry and 100 bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(members):
            archive.writestr(f"x{index}", b"")
    data = bytearray(buffer.getvalue())
    eocd = data.rfind(b"PK\x05\x06")
    assert data[eocd - 20 : eocd - 16] == b"PK\x06\x07"  # zipfile wrote ZIP64
    data[eocd + 8 : eocd + 12] = (1).to_bytes(2, "little") * 2
    data[eocd + 12 : eocd + 16] = (100).to_bytes(4, "little")
    return bytes(data)


def test_a_zip64_directory_is_refused_before_it_is_parsed() -> None:
    data = _zip64_probe(70_000)  # past 0xFFFF entries, so zipfile writes ZIP64
    tracemalloc.start()
    started = time.perf_counter()
    try:
        assert _refused(data) == "loft_zip_invalid"
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert elapsed < 1.0, elapsed
    assert peak < 16 * 1024 * 1024, peak


# --- 4. named versions (format 1.1) ----------------------------------------------


def _golden_v11_entries() -> list[tuple[str, bytes]]:
    return list(_members(GOLDEN.read_bytes()).items())


def _replace(
    entries: list[tuple[str, bytes]], name: str, data: bytes | None
) -> list[tuple[str, bytes]]:
    """*entries* with member *name* replaced (or dropped, for None)."""
    return [
        (member, data if member == name and data is not None else content)
        for member, content in entries
        if not (member == name and data is None)
    ]


def test_too_many_versions_is_refused_on_read() -> None:
    entries = _golden_v11_entries()
    index = json.loads(dict(entries)[VERSIONS_INDEX_PATH])
    template = index["versions"][0]
    index["versions"] = [
        {**template, "seq": seq} for seq in range(1, loft_file.MAX_LOFT_VERSIONS + 2)
    ]
    data = _zip(_replace(entries, VERSIONS_INDEX_PATH, canonical_json(index)))
    assert _refused(data) == "loft_too_many_versions"


def test_too_many_versions_is_refused_on_write() -> None:
    version = _golden_versions()[1]
    versions = [
        version.model_copy(update={"seq": seq})
        for seq in range(1, loft_file.MAX_LOFT_VERSIONS + 2)
    ]
    with pytest.raises(LoftFileError) as caught:
        pack_part(
            document_id=PART_ID,
            tree=_golden_tree(),
            loft_version="t",
            versions=versions,
        )
    assert caught.value.code == "loft_too_many_versions"


@pytest.mark.parametrize(
    ("member", "cap"),
    [
        (VERSIONS_INDEX_PATH, "MAX_LOFT_VERSION_INDEX_BYTES"),
        ("versions/1.tree.json", "MAX_LOFT_VERSION_TREE_BYTES"),
    ],
)
def test_version_member_caps(
    member: str, cap: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each cap refuses one byte over it, on read AND on write."""
    size = len(dict(_golden_v11_entries())[member])
    monkeypatch.setattr(loft_file, cap, size - 1)
    assert _refused(GOLDEN.read_bytes()) == "loft_member_too_large"
    with pytest.raises(LoftFileError) as caught:
        _golden_bytes()
    assert caught.value.code == "loft_member_too_large"


def test_the_total_cap_counts_the_step_text_every_version_inlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three trees name one blob: it is stored once but inlined three times, and
    the reader's budget (and so the writer's) counts every copy."""
    entries = _golden_v11_entries()
    stored = sum(len(data) for _, data in entries)
    beside_manifest = sum(len(data) for name, data in entries if name != MANIFEST_PATH)
    step = len(STEP_TEXT.encode())
    # One byte short of three copies, even by the reader's (looser) measure.
    monkeypatch.setattr(
        loft_file, "MAX_LOFT_TOTAL_BYTES", beside_manifest + 3 * step - 1
    )
    assert _refused(GOLDEN.read_bytes()) == "loft_member_too_large"
    with pytest.raises(LoftFileError) as caught:
        _golden_bytes()
    assert caught.value.code == "loft_member_too_large"
    monkeypatch.setattr(loft_file, "MAX_LOFT_TOTAL_BYTES", stored + 3 * step)
    assert read_loft(_golden_bytes()).versions


def test_a_version_tree_the_index_does_not_list_is_refused() -> None:
    entries = [*_golden_v11_entries(), ("versions/9.tree.json", b"{}")]
    assert _refused(_zip(entries)) == "loft_versions_invalid"


def test_an_index_entry_without_its_tree_is_refused() -> None:
    entries = _replace(_golden_v11_entries(), "versions/2.tree.json", None)
    assert _refused(_zip(entries)) == "loft_member_missing"


def test_version_trees_without_an_index_are_refused() -> None:
    entries = _replace(_golden_v11_entries(), VERSIONS_INDEX_PATH, None)
    assert _refused(_zip(entries)) == "loft_versions_invalid"


def _reverse(index: dict[str, Any]) -> None:
    index["versions"].reverse()


def _duplicate_seq(index: dict[str, Any]) -> None:
    index["versions"][0]["seq"] = 2


def _long_author(index: dict[str, Any]) -> None:
    index["versions"][0]["author"] = "x" * 81


def _naive_time(index: dict[str, Any]) -> None:
    index["versions"][0]["created_at"] = "2026-10-01T09:00:00"


@pytest.mark.parametrize(
    "edit",
    [_reverse, _duplicate_seq, _long_author, _naive_time],
    ids=["descending", "duplicate-seq", "author-too-long", "naive-time"],
)
def test_an_invalid_index_is_refused(edit: Callable[[dict[str, Any]], None]) -> None:
    entries = _golden_v11_entries()
    index = json.loads(dict(entries)[VERSIONS_INDEX_PATH])
    edit(index)
    data = _zip(_replace(entries, VERSIONS_INDEX_PATH, canonical_json(index)))
    assert _refused(data) == "loft_versions_invalid"


@pytest.mark.parametrize(
    "name", ["versions/0.tree.json", "versions/01.tree.json", "versions/x.json"]
)
def test_a_version_member_outside_the_pattern_is_refused(name: str) -> None:
    data = _zip([*_golden_v11_entries(), (name, b"{}")])
    assert _refused(data) == "loft_member_unknown"


def test_a_hand_edited_version_warns_and_imports_as_it_reads() -> None:
    entries = _golden_v11_entries()
    tree = json.loads(dict(entries)["versions/1.tree.json"])
    tree["name"] = "Edited by hand"
    data = _zip(_replace(entries, "versions/1.tree.json", canonical_json(tree)))
    archive = read_loft(data)
    assert [w.code for w in archive.warnings] == ["loft_version_edited"]
    assert archive.versions[0].tree.name == "Edited by hand"
    assert archive.cache is not None  # tree.json itself is untouched


def test_an_invalid_version_tree_is_refused_naming_it() -> None:
    entries = _replace(
        _golden_v11_entries(), "versions/1.tree.json", b'{"name": "x", "features": 1}'
    )
    with pytest.raises(LoftFileError) as caught:
        read_loft(_zip(entries))
    assert caught.value.code == "loft_tree_invalid"
    assert caught.value.details["member"] == "versions/1.tree.json"


def test_a_blob_named_twice_in_one_version_is_still_refused() -> None:
    entries = _golden_v11_entries()
    tree = json.loads(dict(entries)["versions/1.tree.json"])
    tree["features"].append({**tree["features"][0], "id": str(uuid.uuid4())})
    data = _zip(_replace(entries, "versions/1.tree.json", canonical_json(tree)))
    assert _refused(data) == "loft_blob_reused"
