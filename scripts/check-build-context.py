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

It then asks a SECOND question the first cannot reach (`check_workspace_members`
below): is every uv workspace member in a service's dependency closure actually
COPYed at all? The first check grades the COPY lines that exist; this one grades
the one nobody wrote. Adding a workspace package and wiring it into py-kit is a
`packages/**` change that touches no Dockerfile, so nothing in that diff hints
the image needs a new line — and `loft-wire` broke all three images that way on
2026-09-15.

Stdlib only, no daemon, ~50 ms — so it runs in `just lint` and in CI's `compose`
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
from typing import cast

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

#: The fewest COPY sources a healthy walk of this repo may find. A count floor
#: exists because "no COPY source is unreachable" is vacuously true of a walk
#: that examined none: if `_COPY` or the continuation joiner above ever stops
#: matching the Dockerfile syntax in use, `checked` drops to 0, `failures` stays
#: empty, and this gate prints "0 COPY source(s) reach the build context" and
#: exits 0 — disarmed, in the exact CI job that exists to catch the failure the
#: blocked Docker registry makes unreachable locally (measured 2026-08-29).
#: The repo has one Dockerfile with 15 sources; a drop below half of that is a
#: change worth a human look, while leaving room to retire a COPY or two.
MIN_COPY_SOURCES = 8


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


def run(root: Path, quiet: bool = False, min_sources: int = MIN_COPY_SOURCES) -> int:
    """Check every Dockerfile under *root*. Non-zero when a COPY cannot resolve.

    *min_sources* is the vacuity floor (see MIN_COPY_SOURCES); the self-test
    fixtures are tiny by design and pass 1.
    """

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
    if checked < min_sources:
        say(
            f"\ncheck-build-context: WALKED {checked} COPY source(s) of at least "
            f"{min_sources} across {len(dockerfiles)} Dockerfile(s) — the walk "
            "found (almost) nothing, so 'every COPY resolves' is vacuously true. "
            "Either the COPY parser stopped matching, or the floor needs moving."
        )
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

        before = run(root, quiet=True, min_sources=1)
        print(f"  {'ok  ' if before == 1 else 'FAIL'} unnegated COPY source → exit 1")

        (root / ".dockerignore").write_text(
            _SELF_TEST_IGNORE + "!scripts/forgotten.py\n"
        )
        after = run(root, quiet=True, min_sources=1)
        print(f"  {'ok  ' if after == 0 else 'FAIL'} negation added → exit 0")

        # NON-VACUITY: the fixture above resolves 2 sources cleanly, so asking
        # for 3 is the "walked fewer than the floor" case with nothing else
        # wrong — a gate that cannot fail here reports a disarmed parser as a
        # clean build context.
        under = run(root, quiet=True, min_sources=3)
        print(f"  {'ok  ' if under == 1 else 'FAIL'} fewer than the floor → exit 1")

        # NON-VACUITY: a Dockerfile the walk parses but finds no COPY in. This
        # is the shape a broken `_COPY` regex takes, and it used to exit 0
        # printing "0 COPY source(s) reach the build context".
        (root / "Dockerfile").write_text("FROM scratch\nRUN true\n")
        empty = run(root, quiet=True, min_sources=1)
        print(f"  {'ok  ' if empty == 1 else 'FAIL'} a walk examining nothing → exit 1")

    if before == 1 and after == 0 and under == 1 and empty == 1:
        print("\ncheck-build-context: self-test passed (4 checks) — the gate can fail.")
        return 0
    print("\ncheck-build-context: SELF-TEST FAILED — this gate proves nothing.")
    return 1


