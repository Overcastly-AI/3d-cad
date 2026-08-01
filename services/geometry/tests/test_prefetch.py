"""Prefetch: a warm may make the next rebuild cheaper and MUST NOT be an answer.

The rebuild cache (``test_rebuild_cache.py``) proved that a RESUMED evaluation is
byte-identical to a cold one. Speculation adds the dangerous half of that idea:
work started because of a *guess* about what the user will do next. So the gates
here are, in order of how much they matter:

1. **A warm cannot be published.** Not "is not published today" — cannot. The
   entry point returns an ``int``, the wire reply
   (:class:`~py_kit.schemas.features.WarmTreeResult`) has no field that could
   carry geometry, and — the test that would catch a future regression in the
   evaluator rather than in the DTOs —
   :func:`test_a_warm_leaves_no_artifact_anybody_could_fetch` shows that after a
   warm there is literally nothing addressable to serve: the ``mesh_glb_id`` a
   real evaluate of that very tree publishes does not resolve.
2. **A warm is only ever *usable* through the ordinary key.** A prefix that is
   not exactly the requested one — longer, shorter, or differing in one
   parameter deep inside — must not be resumed from, and the answer must equal a
   cold rebuild's down to the GLB bytes.
3. **Speculation is bounded and cancellable**, because on four cores with several
   users an uninterruptible background rebuild is a self-inflicted DoS.

Everything geometric is asserted against a COLD rebuild of the same request,
never a hand-written expectation (same discipline as the cache suite).
"""

from __future__ import annotations

import importlib.util
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from geometry.features import evaluate as evaluate_module
from geometry.features.evaluate import (
    evaluate_tree,
    rebuild_cache_stats,
    reset_rebuild_cache,
    warm_rebuild_cache,
)
from geometry.main import app
from geometry.mesh_store import configure_mesh_store, fetch_mesh_glb
from geometry.rebuild_cache import (
    DEFAULT_WARM_BUDGET_S,
    LiveWorkGate,
    PrefixCache,
    WarmScheduler,
)
from geometry.warm import warm_scheduler, warm_work
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    WarmCancelRequest,
    WarmTreeRequest,
    WarmTreeResult,
)

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"


