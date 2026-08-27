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
* **Instanced product structure (audit N8):** each UNIQUE part is written as ONE
  named ``PRODUCT`` and placed once per instance, so the solid count equals the
  unique-part count (never the instance count) and the file stops growing with the
  fastener count. Instance identity rides the per-occurrence
  ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` name, so each recovered body is still
  traceable to its instance.
* **Byte-determinism (RESEARCH §9):** identical requests → byte-identical STEP and
  STL, in-process AND across an interpreter restart (the assembly writer's
  process-global occurrence-id counter is canonicalised kernel-side).

Plus the error posture: a body-less assembly is a clean 422
``assembly_export_no_body`` envelope, never a zero-solid file; the single-part
export path (``/export``) is untouched (covered by ``test_export``).
"""

from __future__ import annotations

import collections
import hashlib
import math
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

# Upstream import_step carries a Shape[Unknown] type param — scoped ignore only.
from build123d import import_step  # pyright: ignore[reportUnknownVariableType]
from fastapi.testclient import TestClient
from geometry.assembly import evaluate_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.import_step import import_step_assembly
from geometry.assembly.transform import Pose, as_vector
from geometry.kernel import measure_shape
from geometry.kernel.export import STEP_MAGIC
from geometry.main import app
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    ExportAssemblyRequest,
    Placement,
    Quat,
    assembly_export_filename,
)
from py_kit.schemas.features import EvaluatedFeatureInput
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, ExportFormat, Vec3
from py_kit.schemas.step_import import StepAssemblyImportRequest

client = TestClient(app)

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-assembly"
MODEL_FILES = sorted(GOLDENS_DIR.glob("*/model.json"))

each_golden = pytest.mark.parametrize(
    "model_path", MODEL_FILES, ids=[path.parent.name for path in MODEL_FILES]
)
#: Every export format. The assembly inventory is TWO goldens, so a full
#: 4-format sweep is cheap here (unlike the 49-model part inventory).
each_format = pytest.mark.parametrize("fmt", ["step", "stl", "3mf", "glb"])

#: Matches a STEP ``PRODUCT('name',...)`` name field (traceability parse).
_PRODUCT_RE = re.compile(rb"PRODUCT\('([^']*)'")

#: Matches the NAME (second) field of a ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` — the
#: per-OCCURRENCE name under instanced product structure (audit N8): a part is
#: written once as a PRODUCT and used N times, so instance identity rides here.
#: Whitespace-tolerant between tokens: part-21 wraps long entities across lines,
#: so a 36-char instance-id name lands on the line AFTER the entity keyword.
_OCCURRENCE_NAME_RE = re.compile(
    rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\(\s*'[^']*'\s*,\s*'([^']*)'"
)


def _entity_counts(step_bytes: bytes) -> collections.Counter[str]:
    """Count part-21 entity types in *step_bytes* — what a downstream CAD reads.

    Asserting on the EXPORTED BYTES rather than on a composer's return value: a
    right function whose caller drops the result still writes a wrong file, and
    the entity histogram is exactly the view the receiving CAD/PLM has.
    """
    return collections.Counter(
        match.decode("ascii")
        for match in re.findall(rb"=\s*([A-Z_0-9]+)\(", step_bytes)
    )


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
    """Worked round-trip: export a >=2-instance assembly -> re-import -> placements.

    Every re-imported part body lands at its SOLVED world placement (world
    mass-property match within the kernel round-trip bound), and every instance is
    traceable by name to a STEP occurrence (``NEXT_ASSEMBLY_USAGE_OCCURRENCE``,
    the instance-level identity under instanced product structure — audit N8).
    """
    name = model_path.parent.name
    request = _export_request(model_path, "step")
    assert len(request.instances) >= 2, f"{name}: expected a >=2-instance golden"

    data = export_assembly(request)
    assert data.startswith(STEP_MAGIC), f"{name}: not a STEP part 21 file"

    _match_reimported(name, data, _expected_instances(request), tmp_path, roundtrip_tol)

    # Instance traceability: one named occurrence per instance. (The goldens carry
    # no instance names, so the composer falls back to the instance id — which is
    # exactly the identity a re-import must be able to hand back.)
    occurrence_names = {n.decode("ascii") for n in _OCCURRENCE_NAME_RE.findall(data)}
    for inst in request.instances:
        assert str(inst.instance_id) in occurrence_names, (
            f"{name}: instance {inst.instance_id} has no named occurrence in the "
            f"STEP file — not traceable (occurrences: {sorted(occurrence_names)})"
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
for fmt in ("step", "stl", "3mf", "glb"):
    request = ExportAssemblyRequest.model_validate({**base, "format": fmt})
    print(fmt, hashlib.sha256(export_assembly(request)).hexdigest())
"""


@each_golden
def test_assembly_export_is_byte_deterministic_across_interpreter_restart(
    model_path: Path,
) -> None:
    """Fresh-interpreter export (worker-restart emulation, RESEARCH §9) → the
    same bytes as this process in ALL FOUR formats, under a different
    PYTHONHASHSEED. 3MF is the demanding one: lib3mf mints five random UUIDs
    per write, so this proves ``_canonicalise_3mf_ids`` survives a process
    boundary the way the pinned STEP timestamp does."""
    name = model_path.parent.name
    digests = {
        fmt: hashlib.sha256(
            export_assembly(_export_request(model_path, fmt))
        ).hexdigest()
        for fmt in ("step", "stl", "3mf", "glb")
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


# --- guard: non-identity solved rotation + 3 instances + repeated part ----------
#
# BOTH shipped goldens (assembly-two-plates-{bolted,gap}) solve EVERY instance to
# the IDENTITY orientation, so neither exercises a non-identity rotation through
# the kernel ``_placed_body`` gp_Quaternion -> gp_Trsf placement path: a transpose
# of the rotation matrix, or a quaternion component-order swap ((x,y,z,w) vs
# (w,x,y,z)), maps identity -> identity and would pass the entire shipped suite
# while placing every rotated body WRONG. This guard exercises a genuinely
# non-axis-aligned solved rotation, 3 instances, and a REPEATED part (one
# part_key, three instances) — the three round-trip cases the identity-only
# 2-instance goldens miss (geometry-qa audit 2026-07-23, docs/GEOMETRY-QA.md).
#
# The plate part is the shipped ``sketch-extrude-plate-2holes`` golden reused via
# the bolted golden's instance-0 features; its independently HAND-DERIVED mass
# properties (goldens-assembly/*/expected.json "derivation") are the oracle,
# measured to equal OCCT to 0.0 (probe 2026-07-23), so the expected world
# centroid below shares NO code with the OCCT path (nor with ``Pose``) under test.
_PLATE_LOCAL_CENTROID = np.array([20.0, 12.5, 5.0])
_PLATE_VOLUME = 8429.203673205104
_PLATE_AREA = 3614.159265358979


def _rodrigues(axis: tuple[float, float, float], angle_deg: float) -> np.ndarray:
    """Independent rotation matrix via Rodrigues — the world-pose oracle.

    Deliberately NOT built from a quaternion (neither the OCCT ``gp_Quaternion``
    under test nor ``geometry.assembly.transform.Pose``'s quaternion matrix), so a
    shared quaternion-convention bug cannot hide behind a matching oracle.
    """
    a = np.array(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    th = math.radians(angle_deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * k + (1 - math.cos(th)) * (k @ k)


def _axis_angle_quat(
    axis: tuple[float, float, float], angle_deg: float
) -> tuple[float, float, float, float]:
    """The (x, y, z, w) unit quaternion for the same axis+angle (request side)."""
    a = np.array(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    th = math.radians(angle_deg)
    v = a * math.sin(th / 2)
    return (float(v[0]), float(v[1]), float(v[2]), float(math.cos(th / 2)))


def _plate_features() -> list[EvaluatedFeatureInput]:
    bolted = GOLDENS_DIR / "assembly-two-plates-bolted" / "model.json"
    return _load_request(bolted).instances[0].features


def test_step_assembly_export_preserves_human_readable_product_names_roundtrip(
    roundtrip_tol: float,
) -> None:
    """REGRESSION (FINDINGS #7): a Loft->STEP->Loft round trip preserves the
    human-readable instance NAME as the PRODUCT name, never the instance UUID.

    Before the fix the export wrote ``str(instance_id)`` as every PRODUCT name, so
    a re-import recovered parts named ``c8f8baa9-…`` — positions survived but
    identity did not. Here two GROUNDED, NAMED plate instances at distinct
    positions export to STEP; the exported PRODUCT names are the human-readable
    names (and the UUIDs are ABSENT), and re-importing through the assembly reader
    recovers exactly those names paired with their authored placements — identity
    AND position survive the round trip.
    """
    features = _plate_features()
    named = [("Base Plate", (0.0, 0.0, 0.0)), ("Top Plate", (60.0, 0.0, 0.0))]
    instances: list[EvaluatedInstance] = []
    for n, (label, pos) in enumerate(named, start=1):
        instances.append(
            EvaluatedInstance(
                instance_id=uuid.UUID(int=n),
                part_key=f"plate-named-{n}@1",
                name=label,
                features=[f.model_copy(deep=True) for f in features],
                placement=Placement(position=Vec3(x=pos[0], y=pos[1], z=pos[2])),
                grounded=True,
            )
        )
    request = ExportAssemblyRequest(
        assembly_id=uuid.UUID(int=7),
        version=1,
        instances=instances,
        mates=[],
        linear_deflection=0.1,
        format="step",
    )

    data = export_assembly(request)
    assert data.startswith(STEP_MAGIC)

    # Export side: the human-readable names are PRODUCT names; the UUIDs are NOT.
    product_names = {n.decode("ascii") for n in _PRODUCT_RE.findall(data)}
    for label, _pos in named:
        assert label in product_names, (
            f"human-readable name {label!r} is not a PRODUCT name in the exported "
            f"STEP (found {sorted(product_names)}) — the UUID leaked instead"
        )
    for inst in instances:
        assert str(inst.instance_id) not in product_names, (
            f"instance UUID {inst.instance_id} leaked as a PRODUCT name — the "
            f"FINDINGS #7 regression (found {sorted(product_names)})"
        )

    # Round trip: re-import and confirm the names AND placements both survived.
    result = import_step_assembly(StepAssemblyImportRequest(data=data.decode("utf-8")))
    assert {p.name for p in result.products} == {label for label, _ in named}, (
        f"round-trip names {[p.name for p in result.products]} do not match the "
        f"authored names {[label for label, _ in named]}"
    )
    by_name = {p.name: p for p in result.products}
    for label, pos in named:
        got = by_name[label].placement.position
        assert (got.x, got.y, got.z) == pytest.approx(pos, abs=roundtrip_tol), (
            f"{label!r} imported at {(got.x, got.y, got.z)}, authored {pos} — a "
            f"placement regressed while fixing the name (tol {roundtrip_tol!r})"
        )


def test_step_assembly_export_nonidentity_rotation_roundtrip(
    tmp_path: Path, roundtrip_tol: float
) -> None:
    """GUARD: a non-axis-aligned solved rotation + 3 instances of one REPEATED
    part round-trip to the CORRECT world pose (transpose / quat-order guard).

    Three GROUNDED instances of a single plate part (no mates) so each stays at
    its authored == solved placement; the third carries a 50 deg rotation about
    the off-axis (1,2,3). Export STEP -> re-import -> each recovered solid's world
    centroid matches an INDEPENDENT Rodrigues oracle within the kernel round-trip
    bound, and all three (distinct) instance ids appear as distinct PRODUCT names.
    """
    features = _plate_features()
    specs = [
        ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.0),
        ((100.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.0),
        ((5.0, -2.0, 8.0), (1.0, 2.0, 3.0), 50.0),
    ]
    instances: list[EvaluatedInstance] = []
    expected: list[tuple[float, float, tuple[float, float, float]]] = []
    for n, (pos, axis, ang) in enumerate(specs, start=1):
        qx, qy, qz, qw = _axis_angle_quat(axis, ang)
        instances.append(
            EvaluatedInstance(
                instance_id=uuid.UUID(int=n),
                part_key="plate-guard@1",  # SAME key for all three: repeated part
                features=[f.model_copy(deep=True) for f in features],
                placement=Placement(
                    position=Vec3(x=pos[0], y=pos[1], z=pos[2]),
                    orientation=Quat(x=qx, y=qy, z=qz, w=qw),
                ),
                grounded=True,
            )
        )
        world = _rodrigues(axis, ang) @ _PLATE_LOCAL_CENTROID + np.array(pos)
        expected.append(
            (
                _PLATE_VOLUME,
                _PLATE_AREA,
                (float(world[0]), float(world[1]), float(world[2])),
            )
        )

    request = ExportAssemblyRequest(
        assembly_id=uuid.UUID(int=0xA55),
        version=1,
        instances=instances,
        mates=[],
        linear_deflection=0.1,
        format="step",
    )

    data = export_assembly(request)
    assert data.startswith(STEP_MAGIC)

    step_path = tmp_path / "rot.step"
    step_path.write_bytes(data)
    solids = import_step(step_path).solids()
    assert len(solids) == len(expected), (
        f"expected {len(expected)} solids, got {len(solids)}"
    )

    remaining = list(expected)
    for solid in solids:
        props = measure_shape(solid)
        got = (props.centroid.x, props.centroid.y, props.centroid.z)
        nearest = min(
            remaining,
            key=lambda e: sum((g - w) ** 2 for g, w in zip(got, e[2], strict=True)),
        )
        for axis_label, g, w in zip("xyz", got, nearest[2], strict=True):
            assert g == pytest.approx(w, abs=roundtrip_tol), (
                f"rotated round-trip: re-imported centroid.{axis_label} {g!r} does "
                f"not match the independent Rodrigues world pose {w!r} (tol "
                f"{roundtrip_tol!r}) — a transpose / quaternion-order defect in "
                f"_placed_body would land the body here"
            )
        assert props.volume == pytest.approx(nearest[0], abs=roundtrip_tol)
        assert props.surface_area == pytest.approx(nearest[1], abs=roundtrip_tol)
        remaining.remove(nearest)
    assert not remaining, f"{len(remaining)} placed body(s) never recovered"

    # Repeated part must not collide: three DISTINCT named OCCURRENCES of the one
    # shared part (instanced product structure, audit N8 — the part is a single
    # PRODUCT, so instance identity lives on the occurrence, not on a PRODUCT).
    occurrence_names = [n.decode("ascii") for n in _OCCURRENCE_NAME_RE.findall(data)]
    for inst in instances:
        assert occurrence_names.count(str(inst.instance_id)) == 1, (
            f"instance {inst.instance_id} is not a single distinct occurrence name "
            f"(repeated-part occurrences collided or duplicated): {occurrence_names}"
        )
    counts = _entity_counts(data)
    assert counts["MANIFOLD_SOLID_BREP"] == 1, (
        "three instances of ONE part must write ONE B-rep placed three times, got "
        f"{counts['MANIFOLD_SOLID_BREP']} solids"
    )


# --- audit N8: an assembly STEP INSTANCES its parts, it does not duplicate them --
#
# Measured before the fix on a 21-instance assembly: 21 MANIFOLD_SOLID_BREP for 2
# unique parts, 216,689 bytes. Twenty-one copies of geometry where AP214 product
# structure writes one part and places it twenty-one times — a file-size multiplier
# AND a semantic loss (a downstream BOM derived from the STEP read 20 line items
# where Loft's own BOM correctly says qty 20, and a change to one instance was not
# a change to all). Root cause: build123d's ``Shape.located`` is a DEEP GEOMETRIC
# COPY (BRepBuilderAPI_Copy inside ``__deepcopy__``), so the placed occurrences
# shared no TShape and no writer could have found the instancing.
#
# These gates assert on the EXPORTED BYTES — the entity histogram is exactly what
# the receiving CAD reads, and a composer that returns the right structure while a
# caller flattens it would still pass a return-value test.


def _unique_part_keys(request: ExportAssemblyRequest) -> set[str]:
    return {inst.part_key for inst in request.instances}


@each_golden
def test_step_assembly_export_writes_one_brep_per_unique_part(
    model_path: Path,
) -> None:
    """Every shipped golden: solid count == UNIQUE part count, not instance count.

    Both goldens are two instances of ONE part, so a regression to per-instance
    duplication doubles the B-rep count here and fails.
    """
    name = model_path.parent.name
    request = _export_request(model_path, "step")
    counts = _entity_counts(export_assembly(request))
    unique_parts = len(_unique_part_keys(request))

    assert counts["MANIFOLD_SOLID_BREP"] == unique_parts, (
        f"{name}: {counts['MANIFOLD_SOLID_BREP']} B-reps written for {unique_parts} "
        f"unique part(s) across {len(request.instances)} instances — the geometry "
        f"is duplicated per instance instead of instanced (audit N8)"
    )
    assert counts["NEXT_ASSEMBLY_USAGE_OCCURRENCE"] == len(request.instances), (
        f"{name}: {counts['NEXT_ASSEMBLY_USAGE_OCCURRENCE']} occurrences for "
        f"{len(request.instances)} instances — an instance lost its placement"
    )


def _many_instance_request(pin_count: int) -> ExportAssemblyRequest:
    """The audit's shape of assembly: 1 bracket + N dowel pins of ONE part.

    Two unique parts, ``1 + pin_count`` instances, each named the way documents
    names them (``<part name> <n>``). Grounded so every instance stays at its
    authored placement (no mate solve needed for a file-structure assertion).
    """
    features = _plate_features()
    instances = [
        EvaluatedInstance(
            instance_id=uuid.UUID(int=1),
            part_key="bracket@1",
            name="Motor Mount Bracket <1>",
            features=[f.model_copy(deep=True) for f in features],
            placement=Placement(position=Vec3(x=0.0, y=0.0, z=0.0)),
            grounded=True,
        )
    ]
    for n in range(1, pin_count + 1):
        instances.append(
            EvaluatedInstance(
                instance_id=uuid.UUID(int=100 + n),
                part_key="dowel-pin-8x24@1",  # ONE part, N instances
                name=f"Dowel Pin 8x24 <{n}>",
                features=[f.model_copy(deep=True) for f in features],
                placement=Placement(position=Vec3(x=60.0 * n, y=0.0, z=0.0)),
                grounded=True,
            )
        )
    return ExportAssemblyRequest(
        assembly_id=uuid.UUID(int=0xB0B),
        version=1,
        instances=instances,
        mates=[],
        linear_deflection=0.1,
        format="step",
    )


def test_step_assembly_export_instances_twenty_one_occurrences() -> None:
    """The audit's own case: 21 instances of 2 parts -> 2 B-reps, 21 occurrences.

    Asserted on the exported bytes: the part geometry appears ONCE per unique
    part, each occurrence is a placed ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` with its
    own ``ITEM_DEFINED_TRANSFORMATION``, and the file names one PRODUCT per part
    (occurrence suffix stripped) plus the assembly root — so a receiving CAD/PLM
    reads "one dowel pin used twenty times", not twenty distinct products.
    """
    request = _many_instance_request(20)
    data = export_assembly(request)
    counts = _entity_counts(data)

    assert counts["MANIFOLD_SOLID_BREP"] == 2, (
        f"21 instances of 2 unique parts wrote {counts['MANIFOLD_SOLID_BREP']} "
        f"B-reps; instanced product structure writes 2 (audit N8)"
    )
    assert counts["NEXT_ASSEMBLY_USAGE_OCCURRENCE"] == 21
    assert counts["ITEM_DEFINED_TRANSFORMATION"] == 21, (
        "every occurrence carries its own placement transform"
    )
    product_names = [n.decode("ascii") for n in _PRODUCT_RE.findall(data)]
    assert product_names.count("Dowel Pin 8x24") == 1, (
        f"the shared part must be ONE product named for the PART, not per "
        f"instance: {product_names}"
    )
    assert product_names.count("Motor Mount Bracket") == 1, product_names
    assert not [n for n in product_names if "<" in n], (
        f"an occurrence suffix leaked into a PRODUCT name: {product_names}"
    )
    # Instance identity survives on the occurrences (all 21, distinct).
    occurrence_names = [n.decode("ascii") for n in _OCCURRENCE_NAME_RE.findall(data)]
    assert sorted(occurrence_names) == sorted(
        [inst.name for inst in request.instances if inst.name is not None]
    ), occurrence_names


def test_step_assembly_export_size_does_not_scale_with_instance_count() -> None:
    """Adding 15 more instances of a part adds placements, not part geometry.

    The user-visible half of N8 ("size scales linearly, ~1 MB at 100 fasteners"):
    5 -> 20 pins quadruples the instance count; the per-instance cost must be a
    few hundred bytes of product structure, not another copy of the solid. The
    bound is generous on purpose — it fails a return to duplication (which costs
    ~a full B-rep per instance) without pinning an OCCT byte count.
    """
    small = len(export_assembly(_many_instance_request(5)))
    large = len(export_assembly(_many_instance_request(20)))
    per_instance = (large - small) / 15

    assert per_instance < 1000, (
        f"each extra instance cost {per_instance:.0f} bytes ({small} -> {large} "
        f"for 5 -> 20 pins) — the part geometry is being duplicated per instance"
    )
