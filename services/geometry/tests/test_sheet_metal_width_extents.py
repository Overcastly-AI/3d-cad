"""WF-1 LAYER 2 — edge-flange WIDTH EXTENTS + auto bend-END relief + partial-width
development (docs/design/sheet-metal.md §4.5; BACKLOG WF-1 layer 2 + PB-1).

Founder acceptance case, gated by golden: a 100 x 100 base (t = 1.5, r = 2) with a
90-deg flange 50 mm WIDE x 50 mm tall authored DIRECTLY on the full 100 mm edge
(``width_mm``/``offset_mm`` — no cut hack): valid solid with the automatic
bend-end relief notch, analytic volume, correct blank WITH the notch, fold-back
invariant against the live body, byte-determinism. Plus the centered variant (two
interior ends -> two notches), the §4.5.1 schema/feature rejects, and the PB-1
case (a full-width flange on a notch-split edge SEGMENT), which falls out of the
same §4.5.3 outline machinery — previously the `_emit_plus_pattern` typed reject.

Absent width params stay byte-identical to the legacy build — proven by every
committed sheet-metal golden's pinned content hash, not re-proven here.

Tolerances are the goldens' documented per-model values (geometry-gates rule,
never ad-hoc): see each expected.json's tolerance_rationale.
"""

import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from geometry.drawings import flat_pattern_view_result
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.sheet_metal import FlatPattern, unfold_sheet_metal
from geometry.sheet_metal.resolve import coaxial_cylindrical_face_widths
from py_kit.schemas.drawings import ViewScale
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    SheetMetalEdgeFlangeParamsV1,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"
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
    relief_notch_size_mm: float
    relief_notch_count: int
    body_edge_count: int
    bend_edge_count: int
    volume_mm3: float
    volume_tolerance: float = Field(gt=0)
    topology: dict[str, int]
    content_hash: str


_GOLDEN_DIRS = sorted(
    m.parent for m in _GOLDENS_DIR.glob("partial-flange-*/model.json")
)
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_partial_flange_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no partial-flange goldens under {_GOLDENS_DIR}"


def _load(golden_dir: Path) -> tuple[EvaluateTreeRequest, _Expected]:
    request = EvaluateTreeRequest.model_validate_json(
        (golden_dir / "model.json").read_text("utf-8")
    )
    expected = _Expected.model_validate_json(
        (golden_dir / "expected.json").read_text("utf-8")
    )
    return request, expected


def _unfold(request: EvaluateTreeRequest) -> tuple[TreeEvaluation, FlatPattern]:
    evaluation = evaluate_tree(request)
    statuses = [f.status for f in evaluation.result.features]
    assert all(s == "ok" for s in statuses), statuses
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
    """Chain the body edges end-to-end into one closed loop, or None."""
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
    """Shoelace area of the closed vertex loop (last vertex == first)."""
    pts = loop[:-1]
    n = len(pts)
    acc = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


# --------------------------------------------------------------------------- #
# Golden gate                                                                  #
# --------------------------------------------------------------------------- #


@each_golden
def test_unfold_matches_hand_derivation(golden_dir: Path) -> None:
    """Analytic BA / area / envelope / fold width against the golden (§9 #1/#2)."""
    request, expected = _load(golden_dir)
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


