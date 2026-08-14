#!/usr/bin/env python3
"""Reconcile what the sharded Playwright run EXECUTED against what exists.

A sharded gate has a failure mode a green tick cannot show you: the shards
stop covering. `--shard=i/N` where the workflow says N=4 but the matrix lists
three entries, a spec file that stops matching `testMatch`, a shard whose job
was skipped — each of those leaves specs that no shard ever ran, and every job
that DID run still reports success. That is the "gate that cannot fail" class
this repo has now hit four times (a hand-listed axis, a compose smoke that
never ran, `gen-check` measuring the wrong input, and e2e not being wired to
CI at all), so the sharding that makes the browser gate affordable ships with
the control that makes it honest.

The expected set is DERIVED, never enumerated: `playwright test --list
--reporter=json` walks the filesystem, so a spec added tomorrow is in the
expected set the moment it lands. This script fails unless the union of the
shards' executed tests is EXACTLY that set — no test missing, none run twice.

`--timeline` additionally prints, per shard, every test in EXECUTION order with
its offset into the shard and its duration. That costs no new capture: the
reports this job already downloads carry `results[].startTime` and `duration`,
so the question "do failures cluster late in a shard, when the runner has been
under load for ten minutes?" (docs/BACKLOG.md CI-4) is answerable from evidence
already on disk, for every red from now on. It is printed, never asserted on —
a timing report that can fail the build would be a flake generator, and the
pass/fail contract above is the one thing this script must not blur.

Usage:
    e2e-shard-audit.py --discovered LIST.json REPORT.json [REPORT.json ...]
    e2e-shard-audit.py --self-test

Both inputs are Playwright JSON reports (`--reporter=json`); `--discovered`
is the one produced by `--list`, which reports every test as skipped and is
therefore useless for pass/fail but exact for identity.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class Spec:
    """One Playwright spec, keyed by its stable generated id."""

    def __init__(
        self,
        spec_id: str,
        file: str,
        title: str,
        statuses: list[str],
        start: datetime | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        self.id = spec_id
        self.file = file
        self.title = title
        self.statuses = statuses
        self.start = start
        self.duration_ms = duration_ms

    @property
    def failed(self) -> bool:
        return "unexpected" in self.statuses or "timedOut" in self.statuses

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.file} :: {self.title}"


def _parse_start(value: str | None) -> datetime | None:
    """Playwright writes `startTime` as ISO-8601 with a trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _walk(suite: dict[str, Any], out: dict[str, Spec]) -> None:
    for spec in suite.get("specs", []):
        statuses = [test.get("status", "unknown") for test in spec.get("tests", [])]
        starts: list[datetime] = []
        duration_ms = 0.0
        for test in spec.get("tests", []):
            for result in test.get("results", []):
                started = _parse_start(result.get("startTime"))
                if started is not None:
                    starts.append(started)
                duration_ms += float(result.get("duration", 0) or 0)
        out[spec["id"]] = Spec(
            spec_id=spec["id"],
            file=spec.get("file", suite.get("file", "?")),
            title=spec.get("title", "?"),
            statuses=statuses,
            start=min(starts) if starts else None,
            duration_ms=duration_ms,
        )
    for nested in suite.get("suites", []):
        _walk(nested, out)


def read_report(path: Path) -> dict[str, Spec]:
    """Every spec in one Playwright JSON report, keyed by spec id."""
    with path.open() as handle:
        payload = json.load(handle)
    found: dict[str, Spec] = {}
    for suite in payload.get("suites", []):
        _walk(suite, found)
    return found


