#!/usr/bin/env python3
"""Assert every ``${{ }}`` expression in an ``env:`` mapping uses a context that
is AVAILABLE at that level.

WHY THIS EXISTS. On 2026-09-15 a verdict block hoisted a path into a job-level
``env:``::

    jobs.compose-stack-e2e.env.COMPOSE_SMOKE_VERDICT: ${{ runner.temp }}/...

``runner`` is not an available context in a job-level ``env``. GitHub does not
fail the step, or the job: it rejects the workflow at RUN-CREATION. The run is
created with ``total_jobs: 0``, ``created_at == run_started_at == updated_at``,
and a ``name`` that is the FILE PATH rather than the workflow's name — so the
entire file becomes unrunnable and every job in it, including ones that were
about to prove an unrelated fix, is never evaluated at all.

That is strictly worse than the red job the block was added to explain, and it
was invisible to everything we run locally: the file is valid YAML, has no
duplicate keys, and its job/step structure is correct. ``docker compose config
-q`` has nothing to say about it. This closes exactly that gap.

THE TABLE IS NOT FROM MEMORY. It is transcribed from GitHub's own workflow
parser schema, which publishes the allowed contexts per key::

    https://raw.githubusercontent.com/actions/languageservices/
        main/workflow-parser/src/workflow-v1.0.json

whose ``job-env``/``step-env``/``workflow-env`` definitions each carry a
``context`` array. ``--show-table`` prints what this file believes, so a future
reader can diff it against that schema rather than trusting this docstring.
``--self-test`` reproduces the real defect and demands a failure.

SCOPE, STATED HONESTLY. This checks ``env:`` mappings only, in FOUR places:
workflow, job, step, and container (``jobs.<id>.container.env`` plus
``jobs.<id>.services.<id>.env``, which inherit the ``container``/``services``
context and are NARROWER than job-env — no ``secrets``). Expressions in
``if:``, ``with:`` and ``run:`` are COUNTED and reported as unchecked rather
than silently ignored, so the coverage number is visible instead of implied. A
gate that walks what is present cannot see what is absent; saying how much it
did not look at is the cheapest honest substitute.

Two things that number depends on, both of which were once wrong here:

* it is a count of EXPRESSIONS, and the graded side must be counted the same
  way. ``rep.checked`` counts env KEYS, and one key may hold several
  expressions, so subtracting keys from expressions over-reported — measured
  on a fixture with NO expression outside ``env:``, the gate claimed one. A
  wrong scope number is worse than no scope number, because this paragraph is
  what makes it credible.
* a context reference may be written ``name.prop`` OR ``name['prop']``, and
  both are graded; a name inside a single-quoted STRING literal is data and is
  not. Neither of those is decoration: missing the bracket form would let the
  exact defect above through in different syntax, and matching inside a literal
  would block a legal workflow.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import cast

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO / ".github" / "workflows"

# Transcribed from workflow-v1.0.json (see the module docstring). The three
# sets are genuinely different, which is the whole reason this gate exists.
ALLOWED: dict[str, frozenset[str]] = {
    "workflow-env": frozenset({"github", "inputs", "vars", "secrets"}),
    "job-env": frozenset(
        {"github", "inputs", "vars", "needs", "strategy", "matrix", "secrets"}
    ),
    "step-env": frozenset(
        {
            "github",
            "inputs",
            "vars",
            "needs",
            "strategy",
            "matrix",
            "secrets",
            "steps",
            "job",
            "runner",
            "env",
            "hashFiles",
        }
    ),
    # `container-env` and `service-container-mapping` carry NO `context` key of
    # their own in workflow-v1.0.json, so they inherit the enclosing `container`
    # / `services` definition — and that set is NARROWER than `job-env`:
    # **`secrets` is not in it.** (Transcribed: container -> [github, inputs,
    # vars, needs, strategy, matrix].) `secrets` IS allowed in
    # `container.credentials`, which is the neighbouring key and the reason the
    # distinction is easy to get wrong. Grading these as job-env would have
    # been too permissive in exactly that spot.
    "container-env": frozenset(
        {"github", "inputs", "vars", "needs", "strategy", "matrix"}
    ),
}

#: Every context name GitHub defines. An identifier outside this set is a
#: function call (``always()``, ``format(...)``) or a property, not a context,
#: and saying so explicitly keeps the walker from inventing findings.
KNOWN_CONTEXTS = frozenset(
    {
        "github",
        "env",
        "vars",
        "job",
        "jobs",
        "steps",
        "runner",
        "secrets",
        "strategy",
        "matrix",
        "needs",
        "inputs",
    }
)

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
#: A context is used as ``name.property`` or ``name['property']`` — GitHub's
#: index syntax is legal everywhere the dot is, so a walker that knows only the
#: dot would let ``${{ runner['temp'] }}`` through a job-level ``env:`` and the
#: whole workflow would still be rejected at run-creation. Matching ``name``
#: followed by a dot OR a bracket is what distinguishes a context reference
#: from a function call, which is always followed by ``(``.
CONTEXT_REF = re.compile(r"\b([A-Za-z_][A-Za-z0-9_-]*)\s*[.\[]")
#: Single-quoted string literals inside an expression body, with `''` as the
#: escape. Stripped before the scan: a literal is DATA, not a reference, so
#: ``${{ format('{0}/runner.log', x) }}`` must not read as a `runner` use. That
#: would be a false positive on a gate whose findings block a push, and a gate
#: that cries wolf gets muted. (The hazard predates the bracket support above —
#: `'github.com'` in an expression already matched — but widening the pattern
#: widens the exposure, so it is closed in the same change.)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _expressions(text: object) -> list[str]:
    return cast("list[str]", EXPRESSION.findall(str(text)))


def contexts_in(text: object) -> set[str]:
    """The context roots referenced by every expression in *text*."""
    found: set[str] = set()
    for body in _expressions(text):
        body = STRING_LITERAL.sub("''", body)
        for ident in cast("list[str]", CONTEXT_REF.findall(body)):
            if ident in KNOWN_CONTEXTS:
                found.add(ident)
    return found


def has_expression(text: object) -> bool:
    return bool(EXPRESSION.search(str(text)))


class Report:
    def __init__(self) -> None:
        self.files: dict[str, int] = {}
        #: env KEYS graded. This is the census the vacuity floor reads.
        self.checked = 0
        #: EXPRESSIONS inside those keys. Tracked separately from `checked`
        #: because one key may hold several — `V: ${{ github.sha }}-${{
        #: matrix.shard }}` is one key and two expressions — and the "not
        #: graded" remainder below is a subtraction from an expression count.
        #: Subtracting keys from expressions is a unit mismatch, and it
        #: over-reported: measured on that exact fixture, which has NO
        #: expression outside `env:`, the gate printed "1 expression(s)
        #: outside env: not graded". That number IS the scope claim this file
        #: makes about itself, so a wrong one is worse than none.
        self.checked_exprs = 0
        self.unchecked = 0
        self.findings: list[str] = []


def _walk_env(mapping: object, scope: str, where: str, rep: Report) -> None:
    if not isinstance(mapping, dict):
        return
    allowed = ALLOWED[scope]
    for key, value in cast("dict[object, object]", mapping).items():
        if not has_expression(value):
            continue
        rep.checked += 1
        rep.checked_exprs += len(_expressions(value))
        for ctx in contexts_in(value):
            if ctx not in allowed:
                rep.findings.append(
                    f"{where}.{key}: context `{ctx}` is NOT available in a "
                    f"{scope} (allowed: {', '.join(sorted(allowed))}). "
                    f"GitHub rejects the whole workflow at run-creation — "
                    f"total_jobs: 0, nothing runs."
                )


def _count_unchecked(node: object, rep: Report) -> None:
    """Count expressions we did NOT grade, so coverage is visible."""
    if isinstance(node, dict):
        for value in cast("dict[object, object]", node).values():
            _count_unchecked(value, rep)
    elif isinstance(node, list):
        for item in cast("list[object]", node):
            _count_unchecked(item, rep)
    elif has_expression(node):
        rep.unchecked += len(_expressions(node))


def check_file(path: Path, rep: Report) -> None:
    loaded = cast("object", yaml.safe_load(path.read_text()))
    rep.files[path.name] = 0
    if not isinstance(loaded, dict):
        rep.findings.append(f"{path.name}: not a mapping at the top level")
        return
    doc = cast("dict[object, object]", loaded)

    before = rep.checked
    before_exprs = rep.checked_exprs
    _walk_env(doc.get("env"), "workflow-env", f"{path.name}:env", rep)

    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for job_id, job in cast("dict[object, object]", jobs).items():
            if not isinstance(job, dict):
                continue
            job_map = cast("dict[object, object]", job)
            _walk_env(
                job_map.get("env"), "job-env", f"{path.name}:jobs.{job_id}.env", rep
            )

            # `container:` may be a bare image string or a mapping; only the
            # mapping form has an `env:`.
            container = job_map.get("container")
            if isinstance(container, dict):
                _walk_env(
                    cast("dict[object, object]", container).get("env"),
                    "container-env",
                    f"{path.name}:jobs.{job_id}.container.env",
                    rep,
                )

            services = job_map.get("services")
            if isinstance(services, dict):
                for svc_id, svc in cast("dict[object, object]", services).items():
                    if not isinstance(svc, dict):
                        continue
                    _walk_env(
                        cast("dict[object, object]", svc).get("env"),
                        "container-env",
                        f"{path.name}:jobs.{job_id}.services.{svc_id}.env",
                        rep,
                    )

            steps = job_map.get("steps")
            if not isinstance(steps, list):
                continue
            for i, stp in enumerate(cast("list[object]", steps)):
                if not isinstance(stp, dict):
                    continue
                step_map = cast("dict[object, object]", stp)
                name = step_map.get("name") or step_map.get("uses") or f"step[{i}]"
                _walk_env(
                    step_map.get("env"),
                    "step-env",
                    f"{path.name}:jobs.{job_id}.steps[{i}] ({name}).env",
                    rep,
                )
    rep.files[path.name] = rep.checked - before

    # Everything in the file, counted, then the env EXPRESSIONS we DID grade
    # subtracted — so the reported "not graded" number is the honest remainder
    # rather than an implied claim of full coverage. Both sides must be counts
    # of the same thing; subtracting graded KEYS from total EXPRESSIONS is what
    # made this over-report (see Report.checked_exprs).
    _count_unchecked(doc, rep)
    rep.unchecked = max(0, rep.unchecked - (rep.checked_exprs - before_exprs))


def run(workflow_dir: Path) -> tuple[int, Report]:
    rep = Report()
    paths = sorted(p for p in workflow_dir.glob("*.yml") if p.is_file()) + sorted(
        p for p in workflow_dir.glob("*.yaml") if p.is_file()
    )

    if not paths:
        print(
            f"REFUSED  check-workflow-contexts: no workflow files under "
            f"{workflow_dir} — this gate examined NOTHING, which would make "
            f"every 'all contexts are available' claim vacuously true.",
            file=sys.stderr,
        )
        return 1, rep

    for path in paths:
        check_file(path, rep)

    for name, count in rep.files.items():
        print(f"  ok   {name}: {count} env key(s) graded")

    if rep.findings:
        print()
        for f in rep.findings:
            print(f"  FAIL {f}", file=sys.stderr)
        print(
            f"\ncheck-workflow-contexts: {len(rep.findings)} unavailable "
            f"context use(s) across {len(paths)} workflow(s)",
            file=sys.stderr,
        )
        return 1, rep

    print(
        f"\ncheck-workflow-contexts: {rep.checked} env key(s) / "
        f"{rep.checked_exprs} expression(s) across {len(paths)} workflow(s) use "
        f"only available contexts ({rep.unchecked} expression(s) outside env: "
        f"not graded — see the module docstring for why)"
    )
    return 0, rep


# --------------------------------------------------------------------------
# self-test — the gate must be able to FAIL, and must not fire on valid use
# --------------------------------------------------------------------------

_JOB_ENV_RUNNER = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      V: ${{ runner.temp }}/x.txt
    steps:
      - run: echo hi
"""