# ---------------------------------------------------------------------------
# Second check: every workspace member a service DEPENDS ON is in the context.
#
# The check above asks "does this COPY resolve to something?", which is the
# failure `.dockerignore` produces. There is a second, independent way the same
# Dockerfile breaks, and the first check is blind to it by construction: a COPY
# that was never written at all. Adding a uv workspace member and wiring it into
# py-kit is an ordinary, correct change in `packages/**`; nothing in that diff
# touches `deploy/**`, so nothing suggests the image needs a new line — and the
# author cannot build the image to find out, because the Docker registry is
# policy-denied here.
#
# MEASURED on 2026-09-15, when `loft-wire` was split out of py-kit: layer 1
# (`uv sync --no-install-workspace`) resolves HAPPILY with the member absent, so
# the obvious probe says everything is fine, and layer 2 dies with
#   error: Failed to determine installation plan
#     Caused by: Distribution not found at: file:///app/packages/loft-wire
# on all three images, in `deploy-path` only. Reproduced both ways in a scratch
# context: exit 2 without the member's tree, exit 0 with it.
#
# So this derives the closure from pyproject.toml — for each service, which
# workspace members does it reach, transitively, through `[tool.uv.sources]`
# entries marked `workspace = true`? — and asserts each one's DIRECTORY is
# copied by the Dockerfile that installs it.
# ---------------------------------------------------------------------------

#: The Dockerfile that installs the Python workspace.
_WORKSPACE_DOCKERFILE = "deploy/docker/service.Dockerfile"

#: The directory every shipped service lives in. The entry points are DERIVED
#: from it rather than listed — see `_service_entry_points`.
_SERVICE_ROOT = "services/"


def _service_entry_points(root: Path) -> tuple[str, ...]:
    """Every workspace member under `services/` — i.e. one per service image.

    DERIVED, not written down, and that is the whole point. This used to be the
    literal tuple ``("loft-gateway", "loft-documents", "loft-geometry")``, so a
    FOURTH service added under ``services/`` would not have been an entry point,
    its private dependency closure would have been graded by nothing, and the
    gate would have said `ok` — while its image failed at layer 2 in
    `deploy-path`, the one place the failure is reachable.

    The existing empty-closure guard could not have caught that either: it fires
    only when ALL entry points vanish, which is the collapse case. A new service
    is a GROWTH the hardcoded list cannot see, exactly as a moved package is a
    shrink a total floor cannot see.

    This is the same argument the module docstring makes for the COPY lines
    themselves: a check that reads the same list the code reads can only tell
    you the list is self-consistent. Ask what SHOULD be in it, from somewhere
    else — here, the workspace manifest.
    """
    return tuple(
        sorted(
            name
            for name, directory in _workspace_members(root).items()
            if directory.as_posix().startswith(_SERVICE_ROOT)
        )
    )


def _read_toml(path: Path) -> dict[str, object]:
    import tomllib

    with path.open("rb") as handle:
        return dict(tomllib.load(handle))


def _table(parent: object, key: str) -> dict[str, object]:
    """`parent[key]` when both are tables, else an empty one.

    Every access below goes through this rather than chained `.get()` calls:
    `tomllib` returns `Any`-valued containers, and under pyright strict an
    unnarrowed chain is a wall of "partially unknown" errors. Narrowing once, in
    one place, also means a malformed pyproject.toml degrades to "no members
    found" — which the closure's own vacuity guard then REFUSES on, rather than
    crashing with a TypeError nobody can act on.
    """
    if not isinstance(parent, dict):
        return {}
    value = cast("dict[str, object]", parent).get(key)
    if not isinstance(value, dict):
        return {}
    return cast("dict[str, object]", value)


def _string_list(parent: dict[str, object], key: str) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in cast("list[object]", value) if isinstance(item, str)]


def _workspace_members(root: Path) -> dict[str, Path]:
    """Distribution name -> directory, for every uv workspace member."""
    import glob as _glob

    config = _read_toml(root / "pyproject.toml")
    workspace = _table(_table(config, "tool"), "uv")
    patterns = _string_list(_table(workspace, "workspace"), "members")
    members: dict[str, Path] = {}
    for pattern in patterns:
        for match in sorted(_glob.glob(str(root / pattern))):
            manifest = Path(match) / "pyproject.toml"
            if not manifest.is_file():
                continue
            name = _table(_read_toml(manifest), "project").get("name")
            if isinstance(name, str):
                members[name] = Path(match).relative_to(root)
    return members


def _requires(root: Path, directory: Path) -> set[str]:
    """Distribution names this member depends on (PEP 508 names only)."""
    project = _table(_read_toml(root / directory / "pyproject.toml"), "project")
    names: set[str] = set()
    for requirement in _string_list(project, "dependencies"):
        # Cut at the first character that cannot be part of a name.
        name = re.split(r"[\s<>=!~;\[\(]", requirement.strip(), maxsplit=1)[0]
        if name:
            names.add(name)
    return names


