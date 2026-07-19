"""Sheet-metal L-bracket unfold — SPIKE 0 golden gate (docs/design/sheet-metal.md).

The pillar-gating tractability proof: a base flange + ONE edge flange folded 90
degrees unfolds to a dimensionally-correct flat pattern. Proves, against
HAND-DERIVED analytic values (independently recomputed here, not read from
kernel output):

* **Flat length** (§9 #1) — ``flat_length = leg1_dev + BA + leg2_dev`` with the
  bend allowance ``BA = angle_rad * (bend_radius + K*thickness)`` (§1), each leg
  measured to the bend **tangent line** (NOT the sharp corner).
* **Area conservation** (§9 #2) — ``flat_area = SUM(flange developed areas) +
  (BA * bend_width)``.
* **Byte-determinism** (§9 #4) — the ``FlatPattern`` serializes byte-identically
  in-process and across a fresh interpreter restart.
* **Honest failure** — a body that is not a folded sheet raises a typed error,
  never a wrong flat pattern.

Concrete dims (from ``goldens/sheet-metal-l-bracket-unfold/model.json``):
leg1_dev = 50 mm, leg2_dev = 30 mm, thickness t = 2 mm, inner bend radius
r = 3 mm, 90 deg fold, bend width w = 20 mm, K = 0.44 (v1 default).

Hand derivation (recomputed independently in :func:`_hand_derived`):
    BA          = (pi/2) * (3 + 0.44*2) = (pi/2) * 3.88 = 6.094689747964199 mm
    flat_length = 50 + BA + 30           = 86.09468974796420 mm
    flat_area   = 50*20 + 30*20 + BA*20  = 1721.893794959284 mm^2

``leg_dev`` is measured to the TANGENT LINE: it is the length of each flange's
own flat planar face, running from the flange free edge to where the flat meets
the bend arc. The setback legs (50 + 5, 30 + 5, setback = (r+t)*tan(45) = 5 mm)
are deliberately NOT used — BA replaces those two segments.

The L-bracket body is built directly by a test-local helper
(``tests/_l_bracket_builder.py``, mirroring the drawings goldens' body helpers):
the base-flange/edge-flange FEATURE schema is the next slice, so this spike
proves the unfold math + OCCT face resolution before the schema is committed.
"""

import importlib.util
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import (
    NoBendFoundError,
    UnfoldScopeError,
    bend_allowance,
    resolve_bends,
    unfold_l_bracket,
)
from pydantic import BaseModel, ConfigDict

_HERE = Path(__file__).resolve().parent
_BUILDER_PATH = _HERE / "_l_bracket_builder.py"
_GOLDEN_DIR = _HERE.parent / "goldens" / "sheet-metal-l-bracket-unfold"
_MODEL_PATH = _GOLDEN_DIR / "model.json"
_EXPECTED_PATH = _GOLDEN_DIR / "expected.json"


class LBracketModel(BaseModel):
    """The golden's ``model.json`` — L-bracket construction parameters."""

    model_config = ConfigDict(extra="forbid")

    description: str
    leg1_mm: float
    leg2_mm: float
    thickness_mm: float
    bend_radius_mm: float
    bend_width_mm: float
    k_factor: float


class LBracketExpected(BaseModel):
    """The golden's ``expected.json`` — analytic expectations + determinism pin."""

    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float
    tolerance_rationale: str
    bend_allowance_mm: float
    flat_length_mm: float
    flat_area_mm2: float
    bend_strip_length_mm: float
    bend_width_mm: float
    bend_angle_deg: float
    content_hash: str


