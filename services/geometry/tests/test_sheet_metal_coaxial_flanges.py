"""WF-1 code-review — two COAXIAL equal-radius flanges on collinear edge segments
develop correctly (never a false fold-back reject).

The natural extension of PB-1 (docs/design/sheet-metal.md §4.5.3 / §5): a notch-split
base edge with a full-width flange on EACH surviving segment. The two bends share the
SAME axis line AND radius, differing only in along-axis extent/centroid. Two coupled
coaxial-ambiguity fixes are exercised here:

1. CONSTRUCTION — the second collinear flange's bend cylinder is coaxial + equal-radius
   with the first's, so ``find_cylindrical_face`` (axis line + radius) matched BOTH;
   before the fix the second edge flange failed ``edge_flange_failed`` at provenance
   resolution. It now disambiguates by the flange's along-axis SPAN.
2. FOLD-BACK — ``_check_live_fold_back`` measured live widths PER PROVENANCE with the
   centroid-ignoring ``coaxial_cylindrical_face_widths``, which returns EVERY coaxial
   face, so two folds produced ``[wA, wB, wA, wB]`` (count 4) vs developed ``[wA, wB]``
   (count 2) -> a bogus ``UnfoldFoldBackError`` on a valid body. It now measures each
   DISTINCT face once (``resolve.live_bend_face_widths``, deduped by TopoDS identity).

Values are hand-derived in the golden's ``derivation``; the test asserts the
FlatPattern against those independent closed-form numbers (never echoed output), plus
the 3D volume / topology, a single-closed-loop shoelace witness, and byte-determinism
(in-process + fresh interpreter). Tolerances are the golden's documented per-model
values.
"""

import math
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from geometry.drawings import flat_pattern_view_result
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.sheet_metal import FlatPattern, unfold_sheet_metal
from geometry.sheet_metal.resolve import (
    coaxial_cylindrical_face_widths,
    live_bend_face_widths,
)
from py_kit.schemas.drawings import ViewScale
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDEN_DIR = _HERE.parent / "goldens-sheet-metal" / "coaxial-two-segment-flange-unfold"
_UNIT_SCALE = ViewScale(numerator=1, denominator=1)
_Pt = tuple[float, float]


class _Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    bend_allowance_mm: float
    flat_area_mm2: float
    flat_length_mm: float
    bend_width_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    bend_widths_mm: list[float]
    live_bend_face_widths_deduped: list[float]
    live_bend_face_widths_naive_double_counted: list[float]
    body_edge_count: int
    bend_edge_count: int
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
    statuses = [f.status for f in evaluation.result.features]
    assert all(s == "ok" for s in statuses), (
        statuses,
        [f.error for f in evaluation.result.features if f.status != "ok"],
    )
    assert evaluation.body is not None
    assert evaluation.sheet_metal_defaults is not None
    defaults = evaluation.sheet_metal_defaults
    pattern = unfold_sheet_metal(
        evaluation.unfold_body or evaluation.body,
        evaluation.bend_provenance,
        defaults.thickness_mm,
        defaults.k_factor,
        live_body=evaluation.body,
    )
    return evaluation, pattern


def _chain_loop(pattern: FlatPattern) -> list[_Pt] | None:
    segs: list[tuple[_Pt, _Pt]] = [
        ((e.x1, e.y1), (e.x2, e.y2)) for e in pattern.outline if e.role == "body"
    ]
    if not segs:
        return None
    used = [False] * len(segs)
    used[0] = True
    loop: list[_Pt] = [segs[0][0], segs[0][1]]
    for _ in range(len(segs) - 1):
        tail = loop[-1]
        nxt: _Pt | None = None
        for i, (a, b) in enumerate(segs):
            if used[i]:
                continue
            if math.dist(tail, a) <= 1e-6:
                nxt, used[i] = b, True
                break
            if math.dist(tail, b) <= 1e-6:
                nxt, used[i] = a, True
                break
        if nxt is None:
            return None
        loop.append(nxt)
    if not all(used) or math.dist(loop[-1], loop[0]) > 1e-6:
        return None
    return loop


def _enclosed_area(loop: list[_Pt]) -> float:
    pts = loop[:-1]
    n = len(pts)
    acc = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


# --------------------------------------------------------------------------- #
# The core anti-regression: a valid coaxial multi-flange body DEVELOPS         #
# --------------------------------------------------------------------------- #


def test_two_collinear_flanges_build_and_develop() -> None:
    """Both flanges evaluate ok (construction disambiguation) and the body develops
    with NO fold-back false reject (the runtime dedup) — the whole bug, end to end."""
    request, expected = _load()
    evaluation, pattern = _unfold(request)  # raises if the fold-back check false-fires
    assert len(pattern.bends) == expected.bend_count == 2
    result = flat_pattern_view_result(evaluation, _UNIT_SCALE)
    assert result.error is None, result.error
    assert len(result.bend_table) == 2


