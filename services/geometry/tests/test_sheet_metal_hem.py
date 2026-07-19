"""Sheet-metal CLOSED HEM — parity slice (docs/design/sheet-metal-parity.md §2).

A closed hem folds the picked edge ~180 deg back FLAT onto the parent face with a
small inner radius — mechanically a SPECIALIZATION of the shipped edge flange (a
fixed 180-deg fold), so it reuses :func:`build_edge_flange`'s bend machinery and the
shipped :func:`unfold_sheet_metal` verbatim. This gate proves the near-flat fold:

* **Provenance flat-pattern golden** — the authored ``closed-hem-plate`` (a plate +
  one closed hem) rebuilds from a real feature tree, is unfolded by PROVENANCE, and
  is asserted against HAND-DERIVED analytic flat length / area / bend allowance
  (§9 #1/#2, BA = pi*(r + K*t)), plus the fused body's volume + topology + ONE valid
  solid/shell, plus byte-determinism (in-process + a fresh interpreter restart, §9 #4).
* **Schema + evaluation unit tests** — ``SheetMetalHemParamsV1`` lands the intended
  shape (hem_type defaults ``"closed"``; radius/K inherit ``None``), is registered +
  reference-mapped, and the evaluator folds the return (bend_angle fixed 180 deg),
  inherits the base defaults, and records the bend provenance at a 180-deg fold.
* **Honest degradation (parity §3)** — a ZERO-radius (zero-gap degenerate) hem is a
  typed schema rejection; a kernel fold failure maps to a typed ``edge_flange_failed``
  (never a raw exception or an invalid solid); an unresolvable edge is
  ``subshape_unresolved``; a hem with no prior body is ``no_prior_body``.
"""

import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.sheet_metal import (
    FlatPattern,
    unfold_sheet_metal,
)
from py_kit.schemas.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    EvaluateTreeRequest,
    Feature,
    FeatureEnvelope,
    SheetMetalHemFeature,
    SheetMetalHemParamsV1,
    feature_references,
)
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"


# --------------------------------------------------------------------------- #
# Provenance flat-pattern golden                                              #
# --------------------------------------------------------------------------- #


class _ExpectedHem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    tangent_line_convention: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
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


_GOLDEN_DIRS = sorted(
    model.parent for model in _GOLDENS_DIR.glob("closed-hem-*/model.json")
)
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_hem_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no closed-hem-* goldens under {_GOLDENS_DIR}"


def _load(golden_dir: Path) -> tuple[EvaluateTreeRequest, _ExpectedHem]:
    request = EvaluateTreeRequest.model_validate_json(
        (golden_dir / "model.json").read_text("utf-8")
    )
    expected = _ExpectedHem.model_validate_json(
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
        evaluation.body,
        evaluation.bend_provenance,
        defaults.thickness_mm,
        defaults.k_factor,
    )
    return evaluation, pattern


@each_golden
def test_unfold_matches_hand_derivation(golden_dir: Path) -> None:
    """The authored hemmed body unfolds to the HAND-DERIVED flat pattern (§9)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance

    # Hand derivation, recomputed here — a third source independent of the golden
    # AND the kernel (geometry-gates skill). A closed hem is a 180-deg fold.
    ba = math.pi * (expected.bend_radius_mm + 0.44 * 2.0)
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)

    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)

    assert len(pattern.bends) == expected.bend_count
    for bend in pattern.bends:
        assert bend.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bend.angle_deg == pytest.approx(180.0, abs=tol)  # a hem is ~180 deg
        assert bend.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bend.allowance_mm == pytest.approx(ba, abs=tol)
        assert bend.direction == expected.bend_direction
        assert bend.k_factor == pytest.approx(0.44, abs=tol)


@each_golden
def test_unfold_area_conservation_sum_of_parts(golden_dir: Path) -> None:
    """§9 #2: flat_area = base_area + hem_area + BA*width — the developed strip is a
    normal bend strip; reconstructed from the pattern's own reported pieces."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance
    width = pattern.bend_width_mm
    strip_total = sum(b.allowance_mm * b.width_mm for b in pattern.bends)
    rect_area = pattern.flat_length_mm * width
    assert pattern.flat_area_mm2 == pytest.approx(rect_area, abs=tol)
    assert strip_total == pytest.approx(
        expected.bend_count * expected.bend_allowance_mm * width, abs=tol
    )


