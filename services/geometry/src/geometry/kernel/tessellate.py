"""Shape tessellation to binary glTF (GLB).

Uses build123d's ``export_gltf`` (OCCT ``RWGltf_CafWriter`` underneath) via a
tempfile — the writer only speaks paths. Output is deterministic: the same
shape and deflection produce byte-identical GLB across runs and processes
(asserted by the test suite; RESEARCH §9 determinism gate).

Mesh statistics are parsed from the GLB itself, so they describe the actual
artifact rather than a parallel meshing pass.

**Face primitives are FUSED before the payload leaves this module** (PERF-4b),
*when fusing pays*. ``RWGltf_CafWriter`` writes one glTF primitive — and with it
three accessors, so three more JSON objects — per B-rep face. Measured at ~425
bytes of glTF JSON per face, which on a 2 006-face part is ~850 KiB of JSON
before a single vertex. :func:`fuse_faces` concatenates the primitives of each
material run into ONE primitive and records the per-face triangle counts in a
compact side table on the primitive's ``extras`` (:data:`FACE_TRIANGLES_KEY`).

The side table, not a per-vertex attribute, is the encoding because the
information is a RUN-LENGTH by construction: a fused primitive's triangles stay
in face order, so face *i* owns a contiguous index range and the whole partition
is described by one integer per face. A ``_FACE_ID`` vertex attribute would have
spent 4 bytes per VERTEX (~160 KiB raw on the 442-face tray) to say the same
thing. The viewport reconstructs exactly today's per-face draw groups from the
table, so ``group ordinal == face ordinal == OverlayFace.index`` is unchanged —
that invariant is what every downstream face reference is keyed on.

Fusion is byte-for-byte geometry-preserving: it copies the same vertex and index
data into fewer accessors, so vertex/triangle counts, positions and normals are
identical to the unfused payload (asserted in ``test_tessellate_fuse.py``).

**Why it is conditional (measured, docs/PERF.md "PERF-4b").** Fusing re-bases
each face's indices onto the shared vertex buffer, which destroys the thing that
made the index buffer compress: unfused, faces with the same topology have
*byte-identical* local index runs (every quad is ``0,1,2,2,1,3``) and deflate
matches them across the whole buffer. Since PERF-4a the wire is gzipped, so that
matters. Measured cost ~2.3 gzip-bytes per triangle against a ~25-33 gzip-byte
saving per face, i.e. fusion pays exactly while a part has FEW triangles per
face. A deflection sweep on one fixed topology puts the break-even at **~20
triangles per face** (117-face tray: 41.9 t/f -> +45.7 %, 20.3 t/f -> -0.0 %,
8.8 t/f -> -22.6 %), so :data:`FUSE_MAX_TRIANGLES_PER_FACE` sits at 12 for
margin. The 2 006-face sink (4.0 t/f) fuses and halves on the wire; the 442-face
tray (71.6 t/f) declines and keeps today's bytes exactly.
"""

import json
import struct
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from build123d import Unit
from build123d.exporters3d import (
    export_gltf,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
)
from numpy.typing import NDArray

from geometry.kernel.types import BodyShape
from geometry.schemas import DEFAULT_ANGULAR_DEFLECTION, MeshStats

#: Max angle (rad) between adjacent tessellation segments. Fixed service-wide
#: so a given ``linear_deflection`` always means the same mesh. Single source
#: is py-kit's DEFAULT_ANGULAR_DEFLECTION — also the STL export default, so
#: default-quality STL matches the viewport mesh.
ANGULAR_DEFLECTION = DEFAULT_ANGULAR_DEFLECTION

GLB_MAGIC = b"glTF"
_GLB_HEADER = struct.Struct("<4sII")  # magic, version, total length
_GLB_CHUNK_HEADER = struct.Struct("<I4s")  # chunk length, chunk type

#: glTF primitive ``extras`` key holding the fused primitive's per-face triangle
#: counts, in face order. Concatenating these lists over every primitive in
#: document order reproduces ``body.faces()`` order — face ordinal *i* owns the
#: triangles ``sum(counts[:i]) .. sum(counts[:i+1])`` of that primitive. Read by
#: ``apps/web/src/viewport/glbGeometry.ts``; the two ends share only this string.
FACE_TRIANGLES_KEY = "LOFT_face_triangles"

