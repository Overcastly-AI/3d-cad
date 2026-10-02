#!/usr/bin/env python3
"""The vendored planegcs is the upstream sdist plus our patch, and nothing else.

Why this exists (SKETCH-SOLVE-HEAP-ORDER, docs/RESEARCH.md §2)
-------------------------------------------------------------
planegcs 0.8.0 ordered parts of a solve by memory ADDRESS, so one sketch could
solve differently twice in one process. Loft builds planegcs from
``vendor/planegcs/`` with ``vendor/planegcs-loft.patch`` applied. That tree is
LGPL-2.1 code we redistribute in the geometry image, and the corresponding
source we offer is "the PyPI sdist plus this patch"
(deploy/licenses/corresponding-source.json). The offer is only true if the
tree really is that, so this gate checks it offline, on every ``just lint``:

  1. reverse-apply the patch to a copy of the tree;
  2. the result must be byte-identical, file for file, to
     ``vendor/planegcs-upstream.sha256`` (the pristine sdist's files).

An edit made straight in the tree without updating the patch, a patch that no
longer applies, or a stray file (a ``build/`` directory included) all fail.

The offline check trusts the hash list, so an edit to a vendored file AND to
the list would pass it. ``--upstream SDIST`` closes that, and CI runs it on
every push (the sdist is cached by its pinned digest): the sdist must hash to
the digest pinned in the licence manifest, and every listed file must be an
sdist member with exactly that hash. The tree keeps 27 of the sdist's 77
files, the build inputs (pyproject.toml, CMakeLists.txt, LICENSE, README.md,
src/, python/); the sdist's tests, docs and examples are not vendored.

    python3 scripts/check-vendored-planegcs.py
    python3 scripts/check-vendored-planegcs.py --upstream planegcs-0.8.0.tar.gz
    python3 scripts/check-vendored-planegcs.py --self-test   # prove it can fail

Stdlib only, plus GNU ``patch``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR = REPO_ROOT / "vendor"
TREE = VENDOR / "planegcs"
PATCH = VENDOR / "planegcs-loft.patch"
HASHES = VENDOR / "planegcs-upstream.sha256"
MANIFEST = REPO_ROOT / "deploy" / "licenses" / "corresponding-source.json"
SDIST_PREFIX = "planegcs-0.8.0/"
PATCH_REVERSE = ("patch", "-R", "-p1", "-s", "-f", "--no-backup-if-mismatch")
#: The only litter tolerated: bytecode, if something imports python/planegcs
#: from the tree. `uv sync` builds out of tree (scikit-build-core's build dir
#: is temporary) and leaves nothing behind, so a `build/` directory is drift
#: like any other stray file.
IGNORED_PARTS = frozenset({"__pycache__"})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_hashes(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split(maxsplit=1)
            out[rel.strip()] = digest
    return out


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): _sha256(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and not (IGNORED_PARTS & set(p.relative_to(root).parts))
    }


def compare(found: dict[str, str], expected: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for rel in sorted(expected.keys() - found.keys()):
        problems.append(f"missing upstream file {rel}")
    for rel in sorted(found.keys() - expected.keys()):
        problems.append(f"file not in the upstream sdist: {rel}")
    for rel in sorted(found.keys() & expected.keys()):
        if found[rel] != expected[rel]:
            problems.append(
                f"{rel} differs from upstream by more than the patch (edit the "
                f"tree AND regenerate {PATCH.name}, never one of them)"
            )
    return problems


def check_tree(tree: Path, patch: Path, hashes: Path) -> list[str]:
    """Problems with *tree* as 'upstream + patch'; empty means it is exactly that."""
    if shutil.which("patch") is None:
        return ["GNU patch is not installed; cannot verify the vendored tree"]
    with tempfile.TemporaryDirectory(prefix="loft-planegcs-") as tmp:
        work = Path(tmp) / "tree"
        shutil.copytree(
            tree, work, ignore=shutil.ignore_patterns(*sorted(IGNORED_PARTS))
        )
        result = subprocess.run(
            [*PATCH_REVERSE, "-d", str(work)],
            input=patch.read_bytes(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).decode(errors="replace").strip()
            return [f"{patch.name} does not reverse-apply to the tree: {detail}"]
        return compare(tree_hashes(work), read_hashes(hashes))


def check_upstream(sdist: Path, hashes: Path) -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pinned = next(
        a["sha256"]
        for c in manifest["components"]
        if c["id"] == "planegcs"
        for a in c["artefacts"]
        if a.get("filename") == "planegcs-0.8.0.tar.gz"
    )
    actual = _sha256(sdist.read_bytes())
    if actual != pinned:
        return [f"{sdist} hashes to {actual}, the manifest pins {pinned}"]
    expected = read_hashes(hashes)
    found: dict[str, str] = {}
    with tarfile.open(sdist) as tar:
        for member in tar.getmembers():
            rel = member.name.removeprefix(SDIST_PREFIX)
            if member.isfile() and rel in expected:
                handle = tar.extractfile(member)
                assert handle is not None
                found[rel] = _sha256(handle.read())
    return [
        f"{hashes.name} does not describe the pinned sdist: {problem}"
        for problem in compare(found, expected)
    ]


def self_test() -> int:
    failures: list[str] = []
    if check_tree(TREE, PATCH, HASHES):
        failures.append("the real tree must pass before the controls mean anything")
    with tempfile.TemporaryDirectory(prefix="loft-planegcs-st-") as tmp:
        bad = Path(tmp) / "planegcs"
        shutil.copytree(TREE, bad, ignore=shutil.ignore_patterns(*IGNORED_PARTS))
        # An unpatched-file edit: the commonest way the tree drifts.
        target = bad / "src" / "planegcs" / "Geo.cpp"
        target.write_bytes(target.read_bytes() + b"// drift\n")
        if not any("Geo.cpp" in p for p in check_tree(bad, PATCH, HASHES)):
            failures.append("an edit outside the patch was not caught")
        target.write_bytes(target.read_bytes().removesuffix(b"// drift\n"))
        # A patched file edited without regenerating the patch.
        target = bad / "src" / "planegcs" / "SubSystem.cpp"
        original = target.read_bytes()
        edited = original.replace(b"Changed by Loft", b"Edited by Loft", 1)
        if edited == original:
            failures.append("the patched-file control found nothing to edit")
        target.write_bytes(edited)
        if not check_tree(bad, PATCH, HASHES):
            failures.append("an edit inside a patched file was not caught")
        target.write_bytes(original)
        # A stray file, and a stray build/ directory.
        (bad / "src" / "extra.cpp").write_text("int x;\n")
        if not any("extra.cpp" in p for p in check_tree(bad, PATCH, HASHES)):
            failures.append("a file absent from the sdist was not caught")
        (bad / "src" / "extra.cpp").unlink()
        (bad / "src" / "build").mkdir()
        (bad / "src" / "build" / "GCS.cpp").write_text("int y;\n")
        if not any("build/GCS.cpp" in p for p in check_tree(bad, PATCH, HASHES)):
            failures.append("a stray build/ directory was not caught")
    for failure in failures:
        print(f"check-vendored-planegcs --self-test: FAIL {failure}", file=sys.stderr)
    if not failures:
        print("check-vendored-planegcs --self-test: ok (4 drifts caught, tree clean)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        return self_test()
    problems = check_tree(TREE, PATCH, HASHES)
    if argv[:1] == ["--upstream"] and len(argv) == 2:
        problems += check_upstream(Path(argv[1]), HASHES)
    elif argv:
        print(__doc__, file=sys.stderr)
        return 2
    for problem in problems:
        print(f"check-vendored-planegcs: FAIL {problem}", file=sys.stderr)
    if problems:
        return 1
    count = len(read_hashes(HASHES))
    print(f"check-vendored-planegcs: ok ({count} upstream files + the patch)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
