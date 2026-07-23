"""Assembly STEP/STL export gates (``POST /api/v1/assembly/export``).

The interop gate for the assembly pillar (RESEARCH §10/§11; BACKLOG P0 "Assembly
STEP export"): an assembly is "a one-way street" until it exports, so this suite
proves the round-trip a downstream tool actually performs.

Reuses the committed bolted-assembly goldens (``goldens-assembly/*``, ≥2
instances, real solved mate transforms) — the SAME requests
:mod:`tests.test_assembly_goldens` locks the solve for — so the export path is
exercised over genuinely-placed parts, not a hand-rigged pair. For each golden:

* **Worked STEP round-trip:** export → ``build123d.import_step`` → recover N part
  bodies; each re-imported solid's world mass-properties (rigid-invariant volume /
  area, transformed centroid) match the instance's SOLVED placement applied to its
  part's local properties, within the shared ``ROUNDTRIP_TOL`` (never an ad-hoc
  epsilon — the kernel round-trip bound, conftest).
* **Named product structure:** every instance id appears as a STEP ``PRODUCT``
  name, so each recovered body is traceable to its instance (AP214 product
  structure).
* **Byte-determinism (RESEARCH §9):** identical requests → byte-identical STEP and
  STL, in-process AND across an interpreter restart (the assembly writer's
  process-global occurrence-id counter is canonicalised kernel-side).

Plus the error posture: a body-less assembly is a clean 422
``assembly_export_no_body`` envelope, never a zero-solid file; the single-part
export path (``/export``) is untouched (covered by ``test_export``).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

# Upstream import_step carries a Shape[Unknown] type param — scoped ignore only.
from build123d import import_step  # pyright: ignore[reportUnknownVariableType]
from fastapi.testclient import TestClient
from geometry.assembly import evaluate_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.transform import Pose, as_vector
from geometry.kernel import measure_shape
from geometry.kernel.export import STEP_MAGIC
from geometry.main import app
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    ExportAssemblyRequest,
    assembly_export_filename,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, ExportFormat

client = TestClient(app)

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-assembly"
MODEL_FILES = sorted(GOLDENS_DIR.glob("*/model.json"))

each_golden = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)
each_format = pytest.mark.parametrize("fmt", ["step", "stl"])

#: Matches a STEP ``PRODUCT('name',...)`` name field (traceability parse).
_PRODUCT_RE = re.compile(rb"PRODUCT\('([^']*)'")


@dataclass(frozen=True)
class _ExpectedInstance:
    """One instance's rigid-invariant + world properties, from the solve."""

    volume: float
    surface_area: float
    world_centroid: tuple[float, float, float]


def _load_request(model_path: Path) -> EvaluateAssemblyRequest:
    return EvaluateAssemblyRequest.model_validate_json(
        model_path.read_text(encoding="utf-8")
    )


def _export_request(model_path: Path, fmt: ExportFormat) -> ExportAssemblyRequest:
    """The golden's evaluate request, promoted to an export request."""
    return ExportAssemblyRequest.model_validate(
        {**_load_request(model_path).model_dump(mode="json"), "format": fmt}
    )


def _expected_instances(request: EvaluateAssemblyRequest) -> list[_ExpectedInstance]:
    """Each bodied instance's world mass-properties from ``evaluate_assembly``.

    Volume/area are rigid-invariant (compared against the re-imported solid
    directly); the centroid is the part's LOCAL centroid carried through its
    SOLVED placement — the exact world position the exported file must reproduce.
    """
    result = evaluate_assembly(request)
    expected: list[_ExpectedInstance] = []
    for inst in result.instances:
        if inst.properties is None:
            continue
        world = Pose.from_placement(inst.placement).apply_point(
            as_vector(inst.properties.centroid)
        )
        expected.append(
            _ExpectedInstance(
                volume=inst.properties.volume,
                surface_area=inst.properties.surface_area,
                world_centroid=(float(world[0]), float(world[1]), float(world[2])),
            )
        )
    return expected


def _match_reimported(
    name: str,
    step_bytes: bytes,
    expected: list[_ExpectedInstance],
    tmp_path: Path,
    tol: float,
) -> None:
    """Assert the re-imported solids reproduce every expected placed body.

    Recovers N solids (one per instance), measures each through the SAME GProp
    pipeline, and bijectively matches them to the expected instances by nearest
    world centroid — then asserts volume, area, and centroid all agree within
    *tol* (the documented kernel round-trip bound, ``roundtrip_tol`` fixture). A
    body that lands at the wrong placement, or a lost solid, fails the match.
    """
    step_path = tmp_path / f"{name}.step"
    step_path.write_bytes(step_bytes)
    solids = import_step(step_path).solids()
    assert len(solids) == len(expected), (
        f"{name}: expected {len(expected)} solids after import, got {len(solids)}"
    )

    remaining = list(expected)
    for solid in solids:
        props = measure_shape(solid)
        got = (props.centroid.x, props.centroid.y, props.centroid.z)
        nearest = min(
            remaining,
            key=lambda e: sum(
                (g - w) ** 2 for g, w in zip(got, e.world_centroid, strict=True)
            ),
        )
        for axis, g, w in zip("xyz", got, nearest.world_centroid, strict=True):
            assert g == pytest.approx(w, abs=tol), (
                f"{name}: re-imported solid centroid.{axis} {g!r} does not match "
                f"any solved placement (nearest expected {w!r}, tol {tol!r})"
            )
        assert props.volume == pytest.approx(nearest.volume, abs=tol), name
        assert props.surface_area == pytest.approx(nearest.surface_area, abs=tol), name
        remaining.remove(nearest)
    assert not remaining, f"{name}: {len(remaining)} placed body(s) never recovered"