_STEP_ENV_RUNNER = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        env:
          V: ${{ runner.temp }}/x.txt
"""

_JOB_ENV_OK = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      V: ${{ github.sha }}-${{ matrix.shard }}
    steps:
      - run: echo hi
"""

_WORKFLOW_ENV_NEEDS = """
name: t
on: [push]
env:
  V: ${{ needs.other.result }}
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

#: Two expressions inside `env:` and ONE outside it (the step `if:`), so the
#: "not graded" remainder has a known, non-zero, non-trivial answer: 1. A
#: fixture whose correct answer is 0 cannot tell a fixed subtraction from one
#: that simply returns nothing.
_MIXED_COUNTS = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      V: ${{ github.sha }}-${{ github.ref }}
    steps:
      - run: echo hi
        if: ${{ github.event_name == 'push' }}
"""

#: The SAME defect as `_JOB_ENV_RUNNER`, written with GitHub's index syntax
#: instead of a dot. Legal YAML, legal expression syntax, identical outcome at
#: run-creation — and invisible to a walker that only knows `name.`.
_JOB_ENV_RUNNER_INDEX = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      V: ${{ runner['temp'] }}/x.txt
    steps:
      - run: echo hi
"""

#: The MIRROR of the bracket case: `runner` appears, but inside a STRING
#: LITERAL, where it is data and not a reference. This must PASS. Without the
#: literal-stripping it does not, and the gate would block a legal workflow —
#: the direction that gets a gate muted rather than the one that lets a defect
#: through, which is why both directions are pinned.
_JOB_ENV_RUNNER_IN_STRING = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      V: ${{ format('{0}/runner.log', github.sha) }}
    steps:
      - run: echo hi
"""

