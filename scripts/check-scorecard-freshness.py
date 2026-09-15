#!/usr/bin/env python3
"""Scorecard freshness — has anything touched a row's territory since it was scored?

``docs/VISION.md``'s daily-driver scorecard is the document that directs
prioritisation, and on 2026-09-15 a vision-steward pass found it rotting in a
specific, repeatable way:

* **Assemblies & mates** read ❌ for **19 days** on the strength of one named
  blocker (MATE-1, "blocks the entire Assemblies pillar"). MATE-1 closed five
  days after the flip (`a2a6f9f`), nobody re-ran the citation, and the stale ❌
  was used as live evidence in a founder-facing "you cannot build a machine"
  claim before the correction caught it.
* **Sheet metal** was a second, independently-found instance of the *identical*
  failure — flipped ❌ on the same date on three P0s (DXF-4, DXF-5,
  EDGEFLANGE-1), all three closed in source shortly after, never re-scored.

Two for two. **An audit pass that flips rows DOWN creates debt that nothing
tracks**, and the reasoning in each cell makes the row *look* current, which is
worse than a table with no reasoning at all.

This gate asks the one question that went unasked for 19 days, mechanically:
**"did anything land in this row's territory after the commit it cites?"** For
every scorecard row it reads the ``Re-derived <date> @ <sha>`` marker, maps the
row to its territory paths, takes ``git log -1`` over those paths, and reports
STALE when that commit is not an ancestor of the cited sha.

It cannot tell you whether a verdict is still CORRECT — only a human
re-derivation does that. It turns "stale for 19 days, unnoticed" into "flagged
the same day", which is the whole ask.

**Both tables are parsed out of ``docs/VISION.md``** — the scorecard and the
Dimension→territory map that ships beside it in the "Freshness discipline"
section. A territory list hardcoded here would be a second source of truth that
silently drifts from the doc every agent actually reads, which is the same
defect class one level up.

Exit codes: ``0`` all rows fresh or PENDING · ``1`` at least one row STALE, or
missing its marker, or citing a sha that does not resolve · ``2`` REFUSED, the
check examined too little to be evidence.

**Print-only by default where it is wired.** ``just lint`` runs it
``--warn-only`` (always exit 0) and CI does not run it at all: staleness is a
prompt to re-derive, not proof a verdict is wrong, and a hard doc-vs-code timing
gate would block unrelated commits and get muted — a muted gate protects
nothing. The ``--self-test`` IS hard, exactly like its five neighbours in
``just lint``.

Intended callers:

* ``doc-syncer`` — every iteration, prints the STALE/FRESH table with its
  normal output;
* ``vision-steward`` — the FIRST step of an audit cycle, so "which rows might
  need a look" is a computed list rather than guesswork.

Stdlib + ``git``, no daemon, no network::

    python3 scripts/check-scorecard-freshness.py --self-test
    python3 scripts/check-scorecard-freshness.py
    python3 scripts/check-scorecard-freshness.py --warn-only
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VISION = Path("docs/VISION.md")

#: `Re-derived 2026-09-15 @ `21a039f`` — the date is required as well as the
#: sha, because a sha alone does not tell a reader how old the judgement is and
#: the doc mandates both.
CITATION = re.compile(
    r"Re-derived\s+(?P<date>\d{4}-\d{2}-\d{2})\s*@\s*`(?P<sha>[0-9a-f]{7,40})`",
    re.IGNORECASE,
)
#: The first bolded run in a Notes cell — the doc requires every cell to OPEN
#: with its marker, so this is where a PENDING declaration has to be.
LEAD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

#: Floors, measured against `docs/VISION.md` at the commit this landed on
#: (13 scorecard rows, 9 territory entries, 10 rows that map to a territory).
#: Set below the real numbers so ordinary churn never trips them, and far
#: enough above zero that a parser which stops matching REFUSES instead of
#: reporting a clean sweep of nothing. That is not hypothetical here:
#: `check-build-context.py` printed `0 COPY source(s) reach the build context`
#: and exited 0 while standing in for an unreachable `docker build`, and
#: `check-tailwind-scale.py` was one `default=0` from the same.
FLOOR_ROWS = 10
FLOOR_TERRITORIES = 7
FLOOR_MAPPED = 7


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------
def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def resolve(root: Path, rev: str) -> str | None:
    done = git(root, "rev-parse", "--verify", f"{rev}^{{commit}}")
    return done.stdout.strip() if done.returncode == 0 else None


def newest_commit(root: Path, pathspecs: list[str]) -> str | None:
    done = git(root, "log", "-1", "--format=%H", "HEAD", "--", *pathspecs)
    sha = done.stdout.strip()
    return sha or None


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    return git(root, "merge-base", "--is-ancestor", older, newer).returncode == 0


def tracked_count(root: Path, pathspecs: list[str]) -> int:
    done = git(root, "ls-files", "--", *pathspecs)
    return len([line for line in done.stdout.splitlines() if line.strip()])


# --------------------------------------------------------------------------
# Territory globs -> git pathspecs
#
# The doc writes territories the way a builder's brief does — with braces and
# `/**`. NEITHER is git pathspec syntax: git has no brace expansion at all, so
# `…/{features,kernel}/**` passed through verbatim matches NOTHING and the row
# it belongs to would be reported permanently fresh. That is this gate's own
# vacuity trap, so the expansion happens here and every result is checked
# against `git ls-files` below.
# --------------------------------------------------------------------------
def expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    out: list[str] = []
    for option in match.group(1).split(","):
        out.extend(
            expand_braces(pattern[: match.start()] + option + pattern[match.end() :])
        )
    return out


def to_pathspecs(glob: str) -> list[str]:
    specs: list[str] = []
    for pattern in expand_braces(glob.strip()):
        if pattern.endswith("/**"):
            base = pattern[: -len("/**")]
            # A wildcard-free base is a DIRECTORY, and git's native directory
            # pathspec already matches everything beneath it — simpler and
            # more certain than relying on `**` semantics.
            specs.append(f":(glob){base}/**" if "*" in base else base)
        elif "*" in pattern:
            # `:(glob)` gives `**` its documented cross-segment meaning; the
            # default matcher's `*` also crosses `/`, which is looser than the
            # author wrote.
            specs.append(f":(glob){pattern}")
        else:
            specs.append(pattern)
    return specs


# --------------------------------------------------------------------------
# Markdown table parsing
# --------------------------------------------------------------------------
def split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    cells = stripped.strip("|").split("|")
    return [cell.strip() for cell in cells]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell) <= set("-: ") and cell for cell in cells)


def parse_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every pipe table in the document, as (header cells, body rows)."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        header = split_row(lines[index])
        if (
            header
            and index + 1 < len(lines)
            and is_separator(split_row(lines[index + 1]))
        ):
            body: list[list[str]] = []
            cursor = index + 2
            while cursor < len(lines):
                row = split_row(lines[cursor])
                if not row:
                    break
                body.append(row)
                cursor += 1
            tables.append((header, body))
            index = cursor
            continue
        index += 1
    return tables


def plain(cell: str) -> str:
    """Strip the markdown a Dimension name is decorated with."""
    return re.sub(r"[*`]", "", cell).strip()


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
@dataclass
class Row:
    dimension: str
    status: str
    notes: str
    verdict: str = "?"  # FRESH | STALE | PENDING | UNMAPPED | ERROR
    detail: str = ""


@dataclass
class Result:
    rows: list[Row] = field(default_factory=list[Row])
    territories: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    #: Rows whose Dimension matched a territory key. Counted for EVERY row,
    #: PENDING included, because this number measures whether the name
    #: matching between the two tables still works — a property of the
    #: parser, not of how many rows happen to be awaiting evidence today. The
    #: first draft floored on `checked` instead, which would have REFUSED
    #: spuriously the moment a vision-steward marked a few more rows PENDING
    #: mid-audit, i.e. exactly when the tool is being used.
    matched: int = 0
    #: Rows actually put to git (matched AND not PENDING). Informational.
    checked: int = 0
    errors: list[str] = field(default_factory=list[str])
    refusals: list[str] = field(default_factory=list[str])


def find_scorecard(
    tables: list[tuple[list[str], list[list[str]]]],
) -> list[list[str]]:
    for header, body in tables:
        lowered = [plain(h).lower() for h in header]
        if lowered[:3] == ["dimension", "status", "notes"]:
            return body
    return []


def find_territories(
    tables: list[tuple[list[str], list[list[str]]]],
) -> dict[str, list[str]]:
    for header, body in tables:
        lowered = [plain(h).lower() for h in header]
        if (
            len(lowered) >= 2
            and lowered[0] == "dimension"
            and "territory" in lowered[1]
        ):
            out: dict[str, list[str]] = {}
            for cells in body:
                if len(cells) < 2:
                    continue
                # Extract the BACKTICK-QUOTED spans rather than splitting the
                # cell on commas, and do NOT run them through `plain()`. Both
                # were bugs in the first draft and the self-test caught both:
                # a comma split tears `{features,kernel}` in half, and
                # `plain()` strips `*`, which turned `**/import_step.py` into
                # `/import_step.py`. Either one leaves a row watched by
                # nothing while every verdict still reads FRESH — this gate's
                # own vacuity failure, committed by its own parser.
                globs = [
                    span.strip()
                    for span in re.findall(r"`([^`]+)`", cells[1])
                    if span.strip() and span.strip() != "—"
                ]
                if globs:
                    out[plain(cells[0])] = globs
            return out
    return {}


def match_territory(dimension: str, territories: dict[str, list[str]]) -> str | None:
    """Map a scorecard row to a territory key.

    The two tables do not use identical names on purpose — the scorecard row is
    "Part modeling (features, history)" and the territory key is "Part
    modeling"; one territory key ("Free & unlimited / Your data, your files")
    deliberately serves TWO rows. So a key matches when any of its
    slash-separated alternatives is a prefix of the row name. Exact matching
    would silently leave rows unmapped, which reads as "nothing to watch".
    """
    name = dimension.casefold()
    best: str | None = None
    for key in territories:
        for alternative in key.split("/"):
            candidate = alternative.strip().casefold()
            longer = best is None or len(candidate) > len(best.strip().casefold())
            if candidate and name.startswith(candidate) and longer:
                best = key
    return best


def evaluate(root: Path, vision_text: str) -> Result:
    result = Result()
    tables = parse_tables(vision_text)
    body = find_scorecard(tables)
    result.territories = find_territories(tables)

    if len(body) < FLOOR_ROWS:
        result.refusals.append(
            f"parsed {len(body)} scorecard row(s), expected at least {FLOOR_ROWS} — "
            f"the table moved or the parser stopped matching, so a clean report "
            f"here would be a clean report about nothing"
        )
    if len(result.territories) < FLOOR_TERRITORIES:
        result.refusals.append(
            f"parsed {len(result.territories)} territory entr(ies), expected at "
            f"least {FLOOR_TERRITORIES} — with no territory map every row is "
            f"vacuously fresh"
        )

    for cells in body:
        if len(cells) < 3:
            continue
        row = Row(plain(cells[0]), plain(cells[1]), cells[2])
        result.rows.append(row)

        lead = LEAD_BOLD.search(row.notes)
        lead_text = lead.group(1) if lead else ""
        citation = CITATION.search(row.notes)
        pending = "PENDING" in row.status.upper() or "PENDING" in lead_text.upper()

        if match_territory(row.dimension, result.territories) is not None:
            result.matched += 1

        if pending:
            # A legitimate, non-stale state: evidence is in flight and the row
            # names what would resolve it. Exempt from the ancestry check —
            # there is no citation whose age means anything yet.
            row.verdict = "PENDING"
            row.detail = "evidence in flight"
            continue

        if not citation:
            # NOT skipped. A cell with neither marker is the state every rotten
            # row passes through on its way to being believed, so it is the one
            # thing this gate must never wave past.
            row.verdict = "ERROR"
            row.detail = "no `Re-derived <date> @ <sha>` marker and not PENDING"
            result.errors.append(f"{row.dimension}: {row.detail}")
            continue

        cited_short = citation.group("sha")
        cited = resolve(root, cited_short)
        if cited is None:
            row.verdict = "ERROR"
            row.detail = f"cited sha {cited_short} does not resolve in this repo"
            result.errors.append(f"{row.dimension}: {row.detail}")
            continue

        key = match_territory(row.dimension, result.territories)
        if key is None:
            # Sanctioned by the doc for rows whose surface does not exist yet
            # (Collaboration, Extensibility, Agent access). Reported every run
            # so a NEW unmapped row is visible rather than quietly unwatched.
            row.verdict = "UNMAPPED"
            row.detail = "no territory in VISION.md's map — nothing to watch yet"
            continue

        pathspecs: list[str] = []
        for glob in result.territories[key]:
            pathspecs.extend(to_pathspecs(glob))

        # THE anti-vacuity check for this gate. A territory that matches no
        # tracked file makes `git log` return nothing, which reads exactly like
        # "no commit since the citation" — i.e. a typo in the doc's map would
        # certify the row fresh forever.
        if tracked_count(root, pathspecs) == 0:
            row.verdict = "ERROR"
            row.detail = (
                f"territory {result.territories[key]!r} matches NO tracked file — "
                f"this row is watched by nothing"
            )
            result.errors.append(f"{row.dimension}: {row.detail}")
            continue

        result.checked += 1
        newest = newest_commit(root, pathspecs)
        if newest is None:
            row.verdict = "FRESH"
            row.detail = "no commits in territory"
            continue
        if is_ancestor(root, newest, cited):
            row.verdict = "FRESH"
            row.detail = f"cited {cited_short}, territory head {newest[:7]}"
        else:
            row.verdict = "STALE"
            row.detail = (
                f"{newest[:7]} landed in this row's territory after the cited "
                f"{cited_short}"
            )

    if result.matched < FLOOR_MAPPED and not result.refusals:
        result.refusals.append(
            f"only {result.matched} row(s) mapped to a territory, expected at "
            f"least {FLOOR_MAPPED} — the name matching between the scorecard "
            f"and the territory table has broken, so most rows are watched by "
            f"nothing"
        )
    return result


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
_ORDER = {"STALE": 0, "ERROR": 1, "UNMAPPED": 2, "PENDING": 3, "FRESH": 4}


def report(result: Result, warn_only: bool) -> int:
    if result.refusals:
        for refusal in result.refusals:
            print(f"REFUSED  {refusal}", file=sys.stderr)
        return 0 if warn_only else 2

    width = max((len(row.dimension) for row in result.rows), default=10)
    for row in sorted(
        result.rows, key=lambda r: (_ORDER.get(r.verdict, 9), r.dimension)
    ):
        print(f"  {row.verdict:<9}{row.dimension:<{width}}  {row.detail}")

    counts = {verdict: 0 for verdict in _ORDER}
    for row in result.rows:
        counts[row.verdict] = counts.get(row.verdict, 0) + 1
    print(
        f"\nscorecard-freshness: {len(result.rows)} row(s) — "
        + " · ".join(f"{n} {verdict}" for verdict, n in counts.items() if n)
        + f" ({result.checked} checked against git,"
        f" {len(result.territories)} territories)"
    )

    bad = counts.get("STALE", 0) + counts.get("ERROR", 0)
    if bad:
        print(
            "\nA STALE row is a prompt to RE-DERIVE, not proof the verdict is "
            "wrong — re-check it and refresh its marker. An ERROR row is a "
            "defect in the table itself.",
        )
    if warn_only:
        return 0
    return 1 if bad else 0


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
#: The real scorecard's status glyphs, written as escapes. The fixture has to
#: carry the SAME bytes as `docs/VISION.md` — `stage-doc-hunks.py` passed its
#: own self-test while eating a colleague's entry because its fixture used the
#: BACKLOG shape and the victim was a ROADMAP paragraph, so a fixture in the
#: wrong format is a gate that cannot fail for the reason you care about. The
#: escapes exist only because ruff's RUF001 rejects the literal glyphs in
#: Python source (CLAUDE.md: ASCII in code, symbols in markdown); they are
#: byte-identical to what the doc contains.
#: Written as `chr()` rather than an escape because `ruff format` normalises
#: `\uXXXX` back to the literal glyph, which `ruff check` then rejects again —
#: the two halves of the same tool disagree, and `chr()` is the only spelling
#: that survives both.
_TICK = chr(0x2705)  # WHITE HEAVY CHECK MARK
_DASH = chr(0x2796)  # HEAVY MINUS SIGN
_CROSS = chr(0x274C)  # CROSS MARK

_FIXTURE_DOC = """# Vision

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | {t} | **Re-derived 2026-09-15 @ `{sketch_sha}`.** |
| Part modeling (features, history) | {t} | **Re-derived 2026-09-15 @ `{part_sha}`.** |
| Assemblies & mates | {d} | **Re-derived 2026-09-15 @ `{asm_sha}`.** |
| Drawings & documentation | {d} | **Re-derived 2026-09-15 @ `{draw_sha}`.** |
| Sheet metal | {d} | **Re-derived 2026-09-15 @ `{sheet_sha}`.** |
| Workspace & document management | {d} | **Re-derived 2026-09-15 @ `{work_sha}`.** |
| Interop (import + export) | {d} | **Re-derived 2026-09-15 @ `{interop_sha}`.** |
| Performance on real parts | {d} | **PENDING - awaiting the gauntlet.** Old text. |
| Collaboration & versioning | {x} | **Re-derived 2026-09-15 @ `{sketch_sha}`.** No. |
| Extensibility (scripting API) | {x} | **PENDING - awaiting SCRIPT-1.** |
| Agent access (MCP) | {x} | **PENDING - awaiting SCRIPT-1.** |

