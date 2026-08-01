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

Usage:
    e2e-shard-audit.py --discovered LIST.json REPORT.json [REPORT.json ...]

Both inputs are Playwright JSON reports (`--reporter=json`); `--discovered`
is the one produced by `--list`, which reports every test as skipped and is
therefore useless for pass/fail but exact for identity.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class Spec:
    """One Playwright spec, keyed by its stable generated id."""

    def __init__(
        self, spec_id: str, file: str, title: str, statuses: list[str]
    ) -> None:
        self.id = spec_id
        self.file = file
        self.title = title
        self.statuses = statuses

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.file} :: {self.title}"


def _walk(suite: dict[str, Any], out: dict[str, Spec]) -> None:
    for spec in suite.get("specs", []):
        statuses = [test.get("status", "unknown") for test in spec.get("tests", [])]
        out[spec["id"]] = Spec(
            spec_id=spec["id"],
            file=spec.get("file", suite.get("file", "?")),
            title=spec.get("title", "?"),
            statuses=statuses,
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


def main() -> int:
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
    args = parser.parse_args()

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
    for report in args.reports:
        if not report.exists():
            problems.append(
                f"shard report {report} is missing — "
                "that shard produced no evidence it ran"
            )
            continue
        specs = read_report(report)
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

    if problems:
        print("\nFAIL — the e2e evidence is not sound:")
        for line in problems:
            print(f"  {line}")
        return 1

    print("OK — every discovered test was executed exactly once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
