#!/usr/bin/env python3
"""DOCTICK-GATE — every commit that LANDS product behaviour ticks the board.

CLAUDE.md calls this NON-NEGOTIABLE: "Every commit that lands a feature/fix
MUST, in the same commit, update `docs/ROADMAP.md` and `docs/BACKLOG.md`."
Nothing checked it, so it was a preference, and it lost. Three independent
audit passes measured the same thing: pass 7 found ZERO of 11 feature/fix
commits touched either doc; pass 9 found 22 of the last 24. A rule with no
gate is a rule you are relying on people to keep under load, which is the one
condition in which they will not.

WHY IT DIES WITHOUT AN ESCAPE HATCH
-----------------------------------
The naive gate — "every commit must touch BACKLOG.md" — would fail almost
every builder commit we make, because the CURRENT, DELIBERATE protocol is that
one writer (the `backlog-groomer`) owns both shared docs per batch. Two classes
of writer on those two files is what produced the overwrite class that
`stage-doc-hunks.py`'s 900 lines exist to mitigate. So a gate without a
sanctioned "the groomer owns this one" answer is a gate that gets commented out
within a day, and we would be worse off than now: we would have spent the
credibility too.

The hatch is therefore a REQUIRED, ENUMERATED commit trailer:

    Doc-tick: groomer            the backlog-groomer reconciles the board for
                                 this batch (the parallel-builder path)
    Doc-tick: none — <reason>    no board entry applies; the reason is
                                 mandatory and free-text

That converts "silently forgot" into "explicitly deferred, by name, in the
permanent record". The gate counts both and prints the ratio on EVERY run (no
flag needed), so the run log — or `git log --grep='^Doc-tick: groomer'` —
answers "is the hatch load-bearing or is it a bypass?" with a number instead
of an opinion. That question is the whole point: a hatch nobody can count is
a hole. `--max-deferred-ratio` turns that number into a gate when an auditor
wants one.

WHAT BINDS AND WHAT DOES NOT — see `classify()`; each exemption carries its
one-line defence there, because an exemption whose reasoning is not written
down is the next person's bypass.

VACUITY
-------
Four gates have shipped in this repo that could not fail: a CI grep matching
its own prose, a unit test whose helper performed the cleanup it asserted, a
`self_test` returning 0 over zero checks because `all([])` is True, and a loop
that ran zero iterations. Two floors here, deliberately:

  * `EXPECTED_CHECKS` — `--self-test` refuses to report success if it ran
    fewer checks than it is supposed to have.
  * the range floor — enforcing mode over a range containing ZERO commits is
    exit 1, not "everything complies". That is the realistic CI failure:
    `actions/checkout` defaults to `fetch-depth: 1`, `github.event.before`
    then does not resolve, the range silently empties, and the job goes green
    forever while measuring nothing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Touching EITHER satisfies the tick. The standing rule names both, but in
#: practice one commit rarely has something true to say in both files, and a
#: gate that demands a ROADMAP edit for a one-line defect fix teaches people to
#: write filler into the roadmap — which is worse than a stale roadmap.
DOC_PATHS = ("docs/ROADMAP.md", "docs/BACKLOG.md")

#: Conventional-commit types that LAND BEHAVIOUR a user could notice. These
#: bind. Everything else is exempt only if it appears in `EXEMPT_TYPES` below —
#: an unrecognised type binds, so dropping the prefix is not a way out.
BOUND_TYPES = frozenset({"feat", "fix", "perf"})

#: Exempt types, each defended on one line in `classify()`. This list is the
#: ONLY way to be exempt by subject, which means bypassing the gate by
#: mislabelling requires writing a visible, greppable lie into the subject
#: line rather than merely forgetting.
EXEMPT_TYPES = frozenset(
    {
        "docs",
        "test",
        "refactor",
        "chore",
        "ci",
        "build",
        "style",
        "revert",
        "groom",
    }
)

PRODUCT_ROOTS = ("apps/", "services/", "packages/")

#: Generated, never hand-edited (CLAUDE.md "DRY"). A diff here is an OUTPUT of
#: a change, never its substance, so it cannot be the thing that lands.
GENERATED_PREFIXES = ("packages/contracts/", "packages/ts-client/")

TEST_DIR_NAMES = frozenset({"tests", "test", "e2e", "__tests__", "testdata"})
TEST_FILE_RE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")

SUBJECT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:\s")
TRAILER_RE = re.compile(r"^Doc-tick:\s*(?P<value>.+?)\s*$", re.MULTILINE)
#: `none` must be followed by a separator and a reason. Any dash-ish separator
#: is accepted because agents and humans type all of them (hyphen, en dash, em
#: dash, colon) and refusing on punctuation would be the gate at its most
#: annoying and least useful. Written as escapes because ruff's RUF001 rightly
#: objects to ambiguous dashes sitting literally in source strings.
NONE_WITH_REASON_RE = re.compile(
    "^none\\b\\s*[-\\u2013\\u2014:]\\s*(?P<reason>\\S.*)$", re.IGNORECASE
)

ZERO_SHA = "0" * 40

#: Above this, the auto-detected local range is not "the commits you are about
#: to push" — it is a stale ancestor ref, and reporting on it turns `just lint`
#: into a wall of other people's history.
LOCAL_RANGE_CAP = 25

REC_SEP = "\x1e"
FIELD_SEP = "\x1f"


# ── model ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Commit:
    sha: str
    parents: tuple[str, ...]
    message: str
    files: tuple[str, ...]

    @property
    def subject(self) -> str:
        return self.message.strip().splitlines()[0] if self.message.strip() else ""

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass
class Verdict:
    commit: Commit
    #: one of: ticked | deferred-groomer | deferred-none | exempt | VIOLATION
    outcome: str
    reason: str
    hatch_reason: str = ""

    @property
    def short(self) -> str:
        return self.commit.short

    @property
    def subject(self) -> str:
        return self.commit.subject


@dataclass
class Summary:
    verdicts: list[Verdict]

    def count(self, outcome: str) -> int:
        return sum(1 for v in self.verdicts if v.outcome == outcome)

    @property
    def examined(self) -> int:
        return len(self.verdicts)

    @property
    def bound(self) -> int:
        return self.examined - self.count("exempt")

    @property
    def deferred(self) -> int:
        return self.count("deferred-groomer") + self.count("deferred-none")

    @property
    def violations(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.outcome == "VIOLATION"]


# ── git ──────────────────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _rev_exists(repo: Path, rev: str) -> bool:
    if not rev or rev == ZERO_SHA:
        return False
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{rev}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def read_commits(repo: Path, rev_range: str) -> list[Commit]:
    """Every commit in `rev_range`, oldest first, with parents and file list.

    One `git log` for the whole range rather than three calls per commit: a
    pushed range can be 80 commits and this runs inside the fastest CI job.
    """
    fmt = f"{REC_SEP}%H%n%P%n{FIELD_SEP}%B{FIELD_SEP}"
    raw = _git(
        repo,
        "log",
        "--reverse",
        "--no-renames",
        "--name-only",
        f"--format={fmt}",
        rev_range,
        "--",
    )
    commits: list[Commit] = []
    for chunk in raw.split(REC_SEP):
        if not chunk.strip():
            continue
        head, message, tail = chunk.split(FIELD_SEP, 2)
        head_lines = head.strip().splitlines()
        sha = head_lines[0].strip()
        parents = tuple(head_lines[1].split()) if len(head_lines) > 1 else ()
        files = tuple(line for line in tail.splitlines() if line.strip())
        commits.append(Commit(sha=sha, parents=parents, message=message, files=files))
    return commits


def resolve_range(repo: Path, requested: str | None) -> tuple[str | None, str]:
    """Return `(range, note)`. `range is None` means "nothing to examine".

    Handles the two shapes CI actually produces. `github.event.before` is
    forty zeros on a branch's first push and unresolvable under a shallow
    checkout; both fall back to the head commit alone (`SHA^!`) rather than
    silently degrading to an empty range, which is the vacuous-green trap.
    """
    if requested:
        if ".." in requested:
            left, _, right = requested.partition("..")
            right = right or "HEAD"
            if _rev_exists(repo, left):
                return requested, ""
            if _rev_exists(repo, right):
                return (
                    f"{right}^!",
                    f"note: '{left}' does not resolve here (new branch or "
                    f"shallow clone) — examining {right[:7]} alone.",
                )
            return None, f"note: neither end of '{requested}' resolves."
        # `SHA^!` means "this commit alone" to git; strip the suffix before
        # asking whether the object exists, or every single-commit range looks
        # unresolvable and the gate fails for a reason that is not the rule.
        bare = requested[:-2] if requested.endswith("^!") else requested
        if _rev_exists(repo, bare):
            return f"{bare}^!", ""
        return None, f"note: '{requested}' does not resolve."

    return _default_local_range(repo)


def _default_local_range(repo: Path) -> tuple[str | None, str]:
    """The commits you are about to push, for the `just lint` warn-only pass.

    `@{upstream}` is the obvious answer and it is wrong for us: builders are
    REQUIRED to work in worktrees, whose branch (`worktree-agent-<id>`) has no
    upstream at all. So fall back to the nearest remote-tracking ref that is an
    ancestor of HEAD, which in a worktree is the `claude/*` branch it was
    seeded from — exactly the commits the agent has added.
    """
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return f"{proc.stdout.strip()}..HEAD", ""

    try:
        refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/")
    except RuntimeError:
        return None, "note: no remote-tracking refs; nothing to compare against."

    best: tuple[int, str] | None = None
    for ref in refs.split():
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ref, "HEAD"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        if ancestor.returncode != 0:
            continue
        try:
            count = int(_git(repo, "rev-list", "--count", f"{ref}..HEAD").strip())
        except (RuntimeError, ValueError):
            continue
        # NB count == 0 must WIN, not be skipped. Skipping it (the first cut of
        # this function) made a worktree sitting exactly on its remote tip fall
        # through to some OTHER, staler ancestor ref — measured at 172 commits
        # of other people's history, reported as "your unpushed work". A local
        # advisory that cries wolf 172 times is precisely the noise this gate
        # is supposed to avoid becoming.
        if best is None or count < best[0]:
            best = (count, ref)
    if best is None or best[0] == 0:
        return None, ""
    if best[0] > LOCAL_RANGE_CAP:
        return None, (
            f"note: {best[1]} is {best[0]} commits behind HEAD — too far to be "
            "'your unpushed work'. Pass --range explicitly if you meant it."
        )
    return f"{best[1]}..HEAD", f"note: comparing against {best[1]} (no upstream set)."


# ── classification ───────────────────────────────────────────────────────────


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    if TEST_DIR_NAMES & set(parts[:-1]):
        return True
    name = parts[-1]
    if name == "conftest.py":
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    return TEST_FILE_RE.search(name) is not None


def is_product_path(path: str) -> bool:
    if not path.startswith(PRODUCT_ROOTS):
        return False
    if path.startswith(GENERATED_PREFIXES):
        return False
    return not is_test_path(path)


def subject_type(subject: str) -> str | None:
    match = SUBJECT_RE.match(subject)
    return match.group("type").lower() if match else None


def read_trailer(message: str) -> str | None:
    matches = TRAILER_RE.findall(message)
    return matches[-1].strip() if matches else None


def classify(commit: Commit) -> Verdict:
    """Decide whether this commit owed the board a tick, and whether it paid.

    The classification, and the one-line defence of every exemption. Getting
    this wrong in the LOOSE direction makes the gate decorative; getting it
    wrong in the STRICT direction makes it noise people learn to route around,
    which is worse, because a disabled gate takes the rule's credibility with
    it.
    """
    # MERGE — exempt: it authors no change of its own; its content is the union
    # of parents that were each bound on their own commit, so demanding a tick
    # here records the same work twice and rewards nobody.
    if len(commit.parents) > 1:
        return Verdict(commit, "exempt", "merge commit (no authored change)")

    subject = commit.subject
    stype = subject_type(subject)

    # REVERT — exempt: the board entry it would write already exists (the entry
    # the reverted commit made); the honest record of a revert is the revert
    # itself, and forcing a tick invites a duplicate entry describing nothing.
    if (
        stype == "revert"
        or subject.startswith("Revert ")
        or "This reverts commit" in commit.message
    ):
        return Verdict(commit, "exempt", "revert")

    product = [p for p in commit.files if is_product_path(p)]

    # NO PRODUCT CODE — exempt: docs, workflows, scripts and the justfile change
    # nothing a user of the CAD tool can observe, so there is no shipped
    # behaviour for the board to record. This is also what lets the groomer's
    # own passes, and THIS gate's own commit, land without circular ceremony.
    if not product:
        return Verdict(commit, "exempt", "touches no product code")

    # TEST — exempt: hardening a spec changes evidence, not behaviour. Binding
    # it would make every flake fix a doc edit, which is the fastest way to
    # teach people to type the escape hatch by reflex. Note the path filter
    # already caught the common case: a `fix:` whose whole diff is specs has no
    # product files and exited above, so a mislabelled subject cannot smuggle
    # product code in under `test:` — only a genuinely mixed commit reaches
    # here, and mixing test hardening with a product fix is its own defect.
    if stype == "test":
        return Verdict(commit, "exempt", "test-only subject")

    # REFACTOR / CHORE / CI / BUILD / STYLE / DOCS — exempt: behaviour-preserving
    # by definition. If one of these DID change behaviour, the subject line is
    # the lie, and a lie in the permanent record is a reviewable defect in a way
    # that a forgotten doc edit never was.
    if stype in EXEMPT_TYPES:
        return Verdict(commit, "exempt", f"{stype}: (behaviour-preserving)")

    # Everything else binds: feat/fix/perf, AND any unrecognised type — because
    # if an unknown prefix were exempt, "drop the prefix" would be a silent
    # bypass and this gate would be back to being a preference.
    if stype is not None and stype not in BOUND_TYPES:  # pragma: no cover - guard
        raise AssertionError(f"unreachable: {stype} neither bound nor exempt")

    ticked = [p for p in commit.files if p in DOC_PATHS]
    if ticked:
        return Verdict(commit, "ticked", f"ticked {', '.join(sorted(ticked))}")

    trailer = read_trailer(commit.message)
    if trailer is None:
        return Verdict(commit, "VIOLATION", "no board tick and no `Doc-tick:` trailer")
    if trailer.lower() == "groomer":
        return Verdict(commit, "deferred-groomer", "deferred to the groomer", "groomer")
    none_match = NONE_WITH_REASON_RE.match(trailer)
    if none_match:
        return Verdict(
            commit,
            "deferred-none",
            "no board entry applies",
            none_match.group("reason"),
        )
    return Verdict(
        commit,
        "VIOLATION",
        f"`Doc-tick: {trailer}` is not a sanctioned value — use "
        "`groomer`, or `none — <reason>` with the reason spelled out",
    )


# ── reporting ────────────────────────────────────────────────────────────────

HELP = """
  Tick the board in THIS commit:
      git add docs/BACKLOG.md   (use scripts/stage-doc-hunks.py in a shared tree)
  …or declare the deferral, in the commit message, with one of:
      Doc-tick: groomer
      Doc-tick: none — <why no board entry applies>
