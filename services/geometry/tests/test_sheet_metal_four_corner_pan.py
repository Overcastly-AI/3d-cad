"""FLAGSHIP 4-corner pan + flange-after-relief gates (docs/design/sheet-metal.md §4.4).

The canonical sheet-metal use case is a pan/box with ALL FOUR corners relieved. Every
adjacent flange pair SHARES a flange, so each of the four flanges is notched at BOTH
ends — which is exactly the ordering that used to fail: a second relief sharing a
flange with an earlier one resolved its bend signatures against the LIVE (already-
notched) body, whose shortened bend cylinder had a shifted centroid → ``subshape_
unresolved``. The fix (§4.4.4) resolves every relief against a CLEAN un-notched
reference body (all bends, no notches, maintained by the folds), then cuts the
accumulated notches from the live body.

This suite gates:
  * ``pan-four-corner-relieved`` — all ten features ok, ONE shell, a flat pattern with
    the four reentrant notches, and the fold-back invariant (3D bend-face widths ==
    flat bend widths; removed volume == removed flat area x thickness + the per-notch
    neutral-vs-mean-radius bend term over all EIGHT flange notches), reached entirely
    through ``evaluate_tree``.
  * flange-after-relief — an edge flange authored AFTER a corner relief still develops
    a CORRECT flat pattern (option (a): the clean reference keeps all bends regardless
    of feature order), never a silently-ok body with a broken flat pattern.
"""

import copy
import json
import math
import uuid
from pathlib import Path

import pytest
from geometry.drawings.flat_pattern import flat_pattern_view_result
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.properties import measure_shape
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import unfold_sheet_metal
from geometry.sheet_metal.resolve import cylindrical_face_widths
from py_kit.schemas.drawings import ViewScale
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDEN = _HERE.parent / "goldens-sheet-metal" / "pan-four-corner-relieved"
_P = "5e500000-0000-0000-0000-0000000000"


class _Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    relief_size_mm: float
    bend_allowance_mm: float
    unrelieved_flat_area_mm2: float
    removed_area_mm2: float
    flat_area_mm2: float
    bend_count: int
    notch_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_widths_mm: list[float]
    body_edge_count: int
    bend_edge_count: int
    base_volume_mm3: float
    relieved_volume_mm3: float
    removed_volume_mm3: float
    volume_tolerance: float = Field(gt=0)
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


def _pipeline_pattern(evaluation: TreeEvaluation):
    d = evaluation.sheet_metal_defaults
    assert d is not None
    assert evaluation.unfold_body is not None
    return unfold_sheet_metal(
        evaluation.unfold_body,
        evaluation.bend_provenance,
        d.thickness_mm,
        d.k_factor,
        reliefs=evaluation.corner_reliefs or None,
    )


def test_golden_present() -> None:
    assert (_GOLDEN / "model.json").exists()
    assert (_GOLDEN / "expected.json").exists()


def test_all_four_corners_relieve_cleanly() -> None:
    """The headline: base + 4 edge flanges + 4 corner reliefs all evaluate ok, and the
    body is ONE connected shell. Every adjacent flange pair shares a flange, so this is
    the shared-flange resolution the fix unblocks (each of the four flanges notched at
    both ends — the second relief on a shared flange used to be subshape_unresolved)."""
    request, expected = _load()
    evaluation = _evaluate(request)
    assert len(evaluation.corner_reliefs) == expected.bend_count  # four reliefs
    assert len(evaluation.bend_provenance) == expected.bend_count  # four bends
    relieved = measure_shape(_body(evaluation))
    assert relieved.topology.shells == 1
    assert relieved.topology.model_dump() == expected.relieved_topology
    # Each relief sized from relief_ratio * thickness = 1.5 * 2.0 = 3.0.
    for relief in evaluation.corner_reliefs:
        assert relief.size_mm == pytest.approx(expected.relief_size_mm, abs=1e-12)


