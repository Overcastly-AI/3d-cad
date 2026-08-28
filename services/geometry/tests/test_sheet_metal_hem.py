"""Sheet-metal HEM — closed and open (docs/design/sheet-metal-parity.md §2).

A hem folds the picked edge ~180 deg back over the parent face — mechanically a
SPECIALIZATION of the shipped edge flange (a fixed 180-deg fold), so it reuses
:func:`build_edge_flange`'s bend machinery and the shipped
:func:`unfold_sheet_metal` verbatim.

**HEM-1 (2026-08-28) is why the air-gap gate exists.** A ``hem_type="closed"`` hem
inherited the part's GENERAL base-flange bend radius, and the fold's cross-section
makes the layers' air gap exactly ``2 * radius`` — so on 2 mm sheet with a 3 mm part
radius a "closed" hem shipped a **6.00 mm** gap, three gauges of air, while the
feature status read ``ok``, the form read "NEW CLOSED HEM" and the readout read
``Fold 180 deg (closed)``. Every gate in this file passed: they asserted the flat
pattern, the volume, the topology and the determinism hash — all correct — and not
one of them asserted the property the feature's own NAME claims. The golden could
not have caught it either, because it OVERRODE ``bend_radius_mm`` and so never
exercised the default that was wrong. Both halves are fixed here.

This gate proves:

* **The air gap** (:func:`test_hem_air_gap_matches_its_declared_type`) — measured on
  the built solid, parent flat to the face that faces back at it, against a
  documented per-model tolerance AND against the type rule independently.
* **Provenance flat-pattern goldens** — ``closed-hem-plate`` (a plate + one closed
  hem, 2 mm gauge) and ``closed-hem-guard-panel`` (a 300 x 180 mm guard panel with a
  closed hem on both long edges, 1.5 mm gauge — a second gauge, so the
  gauge-proportional radius rule is exercised rather than assumed). Both take the
  DEFAULT radius. Rebuilt from real feature trees, unfolded by PROVENANCE, asserted
  against HAND-DERIVED flat length / area / bend allowance (§9 #1/#2,
  BA = pi*(r + K*t)), plus volume + topology + ONE valid solid/shell, plus
  byte-determinism (in-process + a fresh interpreter restart, §9 #4).
* **The radius rule** — :func:`resolve_hem_bend_radius_mm` at its own seam: derived
  from TYPE and GAUGE, never inherited from the base flange, honoured inside its
  type's range and refused outside it in BOTH directions.
* **Honest degradation (parity §3)** — a ZERO-radius hem is a typed schema
  rejection; a radius contradicting the declared type is ``hem_type_radius_conflict``;
  a sub-tolerance gap is ``hem_gap_degenerate``; a kernel fold failure maps to a
  typed ``edge_flange_failed`` (never a raw exception or an invalid solid); an
  unresolvable edge is ``subshape_unresolved``; a hem with no prior body is
  ``no_prior_body``.
"""

import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest
from build123d import CenterOf, GeomType, Vector
from geometry.features.evaluate import TreeEvaluation, evaluate_tree
from geometry.sheet_metal import (
    FlatPattern,
    unfold_sheet_metal,
)
from py_kit.schemas.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    HEM_CLOSED_MAX_RADIUS_RATIO,
    HEM_CLOSED_RADIUS_RATIO,
    HEM_OPEN_RADIUS_RATIO,
    EvaluateTreeRequest,
    Feature,
    FeatureEnvelope,
    HemRadiusError,
    SheetMetalHemFeature,
    SheetMetalHemParamsV1,
    feature_references,
    resolve_hem_bend_radius_mm,
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
    thickness_mm: float = Field(gt=0)
    hem_type: str
    bend_allowance_mm: float
    flat_length_mm: float
    flat_area_mm2: float
    bend_width_mm: float
    bend_count: int
    bend_angle_deg: float
    bend_radius_mm: float
    bend_direction: str
    # HEM-1: the air gap between the folded return and the parent face — the
    # property the hem's own NAME asserts, and the one every other field in this
    # file was blind to. Measured on the built solid, not derived from the params.
    air_gap_mm: float
    air_gap_tolerance: float = Field(gt=0)
    air_gap_rationale: str
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


