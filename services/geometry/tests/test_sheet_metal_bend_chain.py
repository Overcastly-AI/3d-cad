"""Depth->=2 bend-chain unfold — SPIKE gate (docs/design/sheet-metal.md sec 4.3).

The tractability proof for the FIRST deferred sheet-metal increment: a flange folded
off ANOTHER flange (a box corner / return / hat channel — depth >= 2), which the
shipped depth-1 unfold rejects. Proves, against HAND-DERIVED analytic values
(independently recomputed here, never read from kernel output), on a body built
through TWO shipped edge-flange folds:

* **Recursive composition works** — F2 (depth 2) is placed in F1's ALREADY-flattened
  frame; its developed BA-strip offset equals the bend allowance to ~3e-15 with NO
  error accumulation through the parent's development (the graph-relaxation fear).
* **Area conservation** (sec 9 #2) — flat_area = base + F1 + F2 + Sigma(BA*width),
  base counted once; each flange's developed area equals its 3D face area (isometry).
* **Placement is exact** — the developed bounding boxes match the hand-derived box-
  corner (perp) / 1D-stack (parallel) layout; the flanges occupy disjoint 2D regions
  (no overlap -> idealised zero-relief blank valid, sec 7).
* **Determinism** (sec 9 #4) — the FlatPattern serializes byte-identically in-process
  and across a fresh interpreter restart.
* **Honest failure** — a disconnected bend set (not one rooted tree) raises typed.

VERDICT: TRACTABLE. See the module docstring + docs/design/sheet-metal.md sec 4.3.
"""

import importlib.util
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from build123d import GeomType
from geometry.kernel.faces import SubshapeUnresolvedError
from geometry.sheet_metal._spike_bend_chain import (
    BendChainError,
    unfold_bend_chain,
)
from geometry.sheet_metal.unfold import BendProvenance
from py_kit.schemas.features import CylindricalFaceSignature
from py_kit.schemas.geometry import Vec3
from pydantic import BaseModel, ConfigDict

_HERE = Path(__file__).resolve().parent
_BUILDER_PATH = _HERE / "_bend_chain_builder.py"
_GOLDENS = _HERE.parent / "goldens-sheet-metal"


class ChainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    base_x_mm: float
    base_y_mm: float
    thickness_mm: float
    bend_radius_mm: float
    leg1_mm: float
    leg2_mm: float
    k_factor: float
    kind: str


class ChainExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float
    tolerance_rationale: str
    max_depth: int
    bend_allowance_mm: float
    flat_area_mm2: float
    flat_length_mm: float
    bend_width_mm: float
    flange_dev_areas_mm2: list[float]
    strip_width_max_residual_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    bend_widths_mm: list[float]
    body_edge_count: int
    bend_edge_count: int
    volume_mm3: float
    volume_tolerance: float
    topology: dict[str, int]
    content_hash: str


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_bend_chain_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BUILDER = _load_builder()


def _load(name: str) -> tuple[ChainModel, ChainExpected]:
    d = _GOLDENS / name
    model = ChainModel.model_validate_json(
        (d / "model.json").read_text(encoding="utf-8")
    )
    expected = ChainExpected.model_validate_json(
        (d / "expected.json").read_text(encoding="utf-8")
    )
    return model, expected


def _build(model: ChainModel):  # type: ignore[no-untyped-def]
    return _BUILDER.build_bend_chain(
        model.base_x_mm,
        model.base_y_mm,
        model.thickness_mm,
        model.bend_radius_mm,
        model.leg1_mm,
        model.leg2_mm,
        model.k_factor,
        model.kind,
    )


def _unfold(model: ChainModel):  # type: ignore[no-untyped-def]
    built = _build(model)
    return built, unfold_bend_chain(
        built.body, built.bends, model.thickness_mm, model.k_factor
    )


_CASES = ["spike-bend-chain-corner", "spike-bend-chain-parallel"]


def _hand_ba(model: ChainModel) -> float:
    """BA = (pi/2)(r + K t), recomputed from first principles (not the golden)."""
    return (math.pi / 2.0) * (
        model.bend_radius_mm + model.k_factor * model.thickness_mm
    )


