"""The two geometry observability seams MOVE their metrics (docs/OBSERVABILITY.md).

`py_kit.metrics` declares the numbers; two places in this service produce the
events behind them — the prefix cache (`geometry.rebuild_cache`) and the bounded
STEP parse worker (`geometry.kernel.imports`). A metric that is declared but
never incremented is worse than no metric: an operator reads a flat line as "no
STEP imports are being refused" and acts on it. So every test below asserts a
DELTA on the exact sample an operator would graph, never that a name appears in
the exposition.

Both seams were chosen because they cannot be bypassed: `evaluate_tree` consults
the cache as its second statement whichever of its nine callers asked, and both
STEP readers run their untrusted parse through the one bounded worker. The tests
here drive the seams directly — no OCCT — so they stay fast and stay honest about
what they cover: the wiring, not the kernel.
"""

import signal
import sys

import pytest
from geometry.kernel._step_parse_worker import EXIT_TOO_MANY_PRODUCTS
from geometry.kernel.imports import (
    ImportParseError,
    ImportParseTimeoutError,
    ImportTooManyProductsError,
    run_bounded_parse_worker,
)
from geometry.rebuild_cache import PrefixCache
from py_kit.metrics import REGISTRY


def _value(name: str, labels: dict[str, str] | None = None) -> float:
    """A sample's current value, absent series read as 0.0 (see py-kit tests)."""
    sample = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if sample is None else sample


