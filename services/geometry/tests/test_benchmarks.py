"""Performance benchmark suite — gate 4 of the geometry QA strategy
(docs/RESEARCH.md §9, .claude/skills/geometry-gates/SKILL.md).

Two deliberately-separate tiers over a corpus of REAL operations run on the
shipped golden bodies/parts (not toys), so the suite always measures what a
working engineer actually does:

**Tier 1 — CI tripwires (asserted, in the DEFAULT pytest path).** Every case
below asserts its warm wall-clock is under a GENEROUS ceiling
(:data:`CEILING_LIGHT_MS` / :data:`CEILING_HEAVY_MS`). These exist to catch a
gross regression or a DoS — a 5-10x+ blowup, or the RESEARCH §9 2 s rebuild
ceiling — NOT a 20% drift. A tight perf bound flakes under CI CPU contention
(shared runners, concurrent jobs), and a false-red perf gate is worse than no
gate, so each ceiling is 18x-1000x the measured warm median across the corpus
(2026-07-19 baseline, docs/GEOMETRY-QA.md): even a 4x contention slowdown
leaves >=4x of headroom, so these essentially never false-red on a healthy
machine under load. Each case is warmed once (cold OCCT/import effects
discarded) then timed best-of-N so the tripwire reads warm time, not a cold
outlier.

**Tier 2 — detailed timings (opt-in, `-m benchmark`).** A single benchmark
test measures a fixed-warmup median/p95 for every case and prints a markdown
table for humans to watch trends and refresh docs/GEOMETRY-QA.md. It is
EXCLUDED from the default suite (root pyproject `addopts = "... -m 'not
benchmark'"`) because it is heavy (median-of-N per case); it NEVER asserts a
tight bound. Run it with ``just bench`` (or ``uv run pytest
tests/test_benchmarks.py -m benchmark -s``).

DRY: the inputs are the existing goldens/fixtures — the same feature trees,
sheet-metal trees, drawing request, assembly requests, and primitive shapes
the correctness gates already lock — so a new capability's golden gets a warm
budget for free and no benchmark body is authored twice (CLAUDE.md DRY rule).
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# build123d STEP I/O carries Shape[Unknown]/PathLike[Unknown] type params — the
# same gap test_step_roundtrip.py documents; scoped ignores only.
import pytest
from build123d import (
    Compound,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from geometry.assembly import evaluate_assembly
from geometry.drawings import (
    evaluate_drawing_views,
    place_sheet,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from geometry.harness import build_model_solid, evaluate_model, load_model_request
from geometry.kernel import measure_shape
from geometry.kernel.tessellate import tessellate_glb
from geometry.overlay import evaluate_overlay
from geometry.schemas import DEFAULT_LINEAR_DEFLECTION
from py_kit.schemas.assemblies import EvaluateAssemblyRequest
from py_kit.schemas.drawings import (
    ComposeDrawingRequest,
    SheetLayout,
    SheetPoint,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.overlay import OverlayRequest

_GEO_ROOT = Path(__file__).resolve().parent.parent
_GOLDENS = _GEO_ROOT / "goldens"
_GOLDENS_SM = _GEO_ROOT / "goldens-sheet-metal"
_GOLDENS_ASM = _GEO_ROOT / "goldens-assembly"
_COMPOSE_GOLDEN = Path(__file__).resolve().parent / "compose_goldens" / "request.json"

# --- CI ceiling policy (generous DoS/gross-regression tripwires) ---------------
#: Ceiling (ms) for LIGHT operations (measured warm median < 40 ms: tessellation,
#: single-body trees, booleans, the STEP box round-trip, the L-bracket unfold).
#: 1000 ms is 28x-500x the warm median of every light case (docs/GEOMETRY-QA.md
#: 2026-07-19), so a 4x CI-contention slowdown still clears it >=7x. Sized to
#: catch a gross regression/DoS, never a drift — the detailed tier tracks drift.
CEILING_LIGHT_MS = 1000.0
#: Ceiling (ms) for HEAVY operations (warm median >= 40 ms: multi-feature/dense
#: trees, drawing HLR+compose+serialize, assembly solves, the U-channel unfold).
#: 2000 ms is the RESEARCH §9 rebuild ceiling and 16x-33x the warm median of
#: every heavy case, so a 4x contention slowdown clears it >=4x. Same posture:
#: a DoS/gross-regression tripwire, not a drift detector.
CEILING_HEAVY_MS = 2000.0

#: Timed thunk: runs ONE operation, setup already done (never timed).
Thunk = Callable[[], object]
#: Case factory: does the (untimed) setup and returns the timed thunk.
Factory = Callable[[], Thunk]


@dataclass(frozen=True)
class BenchCase:
    """One benchmarked operation: its group, id, generous CI ceiling, and a
    factory that performs setup once and returns the timed thunk."""

    group: str
    name: str
    ceiling_ms: float
    factory: Factory


_SCALE = ViewScale(numerator=1, denominator=1)


def _tree_model(golden: str) -> object:
    return load_model_request((_GOLDENS / golden / "model.json").read_text("utf-8"))


def _tree_eval_factory(golden: str) -> Factory:
    """Full feature-tree evaluate (solve -> features -> GProp -> tessellate),
    the same path the REST route and worker share."""

    def factory() -> Thunk:
        request = _tree_model(golden)
        return lambda: evaluate_model(request)  # type: ignore[arg-type]

    return factory


def _overlay_factory(golden: str) -> Factory:
    """The INTERACTIVE selection round trip: recompute the tree, attribute every
    face to its feature, and build the pickable overlay — the exact work
    ``POST /api/v1/overlay`` does on a face pick / feature select.

    Budgeted because per-face provenance made this route super-linear in face
    count (audit H4) and it is the one route a user hits on every click; the
    matcher is indexed and the pass is bounded now, and this ceiling is the
    tripwire that keeps it that way."""

    def factory() -> Thunk:
        request = OverlayRequest(tree=_tree_model(golden))  # type: ignore[arg-type]
        return lambda: evaluate_overlay(request)

    return factory


def _tessellate_factory(golden: str) -> Factory:
    """Isolated tessellation (GLB) of a pre-built B-rep — build cost excluded."""

    def factory() -> Thunk:
        solid = build_model_solid(_tree_model(golden))  # type: ignore[arg-type]
        return lambda: tessellate_glb(solid, DEFAULT_LINEAR_DEFLECTION)

    return factory


def _step_roundtrip_factory(golden: str) -> Factory:
    """Export a pre-built solid to STEP, re-import, re-measure — gate 2's path."""

    def factory() -> Thunk:
        solid = build_model_solid(_tree_model(golden))  # type: ignore[arg-type]

        def run() -> object:
            with tempfile.TemporaryDirectory(prefix="loft-bench-step-") as tmp:
                path = Path(tmp) / "s.step"
                export_step(solid, path)
                imported = import_step(path)
                solids = imported.solids()
                shape = solids[0] if len(solids) == 1 else Compound(list(solids))
                return measure_shape(shape)

        return run

    return factory


