"""The ``.loft`` container: canonical bytes, and a reader that refuses hostile zips.

Three claims, each pinned here:

1. **Same part, same bytes.** The golden fixture is checked byte-for-byte, and a
   file that is read and packed again comes back identical (the repack test).
   Regenerate the golden ONLY for a deliberate format change:
   ``LOFT_REGEN_GOLDEN=1 uv run pytest packages/loft-wire/tests/test_loft_file.py``.
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
from pathlib import Path
from typing import Any

import pytest
from loft_wire import loft_file
from loft_wire.geometry import BoundingBox
from loft_wire.loft_file import (
    BODY_STEP_PATH,
    MANIFEST_PATH,
    TREE_PATH,
    LoftCacheProperties,
    LoftFileError,
    LoftTree,
    canonical_json,
    pack_part,
    read_loft,
    sha256_hex,
)

FIXTURE = Path(__file__).parent / "fixtures" / "golden-v1.loft"

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


def _golden_bytes() -> bytes:
    return pack_part(
        document_id=PART_ID,
        tree=_golden_tree(),
        loft_version="golden",
        body_step=BODY_STEP,
        properties=GOLDEN_PROPERTIES,
    )


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


# --- 1. canonical bytes -------------------------------------------------------------


def test_golden_fixture_byte_for_byte() -> None:
    """Pinned bytes. A diff here is a FORMAT change: bump the version or revert."""
    produced = _golden_bytes()
    if os.environ.get("LOFT_REGEN_GOLDEN") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_bytes(produced)
    expected = FIXTURE.read_bytes()
    if produced != expected:
        # Say WHICH layer moved before failing: a member's content, or only the
        # deflate stream (a different zlib build), are different conversations.
        same_members = _members(produced) == _members(expected)
        pytest.fail(
            "golden-v1.loft changed: "
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
    assert manifest["format_version"] == "1.0"
    assert manifest["units"] == {"storage": "mm"}
    for name, digest in manifest["members"].items():
        assert sha256_hex(members[name]) == digest
    assert manifest["cache"]["built_from_tree_sha256"] == manifest["tree_sha256"]


def test_repack_is_byte_identical() -> None:
    """read -> pack gives the same bytes: nothing is lost or reordered on the way."""
    original = FIXTURE.read_bytes()
    archive = read_loft(original)
    assert archive.warnings == ()
    assert archive.tree.features[0].params["data"] == STEP_TEXT
    members = _members(original)
    repacked = pack_part(
        document_id=archive.manifest.document_id,
        tree=archive.tree,
        loft_version=archive.manifest.loft_version,
        body_step=members[BODY_STEP_PATH],
        properties=archive.cache.properties if archive.cache else None,
    )
    assert repacked == original


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
