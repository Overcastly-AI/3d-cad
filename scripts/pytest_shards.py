#!/usr/bin/env python3
"""Split ci.yml's pytest run across N jobs by measured duration, and prove that
every collected test ran exactly once.

WHY. The single `python` job's Pytest step reached 23m42s (bd6037d) against a
30-minute job ceiling, and the suite grows every time a verb or a golden lands.
services/geometry is 73% of the tests (3362 of 4605 on 2026-09-25) and nearly
all of the time, so splitting by directory cannot balance: the cut has to go
through the geometry suite, file by file, weighted by what each file costs.

HOW THE PARTITION IS MADE (same shape as scripts/e2e-shard-plan.py):

    every shard runs pytest's OWN full collection (testpaths, addopts, -m),
    then, in a trylast collection_modifyitems hook:
        for every FILE that still has items:          <- derived, never listed
            weight = manifest.get(file) or tests * mean_seconds_per_test
        bins = longest-processing-time packing(weights, N)
        keep this shard's bin, deselect the rest

The loop is over what pytest discovered, so the manifest
(scripts/pytest-durations.json) is advisory: stale, wrong or empty, it changes
BALANCE and never coverage. A new test file lands in some shard with nothing to
register. The packing is a pure function of (files, weights, N), and every shard
computes it over the same collection, so the bins are disjoint and cover the
suite by construction.

"By construction" is still a claim, so `pytest complete` checks it on every
run from what the shards EXECUTED: each shard writes a JSON ledger (what it
collected, what it was assigned, what it ran, how long each took), and `check`
refuses unless the shards agree on the collected set, every shard 1..N handed
one in, no test ran twice, and the union of what ran is exactly the collected
set. That catches the defects packing cannot: a matrix entry that was dropped, a
shard that died after collection, and a collection that differs between
runners, which would make the shards compute different partitions.

The ledger records every test that went through the run protocol, whatever its
outcome (pass, fail, skip, xfail, error), and is written at session finish.
So a shard with red tests still hands one in, and a shard killed by its timeout
is reported by name as missing.

Unknown files are priced at tests x the manifest's mean seconds per test, NOT
as the heaviest file the way e2e does it. A pytest file costs anything from
10 ms to minutes, and pricing ten new files at the heaviest (~2 min each here)
would put ~20 phantom minutes into the packing and starve the shards that got
them of real work. `check` prints the guessed share, and `durations` refreshes
the manifest from a full set of ledgers.

Usage:
    uv run python scripts/pytest_shards.py run --shard I/N --ledger FILE
        [-- PYTEST ARGS]
    python3 scripts/pytest_shards.py check --ledgers DIR --expect-shards N
        [--workflow .github/workflows/ci.yml]
    python3 scripts/pytest_shards.py durations --ledgers DIR
        [--out scripts/pytest-durations.json]
    python3 scripts/pytest_shards.py --self-test

`check`, `durations` and `--self-test` are stdlib only. `run` imports pytest.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "pytest-durations.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
#: Price per test when the manifest is empty (first run, deleted file).
FALLBACK_SECONDS_PER_TEST = 0.3


# ---------------------------------------------------------------------------
# The partition (stdlib, pure).


def file_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def load_manifest(path: Path = MANIFEST) -> dict[str, dict[str, float]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    seconds: dict[str, float] = data.get("seconds", {})
    tests: dict[str, int] = data.get("tests", {})
    return {
        f: {"seconds": float(s), "tests": float(tests.get(f, 1))}
        for f, s in seconds.items()
    }


def weights(
    tests_per_file: dict[str, int], manifest: dict[str, dict[str, float]]
) -> tuple[dict[str, float], list[str]]:
    """Seconds per file, and the files whose weight had to be guessed."""
    total_s = sum(entry["seconds"] for entry in manifest.values())
    total_n = sum(entry["tests"] for entry in manifest.values())
    per_test = total_s / total_n if total_n else FALLBACK_SECONDS_PER_TEST
    out: dict[str, float] = {}
    guessed: list[str] = []
    for path, count in tests_per_file.items():
        entry = manifest.get(path)
        if entry is None:
            out[path] = count * per_test
            guessed.append(path)
        else:
            out[path] = entry["seconds"]
    return out, sorted(guessed)


def pack(file_weights: dict[str, float], n: int) -> list[list[str]]:
    """Longest-processing-time first: heaviest file onto the lightest bin.

    Deterministic: ties on weight break by path, ties on load by bin index.
    """
    bins: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for path in sorted(file_weights, key=lambda p: (-file_weights[p], p)):
        target = min(range(n), key=lambda i: (load[i], i))
        bins[target].append(path)
        load[target] += file_weights[path]
    return bins


def parse_shard(spec: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)/(\d+)", spec)
    if not match:
        raise SystemExit(f"pytest_shards: --shard wants I/N, got {spec!r}")
    index, total = int(match.group(1)), int(match.group(2))
    if not 1 <= index <= total:
        raise SystemExit(f"pytest_shards: shard {index} is outside 1..{total}")
    return index, total


# ---------------------------------------------------------------------------
# The pytest plugin (registered in-process by `run`).


class _Ledger:
    """What one shard collected, was assigned, and ran (filled by the plugin)."""

    def __init__(self, index: int, total: int, path: Path) -> None:
        self.index, self.total, self.path = index, total, path
        self.collected: list[str] = []
        self.assigned: list[str] = []
        self.guessed: list[str] = []
        self.predicted: list[float] = []
        self.seconds: dict[str, float] = {}
        self.ran: list[str] = []
        self.started = time.monotonic()

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "shard": self.index,
            "total": self.total,
            "collected": self.collected,
            "assigned": self.assigned,
            "ran": {n: round(self.seconds.get(n, 0.0), 4) for n in self.ran},
            "guessed_files": self.guessed,
            "predicted_seconds": [round(s, 1) for s in self.predicted],
            "wall_seconds": round(time.monotonic() - self.started, 1),
        }
        self.path.write_text(json.dumps(body, indent=0) + "\n")


def _plugin(state: _Ledger) -> object:
    """The pytest plugin, built here so pytest is imported only by `run`."""
    import pytest

    class ShardPlugin:
        # trylast: after -m/-k/--deselect, so the partition is over exactly
        # the items an unsharded `pytest` would execute.
        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(
            self, config: pytest.Config, items: list[pytest.Item]
        ) -> None:
            state.collected = [item.nodeid for item in items]
            counts = Counter(file_of(item.nodeid) for item in items)
            file_weights, state.guessed = weights(dict(counts), load_manifest())
            bins = pack(file_weights, state.total)
            state.predicted = [sum(file_weights[f] for f in b) for b in bins]
            mine = set(bins[state.index - 1])
            keep = [item for item in items if file_of(item.nodeid) in mine]
            drop = [item for item in items if file_of(item.nodeid) not in mine]
            if drop:
                config.hook.pytest_deselected(items=drop)
            items[:] = keep
            state.assigned = [item.nodeid for item in keep]

        def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
            # setup + call + teardown, so fixture cost lands on its test.
            state.seconds[report.nodeid] = (
                state.seconds.get(report.nodeid, 0.0) + report.duration
            )

        def pytest_runtest_logfinish(
            self, nodeid: str, location: tuple[str, int | None, str]
        ) -> None:
            # Once per test through the run protocol, whatever its outcome.
            state.ran.append(nodeid)

        def pytest_sessionfinish(self) -> None:
            state.write()

    return ShardPlugin()


def cmd_run(spec: str, ledger: Path, extra: list[str]) -> int:
    index, total = parse_shard(spec)
    # Running this file put scripts/ at sys.path[0], which the plain `pytest`
    # console script would not have; keep the test environment identical.
    here = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != here]
    import pytest

    state = _Ledger(index, total, ledger)
    code = int(pytest.main(extra, plugins=[_plugin(state)]))
    # After pytest's own verdict lines, so a tail read finds it.
    print(
        f"\n== pytest shard {index}/{total}: {len(state.ran)} of "
        f"{len(state.assigned)} assigned test(s) ran "
        f"({len(state.collected)} collected suite-wide), exit {code}, "
        f"ledger {ledger} =="
    )
    return code


# ---------------------------------------------------------------------------
# The reconcile (stdlib).


def reconcile(ledgers: list[dict[str, Any]], expect: int) -> list[str]:
    """Every problem found; empty means each collected test ran exactly once."""
    problems: list[str] = []
    by_shard: dict[int, dict[str, Any]] = {}
    for ledger in ledgers:
        shard, total = ledger["shard"], ledger["total"]
        if total != expect:
            problems.append(
                f"shard {shard} planned for {total} shards but {expect} are "
                f"expected -- its partition differs from its siblings'"
            )
        if shard in by_shard:
            problems.append(f"shard {shard} handed in TWO ledgers")
        by_shard[shard] = ledger
    for shard in range(1, expect + 1):
        if shard not in by_shard:
            problems.append(
                f"shard {shard}/{expect}: NO ledger -- the job never ran, died "
                f"before its session finished, or the matrix lost it"
            )
    for shard in sorted(set(by_shard) - set(range(1, expect + 1))):
        problems.append(f"ledger for shard {shard}, outside 1..{expect}")
    if not by_shard:
        return problems

    # MULTISETS of stable ids (see `stable_id`): after normalising, two real
    # tests may share a key, and a set would let one of them go missing
    # unnoticed. Counts cannot.
    first = min(by_shard)
    universe = Counter(stable_id(n) for n in by_shard[first]["collected"])
    if not universe:
        problems.append("the collected set is EMPTY -- a pass here would be vacuous")
    for shard, ledger in sorted(by_shard.items()):
        theirs = Counter(stable_id(n) for n in ledger["collected"])
        if theirs != universe:
            problems.append(
                f"shard {shard} collected a DIFFERENT suite from shard {first} "
                f"({(theirs - universe).total()} extra, "
                f"{(universe - theirs).total()} missing) -- the shards packed "
                f"different partitions"
            )
        if not ledger["ran"]:
            problems.append(f"shard {shard}: ran ZERO tests")

    ran = Counter[str]()
    ran_by: dict[str, list[int]] = {}
    for shard, ledger in sorted(by_shard.items()):
        for nodeid in ledger["ran"]:
            ran[stable_id(nodeid)] += 1
            ran_by.setdefault(stable_id(nodeid), []).append(shard)
    twice = sorted(k for k in ran if ran[k] > universe[k] > 0)
    if twice:
        problems.append(f"{len(twice)} test(s) ran MORE THAN ONCE:")
        problems += [
            f"    {k}  <- shards {', '.join(map(str, ran_by[k]))}" for k in twice[:20]
        ]
    missing = universe - ran
    if missing:
        where = Counter[str]()
        for key, count in missing.items():
            where[file_of(key)] += count
        problems.append(
            f"{missing.total()} collected test(s) were run by NO shard, in "
            f"{len(where)} file(s):"
        )
        problems += [f"    {c:5d}  {f}" for f, c in where.most_common(25)]
    extra = sorted(k for k in ran if k not in universe)
    if extra:
        problems.append(
            f"{len(extra)} test(s) ran that the collection does not contain:"
        )
        problems += [f"    {n}" for n in extra[:20]]
    return problems


#: A random (version 4) UUID. Some suites parametrize on `uuid.uuid4()` at
#: import time (services/gateway/tests/test_*_proxy.py, 14 ids on 2026-09-25),
#: so the same test has a different node id in every process. The v4 shape is
#: required so fixed ids like 00000000-...-0000000000a5 still compare exactly.
_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def stable_id(nodeid: str) -> str:
    """*nodeid* with random UUIDs masked, so two processes agree on it."""
    return _UUID4.sub("<uuid4>", nodeid)


def unstable_files(ledgers: list[dict[str, Any]]) -> list[str]:
    """Files whose node ids needed `stable_id` to compare."""
    ids = (n for ledger in ledgers for n in ledger["collected"])
    return sorted({file_of(n) for n in ids if stable_id(n) != n})


def read_ledgers(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(directory.rglob("*.json"))]


def workflow_problems(text: str) -> list[str]:
    """ci.yml's matrix, its `--shard .../N` and its `--expect-shards N` agree."""
    problems: list[str] = []
    matrix = re.search(r"^\s*shard:\s*\[([^\]]*)\]", text, re.MULTILINE)
    runs = set(re.findall(r"\$\{\{\s*matrix\.shard\s*\}\}/(\d+)", text))
    expects = set(re.findall(r"--expect-shards\s+(\d+)", text))
    if matrix is None:
        return ["no `shard: [...]` matrix in the workflow"]
    listed = [s.strip().strip("'\"") for s in matrix.group(1).split(",") if s.strip()]
    if len(runs) != 1:
        problems.append(f"every `matrix.shard/N` must use one N, found {sorted(runs)}")
    if len(expects) != 1:
        problems.append(f"want one `--expect-shards N`, found {sorted(expects)}")
    if problems:
        return problems
    n = int(runs.pop())
    if listed != [str(i) for i in range(1, n + 1)]:
        problems.append(
            f"matrix lists {listed} but the run packs for {n} shards -- a shard "
            f"only one side knows about never runs"
        )
    if int(expects.pop()) != n:
        problems.append("--expect-shards disagrees with the run's /N")
    return problems