def _hem_air_gaps_mm(evaluation: TreeEvaluation) -> list[float]:
    """Measure each hem's AIR GAP on the built solid: parent face -> return face.

    HEM-1's gate. The hem's name is a claim about CONTACT, so the assertion has to
    be a distance between two faces of the finished body — not the radius that was
    requested, not the feature's status, not the readout. Every one of those was
    correct while the geometry was wrong: a "closed" hem on 2 mm sheet shipped a
    6.00 mm gap with ``status: ok`` and a label reading ``Fold 180 deg (closed)``.
    (CLAUDE.md's standing lesson: when a gate proves a property, assert with that
    property's own mechanism, never a proxy that skips the step being claimed.)

    Provenance-driven, so it needs no knowledge of the part's orientation: each
    bend's ``base_face_signature`` gives the PARENT plane (centroid + outward
    normal ``n``), and a fold-back's facing skin is a planar face whose outward
    normal is ``-n`` at a POSITIVE offset along ``n`` from that plane. The parent's
    own opposite skin sits at ``-thickness`` and is excluded by the sign.

    **Returns EVERY such face's offset, not the nearest one.** The obvious version
    of this helper takes ``min(...)`` per bend, and on a part with two hems that
    would report the good hem's gap twice — so one hem opening up would sail past
    a green gate. That is the "assertion that cannot observe the failure mode"
    family CLAUDE.md keeps naming, and it is the whole reason this file needed a
    new gate in the first place. The caller therefore asserts the COUNT against
    ``bend_count`` and the VALUE on every element.

    Scope: the ``closed-hem-*`` goldens' only fold-backs are hems, so every facing
    face here belongs to a hem return. A future golden that folds a flange past
    90 deg would need this narrowed to each bend's own span.
    """
    body = evaluation.body
    assert body is not None
    planes = [
        (f.normal_at(f.center(CenterOf.MASS)), f.center(CenterOf.MASS))
        for f in body.faces()
        if f.geom_type == GeomType.PLANE
    ]
    gaps: list[float] = []
    seen: list[tuple[float, float, float, float]] = []
    for prov in evaluation.bend_provenance:
        sig = prov.base_face_signature
        n = Vector(sig.normal.x, sig.normal.y, sig.normal.z)
        origin = Vector(sig.centroid.x, sig.centroid.y, sig.centroid.z)
        # Two hems folding off the SAME flat share a parent plane; count it once
        # so the returned list is one entry per facing FACE, not per (bend, face).
        key = (n.X, n.Y, n.Z, origin.dot(n))
        if key in seen:
            continue
        seen.append(key)
        facing = [
            (c - origin).dot(n)
            for fn, c in planes
            if abs(fn.dot(n) + 1.0) < 1e-9 and (c - origin).dot(n) > 1e-12
        ]
        assert facing, "no face of the body faces back at the hem's parent flat"
        gaps.extend(facing)
    return sorted(gaps)