def test_relieved_body_has_all_eight_notches() -> None:
    """The evaluated body IS the relieved body: less volume than the un-notched
    reference, still one shell. Each of the four flanges lost a corner bite at BOTH
    ends (eight flange notches total)."""
    request, expected = _load()
    evaluation = _evaluate(request)
    relieved = measure_shape(_body(evaluation))
    assert evaluation.unfold_body is not None
    reference = measure_shape(evaluation.unfold_body)
    vtol = expected.volume_tolerance
    assert reference.volume == pytest.approx(expected.base_volume_mm3, abs=vtol)
    assert relieved.volume == pytest.approx(expected.relieved_volume_mm3, abs=vtol)
    assert relieved.volume < reference.volume
    assert (reference.volume - relieved.volume) == pytest.approx(
        expected.removed_volume_mm3, abs=vtol
    )


def test_flat_pattern_matches_pinned_hash_and_notches() -> None:
    """The pipeline flat pattern is byte-deterministic (pinned content_hash) with the
    four reentrant corner notches and the shortened fold lines."""
    request, expected = _load()
    pattern = _pipeline_pattern(_evaluate(request))
    assert pattern.content_hash() == expected.content_hash
    assert pattern.flat_area_mm2 == pytest.approx(
        expected.flat_area_mm2, abs=expected.tolerance
    )
    assert sorted(b.width_mm for b in pattern.bends) == pytest.approx(
        expected.bend_widths_mm, abs=expected.tolerance
    )
    body = [e for e in pattern.outline if e.role == "body"]
    bend = [e for e in pattern.outline if e.role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count


def test_flat_pattern_view_develops_the_relieved_pan() -> None:
    """The user-facing drawing flat_pattern view develops the relieved pan end-to-end:
    the relieved outline + a four-row bend table, no error."""
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


def test_pan_fold_back_consistency_3d_matches_flat() -> None:
    """THE fold-back gate for the full pan (§4.4.4): the evaluated relieved body and
    the pipeline flat pattern model the SAME physical removal, over all eight notches.

    (1) the relieved body's inner bend cylindrical-face widths == flat bend_widths_mm,
    (2) removed 3D volume == removed_flat_area x thickness + the per-notch bend term,
        summed over ALL EIGHT flange notches (four flanges, notched at both ends)."""
    request, expected = _load()
    evaluation = _evaluate(request)
    defaults = evaluation.sheet_metal_defaults
    assert defaults is not None
    thickness = defaults.thickness_mm
    k_factor = defaults.k_factor

    pattern = _pipeline_pattern(evaluation)
    assert evaluation.unfold_body is not None
    reference = measure_shape(evaluation.unfold_body)
    relieved = measure_shape(_body(evaluation))
    vtol = expected.volume_tolerance

    # (1) 3D bend-face widths (on the evaluated relieved body) == flat bend widths.
    flat_widths = sorted(b.width_mm for b in pattern.bends)
    assert flat_widths == pytest.approx(expected.bend_widths_mm, abs=expected.tolerance)
    assert sorted(
        cylindrical_face_widths(_body(evaluation), expected.bend_radius_mm)
    ) == pytest.approx(flat_widths, abs=vtol)

    # (2) removed 3D volume == removed flat area x thickness + eight-notch bend bias.
    removed_area = expected.unrelieved_flat_area_mm2 - pattern.flat_area_mm2
    angle = math.radians(expected.bend_angle_deg)
    bias = expected.notch_count * (
        expected.relief_size_mm * angle * thickness * thickness * (0.5 - k_factor)
    )
    removed_volume = reference.volume - relieved.volume
    assert removed_volume == pytest.approx(removed_area * thickness + bias, abs=vtol)
    assert removed_volume == pytest.approx(expected.removed_volume_mm3, abs=vtol)


def test_pan_is_deterministic() -> None:
    """Same tree twice → identical relieved body + byte-identical flat pattern (§9)."""
    request, _ = _load()
    a = _evaluate(request)
    b = _evaluate(request)
    assert measure_shape(_body(a)).volume == measure_shape(_body(b)).volume
    assert _pipeline_pattern(a).to_json_bytes() == _pipeline_pattern(b).to_json_bytes()


# --------------------------------------------------------------------------- #
# Flange authored AFTER a relief → a CORRECT flat pattern (option (a), §4.4.4). #
# --------------------------------------------------------------------------- #


def _flange_after_relief_tree() -> EvaluateTreeRequest:
    """Base + flange c (off x=40) + flange e (off y=30) + a corner relief at their
    shared corner + flange d (off x=0) authored AFTER the relief."""
    base = json.loads((_GOLDEN / "model.json").read_text("utf-8"))
    byid = {f["id"]: f for f in base["features"]}
    relief = {
        "id": _P + "1a",
        "feature": {
            "type": "sheet_metal_corner_relief",
            "version": 1,
            "params": {
                "bend_a": {"kind": "feature", "feature_id": _P + "c5"},
                "bend_b": {"kind": "feature", "feature_id": _P + "e5"},
                "relief_ratio": 1.5,
            },
        },
    }
    tree = copy.deepcopy(base)
    tree["features"] = [
        byid[_P + "a5"],  # sketch
        byid[_P + "b5"],  # base flange
        byid[_P + "c5"],  # edge flange off x=40
        byid[_P + "e5"],  # edge flange off y=30
        relief,  # corner relief at (40, 30)
        byid[_P + "d5"],  # edge flange off x=0 — AUTHORED AFTER the relief
    ]
    return EvaluateTreeRequest.model_validate(tree)


def test_flange_after_relief_develops_a_correct_flat_pattern() -> None:
    """An edge flange authored AFTER a corner relief still develops a CORRECT flat
    pattern — never a silently-ok body with a broken (subshape_unresolved) flat
    pattern (§4.4.4 option (a)). The clean reference keeps ALL bends regardless of
    order, so the late flange's bend resolves and its full-width fold line develops."""
    evaluation = _evaluate(_flange_after_relief_tree())
    assert len(evaluation.bend_provenance) == 3
    assert len(evaluation.corner_reliefs) == 1

    # The drawing flat_pattern view (the user-facing surface) must NOT error.
    view = flat_pattern_view_result(evaluation, ViewScale(numerator=1, denominator=1))
    assert view.error is None
    assert len(view.bend_table) == 3

    pattern = _pipeline_pattern(evaluation)
    # Relief at (40,30) notches flange c (off x=40, span 30 → 27) and flange e (off
    # y=30, span 40 → 37); the late flange d (off x=0) is UNRELIEVED → full width 30.
    assert sorted(b.width_mm for b in pattern.bends) == pytest.approx(
        [27.0, 30.0, 37.0], abs=1e-9
    )
    # One relief still cuts a real notch: the relieved body is one shell.
    assert measure_shape(_body(evaluation)).topology.shells == 1


def test_flange_after_relief_flat_pattern_is_deterministic() -> None:
    """Same flange-after-relief tree twice → byte-identical flat pattern (§9)."""
    request = _flange_after_relief_tree()
    a = _pipeline_pattern(_evaluate(request))
    b = _pipeline_pattern(_evaluate(request))
    assert a.to_json_bytes() == b.to_json_bytes()


def test_reliefs_sharing_a_flange_all_resolve() -> None:
    """The specific fix: consecutive reliefs that SHARE a flange each evaluate ok.

    In the full pan the four reliefs are g(c,e) h(d,e) i(d,f) j(c,f): h shares flange e
    with g, i shares d with h, j shares c with f... every relief after the first shares
    a flange with an earlier one. Before the fix, the shared flange's bend — shortened
    by the earlier notch — no longer resolved against the live body (used to be
    subshape_unresolved). Now every relief resolves against the clean reference."""
    request, _ = _load()
    evaluation = evaluate_tree(request)
    relief_results = [
        f
        for f in evaluation.result.features
        if f.feature_id in {uuid.UUID(_P + s) for s in ("1a", "1b", "1c", "1d")}
    ]
    assert len(relief_results) == 4
    assert all(r.status == "ok" for r in relief_results), [
        (str(r.feature_id), r.error.code if r.error else None) for r in relief_results
    ]
