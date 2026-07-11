"""STEP/STL export endpoint gates (``POST /api/v1/export``).

Closes docs/GEOMETRY-QA.md gaps #3 and #4:

* **Endpoint-level STEP round-trip (gap #3):** HTTP export → ``import_step``
  → re-measure → mass properties within the shared ``ROUNDTRIP_TOL`` (conftest)
  and exact topology — the same comparison the kernel-level gate uses, now
  exercised through the full HTTP path users hit.
* **Export byte-determinism (gap #4):** identical requests must produce
  byte-identical files for BOTH formats, in-process and across an interpreter
  restart. For STEP this is only true because the kernel pins the creation
  timestamp (``geometry.kernel.export.STEP_EXPORT_TIMESTAMP``) — asserted
  directly here.
* **STL re-import volume:** binary STL is a faceted approximation, so the
  B-rep round-trip tolerance does NOT apply. The volume bound is *derived*
  from the export deflection (see ``stl_volume_tolerance``), never an ad-hoc
  epsilon.

Parametrized over the golden inventory (``goldens/*/model.json``, mirroring
``test_step_roundtrip.py`` — importlib import mode keeps test modules from
importing each other), so every future golden gets export coverage for free.

Scope: **shape goldens only** (``model.json`` carrying a ``ShapeRequest``).
The export endpoint's request vocabulary is parametric shapes — evaluated
feature trees cannot be exported over HTTP yet (that lands with the
part-export item; gap recorded in docs/GEOMETRY-QA.md). Tree goldens still
get STEP round-trip coverage at kernel level via ``test_step_roundtrip.py``,
which rebuilds them through the full evaluate-tree path.
"""

import hashlib
import math
import struct
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx  # httpx is deprecated; httpx2 is the repo standard
import pytest

# Upstream signatures carry Shape[Unknown]/PathLike[Unknown] type params
# (same gap tessellate.py documents for export_gltf) — scoped ignores only.
from build123d import (
    import_step,  # pyright: ignore[reportUnknownVariableType]
    import_stl,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import build_shape, evaluate_tessellation, measure_shape
from geometry.kernel.export import (
    STEP_MAGIC,
    STL_HEADER_BYTES,
    STL_TRIANGLE_RECORD_BYTES,
)
from geometry.main import app
from geometry.schemas import (
    ExportFormat,
    ExportRequest,
    ShapeProperties,
    TessellateRequest,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, export_filename

client = TestClient(app)

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"


def _is_shape_golden(model_path: Path) -> bool:
    """True for goldens the export endpoint can speak (ShapeRequest models);
    feature-tree goldens carry a ``features`` list instead (see module
    docstring for why they are out of endpoint-export scope for now)."""
    import json

    return "shape" in json.loads(model_path.read_text(encoding="utf-8"))


MODEL_FILES = [
    path for path in sorted(GOLDENS_DIR.glob("*/model.json")) if _is_shape_golden(path)
]

each_model = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)
each_format = pytest.mark.parametrize("fmt", ["step", "stl"])

Triangle = tuple[float, float, float, float, float, float, float, float, float]


def _export_request(model_path: Path, fmt: ExportFormat) -> ExportRequest:
    """Derive an export request from a golden's ``TessellateRequest``."""
    tess = TessellateRequest.model_validate_json(model_path.read_text(encoding="utf-8"))
    return ExportRequest(
        shape=tess.shape,
        params=tess.params,
        format=fmt,
        linear_deflection=tess.linear_deflection,
    )


def _post_export(request: ExportRequest) -> httpx.Response:
    return client.post("/api/v1/export", json=request.model_dump(mode="json"))


def _parse_binary_stl(data: bytes) -> list[Triangle]:
    """Parse a binary STL into its triangles (9 vertex floats each).

    Validates the structure users' tools rely on: 80-byte header, uint32
    triangle count, 50-byte records, and a length that matches the count.
    """
    assert len(data) >= STL_HEADER_BYTES, "truncated STL"
    (count,) = struct.unpack_from("<I", data, 80)
    expected_size = STL_HEADER_BYTES + STL_TRIANGLE_RECORD_BYTES * count
    assert len(data) == expected_size, (
        f"binary STL length {len(data)} != header-declared {expected_size}"
    )
    triangles: list[Triangle] = []
    for index in range(count):
        record = struct.unpack_from(
            "<12fH", data, STL_HEADER_BYTES + STL_TRIANGLE_RECORD_BYTES * index
        )
        # Skip the normal (fields 0-2) and the attribute word (field 12).
        triangles.append(tuple(float(value) for value in record[3:12]))  # pyright: ignore[reportArgumentType]
    return triangles


def _enclosed_volume(triangles: list[Triangle]) -> float:
    """Enclosed volume of a closed triangle mesh (divergence theorem).

    ``V = (1/6) * Σ a · (b x c)`` over facets — positive for outward-oriented
    normals, which STL mandates.
    """
    total = 0.0
    for ax, ay, az, bx, by, bz, cx, cy, cz in triangles:
        total += (
            ax * (by * cz - bz * cy)
            - ay * (bx * cz - bz * cx)
            + az * (bx * cy - by * cx)
        )
    return total / 6.0


def stl_volume_tolerance(
    properties: ShapeProperties, linear_deflection: float
) -> float:
    """Derived STL volume tolerance — faceting bound, not an ad-hoc epsilon.

    STL is a faceted approximation, so the B-rep round-trip tolerance (1e-7)
    cannot apply. Derivation from the export deflection:

    * OCCT meshes with RELATIVE linear deflection (build123d's ``export_stl``
      and ``Shape.mesh`` both pass ``isRelative=True`` to
      ``BRepMesh_IncrementalMesh``): the effective deviation budget per edge
      is ``linear_deflection x edge size``. No edge exceeds the AABB
      diagonal, so ``d = linear_deflection x diagonal`` is a model-wide
      ceiling on facet deviation from the true surface.
    * Every point of the faceted boundary then lies within a shell of
      thickness ``d`` around the exact boundary, so the enclosed-volume error
      is bounded by ``surface_area x d``.

    This is a ceiling, not a fit: planar faces facet exactly, so the measured
    deviation for the box golden is 0.0 (docs/GEOMETRY-QA.md). Curved goldens
    will consume real slack; if one exceeds this bound, that is a finding to
    root-cause, never a reason to widen the formula.
    """
    bbox = properties.bounding_box
    diagonal = math.dist(
        (bbox.min.x, bbox.min.y, bbox.min.z), (bbox.max.x, bbox.max.y, bbox.max.z)
    )
    return properties.surface_area * linear_deflection * diagonal


def test_export_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert MODEL_FILES, f"no golden models discovered under {GOLDENS_DIR}"


@each_format
def test_export_response_headers(fmt: ExportFormat) -> None:
    """Correct media type + attachment filename for each format."""
    request = _export_request(MODEL_FILES[0], fmt)
    response = _post_export(request)

    assert response.status_code == 200
    assert response.headers["content-type"] == EXPORT_MEDIA_TYPES[fmt]
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{export_filename(request)}"'
    )
    assert len(response.content) > 0


