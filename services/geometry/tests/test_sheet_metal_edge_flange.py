"""Sheet-metal EDGE FLANGE (bend) — slice #3 gate (docs/design/sheet-metal.md §4.2).

Wires the proven unfold (Spike 0) to REAL user-authored geometry: a base flange +
N edge flanges, each bend tagged with a ``CylindricalFaceSignature`` (§5) at
construction and found back BY PROVENANCE (never blind detection).

Three halves:

* **Provenance flat-pattern goldens** — the authored L-bracket
  (``l-bracket-edge-flange``, N=1) and U-channel (``u-channel-edge-flange``, N=2,
  the depth-1-star §4.3 case) rebuild from a real feature tree, are unfolded via
  :func:`geometry.sheet_metal.unfold_sheet_metal`, and asserted against
  HAND-DERIVED analytic flat length / area / bend allowance (§9 #1/#2), plus the
  fused body's volume + topology, plus byte-determinism (in-process + a fresh
  interpreter restart, §9 #4).
* **Schema + evaluation unit tests** — that ``SheetMetalEdgeFlangeParamsV1`` lands
  the intended shape (inherited radius/K default ``None``), is registered +
  reference-mapped, and that the evaluator folds the flange, inherits the base
  defaults, and records the bend provenance.
* **Honest degradation** — a bend whose signature no longer resolves is a typed
  ``subshape_unresolved``, never a wrong flat pattern (§5).

Does NOT touch ``tests/test_sheet_metal.py`` (Spike 0) or the shared ``goldens/``.
"""

import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.kernel.faces import SubshapeUnresolvedError
from geometry.sheet_metal import (
    FlatPattern,
    SheetMetalDefaults,
    unfold_sheet_metal,
)
from py_kit.schemas.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    EvaluateTreeRequest,
    Feature,
    FeatureEnvelope,
    SheetMetalEdgeFlangeFeature,
    SheetMetalEdgeFlangeParamsV1,
    feature_references,
)
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"


# --------------------------------------------------------------------------- #
# Provenance flat-pattern goldens                                             #
# --------------------------------------------------------------------------- #


class _ExpectedEdgeFlange(BaseModel):
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
    model.parent for model in _GOLDENS_DIR.glob("*-edge-flange/model.json")
)
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_edge_flange_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no *-edge-flange goldens under {_GOLDENS_DIR}"