def workspace_closure(root: Path, entry_points: tuple[str, ...]) -> dict[str, Path]:
    """Every workspace member reachable from *entry_points*, transitively."""
    members = _workspace_members(root)
    seen: dict[str, Path] = {}
    queue = [name for name in entry_points if name in members]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen[name] = members[name]
        for dependency in _requires(root, members[name]):
            if dependency in members and dependency not in seen:
                queue.append(dependency)
    return seen


def check_workspace_members(
    root: Path, quiet: bool = False, entry_points: tuple[str, ...] = ()
) -> int:
    def say(line: str) -> None:
        if not quiet:
            print(line)

    dockerfile = root / _WORKSPACE_DOCKERFILE
    if not dockerfile.is_file():
        say(f"check-build-context: {_WORKSPACE_DOCKERFILE} is missing — REFUSING.")
        return 1

    entry_points = entry_points or _service_entry_points(root)
    if not entry_points:
        # VACUITY, one level up from the closure guard below: if the DERIVATION
        # finds no services, every closure is empty and every verdict is true of
        # nothing. Distinguished from the closure case because the fix is
        # different — this one means the workspace manifest or `services/`
        # moved, not that a package name is wrong.
        say(
            "check-build-context: no uv workspace member lives under "
            f"`{_SERVICE_ROOT}` — either [tool.uv.workspace].members no longer "
            "covers the services or they moved. Deriving zero entry points "
            "would make every 'all members are copied' verdict vacuous."
        )
        return 1

    closure = workspace_closure(root, entry_points)
    if not closure:
        # VACUITY. An empty closure makes "every member is copied" trivially
        # true, which is precisely how this gate would go quiet if the workspace
        # config moved or the entry-point names were renamed.
        say(
            "check-build-context: the workspace closure of "
            f"{', '.join(entry_points)} is EMPTY — either pyproject.toml's "
            "[tool.uv.workspace] moved or those package names no longer exist. "
            "A gate that walks nothing cannot fail."
        )
        return 1

    copied = {source for _, source in copy_sources(dockerfile)}
    say(f"\n{_WORKSPACE_DOCKERFILE} — uv workspace closure")
    # Print the DERIVED entry points: a derivation nobody can see is a list
    # nobody can check, and adding a service should visibly change this line.
    say(f"  entry points (derived from `{_SERVICE_ROOT}`): {', '.join(entry_points)}")
    failures: list[str] = []
    for name, directory in sorted(closure.items()):
        posix = directory.as_posix()
        # The member's TREE must be copied, not merely its manifest: layer 2
        # builds a wheel from it. `COPY services services` covers every service.
        if posix in copied or posix.rsplit("/", 1)[0] in copied:
            say(f"  ok   {name} ({posix})")
            continue
        message = (
            f"{_WORKSPACE_DOCKERFILE} never COPYs `{posix}`, but `{name}` is in "
            f"the dependency closure of {', '.join(entry_points)} — layer 2's "
            "`uv sync --no-editable` will fail with `Distribution not found at: "
            f"file:///app/{posix}` on every service image. Layer 1 will NOT "
            "catch it: --no-install-workspace resolves without the member."
        )
        say(f"  FAIL {message}")
        failures.append(message)

    if failures:
        say(
            f"\ncheck-build-context: FAILED ({len(failures)} workspace member(s) "
            "missing from the image build context)"
        )
        return 1
    say(
        f"check-build-context: all {len(closure)} workspace member(s) in the "
        "service closure reach the build context"
    )
    return 0


