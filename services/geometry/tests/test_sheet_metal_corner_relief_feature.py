"""Corner relief as an AUTHORED FEATURE, end-to-end (docs/design/sheet-metal.md §4.4).

The unit-level `apply_corner_relief` + `unfold_sheet_metal(reliefs=...)` are gated by
``test_sheet_metal_corner_relief.py``; this suite gates the WIRED pipeline — a real
feature tree carrying a ``sheet_metal_corner_relief`` feature evaluates to a body
with the 3D notch AND a flat pattern with the matching notch, reproducing the
fold-back invariant at the evaluate/pipeline level (not just the kernel-tool level).

The golden ``corner-tray-relieved-feature`` is the ``corner-tray-relieved-unfold``
tray tree PLUS an explicit corner-relief feature (bend_a/bend_b FeatureRefs at the
two edge flanges, ``relief_ratio 1.5`` -> size 3.0 at gauge 2.0). The evaluated body
is the RELIEVED body; the flat pattern (unfolded from the pre-relief snapshot with
the recorded relief, §4.4.4) is BYTE-IDENTICAL to the unit golden's pinned
content_hash — proof the feature drives the SAME two halves the unit test does.

Honest degradation (§4.4/§5): a corner relief naming a non-bend feature is a typed
``reference_unresolved``; one naming two parallel (same) bends is a typed
``corner_relief_failed``; a bend signature that no longer resolves is a typed
``subshape_unresolved`` — never a wrong body, never a raw kernel crash, always
inside the strict-prefix partial result.
"""

import copy
import math
import uuid
from pathlib import Path

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.properties import measure_shape
from geometry.kernel.types import BodyShape
from geometry.sheet_metal import unfold_sheet_metal
from geometry.sheet_metal.resolve import cylindrical_face_widths
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureResult,
)
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDEN = _HERE.parent / "goldens-sheet-metal" / "corner-tray-relieved-feature"
_RELIEF_FEATURE_ID = "5e300000-0000-0000-0000-0000000000e3"
_EDGE_FLANGE_A_ID = "5e300000-0000-0000-0000-0000000000c3"
_BASE_FLANGE_ID = "5e300000-0000-0000-0000-0000000000b3"


class _Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    relief: dict[str, object]
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    relief_size_mm: float
    bend_allowance_mm: float
    unrelieved_flat_area_mm2: float
    removed_area_mm2: float
    flat_area_mm2: float
    flat_length_mm: float
    bend_width_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
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
    """The evaluated (relieved) body, narrowed non-None across call sites."""
    assert evaluation.body is not None
    return evaluation.body


def _relief_feature_result(result: EvaluateTreeResult) -> FeatureResult:
    """The corner-relief feature's per-feature result (by its known id)."""
    rid = uuid.UUID(_RELIEF_FEATURE_ID)
    return next(f for f in result.features if f.feature_id == rid)


def _pipeline_pattern(evaluation: TreeEvaluation):
    """The flat pattern exactly as the pipeline builds it — the recorded reliefs
    against the pre-relief snapshot (§4.4.4)."""
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


def test_relief_feature_evaluates_and_records_the_relief() -> None:
    """The authored corner-relief feature evaluates ok and populates the unfold
    inputs — one recorded relief, a pre-relief snapshot, two bends (§4.4)."""
    request, _ = _load()
    evaluation = _evaluate(request)
    assert len(evaluation.corner_reliefs) == 1
    assert len(evaluation.bend_provenance) == 2
    assert evaluation.unfold_body is not None
    # The recorded relief was sized from relief_ratio * thickness = 1.5 * 2.0.
    assert evaluation.corner_reliefs[0].size_mm == pytest.approx(3.0, abs=1e-12)
    assert evaluation.corner_reliefs[0].relief_type == "rectangular"


def test_evaluated_body_has_the_3d_notch() -> None:
    """The evaluated body IS the relieved body — the corner-relief feature cut the
    notch: less volume than the pre-relief snapshot, still one connected shell."""
    request, expected = _load()
    evaluation = _evaluate(request)
    relieved = measure_shape(_body(evaluation))
    assert evaluation.unfold_body is not None
    snapshot = measure_shape(evaluation.unfold_body)
    vtol = expected.volume_tolerance
    # The snapshot is the un-notched sheet body (the unfold reference).
    assert snapshot.volume == pytest.approx(expected.base_volume_mm3, abs=vtol)
    # The evaluated body lost exactly the notch material and stays one shell.
    assert relieved.volume == pytest.approx(expected.relieved_volume_mm3, abs=vtol)
    assert relieved.volume < snapshot.volume
    assert (snapshot.volume - relieved.volume) == pytest.approx(
        expected.removed_volume_mm3, abs=vtol
    )
    assert relieved.topology.model_dump() == expected.relieved_topology
    assert relieved.topology.shells == 1


def test_flat_pattern_matches_pinned_hash_and_area() -> None:
    """The pipeline flat pattern is byte-identical to the unit relieved golden — the
    feature drives the SAME analytic relieved unfold (§4.4.4)."""
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


