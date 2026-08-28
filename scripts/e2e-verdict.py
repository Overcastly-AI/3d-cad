#!/usr/bin/env python3
"""Print the e2e verdict — the LAST thing a red shard says, and the only thing
anybody needs to read.

WHY THIS EXISTS. Subagents cannot read CI; the orchestrator can, and only
through the GitHub MCP `get_job_logs` tool, which returns the LAST N lines of a
job log. Artifact download is policy-denied from this container (curl of the
Azure blob URL the tool hands back -> `CONNECT tunnel failed, 403`), so the JSON
report we carefully upload is unreachable — **the job log is the only channel**.

Measured 2026-08-28 on run 33139349952 (`69b3ef7`), shard 3/4 red: `tail_lines`
of 60, then 190, then 255 NEVER REACHED THE FAILURE LIST, because ~300 lines of
service-log dump and upload-artifact chatter sit between it and the end of the
file. Each tail cost thousands of tokens of context to learn nothing, and the
shard was re-run locally instead — a ~20 minute detour for information CI had
already computed. So: one compact block, printed last, small enough that
`tail_lines: 40` always contains the whole verdict.

THE GUARD IS THE POINT. It must be IMPOSSIBLE for the block to be empty while
playwright exited non-zero. A summariser that silently emits nothing on an
unfamiliar report shape leaves the log exactly as it is today, and it does so at
precisely the moment somebody needs it. So an unparseable/absent report, a
report whose statuses this script does not recognise, or a non-zero status with
no failures in it are all LOUD (`::error::`, exit 3) and name the report path.
Same discipline the other five gates in `just lint` grew: `all([])` is True, and
a check that cannot fail is not a check.

Exit codes:
  0  a verdict was printed and it is CONSISTENT with --status
  3  INCONSISTENT or unexplainable: non-zero status with nothing to show for it,
     or a zero status over a report that lists failures (a lying pass)
  2  usage error

Usage:
  e2e-verdict.py --status N [--report PATH] [--fallback-log PATH]
                 [--label TEXT] [--out PATH] [--max-failures N]
  e2e-verdict.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

# Playwright's spec-level `tests[].status`. Anything outside this set is a shape
# this script has never seen; it is reported as unclassified and treated as a
# failure rather than skipped over, because the alternative is a silent green.
KNOWN_TEST_STATUSES = frozenset({"expected", "unexpected", "flaky", "skipped"})
# Result-level `results[].status`.
FAILED_RESULT_STATUSES = frozenset({"failed", "timedOut", "interrupted"})

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# U+203A, the separator Playwright's own reporters put between a location and a
# test title. Spelled as an escape because ruff's RUF001 rightly refuses the
# raw glyph in source (it is confusable with ">"), and written ONCE so the
# regex, the renderer and the tests cannot drift apart. It is deliberately not
# ASCII ">": these lines are meant to be greppable against Playwright's output.
SEP = "\u203a"
# The list reporter's failure lines, in both the detail section and the trailing
# summary: `  1) e2e/foo.spec.ts:7:3 <SEP> group <SEP> title ────────`.
LIST_FAILURE = re.compile(rf"^\s{{0,6}}\d+\)\s+(\S+:\d+:\d+\s+{SEP}\s+.*?)\s*$")
TITLE_CAP = 120
RULE = "=" * 63


class Finding:
    """One line of the failure list."""

    def __init__(self, kind: str, where: str, title: str) -> None:
        self.kind = kind
        self.where = where
        self.title = title

    def render(self) -> str:
        title = self.title
        if len(title) > TITLE_CAP:
            title = title[: TITLE_CAP - 1] + "…"
        if self.where:
            return f"  {self.kind:<5} {self.where} {SEP} {title}"
        return f"  {self.kind:<5} {title}"


class Parsed:
    """What one report yielded — findings plus the counts to print above them."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.failed = 0
        self.passed = 0
        self.skipped = 0
        self.flaky = 0
        self.unclassified = 0
        self.total = 0
        self.source = ""
        self.problem = ""
        # The report's OWN `stats` block — a second, independently-derived count
        # of the same run. Walking the suite tree and reading the summary are
        # two different derivations, so a disagreement means one of them is
        # wrong and neither should be quietly believed (CLAUDE.md: get a second
        # opinion from a different derivation, not a louder assertion of the
        # first). None when the report carries no usable stats.
        self.stats: dict[str, int] | None = None

    @property
    def counts_known(self) -> bool:
        return self.total > 0 or self.source.startswith("report")

    def counts_line(self) -> str:
        return (
            f"{self.failed} failed, {self.passed} passed, "
            f"{self.skipped} skipped, {self.flaky} flaky of {self.total}"
        )


