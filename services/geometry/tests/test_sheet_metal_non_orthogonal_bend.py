"""NON-ORTHOGONAL (non-90 deg) sheet-metal bend regression pin (sheet-metal.md §1/§9).

geometry-qa verified the bend allowance scales with the MEASURED fold angle
(45 / 60 / 120 deg correct, not a hardcode) but committed no non-90-degree golden.
This is that pin: an authored L-bracket folded at 120 deg, unfolded by provenance.
Its `bend_allowance_mm` is computed from the fold angle as `angle_rad * (r + K*t)`,
so a future change that silently reintroduces a 90-degree hardcode (`pi/2`) in the
unfold / BA path makes BA -- and therefore flat length + area -- wrong here and
fails. The sibling `l-bracket-edge-flange` golden pins the 90-degree case; keeping
this golden OUT of that `*-edge-flange` glob is deliberate (that suite's independent
hand-derivation hardcodes `pi/2`, correct only for the 90-degree parts).

Version-pinned to OCCT/build123d like the other flat-pattern goldens (docs §9 #4):
a kernel bump regenerates the content hash; a byte change without one is a
determinism regression (P0), never a quiet re-baseline.
"""

import math
import subprocess
import sys
from pathlib import Path

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.sheet_metal import FlatPattern, unfold_sheet_metal
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDEN_DIR = _HERE.parent / "goldens-sheet-metal" / "l-bracket-120-flange"

_K = 0.44
_THICKNESS = 2.0


class _Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    bend_allowance_90_deg_mm: float
    bend_allowance_mm: float
    flat_length_mm: float
    flat_area_mm2: float
    bend_width_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    volume_mm3: float
    volume_tolerance: float = Field(gt=0)
    topology: dict[str, int]
    content_hash: str


def _load() -> tuple[EvaluateTreeRequest, _Expected]:
    request = EvaluateTreeRequest.model_validate_json(
        (_GOLDEN_DIR / "model.json").read_text("utf-8")
    )
    expected = _Expected.model_validate_json(
        (_GOLDEN_DIR / "expected.json").read_text("utf-8")
    )
    return request, expected


def _unfold(request: EvaluateTreeRequest) -> tuple[TreeEvaluation, FlatPattern]:
    evaluation = evaluate_tree(request)
    assert all(f.status == "ok" for f in evaluation.result.features)
    assert evaluation.body is not None
    assert evaluation.sheet_metal_defaults is not None
    d = evaluation.sheet_metal_defaults
    pattern = unfold_sheet_metal(
        evaluation.body, evaluation.bend_provenance, d.thickness_mm, d.k_factor
    )
    return evaluation, pattern


def test_golden_exists() -> None:
    """Discovery breakage (a missing 120-degree golden) must fail, never skip."""
    assert (_GOLDEN_DIR / "model.json").exists()
    assert (_GOLDEN_DIR / "expected.json").exists()


def test_bend_allowance_scales_with_measured_angle() -> None:
    """§1: BA = angle_rad * (r + K*t) with the MEASURED fold angle -- NOT a pi/2
    hardcode. The independent hand-derivation recomputes BA from the golden's own
    angle (a third source, kernel- and golden-independent) and the measured bend."""
    request, expected = _load()
    _, pattern = _unfold(request)
    tol = expected.tolerance
    assert len(pattern.bends) == expected.bend_count
    bend = pattern.bends[0]

    # Measured angle is 120 deg, not 90.
    assert bend.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
    assert bend.angle_deg == pytest.approx(120.0, abs=1e-9)

    # Independent hand derivation from the MEASURED angle.
    ba_hand = math.radians(bend.angle_deg) * (expected.bend_radius_mm + _K * _THICKNESS)
    assert ba_hand == pytest.approx(expected.bend_allowance_mm, abs=tol)
    assert bend.allowance_mm == pytest.approx(ba_hand, abs=tol)
    assert bend.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
    assert bend.direction == expected.bend_direction
    assert bend.k_factor == pytest.approx(_K, abs=tol)


def test_bend_allowance_is_not_the_ninety_degree_value() -> None:
    """The regression guard, stated explicitly: a pi/2 hardcode would collapse BA to
    the 90-degree value (~6.095), ~2.03 mm smaller. The measured 120-degree BA must
    be well clear of it (33% larger), so a reintroduced hardcode cannot pass."""
    request, expected = _load()
    _, pattern = _unfold(request)
    ba90 = (math.pi / 2.0) * (expected.bend_radius_mm + _K * _THICKNESS)
    assert ba90 == pytest.approx(
        expected.bend_allowance_90_deg_mm, abs=expected.tolerance
    )
    assert abs(pattern.bends[0].allowance_mm - ba90) > 1.0


def test_flat_length_and_area_track_the_larger_allowance() -> None:
    """The larger 120-degree BA propagates into flat length + area (§9 #1/#2)."""
    request, expected = _load()
    _, pattern = _unfold(request)
    tol = expected.tolerance
    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)
    # The blank is a rectangle: area == flat_length * width (a closed cross-check).
    assert pattern.flat_area_mm2 == pytest.approx(
        pattern.flat_length_mm * pattern.bend_width_mm, abs=tol
    )


def test_fused_body_volume_and_topology() -> None:
    """The folded 120-degree body has the analytic volume + exact topology counts."""
    request, expected = _load()
    evaluation, _ = _unfold(request)
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


def test_content_hash_matches_pinned_golden() -> None:
    """The serialized provenance FlatPattern matches the committed determinism pin."""
    request, expected = _load()
    _, pattern = _unfold(request)
    assert pattern.content_hash() == expected.content_hash


_RESTART_PROBE = """\
import sys
from pathlib import Path

from geometry.features.evaluate import evaluate_tree
from geometry.sheet_metal import unfold_sheet_metal
from py_kit.schemas.features import EvaluateTreeRequest

request = EvaluateTreeRequest.model_validate_json(Path(sys.argv[1]).read_text("utf-8"))
ev = evaluate_tree(request)
d = ev.sheet_metal_defaults
fp = unfold_sheet_metal(ev.body, ev.bend_provenance, d.thickness_mm, d.k_factor)
print(fp.content_hash())
"""


def test_deterministic_across_interpreter_restart() -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical FlatPattern hash (§9)."""
    _, expected = _load()
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_GOLDEN_DIR / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.splitlines()[0] == expected.content_hash
