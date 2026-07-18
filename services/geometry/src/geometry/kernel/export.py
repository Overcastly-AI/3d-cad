"""CAD file export — STEP (exact B-rep) and binary STL (faceted mesh).

Uses build123d's exporters (OCCT ``STEPControl_Writer`` / ``StlAPI_Writer``
underneath). Both outputs are **byte-deterministic** for identical requests
(RESEARCH §9); the geometry export gate asserts it:

* **STEP:** OCCT stamps the file's ``FILE_NAME`` record with the wall-clock
  creation time — the one nondeterministic byte range in the output. We pin
  it to :data:`STEP_EXPORT_TIMESTAMP` via ``export_step(timestamp=...)``
  (decision + evidence recorded in docs/GEOMETRY-QA.md, gap #4). Exporting
  through ``BytesIO`` also keeps filesystem paths out of the file — the
  ``FILE_NAME`` name field stays the fixed writer default, verified on
  build123d 0.11.1.
* **STL:** binary format, fixed 80-byte OCCT header + mesher output, no
  timestamps. ``export_stl`` runs the SAME ``BRepMesh_IncrementalMesh`` call
  as the GLB tessellation path (``Shape.mesh``: relative linear deflection,
  parallel flag), so a given ``linear_deflection`` / ``angular_deflection``
  pair means the same facets in the viewport and in the exported file.
  Defaults come from :mod:`py_kit.schemas.geometry`
  (``DEFAULT_LINEAR_DEFLECTION`` = 0.1 mm, ``DEFAULT_ANGULAR_DEFLECTION`` =
  0.1 rad — the viewport-quality tessellation settings).

Kernel objects never leave ``geometry.kernel``: callers receive bytes.
"""

import io
import tempfile
from datetime import datetime
from pathlib import Path

from build123d.exporters3d import (
    export_step,  # pyright: ignore[reportUnknownVariableType]  (Shape[Unknown] param upstream)
    export_stl,  # pyright: ignore[reportUnknownVariableType]
)

from geometry.kernel.types import BodyShape

#: Pinned STEP creation timestamp (determinism decision, GEOMETRY-QA gap #4).
#: STEP consumers treat ``FILE_NAME``'s timestamp as provenance metadata, not
#: geometry; a fixed sentinel value makes identical requests byte-identical.
STEP_EXPORT_TIMESTAMP = datetime(2000, 1, 1, 0, 0, 0)

#: Marker every STEP part 21 file starts with (sanity-checked after export).
STEP_MAGIC = b"ISO-10303-21"

#: Binary STL layout: 80-byte header + uint32 triangle count, then 50 bytes
#: per triangle (normal + 3 vertices as float32 triples + uint16 attribute).
STL_HEADER_BYTES = 84
STL_TRIANGLE_RECORD_BYTES = 50


def export_step_bytes(shape: BodyShape) -> bytes:
    """Export *shape* as a STEP AP214 part 21 file (exact B-rep, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    :class:`~build123d.Compound` of a multi-body part's solids (multi-body §MB-0);
    a STEP file holds multiple solids natively (valid AP214). Deterministic: the
    creation timestamp is pinned (module docstring).
    """
    buffer = io.BytesIO()
    if not export_step(shape, buffer, timestamp=STEP_EXPORT_TIMESTAMP):
        raise RuntimeError("STEP export failed")
    data = buffer.getvalue()
    if not data.startswith(STEP_MAGIC):
        raise RuntimeError("STEP export produced a non-part-21 payload")
    return data


def export_stl_bytes(
    shape: BodyShape, linear_deflection: float, angular_deflection: float
) -> bytes:
    """Export *shape* as a binary STL (faceted, mm units).

    *shape* is any B-rep :class:`~build123d.Shape` — a single :class:`Solid` or a
    multi-body :class:`~build123d.Compound` (multi-body §MB-0); STL emits every
    triangle of every solid. Deflection semantics match the GLB tessellation path
    (module docstring).

    Raises:
        ValueError: if a deflection is not strictly positive (the API layer
            rejects these at validation time; this guards direct kernel use).
    """
    if linear_deflection <= 0 or angular_deflection <= 0:
        raise ValueError(
            "Deflections must be strictly positive, got "
            f"linear={linear_deflection}, angular={angular_deflection}"
        )
    # StlAPI_Writer only speaks paths — write to a tempfile like the GLB
    # exporter does. The path never leaks into binary STL output.
    with tempfile.TemporaryDirectory(prefix="loft-stl-") as tmp:
        target = Path(tmp) / "shape.stl"
        ok = export_stl(
            shape,
            target,
            tolerance=linear_deflection,
            angular_tolerance=angular_deflection,
            ascii_format=False,
        )
        if not ok:
            raise RuntimeError("STL export failed")
        data = target.read_bytes()
    if len(data) < STL_HEADER_BYTES:
        raise RuntimeError("STL export produced a truncated payload")
    return data
