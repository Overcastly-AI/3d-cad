# Corresponding source for the LGPL components in this image

This image bundles libraries covered by the GNU Lesser General Public License,
version 2.1. This file is the source-access statement that LGPL-2.1 §6
requires. The full analysis behind it is in the project's `docs/LICENSING.md`;
the short version is below, because obligations that live only in a document
nobody ships are not discharged.

## Which clause we are relying on, and why it is not §6(b)

§6(b) — "use a suitable shared library mechanism" — is the clause most people
assume covers a container image. It does not. Clause (1) of §6(b) requires the
library to be **"a copy of the library already present on the user's computer
system"**. In a container image it is our copy, shipped inside the artifact.
Dynamic linking is necessary for §6(b) but not sufficient.

We do satisfy §6(b) clause (2): every LGPL component here is loaded through an
ordinary shared-object mechanism and can be replaced. `OCP.cpython-*.so`
resolves the OCCT libraries through normal `DT_NEEDED` + `RUNPATH` lookup, and
`planegcs` is a CPython extension module imported at run time. Dropping in a
rebuilt, interface-compatible `libTKBRep.so` or a modified `planegcs` works
without touching Loft's code.

So we distribute under **§6(d)**: the image is offered from a designated place
(a container registry), and equivalent access to the corresponding source is
offered from the same place — backed by the **§6(c)** written offer below.

## The exact versions in this image

| component | version           | upstream source                                                                                             |
| --------- | ----------------- | ----------------------------------------------------------------------------------------------------------- |
| OCCT      | 7.9.3             | `https://github.com/Open-Cascade-SAS/OCCT`, tag `V7_9_3`, commit `a016080bf6738d6aeae020badee4e888ad1540a5` |
| planegcs  | 0.8.0             | PyPI sdist `planegcs-0.8.0.tar.gz` (`https://github.com/spookylukey/planegcs`)                              |
| LibRaw    | 0.19.5-1ubuntu1.4 | Ubuntu 20.04 source package `libraw` — `.orig.tar.gz` **and** `.debian.tar.xz`                              |
| FreeImage | 3.18.0            | Ubuntu 20.04 source package `libfreeimage`                                                                  |
| FreeType  | 2.10.1            | Ubuntu 20.04 source package `freetype`                                                                      |

OCCT, planegcs and LibRaw are the components with a source obligation. LibRaw
is LGPL-2.1 by our election (it is offered as LGPL-2.1 **or** CDDL-1.0), and it
is Ubuntu's build, so its corresponding source is upstream **plus the Ubuntu
patch series** — both are in the bundle. FreeImage and FreeType are shipped
under their permissive arms (FIPL-1.0 and FTL respectively) — their texts are
beside this file — so no source obligation attaches to them, and they are
listed only so the versions are on the record.

`corresponding-source.json` beside this file is the machine-readable pin: every
artefact's URL, its SHA-256, and a note on how that digest was established.
`THIRD-PARTY.md` is generated from the installed environment at image build
time and is the authoritative inventory of what is actually here.

These versions are not a hand-maintained claim: Loft's licence gate reads them
back out of the binaries in this image at build time and fails the build if
they disagree with the manifest, so an image whose OCCT moved cannot be
published carrying a stale offer.

## Where to get it (LGPL-2.1 §6(d))

The corresponding source for the three components above is mirrored as a single
archive, **`loft-corresponding-source-<version>.tar.gz`, attached to the same
GitHub release that published this image** — the same place, as §6(d) asks,
rather than a third-party URL that may be retired.

```sh
gh release download <version> --repo Overcastly-AI/3d-cad --pattern 'loft-corresponding-source-*'
tar xzf loft-corresponding-source-<version>.tar.gz
cd loft-corresponding-source-<version> && sha256sum -c SHA256SUMS
```

The archive carries its own `MANIFEST.md`, a `README.md` with relinking
instructions, and a copy of `corresponding-source.json` — so you can check the
digests against what the project committed to its repository, independently of
whatever you downloaded.

If you are looking at an image that was NOT published from a tagged release
(a local build, or one you built yourself), that asset will not exist. The
written offer below stands regardless, and Loft's own source — from which the
bundle is reproducible with `just corresponding-source` — is public.

## Written offer (LGPL-2.1 §6(c))

For a period of three years from the date this image was published, the Loft
project will give any third party, for a charge no more than the cost of
physically performing the distribution, a complete machine-readable copy of the
corresponding source for the LGPL-covered components listed above, together
with the object code and/or source code of Loft itself so that the components
may be relinked. Requests: open an issue at
`https://github.com/Overcastly-AI/3d-cad`.

Loft itself is MIT-licensed and its complete source is public at that URL, so
the relinking material is already available without a request.

