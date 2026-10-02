#!/usr/bin/env python3
"""No hand-written source file grows past 1,500 lines, and none over it grows.

Why this exists (FILE-SIZE-RATCHET, docs/BACKLOG.md)
----------------------------------------------------
On 2026-09-30 ten hand-written files were over 2,000 lines and
``apps/web/src/routes/PartPage.tsx`` was 6,502. Nobody chose that: every
commit added a few lines to the file the change happened to live in, which is
always the cheapest edit, and nothing pushed back. The splits are now filed as
backlog items, and without a ratchet the files they shrink would regrow
behind them. This is the push-back, and it is a RATCHET, not a cap: the files
that are already oversized are allowed to stay that size, never to grow.

The rules, over every tracked ``.py``, ``.ts`` and ``.tsx`` file in scope:

  1. a file NOT in the allowlist may have at most ``LIMIT`` lines, so neither
     a new file nor a file that is under the limit today can pass it;
  2. a file in the allowlist may have at most its entry, so an oversized file
     cannot grow by even one line;
  3. an entry ABOVE the file's actual size fails as stale, and so does an
     entry for a file that is gone, out of scope, or back under the limit.
     That is what makes the list only shrink: a split must lower or remove
     its entry in the same commit, otherwise the headroom it freed could be
     spent again silently. ``--tighten`` writes exactly those reductions and
     can never raise or add an entry.

The allowlist is ``scripts/file-size-allowlist.json``. Raising an entry is a
diff a reviewer reads, which is the point: growth past the limit is a decision,
not an accident.

Scope
-----
Hand-written source only. Out of scope: the generated client and contracts
(``packages/contracts``, ``packages/ts-client``) and the generated gateway
operation table (``packages/loft-script/src/loft/_operations.py``), golden
models and their derivations (``services/geometry/goldens``,
``goldens-gauntlet``) and anything under a ``fixtures/`` directory. Lockfiles
are not ``.py``/``.ts``/``.tsx`` and so are never read. Test files ARE in
scope: a 3,500-line test module is as hard to work in as a 3,500-line feature.

Files come from ``git ls-files`` (tracked content, staged-new included) and
are read from disk, the same convention as ``check-mutation-markers.py``: an
agent's untracked scratch file cannot turn the gate red for everyone, and a
staged file cannot reach a commit unmeasured. A line is what ``wc -l``
counts for a file that ends in a newline.

Non-vacuity: the walk must reach at least ``MIN_FILES`` files (today ~1,220),
so a path filter that quietly admits nothing fails instead of passing.

    python3 scripts/check-file-size.py
    python3 scripts/check-file-size.py --self-test   # prove it can fail
    python3 scripts/check-file-size.py --tighten     # lower stale entries
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_REL = "scripts/file-size-allowlist.json"

#: The most lines a file outside the allowlist may have.
LIMIT = 1500

#: The walk reaches ~1,220 files today; well below that so churn never trips
#: it, well above zero so a broken filter cannot report a clean tree.
MIN_FILES = 500

SUFFIXES = frozenset({".py", ".ts", ".tsx"})

#: Generated or golden trees: path prefixes, matched on whole components.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "packages/contracts/",
    "packages/ts-client/",
    "services/geometry/goldens/",
    "goldens-gauntlet/",
    # Third-party source built as-is plus a checked patch
    # (scripts/check-vendored-planegcs.py): not ours to split.
    "vendor/",
)
#: Single generated files that live beside hand-written ones.
EXCLUDED_FILES = frozenset({"packages/loft-script/src/loft/_operations.py"})
#: A directory with one of these names holds fixtures, wherever it sits.
EXCLUDED_DIRS = frozenset({"fixtures", "__fixtures__", "node_modules"})


def in_scope(rel: str) -> bool:
    """Whether a repo-relative POSIX path is hand-written source we measure."""
    path = PurePosixPath(rel)
    if path.suffix not in SUFFIXES or rel in EXCLUDED_FILES:
        return False
    if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    return not any(part in EXCLUDED_DIRS for part in path.parts[:-1])


def count_lines(path: Path) -> int:
    """Lines as `wc -l` counts them when the file ends in a newline."""
    return len(path.read_bytes().splitlines())


def measure(root: Path) -> dict[str, int]:
    """Line counts of every tracked, in-scope file present on disk."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode()
    sizes: dict[str, int] = {}
    for rel in listed.split("\0"):
        if not rel or not in_scope(rel):
            continue
        path = root / rel
        if path.is_file():  # deleted on disk but not yet staged: absent
            sizes[rel] = count_lines(path)
    return sizes


