#!/usr/bin/env python3
"""Every path a Dockerfile COPYs from the repo is actually IN the build context.

Why this exists
---------------
`.dockerignore` excludes broad directories (`scripts`, `deploy`, `docs`) to keep
the image context tiny, then re-includes the handful of files the images need
with `!` negations. That design has one failure mode and it is silent at every
layer that can be run here: add a file to a `COPY` line, forget the matching
negation, and the daemon resolves the source to *nothing* and fails the build —
but only at `docker build` time, and the Docker registry is policy-blocked in
this container, so **no local gate can reach that failure**. It surfaces in CI's
`deploy-path` workflow, which is the slowest and last signal we have.

It happened on 2026-08-01: LIC-2 added `scripts/corresponding_source.py` to the
runtime `COPY` (the licence gate imports it) without a `!scripts/
corresponding_source.py` negation, and all three service images failed at

    > [gateway runtime 9/11] COPY --chown=loft:loft scripts/check-licences.py
      scripts/corresponding_source.py deploy/docker/licence/verify-kernel.py
      /app/tools/

for two commits. The negation list had already been extended once before for
the same reason, which is the tell that the *list* is the defect, not either
omission — an allow-list nobody can test locally will keep losing entries.

So this reimplements Docker's own `.dockerignore` matching (moby's
`patternmatcher.MatchesOrParentMatches`: last matching pattern wins, and a
pattern matching any parent directory matches the file) and asserts, for every
Dockerfile in the repo, that each COPY source

  1. exists, and
  2. survives `.dockerignore`.

Stdlib only, no daemon, ~10 ms — so it runs in `just lint` and in CI's `compose`
job, beside `check-compose.py`: the two of them are the cheap half of the deploy
gate, making a build failure visible at the moment somebody writes it rather than
twenty minutes later on a runner.

    python3 scripts/check-build-context.py
    python3 scripts/check-build-context.py --self-test   # prove it can fail
"""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Regex-special characters that are NOT part of `.dockerignore` glob syntax and
#: therefore have to be escaped when the pattern is compiled. `[`, `]`, `^` and
#: `-` are deliberately absent: Docker passes character classes straight
#: through, so `**/*.py[cod]` must keep working as a class.
_ESCAPE = set(".+()|{}$\\")


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile one `.dockerignore` pattern, mirroring moby's `Pattern.compile`.

    `**` spans separators (and a trailing `**` matches everything below), `*`
    and `?` do not, `[...]` is a character class.
    """
    out = ["^"]
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        i += 1
        if ch == "*":
            if i < n and pattern[i] == "*":
                i += 1
                if i < n and pattern[i] == "/":  # "**/" is treated as "**"
                    i += 1
                out.append(".*" if i >= n else "(.*/)?")
            else:
                out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch in _ESCAPE:
            out.append("\\" + ch)
        else:
            out.append(ch)
    out.append("$")
    return re.compile("".join(out))


class DockerIgnore:
    """Ordered `.dockerignore` rules, matched the way the daemon matches them."""

    def __init__(self, text: str) -> None:
        self.rules: list[tuple[bool, re.Pattern[str], str]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            exclusion = line.startswith("!")
            if exclusion:
                line = line[1:].strip()
            # Docker cleans the pattern: strip a leading "/" and any "./".
            cleaned = str(PurePosixPath(line.lstrip("/"))).rstrip("/")
            if not cleaned or cleaned == ".":
                continue
            self.rules.append((exclusion, _compile(cleaned), raw.strip()))

    def excluded(self, path: str) -> str | None:
        """The rule excluding *path*, or None when it reaches the context.

        Mirrors `patternmatcher.MatchesOrParentMatches`: rules are applied in
        order, a rule matching any PARENT directory matches the file, and the
        last rule to match decides.
        """
        parts = path.split("/")
        candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        verdict: str | None = None
        for exclusion, regex, source in self.rules:
            # A negation only matters while the path is currently excluded, and
            # an exclusion only while it is currently included.
            if exclusion != (verdict is not None):
                continue
            if any(regex.match(candidate) for candidate in candidates):
                verdict = None if exclusion else source
        return verdict


#: `COPY [--flags] <src>... <dest>` / `ADD ...`, after line continuations are
#: joined. `--from=` sources come from an earlier build stage, not the context.
_COPY = re.compile(r"^\s*(COPY|ADD)\s+(.*)$", re.IGNORECASE)


def copy_sources(dockerfile: Path) -> list[tuple[int, str]]:
    """(line number, source path) for every context-sourced COPY/ADD argument."""
    text = dockerfile.read_text()
    found: list[tuple[int, str]] = []
    joined: list[tuple[int, str]] = []
    buffer, start = "", 0
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.rstrip()
        if not buffer:
            start = number
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append((start, buffer + stripped))
        buffer = ""

    for number, instruction in joined:
        match = _COPY.match(instruction)
        if not match:
            continue
        args = match.group(2).split("#", 1)[0].split()
        flags = [a for a in args if a.startswith("--")]
        if any(f.startswith("--from=") for f in flags):
            continue
        operands = [a for a in args if not a.startswith("--")]
        if len(operands) < 2:
            continue
        for source in operands[:-1]:  # the last operand is the destination
            found.append((number, source.strip("\"'").rstrip("/")))
    return found


def run(root: Path, quiet: bool = False) -> int:
    """Check every Dockerfile under *root*. Non-zero when a COPY cannot resolve."""

    def say(line: str) -> None:
        if not quiet:
            print(line)

    ignore_file = root / ".dockerignore"
    ignore = DockerIgnore(ignore_file.read_text() if ignore_file.exists() else "")

    dockerfiles = sorted(
        p
        for p in root.rglob("*Dockerfile*")
        if ".git" not in p.parts
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
        and p.is_file()
    )
    if not dockerfiles:
        say("check-build-context: no Dockerfiles found — nothing to check.")
        return 1

    failures: list[str] = []
    checked = 0
    for dockerfile in dockerfiles:
        relative = dockerfile.relative_to(root).as_posix()
        say(f"{relative}")
        for number, source in copy_sources(dockerfile):
            checked += 1
            # A source may be a glob; every match must survive, and a glob that
            # matches nothing is the same build failure as a missing file.
            matches = (
                [root / source]
                if not any(ch in source for ch in "*?[")
                else sorted(root.glob(source))
            )
            existing = [m for m in matches if m.exists()]
            if not existing:
                message = (
                    f"{relative}:{number} COPY {source} — no such path in the repo"
                )
                say(f"  FAIL {message}")
                failures.append(message)
                continue
            for match in existing:
                path = match.relative_to(root).as_posix()
                rule = ignore.excluded(path)
                if rule is None:
                    say(f"  ok   {path}")
                    continue
                message = (
                    f"{relative}:{number} COPY {source} — `{path}` is excluded "
                    f"from the build context by .dockerignore rule `{rule}`; "
                    "the daemon will resolve this COPY to nothing and fail the "
                    "build. Add a `!` negation for it."
                )
                say(f"  FAIL {message}")
                failures.append(message)

    if failures:
        say(f"\ncheck-build-context: FAILED ({len(failures)} unreachable source(s))")
        return 1
    say(f"\ncheck-build-context: {checked} COPY source(s) reach the build context")
    return 0


#: The real defect, reduced: a broad directory exclusion, a negation for the
#: file somebody remembered, and a COPY naming one they did not.
_SELF_TEST_IGNORE = "scripts\n!scripts/kept.py\n"
_SELF_TEST_DOCKERFILE = (
    "FROM scratch\nCOPY --chown=a:b scripts/kept.py scripts/forgotten.py /app/tools/\n"
)


def self_test() -> int:
    """Prove the gate FAILS on a missing negation, and passes once it is added.

    A gate nobody has watched fail is not a gate (`just licence-selftest` exists
    for the same reason). This one is especially cheap to doubt, because it
    reimplements somebody else's matching rules: "it printed ok" is worth
    exactly as much as the evidence that it can print anything else.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "kept.py").write_text("")
        (root / "scripts" / "forgotten.py").write_text("")
        (root / "Dockerfile").write_text(_SELF_TEST_DOCKERFILE)
        (root / ".dockerignore").write_text(_SELF_TEST_IGNORE)

        before = run(root, quiet=True)
        print(f"  {'ok  ' if before == 1 else 'FAIL'} unnegated COPY source → exit 1")

        (root / ".dockerignore").write_text(
            _SELF_TEST_IGNORE + "!scripts/forgotten.py\n"
        )
        after = run(root, quiet=True)
        print(f"  {'ok  ' if after == 0 else 'FAIL'} negation added → exit 0")

    if before == 1 and after == 0:
        print("\ncheck-build-context: self-test passed — the gate can fail.")
        return 0
    print("\ncheck-build-context: SELF-TEST FAILED — this gate proves nothing.")
    return 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