def _load_builders() -> ModuleType:
    """Load the tree builders by file path (importlib import-mode: test modules
    cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()

#: What the scheduler hands a warm: poll it between features.
StopFn = Callable[[], bool]

#: Long enough to carry the real mixed vocabulary and to have a middle to edit,
#: short enough that a test does several rebuilds in a couple of seconds.
TREE_N = 12


def _payload(n: int = TREE_N) -> dict[str, Any]:
    return cast(dict[str, Any], _BUILDERS.housing_tree(n))


def _request(payload: dict[str, Any]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(payload)


@dataclass(frozen=True)
class Answer:
    """Everything an evaluation hands out, for warm-vs-cold comparison."""

    statuses: tuple[str, ...]
    mesh_glb_id: str | None
    glb: bytes | None
    volume: float | None
    last_good: uuid.UUID | None
    history: int


def _answer(request: EvaluateTreeRequest, *, record_history: bool = False) -> Answer:
    evaluation = evaluate_tree(request, record_history=record_history)
    result = evaluation.result
    return Answer(
        statuses=tuple(feature.status for feature in result.features),
        mesh_glb_id=result.mesh_glb_id,
        glb=evaluation.glb,
        volume=None if result.properties is None else result.properties.volume,
        last_good=result.last_good_feature_id,
        history=len(evaluation.body_history),
    )


def _cold(request: EvaluateTreeRequest, *, record_history: bool = False) -> Answer:
    """The answer with the cache emptied — the reference every gate compares to."""
    reset_rebuild_cache()
    answer = _answer(request, record_history=record_history)
    reset_rebuild_cache()
    return answer


def _retype(payload: dict[str, Any], index: int) -> dict[str, Any]:
    """The tree with feature *index* edited — what committing an edit sends.

    Nudges the first float parameter it finds DOWNWARD, which is what a modeller
    retyping a depth/radius/offset in an open editor does. Down, and never a
    zero: growing a value hits validated ceilings (a revolve is capped at 360
    degrees) and scaling 0.0 leaves the tree hashing identically, which would
    silently turn an "edit" test into a "repeat" test.
    """
    edited = cast(dict[str, Any], {**payload, "features": list(payload["features"])})
    item = cast(dict[str, Any], edited["features"][index])
    feature = cast(dict[str, Any], item["feature"])
    params = cast(dict[str, Any], feature["params"])
    for key, value in params.items():
        if isinstance(value, float) and value != 0.0:
            params = {**params, key: value * 0.99}
            break
    else:  # pragma: no cover - the housing tree always offers one
        raise AssertionError(f"feature {index} has no float parameter to edit")
    edited["features"][index] = {
        **item,
        "feature": {**feature, "params": params},
    }
    return edited


def _editable_indices(payload: dict[str, Any]) -> list[int]:
    """Every feature position an editor could retype a number in.

    Not every feature has one — a sketch carries entities and constraints, not a
    scalar — so the tests pick their edit sites from here rather than assuming
    that "the feature before feature k" is editable.
    """
    return [
        index
        for index, item in enumerate(payload["features"])
        if any(
            isinstance(value, float) and value != 0.0
            for value in item["feature"]["params"].values()
        )
    ]


def _first_editable_float_index(payload: dict[str, Any]) -> int:
    """The LAST editable feature — the deepest editor an open dialog can name,
    and therefore the longest prefix a warm can settle."""
    editable = _editable_indices(payload)
    assert editable, "the housing tree always offers an editable feature"
    return editable[-1]


# --- 1. A warm cannot be published ---------------------------------------------


def test_a_warm_leaves_no_artifact_anybody_could_fetch() -> None:
    """THE gate. A speculative rebuild must not create something servable.

    A warm evaluates the very same features a real evaluate does, so the only
    thing standing between "speculation" and "a published body" is that the warm
    never derives an artifact. That is asserted the way a consumer would notice
    it: the ``mesh_glb_id`` a real evaluate of this tree publishes does NOT
    resolve after the warm — there is no id to serve, so there is nothing to
    serve it for. The id becomes fetchable only once a real evaluate produced it,
    and it is the same id, because the resume is transparent.
    """
    request = _request(_payload())
    published = _cold(request)
    assert published.mesh_glb_id is not None

    # A fresh mesh store: the cold rebuild above filled the process-wide one.
    configure_mesh_store(None, "test-bucket")
    assert fetch_mesh_glb(published.mesh_glb_id) is None

    reset_rebuild_cache()
    assert warm_rebuild_cache(request) == len(request.features)
    assert fetch_mesh_glb(published.mesh_glb_id) is None, (
        "a warm published an artifact: speculation must never be fetchable"
    )

    # And the warm is still USEFUL: the evaluate that follows resumes on it and
    # publishes the identical id.
    assert _answer(request) == published
    assert fetch_mesh_glb(published.mesh_glb_id) is not None


def test_the_warm_reply_cannot_carry_geometry() -> None:
    """The wire type is the structural half of the same guarantee: there is no
    field on the reply a body, a mesh id or a mass property could travel in, so
    no future handler can start returning one without changing the contract."""
    assert set(WarmTreeResult.model_fields) == {"ticket", "accepted"}
    assert WarmTreeResult.model_fields["accepted"].annotation is bool
    assert WarmTreeResult.model_fields["ticket"].annotation is str


def test_the_warm_route_returns_no_geometry() -> None:
    """The same, end to end: the route's 200 body is exactly the two scheduling
    fields — no mesh id, no properties, no per-feature statuses."""
    client = TestClient(app)
    request = WarmTreeRequest(
        ticket=f"route-shape-{uuid.uuid4()}", tree=_request(_payload(5))
    )
    response = client.post("/api/v1/warm", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    assert set(response.json()) == {"ticket", "accepted"}
    warm_scheduler().cancel(request.ticket)
    warm_scheduler().wait_idle(30.0)


# --- 2. A warm is usable only through the ordinary key --------------------------


def test_a_warmed_prefix_is_never_served_for_a_different_tree() -> None:
    """Edit a feature INSIDE the warmed prefix: the warm must be unusable and the
    answer must be the edited tree's, not the speculated one's."""
    payload = _payload()
    index = _first_editable_float_index(payload)
    warmed = _request(payload)

    inside = _editable_indices(payload)[0]
    assert inside < index
    edited = _retype(payload, inside)  # inside the prefix the warm covered
    cold = _cold(_request(edited))

    reset_rebuild_cache()
    assert warm_rebuild_cache(warmed, prefix_length=index) == index
    before = rebuild_cache_stats()
    assert _answer(_request(edited)) == cold
    assert rebuild_cache_stats().misses == before.misses + 1, (
        "a prefix whose content changed must MISS, never resume"
    )


def test_a_warm_of_a_longer_prefix_cannot_answer_a_shorter_tree() -> None:
    """A checkpoint for 12 features is not an answer for the 9-feature tree that
    precedes it — the state has run past where the shorter tree ends. Rolling the
    travel stop backwards is exactly this case."""
    payload = _payload()
    shorter = _request(_payload(TREE_N - 3))
    cold = _cold(shorter)

    reset_rebuild_cache()
    assert warm_rebuild_cache(_request(payload)) == TREE_N
    before = rebuild_cache_stats()
    assert _answer(shorter) == cold
    assert rebuild_cache_stats().misses == before.misses + 1


def test_warming_the_prefix_of_an_open_editor_serves_the_commit() -> None:
    """The `feature_edit` trigger, end to end at the evaluator: warm 0..k-1 while
    the editor for k is open, then commit an edit to k. The answer is the cold
    one; the saving is that k features arrived from the cache."""
    payload = _payload()
    index = _first_editable_float_index(payload)
    edited = _request(_retype(payload, index))
    cold = _cold(edited)

    reset_rebuild_cache()
    assert warm_rebuild_cache(_request(payload), prefix_length=index) == index
    before = rebuild_cache_stats()
    assert _answer(edited) == cold
    after = rebuild_cache_stats()
    assert after.hits == before.hits + 1
    assert after.resumed_features == before.resumed_features + index


def test_warming_the_provenance_lineage_serves_the_first_face_pick() -> None:
    """The visible one (docs/PERF.md: 29 s for the first pick at N=200).

    A face pick evaluates with ``record_history=True``, which is a SEPARATE cache
    lineage — a plain prefix retains no intermediate bodies and so cannot answer
    per-face provenance. Warming both lineages while the editor is open therefore
    serves the commit AND the pick that follows it; warming only the plain one
    leaves the pick exactly as cold as before.
    """
    payload = _payload()
    index = _first_editable_float_index(payload)
    edited = _request(_retype(payload, index))
    cold = _cold(edited, record_history=True)
    assert cold.history > 0

    reset_rebuild_cache()
    warm_rebuild_cache(_request(payload), prefix_length=index)  # plain lineage only
    before = rebuild_cache_stats()
    assert _answer(edited, record_history=True) == cold
    assert rebuild_cache_stats().misses == before.misses + 1, (
        "the plain lineage must not be able to serve a provenance rebuild"
    )

    reset_rebuild_cache()
    warm_rebuild_cache(_request(payload), prefix_length=index, record_history=True)
    before = rebuild_cache_stats()
    assert _answer(edited, record_history=True) == cold
    after = rebuild_cache_stats()
    assert after.hits == before.hits + 1
    assert after.resumed_features == before.resumed_features + index


def test_re_declaring_the_same_open_editor_keeps_the_checkpoint() -> None:
    """A React re-render re-declares the same intent. The second warm must not
    rebuild, and — the sharper failure — must not leave the cache COLDER than it
    found it: ``take`` removes the entry it resumes from, so a naive re-warm that
    returned early would drop the checkpoint on the floor."""
    payload = _payload()
    index = _first_editable_float_index(payload)
    reset_rebuild_cache()

    assert warm_rebuild_cache(_request(payload), prefix_length=index) == index
    started = time.monotonic()
    assert warm_rebuild_cache(_request(payload), prefix_length=index) == index
    assert time.monotonic() - started < 0.5, "a re-declared warm re-evaluated"

    edited = _request(_retype(payload, index))
    before = rebuild_cache_stats()
    _answer(edited)
    assert rebuild_cache_stats().hits == before.hits + 1


def test_a_warm_stops_at_the_prefix_it_was_given() -> None:
    """``prefix_length`` bounds the WORK, not just the key: warming 0..k-1 must
    not evaluate feature k (whose parameters the user is still typing)."""
    payload = _payload()
    reset_rebuild_cache()
    assert warm_rebuild_cache(_request(payload), prefix_length=4) == 4
    # The full tree now resumes at 4 and no further.
    before = rebuild_cache_stats()
    _answer(_request(payload))
    after = rebuild_cache_stats()
    assert after.resumed_features == before.resumed_features + 4


# --- 3. Bounded and cancellable -------------------------------------------------


def test_the_scheduler_runs_one_warm_at_a_time_and_the_newest_wins() -> None:
    """The concurrency bound is the DoS answer: no matter how many clients
    declare intent, one worker runs one warm. A newer ticket retires the
    incumbent, which observes it on its next feature boundary."""
    scheduler = WarmScheduler()
    running = threading.Event()
    release = threading.Event()
    observed: dict[str, bool] = {}

    def first(should_stop: StopFn) -> None:
        running.set()
        release.wait(10.0)
        observed["first_stopped"] = should_stop()

    def second(should_stop: StopFn) -> None:
        observed["second_ran"] = True
        observed["second_stopped"] = should_stop()

    assert scheduler.submit("a", first)
    assert running.wait(10.0)
    assert scheduler.submit("b", second)
    release.set()
    assert scheduler.wait_idle(10.0)

    assert observed["first_stopped"] is True, "a superseded warm must stop"
    assert observed["second_ran"] is True
    assert observed["second_stopped"] is False
    assert scheduler.stats.superseded == 1


def test_cancelling_a_ticket_stops_the_warm_it_funded() -> None:
    """Closing the editor / ending the drag. The warm sees it between features."""
    scheduler = WarmScheduler()
    running = threading.Event()
    release = threading.Event()
    seen: dict[str, bool] = {}

    def work(should_stop: StopFn) -> None:
        running.set()
        release.wait(10.0)
        seen["stopped"] = should_stop()

    scheduler.submit("editor:7", work)
    assert running.wait(10.0)
    assert scheduler.cancel("editor:7") is True
    release.set()
    assert scheduler.wait_idle(10.0)
    assert seen["stopped"] is True
    assert scheduler.cancel("editor:7") is False, "already finished → nothing to do"
    assert scheduler.stats.cancelled == 1


def test_the_same_ticket_in_flight_is_not_resubmitted() -> None:
    """Idempotence, so a re-render cannot restart the warm it is waiting for."""
    scheduler = WarmScheduler()
    running = threading.Event()
    release = threading.Event()

    def work(_should_stop: StopFn) -> None:
        running.set()
        release.wait(10.0)

    assert scheduler.submit("same", work) is True
    assert running.wait(10.0)
    assert scheduler.submit("same", work) is False
    release.set()
    assert scheduler.wait_idle(10.0)
    assert scheduler.stats.started == 1


def test_the_budget_stops_a_warm_that_would_run_forever() -> None:
    """A spent budget is a stop, not a failure — the shorter prefix it cached is
    a legitimate resume point."""
    scheduler = WarmScheduler(budget_s=0.05)
    verdicts: list[bool] = []

    def work(should_stop: StopFn) -> None:
        verdicts.append(should_stop())
        time.sleep(0.2)
        verdicts.append(should_stop())

    scheduler.submit("slow", work)
    assert scheduler.wait_idle(10.0)
    assert verdicts == [False, True]


def test_a_warm_that_raises_does_not_take_the_worker_down() -> None:
    """Speculation has no caller to report to, so a failure must be counted and
    swallowed — never allowed to kill the one warm thread everything shares."""
    scheduler = WarmScheduler()

    def boom(_should_stop: StopFn) -> None:
        raise RuntimeError("kernel said no")

    scheduler.submit("bad", boom)
    assert scheduler.wait_idle(10.0)
    assert scheduler.stats.failed == 1

    done = threading.Event()
    scheduler.submit("good", lambda _stop: done.set())
    assert scheduler.wait_idle(10.0)
    assert done.is_set(), "the scheduler thread died with the failing warm"


def test_a_warm_drops_its_own_result_rather_than_a_live_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The eviction rule end to end, on real geometry rather than fake payloads.

    Two modelers' checkpoints fill a (deliberately tiny) cache; a third user's
    prefetch then runs a genuine rebuild and finds nowhere to put it. What must
    happen is that the SPECULATION is thrown away — ``warm_rebuild_cache``
    reports 0 features cached — and both live checkpoints still serve the repeat
    that a `/measure` or `/tessellate` would issue. The alternative, measured on
    2026-08-01, is somebody's 244 ms `/measure` becoming 19 s.
    """
    small: PrefixCache[Any] = PrefixCache(2)
    monkeypatch.setattr(evaluate_module, "_REBUILD_CACHE", small)

    payload = _payload(6)
    live_a = _request(payload)
    live_b = _request(_retype(payload, _editable_indices(payload)[-1]))
    speculated = _request(_retype(payload, _editable_indices(payload)[0]))

    # Two live modelers. `del` matters: a checkpoint enters the cache when the
    # evaluation that owns its shapes is released, never before.
    for request in (live_a, live_b):
        evaluation = evaluate_tree(request)
        del evaluation
    assert small.stats.stores == 2

    cached = warm_rebuild_cache(speculated, prefix_length=len(payload["features"]) - 1)

    assert cached == 0, "a warm with nowhere safe to put its result cached nothing"
    assert small.stats.speculative_refused == 1
    assert small.stats.evictions == 0

    for request in (live_a, live_b):
        before = small.stats.hits
        evaluate_tree(request)
        assert small.stats.hits == before + 1, (
            "a live modeler's checkpoint was displaced by somebody else's guess"
        )