@each_golden
def test_outline_is_single_closed_loop_with_the_notch(golden_dir: Path) -> None:
    """The blank is ONE closed loop with the relief notch(es): exact edge counts,
    envelope from the loop, and shoelace area == the reported blank area (the
    independent geometric witness that the notched layout tiles the blank)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    loop = _chain_loop(pattern)
    assert loop is not None, "outline body edges do not form one closed loop"
    xs = [p[0] for p in loop]
    ys = [p[1] for p in loop]
    tol = expected.tolerance
    assert max(xs) - min(xs) == pytest.approx(expected.flat_length_mm, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(expected.bend_width_mm, abs=tol)
    assert _enclosed_area(loop) == pytest.approx(pattern.flat_area_mm2, abs=1e-6)
    # Each fold line spans exactly the AUTHORED width (never the full edge).
    for e in bend:
        assert math.dist((e.x1, e.y1), (e.x2, e.y2)) == pytest.approx(
            expected.bend_widths_mm[0], abs=tol
        )


@each_golden
def test_body_volume_and_topology(golden_dir: Path) -> None:
    """The 3D body carries the relief notch(es): analytic volume + exact topology."""
    request, expected = _load(golden_dir)
    evaluation, _ = _unfold(request)
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


@each_golden
def test_fold_back_invariant_and_pipeline(golden_dir: Path) -> None:
    """The goldens' fold-back invariant, live: the body's cylindrical bend-face
    widths equal the developed fold widths (the §4.5.2 notch never touches the
    bend), and the flat-pattern PIPELINE — which always runs the WF-1 runtime
    cross-check against the live body — succeeds with no error."""
    request, expected = _load(golden_dir)
    evaluation, pattern = _unfold(request)
    assert evaluation.body is not None
    live_widths: list[float] = []
    for prov in evaluation.bend_provenance:
        live_widths.extend(
            coaxial_cylindrical_face_widths(evaluation.body, prov.cyl_signature)
        )
    assert sorted(live_widths) == pytest.approx(
        sorted(b.width_mm for b in pattern.bends), abs=1e-6
    )
    result = flat_pattern_view_result(evaluation, _UNIT_SCALE)
    assert result.error is None, result.error
    assert len(result.bend_table) == expected.bend_count


@each_golden
def test_unfold_is_deterministic_in_process(golden_dir: Path) -> None:
    """Same tree twice → byte-identical FlatPattern serialization (§9 #4)."""
    request, _ = _load(golden_dir)
    _, a = _unfold(request)
    _, b = _unfold(request)
    assert a.to_json_bytes() == b.to_json_bytes()


@each_golden
def test_unfold_content_hash_matches_pinned_golden(golden_dir: Path) -> None:
    """The serialized FlatPattern matches the committed determinism pin (P0)."""
    request, expected = _load(golden_dir)
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
fp = unfold_sheet_metal(
    ev.unfold_body or ev.body,
    ev.bend_provenance,
    d.thickness_mm,
    d.k_factor,
    live_body=ev.body,
)
print(fp.content_hash())
"""


@each_golden
def test_unfold_is_deterministic_across_interpreter_restart(golden_dir: Path) -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical FlatPattern hash."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(golden_dir / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    remote_hash = result.stdout.splitlines()[0]
    assert remote_hash == pattern.content_hash()
    assert remote_hash == expected.content_hash


# --------------------------------------------------------------------------- #
# Schema + feature-eval rejects (§4.5.1)                                       #
# --------------------------------------------------------------------------- #

_T, _R, _K = 1.5, 2.0, 0.44


def _edge_params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "edge": {
            "kind": "subshape",
            "feature_id": str(uuid.uuid4()),
            "subshape_type": "edge",
            "selector": {
                "selector_version": 1,
                "signature": {
                    "subshape_type": "edge",
                    "curve": "line",
                    "end_a": {"x": 0.0, "y": 0.0, "z": _T},
                    "end_b": {"x": 100.0, "y": 0.0, "z": _T},
                    "midpoint": {"x": 50.0, "y": 0.0, "z": _T},
                    "length_mm": 100.0,
                },
            },
        },
        "flange_length_mm": 50.0,
        "bend_angle_deg": 90.0,
    }
    params.update(overrides)
    return params


def test_width_zero_is_a_schema_reject() -> None:
    """width_mm = 0 violates the gt=0 bound — a 422, never a degenerate build."""
    with pytest.raises(ValidationError):
        SheetMetalEdgeFlangeParamsV1.model_validate(_edge_params(width_mm=0.0))


def test_negative_offset_is_a_schema_reject() -> None:
    """offset_mm < 0 violates the ge=0 bound."""
    with pytest.raises(ValidationError):
        SheetMetalEdgeFlangeParamsV1.model_validate(_edge_params(offset_mm=-1.0))


def test_width_params_default_to_full_width() -> None:
    """Absent width params read (None, None) — the full-width legacy contract
    (both nullable-optional on the wire so existing clients stay valid)."""
    params = SheetMetalEdgeFlangeParamsV1.model_validate(_edge_params())
    assert params.width_mm is None
    assert params.offset_mm is None


def _rect_sketch(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": x0, "y": y0},
                "end": {"x": x1, "y": y0},
            },
            {
                "id": "e2",
                "kind": "line",
                "start": {"x": x1, "y": y0},
                "end": {"x": x1, "y": y1},
            },
            {
                "id": "e3",
                "kind": "line",
                "start": {"x": x1, "y": y1},
                "end": {"x": x0, "y": y1},
            },
            {
                "id": "e4",
                "kind": "line",
                "start": {"x": x0, "y": y1},
                "end": {"x": x0, "y": y0},
            },
        ],
        "constraints": [],
    }


def _founder_tree(width_mm: float | None, offset_mm: float) -> EvaluateTreeRequest:
    """The founder base + a width-extent flange on the y=0 edge."""
    sk, bf, ef = (str(uuid.uuid4()) for _ in range(3))
    params = _edge_params(
        **({"width_mm": width_mm} if width_mm is not None else {}),
        **({"offset_mm": offset_mm} if offset_mm else {}),
    )
    edge: dict[str, Any] = params["edge"]  # type: ignore[assignment]
    edge["feature_id"] = bf
    features = [
        {
            "id": sk,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": _rect_sketch(0.0, 0.0, 100.0, 100.0),
            },
        },
        {
            "id": bf,
            "feature": {
                "type": "sheet_metal_base_flange",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sk},
                    "thickness_mm": _T,
                    "bend_radius_mm": _R,
                    "k_factor": _K,
                },
            },
        },
        {
            "id": ef,
            "feature": {
                "type": "sheet_metal_edge_flange",
                "version": 1,
                "params": params,
            },
        },
    ]
    return EvaluateTreeRequest.model_validate(
        {"part_id": str(uuid.uuid4()), "tree_version": 1, "features": features}
    )


def test_span_overflowing_the_edge_is_a_typed_feature_error() -> None:
    """offset + width > edge length can only be checked against the RESOLVED edge
    — a typed `edge_flange_failed` naming the extents, never a raw kernel error."""
    for width, offset in ((120.0, 0.0), (50.0, 60.0)):
        evaluation = evaluate_tree(_founder_tree(width, offset))
        statuses = [f.status for f in evaluation.result.features]
        assert statuses == ["ok", "ok", "error"], (width, offset, statuses)
        err = evaluation.result.features[2].error
        assert err is not None and err.code == "edge_flange_failed"
        assert "width extents" in err.message


def test_offset_with_omitted_width_spans_the_remainder() -> None:
    """width_mm = None + offset > 0 spans [offset, edge_length] (§4.5.1): one
    interior end (the offset side) -> one relief notch; fold width = 100 - 30."""
    evaluation = evaluate_tree(_founder_tree(None, 30.0))
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    assert evaluation.sheet_metal_defaults is not None
    assert evaluation.body is not None and evaluation.unfold_body is not None
    pattern = unfold_sheet_metal(
        evaluation.unfold_body,
        evaluation.bend_provenance,
        _T,
        _K,
        live_body=evaluation.body,
    )
    assert len(pattern.bends) == 1
    assert pattern.bends[0].width_mm == pytest.approx(70.0, abs=1e-9)
    props = evaluation.result.properties
    assert props is not None
    ba = (math.pi / 2.0) * (_R + _K * _T)
    # One notch (at the offset-side interior end): base - t^3 + bend + wall.
    analytic_volume = (
        100.0 * 100.0 * _T
        - _T**3
        + (math.pi / 4.0) * ((_R + _T) ** 2 - _R**2) * 70.0
        + 50.0 * _T * 70.0
    )
    assert props.volume == pytest.approx(analytic_volume, abs=1e-6)
    assert pattern.flat_area_mm2 == pytest.approx(
        100.0 * 100.0 - _T * _T + ba * 70.0 + 50.0 * 70.0, abs=1e-9
    )


# --------------------------------------------------------------------------- #
# PB-1 — a full-width flange on a notch-split edge SEGMENT falls out (§4.5.3)  #
# --------------------------------------------------------------------------- #


def _pb1_tree() -> EvaluateTreeRequest:
    """200 x 100 base; a 60 x 10 notch cut through the y=0 edge BEFORE the fold;
    a full-width flange (leg 40) on the surviving x in [0, 70] edge segment."""
    sk, bf, skc, cut, ef = (str(uuid.uuid4()) for _ in range(5))
    features = [
        {
            "id": sk,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": _rect_sketch(0.0, 0.0, 200.0, 100.0),
            },
        },
        {
            "id": bf,
            "feature": {
                "type": "sheet_metal_base_flange",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sk},
                    "thickness_mm": _T,
                    "bend_radius_mm": _R,
                    "k_factor": _K,
                },
            },
        },
        {
            "id": skc,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": _rect_sketch(70.0, -5.0, 130.0, 10.0),
            },
        },
        {
            "id": cut,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": skc},
                    "distance_mm": 60.0,
                    "operation": "cut",
                },
            },
        },
        {
            "id": ef,
            "feature": {
                "type": "sheet_metal_edge_flange",
                "version": 1,
                "params": {
                    "edge": {
                        "kind": "subshape",
                        "feature_id": bf,
                        "subshape_type": "edge",
                        "selector": {
                            "selector_version": 1,
                            "signature": {
                                "subshape_type": "edge",
                                "curve": "line",
                                "end_a": {"x": 0.0, "y": 0.0, "z": _T},
                                "end_b": {"x": 70.0, "y": 0.0, "z": _T},
                                "midpoint": {"x": 35.0, "y": 0.0, "z": _T},
                                "length_mm": 70.0,
                            },
                        },
                    },
                    "flange_length_mm": 40.0,
                    "bend_angle_deg": 90.0,
                },
            },
        },
    ]
    return EvaluateTreeRequest.model_validate(
        {"part_id": str(uuid.uuid4()), "tree_version": 1, "features": features}
    )


def test_pb1_notch_split_edge_flange_now_flat_patterns() -> None:
    """THE PB-1 gate: a flange on a notch-split edge segment — a perfect 3D body
    that used to typed-reject at the `_emit_plus_pattern` single-loop guard — now
    develops through the §4.5.3 partial-star emitter: the base keeps its notch,
    the strip replaces only its 70 mm span, one closed loop, exact analytics,
    fold-back green through the pipeline. Tolerances: 1e-9 (closed-form layout,
    measured residuals <= 2e-12) / volume 1e-6 mm^3 (measured 5e-11)."""
    evaluation = evaluate_tree(_pb1_tree())
    statuses = [f.status for f in evaluation.result.features]
    assert all(s == "ok" for s in statuses), statuses
    props = evaluation.result.properties
    assert props is not None
    analytic_volume = (
        200.0 * 100.0 * _T
        - 60.0 * 10.0 * _T
        + (math.pi / 4.0) * ((_R + _T) ** 2 - _R**2) * 70.0
        + 40.0 * _T * 70.0
    )
    assert props.volume == pytest.approx(analytic_volume, abs=1e-6)

    assert evaluation.body is not None and evaluation.unfold_body is not None
    pattern = unfold_sheet_metal(
        evaluation.unfold_body,
        evaluation.bend_provenance,
        _T,
        _K,
        live_body=evaluation.body,
    )
    ba = (math.pi / 2.0) * (_R + _K * _T)
    assert len(pattern.bends) == 1
    assert pattern.bends[0].width_mm == pytest.approx(70.0, abs=1e-9)
    assert pattern.flat_area_mm2 == pytest.approx(
        200.0 * 100.0 - 600.0 + ba * 70.0 + 40.0 * 70.0, abs=1e-9
    )
    loop = _chain_loop(pattern)
    assert loop is not None, "PB-1 blank is not one closed loop"
    assert _enclosed_area(loop) == pytest.approx(pattern.flat_area_mm2, abs=1e-6)
    # No auto relief for a full-width flange on its segment: the ends are the
    # segment's own endpoints (a blank corner + the notch boundary, §4.5.2).
    assert len([e for e in pattern.outline if e.role == "body"]) == 8

    result = flat_pattern_view_result(evaluation, _UNIT_SCALE)
    assert result.error is None, result.error
    assert result.bend_table[0].bend_allowance_mm == pytest.approx(ba, abs=1e-9)


def test_pb1_is_deterministic_in_process() -> None:
    """Same PB-1 geometry twice → byte-identical FlatPattern (§9 #4)."""

    def build() -> FlatPattern:
        ev = evaluate_tree(_pb1_tree())
        assert ev.unfold_body is not None and ev.body is not None
        return unfold_sheet_metal(
            ev.unfold_body, ev.bend_provenance, _T, _K, live_body=ev.body
        )

    assert build().to_json_bytes() == build().to_json_bytes()
