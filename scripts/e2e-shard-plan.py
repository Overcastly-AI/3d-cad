#!/usr/bin/env python3
r"""Split the Playwright suite into N shards by measured DURATION, not by count.

WHY THIS EXISTS
---------------
`playwright test --shard=i/N` cuts whole spec files, in filesystem order, on
equal TEST COUNT. Cost per test varies ~20x across this suite and the expensive
specs share naming prefixes, so they are alphabetically ADJACENT and land in one
shard together. Measured (docs/QA-REVIEW.md, CI-4, four shards on one box,
serial, all green): **985 / 986 / 1556-1567 / 1052 s** for near-equal test counts
of 179 / 169 / 171 / 167 — shard 3/4 at **1.58x the median** and 36 % over a
balanced quarter, holding every `pick-*`, `preselection`, `projection`, `qa-*`
and `repick-*` spec, i.e. 100 % of the suite's settled-stamp probes and 88 % of
its pixel censuses in the FEWEST files.

Raising N does not fix that: the heavy block just moves, and the imbalance RATIO
gets worse (`--simulate` reproduces this from the manifest). The lever that does
work is to make the CUT aware of what each file costs.

THE PROPERTY THIS MUST NOT LOSE (docs/BACKLOG.md GATE-1)
--------------------------------------------------------
`scripts/e2e.sh` says sharding is DERIVED from the filesystem so that "a new
spec cannot be born outside the gate" — the failure mode this repo has hit four
times. An explicit membership list would reintroduce it, silently: a new spec
would simply never run and the board would stay green.

So the partition is computed over **the set Playwright itself discovers**, never
over the manifest:

    for every file in `playwright test --list`:      <- the filesystem, derived
        weight = manifest.get(file, PESSIMISTIC)     <- durations, advisory only
    bins = longest-processing-time packing(weights, N)

The manifest can therefore be stale, wrong, or empty and coverage is unchanged —
every discovered file is placed, because the loop is over the discovered set. A
file the manifest has never heard of is assumed to be the HEAVIEST thing in the
suite, so an unmeasured newcomer degrades BALANCE (it may be over-provisioned)
and never coverage. That asymmetry is deliberate: the optimistic default would
pile unknown files onto one shard.

Three checks make that assertable rather than intended:

1. `--self-test` includes an unlisted file and demands it be assigned, and
   demands the union of the bins equal the discovered set exactly.
2. Every real invocation VERIFIES itself: after planning, it re-runs
   `playwright test --list` with the patterns it is about to hand over and
   refuses unless the file set that comes back is exactly the planned one. That
   is not paranoia — `mirror\.spec\.ts$` also matches `sketch-mirror.spec.ts`,
   and this repo has FOUR such basename-suffix pairs today (measured), so an
   unanchored pattern would have run four files twice and left four shards short.
3. `scripts/e2e-shard-audit.py` in the `e2e complete` job independently
   reconciles the union of what the shards EXECUTED against `--list`. That audit
   used to be a check on Playwright's own sharding; with the partition computed
   here it is the cross-check on THIS script, derived a different way.

Usage:
    e2e-shard-plan.py --shard i/N --args-out FILE [--config CFG]
    e2e-shard-plan.py --plan N [--list-json FILE]
    e2e-shard-plan.py --simulate 2-10
    e2e-shard-plan.py --emit-durations REPORT.json ... --out MANIFEST
    e2e-shard-plan.py --drift REPORT.json ...
    e2e-shard-plan.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "apps" / "web"
MANIFEST = REPO / "scripts" / "e2e-durations.json"

#: Weight for a file with no measurement, used only when the manifest is EMPTY.
#: With any measurements present the default is the manifest's own maximum — see
#: `pessimistic_weight`. Both are deliberately at the top of the range.
FALLBACK_SECONDS = 300.0


# ── discovery ────────────────────────────────────────────────────────────────


def _walk(suite: dict[str, Any], out: dict[str, int]) -> None:
    for spec in suite.get("specs", []):
        file = spec.get("file") or suite.get("file") or "?"
        out[file] = out.get(file, 0) + 1
    for nested in suite.get("suites", []):
        _walk(nested, out)


def files_in_report(payload: dict[str, Any]) -> dict[str, int]:
    """file -> number of specs, from a Playwright JSON report or --list dump."""
    found: dict[str, int] = {}
    for suite in payload.get("suites", []):
        _walk(suite, found)
    return found


def playwright_list(
    config: str | None = None, extra: list[str] | None = None
) -> dict[str, Any]:
    """`playwright test --list --reporter=json` — Playwright's OWN discovery.

    Deliberately not a glob of our own: a second implementation of "which files
    are specs" is a second thing that can drift from `testMatch`, and drift here
    is a coverage hole rather than a wrong number.

    A non-zero exit REFUSES even when JSON came back. `--list` reports errors
    (a spec that fails to import, say) by exiting non-zero while still emitting
    a report of everything it *did* manage to collect — so the tolerant reading
    is precisely the one that plans a shard over a suite with files missing
    from it, and every downstream check would agree with itself: the bins
    partition what was discovered, the patterns select what was planned, and
    the `e2e complete` audit reconciles against the same truncated listing. The
    whole gate would be green over a hole. This is the one place strictness has
    to win over robustness.
    """
    cmd = [
        "pnpm",
        "--filter",
        "@loft/web",
        "exec",
        "playwright",
        "test",
        "--list",
        "--reporter=json",
    ]
    if config:
        cmd.append(f"--config={config}")
    cmd.extend(extra or [])
    proc = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, check=False, timeout=600
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"e2e-shard-plan: `playwright test --list` failed ({proc.returncode}) — "
            "refusing to plan over a listing that may be incomplete:\n"
            f"{proc.stderr[-2000:]}\n{proc.stdout[:500]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostics
        raise SystemExit(
            f"e2e-shard-plan: could not parse `--list` output: {exc}\n"
            f"{proc.stdout[:500]}"
        ) from exc


# ── durations ────────────────────────────────────────────────────────────────


def load_manifest(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return {str(k): float(v) for k, v in payload.get("files", {}).items()}


def pessimistic_weight(durations: dict[str, float]) -> float:
    """What an UNMEASURED file is assumed to cost: the heaviest known file.

    Assume-heavy is the whole safety argument. An unmeasured file is most often
    a brand-new spec, and this suite's new specs skew expensive (the viewport
    censuses are the newest and slowest things in it). Guessing light would put
    the next `qa-*` spec on whichever shard is already worst.
    """
    return max(durations.values()) if durations else FALLBACK_SECONDS


# ── packing ──────────────────────────────────────────────────────────────────


def plan_bins(
    discovered: dict[str, int], durations: dict[str, float], n: int
) -> tuple[list[list[str]], list[float], list[str]]:
    """Longest-processing-time packing of the DISCOVERED files into n bins.

    Returns (bins, bin weights, files that had no measurement).

    LPT rather than anything cleverer because the input is ~145 items with one
    hard constraint — a spec file is ATOMIC, it cannot be split across shards —
    so no algorithm can beat `max(single file)` and LPT is within 4/3 - 1/(3n)
    of optimal. Measured against the real manifest it lands within 2 % of the
    ideal quarter, i.e. the residual imbalance is the biggest file, not the
    packer.
    """
    if n < 1:
        raise SystemExit(f"e2e-shard-plan: shard count must be >= 1, got {n}")
    if not discovered:
        # 0 == 0 is the vacuous pass every gate in this repo has a guard for.
        raise SystemExit(
            "e2e-shard-plan: `playwright test --list` discovered NO spec files — "
            "the listing itself is broken; refusing to plan a shard over nothing."
        )
    if len(discovered) < n:
        raise SystemExit(
            f"e2e-shard-plan: {len(discovered)} spec file(s) cannot fill {n} "
            "shards — one shard would run nothing, which reports success while "
            "covering nothing."
        )

    default = pessimistic_weight(durations)
    unmeasured = sorted(f for f in discovered if f not in durations)
    weighted = sorted(
        ((durations.get(f, default), f) for f in discovered),
        key=lambda item: (-item[0], item[1]),
    )
    bins: list[list[str]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for weight, file in weighted:
        target = min(range(n), key=lambda i: (loads[i], i))
        bins[target].append(file)
        loads[target] += weight
    for i in range(n):
        bins[i].sort()
    if any(not b for b in bins):
        raise SystemExit(
            "e2e-shard-plan: packing left an empty shard — refusing to emit a "
            "plan in which a shard runs nothing."
        )
    # THE COVERAGE INVARIANT, CHECKED ON EVERY REAL CALL — not only under
    # --self-test. The self-test proves the property for ITS fixture; this
    # proves it for the suite actually being sharded, which is the one that
    # matters and the one a future edit to the packing loop could break. It is
    # an O(n) set comparison over ~145 strings.
    assert_partition(bins, discovered)
    return bins, loads, unmeasured


def assert_partition(bins: list[list[str]], discovered: dict[str, int]) -> None:
    """Every discovered file in exactly one bin, or refuse.

    Its own function so `--self-test` can hand it a DELIBERATELY broken
    partition and demand a refusal. Asserting this only via `plan_bins`'s happy
    path would be a check on a correct packer, which cannot fail and therefore
    proves nothing about the guard.
    """
    placed = [f for b in bins for f in b]
    if sorted(placed) == sorted(discovered):
        return
    lost = sorted(set(discovered) - set(placed))
    twice = sorted({f for f in placed if placed.count(f) > 1})
    raise SystemExit(
        "e2e-shard-plan: the packing is not a PARTITION of the discovered set "
        f"— {len(lost)} file(s) would run in NO shard ({', '.join(lost[:5])}), "
        f"{len(twice)} in more than one ({', '.join(twice[:5])})."
    )


def fingerprint(bins: list[list[str]]) -> str:
    """A short digest of the WHOLE partition, printed by every shard.

    The four shards plan independently, and nothing forces them to agree: they
    agree because the manifest is committed and discovery is deterministic. If
    that ever stops being true the `e2e complete` audit catches it — but only
    after the whole suite has run, and it reports the symptom (tests executed
    by no shard) rather than the cause. Printing this makes the cause one grep
    across four job logs: four equal fingerprints mean the shards partitioned
    the same suite the same way.
    """
    payload = "\n".join("\t".join(b) for b in bins)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def pattern_for(file: str) -> str:
    """A Playwright positional filter that selects EXACTLY this file.

    MEASURED, not assumed (2026-08-29, `playwright test --list`):

        mirror\\.spec\\.ts$     -> mirror.spec.ts AND sketch-mirror.spec.ts
        /mirror\\.spec\\.ts$    -> mirror.spec.ts
        ^mirror\\.spec\\.ts$    -> nothing at all

    So the argument is a regex tested against a path with a prefix above
    testDir: `^` can never match, and a bare `$`-anchored basename cross-matches
    any file whose name ENDS with it. There are four such pairs in the suite
    right now (fillet-chamfer/sketch-fillet-chamfer, mirror/sketch-mirror,
    pattern/sheet-metal-flat-pattern, undo-redo/assembly-undo-redo), so the
    leading separator is load-bearing: without it those four run twice and four
    other shards come up short.
    """
    return "/" + re.escape(file) + "$"


# ── reporting ────────────────────────────────────────────────────────────────


def describe(
    bins: list[list[str]],
    loads: list[float],
    discovered: dict[str, int],
    unmeasured: list[str],
    stream: Any = sys.stdout,
) -> None:
    total = sum(loads)
    n = len(bins)
    ideal = total / n
    worst = max(loads)
    print(
        f"plan: {len(discovered)} spec files into {n} shards "
        f"[fingerprint {fingerprint(bins)}]",
        file=stream,
    )
    for i, (files, load) in enumerate(zip(bins, loads, strict=True), start=1):
        tests = sum(discovered[f] for f in files)
        print(
            f"  shard {i}/{n}: {len(files):3d} files  {tests:4d} tests  "
            f"{load / 60:6.1f} min predicted  ({load / ideal:.2f}x ideal)",
            file=stream,
        )
    print(
        f"  critical path {worst / 60:.1f} min vs {ideal / 60:.1f} min ideal "
        f"= {worst / ideal:.2f}x",
        file=stream,
    )
    if unmeasured:
        shown = ", ".join(unmeasured[:8])
        more = f" (+{len(unmeasured) - 8} more)" if len(unmeasured) > 8 else ""
        print(
            f"  {len(unmeasured)} file(s) have no measured duration and were "
            f"assumed to be the heaviest in the suite: {shown}{more}",
            file=stream,
        )
        print(
            "  -> balance is degraded, coverage is not. Refresh with "
            "`e2e-shard-plan.py --emit-durations`.",
            file=stream,
        )


def verify(planned: list[str], patterns: list[str], config: str | None) -> list[str]:
    """Re-ask Playwright what these patterns select. Returns problems, if any.

    The plan is only as good as the patterns that carry it, and those are
    regexes going through a CLI. This turns "the anchoring works" into a fact
    established on every run, in ~3 s, instead of a comment that was true when
    it was written.
    """
    selected = set(files_in_report(playwright_list(config, patterns)))
    want = set(planned)
    problems: list[str] = []
    extra = sorted(selected - want)
    missing = sorted(want - selected)
    if extra:
        problems.append(
            f"{len(extra)} file(s) matched that this shard did not plan to run "
            f"(another shard will run them too): {', '.join(extra[:10])}"
        )
    if missing:
        problems.append(
            f"{len(missing)} planned file(s) matched nothing: {', '.join(missing[:10])}"
        )
    return problems


# ── manifest maintenance ─────────────────────────────────────────────────────


def durations_from_reports(paths: list[Path]) -> tuple[dict[str, float], list[str]]:
    """Per-file seconds, summed from Playwright JSON reports.

    Uses the reports the e2e workflow ALREADY uploads (`E2E_JSON_REPORT`), so
    this is not a third measurement path — it is the second reader of the one
    that exists, the first being `e2e-shard-audit.py --timeline`.
    """
    totals: dict[str, float] = {}
    notes: list[str] = []
    for path in paths:
        if not path.exists():
            notes.append(f"{path} is missing")
            continue
        payload = json.loads(path.read_text())
        found: dict[str, float] = {}
        for suite in payload.get("suites", []):
            _collect_durations(suite, found)
        for file, ms in found.items():
            totals[file] = totals.get(file, 0.0) + ms / 1000.0
    return totals, notes


def _collect_durations(suite: dict[str, Any], found: dict[str, float]) -> None:
    for spec in suite.get("specs", []):
        file = spec.get("file") or suite.get("file") or "?"
        for test in spec.get("tests", []):
            for result in test.get("results", []):
                found[file] = found.get(file, 0.0) + float(
                    result.get("duration", 0) or 0
                )
    for nested in suite.get("suites", []):
        _collect_durations(nested, found)


def write_manifest(path: Path, totals: dict[str, float], note: str) -> None:
    payload = {
        "note": note,
        "unit": "seconds of Playwright test time per spec file, one worker",
        "files": {k: round(v, 1) for k, v in sorted(totals.items())},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────


def cmd_shard(args: argparse.Namespace) -> int:
    discovered = files_in_report(playwright_list(args.config))
    durations = load_manifest(args.durations)
    index, n = cast("tuple[int, int]", args.shard)
    bins, loads, unmeasured = plan_bins(discovered, durations, n)
    files = bins[index - 1]
    patterns = [pattern_for(f) for f in files]
    # One pattern per planned file, no more and no fewer. Cheap, and it is the
    # difference between "the plan was right" and "the plan was right and the
    # thing handed to Playwright says the same".
    if len(patterns) != len(files) or len(set(patterns)) != len(set(files)):
        raise SystemExit(
            f"e2e-shard-plan: {len(files)} planned file(s) produced "
            f"{len(set(patterns))} distinct pattern(s) — refusing."
        )
    describe(bins, loads, discovered, unmeasured, stream=sys.stderr)
    print(
        f"shard {index}/{n} will run {len(files)} file(s), "
        f"{loads[index - 1] / 60:.1f} min predicted",
        file=sys.stderr,
    )
    if not args.no_verify:
        problems = verify(files, patterns, args.config)
        if problems:
            print(
                "e2e-shard-plan: the patterns do NOT select the planned files:",
                file=sys.stderr,
            )
            for line in problems:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(
            f"verified: `playwright test --list` with these patterns returns "
            f"exactly the {len(files)} planned file(s)",
            file=sys.stderr,
        )
    args.args_out.write_text("\n".join(patterns) + "\n")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    if args.list_json:
        discovered = files_in_report(json.loads(args.list_json.read_text()))
    else:
        discovered = files_in_report(playwright_list(args.config))
    durations = load_manifest(args.durations)
    bins, loads, unmeasured = plan_bins(discovered, durations, args.plan)
    describe(bins, loads, discovered, unmeasured)
    if args.verbose:
        # Print the weight the PACKER used, not the manifest lookup. An
        # unmeasured file printed as `0.0 min` says the opposite of what
        # happened to it — it was packed as the heaviest file in the suite —
        # and a listing that contradicts the safety property is how the
        # property gets "simplified away" by the next reader.
        default = pessimistic_weight(durations)
        for i, files in enumerate(bins, start=1):
            print(f"\nshard {i}/{args.plan}:")
            for f in files:
                mark = "" if f in durations else "  (unmeasured -> assumed heaviest)"
                print(f"  {durations.get(f, default) / 60:5.1f} min  {f}{mark}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    if args.list_json:
        discovered = files_in_report(json.loads(args.list_json.read_text()))
    else:
        discovered = files_in_report(playwright_list(args.config))
    durations = load_manifest(args.durations)
    low, high = args.simulate
    total = sum(durations.get(f, pessimistic_weight(durations)) for f in discovered)
    biggest = max(durations.get(f, 0.0) for f in discovered)
    print(
        f"suite {total / 60:.1f} min across {len(discovered)} files; "
        f"the largest single file is {biggest / 60:.1f} min, which is the floor "
        "no shard count can go below"
    )
    print(f"{'N':>3}  {'ideal':>8}  {'critical':>9}  {'ratio':>6}  runner-min")
    for n in range(low, high + 1):
        if len(discovered) < n:
            break
        _, loads, _ = plan_bins(discovered, durations, n)
        ideal = total / n
        worst = max(loads)
        # ~4 min of setup per shard (uv sync, pnpm install, browser install),
        # the number the e2e.yml header already uses for this trade.
        runner = total / 60 + 4 * n
        print(
            f"{n:>3}  {ideal / 60:7.1f}m  {worst / 60:8.1f}m  "
            f"{worst / ideal:5.2f}x  {runner:8.0f}"
        )
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    totals, notes = durations_from_reports(args.emit_durations)
    for line in notes:
        print(f"  note: {line}", file=sys.stderr)
    if not totals:
        print(
            "e2e-shard-plan: those reports carried no per-file timing — "
            "refusing to write an empty manifest over a good one.",
            file=sys.stderr,
        )
        return 1
    write_manifest(args.out, totals, args.note)
    print(
        f"wrote {len(totals)} file durations to {args.out} "
        f"(total {sum(totals.values()) / 60:.1f} min)"
    )
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    """Report manifest staleness. Prints; never votes.

    Same contract as `e2e-shard-audit.py --timeline`: a timing assertion in CI
    is a flake generator, and the pass/fail contract of the e2e gate is coverage,
    not speed. What this buys is that "the manifest went stale" is visible on
    green runs instead of being discovered as a slow shard months later.
    """
    observed, notes = durations_from_reports(args.drift)
    for line in notes:
        print(f"  note: {line}")
    manifest = load_manifest(args.durations)
    if not observed:
        print("manifest drift: no per-file timing in these reports — nothing to say.")
        return 0
    unknown = sorted(set(observed) - set(manifest))
    gone = sorted(set(manifest) - set(observed))
    moved: list[tuple[str, float, float]] = []
    for file, seconds in sorted(observed.items()):
        was = manifest.get(file)
        if was and was > 0 and (seconds / was > 2 or was / seconds > 2):
            moved.append((file, was, seconds))
    print("\n== duration manifest drift ==================================")
    print(
        f"manifest {len(manifest)} files / {sum(manifest.values()) / 60:.1f} min; "
        f"this run {len(observed)} files / {sum(observed.values()) / 60:.1f} min"
    )
    if unknown:
        print(f"  {len(unknown)} file(s) not in the manifest (packed as HEAVIEST):")
        for f in unknown[:15]:
            print(f"    {observed[f] / 60:5.1f} min  {f}")
    if gone:
        print(f"  {len(gone)} manifest entry/entries no longer exist: {gone[:10]}")
    if moved:
        print(f"  {len(moved)} file(s) moved by more than 2x:")
        for f, was, now in moved[:15]:
            print(f"    {was / 60:5.1f} -> {now / 60:5.1f} min  {f}")
    if unknown or moved:
        print(
            "  -> refresh: python3 scripts/e2e-shard-plan.py --emit-durations "
            "shard-reports/*.json --out scripts/e2e-durations.json"
        )
    else:
        print("  manifest is current.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--shard",
        type=_shard_spec,
        help="i/N — emit this shard's Playwright file patterns to --args-out",
    )
    mode.add_argument("--plan", type=int, help="print the whole N-way plan")
    mode.add_argument(
        "--simulate",
        type=_range_spec,
        help="LOW-HIGH — critical path vs ideal for each shard count",
    )
    mode.add_argument(
        "--emit-durations",
        nargs="+",
        type=Path,
        metavar="REPORT",
        help="rebuild the manifest from Playwright JSON reports",
    )
    mode.add_argument(
        "--drift",
        nargs="+",
        type=Path,
        metavar="REPORT",
        help="report how stale the manifest is against these reports",
    )
    parser.add_argument("--args-out", type=Path, help="where --shard writes patterns")
    parser.add_argument("--config", help="Playwright --config passed to discovery")
    parser.add_argument("--durations", type=Path, default=MANIFEST)
    parser.add_argument("--list-json", type=Path, help="a pre-computed --list dump")
    parser.add_argument("--out", type=Path, default=MANIFEST)
    parser.add_argument("--note", default="regenerated from a full sharded run")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the `--list` re-check of the emitted patterns (tests only)",
    )
    return parser


def _shard_spec(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)/(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"expected i/N, got {value!r}")
    index, total = int(match.group(1)), int(match.group(2))
    if not 1 <= index <= total:
        raise argparse.ArgumentTypeError(f"shard {index} is not within 1..{total}")
    return index, total


def _range_spec(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)-(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"expected LOW-HIGH, got {value!r}")
    return int(match.group(1)), int(match.group(2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.shard:
        if not args.args_out:
            raise SystemExit("e2e-shard-plan: --shard requires --args-out")
        return cmd_shard(args)
    if args.plan:
        return cmd_plan(args)
    if args.simulate:
        return cmd_simulate(args)
    if args.emit_durations:
        return cmd_emit(args)
    return cmd_drift(args)


# ── self-test ────────────────────────────────────────────────────────────────
# A gate nobody has watched fail is not a gate. This one decides which specs run
# at all, so the check that matters most is GATE-1's: a file the manifest has
# never heard of must still be executed by some shard.

#: See e2e-shard-audit.py — `all([])` is True, so a lost `checks.append` would
#: remove coverage while the self-test still printed success.
EXPECTED_CHECKS = 21


def self_test() -> int:
    checks: list[tuple[bool, str]] = []

    def ok(condition: bool, label: str) -> None:
        checks.append((bool(condition), label))

    # A synthetic suite whose costs are as lopsided as the real one: four heavy
    # files with adjacent names (the real defect) plus a long tail.
    discovered = {f"qa-heavy-{i}.spec.ts": 10 for i in range(4)}
    discovered.update({f"light-{i:02d}.spec.ts": 3 for i in range(20)})
    durations = {f"qa-heavy-{i}.spec.ts": 300.0 for i in range(4)}
    durations.update({f"light-{i:02d}.spec.ts": 30.0 for i in range(20)})

    bins, loads, unmeasured = plan_bins(discovered, durations, 4)
    placed = [f for b in bins for f in b]
    ok(sorted(placed) == sorted(discovered), "every discovered file is placed")
    ok(len(placed) == len(set(placed)), "no file is placed twice")
    ok(not unmeasured, "a fully measured suite reports nothing unmeasured")
    ok(max(loads) / (sum(loads) / 4) < 1.10, "packing lands within 10% of ideal")
    ok(
        all(len({f.split("-")[0] for f in b}) > 1 for b in bins),
        "the four adjacent heavy files do not all land together",
    )

    # THE GATE-1 PROPERTY. A spec that exists on disk but is in no manifest must
    # still run, and must be treated as expensive.
    newcomer = dict(discovered)
    newcomer["brand-new-and-unmeasured.spec.ts"] = 5
    bins_n, _loads_n, unmeasured_n = plan_bins(newcomer, durations, 4)
    placed_n = [f for b in bins_n for f in b]
    ok(
        placed_n.count("brand-new-and-unmeasured.spec.ts") == 1,
        "GATE-1: an unlisted spec is assigned to exactly one shard",
    )
    ok(
        unmeasured_n == ["brand-new-and-unmeasured.spec.ts"],
        "…and is REPORTED as unmeasured rather than passing silently",
    )
    ok(
        pessimistic_weight(durations) == max(durations.values()),
        "…weighted as the heaviest known file, never the lightest",
    )
    # Whole manifest gone: still a complete partition, just a worse one.
    bins_e, _, unmeasured_e = plan_bins(discovered, {}, 4)
    ok(
        sorted(f for b in bins_e for f in b) == sorted(discovered),
        "an EMPTY manifest still covers every file",
    )
    ok(len(unmeasured_e) == len(discovered), "…and says every file is unmeasured")
    # A manifest naming files that no longer exist must not resurrect them.
    stale = dict(durations)
    stale["deleted-last-month.spec.ts"] = 999.0
    bins_s, _, _ = plan_bins(discovered, stale, 4)
    ok(
        "deleted-last-month.spec.ts" not in {f for b in bins_s for f in b},
        "a manifest entry with no file on disk is not run",
    )

    # Refusals — each is a "gate that cannot fail" shape. Asserted on the
    # REASON, not merely on the exception: the empty-discovery and
    # too-few-files guards both fire on an empty listing, so a check that only
    # demanded "it raised" would pass with the vacuous-pass guard deleted.
    # (Measured: removing `if not discovered` left the self-test green until
    # this check named the message.)
    for label, needle, call in (
        (
            "an empty discovery refuses, naming the LISTING as broken",
            "the listing itself is broken",
            lambda: plan_bins({}, durations, 4),
        ),
        (
            "more shards than files refuses (a shard would run nothing)",
            "would run nothing",
            lambda: plan_bins({"only.spec.ts": 1}, {}, 4),
        ),
        (
            "a shard count below 1 refuses",
            "must be >= 1",
            lambda: plan_bins(discovered, {}, 0),
        ),
    ):
        try:
            call()
        except SystemExit as exc:
            ok(needle in str(exc), label)
        else:
            ok(False, label)

    # Pattern anchoring, against the real collision pairs. MEASURED against
    # Playwright itself (see pattern_for's docstring); replayed here with
    # python's engine, which agrees for this character class.
    paths = [
        "/repo/apps/web/e2e/mirror.spec.ts",
        "/repo/apps/web/e2e/sketch-mirror.spec.ts",
        "/repo/apps/web/e2e/undo-redo.spec.ts",
        "/repo/apps/web/e2e/assembly-undo-redo.spec.ts",
    ]
    hits = [p for p in paths if re.search(pattern_for("mirror.spec.ts"), p)]
    ok(hits == ["/repo/apps/web/e2e/mirror.spec.ts"], "a pattern selects ONE file")
    naive = [p for p in paths if re.search(re.escape("mirror.spec.ts") + "$", p)]
    ok(
        len(naive) == 2,
        "…and the negative control (no leading separator) really does cross-match",
    )

    # Determinism: four shards plan independently and must agree.
    ok(
        all(plan_bins(discovered, durations, 4)[0] == bins for _ in range(3)),
        "the plan is deterministic across independent invocations",
    )

    # THE PARTITION GUARD, against a deliberately broken partition in BOTH
    # directions. A guard written against one failure tends to encode that
    # failure's direction, so both are exercised by name: a file in no bin
    # (coverage hole) and a file in two (double-run, which the `e2e complete`
    # audit reports as a duplicate rather than as a hole).
    dropped = [list(b) for b in bins]
    dropped[0] = dropped[0][1:]
    try:
        assert_partition(dropped, discovered)
    except SystemExit as exc:
        ok("in NO shard" in str(exc), "a file placed in no bin is REFUSED")
    else:
        ok(False, "a file placed in no bin is REFUSED")
    doubled = [list(b) for b in bins]
    doubled[1] = [*doubled[1], bins[0][0]]
    try:
        assert_partition(doubled, discovered)
    except SystemExit as exc:
        ok("more than one" in str(exc), "a file placed in two bins is REFUSED")
    else:
        ok(False, "a file placed in two bins is REFUSED")

    # The fingerprint is only useful if it MOVES when the partition does — a
    # constant digest would read as "the four shards agree" forever.
    ok(
        fingerprint(bins) == fingerprint(plan_bins(discovered, durations, 4)[0]),
        "the fingerprint is stable for an identical plan",
    )
    ok(
        fingerprint(bins) != fingerprint(plan_bins(discovered, durations, 3)[0])
        and fingerprint(bins) != fingerprint(dropped),
        "…and CHANGES when the partition changes (so it can detect a mismatch)",
    )

    for good, label in checks:
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
    if len(checks) < EXPECTED_CHECKS:
        print(
            f"\ne2e-shard-plan: SELF-TEST RAN {len(checks)} of {EXPECTED_CHECKS} "
            "checks — it lost coverage and proves nothing."
        )
        return 1
    if all(good for good, _ in checks):
        print("\ne2e-shard-plan: self-test passed — the planner can refuse.")
        return 0
    print("\ne2e-shard-plan: SELF-TEST FAILED.")
    return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