class _BusyAfter:
    """A :class:`~geometry.rebuild_cache.WorkGate` that goes busy on cue.

    Real threads racing a real gate would make these tests probabilistic, and the
    property under test is not probabilistic: it is "the warm stops using the
    core at the NEXT feature boundary, and what it built is in the cache". So the
    gate reports idle for the first *features* checks and busy for ever after,
    which puts the pause at a known feature.
    """

    def __init__(self, features: int) -> None:
        self._remaining = features
        self.waits = 0

    def busy(self) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return True

    def wait_until_idle(self, timeout_s: float) -> bool:
        self.waits += 1
        time.sleep(timeout_s)
        return False


class _BusyOnce:
    """Idle for *after* checks, busy for exactly one boundary, then idle again.

    The realistic shape: a real request arrives, the warm banks its prefix and
    steps aside, the request finishes, the warm picks its own checkpoint back up.
    *on_wait* runs while the warm is waiting — which is where a real request
    would take the banked prefix, the outcome the whole mechanism is for.
    """

    def __init__(self, after: int, on_wait: Callable[[], object] | None = None) -> None:
        self._remaining = after
        self._busy = True
        self._on_wait = on_wait
        self.waits = 0

    def busy(self) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return self._busy

    def wait_until_idle(self, timeout_s: float) -> bool:
        self.waits += 1
        self._busy = False
        if self._on_wait is not None:
            self._on_wait()
        return True