def print_timeline(per_shard: dict[str, dict[str, Spec]]) -> None:
    """Print each shard's tests in execution order, with offsets and durations.

    Read-only by design: this answers "WHERE in the shard did it die?", which is
    the question a one-spec-in-116 red raises and which no artifact we upload
    answers today. It cannot change the verdict.
    """
    slowest: list[tuple[float, str, Spec]] = []
    print("\n== timeline ==================================================")
    print(
        "(times are UTC; join to resources.csv in the e2e-diagnostics-shard-N "
        "artifact by wall clock)"
    )
    for name, specs in per_shard.items():
        timed: list[tuple[datetime, Spec]] = [
            (spec.start, spec) for spec in specs.values() if spec.start is not None
        ]
        timed.sort(key=lambda item: (item[0], item[1].file, item[1].title))
        if not timed:
            print(f"\n{name}: no result carried a startTime — nothing to order.")
            continue
        first = timed[0][0]
        last_end = max(
            start.timestamp() + spec.duration_ms / 1000 for start, spec in timed
        )
        wall_s = last_end - first.timestamp()
        total = len(timed)
        print(
            f"\n{name}: {total} tests, {wall_s / 60:.1f} min wall "
            f"(first test started {first.isoformat()})"
        )
        failures: list[tuple[int, float, Spec]] = []
        for ordinal, (start, spec) in enumerate(timed, start=1):
            offset_s = (start - first).total_seconds()
            status = "FAIL" if spec.failed else (spec.statuses or ["?"])[0]
            print(
                f"  {ordinal:>4}/{total}  t+{offset_s / 60:6.1f}m"
                f"  {spec.duration_ms / 1000:6.1f}s  {status:<10} {spec}"
            )
            slowest.append((spec.duration_ms, name, spec))
            if spec.failed:
                failures.append((ordinal, offset_s, spec))
        for ordinal, offset_s, spec in failures:
            print(
                f"  => {name}: failed at test {ordinal}/{total}, "
                f"{offset_s / 60:.1f} min into a {wall_s / 60:.1f} min shard "
                f"({100 * ordinal // total}% of the way through) — {spec}"
            )

    if slowest:
        print("\nslowest 10 tests across all shards:")
        for duration_ms, name, spec in sorted(
            slowest, key=lambda item: item[0], reverse=True
        )[:10]:
            print(f"  {duration_ms / 1000:6.1f}s  {name}  {spec}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--discovered",
        required=True,
        type=Path,
        help="JSON report from `playwright test --list` (the expected set)",
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="JSON report from each shard's run",
    )
    parser.add_argument(
        "--fail-on-flaky",
        action="store_true",
        help=(
            "treat a test that only passed on retry as a failure. Off while the "
            "known racy specs are still being hardened — see docs/BACKLOG.md; "
            "flakes are always REPORTED either way."
        ),
    )
    parser.add_argument(
        "--timeline",
        action="store_true",
        help=(
            "print each shard's tests in execution order with their offset into "
            "the shard, plus the slowest 10. Never changes the verdict."
        ),
    )
    args = parser.parse_args(argv)

    problems: list[str] = []

    discovered = read_report(args.discovered)
    if not discovered:
        # 0 == 0 is the vacuous pass this whole script exists to prevent.
        print(
            f"FAIL: {args.discovered} discovered NO tests — "
            "the listing itself is broken."
        )
        return 1
    files = len({spec.file for spec in discovered.values()})
    print(f"discovered: {len(discovered)} tests in {files} spec files")

    executed: dict[str, str] = {}  # spec id -> shard that ran it
    duplicates: list[tuple[Spec, str, str]] = []
    flaky: list[Spec] = []
    per_shard: dict[str, dict[str, Spec]] = {}
    for report in args.reports:
        if not report.exists():
            problems.append(
                f"shard report {report} is missing — "
                "that shard produced no evidence it ran"
            )
            continue
        specs = read_report(report)
        per_shard[report.name] = specs
        if not specs:
            problems.append(
                f"shard report {report} contains ZERO tests — that shard ran nothing"
            )
        statuses: dict[str, int] = {}
        for spec_id, spec in specs.items():
            for status in spec.statuses:
                statuses[status] = statuses.get(status, 0) + 1
            if "flaky" in spec.statuses:
                flaky.append(spec)
            if spec_id in executed:
                duplicates.append((spec, executed[spec_id], report.name))
            executed[spec_id] = report.name
        summary = ", ".join(
            f"{count} {name}" for name, count in sorted(statuses.items())
        )
        print(f"  {report.name}: {len(specs)} tests ({summary})")

    missing = [discovered[i] for i in sorted(set(discovered) - set(executed))]
    if missing:
        problems.append(f"{len(missing)} discovered test(s) were run by NO shard:")
        problems.extend(f"    {spec}" for spec in missing[:20])
        if len(missing) > 20:
            problems.append(f"    … and {len(missing) - 20} more")

    unknown = sorted(set(executed) - set(discovered))
    if unknown:
        # Not a coverage hole, but it means the two sides disagree about what
        # exists, so the equality above is no longer meaningful evidence.
        problems.append(
            f"{len(unknown)} executed test(s) are not in the discovered set — "
            "the listing and the run disagree about what exists"
        )

    for spec, first, second in duplicates:
        problems.append(f"ran twice ({first} and {second}): {spec}")

    print(f"executed:   {len(executed)} tests across {len(args.reports)} shard(s)")

    # A test that only passed on retry is a defect — usually a fixed sleep
    # followed by a non-retrying assertion — and the reason to surface it here
    # is that CI retries make it INVISIBLE otherwise. Named, every run, so it
    # cannot decay into "e2e is a bit flaky, re-run it".
    if flaky:
        print(f"\nFLAKY — passed only on retry ({len(flaky)}):")
        for spec in flaky:
            print(f"::warning::flaky e2e test (passed on retry): {spec}")
        if args.fail_on_flaky:
            problems.append(f"{len(flaky)} test(s) passed only on retry")

    # Printed before the verdict so that a red job shows the WHERE next to the
    # WHAT, and printed on green runs too: the green shard's wall clock and
    # slowest tests are the baseline a red one has to be read against, and B4's
    # shard-count decision needs a real per-shard duration from a runner.
    if args.timeline:
        print_timeline(per_shard)

    if problems:
        print("\nFAIL — the e2e evidence is not sound:")
        for line in problems:
            print(f"  {line}")
        return 1

    print("OK — every discovered test was executed exactly once.")
    return 0