def test_flat_pattern_view_picks_up_the_relief() -> None:
    """The drawing-side flat_pattern view (the real user-facing surface) develops the
    RELIEVED blank end-to-end — relieved outline + a two-row bend table, no error."""
    from geometry.drawings.flat_pattern import flat_pattern_view_result
    from py_kit.schemas.drawings import ViewScale

    request, expected = _load()
    scale = ViewScale(numerator=1, denominator=1)
    view = flat_pattern_view_result(_evaluate(request), scale)
    assert view.error is None
    body = [e for e in view.edges if e.edge_role == "body"]
    bend = [e for e in view.edges if e.edge_role == "bend"]
    assert len(body) == expected.body_edge_count
    assert len(bend) == expected.bend_edge_count
    assert len(view.bend_table) == expected.bend_count


def test_pipeline_fold_back_consistency_3d_matches_flat() -> None:
    """THE fold-back gate at the PIPELINE level (§4.4.4): the evaluated relieved body
    and the pipeline flat pattern model the SAME physical removal. Same two witnesses
    as the unit gate, now reached entirely through the feature evaluation:

    (1) the relieved body's inner bend cylindrical-face widths == flat bend_widths_mm,
    (2) removed 3D volume == removed_flat_area x thickness + neutral-vs-mean-radius
        bend term (the developed material folds to the cut material)."""
    request, expected = _load()
    evaluation = _evaluate(request)
    defaults = evaluation.sheet_metal_defaults
    assert defaults is not None
    thickness = defaults.thickness_mm
    k_factor = defaults.k_factor

    pattern = _pipeline_pattern(evaluation)
    assert evaluation.unfold_body is not None
    snapshot = measure_shape(evaluation.unfold_body)
    relieved = measure_shape(_body(evaluation))
    vtol = expected.volume_tolerance

    # (1) 3D bend-face widths (on the evaluated relieved body) == flat bend widths.
    flat_widths = sorted(b.width_mm for b in pattern.bends)
    assert flat_widths == pytest.approx(expected.bend_widths_mm, abs=expected.tolerance)
    assert cylindrical_face_widths(
        _body(evaluation), expected.bend_radius_mm
    ) == pytest.approx(flat_widths, abs=vtol)

    # (2) removed 3D volume == removed flat area x thickness + bias.
    removed_area = expected.unrelieved_flat_area_mm2 - pattern.flat_area_mm2
    angle = math.radians(expected.bend_angle_deg)
    bias = expected.bend_count * (
        expected.relief_size_mm * angle * thickness * thickness * (0.5 - k_factor)
    )
    removed_volume = snapshot.volume - relieved.volume
    assert removed_volume == pytest.approx(removed_area * thickness + bias, abs=vtol)
    assert removed_volume == pytest.approx(expected.removed_volume_mm3, abs=vtol)


def test_pipeline_is_deterministic() -> None:
    """Same tree twice → identical relieved body + byte-identical flat pattern (§9)."""
    request, _ = _load()
    a = _evaluate(request)
    b = _evaluate(request)
    assert measure_shape(_body(a)).volume == measure_shape(_body(b)).volume
    assert _pipeline_pattern(a).to_json_bytes() == _pipeline_pattern(b).to_json_bytes()


# --------------------------------------------------------------------------- #
# Honest degradation — a wired relief never yields a wrong body or a raw crash. #
# --------------------------------------------------------------------------- #


def _tree_with_relief_edit(edit: dict[str, object]) -> EvaluateTreeRequest:
    """The golden tree with the corner-relief feature's params patched."""
    request, _ = _load()
    data = request.model_dump(mode="json")
    for feat in data["features"]:
        if feat["id"] == _RELIEF_FEATURE_ID:
            feat["feature"]["params"].update(edit)
    return EvaluateTreeRequest.model_validate(data)


def test_relief_naming_a_non_bend_feature_is_reference_unresolved() -> None:
    """A corner relief whose bend ref points at a feature with no bend provenance
    (here the base flange) degrades to a typed reference_unresolved (§4.3)."""
    request = _tree_with_relief_edit(
        {"bend_a": {"kind": "feature", "feature_id": _BASE_FLANGE_ID}}
    )
    relief = _relief_feature_result(evaluate_tree(request).result)
    assert relief.status == "error"
    assert relief.error is not None
    assert relief.error.code == "reference_unresolved"


def test_relief_naming_parallel_bends_is_corner_relief_failed() -> None:
    """A corner relief naming the SAME edge flange for both bends (parallel, no corner
    intersection) degrades to a typed corner_relief_failed — never a wrong notch."""
    request = _tree_with_relief_edit(
        {"bend_b": {"kind": "feature", "feature_id": _EDGE_FLANGE_A_ID}}
    )
    relief = _relief_feature_result(evaluate_tree(request).result)
    assert relief.status == "error"
    assert relief.error is not None
    assert relief.error.code == "corner_relief_failed"


def test_relief_before_any_body_is_no_prior_body() -> None:
    """A corner relief with no preceding sheet body is a typed no_prior_body, not a
    crash (strict-prefix — the standard body-affecting guard)."""
    request, _ = _load()
    data = request.model_dump(mode="json")
    relief_feat = next(f for f in data["features"] if f["id"] == _RELIEF_FEATURE_ID)
    lone = copy.deepcopy(data)
    lone["features"] = [relief_feat]
    result = evaluate_tree(EvaluateTreeRequest.model_validate(lone)).result
    assert result.features[0].status == "error"
    assert result.features[0].error is not None
    assert result.features[0].error.code == "no_prior_body"
