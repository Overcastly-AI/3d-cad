#!/usr/bin/env python3
"""Every push-triggered workflow keys its concurrency group PER COMMIT.

Why this exists
---------------
A GitHub concurrency group holds at most one RUNNING run plus one PENDING run.
A newer arrival evicts the pending one, and that happens *regardless of*
``cancel-in-progress``, which only governs runs already holding a runner. So a
group keyed on ``github.ref`` silently drops the middle commit of any rapid
back-to-back push — which is exactly what several agents pushing in parallel
produce, i.e. precisely when per-commit evidence matters most.

``ci.yml`` and ``e2e.yml`` were converted to a per-SHA push group on
2026-07-30. ``deploy-path.yml`` was not, and nobody noticed for two weeks
(CI-2, 2026-08-15) until commit ``8d386ab`` came back ``cancelled`` on
deploy-path while its neighbours succeeded — an observation that was never
discriminated against the other cause of that same word, a job hitting
``timeout-minutes``, and is recorded here as the reason somebody looked rather
than as proof of an eviction. deploy-path is the ONLY workflow that builds
the service images, and the image build is out of local reach entirely (the
Docker registry is policy-blocked in this container), so a commit that loses
its deploy-path run has no image-build evidence *anywhere*.

That drift is the thing this gate catches, and it is a class rather than an
incident: a concurrency expression cannot be exercised locally, its failure
only appears when two pushes land close together, and a wrong one looks
entirely reasonable in review. `scripts/check-build-context.py` exists for the
same reason one directory over — when a failure is unreachable locally,
re-implement just enough to gate it.

What is asserted, and why each line of it is load-bearing
--------------------------------------------------------
For every workflow under ``.github/workflows`` that has a ``push`` trigger:

  1. it has a top-level ``concurrency`` block at all — a workflow added without
     one is the drift this gate is for;
  2. its ``group`` is the canonical expression: PR → keyed on ``github.ref``,
     push → keyed on ``github.sha``.  The two arms are checked by POSITION, so
     swapping them (a group that merely *mentions* ``github.sha`` somewhere)
     fails;
  3. its ``cancel-in-progress`` is ``${{ github.event_name == 'pull_request' }}``
     — cancellation on PRs only, because a superseded PR push really is waste
     while a branch commit's run is the evidence that commit is green;
  4. its group PREFIX is unique across workflows.  Concurrency groups are
     scoped to the REPOSITORY, not to the workflow, so two workflows sharing a
     name would queue and evict each other — a defect the per-file checks above
     cannot see.

Workflows with no ``push`` trigger are reported as skipped rather than passed
in silence: coverage here is derived from the filesystem, so a workflow added
tomorrow is checked automatically and no list can go stale.

Implementation note
-------------------
Stdlib only, so it runs under the bare ``python3`` of a runner with no
installed deps, beside ``check-compose.py`` and ``check-build-context.py`` in
CI's ``compose`` job (and in ``just lint``). The YAML it needs is two scalars
under one top-level key, so it uses a deliberately small line reader — and
CROSS-CHECKS that reader against PyYAML whenever PyYAML happens to be
importable, refusing to report a result the two disagree about. A hand parser
that quietly mis-reads a file would turn this gate into an assertion that
cannot fail, which is worse than no gate.

    python3 scripts/check-workflow-concurrency.py
    python3 scripts/check-workflow-concurrency.py --self-test   # prove it fails
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The canonical group expression, with the workflow's own prefix as the only
#: degree of freedom. Written here once so a failure message can print the
#: exact text that would fix it.
CANONICAL_GROUP = (
    "${{{{ github.event_name == 'pull_request'\n"
    "    && format('{prefix}-pr-{{0}}', github.ref)\n"
    "    || format('{prefix}-sha-{{0}}', github.sha) }}}}"
)

CANONICAL_CANCEL = "${{ github.event_name == 'pull_request' }}"

#: Matches the canonical group once whitespace is collapsed. The two `format`
#: calls are anchored in order, so the PR arm must take `github.ref` and the
#: push arm `github.sha`; a check that only looked for `github.sha` anywhere in
#: the expression would pass a workflow with the arms swapped, which is the
#: symmetric mistake and just as broken.
GROUP_RE = re.compile(
    r"^\$\{\{ github\.event_name == 'pull_request' "
    r"&& format\('(?P<pr_prefix>[a-z0-9][a-z0-9-]*)-pr-\{0\}', github\.ref\) "
    r"\|\| format\('(?P<push_prefix>[a-z0-9][a-z0-9-]*)-sha-\{0\}', github\.sha\) "
    r"\}\}$"
)


def _squash(value: str) -> str:
    """Collapse runs of whitespace, so folded and inline YAML compare equal."""
    return " ".join(value.split())


def _strip_comment(value: str) -> str:
    """Drop a trailing ``# ...`` comment that is not inside quotes."""
    quote: str | None = None
    for index, char in enumerate(value):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    return value


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _section(lines: list[str], key: str) -> tuple[str, list[str]] | None:
    """The inline value and nested lines of top-level ``key:``, or None."""
    for number, line in enumerate(lines):
        if _indent(line) != 0 or not line.startswith(f"{key}:"):
            continue
        inline = _strip_comment(line[len(key) + 1 :]).strip()
        body: list[str] = []
        for following in lines[number + 1 :]:
            if not following.strip():
                body.append(following)
                continue
            if _indent(following) == 0:
                break
            body.append(following)
        return inline, body
    return None