@each_golden
def test_fused_body_is_one_valid_solid_with_analytic_props(golden_dir: Path) -> None:
    """The hemmed body is ONE valid solid/shell (BRepCheck) with the analytic volume
    + exact topology — the near-flat fold does NOT self-intersect (parity §3)."""
    from OCP.BRepCheck import BRepCheck_Analyzer  # type: ignore[import-untyped]

    request, expected = _load(golden_dir)
    evaluation, _ = _unfold(request)
    body = evaluation.body
    assert body is not None
    assert len(body.solids()) == 1
    assert len(body.shells()) == 1
    assert BRepCheck_Analyzer(body.wrapped).IsValid()  # type: ignore[no-untyped-call]
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


@each_golden
def test_outline_is_rectangle_with_one_bend_line(golden_dir: Path) -> None:
    """The developed blank is a rectangle (4 body edges) + one fold line for the hem."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    body_edges = [e for e in pattern.outline if e.role == "body"]
    bend_edges = [e for e in pattern.outline if e.role == "bend"]
    assert len(body_edges) == 4
    assert len(bend_edges) == expected.bend_count
    tol = expected.tolerance
    xs = [c for e in body_edges for c in (e.x1, e.x2)]
    ys = [c for e in body_edges for c in (e.y1, e.y2)]
    assert max(xs) - min(xs) == pytest.approx(expected.flat_length_mm, abs=tol)
    assert max(ys) - min(ys) == pytest.approx(expected.bend_width_mm, abs=tol)


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
fp = unfold_sheet_metal(ev.body, ev.bend_provenance, d.thickness_mm, d.k_factor)
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
# Schema unit tests                                                           #
# --------------------------------------------------------------------------- #


def _edge_ref(feature_id: uuid.UUID) -> dict[str, object]:
    return {
        "kind": "subshape",
        "feature_id": str(feature_id),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "curve": "line",
                "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
                "end_b": {"x": 0.0, "y": 20.0, "z": 0.0},
                "midpoint": {"x": 0.0, "y": 10.0, "z": 0.0},
                "length_mm": 20.0,
            },
        },
    }


def test_hem_type_defaults_closed_and_radius_k_inherit() -> None:
    """hem_type defaults 'closed'; bend_radius_mm / k_factor default None (inherit)."""
    params = SheetMetalHemParamsV1.model_validate(
        {"edge": _edge_ref(uuid.uuid4()), "length_mm": 15.0}
    )
    assert params.hem_type == "closed"
    assert params.bend_radius_mm is None
    assert params.k_factor is None


def test_positive_and_bounded_params() -> None:
    """length > 0, overriding radius > 0, K in [0,1], and only 'closed' hem_type."""
    base = {"edge": _edge_ref(uuid.uuid4()), "length_mm": 15.0}
    for bad in (
        {"length_mm": 0.0},
        {"bend_radius_mm": 0.0},  # zero-radius / zero-gap degenerate hem (parity §3)
        {"bend_radius_mm": -1.0},
        {"k_factor": -0.1},
        {"k_factor": 1.1},
        {"hem_type": "open"},  # deferred shape — not a v1 value
        {"hem_type": "rolled"},
    ):
        with pytest.raises(ValidationError):
            SheetMetalHemParamsV1.model_validate({**base, **bad})


def test_zero_radius_is_typed_rejection_not_degenerate_solid() -> None:
    """Honest degradation (parity §3): a zero-radius (zero-gap) closed hem is a typed
    ValidationError at the schema, never admitted as a degenerate fold."""
    with pytest.raises(ValidationError):
        SheetMetalHemParamsV1.model_validate(
            {"edge": _edge_ref(uuid.uuid4()), "length_mm": 15.0, "bend_radius_mm": 0.0}
        )


def test_feature_validates_and_is_registered() -> None:
    feature = cast(
        FeatureEnvelope,
        TypeAdapter(Feature).validate_python(
            {
                "type": "sheet_metal_hem",
                "version": 1,
                "params": {"edge": _edge_ref(uuid.uuid4()), "length_mm": 15.0},
            }
        ),
    )
    assert isinstance(feature, SheetMetalHemFeature)
    assert FEATURE_REGISTRY.current_version("sheet_metal_hem") == 1
    assert "sheet_metal_hem" in BODY_AFFECTING_FEATURE_TYPES


def test_reference_map_yields_edge_slot_on_base_flange() -> None:
    """Its single reference is the edge → any body-affecting feature (the base)."""
    base_id = uuid.uuid4()
    feature = SheetMetalHemFeature.model_validate(
        {
            "type": "sheet_metal_hem",
            "version": 1,
            "params": {"edge": _edge_ref(base_id), "length_mm": 15.0},
        }
    )
    refs = feature_references(feature)
    assert len(refs) == 1
    assert refs[0].slot == "edge"
    assert refs[0].ref.feature_id == base_id
    assert "sheet_metal_base_flange" in refs[0].allowed_types


# --------------------------------------------------------------------------- #
# Evaluation unit tests                                                       #
# --------------------------------------------------------------------------- #

_SK = uuid.UUID("00000000-0000-0000-0000-0000000070a0")
_BF = uuid.UUID("00000000-0000-0000-0000-0000000070b0")
_HM = uuid.UUID("00000000-0000-0000-0000-0000000070c0")


def _rect(length: float, width: float) -> dict[str, object]:
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "id": "e1",
                    "kind": "line",
                    "start": {"x": 0.0, "y": 0.0},
                    "end": {"x": length, "y": 0.0},
                },
                {
                    "id": "e2",
                    "kind": "line",
                    "start": {"x": length, "y": 0.0},
                    "end": {"x": length, "y": width},
                },
                {
                    "id": "e3",
                    "kind": "line",
                    "start": {"x": length, "y": width},
                    "end": {"x": 0.0, "y": width},
                },
                {
                    "id": "e4",
                    "kind": "line",
                    "start": {"x": 0.0, "y": width},
                    "end": {"x": 0.0, "y": 0.0},
                },
            ],
            "constraints": [],
        },
    }


def _base_flange() -> dict[str, object]:
    return {
        "type": "sheet_metal_base_flange",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": str(_SK)},
            "thickness_mm": 2.0,
            "bend_radius_mm": 3.0,
        },
    }


def _top_edge_sig(x: float, width: float, thickness: float) -> dict[str, object]:
    return {
        "curve": "line",
        "end_a": {"x": x, "y": 0.0, "z": thickness},
        "end_b": {"x": x, "y": width, "z": thickness},
        "midpoint": {"x": x, "y": width / 2.0, "z": thickness},
        "length_mm": width,
    }


def _hem(edge_sig: dict[str, object], **overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "edge": {
            "kind": "subshape",
            "feature_id": str(_BF),
            "subshape_type": "edge",
            "selector": {"selector_version": 1, "signature": edge_sig},
        },
        "length_mm": 15.0,
    }
    params.update(overrides)
    return {"type": "sheet_metal_hem", "version": 1, "params": params}


def _tree(*features: tuple[uuid.UUID, dict[str, object]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [{"id": str(fid), "feature": feat} for fid, feat in features],
        }
    )


def test_hem_folds_and_records_180deg_provenance() -> None:
    """A base flange + hem evaluates ok, fuses to one body, and records the bend
    provenance (§5) with the inherited K-factor and the overridden hem radius."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0), bend_radius_mm=1.0)),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    assert len(evaluation.bend_provenance) == 1
    prov = evaluation.bend_provenance[0]
    assert prov.k_factor == 0.44  # inherited from the base flange default
    assert prov.cyl_signature.radius_mm == pytest.approx(1.0, abs=1e-6)
    assert prov.base_face_signature.area_mm2 == pytest.approx(1000.0, abs=1e-6)


