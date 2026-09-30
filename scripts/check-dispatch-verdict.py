#!/usr/bin/env python3
"""A green ``full lane complete`` check only ever lands on the commit it tested.

WHY THIS EXISTS
---------------
The full lane (``.github/workflows/e2e.yml``) can be dispatched on a specific
commit: ``gh workflow run e2e.yml --ref <branch> -f sha=<S>``. GitHub posts
every check of that run on the run's ``head_sha``, which is ``github.sha``,
i.e. the TIP of the dispatched ref, call it T. When T is not S (the normal
case while agents push, and the nightly dispatcher's pick-then-dispatch race),
a verdict job with the plain name ``full lane complete`` puts a green check on
T, a commit that was never tested. Merging T on the strength of it is the
defect. Found in review of b58ad66 (CI-TWO-LANE, 2026-09-30).

The fix is a conditional name: plain ``full lane complete`` only when the
commit proven equals ``github.sha``, ``full lane complete (proves <S>)``
otherwise. That expression cannot be exercised locally and only matters when
a dispatch and a push interleave, which is exactly the class of workflow
defect this repo gates statically (check-workflow-concurrency.py,
check-workflow-contexts.py).

WHAT IS ASSERTED
----------------
For every workflow with a ``workflow_dispatch`` input named ``sha``:
  1. exactly ONE job's name mentions ``full lane complete``, so no second,
     plain-named job can post that check;
  2. that name is the canonical conditional, keyed on
     ``needs.<T>.outputs.sha == github.sha`` with the plain name on the TRUE
     arm, and the job ``needs`` T;
  3. every checkout outside T takes ``ref: ${{ needs.<T>.outputs.sha }}`` and
     every reusable-workflow call passes ``sha: ${{ needs.<T>.outputs.sha }}``.
     The name compares T's output, so the code tested must be T's output too:
     a checkout left on its default would test github.sha under a verdict
     that names S.
For every workflow with a ``workflow_call`` input named ``sha`` (deploy-path):
  4. every checkout takes ``ref: ${{ inputs.sha }}``.

A run that checks NO dispatch-``sha`` workflow refuses: the full lane is the
reason this gate exists, and a rename that hid it would otherwise pass.

    python3 scripts/check-dispatch-verdict.py
    python3 scripts/check-dispatch-verdict.py --self-test   # prove it fails

Needs PyYAML, like check-workflow-contexts.py beside it in ci.yml's `compose`
job (present in the runner's system python and in the uv environment).
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import cast

import yaml

REPO = Path(__file__).resolve().parents[1]
VERDICT = "full lane complete"

#: The only accepted verdict name, whitespace squashed. The target job id is
#: the one degree of freedom, and it must be the same job on both sides.
CANONICAL_NAME = re.compile(
    r"^\$\{\{ needs\.(?P<t>[A-Za-z0-9_-]+)\.outputs\.sha == github\.sha "
    r"&& 'full lane complete' "
    r"\|\| format\('full lane complete \(proves \{0\}\)', "
    r"needs\.(?P<t2>[A-Za-z0-9_-]+)\.outputs\.sha\) \}\}$"
)

Mapping = dict[object, object]


def _squash(value: object) -> str:
    return " ".join(str(value).split())


def _map(value: object) -> Mapping:
    return cast("Mapping", value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _trigger(doc: Mapping, event: str) -> Mapping | None:
    """``on.<event>`` as a mapping ({} when declared bare), or None."""
    on = doc.get("on", doc.get(True))  # YAML 1.1 reads the bare key as True
    if isinstance(on, str):
        return {} if on == event else None
    if isinstance(on, list):
        return {} if event in cast("list[object]", on) else None
    triggers = _map(on)
    if event not in triggers:
        return None
    return _map(triggers[event])


def _has_sha_input(doc: Mapping, event: str) -> bool:
    trig = _trigger(doc, event)
    return trig is not None and "sha" in _map(trig.get("inputs"))


def _needs(job: Mapping) -> list[str]:
    raw = job.get("needs")
    if isinstance(raw, str):
        return [raw]
    return [str(n) for n in _list(raw)]


def _checkouts(job: Mapping) -> list[Mapping]:
    return [
        _map(step)
        for step in _list(job.get("steps"))
        if str(_map(step).get("uses", "")).startswith("actions/checkout@")
    ]


def check_workflow(name: str, doc: Mapping) -> tuple[bool, list[str]]:
    """(was this workflow in scope for rules 1-3, problems)."""
    problems: list[str] = []
    jobs = {str(k): _map(v) for k, v in _map(doc.get("jobs")).items()}

    if _has_sha_input(doc, "workflow_call"):
        want = "${{ inputs.sha }}"
        for job_id, job in jobs.items():
            for step in _checkouts(job):
                ref = _squash(_map(step.get("with")).get("ref", "<none>"))
                if ref != want:
                    problems.append(
                        f"{name}: jobs.{job_id} checks out `{ref}`, not "
                        f"`{want}`: a called workflow must test the commit its "
                        "caller names"
                    )

    if not _has_sha_input(doc, "workflow_dispatch"):
        return False, problems

    verdicts = {
        job_id: _squash(job.get("name", ""))
        for job_id, job in jobs.items()
        if VERDICT in _squash(job.get("name", ""))
    }
    if len(verdicts) != 1:
        problems.append(
            f"{name}: takes a dispatch `sha` input, so exactly ONE job may be "
            f"named `{VERDICT}`, found {len(verdicts)} "
            f"({', '.join(sorted(verdicts)) or 'none'})"
        )
        return True, problems

    job_id, job_name = next(iter(verdicts.items()))
    match = CANONICAL_NAME.match(job_name)
    if match is None or match.group("t") != match.group("t2"):
        problems.append(
            f"{name}: jobs.{job_id}.name is `{job_name}`. GitHub posts this "
            "run's checks on github.sha (the dispatched ref's TIP), so a plain "
            f"`{VERDICT}` would land green on a commit the run did not test. "
            "Use: ${{ needs.<target>.outputs.sha == github.sha && "
            "'full lane complete' || format('full lane complete (proves {0})', "
            "needs.<target>.outputs.sha) }}"
        )
        return True, problems
    target = match.group("t")
    if target not in jobs:
        problems.append(
            f"{name}: the verdict names job `{target}`, which does not exist"
        )
        return True, problems
    if target not in _needs(jobs[job_id]):
        problems.append(
            f"{name}: jobs.{job_id} reads needs.{target} but does not list "
            f"`{target}` in its needs"
        )

    want = f"${{{{ needs.{target}.outputs.sha }}}}"
    for other_id, job in jobs.items():
        if other_id == target:
            continue
        for step in _checkouts(job):
            ref = _squash(_map(step.get("with")).get("ref", "<none>"))
            if ref != want:
                problems.append(
                    f"{name}: jobs.{other_id} checks out `{ref}`, not `{want}`: "
                    "it would test a different commit from the one the verdict "
                    "names"
                )
        if "uses" in job:
            sha = _squash(_map(job.get("with")).get("sha", "<none>"))
            if sha != want:
                problems.append(
                    f"{name}: jobs.{other_id} calls {job['uses']} with sha "
                    f"`{sha}`, not `{want}`"
                )
    return True, problems


def run(workflow_dir: Path, quiet: bool = False) -> int:
    def say(line: str) -> None:
        if not quiet:
            print(line)

    paths = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    checked = 0
    problems: list[str] = []
    for path in paths:
        doc = _map(yaml.safe_load(path.read_text()))
        in_scope, found = check_workflow(path.name, doc)
        checked += in_scope
        problems += found
        if in_scope:
            mark = "FAIL" if found else "ok  "
            say(f"  {mark} {path.name}: verdict name is per commit")
    if checked == 0:
        say(
            "check-dispatch-verdict: REFUSED, no workflow takes a dispatch `sha` "
            "input. The full lane is why this gate exists; if it moved, move "
            "the gate with it rather than letting it pass over nothing."
        )
        return 1
    for line in problems:
        say(f"  FAIL {line}")
    if problems:
        say(f"\ncheck-dispatch-verdict: {len(problems)} problem(s)")
        return 1
    say(f"\ncheck-dispatch-verdict: {checked} dispatchable workflow(s) hold the rule")
    return 0


# ── self-test ────────────────────────────────────────────────────────────────

_GOOD = """
name: full
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      sha:
        type: string