def _workspace_self_test() -> int:
    """Reproduce the loft-wire defect: a member nobody added a COPY for."""
    import tempfile

    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "deploy/docker").mkdir(parents=True)
        (root / "packages/kit").mkdir(parents=True)
        (root / "packages/wire").mkdir(parents=True)
        (root / "services/gateway").mkdir(parents=True)
        (root / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["services/*", "packages/kit", '
            '"packages/wire"]\n'
        )
        (root / "packages/kit/pyproject.toml").write_text(
            '[project]\nname = "loft-py-kit"\ndependencies = ["loft-wire", '
            '"fastapi>=0.115"]\n'
        )
        (root / "packages/wire/pyproject.toml").write_text(
            '[project]\nname = "loft-wire"\ndependencies = ["pydantic>=2"]\n'
        )
        (root / "services/gateway/pyproject.toml").write_text(
            '[project]\nname = "loft-gateway"\ndependencies = ["loft-py-kit"]\n'
        )

        without = (
            "FROM scratch\nCOPY packages/kit packages/kit\nCOPY services services\n"
        )
        (root / "deploy/docker/service.Dockerfile").write_text(without)
        gateway = ("loft-gateway",)
        before = check_workspace_members(root, quiet=True, entry_points=gateway)
        results.append(("a transitive member with no COPY -> exit 1", before == 1))

        (root / "deploy/docker/service.Dockerfile").write_text(
            without + "COPY packages/wire packages/wire\n"
        )
        after = check_workspace_members(root, quiet=True, entry_points=gateway)
        results.append(("…and adding the COPY -> exit 0", after == 0))

        # VACUITY: an entry point that is not a member walks nothing, which
        # would make every "all members are copied" verdict true of no members.
        empty = check_workspace_members(root, quiet=True, entry_points=("nope",))
        results.append(("an empty closure REFUSES rather than passing", empty == 1))

        # THE DERIVATION CONTROL. A FOURTH service, with a private dependency
        # that nothing COPYs. With entry points DERIVED from `services/` this
        # must be graded and REFUSE; with the old hardcoded triple it was not
        # an entry point at all, its closure was never walked, and the gate
        # said `ok` while that image failed at layer 2.
        #
        # Note the existing guards cannot stand in for this: the closure is
        # non-empty (the three known services are still there) and the total
        # is healthy, so neither vacuity check fires. Growth is invisible to a
        # guard that only detects collapse.
        (root / "services/reports").mkdir(parents=True, exist_ok=True)
        (root / "packages/report-kit").mkdir(parents=True, exist_ok=True)
        # The new package must be a declared workspace member, or the closure
        # would skip it and this control would pass for the wrong reason —
        # a probe aimed past the thing it is testing.
        (root / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["services/*", "packages/kit", '
            '"packages/wire", "packages/report-kit"]\n'
        )
        (root / "packages/report-kit/pyproject.toml").write_text(
            '[project]\nname = "loft-report-kit"\ndependencies = ["pydantic>=2"]\n'
        )
        (root / "services/reports/pyproject.toml").write_text(
            '[project]\nname = "loft-reports"\ndependencies = ["loft-report-kit"]\n'
        )
        derived = _service_entry_points(root)
        results.append(
            (
                "a new services/ member IS derived as an entry point "
                f"(got {', '.join(derived) or 'nothing'})",
                "loft-reports" in derived and "loft-gateway" in derived,
            )
        )
        # `COPY services services` covers the new service's own tree, so the
        # only uncopied member is its private dependency — which is exactly the
        # shape of the real `loft-wire` defect.
        grown = check_workspace_members(root, quiet=True)
        results.append(("…and its uncopied private dependency REFUSES", grown == 1))

        (root / "deploy/docker/service.Dockerfile").write_text(
            without
            + "COPY packages/wire packages/wire\n"
            + "COPY packages/report-kit packages/report-kit\n"
        )
        healed = check_workspace_members(root, quiet=True)
        results.append(("…and adding THAT COPY -> exit 0", healed == 0))

    for label, passed in results:
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
    if all(passed for _, passed in results):
        print(
            "\ncheck-build-context: workspace self-test passed "
            f"({len(results)} checks) — the gate can fail."
        )
        return 0
    print("\ncheck-build-context: WORKSPACE SELF-TEST FAILED.")
    return 1


def main(argv: list[str]) -> int:
    # BOTH checks always run and the statuses are combined, rather than
    # `a() or b()`: short-circuiting would let a `.dockerignore` failure hide a
    # missing workspace member, so the fix for the first would be followed by a
    # second red run for a defect that was already present and already knowable.
    if "--self-test" in argv:
        first = self_test()
        second = _workspace_self_test()
        return max(first, second)
    first = run(REPO_ROOT)
    second = check_workspace_members(REPO_ROOT)
    return max(first, second)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