@each_golden
def test_hem_air_gap_matches_its_declared_type(golden_dir: Path) -> None:
    """HEM-1 — the built solid's air gap is what the hem's TYPE says it is.

    A ``closed`` hem is pressed flat against the parent, so its layers must very
    nearly touch; an ``open`` hem leaves a deliberate opening. The number lives in
    the golden (``air_gap_mm`` + its documented tolerance, never an ad-hoc epsilon)
    and is cross-checked here against the RULE — ``0.1 x gauge`` closed,
    ``1 x gauge`` open, when the model does not override the radius — so the
    golden and the rule are two independent statements of the same fact rather
    than one statement verified against itself.
    """
    request, expected = _load(golden_dir)
    evaluation, _ = _unfold(request)
    gaps = _hem_air_gaps_mm(evaluation)
    assert len(gaps) == expected.bend_count

    for gap in gaps:
        assert gap == pytest.approx(expected.air_gap_mm, abs=expected.air_gap_tolerance)
        # The fold's cross-section makes the gap exactly twice the inner radius —
        # the identity that turns "which radius?" into "how much air?".
        assert gap == pytest.approx(
            2.0 * expected.bend_radius_mm, abs=expected.air_gap_tolerance
        )

    if expected.hem_type == "closed":
        # Independent of the golden's own numbers: a closed hem's gap is a small
        # fraction of GAUGE (0.1 t by the rule), never a multiple of it. The
        # shipped defect was 3.0 x gauge, so this bound alone would have caught it.
        assert expected.air_gap_mm == pytest.approx(
            HEM_CLOSED_RADIUS_RATIO * 2.0 * expected.thickness_mm,
            abs=expected.air_gap_tolerance,
        )
        assert max(gaps) < 0.25 * expected.thickness_mm
    else:
        assert expected.hem_type == "open"
        assert min(gaps) >= 0.25 * expected.thickness_mm


@each_golden
def test_unfold_matches_hand_derivation(golden_dir: Path) -> None:
    """The authored hemmed body unfolds to the HAND-DERIVED flat pattern (§9)."""
    request, expected = _load(golden_dir)
    _, pattern = _unfold(request)
    tol = expected.tolerance

    # Hand derivation, recomputed here — a third source independent of the golden
    # AND the kernel (geometry-gates skill). A hem is a 180-deg fold.
    ba = math.pi * (expected.bend_radius_mm + 0.44 * expected.thickness_mm)
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
    """length > 0, overriding radius > 0, K in [0,1], and only buildable hem types."""
    base = {"edge": _edge_ref(uuid.uuid4()), "length_mm": 15.0}
    for bad in (
        {"length_mm": 0.0},
        {"bend_radius_mm": 0.0},  # zero-radius / zero-gap degenerate hem (parity §3)
        {"bend_radius_mm": -1.0},
        {"k_factor": -0.1},
        {"k_factor": 1.1},
        # Teardrop and rolled hems wrap PAST 180 deg, which this fold cannot build.
        # They are absent from the Literal ON PURPOSE (HEM-1): naming a shape we
        # cannot honour is exactly the label-vs-geometry defect this rule removes.
        {"hem_type": "teardrop"},
        {"hem_type": "rolled"},
    ):
        with pytest.raises(ValidationError):
            SheetMetalHemParamsV1.model_validate({**base, **bad})
    # 'open' IS buildable — the same 180 deg fold at a gap of one gauge.
    assert (
        SheetMetalHemParamsV1.model_validate({**base, "hem_type": "open"}).hem_type
        == "open"
    )


def test_hem_radius_rule_is_type_and_gauge_driven() -> None:
    """HEM-1's rule, unit-tested at its own seam (:func:`resolve_hem_bend_radius_mm`).

    The radius is a function of hem TYPE and GAUGE. An explicit value is honoured
    inside its type's range and REFUSED outside it — never silently ignored (the
    ``extra="ignore"`` defect class) and never silently clamped (the same lie in
    the other direction).
    """
    for t in (0.8, 1.5, 2.0, 3.0):
        assert resolve_hem_bend_radius_mm("closed", t) == HEM_CLOSED_RADIUS_RATIO * t
        assert resolve_hem_bend_radius_mm("open", t) == HEM_OPEN_RADIUS_RATIO * t
        boundary = HEM_CLOSED_MAX_RADIUS_RATIO * t
        # The boundary belongs to BOTH ranges, so the two partition the line with
        # no gap and no overlap.
        assert resolve_hem_bend_radius_mm("closed", t, boundary) == boundary
        assert resolve_hem_bend_radius_mm("open", t, boundary) == boundary
        # In-range overrides are honoured verbatim.
        assert resolve_hem_bend_radius_mm("closed", t, boundary / 2.0) == boundary / 2.0
        assert resolve_hem_bend_radius_mm("open", t, 2.0 * boundary) == 2.0 * boundary
        # SYMMETRIC refusal. CLAUDE.md's own lesson from the staging tool: a guard
        # written against one failure tends to encode that failure's DIRECTION, so
        # both mislabellings are refused, not just the one HEM-1 reported.
        with pytest.raises(HemRadiusError, match="OPEN hem"):
            resolve_hem_bend_radius_mm("closed", t, boundary * 1.001)
        with pytest.raises(HemRadiusError, match="CLOSED hem"):
            resolve_hem_bend_radius_mm("open", t, boundary * 0.999)


