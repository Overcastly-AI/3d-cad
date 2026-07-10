"""Shape tessellation to binary glTF (GLB).

Uses build123d's ``export_gltf`` (OCCT ``RWGltf_CafWriter`` underneath) via a
tempfile — the writer only speaks paths. Output is deterministic: the same
shape and deflection produce byte-identical GLB across runs and processes
(asserted by the test suite; RESEARCH §9 determinism gate).

Mesh statistics are parsed from the GLB itself, so they describe the actual
artifact rather than a parallel meshing pass.
"""

import json
import struct
import tempfile
from pathlib import Path
from typing import Any

from build123d import Solid, Unit
from build123d.exporters3d import (
    export_gltf,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
)

from geometry.schemas import DEFAULT_ANGULAR_DEFLECTION, MeshStats

#: Max angle (rad) between adjacent tessellation segments. Fixed service-wide
#: so a given ``linear_deflection`` always means the same mesh. Single source
#: is py-kit's DEFAULT_ANGULAR_DEFLECTION — also the STL export default, so
#: default-quality STL matches the viewport mesh.
ANGULAR_DEFLECTION = DEFAULT_ANGULAR_DEFLECTION

GLB_MAGIC = b"glTF"
_GLB_HEADER = struct.Struct("<4sII")  # magic, version, total length
_GLB_CHUNK_HEADER = struct.Struct("<I4s")  # chunk length, chunk type


def tessellate_glb(shape: Solid, linear_deflection: float) -> tuple[bytes, MeshStats]:
    """Tessellate *shape* and return ``(glb_bytes, mesh_stats)``.

    The GLB scene is Y-up in metres per the glTF spec (build123d converts
    from OCCT's Z-up millimetres).
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

    return glb, glb_stats(glb)


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
