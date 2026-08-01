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

Two export request vocabularies, both endpoint-covered here (closing
docs/GEOMETRY-QA.md gap #8):

* **Shape goldens** (``model.json`` carrying a ``ShapeRequest``) → the
  parametric ``POST /api/v1/export`` route.
* **Feature-tree goldens** (``model.json`` carrying an ``EvaluateTreeRequest``)
  → the ``POST /api/v1/export/tree`` route, which evaluates the tree through
  the SAME machinery as ``/evaluate`` and exports the last-good body. The
  endpoint-level STEP round-trip now covers evaluated bodies (e.g. the
  extrude/fillet/chamfer trees), not just primitives; a tree that produces no
  body is a clean 422 ``tree_export_failed`` envelope.
"""

import hashlib
import json
import math
import os
import re
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
    Compound,
    import_step,  # pyright: ignore[reportUnknownVariableType]
    import_stl,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid, load_model_request
from geometry.kernel import build_shape, evaluate_tessellation, measure_shape
from geometry.kernel.export import (
    STEP_MAGIC,
    STL_HEADER_BYTES,
    STL_TRIANGLE_RECORD_BYTES,
    export_step_bytes,
)
from geometry.main import app
from geometry.schemas import (
    ExportFormat,
    ExportRequest,
    ShapeProperties,
    TessellateRequest,
)
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    ExportTreeRequest,
    export_tree_filename,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, export_filename

client = TestClient(app)

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"


def _is_shape_golden(model_path: Path) -> bool:
    """True for goldens the export endpoint can speak (ShapeRequest models);
    feature-tree goldens carry a ``features`` list instead and export through
    the ``/export/tree`` route."""
    return "shape" in json.loads(model_path.read_text(encoding="utf-8"))


MODEL_FILES = [
    path for path in sorted(GOLDENS_DIR.glob("*/model.json")) if _is_shape_golden(path)
]

#: Feature-tree goldens (``EvaluateTreeRequest`` models) — the tree-export
#: (``POST /api/v1/export/tree``) inventory. Complements the shape inventory
#: above; every future tree golden gets endpoint export coverage for free.
TREE_MODEL_FILES = [
    path
    for path in sorted(GOLDENS_DIR.glob("*/model.json"))
    if not _is_shape_golden(path)
]

each_model = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)
each_tree_model = pytest.mark.parametrize(
    "model_path", TREE_MODEL_FILES, ids=[path.parent.name for path in TREE_MODEL_FILES]
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


# --- Feature-tree export (POST /api/v1/export/tree) — gap #8 -----------------------


def _tree_export_request(model_path: Path, fmt: ExportFormat) -> ExportTreeRequest:
    """Derive a tree-export request from a golden's ``EvaluateTreeRequest``."""
    tree = EvaluateTreeRequest.model_validate_json(
        model_path.read_text(encoding="utf-8")
    )
    return ExportTreeRequest.model_validate(
        {**tree.model_dump(mode="json"), "format": fmt}
    )


def _post_tree_export(request: ExportTreeRequest) -> httpx.Response:
    return client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))


def test_tree_export_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert TREE_MODEL_FILES, f"no feature-tree goldens discovered under {GOLDENS_DIR}"


@each_tree_model
@each_format
def test_tree_export_response_headers(model_path: Path, fmt: ExportFormat) -> None:
    """Correct media type + attachment filename for each format and tree."""
    request = _tree_export_request(model_path, fmt)
    response = _post_tree_export(request)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == EXPORT_MEDIA_TYPES[fmt]
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{export_tree_filename(request)}"'
    )
    assert len(response.content) > 0


@each_tree_model
def test_tree_step_export_endpoint_roundtrip(
    model_path: Path,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
) -> None:
    """Gap #8: HTTP tree STEP export → re-import → geometry preserved.

    The evaluated body is exported over HTTP, re-imported, and re-measured
    against the SAME body rebuilt through the evaluate-tree path
    (``build_model_solid``): mass properties within ``ROUNDTRIP_TOL``,
    topology exact — the shape-golden round-trip gate, now over trees.
    """
    name = model_path.parent.name
    request = _tree_export_request(model_path, "step")
    response = _post_tree_export(request)

    assert response.status_code == 200, response.text
    assert response.content.startswith(STEP_MAGIC), f"{name}: not a STEP part 21 file"

    step_path = tmp_path / f"{name}.step"
    step_path.write_bytes(response.content)
    imported = import_step(step_path)
    solids = imported.solids()
    # A multi-body golden (§MB-0) exports as a multi-solid STEP; re-measure the
    # whole imported body set (one Solid, or a Compound of the solids) so the
    # round-trip covers multi-body parts too.
    assert solids, f"{name}: expected at least 1 solid after import, got 0"
    reimported_shape = solids[0] if len(solids) == 1 else Compound(list(solids))
    reimported = measure_shape(reimported_shape)

    original = measure_shape(
        build_model_solid(load_model_request(model_path.read_text(encoding="utf-8")))
    )
    assert_roundtrip_preserved(name, reimported, original)


