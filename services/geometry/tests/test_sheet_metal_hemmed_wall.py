"""Hemmed-wall tray gates — hem on a FLANGE top edge flat-patterns (BACKLOG
2026-07-20, TB-1 founder dogfooding; docs/design/sheet-metal.md §4.3/§4.4/§9).

The TB-1 tray (base + 4 walls + closed hems on both long-wall rims + 4 corner
reliefs) evaluated to one valid shell but could NOT flat-pattern: the hem bend's
inner cylinder is tangent to FOUR coplanar planar faces (its real wall + return
flanges, plus the two perpendicular walls' end faces which lie exactly in the
return's tangent plane), so flank resolution — which counted every tangent plane —
raised the typed ``BendFlankingFacesError`` ("flanked by 4 planar faces"). Two
fixes, both gated here against the ``hemmed-wall-tray-unfold`` golden:

* **Topological flank resolution** (``resolve.shares_edge_with``): a bend's
  flanges must SHARE AN EDGE with the bend cylinder (the tangent seam), so a
  merely-coplanar bystander can never masquerade as a flange. Without this fix
  every flat-pattern of this golden fails typed at resolve.
* **Returns-by-provenance in the relieved unfold** (``_partition_arm_returns``):
  with reliefs present, an axis-parallel return (hem) folded off a depth-1 arm —
  identified by its recorded ``base_face_signature`` naming that arm's moving
  flange (§5 fold provenance) — develops as a pure arm EXTENSION
  ``[BA strip][return leg]`` beyond the wall rim; every other depth-≥2 body with
  reliefs stays a typed reject (perpendicular-axis box corners still need miter /
  closed-corner geometry, §4.4.4).

Gates follow the four-corner-pan pattern: hand-derived analytics (never recorded
harness output), the FOLD-BACK invariant measured on the REAL evaluated bodies
(inner bend cylindrical-face widths == flat fold widths; removed 3D volume ==
removed flat area x thickness + the neutral-vs-mean-radius bend term), the
unrelieved TREE-path variant, the minimal plate + one-wall + hem part, the
user-facing drawing view, and byte-determinism (in-process + interpreter restart).
"""

import copy
import math
import subprocess
import sys
from pathlib import Path

import pytest
from geometry.drawings.flat_pattern import flat_pattern_view_result
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.properties import measure_shape
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import FlatPattern, unfold_sheet_metal
from geometry.sheet_metal.resolve import cylindrical_face_widths
from py_kit.schemas.drawings import ViewScale
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDEN = _HERE.parent / "goldens-sheet-metal" / "hemmed-wall-tray-unfold"
_P = "5e800000-0000-0000-0000-0000000000"


class _Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    thickness_mm: float
    k_factor: float
    wall_bend_radius_mm: float
    hem_bend_radius_mm: float
    hem_return_mm: float
    wall_allowance_mm: float
    hem_allowance_mm: float
    relief_size_mm: float
    flat_length_mm: float
    bend_width_mm: float
    unrelieved_flat_area_mm2: float
    removed_area_mm2: float
    flat_area_mm2: float
    minimal_flat_length_mm: float
    minimal_bend_width_mm: float
    bend_count: int
    hem_count: int
    notch_count: int
    wall_bend_widths_mm: list[float]
    hem_bend_widths_mm: list[float]
    reference_wall_bend_widths_mm: list[float]
    hem_fold_inset_mm: float
    body_edge_count: int
    bend_edge_count: int
    bend_direction: str
    reference_volume_mm3: float
    relieved_volume_mm3: float
    removed_volume_mm3: float
    volume_tolerance: float = Field(gt=0)
    reference_topology: dict[str, int]
    relieved_topology: dict[str, int]
    content_hash: str


def _load() -> tuple[EvaluateTreeRequest, _Expected]:
    request = EvaluateTreeRequest.model_validate_json(
        (_GOLDEN / "model.json").read_text("utf-8")
    )
    expected = _Expected.model_validate_json(
        (_GOLDEN / "expected.json").read_text("utf-8")
    )
    return request, expected


def _evaluate(request: EvaluateTreeRequest) -> TreeEvaluation:
    evaluation = evaluate_tree(request)
    statuses = [
        (f.status, f.error.code if f.error else None)
        for f in evaluation.result.features
    ]
    assert all(s == "ok" for s, _ in statuses), statuses
    assert evaluation.body is not None
    return evaluation