def _scalar(body: list[str], key: str, indent: int = 2) -> str | None:
    """The value of ``key`` at *indent* within *body*, folding block scalars."""
    prefix = " " * indent + key + ":"
    for number, line in enumerate(body):
        if _indent(line) != indent or not line.startswith(prefix):
            continue
        head = line[len(prefix) :].strip()
        if head and head[0] not in "|>":
            return _strip_comment(head).strip()
        # A block scalar: everything indented deeper than the key, up to the
        # first non-blank line that is not. `>` folds to spaces, `|` keeps
        # newlines; both are squashed by every caller here, so fold either way.
        collected: list[str] = []
        for following in body[number + 1 :]:
            if not following.strip():
                collected.append("")
                continue
            if _indent(following) <= indent:
                break
            collected.append(following.strip())
        return " ".join(part for part in collected if part)
    return None


class Workflow:
    """The three facts this gate needs, read from one workflow file."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.name = path.name
        lines = text.splitlines()

        # `on:` is the trigger block. (In YAML 1.1 the bare key `on` is the
        # boolean true, which is why the PyYAML cross-check below looks for it
        # under both spellings.)
        trigger = _section(lines, "on")
        self.has_push = False
        if trigger is not None:
            inline, body = trigger
            self.has_push = "push" in inline or any(
                _indent(line) == 2 and line.strip().startswith("push:") for line in body
            )

        concurrency = _section(lines, "concurrency")
        self.has_concurrency = concurrency is not None
        self.group = _scalar(concurrency[1], "group") if concurrency else None
        self.cancel = (
            _scalar(concurrency[1], "cancel-in-progress") if concurrency else None
        )
        _cross_check(self)


def _cross_check(workflow: Workflow) -> None:
    """Assert PyYAML reads the same three facts, when PyYAML is available.

    Skipped silently where PyYAML is absent (a bare runner python3) — the point
    is that the reader is audited by a real parser wherever one exists, not
    that it is only trusted there.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on the environment
        return

    # PyYAML ships no type information, so everything below crosses an untyped
    # boundary once, here, and is narrowed by hand from `object`.
    loaded: object = cast("object", yaml.safe_load(workflow.path.read_text()))
    if not isinstance(loaded, dict):  # pragma: no cover - malformed fixture
        raise SystemExit(f"{workflow.name}: workflow is not a mapping")
    document = cast("dict[object, object]", loaded)

    # In YAML 1.1 the bare key `on` is the boolean true, which is how PyYAML
    # reads a workflow's trigger block; the raw text reader sees the string.
    trigger = document.get("on", document.get(True))
    if isinstance(trigger, (dict, list)):
        has_push = "push" in cast("dict[object, object] | list[object]", trigger)
    else:
        has_push = trigger == "push"

    block = document.get("concurrency")
    group: object = None
    cancel: object = None
    if isinstance(block, dict):
        mapping = cast("dict[object, object]", block)
        group = mapping.get("group")
        cancel = mapping.get("cancel-in-progress")

    mine = (
        workflow.has_push,
        _squash_or_none(workflow.group),
        _squash_or_none(workflow.cancel),
    )
    theirs = (has_push, _as_text(group), _as_text(cancel))

    if mine != theirs:
        raise SystemExit(
            f"{workflow.name}: the line reader and PyYAML disagree "
            f"({mine!r} vs {theirs!r}). Refusing to report a result — fix the "
            "reader in scripts/check-workflow-concurrency.py rather than "
            "trusting either."
        )