def test_hem_inherits_base_radius_when_omitted() -> None:
    """Omitting bend_radius_mm inherits the part's base-flange default (3.0)."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0))),  # no radius override
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    prov = evaluation.bend_provenance[0]
    assert prov.cyl_signature.radius_mm == pytest.approx(3.0, abs=1e-6)


def test_hem_without_base_flange_is_honest_error() -> None:
    """A hem with no prior body is a pinned per-feature error, not a crash."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0))),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "error"]
    err = evaluation.result.features[1].error
    assert err is not None and err.code == "no_prior_body"


def test_hem_unresolvable_edge_is_subshape_unresolved() -> None:
    """A hem edge signature that matches no current edge is subshape_unresolved (§5)."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, _hem(_top_edge_sig(999.0, 20.0, 2.0))),  # no such edge
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "subshape_unresolved"


def test_hem_kernel_failure_maps_to_typed_edge_flange_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honest degradation (parity §3): if the kernel fold fails, the hem returns a
    TYPED ``edge_flange_failed``, never a raw exception or an invalid solid. Proven by
    forcing :func:`build_edge_flange` (in the evaluate module) to raise its own
    EdgeFlangeError — the closed-hem geometry itself is robust (a valid solid down to
    r=1e-6), so this exercises the error-MAPPING contract the guard exists for."""
    from geometry.features import evaluate as ev_mod
    from geometry.sheet_metal import EdgeFlangeError

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise EdgeFlangeError("forced kernel fold failure (test)")

    monkeypatch.setattr(ev_mod, "build_edge_flange", _boom)
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0), bend_radius_mm=1.0)),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "edge_flange_failed"