def _load_builder() -> ModuleType:
    """Load the test-local body builder by file path (importlib import-mode: test
    modules cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_l_bracket_builder", _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BuildFn = Callable[[float, float, float, float, float], BodyShape]

MODEL = LBracketModel.model_validate_json(_MODEL_PATH.read_text(encoding="utf-8"))
EXPECTED = LBracketExpected.model_validate_json(
    _EXPECTED_PATH.read_text(encoding="utf-8")
)
build_l_bracket = cast(BuildFn, _load_builder().build_l_bracket)


def _bracket() -> BodyShape:
    return build_l_bracket(
        MODEL.leg1_mm,
        MODEL.leg2_mm,
        MODEL.thickness_mm,
        MODEL.bend_radius_mm,
        MODEL.bend_width_mm,
    )


def _hand_derived() -> tuple[float, float, float]:
    """Independently recompute (BA, flat_length, flat_area) from first principles.

    Recomputed here — NOT read from the golden or the kernel — so the golden's
    stored expectations and the kernel output are both checked against a third,
    hand-written source (geometry-gates skill: a golden recorded from buggy
    output enshrines the bug)."""
    angle = math.pi / 2.0
    ba = angle * (MODEL.bend_radius_mm + MODEL.k_factor * MODEL.thickness_mm)
    flat_length = MODEL.leg1_mm + ba + MODEL.leg2_mm
    flat_area = (
        MODEL.leg1_mm * MODEL.bend_width_mm
        + MODEL.leg2_mm * MODEL.bend_width_mm
        + ba * MODEL.bend_width_mm
    )
    return ba, flat_length, flat_area


def test_golden_expectations_match_hand_derivation() -> None:
    """The committed golden values equal an independent hand derivation."""
    ba, flat_length, flat_area = _hand_derived()
    tol = EXPECTED.tolerance
    assert ba == pytest.approx(EXPECTED.bend_allowance_mm, abs=tol)
    assert ba == pytest.approx(EXPECTED.bend_strip_length_mm, abs=tol)
    assert flat_length == pytest.approx(EXPECTED.flat_length_mm, abs=tol)
    assert flat_area == pytest.approx(EXPECTED.flat_area_mm2, abs=tol)


def test_bend_allowance_closed_form() -> None:
    """The §1 closed form, checked against the pinned worked example."""
    ba = bend_allowance(math.pi / 2.0, 3.0, 0.44, 2.0)
    # BA = (pi/2)(3 + 0.44*2) = (pi/2)(3.88)
    assert ba == pytest.approx(6.094689747964199, abs=1e-12)


def test_flat_length_invariant() -> None:
    """§9 #1: flat_length = leg1_dev + BA + leg2_dev, legs to the tangent line."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    _, flat_length, _ = _hand_derived()
    tol = EXPECTED.tolerance
    assert pattern.flat_length_mm == pytest.approx(flat_length, abs=tol)
    assert pattern.flat_length_mm == pytest.approx(EXPECTED.flat_length_mm, abs=tol)


def test_area_conservation_invariant() -> None:
    """§9 #2: flat_area = SUM(flange developed areas) + (BA * bend_width).

    Also asserts the developed area is DISTINCT from the folded body's projected
    bend cross-section (a quarter annulus) — that difference IS the K-factor
    method, so a unit-check that treated them as equal would be wrong."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    _, _, flat_area = _hand_derived()
    tol = EXPECTED.tolerance
    assert pattern.flat_area_mm2 == pytest.approx(flat_area, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(EXPECTED.flat_area_mm2, abs=tol)

    # Sum-of-parts, reconstructed from the pattern's own reported pieces.
    bend = pattern.bends[0]
    strip_area = bend.allowance_mm * pattern.bend_width_mm
    w = pattern.bend_width_mm
    flange_area = MODEL.leg1_mm * w + MODEL.leg2_mm * w
    assert pattern.flat_area_mm2 == pytest.approx(flange_area + strip_area, abs=tol)

    # The naive projected bend cross-section (quarter annulus) is NOT the strip.
    r, t = MODEL.bend_radius_mm, MODEL.thickness_mm
    annulus_area = (math.pi / 4.0) * ((r + t) ** 2 - r**2) * pattern.bend_width_mm
    assert not math.isclose(strip_area, annulus_area, abs_tol=1.0)


def test_tangent_line_convention() -> None:
    """Legs are developed to the TANGENT LINE (50/30), not the sharp corner.

    The sharp-corner legs would be leg + setback with setback = (r+t)*tan(45) =
    5 mm; the bend strip occupies exactly [leg1_dev, leg1_dev+BA] in the flat."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    bend = pattern.bends[0]
    ba, _, _ = _hand_derived()
    tol = EXPECTED.tolerance
    # Base flange (longer leg) develops first: strip starts at leg1_dev = 50.
    assert bend.flat_start_mm == pytest.approx(MODEL.leg1_mm, abs=tol)
    assert bend.flat_end_mm == pytest.approx(MODEL.leg1_mm + ba, abs=tol)
    assert bend.flat_end_mm - bend.flat_start_mm == pytest.approx(ba, abs=tol)
    setback = (MODEL.bend_radius_mm + MODEL.thickness_mm) * math.tan(math.pi / 4.0)
    assert setback == pytest.approx(5.0, abs=tol)
    # A sharp-corner unfold would place the seam at leg1 + setback, not leg1.
    assert bend.flat_start_mm != pytest.approx(MODEL.leg1_mm + setback, abs=1e-3)