def test_a_warm_stops_using_the_core_when_a_real_rebuild_wants_it() -> None:
    """CONC-6: one worker has ONE effective core (OCP holds the GIL), so a warm
    that keeps working through somebody's commit does not use spare capacity — it
    takes half of the only capacity there is. Measured cost when it did: the
    commit went 2 589 -> 4 742 ms, i.e. WORSE than never prefetching at all."""
    payload = _payload()
    request = _request(payload)
    gate = _BusyAfter(3)

    reset_rebuild_cache()
    cached = warm_rebuild_cache(request, budget_s=0.5, yield_to=gate)

    assert cached == 3, "the warm ran on for features nobody had asked it to stop at"
    assert gate.waits >= 1, "it must WAIT for the core, not spin on it"


def test_a_warm_that_yields_leaves_the_prefix_it_built_behind() -> None:
    """The half that makes a partial dwell worth anything.

    Work the warm is still HOLDING is invisible — a request that arrives mid-warm
    can only resume from something that is in the cache — so a warm that steps
    aside must bank its prefix on the way out. Measured on the N=100 tray
    (docs/PERF.md 2026-08-01): a face pick that landed while the warm sat
    mid-provenance paid the full 9.2 s and the warm's fifteen seconds bought
    nothing. Here the same yield leaves a resume point, and the rebuild that
    follows uses it.
    """
    payload = _payload()
    request = _request(payload)
    cold = _cold(request)

    reset_rebuild_cache()
    assert warm_rebuild_cache(request, budget_s=0.5, yield_to=_BusyAfter(4)) == 4

    before = rebuild_cache_stats()
    answer = _answer(request)
    after = rebuild_cache_stats()

    assert after.hits == before.hits + 1
    assert after.resumed_features == before.resumed_features + 4
    assert answer == cold, "a resume from a YIELDED prefix must be byte-identical"


