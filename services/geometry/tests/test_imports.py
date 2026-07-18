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
import os
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
    ImportParseTimeoutError,
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


# --- hard wall-clock bound (design §6, BACKLOG P1) ------------------------------


def _open_fd_count() -> int:
    """Open file descriptors of THIS process (Linux) — a leak detector."""
    return len(os.listdir("/proc/self/fd"))


def test_import_parse_timeout_fires_and_is_not_a_hang() -> None:
    """A parse that exceeds the wall-clock bound raises ImportParseTimeoutError.

    Technique (documented): the untrusted parse runs in a spawned OCP-only
    subprocess that costs ~0.9 s of cold OCCT import before it can even read, so
    a sub-100 ms bound ALWAYS trips the timeout deterministically (OCP import is
    never that fast) — forcing a real SIGKILL of a subprocess mid-work, the exact
    adversarial-parse condition, without needing a synthetic pathological
    part-21. The call must return promptly (near the bound + reap), never hang.
    """
    import time

    start = time.monotonic()
    with pytest.raises(ImportParseTimeoutError):
        import_step_solid(_box_step_text(), timeout_s=0.05)
    elapsed = time.monotonic() - start
    # Killed near the bound + reap overhead — nowhere near a full parse/hang.
    assert elapsed < 5.0


def test_import_parse_timeout_reaps_subprocess_no_fd_leak() -> None:
    """Repeated timeouts leak no file descriptors or zombie subprocesses.

    This asserts the file-descriptor property: a stable open-fd count across a
    batch of forced timeouts — a leaked pipe or temp-file fd would grow it
    monotonically. Zombie-freedom is not separately asserted here (a zombie
    consumes no fd) because it is guaranteed by construction: ``subprocess.run``
    kills THEN waits (reaps) before re-raising ``TimeoutExpired``, so no aborted
    child is ever left unreaped.
    """
    # Warm-up so first-call import machinery doesn't skew the baseline count.
    with pytest.raises(ImportParseTimeoutError):
        import_step_solid(_box_step_text(), timeout_s=0.05)
    before = _open_fd_count()
    for _ in range(5):
        with pytest.raises(ImportParseTimeoutError):
            import_step_solid(_box_step_text(), timeout_s=0.05)
    after = _open_fd_count()
    assert after <= before


def test_valid_step_still_imports_through_the_subprocess_bound() -> None:
    """The bound does not perturb a valid parse — a box still round-trips exactly.

    Guards that spawning the killable worker + BREP boundary preserves geometry
    (the golden asserts 0.0 deviation end-to-end; this pins it at the kernel).
    """
    original = Solid.make_box(10, 20, 30)
    imported = import_step_solid(
        export_step_bytes(original).decode("utf-8"), timeout_s=30.0
    )
    got = measure_shape(imported)
    want = measure_shape(original)
    assert got.volume == pytest.approx(want.volume, abs=1e-7)
    assert got.surface_area == pytest.approx(want.surface_area, abs=1e-7)
    assert got.topology == want.topology


# --- evaluate handler -----------------------------------------------------------


def test_import_parse_timeout_is_per_feature_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured tiny bound surfaces as ``import_parse_timeout`` (200, not 500).

    Proves the full config wiring: ``STEP_IMPORT_TIMEOUT_SECONDS`` env →
    ``GeometrySettings`` → the evaluate handler → the kernel subprocess bound →
    a per-feature error inside a 200 under the strict-prefix rule.

    The step cache is reset first to force a genuine MISS: an earlier test in
    this process may have cached the identical box STEP, and a cache HIT
    (deliberately, audit F8) skips the subprocess parse — a hit is only reached
    for content that already parsed cleanly within the bound, so it is exempt
    from the timeout by design. The bound being tested here guards the one real
    parse.
    """
    from geometry.step_cache import reset_step_cache

    reset_step_cache()
    monkeypatch.setenv("STEP_IMPORT_TIMEOUT_SECONDS", "0.05")
    payload = _request(
        [{"id": str(IMPORT_ID), "feature": _import_feature(_box_step_text())}]
    )
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    result = EvaluateTreeResult.model_validate(response.json())
    (only,) = result.features
    assert only.status == "error"
    assert only.error is not None and only.error.code == "import_parse_timeout"
    assert result.properties is None


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


def test_second_import_starts_a_new_body() -> None:
    """MB-0 (docs/design/multi-body.md §MB-0): a second import with a body
    already present NO LONGER errors (the retired ``import_with_prior_body``) —
    it STARTS a second body, so the part ends with two bodies. Two imports of
    the SAME box coexist as two solids (shells=2) with the volume summed over
    the body set (no boolean, no dedup — MB-0 keeps them disjoint bodies)."""
    single = _evaluate(
        _request(
            [{"id": str(IMPORT_ID), "feature": _import_feature(_box_step_text())}]
        )
    )
    assert single.properties is not None
    one_volume = single.properties.volume

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
    assert second.status == "ok"
    assert result.properties is not None
    # Two coexisting bodies: two closed shells, volume summed over the body set.
    assert result.properties.topology.shells == 2
    assert result.properties.volume == pytest.approx(2.0 * one_volume, rel=1e-9)


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
