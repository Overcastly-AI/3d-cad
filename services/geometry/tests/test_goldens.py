"""Golden-model harness — gates 1 and 3 of the geometry QA strategy
(docs/RESEARCH.md §9, .claude/skills/geometry-gates/SKILL.md).

Discovers every golden under ``services/geometry/goldens/`` and, for each:

* rebuilds it through :func:`geometry.harness.evaluate_model`, which
  dispatches to the same evaluation paths the REST routes and the worker
  task share (``evaluate_tessellation`` for shape goldens, ``evaluate_tree``
  for feature-tree goldens);
* asserts mass properties (volume, surface area, centroid, exact AABB)
  within the golden's **documented per-model tolerance** from
  ``expected.json`` (never an ad-hoc epsilon — CLAUDE.md conventions);
* asserts topology counts (faces/edges/shells) and mesh counts
  (vertices/triangles) **exactly**;
* rebuilds twice in-process and once in a fresh interpreter and requires
  byte-identical GLB plus identical metadata (determinism gate). This is the
  canonical determinism home; it strictly subsumes the former
  ``test_kernel.py::test_tessellation_is_deterministic`` (same request, same
  byte-strength assertion, plus the cross-process leg), which was removed.

Adding a golden requires ZERO runner changes: drop
``goldens/<name>/model.json`` (a serialized ``TessellateRequest`` for a
single shape, or a serialized ``EvaluateTreeRequest`` for a feature tree —
:mod:`geometry.harness` owns the dispatch) and ``goldens/<name>/expected.json``
next to it. Expectations must be hand-derived or independently cross-checked
— a golden recorded from buggy harness output enshrines the bug
(geometry-gates skill rule).
"""

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from geometry.harness import ModelRequest, evaluate_model, load_model_request
from geometry.schemas import BoundingBox, TopologyCounts, Vec3
from pydantic import BaseModel, ConfigDict, Field

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"


class ExpectedMassProperties(BaseModel):
    """Mass-property expectations, asserted within the golden's tolerance."""

    model_config = ConfigDict(extra="forbid")

    volume: float = Field(gt=0, description="Volume (mm^3)")
    surface_area: float = Field(gt=0, description="Total surface area (mm^2)")
    centroid: Vec3
    bounding_box: BoundingBox


class ExpectedMesh(BaseModel):
    """Tessellation-artifact expectations, asserted exactly.

    GLB byte size is intentionally absent: it is covered by the byte-level
    determinism gate within a kernel version, and pinning the absolute size
    would break on glTF-writer upgrades without geometric meaning.
    """

    model_config = ConfigDict(extra="forbid")

    vertices: int = Field(ge=3)
    triangles: int = Field(ge=1)