def _assembly_factory(golden: str) -> Factory:
    """Assembly evaluate: multi-instance placement solve + mass-property roll-up."""

    def factory() -> Thunk:
        request = EvaluateAssemblyRequest.model_validate_json(
            (_GOLDENS_ASM / golden / "model.json").read_text("utf-8")
        )
        return lambda: evaluate_assembly(request)

    return factory


def _flat_pattern_factory(base: str) -> Factory:
    """Sheet-metal unfold + flat-pattern sheet compose (L-bracket / U-channel):
    evaluate the sheet-metal tree, unfold to a flat blank, compose onto a sheet
    (the same request test_sheet_metal_flat_pattern_sheet.py builds)."""

    def factory() -> Thunk:
        view_model = _GOLDENS_SM / f"{base}-flat-pattern-view" / "model.json"
        tree = EvaluateTreeRequest.model_validate_json(view_model.read_text("utf-8"))
        expected = json.loads(
            (_GOLDENS_SM / f"{base}-flat-pattern-sheet" / "expected.json").read_text(
                "utf-8"
            )
        )
        request = ComposeDrawingRequest(
            part_id=tree.part_id,
            tree_version=tree.tree_version,
            features=tree.features,
            views=["flat_pattern"],
            scale=_SCALE,
            dimensions=[],
            layout=SheetLayout(
                size=expected["sheet_size"],
                orientation="landscape",
                title=expected["title"],
                views=[
                    SheetViewPlacement(
                        projection="flat_pattern",
                        position=SheetPoint(x_mm=0.0, y_mm=0.0),
                        scale=_SCALE,
                    )
                ],
            ),
            format="svg",
        )

        def run() -> object:
            evaluation = evaluate_drawing_views(request)
            return place_sheet(evaluation, request.dimensions, request.layout)

        return run

    return factory


