"""Scaling benchmarks — how big a part can Loft actually hold? (docs/PERF.md)

The shipped perf suite (``tests/test_benchmarks.py``) times REAL operations on
the shipped goldens, and every one of those is 3-8 features and under 100 faces.
Nothing measured the size a working engineer actually builds. This module sweeps
two INDEPENDENT axes over the parts in ``tests/_big_part_builders.py``:

* **feature count** — a 360 x 240 x 20 mm shelled tray lid swept over N = 10 /
  25 / 50 / 100 / 200 features, in a realistic mixed vocabulary (pockets, holes,
  bosses, fillets, a shell, revolves, a patterned vent, a scoped mirror); and
* **face count** — a finned heat sink at a FIXED six features, swept over fin
  count, so topology grows while the tree does not.

Per point it records rebuild wall time, per-feature cost and the dominant
feature TYPE, face/edge counts, triangle count, GLB payload bytes, STEP and STL
export time and bytes, the interactive overlay (face-matcher) time, and RSS.

TIER POLICY — this file is deliberately NOT a timing gate.

* The **sweep** (:func:`test_record_scaling_tables`) is BOTH ``benchmark``-marked
  (excluded by the root ``addopts = "... -m 'not benchmark'"``) AND gated on
  ``LOFT_SCALING_BENCH=1`` (the ``LOFT_MINIO_SMOKE=1`` idiom), so it never runs
  in CI and can never false-red on a slow runner. It asserts nothing about time.
  Run it with::

      LOFT_SCALING_BENCH=1 uv run pytest \\
        services/geometry/tests/test_scaling_benchmarks.py -m benchmark -s

  It prints the markdown tables that docs/PERF.md is written from. The double
  gate is deliberate: ``just bench`` (``-m benchmark``) must stay a few-minute
  human-watched run, and the full sweep is ~10 minutes.
* The **correctness-under-size gates** below are UNMARKED and DO run in the
  default suite, because "does a big part still produce a valid solid and a STEP
  that round-trips" is a correctness question, not a timing one, and a fast wrong
  answer is worse than a slow right one. They use the SMALL end of each sweep
  (29 features / 32 fins, ~1.5 s total) so the always-on cost is negligible.
"""

from __future__ import annotations

import gzip
import importlib.util
import os
import resource
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

# build123d's STEP I/O carries Shape[Unknown] type params — the same gap
# test_step_roundtrip.py documents; scoped ignores only.
import pytest
from build123d import (
    Compound,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.features import evaluate as evaluate_module
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from geometry.kernel.export import export_step_bytes, export_stl_bytes
from geometry.kernel.healing import body_is_valid
from geometry.kernel.tessellate import tessellate_glb
from geometry.overlay import evaluate_overlay
from geometry.schemas import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
)
from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.overlay import MAX_PROVENANCE_FACES, OverlayRequest

_HERE = Path(__file__).resolve().parent
_BUILDERS_PATH = _HERE / "_big_part_builders.py"

#: Feature-count sweep points (the brief's 10/25/50/100/200). The tray's base
#: block is 5 features, so 10 is the smallest meaningful point.
FEATURE_SWEEP: tuple[int, ...] = (10, 25, 50, 100, 200)
#: Face-count sweep points, as FIN COUNTS. 500 is MAX_PATTERN_COUNT (the shipped
#: work bound), so 500 fins is the largest part this vocabulary can express in
#: one pattern feature — deliberately included to measure the ceiling itself.
FIN_SWEEP: tuple[int, ...] = (8, 32, 64, 128, 256, 500)
#: Samples per point; the reported number is the MEDIAN (a single sample is noise).
SAMPLES = 3

#: Small, always-on correctness sizes (see the tier policy in the docstring).
GATE_FEATURES = 29
GATE_FINS = 32


def _load_builders() -> ModuleType:
    """Load the tree builders by file path (importlib import-mode: test modules
    cannot import each other by name — root pyproject.toml)."""
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BUILDERS = _load_builders()
housing_tree = cast(Callable[[int], dict[str, Any]], _BUILDERS.housing_tree)
heat_sink_tree = cast(Callable[[int], dict[str, Any]], _BUILDERS.heat_sink_tree)


