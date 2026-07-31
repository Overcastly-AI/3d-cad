#!/usr/bin/env python3
"""Licence gate that reads the BINARIES WE SHIP, not package metadata.

Why this exists (LIC-3; docs/LICENSING.md)
------------------------------------------
This project's rule is absolute: **no GPL/AGPL dependencies**. Until
2026-07-31 that rule was enforced by review, i.e. by reading package metadata,
and the OCP wheel is the proof that this cannot work:

    cadquery_ocp_novtk-*.dist-info/METADATA : License: Apache-2.0
    cadquery_ocp_novtk.libs/libjbig-*.so.0  : "JBIG-KIT 2.1 ... Licence: GPL"

A metadata-only scan reports that tree as fully permissive. It is not. The
wheel vendors 90 shared libraries picked up from the build machine by
auditwheel, one of them GPL-2.0-or-later, hard-linked into every process that
imports the kernel. That is how LIC-1 survived to release week.

So this gate walks the actual `.so` files in the installed environment and
classifies each one from a written inventory, and it treats an UNKNOWN library
as a failure — because the vendored set is a property of somebody else's build
machine and changes without notice on any OCP/OCCT bump.

Two profiles
------------
``--profile source-env`` — the developer / CI virtualenv, which legitimately
still contains the GPL library, because the strip happens during the image
build. GPL entries are tolerated here **only** if the inventory marks them
``strip-in-image`` and names a strip script that actually targets them.

``--profile image`` — a built image (or any tree that is about to be
published). No GPL-family library may be present at all, except ones covered
by a redistribution exception. A ``strip-in-image`` entry must be either gone
or replaced by our GPL-free stub, identified by a marker string compiled into
it — which is what makes a silent regression impossible: if a future OCP bump
restores the real jbigkit, the marker is missing and the build fails.

What it checks, per file
------------------------
1. **Inventory classification.** Every loose shared library (i.e. not a
   ``*.cpython-*.so`` extension module) must have an entry below. Unknown
   name -> FAIL, with instructions.
2. **Self-identification.** The file's bytes are searched for GPL/LGPL licence
   strings. A binary that says "Licence: GPL" fails regardless of what the
   inventory or the wheel metadata claims. This is the independent signal: it
   would have caught libjbig with an empty inventory.
3. **ELF facts.** SONAME / DT_NEEDED / dynamic symbols are parsed here (no
   binutils dependency — the runtime image has no ``nm``), so the gate can
   assert that a stub really does satisfy its importer's undefined symbols.

Plus a metadata sweep over ``*.dist-info/METADATA`` — cheap, and it catches a
new *Python* GPL dependency that ships no binary at all. It is a supplement to
the binary scan, never a substitute for it.

Scope, stated honestly: this covers the Python environment WE assemble, which
is where every dependency decision of ours lands and where the P0 came from.
The Debian base layer (``python:3.12-slim-bookworm`` plus seven named apt
packages, all permissive — see deploy/docker/service.Dockerfile) is conveyed
as an upstream image and is not inventoried here.

Usage
-----
    python3 scripts/check-licences.py --profile source-env            # local venv
    python3 scripts/check-licences.py --profile image --root /app     # in-image
    python3 scripts/check-licences.py --self-test                     # prove it fails

Exit codes: 0 clean, 1 usage/internal error, 2 gate violated.
Stdlib only, no third-party imports: it runs inside the runtime image, which
has nothing but the service venv.
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Licence families
# ---------------------------------------------------------------------------
PERMISSIVE = "permissive"
LGPL = "lgpl"  # redistributable with duties (text + notice + source offer)
GPL = "gpl"  # forbidden by policy
GPL_WITH_EXCEPTION = "gpl-with-exception"  # GPL text + an exception that frees us

# Dispositions
SHIP = "ship"
STRIP_IN_IMAGE = "strip-in-image"


@dataclass(frozen=True)
class Entry:
    """One classified shared library.

    ``reason`` is mandatory for anything that is not plainly permissive: an
    allowlist entry without a written reason is how a gate rots into a
    rubber stamp.
    """

    licence: str
    family: str
    reason: str = ""
    disposition: str = SHIP
    # For strip-in-image entries: the script that must remove it, the marker
    # string its GPL-free replacement carries, and the symbol namespace the
    # replacement has to keep satisfying for its importers to link.
    strip_by: str = ""
    stub_marker: str = ""
    symbol_prefix: str = ""


# ---------------------------------------------------------------------------
# THE INVENTORY — every loose .so we ship, and why it is allowed.
#
# Keys are NORMALISED names (auditwheel's `-<8 hex>` tag and the version tail
# removed): `libjbig-0f1087b4.so.0` -> `libjbig`. A trailing `*` matches a
# prefix, used only where a whole upstream project ships many modules under one
# licence (OCCT's 68 libTK*).
# ---------------------------------------------------------------------------
INVENTORY: dict[str, Entry] = {
    # --- Open CASCADE Technology, via cadquery-ocp-novtk -------------------
    "libTK*": Entry(
        "LGPL-2.1-only WITH OCCT-exception-1.0",
        LGPL,
        reason=(
            "OCCT itself. LGPL-2.1 plus the Open CASCADE exception; "
            "we link dynamically and satisfy §6(b)(2) but NOT §6(b)(1) in an "
            "image, so we redistribute under §6(d)+(c): licence text and the "
            "OCCT exception text ship at /app/licenses/, NOTICE carries the "
            "prominent-notice sentence the exception requires, and corresponding "
            "source is offered. docs/LICENSING.md §2."
        ),
    ),
    # --- the GPL one. THIS is what LIC-1 removes. --------------------------
    "libjbig": Entry(
        "GPL-2.0-or-later",
        GPL,
        reason=(
            "jbigkit, vendored into the OCP wheel by auditwheel off an Ubuntu "
            "20.04 build machine. Reached only through libtiff's JBIG codec; "
            "Loft performs no TIFF I/O, so it is dead weight that would "
            "nonetheless make a published geometry image effectively GPL-2.0. "
            "Replaced during the image build by a GPL-free stub exporting the "
            "ten symbols libtiff imports. docs/LICENSING.md §4."
        ),
        disposition=STRIP_IN_IMAGE,
        strip_by="deploy/docker/licence/strip-gpl-jbig.sh",
        stub_marker="LOFT-GPL-FREE-JBIG-STUB",
        symbol_prefix="jbg_",
    ),
    # --- GPL text, but with an exception written for exactly our case ------
    "libgomp": Entry(
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        GPL_WITH_EXCEPTION,
        reason=(
            "GCC's OpenMP runtime. The GCC Runtime Library Exception exists "
            "precisely to let compiled output be redistributed under any "
            "licence; this is the one place where 'GPL' in a scan result is "
            "genuinely fine and must NOT be 'fixed'. docs/LICENSING.md §5."
        ),
    ),
    "libgfortran": Entry(
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        GPL_WITH_EXCEPTION,
        reason="GCC Fortran runtime; same Runtime Library Exception as libgomp.",
    ),
    "libquadmath": Entry(
        "GPL-3.0-or-later WITH GCC-exception-3.1",
        GPL_WITH_EXCEPTION,
        reason="GCC quad-precision math runtime; same Runtime Library Exception.",
    ),
    # --- dual-licensed: we ELECT the permissive/lesser arm and say so ------
    "libfreeimage": Entry(
        "FIPL-1.0",
        PERMISSIVE,
        reason=(
            "FreeImage is FIPL-1.0 OR GPL-2.0 OR GPL-3.0 at the recipient's "
            "choice; Loft elects FIPL-1.0 and ships its text. Silence is not an "
            "election, so NOTICE states it."
        ),
    ),
    "libfreetype": Entry(
        "FTL",
        PERMISSIVE,
        reason="FreeType is FTL OR GPL-2.0; Loft elects the FreeType Licence.",
    ),
    "libraw": Entry(
        "LGPL-2.1-only",
        LGPL,
        reason=(
            "LibRaw is LGPL-2.1 OR CDDL-1.0; Loft elects LGPL-2.1, which carries "
            "the same §6(d) duties as OCCT."
        ),
    ),
    "libzstd": Entry(
        "BSD-3-Clause",
        PERMISSIVE,
        reason="zstd is BSD-3-Clause OR GPL-2.0; Loft elects BSD-3-Clause.",
    ),
    # --- plainly permissive ------------------------------------------------
    "lib3mf": Entry("BSD-2-Clause", PERMISSIVE),
    "libHalf": Entry("BSD-3-Clause", PERMISSIVE),  # IlmBase / OpenEXR
    "libIex": Entry("BSD-3-Clause", PERMISSIVE),
    "libIlmImf": Entry("BSD-3-Clause", PERMISSIVE),
    "libIlmThread": Entry("BSD-3-Clause", PERMISSIVE),
    "libXau": Entry("MIT", PERMISSIVE),
    "libavif": Entry("BSD-2-Clause", PERMISSIVE),
    "libbrotlicommon": Entry("MIT", PERMISSIVE),
    "libbrotlidec": Entry("MIT", PERMISSIVE),
    "libfontconfig": Entry("MIT", PERMISSIVE),  # fontconfig's own MIT-style text
    "libharfbuzz": Entry("MIT", PERMISSIVE),  # "Old MIT"
    "libjpeg": Entry("IJG", PERMISSIVE),  # libjpeg-turbo / IJG
    "libjpegxr": Entry("BSD-2-Clause", PERMISSIVE),
    "libjxrglue": Entry("BSD-2-Clause", PERMISSIVE),
    "liblcms2": Entry("MIT", PERMISSIVE),
    "liblzma": Entry("0BSD", PERMISSIVE),
    "libopenjp2": Entry("BSD-2-Clause", PERMISSIVE),
    "libpng16": Entry("libpng-2.0", PERMISSIVE),
    "libscipy_openblas*": Entry("BSD-3-Clause", PERMISSIVE),
    "libsharpyuv": Entry("BSD-3-Clause", PERMISSIVE),
    "libtiff": Entry("libtiff", PERMISSIVE),
    "libuuid": Entry("BSD-3-Clause", PERMISSIVE),
    "libwebp": Entry("BSD-3-Clause", PERMISSIVE),
    "libwebpdemux": Entry("BSD-3-Clause", PERMISSIVE),
    "libwebpmux": Entry("BSD-3-Clause", PERMISSIVE),
    "libxcb": Entry("MIT", PERMISSIVE),
}

# Python distributions whose METADATA declares a copyleft licence and which are
# nonetheless allowed, each with a written reason. LGPL is allowed by policy
# (docs/RESEARCH.md §8) but is listed so the duties stay visible.
METADATA_ALLOWLIST: dict[str, str] = {
    "planegcs": (
        "LGPL-2.1-or-later. The 2D constraint solver (FreeCAD's PlaneGCS). "
        "Allowed by the LGPL-dynamic policy; called across a C-extension "
        "boundary with no headers incorporated. Duties: ship its LGPL text "
        "(its wheel does carry it), name it in NOTICE, offer source."
    ),
}

# Strings a binary uses to identify its own licence. The GPL pattern excludes
# "Lesser"/"Library" so LGPL notices do not trip it, and the SPDX-style
# "WITH ... exception" forms are handled by the inventory family, not here.
GPL_SIGNATURES = (
    re.compile(rb"GNU (?!Lesser |Library )General Public License"),
    re.compile(rb"Licen[cs]e: GPL"),
    re.compile(rb"SPDX-License-Identifier: (?:AGPL|GPL)-[0-9]"),
    re.compile(rb"GNU Affero General Public License"),
)
LGPL_SIGNATURES = (
    re.compile(rb"GNU (?:Lesser|Library) General Public License"),
    re.compile(rb"SPDX-License-Identifier: LGPL-[0-9]"),
)

_HASH_TAG = re.compile(r"-[0-9a-f]{8}(?=[-.])")
_SO_TAIL = re.compile(r"\.so.*$")
_VERSION_TAIL = re.compile(r"-[\d._]+$")


def normalise(filename: str) -> str:
    """`libjbig-0f1087b4.so.0` -> `libjbig`; `libIex-2_3-f9b27411.so.24` -> `libIex`."""
    name = _HASH_TAG.sub("", filename)
    name = _HASH_TAG.sub("", name)  # numpy double-tags: libgfortran-<h>-<h>.so
    name = _SO_TAIL.sub("", name)
    return _VERSION_TAIL.sub("", name)


def lookup(normalised: str) -> Entry | None:
    entry = INVENTORY.get(normalised)
    if entry is not None:
        return entry
    for key, candidate in INVENTORY.items():
        if key.endswith("*") and normalised.startswith(key[:-1]):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Minimal ELF64 reader — SONAME / DT_NEEDED / dynamic symbols.
#
# The runtime image is python:3.12-slim: no binutils, no `nm`, no `readelf`.
# The gate has to run THERE (that is the whole point of the image profile), so
# it parses the section headers itself. 64-bit little-endian only, which is
# what we ship; anything else is reported as unparsed rather than guessed at.
# ---------------------------------------------------------------------------
SHT_STRTAB = 3
SHT_DYNAMIC = 6
SHT_DYNSYM = 11
DT_NULL = 0
DT_NEEDED = 1
DT_SONAME = 14


@dataclass(frozen=True)
class Elf:
    soname: str
    needed: tuple[str, ...]
    defined: frozenset[str]
    undefined: frozenset[str]


def _cstr(blob: bytes, offset: int) -> str:
    end = blob.find(b"\0", offset)
    return blob[offset : end if end >= 0 else len(blob)].decode("utf-8", "replace")


def read_elf(data: bytes) -> Elf | None:
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return None
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    e_shentsize, e_shnum = struct.unpack_from("<HH", data, 0x3A)
    if e_shoff == 0 or e_shnum == 0:
        return None

    sections: list[tuple[int, int, int, int, int]] = []  # type, off, size, link, entsz
    for i in range(e_shnum):
        base = e_shoff + i * e_shentsize
        if base + 64 > len(data):
            return None
        sh_type = struct.unpack_from("<I", data, base + 4)[0]
        sh_offset, sh_size = struct.unpack_from("<QQ", data, base + 0x18)
        sh_link = struct.unpack_from("<I", data, base + 0x28)[0]
        (sh_entsize,) = struct.unpack_from("<Q", data, base + 0x38)
        sections.append((sh_type, sh_offset, sh_size, sh_link, sh_entsize))

    def strtab(index: int) -> bytes:
        if index >= len(sections):
            return b""
        sh_type, off, size, _, _ = sections[index]
        if sh_type != SHT_STRTAB:
            return b""
        return data[off : off + size]

    soname = ""
    needed: list[str] = []
    for sh_type, off, size, link, _ in sections:
        if sh_type != SHT_DYNAMIC:
            continue
        strings = strtab(link)
        for pos in range(off, off + size, 16):
            tag, val = struct.unpack_from("<qQ", data, pos)
            if tag == DT_NULL:
                break
            if tag == DT_NEEDED:
                needed.append(_cstr(strings, val))
            elif tag == DT_SONAME:
                soname = _cstr(strings, val)

    defined: set[str] = set()
    undefined: set[str] = set()
    for sh_type, off, size, link, entsize in sections:
        if sh_type != SHT_DYNSYM or entsize != 24:
            continue
        strings = strtab(link)
        for pos in range(off, off + size, 24):
            st_name = struct.unpack_from("<I", data, pos)[0]
            st_shndx = struct.unpack_from("<H", data, pos + 6)[0]
            if st_name == 0:
                continue
            name = _cstr(strings, st_name)
            (undefined if st_shndx == 0 else defined).add(name)

    return Elf(soname, tuple(needed), frozenset(defined), frozenset(undefined))


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    path: Path
    normalised: str
    entry: Entry | None
    elf: Elf | None
    says_gpl: bool
    says_lgpl: bool
    is_stub: bool


def is_extension_module(name: str) -> bool:
    """A CPython extension module belongs to a distribution; the metadata sweep
    covers those. The inventory is for LOOSE vendored libraries."""
    return ".cpython-" in name or ".abi3." in name or name.endswith(".pyd")


def scan_roots(roots: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.so*")):
            if not path.is_file() or path.is_symlink() or path in seen:
                continue
            seen.add(path)
            data = path.read_bytes()
            normalised = normalise(path.name)
            entry = None if is_extension_module(path.name) else lookup(normalised)
            findings.append(
                Finding(
                    path=path,
                    normalised=normalised,
                    entry=entry,
                    elf=read_elf(data),
                    says_gpl=any(p.search(data) for p in GPL_SIGNATURES),
                    says_lgpl=any(p.search(data) for p in LGPL_SIGNATURES),
                    is_stub=b"LOFT-GPL-FREE-JBIG-STUB" in data,
                )
            )
    return findings


def scan_metadata(roots: list[Path]) -> list[tuple[str, str, str]]:
    """(distribution, version, declared licence) for every installed wheel."""
    out: list[tuple[str, str, str]] = []
    for root in roots:
        for meta in sorted(root.rglob("*.dist-info/METADATA")):
            parsed = BytesParser().parsebytes(meta.read_bytes(), headersonly=True)
            name = str(parsed.get("Name", meta.parent.name))
            version = str(parsed.get("Version", "?"))
            declared = parsed.get("License-Expression") or parsed.get("License") or ""
            classifiers = [
                str(c)
                for c in (parsed.get_all("Classifier") or [])
                if str(c).startswith("License")
            ]
            licence = str(declared).strip() or "; ".join(classifiers) or "UNDECLARED"
            out.append((name, version, licence.replace("\n", " ")[:120]))
    return out


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def check(
    profile: str,
    roots: list[Path],
    quiet: bool = False,
    declared_licences: str = "",
) -> list[str]:
    failures: list[str] = []
    findings = scan_roots(roots)

    # A gate that scans nothing reports success. Every environment we ship has
    # compiled extension modules at minimum, so an empty scan means the root is
    # wrong — fail rather than emit a green that means nothing.
    if not findings:
        failures.append(
            f"no shared objects found under {[str(r) for r in roots]} — the scan "
            "found nothing to check, which is never a pass. Point --root at the "
            "installed environment."
        )

    by_norm: dict[str, Finding] = {}
    for finding in findings:
        name = finding.path.name
        entry = finding.entry

        # 1. every loose library must be classified
        if entry is None and not is_extension_module(name):
            failures.append(
                f"{finding.path}: UNCLASSIFIED shared library '{finding.normalised}'. "
                "The vendored set is a property of somebody else's build machine "
                "and changes without notice — add an INVENTORY entry to "
                "scripts/check-licences.py with its licence and a written reason, "
                "after checking what it actually is."
            )
            continue
        if entry is None:
            continue
        by_norm.setdefault(finding.normalised, finding)

        # 2. the binary's own words beat the inventory and the wheel metadata
        if finding.says_gpl and entry.family not in (GPL, GPL_WITH_EXCEPTION):
            failures.append(
                f"{finding.path}: the BINARY self-identifies as GPL/AGPL but the "
                f"inventory classifies '{finding.normalised}' as {entry.licence}. "
                "Re-check the upstream licence; the inventory is wrong or the "
                "library changed."
            )

        # 3. profile rules
        if entry.family == GPL and entry.disposition == STRIP_IN_IMAGE:
            if profile == "image":
                if finding.is_stub and not finding.says_gpl:
                    continue  # replaced by our GPL-free stub — the intended state
                failures.append(
                    f"{finding.path}: {entry.licence} library '{finding.normalised}' "
                    "is present in an image about to be published, and it is NOT "
                    f"our GPL-free replacement (marker '{entry.stub_marker}' "
                    f"absent). {entry.strip_by} did not run, or ran and did not "
                    "take. This is a licence violation, not a warning."
                )
            else:
                strip_script = REPO_ROOT / entry.strip_by
                if not strip_script.is_file():
                    failures.append(
                        f"{finding.path}: '{finding.normalised}' is tolerated here "
                        f"only because {entry.strip_by} removes it from the image, "
                        "and that script does not exist."
                    )
                elif finding.normalised not in strip_script.read_text():
                    failures.append(
                        f"{finding.path}: {entry.strip_by} does not mention "
                        f"'{finding.normalised}', so nothing removes it from the "
                        "image."
                    )
        elif entry.family == GPL:
            failures.append(
                f"{finding.path}: {entry.licence} — GPL-family libraries are "
                "forbidden by policy (CLAUDE.md, docs/RESEARCH.md §8) and this "
                "one has no disposition. Remove it or classify it."
            )

    # 4. a stub must still satisfy its importers' undefined symbols, or the
    #    image is a runtime ImportError waiting to happen.
    for finding in by_norm.values():
        entry = finding.entry
        if entry is None or not entry.symbol_prefix or not finding.is_stub:
            continue
        stub_elf = finding.elf
        if stub_elf is None:
            failures.append(f"{finding.path}: not a parseable ELF64 object")
            continue
        importers = 0
        for other in findings:
            if other.elf is None or stub_elf.soname not in other.elf.needed:
                continue
            importers += 1
            missing = sorted(
                s
                for s in other.elf.undefined
                if s.startswith(entry.symbol_prefix) and s not in stub_elf.defined
            )
            if missing:
                failures.append(
                    f"{other.path} imports {missing} from {stub_elf.soname}, which "
                    f"the replacement does not define — this image would fail at "
                    f"import with 'undefined symbol: {missing[0]}'."
                )
        if importers == 0:
            failures.append(
                f"{finding.path}: nothing DT_NEEDEDs {stub_elf.soname!r}. The stub "
                "exists to satisfy a real importer; if the importer is gone, drop "
                "the stub and the inventory entry instead of shipping a decoy."
            )

    # 4b. …and it must still be THERE. Deleting the GPL library instead of
    #     replacing it is the obvious "fix" and it does not work: the vendored
    #     libraries use eager binding, so the image dies at
    #     `undefined symbol: jbg_enc_out` on the first import.
    for normalised, entry in INVENTORY.items():
        if not entry.symbol_prefix or normalised in by_norm:
            continue
        orphaned = sorted(
            f.path.name
            for f in findings
            if f.elf and any(s.startswith(entry.symbol_prefix) for s in f.elf.undefined)
        )
        if orphaned:
            failures.append(
                f"{orphaned} import {entry.symbol_prefix}* symbols but nothing in "
                f"this tree provides '{normalised}'. It was deleted rather than "
                "replaced; the vendored libraries use eager binding, so this "
                "image fails at import."
            )

    # 5. metadata sweep (supplement, not substitute)
    distributions = scan_metadata(roots)
    for name, version, licence in distributions:
        blob = licence.encode()
        if not any(p.search(blob) for p in GPL_SIGNATURES) and not re.search(
            r"\b(?:A?GPL)-[0-9]", licence
        ):
            continue
        if re.search(r"\bLGPL", licence):
            continue
        if name.lower() in METADATA_ALLOWLIST:
            continue
        failures.append(
            f"{name} {version}: METADATA declares '{licence}' — GPL/AGPL Python "
            "dependencies are forbidden (CLAUDE.md). If this is wrong, add it to "
            "METADATA_ALLOWLIST with a written reason."
        )

    # 6. the OCI label must match what is actually in the image. An image that
    #    says `licenses=MIT` while carrying 47 LGPL-2.1 libraries is exactly the
    #    failure mode this whole file exists to prevent, one layer up.
    if declared_licences:
        # Both layers count: OCCT/LibRaw arrive as loose binaries, planegcs as
        # a wheel whose METADATA declares LGPL-2.1-or-later.
        ships_lgpl = any(
            f.entry is not None and f.entry.family == LGPL for f in findings
        ) or any(re.search(r"\bLGPL", lic) for _, _, lic in distributions)
        claims_lgpl = "LGPL" in declared_licences
        if ships_lgpl and not claims_lgpl:
            failures.append(
                f"org.opencontainers.image.licenses={declared_licences!r} but this "
                "image carries LGPL-2.1 libraries (OCCT / planegcs / LibRaw). The "
                "label is the only licence statement that travels with the "
                'artifact. Build with --build-arg IMAGE_LICENSES="MIT AND '
                'LGPL-2.1-or-later".'
            )
        elif claims_lgpl and not ships_lgpl:
            failures.append(
                f"org.opencontainers.image.licenses={declared_licences!r} claims "
                "LGPL but no LGPL library is present. Over-disclosure is a defect "
                "too: it tells users they have duties they do not have."
            )

    if not quiet:
        report(profile, roots, findings, failures)
    return failures


# ---------------------------------------------------------------------------
# Inventory emitted INTO the image (docs/LICENSING.md §6 "in every image")
# ---------------------------------------------------------------------------
def emit_inventory(dest: Path, roots: list[Path]) -> None:
    """Write THIRD-PARTY.md and copy every licence file the wheels ship.

    The wheels are the best source for their own licence text; the ones that
    ship none (the OCP wheel ships zero across 398 recorded files) are covered
    by the texts vendored in deploy/licenses/.
    """
    third_party = dest / "third-party"
    third_party.mkdir(parents=True, exist_ok=True)
    copied = 0
    for root in roots:
        for info in sorted(root.glob("*.dist-info")):
            candidates = [
                p
                for p in info.rglob("*")
                if p.is_file()
                and (
                    p.parent.name == "licenses"
                    or p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
                )
            ]
            if not candidates:
                continue
            out = third_party / info.name.split(".dist-info")[0]
            out.mkdir(parents=True, exist_ok=True)
            for src in candidates:
                (out / src.name).write_bytes(src.read_bytes())
                copied += 1

    findings = scan_roots(roots)
    lines = [
        "# Third-party components in this image",
        "",
        "Generated by `scripts/check-licences.py --emit-inventory` at image build",
        "time from the installed environment itself — not from a hand-maintained",
        "list. Full licence texts are in this directory and in `third-party/`.",
        "See the project's docs/LICENSING.md for the analysis behind each entry.",
        "",
        "## Bundled shared libraries",
        "",
        "| library | licence | note |",
        "| ------- | ------- | ---- |",
    ]
    # Grouped by INVENTORY key so OCCT's 68 modules are one row, not 68 copies
    # of the same 200-character note.
    seen: dict[str, tuple[Entry, int, bool]] = {}
    for finding in findings:
        entry = finding.entry
        if entry is None:
            continue
        key = next((k for k in INVENTORY if INVENTORY[k] is entry), finding.normalised)
        _, count, stub = seen.get(key, (entry, 0, False))
        seen[key] = (entry, count + 1, stub or finding.is_stub)
    for key in sorted(seen, key=str.lower):
        entry, count, stub = seen[key]
        licence = "MIT (Loft GPL-free stub)" if stub else entry.licence
        note = " ".join(entry.reason.split()) if entry.reason else ""
        if count > 1:
            note = f"{count} modules. {note}".strip()
        lines.append(f"| `{key}` | {licence} | {note} |")

    lines += [
        "",
        "## Python distributions",
        "",
        "| package | version | licence |",
        "| ------- | ------- | ------- |",
    ]
    for name, version, licence in sorted(scan_metadata(roots)):
        lines.append(f"| {name} | {version} | {licence} |")
    lines.append("")
    (dest / "THIRD-PARTY.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        f"check-licences: wrote {dest / 'THIRD-PARTY.md'} "
        f"({len(seen)} libraries) and copied {copied} wheel licence file(s)"
    )


def report(
    profile: str,
    roots: list[Path],
    findings: list[Finding],
    failures: list[str],
) -> None:
    loose = [f for f in findings if f.entry is not None]
    modules = len(findings) - len(loose)
    print(f"check-licences: profile={profile} roots={[str(r) for r in roots]}")
    print(
        f"  {len(loose)} classified shared libraries, "
        f"{modules} CPython extension modules"
    )
    families: dict[str, int] = {}
    for finding in loose:
        entry = finding.entry
        assert entry is not None
        families[entry.family] = families.get(entry.family, 0) + 1
    for family in sorted(families):
        print(f"  {family:<20} {families[family]}")
    for finding in loose:
        entry = finding.entry
        assert entry is not None
        if entry.family in (GPL, GPL_WITH_EXCEPTION) or finding.is_stub:
            state = "GPL-FREE STUB" if finding.is_stub else entry.licence
            print(f"  ! {finding.path.name}: {state}")
    for failure in failures:
        print(f"\nFAIL {failure}")
    verdict = f"FAILED — {len(failures)} violation(s)" if failures else "clean"
    print(f"\ncheck-licences: {verdict}")


# ---------------------------------------------------------------------------
# Self-test — a gate nobody has seen fail is not a gate.
# ---------------------------------------------------------------------------
def self_test(roots: list[Path]) -> int:
    """Run the image profile against the REAL GPL library and against the REAL
    stripped result, asserting the first fails and the second passes.

    Uses the actual production strip script, so it also proves that script
    still works against whatever the current wheel vendors.
    """
    originals = [
        p
        for root in roots
        for p in root.rglob("libjbig*.so*")
        if p.is_file() and b"JBIG-KIT" in p.read_bytes()
    ]
    if not originals:
        print(
            "self-test: no unstripped libjbig found under "
            f"{[str(r) for r in roots]} — nothing to prove the gate against.\n"
            "  (If the OCP wheel stopped vendoring jbigkit, delete this "
            "self-test together with the inventory entry.)",
            file=sys.stderr,
        )
        return 1
    original = originals[0]

    with tempfile.TemporaryDirectory() as tmp:
        negative = Path(tmp) / "negative" / "cadquery_ocp_novtk.libs"
        positive = Path(tmp) / "positive" / "cadquery_ocp_novtk.libs"
        negative.mkdir(parents=True)
        positive.mkdir(parents=True)
        # libtiff comes along so the stub's importer really exists in the tree:
        # the symbol-satisfaction check below is then a real assertion.
        copied = [original, *sorted(original.parent.glob("libtiff-*.so*"))]
        for src in copied:
            shutil.copy2(src, negative / src.name)
            shutil.copy2(src, positive / src.name)

        print("=== negative control: the real GPL library, image profile ===")
        bad = check("image", [negative.parent])
        if not bad:
            print("\nself-test FAILED: the gate PASSED a tree containing GPL jbigkit.")
            return 1
        if not any("libjbig" in f for f in bad):
            print("\nself-test FAILED: the gate failed, but not because of libjbig.")
            return 1

        print("\n=== applying the production strip script ===")
        script = REPO_ROOT / "deploy/docker/licence/strip-gpl-jbig.sh"
        proc = subprocess.run(  # fixed in-repo path, no user input
            ["/bin/sh", str(script), str(positive.parent), "--require"],
            capture_output=True,
            text=True,
            check=False,
        )
        print(proc.stdout.strip() or proc.stderr.strip())
        if proc.returncode != 0:
            print(f"\nself-test FAILED: strip script exited {proc.returncode}")
            return 1

        print("\n=== positive control: the stripped tree, image profile ===")
        good = check("image", [positive.parent])
        if good:
            print("\nself-test FAILED: the gate rejected a correctly stripped tree.")
            return 1

    print(
        "\nself-test PASSED: the gate FAILS on the vendored GPL library "
        f"({len(bad)} violation(s) naming libjbig) and PASSES once "
        "deploy/docker/licence/strip-gpl-jbig.sh has replaced it."
    )
    return 0


def default_roots(profile: str) -> list[Path]:
    if profile == "image":
        return [Path("/app/.venv")]
    venv = REPO_ROOT / ".venv"
    site = sorted(venv.glob("lib/python3.*/site-packages"))
    return site or [venv]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Licence gate over the shared objects we actually ship."
    )
    parser.add_argument(
        "--profile",
        choices=("source-env", "image"),
        default="source-env",
        help="source-env: the dev/CI venv (GPL allowed only if stripped in the "
        "image). image: a tree about to be published (no GPL at all).",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="tree to scan; repeatable. Defaults per profile.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="prove the gate can fail: run it against the real GPL library, "
        "then against the real stripped result.",
    )
    parser.add_argument(
        "--expect-licences",
        default="",
        help="the org.opencontainers.image.licenses value this image will "
        "carry; checked against what the scan actually finds.",
    )
    parser.add_argument(
        "--emit-inventory",
        type=Path,
        default=None,
        help="write THIRD-PARTY.md and copy wheel licence files into this "
        "directory (runs after the check, only if the check passes).",
    )
    args = parser.parse_args(argv)

    roots: list[Path] = args.root or default_roots(args.profile)
    if args.self_test:
        return self_test(roots)
    if check(args.profile, roots, declared_licences=args.expect_licences):
        return 2
    if args.emit_inventory is not None:
        emit_inventory(args.emit_inventory, roots)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