@each_tree_model
@each_format
def test_tree_export_is_byte_deterministic_in_process(
    model_path: Path, fmt: ExportFormat
) -> None:
    """Same tree-export request twice → byte-identical file (RESEARCH §9).

    The STEP timestamp is pinned on the tree path exactly as on the shape path
    (both go through ``export_solid`` → ``export_step_bytes``); a flake is P0.
    """
    request = _tree_export_request(model_path, fmt)
    first = _post_tree_export(request)
    second = _post_tree_export(request)

    assert first.content == second.content, (
        f"{model_path.parent.name}: {fmt} tree-export bytes differ between runs"
    )


#: Re-evaluates a feature-tree golden (EvaluateTreeRequest JSON on stdin) in a
#: pristine interpreter and reports both formats' digests through the SAME
#: evaluate-tree → export_solid path the endpoint uses, emulating a worker
#: restart. Multi-body goldens (§MB-0) export as a Compound assembled in fixed
#: base (tree) order; the parent runs this subprocess under a DIFFERENT
#: PYTHONHASHSEED so any accidental dict/set-iteration dependence in that
#: ordering — invisible to the in-process gate, which shares one hash seed —
#: reorders the compound and breaks the digest match.
_TREE_RESTART_PROBE = """\
import hashlib
import sys

from geometry.features import evaluate_tree
from geometry.kernel import export_solid
from py_kit.schemas.features import EvaluateTreeRequest, ExportTreeRequest

request = ExportTreeRequest.model_validate_json(sys.stdin.read())
body = evaluate_tree(EvaluateTreeRequest.model_validate(request.model_dump())).body
assert body is not None, "tree evaluated to no body"
for fmt in ("step", "stl"):
    data = export_solid(
        body, fmt, request.linear_deflection, request.angular_deflection
    )
    print(fmt, hashlib.sha256(data).hexdigest())
"""