def load_allowlist(path: Path) -> dict[str, int]:
    """The `files` map of the allowlist, validated as path -> int."""
    raw: object = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be an object")
    files = cast("dict[str, object]", raw).get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{path}: `files` must be an object")
    out: dict[str, int] = {}
    for key, value in cast("dict[object, object]", files).items():
        if not isinstance(key, str) or type(value) is not int:
            raise ValueError(f"{path}: entry {key!r} must map a path to an int")
        out[key] = value
    return out


def check(sizes: dict[str, int], allowed: dict[str, int]) -> list[str]:
    """Every violation of the three rules, one human-readable line each."""
    problems: list[str] = []
    for rel, lines in sorted(sizes.items()):
        cap = allowed.get(rel)
        if cap is None and lines > LIMIT:
            problems.append(
                f"{rel}: {lines} lines, over the {LIMIT}-line limit "
                f"(split it; it is not in {ALLOWLIST_REL})"
            )
        elif cap is not None and lines > cap:
            problems.append(
                f"{rel}: grew to {lines} lines, its entry is {cap} "
                f"(an oversized file may not grow; move code out instead)"
            )
    for rel, cap in sorted(allowed.items()):
        lines = sizes.get(rel)
        if cap <= LIMIT:
            problems.append(
                f"{ALLOWLIST_REL}: {rel} is listed at {cap}, which is not over "
                f"the limit; remove the entry"
            )
        elif lines is None:
            problems.append(
                f"{ALLOWLIST_REL}: {rel} is listed but is not a tracked, "
                f"in-scope file; remove the entry (--tighten)"
            )
        elif lines <= LIMIT:
            problems.append(
                f"{ALLOWLIST_REL}: {rel} is down to {lines} lines; "
                f"remove its entry (--tighten)"
            )
        elif lines < cap:
            problems.append(
                f"{ALLOWLIST_REL}: {rel} is {lines} lines but listed at {cap}; "
                f"lower the entry to {lines} (--tighten)"
            )
    return problems


def tightened(sizes: dict[str, int], allowed: dict[str, int]) -> dict[str, int]:
    """The allowlist with every entry lowered to the truth. Never raises one."""
    out: dict[str, int] = {}
    for rel, cap in allowed.items():
        lines = sizes.get(rel)
        if lines is not None and lines > LIMIT:
            out[rel] = min(cap, lines)
    return out


def write_allowlist(path: Path, files: dict[str, int]) -> None:
    doc: dict[str, object] = json.loads(path.read_text()) if path.exists() else {}
    doc["files"] = dict(sorted(files.items()))
    path.write_text(json.dumps(doc, indent=2) + "\n")


def run(
    root: Path, allowlist: Path, *, tighten: bool = False, floor: int = MIN_FILES
) -> int:
    sizes = measure(root)
    if len(sizes) < floor:
        print(
            f"check-file-size: only {len(sizes)} in-scope files found "
            f"(floor {floor}); the walk is broken, refusing to pass"
        )
        return 1
    allowed = load_allowlist(allowlist)
    if tighten:
        new = tightened(sizes, allowed)
        write_allowlist(allowlist, new)
        print(f"check-file-size: {len(allowed)} -> {len(new)} entries written")
        allowed = new
    problems = check(sizes, allowed)
    for line in problems:
        print(f"FAIL {line}")
    if problems:
        print(f"check-file-size: {len(problems)} problem(s)")
        return 1
    print(
        f"check-file-size: ok, {len(sizes)} files, {len(allowed)} allowlisted "
        f"over {LIMIT} lines, none grew"
    )
    return 0


# ── self-test ────────────────────────────────────────────────────────────────