def cmd_check(directory: Path, expect: int, workflow: Path | None) -> int:
    ledgers = read_ledgers(directory) if directory.is_dir() else []
    problems = reconcile(ledgers, expect)
    if workflow is not None:
        problems += workflow_problems(workflow.read_text())
    print("\n== pytest shard coverage ==")
    print("  shard    assigned    ran   test s   wall s  planned s")
    for ledger in sorted(ledgers, key=lambda d: d["shard"]):
        i = ledger["shard"]
        planned = (
            ledger["predicted_seconds"][i - 1]
            if i <= len(ledger["predicted_seconds"])
            else 0
        )
        print(
            f"  {i}/{ledger['total']:<5} {len(ledger['assigned']):>9} "
            f"{len(ledger['ran']):>6} {sum(ledger['ran'].values()):>8.0f} "
            f"{ledger['wall_seconds']:>8.0f} {planned:>10.0f}"
        )
    if ledgers:
        ran_total = sum(len(ledger["ran"]) for ledger in ledgers)
        print(
            f"  ran {ran_total} across shards, collected {len(ledgers[0]['collected'])}"
        )
        unstable = unstable_files(ledgers)
        if unstable:
            print(
                f"  {len(unstable)} file(s) parametrize on a random uuid4, so "
                f"their node ids differ per process and were compared with it "
                f"masked: " + ", ".join(unstable)
            )
        guessed = ledgers[0]["guessed_files"]
        if guessed:
            print(
                f"  {len(guessed)} file(s) not in scripts/pytest-durations.json were "
                f"priced by test count (refresh with `durations`): "
                + ", ".join(guessed[:8])
                + (" ..." if len(guessed) > 8 else "")
            )
    if problems:
        print("FAIL:")
        for line in problems:
            print(f"  {line}")
        print("== end pytest shard coverage: FAIL ==")
        return 1
    print("PASS: every collected test ran in exactly one shard")
    print("== end pytest shard coverage: PASS ==")
    return 0