def test_hem_radius_rule_refuses_the_shipped_defect_verbatim() -> None:
    """The exact HEM-1 payload — a "closed" hem inheriting a 3 mm part radius on
    2 mm sheet — is refused, and the message names the fix rather than a number."""
    with pytest.raises(HemRadiusError) as exc:
        resolve_hem_bend_radius_mm("closed", 2.0, 3.0)
    text = str(exc.value)
    assert "6 mm air gap" in text
    assert "hem_type='open'" in text


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
        (
            _HM,
            _hem(
                _top_edge_sig(50.0, 20.0, 2.0),
                hem_type="open",
                bend_radius_mm=1.0,
            ),
        ),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
    assert len(evaluation.bend_provenance) == 1
    prov = evaluation.bend_provenance[0]
    assert prov.k_factor == 0.44  # inherited from the base flange default
    assert prov.cyl_signature.radius_mm == pytest.approx(1.0, abs=1e-6)
    assert prov.base_face_signature.area_mm2 == pytest.approx(1000.0, abs=1e-6)


def test_hem_radius_comes_from_type_and_gauge_not_the_base_flange() -> None:
    """HEM-1 REGRESSION. This test replaces ``test_hem_inherits_base_radius_when_
    omitted``, which asserted — and so PROTECTED — the defect: omitting
    ``bend_radius_mm`` used to inherit the part's general 3.0 mm die-bend radius,
    putting a 6.00 mm air gap (3 gauges) inside a hem labelled "closed".

    The base flange here still carries ``bend_radius_mm = 3.0``, so the assertion
    is specifically that the hem does NOT reach for it.
    """
    for hem_type, ratio in (
        ("closed", HEM_CLOSED_RADIUS_RATIO),
        ("open", HEM_OPEN_RADIUS_RATIO),
    ):
        request = _tree(
            (_SK, _rect(50.0, 20.0)),
            (_BF, _base_flange()),  # part default bend_radius_mm = 3.0
            (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0), hem_type=hem_type)),
        )
        evaluation = evaluate_tree(request)
        assert [f.status for f in evaluation.result.features] == ["ok", "ok", "ok"]
        prov = evaluation.bend_provenance[0]
        assert prov.cyl_signature.radius_mm == pytest.approx(ratio * 2.0, abs=1e-6)
        assert prov.cyl_signature.radius_mm != pytest.approx(3.0, abs=1e-6)
        # K IS still inherited: it is a material property, not a fold dimension.
        assert prov.k_factor == 0.44


def test_hem_type_radius_conflict_is_a_typed_refusal_not_a_mislabelled_body() -> None:
    """HEM-1: an explicit radius that describes the OTHER hem type is refused.

    Silently ignoring it would be the ``extra="ignore"`` class (a field that reads
    as accepted and does nothing); silently clamping it would build geometry the
    user did not ask for. Refusing is the only outcome under which the label, the
    number and the solid cannot disagree — and the message names the fix.
    """
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0), bend_radius_mm=3.0)),  # closed
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "hem_type_radius_conflict"
    assert "hem_type='open'" in err.message
    # Refused, so no mislabelled body reached the caller: the last good body is
    # the plain plate (50 x 20 x 2), not a plate with a 6 mm-gapped "closed" hem.
    assert evaluation.body is not None
    assert float(evaluation.body.volume) == pytest.approx(2000.0, abs=1e-6)