class _Checkpoint:
    """Minimal :class:`geometry.rebuild_cache.Detachable` payload.

    The cache is generic over its payload precisely so it can be exercised
    without the evaluator (and therefore without OCCT); ``detach`` records that
    the cache called it, which is the ownership contract the real checkpoint
    relies on.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.detached = False

    def detach(self) -> None:
        self.detached = True


def _keys(count: int, *, lineage: str) -> list[str]:
    """A key chain shaped like :func:`geometry.rebuild_cache.prefix_keys` output:
    ``count + 1`` entries, index ``k`` addressing the first ``k`` features."""
    return [f"{lineage}:{index}" for index in range(count + 1)]


# ---------------------------------------------------------------------------
# the rebuild cache
# ---------------------------------------------------------------------------


def test_a_cold_lookup_counts_a_miss_and_the_features_it_will_evaluate() -> None:
    misses_before = _value("loft_rebuild_cache_misses_total")
    evaluated_before = _value("loft_rebuild_features_evaluated_total")

    cache: PrefixCache[_Checkpoint] = PrefixCache(4)
    assert cache.take(_keys(30, lineage="cold")) is None

    assert _value("loft_rebuild_cache_misses_total") == misses_before + 1
    # A miss rebuilds from feature 0, so all 30 features are kernel work.
    assert _value("loft_rebuild_features_evaluated_total") == evaluated_before + 30


def test_an_append_counts_a_hit_and_splits_resumed_from_evaluated() -> None:
    """The product's headline saving, as an operator sees it: 29 of 30 features
    served from the cached prefix, 1 actually evaluated."""
    hits_before = _value("loft_rebuild_cache_hits_total")
    evaluated_before = _value("loft_rebuild_features_evaluated_total")
    resumed_before = _value("loft_rebuild_features_resumed_total")

    cache: PrefixCache[_Checkpoint] = PrefixCache(4)
    keys = _keys(30, lineage="append")
    cache.store(keys[29], _Checkpoint("prefix-29"))

    resumed = cache.take(keys)
    assert resumed is not None and resumed[0] == 29

    assert _value("loft_rebuild_cache_hits_total") == hits_before + 1
    assert _value("loft_rebuild_features_evaluated_total") == evaluated_before + 1
    assert _value("loft_rebuild_features_resumed_total") == resumed_before + 29


def test_storing_and_evicting_are_counted_separately() -> None:
    """Evictions are the signal that the working set exceeds the per-process
    LRU — the reading that tells a self-hoster their worker count is fighting
    the cache. It must not be conflated with an ordinary store."""
    stores_before = _value("loft_rebuild_cache_stores_total")
    evictions_before = _value("loft_rebuild_cache_evictions_total")

    cache: PrefixCache[_Checkpoint] = PrefixCache(2)
    for index in range(3):
        cache.store(f"evict:{index}", _Checkpoint(f"cp-{index}"))

    assert _value("loft_rebuild_cache_stores_total") == stores_before + 3
    assert _value("loft_rebuild_cache_evictions_total") == evictions_before + 1


def test_recording_does_not_change_what_the_cache_returns() -> None:
    """Instrumentation is additive: the ownership transfer, the detach and the
    in-process stats all behave exactly as before."""
    cache: PrefixCache[_Checkpoint] = PrefixCache(2)
    keys = _keys(3, lineage="inert")
    checkpoint = _Checkpoint("cp")
    cache.store(keys[3], checkpoint)
    assert checkpoint.detached is True

    taken = cache.take(keys)
    assert taken == (3, checkpoint)
    # `take` REMOVES the entry (ownership transfer), so a second take misses.
    assert cache.take(keys) is None
    stats = cache.stats
    assert (stats.hits, stats.misses, stats.stores) == (1, 1, 1)


# ---------------------------------------------------------------------------
# the bounded STEP parse worker
# ---------------------------------------------------------------------------

#: A child that exits cleanly, standing in for a successful parse. The seam under
#: test is the runner's timing/outcome mapping, which is independent of OCCT —
#: keeping the real reader out of these tests is what makes them run in
#: milliseconds instead of seconds.
_CLEAN_EXIT = [sys.executable, "-c", "pass"]


def _run(
    argv: list[str], *, cpu_timeout_s: float = 20.0, wall_timeout_s: float = 5.0
) -> None:
    run_bounded_parse_worker(
        argv, cpu_timeout_s=cpu_timeout_s, wall_timeout_s=wall_timeout_s
    )


def test_a_successful_parse_is_timed_under_the_ok_outcome() -> None:
    labels = {"outcome": "ok"}
    count_before = _value("loft_step_import_duration_seconds_count", labels)
    sum_before = _value("loft_step_import_duration_seconds_sum", labels)

    _run(_CLEAN_EXIT)

    assert _value("loft_step_import_duration_seconds_count", labels) == count_before + 1
    # A duration, not just a tally: spawning a Python child is never free.
    assert _value("loft_step_import_duration_seconds_sum", labels) > sum_before


def test_the_cpu_ceiling_is_counted_as_a_refusal() -> None:
    """THE metric behind "are my users hitting the DoS ceiling?" — docs/PERF.md
    measured that ceiling at ~3x headroom over the worst file the upload cap
    admits, so a self-hoster whose users reach it must be able to SEE it."""
    refusals_before = _value(
        "loft_step_import_refusals_total", {"reason": "cpu_timeout"}
    )
    duration_before = _value(
        "loft_step_import_duration_seconds_count", {"outcome": "cpu_timeout"}
    )

    # SIGXCPU is exactly what RLIMIT_CPU delivers at the soft limit, so this
    # exercises the real signal→ImportParseTimeoutError mapping.
    with pytest.raises(ImportParseTimeoutError):
        _run(
            [
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGXCPU)",
            ]
        )

    assert (
        _value("loft_step_import_refusals_total", {"reason": "cpu_timeout"})
        == refusals_before + 1
    )
    assert (
        _value("loft_step_import_duration_seconds_count", {"outcome": "cpu_timeout"})
        == duration_before + 1
    )
    assert signal.SIGXCPU  # the constant this test's premise depends on exists


def test_a_wedged_child_is_counted_separately_from_the_cpu_ceiling() -> None:
    """Two different operator actions: a CPU-ceiling refusal says "raise the
    bound or reject the file", a wall-clock kill says "something is stuck"."""
    labels = {"reason": "wall_timeout"}
    before = _value("loft_step_import_refusals_total", labels)

    with pytest.raises(ImportParseTimeoutError):
        _run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            wall_timeout_s=0.25,
        )

    assert _value("loft_step_import_refusals_total", labels) == before + 1


def test_the_assembly_occurrence_ceiling_is_a_refusal() -> None:
    labels = {"reason": "too_many_products"}
    before = _value("loft_step_import_refusals_total", labels)

    with pytest.raises(ImportTooManyProductsError):
        _run([sys.executable, "-c", f"raise SystemExit({EXIT_TOO_MANY_PRODUCTS})"])

    assert _value("loft_step_import_refusals_total", labels) == before + 1


def test_a_malformed_file_is_timed_but_is_not_a_refusal() -> None:
    """Bad input is the user's problem, a resource bound is the operator's. If
    the two shared a counter, "are my users hitting the ceiling?" would be
    unanswerable — which is the whole point of the refusal metric."""
    duration_before = _value(
        "loft_step_import_duration_seconds_count", {"outcome": "parse_failed"}
    )
    refusals_before = _value(
        "loft_step_import_refusals_total", {"reason": "parse_failed"}
    )

    with pytest.raises(ImportParseError):
        _run([sys.executable, "-c", "raise SystemExit(2)"])

    assert (
        _value("loft_step_import_duration_seconds_count", {"outcome": "parse_failed"})
        == duration_before + 1
    )
    assert (
        _value("loft_step_import_refusals_total", {"reason": "parse_failed"})
        == refusals_before
    )
