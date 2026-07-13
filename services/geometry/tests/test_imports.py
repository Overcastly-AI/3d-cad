"""STEP import — kernel reader + evaluate handler (docs/design/step-import.md).

Covers the geometry-side import slice: the low-level ``import_step_solid``
reader (single-solid happy path, parse failure, not-single-solid), and the
``import`` feature handler through ``evaluate_tree`` (a base feature that SETS
the body, the ``import_with_prior_body`` guard, and per-feature error mapping —
never a 500). The round-trip *fidelity* proof (mass props / topology preserved)
lives in the golden ``import-step-box-10x20x30`` and the golden runner; here we
exercise the code paths and error taxonomy.
"""

import io
import uuid
from typing import Any

import pytest
from build123d import (
    Compound,
    Location,
    Solid,
    export_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.features import evaluate_tree
from geometry.kernel import (
    ImportNotSingleSolidError,
    ImportParseError,
    export_step_bytes,
    import_step_solid,
    measure_shape,
)
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeRequest, EvaluateTreeResult

client = TestClient(app)

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fb")
IMPORT_ID = uuid.UUID("00000000-0000-0000-0000-00000000c001")
TAIL_ID = uuid.UUID("00000000-0000-0000-0000-00000000c002")


def _box_step_text() -> str:
    """STEP AP214 text of the 10x20x30 box (byte-deterministic export)."""
    return export_step_bytes(Solid.make_box(10, 20, 30)).decode("utf-8")


def _import_feature(data: str) -> dict[str, Any]:
    return {
        "type": "import",
        "version": 1,
        "params": {"kind": "inline", "format": "step", "data": data},
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": 1,
        "features": features,
    }


def _evaluate(payload: dict[str, Any]) -> EvaluateTreeResult:
    return evaluate_tree(EvaluateTreeRequest.model_validate(payload)).result


# --- kernel reader --------------------------------------------------------------


def test_import_step_solid_round_trips_a_box_losslessly() -> None:
    """A box exported then re-imported measures the analytic box exactly."""
    original = Solid.make_box(10, 20, 30)
    imported = import_step_solid(export_step_bytes(original).decode("utf-8"))

    got = measure_shape(imported)
    want = measure_shape(original)
    assert got.volume == pytest.approx(want.volume, abs=1e-7)
    assert got.surface_area == pytest.approx(want.surface_area, abs=1e-7)
    assert got.topology == want.topology


def test_import_step_solid_is_deterministic() -> None:
    """Same STEP bytes → identical measured geometry (RESEARCH §9)."""
    text = _box_step_text()
    a = measure_shape(import_step_solid(text))
    b = measure_shape(import_step_solid(text))
    assert a == b


def test_import_step_solid_rejects_garbage() -> None:
    """Unparseable bytes raise ImportParseError (never a hang / crash)."""
    with pytest.raises(ImportParseError):
        import_step_solid("this is not a STEP file at all")


def test_import_step_solid_rejects_empty() -> None:
    with pytest.raises(ImportParseError):
        import_step_solid("   ")


def test_import_step_solid_rejects_multi_solid_with_stats() -> None:
    """A compound of two disjoint solids is import_not_single_solid, and the
    message carries the honest shape stats (the v1 healing report)."""
    far = Solid.make_box(5, 5, 5).located(Location((50, 0, 0)))
    two = Compound([Solid.make_box(10, 10, 10), far])
    buffer = io.BytesIO()
    assert export_step(two, buffer)
    with pytest.raises(ImportNotSingleSolidError) as excinfo:
        import_step_solid(buffer.getvalue().decode("utf-8"))
    assert "found 2" in str(excinfo.value)


# --- evaluate handler -----------------------------------------------------------


def test_import_feature_sets_base_body() -> None:
    """An import as the first feature evaluates ok and produces the body."""
    result = _evaluate(
        _request([{"id": str(IMPORT_ID), "feature": _import_feature(_box_step_text())}])
    )
    assert [f.status for f in result.features] == ["ok"]
    assert result.mesh_glb_id is not None
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(6000.0, abs=1e-7)


def test_import_parse_failed_is_per_feature_not_500() -> None:
    """Bad STEP is a per-feature error inside a 200, strict-prefix applied."""
    payload = _request(
        [
            {"id": str(IMPORT_ID), "feature": _import_feature("garbage not step")},
            {"id": str(TAIL_ID), "feature": _import_feature(_box_step_text())},
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    result = EvaluateTreeResult.model_validate(response.json())
    first, second = result.features
    assert first.status == "error"
    assert first.error is not None and first.error.code == "import_parse_failed"
    assert second.status == "skipped"
    assert result.properties is None


def test_import_with_prior_body_is_rejected() -> None:
    """A second import (with a body already present) is import_with_prior_body."""
    result = _evaluate(
        _request(
            [
                {"id": str(IMPORT_ID), "feature": _import_feature(_box_step_text())},
                {"id": str(TAIL_ID), "feature": _import_feature(_box_step_text())},
            ]
        )
    )
    first, second = result.features
    assert first.status == "ok"
    assert second.status == "error"
    assert second.error is not None
    assert second.error.code == "import_with_prior_body"


def test_import_size_bound_is_a_422_not_a_rebuild_error() -> None:
    """An oversize inline payload is rejected at request validation (§6)."""
    from py_kit.schemas.features import MAX_INLINE_STEP_CHARS

    payload = _request(
        [
            {
                "id": str(IMPORT_ID),
                "feature": _import_feature("x" * (MAX_INLINE_STEP_CHARS + 1)),
            }
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 422
