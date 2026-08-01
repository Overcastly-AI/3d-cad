#!/usr/bin/env python3
"""Build the mirrored corresponding-source bundle for the LGPL components we
redistribute (LIC-2; docs/LICENSING.md §7).

    just corresponding-source                # verify + build into dist/
    just corresponding-source-record         # same, but re-pin missing digests

What it does, in order, and why the order matters:

  1. **Checks the manifest against the installed environment.** The pinned
     versions in ``deploy/licenses/corresponding-source.json`` are checked
     against the binaries in this venv (see ``corresponding_source.py``). If a
     wheel bump moved OCCT, the run stops here — building a bundle for 7.9.3
     while shipping 7.9.4 would produce a *confidently wrong* compliance
     artefact, which is worse than none at all.
  2. **Fetches each artefact from its pinned upstream** and verifies its
     SHA-256 against the recorded value. A mismatch is fatal: it means either
     upstream mutated a supposedly immutable file, or we are being served
     something else.
  3. **Assembles a deterministic tar.gz** with a MANIFEST, SHA256SUMS, the
     licence texts, and a README telling a recipient how to actually relink.
  4. **Prints the command the maintainer must run to publish it.** It does NOT
     publish. Attaching a release asset is an outward-facing act and belongs to
     a human with the repository's credentials, not to a build script.

Honesty rules baked in:
  * A digest that has never been computed is ``null``, not a guess. ``--record``
    computes it from bytes actually received and writes it back for review.
  * If ANY artefact is missing or unverified, no bundle is written and the exit
    code is 2. There is no "mostly complete" corresponding source.
  * OCCT is fetched as a git clone verified by COMMIT, never as GitHub's
    ``/archive/refs/tags/`` tarball: those are generated on demand and their
    bytes have changed under people before, so a sha256 pinned to one is a gate
    that fails for the wrong reason. The archive we then pack is built
    byte-deterministically from the commit, so its digest is reproducible —
    two independent clone-and-pack runs gave byte-identical archives.
  * The clone is checked against the tree's OWN declared version
    (``adm/cmake/version.cmake``), not against the tag name. Tags are labels
    and can be moved; comparing a tag to itself is not a check.

Environment note, measured rather than assumed: in the Loft dev container the
GitHub *release-asset* URL for OCCT is 403 (policy denial), but ``git clone``
over HTTPS works, and PyPI and archive.ubuntu.com are directly reachable. So
every leg runs there. If you hit a blocked leg elsewhere, the script names it
and refuses to write a bundle rather than writing a partial one.

Exit codes: 0 bundle complete and verified, 1 usage/manifest error, 2 the
bundle could not be completed (fetch failed, digest mismatch, version drift).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corresponding_source import (
    REPO_ROOT,
    JsonDict,
    ManifestError,
    load_manifest,
    manifest_path,
    verify_versions,
)

# Fixed timestamp for every archive member so the bundle is byte-reproducible
# from the same inputs. 2020-01-01T00:00:00Z, arbitrary but stable.
FIXED_MTIME = 1577836800
DEFAULT_OUT = REPO_ROOT / "dist" / "corresponding-source"
LICENCE_TEXT_DIR = REPO_ROOT / "deploy" / "licenses"


@dataclass
class Artefact:
    component_id: str
    spec: JsonDict
    path: Path | None = None
    sha256: str = ""
    ok: bool = False
    problem: str = ""
    recorded: list[str] = field(default_factory=list[str])

    @property
    def filename(self) -> str:
        return str(self.spec.get("filename") or self.spec.get("archive") or "?")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "loft-lic2/1"})
    with urllib.request.urlopen(request, timeout=300) as response:
        dest.write_bytes(response.read())
    if dest.stat().st_size == 0:
        # Seen for real: the legacy /packages/source/p/<name>/ PyPI path
        # returned a zero-byte body with a success status through an egress
        # proxy. A naive fetch would have mirrored an empty file as "the
        # corresponding source" and every downstream digest check would have
        # agreed with itself.
        raise OSError(
            f"{url} returned a ZERO-BYTE body; refusing to treat it as source"
        )


def fetch_url(artefact: Artefact, downloads: Path) -> None:
    spec = artefact.spec
    dest = downloads / artefact.filename
    urls: list[str] = [str(spec["url"])]
    if spec.get("fallback_url"):
        urls.append(str(spec["fallback_url"]))
    errors: list[str] = []
    for url in urls:
        try:
            print(f"    fetching {url}")
            download(url, dest)
            artefact.path = dest
            return
        except (urllib.error.URLError, OSError) as exc:
            errors.append(f"{url}: {exc}")
    artefact.problem = "; ".join(errors)


def fetch_git(artefact: Artefact, downloads: Path) -> None:
    """Clone at the pinned tag, verify the commit, repack deterministically."""
    spec = artefact.spec
    repo, tag = str(spec["repo"]), str(spec["tag"])
    pinned_commit = spec.get("commit")
    if shutil.which("git") is None:
        artefact.problem = "git is not installed"
        return
    with tempfile.TemporaryDirectory(prefix="loft-cs-git-") as tmp:
        checkout = Path(tmp) / "src"
        print(f"    cloning {repo} at {tag}")
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", tag, repo, str(checkout)],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            artefact.problem = (
                f"git clone {repo} @ {tag} failed: "
                f"{(clone.stderr or clone.stdout).strip().splitlines()[-1:] or ['?']}"
            )
            return
        head = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if pinned_commit and head != pinned_commit:
            # Tags are mutable; commits are not. This is the check that makes
            # "the exact source" mean something.
            artefact.problem = (
                f"tag {tag} now points at {head} but the manifest pins "
                f"{pinned_commit}. An upstream tag was moved — do NOT publish "
                "until a human has established which tree we actually built."
            )
            return
        # A shallow clone silently omits submodule content, so an archive built
        # from one would look complete and not be. OCCT has no submodules
        # today; if that changes this must be fixed, not ignored.
        if (checkout / ".gitmodules").exists():
            artefact.problem = (
                f"{repo} @ {tag} has submodules and this is a --depth 1 clone, "
                "so their content is NOT in the tree. Fetch them before "
                "packing; an incomplete source archive is a false one."
            )
            return
        symlinks = [
            p.relative_to(checkout).as_posix()
            for p in checkout.rglob("*")
            if p.is_symlink() and ".git" not in p.relative_to(checkout).parts
        ]
        if symlinks:
            artefact.problem = (
                f"{repo} @ {tag} contains symlinks ({symlinks[:3]}…); the "
                "deterministic packer only stores regular files, so it would "
                "drop them. Teach pack_directory about symlinks rather than "
                "shipping a tree with holes in it."
            )
            return
        # Prove the tree IS the version we claim, from the tree's own build
        # metadata — not from the tag name, which is just a label a human typed.
        problem = _verify_tree_version(spec, checkout)
        if problem:
            artefact.problem = problem
            return
        if not pinned_commit:
            artefact.recorded.append(f"commit={head}")
            spec["commit"] = head
            spec["commit_source"] = (
                f"git rev-parse HEAD of {repo} @ {tag}, recorded by "
                "scripts/fetch-corresponding-source.py"
            )
        dest = downloads / artefact.filename
        pack_directory(checkout, dest, arcname=f"occt-{tag}", exclude={".git"})
        artefact.path = dest


def _verify_tree_version(spec: JsonDict, checkout: Path) -> str:
    """Read the version out of the cloned source and compare it to the pin.

    Tags are labels; the version constants in the build system are what the
    binaries were actually compiled from. Checking the label against itself
    would be no check at all.
    """
    verify: JsonDict = spec.get("verify_version") or {}
    if not verify:
        return ""
    target = checkout / str(verify["file"])
    if not target.is_file():
        return (
            f"{verify['file']} is missing from the checkout, so the tree's own "
            "declared version cannot be read. Upstream moved it; find it and "
            "update the manifest's verify_version block."
        )
    text = target.read_text(encoding="utf-8", errors="replace")
    parts: list[str] = []
    for pattern in cast(list[str], verify["patterns"]):
        match = re.search(pattern, text)
        if match is None:
            return f"{verify['file']} does not match {pattern!r}"
        parts.append(match.group(1))
    found = str(verify.get("join", ".")).join(parts)
    if found != verify["expect"]:
        return (
            f"{verify['file']} declares version {found}, the manifest expects "
            f"{verify['expect']}. The tag points at a tree that is not the "
            "release we ship — do not publish this as corresponding source."
        )
    return ""


# ---------------------------------------------------------------------------
# Deterministic packing
# ---------------------------------------------------------------------------
def _reset(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = FIXED_MTIME
    info.mode = 0o755 if info.isdir() or (info.mode & 0o100) else 0o644
    return info


def _write_tar_gz(members: list[tuple[str, Path]], dest: Path) -> None:
    """Sorted names, zeroed ownership, fixed mtimes, gzip mtime 0 — so the same
    inputs give the same bytes on any machine."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for arcname, path in sorted(members):
            info = tar.gettarinfo(str(path), arcname=arcname)
            _reset(info)
            if info.isfile():
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
            else:
                tar.addfile(info)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with (
        dest.open("wb") as out,
        gzip.GzipFile(fileobj=out, mode="wb", mtime=0, compresslevel=9) as gz,
    ):
        gz.write(raw.getvalue())


