#!/usr/bin/env python3
"""The real-part gauntlet — the bar this project is graded against.

WHY THIS EXISTS. The golden suite is 87 models and the largest authored one is a
100 x 100 x 14 mm plate. The discipline in those goldens is excellent — analytic
values derived by hand, per-model tolerance rationale, an explicit refusal to pin
GLB byte size because it has no geometric meaning — but it is rigour at a scale
that *cannot fail for the reasons a daily driver fails*. A tool that is correct
on a 40 mm block with two features has proved nothing about the part a working
engineer opens on a Tuesday.

`docs/PERF.md` already closed half of that gap in 2026-07-31: the scaling sweep
(`services/geometry/tests/test_scaling_benchmarks.py`) drives a *generated* tray
to 200 features and a heat sink to 2 006 faces, and it found the N^1.85 rebuild
curve and the provenance cliff. This script does NOT duplicate that. It adds the
axis that generator structurally cannot reach:

    a REAL part, made by somebody else, in somebody else's CAD system.

An imported B-rep has no feature history, so it cannot test rebuild depth — and a
generated tree has no import, no foreign tolerances, no 211-solid assembly and no
solid whose boundary is three shells. The two axes fail differently and both are
required, so this script runs both and reports them side by side.

THE FIXTURES ARE FETCHED, NEVER COMMITTED. `services/geometry/goldens-gauntlet/
fixtures.json` carries a URL, a sha256 and the provenance read out of each file's
own ISO-10303-21 HEADER. Every one of them is all-rights-reserved or a named
third party's upload, so this repository redistributes none of them; it downloads
them into a gitignored cache, measures, and reports. See that manifest's comment
for why that is a licence decision rather than a convenience.

HONESTY RULES BUILT INTO THE OUTPUT

* Every run prints the load average and core count it ran under. A number with no
  load stated is not a measurement, and this container hosts several agents.
* A failure is a RESULT, not an error. If an import blows its budget, if a part
  will not round-trip, if an incremental edit rebuilds the world, the row says so
  and the run still completes. Nothing here tunes a fixture until it passes.
* Counts are asserted, not assumed. A leg that measures zero parts, or a deep
  tree whose motif sites have wrapped onto each other, REFUSES rather than
  reporting a vacuous pass — the failure mode this repo has paid for repeatedly
  (a gate that examines nothing passes happily).

USAGE

    just gauntlet                  # both legs, markdown to stdout
    uv run python scripts/gauntlet.py --leg import
    uv run python scripts/gauntlet.py --leg deep --json out.json

CI. Deliberately NOT wired into any workflow. The deep leg alone is ~6 minutes
on this container and the import leg needs egress to raw.githubusercontent.com;
both are far too slow for every push, and a timing gate on a shared runner is a
false-red machine (docs/PERF.md's standing rule). It is written to be runnable
unattended — `--json` emits a machine-readable record — so a nightly job can
adopt it without touching this file. That is the right home for it.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import resource
import statistics
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "services" / "geometry" / "goldens-gauntlet" / "fixtures.json"
DEFAULT_CACHE = REPO / ".gauntlet-cache"

#: Samples per timed point. The deep leg's rebuilds are tens of seconds, so this
#: is deliberately small; the spread is reported alongside the median rather than
#: hidden by it.
SAMPLES = 3

# --- Deep-part sweep -----------------------------------------------------------
#
# `housing_tree` lays its motifs on a SITE_COLS x SITE_ROWS grid and `_site_centre`
# takes `index % SITE_COLS` and `(index // SITE_COLS) % SITE_ROWS`, so site 96
# lands exactly on top of site 0 -- and 96 % 8 == 0 means it lands there with the
# SAME motif. Past that point the part stops growing and starts re-cutting its own
# pockets, which would read as a flattening performance curve when it is really a
# degenerate fixture. 96 sites x 21 features per 8-motif cycle / 8 + 5 base
# features = 257 is the last wrap-free length. `_assert_no_site_wrap` enforces it.
DEEP_SWEEP: tuple[int, ...] = (100, 200, 250)


def _load_test_module(name: str) -> ModuleType:
    """Load a helper from `services/geometry/tests/` by path.

    The tests directory is not an importable package (pytest runs it in importlib
    mode so module names may repeat across workspace members), so the builders
    and the kernel probes are loaded the same way a test would get them.
    """
    path = REPO / "services" / "geometry" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_no_site_wrap(builders: ModuleType, n: int) -> None:
    """Refuse a sweep point whose motif sites have wrapped onto each other.

    This is the "assert the count you expect to walk" guard. Without it the sweep
    would happily measure a 300-feature tray in which features 258+ re-cut pockets
    that already exist, and the resulting sub-linear curve would look like good
    news instead of a broken fixture.
    """
    cycle = sum(builders.MOTIF_FEATURE_COUNTS)
    sites = builders.SITE_COLS * builders.SITE_ROWS
    limit = builders.HOUSING_BASE_FEATURES + sites * cycle // len(
        builders.MOTIF_FEATURE_COUNTS
    )
    if n > limit:
        raise SystemExit(
            f"gauntlet: housing_tree({n}) exceeds the wrap-free limit of {limit} "
            f"features ({sites} sites x {cycle} features per cycle). Past the "
            f"limit motifs re-cut their own sites and the part stops growing; "
            f"widen the site grid in _big_part_builders.py before sweeping here."
        )


# --- Measurement primitives ----------------------------------------------------


def _peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _rss_mib() -> float:
    try:
        with open("/proc/self/statm") as handle:
            pages = int(handle.read().split()[1])
    except OSError:  # pragma: no cover - non-linux
        return float("nan")
    return pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)


def _ms(thunk: Callable[[], Any]) -> tuple[float, Any]:
    start = time.perf_counter()
    value = thunk()
    return (time.perf_counter() - start) * 1000.0, value


def _median_ms(thunk: Callable[[], Any], samples: int = SAMPLES) -> tuple[float, float]:
    """(median ms, spread %) over *samples* runs, after one untimed warmup."""
    thunk()
    times = [_ms(thunk)[0] for _ in range(samples)]
    median = statistics.median(times)
    spread = (max(times) - min(times)) / median * 100.0 if median else 0.0
    return median, spread


def _machine() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    mem_gib = float("nan")
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    mem_gib = int(line.split()[1]) / (1024.0 * 1024.0)
                    break
    except OSError:  # pragma: no cover
        pass
    return {
        "cores": os.cpu_count(),
        "mem_total_gib": round(mem_gib, 1),
        "loadavg": [round(load1, 2), round(load5, 2), round(load15, 2)],
        "python": sys.version.split()[0],
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# --- Fixture fetch -------------------------------------------------------------


def _fetch(entry: dict[str, Any], cache: Path) -> Path:
    """Return a local path to *entry*'s bytes, downloading once, digest-verified.

    A digest mismatch is fatal: the whole point of pinning the hash is that a
    fixture which changed upstream is a DIFFERENT part, and silently measuring it
    would make every historical number in docs/GEOMETRY-QA.md incomparable.
    """
    cache.mkdir(parents=True, exist_ok=True)

    # The manifest is committed and this is a dev script, so neither of these
    # can fire today. They cost two lines and they close the hole permanently,
    # rather than leaving it to depend on a property of the manifest that
    # nothing enforces: a `name` is about to become a FILENAME and a `url` is
    # about to be handed to `urlopen`, which also speaks `file:` and `ftp:`.
    name = str(entry["name"])
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        raise SystemExit(
            f"gauntlet: manifest entry name {name!r} is not a bare filename "
            "component — it would escape the fixture cache directory."
        )
    url = str(entry["url"])
    if not url.startswith("https://"):
        raise SystemExit(
            f"gauntlet: manifest entry {name!r} has a non-https url {url!r}. "
            "urlopen also opens `file:` and `ftp:`, so a fixture source must "
            "say https:// explicitly."
        )

    target = cache / f"{name}.stp"
    if target.exists():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest == entry["sha256"]:
            return target
        target.unlink()
    with urllib.request.urlopen(url, timeout=300) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(
            f"gauntlet: {entry['name']} digest mismatch\n"
            f"  expected {entry['sha256']}\n  got      {digest}\n"
            f"  url      {entry['url']}\n"
            "The upstream bytes changed. That is a different part; update the "
            "manifest deliberately and re-baseline, do not measure it as though "
            "it were the same fixture."
        )
    target.write_bytes(payload)
    return target


# --- Leg I: real imported parts -------------------------------------------------


@dataclass
class ImportPoint:
    name: str
    mb: float
    chars: int
    cap_pct: float
    bounded_ok: bool
    bounded_detail: str
    import_ms: float
    faces: int
    edges: int
    solids: int
    shells: int
    volume_mm3: float
    volume_converged_mm3: float
    volume_gauss_rel: float
    area_mm2: float
    tess_ms: float
    triangles: int
    glb_kib: float
    glb_gzip_kib: float
    step_export_ms: float
    step_kib: float
    reimport_ms: float
    roundtrip_volume_rel: float
    roundtrip_topology_ok: bool
    roundtrip_detail: str
    peak_rss_mib: float
    notes: list[str] = field(default_factory=lambda: [])


def _topology(body: Any) -> tuple[int, int, int, int]:
    return (
        len(body.faces()),
        len(body.edges()),
        len(body.solids()),
        len(body.shells()),
    )


def run_import_leg(cache: Path, only: set[str] | None) -> list[ImportPoint]:
    from geometry.kernel import import_step_solid, measure_shape
    from geometry.kernel.export import export_step_bytes
    from geometry.kernel.tessellate import tessellate_glb
    from loft_wire.features import MAX_INLINE_STEP_CHARS

    probes = _load_test_module("_gauntlet_probes")
    manifest = json.loads(MANIFEST.read_text())
    entries = [e for e in manifest["fixtures"] if not only or e["name"] in only]
    if not entries:
        raise SystemExit("gauntlet: import leg selected zero fixtures — refusing")

    settings = _shipped_import_bounds()
    points: list[ImportPoint] = []
    for entry in entries:
        path = _fetch(entry, cache)
        text = path.read_text(errors="replace")
        notes: list[str] = []

        # 1. The SHIPPED path, with the shipped budget. This is what a user gets.
        bounded_ok, bounded_detail = _bounded_import(text, settings)

        # 2. An unbounded parse, so the curve is measurable past the budget.
        import_ms, body = _ms(
            lambda t=text: import_step_solid(
                t, cpu_timeout_s=1800.0, wall_timeout_s=3600.0
            )
        )
        faces, edges, solids, shells = _topology(body)
        props = measure_shape(body)
        converged = float(probes.converged_volume(body))
        gauss_rel = abs(props.volume - converged) / abs(converged) if converged else 0.0

        tess_ms, (glb, mesh) = _ms(lambda b=body: tessellate_glb(b, 0.1))
        gzipped = gzip.compress(glb, compresslevel=6)

        step_ms, step_bytes = _ms(lambda b=body: export_step_bytes(b))
        step_text = step_bytes.decode("utf-8", errors="replace")
        try:
            reimport_ms, back = _ms(
                lambda t=step_text: import_step_solid(
                    t, cpu_timeout_s=1800.0, wall_timeout_s=3600.0
                )
            )
            back_props = measure_shape(back)
            back_topo = _topology(back)
            rel = (
                abs(back_props.volume - props.volume) / abs(props.volume)
                if props.volume
                else 0.0
            )
            topo_ok = back_topo == (faces, edges, solids, shells)
            rt_detail = (
                "exact"
                if topo_ok
                else f"{back_topo} != {(faces, edges, solids, shells)}"
            )
        except Exception as exc:  # a failure is a RESULT here, not an error
            reimport_ms, rel, topo_ok = float("nan"), float("nan"), False
            rt_detail = f"re-import FAILED: {type(exc).__name__}: {exc}"

        cap_pct = 100.0 * len(text) / MAX_INLINE_STEP_CHARS
        if cap_pct > 80.0:
            notes.append(f"{cap_pct:.0f}% of the {MAX_INLINE_STEP_CHARS >> 20} MiB cap")
        if not bounded_ok:
            notes.append("REJECTED by the shipped import budget")
        if gauss_rel > 1e-9:
            notes.append(
                f"the volume the product REPORTS is {gauss_rel:.2e} off the "
                f"converged integral ({props.volume:.1f} vs {converged:.1f} mm3)"
            )
        if shells > solids:
            notes.append(f"{shells} shells on {solids} solid(s) — internal voids")

        points.append(
            ImportPoint(
                name=entry["name"],
                mb=round(len(text) / 1e6, 2),
                chars=len(text),
                cap_pct=round(cap_pct, 1),
                bounded_ok=bounded_ok,
                bounded_detail=bounded_detail,
                import_ms=round(import_ms, 1),
                faces=faces,
                edges=edges,
                solids=solids,
                shells=shells,
                volume_mm3=props.volume,
                volume_converged_mm3=converged,
                volume_gauss_rel=gauss_rel,
                area_mm2=props.surface_area,
                tess_ms=round(tess_ms, 1),
                triangles=mesh.triangles,
                glb_kib=round(len(glb) / 1024.0, 1),
                glb_gzip_kib=round(len(gzipped) / 1024.0, 1),
                step_export_ms=round(step_ms, 1),
                step_kib=round(len(step_bytes) / 1024.0, 1),
                reimport_ms=round(reimport_ms, 1),
                roundtrip_volume_rel=rel,
                roundtrip_topology_ok=topo_ok,
                roundtrip_detail=rt_detail,
                peak_rss_mib=round(_peak_rss_mib(), 0),
                notes=notes,
            )
        )
        print(
            f"  … {entry['name']}: {faces} faces, import {import_ms:.0f} ms",
            file=sys.stderr,
        )
    return points


def _shipped_import_bounds() -> tuple[float, float]:
    from geometry.main import GeometrySettings

    settings = GeometrySettings()
    return (
        settings.step_import_timeout_seconds,
        settings.step_import_wall_timeout_seconds,
    )


def _bounded_import(text: str, bounds: tuple[float, float]) -> tuple[bool, str]:
    """Run the parse the way the service runs it, and report the verdict.

    The step cache is reset first: a hit would skip the bounded subprocess parse
    entirely and report a pass for a file the service would actually reject.
    """
    from geometry.step_cache import import_step_solid_cached, reset_step_cache

    cpu_s, wall_s = bounds
    reset_step_cache()
    start = time.perf_counter()
    try:
        import_step_solid_cached(text, cpu_timeout_s=cpu_s, wall_timeout_s=wall_s)
    except Exception as exc:  # a rejection IS the measurement
        return False, f"{type(exc).__name__} after {(time.perf_counter() - start):.1f}s"
    return True, f"ok in {(time.perf_counter() - start):.1f}s"


# --- Leg II: the deep parametric part -------------------------------------------


@dataclass
class DeepPoint:
    features: int
    cold_rebuild_ms: float
    cold_spread_pct: float
    repeat_ms: float
    append_ms: float
    append_feature_type: str
    append_busts_scope: bool
    edit_late_index: int
    edit_late_ms: float
    edit_early_index: int
    edit_early_ms: float
    faces: int
    edges: int
    triangles: int
    tess_ms: float
    glb_kib: float
    volume_mm3: float
    peak_rss_mib: float
    rss_mib: float
    all_features_ok: bool
    detail: str


def _perturb(
    payload: dict[str, Any], index: int, *, backwards: bool = False
) -> tuple[dict[str, Any], int]:
    """Copy *payload* with the nearest numeric feature param to *index* nudged 1%.

    Returns the mutated payload and the index actually mutated. Not every feature
    carries a dimension — a sketch, a pattern and a mirror do not — so the honest
    thing is to report where the edit LANDED rather than to claim it landed at
    *index*. Searching backwards from the end is what the "edit late" probe wants;
    forwards from the front is what "edit early" wants.

    Raising when nothing is found is deliberate. A probe that silently edited
    nothing would time a REPEAT and report it as an incremental edit — the
    cheapest possible way to publish a flattering number that means nothing.
    """
    tweakable = (
        "distance_mm",
        "depth_mm",
        "diameter_mm",
        "radius_mm",
        "thickness_mm",
        "offset_mm",
        "angle_deg",
    )
    mutated = json.loads(json.dumps(payload))
    count = len(mutated["features"])
    order = range(min(index, count - 1), -1, -1) if backwards else range(index, count)
    for offset in order:
        params = mutated["features"][offset]["feature"].get("params", {})
        for key in tweakable:
            value = params.get(key)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value
            ):
                params[key] = value * 1.01
                return mutated, offset
    raise SystemExit(
        f"gauntlet: no numeric param found scanning "
        f"{'backwards' if backwards else 'forwards'} from feature {index} of "
        f"{count} — the incremental-edit measurement would be vacuous. Fix the "
        "probe, not the number."
    )


def _changes_capture_scope(item: dict[str, Any]) -> bool:
    """Would appending *item* change the mirror capture scope, and so every key?

    `rebuild_cache.prefix_keys` hashes the capture scope into EVERY prefix key,
    because a `features`-scoped mirror makes the features it names retain their
    reflectable tools — so the state after k features genuinely depends on the
    suffix, and appending such a mirror is a correct total miss rather than a
    cache defect. Read from the payload rather than from `evaluate`'s private
    `_tool_scope_ids`, so this stays a public reading of the documented rule.
    """
    feature = item.get("feature", {})
    if feature.get("type") not in ("mirror", "pattern"):
        return False
    scope = feature.get("params", {}).get("scope", {})
    return bool(scope.get("kind") == "features")


def run_deep_leg(sweep: tuple[int, ...]) -> list[DeepPoint]:
    from geometry.features import evaluate_tree
    from geometry.features.evaluate import reset_rebuild_cache
    from geometry.kernel.tessellate import tessellate_glb
    from loft_wire.features import EvaluateTreeRequest

    builders = _load_test_module("_big_part_builders")
    points: list[DeepPoint] = []

    for n in sweep:
        _assert_no_site_wrap(builders, n)
        payload = builders.housing_tree(n)
        request = EvaluateTreeRequest.model_validate(payload)

        def cold(req: Any = request) -> Any:
            reset_rebuild_cache()
            return evaluate_tree(req)

        cold_ms, spread = _median_ms(cold, samples=SAMPLES)

        # Warm behaviours, each measured against a freshly-seeded cache so one
        # leg cannot inherit another's checkpoint.
        reset_rebuild_cache()
        evaluate_tree(request)
        repeat_ms, evaluation = _ms(lambda r=request: evaluate_tree(r))

        # An APPEND is the case the prefix cache is built to serve -- but only
        # when the appended feature does not change the mirror CAPTURE SCOPE,
        # which is hashed into every prefix key by design (rebuild_cache.py
        # prefix_keys). Appending a `features`-scoped mirror is therefore a
        # documented, correct miss. Report which case this point measured, or the
        # number is unreadable: at N=25 the 26th feature IS such a mirror and the
        # append costs a full rebuild for a reason that is not a defect.
        append_payload = builders.housing_tree(n + 1)
        append_request = EvaluateTreeRequest.model_validate(append_payload)
        append_type = str(append_payload["features"][-1]["feature"]["type"])
        busts = _changes_capture_scope(append_payload["features"][-1])
        reset_rebuild_cache()
        evaluate_tree(request)
        append_ms, _ = _ms(lambda r=append_request: evaluate_tree(r))

        late_payload, late_index = _perturb(payload, n - 1, backwards=True)
        late_request = EvaluateTreeRequest.model_validate(late_payload)
        reset_rebuild_cache()
        evaluate_tree(request)
        late_ms, _ = _ms(lambda r=late_request: evaluate_tree(r))

        early_payload, early_index = _perturb(payload, 3)
        early_request = EvaluateTreeRequest.model_validate(early_payload)
        reset_rebuild_cache()
        evaluate_tree(request)
        early_ms, _ = _ms(lambda r=early_request: evaluate_tree(r))

        reset_rebuild_cache()
        evaluation = evaluate_tree(request)
        failures = [
            f"{r.feature_id}:{r.status}"
            for r in evaluation.result.features
            if r.status != "ok"
        ]
        body = evaluation.body
        assert body is not None, "deep tree produced no body"
        faces, edges, _solids, _shells = _topology(body)
        tess_ms, (glb, mesh) = _ms(lambda b=body: tessellate_glb(b, 0.1))
        props = evaluation.result.properties

        points.append(
            DeepPoint(
                features=n,
                cold_rebuild_ms=round(cold_ms, 1),
                cold_spread_pct=round(spread, 1),
                repeat_ms=round(repeat_ms, 1),
                append_ms=round(append_ms, 1),
                append_feature_type=append_type,
                append_busts_scope=busts,
                edit_late_index=late_index,
                edit_late_ms=round(late_ms, 1),
                edit_early_index=early_index,
                edit_early_ms=round(early_ms, 1),
                faces=faces,
                edges=edges,
                triangles=mesh.triangles,
                tess_ms=round(tess_ms, 1),
                glb_kib=round(len(glb) / 1024.0, 1),
                volume_mm3=props.volume if props else float("nan"),
                peak_rss_mib=round(_peak_rss_mib(), 0),
                rss_mib=round(_rss_mib(), 0),
                all_features_ok=not failures,
                detail="; ".join(failures[:4]) if failures else "all ok",
            )
        )
        print(
            f"  … N={n}: cold {cold_ms / 1000:.1f}s, edit#{early_index} "
            f"{early_ms / 1000:.1f}s, edit#{late_index} {late_ms / 1000:.1f}s",
            file=sys.stderr,
        )
    return points


# --- Reporting ------------------------------------------------------------------


def _import_table(points: list[ImportPoint]) -> str:
    head = (
        "| part | MB | faces | edges | solids | shells | import ms | "
        "tess ms | tris | GLB KiB | gz KiB | STEP ms | STEP KiB | "
        "re-import ms | RT vol rel | RT topo | GProp rel | peak RSS |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |\n"
    )
    rows = "".join(
        f"| {p.name} | {p.mb} | {p.faces} | {p.edges} | {p.solids} | {p.shells} | "
        f"{p.import_ms:.0f} | {p.tess_ms:.0f} | {p.triangles} | {p.glb_kib:.0f} | "
        f"{p.glb_gzip_kib:.0f} | {p.step_export_ms:.0f} | {p.step_kib:.0f} | "
        f"{p.reimport_ms:.0f} | {p.roundtrip_volume_rel:.2e} | "
        f"{'exact' if p.roundtrip_topology_ok else 'DIFFERS'} | "
        f"{p.volume_gauss_rel:.2e} | {p.peak_rss_mib:.0f} |\n"
        for p in points
    )
    return head + rows


def _deep_table(points: list[DeepPoint]) -> str:
    head = (
        "| features | cold rebuild ms | spread | repeat ms | append ms | "
        "edit late ms | edit early ms | faces | tris | tess ms | peak RSS | ok |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | --- |\n"
    )
    rows = "".join(
        f"| {p.features} | {p.cold_rebuild_ms:.0f} | ±{p.cold_spread_pct:.0f}% | "
        f"{p.repeat_ms:.0f} | {p.append_ms:.0f} ({p.append_feature_type}"
        f"{', scope-bust' if p.append_busts_scope else ''}) | "
        f"{p.edit_late_ms:.0f} (#{p.edit_late_index}) | "
        f"{p.edit_early_ms:.0f} (#{p.edit_early_index}) | {p.faces} | "
        f"{p.triangles} | {p.tess_ms:.0f} | {p.peak_rss_mib:.0f} | "
        f"{'yes' if p.all_features_ok else p.detail} |\n"
        for p in points
    )
    return head + rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leg", choices=("import", "deep", "all"), default="all")
    parser.add_argument("--only", help="comma-separated fixture names (import leg)")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--json", type=Path, help="write the full record here")
    parser.add_argument(
        "--deep-sweep",
        default=",".join(str(n) for n in DEEP_SWEEP),
        help="comma-separated feature counts",
    )
    args = parser.parse_args()

    machine = _machine()
    print(
        f"gauntlet: {machine['cores']} cores, {machine['mem_total_gib']} GiB, "
        f"loadavg {machine['loadavg']}, {machine['utc']}",
        file=sys.stderr,
    )

    record: dict[str, Any] = {"machine_start": machine}
    only = set(args.only.split(",")) if args.only else None

    if args.leg in ("import", "all"):
        print("gauntlet: leg I — real imported parts", file=sys.stderr)
        imports = run_import_leg(args.cache, only)
        record["import"] = [asdict(p) for p in imports]
    if args.leg in ("deep", "all"):
        print("gauntlet: leg II — deep parametric part", file=sys.stderr)
        sweep = tuple(int(x) for x in args.deep_sweep.split(","))
        deep = run_deep_leg(sweep)
        record["deep"] = [asdict(p) for p in deep]

    record["machine_end"] = _machine()

    out: list[str] = []
    out.append(
        f"_Machine: {machine['cores']} cores, {machine['mem_total_gib']} GiB. "
        f"Load average at start {machine['loadavg']}, at end "
        f"{record['machine_end']['loadavg']}. {machine['utc']}._\n"
    )
    if "import" in record:
        out.append("\n#### Leg I — real imported parts\n")
        out.append(_import_table([ImportPoint(**p) for p in record["import"]]))
        for p in record["import"]:
            if p["notes"] or not p["bounded_ok"]:
                out.append(
                    f"\n* **{p['name']}** — shipped bounded import: "
                    f"{p['bounded_detail']}. {'; '.join(p['notes'])}\n"
                )
    if "deep" in record:
        out.append("\n#### Leg II — deep parametric part (housing tray)\n")
        out.append(_deep_table([DeepPoint(**p) for p in record["deep"]]))
    report = "".join(out)
    print(report)

    if args.json:
        args.json.write_text(json.dumps(record, indent=2, default=str) + "\n")
        print(f"gauntlet: wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