def cmd_durations(directory: Path, out: Path) -> int:
    ledgers = read_ledgers(directory)
    problems = reconcile(ledgers, ledgers[0]["total"] if ledgers else 1)
    if problems:
        # A manifest from a partial run would price the absent files as
        # guesses on the next run; refuse rather than degrade quietly.
        print("pytest_shards durations: ledgers are not a complete run:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    files: dict[str, dict[str, float]] = {}
    for ledger in ledgers:
        for nodeid, seconds in ledger["ran"].items():
            entry = files.setdefault(file_of(nodeid), {"seconds": 0.0, "tests": 0})
            entry["seconds"] += seconds
            entry["tests"] += 1
    body = {
        "about": (
            "Per-file pytest seconds (setup+call+teardown) and test counts for "
            "scripts/pytest_shards.py's packing. Advisory: it moves balance, "
            "never coverage. Regenerate with `pytest_shards.py durations` from "
            "a complete set of shard ledgers."
        ),
        "seconds": {f: round(e["seconds"], 2) for f, e in sorted(files.items())},
        "tests": {f: int(e["tests"]) for f, e in sorted(files.items())},
    }
    # Flat maps of scalars at indent 2: exactly what prettier would write, so
    # `prettier --check .` stays green on a regenerated file.
    out.write_text(json.dumps(body, indent=2) + "\n")
    total = sum(e["seconds"] for e in files.values())
    print(f"pytest_shards durations: {len(files)} files, {total:.0f}s -> {out}")
    return 0


# ---------------------------------------------------------------------------


def self_test() -> int:
    fails = 0

    def expect(name: str, problems: list[str], want: str | None) -> None:
        nonlocal fails
        text = "\n".join(problems)
        ok = (not problems) if want is None else (want in text)
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        if not ok:
            fails += 1
            print(
                f"        wanted {'no problems' if want is None else repr(want)}; got:"
            )
            print("\n".join(f"        | {p}" for p in problems) or "        | (none)")

    print("pytest_shards self-test:")
    # Packing: a file absent from the manifest is still placed, exactly once.
    manifest = {
        "a.py": {"seconds": 90.0, "tests": 3},
        "b.py": {"seconds": 60.0, "tests": 30},
    }
    counts = {"a.py": 3, "b.py": 30, "c.py": 10, "d.py": 1, "e.py": 2}
    w, guessed = weights(counts, manifest)
    bins = pack(w, 3)
    placed = [f for b in bins for f in b]
    expect(
        "every discovered file is placed exactly once, manifest or not",
        []
        if sorted(placed) == sorted(counts) and len(placed) == len(set(placed))
        else [str(bins)],
        None,
    )
    expect(
        "unknown files are priced by count at the manifest's mean s/test",
        []
        if guessed == ["c.py", "d.py", "e.py"] and abs(w["c.py"] - 10 * 150 / 33) < 1e-9
        else [str(w)],
        None,
    )
    expect(
        "packing is deterministic and ignores dict order",
        [] if pack(dict(reversed(list(w.items()))), 3) == bins else ["order-dependent"],
        None,
    )
    expect(
        "the heaviest file goes first onto its own bin",
        [] if bins[0][0] == "a.py" and bins[1][0] == "b.py" else [str(bins)],
        None,
    )
    expect(
        "an empty manifest still partitions (fallback price)",
        []
        if sorted(f for b in pack(weights(counts, {})[0], 2) for f in b)
        == sorted(counts)
        else ["lost"],
        None,
    )

    # Reconcile.
    full = ["t/x.py::one", "t/x.py::two", "t/y.py::three[1]", "t/y.py::three[2]"]

    def ledger(
        shard: int, ran: list[str], total: int = 2, collected: list[str] = full
    ) -> dict[str, Any]:
        return {
            "shard": shard,
            "total": total,
            "collected": collected,
            "assigned": ran,
            "ran": {n: 0.1 for n in ran},
            "guessed_files": [],
            "predicted_seconds": [1.0] * total,
            "wall_seconds": 1.0,
        }

    good = [ledger(1, full[:2]), ledger(2, full[2:])]
    expect("an exact cover passes", reconcile(good, 2), None)
    expect(
        "a dropped test is named",
        reconcile([ledger(1, full[:2]), ledger(2, full[2:3])], 2),
        "1 collected test(s) were run by NO shard",
    )
    expect(
        "a test run twice is refused",
        reconcile([ledger(1, full[:3]), ledger(2, full[2:])], 2),
        "ran MORE THAN ONCE",
    )
    expect(
        "a missing shard is refused by number even when the union is complete",
        reconcile([ledger(1, full)], 2),
        "shard 2/2: NO ledger",
    )
    expect(
        "a shard that ran nothing is refused",
        reconcile([ledger(1, full), ledger(2, [])], 2),
        "shard 2: ran ZERO tests",
    )
    expect(
        "a matrix shorter than the packing is refused (3 planned, 2 ran)",
        reconcile([ledger(1, full[:2], 3), ledger(2, full[2:], 3)], 3),
        "shard 3/3: NO ledger",
    )
    expect(
        "shards that collected different suites are refused",
        reconcile([ledger(1, full[:2]), ledger(2, full[2:], collected=full[:3])], 2),
        "collected a DIFFERENT suite",
    )
    expect(
        "an empty collection cannot pass vacuously",
        reconcile([ledger(1, [], collected=[]), ledger(2, [], collected=[])], 2),
        "collected set is EMPTY",
    )
    expect(
        "a test outside the collection is refused",
        reconcile([ledger(1, full[:2]), ledger(2, [*full[2:], "t/z.py::bench"])], 2),
        "the collection does not contain",
    )

    # Random uuid4 parametrize ids differ per process (the gateway proxy
    # suites, found by this reconcile's first real run).
    u1 = "t/p.py::t[GET-/parts/4914c9f6-28ee-453b-833d-a49b4ac39600]"
    u2 = "t/p.py::t[GET-/parts/7365879a-0a83-4109-a341-729c78dbe089]"
    expect(
        "a uuid4 that differs between shards' collections still reconciles",
        reconcile(
            [
                ledger(1, full, collected=[*full, u1]),
                ledger(2, [u2], collected=[*full, u2]),
            ],
            2,
        ),
        None,
    )
    fixed1 = "t/p.py::t[00000000-0000-0000-0000-0000000000a5]"
    fixed2 = "t/p.py::t[00000000-0000-0000-0000-0000000000a6]"
    expect(
        "a FIXED (non-v4) uuid is still compared exactly",
        reconcile([ledger(1, full, collected=[*full, fixed1]), ledger(2, [fixed2])], 2),
        "the collection does not contain",
    )
    twins = [*full, u1, u2]  # two real tests, one masked key
    expect(
        "two tests that mask to one key: dropping one is still caught",
        reconcile(
            [ledger(1, full, collected=twins), ledger(2, [u1], collected=twins)], 2
        ),
        "1 collected test(s) were run by NO shard",
    )

    # The workflow wiring.
    wf = (
        "        shard: [1, 2, 3]\n"
        '      run: pytest_shards.py run --shard "${{ matrix.shard }}/3"\n'
        "      run: python3 scripts/pytest_shards.py check --expect-shards 3\n"
    )
    expect("consistent workflow wiring passes", workflow_problems(wf), None)
    expect(
        "a matrix missing a shard is refused",
        workflow_problems(wf.replace("[1, 2, 3]", "[1, 2]")),
        "matrix lists",
    )
    expect(
        "--expect-shards drifting from /N is refused",
        workflow_problems(wf.replace("--expect-shards 3", "--expect-shards 2")),
        "--expect-shards disagrees",
    )
    expect(
        "the real ci.yml is consistent",
        workflow_problems(WORKFLOW.read_text()),
        None,
    )
    # End to end over files, including the exit code.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "1.json").write_text(json.dumps(ledger(1, full[:2])))
        report = io.StringIO()
        # Captured: its FAIL block is the expected outcome, not lint news.
        with contextlib.redirect_stdout(report):
            code = cmd_check(base, 2, None)
        expect(
            "check exits non-zero when a shard's ledger is missing",
            []
            if code == 1 and "shard 2/2: NO ledger" in report.getvalue()
            else [f"exit {code}", *report.getvalue().splitlines()],
            None,
        )
    if fails:
        print(f"pytest_shards self-test: {fails} case(s) FAILED")
        return 1
    print("pytest_shards self-test: all cases pass")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--self-test"]:
        return self_test()
    extra: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, extra = argv[:cut], argv[cut + 1 :]
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--shard", required=True, help="I/N")
    run.add_argument("--ledger", type=Path, required=True)
    check = sub.add_parser("check")
    check.add_argument("--ledgers", type=Path, required=True)
    check.add_argument("--expect-shards", type=int, required=True)
    check.add_argument("--workflow", type=Path)
    durations = sub.add_parser("durations")
    durations.add_argument("--ledgers", type=Path, required=True)
    durations.add_argument("--out", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args.shard, args.ledger, extra)
    if args.cmd == "check":
        return cmd_check(args.ledgers, args.expect_shards, args.workflow)
    return cmd_durations(args.ledgers, args.out)


if __name__ == "__main__":
    sys.exit(main())
