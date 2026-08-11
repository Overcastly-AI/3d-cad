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


#: A line that STARTS a new top-level entry in these docs. Used to detect a hunk
#: carrying more than one entry, which is the case marker-matching alone cannot
#: resolve.
#:
#: THE BOLD-LEAD ALTERNATIVE IS NOT DECORATION — it is docs/ROADMAP.md's entire
#: format, and leaving it out cost a colleague's entry on 2026-08-01. BACKLOG
#: entries are list items (`- [ ]`), so `[-*]\s` found their boundaries; ROADMAP
#: entries are bold-lead PARAGRAPHS (`**QA3-1 CLOSED (…) — …**`), which matched
#: nothing. Two adjacent ROADMAP entries therefore read as ONE contiguous run of
#: added lines with no detectable boundary, the marker made the whole run "mine",
#: and the tool staged 31 lines where 16 were mine — reporting "left 0 hunk(s)
#: unstaged for their author" while it did. Note `[-*]\s` cannot match `**bold`
#: anyway: `[-*]` takes the first star and `\s` then fails on the second.
#:
#: A list item, a heading or the attribution marker opens an entry wherever it
#: appears — nothing else in these docs starts a line that way.
ENTRY_START_ANYWHERE = re.compile(r"^\+(?:\s*[-*]\s|#{1,6}\s|>\s*ATTRIBUTION)")

#: A bold lead, which is ROADMAP's entry format AND an ordinary way to open a
#: sentence INSIDE an entry ("**94.8 %**, every answer naming the near face").
#: Treating it as an entry start unconditionally is the MIRROR of the defect
#: above: instead of MISSING a boundary it INVENTS one, splitting a single entry
#: in two. The marker then matches only the first half, the second half is
#: attributed to a colleague who does not exist, and `mine_only_subhunks` drops
#: it — so the tool truncates the author's OWN entry while reporting "left 0
#: hunk(s) unstaged for their author". Measured 2026-08-11 by the SEL-6 QA agent:
#: 7 lines staged of a 31-line ROADMAP entry, caught only because it read
#: `git diff --cached` in full. Hence the context rule in `entry_heads`: a bold
#: lead opens an entry only where an entry CAN begin — at the top of the run or
#: after a blank line. Both docs separate entries with a blank line, so this
#: keeps the ROADMAP fix the unconditional form was added for.
BOLD_LEAD = re.compile(r"^\+\s*\*\*")


def entry_heads(added: list[str]) -> list[bool]:
    """Which of *added* (in order) open a new entry — bold leads read IN CONTEXT.

    ONE derivation, used by attribution and by reporting alike, so "where an
    entry begins" cannot come to mean two different things in two places.
    """
    heads: list[bool] = []
    prev_blank = True  # the first added line can only be a beginning
    for ln in added:
        if ENTRY_START_ANYWHERE.match(ln):
            heads.append(True)
        elif BOLD_LEAD.match(ln):
            heads.append(prev_blank)
        else:
            heads.append(False)
        prev_blank = ln.strip() == "+"
    return heads


def added_lines(hunk: str) -> list[str]:
    return [
        ln
        for ln in hunk.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]


def foreign_entries(hunk: str, markers: list[str]) -> list[str]:
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
    added = added_lines(hunk)
    entries: list[tuple[str, list[str]]] = []
    for is_head, ln in zip(entry_heads(added), added, strict=True):
        if is_head or not entries:
            entries.append((ln, [ln]))
        else:
            entries[-1][1].append(ln)
    return [
        head
        for head, body in entries
        if not any(m in ln for ln in body for m in markers)
    ]


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def mine_only_subhunks(hunk: str, markers: list[str]) -> list[str]:
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
    # Same head derivation as foreign_entries, over the added lines in the same
    # order, so the two cannot disagree about where an entry starts.
    added_idx = [i for i, ln in enumerate(lines[1:], start=1) if ln.startswith("+")]
    head_of = dict(
        zip(added_idx, entry_heads([lines[i] for i in added_idx]), strict=True),
    )
    for idx, ln in enumerate(lines[1:], start=1):
        if not ln.startswith("+"):
            continue
        if head_of[idx] or not pending:
            for i in pending:
                owner[i] = current_is_mine
            pending, current_is_mine = [], any(m in ln for m in markers)
        else:
            current_is_mine = current_is_mine or any(m in ln for m in markers)
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