@pytest.mark.parametrize("name", _CASES)
def test_golden_matches_hand_derivation(name: str) -> None:
    """The committed golden's headline numbers equal an independent hand derivation."""
    model, expected = _load(name)
    ba = _hand_ba(model)
    tol = expected.tolerance
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)

    base_area = model.base_x_mm * model.base_y_mm
    f1_area = model.leg1_mm * model.base_x_mm
    # perp: F2 folds off F1's side edge -> width = F1's developed leg (25); parallel:
    # F2 folds off F1's free edge -> width = the base edge (40).
    f2_width = model.leg1_mm if model.kind == "perp" else model.base_x_mm
    f2_area = model.leg2_mm * f2_width
    strips = ba * model.base_x_mm + ba * f2_width
    flat_area = base_area + f1_area + f2_area + strips
    assert flat_area == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert sorted([base_area, f1_area, f2_area]) == pytest.approx(
        sorted(expected.flange_dev_areas_mm2), abs=tol
    )


@pytest.mark.parametrize("name", _CASES)
def test_is_a_genuine_depth_2_chain(name: str) -> None:
    """max tree depth is 2 — F2 folds off F1, not the base (a real bend chain)."""
    model, expected = _load(name)
    _, result = _unfold(model)
    assert result.max_depth == 2 == expected.max_depth


@pytest.mark.parametrize("name", _CASES)
def test_recursive_composition_has_no_accumulation(name: str) -> None:
    """The depth-2 crux: each developed BA-strip equals the bend allowance to FP
    scale, PROVING F2's placement composed correctly through F1's already-flattened
    frame with no relaxation and no error accumulation."""
    model, expected = _load(name)
    _, result = _unfold(model)
    ba = _hand_ba(model)
    assert len(result.strip_widths_mm) == 2
    resid = max(abs(s - ba) for s in result.strip_widths_mm)
    assert resid <= expected.strip_width_max_residual_mm
    assert resid <= 1e-12  # far tighter than the kernel linear tolerance


@pytest.mark.parametrize("name", _CASES)
def test_area_conservation_and_isometry(name: str) -> None:
    """sec 9 #2: flat_area conserves the neutral surface, and each flange's developed
    2D area equals its 3D face area (the map is a rigid isometry)."""
    model, expected = _load(name)
    built, result = _unfold(model)
    tol = expected.tolerance
    assert result.pattern.flat_area_mm2 == pytest.approx(
        expected.flat_area_mm2, abs=tol
    )

    # Each developed flange area == its 3D planar face area (the map is an isometry):
    # every reported developed area is present among the body's planar face areas.
    body_face_areas = [
        float(f.area) for f in built.body.faces() if f.geom_type == GeomType.PLANE
    ]
    for dev in result.flange_dev_areas_mm2:
        assert any(abs(dev - fa) <= tol for fa in body_face_areas), (
            f"developed area {dev} matches no 3D planar face (not an isometry)"
        )
    assert sorted(result.flange_dev_areas_mm2) == pytest.approx(
        sorted(expected.flange_dev_areas_mm2), abs=tol
    )


@pytest.mark.parametrize("name", _CASES)
def test_developed_placement_and_no_overlap(name: str) -> None:
    """The developed bounding boxes match the hand-derived layout, and the three
    flange regions are pairwise DISJOINT (no overlap -> zero-relief blank valid)."""
    model, expected = _load(name)
    _, result = _unfold(model)
    tol = expected.tolerance
    assert result.pattern.flat_length_mm == pytest.approx(
        expected.flat_length_mm, abs=tol
    )
    assert result.pattern.bend_width_mm == pytest.approx(
        expected.bend_width_mm, abs=tol
    )

    boxes = result.flange_bboxes

    def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
        # positive-area intersection (touching edges do not count)
        ix = min(a[2], b[2]) - max(a[0], b[0])
        iy = min(a[3], b[3]) - max(a[1], b[1])
        return ix > 1e-6 and iy > 1e-6

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not overlaps(boxes[i], boxes[j]), f"flanges {i},{j} overlap in 2D"


