"""Several modelers, several DIFFERENT parts, one worker (docs/PERF.md 2026-08-01).

``test_rebuild_cache.py`` already pins the same-tree case: three threads asking
for one tree all get the cold answer. This file pins the case an operator
actually has — **N people on N different parts in one geometry process** — and it
is a different hazard, because the shared mutable state between them is not one
checkpoint but the whole LRU: thread A's ``take`` can evict thread B's entry
mid-flight, and an OCCT boolean rewrites its arguments' subshapes in place
(CM-6b), so a checkpoint lent to the wrong lineage would not raise — it would
return a *plausible body for the wrong part*.

The gate is the same one the load harness (``scripts/concurrency-load.py``) uses
over HTTP and for the same reason: ``mesh_glb_id`` is a content hash of the GLB
and ``volume`` comes off the exact B-rep, so two crossed evaluations cannot
agree with their serial baselines by accident.

WHY THE PARTS DIFFER BY A CORNER RADIUS. Feature 2 of the tray is a whole-body
``axis_parallel`` Z fillet, so moving it re-hashes every prefix after it while
leaving the tree valid and the cost unchanged — distinct lineages, same work.
The offsets are micrometres on purpose (the load harness learned this the hard
way: a 0.1 mm-per-run offset silently turned an 8 mm round into a 48 mm one,
i.e. a different part with a different cost).
"""

from __future__ import annotations

import copy
import importlib.util
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from geometry.features.evaluate import evaluate_tree, reset_rebuild_cache
from py_kit.schemas.features import EvaluateTreeRequest

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"


def _load_builders() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()

#: Small enough that the whole file is a few seconds in the default suite, long
#: enough to carry the mixed vocabulary (pockets, holes, fillets, shell, datum)
#: that makes a crossed body detectable at all.
TREE_N = 10

#: More threads than the cache holds entries per lineage, so the LRU is genuinely
#: contended rather than comfortably large.
MODELERS = 4


def _part(modeler: int) -> EvaluateTreeRequest:
    payload = cast(dict[str, Any], copy.deepcopy(_BUILDERS.housing_tree(TREE_N)))
    fillet = cast(list[dict[str, Any]], payload["features"])[2]
    params = cast(dict[str, Any], cast(dict[str, Any], fillet["feature"])["params"])
    assert "radius_mm" in params, "feature 2 of the tray is the corner fillet"
    params["radius_mm"] = round(float(params["radius_mm"]) + 1e-3 * (modeler + 1), 6)
    return EvaluateTreeRequest.model_validate(payload)


def _signature(
    request: EvaluateTreeRequest, *, record_history: bool = False
) -> tuple[str | None, float | None, tuple[str, ...]]:
    """What a crossed evaluation could not fake, plus the per-feature verdict."""
    result = evaluate_tree(request, record_history=record_history).result
    return (
        result.mesh_glb_id,
        result.properties.volume if result.properties else None,
        tuple(feature.status for feature in result.features),
    )


def test_four_modelers_on_four_parts_never_cross() -> None:
    """The P0 gate. Each part's concurrent answer must equal its serial answer.

    Serial baselines are taken first, each from a cold cache, so the comparison
    is against the value a lone user would have received — not against whatever
    the concurrent run happened to agree on.
    """
    requests = [_part(modeler) for modeler in range(MODELERS)]
    baselines: list[tuple[str | None, float | None, tuple[str, ...]]] = []
    for request in requests:
        reset_rebuild_cache()
        baselines.append(_signature(request))
    assert len({baseline[0] for baseline in baselines}) == MODELERS, (
        "the parts must be genuinely different, or this test proves nothing"
    )
    assert all(set(baseline[2]) == {"ok"} for baseline in baselines)

    reset_rebuild_cache()
    observed: dict[int, tuple[str | None, float | None, tuple[str, ...]]] = {}
    lock = threading.Lock()
    errors: list[BaseException] = []

    def run(modeler: int) -> None:
        try:
            # Two rounds: the second is where a resume can happen at all, since
            # the first round's checkpoints only enter the LRU once their
            # evaluations are released.
            for _ in range(2):
                signature = _signature(requests[modeler])
                with lock:
                    observed[modeler] = signature
        # Deliberately broad: a thread that raises would otherwise vanish
        # silently and the test would pass on three of four modelers.
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(modeler,), name=f"modeler-{modeler}")
        for modeler in range(MODELERS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"a concurrent rebuild raised: {errors[0]!r}"
    for modeler, baseline in enumerate(baselines):
        assert observed[modeler] == baseline, (
            f"modeler {modeler} got a DIFFERENT body under concurrency than "
            f"alone: {observed[modeler]} vs {baseline}"
        )


def test_interleaved_evaluate_and_overlay_lineages_never_cross() -> None:
    """The two lineages of one part are keyed apart, under contention.

    ``record_history`` is part of the cache key because a prefix evaluated
    without snapshots cannot serve per-face provenance. An edit-then-pick session
    alternates between the two lineages of the SAME tree, so this is the pairing
    most likely to hand one lineage's checkpoint to the other — and the answer
    must be identical either way, since history only adds retained snapshots.
    """
    request = _part(0)
    reset_rebuild_cache()
    plain = _signature(request)
    reset_rebuild_cache()
    with_history = _signature(request, record_history=True)
    assert plain == with_history, "recording history must not change the body"

    reset_rebuild_cache()
    observed: list[tuple[str | None, float | None, tuple[str, ...]]] = []
    lock = threading.Lock()

    def run(record_history: bool) -> None:
        for _ in range(3):
            signature = _signature(request, record_history=record_history)
            with lock:
                observed.append(signature)

    threads = [
        threading.Thread(target=run, args=(record_history,))
        for record_history in (False, True, False, True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert observed == [plain] * len(observed)
