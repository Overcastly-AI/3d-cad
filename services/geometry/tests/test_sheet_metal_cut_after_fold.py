"""WF-1 — cut-after-fold flat pattern is an HONEST typed reject, never a wrong blank.

Founder dogfooding 2026-07-22 (BACKLOG P0): a base flange 100 x 100 (t = 1.5,
r = 2, K = 0.44), a FULL-WIDTH 90-deg edge flange on the y=0 edge (leg 50), then an
ordinary extrude CUT trimming the flange AND its bend to 50 wide. The 3D body is
exact (kernel volume == closed form), but the unfold develops from the CLEAN fold
reference (``TreeEvaluation.unfold_body``, maintained by the folds — sheet-metal.md
§4.4.4), which never saw the cut: before the fix the flat pattern SUCCEEDED with the
full-width 154.178 x 100 blank — the silently-wrong development §5/§7 forbid.

Layer 1 (this suite's subject): the runtime FOLD-BACK cross-check inside
:func:`geometry.sheet_metal.unfold_sheet_metal` — every developed fold width must
equal a live cylindrical bend-face width on that bend's axis
(:func:`geometry.sheet_metal.resolve.coaxial_cylindrical_face_widths`, centroid
deliberately ignored so the TRIMMED bend is measured, not lost). The WF-1 repro is
now a typed ``flat_pattern_failed`` naming the fold and both widths; layer 2
(developing the trimmed fold correctly, width-extent params) is the documented
follow-on.

Tolerances are documented per-model (geometry-gates rule, never ad-hoc): closed-form
volume residual measured 2.2e-11 on build123d 0.11.1 / OCCT 7.9 (2026-07-22);
the 1e-6 mm^3 ceiling matches the sibling sheet-metal goldens' volume tolerance
(hemmed-wall / four-corner pan) with ample FP headroom.
"""

import math
import uuid
from typing import Any

import pytest
from geometry.drawings import flat_pattern_view_result
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from py_kit.schemas.drawings import DrawingViewResult, ViewScale
from py_kit.schemas.features import EvaluateTreeRequest

_UNIT_SCALE = ViewScale(numerator=1, denominator=1)

_SK = "00000000-0000-0000-0000-00000000f0a1"
_BF = "00000000-0000-0000-0000-00000000f0b1"
_EF = "00000000-0000-0000-0000-00000000f0c1"
_SK_CUT = "00000000-0000-0000-0000-00000000f0d1"
_CUT = "00000000-0000-0000-0000-00000000f0e1"

_THICKNESS = 1.5
_RADIUS = 2.0
_LEG = 50.0
#: Closed-form 3D volume of the TRIMMED part (mm^3): base plate 100 x 100 x 1.5 +
#: the surviving 50-wide bend (quarter annulus (pi/4) * (3.5^2 - 2^2) * 50) + the
#: surviving 50-wide wall (leg 50 x t 1.5 x 50) = 19073.976742 — the founder-verified
#: "3D is perfect" number.
_TRIMMED_VOLUME = (
    100.0 * 100.0 * _THICKNESS
    + (math.pi / 4.0) * ((_RADIUS + _THICKNESS) ** 2 - _RADIUS**2) * 50.0
    + _LEG * _THICKNESS * 50.0
)
_VOLUME_TOL = 1e-6  # mm^3 — documented above (measured residual 2.2e-11)


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


def _wf1_tree(
    cut_rect: tuple[float, float, float, float] | None,
) -> EvaluateTreeRequest:
    """The WF-1 feature tree: base flange + full-width edge flange (+ optional cut).

    *cut_rect* is the XY-plane cut profile ``(x0, y0, x1, y1)`` extruded 60 mm
    (``operation="cut"``); ``None`` builds the un-cut control part.
    """
    features: list[dict[str, Any]] = [
        {
            "id": _SK,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": _rect_sketch(0.0, 0.0, 100.0, 100.0),
            },
        },
        {
            "id": _BF,
            "feature": {
                "type": "sheet_metal_base_flange",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _SK},
                    "thickness_mm": _THICKNESS,
                    "bend_radius_mm": _RADIUS,
                    "k_factor": 0.44,
                },
            },
        },
        {
            "id": _EF,
            "feature": {
                "type": "sheet_metal_edge_flange",
                "version": 1,
                "params": {
                    "edge": {
                        "kind": "subshape",
                        "feature_id": _BF,
                        "subshape_type": "edge",
                        "selector": {
                            "selector_version": 1,
                            "signature": {
                                "subshape_type": "edge",
                                "curve": "line",
                                "end_a": {"x": 0.0, "y": 0.0, "z": 1.5},
                                "end_b": {"x": 100.0, "y": 0.0, "z": 1.5},
                                "midpoint": {"x": 50.0, "y": 0.0, "z": 1.5},
                                "length_mm": 100.0,
                            },
                        },
                    },
                    "flange_length_mm": _LEG,
                    "bend_angle_deg": 90.0,
                },
            },
        },
    ]
    if cut_rect is not None:
        x0, y0, x1, y1 = cut_rect
        features += [
            {
                "id": _SK_CUT,
                "feature": {
                    "type": "sketch",
                    "version": 1,
                    "params": _rect_sketch(x0, y0, x1, y1),
                },
            },
            {
                "id": _CUT,
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": _SK_CUT},
                        "distance_mm": 60.0,
                        "operation": "cut",
                    },
                },
            },
        ]
    return EvaluateTreeRequest.model_validate(
        {"part_id": str(uuid.uuid4()), "tree_version": 1, "features": features}
    )