#: Cap on the vertices fused into one primitive. Small caps keep index VALUES
#: small, which keeps them compressible; large caps spend fewer JSON bytes on
#: primitives. Measured optimum on the gzipped payload (500-fin sink, level 6):
#: 256 -> 45 889 B, **512 -> 45 086 B**, 1 024 -> 45 689 B, 16 384 -> 57 779 B.
#: 512 also keeps indices in ``UNSIGNED_SHORT`` by construction — widening to
#: ``UNSIGNED_INT`` would double the index buffer and hand back the saving.
_MAX_FUSED_VERTICES = 512

#: Fuse only while a body averages at or below this many triangles per B-rep
#: face. Above it, re-basing indices costs more gzip than the removed JSON
#: saves (module docstring; break-even measured at ~20, this is the margin).
FUSE_MAX_TRIANGLES_PER_FACE = 12

_TRIANGLES_MODE = 4
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_UNSIGNED_SHORT = 5123
_UNSIGNED_INT = 5125
_FLOAT = 5126

_COMPONENT_DTYPE: dict[int, str] = {
    5120: "<i1",
    5121: "<u1",
    5122: "<i2",
    5123: "<u2",
    5125: "<u4",
    _FLOAT: "<f4",
}
_TYPE_COMPONENTS: dict[str, int] = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}

#: Document-level keys whose presence means the payload references bufferViews
#: or accessors this rewriter does not track. Fusion declines rather than
#: guesses — ``RWGltf_CafWriter`` emits none of them for a static XDE document,
#: so this is a guard, not a routine path.
_UNFUSABLE_KEYS = (
    "animations",
    "skins",
    "images",
    "textures",
    "extensionsRequired",
    "extensionsUsed",
)


class _Unfusable(Exception):
    """A payload shape this rewriter declines to touch (caller keeps the original)."""


def tessellate_glb(
    shape: BodyShape, linear_deflection: float
) -> tuple[bytes, MeshStats]:
    """Tessellate *shape* and return ``(glb_bytes, mesh_stats)``.

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid`, or
    a :class:`~build123d.Compound` of a multi-body part's disjoint solids
    (docs/design/multi-body.md §MB-0), which ``RWGltf_CafWriter`` writes as a
    multi-mesh scene :func:`glb_stats` sums over. The GLB scene is Y-up in metres
    per the glTF spec (build123d converts from OCCT's Z-up millimetres).
    """
    if linear_deflection <= 0:
        raise ValueError(f"linear_deflection must be > 0, got {linear_deflection}")

    with tempfile.TemporaryDirectory(prefix="loft-glb-") as tmp:
        target = Path(tmp) / "shape.glb"
        ok = export_gltf(
            shape,
            target,
            unit=Unit.MM,
            binary=True,
            linear_deflection=linear_deflection,
            angular_deflection=ANGULAR_DEFLECTION,
        )
        if not ok:
            raise RuntimeError("glTF export failed")
        glb = target.read_bytes()

    glb = fuse_faces(glb)
    return glb, glb_stats(glb)


def fuse_faces(glb: bytes) -> bytes:
    """Rewrite *glb* with one primitive per material run instead of per face.

    Geometry-preserving by construction: the same vertex and index values are
    copied into fewer accessors, and each output primitive carries its per-face
    triangle counts under ``extras[FACE_TRIANGLES_KEY]`` so a reader can rebuild
    the exact per-face partition (see the module docstring).

    Returns *glb* unchanged when the payload is not of the shape this rewriter
    understands (a glTF extension, a texture, a non-triangle primitive). That is
    a safe fallback, not a silent one: without the side table the viewport falls
    back to one draw group per primitive, which is the pre-PERF-4b behaviour.
    """
    try:
        return _fuse_faces(glb)
    except _Unfusable:
        return glb