def test_a_warm_reclaims_its_own_checkpoint_and_carries_on() -> None:
    """A pause is not a stop: once the core is free the warm picks its own
    checkpoint back up and finishes the prefix, rather than starting again (which
    would spend the budget rebuilding what it already had)."""
    payload = _payload()
    request = _request(payload)

    reset_rebuild_cache()
    before = rebuild_cache_stats()
    # Idle for two features, busy for one boundary, then idle again: the warm
    # banks 2, waits, reclaims, and runs to the end of the prefix.
    gate = _BusyOnce(after=2)
    cached = warm_rebuild_cache(request, prefix_length=6, budget_s=5.0, yield_to=gate)
    after = rebuild_cache_stats()

    assert cached == 6
    assert gate.waits == 1
    assert after.stores == before.stores + 2, (
        "the pause banked a prefix; the finish banked the rest"
    )
    assert after.hits == before.hits + 1, (
        "it reclaimed its own checkpoint instead of rebuilding the prefix"
    )


def test_a_warm_that_loses_its_checkpoint_to_a_real_request_stops() -> None:
    """The good outcome, and the reason it must not restart: if a real rebuild
    took the banked prefix while the warm was waiting, the speculation has been
    SPENT. Rebuilding the same prefix again would be pure waste on the one core
    the real request is using."""
    payload = _payload()
    request = _request(payload)

    reset_rebuild_cache()
    gate = _BusyOnce(after=3, on_wait=lambda: evaluate_tree(request))
    cached = warm_rebuild_cache(request, prefix_length=8, budget_s=5.0, yield_to=gate)

    assert cached == 3, "the warm carried on after its reason had been served"