def test_bend_metadata_and_geometry() -> None:
    """The bend resolves to its true geometry: 90 deg, r = 3, width = 20, and the
    axis/radius/centroid payload the shipped CylindricalFaceSignature (§5) needs."""
    body = _bracket()
    pattern = unfold_l_bracket(body, MODEL.thickness_mm, MODEL.k_factor)
    tol = EXPECTED.tolerance
    bend = pattern.bends[0]
    assert bend.angle_deg == pytest.approx(EXPECTED.bend_angle_deg, abs=tol)
    assert bend.radius_mm == pytest.approx(MODEL.bend_radius_mm, abs=tol)
    assert bend.width_mm == pytest.approx(MODEL.bend_width_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(EXPECTED.bend_width_mm, abs=tol)

    # §5 signature payload is available at resolution time (axis + radius + centroid).
    resolved = resolve_bends(body, MODEL.thickness_mm)
    assert len(resolved) == 1
    rb = resolved[0]
    assert rb.radius_mm == pytest.approx(MODEL.bend_radius_mm, abs=tol)
    # Axis is parallel to Y (the bend-width direction) through the origin.
    assert abs(abs(rb.axis_dir[1]) - 1.0) < tol
    assert math.isfinite(rb.centroid[0])
    assert rb.angle_rad == pytest.approx(math.pi / 2.0, abs=tol)


def test_outline_is_the_expected_rectangle() -> None:
    """The L-bracket blank is a flat_length x width rectangle + one bend line."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    body_edges = [e for e in pattern.outline if e.role == "body"]
    bend_edges = [e for e in pattern.outline if e.role == "bend"]
    assert len(body_edges) == 4  # rectangle
    assert len(bend_edges) == 1  # one fold line
    tol = EXPECTED.tolerance
    xs = [c for e in body_edges for c in (e.x1, e.x2)]
    ys = [c for e in body_edges for c in (e.y1, e.y2)]
    assert max(xs) - min(xs) == pytest.approx(EXPECTED.flat_length_mm, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(EXPECTED.bend_width_mm, abs=tol)


def test_flat_pattern_is_deterministic_in_process() -> None:
    """Same body twice → byte-identical FlatPattern serialization (§9 #4)."""
    a = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    b = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    assert a.to_json_bytes() == b.to_json_bytes()
    assert a.content_hash() == b.content_hash()


def test_content_hash_matches_pinned_golden() -> None:
    """The serialized FlatPattern matches the committed determinism pin.

    A change here without an OCCT/build123d bump is a determinism regression
    (P0), not a value to update (see expected.json derivation)."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    assert pattern.content_hash() == EXPECTED.content_hash


def test_flat_pattern_is_deterministic_across_interpreter_restart() -> None:
    """Fresh-interpreter rebuild (worker-restart emulation, §9 #4) reproduces
    the byte-identical FlatPattern hash."""
    pattern = unfold_l_bracket(_bracket(), MODEL.thickness_mm, MODEL.k_factor)
    result = subprocess.run(
        [sys.executable, str(_BUILDER_PATH), str(_MODEL_PATH)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    remote_hash = result.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == EXPECTED.content_hash


def test_non_sheet_body_fails_honestly() -> None:
    """A body with no bend region raises a typed error, never a wrong pattern
    (§9 #5's honest-failure posture)."""
    from build123d import Box

    with pytest.raises(NoBendFoundError):
        unfold_l_bracket(Box(20.0, 20.0, 2.0), MODEL.thickness_mm, MODEL.k_factor)


def test_wrong_gauge_thickness_fails_honestly() -> None:
    """Unfolding at a thickness that doesn't match the body's gauge finds no
    concentric radius pair → typed error, not a silently wrong allowance."""
    with pytest.raises(NoBendFoundError):
        unfold_l_bracket(_bracket(), MODEL.thickness_mm + 1.0, MODEL.k_factor)


def test_multi_bend_body_is_out_of_spike_scope() -> None:
    """Two bends (e.g. a depth-1 N=2 star) is the feature slice, not SPIKE 0 —
    the unfold refuses it with a scoped typed error, not a guess.

    Two independent L-brackets, the second translated far off so its bend axis
    is not concentric with the first's: :func:`resolve_bends` finds two distinct
    bends → :class:`UnfoldScopeError`."""
    from build123d import Compound

    first = _bracket()
    second = build_l_bracket(15.0, 12.0, 2.0, 3.0, 20.0).translate((200.0, 0.0, 200.0))
    combined = Compound(children=[first, second])
    with pytest.raises(UnfoldScopeError):
        unfold_l_bracket(combined, MODEL.thickness_mm, MODEL.k_factor)