def _fuse_faces(glb: bytes) -> bytes:
    document, blob = _split_glb(glb)
    for key in _UNFUSABLE_KEYS:
        if document.get(key):
            raise _Unfusable(key)
    meshes: list[dict[str, Any]] = document.get("meshes", [])
    if not meshes:
        raise _Unfusable("no meshes")
    if _triangles_per_face(document) > FUSE_MAX_TRIANGLES_PER_FACE:
        # Dense faces: the index-compressibility cost outruns the JSON saving.
        # Declining returns the ORIGINAL bytes, so such a part is bit-for-bit
        # what it was before PERF-4b — no regression, measured not assumed.
        raise _Unfusable("triangle-dense faces")

    out_blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    for mesh in meshes:
        primitives: list[dict[str, Any]] = mesh["primitives"]
        if not primitives:
            raise _Unfusable("empty mesh")
        fused: list[dict[str, Any]] = []
        for chunk in _fusable_chunks(document, primitives):
            fused.append(
                _emit_fused_primitive(document, blob, chunk, out_blob, views, accessors)
            )
        mesh["primitives"] = fused

    document["accessors"] = accessors
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(out_blob)}]
    return _build_glb(document, bytes(out_blob))


def _triangles_per_face(document: dict[str, Any]) -> float:
    """Mean triangles per glTF primitive — one primitive is one B-rep face here."""
    accessors: list[dict[str, Any]] = document["accessors"]
    faces = 0
    triangles = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            faces += 1
            if "indices" in primitive:
                triangles += int(accessors[int(primitive["indices"])]["count"]) // 3
    return triangles / faces if faces else 0.0


def _split_glb(glb: bytes) -> tuple[dict[str, Any], bytes]:
    """``(json_document, binary_chunk)`` of a GLB v2 payload."""
    magic, version, length = _GLB_HEADER.unpack_from(glb, 0)
    if magic != GLB_MAGIC or version != 2 or length != len(glb):
        raise ValueError("Not a well-formed GLB v2 payload")
    offset = _GLB_HEADER.size
    document: dict[str, Any] | None = None
    blob = b""
    while offset < len(glb):
        chunk_length, chunk_type = _GLB_CHUNK_HEADER.unpack_from(glb, offset)
        start = offset + _GLB_CHUNK_HEADER.size
        payload = glb[start : start + chunk_length]
        if chunk_type == b"JSON":
            document = json.loads(payload.decode("utf-8"))
        elif chunk_type == b"BIN\x00":
            blob = payload
        offset = start + chunk_length
    if document is None:
        raise ValueError("GLB has no JSON chunk")
    return document, blob


def _build_glb(document: dict[str, Any], blob: bytes) -> bytes:
    """Assemble a GLB v2 payload from a JSON document and a binary chunk.

    Compact separators and deterministic key order (``json.dumps`` preserves
    insertion order, and every dict here is built in a fixed order), so the same
    input always yields the same bytes — the ``mesh_glb_id`` content hash
    depends on it.
    """
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    bin_chunk = blob + b"\x00" * (-len(blob) % 4)
    total = (
        _GLB_HEADER.size + 2 * _GLB_CHUNK_HEADER.size + len(json_chunk) + len(bin_chunk)
    )
    return b"".join(
        (
            _GLB_HEADER.pack(GLB_MAGIC, 2, total),
            _GLB_CHUNK_HEADER.pack(len(json_chunk), b"JSON"),
            json_chunk,
            _GLB_CHUNK_HEADER.pack(len(bin_chunk), b"BIN\x00"),
            bin_chunk,
        )
    )


def _primitive_signature(primitive: dict[str, Any]) -> tuple[Any, ...]:
    """What must match for two primitives to fuse: material, mode, attributes."""
    if primitive.get("targets") or primitive.get("extras"):
        raise _Unfusable("primitive carries morph targets or extras")
    if primitive.get("mode", _TRIANGLES_MODE) != _TRIANGLES_MODE:
        raise _Unfusable("non-triangle primitive")
    if "indices" not in primitive:
        raise _Unfusable("non-indexed primitive")
    attributes: dict[str, int] = primitive["attributes"]
    return (primitive.get("material"), tuple(sorted(attributes)))


