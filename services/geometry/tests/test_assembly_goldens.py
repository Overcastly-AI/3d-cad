"""Assembly golden-model harness — the v1 DoD correctness gate (design
``assemblies.md`` §6; RESEARCH §9).

The assembly analogue of :mod:`tests.test_goldens`. Assembly correctness is
ANALYTICALLY checkable (design §6): a bolted joint's solved transforms and the
combined mass-property roll-up are exact hand-derivable values, so this pillar is
gateable as rigorously as parts. Discovers every golden under
``services/geometry/goldens-assembly/`` and, for each:

* rebuilds it through :func:`geometry.assembly.evaluate_assembly` (the SAME
  function the ``POST /api/v1/assembly/evaluate`` route calls);
* asserts each instance's SOLVED :class:`Placement` equals the hand-derived
  analytic transform within the golden's DOCUMENTED per-model tolerance (§6.1 —
  never an ad-hoc epsilon; quaternion compared via its rotation matrix so the
  assertion is immune to the ``±q`` double cover);
* asserts the combined mass properties equal the analytic roll-up (§6.1);
* asserts the solve ``status`` and the SHARED-MESH dedup contract (§6.4 — the
  same part instanced twice yields ONE ``part_mesh_glb_id``);
* rebuilds twice in-process and once in a fresh interpreter and requires a
  byte-identical result (the §6.2 solve-determinism gate, in 3D — bitwise-stable
  mesh ids AND solved transforms, the BLAS pin from #2 holding across restart).

Adding an assembly golden requires ZERO runner changes: drop
``goldens-assembly/<name>/model.json`` (a serialized ``EvaluateAssemblyRequest``)
and ``goldens-assembly/<name>/expected.json`` next to it.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from geometry.assembly import evaluate_assembly
from geometry.assembly.transform import Pose
from py_kit.schemas.assemblies import (
    AssemblySolveStatus,
    EvaluateAssemblyRequest,
    Placement,
)
from py_kit.schemas.geometry import BoundingBox, Vec3
from pydantic import BaseModel, ConfigDict, Field

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens-assembly"


class ExpectedInstancePlacement(BaseModel):
    """One instance's expected SOLVED placement (hand-derived, design §6.1)."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    placement: Placement


class ExpectedCombinedProperties(BaseModel):
    """Combined mass-property expectations, asserted within tolerance (§6.1)."""

    model_config = ConfigDict(extra="forbid")

    volume: float = Field(gt=0)
    surface_area: float = Field(gt=0)
    centroid: Vec3
    bounding_box: BoundingBox


class ExpectedTopology(BaseModel):
    """Summed per-instance topology counts, asserted exactly (§4 roll-up)."""

    model_config = ConfigDict(extra="forbid")

    faces: int
    edges: int
    shells: int