"""


def report(summary: Summary, rev_range: str, note: str, *, verbose: bool) -> None:
    if note:
        print(note)
    print(f"doc-tick: {rev_range} — {summary.examined} commit(s) examined")

    if verbose:
        for v in summary.verdicts:
            mark = "FAIL" if v.outcome == "VIOLATION" else "ok  "
            print(f"  {mark} {v.short} {v.outcome:<17} {v.subject[:56]}")

    for v in summary.violations:
        print(f"\nFAIL {v.commit.short} {v.commit.subject}")
        product = [p for p in v.commit.files if is_product_path(p)]
        shown = ", ".join(product[:3]) + (" …" if len(product) > 3 else "")
        print(f"     landed product code ({len(product)} file(s): {shown})")
        print(f"     {v.reason}")

    print(
        f"\n  bound {summary.bound}"
        f" | ticked {summary.count('ticked')}"
        f" | deferred→groomer {summary.count('deferred-groomer')}"
        f" | deferred→none {summary.count('deferred-none')}"
        f" | exempt {summary.count('exempt')}"
        f" | violations {len(summary.violations)}"
    )
    if summary.bound:
        pct = 100.0 * summary.deferred / summary.bound
        print(f"  deferral ratio: {summary.deferred}/{summary.bound} = {pct:.0f}%")


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce CLAUDE.md's doc-tick rule over a commit range."
    )
    parser.add_argument(
        "--range",
        dest="rev_range",
        default=None,
        help="git revision range (e.g. $BEFORE..$SHA). Defaults to the commits "
        "you have not pushed yet.",
    )
    parser.add_argument(
        "--repo", default=str(REPO_ROOT), help="repository root (default: this repo)"
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="report violations but exit 0 (the local `just lint` posture: the "
        "commit you are about to write does not exist yet)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="permit a range with zero commits. CI must NEVER pass this: an "
        "empty range is how this gate would go vacuously green forever.",
    )
    parser.add_argument(
        "--max-deferred-ratio",
        type=float,
        default=None,
        help="fail if more than this fraction (0..1) of BOUND commits used the "
        "escape hatch. Off by default — the ratio is always printed; this "
        "arms it for an auditor asking whether the hatch has become the norm.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print a line per commit examined"
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    try:
        rev_range, note = resolve_range(repo, args.rev_range)
    except RuntimeError as exc:
        print(f"doc-tick: {exc}")
        return 1

    if rev_range is None:
        if args.warn_only:
            if note:
                print(f"doc-tick: skipped — {note}")
            return 0
        print(f"doc-tick: FAIL — no commit range to examine. {note}")
        print(HELP)
        return 1

    try:
        commits = read_commits(repo, rev_range)
    except RuntimeError as exc:
        print(f"doc-tick: {exc}")
        return 0 if args.warn_only else 1

    summary = Summary([classify(c) for c in commits])
    report(summary, rev_range, note, verbose=args.verbose)

    # COUNT FLOOR. "Every commit complies" over zero commits is not compliance,
    # it is a broken range — and it is the single most likely way this gate
    # rots, because the symptom is a fast green job.
    if summary.examined == 0 and not args.allow_empty:
        if args.warn_only:
            return 0
        print(
            "\ndoc-tick: FAIL — the range resolved to ZERO commits, so this "
            "gate measured nothing. That is a broken range (shallow checkout, "
            "unresolvable $BEFORE), not a pass. Pass --allow-empty only if you "
            "genuinely mean 'this push had no commits'."
        )
        return 1

    if summary.violations:
        print(HELP)
        if args.warn_only:
            print("doc-tick: warn-only — not failing your lint, but CI will.")
            return 0
        return 1

    if args.max_deferred_ratio is not None and summary.bound:
        ratio = summary.deferred / summary.bound
        if ratio > args.max_deferred_ratio:
            print(
                f"\ndoc-tick: FAIL — {ratio:.0%} of bound commits deferred, "
                f"ceiling is {args.max_deferred_ratio:.0%}. The escape hatch "
                "has become the norm; the board is not being reconciled."
            )
            return 0 if args.warn_only else 1

    print("doc-tick: OK")
    return 0


# ── self-test ────────────────────────────────────────────────────────────────
#
# A gate nobody has watched fail is not a gate. Four in this repo could not
# fail; two of them PRINTED "the gate can fail" while doing nothing. So this
# builds a throwaway repository containing the real failing case — an
# app-code diff, a `feat:` subject and no doc diff, the shape of the commits
# audit pass 7 counted — and DEMANDS exit 1, alongside every exemption the
# classification claims, so a future edit that loosens one is visible here.

#: How many checks `self_test` must run. The verdict below is
#: `all(ok for ok, _ in checks)` and `all([])` is True, so a check lost to a
#: refactor would silently remove coverage while still printing success — the
#: exact defect GATE-FLOOR filed against two neighbouring gates. `<`, not
#: `!=`: adding checks needs no edit here, only losing them is an error.
EXPECTED_CHECKS = 25


def self_test() -> int:
    import io
    import tempfile
    from contextlib import redirect_stdout

    checks: list[tuple[bool, str]] = []

    def sh(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
        import os

        full = {**os.environ, **(env or {})}
        subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, env=full
        )

    def write(repo: Path, path: str, text: str) -> None:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(repo: Path, message: str, files: dict[str, str]) -> str:
        for path, text in files.items():
            write(repo, path, text)
        sh(repo, "add", "-A")
        sh(
            repo,
            "commit",
            "-m",
            message,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )
        return _git(repo, "rev-parse", "HEAD").strip()

    def run(argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        sh(repo, "init", "-q", "-b", "main")
        sh(repo, "config", "user.email", "t@t")
        sh(repo, "config", "user.name", "t")
        base = commit(
            repo,
            "chore: seed",
            {
                "README.md": "seed\n",
                "docs/ROADMAP.md": "# roadmap\n",
                "docs/BACKLOG.md": "# backlog\n",
            },
        )

        def only(sha: str, *extra: str) -> tuple[int, str]:
            return run(["--repo", str(repo), "--range", f"{sha}^!", *extra])

        # (1) THE case, shaped like the commits audit pass 7 counted: product
        # code, `feat:` subject, no doc diff, no trailer.
        bad = commit(
            repo,
            "feat(web): a thing the user can see",
            {"apps/web/src/Thing.tsx": "export const a = 1;\n"},
        )
        code, out = only(bad)
        checks.append((code == 1, "feat: + product code + no tick -> exit 1"))
        checks.append(("no board tick" in out, "…and says why"))
        checks.append(("apps/web/src/Thing.tsx" in out, "…and names the product file"))

        # (2) The same commit with a tick passes — via BACKLOG…
        good_backlog = commit(
            repo,
            "feat(web): another thing",
            {
                "apps/web/src/Two.tsx": "export const b = 2;\n",
                "docs/BACKLOG.md": "# backlog\n- [x] two\n",
            },
        )
        checks.append((only(good_backlog)[0] == 0, "tick via BACKLOG.md -> exit 0"))

        # …and via ROADMAP alone, because either satisfies.
        good_roadmap = commit(
            repo,
            "fix(kernel): three",
            {
                "services/geometry/src/x.py": "X = 3\n",
                "docs/ROADMAP.md": "# roadmap\nthree\n",
            },
        )
        checks.append((only(good_roadmap)[0] == 0, "tick via ROADMAP.md alone -> 0"))

        # (3) The sanctioned hatch: the groomer owns the board this batch.
        deferred = commit(
            repo,
            "feat(web): four\n\nDoc-tick: groomer\n",
            {"apps/web/src/Four.tsx": "export const d = 4;\n"},
        )
        code_d, out_d = only(deferred)
        checks.append((code_d == 0, "`Doc-tick: groomer` -> exit 0"))
        checks.append(
            ("deferred→groomer 1" in out_d, "…and the deferral is COUNTED, not silent")
        )

        # (4) `none` without a reason is NOT a hatch — that is the silent bypass
        # the whole design is trying to avoid.
        bare_none = commit(
            repo,
            "feat(web): five\n\nDoc-tick: none\n",
            {"apps/web/src/Five.tsx": "export const e = 5;\n"},
        )
        code_n, out_n = only(bare_none)
        checks.append((code_n == 1, "`Doc-tick: none` with no reason -> exit 1"))
        checks.append(("not a sanctioned value" in out_n, "…and says the value is bad"))

        # …with a reason it passes, and the reason lives in the record forever.
        good_none = commit(
            repo,
            "feat(web): six\n\nDoc-tick: none — an unfiled hotfix, filed as SIX-1\n",
            {"apps/web/src/Six.tsx": "export const f = 6;\n"},
        )
        checks.append(
            (only(good_none)[0] == 0, "`Doc-tick: none - <reason>` -> exit 0")
        )

        # An invented value is refused rather than accepted as "some trailer".
        junk = commit(
            repo,
            "feat(web): seven\n\nDoc-tick: later\n",
            {"apps/web/src/Seven.tsx": "export const g = 7;\n"},
        )
        checks.append((only(junk)[0] == 1, "an unsanctioned trailer value -> exit 1"))

        # (5) Exemptions.
        docs_only = commit(repo, "docs(claude): a recipe", {"CLAUDE.md": "x\n"})
        checks.append((only(docs_only)[0] == 0, "docs-only commit -> exempt"))

        test_only = commit(
            repo,
            "test(web): harden a flaky wait",
            {"apps/web/e2e/thing.spec.ts": "// spec\n"},
        )
        checks.append((only(test_only)[0] == 0, "test-only paths -> exempt"))

        # A `fix:` whose entire diff is specs is test hardening wearing a fix
        # subject; the PATH filter catches it, not the subject.
        fix_specs = commit(
            repo,
            "fix(web): the spec asserted a pre-settle transient",
            {"apps/web/e2e/other.spec.ts": "// spec2\n"},
        )
        checks.append((only(fix_specs)[0] == 0, "fix: touching only specs -> exempt"))

        gen_only = commit(
            repo,
            "chore(contracts): regenerate",
            {"packages/ts-client/gateway/schema.ts": "export {};\n"},
        )
        checks.append((only(gen_only)[0] == 0, "generated packages only -> exempt"))

        reverted = commit(
            repo,
            "revert: feat(web): a thing\n\nThis reverts commit deadbee.\n",
            {"apps/web/src/Thing.tsx": "export const a = 0;\n"},
        )
        checks.append((only(reverted)[0] == 0, "a revert -> exempt"))

        # (6) THE ANTI-BYPASS: an unrecognised subject type still binds, so
        # dropping the conventional prefix is not a way out.
        sh(repo, "checkout", "-q", "-b", "side")
        noprefix = commit(
            repo,
            "make the button blue",
            {"apps/web/src/Blue.tsx": "export const h = 8;\n"},
        )
        checks.append((only(noprefix)[0] == 1, "unrecognised subject type -> exit 1"))

        # (7) A merge commit authors nothing of its own.
        sh(repo, "checkout", "-q", "main")
        sh(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")
        merge_sha = _git(repo, "rev-parse", "HEAD").strip()
        code_m, out_m = run(["--repo", str(repo), "--range", f"{merge_sha}^!"])
        checks.append((code_m == 0, "a merge commit -> exempt"))
        del out_m

        # (8) COUNT FLOOR: an empty range is a broken range, not compliance.
        code_e, out_e = run(["--repo", str(repo), "--range", "HEAD..HEAD"])
        checks.append((code_e == 1, "an EMPTY range -> exit 1 (count floor)"))
        checks.append(("ZERO commits" in out_e, "…and says the gate measured nothing"))
        empty_args = ["--repo", str(repo), "--range", "HEAD..HEAD"]
        code_ae, _ = run([*empty_args, "--allow-empty"])
        checks.append((code_ae == 0, "…unless --allow-empty is explicit"))

        # (9) warn-only reports the violation and still exits 0 (local posture).
        code_w, out_w = only(bad, "--warn-only")
        checks.append((code_w == 0, "--warn-only on a violation -> exit 0"))
        checks.append(("CI will" in out_w, "…but says CI will fail it"))

        # (10) The deferral ceiling an auditor can arm.
        code_r, out_r = run(
            [
                "--repo",
                str(repo),
                "--range",
                f"{base}..{merge_sha}",
                "--max-deferred-ratio",
                "0",
            ]
        )
        checks.append((code_r == 1, "--max-deferred-ratio 0 with a deferral -> exit 1"))
        checks.append(("deferral ratio" in out_r, "…and the ratio is always printed"))

    for ok, label in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if len(checks) < EXPECTED_CHECKS:
        print(
            f"\ncheck-doc-tick: SELF-TEST RAN {len(checks)} of {EXPECTED_CHECKS} "
            "checks — the self-test lost coverage; it proves nothing."
        )
        return 1
    if all(ok for ok, _ in checks):
        print(f"\ncheck-doc-tick: self-test passed ({len(checks)} checks) — it fails.")
        return 0
    print("\ncheck-doc-tick: SELF-TEST FAILED — this gate proves nothing.")
    return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
