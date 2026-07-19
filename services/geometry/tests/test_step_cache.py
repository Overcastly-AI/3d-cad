"""STEP re-parse cache — content-keyed skip of the subprocess parse (audit F8).

An inline ``import`` feature re-parses the full STEP part on every tree
evaluation; :mod:`geometry.step_cache` memoises the parse result keyed on the
STEP content so an unchanged import pays one parse per distinct upload, not one
per edit. These tests prove:

* one-parse-not-two — a second evaluation of the SAME inline import does NOT
  re-spawn the parse (a counter on ``import_step_solid`` proves it ran once);
* a DIFFERENT STEP content is a genuine miss (parses again);
* a hit is byte-identical to a miss (same ``mesh_glb_id`` + measured props), so
  the determinism goldens cannot be perturbed;
* a hit still yields the correct measured solid (vol / topology);
* only cleanly-parsed bodies are cached — a parse failure is never cached, so
  the bounded subprocess (and its timeout) re-runs on the next attempt.

The round-trip *fidelity* proof lives in the ``import-step-box-10x20x30``
golden; here we exercise the cache behaviour and the security invariant.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from build123d import Solid
from geometry import step_cache
from geometry.features import evaluate_tree
from geometry.kernel import (
    ImportParseError,
    export_step_bytes,
    import_step_solid,
)
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import EvaluateTreeRequest, EvaluateTreeResult

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
IMPORT_ID = uuid.UUID("00000000-0000-0000-0000-00000000d001")


def _box_step_text(sx: float = 10, sy: float = 20, sz: float = 30) -> str:
    """STEP AP214 text of a box (byte-deterministic export)."""
    return export_step_bytes(Solid.make_box(sx, sy, sz)).decode("utf-8")


def _request(data: str) -> EvaluateTreeRequest:
    payload: dict[str, Any] = {
        "part_id": str(PART_ID),
        "tree_version": 1,
        "features": [
            {
                "id": str(IMPORT_ID),
                "feature": {
                    "type": "import",
                    "version": 1,
                    "params": {"kind": "inline", "format": "step", "data": data},
                },
            }
        ],
    }
    return EvaluateTreeRequest.model_validate(payload)


def _evaluate(data: str) -> EvaluateTreeResult:
    return evaluate_tree(_request(data)).result


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    """Isolate each test with an empty per-worker cache (order-independent)."""
    step_cache.reset_step_cache()
    yield
    step_cache.reset_step_cache()


def _spy_parse(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """Wrap the cache module's ``import_step_solid`` with a call counter.

    The cache module calls ``import_step_solid`` (which spawns the killable
    subprocess parse) by name in its own namespace, so patching the name THERE
    counts real parses — a hit skips the call, a miss increments it.
    """
    calls = 0
    real = import_step_solid

    def counted(step_text: str, *, timeout_s: float) -> BodyShape:
        nonlocal calls
        calls += 1
        return real(step_text, timeout_s=timeout_s)

    monkeypatch.setattr(step_cache, "import_step_solid", counted)
    return lambda: calls


def test_second_evaluation_of_same_import_does_not_reparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One-parse-not-two: the SAME inline import parses once across two evals."""
    parses = _spy_parse(monkeypatch)
    data = _box_step_text()

    first = _evaluate(data)
    assert [f.status for f in first.features] == ["ok"]
    assert parses() == 1

    second = _evaluate(data)
    assert [f.status for f in second.features] == ["ok"]
    # The subprocess parse ran ONCE — the second evaluation hit the cache.
    assert parses() == 1


def test_hit_is_byte_identical_to_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cache hit yields the identical mesh + measured props as the miss.

    This is the determinism guard: if a hit perturbed the body the goldens
    would drift, so the re-read body must tessellate byte-identically.
    """
    _spy_parse(monkeypatch)
    data = _box_step_text()

    miss = _evaluate(data)
    hit = _evaluate(data)

    assert hit.mesh_glb_id == miss.mesh_glb_id
    assert hit.properties == miss.properties


def test_hit_yields_the_correct_measured_solid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cached (re-read) body measures the analytic box exactly."""
    _spy_parse(monkeypatch)
    data = _box_step_text()
    _evaluate(data)  # populate
    hit = _evaluate(data)

    assert hit.properties is not None
    assert hit.properties.volume == pytest.approx(6000.0, abs=1e-7)
    assert hit.properties.topology.faces == 6
    assert hit.properties.topology.edges == 12


def test_different_content_is_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DIFFERENT STEP content parses again — distinct keys, distinct parses."""
    parses = _spy_parse(monkeypatch)

    _evaluate(_box_step_text(10, 20, 30))
    assert parses() == 1

    _evaluate(_box_step_text(11, 22, 33))
    assert parses() == 2

    # ...and the first content is still cached (no third parse).
    _evaluate(_box_step_text(10, 20, 30))
    assert parses() == 2


def test_parse_failure_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed parse is never cached, so the bounded parse re-runs next time.

    Guards the security invariant: only a body that cleared every bound is
    cached, so a rejected input cannot become a hit that skips the subprocess
    timeout on a later attempt. Proven behaviourally: the second attempt on the
    SAME bad content runs the real parse AGAIN (counter reaches 2) — a silent
    "hit" would leave it at 1.
    """
    parses = _spy_parse(monkeypatch)
    with pytest.raises(ImportParseError):
        step_cache.import_step_solid_cached("garbage not step", timeout_s=30.0)
    assert parses() == 1
    # Re-attempt still raises AND re-parses (the failure was not cached).
    with pytest.raises(ImportParseError):
        step_cache.import_step_solid_cached("garbage not step", timeout_s=30.0)
    assert parses() == 2


def test_cache_evicts_at_capacity() -> None:
    """The LRU is bounded — memory cannot grow without limit."""
    cache = step_cache.StepParseCache(capacity=2)
    cache.put("a", b"1")
    cache.put("b", b"2")
    cache.put("c", b"3")  # evicts "a" (least-recently-used)
    assert cache.get("a") is None
    assert cache.get("b") == b"2"
    assert cache.get("c") == b"3"