def test_open_hem_with_a_closed_hem_radius_is_refused_too() -> None:
    """The SYMMETRIC refusal. CLAUDE.md's staging-tool lesson: a guard written
    against one failure tends to encode that failure's direction, so the mirror
    mislabelling (an "open" hem whose layers are effectively touching) is refused
    by the same rule rather than sailing past it."""
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (
            _HM,
            _hem(
                _top_edge_sig(50.0, 20.0, 2.0),
                hem_type="open",
                bend_radius_mm=0.05,
            ),
        ),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "hem_type_radius_conflict"
    assert "hem_type='closed'" in err.message


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
        (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0))),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "edge_flange_failed"


def test_hem_sub_tolerance_gap_is_refused_before_the_kernel_is_asked() -> None:
    """Honest degradation (parity §3) on a REAL degenerate fold — NOT monkeypatched.

    An authorable sub-gauge radius (the schema only enforces ``gt=0``) folds the
    return to within less than this kernel's 1e-4 mm linear tolerance of the parent
    — the two layers are the SAME PLACE, i.e. a zero-width slit RESEARCH §9 refuses
    rather than heals. Before HEM-1 this shipped: at ``r = 1e-6`` the hem reported
    ``ok`` and handed back a BRepCheck-VALID solid that
    ``find_zero_width_slits`` called degenerate (300 mm^2 of coincident face — the
    limit ``test_degenerate.py`` used to record and now asserts as this guard).

    ``hem_gap_degenerate`` is arithmetic on the resolved radius, so it fires before
    the kernel spends a fuse on a body that must be thrown away.
    """
    for radius in (1e-9, 1e-6, 4.9e-5):  # gap 2e-9 .. 9.8e-5, all under 1e-4
        request = _tree(
            (_SK, _rect(50.0, 20.0)),
            (_BF, _base_flange()),
            (_HM, _hem(_top_edge_sig(50.0, 20.0, 2.0), bend_radius_mm=radius)),
        )
        evaluation = evaluate_tree(request)
        assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
        err = evaluation.result.features[2].error
        assert err is not None and err.code == "hem_gap_degenerate", (radius, err)


def test_edge_flange_degenerate_radius_still_degrades_typed_not_generic() -> None:
    """The provenance-mapping regression the tiny-radius HEM case used to carry.

    A sub-gauge radius fuses into one solid yet leaves no findable bend arc, so
    ``find_cylindrical_face`` raises ``NoBendFoundError``; the guard in
    ``edge_flange.py`` maps it to a TYPED ``edge_flange_failed``, never the generic
    ``evaluation_failed`` / "Unexpected NoBendFoundError" bucket. Regression for the
    code-review 🟡 on 35e11f1 (the try/except used to END before the bend-face
    resolution, so this real path escaped unwrapped).

    It moved from the hem to the EDGE FLANGE because HEM-1's ``hem_gap_degenerate``
    now refuses a sub-tolerance hem earlier, which would have quietly retired this
    coverage — the same defect class as an assertion that stops being able to
    observe its subject.
    """
    flange: dict[str, object] = {
        "type": "sheet_metal_edge_flange",
        "version": 1,
        "params": {
            "edge": {
                "kind": "subshape",
                "feature_id": str(_BF),
                "subshape_type": "edge",
                "selector": {
                    "selector_version": 1,
                    "signature": _top_edge_sig(50.0, 20.0, 2.0),
                },
            },
            "flange_length_mm": 15.0,
            "bend_angle_deg": 90.0,
            "bend_radius_mm": 1e-9,
        },
    }
    request = _tree(
        (_SK, _rect(50.0, 20.0)),
        (_BF, _base_flange()),
        (_HM, flange),
    )
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok", "error"]
    err = evaluation.result.features[2].error
    assert err is not None and err.code == "edge_flange_failed"
