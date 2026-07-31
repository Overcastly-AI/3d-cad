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

| component | version | upstream source                                           |
| --------- | ------- | --------------------------------------------------------- |
| OCCT      | 7.9.3   | `https://github.com/Open-Cascade-SAS/OCCT` (tag `V7_9_3`) |
| planegcs  | 0.8.0   | `https://github.com/spookylukey/planegcs`                 |
| LibRaw    | 0.19.5  | Ubuntu 20.04 source package `libraw`                      |
| FreeImage | 3.18.0  | Ubuntu 20.04 source package `libfreeimage`                |
| FreeType  | 2.10.1  | Ubuntu 20.04 source package `freetype`                    |

OCCT and planegcs are the LGPL components. LibRaw is LGPL-2.1 by our election
(it is offered as LGPL-2.1 **or** CDDL-1.0). FreeImage and FreeType are shipped
under their permissive arms (FIPL-1.0 and FTL respectively) — their texts are
beside this file — so no source obligation attaches to them, and they are
listed only so the versions are on the record.

`THIRD-PARTY.md` in this directory is generated from the installed environment
at image build time and is the authoritative inventory of what is actually
here.

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

## What is NOT here, and is tracked

A **mirrored source bundle attached to the same release as the image** is the
strong reading of "equivalent access from the same place"; pointing at a third
party who may retire a URL is the weakest defensible one. Mirroring is tracked
as LIC-2 in the project backlog. Until it lands, the upstream URLs above plus
the written offer are what we rely on.
