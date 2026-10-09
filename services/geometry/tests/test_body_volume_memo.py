"""The per-body volume memo always describes the body it is keyed to.

:attr:`~geometry.features.state.EvaluationState.body_volumes` bounds the boolean
integrity guard (:mod:`geometry.kernel.boolean_guard`). A value that outlived
its shape would bound the next boolean by the wrong operand, so every funnel
that installs a shape either records the volume the op measured on THAT shape
or drops the entry. A mirror and a pattern record theirs since
PERF-REBUILD-200 pass 2 (RESEARCH §15a step 5); these tests rebuild every
golden with a mirror or a pattern, and the 29-feature housing, and check the
memo against a fresh integration after every install.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from geometry.features.evaluate import reset_rebuild_cache
from geometry.features.state import EvaluationState
from geometry.harness import evaluate_model, golden_refusals, load_model_request
from geometry.kernel.healing import shape_volume
from loft_wire.features import EvaluateTreeRequest

_GOLDENS = Path(__file__).resolve().parents[1] / "goldens"
_BUILDERS = Path(__file__).resolve().parent / "_big_part_builders.py"

#: The memo and a fresh integration of the same shape agree to float noise
#: (a multi-lump result is integrated lump by lump, the check whole). A stale
#: entry is off by a feature's material, many orders above this.
_REL = 1e-9


def _replicating_goldens() -> list[Path]:
    """Every golden tree with a mirror or a pattern feature, by name."""
    found: list[Path] = []
    for model in sorted(_GOLDENS.glob("*/model.json")):
        data = json.loads(model.read_text("utf-8"))
        kinds = {item["feature"]["type"] for item in data.get("features", [])}
        if kinds & {"mirror", "pattern"}:
            found.append(model)
    return found


class _Audit:
    """Wraps the three body funnels; checks the memo after each install."""

    def __init__(self) -> None:
        self.checked = 0
        self.recorded_by_replication = 0

    def check(self, state: EvaluationState, body_id: uuid.UUID) -> None:
        known = state.body_volumes.get(body_id)
        if known is None:
            return
        fresh = shape_volume(state.bodies[body_id])
        assert known == pytest.approx(fresh, rel=_REL, abs=1e-9), (
            f"memo {known} describes another shape than the body ({fresh})"
        )
        self.checked += 1

    def wrap(self, funnel: Callable[..., None]) -> Callable[..., None]:
        def audited(state: EvaluationState, *args: Any, **kwargs: Any) -> None:
            funnel(state, *args, **kwargs)
            body_id = state.active_body_id
            assert body_id is not None
            self.check(state, body_id)
            caller = inspect.stack()[1].function
            replicating = caller.startswith(("_evaluate_mirror", "_evaluate_pattern"))
            if replicating and kwargs.get("volume") is not None:
                self.recorded_by_replication += 1

        return audited


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Audit]:
    found = _Audit()
    for name in ("set_active_body", "start_body", "combine_bodies"):
        monkeypatch.setattr(
            EvaluationState, name, found.wrap(getattr(EvaluationState, name))
        )
    reset_rebuild_cache()
    yield found
    reset_rebuild_cache()


@pytest.mark.parametrize("model", _replicating_goldens(), ids=lambda p: p.parent.name)
def test_mirror_and_pattern_goldens_keep_the_memo_true(
    model: Path, audit: _Audit
) -> None:
    """Every install's memo matches its body, and the replicating verbs record."""
    request = load_model_request(model.read_text("utf-8"))
    evaluate_model(request, golden_refusals(model))
    assert audit.checked > 0
    assert audit.recorded_by_replication > 0, "the mirror/pattern recorded no volume"


def test_housing_tree_keeps_the_memo_true(audit: _Audit) -> None:
    """The perf tray: features-scope pattern cuts and mirrors among 29 features."""
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS)
    assert spec is not None and spec.loader is not None
    builders = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builders)
    from geometry.features import evaluate_tree

    tree = EvaluateTreeRequest.model_validate(builders.housing_tree(29))
    evaluation = evaluate_tree(tree)
    assert all(r.status == "ok" for r in evaluation.result.features)
    assert audit.recorded_by_replication >= 2