@each_tree_model
def test_tree_export_is_byte_deterministic_across_interpreter_restart(
    model_path: Path,
) -> None:
    """Fresh-interpreter tree export (worker-restart emulation, RESEARCH §9) →
    same STEP and STL bytes as this process, under a DIFFERENT hash seed.

    Closes the multi-body determinism gap the shape-golden restart gate cannot
    reach: a part with >1 body tessellates/exports a ``Compound`` assembled in
    fixed base order (``list(state.bodies.values())`` over an insertion-ordered
    dict). The in-process gate shares one PYTHONHASHSEED, so a latent dict/set
    ordering dependence would pass it; forcing a different seed in the child is
    what actually proves the base-order compound is hash-independent.
    """
    name = model_path.parent.name
    request = _tree_export_request(model_path, "step")  # deflections carry over
    digests = {
        fmt: hashlib.sha256(
            _post_tree_export(_tree_export_request(model_path, fmt)).content
        ).hexdigest()
        for fmt in ("step", "stl")
    }

    env = {**os.environ, "PYTHONHASHSEED": "0"}
    result = subprocess.run(
        [sys.executable, "-c", _TREE_RESTART_PROBE],
        input=request.model_dump_json(),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, (
        f"{name}: tree restart probe failed:\n{result.stderr}"
    )

    remote = dict(line.split() for line in result.stdout.splitlines())
    for fmt, digest in digests.items():
        assert remote[fmt] == digest, (
            f"{name}: {fmt} tree-export bytes differ across interpreter restart "
            f"(base-order compound assembly is not hash-independent)"
        )


def test_tree_export_no_body_feature_returns_envelope(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    """A tree with no body-affecting feature → clean 422, not a partial file.

    Truncate the extrude golden to its sketch alone: the strict-prefix rule
    leaves no body, so export is a ``tree_export_failed`` envelope (`no_body`),
    never a 500 or a zero-byte download.
    """
    tree_path = TREE_MODEL_FILES[0]
    tree = EvaluateTreeRequest.model_validate_json(
        tree_path.read_text(encoding="utf-8")
    )
    sketch_only = tree.model_copy(update={"features": tree.features[:1]})
    request = ExportTreeRequest.model_validate(
        {**sketch_only.model_dump(mode="json"), "format": "step"}
    )
    response = _post_tree_export(request)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "tree_export_failed"
    assert body["error"]["details"] == {"reason": "no_body"}


def test_tree_export_strict_prefix_failure_surfaces_feature_error() -> None:
    """A strict-prefix failure → 422 carrying the failing ``FeatureError``.

    Point the extrude at a non-existent profile: evaluation fails on that
    feature (``reference_unresolved``), so there is no body to export and the
    envelope details carry the per-feature error code — the §4.3 semantics
    reused, not a 500.
    """
    tree_path = TREE_MODEL_FILES[0]
    payload = json.loads(tree_path.read_text(encoding="utf-8"))
    # Find an extrude feature and break its profile reference.
    for entry in payload["features"]:
        params = entry["feature"]["params"]
        if entry["feature"]["type"] == "extrude":
            params["profile"]["feature_id"] = "00000000-0000-0000-0000-0000deadbeef"
            break
    else:
        pytest.skip("no extrude feature in the first tree golden to break")

    response = client.post("/api/v1/export/tree", json={**payload, "format": "step"})

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "tree_export_failed"
    assert error["details"]["feature_error"]["code"] == "reference_unresolved"


# --- audit N4: the deliverable file says what it is ------------------------------
#
# Measured before the fix: `Content-Disposition: filename="part-ddc5d49d-….step"`
# containing `#7 = PRODUCT('SOLID','SOLID','',(#8));` — the string "Motor Mount
# Bracket" appeared nowhere in the file the vendor received, so quoting a job meant
# five hand-renames before you could attach the files. Asserted on the exported
# BYTES + the response header, not on the helper's return value.

_STEP_PRODUCT_RE = re.compile(rb"PRODUCT\('([^']*)'")


def test_tree_step_export_names_the_product_after_the_document() -> None:
    """A named export writes PRODUCT('<document name>'), never PRODUCT('SOLID')."""
    request = _tree_export_request(TREE_MODEL_FILES[0], "step").model_copy(
        update={"name": "Motor Mount Bracket"}
    )
    data = client.post(
        "/api/v1/export/tree", json=request.model_dump(mode="json")
    ).content

    products = [n.decode("ascii") for n in _STEP_PRODUCT_RE.findall(data)]
    assert products, "no PRODUCT entity in the exported STEP"
    assert all(name == "Motor Mount Bracket" for name in products), (
        f"the document name did not reach the exported PRODUCT names: {products}"
    )
    assert b"PRODUCT('SOLID'" not in data


def test_tree_step_export_without_a_name_is_byte_identical_to_before() -> None:
    """The name is OPTIONAL and inert: no name -> the pre-N4 bytes, exactly.

    Guards the additive posture — a caller that has no document name to send
    must get the file it got yesterday (and the goldens keep passing).
    """
    base = _tree_export_request(TREE_MODEL_FILES[0], "step")
    assert base.name is None
    unnamed = client.post("/api/v1/export/tree", json=base.model_dump(mode="json"))
    assert unnamed.status_code == 200
    rebuilt = build_model_solid(
        load_model_request(TREE_MODEL_FILES[0].read_text(encoding="utf-8"))
    )
    assert export_step_bytes(rebuilt) == unnamed.content


def test_tree_export_filename_is_the_document_name_or_the_part_id() -> None:
    """Downloads land as `motor-mount-bracket.step`, not `part-<uuid>.step`.

    And the fallback stays keyed to the part id, so an unnamed export can still
    never collide with another part's download.
    """
    named = _tree_export_request(TREE_MODEL_FILES[0], "step").model_copy(
        update={"name": "Motor Mount Bracket  Rev.A"}
    )
    assert export_tree_filename(named) == "motor-mount-bracket-rev-a.step"

    unnamed = _tree_export_request(TREE_MODEL_FILES[0], "stl")
    assert export_tree_filename(unnamed) == f"part-{unnamed.part_id}.stl"

    # A name with nothing sluggable in it must not produce a bare ".step".
    unsluggable = named.model_copy(update={"name": "///"})
    assert export_tree_filename(unsluggable) == f"part-{named.part_id}.step"


def test_tree_export_response_header_carries_the_document_name() -> None:
    """The header the browser saves by — the caller is not trusted to re-derive it."""
    request = _tree_export_request(TREE_MODEL_FILES[0], "step").model_copy(
        update={"name": "Motor Mount Bracket"}
    )
    response = _post_tree_export(request)
    assert response.status_code == 200, response.text
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="motor-mount-bracket.step"'
    )