def hunk_adds_marker(hunk: str, markers: list[str]) -> bool:
    """True when a line this hunk ADDS contains *marker*.

    Deliberately ignores context and removed lines: a neighbouring agent's entry
    can easily appear as CONTEXT inside your hunk, and matching on that would
    re-introduce the very sweeping this script exists to prevent.
    """
    return any(
        ln.startswith("+") and not ln.startswith("+++") and m in ln
        for ln in hunk.splitlines()
        for m in markers
    )


def entry_count_by_blank_line(hunk: str) -> int:
    """A SECOND, independently-derived count of the entries a hunk adds.

    `ENTRY_START` recognises entries by how they begin, so it is blind to any
    format nobody has taught it — and being blind means silently merging two
    entries into one, which is how a colleague's ROADMAP paragraph got swept on
    2026-08-01 (the regex knew list items and headings, ROADMAP uses bold-lead
    paragraphs). Adding the missing alternative fixes that instance; it does
    nothing for the next format.

    This counts a different way — added lines separated by an added BLANK line —
    so the two disagree exactly when one of them has missed a boundary. It is not
    better than `ENTRY_START` and is not used for attribution; it is used to
    refuse when the two do not agree, because a disagreement means the tool
    cannot tell whose lines these are, and guessing is what does the damage.

    NB this is why `verify_staged` alone is not enough: that check compares the
    result against what attribution CLAIMED, so a wrong claim verifies happily.
    """
    count, in_entry = 0, False
    for ln in added_lines(hunk):
        if ln.strip() == "+":
            in_entry = False
        elif not in_entry:
            count, in_entry = count + 1, True
    return count


def verify_staged(
    path: str,
    filtered: list[str],
    matched: list[str],
    markers: list[str],
    baseline: str,
    cwd: Path | None,
) -> list[str]:
    """Post-condition on the INDEX: exactly my lines went in, none of theirs.

    Compares the blob `git commit` would use against *baseline* — the index as it
    was BEFORE this invocation, NOT against HEAD.

    That distinction is the whole bug fix. Using HEAD made the tool impossible to
    run twice on one file: the second invocation saw the FIRST run's correctly
    staged lines as "lines I never claimed" and refused, restoring the index and
    silently undoing run one. Two agents hit it on 2026-08-02, because a BACKLOG
    tick is genuinely two disjoint edits (the `- [ ]`->`- [x]` flip and the DONE
    note) and both worked around it by hand-building the blob — the fiddly path
    this tool exists to remove. Baselining on the pre-run index makes runs
    compose, which is what a staging tool has to do.

    Two failures are possible and both are silent without this:

      * a colleague's added line reached the index — the sweep, in any of the
        three shapes it has taken so far;
      * a line I claimed did NOT reach the index — the drop, which is what an
        over-eager entry boundary would cause.

    Counting occurrences rather than testing membership matters: these docs
    legitimately repeat short lines (a bare `\\n`, a `---`), so "is it present"
    would pass while a duplicate went missing.
    """
    from collections import Counter

    staged = run(["git", "show", f":{path}"], cwd=cwd).stdout
    gained = Counter(staged.splitlines()) - Counter(baseline.splitlines())

    claimed = Counter(
        ln[1:] for hunk in filtered for ln in added_lines(hunk)
    )  # what the emitted patch says it adds
    theirs = Counter(
        ln[1:]
        for hunk in matched
        for is_head, ln in zip(
            entry_heads(added_lines(hunk)), added_lines(hunk), strict=True
        )
        if is_head and not any(m in ln for m in markers)
    )  # entry-start lines that are definitely NOT mine

    problems: list[str] = []
    for line, n in (gained - claimed).items():
        problems.append(f"staged {n} line(s) I never claimed: {line.strip()[:90]!r}")
    for line, n in (claimed - gained).items():
        problems.append(f"failed to stage {n} of my line(s): {line.strip()[:90]!r}")
    for line in theirs:
        if gained[line]:
            problems.append(f"a colleague's entry reached the index: {line[:90]!r}")
    return problems