def test_the_budget_bounds_a_warm_that_never_gets_the_core() -> None:
    """A worker with no spare cycles is the case where speculation is worth
    nothing, and it must cost nothing either: the budget expires while the warm
    is waiting, and the ticket retires rather than queueing behind the load."""
    payload = _payload()
    request = _request(payload)

    reset_rebuild_cache()
    started = time.perf_counter()
    cached = warm_rebuild_cache(request, budget_s=0.3, yield_to=_BusyAfter(0))
    elapsed = time.perf_counter() - started

    assert cached == 0, "a warm that never got the core cannot have cached anything"
    assert elapsed < 5.0, "the budget must bound the waiting, not only the working"


def test_the_gate_never_serialises_two_real_rebuilds() -> None:
    """The gate is a COUNTER, and it has to stay one: making it a lock would
    serialise the concurrent rebuilds ``test_concurrent_modelers.py`` covers and
    would turn a latency fix into a throughput bug."""
    gate = LiveWorkGate()
    both_inside = threading.Barrier(2, timeout=5.0)

    def rebuild() -> None:
        with gate.tracked():
            both_inside.wait()

    threads = [threading.Thread(target=rebuild) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10.0)
        assert not thread.is_alive(), "two real rebuilds serialised on the gate"
    assert gate.busy() is False