def _evaluate(request: EvaluateTreeRequest) -> TreeEvaluation:
    evaluation = evaluate_tree(request)
    assert all(f.status == "ok" for f in evaluation.result.features), (
        "the WF-1 tree evaluates fully green — the dishonesty was only ever in "
        "the flat pattern"
    )
    return evaluation


def _flat_pattern(evaluation: TreeEvaluation) -> DrawingViewResult:
    return flat_pattern_view_result(evaluation, _UNIT_SCALE)


def test_wf1_3d_body_is_exact_and_green() -> None:
    """The founder-verified premise: evaluate is green and the trimmed 3D volume
    equals the closed form exactly — the defect was NEVER in the solid model."""
    evaluation = _evaluate(_wf1_tree((50.0, -6.0, 101.0, 0.0)))
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(_TRIMMED_VOLUME, abs=_VOLUME_TOL)


def test_wf1_cut_after_fold_flat_pattern_is_typed_reject() -> None:
    """THE WF-1 gate: the trimmed-fold part flat-patterns to a typed
    ``flat_pattern_failed`` naming the fold and BOTH widths — never the silent
    full-width 154.178 x 100 blank it produced before the fix, never a crash."""
    evaluation = _evaluate(_wf1_tree((50.0, -6.0, 101.0, 0.0)))
    result = _flat_pattern(evaluation)
    assert result.edges == []
    assert result.bend_table == []
    assert result.error is not None
    assert result.error.code == "flat_pattern_failed"
    # The message names the fold and both widths (the honest-reject contract):
    # the development says 100 mm, the live trimmed bend face measures 50 mm.
    assert "bend-1" in result.error.message
    assert "100" in result.error.message
    assert "50" in result.error.message
    assert "cut" in result.error.message


def test_wf1_cut_that_removes_the_whole_fold_is_typed_reject() -> None:
    """A cut that removes the flange AND its bend ENTIRELY (live body has zero
    bend faces left, provenance still records the fold): the count arm of the
    fold-back check — a typed reject, not a blank developing a ghost fold."""
    evaluation = _evaluate(_wf1_tree((-1.0, -6.0, 101.0, 0.0)))
    result = _flat_pattern(evaluation)
    assert result.error is not None
    assert result.error.code == "flat_pattern_failed"
    assert "0 cylindrical bend face" in result.error.message


def test_wf1_uncut_control_still_flat_patterns() -> None:
    """The un-cut sibling part (same base + full-width flange, no cut) still
    develops: the fold-back check must NOT trip on a correct unfold. Blank =
    (100 + BA + 50) x 100 with BA = (pi/2) * (2 + 0.44 * 1.5) (sheet-metal §1)."""
    evaluation = _evaluate(_wf1_tree(None))
    result = _flat_pattern(evaluation)
    assert result.error is None, result.error
    ba = (math.pi / 2.0) * (_RADIUS + 0.44 * _THICKNESS)
    xs = [c for e in result.edges for c in (e.start.x_mm, e.end.x_mm)]
    ys = [c for e in result.edges for c in (e.start.y_mm, e.end.y_mm)]
    tol = 1e-9  # documented: exact closed-form layout, residuals are ulp-scale
    assert max(xs) - min(xs) == pytest.approx(100.0 + ba + _LEG, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(100.0, abs=tol)
    assert len(result.bend_table) == 1
    assert result.bend_table[0].bend_allowance_mm == pytest.approx(ba, abs=tol)