def _body(evaluation: TreeEvaluation) -> BodyShape:
    assert evaluation.body is not None
    return evaluation.body


def _pipeline_pattern(evaluation: TreeEvaluation) -> FlatPattern:
    d = evaluation.sheet_metal_defaults
    assert d is not None
    unfold_body = evaluation.unfold_body or evaluation.body
    assert unfold_body is not None
    return unfold_sheet_metal(
        unfold_body,
        evaluation.bend_provenance,
        d.thickness_mm,
        d.k_factor,
        reliefs=evaluation.corner_reliefs or None,
    )


def _variant_without(
    request: EvaluateTreeRequest, drop: set[str]
) -> EvaluateTreeRequest:
    """The golden tree with the features whose id-suffix is in *drop* removed."""
    tree = copy.deepcopy(request.model_dump(mode="json"))
    tree["features"] = [f for f in tree["features"] if f["id"][-2:] not in drop]
    return EvaluateTreeRequest.model_validate(tree)


def test_golden_present() -> None:
    assert (_GOLDEN / "model.json").exists()
    assert (_GOLDEN / "expected.json").exists()


def test_tray_evaluates_to_one_valid_relieved_shell() -> None:
    """All 12 features ok (4 walls + 2 hems + 4 reliefs COEXIST); the live relieved
    body and the clean un-notched reference are each ONE valid shell with the pinned
    topology and analytic volume."""
    from OCP.BRepCheck import BRepCheck_Analyzer  # type: ignore[import-untyped]

    request, expected = _load()
    evaluation = _evaluate(request)
    assert len(evaluation.result.features) == 12
    assert len(evaluation.bend_provenance) == expected.bend_count
    assert len(evaluation.corner_reliefs) == 4

    live = measure_shape(_body(evaluation))
    assert live.topology.shells == 1
    assert live.topology.model_dump() == expected.relieved_topology
    assert BRepCheck_Analyzer(_body(evaluation).wrapped).IsValid()  # type: ignore[no-untyped-call]

    assert evaluation.unfold_body is not None
    reference = measure_shape(evaluation.unfold_body)
    assert reference.topology.model_dump() == expected.reference_topology
    vtol = expected.volume_tolerance
    assert reference.volume == pytest.approx(expected.reference_volume_mm3, abs=vtol)
    assert live.volume == pytest.approx(expected.relieved_volume_mm3, abs=vtol)


def test_flat_pattern_matches_hand_derivation() -> None:
    """The pipeline flat pattern matches the HAND-DERIVED analytics (§9 #1/#2):
    extents, relieved area, shortened wall folds, full-width hem folds, and the hem
    developing as BA = pi*(r + K*t) + return length — the same closed form the
    closed-hem-plate golden proves on a base-plate edge."""
    request, expected = _load()
    pattern = _pipeline_pattern(_evaluate(request))
    tol = expected.tolerance

    # Third-source recomputation, independent of golden AND kernel.
    t, k = expected.thickness_mm, expected.k_factor
    ba_wall = (math.pi / 2.0) * (expected.wall_bend_radius_mm + k * t)
    ba_hem = math.pi * (expected.hem_bend_radius_mm + k * t)
    assert ba_wall == pytest.approx(expected.wall_allowance_mm, abs=tol)
    assert ba_hem == pytest.approx(expected.hem_allowance_mm, abs=tol)
    assert 356.0 + 2 * ba_wall + 2 * ba_hem == pytest.approx(
        expected.flat_length_mm, abs=tol
    )

    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert expected.unrelieved_flat_area_mm2 - expected.removed_area_mm2 == (
        pytest.approx(expected.flat_area_mm2, abs=tol)
    )

    assert len(pattern.bends) == expected.bend_count
    hems = [b for b in pattern.bends if abs(b.angle_deg - 180.0) <= tol]
    walls = [b for b in pattern.bends if abs(b.angle_deg - 90.0) <= tol]
    assert len(hems) == expected.hem_count
    assert len(walls) == expected.bend_count - expected.hem_count
    for b in hems:
        assert b.radius_mm == pytest.approx(expected.hem_bend_radius_mm, abs=tol)
        assert b.allowance_mm == pytest.approx(ba_hem, abs=tol)
        assert b.k_factor == pytest.approx(k, abs=tol)
        assert b.direction == expected.bend_direction
    assert sorted(b.width_mm for b in hems) == pytest.approx(
        expected.hem_bend_widths_mm, abs=tol
    )
    assert sorted(b.width_mm for b in walls) == pytest.approx(
        expected.wall_bend_widths_mm, abs=tol
    )
    for b in walls:
        assert b.allowance_mm == pytest.approx(ba_wall, abs=tol)
        assert b.direction == expected.bend_direction