def test_the_default_budget_is_stated_and_bounded() -> None:
    """A budget nobody can find is not a budget. This one was fitted to a
    measurement — a full-prefix warm on the 200-feature tray is 28.9 CPU s, and
    the first value tried (10 s) truncated exactly the part the fix exists for —
    so it is pinned here beside the reasoning in ``rebuild_cache.py``. It is NOT
    the DoS bound; the single scheduler thread is."""
    assert DEFAULT_WARM_BUDGET_S == 30.0
    assert WarmScheduler().stats.submitted == 0


# --- 4. The work one ticket represents ------------------------------------------


def test_warm_work_warms_the_requested_lineages_in_order() -> None:
    """`warm_work` is the whole translation from "a ticket was accepted" to
    kernel work: lineages in priority order under one shared stop predicate, and
    a stop between them so a cancelled ticket cannot start the second."""
    payload = _payload()
    index = _first_editable_float_index(payload)
    edited = _request(_retype(payload, index))
    plain_cold = _cold(edited)
    history_cold = _cold(edited, record_history=True)

    reset_rebuild_cache()
    warm_work(
        WarmTreeRequest(
            ticket="t",
            tree=_request(payload),
            prefix_length=index,
            lineages=["evaluate", "provenance"],
        )
    )(lambda: False)

    before = rebuild_cache_stats()
    assert _answer(edited) == plain_cold
    assert _answer(edited, record_history=True) == history_cold
    after = rebuild_cache_stats()
    assert after.hits == before.hits + 2, "both lineages were warmed"


def test_an_already_stopped_ticket_does_no_work_at_all() -> None:
    payload = _payload()
    reset_rebuild_cache()
    before = rebuild_cache_stats()
    warm_work(WarmTreeRequest(ticket="t", tree=_request(payload)))(lambda: True)
    assert rebuild_cache_stats() == before


# --- 5. The routes --------------------------------------------------------------


def test_the_warm_route_queues_work_that_a_later_evaluate_resumes() -> None:
    client = TestClient(app)
    payload = _payload()
    index = _first_editable_float_index(payload)
    edited = _request(_retype(payload, index))
    cold = _cold(edited)

    reset_rebuild_cache()
    ticket = f"editor-{uuid.uuid4()}"
    response = client.post(
        "/api/v1/warm",
        json=WarmTreeRequest(
            ticket=ticket,
            tree=_request(payload),
            prefix_length=index,
            lineages=["evaluate"],
        ).model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json() == {"ticket": ticket, "accepted": True}
    assert warm_scheduler().wait_idle(60.0)

    before = rebuild_cache_stats()
    assert _answer(edited) == cold
    assert rebuild_cache_stats().hits == before.hits + 1


def test_the_cancel_route_retires_a_ticket() -> None:
    client = TestClient(app)
    ticket = f"cancel-{uuid.uuid4()}"
    running = threading.Event()
    release = threading.Event()

    def work(_should_stop: StopFn) -> None:
        running.set()
        release.wait(10.0)

    warm_scheduler().submit(ticket, work)
    assert running.wait(10.0)
    response = client.post(
        "/api/v1/warm/cancel",
        json=WarmCancelRequest(ticket=ticket).model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json() == {"ticket": ticket, "accepted": True}
    release.set()
    assert warm_scheduler().wait_idle(10.0)

    unknown = client.post("/api/v1/warm/cancel", json={"ticket": "never-issued"})
    assert unknown.json() == {"ticket": "never-issued", "accepted": False}