class AssemblyGoldenExpectation(BaseModel):
    """Committed expectations for one assembly golden (``expected.json``).

    ``tolerance`` is the reviewed per-model bound for solved-placement + combined
    mass-property assertions (§6.1). Loosening it is never a fix for a red run: it
    is a reviewed decision requiring justification in ``tolerance_rationale`` AND
    ``docs/GEOMETRY-QA.md``. ``status`` / ``distinct_mesh_count`` / ``topology``
    take no tolerance — they match exactly or the golden fails.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    status: AssemblySolveStatus
    distinct_mesh_count: int = Field(ge=1)
    instances: list[ExpectedInstancePlacement]
    properties: ExpectedCombinedProperties
    topology: ExpectedTopology


@dataclass(frozen=True)
class AssemblyGoldenCase:
    """A discovered assembly golden: its name, request, and expectations."""

    name: str
    request: EvaluateAssemblyRequest
    expected: AssemblyGoldenExpectation


def _load_goldens() -> list[AssemblyGoldenCase]:
    cases: list[AssemblyGoldenCase] = []
    for model_path in sorted(GOLDENS_DIR.glob("*/model.json")):
        golden_dir = model_path.parent
        cases.append(
            AssemblyGoldenCase(
                name=golden_dir.name,
                request=EvaluateAssemblyRequest.model_validate_json(
                    model_path.read_text(encoding="utf-8")
                ),
                expected=AssemblyGoldenExpectation.model_validate_json(
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
    assert GOLDEN_CASES, f"no assembly goldens discovered under {GOLDENS_DIR}"


def test_every_golden_dir_is_complete() -> None:
    for golden_dir in sorted(p for p in GOLDENS_DIR.iterdir() if p.is_dir()):
        assert (golden_dir / "model.json").is_file(), f"{golden_dir}: model.json"
        assert (golden_dir / "expected.json").is_file(), f"{golden_dir}: expected.json"


@each_golden
def test_solved_placements_match_analytic_transform(case: AssemblyGoldenCase) -> None:
    """Each instance's SOLVED placement equals the hand-derived analytic transform
    within the documented tolerance (design §6.1)."""
    result = evaluate_assembly(case.request)
    assert result.status == case.expected.status, (
        f"{case.name}: status expected {case.expected.status}, got {result.status}"
    )

    tolerance = case.expected.tolerance
    got_by_id = {str(inst.instance_id): inst.placement for inst in result.instances}
    for want in case.expected.instances:
        got = got_by_id[want.instance_id]
        # Translation: component-wise within tolerance.
        for axis, g, w in (
            ("x", got.position.x, want.placement.position.x),
            ("y", got.position.y, want.placement.position.y),
            ("z", got.position.z, want.placement.position.z),
        ):
            assert g == pytest.approx(w, abs=tolerance), (
                f"{case.name}: instance {want.instance_id} position.{axis} "
                f"expected {w!r}, got {g!r} (documented tolerance {tolerance!r} — "
                "never loosen to go green; see expected.json tolerance_rationale)"
            )
        # Orientation via the rotation matrix — immune to the ±q double cover.
        got_r = Pose.from_placement(got).matrix()
        want_r = Pose.from_placement(want.placement).matrix()
        assert got_r == pytest.approx(want_r, abs=tolerance), (
            f"{case.name}: instance {want.instance_id} orientation differs from "
            f"the analytic transform beyond {tolerance!r}"
        )


@each_golden
def test_combined_properties_match_analytic_rollup(case: AssemblyGoldenCase) -> None:
    """Combined mass properties equal the analytic roll-up (design §6.1)."""
    result = evaluate_assembly(case.request)
    assert result.properties is not None, f"{case.name}: no combined properties"
    actual = result.properties
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
            f"{case.name}: combined {label} expected {want!r}, got {got!r} "
            f"(documented tolerance {tolerance!r}; see tolerance_rationale)"
        )
    # bounding_box mirrors properties.bounding_box (the convenience field).
    assert result.bounding_box == actual.bounding_box, case.name


@each_golden
def test_topology_rollup_and_shared_mesh_dedup(case: AssemblyGoldenCase) -> None:
    """Summed topology exact + the SHARED-MESH dedup contract (design §6.4).

    The whole point of per-instance-transform-over-shared-mesh: the same part
    instanced N times yields ONE distinct ``part_mesh_glb_id``."""
    result = evaluate_assembly(case.request)
    assert result.properties is not None
    topo = result.properties.topology
    assert (topo.faces, topo.edges, topo.shells) == (
        case.expected.topology.faces,
        case.expected.topology.edges,
        case.expected.topology.shells,
    ), f"{case.name}: combined topology mismatch"

    mesh_ids = {inst.part_mesh_glb_id for inst in result.instances}
    assert None not in mesh_ids, f"{case.name}: an instance produced no mesh"
    assert len(mesh_ids) == case.expected.distinct_mesh_count, (
        f"{case.name}: expected {case.expected.distinct_mesh_count} distinct "
        f"part_mesh_glb_id(s) (shared-mesh dedup, §6.4), got {len(mesh_ids)}"
    )
    # Every instance carries a content address (sha256:<hex>), never a raw hash.
    for inst in result.instances:
        assert inst.part_mesh_glb_id is not None
        assert inst.part_mesh_glb_id.startswith("sha256:"), case.name


@each_golden
def test_rebuild_is_deterministic_in_process(case: AssemblyGoldenCase) -> None:
    """Same request twice → byte-identical result JSON (the §6.2 determinism gate,
    in 3D: bitwise-stable mesh ids AND solved transforms). Any flake here is a P0,
    not a retry."""
    first = evaluate_assembly(case.request).model_dump_json()
    second = evaluate_assembly(case.request).model_dump_json()
    assert first == second, f"{case.name}: result differs between rebuilds"


_RESTART_PROBE = """\
import sys

from geometry.assembly import evaluate_assembly
from py_kit.schemas.assemblies import EvaluateAssemblyRequest

request = EvaluateAssemblyRequest.model_validate_json(sys.stdin.read())
print(evaluate_assembly(request).model_dump_json())
"""


@each_golden
def test_rebuild_is_deterministic_across_interpreter_restart(
    case: AssemblyGoldenCase,
) -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, §6.2 / RESEARCH §9)
    must produce the same result JSON as this process — the BLAS pin (#2) fixes
    the solver's floating-point reduction order across processes."""
    local = evaluate_assembly(case.request).model_dump_json()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=case.request.model_dump_json(),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"{case.name}: restart probe failed:\n{result.stderr}"
    )
    assert result.stdout.strip() == local, (
        f"{case.name}: result differs across interpreter restart"
    )