def _fusable_chunks(
    document: dict[str, Any], primitives: list[dict[str, Any]]
) -> list[list[dict[str, Any]]]:
    """Split *primitives* into runs that fuse into one primitive each.

    A run breaks on a material/attribute change (a fused primitive can carry
    only one material) or when it would exceed :data:`_MAX_FUSED_VERTICES`.
    Runs stay in document order, so concatenating their face tables reproduces
    face order — the invariant the viewport picks by.
    """
    accessors: list[dict[str, Any]] = document["accessors"]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    signature: tuple[Any, ...] | None = None
    vertices = 0
    for primitive in primitives:
        own = _primitive_signature(primitive)
        count = int(accessors[int(primitive["attributes"]["POSITION"])]["count"])
        if current and (own != signature or vertices + count > _MAX_FUSED_VERTICES):
            chunks.append(current)
            current = []
            vertices = 0
        signature = own
        current.append(primitive)
        vertices += count
    if current:
        chunks.append(current)
    return chunks


def _read_accessor(document: dict[str, Any], blob: bytes, index: int) -> NDArray[Any]:
    """Accessor *index* as an ``(count, components)`` array, honouring stride."""
    accessor: dict[str, Any] = document["accessors"][index]
    if "sparse" in accessor or "bufferView" not in accessor:
        raise _Unfusable("sparse or bufferView-less accessor")
    components = _TYPE_COMPONENTS.get(accessor["type"])
    dtype_name = _COMPONENT_DTYPE.get(int(accessor["componentType"]))
    if components is None or dtype_name is None:
        raise _Unfusable("unsupported accessor type")
    dtype = np.dtype(dtype_name)
    count = int(accessor["count"])
    view: dict[str, Any] = document["bufferViews"][int(accessor["bufferView"])]
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    packed = components * dtype.itemsize
    stride = int(view.get("byteStride", 0)) or packed
    if stride == packed:
        flat = np.frombuffer(blob, dtype=dtype, count=count * components, offset=start)
        return flat.reshape(count, components)
    rows = np.empty((count, components), dtype=dtype)
    for row in range(count):
        rows[row] = np.frombuffer(
            blob, dtype=dtype, count=components, offset=start + row * stride
        )
    return rows


def _add_view(
    out_blob: bytearray,
    views: list[dict[str, Any]],
    data: bytes,
    *,
    stride: int | None,
    target: int,
) -> int:
    """Append *data* to the binary chunk as a new bufferView; return its index."""
    out_blob.extend(b"\x00" * (-len(out_blob) % 4))
    view: dict[str, Any] = {
        "buffer": 0,
        "byteOffset": len(out_blob),
        "byteLength": len(data),
    }
    if stride is not None:
        view["byteStride"] = stride
    view["target"] = target
    out_blob.extend(data)
    views.append(view)
    return len(views) - 1