def test_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the gate, never skip it silently."""
    assert MODEL_FILES, f"no assembly goldens discovered under {GOLDENS_DIR}"


@each_golden
def test_step_assembly_export_roundtrip(
    model_path: Path, tmp_path: Path, roundtrip_tol: float
) -> None:
    """Worked round-trip: export a ≥2-instance assembly → re-import → placements.

    Every re-imported part body lands at its SOLVED world placement (world
    mass-property match within the kernel round-trip bound), and every instance is
    traceable to a named STEP ``PRODUCT``.
    """
    name = model_path.parent.name
    request = _export_request(model_path, "step")
    assert len(request.instances) >= 2, f"{name}: expected a >=2-instance golden"

    data = export_assembly(request)
    assert data.startswith(STEP_MAGIC), f"{name}: not a STEP part 21 file"

    _match_reimported(name, data, _expected_instances(request), tmp_path, roundtrip_tol)

    # Named product structure: every instance id is a PRODUCT name (traceability).
    product_names = {n.decode("ascii") for n in _PRODUCT_RE.findall(data)}
    for inst in request.instances:
        assert str(inst.instance_id) in product_names, (
            f"{name}: instance {inst.instance_id} has no PRODUCT name in the STEP "
            f"file — not traceable (products found: {sorted(product_names)})"
        )


@each_golden
def test_step_assembly_export_endpoint_roundtrip(
    model_path: Path, tmp_path: Path, roundtrip_tol: float
) -> None:
    """Same round-trip through the HTTP route users hit (headers + placements)."""
    name = model_path.parent.name
    request = _export_request(model_path, "step")
    response = client.post(
        "/api/v1/assembly/export", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == EXPORT_MEDIA_TYPES["step"]
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{assembly_export_filename(request)}"'
    )
    assert response.content.startswith(STEP_MAGIC), f"{name}: not a STEP part 21 file"
    _match_reimported(
        name, response.content, _expected_instances(request), tmp_path, roundtrip_tol
    )


@each_golden
@each_format
def test_assembly_export_is_byte_deterministic_in_process(
    model_path: Path, fmt: ExportFormat
) -> None:
    """Same request twice → byte-identical file (RESEARCH §9; a flake is P0).

    Covers the assembly writer's process-global occurrence-id counter: without
    the kernel-side canonicalisation a second in-process export would differ.
    """
    request = _export_request(model_path, fmt)
    first = export_assembly(request)
    second = export_assembly(request)
    assert first == second, (
        f"{model_path.parent.name}: {fmt} assembly export bytes differ between runs"
    )


#: Re-exports an assembly golden (EvaluateAssemblyRequest JSON on stdin) in a
#: pristine interpreter under a DIFFERENT hash seed, reporting both formats'
#: digests — emulating a worker restart (proves the solve + composition + id
#: canonicalisation are hash- and process-independent).
_RESTART_PROBE = """\
import hashlib
import json
import sys

from geometry.assembly.export import export_assembly
from py_kit.schemas.assemblies import ExportAssemblyRequest

base = json.loads(sys.stdin.read())
for fmt in ("step", "stl"):
    request = ExportAssemblyRequest.model_validate({**base, "format": fmt})
    print(fmt, hashlib.sha256(export_assembly(request)).hexdigest())
"""


@each_golden
def test_assembly_export_is_byte_deterministic_across_interpreter_restart(
    model_path: Path,
) -> None:
    """Fresh-interpreter export (worker-restart emulation, RESEARCH §9) → same
    STEP and STL bytes as this process, under a different PYTHONHASHSEED."""
    name = model_path.parent.name
    digests = {
        fmt: hashlib.sha256(
            export_assembly(_export_request(model_path, fmt))
        ).hexdigest()
        for fmt in ("step", "stl")
    }

    env = {**os.environ, "PYTHONHASHSEED": "0"}
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=_load_request(model_path).model_dump_json(),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert result.returncode == 0, f"{name}: restart probe failed:\n{result.stderr}"

    remote = dict(line.split() for line in result.stdout.splitlines())
    for fmt, digest in digests.items():
        assert remote[fmt] == digest, (
            f"{name}: {fmt} assembly export bytes differ across interpreter restart"
        )


def test_assembly_export_no_body_returns_envelope() -> None:
    """A body-less assembly → clean 422, not a zero-solid file (design §4.3)."""
    payload = ExportAssemblyRequest(
        assembly_id=uuid.UUID(int=1),
        version=1,
        instances=[
            EvaluatedInstance(
                instance_id=uuid.UUID(int=2),
                part_key="empty@tip",
                features=[],  # no body-affecting feature → evaluates to no body
                grounded=True,
            )
        ],
        format="step",
    ).model_dump(mode="json")

    response = client.post("/api/v1/assembly/export", json=payload)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "assembly_export_no_body"


def test_assembly_export_rejects_invalid_format() -> None:
    """An unsupported export format is a 422 at the DTO, never reaches geometry."""
    request = _export_request(MODEL_FILES[0], "step").model_dump(mode="json")
    request["format"] = "iges"
    response = client.post("/api/v1/assembly/export", json=request)
    assert response.status_code == 422, response.text