@each_model
def test_step_export_endpoint_roundtrip(
    model_path: Path,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    """Gap #3: HTTP STEP export → re-import → geometry preserved.

    Same comparison as the kernel-level gate (shared conftest fixture): mass
    properties within ``ROUNDTRIP_TOL``, topology exact.
    """
    name = model_path.parent.name
    request = _export_request(model_path, "step")
    response = _post_export(request)

    assert response.status_code == 200
    assert response.content.startswith(STEP_MAGIC), f"{name}: not a STEP part 21 file"

    step_path = tmp_path / f"{name}.step"
    step_path.write_bytes(response.content)
    imported = import_step(step_path)
    solids = imported.solids()
    assert len(solids) == 1, f"{name}: expected 1 solid after import, got {len(solids)}"
    reimported = measure_shape(solids[0])

    original = measure_shape(build_shape(request))
    assert_roundtrip_preserved(name, reimported, original)


@each_model
def test_stl_export_endpoint_roundtrip_volume(model_path: Path, tmp_path: Path) -> None:
    """HTTP STL export → re-import → enclosed volume within the derived bound.

    Also asserts facet-count parity with the GLB tessellation of the same
    request — both paths run the identical OCCT mesher call, so a divergence
    is a real change — and that the kernel can re-read its own artifact.
    """
    name = model_path.parent.name
    tess_request = TessellateRequest.model_validate_json(
        model_path.read_text(encoding="utf-8")
    )
    request = _export_request(model_path, "stl")
    response = _post_export(request)
    assert response.status_code == 200

    triangles = _parse_binary_stl(response.content)

    # Structural parity with the viewport mesh (same request, same mesher).
    _glb, metadata = evaluate_tessellation(tess_request)
    assert len(triangles) == metadata.mesh.triangles, (
        f"{name}: STL facet count {len(triangles)} != GLB triangle count "
        f"{metadata.mesh.triangles} for identical deflection settings"
    )

    # Mass-property gate: enclosed volume within the deflection-derived bound.
    volume = _enclosed_volume(triangles)
    expected = metadata.properties.volume
    tolerance = stl_volume_tolerance(metadata.properties, request.linear_deflection)
    assert volume == pytest.approx(expected, abs=tolerance), (
        f"{name}: STL enclosed volume {volume!r} vs B-rep {expected!r} exceeds "
        f"the faceting bound {tolerance!r} (see stl_volume_tolerance derivation)"
    )

    # The kernel must be able to re-read its own artifact.
    stl_path = tmp_path / f"{name}.stl"
    stl_path.write_bytes(response.content)
    imported = import_stl(stl_path)
    assert imported.area > 0, f"{name}: kernel re-import of exported STL failed"


def test_step_export_timestamp_is_pinned() -> None:
    """Gap #4: the STEP FILE_NAME timestamp is the pinned sentinel, not now().

    OCCT stamps STEP files with wall-clock creation time — the only
    nondeterministic bytes in the output. The kernel pins it (decision in
    geometry/kernel/export.py + docs/GEOMETRY-QA.md).
    """
    from datetime import datetime

    from geometry.kernel.export import STEP_EXPORT_TIMESTAMP

    response = _post_export(_export_request(MODEL_FILES[0], "step"))
    text = response.content.decode("utf-8", errors="replace")

    assert STEP_EXPORT_TIMESTAMP.isoformat() in text, (
        "pinned timestamp missing from STEP FILE_NAME record"
    )
    today = datetime.now().strftime("%Y-%m-%d")
    assert today not in text, (
        f"wall-clock date {today} leaked into STEP output — determinism broken"
    )


@each_model
@each_format
def test_export_is_byte_deterministic_in_process(
    model_path: Path, fmt: ExportFormat
) -> None:
    """Same request twice → byte-identical file (RESEARCH §9; flake = P0)."""
    request = _export_request(model_path, fmt)
    first = _post_export(request)
    second = _post_export(request)

    assert first.content == second.content, (
        f"{model_path.parent.name}: {fmt} export bytes differ between runs"
    )


#: Re-exports a golden (TessellateRequest JSON on stdin) in a pristine
#: interpreter and reports both formats' digests, emulating a worker restart.
_RESTART_PROBE = """\
import hashlib
import sys

from geometry.kernel import evaluate_export
from geometry.schemas import ExportRequest, TessellateRequest

tess = TessellateRequest.model_validate_json(sys.stdin.read())
for fmt in ("step", "stl"):
    request = ExportRequest(
        shape=tess.shape,
        params=tess.params,
        format=fmt,
        linear_deflection=tess.linear_deflection,
    )
    print(fmt, hashlib.sha256(evaluate_export(request)).hexdigest())
"""


@each_model
def test_export_is_byte_deterministic_across_interpreter_restart(
    model_path: Path,
) -> None:
    """Fresh-interpreter export (worker-restart emulation) → same bytes,
    both formats — one subprocess per golden to keep the gate fast."""
    name = model_path.parent.name
    digests = {
        fmt: hashlib.sha256(
            _post_export(_export_request(model_path, fmt)).content
        ).hexdigest()
        for fmt in ("step", "stl")
    }

    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=model_path.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{name}: restart probe failed:\n{result.stderr}"

    remote = dict(line.split() for line in result.stdout.splitlines())
    for fmt, digest in digests.items():
        assert remote[fmt] == digest, (
            f"{name}: {fmt} export bytes differ across interpreter restart"
        )


def test_stl_default_quality_matches_explicit_defaults() -> None:
    """Omitted STL quality params equal the documented defaults, byte-for-byte."""
    base: dict[str, Any] = {
        "shape": "box",
        "params": {"x": 10.0, "y": 20.0, "z": 30.0},
        "format": "stl",
    }
    implicit = client.post("/api/v1/export", json=base)
    explicit = client.post(
        "/api/v1/export",
        json={**base, "linear_deflection": 0.1, "angular_deflection": 0.1},
    )

    assert implicit.status_code == explicit.status_code == 200
    assert implicit.content == explicit.content


@pytest.mark.parametrize(
    "payload",
    [
        # unsupported format
        {"shape": "box", "params": {"x": 1.0, "y": 1.0, "z": 1.0}, "format": "iges"},
        # missing format
        {"shape": "box", "params": {"x": 1.0, "y": 1.0, "z": 1.0}},
        # bad shape params (same validators as tessellate — shared base model)
        {"shape": "box", "params": {"x": 0.0, "y": 1.0, "z": 1.0}, "format": "step"},
        # non-positive STL quality params
        {
            "shape": "box",
            "params": {"x": 1.0, "y": 1.0, "z": 1.0},
            "format": "stl",
            "linear_deflection": 0.0,
        },
        {
            "shape": "box",
            "params": {"x": 1.0, "y": 1.0, "z": 1.0},
            "format": "stl",
            "angular_deflection": -0.1,
        },
    ],
)
def test_export_rejects_invalid_requests_with_envelope(
    payload: dict[str, Any],
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post("/api/v1/export", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())
