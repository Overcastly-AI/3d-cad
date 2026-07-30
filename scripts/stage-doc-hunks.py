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


def run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=REPO_ROOT, input=stdin, capture_output=True, text=True
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

    Only valid when the hunk adds and never deletes — the caller enforces that.
    """
    lines = hunk.splitlines(keepends=True)
    m = HUNK_HEADER.match(lines[0])
    assert m, f"unparsable hunk header: {lines[0]!r}"
    old_line, new_line = int(m.group(1)), int(m.group(3))

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
    run_new_start = new_line
    run_old_anchor = old_line - 1
    for idx, ln in enumerate(lines[1:], start=1):
        if ln.startswith("+"):
            if owner.get(idx):
                if not run:
                    run_new_start, run_old_anchor = new_line, old_line - 1
                run.append(ln)
            elif run:
                out.append(
                    f"@@ -{run_old_anchor},0 +{run_new_start},{len(run)} @@\n"
                    + "".join(run)
                )
                run = []
            new_line += 1
        else:  # context line: advances both sides
            if run:
                out.append(
                    f"@@ -{run_old_anchor},0 +{run_new_start},{len(run)} @@\n"
                    + "".join(run)
                )
                run = []
            old_line += 1
            new_line += 1
    if run:
        out.append(
            f"@@ -{run_old_anchor},0 +{run_new_start},{len(run)} @@\n" + "".join(run)
        )
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


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    path, marker = sys.argv[1], sys.argv[2]

    diff = run(["git", "diff", "--", path]).stdout
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
    applied = run(["git", "apply", "--cached", "--unidiff-zero", "-"], stdin=patch)
    if applied.returncode != 0:
        print(f"stage-doc-hunks: patch did not apply.\n{applied.stderr}")
        return 3

    print(
        f"stage-doc-hunks: staged {len(mine)} hunk(s) of {path} matching {marker!r}; "
        f"left {theirs} hunk(s) unstaged for their author."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