# ── self-test ────────────────────────────────────────────────────────────────
# A gate nobody has watched fail is not a gate (`just licence-selftest`,
# `check-build-context.py --self-test`, `stage-doc-hunks.py --self-test` all
# exist for this reason). This one guards the e2e evidence itself, and it just
# grew a reporting mode — the exact moment a "print" accidentally becomes an
# "assert" and starts failing builds for slow tests. So the self-test pins the
# reporting/verdict separation explicitly, not just the happy path.


#: How many checks `self_test` is supposed to append. A count floor exists
#: because the verdict is `all(ok for ok, _ in checks)` and `all([])` is True:
#: a `checks.append` lost to a refactor removes coverage silently and the
#: self-test still prints "the gate can fail". `<`, not `!=`, so ADDING checks
#: needs no edit here — only losing them is an error.
EXPECTED_CHECKS = 14


def _spec(
    spec_id: str,
    title: str,
    status: str = "expected",
    start: str | None = None,
    duration: float = 1000.0,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    if start is not None:
        results.append({"startTime": start, "duration": duration, "status": status})
    return {
        "id": spec_id,
        "title": title,
        "file": "synthetic.spec.ts",
        "tests": [{"status": status, "results": results}],
    }


def _report(path: Path, specs: list[dict[str, Any]]) -> Path:
    payload = {"suites": [{"title": "synthetic.spec.ts", "specs": specs}]}
    path.write_text(json.dumps(payload))
    return path


def self_test() -> int:
    import io
    import tempfile
    from contextlib import redirect_stdout

    checks: list[tuple[bool, str]] = []

    def run(argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = "2026-08-11T12:00:0"
        discovered = _report(
            root / "discovered.json",
            [_spec("a", "one"), _spec("b", "two"), _spec("c", "three")],
        )
        # Two shards covering the set exactly; the middle test of shard 1 fails.
        shard1 = _report(
            root / "playwright-shard-1.json",
            [
                _spec("a", "one", start=f"{base}0.000Z", duration=1000),
                _spec("b", "two", "unexpected", start=f"{base}5.000Z", duration=9000),
            ],
        )
        shard2 = _report(
            root / "playwright-shard-2.json",
            [_spec("c", "three", start=f"{base}1.000Z", duration=2000)],
        )
        good = [str(discovered), str(shard1), str(shard2)]

        code, out = run(["--discovered", good[0], good[1], good[2]])
        checks.append((code == 0, "complete coverage -> exit 0"))
        checks.append(("timeline" not in out, "no --timeline -> no timeline printed"))

        # THE contract: the timeline reports, it never votes. Same inputs, same
        # verdict — including a shard full of failures, which is when the
        # temptation to "just fail on the slow one" would land.
        code_t, out_t = run(["--discovered", *good, "--timeline"])
        checks.append((code_t == 0, "--timeline on a covered set -> still exit 0"))
        checks.append(
            ("failed at test 2/2" in out_t, "timeline names the failing ordinal")
        )
        checks.append(
            ("slowest 10 tests" in out_t, "timeline reports the slowest tests")
        )
        checks.append(("2 tests, 0.2 min wall" in out_t, "timeline computes the wall"))

        # A missing test must still fail — with the timeline on, so the new
        # printing cannot swallow the verdict.
        code_m, out_m = run(["--discovered", good[0], good[1], "--timeline"])
        checks.append((code_m == 1, "a test no shard ran -> exit 1"))
        checks.append(("run by NO shard" in out_m, "…and says which"))

        # Same report twice: the coverage set is complete, so ONLY the duplicate
        # detection can catch it.
        duplicate = _report(
            root / "playwright-shard-3.json",
            [_spec("c", "three", start=f"{base}1.000Z")],
        )
        code_d, out_d = run(["--discovered", *good, str(duplicate)])
        checks.append((code_d == 1, "a test run by two shards -> exit 1"))
        checks.append(("ran twice" in out_d, "…and says so"))

        # Retry posture: a flaky test is always reported, and fails only when
        # --fail-on-flaky is set (which the workflow always sets).
        flaky_shard = _report(
            root / "playwright-shard-4.json",
            [_spec("c", "three", "flaky", start=f"{base}1.000Z")],
        )
        flaky_args = ["--discovered", good[0], good[1], str(flaky_shard)]
        code_f, out_f = run(flaky_args)
        checks.append((code_f == 0, "flaky without --fail-on-flaky -> exit 0"))
        checks.append(("::warning::flaky" in out_f, "…but always warned about"))
        code_ff, _ = run([*flaky_args, "--fail-on-flaky"])
        checks.append((code_ff == 1, "flaky with --fail-on-flaky -> exit 1"))

        # An empty listing is the vacuous pass this script exists to prevent.
        empty = _report(root / "empty.json", [])
        code_e, _ = run(["--discovered", str(empty), good[1]])
        checks.append((code_e == 1, "an empty discovery -> exit 1"))

    for ok, label in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if len(checks) < EXPECTED_CHECKS:
        print(
            f"\ne2e-shard-audit: SELF-TEST RAN {len(checks)} of {EXPECTED_CHECKS} "
            "checks — the self-test lost coverage; it proves nothing."
        )
        return 1
    if all(ok for ok, _ in checks):
        print("\ne2e-shard-audit: self-test passed — the gate can fail.")
        return 0
    print("\ne2e-shard-audit: SELF-TEST FAILED — this gate proves nothing.")
    return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