# JSON from an external tool is `Any`; these three keep the traversal honest
# (and pyright-strict clean) by narrowing at every hop instead of assuming a
# shape. A report that does not look the way we expect must degrade into empty
# containers, never into an exception — the caller has to print something.
def _obj(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _arr(value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _titles(node: dict[str, Any], ancestors: list[str]) -> list[str]:
    """Suite titles above a spec, minus the root (which is just the file name)."""
    title = str(node.get("title", ""))
    if not ancestors and title == str(node.get("file", "")):
        return []
    return [*ancestors, title] if title else list(ancestors)


def _walk(suite: dict[str, Any], ancestors: list[str], parsed: Parsed) -> None:
    here = _titles(suite, ancestors)
    for raw_spec in _arr(suite.get("specs")):
        spec = _obj(raw_spec)
        parsed.total += 1
        tests = [_obj(test) for test in _arr(spec.get("tests"))]
        statuses = [_text(test.get("status")) or "unknown" for test in tests]
        results: list[str] = [
            _text(_obj(result).get("status")) or "unknown"
            for test in tests
            for result in _arr(test.get("results"))
        ]
        file = _text(spec.get("file")) or _text(suite.get("file")) or "?"
        line = spec.get("line")
        where = f"{file}:{line}" if isinstance(line, int) and line else file
        path = [*here, _text(spec.get("title")) or "?"]
        title = f" {SEP} ".join(p for p in path if p)

        unknown = [s for s in statuses if s not in KNOWN_TEST_STATUSES]
        failed = "unexpected" in statuses or any(
            r in FAILED_RESULT_STATUSES for r in results
        )
        if unknown:
            parsed.unclassified += 1
            parsed.failed += 1
            parsed.findings.append(
                Finding("?????", where, f"{title}  [unknown status {unknown}]")
            )
        elif failed:
            parsed.failed += 1
            parsed.findings.append(Finding("FAIL", where, title))
        elif "flaky" in statuses:
            parsed.flaky += 1
            # No retries are configured (GATE-1a), so a flaky result can only
            # mean retries came back — the reconcile job fails on it, and it
            # belongs in the list rather than in a count nobody reads.
            parsed.findings.append(Finding("FLAKY", where, title))
        elif statuses and all(s == "skipped" for s in statuses):
            parsed.skipped += 1
        else:
            parsed.passed += 1
    for nested in _arr(suite.get("suites")):
        _walk(_obj(nested), here, parsed)


def parse_report(path: Path) -> Parsed:
    """Parse a Playwright JSON report. Never raises: an unusable report is a
    Parsed carrying `problem`, because the caller must still print something."""
    parsed = Parsed()
    parsed.source = f"report {path}"
    try:
        raw = path.read_text()
    except OSError as exc:
        parsed.problem = f"cannot read {path}: {exc}"
        return parsed
    if not raw.strip():
        parsed.problem = f"{path} is empty ({path.stat().st_size} bytes)"
        return parsed
    try:
        loaded: object = json.loads(raw)
    except ValueError as exc:
        parsed.problem = f"{path} is not valid JSON: {exc}"
        return parsed
    kind = type(loaded).__name__
    payload = _obj(loaded)
    if kind != "dict":
        parsed.problem = f"{path} is JSON but not an object ({kind})"
        return parsed
    if not isinstance(payload.get("suites"), list):
        parsed.problem = f"{path} has no `suites` array — not a Playwright report"
        return parsed
    for suite in _arr(payload.get("suites")):
        _walk(_obj(suite), [], parsed)
    stats = _obj(payload.get("stats"))
    counted: dict[str, int] = {}
    for key in ("expected", "unexpected", "flaky", "skipped"):
        value: object = stats.get(key)
        if isinstance(value, int):
            counted[key] = value
    if counted:
        parsed.stats = counted
    # A run that dies in setup (webServer timeout, a config error) reports ZERO
    # specs and a non-zero status. Its reason lives in the top-level `errors`,
    # so surface that as the finding rather than letting the guard cry "empty".
    for error in _arr(payload.get("errors")):
        fields = _obj(error)
        message = _text(fields.get("message")) or _text(fields.get("value"))
        if not message and not fields:
            message = str(error)
        first = ANSI.sub("", message).strip().splitlines()
        if first:
            parsed.findings.append(Finding("ERROR", "", first[0]))
    return parsed


def parse_list_log(path: Path) -> list[Finding]:
    """Failure lines recovered from the list reporter's own output.

    The second, independently-derived source. It exists for the case the JSON
    report is absent or malformed — which is exactly when the guard would
    otherwise have nothing to say, and exactly when somebody needs it to.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    seen: set[str] = set()
    found: list[Finding] = []
    for line in text.splitlines():
        match = LIST_FAILURE.match(ANSI.sub("", line).rstrip())
        if not match:
            continue
        entry = match.group(1).rstrip("─ ").strip()
        if entry in seen:
            continue
        seen.add(entry)
        where, _, title = entry.partition(f" {SEP} ")
        found.append(Finding("FAIL", where, title))
    return found


def build_block(
    status: int,
    report: Path | None,
    fallback_log: Path | None,
    label: str,
    max_failures: int,
) -> tuple[list[str], int]:
    """The verdict block, and the exit code. Guaranteed non-empty."""
    out: list[str] = []
    tag = f"[{label}] " if label else ""
    parsed = parse_report(report) if report is not None else Parsed()
    if report is None:
        parsed.problem = "no JSON report was requested (E2E_JSON_REPORT unset)"

    findings = list(parsed.findings)
    recovered: list[Finding] = []
    if parsed.problem and fallback_log is not None:
        recovered = parse_list_log(fallback_log)
        findings.extend(recovered)

    out.append(f"== e2e verdict {RULE[:48]}")
    if parsed.problem:
        out.append(f"e2e verdict: {tag}NO USABLE JSON REPORT — {parsed.problem}")
        if recovered:
            out.append(
                f"e2e verdict: {len(recovered)} failure(s) recovered from the "
                f"list-reporter output ({fallback_log}):"
            )
        elif fallback_log is not None:
            out.append(f"e2e verdict: nothing recoverable from {fallback_log} either.")
    else:
        verdict = "GREEN" if status == 0 and parsed.failed == 0 else "RED"
        out.append(
            f"e2e verdict: {tag}{parsed.counts_line()} — {verdict} "
            f"(playwright exit {status})"
        )

    # Cross-check the suite walk against the report's own `stats` summary. They
    # are two derivations of one run; if they disagree, say so rather than
    # printing the one that happens to be mine.
    stats_failed = 0
    if parsed.stats is not None and not parsed.problem:
        stats_failed = parsed.stats.get("unexpected", 0)
        mine = {
            "unexpected": parsed.failed,
            "expected": parsed.passed,
            "skipped": parsed.skipped,
            "flaky": parsed.flaky,
        }
        disagree = [
            f"{key}: walked {mine[key]}, stats say {theirs}"
            for key, theirs in parsed.stats.items()
            if mine.get(key, theirs) != theirs
        ]
        if disagree:
            out.append(
                "e2e verdict: !! this summary disagrees with the report's own "
                f"stats ({'; '.join(disagree)}) — trust neither until checked."
            )

    shown = findings[:max_failures]
    out.extend(finding.render() for finding in shown)
    if len(findings) > len(shown):
        out.append(
            f"  … and {len(findings) - len(shown)} more — full list in "
            f"{report if report is not None else 'the JSON report'}"
        )

    exit_code = 0
    # ── The guard. Three ways the block can lie, and all are loud. ────────────
    if not findings and (status != 0 or stats_failed > 0):
        exit_code = 3
        if status != 0:
            out.append(
                f"e2e verdict: !! playwright exited {status} and this summary "
                "found NO failures."
            )
        else:
            out.append(
                f"e2e verdict: !! the report's stats say {stats_failed} "
                "unexpected result(s) and this summary found NO failures."
            )
        out.append(
            "e2e verdict: !! that is a defect in the summary, not a pass. "
            "Report: "
            f"{report if report is not None else '(none)'}"
            + (
                f"; parsed {parsed.total} spec(s)."
                if not parsed.problem
                else f"; {parsed.problem}."
            )
        )
        out.append(
            "e2e verdict: !! read the log above, and the "
            "playwright-json-shard-N / e2e-diagnostics-shard-N artifacts."
        )
        out.append(
            "::error::e2e verdict: non-zero playwright status with an empty "
            "failure list — see the lines above"
        )
    elif status == 0 and parsed.failed > 0:
        exit_code = 3
        out.append(
            f"e2e verdict: !! playwright exited 0 but the report lists "
            f"{parsed.failed} failure(s) — a pass that cannot be trusted."
        )
        out.append(
            "::error::e2e verdict: playwright exited 0 over a report containing "
            "failures"
        )
    elif status == 0 and not parsed.problem and parsed.total == 0:
        # Not fatal (a caller may legitimately filter to nothing), but a green
        # over zero tests is the shape of a gate that quietly stopped covering.
        out.append(
            "e2e verdict: !! zero tests in the report — a green over nothing "
            "is not evidence. Check the shard/grep arguments."
        )
    return out, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--status", type=int, help="playwright's exit status")
    parser.add_argument("--report", type=Path, help="Playwright JSON report")
    parser.add_argument(
        "--fallback-log",
        type=Path,
        help="captured list-reporter output, used when the JSON report is unusable",
    )
    parser.add_argument("--label", default="", help="e.g. 'shard 3/4'")
    parser.add_argument("--out", type=Path, help="also write the block here")
    parser.add_argument("--max-failures", type=int, default=25)
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.status is None:
        parser.error("--status is required (or --self-test)")

    block, code = build_block(
        status=args.status,
        report=args.report,
        fallback_log=args.fallback_log,
        label=args.label,
        max_failures=args.max_failures,
    )
    text = "\n".join(block)
    print(text, flush=True)
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n")
        except OSError as exc:  # never let bookkeeping mask the verdict
            print(f"e2e verdict: (could not write {args.out}: {exc})", flush=True)
    return code


# ── self-test ────────────────────────────────────────────────────────────────
# The gate that guards the evidence needs its own guard: stdlib only, ~30 ms,
# and it proves the guard FIRES on the case it exists for and does NOT fire on
# an ordinary red — the negative control being an input mutation (strip the
# failures out of a red report), so the check is demonstrably coupled to the
# thing it measures rather than constant.


def _spec(title: str, line: int, status: str, result: str | None = None) -> Any:
    return {
        "title": title,
        "file": "e2e/synthetic.spec.ts",
        "line": line,
        "column": 3,
        "id": f"id-{line}",
        "tests": [
            {
                "status": status,
                "results": [{"status": result or status, "duration": 10}],
            }
        ],
    }


def _write(
    path: Path,
    specs: list[Any],
    errors: list[Any] | None = None,
    stats: dict[str, int] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "suites": [
            {
                "title": "e2e/synthetic.spec.ts",
                "file": "e2e/synthetic.spec.ts",
                "specs": [],
                "suites": [{"title": "a group", "specs": specs, "suites": []}],
            }
        ],
        "errors": errors or [],
    }
    if stats is not None:
        payload["stats"] = stats
    path.write_text(json.dumps(payload))
    return path


def self_test() -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name}{(' — ' + detail) if detail else ''}")
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        red = _write(
            root / "red.json",
            [
                _spec("passes", 10, "expected", "passed"),
                _spec("fails here", 20, "unexpected", "failed"),
                _spec("times out", 30, "unexpected", "timedOut"),
                _spec("skipped", 40, "skipped"),
            ],
        )
        block, code = build_block(1, red, None, "shard 3/4", 25)
        text = "\n".join(block)
        check("red: exit 0 (consistent)", code == 0, f"got {code}")
        check("red: counts", "2 failed, 1 passed, 1 skipped" in text, text)
        check(
            f"red: names both failures with file:line {SEP} title",
            f"e2e/synthetic.spec.ts:20 {SEP} a group {SEP} fails here" in text
            and f"e2e/synthetic.spec.ts:30 {SEP} a group {SEP} times out" in text,
            text,
        )
        check("red: fits in a 40-line tail", len(block) <= 40, str(len(block)))

        green = _write(root / "green.json", [_spec("passes", 10, "expected", "passed")])
        block, code = build_block(0, green, None, "shard 1/4", 25)
        text = "\n".join(block)
        check("green: exit 0", code == 0, f"got {code}")
        check("green: says GREEN", "— GREEN (playwright exit 0)" in text, text)
        check("green: no failure lines", " FAIL " not in text, text)
        check("green: is quiet (<= 3 lines)", len(block) <= 3, str(len(block)))

        # THE NEGATIVE CONTROL: the same red report with its failures removed is
        # the empty-summary case, and the guard must fire on it. Mutating the
        # INPUT proves the guard is coupled to what it measures — asserting the
        # exit code on the red fixture alone would pass for a guard hard-wired
        # to 0.
        stripped = _write(
            root / "stripped.json", [_spec("passes", 10, "expected", "passed")]
        )
        block, code = build_block(1, stripped, None, "shard 3/4", 25)
        text = "\n".join(block)
        check("empty-summary guard: exit 3", code == 3, f"got {code}")
        check("empty-summary guard: ::error:: annotation", "::error::" in text, text)
        check("empty-summary guard: names the report", str(stripped) in text, text)

        missing = root / "not-written.json"
        block, code = build_block(1, missing, None, "shard 2/4", 25)
        text = "\n".join(block)
        check("absent report: exit 3", code == 3, f"got {code}")
        check("absent report: says why", "NO USABLE JSON REPORT" in text, text)
        check("absent report: names the path", str(missing) in text, text)

        malformed = root / "malformed.json"
        malformed.write_text("{ this is not json")
        listlog = root / "list.log"
        # Real list-reporter shapes: the per-test tick line (never a finding),
        # the trailing rule after a failure title, and ANSI colour.
        rule = "\u2500" * 6
        listlog.write_text(
            f"  \u2718  2 e2e/real.spec.ts:7:3 {SEP} group {SEP} blew up (8ms)\n"
            f"  1) e2e/real.spec.ts:7:3 {SEP} group {SEP} blew up {rule}\n"
            f"\x1b[31m  2) e2e/other.spec.ts:9:1 {SEP} group {SEP} blew up too"
            "\x1b[39m\n"
            "  1 failed\n"
        )
        block, code = build_block(1, malformed, listlog, "shard 4/4", 25)
        text = "\n".join(block)
        check("malformed + fallback: exit 0 (it said something)", code == 0, f"{code}")
        check(
            "malformed + fallback: recovered both failures",
            f"e2e/real.spec.ts:7:3 {SEP} group {SEP} blew up" in text
            and f"e2e/other.spec.ts:9:1 {SEP} group {SEP} blew up too" in text,
            text,
        )
        check("malformed + fallback: strips ANSI", "\x1b[" not in text, repr(text))
        block, code = build_block(1, malformed, None, "", 25)
        check("malformed, no fallback: exit 3", code == 3, f"got {code}")

        empty = root / "empty.json"
        empty.write_text("")
        block, code = build_block(1, empty, None, "", 25)
        check(
            "zero-byte report: exit 3 and says empty",
            code == 3 and "is empty" in "\n".join(block),
            "\n".join(block),
        )

        setup_died = _write(
            root / "setup.json",
            [],
            errors=[
                {"message": "Error: Timed out waiting 60000ms from config.webServer"}
            ],
        )
        block, code = build_block(1, setup_died, None, "shard 1/4", 25)
        text = "\n".join(block)
        check(
            "setup death: surfaces the run error instead of crying empty",
            code == 0 and "config.webServer" in text,
            text,
        )

        lying = _write(
            root / "lying.json", [_spec("fails", 20, "unexpected", "failed")]
        )
        block, code = build_block(0, lying, None, "", 25)
        check(
            "status 0 over a failing report: exit 3",
            code == 3 and "cannot be trusted" in "\n".join(block),
            "\n".join(block),
        )

        unknown = _write(root / "unknown.json", [_spec("weird", 50, "martian")])
        block, code = build_block(1, unknown, None, "", 25)
        text = "\n".join(block)
        check(
            "unfamiliar status is listed, not skipped",
            code == 0 and "unknown status" in text and "?????" in text,
            text,
        )

        # The report's own stats are the second derivation: a walk that finds
        # nothing while the summary counts failures is the exact shape this
        # whole script exists to make impossible, and it must fire even when
        # playwright's status is 0.
        blind = _write(
            root / "blind.json",
            [_spec("passes", 10, "expected", "passed")],
            stats={"expected": 1, "unexpected": 2, "flaky": 0, "skipped": 0},
        )
        block, code = build_block(0, blind, None, "", 25)
        text = "\n".join(block)
        check(
            "stats say failures, walk found none: exit 3",
            code == 3 and "stats say 2 unexpected result(s)" in text,
            text,
        )
        skewed = _write(
            root / "skewed.json",
            [_spec("fails", 20, "unexpected", "failed")],
            stats={"expected": 7, "unexpected": 1, "flaky": 0, "skipped": 0},
        )
        block, code = build_block(1, skewed, None, "", 25)
        check(
            "walk/stats disagreement is reported",
            "disagrees with the report's own stats" in "\n".join(block)
            and "expected: walked 0, stats say 7" in "\n".join(block),
            "\n".join(block),
        )
        agreeing = _write(
            root / "agree.json",
            [
                _spec("passes", 10, "expected", "passed"),
                _spec("fails", 20, "unexpected", "failed"),
            ],
            stats={"expected": 1, "unexpected": 1, "flaky": 0, "skipped": 0},
        )
        block, code = build_block(1, agreeing, None, "", 25)
        check(
            "agreeing stats produce no noise",
            code == 0 and "disagrees" not in "\n".join(block),
            "\n".join(block),
        )

        many = _write(
            root / "many.json",
            [_spec(f"fails {n}", n, "unexpected", "failed") for n in range(1, 41)],
        )
        block, code = build_block(1, many, None, "shard 3/4", 25)
        text = "\n".join(block)
        check(
            "40 failures truncate to a readable tail",
            code == 0 and "… and 15 more" in text and len(block) <= 30,
            f"{len(block)} lines",
        )

    if failures:
        print(f"\ne2e-verdict self-test: {len(failures)} FAILED: {failures}")
        return 1
    print("\ne2e-verdict self-test: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