def stage(path: str, markers: list[str], cwd: Path | None = None) -> int:
    # The baseline for the post-condition is the index AS IT IS NOW, so repeated
    # invocations compose instead of each one accusing the last of foreign lines.
    baseline = run(["git", "show", f":{path}"], cwd=cwd).stdout
    diff = run(["git", "diff", "--", path], cwd=cwd).stdout
    if not diff.strip():
        print(f"stage-doc-hunks: {path} has no unstaged changes.")
        return 2

    header, hunks = split_hunks(diff)
    mine = [h for h in hunks if hunk_adds_marker(h, markers)]
    theirs = len(hunks) - len(mine)

    if not mine:
        print(
            f"stage-doc-hunks: no hunk in {path} ADDS a line containing any of\n"
            f"  {markers!r}.\n"
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
    disagree: list[str] = []
    filtered: list[str] = []
    for hunk in mine:
        seen = max(sum(entry_heads(added_lines(hunk))), 1)
        blanks = entry_count_by_blank_line(hunk)
        # BOTH DIRECTIONS, and the second one is not hypothetical. The original
        # check read `blanks > seen`, which catches ENTRY_START MISSING a
        # boundary (two entries read as one -> a colleague gets swept) and is
        # blind to it INVENTING one (one entry read as two -> the author's own
        # entry gets truncated). The blind direction shipped the 2026-08-11
        # defect: `seen=2, blanks=1`, so `1 > 2` was false and nothing fired.
        # A disagreement either way means the tool cannot tell whose lines these
        # are, and guessing is the whole failure mode — so refuse either way.
        if blanks != seen:
            disagree.append(
                f"{blanks} entries by blank-line separation, but {seen} "
                "recognised entry-start line(s)"
            )
            continue
        foreign = foreign_entries(hunk, markers)
        if not foreign:
            filtered.append(hunk)
            continue
        if any(
            ln.startswith("-") and not ln.startswith("---") for ln in hunk.splitlines()
        ):
            refuse.extend(foreign)
            continue
        filtered.extend(mine_only_subhunks(hunk, markers))

    if disagree:
        print(
            f"stage-doc-hunks: REFUSING — I cannot tell where the entries in "
            f"{path} begin, so I cannot tell which lines are yours:\n"
        )
        for line in disagree:
            print(f"  {line}")
        print(
            "\n  That gap is how a colleague's entry gets swept. Either the doc "
            "uses a\n  format ENTRY_START does not know (teach it, and add the "
            "shape to\n  --self-test), or your entry spans a blank line. Stage "
            "this one by hand."
        )
        return 6

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

    # Everything above is ATTRIBUTION, and attribution is a heuristic about
    # somebody else's prose — it will keep having edge cases (it has had three in
    # two days: hunk-granularity sweeping, a marker matching inside a colleague's
    # sentence, and ROADMAP's bold-lead paragraphs going unrecognised). So the
    # guard below is deliberately NOT another heuristic: whatever attribution
    # decided, verify the RESULT against it and undo on disagreement. That check
    # is format-independent and would have caught all three.
    before = run(["git", "ls-files", "-s", "--", path], cwd=cwd).stdout.strip()

    patch = "".join(header) + "".join(filtered)
    applied = run(
        ["git", "apply", "--cached", "--unidiff-zero", "-"], stdin=patch, cwd=cwd
    )
    if applied.returncode != 0:
        print(f"stage-doc-hunks: patch did not apply.\n{applied.stderr}")
        return 3

    problems = verify_staged(path, filtered, mine, markers, baseline, cwd)
    if problems:
        # Restore this path's index entry EXACTLY as we found it. Named path
        # only, and via the recorded blob rather than `git reset`, so a
        # colleague's staged work in other files is untouched.
        if before:
            meta, _, name = before.partition("\t")
            mode, sha, _stage = meta.split()
            run(
                ["git", "update-index", "--cacheinfo", f"{mode},{sha},{name or path}"],
                cwd=cwd,
            )
        print(
            f"stage-doc-hunks: REFUSING — the staged tree does not match what I "
            f"meant to stage, so I put {path}'s index entry back:\n"
        )
        for problem in problems:
            print(f"  {problem}")
        print(
            "\n  Attribution got this file wrong. Stage it by hand, and tell "
            "whoever owns the tool what the two entries looked like."
        )
        return 5

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
        for is_head, ln in zip(
            entry_heads(added_lines(hunk)), added_lines(hunk), strict=True
        )
        if is_head
    ]
    print(
        f"stage-doc-hunks: staged {len(mine)} hunk(s) of {path} matching {markers!r}; "
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


#: docs/ROADMAP.md's shape, which the list-item fixture above does NOT exercise:
#: bold-lead PARAGRAPHS, a colleague's directly above mine, separated by one
#: blank line. This is the case that shipped a sweep on 2026-08-01 while the
#: BACKLOG-shaped self-test passed — a fixture in the wrong format is a gate that
#: cannot fail for the reason you care about.
_ROADMAP_BASE = """# Roadmap

Status legend.

**An older entry that was already here.** Its second line of prose.
"""

_ROADMAP_DIRTY = _ROADMAP_BASE.replace(
    "**An older entry",
    "**THEIR ENTRY (2026-08-01, colleague) — a headline that\n"
    "wraps onto a second line.** Their body prose, which continues\n"
    "for a third line as these entries do.\n"
    "\n"
    "**MY ROADMAP ENTRY marker-phrase — my headline, also\n"
    "wrapped.** My body prose here.\n"
    "\n"
    "**An older entry",
)

_ROADMAP_EXPECTED = _ROADMAP_BASE.replace(
    "**An older entry",
    "**MY ROADMAP ENTRY marker-phrase — my headline, also\n"
    "wrapped.** My body prose here.\n"
    "\n"
    "**An older entry",
)


#: THE MIRROR SHAPE: my entry contains a CONTINUATION line that opens with a
#: bold run — "**94.8 %**, every answer…" — which is how anyone writes a measured
#: result, and is what a QA agent actually wrote on 2026-08-11. An unconditional
#: `\*\*` entry-start reads that line as a second entry, the marker matches only
#: the text above it, and everything from there down is dropped as "somebody
#: else's" — 7 lines staged of 31, reported as a clean run.
#:
#: The colleague's entry is here too so the case proves BOTH properties at once:
#: my entry must arrive WHOLE, and theirs must still not be swept.
_CONT_BASE = """# Roadmap

Status legend.

**An older entry that was already here.** Its second line of prose.
"""

_CONT_MINE = (
    "**MY ROADMAP ENTRY marker-phrase — the headline.** Body prose\n"
    "that runs on for a line.\n"
    "**94.8 %** of points answered, every one of them naming the near\n"
    "face — the continuation line that used to end the entry early.\n"
    "**Mutation-verified**: reverting the fix turns this red.\n"
)

_CONT_DIRTY = _CONT_BASE.replace(
    "**An older entry",
    "**THEIR ENTRY (colleague) — a headline.** Their body prose,\n"
    "which continues for a second line.\n"
    "\n" + _CONT_MINE + "\n**An older entry",
)

_CONT_EXPECTED = _CONT_BASE.replace(
    "**An older entry",
    _CONT_MINE + "\n**An older entry",
)


def _case(
    name: str, doc_name: str, base: str, dirty: str, expected: str, marker: str
) -> list[tuple[bool, str]]:
    """Run one staging scenario in a throwaway repo; return (ok, label) checks."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        doc = repo / doc_name
        for args in (
            ["git", "init", "-q", "."],
            ["git", "config", "user.email", "self-test@loft.invalid"],
            ["git", "config", "user.name", "self-test"],
        ):
            run(args, cwd=repo)
        doc.write_text(base)
        run(["git", "add", doc_name], cwd=repo)
        run(["git", "commit", "-qm", "base"], cwd=repo)

        doc.write_text(dirty)
        code = stage(doc_name, [marker], cwd=repo)
        staged = run(["git", "show", f":{doc_name}"], cwd=repo).stdout
        working = doc.read_text()

    theirs = "THEIR ENTRY" if "THEIR ENTRY" in dirty else "SIBLING IN-FLIGHT"
    checks = [
        (code == 0, f"{name}: exits 0"),
        (staged == expected, f"{name}: the staged tree is EXACTLY my entry, in place"),
        (theirs not in staged, f"{name}: the colleague's entry is NOT staged"),
        (theirs in working, f"{name}: the colleague's entry survives for them"),
    ]
    if staged != expected:
        print("\n--- staged ---")
        print(staged)
        print("--- expected ---")
        print(expected)
    return checks


def _twice_case() -> list[tuple[bool, str]]:
    """Two invocations on ONE file must COMPOSE, not undo each other.

    The real shape: a BACKLOG tick is two disjoint edits — the `- [ ]`->`- [x]`
    flip and an appended DONE note — so an agent naturally runs the tool twice.
    Before 2026-08-02 the post-condition baselined on HEAD, so run two saw run
    one's correctly staged lines as "lines I never claimed", refused, and
    restored the index — silently undoing run one while reporting a refusal for
    a file that was fine. Two agents hit it in one night and both hand-built the
    blob instead, which is exactly the fiddly path this tool exists to delete.
    """
    import tempfile

    base = (
        "# Board\n\n- [ ] (P1) **ITEM-A alpha.** Body.\n\n"
        "- [ ] (P1) **ITEM-B beta.** Body.\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        doc = repo / "BACKLOG.md"
        for args in (
            ["git", "init", "-q", "."],
            ["git", "config", "user.email", "self-test@loft.invalid"],
            ["git", "config", "user.name", "self-test"],
        ):
            run(args, cwd=repo)
        doc.write_text(base)
        run(["git", "add", "BACKLOG.md"], cwd=repo)
        run(["git", "commit", "-qm", "base"], cwd=repo)

        # Two appended entries, staged one marker at a time.
        doc.write_text(
            base
            + "\n- [x] (P1) **ITEM-C gamma.** Done.\n\n"
            + "- [x] (P1) **ITEM-D delta.** Done.\n"
        )
        first = stage("BACKLOG.md", ["ITEM-C gamma"], cwd=repo)
        after_first = run(["git", "show", ":BACKLOG.md"], cwd=repo).stdout
        second = stage("BACKLOG.md", ["ITEM-D delta"], cwd=repo)
        staged = run(["git", "show", ":BACKLOG.md"], cwd=repo).stdout

    return [
        (first == 0, "twice: first invocation stages"),
        (
            "ITEM-C gamma" in after_first,
            "twice: first invocation's entry is in the index",
        ),
        (second == 0, "twice: SECOND invocation stages instead of refusing"),
        ("ITEM-C gamma" in staged, "twice: run one's entry SURVIVES run two"),
        ("ITEM-D delta" in staged, "twice: run two's entry is there too"),
    ]


def self_test() -> int:
    """Stage a hunk shared with a colleague and demand the INDEX be exactly right.

    This tool had no self-test until 2026-08-01, which is precisely how it shipped
    a defect that RELOCATED the author's own entry to the end of the file while
    printing success. Asserting the exit code would not have caught it — only
    reading the resulting tree does, so this compares `git show :FILE`
    byte-for-byte.

    THREE fixtures, because each was added the day the tool failed for a shape
    the previous fixtures could not express:

      backlog            list items — the original.
      roadmap            bold-lead PARAGRAPHS. Added 2026-08-01 after the
                         BACKLOG-only self-test passed while the tool swept a
                         colleague's ROADMAP entry hours later.
      bold-continuation  a bold run OPENING A LINE INSIDE my own entry. Added
                         2026-08-11 after the tool staged 7 lines of a 31-line
                         entry and called it clean.

    The two ROADMAP cases pull in opposite directions and that is the point: one
    fails if a boundary is MISSED, the other if a boundary is INVENTED. A fixture
    in the wrong shape is a gate that cannot fail for the reason you care about.

    NEGATIVE CONTROLS — each was RUN, and what each actually does is written
    down here rather than what it was expected to do:

      * bold lead unconditional (`heads.append(True)` in `entry_heads`)
        -> bold-continuation REFUSES: "2 entries by blank-line separation, but
        4 recognised entry-start line(s)". Loud, so nothing is lost.
      * the same, PLUS the cross-check reverted to `blanks > seen`
        -> bold-continuation EXITS 0, leaves the colleague alone, and stages a
        truncated entry. The shipped 2026-08-11 defect, reproduced exactly —
        and note only the byte-for-byte tree check catches it. An exit-code
        assertion passes here, which is why this self-test compares the tree.
      * bold NEVER a head (`heads.append(False)`, the pre-2026-08-01 blindness)
        -> roadmap AND bold-continuation both refuse. Worth stating plainly:
        that shape used to SWEEP a colleague silently, and it no longer can,
        because the cross-check now fires in the missed-boundary direction even
        when the regex is blind. The regex got the case right; the cross-check
        is what makes being wrong survivable.
    """
    checks = (
        _case(
            "backlog",
            "BACKLOG.md",
            _SELF_TEST_BASE,
            _SELF_TEST_DIRTY,
            _SELF_TEST_EXPECTED,
            "MY NEW ENTRY marker-phrase",
        )
        + _case(
            "roadmap",
            "ROADMAP.md",
            _ROADMAP_BASE,
            _ROADMAP_DIRTY,
            _ROADMAP_EXPECTED,
            "MY ROADMAP ENTRY marker-phrase",
        )
        + _case(
            "bold-continuation",
            "ROADMAP.md",
            _CONT_BASE,
            _CONT_DIRTY,
            _CONT_EXPECTED,
            "MY ROADMAP ENTRY marker-phrase",
        )
        + _twice_case()
    )

    for ok, label in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if all(ok for ok, _ in checks):
        print("\nstage-doc-hunks: self-test passed.")
        return 0
    print("\nstage-doc-hunks: SELF-TEST FAILED — do not stage shared docs with this.")
    return 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    # MULTIPLE markers are allowed and are the right answer for a BACKLOG tick,
    # which is two disjoint edits (the `- [ ]`->`- [x]` flip and the DONE note).
    return stage(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