## The GCC runtime libraries, and why no source is offered for them

This image also contains eight files that are GPL-3.0 **with** the GCC Runtime
Library Exception — `libgomp`, `libgfortran` and `libquadmath`, pulled in by
auditwheel when the OCP, numpy, scipy and scikit-learn wheels were built. No
corresponding source is offered for them. That is a decision, not an oversight,
and this is our reading of the licence rather than legal advice.

**The reasoning.** The exception's §1 says you may propagate "a work of Target
Code formed by combining the Runtime Library with Independent Modules, even if
such propagation would otherwise violate the terms of GPLv3", and that you "may
then convey such a combination under terms of your choice". Conveying object
code without corresponding source is exactly what would otherwise violate
GPLv3 (§6), so the grant reaches it — and "under terms of your choice" does not
sit alongside an inherited source duty. This image is that combination and
nothing else: those three libraries are here only because compiled extension
modules `DT_NEEDED` them, and those modules are Independent Modules under §0 —
they require the Runtime Library to run but are not based on it. Every one of
them was produced by an Eligible Compilation Process.

The thing the exception does not plainly cover is conveying a Runtime Library
**on its own**, detached from any Target Code. That is what a distribution does
when it ships `libgomp` as an installable package, and it is why distributions
publish GCC source; we are not disagreeing with them, we are doing a different
thing. If Loft ever publishes a runtime library as an artifact in its own right,
this analysis stops applying and the source duty is back.

**We identified them anyway.** A decision that turns on _which_ binaries these
are is only auditable if we say which binaries they are, so
`corresponding-source.json` beside this file records all eight individually:
GNU build-id, SHA-256, size, and the exact build of GCC each one came from,
with the evidence for it. The full GPL-3.0 text and the exception text are here
as `GPL-3.0.txt` and `GCC-RUNTIME-LIBRARY-EXCEPTION-3.1.txt`.

| file                                         | GCC build                                  | how we know                                         |
| -------------------------------------------- | ------------------------------------------ | --------------------------------------------------- |
| `cadquery_ocp_novtk.libs/libgomp-*.so.1.0.0` | conda-forge GCC **15.2.0** (build 19)      | its own `.comment` string                           |
| `scipy.libs/libgfortran-83c28eba.so.5.0.0`   | AlmaLinux 8 **gcc 8.5.0-28.el8_10.alma.1** | scipy's auditwheel SBOM                             |
| `scipy.libs/libquadmath-2284e583.so.0.0.0`   | AlmaLinux 8 **gcc 8.5.0-28.el8_10.alma.1** | scipy's auditwheel SBOM                             |
| `numpy.libs/libgfortran-83c28eba-*.so.5.0.0` | AlmaLinux 8 **gcc 8.5.0-28.el8_10.alma.1** | identical GNU build-id to scipy's copy              |
| `numpy.libs/libquadmath-2284e583-*.so.0.0.0` | AlmaLinux 8 **gcc 8.5.0-28.el8_10.alma.1** | identical GNU build-id to scipy's copy              |
| `scikit_learn.libs/libgomp-*.so.1.0.0`       | AlmaLinux 8 **gcc 8.5.0-28.el8_10.alma.1** | scikit-learn's auditwheel SBOM                      |
| `scipy.libs/libgfortran-040039e1-*.so.5.0.0` | CentOS 7 **libgfortran5 8.3.1-2.1.1.el7**  | the scipy-openblas32 wheel's SBOM, build-id-matched |
| `scipy.libs/libquadmath-96973f99-*.so.0.0.0` | CentOS 7 **libquadmath 4.8.5-44.el7**      | the scipy-openblas32 wheel's SBOM, build-id-matched |

If you read the exception more strictly than we do, that table tells you exactly
which source package to ask AlmaLinux, CentOS or conda-forge for. We do not
mirror them, and we deliberately do not substitute an upstream FSF tarball for
a distributor's build: for the seven distro files the corresponding source is
the source package **including its patch series**, and in one case — CentOS 7's
`8.3.1` — no upstream release of that version exists at all. Shipping
`gcc-8.3.0.tar.xz` and calling it corresponding source would be the same defect
as shipping LibRaw's `.orig` tarball without the Ubuntu patches.

These identifications are not a hand-maintained claim either: Loft's licence
gate reads the build-id out of every one of these binaries at build time and
fails the build if it finds a GCC runtime library this file does not account
for, so a wheel bump cannot quietly change the answer.

One deliberate difference from upstream: this image ships a **GPL-free
replacement** for `libjbig`, not jbigkit. It is original MIT work
(`deploy/docker/licence/jbig-stub.c` in the Loft repository) exporting the ten
`jbg_*` symbols `libtiff` imports; it contains no jbigkit code, so no jbigkit
source is owed or included.