def test_hem_fold_lines_sit_mid_ba_beyond_the_wall_rim() -> None:
    """The two hem fold lines are the full-width (300 mm) 'bend' outline edges and
    sit return + BA/2 in from their blank edge — the geometric witness that each hem
    developed as [return leg][BA strip] BEYOND its wall's rim, not as a narrowed or
    mislaid arm."""
    request, expected = _load()
    pattern = _pipeline_pattern(_evaluate(request))
    tol = expected.tolerance
    folds = [e for e in pattern.outline if e.role == "bend"]
    hem_folds = [
        e
        for e in folds
        if math.dist((e.x1, e.y1), (e.x2, e.y2)) == pytest.approx(300.0, abs=tol)
    ]
    assert len(hem_folds) == expected.hem_count
    positions = sorted({e.x1 for e in hem_folds} | {e.x2 for e in hem_folds})
    assert len(positions) == 2
    inset = expected.hem_fold_inset_mm
    assert positions[0] == pytest.approx(inset, abs=tol)
    assert positions[1] == pytest.approx(expected.flat_length_mm - inset, abs=tol)


def test_fold_back_consistency_3d_matches_flat() -> None:
    """THE fold-back gate (§4.4.4), measured on the REAL evaluated bodies:

    (1) the LIVE relieved body's inner bend cylindrical-face widths equal the flat
        fold widths — wall bends (r=2) shortened to the notched spans, hem bends
        (r=1) full width — and the CLEAN reference body's r=2 widths are the
        unrelieved spans;
    (2) removed 3D volume == removed flat area x thickness + the per-notch
        neutral-vs-mean-radius bend term over all EIGHT wall-root notches."""
    request, expected = _load()
    evaluation = _evaluate(request)
    defaults = evaluation.sheet_metal_defaults
    assert defaults is not None
    pattern = _pipeline_pattern(evaluation)
    vtol = expected.volume_tolerance

    hems = [b for b in pattern.bends if abs(b.angle_deg - 180.0) <= expected.tolerance]
    walls = [b for b in pattern.bends if abs(b.angle_deg - 90.0) <= expected.tolerance]
    assert sorted(
        cylindrical_face_widths(_body(evaluation), expected.wall_bend_radius_mm)
    ) == pytest.approx(sorted(b.width_mm for b in walls), abs=vtol)
    assert sorted(
        cylindrical_face_widths(_body(evaluation), expected.hem_bend_radius_mm)
    ) == pytest.approx(sorted(b.width_mm for b in hems), abs=vtol)
    assert evaluation.unfold_body is not None
    assert sorted(
        cylindrical_face_widths(evaluation.unfold_body, expected.wall_bend_radius_mm)
    ) == pytest.approx(expected.reference_wall_bend_widths_mm, abs=vtol)

    reference = measure_shape(evaluation.unfold_body)
    live = measure_shape(_body(evaluation))
    removed_volume = reference.volume - live.volume
    removed_area = expected.unrelieved_flat_area_mm2 - pattern.flat_area_mm2
    t, k = defaults.thickness_mm, defaults.k_factor
    bias = expected.notch_count * (
        expected.relief_size_mm * math.radians(90.0) * t * t * (0.5 - k)
    )
    assert removed_volume == pytest.approx(removed_area * t + bias, abs=vtol)
    assert removed_volume == pytest.approx(expected.removed_volume_mm3, abs=vtol)


