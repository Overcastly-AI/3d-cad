"""Sheet-metal BASE FLANGE feature — slice #1 gate (docs/design/sheet-metal.md §4.1).

Two halves:

* **Golden gate** — every ``goldens-sheet-metal/base-flange-*/`` model rebuilds
  through the SAME :func:`geometry.harness.evaluate_model` dispatch the REST
  routes / worker share, asserting mass properties within the golden's
  documented per-model tolerance, exact topology + mesh counts, and byte-level
  determinism (in-process + a fresh-interpreter restart) — the RESEARCH §9
  posture the shared ``goldens/`` harness uses, scoped here to the sheet-metal
  golden dir (its own harness, NOT the shared ``goldens/`` tree — brief).
* **Schema + evaluation unit tests** — that ``SheetMetalBaseFlangeParamsV1``
  lands the intended shape (K-factor default 0.44, required gauge/bend-radius),
  is registered + reference-mapped like every other body-creating feature, and
  that the evaluator thickens the profile to gauge AND records the part's
  sheet-metal defaults on the body for the edge-flange / unfold slices (§5).

Does NOT touch ``tests/test_sheet_metal.py`` (Spike 0) or any shared golden.
"""

import hashlib
import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest
from geometry.features.evaluate import (
    EvaluationState,
    _evaluate_sheet_metal_base_flange,  # pyright: ignore[reportPrivateUsage]
    _evaluate_sketch,  # pyright: ignore[reportPrivateUsage]
    evaluate_tree,
)
from geometry.harness import evaluate_model, load_model_request
from geometry.schemas import BoundingBox, TopologyCounts, Vec3
from geometry.sheet_metal import SheetMetalDefaults
from py_kit.schemas.features import (
    BASE_BODY_AFFECTING_FEATURE_TYPES,
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    SHEET_METAL_DEFAULT_K_FACTOR,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    Feature,
    FeatureEnvelope,
    SheetMetalBaseFlangeFeature,
    SheetMetalBaseFlangeParamsV1,
    feature_references,
)
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"


# --------------------------------------------------------------------------- #
# Golden gate                                                                  #
# --------------------------------------------------------------------------- #


class _ExpectedMassProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volume: float = Field(gt=0)
    surface_area: float = Field(gt=0)
    centroid: Vec3
    bounding_box: BoundingBox


class _ExpectedMesh(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vertices: int = Field(ge=3)
    triangles: int = Field(ge=1)


class _GoldenExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    properties: _ExpectedMassProperties
    topology: TopologyCounts
    mesh: _ExpectedMesh


def _base_flange_golden_dirs() -> list[Path]:
    return sorted(
        model.parent for model in _GOLDENS_DIR.glob("base-flange-*/model.json")
    )


_GOLDEN_DIRS = _base_flange_golden_dirs()
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_base_flange_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no base-flange goldens under {_GOLDENS_DIR}"


@each_golden
def test_base_flange_mass_properties_and_topology(golden_dir: Path) -> None:
    """Volume = profile_area x gauge, exact planar mass props + topology/mesh."""
    request = load_model_request((golden_dir / "model.json").read_text("utf-8"))
    expected = _GoldenExpectation.model_validate_json(
        (golden_dir / "expected.json").read_text("utf-8")
    )
    glb, metadata = evaluate_model(request)
    props = metadata.properties
    tol = expected.tolerance

    ep = expected.properties
    bb, ebb = props.bounding_box, ep.bounding_box
    checks: list[tuple[str, float, float]] = [
        ("volume", props.volume, ep.volume),
        ("surface_area", props.surface_area, ep.surface_area),
        ("centroid.x", props.centroid.x, ep.centroid.x),
        ("centroid.y", props.centroid.y, ep.centroid.y),
        ("centroid.z", props.centroid.z, ep.centroid.z),
        ("bbox.min.x", bb.min.x, ebb.min.x),
        ("bbox.min.y", bb.min.y, ebb.min.y),
        ("bbox.min.z", bb.min.z, ebb.min.z),
        ("bbox.max.x", bb.max.x, ebb.max.x),
        ("bbox.max.y", bb.max.y, ebb.max.y),
        ("bbox.max.z", bb.max.z, ebb.max.z),
    ]
    for label, got, want in checks:
        assert got == pytest.approx(want, abs=tol), (
            f"{golden_dir.name}: {label} expected {want!r}, got {got!r} "
            f"(documented tolerance {tol!r} — never loosen to go green)"
        )

    assert props.topology == expected.topology, golden_dir.name
    assert metadata.mesh.vertices == expected.mesh.vertices, golden_dir.name
    assert metadata.mesh.triangles == expected.mesh.triangles, golden_dir.name
    assert metadata.mesh.glb_bytes == len(glb), golden_dir.name


@each_golden
def test_base_flange_rebuild_is_deterministic_in_process(golden_dir: Path) -> None:
    """Same request twice → identical metadata AND byte-identical GLB (§9)."""
    request = load_model_request((golden_dir / "model.json").read_text("utf-8"))
    glb_a, meta_a = evaluate_model(request)
    glb_b, meta_b = evaluate_model(request)
    assert meta_a == meta_b, f"{golden_dir.name}: metadata differs between rebuilds"
    assert glb_a == glb_b, f"{golden_dir.name}: GLB bytes differ between rebuilds"


_RESTART_PROBE = """\
import hashlib
import sys

from geometry.harness import evaluate_model, load_model_request

glb, metadata = evaluate_model(load_model_request(sys.stdin.read()))
print(hashlib.sha256(glb).hexdigest())
print(metadata.model_dump_json())
"""


@each_golden
def test_base_flange_rebuild_is_deterministic_across_restart(golden_dir: Path) -> None:
    """Fresh-interpreter rebuild reproduces byte-identical GLB + metadata (§9)."""
    request = load_model_request((golden_dir / "model.json").read_text("utf-8"))
    glb, metadata = evaluate_model(request)
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE],
        input=request.model_dump_json(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{golden_dir.name}: restart failed:\n{result.stderr}"
    )
    remote_digest, remote_metadata = result.stdout.splitlines()
    assert remote_digest == hashlib.sha256(glb).hexdigest(), golden_dir.name
    assert remote_metadata == metadata.model_dump_json(), golden_dir.name