def _repo(tmp: Path, files: dict[str, int], allowed: dict[str, int]) -> Path:
    """A throwaway git repo with `files` tracked at the given sizes, plus one
    small file so the (lowered) floor is never what decides a case."""
    root = tmp / "repo"
    root.mkdir()
    everything = {"pad.py": 1} | files
    for rel, lines in everything.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n" * lines)
    (root / "scripts").mkdir(exist_ok=True)
    (root / ALLOWLIST_REL).write_text(json.dumps({"files": allowed}) + "\n")
    subprocess.run(["git", "init", "-q", "--template="], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    return root


_PART = "apps/web/src/routes/PartPage.tsx"


def self_test() -> int:
    big = LIMIT + 1000
    #: (name, tracked files -> lines, allowlist, expected exit code)
    cases: list[tuple[str, dict[str, int], dict[str, int], int]] = [
        ("the tip: an oversized file at its entry", {_PART: big}, {_PART: big}, 0),
        (
            "ACCEPT: +1 line to an allowlisted file",
            {_PART: big + 1},
            {_PART: big},
            1,
        ),
        ("ACCEPT: a new file of LIMIT+1 lines", {"src/new.ts": LIMIT + 1}, {}, 1),
        ("a new file of exactly LIMIT lines passes", {"src/new.py": LIMIT}, {}, 0),
        (
            "an under-limit file growing past the limit",
            {"src/a.tsx": LIMIT + 1},
            {},
            1,
        ),
        (
            "a split that left its entry too high (list must shrink)",
            {_PART: big - 10},
            {_PART: big},
            1,
        ),
        (
            "a split under the limit that kept its entry",
            {_PART: 900},
            {_PART: big},
            1,
        ),
        ("an entry for a deleted file", {}, {_PART: big}, 1),
        ("an entry at or under the limit", {_PART: 10}, {_PART: LIMIT}, 1),
        (
            "generated client is out of scope",
            {"packages/ts-client/src/gateway/schema.ts": big},
            {},
            0,
        ),
        (
            "goldens and fixtures are out of scope",
            {
                "services/geometry/goldens/g/derive.py": big,
                "apps/web/e2e/fixtures/big.ts": big,
                "packages/loft-script/src/loft/_operations.py": big,
            },
            {},
            0,
        ),
        ("other suffixes are out of scope", {"src/big.js": big}, {}, 0),
        (
            "an entry for an out-of-scope file is stale",
            {"packages/contracts/x.ts": big},
            {"packages/contracts/x.ts": big},
            1,
        ),
    ]
    failed = 0
    for name, files, allowed, want in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(Path(tmp), files, allowed)
            got = _quiet_run(root, root / ALLOWLIST_REL)
        ok = got == want
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name} (exit {got}, want {want})")

    # An untracked file is invisible; staging it makes it count.
    with tempfile.TemporaryDirectory() as tmp:
        root = _repo(Path(tmp), {}, {})
        (root / "scratch.py").write_text("x = 1\n" * (LIMIT + 1))
        untracked = _quiet_run(root, root / ALLOWLIST_REL)
        subprocess.run(["git", "add", "scratch.py"], cwd=root, check=True)
        staged = _quiet_run(root, root / ALLOWLIST_REL)
    ok = (untracked, staged) == (0, 1)
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} untracked ignored, staged counted")

    # The floor: a walk that admits almost nothing refuses rather than
    # reporting a clean tree. Every other case lowers it to 1.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / ALLOWLIST_REL).write_text('{"files": {}}\n')
        (root / "one.py").write_text("x = 1\n")
        subprocess.run(["git", "init", "-q", "--template="], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        got = _quiet_run(root, root / ALLOWLIST_REL, floor=MIN_FILES)
    failed += got != 1
    print(f"{'ok  ' if got == 1 else 'FAIL'} a walk under the file floor is refused")

    # --tighten lowers and drops, never raises or adds, then passes.
    with tempfile.TemporaryDirectory() as tmp:
        files = {_PART: big - 5, "a.py": LIMIT + 7, "b.py": 100, "c.py": LIMIT + 3}
        allowed = {_PART: big, "a.py": LIMIT + 2, "b.py": big, "gone.py": big}
        root = _repo(Path(tmp), files, allowed)
        tight = _quiet_run(root, root / ALLOWLIST_REL, tighten=True)
        after = load_allowlist(root / ALLOWLIST_REL)
    want_after = {_PART: big - 5, "a.py": LIMIT + 2}
    ok = after == want_after and tight == 1  # a.py grew, c.py is new: still red
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} --tighten only shrinks ({after})")

    if failed:
        print(f"\ncheck-file-size: self-test FAILED ({failed} case(s))")
        return 1
    print(f"\ncheck-file-size: self-test passed ({len(cases) + 3} checks)")
    return 0


def _quiet_run(
    root: Path, allowlist: Path, *, tighten: bool = False, floor: int = 1
) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return run(root, allowlist, tighten=tighten, floor=floor)


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run(REPO_ROOT, REPO_ROOT / ALLOWLIST_REL, tighten="--tighten" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