def _drawing_factory(fmt: str) -> Factory:
    """Drawing HLR projection + sheet compose + serialize (SVG/PDF/DXF) of the
    plate compose golden (box + Ø10 hole, 4 views, dims)."""

    serialize: Callable[[object], object] = {
        "svg": serialize_svg,
        "pdf": serialize_pdf,
        "dxf": serialize_dxf,
    }[fmt]  # type: ignore[assignment]

    def factory() -> Thunk:
        request = ComposeDrawingRequest.model_validate_json(
            _COMPOSE_GOLDEN.read_text("utf-8")
        )

        def run() -> object:
            evaluation = evaluate_drawing_views(request)
            composed = place_sheet(evaluation, request.dimensions, request.layout)
            return serialize(composed)

        return run

    return factory


#: The benchmarked corpus — every group a working engineer exercises, keyed to a
#: real golden/fixture (DRY). Ceilings from the two-bucket policy above.
_L = CEILING_LIGHT_MS
_H = CEILING_HEAVY_MS
CASES: list[BenchCase] = [
    # Feature-tree evaluation (sketch -> extrude -> pattern/cut/fillet/shell).
    BenchCase(
        "tree",
        "plate-6hole-ring-cut",
        _H,
        _tree_eval_factory("sketch-extrude-plate-6hole-ring-cut-60x60x10"),
    ),
    BenchCase(
        "tree",
        "pattern-cut-6hole-boltcircle",
        _H,
        _tree_eval_factory("pattern-cut-6hole-boltcircle-60x60x10"),
    ),
    BenchCase(
        "tree",
        "shell-open-top-box",
        _L,
        _tree_eval_factory("shell-open-top-box-40x25x10-t2"),
    ),
    BenchCase(
        "tree", "fillet-top-edge", _L, _tree_eval_factory("fillet-top-edge-40x25x10-r5")
    ),
    # The v2 `features`-scope mirror: k selected features cost k exact reflections
    # + k booleans (docs/design/mirror-semantics.md §9 asks for a rebuild-time
    # assertion on the new goldens rather than a claim in prose). This golden is the
    # heaviest of the three — a cut of a reflected bore plus a fuse of a reflected
    # prism, on top of the hole and boss the chain already builds.
    BenchCase(
        "tree",
        "mirror-features-hole-boss",
        _H,
        _tree_eval_factory("mirror-features-hole-boss-plate-40x40x20"),
    ),
    # Booleans (union/subtract) + fillet-on-boolean (multi-body).
    BenchCase(
        "boolean",
        "union-two-cubes-overlap",
        _L,
        _tree_eval_factory("boolean-union-two-cubes-overlap"),
    ),
    BenchCase(
        "boolean",
        "subtract-two-cubes-overlap",
        _L,
        _tree_eval_factory("boolean-subtract-two-cubes-overlap"),
    ),
    BenchCase(
        "boolean",
        "union-then-fillet",
        _L,
        _tree_eval_factory("boolean-union-then-fillet"),
    ),
    # Interactive selection overlay (recompute + per-face provenance + pick
    # geometry) — the route every viewport click hits (audit H4).
    BenchCase(
        "overlay",
        "plate-6hole-ring-cut",
        _H,
        _overlay_factory("sketch-extrude-plate-6hole-ring-cut-60x60x10"),
    ),
    BenchCase(
        "overlay",
        "pattern-cut-6hole-boltcircle",
        _H,
        _overlay_factory("pattern-cut-6hole-boltcircle-60x60x10"),
    ),
    # Tessellation (GLB): a primitive, a curved primitive, and a dense body.
    BenchCase("tessellate", "box-primitive", _L, _tessellate_factory("box-10x20x30")),
    BenchCase(
        "tessellate", "cylinder-curved", _L, _tessellate_factory("cylinder-r10-h25")
    ),
    BenchCase(
        "tessellate",
        "complex-6hole-plate",
        _L,
        _tessellate_factory("pattern-cut-6hole-boltcircle-60x60x10"),
    ),
    # STEP export -> re-import round-trip (gate 2 path).
    BenchCase("step_roundtrip", "box", _L, _step_roundtrip_factory("box-10x20x30")),
    BenchCase(
        "step_roundtrip",
        "complex-6hole-plate",
        _H,
        _step_roundtrip_factory("pattern-cut-6hole-boltcircle-60x60x10"),
    ),
    # Sheet-metal unfold + flat-pattern compose (the new pillar).
    BenchCase(
        "sheet_metal", "l-bracket-flat-pattern", _L, _flat_pattern_factory("l-bracket")
    ),
    BenchCase(
        "sheet_metal", "u-channel-flat-pattern", _H, _flat_pattern_factory("u-channel")
    ),
    # Drawing HLR projection + sheet compose + serialize.
    BenchCase("drawing", "hlr-compose-svg", _H, _drawing_factory("svg")),
    BenchCase("drawing", "hlr-compose-pdf", _H, _drawing_factory("pdf")),
    BenchCase("drawing", "hlr-compose-dxf", _H, _drawing_factory("dxf")),
    # Assembly evaluate (multi-instance + mate solve).
    BenchCase(
        "assembly",
        "two-plates-bolted",
        _H,
        _assembly_factory("assembly-two-plates-bolted"),
    ),
    BenchCase(
        "assembly", "two-plates-gap", _H, _assembly_factory("assembly-two-plates-gap")
    ),
]

