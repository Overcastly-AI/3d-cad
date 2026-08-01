"""Corresponding-source manifest: loading, and version detection from the
BINARIES WE ACTUALLY SHIP (LIC-2; docs/LICENSING.md §7).

Why this is a module and not two copies
---------------------------------------
Two callers need the same answer to "which version of OCCT / planegcs /
LibRaw is in this environment?":

  * ``scripts/check-licences.py`` — the gate. It must fail LOUDLY when a wheel
    bump moves a version out from under the pinned manifest, because at that
    moment the written offer in ``CORRESPONDING-SOURCE.md`` starts describing
    source that does not correspond to the binaries.
  * ``scripts/fetch-corresponding-source.py`` — the release tool. It must
    refuse to build a bundle for versions we are not shipping.

Two implementations of that would drift, and the drift would be silent in the
direction that matters. So it lives here once.

Stdlib only, no side effects on import: the gate runs INSIDE the runtime image,
which contains nothing but the service venv. Both this file and the manifest
are copied to ``/app/tools`` / ``/app/licenses`` by the image build.

Detection is per-component and deliberately different for each, because the
honest signal is different for each:

  ``so-version``      OCCT stamps its release into every SONAME tail
                      (``libTKernel-<hash>.so.7.9.3``). All 46 must agree.
  ``dist-info``       planegcs is a wheel we depend on directly; its
                      ``METADATA`` version is authoritative.
  ``auditwheel-sbom`` LibRaw's SONAME (``.so.19.0.2``) is NOT its release
                      version, so filename parsing would pin the wrong source
                      with total confidence. auditwheel records the real Ubuntu
                      source-package version (``0.19.5-1ubuntu1.4``) in a
                      CycloneDX SBOM inside the wheel's dist-info.

A component that is ABSENT is not a failure — we stopped shipping it, so the
obligation lapsed. A component that is present but whose version cannot be
determined IS a failure: that is detection rotting into a rubber stamp, which
is the same class of defect as the metadata-only scan LIC-3 replaced.

The GCC runtime libraries (LIC-4) are handled separately, at the bottom of this
file, because the question about them is a different one. They are not in the
mirrored bundle — the GCC Runtime Library Exception discharges the duty for the
way we convey them — but the manifest records the exact GCC build behind every
one of them, and ``verify_gcc_runtime`` requires the tree to contain no
GPL-with-exception binary we have not identified. Identity is the GNU build-id,
not the filename: auditwheel renames these files per wheel build, and two
different distro builds of "GCC 8.5.0" are two different sources.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any, cast

# The manifest is JSON we author and review; a structural type would be more
# precise but would also duplicate the schema in two places. One alias, used
# everywhere, keeps pyright strict-clean without pretending to more static
# knowledge than a JSON file gives us.
JsonDict = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parent.parent

# Repo layout first, then the in-image layout the Dockerfile produces.
#
# The second candidate is written RELATIVE to this file (script at
# `<prefix>/tools/`, manifest at `<prefix>/licenses/`) rather than as a literal
# `/app/licenses/...`. It resolves to exactly `/app/licenses/...` inside the
# image — but, unlike an absolute path, it can also be exercised on a developer
# machine by laying out a scratch `<prefix>` and running the gate against it.
# An in-image-only code path is one that first gets tested in a Docker build,
# and the Docker registry is blocked in this project's dev container.
MANIFEST_CANDIDATES = (
    REPO_ROOT / "deploy" / "licenses" / "corresponding-source.json",
    REPO_ROOT / "licenses" / "corresponding-source.json",
)

FOUND = "found"
ABSENT = "absent"
BROKEN = "broken"


class ManifestError(RuntimeError):
    """The manifest is missing or malformed. Never soft-skipped: a gate whose
    input vanished must fail, not pass quietly."""


@dataclass(frozen=True)
class Detection:
    status: str  # FOUND | ABSENT | BROKEN
    version: str = ""
    detail: str = ""


def manifest_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise ManifestError(f"--manifest {explicit} does not exist")
        return explicit
    for candidate in MANIFEST_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise ManifestError(
        "no corresponding-source manifest found at "
        f"{[str(p) for p in MANIFEST_CANDIDATES]}. It pins the exact upstream "
        "source for the LGPL binaries we redistribute; without it the licence "
        "gate cannot tell whether a wheel bump has invalidated the written "
        "offer. See docs/LICENSING.md §7."
    )


def load_manifest(explicit: Path | None = None) -> JsonDict:
    path = manifest_path(explicit)
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - trivial
        raise ManifestError(f"{path}: not valid JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: expected a JSON object at the top level")
    manifest = cast(JsonDict, data)
    components = manifest.get("components")
    if not isinstance(components, list):
        raise ManifestError(f"{path}: expected an object with a 'components' list")
    for component in cast(list[JsonDict], components):
        for field in ("id", "version", "detect", "artefacts"):
            if field not in component:
                raise ManifestError(
                    f"{path}: component {component.get('id', '?')!r} is missing "
                    f"required field {field!r}"
                )
    _validate_gcc_runtime(path, manifest)
    manifest["_path"] = str(path)
    return manifest


def _validate_gcc_runtime(path: Path, manifest: JsonDict) -> None:
    """The LIC-4 block is required, not optional.

    Making it optional would mean a manifest that simply lost the section still
    passes the gate — and the section IS the record that every GPL-with-exception
    binary we ship has been identified. Absence must be loud.
    """
    block = manifest.get("gcc_runtime")
    if not isinstance(block, dict):
        raise ManifestError(
            f"{path}: no 'gcc_runtime' object. It records the decision about the "
            "GCC runtime libraries we redistribute and the exact GCC build behind "
            "each of them (LIC-4, docs/LICENSING.md §7.5); without it the gate "
            "cannot tell a known runtime from one a wheel bump slipped in."
        )
    gcc_runtime = cast(JsonDict, block)
    if not str(gcc_runtime.get("decision", "")).strip():
        raise ManifestError(f"{path}: gcc_runtime.decision is empty")
    files = gcc_runtime.get("files")
    if not isinstance(files, list):
        raise ManifestError(f"{path}: expected gcc_runtime.files to be a list")
    for record in cast(list[JsonDict], files):
        for field in ("library", "file", "sha256", "size", "gcc", "build_id"):
            if field not in record:
                raise ManifestError(
                    f"{path}: gcc_runtime file {record.get('file', '?')!r} is "
                    f"missing required field {field!r} (null is allowed for "
                    "build_id — some toolchains strip it — but the key is not)"
                )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
_SO_VERSION = re.compile(r"\.so\.(\d+(?:\.\d+)*)$")


def _detect_so_version(detect: JsonDict, roots: list[Path]) -> Detection:
    glob = detect.get("glob", "")
    if not glob:
        return Detection(BROKEN, detail="detect.glob is empty")
    names = sorted(
        {
            path.name
            for root in roots
            if root.exists()
            for path in root.rglob(glob)
            if path.is_file() and not path.is_symlink()
        }
    )
    if not names:
        return Detection(ABSENT, detail=f"no file matches {glob}")
    versions = {m.group(1) for name in names if (m := _SO_VERSION.search(name))}
    if not versions:
        return Detection(
            BROKEN,
            detail=(
                f"{len(names)} file(s) match {glob} but none carries a version "
                f"in its name (e.g. {names[0]}). The naming convention this "
                "check relies on has changed; re-derive the version by hand and "
                "fix the detector rather than deleting it."
            ),
        )
    if len(versions) > 1:
        return Detection(
            BROKEN,
            detail=(
                f"{glob} files disagree on their version: {sorted(versions)}. "
                "Two upstream releases are mixed in one environment."
            ),
        )
    return Detection(FOUND, versions.pop(), f"{len(names)} file(s) matching {glob}")


def _iter_dist_info(roots: list[Path]) -> Iterator[tuple[str, str, Path]]:
    for root in roots:
        if not root.exists():
            continue
        for meta in sorted(root.rglob("*.dist-info/METADATA")):
            parsed = BytesParser().parsebytes(meta.read_bytes(), headersonly=True)
            name = str(parsed.get("Name", "")).strip()
            version = str(parsed.get("Version", "")).strip()
            if name:
                yield name, version, meta.parent


def _normalise_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _detect_dist_info(detect: JsonDict, roots: list[Path]) -> Detection:
    wanted = _normalise_dist(detect.get("distribution", ""))
    if not wanted:
        return Detection(BROKEN, detail="detect.distribution is empty")
    for name, version, _ in _iter_dist_info(roots):
        if _normalise_dist(name) == wanted:
            if not version:
                return Detection(BROKEN, detail=f"{name} dist-info declares no Version")
            return Detection(FOUND, version, f"{name} dist-info METADATA")
    return Detection(ABSENT, detail=f"no dist-info for {detect['distribution']}")


def _detect_auditwheel_sbom(detect: JsonDict, roots: list[Path]) -> Detection:
    wanted_dist = _normalise_dist(detect.get("distribution", ""))
    wanted_component = detect.get("component", "")
    if not wanted_dist or not wanted_component:
        return Detection(
            BROKEN, detail="detect.distribution / detect.component is empty"
        )
    info_dirs = [
        info
        for name, _version, info in _iter_dist_info(roots)
        if _normalise_dist(name) == wanted_dist
    ]
    if not info_dirs:
        return Detection(ABSENT, detail=f"no dist-info for {detect['distribution']}")
    sboms = [p for info in info_dirs for p in sorted(info.glob("sboms/*.json"))]
    if not sboms:
        return Detection(
            BROKEN,
            detail=(
                f"{detect['distribution']} ships no auditwheel SBOM "
                f"({info_dirs[0]}/sboms/*.json). That SBOM is the only place the "
                f"real {wanted_component} source-package version is recorded — "
                "the SONAME is not it. Re-derive the version from the new wheel "
                "and fix this detector."
            ),
        )
    versions: set[str] = set()
    for sbom in sboms:
        try:
            data = json.loads(sbom.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return Detection(BROKEN, detail=f"{sbom}: not valid JSON")
        for component in data.get("components", []):
            if component.get("name") == wanted_component:
                version = str(component.get("version", "")).strip()
                if version:
                    versions.add(version)
    if not versions:
        return Detection(
            BROKEN,
            detail=(
                f"auditwheel SBOM lists no component named {wanted_component!r}. "
                "Either the wheel stopped vendoring it (drop the manifest entry) "
                "or it was renamed (fix the detector)."
            ),
        )
    if len(versions) > 1:
        return Detection(
            BROKEN, detail=f"SBOM disagrees on {wanted_component}: {sorted(versions)}"
        )
    return Detection(FOUND, versions.pop(), f"auditwheel SBOM ({sboms[0].name})")


_DETECTORS = {
    "so-version": _detect_so_version,
    "dist-info": _detect_dist_info,
    "auditwheel-sbom": _detect_auditwheel_sbom,
}


def detect_version(component: JsonDict, roots: list[Path]) -> Detection:
    detect: JsonDict = component.get("detect") or {}
    kind = str(detect.get("kind", ""))
    detector = _DETECTORS.get(kind)
    if detector is None:
        return Detection(
            BROKEN,
            detail=(
                f"unknown detect.kind {kind!r}; known kinds are {sorted(_DETECTORS)}"
            ),
        )
    return detector(detect, roots)


# ---------------------------------------------------------------------------
# The gate's question
# ---------------------------------------------------------------------------
def verify_versions(
    manifest: JsonDict, roots: list[Path]
) -> tuple[list[str], list[tuple[str, Detection]]]:
    """Return (failures, per-component detections).

    A failure here means the published written offer would describe source that
    does not correspond to the binaries — which is the whole obligation, not a
    bookkeeping detail.
    """
    failures: list[str] = []
    detections: list[tuple[str, Detection]] = []
    for component in cast(list[JsonDict], manifest["components"]):
        detection = detect_version(component, roots)
        detections.append((component["id"], detection))
        pinned = str(component["version"])
        if detection.status == BROKEN:
            failures.append(
                f"corresponding-source: cannot determine the shipped version of "
                f"{component['id']} ({component.get('name', '')}) — "
                f"{detection.detail}. A version we cannot read is a written "
                f"offer we cannot honour; fix the detector in "
                f"scripts/corresponding_source.py."
            )
        elif detection.status == FOUND and detection.version != pinned:
            failures.append(
                f"corresponding-source: {component['id']} "
                f"({component.get('name', '')}) is pinned at {pinned} in "
                f"{manifest.get('_path', 'the manifest')} but this environment "
                f"ships {detection.version} (via {detection.detail}). A wheel "
                f"bump moved it. Everything downstream is now WRONG: the "
                f"upstream URLs, the recorded checksums, and the §6(c) written "
                f"offer in deploy/licenses/CORRESPONDING-SOURCE.md all describe "
                f"source that does not correspond to these binaries. Re-pin the "
                f"manifest (new version, new URLs, new digests via "
                f"`just corresponding-source-record`) and re-read "
                f"docs/LICENSING.md §7 before publishing anything."
            )
    return failures, detections


# ---------------------------------------------------------------------------
# LIC-4 — the GCC runtime libraries
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GccRuntimeBinary:
    """A GPL-with-exception binary as found in the tree we are about to ship."""

    path: str
    library: str
    sha256: str
    size: int
    build_id: str = ""  # "" when the toolchain stripped the note
    comment: str = ""  # the .comment section's GCC string, when present

    @property
    def identity(self) -> str:
        return self.build_id or self.sha256


def _record_identity(record: JsonDict) -> str:
    build_id = record.get("build_id")
    return str(build_id) if build_id else str(record.get("sha256", ""))


def verify_gcc_runtime(
    manifest: JsonDict, observed: list[GccRuntimeBinary]
) -> tuple[list[str], list[str]]:
    """Every GCC runtime library in the tree must be one we have identified.

    Returns (failures, notes). The notes say what was MEASURED — which GCC
    builds are in this tree, and how many files each accounts for — because a
    bare "clean" from a gate like this is not checkable by a reader.

    A recorded file that is absent is not a failure (a wheel stopped vendoring
    it, the same lapse-of-obligation rule the components use). A file we did not
    record IS a failure: the decision in ``gcc_runtime.decision`` is about
    binaries we have looked at, and an unidentified one is outside it.
    """
    gcc_runtime = cast(JsonDict, manifest.get("gcc_runtime") or {})
    records = cast(list[JsonDict], gcc_runtime.get("files") or [])
    # A build-id maps to a LIST, not to one record: the same GCC build is
    # vendored into several wheels, so numpy's and scipy's copies of the el8
    # libgfortran are two distinct files sharing one build-id. Keying this on
    # identity alone silently made each of them look like a stale copy of the
    # other — caught by running the gate, which is why the self-test below
    # exists.
    by_identity: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        by_identity.setdefault(_record_identity(record), []).append(index)

    failures: list[str] = []
    matched: set[int] = set()
    identified = 0
    versions: dict[str, int] = {}
    for binary in observed:
        candidates = by_identity.get(binary.identity, [])
        found = next(
            (
                i
                for i in candidates
                if str(records[i].get("sha256")) == binary.sha256
                and int(records[i].get("size", -1)) == binary.size
            ),
            None,
        )
        record = None if found is None else records[found]
        if record is None and candidates:
            same_build = records[candidates[0]]
            failures.append(
                f"{binary.path}: matches the recorded build "
                f"{same_build.get('gcc')} by build-id, but no record has its "
                f"bytes (observed sha256={binary.sha256} size={binary.size}). "
                "The GCC build is unchanged, so this is a re-patched copy from a "
                "new wheel build: re-pin sha256/size in gcc_runtime.files so the "
                "record still describes THESE binaries."
            )
            continue
        if record is None:
            failures.append(
                f"{binary.path}: unidentified GCC runtime library. It is "
                "GPL-3.0 WITH the Runtime Library Exception, and Loft's position "
                "that the exception discharges the source duty (deploy/licenses/"
                "CORRESPONDING-SOURCE.md) is a statement about binaries we have "
                "identified — this one is not among them, so a wheel bump has "
                "changed the set. Derive its provenance and add a record to "
                "gcc_runtime.files in the manifest. Observed: build_id="
                f"{binary.build_id or '(none — key the record on sha256)'} "
                f"sha256={binary.sha256} size={binary.size}"
                + (f" comment={binary.comment!r}" if binary.comment else "")
                + ". Where to look: the .comment section above, the auditwheel "
                "SBOM in the vendoring wheel's dist-info/sboms/, and — when the "
                "filename carries a doubled hash tag — the wheel it was "
                "re-vendored from, whose own SBOM names the distro package. "
                "docs/LICENSING.md §7.5."
            )
            continue
        assert found is not None
        matched.add(found)
        identified += 1
        gcc = str(record.get("gcc", "?"))
        versions[gcc] = versions.get(gcc, 0) + 1

    notes: list[str] = []
    if observed or records:
        summary = ", ".join(f"GCC {v} ({n})" for v, n in sorted(versions.items()))
        notes.append(
            f"gcc-runtime: {identified}/{len(observed)} identified"
            + (f" — {summary}" if summary else "")
        )
    absent = [r for i, r in enumerate(records) if i not in matched]
    for record in absent:
        notes.append(
            f"gcc-runtime: {record.get('file')} recorded but absent here "
            "(a wheel stopped vendoring it — not a failure)"
        )
    return failures, notes
