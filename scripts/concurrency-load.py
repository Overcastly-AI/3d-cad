#!/usr/bin/env python3
"""Multi-user load harness for the geometry service (docs/PERF.md).

**Why this exists.** Every number in docs/PERF.md before 2026-08-01 is
single-user, single-process and in-process. The first question a self-hosting
operator asks is "can my team of four use this at once?", and docs/OPERATIONS.md
§6 answered it by REASONING (one worker per host, because the rebuild cache is a
per-process LRU with no session affinity) rather than by measurement. This
harness measures it.

**What it simulates.** ``--users N`` independent modelers, each in its own
thread with its own connection, each on its OWN part (a docs/PERF.md tray whose
corner-fillet radius carries a per-user salt, so no two users share a cache
lineage — four modelers are four parts, not one). Each runs the realistic edit
loop: *edit a dimension -> re-evaluate -> pick a face (/overlay) -> measure two
edges (/measure)*. The very first evaluate of each user is recorded separately
as the COLD OPEN, which is the thing a page load pays.

**Closed loop, zero think time** by default: N users means N requests in flight
at all times, which is the saturation model that makes p95-vs-concurrency
readable. ``--think-ms`` adds a pause if you want an open-ish model.

**Correctness under concurrency is checked on every response, not sampled.**
Before the load, one user's tree in each of its edit states is evaluated ALONE
and its ``mesh_glb_id`` + volume recorded. Every response during the load is
compared against the baseline for that exact tree state. A mismatch means two
concurrent evaluations crossed, which is a P0 and is reported as such — ahead of
every latency number.

**Worker fan-out.** ``--workers`` takes the geometry base URLs. Dispatch is
``random`` (the honest model of a shared listening socket / compose DNS
round-robin: no affinity) or ``sticky`` (each user pinned to one worker — the
accidental affinity a keep-alive connection gives you, and the thing session
affinity would make deliberate). Comparing the two IS the worker-vs-cache
measurement.

Cache hit rate is SCRAPED from each worker's ``/metrics``
(``loft_rebuild_cache_{hits,misses}_total``, docs/OBSERVABILITY.md), never
inferred from timings.

    scripts/load-stack.sh up 2
    uv run python scripts/concurrency-load.py \
        --users 4 --size 50 --loops 3 \
        --workers http://127.0.0.1:8512 http://127.0.0.1:8513 \
        --dispatch random --json out.json
    scripts/load-stack.sh down
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import resource
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx2 as httpx  # the repo's http client (gateway/upstream.py does the same)

#: A feature-tree request payload (an ``EvaluateTreeRequest`` before validation).
type Tree = dict[str, Any]

#: The content signature of an evaluated body: ``(mesh_glb_id, volume_mm3)``.
type Signature = tuple[str | None, float | None]

_REPO = Path(__file__).resolve().parent.parent


def _load_housing_tree() -> Callable[[int], Tree]:
    """The docs/PERF.md tray builder, loaded from the geometry test tree.

    Loaded by path rather than imported, because ``services/geometry/tests`` is
    not an importable package from here — a ``sys.path`` insertion plus a plain
    ``import`` works at runtime but leaves the symbol untyped, and this repo is
    pyright-strict, so one untyped symbol poisons every downstream annotation in
    the file. Reusing the builder (instead of copying it) is the point: a number
    here is then directly comparable with docs/PERF.md's Axis-A table.
    """
    path = _REPO / "services" / "geometry" / "tests" / "_big_part_builders.py"
    spec = importlib.util.spec_from_file_location("_big_part_builders", path)
    if spec is None or spec.loader is None:  # pragma: no cover — path is fixed
        raise SystemExit(f"cannot load the part builders from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Callable[[int], Tree], module.housing_tree)


housing_tree = _load_housing_tree()

#: Requests that carry a whole feature tree are slow by construction; a timeout
#: shorter than the worst cold open would turn "degraded" into "failed" and hide
#: the number we are here to measure.
REQUEST_TIMEOUT_S = 900.0


# --- JSON narrowing -----------------------------------------------------------
# A decoded JSON body is `object`, and pyright-strict rightly refuses to let an
# `Any` leak out of it. These two are the only narrowing seam in the file, so a
# malformed response degrades to an empty container instead of an AttributeError
# mid-load (which would end the run and lose every sample taken so far).


def _as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


# --- part construction --------------------------------------------------------


def _mutate_first(tree: Tree, key: str, delta: float) -> int:
    """Add *delta* to the FIRST feature param named *key*; return its index."""
    for index, item in enumerate(_as_list(tree["features"])):
        params = _as_dict(_as_dict(item).get("feature")).get("params")
        numeric = _as_dict(params).get(key)
        if isinstance(numeric, (int, float)) and not isinstance(numeric, bool):
            _as_dict(params)[key] = round(float(numeric) + delta, 6)
            return index
    raise ValueError(f"no feature carries a numeric {key!r}")


def _salted(size: int, radius_delta: float) -> Tree:
    """``housing_tree(size)`` with the whole-body corner round moved.

    ``radius_mm`` on the tray's ``axis_parallel`` Z fillet (feature index 2, so
    EARLY) is the dimension this harness moves, for both the per-user salt and
    the per-loop edit, and the choice is measured rather than aesthetic: it is a
    whole-body predicate fillet, so no later feature holds a picked-subshape
    reference to what it produces, and every prefix downstream of it re-hashes.
    Moving a dimension near the TIP was tried first and is NOT usable — bumping
    the last ``distance_mm`` of the N=50 tray by 0.01 mm makes the picked-edge
    fillet that consumes it fail ``subshape_unresolved``, i.e. the tree stops
    being a valid load subject. (That is a real topological-naming limitation
    and it is filed separately; it is not what this harness is measuring.)
    """
    tree = housing_tree(size)
    index = _mutate_first(tree, "radius_mm", radius_delta)
    assert index == 2, f"expected the corner fillet at index 2, found {index}"
    return tree


def user_states(
    size: int,
    user: int,
    loops: int,
    *,
    mode: str,
    run: int = 0,
    shared: bool = False,
) -> list[Tree]:
    """The ``loops`` tree states user *user* cycles through.

    The per-user salt is an early dimension, so no two users share a cache
    lineage — four modelers are four parts. Salting only the tip would let N
    users share one cached prefix and would flatter the cache by exactly the
    factor this harness exists to measure.

    Two modes, because they are the two halves of what a modeler actually does
    and docs/PERF.md only ever measured the second:

    * ``edit`` — the SAME part at ``size`` features, one dimension moved per
      loop. This is "change a number and look at the result", the commonest
      action in CAD.
    * ``append`` — ``size - loops + 1 .. size`` features, i.e. one new feature
      per loop. ``housing_tree`` is a canonical sequence, so state *k* is a
      strict prefix of state *k+1*; this is docs/PERF.md's "append" case, the
      one the rebuild cache is built to serve.
    """
    # EVERY offset here is micrometres, and that is a correctness property of
    # the harness, not tidiness. The first version used 0.1 mm per ``run``, so
    # --run 400 moved an 8 mm corner round to 48 mm — a different part, quietly,
    # and therefore a different cost. Runs were then not comparable with each
    # other or with docs/PERF.md's tray. Keep the whole spread under ~0.02 mm:
    # distinct content hashes (which is all the cache key needs), identical
    # geometry to any tolerance anyone cares about.
    #
    # ``run`` shifts every tree of a run into its own lineage, so a second run
    # against a still-warm worker measures a COLD cache the way the first did.
    # ``shared`` drops the per-user component so every user hammers ONE lineage:
    # the adversarial case for the cache's ownership transfer, since a single
    # checkpoint is then contended by every thread at once.
    salt = (0.0 if shared else 1e-3 * (user + 1)) + 1e-5 * run
    if mode == "append":
        first = size - loops + 1
        if first < 6:
            raise SystemExit("--size must exceed --loops + 5 in append mode")
        return [_salted(first + loop, salt) for loop in range(loops)]
    return [_salted(size, salt + 1e-4 * (loop + 1)) for loop in range(loops)]


# --- measurement --------------------------------------------------------------


@dataclass
class Sample:
    op: str
    user: int
    worker: str
    started: float
    elapsed_ms: float
    status: int
    note: str = ""


@dataclass
class Recorder:
    samples: list[Sample] = field(default_factory=list[Sample])
    mismatches: list[str] = field(default_factory=list[str])
    errors: list[str] = field(default_factory=list[str])
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, sample: Sample) -> None:
        with self._lock:
            self.samples.append(sample)

    def mismatch(self, message: str) -> None:
        with self._lock:
            self.mismatches.append(message)

    def error(self, message: str) -> None:
        with self._lock:
            self.errors.append(message)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


#: ``GEOMETRY_TIMEOUT_S`` in ``services/gateway/src/gateway/geometry.py``. This
#: harness talks to geometry DIRECTLY, so nothing here is cut off by it — but
#: the browser never does, so any sample above this line is an operation that
#: would have come back to a real user as a 502 ``upstream_unavailable``
#: ("Geometry service is unreachable") with the work thrown away. Counting them
#: is the difference between "slow" and "broken".
GATEWAY_UPSTREAM_TIMEOUT_MS = 30_000.0


def summarize(
    samples: list[Sample], op: str, *, user: int | None = None
) -> dict[str, Any]:
    picked = [s for s in samples if s.op == op and (user is None or s.user == user)]
    times = [s.elapsed_ms for s in picked if s.status == 200]
    failures = [s for s in picked if s.status != 200]
    return {
        "op": op,
        "n": len(times),
        "failed": len(failures),
        "p50_ms": round(statistics.median(times), 1) if times else None,
        "p95_ms": round(percentile(times, 0.95), 1) if times else None,
        "max_ms": round(max(times), 1) if times else None,
        "over_gateway_timeout": sum(
            1 for t in times if t > GATEWAY_UPSTREAM_TIMEOUT_MS
        ),
    }


# --- the simulated modeler ----------------------------------------------------


class Fleet:
    """Worker selection: the model of what a request-to-process mapping is."""

    def __init__(self, urls: list[str], dispatch: str) -> None:
        self.urls = urls
        self.dispatch = dispatch
        self._counter = 0
        self._lock = threading.Lock()

    def pick(self, user: int) -> str:
        if self.dispatch == "sticky":
            return self.urls[user % len(self.urls)]
        if self.dispatch == "roundrobin":
            with self._lock:
                url = self.urls[self._counter % len(self.urls)]
                self._counter += 1
            return url
        # "random" — no affinity, which is what a shared listening socket and
        # compose DNS round-robin give a stateless client.
        return random.choice(self.urls)


def post(
    client: httpx.Client, base: str, path: str, payload: Tree
) -> tuple[int, object, float]:
    started = time.perf_counter()
    try:
        response = client.post(f"{base}{path}", json=payload)
    except Exception as exc:  # a transport failure IS a load result
        return 0, {"transport_error": repr(exc)}, (time.perf_counter() - started) * 1000
    elapsed = (time.perf_counter() - started) * 1000
    try:
        body: object = response.json()
    except Exception:
        body = None
    return response.status_code, body, elapsed


def signature(body: object) -> Signature:
    """The two things a crossed evaluation could not fake: the content hash of
    the mesh and the volume of the body."""
    payload = _as_dict(body)
    volume = _as_dict(payload.get("properties")).get("volume")
    mesh = payload.get("mesh_glb_id")
    return (
        mesh if isinstance(mesh, str) else None,
        float(volume) if isinstance(volume, (int, float)) else None,
    )


def run_user(
    user: int,
    states: list[Tree],
    fleet: Fleet,
    recorder: Recorder,
    observed: dict[tuple[int, int, str], Signature],
    barrier: threading.Barrier,
    think_ms: float,
    warm: bool = False,
) -> None:
    client = httpx.Client(timeout=REQUEST_TIMEOUT_S)
    barrier.wait()
    try:
        # 1. COLD OPEN — the first evaluate of a tree this fleet has never seen.
        #    Nothing is evaluated before the load starts, precisely so this stays
        #    a genuine miss; the correctness baseline is taken AFTERWARDS.
        worker = fleet.pick(user)
        started = time.perf_counter()
        status, body, elapsed = post(client, worker, "/api/v1/evaluate", states[0])
        recorder.add(Sample("open", user, worker, started, elapsed, status))
        _record(recorder, observed, user, 0, status, body, "open")

        # 2. the edit loop.
        for loop, state in enumerate(states):
            worker = fleet.pick(user)
            if warm:
                # What opening a feature editor does (PERF-1b): declare the
                # prefix before the edited feature settled, so the commit that
                # follows resumes there. Returns as soon as the warm is QUEUED,
                # so the timing below still measures the evaluate, not the warm
                # — which is exactly why a warm's cost shows up as somebody
                # ELSE's latency on a worker with one effective core.
                post(
                    client,
                    worker,
                    "/api/v1/warm",
                    {
                        "ticket": f"editor-{user}-{loop}",
                        "tree": state,
                        "prefix_length": max(0, len(_as_list(state["features"])) - 1),
                    },
                )
            started = time.perf_counter()
            status, body, elapsed = post(client, worker, "/api/v1/evaluate", state)
            recorder.add(Sample("evaluate", user, worker, started, elapsed, status))
            _record(recorder, observed, user, loop, status, body, "evaluate")

            worker = fleet.pick(user)
            started = time.perf_counter()
            status, overlay, elapsed = post(
                client, worker, "/api/v1/overlay", {"tree": state}
            )
            recorder.add(Sample("overlay", user, worker, started, elapsed, status))
            edge_count = len(_as_list(_as_dict(overlay).get("edges")))

            if edge_count >= 2:
                worker = fleet.pick(user)
                started = time.perf_counter()
                status, _measured, elapsed = post(
                    client,
                    worker,
                    "/api/v1/measure",
                    {
                        "a": {"kind": "edge", "index": 0},
                        "b": {"kind": "edge", "index": 1},
                        "tree": state,
                    },
                )
                recorder.add(Sample("measure", user, worker, started, elapsed, status))
            if think_ms:
                time.sleep(think_ms / 1000.0)
    finally:
        client.close()


_OBSERVED_LOCK = threading.Lock()


def _record(
    recorder: Recorder,
    observed: dict[tuple[int, int, str], Signature],
    user: int,
    loop: int,
    status: int,
    body: object,
    op: str,
) -> None:
    """Bank what this response CLAIMED the body is, for the post-load audit.

    The comparison cannot happen here: a baseline taken before the load would
    warm the very cache whose cold path we are timing. So every evaluate's
    ``(mesh_glb_id, volume)`` is banked under its exact tree state and checked
    afterwards, serially, against the same tree evaluated alone.
    """
    if status != 200:
        recorder.error(
            f"user{user} {op} loop{loop} -> HTTP {status}: {str(body)[:300]}"
        )
        return
    with _OBSERVED_LOCK:
        observed[(user, loop, op)] = signature(body)


def audit_correctness(
    worker: str,
    all_states: list[list[Tree]],
    observed: dict[tuple[int, int, str], Signature],
    recorder: Recorder,
) -> int:
    """Re-evaluate every tree state ALONE and compare with what load returned.

    This is the P0 detector. ``mesh_glb_id`` is a content hash of the GLB and
    ``volume_mm3`` comes off the exact B-rep, so if two concurrent evaluations of
    different trees ever crossed — a shared checkpoint lent twice, an OCCT
    boolean rewriting an argument another thread still holds (CM-6b) — the load
    response cannot match the quiet one.
    """
    client = httpx.Client(timeout=REQUEST_TIMEOUT_S)
    checked = 0
    try:
        for user, states in enumerate(all_states):
            for loop, state in enumerate(states):
                status, body, _elapsed = post(client, worker, "/api/v1/evaluate", state)
                if status != 200:
                    recorder.error(f"audit user{user} loop{loop} -> HTTP {status}")
                    continue
                bad = [
                    str(_as_dict(f).get("feature_id"))
                    for f in _as_list(_as_dict(body).get("features"))
                    if _as_dict(f).get("status") not in ("ok", "suppressed")
                ]
                if bad:
                    # A tree that does not fully evaluate is not a valid load
                    # subject — its cost is not a rebuild's cost. Fail loudly
                    # rather than silently benchmarking a broken part.
                    recorder.error(
                        f"audit user{user} loop{loop}: {len(bad)} features not ok "
                        f"(first {bad[0]}) — this load subject is INVALID"
                    )
                truth = signature(body)
                for op in ("open", "evaluate"):
                    got = observed.get((user, loop, op))
                    if got is None:
                        continue
                    checked += 1
                    if got != truth:
                        recorder.mismatch(
                            f"user{user} {op} loop{loop}: under load "
                            f"mesh={got[0]} volume={got[1]!r}; alone "
                            f"mesh={truth[0]} volume={truth[1]!r}"
                        )
    finally:
        client.close()
    return checked


# --- metrics scraping ---------------------------------------------------------


def scrape_cache(urls: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for url in urls:
        counters: dict[str, float] = {}
        try:
            text = httpx.get(f"{url}/metrics", timeout=30.0).text
        except Exception as exc:
            out[url] = {"scrape_error": repr(exc)}  # type: ignore[dict-item]
            continue
        for line in text.splitlines():
            if line.startswith("#"):
                continue
            for name in (
                "loft_rebuild_cache_hits_total",
                "loft_rebuild_cache_misses_total",
                "loft_rebuild_cache_stores_total",
                "loft_rebuild_cache_evictions_total",
            ):
                if line.startswith(name + " "):
                    counters[
                        name.replace("loft_rebuild_cache_", "").replace("_total", "")
                    ] = float(line.split()[1])
        out[url] = counters
    return out


def delta_cache(
    before: dict[str, dict[str, float]], after: dict[str, dict[str, float]]
) -> dict[str, Any]:
    per_worker: dict[str, dict[str, float]] = {}
    totals = {"hits": 0.0, "misses": 0.0, "stores": 0.0, "evictions": 0.0}
    for url, post_counters in after.items():
        pre = before.get(url, {})
        row = {key: post_counters.get(key, 0.0) - pre.get(key, 0.0) for key in totals}
        per_worker[url] = row
        for key in totals:
            totals[key] += row[key]
    looked_up = totals["hits"] + totals["misses"]
    return {
        "per_worker": per_worker,
        "totals": totals,
        "hit_rate": round(totals["hits"] / looked_up, 4) if looked_up else None,
    }


# --- worker process introspection --------------------------------------------


def _worker_procs(ports: list[int]) -> dict[int, Path]:
    """The uvicorn PID serving each port (the child, not the ``uv run`` wrapper)."""
    out: dict[int, Path] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().decode(errors="replace")
        except OSError:
            continue
        if "geometry.main:app" not in cmdline or "uv\x00run" in cmdline:
            continue
        for port in ports:
            if f"--port\x00{port}" in cmdline:
                out[port] = entry
    return out


def worker_rss_mib(ports: list[int]) -> dict[int, float]:
    """RSS of each geometry uvicorn, read from /proc — no psutil dependency."""
    out: dict[int, float] = {}
    for port, entry in _worker_procs(ports).items():
        try:
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    out[port] = round(float(line.split()[1]) / 1024.0, 1)
        except (OSError, ValueError):
            continue
    return out


def worker_cpu_s(ports: list[int]) -> dict[int, float]:
    """utime+stime of each geometry worker, seconds.

    THE VALIDITY CONTROL for every number this harness prints. A load generator
    that is itself the bottleneck reports the generator's limits as the server's
    — and this one is a Python process serialising a 50-feature tree per request
    under the same GIL the server has, which is exactly the shape of that
    mistake. Comparing summed worker CPU against the harness's own
    ``getrusage`` (and both against wall x cores) says whether the server was
    the constraint. Report it; do not assume it.
    """
    out: dict[int, float] = {}
    ticks = float(os.sysconf("SC_CLK_TCK"))
    for port, entry in _worker_procs(ports).items():
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        out[port] = round((int(fields[11]) + int(fields[12])) / ticks, 2)
    return out


# --- main ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=1)
    parser.add_argument("--size", type=int, default=50, help="features in the tray")
    parser.add_argument("--loops", type=int, default=3)
    parser.add_argument(
        "--workers", nargs="+", default=["http://127.0.0.1:8512"], help="geometry URLs"
    )
    parser.add_argument(
        "--dispatch", choices=("random", "sticky", "roundrobin"), default="random"
    )
    parser.add_argument("--think-ms", type=float, default=0.0)
    parser.add_argument(
        "--mode",
        choices=("edit", "append"),
        default="edit",
        help="edit = move a dimension on the same tree (the common action); "
        "append = add one feature per loop (docs/PERF.md's cached case)",
    )
    parser.add_argument(
        "--run",
        type=int,
        default=0,
        help="lineage offset — give each run against a warm worker a distinct value",
    )
    parser.add_argument(
        "--warm",
        action="store_true",
        help="issue the PERF-1b /warm prefetch before each edit, as an open "
        "feature editor does — measures what speculation costs OTHER users",
    )
    parser.add_argument(
        "--heavy",
        type=int,
        default=0,
        help="give user 0 a tree of this many features (the mixed case: one big "
        "cold open against everyone else's small edits)",
    )
    parser.add_argument(
        "--shared-part",
        action="store_true",
        help="every user works on the SAME part — the adversarial correctness case",
    )
    parser.add_argument("--label", default="")
    parser.add_argument("--json", default="")
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="skip the post-load serial re-evaluation (it costs one cold rebuild "
        "per user per state; only skip it when a previous identical run audited "
        "clean and you are re-measuring timings)",
    )
    args = parser.parse_args(argv)

    fleet = Fleet(args.workers, args.dispatch)
    recorder = Recorder()
    observed: dict[tuple[int, int, str], tuple[str | None, float | None]] = {}

    # --heavy is the mixed case docs/OPERATIONS.md never tried: ONE person
    # opening a big part cold while everyone else does small edits. User 0 gets
    # the big tree and a single loop (one cold open is the whole scenario); the
    # rest run the ordinary loop at --size.
    all_states = [
        user_states(
            args.heavy if (args.heavy and user == 0) else args.size,
            user,
            1 if (args.heavy and user == 0) else args.loops,
            mode=args.mode,
            run=args.run,
            shared=args.shared_part,
        )
        for user in range(args.users)
    ]

    before = scrape_cache(args.workers)
    ports = [int(url.rsplit(":", 1)[1]) for url in args.workers]
    rss_before = worker_rss_mib(ports)
    cpu_before = worker_cpu_s(ports)
    self_before = resource.getrusage(resource.RUSAGE_SELF)

    barrier = threading.Barrier(args.users)
    threads = [
        threading.Thread(
            target=run_user,
            args=(
                user,
                all_states[user],
                fleet,
                recorder,
                observed,
                barrier,
                args.think_ms,
                args.warm,
            ),
            name=f"modeler-{user}",
            daemon=True,
        )
        for user in range(args.users)
    ]
    wall_start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - wall_start

    after = scrape_cache(args.workers)
    cpu_after = worker_cpu_s(ports)
    self_after = resource.getrusage(resource.RUSAGE_SELF)
    rss_after = worker_rss_mib(ports)
    worker_cpu = round(
        sum(cpu_after.get(p, 0.0) - cpu_before.get(p, 0.0) for p in ports), 2
    )
    harness_cpu = round(
        (self_after.ru_utime + self_after.ru_stime)
        - (self_before.ru_utime + self_before.ru_stime),
        2,
    )

    audited = (
        0
        if args.no_audit
        else audit_correctness(args.workers[0], all_states, observed, recorder)
    )

    ops = ["open", "evaluate", "overlay", "measure"]
    report: dict[str, Any] = {
        "label": args.label,
        "users": args.users,
        "size": args.size,
        "loops": args.loops,
        "workers": args.workers,
        "dispatch": args.dispatch,
        "mode": args.mode,
        "heavy": args.heavy,
        "warm": args.warm,
        "shared_part": args.shared_part,
        "run": args.run,
        "wall_s": round(wall, 2),
        "completed_ops": len([s for s in recorder.samples if s.status == 200]),
        "throughput_ops_s": round(
            len([s for s in recorder.samples if s.status == 200]) / wall, 3
        ),
        "per_op": [summarize(recorder.samples, op) for op in ops],
        # Per-user, because the mixed case is ONLY legible per user: the point
        # is what the small editors pay while the big part rebuilds.
        "per_user": {
            str(user): [
                summarize(recorder.samples, op, user=user)
                for op in ops
                if any(s.op == op and s.user == user for s in recorder.samples)
            ]
            for user in range(args.users)
        },
        "cache": delta_cache(before, after),
        "worker_cpu_s": worker_cpu,
        "worker_cores_used": round(worker_cpu / wall, 2) if wall else None,
        "harness_cpu_s": harness_cpu,
        "harness_cores_used": round(harness_cpu / wall, 2) if wall else None,
        "cpu_count": os.cpu_count(),
        "rss_mib_before": rss_before,
        "rss_mib_after": rss_after,
        "responses_audited": audited,
        # Raw samples, so a question nobody thought to ask before the run can
        # still be answered from the artifact instead of by re-running it.
        "samples": [
            {
                "op": s.op,
                "user": s.user,
                "worker": s.worker,
                "ms": round(s.elapsed_ms, 1),
                "status": s.status,
            }
            for s in recorder.samples
        ],
        "correctness_mismatches": recorder.mismatches,
        "errors": recorder.errors[:20],
        "error_count": len(recorder.errors),
    }
    print(json.dumps(report, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    if recorder.mismatches:
        print("\n*** CORRECTNESS MISMATCH UNDER LOAD — P0 ***")
        return 3
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    raise SystemExit(main())