# --------------------------------------------------------------------------- #
# Schema unit tests                                                            #
# --------------------------------------------------------------------------- #


def _profile_ref() -> dict[str, object]:
    return {"kind": "feature", "feature_id": str(uuid.uuid4())}


def test_k_factor_defaults_to_v1_baseline() -> None:
    """K-factor is optional and defaults to the pinned v1 0.44 (§1/§9)."""
    params = SheetMetalBaseFlangeParamsV1.model_validate(
        {"profile": _profile_ref(), "thickness_mm": 2.0, "bend_radius_mm": 3.0}
    )
    assert params.k_factor == SHEET_METAL_DEFAULT_K_FACTOR == 0.44
    assert params.direction == "normal"
    assert params.merge is True


def test_bend_radius_is_required() -> None:
    """bend_radius_mm has no universal default — omitting it is a 422."""
    with pytest.raises(ValidationError):
        SheetMetalBaseFlangeParamsV1.model_validate(
            {"profile": _profile_ref(), "thickness_mm": 2.0}
        )


def test_gauge_and_radius_must_be_positive() -> None:
    """Gauge thickness and bend radius are strictly positive."""
    for bad in ({"thickness_mm": 0.0}, {"thickness_mm": -1.0}):
        with pytest.raises(ValidationError):
            SheetMetalBaseFlangeParamsV1.model_validate(
                {"profile": _profile_ref(), "bend_radius_mm": 3.0, **bad}
            )
    with pytest.raises(ValidationError):
        SheetMetalBaseFlangeParamsV1.model_validate(
            {"profile": _profile_ref(), "thickness_mm": 2.0, "bend_radius_mm": 0.0}
        )


def test_k_factor_is_bounded_to_unit_interval() -> None:
    """K ∈ [0, 1] — a fraction of thickness (§1)."""
    for bad_k in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            SheetMetalBaseFlangeParamsV1.model_validate(
                {
                    "profile": _profile_ref(),
                    "thickness_mm": 2.0,
                    "bend_radius_mm": 3.0,
                    "k_factor": bad_k,
                }
            )


def test_feature_validates_and_is_registered() -> None:
    """The envelope validates through the discriminated Feature union and is
    registered at v1 (so documents' generic CRUD stores/loads it)."""
    feature = cast(
        FeatureEnvelope,
        TypeAdapter(Feature).validate_python(
            {
                "type": "sheet_metal_base_flange",
                "version": 1,
                "params": {
                    "profile": _profile_ref(),
                    "thickness_mm": 2.0,
                    "bend_radius_mm": 3.0,
                },
            }
        ),
    )
    assert isinstance(feature, SheetMetalBaseFlangeFeature)
    assert FEATURE_REGISTRY.current_version("sheet_metal_base_flange") == 1


def test_type_sets_classify_base_flange() -> None:
    """A base flange is body-affecting AND a valid boolean operand base."""
    assert "sheet_metal_base_flange" in BODY_AFFECTING_FEATURE_TYPES
    assert "sheet_metal_base_flange" in BASE_BODY_AFFECTING_FEATURE_TYPES


def test_reference_map_yields_profile_sketch_slot() -> None:
    """Its single reference is the profile → sketch slot (like extrude)."""
    profile_id = uuid.uuid4()
    feature = SheetMetalBaseFlangeFeature.model_validate(
        {
            "type": "sheet_metal_base_flange",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "thickness_mm": 2.0,
                "bend_radius_mm": 3.0,
            },
        }
    )
    refs = feature_references(feature)
    assert len(refs) == 1
    assert refs[0].slot == "profile"
    assert refs[0].ref.feature_id == profile_id
    assert refs[0].allowed_types == frozenset({"sketch"})


