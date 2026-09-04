#!/usr/bin/env python3
"""No mutation/ablation/debug marker survives into committed SOURCE.

Why this exists
---------------
Mutation testing is mandatory here: every builder injects a mutant, watches the
gate redden, and reverts. On 2026-08-14 an agent was stopped mid-mutation and
the orchestrator committed its preserved worktree, which still contained

    rendersInProbeWindow:
      after === null || before === null ? null : 0, // <marker>: always 0

in ``apps/web/e2e/diagnostics.ts``. ``just lint`` passed. ``pyright`` passed.
1598 unit tests passed. The only gate that could see it was the e2e, and the
e2e was the gate that had been skipped. It then failed on every commit for the
next ten and was half of a red streak that went unexplained for a day. The
comment said what it was, in capitals, and nothing read it (docs/RETRO.md §4b).

That is a *class*, not an incident, and it is manufactured by our own process:
an agent killed mid-mutation leaves a defect that is BY CONSTRUCTION invisible
to every gate except the one it was aimed at. So the guard cannot be another
behavioural test — it has to be the one thing that is cheap and total: read
every line of source and refuse the ones that are labelled.

The design problem is false positives, not detection
----------------------------------------------------
This repo writes at length, in code comments, about its own mutation tests. A
word-boundary grep for the marker over ``*.ts`` matches FOUR legitimate lines
today (``apps/web/e2e/support.ts:426`` and three in
``sketch-visibility.spec.ts``), all of them prose calibrating a threshold
against a measured mutant. ``docs/RETRO.md``, ``CLAUDE.md`` and
``.claude/ORCHESTRATOR.md`` contain the word too, and several commit messages
quote the defect line verbatim. A gate that fires on those gets muted within a
day, and a muted gate is worse than none.

So the discriminator is not the WORD, it is whether the word LABELS CODE:

  * a marker anywhere in the *code* part of a line (identifier, string) — fail;
  * a marker anywhere in a *trailing* comment, i.e. one that shares its line
    with executing code — fail.  This is the defect's exact shape;
  * a marker in a *standalone* comment — fail only in LABEL form: it starts the
    comment body AND is followed by label punctuation (``:  =  -  >  !``),
    by nothing, or by a body short enough (<= 40 chars) to be a note rather
    than a sentence.

Prose acquits because prose puts the word in the middle of a sentence, or ends
it with a full stop and keeps writing. All four live occurrences acquit; the
real defect line fails on both of the first two rules. Markdown is not scanned
at all — prose about this defect class is exactly what ``docs/`` is for.

If this fires while you are mid-mutation, it is working. Mutation testing runs
the gate the mutant is AIMED at, not ``just lint``; a labelled mutant reaching
``just lint`` means it is on its way into a commit, which is the exact journey
``0580f7d`` made. Revert the mutant, then lint.

Consequence, stated so nobody has to discover it: **do not open a standalone
comment with an all-caps marker, and do not put one in a trailing comment.**
There is no allow-list and no suppression pragma, deliberately — an allow-list
rots and a pragma is the mute button this gate exists to avoid. If you need to
write about a past mutant in code, write it lowercase (``healthy 1168.32,
mutant 212.49`` — how the existing prose already does it) or put the word
somewhere other than the first token of the line.

Telling code from prose needs a tokenizer, so:
  * ``.py`` is classified by the stdlib ``tokenize`` module — a real tokenizer,
    not a reimplementation. COMMENT tokens and TRIPLE-QUOTED strings (i.e.
    docstrings) are prose; everything else is code.
  * ``.ts/.tsx/.js/.css/.c`` and the ``#``-comment family (``.sh .yml .toml``,
    ``justfile``, ``*.Dockerfile``) use a small hand scanner that tracks string
    literals, template literals and ``/* */`` blocks. It is audited two ways:
    a self-test battery of the constructs that break naive greps, and an
    empirical run over the whole repository, where it must acquit all four
    known-prose lines and flag nothing else.

What is deliberately NOT a marker, and why
------------------------------------------
* ``MUTATION`` — the word for the *practice*. ``useMutation`` is a TanStack
  Query API used throughout ``apps/web`` and "mutation testing" is written in
  capitals in headings here. ``MUTANT`` names the *artefact*; that is the line.
* ``TODO`` / ``FIXME`` — zero occurrences in source today, and they annotate
  *intent*, not behaviour. This gate is about code that LIES about what it
  measures. Firing on TODO turns it into a style rule people argue about.
* ``HACK`` / ``TEMP`` — mean "ugly but correct", which is not the class.
* ``.skip(`` — measured: ten legitimate uses (``pytest.skip`` on a missing
  server binary, ``@pytest.mark.skipif``, a Playwright ``test.skip(condition,
  reason)``). A conditional skip is a real construct. ``.only(`` has NO
  legitimate form and zero occurrences, so it is in.
* ``console.log`` — eslint's territory, and legitimate in ``scripts/``.
* ``@ts-ignore`` / ``eslint-disable`` — suppression, a different class, owned
  by the lint config.

What this CANNOT catch, said plainly
------------------------------------
An UNLABELLED mutant. If the stopped agent had written ``: 0`` with no comment,
nothing here would see it, and no cheap static derivation would: telling "this
literal is the answer" from "this literal replaced a computation" needs the
semantics of the surrounding program.

A second, marker-independent derivation was built and rejected ON MEASUREMENT
rather than on argument, and ``--survey`` still prints the census so the number
can be re-derived instead of believed. The candidate was the shape the brief
suggested — a commented-out original sitting beside the constant that replaced
it, scored by ``difflib`` similarity within a three-line window. It flags **15**
lines of this repository and **none** of them is a defect: generated
``@enum {string}`` JSDoc beside its enum, two ``# shellcheck source=`` directives
beside the ``source`` line they annotate, a worked arithmetic example beside the
assertion it explains. A 100% false-positive rate is a mute button by another
name. And the decisive point is not the noise: **it would not have caught the
real defect either.** The stopped agent overwrote ``after - before`` in place;
there was never a commented-out original to find. A second derivation that
misses the incident that commissioned it is not a second opinion, it is a
second guess.

So: marker-grep is the practical shape here, and it closes the LABELLED half.
The unlabelled half has a control, and it is not static — it is the
ORCHESTRATOR.md rule that reconciling a stopped agent means running the gates
that agent's work was ABOUT, plus reading ``git diff --cached`` in full. This
gate is one second of CI and it says which half it covers.

Non-vacuity
-----------
Two floors, because ``0 violations`` is the same output as ``the scanner
matched nothing``:

 1. every configured pattern is run against a built-in canary corpus on EVERY
    invocation, and the run aborts if any pattern fails to match it or if the
    classifier convicts the canary's prose. A pattern that has been typo'd,
    commented out, or shadowed cannot report a clean tree.
 2. the file walk must reach at least ``MIN_FILES`` files (today it reaches
    ~880). A path filter that quietly admits nothing fails instead of passing.

Files are taken from ``git ls-files`` — TRACKED content only. That is a
deliberate difference from ``prettier --check .``, which walks the filesystem
and so lets one agent's untracked scratch file turn the gate red for everyone
(CLAUDE.md, 2026-07-30). Staged-new files are index entries, so a marker still
cannot reach a commit unseen.

    python3 scripts/check-mutation-markers.py
    python3 scripts/check-mutation-markers.py --self-test   # prove it can fail
    python3 scripts/check-mutation-markers.py --survey      # the census above
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

REPO_ROOT = Path(__file__).resolve().parent.parent

#: This file necessarily contains every marker literal it hunts for, so it is
#: the one path the scan skips. It is a single exact path, not a glob or a
#: directory: the self-test's `the-exemption-is-one-exact-path` case puts the
#: identical bytes at a different name and demands a failure, so the exemption
#: cannot quietly grow into a hiding place.
SELF_REL = "scripts/check-mutation-markers.py"

#: The walk must reach at least this many files. Today it reaches ~880; the
#: floor is set well below that so ordinary churn never trips it, and well
#: above zero so a broken path filter cannot report a clean tree.
MIN_FILES = 300

# --------------------------------------------------------------------------
# What gets read
# --------------------------------------------------------------------------

#: `//` + `/* */`, with string and template-literal tracking.
C_LIKE = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".c"}

#: Classified by the stdlib tokenizer.
PY_LIKE = {".py"}

#: `#` to end of line, comment only at the start of a word (the YAML/shell
#: rule, which also keeps `${VAR#pattern}` out of trouble).
HASH_LIKE = {".sh", ".bash", ".yml", ".yaml", ".toml", ".ini"}
HASH_NAMES = {"justfile", "Dockerfile"}

#: Generated or foreign-syntax files. Lockfiles have no comments and are
#: enormous; `.mako` is an alembic template whose comment token is `##` and
#: whose `#` is interpolation syntax, so the hash scanner would misread it —
#: two files, no marker risk, not worth a fourth classifier.
SKIP_NAMES = {"pnpm-lock.yaml", "uv.lock", "package-lock.json"}
SKIP_SUFFIXES = {".mako"}

#: Where a focused test would live. `.only(` is only meaningful here.
TEST_PATH = re.compile(
    r"(?:^|/)(?:e2e|tests?)/|\.(?:spec|test)\.[cm]?[jt]sx?$|(?:^|/)test_[^/]*\.py$"
)


def kind_of(rel: str) -> str | None:
    """Which classifier a repo-relative path needs, or None to skip it.

    `PurePath`, so this never touches the filesystem: the self-test asks the
    same question of paths that do not exist.
    """
    path = PurePath(rel)
    if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
        return None
    if path.suffix in PY_LIKE:
        return "py"
    if path.suffix in C_LIKE:
        return "c"
    if path.suffix in HASH_LIKE or path.name in HASH_NAMES:
        return "hash"
    if path.name.endswith(".Dockerfile"):
        return "hash"
    return None


# --------------------------------------------------------------------------
# What counts as a marker
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Marker:
    """A capitalised label that must never survive into source."""

    name: str
    pattern: re.Pattern[str]
    #: A plain substring that EVERY match of `pattern` must contain. Only used
    #: to skip files cheaply (classifying 877 files char-by-char costs 5.6 s;
    #: with this it costs 0.3 s). Being a superset is the whole contract, and
    #: `canary_check` re-asserts it against every canary on every run so the
    #: two cannot drift apart into a scanner that silently sees nothing.
    trigger: str
    canary: str
    hint: str


#: Case-sensitive, all-caps only. Lower-case `mutant`/`ablation` is how the
#: measured prose in `apps/web/e2e/**` already reads, and keeping it legal is
#: what makes "write it lowercase" a real escape rather than a lie.
MARKERS: tuple[Marker, ...] = (
    Marker(
        "mutant",
        re.compile(r"\bMUTANTS?\b|\bMUTATED\b"),
        "MUTANT|MUTATED",
        "x = 0; // " + "MUTANT" + ": always 0",
        "a mutation-test constant left in the tree (docs/RETRO.md §4b)",
    ),
    Marker(
        "ablation",
        re.compile(r"\bABLATIONS?\b|\bABLATED\b"),
        "ABLAT",
        "x = 0; // " + "ABLATION" + ": guard removed",
        "an ablation left switched on",
    ),
    Marker(
        "do-not-commit",
        re.compile(
            r"\bDO[ _-]?NOT[ _-]?(?:COMMIT|MERGE|SHIP|PUSH)\b"
            r"|\bDONOTCOMMIT\b|\bNOCOMMIT\b"
        ),
        "DO[ _-]?NOT|DONOTCOMMIT|NOCOMMIT",
        "x = 0; // " + "DO NOT COMMIT",
        "the author said so themselves",
    ),
    Marker(
        "revert-me",
        re.compile(r"\bREVERT[ _-]?ME\b|\bREVERT[ _-]BEFORE\b|\bUNREVERT\b"),
        "REVERT",
        "x = 0; // " + "REVERT ME",
        "a temporary change that outlived its author's session",
    ),
    Marker(
        "xxx",
        re.compile(r"\bXXX\b"),
        "XXX",
        "x = 0; // " + "XXX" + " REVERT",
        "the C-tradition danger marker; zero legitimate uses in this tree",
    ),
)


@dataclass(frozen=True)
class CodePattern:
    """Something that must not appear in the CODE part of a line."""

    name: str
    pattern: re.Pattern[str]
    trigger: str
    kinds: frozenset[str]
    tests_only: bool
    canary_path: str
    canary: str
    hint: str


CODE_PATTERNS: tuple[CodePattern, ...] = (
    CodePattern(
        "debugger-statement",
        re.compile(r"(?:^|[\s;{}()])debugger\s*(?:;|$)"),
        "debugger",
        frozenset({"c"}),
        False,
        "canary.ts",
        "  debugger;",
        "a breakpoint that ships to users",
    ),
    CodePattern(
        "focused-test",
        re.compile(r"\b(?:test|it|describe|suite|bench|context)\.only\s*\("),
        r"\.only",
        frozenset({"c"}),
        True,
        "e2e/canary.spec.ts",
        'test.only("just this one", async () => {});',
        "a focused test silently disables every other test in the file",
    ),
    CodePattern(
        "python-debugger",
        re.compile(
            r"\b(?:i?pdb)\.set_trace\s*\(|\bbreakpoint\s*\(\s*\)|^\s*import\s+i?pdb\b"
        ),
        "set_trace|breakpoint|pdb",
        frozenset({"py"}),
        False,
        "canary.py",
        "    breakpoint()",
        "an interactive debugger hangs CI instead of failing it",
    ),
)

#: The union of every trigger. A file whose raw text does not match this cannot
#: contain a violation, so it is never classified. Built from the tables above
#: rather than written out, so adding a pattern cannot leave the fast path
#: behind — the failure mode that would turn this gate into a scanner that
#: examines nothing and reports a clean tree.
_TRIGGERS: tuple[str, ...] = tuple(item.trigger for item in MARKERS) + tuple(
    item.trigger for item in CODE_PATTERNS
)
PREFILTER = re.compile(
    "|".join(f"(?:{trigger})" for trigger in _TRIGGERS), re.MULTILINE
)

#: Punctuation that turns a leading marker into a LABEL rather than the first
#: word of a sentence. A full stop is deliberately absent: `MUTANT. Calibrate
#: from those two numbers` is prose, and is a real line in this repository.
LABEL_PUNCT = frozenset(":=->!|")

#: A comment body no longer than this is a note, not a sentence, so a leading
#: marker labels it even without punctuation (`XXX REVERT`, `MUTANT always 0`).
#: The four known-prose lines in the tree run 65-74 characters.
MAX_LABEL_BODY = 40

# --------------------------------------------------------------------------
# Telling code from prose
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """One source line split into its executing part and its prose part."""

    number: int
    code: str
    comment: str


def _split_c_like(text: str) -> list[Line]:
    """Split C-family lines, tracking strings, template literals and blocks.

    Known limit: an unescaped `//` inside a REGEX literal (`/\\/\\//`) reads as
    a line comment. Harmless in practice — it only changes which half of the
    line a marker would be found in, and both halves are checked — and closing
    it would need a full JS parse to tell division from a regex.
    """
    lines: list[Line] = []
    in_block = False
    in_template = False
    for number, raw in enumerate(text.splitlines(), start=1):
        code: list[str] = []
        comment: list[str] = []
        quote: str | None = None
        index, end = 0, len(raw)
        while index < end:
            char = raw[index]
            if in_block:
                comment.append(char)
                if char == "*" and index + 1 < end and raw[index + 1] == "/":
                    comment.append("/")
                    index += 2
                    in_block = False
                    continue
                index += 1
                continue
            if in_template or quote is not None:
                code.append(char)
                if char == "\\":
                    if index + 1 < end:
                        code.append(raw[index + 1])
                        index += 2
                    else:
                        index += 1
                    continue
                if in_template and char == "`":
                    in_template = False
                elif quote is not None and char == quote:
                    quote = None
                index += 1
                continue
            if char == "/" and index + 1 < end and raw[index + 1] == "/":
                comment.append(raw[index:])
                index = end
                continue
            if char == "/" and index + 1 < end and raw[index + 1] == "*":
                in_block = True
                comment.append("/*")
                index += 2
                continue
            if char == "`":
                in_template = True
            elif char in "'\"":
                quote = char
            code.append(char)
            index += 1
        # Single- and double-quoted strings do not span lines in this family;
        # template literals and block comments do, so only `quote` resets.
        lines.append(Line(number, "".join(code), "".join(comment)))
    return lines


def _split_hash(text: str) -> list[Line]:
    """Split `#`-comment lines (shell, YAML, TOML, justfile, Dockerfile).

    A `#` opens a comment only at the start of a line or after whitespace —
    the YAML and shell rule, which also keeps `${VAR#pattern}` and `sha#1` out
    of the comment half. Heredocs are not tracked; a `#` inside one reads as a
    comment, which can only ever move a marker from the code half to the prose
    half of a line that has no code on it anyway.
    """
    lines: list[Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        code: list[str] = []
        comment: list[str] = []
        quote: str | None = None
        index, end = 0, len(raw)
        while index < end:
            char = raw[index]
            if quote is not None:
                code.append(char)
                if char == "\\" and quote == '"' and index + 1 < end:
                    code.append(raw[index + 1])
                    index += 2
                    continue
                if char == quote:
                    quote = None
                index += 1
                continue
            if char == "#" and (index == 0 or raw[index - 1].isspace()):
                comment.append(raw[index:])
                index = end
                continue
            if char in "'\"":
                quote = char
            code.append(char)
            index += 1
        lines.append(Line(number, "".join(code), "".join(comment)))
    return lines


_TRIPLE = re.compile(r"^[A-Za-z]*(?:\"\"\"|''')")


def _split_python(text: str) -> list[Line]:
    """Split Python lines using the stdlib tokenizer, not a reimplementation.

    COMMENT tokens are prose. So are TRIPLE-QUOTED strings: a docstring is how
    this repository writes about its own mutation tests, and treating it as
    code would convict every honest explanation. Ordinary quoted strings stay
    on the code side, so a marker smuggled into a string literal still fails.

    Falls back to the `#` scanner for a file the tokenizer refuses (a syntax
    error is somebody else's gate, and this one should not also explode).
    """
    raw_lines = text.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _split_hash(text)

    prose: list[bytearray] = [bytearray(len(line)) for line in raw_lines]

    def mark(srow: int, scol: int, erow: int, ecol: int) -> None:
        for row in range(srow, erow + 1):
            if row < 1 or row > len(prose):
                continue
            line = prose[row - 1]
            start = scol if row == srow else 0
            stop = ecol if row == erow else len(line)
            for column in range(max(start, 0), min(stop, len(line))):
                line[column] = 1

    for token in tokens:
        if token.type == tokenize.COMMENT or (
            token.type == tokenize.STRING and _TRIPLE.match(token.string) is not None
        ):
            mark(token.start[0], token.start[1], token.end[0], token.end[1])

    lines: list[Line] = []
    for number, raw in enumerate(raw_lines, start=1):
        flags = prose[number - 1]
        pairs = list(zip(raw, flags, strict=True))
        code = "".join(char for char, flag in pairs if not flag)
        comment = "".join(char for char, flag in pairs if flag)
        lines.append(Line(number, code, comment))
    return lines


SPLITTERS = {"c": _split_c_like, "hash": _split_hash, "py": _split_python}

#: Comment openers and block decoration to strip before asking "does this
#: comment START with a marker": `//`, `#`, `/*`, the ` * ` of a JSDoc
#: continuation line, and a trailing `*/`.
_DECORATION = re.compile(r"^(?:/\*+|//+|#+|\*+/?|--)\s*")


def comment_body(comment: str) -> str:
    """The prose of a comment, with its opener and block decoration removed."""
    body = comment.strip()
    while True:
        stripped = _DECORATION.sub("", body, count=1)
        if stripped == body:
            break
        body = stripped
    return body.removesuffix("*/").strip()


def labels_code(body: str, match: re.Match[str]) -> bool:
    """Does this marker LABEL the comment, or merely appear in a sentence?"""
    if match.start() != 0:
        return False
    rest = body[match.end() :].lstrip()
    if not rest:
        return True
    if rest[0] in LABEL_PUNCT:
        return True
    return len(body) <= MAX_LABEL_BODY


# --------------------------------------------------------------------------
# The scan
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    where: str
    text: str
    hint: str


def scan_text(rel: str, text: str, kind: str) -> list[Violation]:
    """Every violation in one file's text."""
    if PREFILTER.search(text) is None:
        return []
    found: list[Violation] = []
    is_test = TEST_PATH.search(rel) is not None
    for line in SPLITTERS[kind](text):
        stripped = line.code.strip()
        body = comment_body(line.comment) if line.comment else ""

        for marker in MARKERS:
            hit = marker.pattern.search(line.code)
            if hit is not None:
                found.append(
                    Violation(
                        rel,
                        line.number,
                        marker.name,
                        "in code",
                        (line.code + line.comment).strip(),
                        marker.hint,
                    )
                )
                continue
            if not body:
                continue
            hit = marker.pattern.search(body)
            if hit is None:
                continue
            if stripped:
                where = "in a trailing comment on executing code"
            elif labels_code(body, hit):
                where = "labelling the line below it"
            else:
                continue  # prose: the word in a sentence, not a label
            found.append(
                Violation(
                    rel,
                    line.number,
                    marker.name,
                    where,
                    (line.code + line.comment).strip(),
                    marker.hint,
                )
            )

        for pattern in CODE_PATTERNS:
            if kind not in pattern.kinds:
                continue
            if pattern.tests_only and not is_test:
                continue
            if pattern.pattern.search(line.code) is not None:
                found.append(
                    Violation(
                        rel,
                        line.number,
                        pattern.name,
                        "in code",
                        (line.code + line.comment).strip(),
                        pattern.hint,
                    )
                )
    return found


def repo_files(root: Path) -> list[str]:
    """Tracked, scannable, repo-relative paths.

    `git ls-files` rather than a filesystem walk: an untracked scratch file
    must not be able to turn this gate red for a colleague the way an
    untracked `eval1.json` once turned `prettier --check .` red for everyone.
    Falls back to a walk outside a git repository, which is how the self-test's
    temporary corpora are read.
    """
    listed: list[str] = []
    # `--show-toplevel` first, because a temporary directory that happens to
    # live INSIDE a checkout would otherwise make `git ls-files` answer for the
    # enclosing repository — a self-test fixture silently scanning the real
    # tree is the "gate measured the wrong input" trap in miniature.
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    at_toplevel = top.returncode == 0 and Path(top.stdout.strip()) == root.resolve()
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if at_toplevel and result.returncode == 0:
        listed = [entry for entry in result.stdout.split("\0") if entry]
    else:
        listed = [
            str(path.relative_to(root))
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]
    ignored = ("node_modules/", ".venv/", "dist/", "build/", "__pycache__/")
    return [
        rel
        for rel in listed
        if rel != SELF_REL
        and not any(part in rel for part in ignored)
        and kind_of(rel) is not None
    ]


def canary_check() -> list[str]:
    """Prove every pattern is live, in this process, before trusting a clean run.

    Positive: each marker and each code pattern must be convicted from its own
    canary line. Negative: the four shapes of legitimate prose this repository
    actually writes must be acquitted. `0 violations` from a scanner that
    cannot match anything is the failure this repo has shipped before, and it
    reads identically to success.
    """
    problems: list[str] = []

    for marker in MARKERS:
        if PREFILTER.search(marker.canary) is None:
            problems.append(f"the prefilter does not cover marker `{marker.name}`")
        hits = scan_text("canary.ts", marker.canary, "c")
        if not any(hit.rule == marker.name for hit in hits):
            problems.append(f"marker `{marker.name}` did not match its own canary")

    for pattern in CODE_PATTERNS:
        if PREFILTER.search(pattern.canary) is None:
            problems.append(f"the prefilter does not cover pattern `{pattern.name}`")
        kind = "py" if "py" in pattern.kinds else "c"
        hits = scan_text(pattern.canary_path, pattern.canary, kind)
        if not any(hit.rule == pattern.name for hit in hits):
            problems.append(f"pattern `{pattern.name}` did not match its own canary")

    word = "MUTANT"
    prose = (
        "/**\n"
        f" * healthy 1168.32, mutant 212.49 — ANY FLOOR BELOW ~213 PASSES THE\n"
        f" * {word}. Calibrate from those two numbers, not from 'versus zero'.\n"
        " */\n"
        f"// THE {word} IS NOT ZERO, AND THE FIRST DRAFT OF THIS COMMENT SAID IT WAS.\n"
        f"// a re-calibrator is the {word}, 212.49: anything below ~213 passes it, so\n"
        f"// AND THE {word} IS NOT ONE NUMBER - IT IS A LOTTERY, re-measured\n"
    )
    convicted = scan_text("prose-canary.ts", prose, "c")
    if convicted:
        problems.append(
            "the classifier convicted known-good prose: "
            + "; ".join(f"line {hit.line}" for hit in convicted)
        )
    return problems


def run(root: Path, quiet: bool = False, min_files: int = MIN_FILES) -> int:
    """Scan *root*. Non-zero on any violation, dead pattern or empty walk."""

    def say(line: str) -> None:
        if not quiet:
            print(line)

    problems = canary_check()
    if problems:
        for problem in problems:
            say(f"  FAIL {problem}")
        say(
            "\ncheck-mutation-markers: the SCANNER is broken, so a clean tree "
            "would prove nothing. Refusing to report a result."
        )
        return 1

    violations: list[Violation] = []
    acquitted = 0
    scanned = 0
    for rel in repo_files(root):
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        if PREFILTER.search(text) is None:
            continue
        kind = kind_of(rel)
        assert kind is not None
        violations.extend(scan_text(rel, text, kind))
        for marker in MARKERS:
            acquitted += len(marker.pattern.findall(text))

    if scanned < min_files:
        say(
            f"check-mutation-markers: only {scanned} file(s) scanned, floor is "
            f"{min_files}. The path filter or the file list is broken — a scan "
            "that reaches nothing reports the same '0 violations' as a clean tree."
        )
        return 1

    if violations:
        for hit in sorted(violations, key=lambda v: (v.path, v.line)):
            say(f"  FAIL {hit.path}:{hit.line}  [{hit.rule}] {hit.where}")
            say(f"         {hit.text}")
            say(f"         why: {hit.hint}")
        say(
            f"\ncheck-mutation-markers: FAILED ({len(violations)} marker(s) in "
            f"{len({hit.path for hit in violations})} file(s))\n"
            "A marker that labels code is mutation/debug residue: revert the "
            "line, do not delete the comment and keep the constant.\n"
            "If this is PROSE about a past mutation, write the word in lower "
            "case or move it off the first token of the comment — that is the "
            "whole difference between a label and a sentence, and there is no "
            "suppression pragma by design."
        )
        return 1

    say(
        f"check-mutation-markers: {scanned} source file(s) clean; "
        f"{len(MARKERS) + len(CODE_PATTERNS)} pattern(s) proven live against the "
        f"canary; {acquitted} prose mention(s) correctly acquitted"
    )
    return 0


# --------------------------------------------------------------------------
# The census that rejected the second derivation (kept so it can be re-derived)
# --------------------------------------------------------------------------


def survey(root: Path) -> int:
    """Count "commented-out code beside live code" — the rejected heuristic.

    The obvious second, marker-independent derivation is to look for the shape
    the ticket describes: a commented-out original sitting next to the constant
    that replaced it. This prints every line the heuristic would flag, so the
    decision to leave it out rests on a number anyone can reproduce rather than
    on an assertion.
    """
    import difflib

    flagged = 0
    for rel in repo_files(root):
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        kind = kind_of(rel)
        assert kind is not None
        lines = SPLITTERS[kind](text)
        for index, line in enumerate(lines):
            if line.code.strip():
                continue
            body = comment_body(line.comment)
            if not body or not re.search(r"[=;{(]|=>", body):
                continue
            window = lines[max(0, index - 3) : index + 4]
            for other in window:
                live = other.code.strip()
                if not live or other.number == line.number:
                    continue
                ratio = difflib.SequenceMatcher(None, body, live).ratio()
                if ratio >= 0.6:
                    flagged += 1
                    print(f"  {rel}:{line.number}  ~{ratio:.2f}  {body[:70]}")
                    break
    print(f"\ncommented-out-code-beside-live-code would flag {flagged} line(s)")
    return 0


# --------------------------------------------------------------------------
# Proving the gate can fail
# --------------------------------------------------------------------------

#: The line that actually shipped, reassembled so this file does not contain
#: it verbatim (it is exempt from the scan, but a fixture that reads as the
#: real thing is a trap for the next grep somebody runs).
REAL_DEFECT = (
    "      rendersInProbeWindow: after === null || before === null ? null : 0,"
    " // " + "MUTANT" + ": always 0"
)


def _padding(count: int) -> dict[str, str]:
    """`count` innocuous TypeScript files, so a case clears the MIN_FILES floor.

    Without these every case would exit 1 for the wrong reason, and a fixture
    that fails for the wrong reason is the same defect as a gate that passes
    for the wrong reason.
    """
    return {
        f"src/pad{index}.ts": f"export const pad{index} = {index};\n"
        for index in range(count)
    }


#: How many checks `self_test` is supposed to append. A count floor exists
#: because the verdict is `all(ok for _, ok in results)` and `all([])` is True:
#: a `results.append` lost to a refactor removes coverage silently and the
#: self-test still prints that it passed. This gate already fixtures a corpus
#: floor (MIN_FILES) for the tree it scans; this is the same floor for the
#: check list that asserts it. `<`, not `!=`, so ADDING checks needs no edit
#: here — only losing them is an error.
EXPECTED_CHECKS = 23


def self_test() -> int:
    """Reproduce the real defect and DEMAND a failure, then the controls.

    The required cases, in the order the ticket that commissioned this gate
    names them: the exact line that shipped, in a file with a `.ts` extension,
    must fail; the same words as prose in a `.md` must not be read at all; and
    a scan that matches nothing must fail rather than report a clean tree.
    Everything after that is a symmetric mistake — this repo's lesson is that a
    guard written against one failure encodes that failure's direction, so the
    acquittal side is fixtured as heavily as the conviction side.
    """
    import tempfile

    word = "MUTANT"

    prose_ts = (
        "/**\n"
        f" * healthy 1168.32, mutant 212.49 — ANY FLOOR BELOW ~213 PASSES THE\n"
        f" * {word}. Calibrate from those two numbers, not from 'versus zero'.\n"
        " */\n"
        "export const INK_FLOOR = 400;\n"
        f"// THE {word} IS NOT ZERO, AND THE FIRST DRAFT OF THIS COMMENT SAID IT WAS.\n"
        f"// a re-calibrator is the {word}, 212.49: anything below ~213 passes it, so\n"
    )

    cases: list[tuple[str, dict[str, str], int, int]] = [
        (
            "THE REAL DEFECT: the shipped line, in a .ts file",
            {
                "apps/web/e2e/diagnostics.ts": (
                    "const common = {\n" + REAL_DEFECT + "\n};\n"
                )
            },
            1,
            1,
        ),
        (
            # The `.ts` file is not decoration: with only the markdown present
            # the corpus has ZERO scannable files, so the case would exit 1 on
            # the floor and, had the expectation been 1, would have "passed"
            # for entirely the wrong reason. The floor caught exactly that
            # while this fixture was being written.
            "NEGATIVE CONTROL: the same line as prose in a .md",
            {
                "docs/RETRO.md": "The mutant was:\n\n```ts\n" + REAL_DEFECT + "\n```\n",
                "CLAUDE.md": f"a stopped agent leaves a {word} in the tree\n",
                "src/innocent.ts": "export const x = 1;\n",
            },
            0,
            1,
        ),
        (
            "NEGATIVE CONTROL: measured prose about a mutant, in .ts",
            {"apps/web/e2e/support.ts": prose_ts},
            0,
            1,
        ),
        # The three floor cases run against the REAL MIN_FILES; everything else
        # runs against a floor of 1, so a fixture never has to write 300 files
        # to prove a point about one line. The padded pass is what stops the
        # floor from being a check that always fails.
        (
            "NON-VACUITY: a clean corpus AT the floor passes",
            dict(_padding(MIN_FILES)),
            0,
            MIN_FILES,
        ),
        (
            "NON-VACUITY: a corpus BELOW the floor fails",
            {"src/only.ts": "export const x = 1;\n"},
            1,
            MIN_FILES,
        ),
        (
            "NON-VACUITY: an empty corpus fails",
            {},
            1,
            MIN_FILES,
        ),
        (
            "the marker labelling the line below it (no colon needed)",
            {"src/a.ts": f"// {word} always 0\nexport const x = 0;\n"},
            1,
            1,
        ),
        (
            "the marker in a python docstring sentence is prose",
            {
                "services/geometry/x.py": (
                    '"""Calibration.\n\n'
                    f"    healthy 1168, {word.lower()} 212 - the floor is between\n"
                    f"    them. ANY FLOOR BELOW ~213 PASSES THE {word}. Calibrate.\n"
                    '    """\n'
                    "X = 400\n"
                )
            },
            0,
            1,
        ),
        (
            "the marker on a python code line fails",
            {"services/geometry/x.py": f"X = 0  # {word}: always 0\n"},
            1,
            1,
        ),
        (
            "a marker inside a python STRING is code, not prose",
            {"services/geometry/x.py": f'X = "{word}"\n'},
            1,
            1,
        ),
        (
            "a URL inside a TS string is not a comment",
            {"src/a.ts": 'export const u = "https://x/y";\nexport const v = 1;\n'},
            0,
            1,
        ),
        (
            "the marker inside a TS string literal fails",
            {"src/a.ts": f'export const u = "{word}";\n'},
            1,
            1,
        ),
        (
            "a `#` inside a shell parameter expansion is not a comment",
            {"scripts/a.sh": '#!/usr/bin/env bash\necho "${VAR#prefix}"\n'},
            0,
            1,
        ),
        (
            "the marker trailing a YAML value fails",
            {
                ".github/workflows/a.yml": (
                    f"jobs:\n  x:\n    timeout-minutes: 1 # {word}\n"
                )
            },
            1,
            1,
        ),
        (
            "a focused test fails, but only in a test file",
            {"apps/web/e2e/a.spec.ts": 'test.only("x", async () => {});\n'},
            1,
            1,
        ),
        (
            "`.only(` outside a test path is not this gate's business",
            {"src/query.ts": "export const q = builder.only(1);\n"},
            0,
            1,
        ),
        (
            "`.skip(` is legitimate and must NOT fail",
            {
                "services/geometry/tests/test_a.py": (
                    "import pytest\n\n\ndef test_a():\n"
                    '    pytest.skip("no server binaries")\n'
                ),
                "apps/web/e2e/a.spec.ts": (
                    'test.skip(browserName === "webkit", "flaky");\n'
                ),
            },
            0,
            1,
        ),
        (
            "a leftover `debugger;` fails",
            {"src/a.ts": "export function f() {\n  debugger;\n}\n"},
            1,
            1,
        ),
        (
            "a leftover breakpoint() fails",
            {"services/geometry/x.py": "def f():\n    breakpoint()\n"},
            1,
            1,
        ),
        (
            "`DO NOT COMMIT` trailing a code line fails",
            {"src/a.ts": "export const x = 0; // DO NOT COMMIT\n"},
            1,
            1,
        ),
        (
            "the exemption is ONE exact path: the same bytes elsewhere fail",
            {"scripts/copy-of-the-gate.py": f'PATTERN = "{word}"\n'},
            1,
            1,
        ),
    ]

    results: list[tuple[str, bool]] = []
    roots: dict[str, Path] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for label, files, expected, floor in cases:
            root = Path(tmp) / re.sub(r"[^a-z0-9]+", "-", label.lower())
            root.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            roots[label] = root
            actual = run(root, quiet=True, min_files=floor)
            ok = actual == expected
            results.append((label, ok))
            verdict = "ok  " if ok else "FAIL"
            print(f"  {verdict} {label} -> exit {actual} (want {expected})")

        # Negative controls on the two rules that do the ACQUITTING. Without
        # these, "prose passes" is indistinguishable from "the scanner never
        # looked", which is the shape of every gate this repo has shipped that
        # could not fail. Each one reverts exactly one decision and demands
        # that the corresponding acquittal turns into a conviction.
        real_rule = labels_code

        def always_labels(body: str, hit: re.Match[str]) -> bool:
            return True

        def drop_label_rule() -> None:
            globals()["labels_code"] = always_labels

        def restore_label_rule() -> None:
            globals()["labels_code"] = real_rule

        def scan_markdown_too() -> None:
            C_LIKE.add(".md")

        def stop_scanning_markdown() -> None:
            C_LIKE.discard(".md")

        controls: tuple[
            tuple[str, Callable[[], None], Callable[[], None], str], ...
        ] = (
            (
                "CONTROL: without the label rule, the .ts prose case convicts",
                drop_label_rule,
                restore_label_rule,
                "NEGATIVE CONTROL: measured prose about a mutant, in .ts",
            ),
            (
                "CONTROL: if .md were scanned, the markdown case convicts",
                scan_markdown_too,
                stop_scanning_markdown,
                "NEGATIVE CONTROL: the same line as prose in a .md",
            ),
        )
        for label, disable, restore, target_case in controls:
            disable()
            try:
                actual = run(roots[target_case], quiet=True, min_files=1)
            finally:
                restore()
            ok = actual == 1
            results.append((label, ok))
            print(f"  {'ok  ' if ok else 'FAIL'} {label} -> exit {actual} (want 1)")

    if len(results) < EXPECTED_CHECKS:
        print(
            f"\ncheck-mutation-markers: SELF-TEST RAN {len(results)} of "
            f"{EXPECTED_CHECKS} checks - the self-test lost coverage; it proves "
            "nothing."
        )
        return 1
    if all(ok for _, ok in results):
        print(
            f"\ncheck-mutation-markers: self-test passed - {len(results)} cases; "
            "the real defect fails, prose does not, and an empty scan cannot "
            "report clean."
        )
        return 0
    print("\ncheck-mutation-markers: SELF-TEST FAILED - this gate proves nothing.")
    return 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    if "--survey" in argv:
        return survey(REPO_ROOT)
    return run(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