@pytest.mark.parametrize("name", _CASES)
def test_outline_and_bend_table(name: str) -> None:
    """Three developed rectangles (12 body edges) + one fold line per bend, all
    bends the expected 90deg 'up' folds."""
    model, expected = _load(name)
    _, result = _unfold(model)
    p = result.pattern
    body_edges = [e for e in p.outline if e.role == "body"]
    bend_edges = [e for e in p.outline if e.role == "bend"]
    assert len(body_edges) == expected.body_edge_count
    assert len(bend_edges) == expected.bend_edge_count
    assert len(p.bends) == expected.bend_count
    tol = expected.tolerance
    for bl in p.bends:
        assert bl.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bl.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bl.direction == expected.bend_direction
        assert bl.flat_end_mm - bl.flat_start_mm == pytest.approx(
            expected.bend_allowance_mm, abs=tol
        )
    assert sorted(bl.width_mm for bl in p.bends) == pytest.approx(
        sorted(expected.bend_widths_mm), abs=tol
    )


@pytest.mark.parametrize("name", _CASES)
def test_built_body_is_additive_and_well_formed(name: str) -> None:
    """The depth-2 body is a single solid of exactly-additive volume (no 3D self-
    intersection) with the expected bend topology — the geometric sanity that the
    perpendicular return is a real box corner, not an overlap."""
    model, expected = _load(name)
    built, _ = _unfold(model)
    body = built.body
    assert len(body.solids()) == expected.topology["solids"]
    assert len(body.faces()) == expected.topology["faces"]
    cyls = sum(1 for f in body.faces() if f.geom_type == GeomType.CYLINDER)
    assert cyls == expected.topology["cylinders"]
    assert float(body.volume) == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )


@pytest.mark.parametrize("name", _CASES)
def test_flat_pattern_is_deterministic_in_process(name: str) -> None:
    """Same model twice -> byte-identical FlatPattern serialization (sec 9 #4)."""
    model, _ = _load(name)
    _, a = _unfold(model)
    _, b = _unfold(model)
    assert a.pattern.to_json_bytes() == b.pattern.to_json_bytes()
    assert a.pattern.content_hash() == b.pattern.content_hash()


@pytest.mark.parametrize("name", _CASES)
def test_content_hash_matches_pinned_golden(name: str) -> None:
    """The serialized FlatPattern matches the committed determinism pin.

    A change here without an OCCT/build123d bump is a determinism regression (P0)."""
    model, expected = _load(name)
    _, result = _unfold(model)
    assert result.pattern.content_hash() == expected.content_hash


@pytest.mark.parametrize("name", _CASES)
def test_deterministic_across_interpreter_restart(name: str) -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, sec 9 #4) reproduces the
    byte-identical FlatPattern hash."""
    model, expected = _load(name)
    _, result = _unfold(model)
    proc = subprocess.run(
        [sys.executable, str(_BUILDER_PATH), str(_GOLDENS / name / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"restart probe failed:\n{proc.stderr}"
    remote_hash = proc.stdout.splitlines()[0]
    assert remote_hash == result.pattern.content_hash()
    assert remote_hash == expected.content_hash


def test_empty_bends_fail_honestly() -> None:
    """No bends -> typed error, never an empty/garbage pattern."""
    model, _ = _load("spike-bend-chain-corner")
    built = _build(model)
    with pytest.raises(BendChainError):
        unfold_bend_chain(built.body, [], model.thickness_mm, model.k_factor)


def test_unresolvable_bend_provenance_fails_honestly() -> None:
    """A bend whose provenance no longer resolves against the body degrades to a
    typed subshape_unresolved (sec 5) — never a silently wrong flat pattern. Here a
    bogus bend radius matches no cylindrical face on the body."""
    model, _ = _load("spike-bend-chain-corner")
    built = _build(model)
    good = built.bends[0]
    bogus = BendProvenance(
        cyl_signature=CylindricalFaceSignature(
            axis_origin=Vec3(x=0.0, y=0.0, z=0.0),
            axis_dir=Vec3(x=1.0, y=0.0, z=0.0),
            radius_mm=999.0,
            centroid=Vec3(x=0.0, y=0.0, z=0.0),
        ),
        base_face_signature=good.base_face_signature,
        k_factor=good.k_factor,
    )
    with pytest.raises(SubshapeUnresolvedError):
        unfold_bend_chain(built.body, [good, bogus], model.thickness_mm, model.k_factor)