def _request(payload: dict[str, Any]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(payload)


def _failed_features(request: EvaluateTreeRequest, evaluation: Any) -> list[str]:
    """``index:type:status:code`` for every feature that did not evaluate ok."""
    return [
        f"{index}:{request.features[index].feature.type}:{result.status}:"
        f"{result.error.code if result.error else '-'}"
        for index, result in enumerate(evaluation.result.features)
        if result.status != "ok"
    ]


def _rss_mb() -> float:
    """Resident set size of this process, MiB (``/proc/self/status`` VmRSS)."""
    for line in Path("/proc/self/status").read_text("utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return float(line.split()[1]) / 1024.0
    return float("nan")


def _peak_rss_mb() -> float:
    """Process high-water RSS, MiB (``ru_maxrss`` is KiB on Linux)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _time_once(thunk: Callable[[], object]) -> float:
    start = time.perf_counter()
    thunk()
    return (time.perf_counter() - start) * 1000.0


def _median_ms(thunk: Callable[[], object], samples: int = SAMPLES) -> float:
    """Median wall-clock of *samples* runs, in ms. One untimed warmup first, so
    cold OCCT/import effects never land in the reported number."""
    thunk()
    return statistics.median([_time_once(thunk) for _ in range(samples)])


@dataclass(frozen=True)
class ScalePoint:
    """One measured sweep point. Times are medians of :data:`SAMPLES` runs."""

    label: str
    features: int
    rebuild_ms: float
    tessellate_ms: float
    dominant: str
    faces: int
    edges: int
    triangles: int
    glb_bytes: int
    glb_gzip_bytes: int
    step_ms: float
    step_bytes: int
    stl_ms: float
    stl_bytes: int
    overlay_ms: float
    provenance_attributed: bool
    rss_mb: float
    peak_rss_mb: float
    volume: float


def _profile_by_feature_type(
    request: EvaluateTreeRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, tuple[int, float]]:
    """One instrumented rebuild: ``{feature type: (calls, total ms)}``.

    Wraps every entry of ``geometry.features.evaluate.FEATURE_HANDLERS``.
    ``_dispatch`` looks the handler up in that module global per call, so
    patching the dict is enough and no evaluation logic is duplicated.
    """
    totals: dict[str, list[float]] = {}
    original = dict(evaluate_module.FEATURE_HANDLERS)

    def wrap(name: str, handler: Any) -> Any:
        def timed(item: Any, state: Any) -> Any:
            start = time.perf_counter()
            try:
                return handler(item, state)
            finally:
                elapsed = (time.perf_counter() - start) * 1000.0
                totals.setdefault(name, []).append(elapsed)

        return timed

    monkeypatch.setattr(
        evaluate_module,
        "FEATURE_HANDLERS",
        {name: wrap(name, handler) for name, handler in original.items()},
    )
    evaluate_tree(request)
    return {name: (len(times), sum(times)) for name, times in totals.items()}


def _measure(
    label: str, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> ScalePoint:
    """Rebuild, tessellate, overlay and export one part; record every metric."""
    request = _request(payload)
    evaluation = evaluate_tree(request)
    failures = _failed_features(request, evaluation)
    assert not failures, f"{label}: benchmark tree did not evaluate clean: {failures}"
    body = evaluation.body
    properties = evaluation.result.properties
    mesh = evaluation.mesh
    assert body is not None and properties is not None and mesh is not None

    rebuild_ms = _median_ms(lambda: evaluate_tree(request))
    tessellate_ms = _median_ms(
        lambda: tessellate_glb(body, request.linear_deflection or 0.1)
    )
    step_bytes = export_step_bytes(body)
    step_ms = _median_ms(lambda: export_step_bytes(body))
    stl_bytes = export_stl_bytes(
        body, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
    )
    stl_ms = _median_ms(
        lambda: export_stl_bytes(
            body, DEFAULT_LINEAR_DEFLECTION, DEFAULT_ANGULAR_DEFLECTION
        )
    )

    overlay_request = OverlayRequest(tree=request)
    overlay = evaluate_overlay(overlay_request)
    overlay_ms = _median_ms(lambda: evaluate_overlay(overlay_request))
    attributed = any(face.feature_id is not None for face in overlay.faces)

    by_type = _profile_by_feature_type(request, monkeypatch)
    dominant = "-"
    if by_type:
        name, (calls, total) = max(by_type.items(), key=lambda kv: kv[1][1])
        share = 100.0 * total / max(sum(t for _c, t in by_type.values()), 1e-9)
        dominant = f"{name} ({share:.0f}%, {calls}x)"

    return ScalePoint(
        label=label,
        features=len(request.features),
        rebuild_ms=rebuild_ms,
        tessellate_ms=tessellate_ms,
        dominant=dominant,
        faces=properties.topology.faces,
        edges=properties.topology.edges,
        triangles=mesh.triangles,
        glb_bytes=mesh.glb_bytes,
        glb_gzip_bytes=len(gzip.compress(evaluation.glb or b"", 6)),
        step_ms=step_ms,
        step_bytes=len(step_bytes),
        stl_ms=stl_ms,
        stl_bytes=len(stl_bytes),
        overlay_ms=overlay_ms,
        provenance_attributed=attributed,
        rss_mb=_rss_mb(),
        peak_rss_mb=_peak_rss_mb(),
        volume=properties.volume,
    )


def _table(title: str, axis: str, points: list[ScalePoint]) -> str:
    header = (
        f"| {axis} | feats | rebuild ms | tess ms | dominant feature | faces | "
        "edges | tris | GLB KiB | GLB gz KiB | STEP ms | STEP KiB | STL ms | "
        "STL KiB | overlay ms | prov | RSS MiB |"
    )
    rule = "| --- |" + " ---: |" * 15 + " ---: |"
    rows = [
        f"| {p.label} | {p.features} | {p.rebuild_ms:.0f} | {p.tessellate_ms:.0f} | "
        f"{p.dominant} | {p.faces} | {p.edges} | {p.triangles} | "
        f"{p.glb_bytes / 1024:.0f} | {p.glb_gzip_bytes / 1024:.0f} | "
        f"{p.step_ms:.0f} | {p.step_bytes / 1024:.0f} | {p.stl_ms:.0f} | "
        f"{p.stl_bytes / 1024:.0f} | {p.overlay_ms:.0f} | "
        f"{'yes' if p.provenance_attributed else 'NULL'} | {p.rss_mb:.0f} |"
        for p in points
    ]
    return "\n".join(["", f"### {title}", "", header, rule, *rows])


def _machine() -> str:
    return (
        f"nproc={os.cpu_count()}  "
        f"MemTotal={_meminfo_gib():.1f} GiB  "
        f"samples/point={SAMPLES} (median)"
    )


def _meminfo_gib() -> float:
    for line in Path("/proc/meminfo").read_text("utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return float(line.split()[1]) / (1024.0 * 1024.0)
    return float("nan")


# --- Correctness under size (UNMARKED — runs in the default suite) --------------


@pytest.mark.parametrize(
    ("label", "payload_fn", "size"),
    [
        ("housing", housing_tree, GATE_FEATURES),
        ("heat-sink", heat_sink_tree, GATE_FINS),
    ],
)
def test_big_part_rebuilds_to_a_valid_solid(
    label: str, payload_fn: Callable[[int], dict[str, Any]], size: int
) -> None:
    """A multi-feature / multi-hundred-face part is a VALID solid, not just a fast
    one. Every feature ``ok``, positive volume, and ``BRepCheck`` clean — the same
    predicate the feature evaluator installs bodies through
    (:func:`geometry.kernel.healing.body_is_valid`). A silent invalid body is the
    P0 this gate exists to catch, and it is size-dependent: booleans that pass on
    a 3-feature toy can weld a void shut on a 30-feature one."""
    request = _request(payload_fn(size))
    evaluation = evaluate_tree(request)
    assert not _failed_features(request, evaluation)
    body = evaluation.body
    properties = evaluation.result.properties
    assert body is not None and properties is not None
    assert properties.volume > 0.0
    assert body_is_valid(body), (
        f"{label}({size}) rebuilt to a BRepCheck-INVALID solid — a wrong body "
        "reachable from the UI, not a tolerance question."
    )


@pytest.mark.parametrize(
    ("label", "payload_fn", "size"),
    [
        ("housing", housing_tree, GATE_FEATURES),
        ("heat-sink", heat_sink_tree, GATE_FINS),
    ],
)
def test_big_part_step_round_trip_preserves_mass_and_topology(
    label: str,
    payload_fn: Callable[[int], dict[str, Any]],
    size: int,
    tmp_path: Path,
    assert_roundtrip_preserved: Callable[[str, Any, Any], None],
) -> None:
    """Gate 2 (round-trip fidelity) at SIZE, not on a box.

    Same bound as every other round-trip gate — the shared ``ROUNDTRIP_TOL``
    conftest fixture (1e-7, the CLAUDE.md kernel linear tolerance), and topology
    counts exactly. Deliberately NOT a size-scaled epsilon: a deviation that
    appears only on a big part is a defect in export/import, and hiding it behind
    a looser bound is the failure mode this suite exists to prevent."""
    request = _request(payload_fn(size))
    evaluation = evaluate_tree(request)
    body = evaluation.body
    assert body is not None
    original = measure_shape(body)

    path = tmp_path / f"{label}-{size}.step"
    assert export_step(body, path)
    imported = import_step(path)
    solids = imported.solids()
    shape = solids[0] if len(solids) == 1 else Compound(list(solids))
    assert_roundtrip_preserved(f"{label}({size})", measure_shape(shape), original)


@pytest.mark.parametrize(
    ("label", "payload_fn", "size"),
    [
        ("housing", housing_tree, GATE_FEATURES),
        ("heat-sink", heat_sink_tree, GATE_FINS),
    ],
)
def test_big_part_rebuild_is_deterministic(
    label: str, payload_fn: Callable[[int], dict[str, Any]], size: int
) -> None:
    """Gate 3 (determinism) at size: two rebuilds of the same tree produce a
    byte-identical GLB and identical mass properties. Determinism is where a big
    part is most at risk — more booleans, more unordered kernel containers."""
    request = _request(payload_fn(size))
    first, second = evaluate_tree(request), evaluate_tree(request)
    assert first.glb is not None and second.glb is not None
    assert first.glb == second.glb, f"{label}({size}): GLB differs between rebuilds"
    assert first.result.properties == second.result.properties


def test_provenance_bound_is_reachable_by_an_authored_part() -> None:
    """The :data:`MAX_PROVENANCE_FACES` docstring claims "an authored part is
    nowhere near the bound (tens of body-affecting features x tens-to-low-hundreds
    of faces each), so a working engineer never feels it."

    The bound is the SUM over snapshots (``len(final faces) + sum(len(snapshot
    faces))``), so it is spent by FEATURE COUNT x face count, not by face count
    alone. This test pins the arithmetic that decides whether that claim holds for
    the tray, so a change to the bound or to the snapshot policy shows up here
    rather than as a silently-null overlay in the UI. It asserts only the ceiling
    value and the shape of the budget — the measured crossing point lives in
    docs/PERF.md."""
    assert MAX_PROVENANCE_FACES == 8_000
    request = _request(housing_tree(GATE_FEATURES))
    evaluation = evaluate_tree(request, record_history=True)
    body = evaluation.body
    assert body is not None
    budget = len(body.faces()) + sum(
        len(snapshot.faces()) for _feature_id, snapshot in evaluation.body_history
    )
    # A 29-feature part must still be under the bound; if this ever trips, the
    # overlay is silently returning null attribution for ordinary parts.
    assert budget < MAX_PROVENANCE_FACES, (
        f"a {GATE_FEATURES}-feature part already spends {budget} of the "
        f"{MAX_PROVENANCE_FACES} provenance budget — feature-localized selection "
        "highlighting is off for real parts (docs/PERF.md)."
    )


# --- The sweep (benchmark-marked AND env-gated; never a CI gate) ----------------


@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("LOFT_SCALING_BENCH") != "1",
    reason="scaling sweep is opt-in: set LOFT_SCALING_BENCH=1 (see module docstring)",
)
def test_record_scaling_tables(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sweep both axes and print the markdown tables docs/PERF.md is written from.

    Asserts nothing about time. The only assertions are correctness ones that
    would invalidate a measurement (every feature ``ok``, a body exists) — a
    number measured on a broken rebuild is worse than no number."""
    feature_points = [
        _measure(f"N={n}", housing_tree(n), monkeypatch) for n in FEATURE_SWEEP
    ]
    fin_points = [
        _measure(f"{k} fins", heat_sink_tree(k), monkeypatch) for k in FIN_SWEEP
    ]
    with capsys.disabled():
        print(f"\n{_machine()}")
        print(
            _table(
                "Axis A - feature count (shelled tray lid, mixed vocabulary)",
                "part",
                feature_points,
            )
        )
        print(
            _table(
                "Axis B - face count (finned heat sink, 6 features throughout)",
                "part",
                fin_points,
            )
        )
        print("\n### Per-feature-type cost, N=200 tray (one instrumented rebuild)\n")
        by_type = _profile_by_feature_type(_request(housing_tree(200)), monkeypatch)
        total = sum(t for _c, t in by_type.values())
        print("| feature type | calls | total ms | ms/call | share |")
        print("| --- | ---: | ---: | ---: | ---: |")
        for name, (calls, elapsed) in sorted(by_type.items(), key=lambda kv: -kv[1][1]):
            print(
                f"| {name} | {calls} | {elapsed:.0f} | {elapsed / calls:.1f} | "
                f"{100.0 * elapsed / total:.1f}% |"
            )
    for point in feature_points + fin_points:
        assert point.volume > 0.0


@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("LOFT_SCALING_BENCH") != "1",
    reason="scaling sweep is opt-in: set LOFT_SCALING_BENCH=1 (see module docstring)",
)
def test_record_provenance_budget_crossing(capsys: pytest.CaptureFixture[str]) -> None:
    """Find the tray size at which per-face provenance goes dark.

    ``attribute_faces`` skips attribution (returns all-``None``) once ``len(final
    faces) + sum(len(snapshot faces))`` exceeds :data:`MAX_PROVENANCE_FACES`. That
    budget is quadratic-ish in tree length for a growing part, so the interesting
    number is the FEATURE COUNT at which feature-localized selection highlighting
    silently stops working in the viewport. Printed, never asserted."""
    rows: list[tuple[int, int, int, bool, float]] = []
    for n in (10, 25, 50, 75, 100, 150, 200):
        request = _request(housing_tree(n))
        start = time.perf_counter()
        overlay = evaluate_overlay(OverlayRequest(tree=request))
        elapsed = (time.perf_counter() - start) * 1000.0
        evaluation = evaluate_tree(request, record_history=True)
        body = evaluation.body
        assert body is not None
        budget = len(body.faces()) + sum(
            len(snapshot.faces()) for _fid, snapshot in evaluation.body_history
        )
        rows.append(
            (
                n,
                budget,
                len(overlay.faces),
                any(f.feature_id is not None for f in overlay.faces),
                elapsed,
            )
        )
    with capsys.disabled():
        print("\n### Provenance budget vs tray size\n")
        print(
            f"| features | provenance budget | /{MAX_PROVENANCE_FACES} | overlay "
            "faces | attributed | overlay ms |"
        )
        print("| ---: | ---: | ---: | ---: | --- | ---: |")
        for n, budget, faces, attributed, elapsed in rows:
            print(
                f"| {n} | {budget} | {100.0 * budget / MAX_PROVENANCE_FACES:.0f}% | "
                f"{faces} | {'yes' if attributed else 'NULL'} | {elapsed:.0f} |"
            )


def test_builders_produce_distinct_parts() -> None:
    """A collection/builder breakage must fail loudly, never silently measure the
    same toy twice."""
    tray = _request(housing_tree(50))
    sink = _request(heat_sink_tree(32))
    assert tray.part_id != sink.part_id
    assert len(tray.features) == 50
    assert len(sink.features) == _BUILDERS.HEAT_SINK_FEATURES
    assert {f.feature.type for f in tray.features} >= {
        "sketch",
        "extrude",
        "fillet",
        "shell",
        "hole",
        "datum",
        "revolve",
        "pattern",
        "mirror",
    }
