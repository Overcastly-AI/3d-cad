#!/usr/bin/env python3
"""Stage only YOUR hunks of a shared doc, leaving other agents' text alone.

    python3 scripts/stage-doc-hunks.py docs/BACKLOG.md "#57 — MASS PROPERTIES"

Why this exists. `docs/ROADMAP.md` and `docs/BACKLOG.md` are the two files EVERY
agent is required to touch in the same commit as its work, so they are nearly
always dirty with somebody else's in-flight text. `git add docs/BACKLOG.md` then
silently captures it, and the result is a commit whose message describes none of
its own contents and whose git authorship is wrong. Nothing is lost, which is
exactly why it goes unnoticed.

CLAUDE.md has carried a rule against this since the first occurrence. It happened
again the same day, by the same person who wrote the rule, because the correct
path (`git add -p`, or hand-rolling a filtered `git apply --cached`) is fiddly and
the wrong path is four words. A rule that loses to convenience under load is not a
control. So: this makes the correct path one command.

It stages a hunk only when one of the lines that hunk ADDS contains *marker* —
pick something unmistakably yours, like the item id you just wrote. Everything
else stays unstaged and untouched in the working tree, ready for its author.

Exit codes: 0 staged something, 2 nothing matched (likely a wrong marker — better
to fail than to stage nothing and let you commit an empty doc change believing it
worked), 3 the patch would not apply.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(
    args: list[str], stdin: str | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd or REPO_ROOT, input=stdin, capture_output=True, text=True
    )


def split_hunks(diff: str) -> tuple[list[str], list[str]]:
    """Split a unified diff into (header_lines, hunk_blocks)."""
    lines = diff.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("@@")), len(lines))
    header: list[str] = lines[:start]
    hunks: list[str] = []
    current: list[str] = []
    for ln in lines[start:]:
        if ln.startswith("@@"):
            if current:
                hunks.append("".join(current))
            current = [ln]
        else:
            current.append(ln)
    if current:
        hunks.append("".join(current))
    return header, hunks


#: A line that STARTS a new top-level entry in these docs — a list item or a
#: heading. Used to detect a hunk carrying more than one entry, which is the
#: case marker-matching alone cannot resolve.
ENTRY_START = re.compile(r"^\+(?:\s*[-*]\s|#{1,6}\s|>\s*ATTRIBUTION)")


def added_lines(hunk: str) -> list[str]:
    return [
        ln
        for ln in hunk.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]


def foreign_entries(hunk: str, marker: str) -> list[str]:
    """Entry-start lines in *hunk* that are NOT part of the marker's own entry.

    Marker-matching works at HUNK granularity, but git merges ADJACENT changed
    lines into one hunk — so when another agent's entry happens to sit directly
    above or below yours, both ride in on the same hunk and the marker match
    stages theirs too. That is not hypothetical: it happened on 2026-07-30, and
    the tool reported "left 1 hunk(s) unstaged for their author" while doing it,
    which is worse than failing.

    The diff alone cannot tell whose line is whose, so this does not guess. It
    finds where each ENTRY starts, attributes every added line to the entry it
    falls under, and returns the entries that never mention the marker. If that
    list is non-empty the caller must refuse: staging is all-or-nothing per hunk,
    so there is no correct automatic answer, only a visible failure or a silent
    sweep.
    """
    entries: list[tuple[str, list[str]]] = []
    for ln in added_lines(hunk):
        if ENTRY_START.match(ln) or not entries:
            entries.append((ln, [ln]))
        else:
            entries[-1][1].append(ln)
    return [head for head, body in entries if not any(marker in ln for ln in body)]


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def mine_only_subhunks(hunk: str, marker: str) -> list[str]:
    """Rebuild an insert-only *hunk* as sub-hunks carrying only YOUR entry.

    Emitted in `--unidiff-zero` form (`@@ -a,0 +b,n @@`), which is why the caller
    passes that flag: each sub-hunk inserts after old-file line *a* and needs no
    surrounding context, so a colleague's added lines simply do not appear in the
    patch and stay in the working tree for them.

    THE NEW-SIDE NUMBER IS DERIVED, NOT COUNTED, and that is the whole subtlety.
    The first version counted `b` by walking the working-tree diff, which numbers
    the new side of a file that contains the colleague's lines too. The patch we
    emit does NOT contain them, so every sub-hunk after a dropped foreign line
    carried a `b` too large by exactly the number of lines dropped, and
    `git apply` placed the insertion somewhere else in the file — while the tool
    printed success. Measured 2026-08-01 (dogfooding pass #3 hit it for real): a
    sibling's in-flight entry sitting directly above mine produced `@@ -5,0 +9,3`
    where `+6` was correct, and the staged tree carried my entry at the END of the
    file, after an unrelated item, with its blank-line separator gone. The
    colleague's text was correctly left alone; MY text was silently relocated.

    So `b` is computed from the old-side anchor plus only the lines this patch
    actually emits — `run_old_anchor + 1 + emitted` — which cannot drift from
    what the patch contains because it is a function of it.

    Only valid when the hunk adds and never deletes — the caller enforces that.
    """
    lines = hunk.splitlines(keepends=True)
    m = HUNK_HEADER.match(lines[0])
    assert m, f"unparsable hunk header: {lines[0]!r}"
    old_line = int(m.group(1))

    # Attribute each added line to its entry, exactly as foreign_entries does,
    # so "mine" means the same thing in both places.
    owner: dict[int, bool] = {}
    current_is_mine = False
    pending: list[int] = []
    for idx, ln in enumerate(lines[1:], start=1):
        if not ln.startswith("+"):
            continue
        if ENTRY_START.match(ln) or not pending:
            for i in pending:
                owner[i] = current_is_mine
            pending, current_is_mine = [], marker in ln
        else:
            current_is_mine = current_is_mine or marker in ln
        pending.append(idx)
    for i in pending:
        owner[i] = current_is_mine

    out: list[str] = []
    run: list[str] = []
    run_old_anchor = old_line - 1
    emitted = 0  # lines this patch has already inserted, ahead of the current run

    def flush() -> None:
        nonlocal run, emitted
        if not run:
            return
        # `+ b` is where these lines land in the file this patch PRODUCES: after
        # old-file line `run_old_anchor`, shifted by whatever we inserted earlier.
        out.append(
            f"@@ -{run_old_anchor},0 +{run_old_anchor + 1 + emitted},{len(run)} @@\n"
            + "".join(run)
        )
        emitted += len(run)
        run = []

    for idx, ln in enumerate(lines[1:], start=1):
        if ln.startswith("+"):
            if owner.get(idx):
                if not run:
                    run_old_anchor = old_line - 1
                run.append(ln)
            else:
                # A colleague's line: dropped from the patch entirely, so it must
                # NOT advance the new-side count. Advancing here was the bug.
                flush()
        else:  # context line: advances the old side only (we emit no context)
            flush()
            old_line += 1
    flush()
    return out


def hunk_adds_marker(hunk: str, marker: str) -> bool:
    """True when a line this hunk ADDS contains *marker*.

    Deliberately ignores context and removed lines: a neighbouring agent's entry
    can easily appear as CONTEXT inside your hunk, and matching on that would
    re-introduce the very sweeping this script exists to prevent.
    """
    return any(
        ln.startswith("+") and not ln.startswith("+++") and marker in ln
        for ln in hunk.splitlines()
    )


def stage(path: str, marker: str, cwd: Path | None = None) -> int:
    diff = run(["git", "diff", "--", path], cwd=cwd).stdout
    if not diff.strip():
        print(f"stage-doc-hunks: {path} has no unstaged changes.")
        return 2

    header, hunks = split_hunks(diff)
    mine = [h for h in hunks if hunk_adds_marker(h, marker)]
    theirs = len(hunks) - len(mine)

    if not mine:
        print(
            f"stage-doc-hunks: no hunk in {path} ADDS a line containing {marker!r}.\n"
            f"  {len(hunks)} hunk(s) present. Check the marker — staging nothing "
            "silently would be worse than failing."
        )
        return 2

    # A matched hunk often ALSO carries a colleague's entry, because git merges
    # changes within its context window into one hunk — a blank line between two
    # appended entries is NOT enough to separate them (measured). Marker-matching
    # at hunk granularity therefore sweeps their work while reporting success.
    #
    # So filter at LINE granularity instead of refusing: rebuild each matched
    # hunk as insert-only sub-hunks containing just the marker's own entry. This
    # is exact for the append case these docs actually see. A hunk that also
    # DELETES lines is not an append, so there is no safe automatic answer and it
    # is refused by name rather than guessed at.
    refuse: list[str] = []
    filtered: list[str] = []
    for hunk in mine:
        foreign = foreign_entries(hunk, marker)
        if not foreign:
            filtered.append(hunk)
            continue
        if any(
            ln.startswith("-") and not ln.startswith("---") for ln in hunk.splitlines()
        ):
            refuse.extend(foreign)
            continue
        filtered.extend(mine_only_subhunks(hunk, marker))

    if refuse:
        print(
            f"stage-doc-hunks: REFUSING — a matched hunk in {path} both DELETES "
            "lines and adds entries that are not yours, so it cannot be split "
            "safely:\n"
        )
        for head in refuse:
            print(f"  not yours: {head.rstrip()}")
        print("\n  Stage this one by hand.")
        return 4

    patch = "".join(header) + "".join(filtered)
    applied = run(
        ["git", "apply", "--cached", "--unidiff-zero", "-"], stdin=patch, cwd=cwd
    )
    if applied.returncode != 0:
        print(f"stage-doc-hunks: patch did not apply.\n{applied.stderr}")
        return 3

    # NAME WHAT WAS STAGED, don't just count it. A count cannot show you that the
    # marker landed inside a colleague's prose — which is exactly how "OPS-1"
    # swept an OBS-1 entry whose text read "the same shape as OPS-1"
    # (2026-07-31). The tool did what it was told; the marker was the defect, and
    # a count of "1 hunk" looked perfectly correct while it happened. Printing
    # the entry-start line of every staged entry makes the sweep visible in the
    # one place the author is already looking.
    staged_entries = [
        ln.rstrip()
        for hunk in filtered
        for ln in added_lines(hunk)
        if ENTRY_START.match(ln)
    ]
    print(
        f"stage-doc-hunks: staged {len(mine)} hunk(s) of {path} matching {marker!r}; "
        f"left {theirs} hunk(s) unstaged for their author."
    )
    if staged_entries:
        print("  entries staged — CHECK EVERY ONE OF THESE IS YOURS:")
        for head in staged_entries:
            print(f"    {head}")
    return 0


#: The exact shape that broke it: a colleague's in-flight entry directly ABOVE
#: mine, both uncommitted, with an unrelated entry below. Git merges all of it
#: into one hunk, so the emitted patch drops the colleague's lines — and every
#: new-side line number after them used to be wrong.
_SELF_TEST_BASE = """## Later (P3)

- [ ] (P3, S) **Their existing item.** Some text on the
      second line of their entry, and a third line here.

- [ ] (P3, S) **Another older item.** Body text.
"""

_SELF_TEST_MINE = """      and my second line of body text.
"""

_SELF_TEST_DIRTY = _SELF_TEST_BASE.replace(
    "- [ ] (P3, S) **Another older item.**",
    "- [ ] (P3, S) **SIBLING IN-FLIGHT entry.** Sibling body line one\n"
    "      and sibling body line two.\n"
    "\n"
    "- [x] (P3, XS) **MY NEW ENTRY marker-phrase.** My first line of body\n"
    "" + _SELF_TEST_MINE + "\n"
    "- [ ] (P3, S) **Another older item.**",
)

#: What the INDEX must contain afterwards: my entry in its right place, the
#: colleague's entry absent (still theirs, in the working tree).
_SELF_TEST_EXPECTED = _SELF_TEST_BASE.replace(
    "- [ ] (P3, S) **Another older item.**",
    "- [x] (P3, XS) **MY NEW ENTRY marker-phrase.** My first line of body\n"
    "" + _SELF_TEST_MINE + "\n"
    "- [ ] (P3, S) **Another older item.**",
)


def self_test() -> int:
    """Stage a hunk shared with a colleague and demand the INDEX be exactly right.

    This tool had no self-test until 2026-08-01, which is precisely how it
    shipped a defect that RELOCATED the author's own entry to the end of the file
    while printing success. Asserting the exit code would not have caught it —
    only reading the resulting tree does. So this compares `git show :FILE`
    byte-for-byte, and separately demands the colleague's line never entered the
    index and never left the working tree.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        doc = repo / "BACKLOG.md"
        for args in (
            ["git", "init", "-q", "."],
            ["git", "config", "user.email", "self-test@loft.invalid"],
            ["git", "config", "user.name", "self-test"],
        ):
            run(args, cwd=repo)
        doc.write_text(_SELF_TEST_BASE)
        run(["git", "add", "BACKLOG.md"], cwd=repo)
        run(["git", "commit", "-qm", "base"], cwd=repo)

        doc.write_text(_SELF_TEST_DIRTY)
        code = stage("BACKLOG.md", "MY NEW ENTRY marker-phrase", cwd=repo)
        staged = run(["git", "show", ":BACKLOG.md"], cwd=repo).stdout

        ok_exit = code == 0
        ok_tree = staged == _SELF_TEST_EXPECTED
        ok_theirs = "SIBLING IN-FLIGHT" not in staged
        ok_kept = "SIBLING IN-FLIGHT" in doc.read_text()

    print(f"  {'ok  ' if ok_exit else 'FAIL'} staging a shared hunk exits 0")
    print(
        f"  {'ok  ' if ok_tree else 'FAIL'} the staged tree places my entry EXACTLY "
        "where I wrote it"
    )
    print(f"  {'ok  ' if ok_theirs else 'FAIL'} the colleague's entry is NOT staged")
    print(
        f"  {'ok  ' if ok_kept else 'FAIL'} the colleague's entry survives in the "
        "working tree"
    )
    if not ok_tree:
        print("\n--- staged ---")
        print(staged)
        print("--- expected ---")
        print(_SELF_TEST_EXPECTED)
    if ok_exit and ok_tree and ok_theirs and ok_kept:
        print("\nstage-doc-hunks: self-test passed.")
        return 0
    print("\nstage-doc-hunks: SELF-TEST FAILED — do not stage shared docs with this.")
    return 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    return stage(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