Prose between the tables.

| Dimension | Territory (globs) |
|---|---|
| Sketching & constraints | `services/geometry/src/geometry/sketch/**` |
| Part modeling | `services/geometry/src/geometry/{{features,kernel}}/**` |
| Assemblies & mates | `services/documents/src/documents/assemblies.py` |
| Drawings & documentation | `services/geometry/src/geometry/drawings/**` |
| Sheet metal | `services/geometry/src/geometry/sheet_metal/**` |
| Workspace & document management | `apps/web/src/routes/PartsPage.tsx` |
| Interop | `**/import_step.py` |
| Performance on real parts | `docs/PERF.md` |
"""

_FIXTURE_FILES = [
    "services/geometry/src/geometry/sketch/solver.py",
    "services/geometry/src/geometry/features/extrude.py",
    "services/geometry/src/geometry/kernel/edges.py",
    "services/documents/src/documents/assemblies.py",
    "services/geometry/src/geometry/drawings/compose.py",
    "services/geometry/src/geometry/sheet_metal/unfold.py",
    "apps/web/src/routes/PartsPage.tsx",
    "services/geometry/src/geometry/kernel/import_step.py",
    "docs/PERF.md",
]

_GIT_ID = (
    "-c",
    "user.email=selftest@loft.invalid",
    "-c",
    "user.name=selftest",
    "-c",
    "commit.gpgsign=false",
)


def _commit(root: Path, path: str, body: str) -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), "add", path], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), *_GIT_ID, "commit", "-q", "-m", f"touch {path}"],
        check=True,
        capture_output=True,
    )
    return git(root, "rev-parse", "HEAD").stdout.strip()


def _build_fixture(root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(root), "init", "-q", "-b", "main"],
        check=True,
        capture_output=True,
    )
    shas: dict[str, str] = {}
    for path in _FIXTURE_FILES:
        shas[path] = _commit(root, path, "seed\n")
    head = git(root, "rev-parse", "HEAD").stdout.strip()[:7]
    return {"head": head, **{k: v[:7] for k, v in shas.items()}}


def _doc(head: str, **overrides: str) -> str:
    fields = {
        "t": _TICK,
        "d": _DASH,
        "x": _CROSS,
        "sketch_sha": head,
        "part_sha": head,
        "asm_sha": head,
        "draw_sha": head,
        "sheet_sha": head,
        "work_sha": head,
        "interop_sha": head,
    }
    fields.update(overrides)
    return _FIXTURE_DOC.format(**fields)


def self_test() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"ok  {name}")
        else:
            failures.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        shas = _build_fixture(root)
        head = shas["head"]

        # --- positive control -------------------------------------------
        clean = evaluate(root, _doc(head))
        check(
            "positive control: every row FRESH or PENDING",
            not clean.refusals
            and not clean.errors
            and all(
                row.verdict in {"FRESH", "PENDING", "UNMAPPED"} for row in clean.rows
            ),
            f"refusals={clean.refusals} errors={clean.errors} "
            f"verdicts={[(r.dimension, r.verdict) for r in clean.rows]}",
        )
        check(
            "positive control: brace territory really is checked against git",
            clean.checked >= FLOOR_MAPPED,
            f"only {clean.checked} rows reached git — brace expansion is the "
            f"likely culprit",
        )

        # --- THE defect: a commit lands in a row's territory after its sha --
        _commit(root, "services/documents/src/documents/assemblies.py", "MATE-1 fix\n")
        stale = evaluate(root, _doc(head))
        assemblies = [r for r in stale.rows if r.dimension.startswith("Assemblies")]
        check(
            "the Assemblies incident: a later territory commit reports STALE",
            len(assemblies) == 1 and assemblies[0].verdict == "STALE",
            f"got {[(r.dimension, r.verdict) for r in assemblies]}",
        )
        check(
            "…and only that row — its neighbours stay FRESH",
            sum(1 for r in stale.rows if r.verdict == "STALE") == 1,
            f"{[(r.dimension, r.verdict) for r in stale.rows if r.verdict == 'STALE']}",
        )

        # --- PENDING must NOT be reported stale -------------------------
        _commit(root, "docs/PERF.md", "new numbers\n")
        pending = evaluate(root, _doc(head))
        perf = [r for r in pending.rows if r.dimension.startswith("Performance")]
        check(
            "a PENDING row with a moved territory is NOT rot",
            len(perf) == 1 and perf[0].verdict == "PENDING",
            f"got {[(r.dimension, r.verdict) for r in perf]}",
        )

        # --- the floor must measure the PARSER, not the doc's mood -------
        # An audit cycle marks rows PENDING as it dispatches measurement, so a
        # floor counting rows-put-to-git would refuse hardest exactly when the
        # vision-steward is using the tool. Caught in review of the first
        # draft; this is its negative control.
        mostly_pending = _doc(head)
        for dimension in (
            "Sketching & constraints",
            "Drawings & documentation",
            "Sheet metal",
            "Workspace & document management",
        ):
            mostly_pending = re.sub(
                rf"(\| {re.escape(dimension)} \| [^|]*\| )\*\*Re-derived[^*]*\*\*",
                r"\1**PENDING — awaiting a measurement.**",
                mostly_pending,
            )
        result = evaluate(root, mostly_pending)
        check(
            "marking most rows PENDING does NOT trip the vacuity floor",
            not result.refusals
            and sum(1 for r in result.rows if r.verdict == "PENDING") >= 7,
            f"refusals={result.refusals} "
            f"pending={sum(1 for r in result.rows if r.verdict == 'PENDING')}",
        )

        # --- a row with NO marker must FAIL, not be skipped --------------
        anchor = f"| Sheet metal | {_DASH} | **Re-derived 2026-09-15 @ `{head}`.** |"
        unmarked = _doc(head).replace(
            anchor, f"| Sheet metal | {_DASH} | Shipped, QA'd, looks fine. |"
        )
        # A `.replace` whose anchor has drifted is a SILENT no-op, so the
        # mutation would simply not happen and the case would pass by testing
        # the clean document. Assert the mutation landed before asserting what
        # it caused.
        check(
            "…and the no-marker mutation actually applied",
            unmarked != _doc(head),
            f"anchor not found: {anchor!r}",
        )
        result = evaluate(root, unmarked)
        sheet = [r for r in result.rows if r.dimension == "Sheet metal"]
        check(
            "a row with NO marker is an ERROR, never a skip",
            len(sheet) == 1 and sheet[0].verdict == "ERROR" and bool(result.errors),
            f"got {[(r.dimension, r.verdict) for r in sheet]}",
        )

        # --- an unresolvable citation is worthless ----------------------
        result = evaluate(root, _doc(head, draw_sha="deadbee"))
        draw = [r for r in result.rows if r.dimension.startswith("Drawings")]
        check(
            "a cited sha that does not resolve is an ERROR",
            len(draw) == 1 and draw[0].verdict == "ERROR",
            f"got {[(r.dimension, r.verdict) for r in draw]}",
        )

        # --- a territory that watches nothing ---------------------------
        typo = _doc(head).replace(
            "`services/geometry/src/geometry/sheet_metal/**`",
            "`services/geometry/src/geometry/sheetmetal/**`",
        )
        result = evaluate(root, typo)
        sheet = [r for r in result.rows if r.dimension == "Sheet metal"]
        check(
            "a territory glob matching NO tracked file is an ERROR, not 'fresh'",
            len(sheet) == 1
            and sheet[0].verdict == "ERROR"
            and "watched by nothing" in sheet[0].detail,
            f"got {[(r.dimension, r.verdict, r.detail) for r in sheet]}",
        )

        # --- vacuity: the parser stops matching -------------------------
        result = evaluate(root, "# Vision\n\nNo tables at all.\n")
        check(
            "an empty document REFUSES rather than reporting a clean sweep",
            len(result.refusals) >= 2,
            f"refusals={result.refusals}",
        )
        check(
            "…and refusal is exit 2, distinct from a STALE finding's exit 1",
            report(result, warn_only=False) == 2,
            "refusal did not return 2",
        )
        result = evaluate(root, _doc(head).split("Prose between")[0])
        check(
            "deleting the TERRITORY table REFUSES (else every row is vacuously fresh)",
            bool(result.refusals),
            f"refusals={result.refusals}",
        )

        # --- --warn-only never blocks -----------------------------------
        stale_again = evaluate(root, _doc(head))
        check(
            "--warn-only reports the same finding and still exits 0",
            report(stale_again, warn_only=True) == 0,
            "warn-only returned nonzero",
        )

    if failures:
        print("\nSELF-TEST FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(
        "\nscorecard-freshness: self-test passed — the check can refuse and can fail."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VISION.md scorecard freshness")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--doc", type=Path, default=None, help=f"default {VISION}")
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="report and always exit 0 (how `just lint` and doc-syncer run it)",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    doc = args.doc or (args.root / VISION)
    if not doc.exists():
        print(f"scorecard-freshness: REFUSED — {doc} does not exist", file=sys.stderr)
        return 0 if args.warn_only else 2
    return report(
        evaluate(args.root, doc.read_text(encoding="utf-8")), warn_only=args.warn_only
    )


if __name__ == "__main__":
    sys.exit(main())