#: `container.env` and `services.<id>.env` are real env mappings that were
#: walked by nothing. Their allowed set is NARROWER than job-env — no
#: `secrets` — so this fixture also pins the distinction that is easiest to get
#: wrong: the same `secrets` use is legal in `container.credentials`.
_CONTAINER_ENV_SECRETS = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    container:
      image: alpine
      env:
        V: ${{ secrets.TOKEN }}
    steps:
      - run: echo hi
"""

_SERVICE_ENV_RUNNER = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres:16
        env:
          V: ${{ runner.temp }}
    steps:
      - run: echo hi
"""

_CONTAINER_ENV_OK = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    container:
      image: alpine
      env:
        V: ${{ github.sha }}
    steps:
      - run: echo hi
"""

#: A bare `container: <image>` string has no `env:` at all. The walker must
#: step over it rather than trip on it.
_CONTAINER_BARE_STRING = """
name: t
on: [push]
jobs:
  a:
    runs-on: ubuntu-latest
    container: alpine
    steps:
      - run: echo hi
        env:
          V: ${{ runner.temp }}
"""

CASES = [
    ("job-env with runner.temp REFUSES (the real defect)", _JOB_ENV_RUNNER, 1),
    ("job-env with runner['temp'] REFUSES (index syntax)", _JOB_ENV_RUNNER_INDEX, 1),
    ("'runner' inside a STRING literal passes", _JOB_ENV_RUNNER_IN_STRING, 0),
    ("step-env with runner.temp passes (control)", _STEP_ENV_RUNNER, 0),
    ("job-env with github/matrix passes (control)", _JOB_ENV_OK, 0),
    ("workflow-env with needs REFUSES", _WORKFLOW_ENV_NEEDS, 1),
    ("mixed env/non-env expressions pass", _MIXED_COUNTS, 0),
    ("container.env with secrets REFUSES", _CONTAINER_ENV_SECRETS, 1),
    ("services.<id>.env with runner REFUSES", _SERVICE_ENV_RUNNER, 1),
    ("container.env with github passes (control)", _CONTAINER_ENV_OK, 0),
    ("bare `container: <image>` string passes", _CONTAINER_BARE_STRING, 0),
]

#: THE COUNTING CONTROLS. `rep.checked` counts env KEYS and `_count_unchecked`
#: counts EXPRESSIONS, and the "not graded" remainder subtracts one from the
#: other — so a key holding two expressions used to over-report by one, and the
#: number that is WRONG is precisely the gate's own statement of its scope.
#:
#: Both directions are pinned, because a guard written against one failure
#: encodes that failure's direction: `_JOB_ENV_OK` must report ZERO ungraded
#: (it was reporting 1), and `_MIXED_COUNTS` must report exactly ONE — so a
#: "fix" that hardwired the remainder to 0, or that stopped counting outside
#: `env:` at all, fails here rather than looking correct.
#:
#: (label, fixture, expected keys, expected graded expressions, expected ungraded)
_COUNT_CASES = [
    ("two expressions in ONE env key", _JOB_ENV_OK, 1, 2, 0),
    ("env expressions PLUS one outside", _MIXED_COUNTS, 1, 2, 1),
    ("one expression in one env key", _WORKFLOW_ENV_NEEDS, 1, 1, 0),
]


def self_test() -> int:
    failures = 0
    for label, text, expected in CASES:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "workflows"
            d.mkdir(parents=True)
            (d / "t.yml").write_text(text)
            code, _ = run(d)
        ok = code == expected
        failures += not ok
        print(
            f"  {'ok  ' if ok else 'FAIL'} {label} -> exit {code} (expected {expected})"
        )

    for label, text, keys, exprs, ungraded in _COUNT_CASES:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "workflows"
            d.mkdir(parents=True)
            (d / "t.yml").write_text(text)
            _, crep = run(d)
        got = (crep.checked, crep.checked_exprs, crep.unchecked)
        want = (keys, exprs, ungraded)
        ok = got == want
        failures += not ok
        print(
            f"  {'ok  ' if ok else 'FAIL'} counts [{label}] -> "
            f"keys/graded/ungraded {got} (expected {want})"
        )

    # Vacuity control: an empty directory must REFUSE, not pass.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "workflows"
        d.mkdir(parents=True)
        code, _ = run(d)
    ok = code == 1
    failures += not ok
    print(
        f"  {'ok  ' if ok else 'FAIL'} no workflow files REFUSES "
        f"-> exit {code} (expected 1)"
    )

    # The gate must agree with the REAL tree, or it cries wolf and gets muted.
    code, rep = run(WORKFLOW_DIR)
    ok = code == 0 and rep.checked > 0
    failures += not ok
    print(
        f"  {'ok  ' if ok else 'FAIL'} the committed workflows pass and are "
        f"non-empty -> exit {code}, {rep.checked} graded"
    )

    if failures:
        print(
            f"\ncheck-workflow-contexts: SELF-TEST FAILED ({failures})",
            file=sys.stderr,
        )
        return 1
    print("\ncheck-workflow-contexts: self-test passed — the gate can fail.")
    return 0


def show_table() -> int:
    print("Allowed contexts per env scope, transcribed from GitHub's")
    print("workflow-parser schema (workflow-v1.0.json). Diff this against")
    print("that file rather than trusting the docstring:\n")
    for scope in ("workflow-env", "job-env", "container-env", "step-env"):
        print(f"  {scope:<14} {', '.join(sorted(ALLOWED[scope]))}")
    print(
        "\n`container-env` covers jobs.<id>.container.env and "
        "jobs.<id>.services.<id>.env,\nwhich inherit the `container` / "
        "`services` context (they carry no `context` key\nof their own). Note "
        "it does NOT include `secrets`, though the adjacent\n"
        "`container.credentials` does."
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--show-table", action="store_true")
    args = ap.parse_args()
    if args.show_table:
        return show_table()
    if args.self_test:
        return self_test()
    code, _ = run(WORKFLOW_DIR)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