def test_flat_pattern_view_develops_the_hemmed_tray() -> None:
    """The user-facing drawing flat_pattern view — the surface the founder hit the
    'flanked by 4 planar faces' typed reject on — now develops the tray: outline +
    a six-row bend table, no error."""
    request, expected = _load()
    view = flat_pattern_view_result(
        _evaluate(request), ViewScale(numerator=1, denominator=1)
    )
    assert view.error is None
    body = [e for e in view.edges if e.edge_role == "body"]
    bend = [e for e in view.edges if e.edge_role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    assert len(view.bend_table) == expected.bend_count


def test_unrelieved_tray_unfolds_through_the_bend_tree() -> None:
    """The same tray WITHOUT reliefs routes to the depth-≥2 bend-TREE path (the hems
    make it depth 2) and develops the unrelieved blank: same two extents (the tree
    frame swaps the axes), unrelieved area, full-width folds. Regression for the
    flank fix alone — before it, THIS variant failed typed at resolve too."""
    request, expected = _load()
    variant = _variant_without(request, {"41", "42", "43", "44"})
    evaluation = _evaluate(variant)
    assert not evaluation.corner_reliefs
    pattern = _pipeline_pattern(evaluation)
    tol = expected.tolerance
    assert pattern.flat_length_mm == pytest.approx(expected.bend_width_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(
        expected.unrelieved_flat_area_mm2, abs=tol
    )
    assert len(pattern.bends) == expected.bend_count
    hems = [b for b in pattern.bends if abs(b.angle_deg - 180.0) <= tol]
    assert sorted(b.width_mm for b in hems) == pytest.approx(
        expected.hem_bend_widths_mm, abs=tol
    )
    for b in hems:
        assert b.allowance_mm == pytest.approx(expected.hem_allowance_mm, abs=tol)


def test_minimal_hemmed_wall_unfolds() -> None:
    """The MINIMAL hemmed-wall part — plate + ONE wall + a closed hem on its top
    rim (the single most common real hem placement) — develops the analytic strip:
    base 180 + BA_wall + wall 80 + BA_hem + return 8, full 300 mm wide."""
    request, expected = _load()
    variant = _variant_without(
        request, {"d8", "e8", "f8", "28", "41", "42", "43", "44"}
    )
    evaluation = _evaluate(variant)
    pattern = _pipeline_pattern(evaluation)
    tol = expected.tolerance
    assert pattern.flat_length_mm == pytest.approx(
        expected.minimal_flat_length_mm, abs=tol
    )
    assert pattern.bend_width_mm == pytest.approx(
        expected.minimal_bend_width_mm, abs=tol
    )
    analytic = 180.0 + expected.wall_allowance_mm + 80.0 + expected.hem_allowance_mm
    assert analytic + 8.0 == pytest.approx(expected.minimal_bend_width_mm, abs=tol)
    assert len(pattern.bends) == 2
    hem = next(b for b in pattern.bends if abs(b.angle_deg - 180.0) <= tol)
    assert hem.allowance_mm == pytest.approx(expected.hem_allowance_mm, abs=tol)
    assert hem.width_mm == pytest.approx(300.0, abs=tol)


def test_flat_pattern_matches_pinned_hash_and_is_deterministic() -> None:
    """Byte-determinism (§9 #4): the pipeline pattern matches the committed
    determinism pin and reproduces byte-identically in-process."""
    request, expected = _load()
    a = _pipeline_pattern(_evaluate(request))
    b = _pipeline_pattern(_evaluate(request))
    assert a.to_json_bytes() == b.to_json_bytes()
    assert a.content_hash() == expected.content_hash


_RESTART_PROBE = """\
import sys
from pathlib import Path

from geometry.features.evaluate import evaluate_tree
from geometry.sheet_metal import unfold_sheet_metal
from py_kit.schemas.features import EvaluateTreeRequest

request = EvaluateTreeRequest.model_validate_json(Path(sys.argv[1]).read_text("utf-8"))
ev = evaluate_tree(request)
d = ev.sheet_metal_defaults
fp = unfold_sheet_metal(
    ev.unfold_body or ev.body,
    ev.bend_provenance,
    d.thickness_mm,
    d.k_factor,
    reliefs=ev.corner_reliefs or None,
)
print(fp.content_hash())
"""


def test_unfold_is_deterministic_across_interpreter_restart() -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical FlatPattern hash."""
    _, expected = _load()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_GOLDEN / "model.json")],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.splitlines()[0] == expected.content_hash