jobs:
  target:
    runs-on: ubuntu-latest
    outputs:
      sha: ${{ steps.r.outputs.sha }}
    steps:
      - id: r
        run: echo sha=x >> "$GITHUB_OUTPUT"
      - uses: actions/checkout@v4
        with:
          ref: ${{ steps.r.outputs.sha }}
  shard:
    needs: target
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ needs.target.outputs.sha }}
  docker:
    needs: target
    uses: ./.github/workflows/called.yml
    with:
      sha: ${{ needs.target.outputs.sha }}
  complete:
    name: >-
      ${{ needs.target.outputs.sha == github.sha
          && 'full lane complete'
          || format('full lane complete (proves {0})', needs.target.outputs.sha) }}
    needs: [target, shard, docker]
    runs-on: ubuntu-latest
    steps:
      - run: true
"""

_CALLED = """
name: called
on:
  workflow_call:
    inputs:
      sha:
        type: string
        required: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.sha }}
"""

_PLAIN = "    name: full lane complete\n"
_COND = (
    "    name: >-\n"
    "      ${{ needs.target.outputs.sha == github.sha\n"
    "          && 'full lane complete'\n"
    "          || format('full lane complete (proves {0})', "
    "needs.target.outputs.sha) }}\n"
)

#: `all([])` is True: a lost case must not read as a passing self-test.
EXPECTED_CHECKS = 10


def self_test() -> int:
    assert _COND in _GOOD
    cases: list[tuple[str, dict[str, str], int]] = [
        (
            "the canonical full lane + called workflow",
            {"full.yml": _GOOD, "called.yml": _CALLED},
            0,
        ),
        (
            "THE REVIEW FINDING: a plain verdict name",
            {"full.yml": _GOOD.replace(_COND, _PLAIN)},
            1,
        ),
        (
            "the condition inverted (plain name when the commits DIFFER)",
            {
                "full.yml": _GOOD.replace(
                    "outputs.sha == github.sha", "outputs.sha != github.sha"
                )
            },
            1,
        ),
        (
            "the verdict does not need the target it reads",
            {
                "full.yml": _GOOD.replace(
                    "needs: [target, shard, docker]", "needs: [shard, docker]"
                )
            },
            1,
        ),
        (
            "a second, plain-named job would post the same check",
            {
                "full.yml": _GOOD
                + "  also:\n    name: full lane complete\n    runs-on: ubuntu-latest\n"
                "    steps:\n      - run: true\n"
            },
            1,
        ),
        (
            "a dispatch `sha` input with no verdict job at all",
            {
                "full.yml": _GOOD.split("  complete:\n")[0],
            },
            1,
        ),
        (
            "a checkout left on its default (tests github.sha, not the target)",
            {
                "full.yml": _GOOD.replace(
                    "      - uses: actions/checkout@v4\n        with:\n"
                    "          ref: ${{ needs.target.outputs.sha }}\n",
                    "      - uses: actions/checkout@v4\n",
                )
            },
            1,
        ),
        (
            "a called workflow that checks out its default instead of inputs.sha",
            {
                "full.yml": _GOOD,
                "called.yml": _CALLED.replace("ref: ${{ inputs.sha }}", "ref: main"),
            },
            1,
        ),
        (
            "workflows without a dispatch `sha` are out of scope",
            {
                "full.yml": _GOOD,
                "ci.yml": "name: ci\non: [push]\njobs:\n  a:\n"
                "    name: full lane complete\n    runs-on: ubuntu-latest\n"
                "    steps:\n      - uses: actions/checkout@v4\n",
            },
            0,
        ),
        (
            "NO dispatchable workflow at all is REFUSED, not passed",
            {"ci.yml": _CALLED},
            1,
        ),
    ]
    results: list[bool] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, (label, files, expected) in enumerate(cases):
            directory = Path(tmp) / str(index)
            directory.mkdir()
            for filename, text in files.items():
                (directory / filename).write_text(text)
            actual = run(directory, quiet=True)
            ok = actual == expected
            results.append(ok)
            mark = "ok  " if ok else "FAIL"
            print(f"  {mark} {label} -> exit {actual} (expected {expected})")
    ran = len(results)
    if ran < EXPECTED_CHECKS:
        print(f"\ncheck-dispatch-verdict: SELF-TEST RAN {ran} of {EXPECTED_CHECKS}")
        return 1
    if all(results):
        print(f"\ncheck-dispatch-verdict: self-test passed ({ran} checks)")
        return 0
    print("\ncheck-dispatch-verdict: SELF-TEST FAILED — this gate proves nothing.")
    return 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run(REPO / ".github" / "workflows")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
