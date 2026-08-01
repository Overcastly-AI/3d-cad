"""GLB face-primitive fusion (PERF-4b) — the face-identity contract.

``tessellate.fuse_faces`` rewrites OCCT's one-primitive-per-B-rep-face payload
into a few large primitives plus a per-face triangle side table. Every
downstream face reference in the product — ``on_face`` datums, shell openings,
hole placement, sketch-on-face, the feature-localized selection tint — is keyed
on a face ORDINAL, so the only thing that makes the rewrite safe is that the
side table reproduces the original partition EXACTLY.

These tests assert that at the strongest available level: for every face
ordinal, the fused payload's triangle stream (positions AND normals, in order)
is byte-identical to the unfused primitive's. Not "the same number of
triangles" — the same triangles. The viewport half of the same contract is
``apps/web/src/viewport/glbGeometry.test.ts``, which parses BOTH encodings of
one real part and asserts they resolve every triangle to the same face.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import Box, Compound, Cylinder, Pos, Unit
from build123d.exporters3d import (
    export_gltf,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.kernel.tessellate import (
    ANGULAR_DEFLECTION,
    FACE_TRIANGLES_KEY,
    FUSE_MAX_TRIANGLES_PER_FACE,
    _read_accessor,  # pyright: ignore[reportPrivateUsage]
    _split_glb,  # pyright: ignore[reportPrivateUsage]
    face_triangle_counts,
    fuse_faces,
    glb_primitive_count,
    glb_stats,
    tessellate_glb,
)
from geometry.kernel.types import BodyShape


#: Two planar bodies with UNEVEN triangle counts per face (a notch and a
#: through slot each split a face into 4 and 8 triangles). Even triangle counts
#: everywhere would let an off-by-one side table pass. Same part as the
#: viewport fixtures — see ``apps/web/src/viewport/__fixtures__/README.md``.
def _two_bodies() -> Compound:
    notched = (Box(30, 20, 10) - Pos(12, 7, 4) * Box(10, 10, 10)).solid()
    plate = (Box(24, 16, 6) - Pos(0, 0, 1) * Box(10, 6, 6)).solid()
    return Compound(children=[notched, (Pos(0, 40, 0) * plate).solid()])


def _unfused(shape: BodyShape, deflection: float = 0.1) -> bytes:
    """What ``RWGltf_CafWriter`` writes: one primitive per B-rep face."""
    with tempfile.TemporaryDirectory(prefix="loft-fuse-test-") as tmp:
        target = Path(tmp) / "shape.glb"
        assert export_gltf(
            shape,
            target,
            unit=Unit.MM,
            binary=True,
            linear_deflection=deflection,
            angular_deflection=ANGULAR_DEFLECTION,
        )
        return target.read_bytes()


def _face_streams(glb: bytes) -> list[tuple[bytes, bytes]]:
    """``(positions, normals)`` of each face's triangles, in face order.

    Reads whichever encoding the payload uses, so the same helper describes the
    unfused and fused payloads and the two can be compared directly.
    """
    document, blob = _split_glb(glb)
    streams: list[tuple[bytes, bytes]] = []
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            indices = _read_accessor(document, blob, int(primitive["indices"]))
            flat = indices.reshape(-1)
            position = _read_accessor(
                document, blob, int(primitive["attributes"]["POSITION"])
            )
            normal = _read_accessor(
                document, blob, int(primitive["attributes"]["NORMAL"])
            )
            table: list[int] = primitive.get("extras", {}).get(
                FACE_TRIANGLES_KEY, [int(flat.size) // 3]
            )
            offset = 0
            for triangles in table:
                span = flat[offset * 3 : (offset + triangles) * 3]
                streams.append((position[span].tobytes(), normal[span].tobytes()))
                offset += triangles
    return streams


def test_every_face_keeps_its_exact_triangles() -> None:
    """Face ordinal *i* names the same triangles before and after fusion."""
    shape = _two_bodies()
    unfused = _unfused(shape)
    fused = fuse_faces(unfused)
    assert fused != unfused, "this part is expected to fuse"

    before = _face_streams(unfused)
    after = _face_streams(fused)
    assert len(before) == len(after) == len(shape.faces())
    for ordinal, (want, got) in enumerate(zip(before, after, strict=True)):
        assert want == got, f"face {ordinal}: triangle stream changed"


def test_face_table_matches_the_brep_face_count() -> None:
    """One side-table entry per B-rep face, in ``body.faces()`` order."""
    shape = _two_bodies()
    counts = face_triangle_counts(fuse_faces(_unfused(shape)))
    assert counts is not None
    assert len(counts) == len(shape.faces())
    assert sum(counts) == glb_stats(_unfused(shape)).triangles


def test_fusion_collapses_primitives_without_moving_the_mesh() -> None:
    """Fewer primitives, same vertices and triangles — the whole point."""
    unfused = _unfused(_two_bodies())
    fused = fuse_faces(unfused)
    assert glb_primitive_count(unfused) == 20
    assert glb_primitive_count(fused) == 2  # one per body/mesh
    assert len(fused) < len(unfused)
    before = glb_stats(unfused)
    after = glb_stats(fused)
    assert (before.vertices, before.triangles) == (after.vertices, after.triangles)
    assert after.glb_bytes == len(fused)


def test_triangle_dense_faces_are_left_alone() -> None:
    """A part above the density threshold keeps OCCT's bytes, bit for bit.

    Re-basing indices costs more gzip than the removed JSON saves once faces
    carry many triangles (docs/PERF.md "PERF-4b"), so declining is the correct
    answer — and declining must be a true no-op, not a re-encode.
    """
    unfused = _unfused(Cylinder(5, 10).solid())
    stats = glb_stats(unfused)
    density = stats.triangles / glb_primitive_count(unfused)
    assert density > FUSE_MAX_TRIANGLES_PER_FACE, "fixture is not dense enough"
    assert fuse_faces(unfused) is unfused
    assert face_triangle_counts(unfused) is None


def test_unrecognised_payloads_fall_back_to_the_original() -> None:
    """An extension we do not model must not be silently mangled."""
    document, blob = _split_glb(_unfused(_two_bodies()))
    document["extensionsUsed"] = ["KHR_materials_unlit"]
    from geometry.kernel.tessellate import (
        _build_glb,  # pyright: ignore[reportPrivateUsage]
    )

    payload = _build_glb(document, blob)
    assert fuse_faces(payload) is payload


def test_fusion_is_deterministic() -> None:
    """``mesh_glb_id`` is a content hash — the encoding may not wobble."""
    unfused = _unfused(_two_bodies())
    assert fuse_faces(unfused) == fuse_faces(unfused)
    shape = _two_bodies()
    first, _ = tessellate_glb(shape, 0.1)
    second, _ = tessellate_glb(shape, 0.1)
    assert first == second


def test_positions_are_not_welded_across_faces() -> None:
    """Faces must keep their OWN vertices — the per-body split depends on it.

    ``apps/web/src/viewport/bodyPartition.ts`` derives the per-body face sets
    from connected components, which is only exact because faces of one solid
    share coordinates but never buffer indices. Concatenating primitives must
    not start welding them.
    """
    fused = fuse_faces(_unfused(_two_bodies()))
    document, blob = _split_glb(fused)
    counts = face_triangle_counts(fused)
    assert counts is not None
    face = 0
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            # Vertex indices are per-primitive, so ownership is checked within
            # each fused primitive — that is where welding could happen.
            owners: dict[int, int] = {}
            flat = _read_accessor(document, blob, int(primitive["indices"])).reshape(-1)
            offset = 0
            for triangles in primitive["extras"][FACE_TRIANGLES_KEY]:
                for vertex in flat[offset * 3 : (offset + triangles) * 3]:
                    assert owners.setdefault(int(vertex), face) == face, (
                        f"vertex {vertex} is shared between faces"
                    )
                offset += triangles
                face += 1
    assert face == len(counts)


def test_fused_payload_is_a_well_formed_glb() -> None:
    """Chunk lengths, alignment and accessor bounds — a loader will refuse less."""
    fused = fuse_faces(_unfused(_two_bodies()))
    assert len(fused) % 4 == 0
    document, blob = _split_glb(fused)
    assert document["buffers"] == [{"byteLength": len(blob)}]
    for view in document["bufferViews"]:
        assert view["byteOffset"] % 4 == 0
        assert view["byteOffset"] + view["byteLength"] <= len(blob)
    for accessor in document["accessors"]:
        assert accessor["count"] >= 1
        if accessor["type"] == "VEC3" and "max" in accessor:
            assert len(accessor["max"]) == 3 and len(accessor["min"]) == 3
    # The JSON chunk must still be parseable on its own (no stray padding bytes
    # inside it) — re-parsing is how the viewport reads the side table.
    assert json.loads(json.dumps(document)) == document


def test_vertex_cap_splits_instead_of_widening_indices() -> None:
    """A body past the cap fuses into several UNSIGNED_SHORT primitives.

    Widening to ``UNSIGNED_INT`` would double the index buffer and hand back
    what fusion saves, so the cap splits the run instead — and the face table
    must still line up across the split.
    """
    fins = [(Pos(i * 3.0, 0, 0) * Box(1.0, 20.0, 12.0)).solid() for i in range(60)]
    shape = Compound(children=[Box(200, 20, 4).solid(), *fins])
    unfused = _unfused(shape)
    fused = fuse_faces(unfused)
    assert glb_primitive_count(fused) > 1
    assert glb_primitive_count(fused) < glb_primitive_count(unfused)
    document, _ = _split_glb(fused)
    for accessor in document["accessors"]:
        assert accessor["componentType"] != 5125, "index buffer was widened"
    assert _face_streams(unfused) == _face_streams(fused)


@pytest.mark.parametrize(
    "shape",
    [
        Box(10, 20, 30).solid(),
        Compound(
            children=[Box(4, 4, 4).solid(), (Pos(20, 0, 0) * Box(6, 6, 6)).solid()]
        ),
    ],
    ids=["box", "two-boxes"],
)
def test_tessellate_glb_reports_the_fused_payload(shape: BodyShape) -> None:
    """``MeshStats`` describes the artifact that ships, not a pre-fusion one."""
    glb, stats = tessellate_glb(shape, 0.1)
    assert stats.glb_bytes == len(glb)
    counts = face_triangle_counts(glb)
    assert counts is not None and len(counts) == len(shape.faces())
    assert sum(counts) == stats.triangles


def test_read_accessor_handles_a_strided_buffer_view() -> None:
    """Interleaved attributes are legal glTF; the reader must not assume packed."""
    values = np.arange(12, dtype=np.float32).reshape(4, 3)
    padded = np.zeros((4, 4), dtype=np.float32)
    padded[:, :3] = values
    document: dict[str, Any] = {
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 4,
                "type": "VEC3",
            }
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteStride": 16}],
    }
    got = _read_accessor(document, padded.tobytes(), 0)
    assert np.array_equal(got, values)