def pack_directory(
    root: Path, dest: Path, arcname: str, exclude: set[str] | None = None
) -> None:
    exclude = exclude or set()
    members = [
        (f"{arcname}/{path.relative_to(root).as_posix()}", path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and not (exclude & set(path.relative_to(root).parts))
    ]
    _write_tar_gz(members, dest)


# ---------------------------------------------------------------------------
# Bundle documents
# ---------------------------------------------------------------------------
def render_manifest_md(
    manifest: JsonDict, artefacts: list[Artefact], release: str
) -> str:
    lines = [
        f"# Corresponding source for Loft {release}",
        "",
        "Machine-readable pins: `corresponding-source.json` beside this file.",
        "Digests: `SHA256SUMS` (`sha256sum -c SHA256SUMS`).",
        "",
        "| component | version | licence | file |",
        "| --------- | ------- | ------- | ---- |",
    ]
    components = cast(list[JsonDict], manifest["components"])
    by_component = {str(c["id"]): c for c in components}
    for artefact in artefacts:
        component = by_component[artefact.component_id]
        lines.append(
            f"| {component.get('name', component['id'])} "
            f"| `{component['version']}` "
            f"| {component.get('licence', '?')} "
            f"| `{artefact.component_id}/{artefact.filename}` |"
        )
    lines += [
        "",
        "## Provenance",
        "",
    ]
    for component in components:
        lines.append(f"### {component.get('name', component['id'])}")
        lines.append("")
        lines.append(f"- Shipped version: **{component['version']}**")
        lines.append(f"- Reaches the image via: {component.get('arrives_via', '?')}")
        lines.append(f"- Obligation: {component.get('obligation', '?')}")
        for spec in cast(list[JsonDict], component["artefacts"]):
            if spec.get("kind") == "git":
                lines.append(
                    f"- `{spec.get('archive')}` — repacked from "
                    f"{spec['repo']} tag `{spec['tag']}`, commit "
                    f"`{spec.get('commit') or 'UNRECORDED'}`"
                )
            else:
                lines.append(f"- `{spec.get('filename')}` — {spec.get('url')}")
        lines.append("")
    return "\n".join(lines) + "\n"


BUNDLE_README = """# Corresponding source — Loft {release}

This archive is the **corresponding source** for the LGPL-2.1 libraries bundled
in Loft's published container images. It exists so that LGPL-2.1 §6(d) is
satisfied from the same place the object code is offered, rather than by
pointing you at a third party who may retire a URL.

Loft itself is MIT-licensed; its complete source is at
<https://github.com/Overcastly-AI/3d-cad>. Nothing here is Loft's own code.

## Verifying this bundle

```sh
sha256sum -c SHA256SUMS
```

`corresponding-source.json` records, for every artefact, where it came from and
how its digest was established. The Loft repository carries the same file, so
you can check that what you received is what the project claims to have
published — compare it against
`deploy/licenses/corresponding-source.json` at the tag `{release}`.

## Relinking

The LGPL requires that you be able to modify these libraries and relink them
into the work. Loft loads all of them through ordinary shared-object mechanisms
(`DT_NEEDED` + `RUNPATH` for OCCT, a CPython extension module for planegcs), so
relinking does not require rebuilding Loft:

1. Build the component from the source here, keeping its SONAME and ABI.
2. Replace the corresponding `.so` inside the image — they live in the Python
   environment at `/app/.venv/lib/python3.*/site-packages/`, in
   `cadquery_ocp_novtk.libs/` (OCCT, LibRaw) and `planegcs/` (planegcs).
3. Run the image as usual. Nothing in Loft's own code needs to change.

The image also carries `/app/licenses/`, including `THIRD-PARTY.md` (generated
from the installed environment at build time), the full licence texts, and the
§6(c) written offer.

## One deliberate difference from upstream

The geometry image ships a **GPL-free replacement** for `libjbig`, not
jbigkit. The upstream OCP wheel vendors jbigkit (GPL-2.0-or-later) because its
build machine had it; Loft is MIT and cannot redistribute it, and it is
unreachable dead weight (Loft performs no TIFF I/O). The replacement is
original MIT work in the Loft repository at
`deploy/docker/licence/jbig-stub.c`; it exports the ten `jbg_*` symbols
`libtiff` imports and aborts loudly if any is ever called. It contains no
jbigkit code, so no jbigkit source is included here or owed.
"""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def default_roots() -> list[Path]:
    venv = REPO_ROOT / ".venv"
    site = sorted(venv.glob("lib/python3.*/site-packages"))
    return site or [venv]


def run(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"fetch-corresponding-source: {exc}", file=sys.stderr)
        return 1
    path = manifest_path(args.manifest)
    print(f"fetch-corresponding-source: manifest {path}")

    roots = args.root or default_roots()
    failures, detections = verify_versions(manifest, roots)
    for component_id, detection in detections:
        print(f"  {component_id:<10} {detection.status:<7} {detection.version or '-'}")
    if failures:
        for failure in failures:
            print(f"\nFAIL {failure}", file=sys.stderr)
        print(
            "\nRefusing to build a bundle for versions this environment does not "
            "ship. A confidently wrong compliance artefact is worse than none.",
            file=sys.stderr,
        )
        return 2

    selected = [
        c for c in manifest["components"] if not args.only or c["id"] in args.only
    ]
    if args.only:
        unknown = set(args.only) - {c["id"] for c in manifest["components"]}
        if unknown:
            print(f"unknown component id(s): {sorted(unknown)}", file=sys.stderr)
            return 1

    out = args.out
    downloads = out / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)

    artefacts: list[Artefact] = []
    for component in selected:
        print(f"\n  {component['id']} {component['version']}")
        for spec in component["artefacts"]:
            artefact = Artefact(component_id=component["id"], spec=spec)
            artefacts.append(artefact)
            if spec.get("kind") == "git":
                fetch_git(artefact, downloads)
            else:
                fetch_url(artefact, downloads)
            if artefact.path is None:
                print(f"    UNAVAILABLE {artefact.filename}: {artefact.problem}")
                continue
            artefact.sha256 = sha256_file(artefact.path)
            expected = spec.get("sha256")
            if expected is None:
                if args.record:
                    spec["sha256"] = artefact.sha256
                    spec["sha256_source"] = (
                        "computed by scripts/fetch-corresponding-source.py --record"
                    )
                    artefact.recorded.append(f"sha256={artefact.sha256}")
                    artefact.ok = True
                    print(f"    RECORDED {artefact.filename} {artefact.sha256}")
                else:
                    artefact.problem = (
                        "no sha256 recorded in the manifest; re-run with "
                        "--record and review the diff before committing"
                    )
                    print(
                        f"    UNPINNED {artefact.filename} (computed {artefact.sha256})"
                    )
            elif expected != artefact.sha256:
                artefact.problem = (
                    f"sha256 mismatch: manifest says {expected}, the bytes we "
                    f"received hash to {artefact.sha256}. Either an immutable "
                    "upstream file changed, or this download is not what it "
                    "claims. Do not publish."
                )
                print(f"    MISMATCH {artefact.filename}")
            else:
                artefact.ok = True
                print(f"    ok       {artefact.filename} {artefact.sha256[:16]}…")

    if args.record:
        recorded = [a for a in artefacts if a.recorded]
        if recorded:
            serialisable = {k: v for k, v in manifest.items() if k != "_path"}
            path.write_text(
                json.dumps(serialisable, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"\nfetch-corresponding-source: re-pinned {path}")
            for artefact in recorded:
                print(f"  {artefact.filename}: {', '.join(artefact.recorded)}")
            print(
                "  REVIEW THIS DIFF before committing. A digest is a claim about "
                "what upstream published; it is only worth what the review is."
            )

    unresolved = [a for a in artefacts if not a.ok]
    if unresolved:
        print("\nfetch-corresponding-source: BUNDLE NOT BUILT", file=sys.stderr)
        for artefact in unresolved:
            print(
                f"  {artefact.component_id}/{artefact.filename}: {artefact.problem}",
                file=sys.stderr,
            )
        print(
            "\nA partial corresponding-source bundle is not a lesser compliance "
            "artefact, it is a false one. Fix the above (github.com is blocked "
            "in the Loft dev container — run this where egress is ordinary) and "
            "re-run. docs/LICENSING.md §7.",
            file=sys.stderr,
        )
        return 2

    if args.only:
        print(
            "\nfetch-corresponding-source: --only was given, so this is a partial "
            "run; no bundle written. Re-run without --only to build the release "
            "artefact."
        )
        return 0

    release = args.release
    bundle_name = manifest["bundle"]["name_template"].format(release=release)
    stem = bundle_name.removesuffix(".tar.gz")
    with tempfile.TemporaryDirectory(prefix="loft-cs-stage-") as tmp:
        stage = Path(tmp) / stem
        stage.mkdir(parents=True)
        for artefact in artefacts:
            target = stage / artefact.component_id / artefact.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            assert artefact.path is not None
            shutil.copy2(artefact.path, target)
        (stage / "README.md").write_text(
            BUNDLE_README.format(release=release), encoding="utf-8"
        )
        (stage / "MANIFEST.md").write_text(
            render_manifest_md(manifest, artefacts, release), encoding="utf-8"
        )
        shutil.copy2(path, stage / "corresponding-source.json")
        licences = stage / "licenses"
        licences.mkdir()
        for text in sorted(LICENCE_TEXT_DIR.glob("*.txt")):
            shutil.copy2(text, licences / text.name)
        for doc in ("CORRESPONDING-SOURCE.md",):
            source = LICENCE_TEXT_DIR / doc
            if source.is_file():
                shutil.copy2(source, licences / doc)
        sums = "".join(
            f"{sha256_file(p)}  {p.relative_to(stage).as_posix()}\n"
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        )
        (stage / "SHA256SUMS").write_text(sums, encoding="utf-8")

        bundle = out / bundle_name
        pack_directory(stage, bundle, arcname=stem)

    digest = sha256_file(bundle)
    print(f"\nfetch-corresponding-source: {bundle}")
    print(f"  sha256 {digest}")
    print(f"  {bundle.stat().st_size} bytes, {len(artefacts)} upstream artefact(s)")
    print(
        "\nNOT PUBLISHED — that is a human decision. To attach it to the release "
        "that publishes the images:\n"
        f"  gh release upload {release} {bundle} --clobber\n"
        "Then follow the post-publication check in docs/LICENSING.md §7 "
        "(the written offer must resolve to a file that exists)."
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and package the corresponding source for Loft's LGPL "
            "components. Prepares a release asset; never publishes it."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="path to corresponding-source.json (default: deploy/licenses/).",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="installed environment to check versions against; repeatable.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).",
    )
    parser.add_argument(
        "--release",
        default=os.environ.get("LOFT_RELEASE", "dev"),
        help="release tag the bundle is named for (default: $LOFT_RELEASE or 'dev').",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="ID",
        help="fetch only these component ids; skips bundle assembly.",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="write digests (and the resolved git commit) back into the "
        "manifest for review. Never overwrites a digest that is already "
        "recorded — a mismatch is a failure, not a re-pin.",
    )
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
