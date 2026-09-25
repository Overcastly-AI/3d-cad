"""A face pick right after opening a part is a rebuild-cache HIT (PERF-REAL-3).

The interactive loop the product lives in is: open (or edit) a part, which
``POST /evaluate``s its tree, then arm a face pick, which ``POST /overlay``s the
SAME tree. The rebuild cache (:mod:`geometry.rebuild_cache`) exists to make the
second call cost only what is new — nothing, here. It did not: the overlay
evaluated with ``record_history=True`` and ``record_history`` was IN the cache
key, so the pick after every open or edit was a guaranteed miss on a lineage of
its own and re-ran the whole tree. On the gauntlet's imported ``gearbox-11752``
(1 018 faces, one inline-STEP feature) that was 7.9 s of an 8.5 s cold evaluate
spent again, in process, for a question the cache already held the answer to.

Asserted on the cache's own COUNTERS, not on timing: a hit is a statement about
what the service did, and wall clock on a shared runner cannot tell a hit from a
fast miss. Both requests go through the real HTTP routes in their real wire
shapes — the evaluate body is what documents serves (no ``linear_deflection``,
a ``materials`` field), the overlay body is what the web client builds
(``linear_deflection`` explicit, no materials) — so a request field leaking into
the key would fail here too, not only a lineage split.
"""

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from geometry.features.evaluate import rebuild_cache_stats, reset_rebuild_cache
from geometry.main import app

client = TestClient(app)

_TESTS = Path(__file__).resolve().parent
_GOLDENS = _TESTS.parent / "goldens"


def _load_builders() -> ModuleType:
    """The tree builders, by file path (importlib import-mode: test modules
    cannot import each other by name)."""
    path = _TESTS / "_big_part_builders.py"
    spec = importlib.util.spec_from_file_location("_big_part_builders", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _housing() -> dict[str, Any]:
    """A modelled part: a dozen mixed features (pockets, holes, fillets, a shell,
    a datum), so the pick's per-face provenance has several owners to tell apart."""
    return cast(dict[str, Any], _load_builders().housing_tree(12))


def _imported() -> dict[str, Any]:
    """An imported part, the shape of every real part in the gauntlet: ONE inline
    STEP ``import`` feature and nothing else."""
    model = _GOLDENS / "import-step-box-10x20x30" / "model.json"
    return cast(dict[str, Any], json.loads(model.read_text()))


def _documents_shape(tree: dict[str, Any]) -> dict[str, Any]:
    """What ``GET /parts/{id}/evaluation-request`` hands the gateway: the ordered
    features and the material assignment, deflection left at its default."""
    body = {key: value for key, value in tree.items() if key != "linear_deflection"}
    body["materials"] = None
    return body


def _web_shape(tree: dict[str, Any]) -> dict[str, Any]:
    """What ``apps/web`` ``buildEvaluateTree`` sends as the overlay's tree."""
    body = {key: value for key, value in tree.items() if key != "materials"}
    body["linear_deflection"] = 0.1
    return {"tree": body}


TREES = {"housing-12": _housing, "import-step-box": _imported}


@pytest.mark.parametrize("name", sorted(TREES))
def test_an_overlay_after_an_evaluate_of_the_same_tree_is_a_frontier_hit(
    name: str,
) -> None:
    """HEADLINE GATE: open, then pick. The pick must resume the checkpoint the
    open left at the tree's full length — one hit, zero misses, every feature
    resumed, and not via a ladder rung (a rung hit would still re-run the tail)."""
    tree = TREES[name]()
    count = len(tree["features"])

    opened = client.post("/api/v1/evaluate", json=_documents_shape(tree))
    assert opened.status_code == 200, opened.text
    before = rebuild_cache_stats()

    picked = client.post("/api/v1/overlay", json=_web_shape(tree))
    assert picked.status_code == 200, picked.text
    after = rebuild_cache_stats()

    assert after.misses == before.misses, (
        "the face pick after an evaluate of the SAME tree missed the rebuild cache "
        f"and re-ran all {count} features"
    )
    assert after.hits == before.hits + 1
    assert after.resumed_features == before.resumed_features + count
    assert after.rung_hits == before.rung_hits, "a frontier hit, not a rung resume"


@pytest.mark.parametrize("name", sorted(TREES))
def test_the_hit_serves_the_same_pick_a_cold_overlay_does(name: str) -> None:
    """A hit is only a win if it is TRANSPARENT: the overlay served from the
    checkpoint an evaluate left must be the overlay a cold worker computes —
    every vertex, edge, face and, above all, every per-face ``feature_id``
    (provenance a prefix evaluated without history would get silently wrong)."""
    tree = TREES[name]()
    reset_rebuild_cache()
    cold = client.post("/api/v1/overlay", json=_web_shape(copy.deepcopy(tree)))
    assert cold.status_code == 200, cold.text

    reset_rebuild_cache()
    assert (
        client.post("/api/v1/evaluate", json=_documents_shape(tree)).status_code == 200
    )
    warm = client.post("/api/v1/overlay", json=_web_shape(tree))
    assert warm.status_code == 200, warm.text

    assert warm.json() == cold.json()
    owners = [face["feature_id"] for face in cold.json()["faces"]]
    assert owners and all(owner is not None for owner in owners), (
        "non-vacuous: every face of the part is attributed to a feature"
    )


def test_an_evaluate_after_an_overlay_is_a_hit_too() -> None:
    """The other order (pick, then edit-free re-open or ``/measure``): one lineage
    serves both callers, so neither can leave the other a cold cache."""
    tree = _housing()
    assert client.post("/api/v1/overlay", json=_web_shape(tree)).status_code == 200
    before = rebuild_cache_stats()
    assert (
        client.post("/api/v1/evaluate", json=_documents_shape(tree)).status_code == 200
    )
    after = rebuild_cache_stats()
    assert (after.hits, after.misses) == (before.hits + 1, before.misses)