class GoldenExpectation(BaseModel):
    """Committed expectations for one golden model (``expected.json``).

    ``tolerance`` is the reviewed per-model bound for mass-property
    assertions. Loosening it is never a fix for a red run: it is a reviewed
    decision requiring kernel-level justification recorded in
    ``tolerance_rationale`` AND ``docs/GEOMETRY-QA.md``. Topology and mesh
    counts take no tolerance — they match exactly or the golden fails.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str] = Field(
        description="Hand derivation of the expected values, line by line"
    )
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    properties: ExpectedMassProperties
    topology: TopologyCounts
    mesh: ExpectedMesh


@dataclass(frozen=True)
class GoldenCase:
    """A discovered golden: its name, build request, and expectations."""

    name: str
    request: ModelRequest
    expected: GoldenExpectation


def _load_goldens() -> list[GoldenCase]:
    """Discover and validate every golden directory. Malformed goldens fail
    collection loudly (pydantic ``extra="forbid"`` catches typo'd keys)."""
    cases: list[GoldenCase] = []
    for model_path in sorted(GOLDENS_DIR.glob("*/model.json")):
        golden_dir = model_path.parent
        cases.append(
            GoldenCase(
                name=golden_dir.name,
                request=load_model_request(model_path.read_text(encoding="utf-8")),
                expected=GoldenExpectation.model_validate_json(
                    (golden_dir / "expected.json").read_text(encoding="utf-8")
                ),
            )
        )
    return cases


GOLDEN_CASES = _load_goldens()
each_golden = pytest.mark.parametrize(
    "case", GOLDEN_CASES, ids=[case.name for case in GOLDEN_CASES]
)


def test_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert GOLDEN_CASES, f"no goldens discovered under {GOLDENS_DIR}"


def test_every_golden_dir_is_complete() -> None:
    """Every directory under goldens/ carries both halves of a golden."""
    for golden_dir in sorted(p for p in GOLDENS_DIR.iterdir() if p.is_dir()):
        assert (golden_dir / "model.json").is_file(), f"{golden_dir}: model.json"
        assert (golden_dir / "expected.json").is_file(), f"{golden_dir}: expected.json"


@each_golden
def test_mass_properties_within_documented_tolerance(case: GoldenCase) -> None:
    _, metadata = evaluate_model(case.request)
    actual = metadata.properties
    expected = case.expected.properties
    tolerance = case.expected.tolerance

    checks: list[tuple[str, float, float]] = [
        ("volume", actual.volume, expected.volume),
        ("surface_area", actual.surface_area, expected.surface_area),
        ("centroid.x", actual.centroid.x, expected.centroid.x),
        ("centroid.y", actual.centroid.y, expected.centroid.y),
        ("centroid.z", actual.centroid.z, expected.centroid.z),
        ("bbox.min.x", actual.bounding_box.min.x, expected.bounding_box.min.x),
        ("bbox.min.y", actual.bounding_box.min.y, expected.bounding_box.min.y),
        ("bbox.min.z", actual.bounding_box.min.z, expected.bounding_box.min.z),
        ("bbox.max.x", actual.bounding_box.max.x, expected.bounding_box.max.x),
        ("bbox.max.y", actual.bounding_box.max.y, expected.bounding_box.max.y),
        ("bbox.max.z", actual.bounding_box.max.z, expected.bounding_box.max.z),
    ]
    for label, got, want in checks:
        assert got == pytest.approx(want, abs=tolerance), (
            f"{case.name}: {label} expected {want!r}, got {got!r} "
            f"(documented tolerance {tolerance!r} — never loosen to go green; "
            f"see expected.json tolerance_rationale)"
        )


@each_golden
def test_topology_and_mesh_counts_exact(case: GoldenCase) -> None:
    """Exact-match gate: a changed count is a real geometric change —
    explain it or fix it (geometry-gates skill), never widen it."""
    glb, metadata = evaluate_model(case.request)

    assert metadata.properties.topology == case.expected.topology, (
        f"{case.name}: topology expected "
        f"{case.expected.topology.model_dump()}, "
        f"got {metadata.properties.topology.model_dump()}"
    )
    assert metadata.mesh.vertices == case.expected.mesh.vertices, case.name
    assert metadata.mesh.triangles == case.expected.mesh.triangles, case.name
    assert metadata.mesh.glb_bytes == len(glb), case.name


@each_golden
def test_rebuild_is_deterministic_in_process(case: GoldenCase) -> None:
    """Same request twice → identical metadata AND byte-identical GLB.

    Canonical home of the determinism gate (RESEARCH §9); any flake here is
    a P0, not a retry.
    """
    glb_a, meta_a = evaluate_model(case.request)
    glb_b, meta_b = evaluate_model(case.request)

    assert meta_a == meta_b, f"{case.name}: metadata differs between rebuilds"
    assert glb_a == glb_b, f"{case.name}: GLB bytes differ between rebuilds"


#: Rebuilds a request (JSON on stdin) in a pristine interpreter and reports
#: the GLB digest + metadata, emulating a worker-process restart.
_RESTART_PROBE = """\
import hashlib
import sys

from geometry.harness import evaluate_model, load_model_request

glb, metadata = evaluate_model(load_model_request(sys.stdin.read()))
print(hashlib.sha256(glb).hexdigest())
print(metadata.model_dump_json())
"""


@each_golden
def test_rebuild_is_deterministic_across_interpreter_restart(
    case: GoldenCase,
) -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, RESEARCH §9)
    must produce the same GLB bytes and metadata as this process."""
    glb, metadata = evaluate_model(case.request)

    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=case.request.model_dump_json(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{case.name}: restart probe failed:\n{result.stderr}"
    )

    remote_digest, remote_metadata = result.stdout.splitlines()
    assert remote_digest == hashlib.sha256(glb).hexdigest(), (
        f"{case.name}: GLB bytes differ across interpreter restart"
    )
    assert remote_metadata == metadata.model_dump_json(), (
        f"{case.name}: metadata differs across interpreter restart"
    )
