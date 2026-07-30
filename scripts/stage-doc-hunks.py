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

    patch = "".join(header) + "".join(mine)
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