# --------------------------------------------------------------------------- #
# Evaluation unit tests                                                        #
# --------------------------------------------------------------------------- #

_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000050a0")
_FLANGE_ID = uuid.UUID("00000000-0000-0000-0000-0000000050b0")


def _rect_sketch() -> dict[str, object]:
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
                    "end": {"x": 40.0, "y": 0.0},
                },
                {
                    "id": "e2",
                    "kind": "line",
                    "start": {"x": 40.0, "y": 0.0},
                    "end": {"x": 40.0, "y": 25.0},
                },
                {
                    "id": "e3",
                    "kind": "line",
                    "start": {"x": 40.0, "y": 25.0},
                    "end": {"x": 0.0, "y": 25.0},
                },
                {
                    "id": "e4",
                    "kind": "line",
                    "start": {"x": 0.0, "y": 25.0},
                    "end": {"x": 0.0, "y": 0.0},
                },
            ],
            "constraints": [],
        },
    }


def _flange_feature(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "profile": {"kind": "feature", "feature_id": str(_SKETCH_ID)},
        "thickness_mm": 2.0,
        "bend_radius_mm": 3.0,
    }
    params.update(overrides)
    return {"type": "sheet_metal_base_flange", "version": 1, "params": params}


def _tree(*features: dict[str, object]) -> EvaluateTreeRequest:
    ids = [_SKETCH_ID, _FLANGE_ID]
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [
                {"id": str(fid), "feature": feat}
                for fid, feat in zip(ids, features, strict=True)
            ],
        }
    )


def test_base_flange_evaluates_to_gauge_thickness_solid() -> None:
    """A profile + base flange evaluates ok to volume = area x gauge."""
    request = _tree(_rect_sketch(), _flange_feature())
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok"]
    assert evaluation.result.properties is not None
    assert evaluation.result.properties.volume == pytest.approx(2000.0, abs=1e-9)


def test_base_flange_records_sheet_metal_defaults_on_state() -> None:
    """On success the part's gauge/K/radius are recorded on the body identity
    (its base-feature id) for the edge-flange / unfold slices (§5)."""
    state = EvaluationState(linear_deflection=0.1)
    # Solve the sketch first so the profile resolves.
    sketch_item = EvaluatedFeatureInput.model_validate(
        {"id": str(_SKETCH_ID), "feature": _rect_sketch()}
    )
    assert _evaluate_sketch(sketch_item, state) is None

    flange_item = EvaluatedFeatureInput.model_validate(
        {"id": str(_FLANGE_ID), "feature": _flange_feature()}
    )
    assert _evaluate_sheet_metal_base_flange(flange_item, state) is None

    assert _FLANGE_ID in state.bodies  # a base flange starts the first body
    assert state.sheet_metal_defaults[_FLANGE_ID] == SheetMetalDefaults(
        thickness_mm=2.0, k_factor=0.44, bend_radius_mm=3.0
    )


def test_reverse_direction_thickens_the_other_way() -> None:
    """direction='reverse' thickens along -Z (below the XY sketch plane)."""
    request = _tree(_rect_sketch(), _flange_feature(direction="reverse"))
    evaluation = evaluate_tree(request)
    assert [f.status for f in evaluation.result.features] == ["ok", "ok"]
    props = evaluation.result.properties
    assert props is not None
    assert props.bounding_box.min.z == pytest.approx(-2.0, abs=1e-9)
    assert props.bounding_box.max.z == pytest.approx(0.0, abs=1e-9)


def test_missing_profile_is_reference_unresolved() -> None:
    """A profile that is not an earlier ok sketch is a pinned per-feature error
    (the reused extrude reference rule), never a crash."""
    request = _tree(_rect_sketch(), _flange_feature())
    # Point the flange at a non-existent sketch id.
    request.features[1].feature = SheetMetalBaseFlangeFeature.model_validate(
        _flange_feature(profile={"kind": "feature", "feature_id": str(uuid.uuid4())})
    )
    evaluation = evaluate_tree(request)
    statuses = [f.status for f in evaluation.result.features]
    assert statuses == ["ok", "error"]
    err = evaluation.result.features[1].error
    assert err is not None and err.code == "reference_unresolved"


def test_bend_allowance_uses_stored_defaults() -> None:
    """Sanity that the stored K/radius/thickness feed the §1 bend-allowance form
    the unfold will use (defaults ride correctly for the downstream slice)."""
    from geometry.sheet_metal import bend_allowance

    d = SheetMetalDefaults(thickness_mm=2.0, k_factor=0.44, bend_radius_mm=3.0)
    ba = bend_allowance(math.pi / 2.0, d.bend_radius_mm, d.k_factor, d.thickness_mm)
    assert ba == pytest.approx(6.094689747964199, abs=1e-12)