def test_fold_back_dedup_measures_each_bend_face_once() -> None:
    """The heart of the fix: ``live_bend_face_widths`` returns TWO widths (one per
    distinct coaxial bend face), while the buggy per-signature scan returns FOUR
    (each signature matches BOTH coaxial faces). Deduping is by IDENTITY, so the two
    genuinely-equal 80 mm widths still count as two, never collapse to one."""
    request, expected = _load()
    evaluation, pattern = _unfold(request)
    assert evaluation.body is not None
    sigs = [p.cyl_signature for p in evaluation.bend_provenance]

    # The buggy pattern (what `_check_live_fold_back` used to do): sum per-signature.
    naive: list[float] = []
    for sig in sigs:
        naive.extend(coaxial_cylindrical_face_widths(evaluation.body, sig))
    assert sorted(naive) == pytest.approx(
        expected.live_bend_face_widths_naive_double_counted, abs=1e-6
    )
    assert len(naive) == 4  # the N^2 double-count that false-rejected

    # The fix: each distinct face measured once.
    deduped = sorted(w for _r, w in live_bend_face_widths(evaluation.body, sigs))
    assert deduped == pytest.approx(expected.live_bend_face_widths_deduped, abs=1e-6)
    assert len(deduped) == 2
    # And the deduped live widths equal the developed fold widths (fold-back holds).
    assert deduped == pytest.approx(sorted(b.width_mm for b in pattern.bends), abs=1e-6)


# --------------------------------------------------------------------------- #
# Analytic golden gate (independent closed-form values, not echoed output)     #
# --------------------------------------------------------------------------- #


def test_unfold_matches_hand_derivation() -> None:
    request, expected = _load()
    _, pattern = _unfold(request)
    tol = expected.tolerance

    ba = (math.pi / 2.0) * (expected.bend_radius_mm + 0.44 * 1.5)
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)
    assert len(pattern.bends) == expected.bend_count
    assert sorted(b.width_mm for b in pattern.bends) == pytest.approx(
        expected.bend_widths_mm, abs=tol
    )
    for bend in pattern.bends:
        assert bend.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bend.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bend.allowance_mm == pytest.approx(ba, abs=tol)
        assert bend.direction == expected.bend_direction
        assert abs(bend.flat_end_mm - bend.flat_start_mm) == pytest.approx(ba, abs=tol)


def test_outline_is_single_closed_loop() -> None:
    request, expected = _load()
    _, pattern = _unfold(request)
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    loop = _chain_loop(pattern)
    assert loop is not None, "the two-segment blank is not one closed loop"
    # Shoelace of the closed loop == the reported area: independent geometric witness
    # that the base-with-notch + two flange legs tile ONE blank without overlap/gap.
    assert _enclosed_area(loop) == pytest.approx(pattern.flat_area_mm2, abs=1e-6)
    for e in bend:
        assert math.dist((e.x1, e.y1), (e.x2, e.y2)) == pytest.approx(
            expected.bend_widths_mm[0], abs=expected.tolerance
        )


def test_body_volume_and_topology() -> None:
    request, expected = _load()
    evaluation, _ = _unfold(request)
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


def test_unfold_content_hash_matches_pinned_golden() -> None:
    request, expected = _load()
    _, pattern = _unfold(request)
    assert pattern.content_hash() == expected.content_hash


def test_unfold_is_deterministic_in_process() -> None:
    request, _ = _load()
    _, a = _unfold(request)
    _, b = _unfold(request)
    assert a.to_json_bytes() == b.to_json_bytes()


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
    live_body=ev.body,
)
print(fp.content_hash())
"""


def test_unfold_is_deterministic_across_interpreter_restart() -> None:
    request, expected = _load()
    _, pattern = _unfold(request)
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(_GOLDEN_DIR / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    remote_hash = result.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == expected.content_hash


# --------------------------------------------------------------------------- #
# Construction disambiguation unit test (the second collinear flange resolves) #
# --------------------------------------------------------------------------- #


def test_second_collinear_flange_resolves_its_own_bend() -> None:
    """Each provenance's recorded bend signature centroid lands on its OWN segment
    (x ~ 40 vs x ~ 160), proving construction tagged two DISTINCT coaxial bends
    rather than mis-resolving both flanges onto the first bend cylinder."""
    request, _ = _load()
    evaluation, _ = _unfold(request)
    xs = sorted(p.cyl_signature.centroid.x for p in evaluation.bend_provenance)
    assert len(xs) == 2
    assert xs[0] == pytest.approx(40.0, abs=1e-6)
    assert xs[1] == pytest.approx(160.0, abs=1e-6)


def test_golden_model_uses_deterministic_ids() -> None:
    """The committed golden model.json must parse (no random ids) so the pinned hash
    is reproducible from the file, not just a live-built tree."""
    request, _ = _load()
    assert request.part_id == uuid.UUID("00000000-0000-0000-0000-0000000c0001")
    assert len(request.features) == 6
    types = [f.feature.type for f in request.features]
    assert types.count("sheet_metal_edge_flange") == 2
