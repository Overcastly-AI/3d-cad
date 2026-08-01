"""What the rebuild cache is actually worth, at real part size (docs/PERF.md #1).

`test_scaling_benchmarks.py` measures COLD rebuilds — it empties the cache
before every sample on purpose, because the exponent it reports is a property of
the evaluator, not of the cache. This file measures the other half: what an
APPEND and a REPEAT cost on a warm tree, which is what a modeller actually pays
per interaction.

TIER POLICY — identical to the scaling sweep, for the same reasons. Both
``benchmark``-marked (excluded by the root ``addopts``) AND gated on
``LOFT_SCALING_BENCH=1``, so it never runs in CI and can never false-red on a
loaded runner. It asserts nothing about time; it prints the table docs/PERF.md
quotes. Run it with::

    LOFT_SCALING_BENCH=1 uv run pytest \\
      services/geometry/tests/test_rebuild_cache_benchmarks.py -m benchmark -s

The always-on correctness gates for the cache live in ``test_rebuild_cache.py``,
where they belong: a cache that is fast and wrong is the failure this project
promises not to ship.
"""

from __future__ import annotations

import importlib.util
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from geometry.features import evaluate_tree
from geometry.features.evaluate import reset_rebuild_cache
from py_kit.schemas.features import EvaluateTreeRequest

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"

#: The same Axis-A points docs/PERF.md sweeps, so the warm column sits beside the
#: cold one without a caveat about part size.
FEATURE_SWEEP: tuple[int, ...] = (10, 25, 50, 100, 200)
SAMPLES = 3


def _load_builders() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()
housing_tree = cast(Callable[[int], dict[str, Any]], _BUILDERS.housing_tree)


def _request(n: int) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(housing_tree(n))


def _ms(thunk: Callable[[], object]) -> float:
    start = time.perf_counter()
    thunk()
    return (time.perf_counter() - start) * 1000.0


def _rss_mb() -> float:
    for line in Path("/proc/self/status").read_text("utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return float(line.split()[1]) / 1024.0
    return float("nan")


@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("LOFT_SCALING_BENCH") != "1",
    reason="scaling sweep is opt-in: set LOFT_SCALING_BENCH=1 (see module docstring)",
)
def test_record_rebuild_cache_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Cold vs append vs repeat at each Axis-A point, plus warm RSS.

    * **cold** — the cache emptied first: what every route used to pay, every time.
    * **append** — the tree evaluated at N-1 (and released), then evaluated at N:
      the modeller's "add one feature", and the case the cache exists for.
    * **repeat** — the same tree again, i.e. the ``/measure`` / ``/tessellate`` /
      ``/export`` / drawings call that follows an ``/evaluate``. Zero features to
      run, so the published artifacts are reused as well.
    * **RSS warm** — resident set with the checkpoint retained, against the cold
      figure: the memory this cache actually costs at real part size.
    """
    rows: list[tuple[int, float, float, float, float, float]] = []
    for n in FEATURE_SWEEP:
        rows.append(_point(n))

    lines = [
        "",
        "| feats | cold rebuild ms | append ms | repeat ms | append speedup | "
        "repeat speedup | RSS cold MiB | RSS warm MiB |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for n, cold, append, repeat, rss_cold, rss_warm in rows:
        lines.append(
            f"| {n} | {cold:.0f} | {append:.0f} | {repeat:.0f} | "
            f"{cold / max(append, 1e-9):.0f}x | {cold / max(repeat, 1e-9):.0f}x | "
            f"{rss_cold:.0f} | {rss_warm:.0f} |"
        )
    with capsys.disabled():
        print("\n".join(lines))


def _cold(request: EvaluateTreeRequest) -> object:
    reset_rebuild_cache()
    return evaluate_tree(request)


def _point(n: int) -> tuple[int, float, float, float, float, float]:
    """One sweep point: cold / append / repeat medians plus cold and warm RSS."""
    request, previous = _request(n), _request(n - 1)

    reset_rebuild_cache()
    evaluate_tree(request)  # untimed warmup, as the scaling sweep does
    cold = statistics.median([_ms(lambda: _cold(request)) for _ in range(SAMPLES)])
    rss_cold = _rss_mb()

    appends: list[float] = []
    for _ in range(SAMPLES):
        reset_rebuild_cache()
        evaluate_tree(previous)  # released immediately -> checkpoint offered
        appends.append(_ms(lambda: evaluate_tree(request)))
    append = statistics.median(appends)

    reset_rebuild_cache()
    evaluate_tree(request)
    repeats = [_ms(lambda: evaluate_tree(request)) for _ in range(SAMPLES)]
    rss_warm = _rss_mb()
    return n, cold, append, statistics.median(repeats), rss_cold, rss_warm