def _squash_or_none(value: str | None) -> str | None:
    return None if value is None else _squash(value)


def _as_text(value: object) -> str | None:
    """Render a PyYAML scalar the way the raw text reader would have read it."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return _squash(str(value))


def run(root: Path, quiet: bool = False) -> int:
    """Check every workflow under *root*. Non-zero when any keying is wrong."""

    def say(line: str) -> None:
        if not quiet:
            print(line)

    directory = root / ".github" / "workflows"
    paths = sorted(
        path
        for path in directory.glob("*")
        if path.suffix in {".yml", ".yaml"} and path.is_file()
    )
    if not paths:
        say(f"check-workflow-concurrency: no workflows under {directory} — nothing")
        return 1

    failures: list[str] = []
    prefixes: dict[str, str] = {}
    checked = 0

    for path in paths:
        workflow = Workflow(path, path.read_text())
        if not workflow.has_push:
            say(f"  skip {workflow.name} — no push trigger")
            continue
        checked += 1

        if not workflow.has_concurrency or workflow.group is None:
            message = (
                f"{workflow.name}: no `concurrency.group`. A push-triggered "
                "workflow needs a per-COMMIT group, or a later push evicts the "
                "run for this commit while it is still pending."
            )
            say(f"  FAIL {message}")
            failures.append(message)
            continue

        match = GROUP_RE.match(_squash(workflow.group))
        if match is None:
            message = (
                f"{workflow.name}: `concurrency.group` is not the canonical "
                f"per-SHA expression.\n         got: {_squash(workflow.group)}\n"
                "         A group keyed on github.ref loses the middle commit "
                "of a rapid double push: the group admits one running plus one "
                "PENDING run, and a newer arrival evicts the pending one no "
                "matter what cancel-in-progress says."
            )
            say(f"  FAIL {message}")
            failures.append(message)
            continue

        prefix = match.group("pr_prefix")
        if prefix != match.group("push_prefix"):
            message = (
                f"{workflow.name}: the PR arm uses prefix `{prefix}` and the "
                f"push arm `{match.group('push_prefix')}`. Use one prefix per "
                "workflow so the two arms name the same family of groups."
            )
            say(f"  FAIL {message}")
            failures.append(message)
            continue

        if prefix in prefixes:
            message = (
                f"{workflow.name}: group prefix `{prefix}` is already used by "
                f"{prefixes[prefix]}. Concurrency groups are scoped to the "
                "REPOSITORY, so two workflows sharing one queue and evict each "
                "other's runs."
            )
            say(f"  FAIL {message}")
            failures.append(message)
            continue
        prefixes[prefix] = workflow.name

        if _squash_or_none(workflow.cancel) != CANONICAL_CANCEL:
            message = (
                f"{workflow.name}: `cancel-in-progress` is "
                f"`{workflow.cancel}`, expected `{CANONICAL_CANCEL}`. Cancel on "
                "PULL REQUESTS only — on a branch push, a cancelled run is not "
                "a pass, and CLAUDE.md requires every commit to be green on its "
                "own."
            )
            say(f"  FAIL {message}")
            failures.append(message)
            continue

        say(f"  ok   {workflow.name} — push group `{prefix}-sha-<commit>`")

    if not checked:
        say("check-workflow-concurrency: no push-triggered workflow was checked")
        return 1
    if failures:
        say(f"\ncheck-workflow-concurrency: FAILED ({len(failures)} workflow(s))")
        say("The canonical block, with <prefix> the workflow's own name:\n")
        say("concurrency:")
        say("  group: >-")
        for line in CANONICAL_GROUP.format(prefix="<prefix>").splitlines():
            say(f"    {line}")
        say(f"  cancel-in-progress: {CANONICAL_CANCEL}")
        return 1
    say(
        f"\ncheck-workflow-concurrency: {checked} push-triggered workflow(s) "
        "key their group per commit"
    )
    return 0


def _fixture(prefix: str, group: str | None, cancel: str = CANONICAL_CANCEL) -> str:
    """A minimal workflow file: push-triggered, with the given concurrency."""
    text = f"name: {prefix}\n\non:\n  push:\n    branches:\n      - main\n"
    if group is not None:
        text += f"\nconcurrency:\n  group: {group}\n  cancel-in-progress: {cancel}\n"
    return text + "\njobs:\n  noop:\n    runs-on: ubuntu-latest\n    steps:\n"


def _canonical_fixture(prefix: str, folded: bool = True) -> str:
    body = CANONICAL_GROUP.format(prefix=prefix)
    if not folded:
        # Same expression on ONE line: the gate is about SEMANTICS, so this
        # must pass too, and that is what proves the folding reader is not
        # accidentally matching on layout.
        return _fixture(prefix, _squash(body))
    indented = "\n".join(f"    {line}" for line in body.splitlines())
    return _fixture(prefix, ">-\n" + indented)


def self_test() -> int:
    """Prove the gate FAILS on each way the keying can be wrong.

    Every case below is a defect this repo has actually paid for or is one
    negation away from: the CI-2 ref-keyed group, the 2026-07-30 blanket
    cancellation, a new workflow landing with no concurrency block at all, and
    two workflows sharing a repository-scoped group name. The swapped-arms case
    is here because it is the symmetric mistake — a guard written against one
    failure tends to encode that failure's direction, and a check that merely
    looked for `github.sha` in the expression would sail past it.
    """
    import tempfile

    cases: list[tuple[str, dict[str, str], int]] = [
        (
            "canonical trio (folded)",
            {
                "ci.yml": _canonical_fixture("ci"),
                "e2e.yml": _canonical_fixture("e2e"),
                "deploy-path.yml": _canonical_fixture("deploy-path"),
            },
            0,
        ),
        (
            "canonical, written on one line",
            {"ci.yml": _canonical_fixture("ci", folded=False)},
            0,
        ),
        (
            "CI-2: push group keyed on the ref",
            {
                "deploy-path.yml": _fixture(
                    "deploy-path",
                    "deploy-path-${{ github.ref }}",
                    cancel="false",
                )
            },
            1,
        ),
        (
            "blanket cancel-in-progress: true",
            {
                "ci.yml": _fixture(
                    "ci", _squash(CANONICAL_GROUP.format(prefix="ci")), "true"
                )
            },
            1,
        ),
        (
            "no concurrency block at all",
            {"new.yml": _fixture("new", None)},
            1,
        ),
        (
            "two workflows sharing a repository-scoped group",
            {
                "ci.yml": _canonical_fixture("ci"),
                "clone.yml": _canonical_fixture("ci"),
            },
            1,
        ),
        (
            "arms swapped: PR keyed on sha, push on ref",
            {
                "ci.yml": _fixture(
                    "ci",
                    "${{ github.event_name == 'pull_request' "
                    "&& format('ci-pr-{0}', github.sha) "
                    "|| format('ci-sha-{0}', github.ref) }}",
                )
            },
            1,
        ),
        (
            "pull_request-only workflow is skipped, not failed",
            {
                "ci.yml": _canonical_fixture("ci"),
                "manual.yml": "name: manual\n\non:\n  pull_request:\n\njobs:\n",
            },
            0,
        ),
    ]

    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for label, files, expected in cases:
            root = Path(tmp) / label.replace(" ", "-").replace(":", "")
            (root / ".github" / "workflows").mkdir(parents=True)
            for name, text in files.items():
                (root / ".github" / "workflows" / name).write_text(text)
            actual = run(root, quiet=True)
            ok = actual == expected
            results.append((label, ok))
            verdict = "ok  " if ok else "FAIL"
            print(f"  {verdict} {label} → exit {actual} (expected {expected})")

    if all(ok for _, ok in results):
        print("\ncheck-workflow-concurrency: self-test passed — the gate can fail.")
        return 0
    print("\ncheck-workflow-concurrency: SELF-TEST FAILED — this gate proves nothing.")
    return 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