def _load(golden_dir: Path) -> tuple[EvaluateTreeRequest, _ExpectedEdgeFlange]:
    request = EvaluateTreeRequest.model_validate_json(
        (golden_dir / "model.json").read_text("utf-8")
    )
    expected = _ExpectedEdgeFlange.model_validate_json(
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
    """The authored body unfolds to the HAND-DERIVED analytic flat pattern (§9)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance

    # Hand derivation, recomputed here — a third source independent of the golden
    # AND the kernel (geometry-gates skill).
    ba = (math.pi / 2.0) * (expected.bend_radius_mm + 0.44 * 2.0)
    assert ba == pytest.approx(expected.bend_allowance_mm, abs=tol)

    assert pattern.flat_length_mm == pytest.approx(expected.flat_length_mm, abs=tol)
    assert pattern.flat_area_mm2 == pytest.approx(expected.flat_area_mm2, abs=tol)
    assert pattern.bend_width_mm == pytest.approx(expected.bend_width_mm, abs=tol)

    assert len(pattern.bends) == expected.bend_count
    for bend in pattern.bends:
        assert bend.angle_deg == pytest.approx(expected.bend_angle_deg, abs=tol)
        assert bend.radius_mm == pytest.approx(expected.bend_radius_mm, abs=tol)
        assert bend.allowance_mm == pytest.approx(ba, abs=tol)
        assert bend.direction == expected.bend_direction
        assert bend.k_factor == pytest.approx(0.44, abs=tol)


@each_golden
def test_unfold_area_conservation_sum_of_parts(golden_dir: Path) -> None:
    """§9 #2: flat_area = base_area + SUM(flange_area) + SUM(BA*width), the shared
    base counted ONCE — reconstructed from the pattern's own reported pieces."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance
    width = pattern.bend_width_mm
    strip_total = sum(b.allowance_mm * b.width_mm for b in pattern.bends)
    # For these full-width goldens the blank is a rectangle, so the whole area
    # equals flat_length * width — a strong closed check on the sum-of-parts.
    rect_area = pattern.flat_length_mm * width
    assert pattern.flat_area_mm2 == pytest.approx(rect_area, abs=tol)
    assert strip_total == pytest.approx(
        expected.bend_count * expected.bend_allowance_mm * width, abs=tol
    )


@each_golden
def test_fused_body_volume_and_topology(golden_dir: Path) -> None:
    """The authored sheet body has the analytic volume + exact topology counts."""
    request, expected = _load(golden_dir)
    evaluation, _ = _unfold(request)
    props = evaluation.result.properties
    assert props is not None
    assert props.volume == pytest.approx(
        expected.volume_mm3, abs=expected.volume_tolerance
    )
    assert props.topology.model_dump() == expected.topology


@each_golden
def test_outline_is_rectangle_with_one_bend_line_per_bend(golden_dir: Path) -> None:
    """The developed blank is a rectangle (4 body edges) + one fold line per bend."""
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
    """The serialized provenance FlatPattern matches the committed determinism pin.

    A change without an OCCT/build123d bump is a determinism regression (P0)."""
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
    assert remote_hash == pattern.content_hash()  # type: ignore[attr-defined]
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


def test_radius_and_k_inherit_when_omitted() -> None:
    """bend_radius_mm / k_factor default to None (inherit the base defaults, §4.2)."""
    params = SheetMetalEdgeFlangeParamsV1.model_validate(
        {
            "edge": _edge_ref(uuid.uuid4()),
            "flange_length_mm": 30.0,
            "bend_angle_deg": 90.0,
        }
    )
    assert params.bend_radius_mm is None
    assert params.k_factor is None


def test_positive_and_bounded_params() -> None:
    """flange_length > 0, bend_angle in (0, 180], overriding radius > 0, K in [0,1]."""
    base = {
        "edge": _edge_ref(uuid.uuid4()),
        "flange_length_mm": 30.0,
        "bend_angle_deg": 90.0,
    }
    for bad in (
        {"flange_length_mm": 0.0},
        {"bend_angle_deg": 0.0},
        {"bend_angle_deg": 181.0},
        {"bend_radius_mm": 0.0},
        {"k_factor": -0.1},
        {"k_factor": 1.1},
    ):
        with pytest.raises(ValidationError):
            SheetMetalEdgeFlangeParamsV1.model_validate({**base, **bad})


def test_feature_validates_and_is_registered() -> None:
    feature = cast(
        FeatureEnvelope,
        TypeAdapter(Feature).validate_python(
            {
                "type": "sheet_metal_edge_flange",
                "version": 1,
                "params": {
                    "edge": _edge_ref(uuid.uuid4()),
                    "flange_length_mm": 30.0,
                    "bend_angle_deg": 90.0,
                },
            }
        ),
    )
    assert isinstance(feature, SheetMetalEdgeFlangeFeature)
    assert FEATURE_REGISTRY.current_version("sheet_metal_edge_flange") == 1
    assert "sheet_metal_edge_flange" in BODY_AFFECTING_FEATURE_TYPES


def test_reference_map_yields_edge_slot_on_base_flange() -> None:
    """Its single reference is the edge → any body-affecting feature (the base)."""
    base_id = uuid.uuid4()
    feature = SheetMetalEdgeFlangeFeature.model_validate(
        {
            "type": "sheet_metal_edge_flange",
            "version": 1,
            "params": {
                "edge": _edge_ref(base_id),
                "flange_length_mm": 30.0,
                "bend_angle_deg": 90.0,
            },
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

_SK = uuid.UUID("00000000-0000-0000-0000-0000000060a0")
_BF = uuid.UUID("00000000-0000-0000-0000-0000000060b0")
_EF = uuid.UUID("00000000-0000-0000-0000-0000000060c0")


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


def _edge_flange(edge_sig: dict[str, object], **overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "edge": {
            "kind": "subshape",
            "feature_id": str(_BF),
            "subshape_type": "edge",
            "selector": {"selector_version": 1, "signature": edge_sig},
        },
        "flange_length_mm": 30.0,
        "bend_angle_deg": 90.0,
    }
    params.update(overrides)
    return {"type": "sheet_metal_edge_flange", "version": 1, "params": params}


def _tree(*features: tuple[uuid.UUID, dict[str, object]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [{"id": str(fid), "feature": feat} for fid, feat in features],
        }
    )


def test_edge_flange_folds_and_records_provenance() -> None:
    """A base flange + edge flange evaluates ok, fuses to one body, and records
    the bend provenance (§5) with the inherited K-factor."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_EF, _edge_flange(_top_edge_sig(50.0, 20.0, 2.0))),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    assert len(evaluation.bend_provenance) == 1
    prov = evaluation.bend_provenance[0]
    assert prov.k_factor == 0.44  # inherited from the base flange default
    assert prov.cyl_signature.radius_mm == pytest.approx(3.0, abs=1e-6)
    assert prov.base_face_signature.area_mm2 == pytest.approx(1000.0, abs=1e-6)


def test_edge_flange_overrides_radius_and_k() -> None:
    """Per-bend radius / K override the inherited base defaults (§4.2)."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (
            _EF,
            _edge_flange(
                _top_edge_sig(50.0, 20.0, 2.0), bend_radius_mm=4.0, k_factor=0.5
            ),
        ),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    prov = evaluation.bend_provenance[0]
    assert prov.k_factor == 0.5
    assert prov.cyl_signature.radius_mm == pytest.approx(4.0, abs=1e-6)


def test_edge_flange_without_base_flange_is_honest_error() -> None:
    """An edge flange with no prior body is a pinned per-feature error, not a crash."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_EF, _edge_flange(_top_edge_sig(50.0, 20.0, 2.0))),
    )
    evaluation = evaluate_tree(request)
    statuses = [f.status for f in evaluation.result.features]
    assert statuses == ["ok", "error"]
    err = evaluation.result.features[1].error
    assert err is not None and err.code == "no_prior_body"


def test_edge_flange_unresolvable_edge_is_subshape_unresolved() -> None:
    """An edge signature that matches no current edge is subshape_unresolved (§5)."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_EF, _edge_flange(_top_edge_sig(999.0, 20.0, 2.0))),  # no such edge
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "subshape_unresolved"


def test_bend_provenance_degrades_when_bend_face_removed() -> None:
    """§5 honest degradation: if the tagged bend face is gone, the unfold raises a
    typed subshape_unresolved — never a silently wrong flat pattern."""
    from build123d import Box
    from geometry.kernel.edges import enumerate_edges
    from geometry.sheet_metal import BendProvenance, build_edge_flange

    base = Box(40.0, 20.0, 2.0).translate((20.0, 10.0, 1.0))
    edge = next(
        rec.edge
        for rec in enumerate_edges(base)
        if abs((rec.edge @ 0.0).X - 40.0) < 1e-9
        and abs((rec.edge @ 1.0).X - 40.0) < 1e-9
        and abs((rec.edge @ 0.5).Z - 2.0) < 1e-9
        and rec.signature.curve == "line"
    )
    built = build_edge_flange(base, edge, 30.0, 90.0, 3.0, 2.0)
    prov = BendProvenance(built.cyl_signature, built.base_face_signature, 0.44)
    # Unfolding the ORIGINAL flat base (no bend face) must not resolve the signature.
    with pytest.raises(SubshapeUnresolvedError):
        unfold_sheet_metal(base, [prov], 2.0, 0.44)


def test_defaults_feed_bend_allowance() -> None:
    """Sanity: the stored defaults compute the §1 bend allowance the unfold uses."""
    from geometry.sheet_metal import bend_allowance

    d = SheetMetalDefaults(thickness_mm=2.0, k_factor=0.44, bend_radius_mm=3.0)
    ba = bend_allowance(math.pi / 2.0, d.bend_radius_mm, d.k_factor, d.thickness_mm)
    assert ba == pytest.approx(6.094689747964199, abs=1e-12)


# --------------------------------------------------------------------------- #
# Deferred-scope boundaries — locked with real assertions, not prose (slice #3 #
# code-review debt: the deferred cases were documented but not gated).        #
# --------------------------------------------------------------------------- #


def test_perpendicular_bend_star_is_unfold_star_error() -> None:
    """A depth-1 star whose flanges fold off PERPENDICULAR base edges is outside the
    v1 PARALLEL-star scope (§4.3): the parallel-axis check must raise UnfoldStarError,
    never a silently wrong flat pattern. Authored end-to-end (two real edge flanges
    on perpendicular edges of one plate), so the boundary is gated on real geometry."""
    from build123d import Box
    from geometry.kernel.edges import enumerate_edges
    from geometry.sheet_metal import BendProvenance, build_edge_flange
    from geometry.sheet_metal.unfold import UnfoldStarError

    base = Box(40.0, 40.0, 2.0).translate((20.0, 20.0, 1.0))

    # Bend 1 folds off the x=40 edge (bend axis +Y); bend 2 off the y=40 top edge
    # (bend axis +X) — the two axes are perpendicular (same idiom as the degradation
    # test above, avoiding the untyped-Vector helper).
    edge1 = next(
        rec.edge
        for rec in enumerate_edges(base)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.0).X - 40.0) < 1e-6
        and abs((rec.edge @ 1.0).X - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Z - 2.0) < 1e-6
    )
    r1 = build_edge_flange(base, edge1, 30.0, 90.0, 3.0, 2.0)
    edge2 = next(
        rec.edge
        for rec in enumerate_edges(r1.body)
        if rec.signature.curve == "line"
        and abs((rec.edge @ 0.5).Y - 40.0) < 1e-6
        and abs((rec.edge @ 0.5).Z - 2.0) < 1e-6
        and abs((rec.edge @ 1.0).X - (rec.edge @ 0.0).X) > 1e-3
    )
    r2 = build_edge_flange(r1.body, edge2, 30.0, 90.0, 3.0, 2.0)

    provs = [
        BendProvenance(r1.cyl_signature, r1.base_face_signature, 0.44),
        BendProvenance(r2.cyl_signature, r2.base_face_signature, 0.44),
    ]
    with pytest.raises(UnfoldStarError, match="not parallel"):
        unfold_sheet_metal(r2.body, provs, 2.0, 0.44)