_IDS = [f"{c.group}:{c.name}" for c in CASES]


def _time_once(thunk: Thunk) -> float:
    """Wall-clock a single thunk call, in milliseconds."""
    start = time.perf_counter()
    thunk()
    return (time.perf_counter() - start) * 1000.0


def test_benchmark_corpus_is_nonempty() -> None:
    """A collection breakage must fail loudly, never silently skip the gate."""
    assert CASES, "no benchmark cases discovered"


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_operation_within_ci_ceiling(case: BenchCase) -> None:
    """CI tripwire (tier 1): warm wall-clock under the generous ceiling.

    One warmup (cold OCCT/import effects discarded) then best-of-2 timed — the
    minimum is the warmest, contention-free reading, so this reads warm time and
    never false-reds on a cold outlier. The ceiling is a DoS/gross-regression
    tripwire (18x-1000x warm), NOT a drift bound — see the module docstring and
    docs/GEOMETRY-QA.md. Loosening it is a reviewed decision recorded there, not
    a quick fix; a genuine >5-10x blowup is a defect to root-cause, not to widen.
    """
    run = case.factory()
    run()  # warmup — discard the cold reading
    best_ms = min(_time_once(run), _time_once(run))
    assert best_ms < case.ceiling_ms, (
        f"{case.group}:{case.name}: warm best {best_ms:.1f} ms exceeded the "
        f"{case.ceiling_ms:.0f} ms CI ceiling. This ceiling is 18x-1000x the "
        f"documented warm baseline (docs/GEOMETRY-QA.md) — a breach is a gross "
        f"regression or a DoS to root-cause (sketch/solver/feature-eval/"
        f"tessellation/export), never a bound to loosen."
    )


@pytest.mark.benchmark
def test_record_detailed_timings(capsys: pytest.CaptureFixture[str]) -> None:
    """Detailed tier (tier 2, opt-in `-m benchmark`): fixed-warmup median/p95 per
    case, printed as a markdown table for docs/GEOMETRY-QA.md. Asserts NOTHING
    tight — it records numbers, it does not gate. Run via ``just bench``."""
    warmup, samples = 2, 15
    rows: list[tuple[str, str, float, float, float]] = []
    for case in CASES:
        run = case.factory()
        for _ in range(warmup):
            run()
        times = sorted(_time_once(run) for _ in range(samples))
        median = statistics.median(times)
        # p95 by nearest-rank on the sorted samples (small-N stable).
        p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
        rows.append((case.group, case.name, median, p95, case.ceiling_ms))

    lines = [
        "",
        f"### Benchmark detail (warmup={warmup}, median-of-{samples})",
        "",
        "| group | operation | median ms | p95 ms | CI ceiling ms |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    lines += [
        f"| {g} | {n} | {med:.2f} | {p95:.2f} | {ceil:.0f} |"
        for (g, n, med, p95, ceil) in rows
    ]
    table = "\n".join(lines)
    with capsys.disabled():
        print(table)

    # Sanity only (NOT a perf gate): every recorded median is comfortably under
    # its ceiling — if this ever fails the ceiling policy itself needs review.
    for g, n, med, _p95, ceil in rows:
        assert med < ceil, f"{g}:{n} median {med:.1f} ms >= ceiling {ceil:.0f} ms"