def _emit_fused_primitive(
    document: dict[str, Any],
    blob: bytes,
    chunk: list[dict[str, Any]],
    out_blob: bytearray,
    views: list[dict[str, Any]],
    accessors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Concatenate *chunk*'s primitives into one, with the per-face side table."""
    source: list[dict[str, Any]] = document["accessors"]
    names = sorted(chunk[0]["attributes"])
    attributes: dict[str, int] = {}
    for name in names:
        columns = [
            _read_accessor(document, blob, int(primitive["attributes"][name]))
            for primitive in chunk
        ]
        first = source[int(chunk[0]["attributes"][name])]
        for primitive in chunk[1:]:
            other = source[int(primitive["attributes"][name])]
            if (
                other["componentType"] != first["componentType"]
                or other["type"] != first["type"]
                or other.get("normalized") != first.get("normalized")
            ):
                raise _Unfusable(f"attribute {name} changes format mid-mesh")
        values = np.concatenate(columns)
        accessor: dict[str, Any] = {
            "bufferView": _add_view(
                out_blob,
                views,
                values.tobytes(),
                stride=values.shape[1] * values.dtype.itemsize,
                target=_ARRAY_BUFFER,
            ),
            "byteOffset": 0,
            "componentType": int(first["componentType"]),
            "count": int(values.shape[0]),
            "type": str(first["type"]),
        }
        if name == "POSITION":
            # Required by the glTF spec for POSITION, and the loader's bounding
            # volume. Recomputed from the very bytes written, so it cannot drift
            # from them.
            accessor["max"] = [float(v) for v in values.max(axis=0)]
            accessor["min"] = [float(v) for v in values.min(axis=0)]
        if first.get("normalized"):
            accessor["normalized"] = True
        accessors.append(accessor)
        attributes[name] = len(accessors) - 1

    face_triangles: list[int] = []
    index_columns: list[NDArray[Any]] = []
    offset = 0
    for primitive in chunk:
        indices = _read_accessor(document, blob, int(primitive["indices"]))
        index_columns.append(indices.reshape(-1).astype(np.int64) + offset)
        face_triangles.append(int(indices.size) // 3)
        offset += int(source[int(primitive["attributes"]["POSITION"])]["count"])
    joined = np.concatenate(index_columns)
    if offset == 0 or joined.size == 0:
        raise _Unfusable("empty primitive run")
    wide = offset > 65_536
    index_dtype = np.dtype("<u4") if wide else np.dtype("<u2")
    accessors.append(
        {
            "bufferView": _add_view(
                out_blob,
                views,
                joined.astype(index_dtype).tobytes(),
                stride=None,
                target=_ELEMENT_ARRAY_BUFFER,
            ),
            "byteOffset": 0,
            "componentType": _UNSIGNED_INT if wide else _UNSIGNED_SHORT,
            "count": int(joined.size),
            "type": "SCALAR",
        }
    )

    primitive_out: dict[str, Any] = {
        "attributes": attributes,
        "extras": {FACE_TRIANGLES_KEY: face_triangles},
        "indices": len(accessors) - 1,
        "mode": _TRIANGLES_MODE,
    }
    material = chunk[0].get("material")
    if material is not None:
        primitive_out["material"] = material
    return primitive_out


def face_triangle_counts(glb: bytes) -> list[int] | None:
    """Per-face triangle counts of *glb*, in face order — ``None`` if unfused.

    The kernel-side mirror of what the viewport reads: the concatenation of
    every primitive's :data:`FACE_TRIANGLES_KEY` table in document order.
    """
    document, _ = _split_glb(glb)
    counts: list[int] = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            table = primitive.get("extras", {}).get(FACE_TRIANGLES_KEY)
            if table is None:
                return None
            counts.extend(int(value) for value in table)
    return counts


def glb_primitive_count(glb: bytes) -> int:
    """Total glTF primitives in *glb* — the viewport's draw-group budget."""
    document, _ = _split_glb(glb)
    return sum(len(mesh.get("primitives", [])) for mesh in document.get("meshes", []))


def glb_stats(glb: bytes) -> MeshStats:
    """Parse a binary glTF payload and count its vertices and triangles."""
    magic, version, length = _GLB_HEADER.unpack_from(glb, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError(f"Not a GLB v2 payload (magic={magic!r}, version={version})")
    if length != len(glb):
        raise ValueError(f"GLB length mismatch: header says {length}, got {len(glb)}")

    chunk_length, chunk_type = _GLB_CHUNK_HEADER.unpack_from(glb, _GLB_HEADER.size)
    if chunk_type != b"JSON":
        raise ValueError(f"First GLB chunk must be JSON, got {chunk_type!r}")
    json_start = _GLB_HEADER.size + _GLB_CHUNK_HEADER.size
    document: dict[str, Any] = json.loads(
        glb[json_start : json_start + chunk_length].decode("utf-8")
    )

    accessors: list[dict[str, Any]] = document.get("accessors", [])
    meshes: list[dict[str, Any]] = document.get("meshes", [])
    vertices = 0
    triangles = 0
    for mesh in meshes:
        primitives: list[dict[str, Any]] = mesh.get("primitives", [])
        for primitive in primitives:
            attributes: dict[str, int] = primitive["attributes"]
            vertices += int(accessors[attributes["POSITION"]]["count"])
            if "indices" in primitive:
                triangles += int(accessors[int(primitive["indices"])]["count"]) // 3

    return MeshStats(vertices=vertices, triangles=triangles, glb_bytes=len(glb))