def test_split_base_moving_no_base_match_is_unfold_star_error() -> None:
    """`_split_base_moving`'s no-base-match branch (§4.3): if neither flanking face of
    a bend matches the recorded base-flange signature, the bend is not a depth-1
    flange off the recorded base — an honest UnfoldStarError, never a guess."""
    from build123d import Box
    from geometry.sheet_metal.resolve import FlangeFaceRecord
    from geometry.sheet_metal.unfold import (
        UnfoldStarError,
        _split_base_moving,  # pyright: ignore[reportPrivateUsage]
    )
    from py_kit.schemas.features import PlanarFaceSignature
    from py_kit.schemas.geometry import Vec3

    face = Box(1.0, 1.0, 1.0).faces()[0]  # a real (placeholder) planar Face

    def flange(cx: float) -> FlangeFaceRecord:
        sig = PlanarFaceSignature(
            normal=Vec3(x=0.0, y=0.0, z=1.0),
            centroid=Vec3(x=cx, y=0.0, z=0.0),
            area_mm2=100.0,
        )
        return FlangeFaceRecord(
            face=face,
            signature=sig,
            developed_length_mm=10.0,
            width_mm=10.0,
            area_mm2=100.0,
            normal=(0.0, 0.0, 1.0),
            centroid=(cx, 0.0, 0.0),
        )

    # The recorded base sits at x=500 — neither flange (x=10 / x=20) matches it.
    base_sig = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=500.0, y=0.0, z=0.0),
        area_mm2=100.0,
    )
    with pytest.raises(UnfoldStarError, match="Neither flanking face"):
        _split_base_moving((flange(10.0), flange(20.0)), base_sig)
