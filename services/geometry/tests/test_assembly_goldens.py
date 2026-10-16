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

import numpy as np
import pytest
from geometry.assembly import evaluate_assembly
from geometry.assembly.evaluate import solve_assembly
from geometry.assembly.export import export_assembly
from geometry.assembly.transform import Pose
from geometry.kernel.step_tree import (
    Box3,
    StepTreeNode,
    placed_bounding_box,
    read_step_tree,
)
from loft_wire.assemblies import (
    AssemblySolveStatus,
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
    Placement,
)
from loft_wire.geometry import BoundingBox, Vec3
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


class ExpectedJointState(BaseModel):
    """One joint's expected solved state (S4a). ``rot_deg`` / ``lin_mm`` must be
    null exactly when the motion has no such value; ``at_limit`` (S4b) is
    checked exactly when given."""

    model_config = ConfigDict(extra="forbid")

    mate_id: str
    rot_deg: float | None
    lin_mm: float | None
    at_limit: bool | None = None
    axis_world: Vec3


class ExpectedPatternCount(BaseModel):
    """One component pattern's expected count per seed (ASM-A3-PATTERN)."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    count: int


class ExpectedProbe(BaseModel):
    """A point fixed in an instance's part frame and where it must land in the
    world at the solved placement (e.g. a hinge leaf's far edge)."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    local: Vec3
    world: Vec3
    note: str


class ExpectedInContext(BaseModel):
    """One in-context link's expected resolution (ASM-A3-IN-CONTEXT): a
    projected circle's centre and radius in its edited part's frame, and
    whether the evaluation moved it from the stored value."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    state: str
    center: Vec3
    radius: float
    changed: bool


class ExpectedStepNode(BaseModel):
    """Occurrences of one product under a STEP assembly product, in order of
    first appearance: the product's name, how many occurrences share it, and
    (for a sub-assembly) what one of them holds (BIKE2-STEP-FLAT)."""

    model_config = ConfigDict(extra="forbid")

    product: str
    count: int = Field(ge=1)
    children: list[ExpectedStepNode] = Field(default_factory=list["ExpectedStepNode"])


class ExpectedStep(BaseModel):
    """The golden's STEP export read back as a product tree: exported under
    ``name``, which must name the root product; ``breps`` B-reps written."""

    model_config = ConfigDict(extra="forbid")

    name: str
    breps: int = Field(ge=1)
    children: list[ExpectedStepNode]


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
    remaining_dof: int | None = Field(
        default=None, ge=0, description="Diagnosed DOF; checked when given"
    )
    joint_states: list[ExpectedJointState] | None = Field(
        default=None, description="Solved joint states; checked when given"
    )
    pattern_counts: list[ExpectedPatternCount] | None = Field(
        default=None, description="Per-pattern counts; checked when given"
    )
    probes: list[ExpectedProbe] = Field(default_factory=list["ExpectedProbe"])
    in_context: list[ExpectedInContext] | None = Field(
        default=None, description="In-context link resolutions; checked when given"
    )
    step: ExpectedStep | None = Field(
        default=None, description="STEP product tree; checked when given"
    )
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
def test_dof_joint_states_and_probes_match_hand_values(
    case: AssemblyGoldenCase,
) -> None:
    """Joint goldens (S4a): the diagnosed DOF, each joint's solved state and the
    world position of hand-picked body points, within the documented tolerance.
    Goldens that state none of these check nothing here."""
    result = evaluate_assembly(case.request)
    expected = case.expected
    tolerance = expected.tolerance
    if expected.remaining_dof is not None:
        got_dof = 0 if result.diagnosis is None else result.diagnosis.remaining_dof
        assert got_dof == expected.remaining_dof, f"{case.name}: remaining_dof"
    if expected.pattern_counts is not None:
        assert [
            (str(state.pattern_id), state.count, state.error_code)
            for state in result.pattern_states
        ] == [
            (want.pattern_id, want.count, None) for want in expected.pattern_counts
        ], f"{case.name}: pattern counts"
    if expected.joint_states is not None:
        got_states = result.joint_states
        assert [str(js.mate_id) for js in got_states] == [
            js.mate_id for js in expected.joint_states
        ], f"{case.name}: joint_states mate ids"
        for got, want in zip(got_states, expected.joint_states, strict=True):
            if want.at_limit is not None:
                assert got.at_limit is want.at_limit, f"{case.name}: at_limit"
            for label, g, w in (
                ("rot_deg", got.rot_deg, want.rot_deg),
                ("lin_mm", got.lin_mm, want.lin_mm),
            ):
                assert (g is None) == (w is None), f"{case.name}: {label} presence"
                if g is not None and w is not None:
                    assert g == pytest.approx(w, abs=tolerance), (
                        f"{case.name}: joint {want.mate_id} {label} expected {w!r}, "
                        f"got {g!r}"
                    )
            for g, w in (
                (got.axis_world.x, want.axis_world.x),
                (got.axis_world.y, want.axis_world.y),
                (got.axis_world.z, want.axis_world.z),
            ):
                assert g == pytest.approx(w, abs=tolerance), f"{case.name}: axis"
    if expected.in_context is not None:
        got_links = [
            (s.entity_id, s.state, s.resolved, s.changed) for s in result.in_context
        ]
        assert [g[:2] for g in got_links] == [
            (w.entity_id, w.state) for w in expected.in_context
        ], f"{case.name}: in-context links"
        for (_, _, curve, changed), want in zip(
            got_links, expected.in_context, strict=True
        ):
            assert curve is not None and curve.kind == "circle", case.name
            assert changed is want.changed, f"{case.name}: in-context changed"
            assert [curve.center.x, curve.center.y, curve.center.z] == pytest.approx(
                [want.center.x, want.center.y, want.center.z], abs=tolerance
            ), f"{case.name}: in-context centre of {want.entity_id}"
            assert curve.radius == pytest.approx(want.radius, abs=tolerance)
    placements = {str(inst.instance_id): inst.placement for inst in result.instances}
    for probe in expected.probes:
        pose = Pose.from_placement(placements[probe.instance_id])
        local = np.array([probe.local.x, probe.local.y, probe.local.z])
        world = pose.apply_point(local)
        want = np.array([probe.world.x, probe.world.y, probe.world.z])
        assert world == pytest.approx(want, abs=tolerance), (
            f"{case.name}: probe ({probe.note}) expected {want.tolist()}, got "
            f"{world.tolist()}"
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
from loft_wire.assemblies import EvaluateAssemblyRequest

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


def _product_groups(node: StepTreeNode) -> list[ExpectedStepNode]:
    """*node*'s children grouped by the product LABEL they refer to (so a
    shared product is one group), in order of first appearance."""
    groups: dict[str, list[StepTreeNode]] = {}
    for child in node.children:
        groups.setdefault(child.product_label, []).append(child)
    return [
        ExpectedStepNode(
            product=members[0].product or "",
            count=len(members),
            children=_product_groups(members[0]),
        )
        for members in groups.values()
    ]


def _step_leaves(node: StepTreeNode) -> list[StepTreeNode]:
    if not node.children:
        return [node]
    return [leaf for child in node.children for leaf in _step_leaves(child)]


def _flat(box: Box3) -> np.ndarray:
    return np.array([*box[0], *box[1]])


STEP_CASES = [case for case in GOLDEN_CASES if case.expected.step is not None]


def test_a_nested_patterned_golden_carries_a_step_tree() -> None:
    """The STEP tree gate must reach a sub-assembly that holds a pattern."""
    assert any(
        any(
            inst.sub_assembly is not None and inst.sub_assembly.patterns
            for inst in case.request.instances
        )
        for case in STEP_CASES
    ), "no assembly golden checks a nested, patterned STEP tree (BIKE2-STEP-FLAT)"


@pytest.mark.parametrize("case", STEP_CASES, ids=[c.name for c in STEP_CASES])
def test_step_export_keeps_the_product_tree(case: AssemblyGoldenCase) -> None:
    """STEP export -> OCCT XCAF re-import keeps the assembly's structure
    (BIKE2-STEP-FLAT): the root product is named after the assembly, each
    sub-assembly is one nested product however often it is used, pattern copies
    are occurrences of their seed's product, and every part occurrence's
    world-space box (its locations composed down the tree) equals the box of
    its part at the evaluate result's placement, matched by name."""
    step = case.expected.step
    assert step is not None
    tolerance = case.expected.tolerance
    request = ExportAssemblyRequest.model_validate(
        {**case.request.model_dump(mode="json"), "format": "step", "name": step.name}
    )
    data = export_assembly(request)
    tree = read_step_tree(data)

    assert tree.product == step.name, f"{case.name}: root product {tree.product!r}"
    assert _product_groups(tree) == step.children, f"{case.name}: product tree"
    assert data.count(b"MANIFOLD_SOLID_BREP(") == step.breps, f"{case.name}: B-reps"

    # The oracle: every placed part at the placement the evaluate route reports.
    published = {
        inst.instance_id: inst.placement
        for inst in evaluate_assembly(case.request).instances
    }
    expected: list[tuple[str | None, np.ndarray]] = []
    for occ in solve_assembly(case.request).occurrences:
        if occ.body is None:
            continue
        assert published[occ.occurrence_id] == occ.placement, case.name
        pose = Pose.from_placement(occ.placement)
        box = placed_bounding_box(
            occ.body,
            (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
            (float(pose.q[0]), float(pose.q[1]), float(pose.q[2]), float(pose.q[3])),
        )
        expected.append((occ.name, _flat(box)))

    leaves = _step_leaves(tree)
    assert len(leaves) == len(expected), f"{case.name}: part occurrence count"
    remaining = list(expected)
    for leaf in leaves:
        assert leaf.bounding_box is not None
        got = _flat(leaf.bounding_box)
        candidates = [item for item in remaining if item[0] == leaf.name]
        assert candidates, f"{case.name}: no placed part named {leaf.name!r}"
        nearest = min(candidates, key=lambda item: float(np.abs(item[1] - got).max()))
        deviation = float(np.abs(nearest[1] - got).max())
        assert deviation <= tolerance, (
            f"{case.name}: {leaf.name} lands {deviation!r} mm from its evaluated "
            f"placement (tolerance {tolerance!r})"
        )
        remaining.remove(nearest)
    assert not remaining, f"{case.name}: {len(remaining)} placed part(s) missing"
